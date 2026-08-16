from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.analytics.anomaly import flag_underperforming_panels
from helio.api.schemas.panels import PanelPoint, PanelsResponse
from helio.db.models import PollLog, System
from helio.db.session import get_db

DEFAULT_WINDOW_DAYS = 30
NO_SYSTEM_MESSAGE = (
    "No system is configured yet. Save your system details on the Setup tab, "
    "then per-panel data appears after the next daily poll."
)
NO_POLL_MESSAGE = (
    "No panel poll has run yet. Per-panel data appears after the first daily "
    "poll completes."
)
NO_READINGS_MESSAGE = (
    "The last panel poll stored no readings for this window. Widen the window "
    "with ?days= or wait for the next daily poll."
)

router = APIRouter()


async def _unavailable_reason(db: AsyncSession, system_id: int) -> str:
    """Explain an empty per-panel window using the most recent panels poll.

    A poll that recorded 'partial' already carries an owner-facing explanation
    (most often an Enphase plan without device-level access), so it is reused
    verbatim rather than restated here.

    Args:
        db: Active async database session.
        system_id: System the window was requested for.

    Returns:
        A sentence the UI can show in place of the heatmap.
    """
    last = (
        await db.execute(
            select(PollLog)
            .where(PollLog.system_id == system_id, PollLog.poll_type == "panels")
            .order_by(PollLog.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last is None:
        return NO_POLL_MESSAGE
    if last.error_message:
        return last.error_message
    return NO_READINGS_MESSAGE


@router.get("/panels", response_model=PanelsResponse)
async def get_panels(
    days: int = Query(
        DEFAULT_WINDOW_DAYS,
        ge=1,
        le=365,
        description="Length of the comparison window, in days, ending today.",
    ),
    db: AsyncSession = Depends(get_db),
) -> PanelsResponse:
    """Return per-panel production with the fleet average and outlier flags.

    Each panel is compared to the rest of the fleet over the window rather than
    to a nameplate rating, so shared conditions cancel out (BR-16). An empty
    fleet answers 200 with data_available false and a reason, because a panel
    heatmap that no install can populate is not an error.

    Args:
        days: Length of the comparison window, ending today.
        db: Async database session (injected).

    Returns:
        PanelsResponse with one entry per reporting panel, the fleet statistics
        they were judged against, and the window they cover.
    """
    window_end = date.today()
    window_start = window_end - timedelta(days=days - 1)

    system = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if system is None:
        return PanelsResponse(
            panels=[],
            fleet_average_wh=0.0,
            fleet_stdev_wh=0.0,
            window_start=window_start,
            window_end=window_end,
            data_available=False,
            unavailable_reason=NO_SYSTEM_MESSAGE,
        )

    fleet = await flag_underperforming_panels(db, system.id, window_start, window_end)
    return PanelsResponse(
        panels=[
            PanelPoint(
                panel_serial=panel.panel_serial,
                energy_wh=panel.energy_wh,
                normalized_efficiency=panel.normalized_efficiency,
                deviation_sigma=panel.deviation_sigma,
                is_underperforming=panel.is_underperforming,
            )
            for panel in fleet.panels
        ],
        fleet_average_wh=fleet.average_wh,
        fleet_stdev_wh=fleet.stdev_wh,
        window_start=window_start,
        window_end=window_end,
        data_available=bool(fleet.panels),
        unavailable_reason=(
            None if fleet.panels else await _unavailable_reason(db, system.id)
        ),
    )
