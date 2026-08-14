from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from loguru import logger

from helio import cli
from helio.cli import EXIT_NO_SYSTEM, POLL_STATUS_LIMIT, main

COMMANDS = ["backfill", "poll-now", "poll-status", "rebuild-summaries", "seed-mock"]


@pytest.fixture
def session(monkeypatch) -> AsyncMock:
    """Patch AsyncSessionLocal so commands run against a mocked session."""
    mock_session = AsyncMock()

    @asynccontextmanager
    async def factory():
        yield mock_session

    monkeypatch.setattr(cli, "AsyncSessionLocal", factory)
    return mock_session


@pytest.fixture
def logged() -> list[str]:
    """Collect loguru messages; its default sink bypasses capsys."""
    messages: list[str] = []
    handler_id = logger.add(messages.append, format="{message}")
    yield messages
    logger.remove(handler_id)


def _returns_system(session: AsyncMock, system: MagicMock | None) -> None:
    """Make the system lookup resolve to `system` (None means not configured)."""
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=system))
    )


def _poll_log(**overrides) -> MagicMock:
    """Build a stand-in poll_log row."""
    defaults = {
        "started_at": datetime(2024, 4, 28, 6, 30, tzinfo=UTC),
        "poll_type": "daily",
        "status": "success",
        "records_fetched": 96,
        "records_inserted": 96,
        "error_message": None,
    }
    return MagicMock(**{**defaults, **overrides})


@pytest.mark.parametrize("command", COMMANDS)
def test_every_command_exits_with_a_setup_pointer_when_unconfigured(
    command, session, logged, monkeypatch
):
    """A fresh install must get an actionable message, not a traceback."""
    _returns_system(session, None)
    # Guard: a worker must never be reached without a system.
    for name in ("backfill", "run_daily_poll", "recent_polls"):
        monkeypatch.setattr(cli, name, AsyncMock(side_effect=AssertionError(name)))

    assert main([command]) == EXIT_NO_SYSTEM
    assert "Setup tab" in "".join(logged)


def test_backfill_delegates_to_the_ingestion_worker(session, monkeypatch):
    system = MagicMock(id=1)
    _returns_system(session, system)
    worker = AsyncMock()
    monkeypatch.setattr(cli, "backfill", worker)

    assert main(["backfill"]) == 0
    worker.assert_awaited_once_with(session, system)


def test_poll_now_runs_the_scheduled_job(session, monkeypatch):
    _returns_system(session, MagicMock(id=1))
    worker = AsyncMock()
    monkeypatch.setattr(cli, "run_daily_poll", worker)

    assert main(["poll-now"]) == 0
    worker.assert_awaited_once_with()


def test_rebuild_summaries_reports_what_it_rebuilt(session, monkeypatch, capsys):
    system = MagicMock(id=1)
    _returns_system(session, system)
    worker = AsyncMock(return_value=(30, 2))
    monkeypatch.setattr(cli, "rebuild_all_summaries", worker)

    assert main(["rebuild-summaries"]) == 0
    worker.assert_awaited_once_with(session, system)
    assert "Rebuilt 30 daily and 2 monthly summaries." in capsys.readouterr().out


def test_seed_mock_passes_the_requested_year_count(session, monkeypatch, capsys):
    system = MagicMock(id=1)
    _returns_system(session, system)
    worker = AsyncMock(return_value=(96, 1))
    monkeypatch.setattr(cli, "seed_mock", worker)

    assert main(["seed-mock", "--years", "1"]) == 0
    worker.assert_awaited_once_with(session, system, years=1)
    assert "Seeded 96 intervals and 1 irradiance days." in capsys.readouterr().out


def test_poll_status_prints_the_recent_runs(session, monkeypatch, capsys):
    _returns_system(session, MagicMock(id=1))
    rows = [_poll_log(), _poll_log(poll_type="backfill", records_inserted=0)]
    monkeypatch.setattr(cli, "recent_polls", AsyncMock(return_value=rows))

    assert main(["poll-status"]) == 0
    out = capsys.readouterr().out
    assert "STARTED (UTC)" in out
    assert out.count("2024-04-28 06:30:00") == 2
    assert "backfill" in out


def test_poll_status_surfaces_the_failure_reason(session, monkeypatch, capsys):
    """A failed poll is only useful if the operator can see why it failed."""
    _returns_system(session, MagicMock(id=1))
    row = _poll_log(status="failed", error_message="401 Unauthorized")
    monkeypatch.setattr(cli, "recent_polls", AsyncMock(return_value=[row]))

    assert main(["poll-status"]) == 0
    out = capsys.readouterr().out
    assert "failed" in out
    assert "error: 401 Unauthorized" in out


def test_poll_status_asks_for_at_most_ten_runs(session, monkeypatch):
    _returns_system(session, MagicMock(id=1))
    query = AsyncMock(return_value=[])
    monkeypatch.setattr(cli, "recent_polls", query)

    assert main(["poll-status"]) == 0
    query.assert_awaited_once_with(session, POLL_STATUS_LIMIT)
    assert POLL_STATUS_LIMIT == 10


def test_poll_status_says_so_when_nothing_has_run(session, monkeypatch, capsys):
    _returns_system(session, MagicMock(id=1))
    monkeypatch.setattr(cli, "recent_polls", AsyncMock(return_value=[]))

    assert main(["poll-status"]) == 0
    assert "No polls have run yet." in capsys.readouterr().out


def test_an_unknown_command_is_rejected():
    with pytest.raises(SystemExit) as exc:
        main(["not-a-command"])

    assert exc.value.code != 0
