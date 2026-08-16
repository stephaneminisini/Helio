from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.api.schemas.overview import ComparisonPair, OverviewResponse, YtdPoint
from helio.core.comparisons import pct_change
from helio.core.dates import (
    month_to_date,
    same_day_in_year,
    same_day_last_month,
    same_day_last_year,
    today,
)
from helio.db.models import DailySummary, System
from helio.db.session import get_db

router = APIRouter()


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
        current_kwh=current, prior_kwh=prior, pct_change=pct_change(current, prior)
    )


def _ytd_history(
    totals: dict[int, float], current_year: int, install_date: date
) -> list[YtdPoint]:
    """Build the year-to-date series, oldest year first.

    Args:
        totals: Production in kWh per year, already restricted to the 1 January
            to anchor-day window and already missing the years with no data.
        current_year: The year the anchor day falls in.
        install_date: When the system started producing.

    Returns:
        One YtdPoint per year present in `totals`, each carrying how the current
        year compares with it. The current year's own entry has no percentage,
        having nothing to compare against.
    """
    current_ytd = totals.get(current_year, 0.0)
    return [
        YtdPoint(
            year=year,
            production_kwh=round(total, 3),
            pct_change=(
                None if year == current_year else pct_change(current_ytd, total)
            ),
            is_partial=install_date > date(year, 1, 1),
        )
        for year, total in sorted(totals.items())
    ]


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
            ytd_history=[],
            best_day_kwh=None,
            best_day_date=None,
            all_time_kwh=0.0,
        )

    anchor = today()
    day_last_month = same_day_last_month(anchor)
    day_last_year = same_day_last_year(anchor)

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
    # One indexed sum per year the system has been installed, oldest first. A
    # 20-year-old system costs 20 small queries here, which is cheaper than the
    # SQL needed to group by year while keeping each window's end date exact.
    ytd_by_year: dict[int, float] = {}
    for year in range(system.install_date.year, anchor.year + 1):
        total = await get_period_kwh(date(year, 1, 1), same_day_in_year(anchor, year))
        if total is not None:
            ytd_by_year[year] = total
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
        ytd_history=_ytd_history(
            ytd_by_year, current_year=anchor.year, install_date=system.install_date
        ),
        best_day_kwh=float(best_row.production_kwh) if best_row else None,
        best_day_date=best_row.day if best_row else None,
        all_time_kwh=all_time_kwh,
    )
