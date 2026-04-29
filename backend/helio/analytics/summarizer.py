from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.db.models import (
    DailySummary,
    EnergyInterval,
    Irradiance,
    MonthlySummary,
    System,
)


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


async def build_monthly_summary(
    session: AsyncSession,
    system_id: int,
    month: date,
    system: System,
) -> MonthlySummary:
    """Compute monthly PR and expected PR, upsert into monthly_summaries.

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

    years_since_install = (
        (month - system.install_date).days / 365.25 if system.install_date else 0
    )
    deg_rate = float(system.degradation_rate or 0) / 100
    expected_pr = Decimal(str(round((1 - deg_rate) ** years_since_install, 4)))

    is_anomaly = False
    anomaly_reason = None
    if performance_ratio and expected_pr:
        drop = float(expected_pr) - float(performance_ratio)
        if drop > 0.015:
            is_anomaly = True
            anomaly_reason = (
                f"PR {float(performance_ratio):.1%} is {drop:.1%} "
                f"below expected {float(expected_pr):.1%}"
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
            expected_pr=expected_pr,
            is_anomaly=is_anomaly,
            anomaly_reason=anomaly_reason,
        )
        session.add(row)
    else:
        existing_monthly.production_kwh = production_kwh
        existing_monthly.theoretical_kwh = theoretical_kwh
        existing_monthly.performance_ratio = performance_ratio
        existing_monthly.expected_pr = expected_pr
        existing_monthly.is_anomaly = is_anomaly
        existing_monthly.anomaly_reason = anomaly_reason
        row = existing_monthly

    await session.commit()
    logger.info(
        "Monthly summary built for system={} month={} PR={}",
        system_id,
        month,
        performance_ratio,
    )
    return row
