"""Cached read of the system's instantaneous output.

An envoy reports production in 15-minute batches and the free Enphase plan's
request quota is small, so the dashboard must not reach upstream on every
render. One reading is fetched per TTL and served to every caller in between.

A failed fetch is cached too. When Enphase is unreachable or rate limiting,
retrying on each dashboard load would spend the remaining quota faster than a
working system does, and the dashboard has nothing to show either way.
"""

import asyncio
import time

import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from helio.db.models import System
from helio.ingestion.enphase_client import CurrentProduction
from helio.ingestion.tokens import TokenError, build_authenticated_client

# An envoy reports every 15 minutes, so asking more often cannot surface a newer
# number; it would only spend request quota.
CACHE_TTL_SECONDS = 900

_lock = asyncio.Lock()
_cached: CurrentProduction | None = None
_cached_at: float | None = None


def monotonic() -> float:
    """Return a monotonic clock reading, in seconds.

    Returns:
        Seconds from an arbitrary origin. Wrapped in a function so tests can
        pin it, and monotonic rather than wall clock so a system time change
        cannot make a cached reading look eternally fresh.
    """
    return time.monotonic()


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


async def get_live_power(
    session: AsyncSession, system: System
) -> CurrentProduction | None:
    """Return the system's latest output, fetching at most once per TTL.

    Args:
        session: Async database session owning `system`.
        system: The system row supplying the Enphase credentials.

    Returns:
        The cached reading when it is still fresh, otherwise a newly fetched
        one, or None when it cannot be fetched. The lock means simultaneous
        dashboard loads share a single upstream call rather than racing to
        make one each.
    """
    global _cached, _cached_at
    async with _lock:
        now = monotonic()
        if _cached_at is not None and now - _cached_at < CACHE_TTL_SECONDS:
            return _cached
        _cached = await _fetch(session, system)
        _cached_at = now
        return _cached
