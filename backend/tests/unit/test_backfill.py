from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from helio.ingestion import backfill as backfill_module
from helio.ingestion.backfill import backfill, progress


@pytest.fixture(autouse=True)
def reset_progress():
    """Reset the module-level progress singleton around every test."""
    progress.running = False
    progress.total_days = 0
    progress.completed_days = 0
    progress.failed_days = 0
    progress.error = None
    yield
    progress.running = False


def _session_factory(session):
    """Build a stand-in for AsyncSessionLocal yielding the given mock session.

    Args:
        session: The mock session `async with AsyncSessionLocal()` should yield.

    Returns:
        A callable returning an async context manager.
    """
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx)


def _mock_system():
    """Build a System-shaped mock with a usable install date and coordinates."""
    system = MagicMock()
    system.id = 1
    system.install_date = date(2024, 1, 1)
    system.latitude = 45.5
    system.longitude = -73.6
    system.tilt_angle_deg = 30
    system.azimuth_deg = 180
    return system


def _session_returning(system):
    """Build a mock session whose first execute() resolves to the given system."""
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=system))
    )
    return session


@pytest.mark.asyncio
async def test_backfill_records_error_when_no_system_configured():
    session = _session_returning(None)

    with patch.object(backfill_module, "AsyncSessionLocal", _session_factory(session)):
        await backfill()

    assert progress.running is False
    assert progress.error is not None
    assert "setup" in progress.error.lower()


@pytest.mark.asyncio
async def test_backfill_refuses_concurrent_start():
    progress.running = True
    factory = _session_factory(_session_returning(_mock_system()))

    with patch.object(backfill_module, "AsyncSessionLocal", factory):
        await backfill()

    factory.assert_not_called()
    assert progress.running is True


@pytest.mark.asyncio
async def test_backfill_reports_credential_failure():
    session = _session_returning(_mock_system())
    client = AsyncMock()
    client.refresh_access_token = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "401", request=MagicMock(), response=MagicMock()
        )
    )

    with (
        patch.object(backfill_module, "AsyncSessionLocal", _session_factory(session)),
        patch.object(backfill_module, "EnphaseClient", MagicMock(return_value=client)),
    ):
        await backfill()

    assert progress.running is False
    assert progress.error is not None
    assert "ENPHASE_ACCESS_TOKEN" in progress.error


@pytest.mark.asyncio
async def test_backfill_counts_progress_across_days():
    session = _session_returning(_mock_system())
    client = AsyncMock()
    client.refresh_access_token = AsyncMock()
    gaps = [date(2024, 4, 1), date(2024, 4, 2), date(2024, 4, 3)]

    with (
        patch.object(backfill_module, "AsyncSessionLocal", _session_factory(session)),
        patch.object(backfill_module, "EnphaseClient", MagicMock(return_value=client)),
        patch.object(backfill_module, "NRELClient", MagicMock()),
        patch.object(backfill_module, "NASAClient", MagicMock()),
        patch.object(backfill_module, "INTER_DAY_PAUSE_SECONDS", 0),
        patch.object(backfill_module, "detect_gaps", AsyncMock(return_value=gaps)),
        patch.object(
            backfill_module, "poll_intervals", AsyncMock(return_value=(88, 88))
        ),
        patch.object(backfill_module, "poll_irradiance", AsyncMock()),
        patch.object(backfill_module, "build_daily_summary", AsyncMock()),
    ):
        await backfill()

    assert progress.total_days == 3
    assert progress.completed_days == 3
    assert progress.failed_days == 0
    assert progress.error is None
    assert progress.running is False


@pytest.mark.asyncio
async def test_backfill_isolates_a_failing_day():
    session = _session_returning(_mock_system())
    client = AsyncMock()
    client.refresh_access_token = AsyncMock()
    gaps = [date(2024, 4, 1), date(2024, 4, 2)]
    summary = AsyncMock()

    with (
        patch.object(backfill_module, "AsyncSessionLocal", _session_factory(session)),
        patch.object(backfill_module, "EnphaseClient", MagicMock(return_value=client)),
        patch.object(backfill_module, "NRELClient", MagicMock()),
        patch.object(backfill_module, "NASAClient", MagicMock()),
        patch.object(backfill_module, "INTER_DAY_PAUSE_SECONDS", 0),
        patch.object(backfill_module, "detect_gaps", AsyncMock(return_value=gaps)),
        patch.object(
            backfill_module,
            "poll_intervals",
            AsyncMock(side_effect=[RuntimeError("rate limit"), (88, 88)]),
        ),
        patch.object(backfill_module, "poll_irradiance", AsyncMock()),
        patch.object(backfill_module, "build_daily_summary", summary),
    ):
        await backfill()

    assert progress.total_days == 2
    assert progress.completed_days == 2
    assert progress.failed_days == 1
    # The day whose intervals failed must not get a summary built from nothing.
    assert summary.await_count == 1
