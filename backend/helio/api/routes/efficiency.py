from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.analytics.degradation import (
    calculate_annual_degradation,
    estimate_lost_production,
    measured_baseline_pr,
    project_future_efficiency,
)
from helio.api.schemas.efficiency import (
    DegradationSummary,
    EfficiencyResponse,
    MonthlyPRPoint,
    ProjectionSummary,
)
from helio.db.models import (
    DEFAULT_ENERGY_RATE_CURRENCY,
    DEFAULT_ENERGY_RATE_PER_KWH,
    DEFAULT_WARRANTY_DEGRADATION_RATE,
    MonthlySummary,
    System,
)
from helio.db.session import get_db

router = APIRouter()

# Far enough ahead to show where the trend is heading, short enough that the
# extrapolation is still worth reading.
PROJECTION_YEARS = 5


@router.get("/efficiency", response_model=EfficiencyResponse)
async def get_efficiency(db: AsyncSession = Depends(get_db)) -> EfficiencyResponse:
    """Return performance ratio history, degradation metrics and a projection.

    The warranty threshold and the energy rate come from the system record, so
    each install is measured against the warranty its modules actually carry and
    lost production is priced at the tariff the owner pays. The projection
    extends the measured trend PROJECTION_YEARS years past the last measured
    year, carrying its own confidence flag.

    Args:
        db: Async database session (injected).

    Returns:
        EfficiencyResponse with PR history, degradation summary and projection.
    """
    system = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if system is None:
        return EfficiencyResponse(
            pr_history=[],
            degradation=DegradationSummary(
                annual_rates={},
                lost_kwh=0.0,
                lost_dollars=0.0,
                warranty_threshold=float(DEFAULT_WARRANTY_DEGRADATION_RATE),
                exceeds_warranty=False,
                energy_rate_per_kwh=float(DEFAULT_ENERGY_RATE_PER_KWH),
                energy_rate_currency=DEFAULT_ENERGY_RATE_CURRENCY,
                baseline_pr=None,
                baseline_source="none",
            ),
            projection=ProjectionSummary(
                months_of_history=0,
                annual_rate=None,
                low_confidence=True,
                warranty_breach_year=None,
                years=[],
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
            anomaly_reason=row.anomaly_reason,
        )
        for row in monthly
    ]

    energy_rate = float(system.energy_rate_per_kwh)
    annual_rates = await calculate_annual_degradation(db, system.id)
    lost = await estimate_lost_production(db, system.id, energy_rate)
    projection = await project_future_efficiency(db, system, PROJECTION_YEARS)

    # Both the anomaly flags and the lost-production figure are measured against
    # this, so the client is told what it was and where it came from.
    baseline = await measured_baseline_pr(db, system)
    if baseline is None:
        baseline_source = "none"
    elif system.baseline_pr is not None:
        baseline_source = "configured"
    else:
        baseline_source = "measured"

    # The stored threshold is a percent per year; annual_drop is a difference of
    # Performance Ratio fractions, so the threshold is scaled to match.
    warranty_threshold = float(system.warranty_degradation_rate)
    recent_years = sorted(annual_rates.keys())[-2:]
    exceeds = False
    if len(recent_years) == 2:
        drop = annual_rates[recent_years[-1]].get("annual_drop") or 0
        exceeds = drop > warranty_threshold / 100

    return EfficiencyResponse(
        pr_history=pr_history,
        degradation=DegradationSummary(
            annual_rates=annual_rates,
            lost_kwh=lost["lost_kwh"],
            lost_dollars=lost["lost_dollars"],
            warranty_threshold=warranty_threshold,
            exceeds_warranty=exceeds,
            energy_rate_per_kwh=energy_rate,
            energy_rate_currency=system.energy_rate_currency,
            baseline_pr=round(baseline, 4) if baseline is not None else None,
            baseline_source=baseline_source,
        ),
        projection=ProjectionSummary(**projection),
    )
