from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from loguru import logger

from helio.ingestion import scheduler
from helio.ingestion.irradiance_client import NASAClient, NRELClient
from helio.ingestion.tokens import TokenError


@pytest.fixture
def located_system(poll_env):
    """The poll_env system with coordinates set so irradiance is attempted."""
    system, steps = poll_env
    system.latitude = Decimal("45.5231")
    system.longitude = Decimal("-122.6765")
    return system, steps


@pytest.fixture
def logged() -> list[str]:
    """Collect loguru messages; its default sink bypasses capsys."""
    messages: list[str] = []
    handler_id = logger.add(messages.append, format="{message}")
    yield messages
    logger.remove(handler_id)


@pytest.fixture
def poll_env(monkeypatch):
    """Patch the scheduler's collaborators so the daily poll runs in memory.

    Returns the mocked system and the patched ingestion steps keyed by name.
    """
    system = MagicMock(
        id=1,
        latitude=None,
        longitude=None,
        tilt_angle_deg=Decimal("30"),
        azimuth_deg=Decimal("180"),
        irradiance_source="nasa",
    )
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=system))
    )

    @asynccontextmanager
    async def factory():
        yield session

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", factory)
    monkeypatch.setattr(scheduler, "build_authenticated_client", AsyncMock())
    steps = {
        name: AsyncMock()
        for name in (
            "poll_intervals",
            "poll_irradiance",
            "build_daily_summary",
            "build_monthly_summary",
        )
    }
    for name, mock in steps.items():
        monkeypatch.setattr(scheduler, name, mock)
    return system, steps


@pytest.mark.asyncio
async def test_daily_poll_skips_irradiance_without_coordinates(poll_env, logged):
    """Fetching 0,0 would silently corrupt PR, so the step must be skipped."""
    _, steps = poll_env

    await scheduler.run_daily_poll()

    steps["poll_irradiance"].assert_not_awaited()
    messages = "".join(logged)
    assert "Setup tab" in messages
    assert "irradiance" in messages


@pytest.mark.asyncio
async def test_daily_poll_uses_the_configured_coordinates(poll_env):
    system, steps = poll_env
    system.latitude = Decimal("45.5231")
    system.longitude = Decimal("-122.6765")

    await scheduler.run_daily_poll()

    irradiance = steps["poll_irradiance"]
    irradiance.assert_awaited_once()
    latitude, longitude = irradiance.await_args.args[3:5]
    assert (latitude, longitude) == (45.5231, -122.6765)


@pytest.mark.asyncio
async def test_daily_poll_still_polls_intervals_without_coordinates(poll_env):
    """Production data does not depend on the site location."""
    _, steps = poll_env

    await scheduler.run_daily_poll()

    steps["poll_intervals"].assert_awaited_once()
    steps["build_daily_summary"].assert_awaited_once()


@pytest.mark.asyncio
async def test_daily_poll_aborts_on_token_error_without_crashing(
    poll_env, logged, monkeypatch
):
    """An undecryptable token logs an actionable error and stops the poll."""
    _, steps = poll_env
    monkeypatch.setattr(
        scheduler,
        "build_authenticated_client",
        AsyncMock(
            side_effect=TokenError(
                "Stored Enphase refresh token cannot be "
                "decrypted with the current FERNET_KEY"
            )
        ),
    )

    await scheduler.run_daily_poll()

    combined = "".join(logged)
    assert "FERNET_KEY" in combined
    assert "skipping daily poll" in combined
    for mock in steps.values():
        mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_daily_poll_prefers_the_stored_source_over_the_env_var(
    located_system, monkeypatch
):
    """AC1: the DB value wins, so the Setup tab is not silently ignored."""
    system, steps = located_system
    system.irradiance_source = "nasa"
    monkeypatch.setattr(scheduler.settings, "irradiance_source", "nrel")
    monkeypatch.setattr(scheduler.settings, "nrel_api_key", "test-key")

    await scheduler.run_daily_poll()

    client, recorded_source = (
        steps["poll_irradiance"].await_args.args[1],
        steps["poll_irradiance"].await_args.args[-1],
    )
    assert isinstance(client, NASAClient)
    assert recorded_source == "nasa"


@pytest.mark.asyncio
async def test_daily_poll_uses_nrel_when_the_system_selects_it(
    located_system, monkeypatch
):
    """AC2: switching the source takes effect on the next poll, no restart."""
    system, steps = located_system
    system.irradiance_source = "nrel"
    monkeypatch.setattr(scheduler.settings, "irradiance_source", "nasa")
    monkeypatch.setattr(scheduler.settings, "nrel_api_key", "test-key")

    await scheduler.run_daily_poll()

    assert isinstance(steps["poll_irradiance"].await_args.args[1], NRELClient)
    assert steps["poll_irradiance"].await_args.args[-1] == "nrel"


@pytest.mark.asyncio
async def test_daily_poll_skips_irradiance_when_nrel_key_is_missing(
    located_system, logged, monkeypatch
):
    """AC4: the key is named in the log and the interval poll still runs."""
    system, steps = located_system
    system.irradiance_source = "nrel"
    monkeypatch.setattr(scheduler.settings, "nrel_api_key", "")

    await scheduler.run_daily_poll()

    steps["poll_irradiance"].assert_not_awaited()
    steps["poll_intervals"].assert_awaited_once()
    steps["build_daily_summary"].assert_awaited_once()
    assert "NREL_API_KEY" in "".join(logged)


@pytest.mark.asyncio
async def test_daily_poll_skips_irradiance_for_a_manual_source(located_system, logged):
    """A manual source fetches nothing by design, so it is not a failure."""
    system, steps = located_system
    system.irradiance_source = "manual"

    await scheduler.run_daily_poll()

    steps["poll_irradiance"].assert_not_awaited()
    assert "completed with failures" not in "".join(logged)


@pytest.mark.asyncio
async def test_daily_poll_skips_irradiance_for_an_unsupported_source(
    located_system, logged
):
    """A source no client can serve is reported rather than silently ignored."""
    system, steps = located_system
    system.irradiance_source = "sunshine-vibes"

    await scheduler.run_daily_poll()

    steps["poll_irradiance"].assert_not_awaited()
    steps["poll_intervals"].assert_awaited_once()
    combined = "".join(logged)
    assert "sunshine-vibes" in combined
    assert "not supported" in combined
