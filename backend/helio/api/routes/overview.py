from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.api.schemas.overview import ComparisonPair, OverviewResponse
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
            today=date.today(),
            today_kwh=0.0,
            current_power_w=None,
            day_comparison=ComparisonPair(
                current_kwh=0.0, prior_kwh=None, pct_change=None
            ),
            month_comparison=ComparisonPair(
                current_kwh=0.0, prior_kwh=None, pct_change=None
            ),
            ytd_comparison=ComparisonPair(
                current_kwh=0.0, prior_kwh=None, pct_change=None
            ),
            best_day_kwh=None,
            best_day_date=None,
            all_time_kwh=0.0,
        )

    today = date.today()
    same_day_lyr = today - timedelta(days=365)
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    async def get_day_kwh(d: date) -> float:
        row = (
            await db.execute(
                select(DailySummary).where(
                    DailySummary.system_id == system.id,
                    DailySummary.day == d,
                )
            )
        ).scalar_one_or_none()
        return float(row.production_kwh or 0) if row else 0.0

    async def get_period_kwh(start: date, end: date) -> float:
        result = await db.execute(
            select(func.sum(DailySummary.production_kwh)).where(
                DailySummary.system_id == system.id,
                DailySummary.day >= start,
                DailySummary.day <= end,
            )
        )
        return float(result.scalar() or 0)

    today_kwh = await get_day_kwh(today)
    lyr_day_kwh = await get_day_kwh(same_day_lyr)
    this_month = await get_period_kwh(month_start, today)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month = await get_period_kwh(last_month_start, last_month_end)
    this_ytd = await get_period_kwh(year_start, today)
    last_ytd = await get_period_kwh(
        year_start.replace(year=year_start.year - 1), same_day_lyr
    )

    best = (
        await db.execute(
            select(DailySummary)
            .where(DailySummary.system_id == system.id)
            .order_by(DailySummary.production_kwh.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    all_time_result = await db.execute(
        select(func.sum(DailySummary.production_kwh)).where(
            DailySummary.system_id == system.id
        )
    )
    all_time_kwh = float(all_time_result.scalar() or 0)

    return OverviewResponse(
        today=today,
        today_kwh=today_kwh,
        current_power_w=None,
        day_comparison=ComparisonPair(
            current_kwh=today_kwh,
            prior_kwh=lyr_day_kwh if lyr_day_kwh else None,
            pct_change=_pct_change(today_kwh, lyr_day_kwh),
        ),
        month_comparison=ComparisonPair(
            current_kwh=this_month,
            prior_kwh=last_month if last_month else None,
            pct_change=_pct_change(this_month, last_month),
        ),
        ytd_comparison=ComparisonPair(
            current_kwh=this_ytd,
            prior_kwh=last_ytd if last_ytd else None,
            pct_change=_pct_change(this_ytd, last_ytd),
        ),
        best_day_kwh=float(best.production_kwh) if best else None,
        best_day_date=best.day if best else None,
        all_time_kwh=all_time_kwh,
    )
