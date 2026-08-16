from datetime import UTC, date, datetime, time, timedelta

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from helio.db.models import (
    DailySummary,
    EnergyInterval,
    Irradiance,
    PanelReading,
    PollLog,
    System,
)
from helio.ingestion.enphase_client import (
    EnphaseClient,
    PanelDataUnavailableError,
    PanelEnergy,
)
from helio.ingestion.irradiance_client import IrradianceClient

MISSING_COORDINATES_MESSAGE = (
    "Irradiance skipped: this system has no latitude or longitude. Open the "
    "Setup tab at http://localhost:3000, save your site coordinates, and run "
    "the poll again. Performance ratio stays unavailable until then."
)
EMPTY_PANEL_PAYLOAD_MESSAGE = (
    "Enphase reported no microinverters for {}. Per-panel monitoring stays "
    "empty for that day; the rest of the poll is unaffected."
)


def irradiance_location(system: System) -> tuple[float, float] | None:
    """Return the site coordinates, or None when they are not configured.

    Irradiance is location-based, so polling without coordinates would fetch
    the series for 0,0 in the Gulf of Guinea and silently corrupt every
    performance ratio derived from it. Callers skip the irradiance step
    instead.

    Args:
        system: The configured system.

    Returns:
        Tuple of (latitude, longitude), or None after logging a warning if
        either coordinate is unset.
    """
    if system.latitude is None or system.longitude is None:
        logger.warning(MISSING_COORDINATES_MESSAGE)
        return None
    return float(system.latitude), float(system.longitude)


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


