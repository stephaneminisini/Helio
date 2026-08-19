import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from helio.db.models import EnergyInterval, System
from helio.ingestion import live_power
from helio.ingestion.enphase_client import CurrentProduction
from helio.ingestion.live_power import (
    CACHE_TTL_SECONDS,
    MAX_STORED_AGE,
    LivePower,
    get_live_power,
)
from helio.ingestion.tokens import TokenError

NOW = datetime(2024, 7, 19, 13, 5, tzinfo=UTC)

READING = CurrentProduction(
    watts=4210.0, reported_at=datetime(2024, 7, 19, 13, 0, tzinfo=UTC)
)
LIVE = LivePower(watts=READING.watts, reported_at=READING.reported_at, source="live")


@pytest.fixture(autouse=True)
def empty_cache():
    """The cache outlives a request, so each test starts and ends without one."""
    live_power.reset_cache()
    yield
    live_power.reset_cache()


@pytest.fixture(autouse=True)
def pinned_now(monkeypatch):
    """Pin the wall clock the stored reading's age is measured against."""
    monkeypatch.setattr(live_power, "utcnow", lambda: NOW)


@pytest.fixture
def frozen_clock(monkeypatch):
    """Drive the cache's clock by hand, in seconds."""
    elapsed = {"seconds": 0.0}
    monkeypatch.setattr(live_power, "monotonic", lambda: elapsed["seconds"])

    def advance(seconds: float) -> None:
        elapsed["seconds"] += seconds

    return advance


@pytest.fixture
def enphase(monkeypatch):
    """Stub the authenticated client, returning the call-counting builder."""

    def stub(reading=READING, error: Exception | None = None) -> AsyncMock:
        if error is not None:
            builder = AsyncMock(side_effect=error)
        else:
            client = MagicMock()
            client.get_current_power = AsyncMock(return_value=reading)
            builder = AsyncMock(return_value=client)
        monkeypatch.setattr(live_power, "build_authenticated_client", builder)
        return builder

    return stub


def _system() -> MagicMock:
    system = MagicMock(spec=System)
    system.id = 1
    system.enphase_system_id = "12345"
    return system


def _interval(
    *,
    minutes_ago: float = 5,
    production_wh: Decimal | None = Decimal("1000.000"),
    duration_seconds: int = 900,
) -> MagicMock:
    """One stored interval, aged relative to the pinned clock.

    Args:
        minutes_ago: How long before NOW the interval started.
        production_wh: Energy recorded over the interval, or None when the
            envoy reported the interval without a figure.
        duration_seconds: How long the interval covers.

    Returns:
        A stand-in for the EnergyInterval row the fallback query returns. The
        default is 1000 Wh over 15 minutes, which is 4000 W.
    """
    row = MagicMock(spec=EnergyInterval)
    row.interval_start = NOW - timedelta(minutes=minutes_ago)
    row.production_wh = production_wh
    row.duration_seconds = duration_seconds
    return row


def _session(row: MagicMock | None = None) -> AsyncMock:
    """A session whose interval query returns `row`, so nothing stored by default."""
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=row))
    )
    return session


@pytest.mark.asyncio
async def test_returns_the_reading_from_enphase(enphase):
    """AC1: the reading and its measurement time both reach the caller."""
    enphase()

    assert await get_live_power(_session(), _system()) == LIVE


@pytest.mark.asyncio
async def test_prefers_the_live_reading_over_a_stored_one(enphase):
    """A reading from Enphase is current; a stored one is only the last recorded."""
    enphase()

    reading = await get_live_power(_session(_interval()), _system())

    assert reading == LIVE


@pytest.mark.asyncio
async def test_serves_a_second_caller_from_the_cache(enphase, frozen_clock):
    """AC2: two dashboard loads inside the window cost one upstream call."""
    builder = enphase()
    session, system = _session(), _system()

    first = await get_live_power(session, system)
    frozen_clock(CACHE_TTL_SECONDS - 1)
    second = await get_live_power(session, system)

    assert first == second == LIVE
    assert builder.await_count == 1


