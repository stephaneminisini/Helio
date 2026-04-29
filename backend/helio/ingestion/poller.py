from datetime import UTC, date, datetime, timedelta

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.db.models import DailySummary, EnergyInterval, Irradiance, PollLog
from helio.ingestion.enphase_client import EnphaseClient
from helio.ingestion.irradiance_client import IrradianceClient


async def detect_gaps(
    session: AsyncSession,
    system_id: int,
    start_date: date,
    end_date: date,
) -> list[date]:
    """Return dates in [start_date, end_date] that have no daily_summary row.

    Args:
        session: Active async database session.
        system_id: System to check gaps for.
        start_date: First date to check (inclusive).
        end_date: Last date to check (inclusive).

    Returns:
        Sorted list of dates with missing data.
    """
    stmt = select(DailySummary.day).where(
        DailySummary.system_id == system_id,
        DailySummary.day >= start_date,
        DailySummary.day <= end_date,
    )
    result = await session.execute(stmt)
    present = set(result.scalars().all())
    all_dates = {
        start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)
    }
    return sorted(all_dates - present)


async def poll_intervals(
    session: AsyncSession,
    client: EnphaseClient,
    system_id: int,
    start_date: date,
    end_date: date,
) -> tuple[int, int]:
    """Fetch intervals from Enphase and upsert them into energy_intervals.

    Args:
        session: Active async database session.
        client: Authenticated EnphaseClient instance.
        system_id: DB system ID for the target system.
        start_date: Start of date range.
        end_date: End of date range.

    Returns:
        Tuple of (records_fetched, records_inserted).

    Raises:
        Exception: Re-raises any exception from the Enphase client after logging.
    """
    started_at = datetime.now(tz=UTC)
    poll_log = PollLog(
        system_id=system_id,
        poll_type="intervals",
        started_at=started_at,
        status="running",
    )
    session.add(poll_log)
    await session.flush()

    try:
        intervals = await client.get_intervals(start_date, end_date)
        records_fetched = len(intervals)
        records_inserted = 0

        for iv in intervals:
            existing = await session.execute(
                select(EnergyInterval).where(
                    EnergyInterval.system_id == system_id,
                    EnergyInterval.interval_start == iv.interval_start,
                )
            )
            if existing.scalar_one_or_none() is None:
                session.add(
                    EnergyInterval(
                        system_id=system_id,
                        interval_start=iv.interval_start,
                        duration_seconds=iv.duration_seconds,
                        production_wh=iv.production_wh,
                    )
                )
                records_inserted += 1

        poll_log.status = "success"
        poll_log.completed_at = datetime.now(tz=UTC)
        poll_log.records_fetched = records_fetched
        poll_log.records_inserted = records_inserted
        poll_log.date_range_start = start_date
        poll_log.date_range_end = end_date
        await session.commit()
        logger.info(
            "Polled intervals {}-{}: fetched={}, inserted={}",
            start_date,
            end_date,
            records_fetched,
            records_inserted,
        )
        return records_fetched, records_inserted

    except Exception as exc:
        poll_log.status = "error"
        poll_log.error_message = str(exc)
        poll_log.completed_at = datetime.now(tz=UTC)
        await session.commit()
        logger.error("Poll failed for {}-{}: {}", start_date, end_date, exc)
        raise


async def poll_irradiance(
    session: AsyncSession,
    client: IrradianceClient,
    system_id: int,
    latitude: float,
    longitude: float,
    tilt: float,
    azimuth: float,
    target_date: date,
    source: str,
) -> None:
    """Fetch irradiance for one day and upsert into irradiance table.

    Args:
        session: Active async database session.
        client: IrradianceClient (NRELClient or NASAClient).
        system_id: DB system ID.
        latitude: Site latitude.
        longitude: Site longitude.
        tilt: Panel tilt in degrees.
        azimuth: Panel azimuth in degrees.
        target_date: Date to fetch.
        source: 'nrel' or 'nasa'.
    """
    from helio.ingestion.irradiance_client import compute_poa

    data = await client.get_daily_irradiance(latitude, longitude, target_date)
    poa = compute_poa(
        ghi=data["ghi"],
        dni=data["dni"],
        tilt=tilt,
        azimuth=azimuth,
        latitude=latitude,
        target_date=target_date,
    )
    existing = await session.execute(
        select(Irradiance).where(
            Irradiance.system_id == system_id,
            Irradiance.day == target_date,
            Irradiance.source == source,
        )
    )
    row = existing.scalar_one_or_none()
    if row is None:
        session.add(
            Irradiance(
                system_id=system_id,
                day=target_date,
                ghi_kwh_m2=data["ghi"],
                dni_kwh_m2=data["dni"],
                poa_kwh_m2=poa,
                source=source,
            )
        )
    else:
        row.ghi_kwh_m2 = data["ghi"]
        row.dni_kwh_m2 = data["dni"]
        row.poa_kwh_m2 = poa

    await session.commit()
    logger.debug("Irradiance stored for {} (source={})", target_date, source)
