from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import httpx
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


def _http_error(status: int) -> httpx.HTTPStatusError:
    """Build the error a client's raise_for_status would raise for `status`."""
    request = httpx.Request("GET", "https://power.larc.nasa.gov/api/temporal/daily")
    return httpx.HTTPStatusError(
        str(status), request=request, response=httpx.Response(status, request=request)
    )


def _freeze_today(monkeypatch, today: date) -> None:
    """Pin the scheduler's notion of today so the polled date is predictable.

    Only date.today() is replaced, so the timedelta arithmetic that follows
    still runs on a real date.
    """
    monkeypatch.setattr(
        scheduler, "date", MagicMock(today=MagicMock(return_value=today))
    )


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


@pytest.mark.asyncio
async def test_daily_poll_stops_when_no_system_is_configured(
    poll_env, logged, monkeypatch
):
    """A fresh install has nothing to poll, so the job must say so and stop."""
    _, steps = poll_env
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    @asynccontextmanager
    async def factory():
        yield session

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", factory)

    await scheduler.run_daily_poll()

    for mock in steps.values():
        mock.assert_not_awaited()
    assert any("No system found" in line for line in logged)


@pytest.mark.asyncio
async def test_daily_poll_stops_on_an_unexpected_token_error(
    poll_env, logged, monkeypatch
):
    """Without a client every step would fail, so the job aborts as a whole."""
    _, steps = poll_env
    monkeypatch.setattr(
        scheduler,
        "build_authenticated_client",
        AsyncMock(side_effect=OSError("connection reset by peer")),
    )

    await scheduler.run_daily_poll()

    for mock in steps.values():
        mock.assert_not_awaited()
    combined = "".join(logged)
    assert "Unexpected token refresh error" in combined
    assert "connection reset by peer" in combined


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("step", "error", "reported"),
    [
        ("poll_intervals", RuntimeError("Enphase returned 500"), "intervals"),
        ("poll_irradiance", _http_error(503), "irradiance"),
        (
            "build_daily_summary",
            ValueError("no intervals for the day"),
            "daily_summary",
        ),
    ],
)
async def test_daily_poll_records_a_failed_step_and_carries_on(
    located_system, logged, step, error, reported
):
    """One broken source must not cost the day its remaining data."""
    _, steps = located_system
    steps[step].side_effect = error

    await scheduler.run_daily_poll()

    for name, mock in steps.items():
        if name != "build_monthly_summary":
            mock.assert_awaited_once()
    failures = [line for line in logged if "completed with failures" in line]
    assert len(failures) == 1
    assert reported in failures[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("step", "reported"),
    [
        ("poll_intervals", "intervals"),
        ("poll_panels", "panels"),
        ("poll_irradiance", "irradiance"),
        ("build_daily_summary", "daily_summary"),
    ],
)
async def test_daily_poll_reports_an_unanticipated_step_error(
    located_system, logged, step, reported
):
    """APScheduler discards a failing job's traceback, so nothing may escape.

    An error no handler named has to be logged and counted here or the poll
    would fail silently every night.
    """
    _, steps = located_system
    steps[step].side_effect = OSError("connection reset by peer")

    await scheduler.run_daily_poll()

    failures = [line for line in logged if "completed with failures" in line]
    assert len(failures) == 1
    assert reported in failures[0]
    assert any(
        "Unexpected" in line and "connection reset by peer" in line for line in logged
    )


@pytest.mark.asyncio
async def test_daily_poll_closes_the_previous_month_on_the_first(
    located_system, monkeypatch
):
    """The month can only be summarised once its last day has been polled."""
    system, steps = located_system
    _freeze_today(monkeypatch, date(2024, 5, 2))

    await scheduler.run_daily_poll()

    monthly = steps["build_monthly_summary"]
    monthly.assert_awaited_once()
    assert monthly.await_args.args[1:] == (system.id, date(2024, 4, 1), system)


@pytest.mark.asyncio
async def test_daily_poll_skips_the_monthly_summary_mid_month(
    located_system, monkeypatch
):
    """Summarising an unfinished month would publish a figure that then moves."""
    _, steps = located_system
    _freeze_today(monkeypatch, date(2024, 5, 17))

    await scheduler.run_daily_poll()

    steps["build_monthly_summary"].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError("no daily rows"), OSError("reset")])
async def test_daily_poll_records_a_failed_monthly_summary(
    located_system, logged, monkeypatch, error
):
    """The daily data is already stored, so a bad rollup is reported, not raised."""
    _, steps = located_system
    _freeze_today(monkeypatch, date(2024, 5, 2))
    steps["build_monthly_summary"].side_effect = error

    await scheduler.run_daily_poll()

    failures = [line for line in logged if "completed with failures" in line]
    assert len(failures) == 1
    assert "monthly_summary" in failures[0]


def test_start_scheduler_registers_the_daily_poll_at_the_configured_time(
    monkeypatch, logged
):
    """A wrong hour would move the poll outside the Enphase retention window."""
    instance = MagicMock()
    monkeypatch.setattr(scheduler, "scheduler", instance)
    monkeypatch.setattr(scheduler.settings, "poll_hour", 4)
    monkeypatch.setattr(scheduler.settings, "poll_minute", 30)

    scheduler.start_scheduler()

    instance.add_job.assert_called_once()
    args, kwargs = instance.add_job.call_args
    assert args == (scheduler.run_daily_poll, "cron")
    assert (kwargs["hour"], kwargs["minute"]) == (4, 30)
    # Replacing keeps a restart from stacking a second identical job.
    assert kwargs["id"] == "daily_poll"
    assert kwargs["replace_existing"] is True
    instance.start.assert_called_once()
    assert any("04:30" in line for line in logged)