@pytest.mark.asyncio
async def test_fetches_again_once_the_cache_expires(enphase, frozen_clock):
    builder = enphase()
    session, system = _session(), _system()

    await get_live_power(session, system)
    frozen_clock(CACHE_TTL_SECONDS)
    await get_live_power(session, system)

    assert builder.await_count == 2


@pytest.mark.asyncio
async def test_concurrent_callers_share_one_upstream_call(enphase):
    """Two dashboards loading at once must not each spend a request."""
    builder = enphase()
    session, system = _session(), _system()

    readings = await asyncio.gather(
        get_live_power(session, system), get_live_power(session, system)
    )

    assert readings == [LIVE, LIVE]
    assert builder.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        TokenError("no refresh token"),
        httpx.HTTPStatusError(
            "unauthorized",
            request=httpx.Request("GET", "https://api.enphaseenergy.com"),
            response=httpx.Response(401),
        ),
        httpx.ConnectError("no route to host"),
        RuntimeError("rate limit"),
        ValueError("Token refresh response missing access_token"),
    ],
)
async def test_returns_none_when_enphase_cannot_be_read(enphase, error):
    """AC3: a missing reading must not cost the caller the rest of the payload."""
    enphase(error=error)

    assert await get_live_power(_session(), _system()) is None


@pytest.mark.asyncio
async def test_caches_a_failure_too(enphase, frozen_clock):
    """Retrying a dead upstream on every render spends the quota fastest."""
    builder = enphase(error=RuntimeError("rate limit"))
    session, system = _session(), _system()

    await get_live_power(session, system)
    frozen_clock(CACHE_TTL_SECONDS - 1)

    assert await get_live_power(session, system) is None
    assert builder.await_count == 1


@pytest.mark.asyncio
async def test_passes_through_a_system_that_has_never_reported(enphase):
    """No reading upstream is still no reading here, and not an error."""
    enphase(reading=None)

    assert await get_live_power(_session(), _system()) is None


@pytest.mark.asyncio
async def test_falls_back_to_the_last_stored_interval(enphase):
    """An unreachable Enphase costs the card its currency, not its content."""
    enphase(error=httpx.ConnectError("no route to host"))
    row = _interval()

    reading = await get_live_power(_session(row), _system())

    # 1000 Wh over 15 minutes, the mean over the interval rather than a
    # measurement taken at its start.
    assert reading == LivePower(
        watts=4000.0, reported_at=row.interval_start, source="stored"
    )


@pytest.mark.asyncio
async def test_refuses_a_stored_interval_older_than_the_window(enphase):
    """Past a point a recorded figure is not worth showing at all."""
    enphase(error=httpx.ConnectError("no route to host"))
    stale = _interval(minutes_ago=MAX_STORED_AGE.total_seconds() / 60 + 1)

    assert await get_live_power(_session(stale), _system()) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        pytest.param(_interval(production_wh=None), id="no production recorded"),
        pytest.param(_interval(duration_seconds=0), id="no duration to average over"),
    ],
)
async def test_refuses_a_stored_interval_it_cannot_average(enphase, row):
    """Neither an absent figure nor a zero-length window yields a power."""
    enphase(error=httpx.ConnectError("no route to host"))

    assert await get_live_power(_session(row), _system()) is None


@pytest.mark.asyncio
async def test_re_reads_the_stored_fallback_while_a_failure_is_cached(
    enphase, frozen_clock
):
    """A poll can land mid-TTL, so the fallback must not be cached with the failure."""
    builder = enphase(error=RuntimeError("rate limit"))
    session, system = _session(), _system()

    assert await get_live_power(session, system) is None
    frozen_clock(CACHE_TTL_SECONDS - 1)
    row = _interval()
    session.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=row)
    )
    second = await get_live_power(session, system)

    assert second == LivePower(
        watts=4000.0, reported_at=row.interval_start, source="stored"
    )
    # The newly stored interval surfaced without spending another request.
    assert builder.await_count == 1
