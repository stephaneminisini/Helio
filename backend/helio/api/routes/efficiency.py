from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.analytics.degradation import (
    calculate_annual_degradation,
    estimate_lost_production,
)
from helio.api.schemas.efficiency import (
    DegradationSummary,
    EfficiencyResponse,
    MonthlyPRPoint,
)
from helio.db.models import MonthlySummary, System
from helio.db.session import get_db

router = APIRouter()

WARRANTY_THRESHOLD_PER_YEAR = 0.007  # 0.7% annual degradation


@router.get("/efficiency", response_model=EfficiencyResponse)
async def get_efficiency(db: AsyncSession = Depends(get_db)) -> EfficiencyResponse:
    """Return performance ratio history and degradation metrics.

    Args:
        db: Async database session (injected).

    Returns:
        EfficiencyResponse with PR history and degradation summary.
    """
    system = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if system is None:
        return EfficiencyResponse(
            pr_history=[],
            degradation=DegradationSummary(
                annual_rates={},
                lost_kwh=0.0,
                lost_dollars=0.0,
                warranty_threshold=WARRANTY_THRESHOLD_PER_YEAR * 100,
                exceeds_warranty=False,
            ),
        )

    monthly = (
        (
            await db.execute(
                select(MonthlySummary)
                .where(MonthlySummary.system_id == system.id)
                .order_by(MonthlySummary.month)
            )
        )
        .scalars()
        .all()
    )

    pr_history = [
        MonthlyPRPoint(
            month=row.month,
            production_kwh=float(row.production_kwh or 0),
            performance_ratio=(
                float(row.performance_ratio) if row.performance_ratio else None
            ),
            expected_pr=float(row.expected_pr) if row.expected_pr else None,
            is_anomaly=row.is_anomaly,
        )
        for row in monthly
    ]

    annual_rates = await calculate_annual_degradation(db, system.id)
    lost = await estimate_lost_production(db, system.id)

    recent_years = sorted(annual_rates.keys())[-2:]
    exceeds = False
    if len(recent_years) == 2:
        drop = annual_rates[recent_years[-1]].get("annual_drop") or 0
        exceeds = drop > WARRANTY_THRESHOLD_PER_YEAR

    return EfficiencyResponse(
        pr_history=pr_history,
        degradation=DegradationSummary(
            annual_rates=annual_rates,
            lost_kwh=lost["lost_kwh"],
            lost_dollars=lost["lost_dollars"],
            warranty_threshold=WARRANTY_THRESHOLD_PER_YEAR * 100,
            exceeds_warranty=exceeds,
        ),
    )
