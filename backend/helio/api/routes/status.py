from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.api.schemas.status import BackfillStatus, PollLogEntry, StatusResponse
from helio.core.config import settings
from helio.db.models import DailySummary, MonthlySummary, PollLog, System
from helio.db.session import get_db
from helio.ingestion.backfill import backfill, progress

router = APIRouter()

# NRELClient returns 30-year TMY annual averages and ignores the requested date,
# so only NASA POWER supports a literal per-day weather normalization claim.
WEATHER_NORMALIZED_SOURCES = frozenset({"nasa"})


def _current_backfill_status() -> BackfillStatus:
    """Snapshot the module-level backfill progress counters.

    Returns:
        BackfillStatus for the most recent or in-flight run.
    """
    return BackfillStatus(
        running=progress.running,
        total_days=progress.total_days,
        completed_days=progress.completed_days,
        failed_days=progress.failed_days,
        error=progress.error,
    )


@router.get("/status", response_model=StatusResponse)
async def get_status(db: AsyncSession = Depends(get_db)) -> StatusResponse:
    """Report how far ingestion has got, including nothing at all.

    Every other endpoint answers with zeros whether the system is unconfigured,
    freshly deployed, or failing to authenticate. This one distinguishes them.

    Args:
        db: Async database session (injected).

    Returns:
        StatusResponse describing configuration, data coverage, the last poll,
        and backfill progress.
    """
    system = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if system is None:
        return StatusResponse(
            configured=False,
            location_configured=False,
            install_date=None,
            first_day=None,
            last_day=None,
            days_with_data=0,
            days_expected=0,
            missing_days=0,
            months_with_data=0,
            irradiance_source=None,
            weather_normalized=False,
            last_poll=None,
            backfill=_current_backfill_status(),
        )

    first_day, last_day, days_with_data = (
        await db.execute(
            select(
                func.min(DailySummary.day),
                func.max(DailySummary.day),
                func.count(DailySummary.id),
            ).where(DailySummary.system_id == system.id)
        )
    ).one()

    months_with_data = (
        await db.execute(
            select(func.count(MonthlySummary.id)).where(
                MonthlySummary.system_id == system.id
            )
        )
    ).scalar_one()

    last_poll = (
        await db.execute(
            select(PollLog)
            .where(PollLog.system_id == system.id)
            .order_by(PollLog.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    # Today is still in progress, so a complete history ends yesterday.
    yesterday = date.today() - timedelta(days=1)
    days_expected = max(0, (yesterday - system.install_date).days + 1)

    return StatusResponse(
        configured=True,
        location_configured=system.latitude is not None
        and system.longitude is not None,
        install_date=system.install_date,
        first_day=first_day,
        last_day=last_day,
        days_with_data=days_with_data or 0,
        days_expected=days_expected,
        missing_days=max(0, days_expected - (days_with_data or 0)),
        months_with_data=months_with_data or 0,
        # Ingestion reads IRRADIANCE_SOURCE from the environment, not the systems
        # row, so the environment value is the only honest thing to report here.
        irradiance_source=settings.irradiance_source,
        weather_normalized=settings.irradiance_source in WEATHER_NORMALIZED_SOURCES,
        last_poll=(
            PollLogEntry.model_validate(last_poll) if last_poll is not None else None
        ),
        backfill=_current_backfill_status(),
    )


@router.post("/backfill", response_model=BackfillStatus, status_code=202)
async def start_backfill(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> BackfillStatus:
    """Start a historical backfill in the background.

    Args:
        background_tasks: FastAPI background task registry (injected).
        db: Async database session (injected).

    Returns:
        BackfillStatus for the run that was just queued. Poll GET /api/status
        for progress.

    Raises:
        HTTPException: 404 if no system is configured, 409 if a backfill is
            already running.
    """
    system = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if system is None:
        raise HTTPException(status_code=404, detail="No system configured")
    if progress.running:
        raise HTTPException(status_code=409, detail="A backfill is already running")

    background_tasks.add_task(backfill)
    return BackfillStatus(
        running=True, total_days=0, completed_days=0, failed_days=0, error=None
    )
