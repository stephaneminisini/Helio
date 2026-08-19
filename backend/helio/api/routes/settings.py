from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from helio.api.schemas.settings import (
    SettingsCreate,
    SettingsResponse,
    SettingsUpdate,
)
from helio.core.config import settings
from helio.db.models import System
from helio.db.session import get_db

router = APIRouter()

# Fields an update may set back to null. Everywhere else a null has to be dropped:
# most of the nullable columns carry NOT NULL defaults, and the rest have never
# been clearable through this endpoint. baseline_pr is different because null is
# one of its two meaningful states - it means "measure the baseline from the
# system's own first year" - so an override the owner cannot undo would be a trap.
CLEARABLE_FIELDS = frozenset({"baseline_pr"})


def _to_response(system: System) -> SettingsResponse:
    """Serialise a system row plus the Enphase connection state.

    Whether Enphase is connected comes from the application configuration
    rather than the row, so it is merged in here for every endpoint.

    Args:
        system: The persisted system row.

    Returns:
        SettingsResponse for the given system.
    """
    return SettingsResponse.model_validate(system).model_copy(
        update={"enphase_connected": settings.enphase_configured}
    )


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db)) -> SettingsResponse:
    """Return the current system configuration.

    Args:
        db: Async database session (injected).

    Returns:
        SettingsResponse with system configuration.

    Raises:
        HTTPException: 404 if no system is configured.
    """
    system = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if system is None:
        raise HTTPException(status_code=404, detail="No system configured")
    return _to_response(system)


@router.post(
    "/settings",
    response_model=SettingsResponse,
    status_code=201,
    responses={409: {"description": "A system is already configured"}},
)
async def create_settings(
    payload: SettingsCreate,
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    """Create the system record for a fresh install.

    The product is single-system, so at most one row may exist. Note that
    latitude and longitude must be supplied for irradiance data to be
    collected at all; the ingestion layer skips the irradiance step without
    them, which leaves performance ratio unavailable.

    Args:
        payload: Validated request body; see SettingsCreate for required fields.
        db: Async database session (injected).

    Returns:
        SettingsResponse for the newly created system.

    Raises:
        HTTPException: 409 if a system is already configured, including when a
            concurrent request wins the race and the singleton index rejects
            this insert.
        RequestValidationError: 422 if the body is missing a required field or
            a value falls outside the bounds declared on SettingsCreate.
    """
    existing = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if existing is not None:
        logger.info(
            "POST /api/settings rejected: system {} already configured",
            existing.enphase_system_id,
        )
        raise HTTPException(status_code=409, detail="System already configured")

    # exclude_none is load-bearing: degradation_rate, warranty_degradation_rate,
    # energy_rate_per_kwh, energy_rate_currency and irradiance_source are NOT
    # NULL with column defaults, so an explicit null must be dropped rather than
    # written.
    system = System(**payload.model_dump(exclude_none=True))
    db.add(system)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        logger.warning(
            "Concurrent POST /api/settings lost the race (enphase_system_id={}): {}",
            payload.enphase_system_id,
            exc,
        )
        raise HTTPException(
            status_code=409, detail="System already configured"
        ) from exc
    await db.refresh(system)
    return _to_response(system)


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    payload: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    """Update the system configuration.

    Only the fields present in the request body are touched. A field sent as null
    is ignored unless it is one of CLEARABLE_FIELDS, so a client cannot null out a
    column that carries a NOT NULL default.

    Args:
        payload: Fields to update (all optional).
        db: Async database session (injected).

    Returns:
        Updated SettingsResponse.

    Raises:
        HTTPException: 404 if no system is configured.
        RequestValidationError: 422 if a value falls outside the bounds declared
            on SettingsUpdate.
    """
    system = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if system is None:
        raise HTTPException(status_code=404, detail="No system configured")

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None and field not in CLEARABLE_FIELDS:
            continue
        setattr(system, field, value)

    await db.commit()
    await db.refresh(system)
    return _to_response(system)
