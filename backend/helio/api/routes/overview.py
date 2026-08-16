from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.api.schemas.overview import ComparisonPair, OverviewResponse
from helio.core.dates import (
    month_to_date,
    same_day_last_month,
    same_day_last_year,
    today,
)
from helio.db.models import DailySummary, System
from helio.db.session import get_db

router = APIRouter()


def _pct_change(current: float, prior: float | None) -> float | None:
    """Compute percentage change from prior to current.

    Args:
        current: Current period value.
        prior: Prior period value (may be None or zero).

    Returns:
        Percentage change rounded to 1 decimal, or None if prior is unavailable.
    """
    if prior is None or prior == 0:
        return None
    return round((current - prior) / prior * 100, 1)


def _pair(current: float, prior: float | None) -> ComparisonPair:
    """Pair a current total with its prior counterpart.

    Args:
        current: Production for the current period, in kWh.
        prior: Production for the equivalent prior period, or None when nothing
            is stored for it.

    Returns:
        A ComparisonPair whose pct_change is None unless the prior side is a
        usable non-zero figure, so an unmeasured period reads as unknown rather
        than as a 100 percent improvement.
    """
    return ComparisonPair(
        current_kwh=current, prior_kwh=prior, pct_change=_pct_change(current, prior)
    )


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(db: AsyncSession = Depends(get_db)) -> OverviewResponse:
    """Return today's production and historical comparisons.

    Args:
        db: Async database session (injected).

    Returns:
        OverviewResponse with today's stats and period comparisons.
    """
    system = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if system is None:
        return OverviewResponse(
            today=today(),
            today_kwh=0.0,
            current_power_w=None,
            day_comparison=_pair(0.0, None),
            day_vs_last_month=_pair(0.0, None),
            month_comparison=_pair(0.0, None),
            month_vs_last_year=_pair(0.0, None),
            ytd_comparison=_pair(0.0, None),
            best_day_kwh=None,
            best_day_date=None,
            all_time_kwh=0.0,
        )

    anchor = today()
    day_last_month = same_day_last_month(anchor)
    day_last_year = same_day_last_year(anchor)
    year_start = anchor.replace(month=1, day=1)

    async def get_day_kwh(d: date) -> float | None:
        row = (
            await db.execute(
                select(DailySummary).where(
                    DailySummary.system_id == system.id,
                    DailySummary.day == d,
                )
            )
        ).scalar_one_or_none()
        return float(row.production_kwh or 0) if row else None

    async def get_period_kwh(start: date, end: date) -> float | None:
        """Sum production over an inclusive window, or None when it has no data.

        A window with no stored days sums to SQL NULL, which must stay distinct
        from a real zero so the comparison can say "unknown" instead of "none".
        """
        result = await db.execute(
            select(func.sum(DailySummary.production_kwh)).where(
                DailySummary.system_id == system.id,
                DailySummary.day >= start,
                DailySummary.day <= end,
            )
        )
        total = result.scalar()
        return float(total) if total is not None else None

    # SQLAlchemy AsyncSession is not safe for concurrent use; queries run sequentially
    today_kwh_raw = await get_day_kwh(anchor)
    last_month_day_kwh = await get_day_kwh(day_last_month)
    last_year_day_kwh = await get_day_kwh(day_last_year)
    # Every prior period stops at the equivalent day of the month, so a
    # month-to-date figure is never compared against a full month it cannot
    # have caught up with yet.
    this_month = await get_period_kwh(*month_to_date(anchor))
    last_month = await get_period_kwh(*month_to_date(day_last_month))
    month_last_year = await get_period_kwh(*month_to_date(day_last_year))
    this_ytd = await get_period_kwh(year_start, anchor)
    last_ytd = await get_period_kwh(
        year_start.replace(year=year_start.year - 1), day_last_year
    )
    best_result = await db.execute(
        select(DailySummary)
        .where(DailySummary.system_id == system.id)
        .order_by(DailySummary.production_kwh.desc())
        .limit(1)
    )
    all_time_result = await db.execute(
        select(func.sum(DailySummary.production_kwh)).where(
            DailySummary.system_id == system.id
        )
    )

    today_kwh = today_kwh_raw if today_kwh_raw is not None else 0.0
    best_row = best_result.scalar_one_or_none()
    all_time_kwh = float(all_time_result.scalar() or 0)

    return OverviewResponse(
        today=anchor,
        today_kwh=today_kwh,
        current_power_w=None,
        day_comparison=_pair(today_kwh, last_year_day_kwh),
        day_vs_last_month=_pair(today_kwh, last_month_day_kwh),
        month_comparison=_pair(this_month or 0.0, last_month),
        month_vs_last_year=_pair(this_month or 0.0, month_last_year),
        ytd_comparison=_pair(this_ytd or 0.0, last_ytd),
        best_day_kwh=float(best_row.production_kwh) if best_row else None,
        best_day_date=best_row.day if best_row else None,
        all_time_kwh=all_time_kwh,
    )
