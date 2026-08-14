from datetime import UTC, datetime

from cryptography.fernet import InvalidToken
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from helio.core.config import settings
from helio.core.crypto import decrypt, encrypt
from helio.db.models import System
from helio.ingestion.enphase_client import EnphaseClient

# Enphase refresh tokens are valid for 30 days from issue and rotate on every
# use, so a system that polls daily never gets close to expiry. Warn well before
# the deadline so an operator can reconnect after a long outage.
REFRESH_TOKEN_LIFETIME_DAYS = 30
REFRESH_TOKEN_WARN_AFTER_DAYS = 25

_DECRYPT_HINT = (
    "cannot be decrypted with the current FERNET_KEY. If the key was rotated or "
    "regenerated, restore the previous key or reconnect the Enphase account to "
    "store fresh tokens."
)
_MISSING_REFRESH_TOKEN = (
    "No Enphase refresh token available: none is stored for this system and "
    "ENPHASE_REFRESH_TOKEN is unset. Set ENPHASE_REFRESH_TOKEN in .env to "
    "bootstrap the first poll."
)


class TokenError(RuntimeError):
    """Raised when Enphase tokens are missing, malformed, or undecryptable."""


def _decrypt_column(value: str | None, label: str) -> str | None:
    """Decrypt a stored token column, treating an empty column as absent.

    Args:
        value: Ciphertext read off the systems row, or None.
        label: Human-readable token name used in the error message.

    Returns:
        The plaintext token, or None when nothing is stored.

    Raises:
        TokenError: If the stored value cannot be decrypted with FERNET_KEY.
    """
    if not value:
        return None
    try:
        return decrypt(value, settings.fernet_key)
    except (InvalidToken, ValueError, TypeError) as exc:
        raise TokenError(f"Stored Enphase {label} {_DECRYPT_HINT}") from exc


def load_tokens(system: System) -> tuple[str, str]:
    """Return the access and refresh tokens to use for this system.

    Tokens persisted on the row win over the .env values, which only serve to
    bootstrap the very first poll of a fresh install.

    Args:
        system: The system row to read tokens from.

    Returns:
        A (access_token, refresh_token) pair of plaintext tokens. The access
        token may be empty; it is replaced by the refresh call.

    Raises:
        TokenError: If a stored token cannot be decrypted, or if no refresh
            token exists in either the database or the environment.
    """
    access_token = _decrypt_column(system.enphase_access_token, "access token")
    refresh_token = _decrypt_column(system.enphase_refresh_token, "refresh token")

    access_token = access_token or settings.enphase_access_token
    refresh_token = refresh_token or settings.enphase_refresh_token
    if not refresh_token:
        raise TokenError(_MISSING_REFRESH_TOKEN)
    return access_token, refresh_token


async def save_tokens(
    session: AsyncSession,
    system: System,
    access_token: str,
    refresh_token: str,
) -> None:
    """Persist a rotated token pair, encrypted at rest.

    Committed on its own rather than alongside the rest of the poll: the
    refresh token Enphase just returned is the only one that still works, so
    rolling it back over an unrelated failure would lock the install out.

    Args:
        session: Async database session owning `system`.
        system: The system row to update.
        access_token: Freshly issued access token.
        refresh_token: Freshly issued refresh token.
    """
    system.enphase_access_token = encrypt(access_token, settings.fernet_key)
    system.enphase_refresh_token = encrypt(refresh_token, settings.fernet_key)
    system.token_updated_at = datetime.now(tz=UTC)
    await session.commit()
    logger.info("Enphase tokens persisted for system {}", system.enphase_system_id)


def refresh_token_age_warning(
    system: System, now: datetime | None = None
) -> str | None:
    """Describe how close the stored refresh token is to expiring.

    Args:
        system: The system row holding token_updated_at.
        now: Current time, injectable for tests. Defaults to UTC now.

    Returns:
        A warning message once the token is at least
        REFRESH_TOKEN_WARN_AFTER_DAYS old, else None. Also None when no
        rotation has been recorded yet, since its age is unknown.
    """
    stamped = system.token_updated_at
    if stamped is None:
        return None

    age_days = ((now or datetime.now(tz=UTC)) - stamped).days
    if age_days < REFRESH_TOKEN_WARN_AFTER_DAYS:
        return None

    remaining = max(0, REFRESH_TOKEN_LIFETIME_DAYS - age_days)
    return (
        f"Enphase refresh token is {age_days} days old and will expire in "
        f"{remaining} days. Reconnect the Enphase account before then or the "
        "daily poll will start failing."
    )


async def build_authenticated_client(
    session: AsyncSession, system: System
) -> EnphaseClient:
    """Build an Enphase client with a fresh access token, persisting the rotation.

    Args:
        session: Async database session owning `system`.
        system: The system row supplying the Enphase system ID and tokens.

    Returns:
        An EnphaseClient whose access token has just been refreshed.

    Raises:
        TokenError: If no usable refresh token can be loaded.
        ValueError: If the token response omits access_token.
        httpx.HTTPStatusError: If Enphase rejects the refresh.
    """
    access_token, refresh_token = load_tokens(system)

    warning = refresh_token_age_warning(system)
    if warning is not None:
        logger.warning("{}", warning)

    client = EnphaseClient(
        client_id=settings.enphase_client_id,
        client_secret=settings.enphase_client_secret,
        system_id=system.enphase_system_id,
        access_token=access_token,
        refresh_token=refresh_token,
    )
    await client.refresh_access_token()
    await save_tokens(session, system, client.access_token, client.refresh_token)
    return client
