from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.api.schemas.settings import (
    SettingsCreate,
    SettingsResponse,
    SettingsUpdate,
)
from helio.db.models import System
from helio.db.session import get_db

router = APIRouter()


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
    return SettingsResponse.model_validate(system)


@router.post("/settings", response_model=SettingsResponse, status_code=201)
async def create_settings(
    payload: SettingsCreate,
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    """Create the single system record for a fresh install.

    Args:
        payload: System configuration; enphase_system_id and install_date required.
        db: Async database session (injected).

    Returns:
        SettingsResponse for the newly created system.

    Raises:
        HTTPException: 409 if a system is already configured.
    """
    existing = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="System already configured")

    system = System(**payload.model_dump(exclude_none=True))
    db.add(system)
    await db.commit()
    await db.refresh(system)
    return SettingsResponse.model_validate(system)


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    payload: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    """Update the system configuration.

    Args:
        payload: Fields to update (all optional).
        db: Async database session (injected).

    Returns:
        Updated SettingsResponse.

    Raises:
        HTTPException: 404 if no system is configured.
    """
    system = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if system is None:
        raise HTTPException(status_code=404, detail="No system configured")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(system, field, value)

    await db.commit()
    await db.refresh(system)
    return SettingsResponse.model_validate(system)
