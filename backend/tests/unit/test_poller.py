from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from helio.db.models import EnergyInterval
from helio.ingestion.enphase_client import IntervalData
from helio.ingestion.poller import detect_gaps, poll_intervals


@pytest.mark.asyncio
async def test_detect_gaps_returns_missing_dates():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(
                    all=MagicMock(return_value=[date(2024, 4, 1), date(2024, 4, 3)])
                )
            )
        )
    )

    gaps = await detect_gaps(
        session=mock_session,
        system_id=1,
        start_date=date(2024, 4, 1),
        end_date=date(2024, 4, 4),
    )
    assert date(2024, 4, 2) in gaps
    assert date(2024, 4, 4) in gaps
    assert date(2024, 4, 1) not in gaps
    assert date(2024, 4, 3) not in gaps


@pytest.mark.asyncio
async def test_detect_gaps_no_gaps():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(
                    all=MagicMock(
                        return_value=[
                            date(2024, 4, 1),
                            date(2024, 4, 2),
                            date(2024, 4, 3),
                        ]
                    )
                )
            )
        )
    )

    gaps = await detect_gaps(
        session=mock_session,
        system_id=1,
        start_date=date(2024, 4, 1),
        end_date=date(2024, 4, 3),
    )
    assert gaps == []


@pytest.mark.asyncio
async def test_poll_intervals_inserts_new_records():
    mock_session = AsyncMock()
    # execute: batch timestamp query returns empty set (no existing records)
    mock_session.execute = AsyncMock(
        side_effect=[
            MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[]))
                )
            ),
        ]
    )
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    mock_client = AsyncMock()
    mock_client.get_intervals = AsyncMock(
        return_value=[
            IntervalData(
                interval_start=datetime(2024, 4, 28, 10, 0, tzinfo=UTC),
                duration_seconds=900,
                production_wh=1250.0,
            )
        ]
    )

    fetched, inserted = await poll_intervals(
        session=mock_session,
        client=mock_client,
        system_id=1,
        start_date=date(2024, 4, 28),
        end_date=date(2024, 4, 28),
    )

    assert fetched == 1
    assert inserted == 1
    mock_session.add.assert_called()


@pytest.mark.asyncio
async def test_poll_intervals_skips_existing_records():
    existing_ts = datetime(2024, 4, 28, 10, 0, tzinfo=UTC)
    mock_session = AsyncMock()
    # execute is called once with batch timestamp query: returns the existing timestamp
    mock_session.execute = AsyncMock(
        side_effect=[
            MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[existing_ts]))
                )
            ),
        ]
    )
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    mock_client = AsyncMock()
    mock_client.get_intervals = AsyncMock(
        return_value=[
            IntervalData(
                interval_start=existing_ts,
                duration_seconds=900,
                production_wh=1250.0,
            )
        ]
    )

    fetched, inserted = await poll_intervals(
        session=mock_session,
        client=mock_client,
        system_id=1,
        start_date=date(2024, 4, 28),
        end_date=date(2024, 4, 28),
    )

    assert fetched == 1
    assert inserted == 0
    # Verify no EnergyInterval was added (only poll_log was added via session.add)
    add_calls = mock_session.add.call_args_list
    for call in add_calls:
        assert not isinstance(call.args[0], EnergyInterval)
