from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from loguru import logger

from helio.ingestion import scheduler
from helio.ingestion.enphase_client import PanelDataUnavailableError
from helio.ingestion.irradiance_client import (
    IrradianceUnavailableError,
    NASAClient,
)
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


@pytest.mark.asyncio
async def test_daily_poll_prefers_the_stored_source_over_the_env_var(
    located_system, monkeypatch
):
    """AC1: the DB value wins, so the Setup tab is not silently ignored."""
    system, steps = located_system
    system.irradiance_source = "nasa"
    monkeypatch.setattr(scheduler.settings, "irradiance_source", "manual")

    await scheduler.run_daily_poll()

    client, recorded_source = (
        steps["poll_irradiance"].await_args.args[1],
        steps["poll_irradiance"].await_args.args[-1],
    )
    assert isinstance(client, NASAClient)
    assert recorded_source == "nasa"


@pytest.mark.asyncio
async def test_daily_poll_leaves_an_unavailable_day_as_a_gap(located_system, logged):
    """AC3: a day the source cannot supply is logged and left for backfill."""
    _, steps = located_system
    steps["poll_irradiance"].side_effect = IrradianceUnavailableError(
        "NASA POWER reported ALLSKY_SFC_SW_DWN as unavailable (-999.0) for 20240428"
    )

    await scheduler.run_daily_poll()

    steps["poll_intervals"].assert_awaited_once()
    steps["build_daily_summary"].assert_awaited_once()
    combined = "".join(logged)
    assert "left for backfill" in combined
    assert "20240428" in combined


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
