"""Generate synthetic production and irradiance data for development.

Lets a contributor see a populated dashboard without an Enphase account. The
numbers are deterministic for a given seed and shaped to be plausible rather
than physically exact: a seasonal envelope, a half-sine day, per-day cloud
noise, and a performance ratio that decays at the system's own degradation
rate so the efficiency page shows a believable trend.
"""

import math
import random
from datetime import UTC, date, datetime, timedelta

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from helio.analytics.summarizer import rebuild_all_summaries
from helio.db.models import EnergyInterval, Irradiance, System

DEFAULT_YEARS = 3
INTERVALS_PER_DAY = 96
INTERVAL_SECONDS = 900
CHUNK_ROWS = 2000
SOURCE = "mock"
TARGET_PR = 0.82
# Peak irradiance in kWh/m2/day at the summer solstice, before cloud losses.
PEAK_POA_KWH_M2 = 7.0
SUMMER_SOLSTICE_DOY = 172
# The daylight window is centred on this UTC hour and never crosses midnight,
# so every interval lands in the day the summary aggregates it into.
SOLAR_NOON_HOUR = 13.0
DEFAULT_SIZE_KW = 10.0
DEFAULT_LATITUDE = 45.0
REAL_DATA_MESSAGE = (
    "This database holds {} production intervals the mock seeder did not write, so "
    "seeding would overwrite real measurements. Point at an empty development "
    "database instead."
)


class RealDataError(RuntimeError):
    """Raised when the target database already holds real production data.

    Seeding overwrites intervals day by day, and measurements older than the
    Enphase retention window cannot be fetched again, so a live install must be
    refused rather than overwritten.
    """


def _seasonal_factor(day: date, latitude: float) -> float:
    """Return a 0.3-1.0 envelope peaking at the local summer solstice.

    Args:
        day: The day to evaluate.
        latitude: Site latitude; negative flips the seasons.

    Returns:
        Multiplier applied to peak irradiance and daylight length.
    """
    phase = 2 * math.pi * (day.timetuple().tm_yday - SUMMER_SOLSTICE_DOY) / 365.25
    if latitude < 0:
        phase += math.pi
    return 0.65 + 0.35 * math.cos(phase)


def _interval_weights(daylight_hours: float) -> list[float]:
    """Distribute one day's energy across the 96 intervals as a half sine.

    Args:
        daylight_hours: Width of the production window in hours.

    Returns:
        96 weights summing to 1.0, zero outside the daylight window.
    """
    sunrise = SOLAR_NOON_HOUR - daylight_hours / 2
    weights = []
    for index in range(INTERVALS_PER_DAY):
        hour = index * 24 / INTERVALS_PER_DAY
        position = (hour - sunrise) / daylight_hours
        weights.append(math.sin(math.pi * position) if 0 < position < 1 else 0.0)
    total = sum(weights)
    return [weight / total for weight in weights]


def _day_profile(
    day: date, system: System, rng: random.Random
) -> tuple[float, float, list[float]]:
    """Compute one day's irradiance, energy and per-interval distribution.

    Args:
        day: The day to generate.
        system: System supplying size, latitude, install date and degradation.
        rng: Seeded generator, for reproducible cloud cover.

    Returns:
        Tuple of (poa_kwh_m2, production_kwh, interval_weights).
    """
    latitude = float(
        system.latitude if system.latitude is not None else DEFAULT_LATITUDE
    )
    seasonal = _seasonal_factor(day, latitude)
    # Mostly-sunny bias with the occasional washout.
    cloud = min(1.0, rng.betavariate(5, 2) + 0.15)
    poa = PEAK_POA_KWH_M2 * seasonal * cloud

    size_kw = float(system.system_size_kw or DEFAULT_SIZE_KW)
    years_installed = max(0.0, (day - system.install_date).days / 365.25)
    degradation = (1 - float(system.degradation_rate or 0) / 100) ** years_installed
    production_kwh = poa * size_kw * TARGET_PR * degradation

    return poa, production_kwh, _interval_weights(9 + 6 * seasonal)


