from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.db.models import MonthlySummary


async def calculate_annual_degradation(
    session: AsyncSession,
    system_id: int,
) -> dict[int, dict]:
    """Compute average annual Performance Ratio and year-over-year drop.

    Args:
        session: Active async database session.
        system_id: System to analyze.

    Returns:
        Dict keyed by year with 'avg_pr' (float) and 'annual_drop' (float or None
        for the first year).
    """
    stmt = (
        select(MonthlySummary)
        .where(
            MonthlySummary.system_id == system_id,
            MonthlySummary.performance_ratio.is_not(None),
        )
        .order_by(MonthlySummary.month)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    by_year: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        by_year[row.month.year].append(float(row.performance_ratio))

    output: dict[int, dict] = {}
    prev_avg: float | None = None
    for year in sorted(by_year):
        avg_pr = sum(by_year[year]) / len(by_year[year])
        annual_drop = round(prev_avg - avg_pr, 4) if prev_avg is not None else None
        output[year] = {
            "avg_pr": round(avg_pr, 4),
            "annual_drop": annual_drop,
        }
        prev_avg = avg_pr
    return output


async def estimate_lost_production(
    session: AsyncSession,
    system_id: int,
    rate_per_kwh: float = 0.15,
) -> dict[str, float]:
    """Estimate total production lost due to actual PR falling below expected PR.

    Args:
        session: Active async database session.
        system_id: System to analyze.
        rate_per_kwh: Electricity rate in dollars per kWh for dollar estimate.

    Returns:
        Dict with 'lost_kwh' (float) and 'lost_dollars' (float).
    """
    stmt = select(MonthlySummary).where(
        MonthlySummary.system_id == system_id,
        MonthlySummary.performance_ratio.is_not(None),
        MonthlySummary.expected_pr.is_not(None),
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    total_lost_kwh = 0.0
    for row in rows:
        pr = float(row.performance_ratio)
        expected = float(row.expected_pr)
        production = float(row.production_kwh or 0)
        if expected > 0 and pr < expected:
            lost_fraction = (expected - pr) / expected
            total_lost_kwh += production * lost_fraction

    return {
        "lost_kwh": round(total_lost_kwh, 1),
        "lost_dollars": round(total_lost_kwh * rate_per_kwh, 2),
    }
