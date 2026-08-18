from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.analytics.degradation import DAYS_PER_YEAR, measured_baseline_pr
from helio.db.models import (
    DailySummary,
    EnergyInterval,
    Irradiance,
    MonthlySummary,
    System,
)

# A month has to fall this far below the baseline curve to be called an anomaly.
# Named here because the whole point of the baseline work is that this number is
# meaningful: against an unreachable expected PR it was exceeded every month.
ANOMALY_DROP = 0.015


async def build_daily_summary(
    session: AsyncSession,
    system_id: int,
    day: date,
) -> DailySummary:
    """Aggregate energy_intervals for one day into a daily_summary row.

    Args:
        session: Active async database session.
        system_id: System to summarize.
        day: Date to summarize.

    Returns:
        The upserted DailySummary instance.

    Raises:
        ValueError: If the day argument is invalid.
    """
    next_day = day + timedelta(days=1)
    stmt = select(EnergyInterval).where(
        EnergyInterval.system_id == system_id,
        EnergyInterval.interval_start >= day,
        EnergyInterval.interval_start < next_day,
    )
    result = await session.execute(stmt)
    intervals = result.scalars().all()

    if not intervals:
        logger.warning("No intervals found for system={} day={}", system_id, day)

    total_wh = sum(float(iv.production_wh or 0) for iv in intervals)
    peak_wh = max((float(iv.production_wh or 0) for iv in intervals), default=0.0)
    peak_at = next(
        (
            iv.interval_start
            for iv in intervals
            if float(iv.production_wh or 0) == peak_wh
        ),
        None,
    )

    FULL_DAY_INTERVAL_COUNT = 88  # 96 intervals per day minus tolerance for edge hours

    existing = (
        await session.execute(
            select(DailySummary).where(
                DailySummary.system_id == system_id,
                DailySummary.day == day,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        row = DailySummary(
            system_id=system_id,
            day=day,
            production_kwh=Decimal(str(round(total_wh / 1000, 3))),
            peak_power_w=Decimal(str(round(peak_wh * 4, 1))),
            peak_power_at=peak_at,
            interval_count=len(intervals),
            is_complete=len(intervals) >= FULL_DAY_INTERVAL_COUNT,
        )
        session.add(row)
    else:
        existing.production_kwh = Decimal(str(round(total_wh / 1000, 3)))
        existing.peak_power_w = Decimal(str(round(peak_wh * 4, 1)))
        existing.peak_power_at = peak_at
        existing.interval_count = len(intervals)
        existing.is_complete = len(intervals) >= FULL_DAY_INTERVAL_COUNT
        row = existing

    await session.commit()
    logger.info(
        "Daily summary built for system={} day={} kwh={}",
        system_id,
        day,
        row.production_kwh,
    )
    return row


async def rebuild_all_summaries(
    session: AsyncSession,
    system: System,
) -> tuple[int, int]:
    """Rebuild every daily and monthly summary from the raw intervals.

    Useful after a backfill, or after fixing an aggregation bug: existing rows
    are upserted rather than deleted, so the operation is safe to repeat. Only
    days that actually have intervals are rebuilt.

    Args:
        session: Active async database session.
        system: The system to rebuild summaries for.

    Returns:
        Tuple of (days_rebuilt, months_rebuilt).
    """
    day_column = func.date(EnergyInterval.interval_start).label("day")
    days = (
        (
            await session.execute(
                select(day_column)
                .where(EnergyInterval.system_id == system.id)
                .distinct()
                .order_by(day_column)
            )
        )
        .scalars()
        .all()
    )

    if not days:
        logger.warning(
            "No intervals stored for system={} - nothing to rebuild", system.id
        )
        return 0, 0

    for day in days:
        await build_daily_summary(session, system.id, day)

    months = sorted({day.replace(day=1) for day in days})
    for month in months:
        await build_monthly_summary(session, system.id, month, system)

    # After the loop, not inside it: the baseline is measured from the first year
    # of monthly PRs, so nothing can be expected of any month until every month
    # exists. Doing it per month would leave the first year unexpected until a
    # second rebuild.
    await apply_expected_pr(session, system)

    logger.info(
        "Rebuilt {} daily and {} monthly summaries for system={}",
        len(days),
        len(months),
        system.id,
    )
    return len(days), len(months)


async def build_monthly_summary(
    session: AsyncSession,
    system_id: int,
    month: date,
    system: System,
) -> MonthlySummary:
    """Compute one month's production, theoretical yield and PR, and upsert it.

    Expected PR and the anomaly flag are deliberately not set here: they rest on
    a baseline measured across the whole series, so they cannot be decided from
    one month in isolation. Call apply_expected_pr afterwards, which every caller
    of this function does.

    Args:
        session: Active async database session.
        system_id: System to summarize.
        month: First day of the month to summarize.
        system: System ORM instance for size and install date.

    Returns:
        The upserted MonthlySummary instance.

    Raises:
        ValueError: If the month argument is not the first day of a month.
    """
    _, last_day = monthrange(month.year, month.month)
    month_end = date(month.year, month.month, last_day)

    daily_stmt = select(DailySummary).where(
        DailySummary.system_id == system_id,
        DailySummary.day >= month,
        DailySummary.day <= month_end,
    )
    daily_result = await session.execute(daily_stmt)
    daily_rows = daily_result.scalars().all()
    production_kwh = Decimal(str(sum(float(r.production_kwh or 0) for r in daily_rows)))

    irr_stmt = select(Irradiance).where(
        Irradiance.system_id == system_id,
        Irradiance.day >= month,
        Irradiance.day <= month_end,
    )
    irr_result = await session.execute(irr_stmt)
    irr_rows = irr_result.scalars().all()
    total_poa = sum(float(r.poa_kwh_m2 or 0) for r in irr_rows)

    system_size = float(system.system_size_kw or 0)
    theoretical_kwh = (
        Decimal(str(round(system_size * total_poa, 3))) if total_poa else None
    )

    performance_ratio = None
    if theoretical_kwh and float(theoretical_kwh) > 0:
        performance_ratio = Decimal(
            str(round(float(production_kwh) / float(theoretical_kwh), 4))
        )

    existing_monthly = (
        await session.execute(
            select(MonthlySummary).where(
                MonthlySummary.system_id == system_id,
                MonthlySummary.month == month,
            )
        )
    ).scalar_one_or_none()

    if existing_monthly is None:
        row = MonthlySummary(
            system_id=system_id,
            month=month,
            production_kwh=production_kwh,
            theoretical_kwh=theoretical_kwh,
            performance_ratio=performance_ratio,
        )
        session.add(row)
    else:
        existing_monthly.production_kwh = production_kwh
        existing_monthly.theoretical_kwh = theoretical_kwh
        existing_monthly.performance_ratio = performance_ratio
        row = existing_monthly

    await session.commit()
    logger.info(
        "Monthly summary built for system={} month={} PR={}",
        system_id,
        month,
        performance_ratio,
    )
    return row


async def apply_expected_pr(session: AsyncSession, system: System) -> int:
    """Set expected PR and the anomaly flag on every stored month.

    Expected PR is a property of the whole series rather than of one month: it
    rests on a baseline measured across the system's first year, which cannot be
    known while that year is still being built. Every month is therefore rewritten
    once the summaries exist, which also means a system crossing into its first
    full year picks expected PR up on its earlier months at the same time.

    A system with no baseline yet leaves expected_pr null and every month
    unflagged. That is deliberate: the alternative is inventing a standard, and an
    unreachable one flags every month for every system forever, which is what this
    replaced.

    Args:
        session: Active async database session.
        system: System whose months to rewrite; read for its id, install date,
            degradation rate and configured baseline.

    Returns:
        How many months were flagged as anomalous.
    """
    baseline = await measured_baseline_pr(session, system)
    rows = (
        (
            await session.execute(
                select(MonthlySummary)
                .where(MonthlySummary.system_id == system.id)
                .order_by(MonthlySummary.month)
            )
        )
        .scalars()
        .all()
    )

    deg_rate = float(system.degradation_rate or 0) / 100
    flagged = 0
    for row in rows:
        row.expected_pr = None
        row.is_anomaly = False
        row.anomaly_reason = None
        if baseline is None:
            continue

        years_since_install = (row.month - system.install_date).days / DAYS_PER_YEAR
        expected = round(baseline * (1 - deg_rate) ** years_since_install, 4)
        row.expected_pr = Decimal(str(expected))
        if row.performance_ratio is None:
            continue

        drop = expected - float(row.performance_ratio)
        if drop > ANOMALY_DROP:
            row.is_anomaly = True
            row.anomaly_reason = (
                f"PR {float(row.performance_ratio):.1%} is {drop:.1%} "
                f"below expected {expected:.1%}"
            )
            flagged += 1

    await session.commit()
    logger.info(
        "Expected PR applied for system={} baseline={} months={} flagged={}",
        system.id,
        baseline,
        len(rows),
        flagged,
    )
    return flagged
