from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from loguru import logger

from helio.db.models import System
from helio.ingestion import scheduler as scheduler_module
from helio.ingestion.tokens import TokenError


@pytest.fixture
def captured_logs():
    """Capture everything written to the logger for the duration of a test."""
    lines: list[str] = []
    sink_id = logger.add(lines.append, level="DEBUG")
    yield lines
    logger.remove(sink_id)


@pytest.fixture
def poll_env(monkeypatch):
    """Wire _daily_poll to a mocked session holding one system, and stub the steps.

    Returns the mocks for the steps that must not run when authentication fails.
    """
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=MagicMock(
                return_value=System(
                    id=1, enphase_system_id="sys-001", install_date=date(2023, 1, 1)
                )
            )
        )
    )

    @asynccontextmanager
    async def session_factory():
        yield session

    monkeypatch.setattr(scheduler_module, "AsyncSessionLocal", session_factory)
    steps = {
        "poll_intervals": AsyncMock(),
        "poll_irradiance": AsyncMock(),
        "build_daily_summary": AsyncMock(),
    }
    for name, mock in steps.items():
        monkeypatch.setattr(scheduler_module, name, mock)
    return steps


async def test_daily_poll_aborts_on_token_error_without_crashing(
    poll_env, captured_logs, monkeypatch
):
    """AC5: an undecryptable token logs an actionable error and stops the poll."""
    monkeypatch.setattr(
        scheduler_module,
        "build_authenticated_client",
        AsyncMock(
            side_effect=TokenError(
                "Stored Enphase refresh token cannot be "
                "decrypted with the current FERNET_KEY"
            )
        ),
    )

    await scheduler_module._daily_poll()

    combined = "".join(captured_logs)
    assert "FERNET_KEY" in combined
    assert "skipping daily poll" in combined
    for mock in poll_env.values():
        mock.assert_not_awaited()