def _elapsed_intervals(now: datetime) -> int:
    """Count the intervals of `now`'s own day that have already finished.

    Args:
        now: The current instant, timezone-aware.

    Returns:
        How many whole INTERVAL_SECONDS windows have closed since midnight, so
        0 at midnight and INTERVALS_PER_DAY at the end of the day.
    """
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int((now - midnight).total_seconds() // INTERVAL_SECONDS)


def _interval_rows(
    system_id: int,
    day: date,
    kwh: float,
    weights: list[float],
    limit: int | None = None,
) -> list[dict]:
    """Build the energy_intervals rows for one day.

    Args:
        system_id: Owning system.
        day: The day to generate.
        kwh: Total production for the day in kilowatt-hours.
        weights: Per-interval share of the daily total.
        limit: Stop after this many intervals, for a day still in progress. The
            weights are not renormalised, so a truncated day carries only the
            energy that had actually been produced by the cutoff, which is what
            a live install would have recorded.

    Returns:
        Rows ready for a bulk insert.
    """
    midnight = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return [
        {
            "system_id": system_id,
            "interval_start": midnight + timedelta(seconds=index * INTERVAL_SECONDS),
            "duration_seconds": INTERVAL_SECONDS,
            "production_wh": round(kwh * 1000 * weight, 3),
        }
        for index, weight in enumerate(weights[:limit])
    ]


async def _upsert(
    session: AsyncSession, table, rows: list[dict], keys: list[str]
) -> None:
    """Bulk upsert rows in chunks, overwriting the generated columns.

    Reseeding must be repeatable, and both target tables carry a unique
    constraint, so a plain insert would fail on the second run.

    Args:
        session: Active async database session.
        table: The ORM model to insert into.
        rows: Rows to write.
        keys: Columns forming the unique constraint.
    """
    updatable = [name for name in rows[0] if name not in keys]
    for start in range(0, len(rows), CHUNK_ROWS):
        chunk = rows[start : start + CHUNK_ROWS]
        stmt = pg_insert(table)
        stmt = stmt.on_conflict_do_update(
            index_elements=keys,
            set_={name: getattr(stmt.excluded, name) for name in updatable},
        )
        await session.execute(stmt, chunk)
    await session.commit()


async def _unseeded_interval_count(session: AsyncSession, system_id: int) -> int:
    """Count production intervals on days this seeder never wrote.

    Every day the seeder covers also gets an irradiance row tagged SOURCE, so an
    interval on a day without one came from real ingestion. That makes reseeding
    an already-mocked database free, while a live install is recognised.

    Args:
        session: Active async database session.
        system_id: System whose intervals to inspect.

    Returns:
        Number of energy_intervals rows on days carrying no mock irradiance.
    """
    seeded_days = select(Irradiance.day).where(
        Irradiance.system_id == system_id,
        Irradiance.source == SOURCE,
    )
    stmt = (
        select(func.count())
        .select_from(EnergyInterval)
        .where(
            EnergyInterval.system_id == system_id,
            func.date(EnergyInterval.interval_start).not_in(seeded_days),
        )
    )
    return (await session.execute(stmt)).scalar_one()


async def seed_mock(
    session: AsyncSession,
    system: System,
    years: int = DEFAULT_YEARS,
    seed: int = 42,
) -> tuple[int, int]:
    """Populate intervals, irradiance and summaries with synthetic data.

    Existing rows for the same days are overwritten, so the command is safe to
    re-run. Summaries are rebuilt at the end so the dashboard has something to
    read immediately.

    Today is included, truncated at the last interval to have closed, so the
    Overview opens on a figure that grows through the day like a live install's
    rather than on a zero. Re-running later in the day tops the day up: the
    upsert is keyed on the interval start, so the intervals already written are
    rewritten with the same values and the newly elapsed ones are added.

    Args:
        session: Active async database session.
        system: The configured system to attach the data to.
        years: How many years back from today to generate.
        seed: Seed for the cloud-cover noise, for reproducible data.

    Returns:
        Tuple of (interval_rows, irradiance_rows) written.

    Raises:
        RealDataError: If the system already has production intervals this
            seeder did not write, which is what a live install looks like.
    """
    unseeded = await _unseeded_interval_count(session, system.id)
    if unseeded:
        raise RealDataError(REAL_DATA_MESSAGE.format(unseeded))

    now = datetime.now(UTC)
    end = now.date()
    start = end - timedelta(days=round(years * 365.25) - 1)
    # Today's own intervals stop at the cutoff; every prior day is whole.
    today_intervals = _elapsed_intervals(now)
    rng = random.Random(seed)
    logger.info("Seeding mock data for system={} from {} to {}", system.id, start, end)

    intervals: list[dict] = []
    irradiance: list[dict] = []
    day = start
    while day <= end:
        poa, production_kwh, weights = _day_profile(day, system, rng)
        limit = today_intervals if day == end else None
        intervals.extend(_interval_rows(system.id, day, production_kwh, weights, limit))
        # A part-day's irradiance has to cover the same window as its production,
        # or the monthly performance ratio divides part of a day's output by all
        # of its sunlight and reads as a real efficiency drop. The weights are
        # the day's energy distribution, so their partial sum is the fraction of
        # the day's sunlight that has arrived.
        elapsed = sum(weights[:limit]) if limit is not None else 1.0
        day_poa = poa * elapsed
        irradiance.append(
            {
                "system_id": system.id,
                "day": day,
                "ghi_kwh_m2": round(day_poa / 1.1, 4),
                "dni_kwh_m2": round(day_poa / 1.1 * 0.85, 4),
                "poa_kwh_m2": round(day_poa, 4),
                "source": SOURCE,
            }
        )
        day += timedelta(days=1)

    await _upsert(session, EnergyInterval, intervals, ["system_id", "interval_start"])
    await _upsert(session, Irradiance, irradiance, ["system_id", "day", "source"])
    logger.info(
        "Wrote {} intervals and {} irradiance rows", len(intervals), len(irradiance)
    )

    await rebuild_all_summaries(session, system)
    return len(intervals), len(irradiance)
