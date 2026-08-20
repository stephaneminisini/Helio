"""Cached read of the system's instantaneous output.

An envoy reports production in 15-minute batches and the free Enphase plan's
request quota is small, so the dashboard must not reach upstream on every
render. One reading is fetched per TTL and served to every caller in between.

A failed fetch is cached too. When Enphase is unreachable or rate limiting,
retrying on each dashboard load would spend the remaining quota faster than a
working system does.

What it does not mean is that the dashboard has nothing to show. The stored
intervals usually hold a reading minutes old, so a failed fetch falls back to
the newest one recent enough to still be worth reporting, labelled as recorded
rather than current.
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.db.models import EnergyInterval, System
from helio.ingestion.enphase_client import CurrentProduction
from helio.ingestion.tokens import TokenError, build_authenticated_client

# An envoy reports every 15 minutes, so asking more often cannot surface a newer
# number; it would only spend request quota.
CACHE_TTL_SECONDS = 900

# How old a stored interval may be and still stand in for a live reading. An
# envoy reports every 15 minutes, so an hour absorbs a few missed reports while
# refusing a figure nobody would call current: a stale number on the largest
# card on the page is worse than an honest blank.
MAX_STORED_AGE = timedelta(hours=1)

_lock = asyncio.Lock()
_cached: CurrentProduction | None = None
_cached_at: float | None = None


@dataclass(frozen=True)
class LivePower:
    """The system's output, and where the figure came from.

    Attributes:
        watts: Output in watts. Instantaneous when live, and the mean over the
            interval when stored, because an interval records energy across a
            window rather than at a moment.
        reported_at: When the reading was taken, in UTC. For a stored reading
            this is the start of the interval it came from.
        source: "live" for a reading fetched from Enphase, "stored" for the
            fallback. Callers have to be able to tell them apart, since showing
            a recorded figure as the current one would be a worse bug than the
            blank card this fallback replaces.
    """

    watts: float
    reported_at: datetime
    source: Literal["live", "stored"]


def monotonic() -> float:
    """Return a monotonic clock reading, in seconds.

    Returns:
        Seconds from an arbitrary origin. Wrapped in a function so tests can
        pin it, and monotonic rather than wall clock so a system time change
        cannot make a cached reading look eternally fresh.
    """
    return time.monotonic()


def utcnow() -> datetime:
    """Return the current instant in UTC.

    Returns:
        An aware datetime, matching the timezone the intervals are stored in.
        Wrapped for the same reason as monotonic(): the age cutoff below cannot
        be tested against a clock the test cannot pin.
    """
    return datetime.now(UTC)


def reset_cache() -> None:
    """Forget the cached reading, so the next caller fetches a new one."""
    global _cached, _cached_at
    _cached = None
    _cached_at = None


async def _fetch(session: AsyncSession, system: System) -> CurrentProduction | None:
    """Read the latest output from Enphase, or None when it cannot be read.

    Args:
        session: Async database session owning `system`.
        system: The system row supplying the Enphase credentials.

    Returns:
        The reading, or None on any upstream or credential failure. Live power
        is one figure on a dashboard full of stored history, so a missing
        reading must not cost the caller the rest of the payload.
    """
    try:
        client = await build_authenticated_client(session, system)
        return await client.get_current_power()
    except TokenError as exc:
        logger.warning("Live power unavailable, Enphase not connected: {}", exc)
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Live power unavailable, Enphase returned {}", exc.response.status_code
        )
    except httpx.HTTPError as exc:
        logger.warning("Live power unavailable, Enphase unreachable: {}", exc)
    except RuntimeError as exc:
        logger.warning("Live power unavailable, Enphase rate limited: {}", exc)
    except ValueError as exc:
        logger.warning("Live power unavailable, unusable Enphase response: {}", exc)
    return None


async def _latest_stored(session: AsyncSession, system: System) -> LivePower | None:
    """Return the newest recent stored interval as a power reading.

    Args:
        session: Async database session.
        system: The system whose intervals are read.

    Returns:
        The mean power over the newest stored interval, or None when there is no
        interval, the newest one is older than MAX_STORED_AGE, or it recorded no
        production or no duration. The age is measured from the interval's
        start, so the reading can be one interval older than MAX_STORED_AGE
        alone suggests.
    """
    row = (
        await session.execute(
            select(EnergyInterval)
            .where(EnergyInterval.system_id == system.id)
            .order_by(EnergyInterval.interval_start.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None or row.production_wh is None or not row.duration_seconds:
        return None
    if utcnow() - row.interval_start > MAX_STORED_AGE:
        return None
    return LivePower(
        watts=round(float(row.production_wh) / (row.duration_seconds / 3600), 1),
        reported_at=row.interval_start,
        source="stored",
    )


async def get_live_power(session: AsyncSession, system: System) -> LivePower | None:
    """Return the system's latest output, fetching from Enphase once per TTL.

    Args:
        session: Async database session owning `system`.
        system: The system row supplying the Enphase credentials.

    Returns:
        The live reading when Enphase answers, otherwise the most recent stored
        interval, or None when neither is available. The lock means simultaneous
        dashboard loads share a single upstream call rather than racing to make
        one each.

        The stored fallback is deliberately outside the cache. A failed fetch is
        remembered for the whole TTL to protect the request quota, and a poll
        can land in the middle of that, so the fallback is re-read per call.
    """
    global _cached, _cached_at
    async with _lock:
        now = monotonic()
        if _cached_at is None or now - _cached_at >= CACHE_TTL_SECONDS:
            _cached = await _fetch(session, system)
            _cached_at = now
        live = _cached

    if live is not None:
        return LivePower(watts=live.watts, reported_at=live.reported_at, source="live")
    return await _latest_stored(session, system)
