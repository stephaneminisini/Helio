import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.api.schemas.auth import AuthorizeResponse, ConnectionStatus
from helio.core.config import settings
from helio.db.models import PollLog, System
from helio.db.session import get_db
from helio.ingestion.enphase_client import EnphaseClient, authorize_url
from helio.ingestion.tokens import refresh_token_age_warning, save_tokens

router = APIRouter(prefix="/auth/enphase", tags=["auth"])

MISSING_CREDENTIALS_DETAIL = (
    "Enphase client credentials are not configured. Set ENPHASE_CLIENT_ID and "
    "ENPHASE_CLIENT_SECRET in .env, then restart the API."
)


def _client_configured() -> bool:
    """Report whether the server holds an Enphase client ID and secret."""
    return bool(settings.enphase_client_id and settings.enphase_client_secret)


def _back_to_dashboard(result: str) -> RedirectResponse:
    """Send the browser back to the dashboard carrying the flow's outcome.

    Only a fixed result code travels in the URL; the dashboard owns the wording
    so nothing an external caller controls is ever echoed back to the user.

    Args:
        result: One of "connected", "denied", "exchange_failed",
            "not_configured", or "no_system".

    Returns:
        A redirect to the dashboard with the result in the query string.
    """
    base = settings.frontend_base_url.rstrip("/")
    return RedirectResponse(f"{base}/?enphase={result}")


@router.get("/authorize", response_model=AuthorizeResponse)
async def authorize() -> AuthorizeResponse:
    """Return the Enphase consent URL to send the user's browser to.

    Returns:
        AuthorizeResponse holding the consent URL. It carries the public client
        ID and the registered redirect URI, never the client secret.

    Raises:
        HTTPException: 503 if the server has no client ID or secret configured,
            since Enphase would reject the consent request.
    """
    if not _client_configured():
        logger.error(
            "GET /api/auth/enphase/authorize refused: {}", MISSING_CREDENTIALS_DETAIL
        )
        raise HTTPException(status_code=503, detail=MISSING_CREDENTIALS_DETAIL)
    return AuthorizeResponse(
        authorization_url=authorize_url(
            settings.enphase_client_id, settings.enphase_redirect_uri
        )
    )


@router.get("/callback", response_class=RedirectResponse)
async def callback(
    code: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Exchange the authorization code for tokens and store them encrypted.

    Enphase drives this endpoint through the browser, so every outcome is a
    redirect back to the dashboard rather than an error body. Tokens are only
    written once Enphase has returned a complete pair, so a rejected code
    leaves no partial credentials behind.

    Args:
        code: Single-use authorization code appended by Enphase.
        error: Error code Enphase appends when the user declines consent.
        db: Async database session (injected).

    Returns:
        A redirect to the dashboard carrying the outcome of the exchange.
    """
    if not _client_configured():
        logger.error("Enphase callback received but {}", MISSING_CREDENTIALS_DETAIL)
        return _back_to_dashboard("not_configured")

    if error or not code:
        logger.warning(
            "Enphase consent returned no usable code: {}", error or "code missing"
        )
        return _back_to_dashboard("denied")

    system = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if system is None:
        logger.warning("Enphase callback received before a system was configured")
        return _back_to_dashboard("no_system")

    client = EnphaseClient(
        client_id=settings.enphase_client_id,
        client_secret=settings.enphase_client_secret,
        system_id=system.enphase_system_id,
        access_token="",
        refresh_token="",
    )
    try:
        access_token, refresh_token = await client.authenticate(
            code, settings.enphase_redirect_uri
        )
    except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as exc:
        logger.error("Enphase code exchange failed, nothing stored: {}", exc)
        return _back_to_dashboard("exchange_failed")

    await save_tokens(db, system, access_token, refresh_token)
    logger.info("Enphase account connected for system {}", system.enphase_system_id)
    return _back_to_dashboard("connected")


@router.get("/status", response_model=ConnectionStatus)
async def connection_status(db: AsyncSession = Depends(get_db)) -> ConnectionStatus:
    """Report whether the Enphase account is connected and when it last polled.

    Args:
        db: Async database session (injected).

    Returns:
        ConnectionStatus, which by construction carries no token or secret.
    """
    system = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if system is None:
        return ConnectionStatus(connected=False, client_configured=_client_configured())

    last_poll = (
        await db.execute(
            select(func.max(PollLog.completed_at)).where(
                PollLog.system_id == system.id, PollLog.status == "success"
            )
        )
    ).scalar()
    return ConnectionStatus(
        connected=bool(system.enphase_refresh_token),
        client_configured=_client_configured(),
        token_updated_at=system.token_updated_at,
        last_successful_poll_at=last_poll,
        token_warning=refresh_token_age_warning(system),
    )
