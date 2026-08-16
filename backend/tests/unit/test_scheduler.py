from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from loguru import logger

from helio.ingestion import scheduler
from helio.ingestion.enphase_client import PanelDataUnavailableError
from helio.ingestion.tokens import TokenError


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
            "poll_panels",
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
async def test_daily_poll_continues_when_panel_data_is_unavailable(poll_env, logged):
    """AC4: a plan without per-panel access explains itself and degrades quietly.

    Treating it as a failure would make every poll on such an install report a
    failure forever, so the run must still come out clean.
    """
    system, steps = poll_env
    system.latitude = Decimal("45.5231")
    system.longitude = Decimal("-122.6765")
    steps["poll_panels"].side_effect = PanelDataUnavailableError(
        "Enphase answered 403 for device-level telemetry."
    )

    await scheduler.run_daily_poll()

    steps["poll_intervals"].assert_awaited_once()
    steps["poll_irradiance"].assert_awaited_once()
    steps["build_daily_summary"].assert_awaited_once()
    skipped = [line for line in logged if "Panel poll skipped" in line]
    assert len(skipped) == 1
    assert "403" in skipped[0]
    assert any("Daily poll complete for" in line for line in logged)


@pytest.mark.asyncio
async def test_daily_poll_reports_a_genuine_panel_failure(poll_env, logged):
    """A rate-limited panel poll is a fault, so it must show up as one."""
    system, steps = poll_env
    system.latitude = Decimal("45.5231")
    system.longitude = Decimal("-122.6765")
    steps["poll_panels"].side_effect = RuntimeError("rate limit")

    await scheduler.run_daily_poll()

    steps["build_daily_summary"].assert_awaited_once()
    failures = [line for line in logged if "completed with failures" in line]
    assert len(failures) == 1
    assert "panels" in failures[0]


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
