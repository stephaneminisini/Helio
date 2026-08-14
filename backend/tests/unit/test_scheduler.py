from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from loguru import logger

from helio.ingestion import scheduler


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

    Returns the mocked system and the patched poll_irradiance.
    """
    system = MagicMock(
        id=1,
        latitude=None,
        longitude=None,
        tilt_angle_deg=Decimal("30"),
        azimuth_deg=Decimal("180"),
    )
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=system))
    )

    @asynccontextmanager
    async def factory():
        yield session

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", factory)
    monkeypatch.setattr(scheduler, "EnphaseClient", MagicMock(return_value=AsyncMock()))
    monkeypatch.setattr(scheduler, "poll_intervals", AsyncMock())
    monkeypatch.setattr(scheduler, "build_daily_summary", AsyncMock())
    monkeypatch.setattr(scheduler, "build_monthly_summary", AsyncMock())
    irradiance = AsyncMock()
    monkeypatch.setattr(scheduler, "poll_irradiance", irradiance)
    return system, irradiance


@pytest.mark.asyncio
async def test_daily_poll_skips_irradiance_without_coordinates(poll_env, logged):
    """Fetching 0,0 would silently corrupt PR, so the step must be skipped."""
    _, irradiance = poll_env

    await scheduler._daily_poll()

    irradiance.assert_not_awaited()
    messages = "".join(logged)
    assert "Setup tab" in messages
    assert "irradiance" in messages


@pytest.mark.asyncio
async def test_daily_poll_uses_the_configured_coordinates(poll_env):
    system, irradiance = poll_env
    system.latitude = Decimal("45.5231")
    system.longitude = Decimal("-122.6765")

    await scheduler._daily_poll()

    irradiance.assert_awaited_once()
    latitude, longitude = irradiance.await_args.args[3:5]
    assert (latitude, longitude) == (45.5231, -122.6765)


@pytest.mark.asyncio
async def test_daily_poll_still_polls_intervals_without_coordinates(poll_env):
    """Production data does not depend on the site location."""
    await scheduler._daily_poll()

    scheduler.poll_intervals.assert_awaited_once()
    scheduler.build_daily_summary.assert_awaited_once()