async def recent_polls(session: AsyncSession, limit: int = 10) -> list[PollLog]:
    """Return the most recent poll_log rows, newest first.

    Args:
        session: Active async database session.
        limit: Maximum number of rows to return.

    Returns:
        PollLog rows ordered by start time descending.
    """
    result = await session.execute(
        select(PollLog).order_by(PollLog.started_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


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
        RuntimeError: On rate-limit exhaustion from the Enphase API.
        httpx.HTTPStatusError: On non-retryable HTTP errors from the Enphase API.
        Exception: Re-raises any unexpected error after logging.
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

        # Load all existing timestamps for this date range in one query
        range_start = datetime.combine(start_date, time.min, tzinfo=UTC)
        range_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=UTC)
        existing_timestamps_result = await session.execute(
            select(EnergyInterval.interval_start).where(
                EnergyInterval.system_id == system_id,
                EnergyInterval.interval_start >= range_start,
                EnergyInterval.interval_start < range_end,
            )
        )
        existing_timestamps = set(existing_timestamps_result.scalars().all())

        for iv in intervals:
            if iv.interval_start not in existing_timestamps:
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

    except (RuntimeError, httpx.HTTPStatusError) as exc:
        original_exc = exc
        try:
            await session.rollback()
            error_log = PollLog(
                system_id=system_id,
                poll_type="intervals",
                started_at=started_at,
                status="error",
                error_message=str(exc),
                completed_at=datetime.now(tz=UTC),
                date_range_start=start_date,
                date_range_end=end_date,
            )
            session.add(error_log)
            await session.commit()
        except Exception as log_exc:
            logger.error(
                "Failed to persist poll error log for {}-{}: {}",
                start_date,
                end_date,
                log_exc,
            )
        logger.error("Poll failed for {}-{}: {}", start_date, end_date, original_exc)
        raise original_exc
    except Exception as exc:
        original_exc = exc
        try:
            await session.rollback()
            error_log = PollLog(
                system_id=system_id,
                poll_type="intervals",
                started_at=started_at,
                status="error",
                error_message=f"Unexpected error: {exc}",
                completed_at=datetime.now(tz=UTC),
                date_range_start=start_date,
                date_range_end=end_date,
            )
            session.add(error_log)
            await session.commit()
        except Exception as log_exc:
            logger.error(
                "Failed to persist poll error log for {}-{}: {}",
                start_date,
                end_date,
                log_exc,
            )
        logger.error(
            "Unexpected poll error for {}-{}: {}", start_date, end_date, original_exc
        )
        raise original_exc


async def _upsert_panel_readings(
    session: AsyncSession,
    system_id: int,
    target_date: date,
    readings: list[PanelEnergy],
) -> int:
    """Write one panel_readings row per panel for target_date.

    Args:
        session: Active async database session.
        system_id: DB system ID.
        target_date: Date the readings cover.
        readings: Per-panel energy totals for that date.

    Returns:
        The number of rows inserted; the remainder were updates.
    """
    existing = await session.execute(
        select(PanelReading).where(
            PanelReading.system_id == system_id,
            PanelReading.day == target_date,
        )
    )
    by_serial = {row.panel_serial: row for row in existing.scalars().all()}
    inserted = 0
    for reading in readings:
        row = by_serial.get(reading.panel_serial)
        if row is None:
            session.add(
                PanelReading(
                    system_id=system_id,
                    panel_serial=reading.panel_serial,
                    day=target_date,
                    energy_wh=reading.energy_wh,
                )
            )
            inserted += 1
        else:
            row.energy_wh = reading.energy_wh
    return inserted


async def _record_panel_failure(
    session: AsyncSession,
    system_id: int,
    started_at: datetime,
    target_date: date,
    status: str,
    message: str,
) -> None:
    """Persist the outcome of a failed panel poll.

    The running poll_log row was only flushed, so the rollback that clears the
    failed transaction discards it; a fresh row carries the outcome instead.

    Args:
        session: Active async database session.
        system_id: DB system ID.
        started_at: When the poll started.
        target_date: Date the poll covered.
        status: Row status, 'partial' when panel data is simply unavailable and
            'error' when the poll genuinely failed.
        message: Explanation stored on the row.
    """
    try:
        await session.rollback()
        session.add(
            PollLog(
                system_id=system_id,
                poll_type="panels",
                started_at=started_at,
                status=status,
                error_message=message,
                completed_at=datetime.now(tz=UTC),
                date_range_start=target_date,
                date_range_end=target_date,
            )
        )
        await session.commit()
    except SQLAlchemyError as exc:
        logger.error("Failed to persist panels poll log for {}: {}", target_date, exc)


async def poll_panels(
    session: AsyncSession,
    client: EnphaseClient,
    system_id: int,
    target_date: date,
) -> tuple[int, int]:
    """Fetch per-panel production for one day and upsert into panel_readings.

    Args:
        session: Active async database session.
        client: Authenticated EnphaseClient instance.
        system_id: DB system ID for the target system.
        target_date: Date to fetch.

    Returns:
        Tuple of (records_fetched, records_inserted); fetched minus inserted is
        the number of rows updated in place.

    Raises:
        PanelDataUnavailableError: If the Enphase plan does not expose
            device-level telemetry, or it reports no microinverters at all.
            Recorded as a 'partial' poll rather than an error because it is a
            capability limit, not a fault.
        RuntimeError: On rate-limit exhaustion from the Enphase API.
        httpx.HTTPStatusError: On non-retryable HTTP errors from the Enphase API.
        Exception: Re-raises any unexpected error after recording it.
    """
    started_at = datetime.now(tz=UTC)
    poll_log = PollLog(
        system_id=system_id,
        poll_type="panels",
        started_at=started_at,
        status="running",
        date_range_start=target_date,
        date_range_end=target_date,
    )
    session.add(poll_log)
    await session.flush()

    try:
        readings = await client.get_panel_data(target_date)
        if not readings:
            raise PanelDataUnavailableError(
                EMPTY_PANEL_PAYLOAD_MESSAGE.format(target_date)
            )
        inserted = await _upsert_panel_readings(
            session, system_id, target_date, readings
        )
        poll_log.status = "success"
        poll_log.completed_at = datetime.now(tz=UTC)
        poll_log.records_fetched = len(readings)
        poll_log.records_inserted = inserted
        await session.commit()
        logger.info(
            "Polled panels for {}: fetched={}, inserted={}",
            target_date,
            len(readings),
            inserted,
        )
        return len(readings), inserted

    except PanelDataUnavailableError as exc:
        await _record_panel_failure(
            session, system_id, started_at, target_date, "partial", str(exc)
        )
        raise
    except (RuntimeError, httpx.HTTPStatusError) as exc:
        await _record_panel_failure(
            session, system_id, started_at, target_date, "error", str(exc)
        )
        logger.error("Panel poll failed for {}: {}", target_date, exc)
        raise
    except Exception as exc:
        await _record_panel_failure(
            session,
            system_id,
            started_at,
            target_date,
            "error",
            f"Unexpected error: {exc}",
        )
        logger.error("Unexpected panel poll error for {}: {}", target_date, exc)
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
        longitude=longitude,
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
