import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from helio.db.models import System
from helio.ingestion import live_power
from helio.ingestion.enphase_client import CurrentProduction
from helio.ingestion.live_power import CACHE_TTL_SECONDS, get_live_power
from helio.ingestion.tokens import TokenError

READING = CurrentProduction(
    watts=4210.0, reported_at=datetime(2024, 7, 19, 13, 0, tzinfo=UTC)
)


@pytest.fixture(autouse=True)
def empty_cache():
    """The cache outlives a request, so each test starts and ends without one."""
    live_power.reset_cache()
    yield
    live_power.reset_cache()


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


@pytest.mark.asyncio
async def test_returns_the_reading_from_enphase(enphase):
    """AC1: the reading and its measurement time both reach the caller."""
    enphase()

    assert await get_live_power(AsyncMock(), _system()) == READING


@pytest.mark.asyncio
async def test_serves_a_second_caller_from_the_cache(enphase, frozen_clock):
    """AC2: two dashboard loads inside the window cost one upstream call."""
    builder = enphase()
    session, system = AsyncMock(), _system()

    first = await get_live_power(session, system)
    frozen_clock(CACHE_TTL_SECONDS - 1)
    second = await get_live_power(session, system)

    assert first == second == READING
    assert builder.await_count == 1


@pytest.mark.asyncio
async def test_fetches_again_once_the_cache_expires(enphase, frozen_clock):
    builder = enphase()
    session, system = AsyncMock(), _system()

    await get_live_power(session, system)
    frozen_clock(CACHE_TTL_SECONDS)
    await get_live_power(session, system)

    assert builder.await_count == 2


@pytest.mark.asyncio
async def test_concurrent_callers_share_one_upstream_call(enphase):
    """Two dashboards loading at once must not each spend a request."""
    builder = enphase()
    session, system = AsyncMock(), _system()

    readings = await asyncio.gather(
        get_live_power(session, system), get_live_power(session, system)
    )

    assert readings == [READING, READING]
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

    assert await get_live_power(AsyncMock(), _system()) is None


@pytest.mark.asyncio
async def test_caches_a_failure_too(enphase, frozen_clock):
    """Retrying a dead upstream on every render spends the quota fastest."""
    builder = enphase(error=RuntimeError("rate limit"))
    session, system = AsyncMock(), _system()

    await get_live_power(session, system)
    frozen_clock(CACHE_TTL_SECONDS - 1)

    assert await get_live_power(session, system) is None
    assert builder.await_count == 1


@pytest.mark.asyncio
async def test_passes_through_a_system_that_has_never_reported(enphase):
    """No reading upstream is still no reading here, and not an error."""
    enphase(reading=None)

    assert await get_live_power(AsyncMock(), _system()) is None
