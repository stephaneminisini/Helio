from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.db.models import MonthlySummary, System

# A year of monthly points is the least that averages the seasons out; below it
# a trend line mostly measures which months happen to be in the sample.
MIN_MONTHS_FOR_CONFIDENCE = 12
# The baseline window, for the same reason: Performance Ratio swings several
# points with cell temperature, so a shorter window measures whichever seasons
# the sample happens to cover rather than the system's own standard.
BASELINE_MONTHS = 12
DAYS_PER_YEAR = 365.25


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


async def measured_baseline_pr(
    session: AsyncSession,
    system: System,
) -> float | None:
    """Return the Performance Ratio this system should be measured against.

    A configured System.baseline_pr wins outright: that is the owner stating what
    their install was commissioned to achieve, which a commissioning report gives
    directly and which no amount of history should override.

    Otherwise the baseline is the system's own first BASELINE_MONTHS of measured
    PR, walked back up the degradation curve to the install date so that a
    (1 - rate) ** years curve built on it starts where the system started.
    Anchoring on the system's own output is the whole point: no array converts
    every watt of irradiance into metered AC energy, so a PR of 1.0 is
    unreachable and every month measured against it looks broken.

    Args:
        session: Active async database session.
        system: System to derive the baseline for; read for its id, install date,
            degradation rate and configured baseline.

    Returns:
        The expected PR at the install date, or None when the system has neither
        a configured baseline nor a full year of measured months, in which case
        there is no honest standard to compare it against yet.
    """
    if system.baseline_pr is not None:
        return float(system.baseline_pr)

    stmt = (
        select(MonthlySummary)
        .where(
            MonthlySummary.system_id == system.id,
            MonthlySummary.performance_ratio.is_not(None),
        )
        .order_by(MonthlySummary.month)
        .limit(BASELINE_MONTHS)
    )
    rows = (await session.execute(stmt)).scalars().all()
    if len(rows) < BASELINE_MONTHS:
        return None

    ratios = [float(row.performance_ratio) for row in rows]
    # The window's average belongs to the middle of the window rather than to the
    # install date, so it is de-degraded by its own mean age before being used as
    # the curve's starting point. The correction is small at ordinary degradation
    # rates, but it is what stops the baseline from sitting half a year low.
    mean_elapsed = sum(
        (row.month - system.install_date).days / DAYS_PER_YEAR for row in rows
    ) / len(rows)
    rate = float(system.degradation_rate or 0) / 100
    return sum(ratios) / len(ratios) / (1 - rate) ** mean_elapsed


async def estimate_lost_production(
    session: AsyncSession,
    system_id: int,
    rate_per_kwh: float,
) -> dict[str, float]:
    """Estimate total production lost due to actual PR falling below expected PR.

    Args:
        session: Active async database session.
        system_id: System to analyze.
        rate_per_kwh: Electricity rate per kWh, in the system's configured
            currency. Required rather than defaulted so the dollar figure can
            never rest on an unstated assumption.

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


async def project_future_efficiency(
    session: AsyncSession,
    system: System,
    years_ahead: int,
) -> dict:
    """Extrapolate the measured Performance Ratio trend into future years.

    The trend is a least-squares fit of every monthly Performance Ratio against
    the years elapsed since install. Using the whole series rather than its two
    endpoints keeps one unusual month from setting the slope. Each future year
    is reported at its mid-point, the value comparable to a yearly average.

    The projection is then compared against a warranted curve: the same
    (1 - rate) ** years shape the summarizer uses for expected PR, but anchored
    on this system's own fitted baseline and decayed at the warranty rate rather
    than the observed one. The first projected year to fall below that curve is
    reported, which is how a user learns whether the current trend is heading
    outside what the modules are warranted for.

    Args:
        session: Active async database session.
        system: System to project; read for its id, install date and warranty
            degradation rate.
        years_ahead: How many years past the last measured year to project.

    Returns:
        Dict with 'months_of_history' (int), 'annual_rate' (the PR fraction the
        fit loses per year, negative if the system is improving, None when no
        fit is possible), 'low_confidence' (bool), 'warranty_breach_year' (int
        or None) and 'years' (list of {'year': int, 'projected_pr': float}).
        annual_rate is a PR fraction per year, so it compares directly against
        a warranty threshold expressed in percent per year divided by 100.
    """
    stmt = (
        select(MonthlySummary)
        .where(
            MonthlySummary.system_id == system.id,
            MonthlySummary.performance_ratio.is_not(None),
        )
        .order_by(MonthlySummary.month)
    )
    rows = (await session.execute(stmt)).scalars().all()

    months = len(rows)
    # Two points spread over time are the minimum for a slope; anything less is
    # reported as no projection rather than as a flat line.
    no_projection = {
        "months_of_history": months,
        "annual_rate": None,
        "low_confidence": True,
        "warranty_breach_year": None,
        "years": [],
    }
    if months < 2:
        return no_projection

    elapsed = [(row.month - system.install_date).days / DAYS_PER_YEAR for row in rows]
    ratios = [float(row.performance_ratio) for row in rows]
    mean_elapsed = sum(elapsed) / months
    mean_ratio = sum(ratios) / months
    spread = sum((years - mean_elapsed) ** 2 for years in elapsed)
    if spread == 0:
        return no_projection

    slope = (
        sum(
            (years - mean_elapsed) * (ratio - mean_ratio)
            for years, ratio in zip(elapsed, ratios, strict=True)
        )
        / spread
    )
    baseline = mean_ratio - slope * mean_elapsed
    warranty_rate = float(system.warranty_degradation_rate) / 100

    projections = []
    breach_year = None
    for offset in range(1, years_ahead + 1):
        year = rows[-1].month.year + offset
        years_out = (date(year, 7, 1) - system.install_date).days / DAYS_PER_YEAR
        projected = max(0.0, baseline + slope * years_out)
        warranted = baseline * (1 - warranty_rate) ** years_out
        if breach_year is None and projected < warranted:
            breach_year = year
        projections.append({"year": year, "projected_pr": round(projected, 4)})

    return {
        "months_of_history": months,
        "annual_rate": round(-slope, 4),
        "low_confidence": months < MIN_MONTHS_FOR_CONFIDENCE,
        "warranty_breach_year": breach_year,
        "years": projections,
    }
