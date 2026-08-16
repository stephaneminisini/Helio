from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from helio.db.models import EnergyInterval, PanelReading, PollLog
from helio.ingestion.enphase_client import (
    IntervalData,
    PanelDataUnavailableError,
    PanelEnergy,
)
from helio.ingestion.poller import (
    detect_gaps,
    irradiance_location,
    poll_intervals,
    poll_panels,
)

POLL_DAY = date(2024, 4, 28)


def _panel_session(existing: list[PanelReading] | None = None) -> AsyncMock:
    """Mock session whose only query returns the given panel_readings rows."""
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=existing or []))
            )
        )
    )
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


def _added(session: AsyncMock, model: type) -> list:
    """Return the objects of the given type handed to session.add()."""
    return [
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], model)
    ]


def test_irradiance_location_returns_the_configured_coordinates():
    system = MagicMock(latitude=Decimal("45.5231"), longitude=Decimal("-122.6765"))

    assert irradiance_location(system) == (45.5231, -122.6765)


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (None, Decimal("-122.6765")),
        (Decimal("45.5231"), None),
        (None, None),
    ],
)
def test_irradiance_location_refuses_to_default_to_the_gulf_of_guinea(
    latitude, longitude
):
    """0,0 would silently corrupt every performance ratio derived from it."""
    system = MagicMock(latitude=latitude, longitude=longitude)

    assert irradiance_location(system) is None


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


@pytest.mark.asyncio
async def test_poll_panels_writes_one_row_per_panel_and_a_poll_log():
    """AC2: a successful poll stores every panel and records the run."""
    session = _panel_session()
    client = AsyncMock()
    client.get_panel_data = AsyncMock(
        return_value=[
            PanelEnergy(panel_serial="482218012345", energy_wh=41.0),
            PanelEnergy(panel_serial="482218012346", energy_wh=19.0),
        ]
    )

    fetched, inserted = await poll_panels(session, client, 1, POLL_DAY)

    assert (fetched, inserted) == (2, 2)
    assert [
        (row.panel_serial, row.energy_wh, row.day)
        for row in _added(session, PanelReading)
    ] == [
        ("482218012345", 41.0, POLL_DAY),
        ("482218012346", 19.0, POLL_DAY),
    ]
    log = _added(session, PollLog)[-1]
    assert (log.poll_type, log.status, log.records_fetched, log.records_inserted) == (
        "panels",
        "success",
        2,
        2,
    )
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_poll_panels_updates_a_repolled_day_instead_of_duplicating_it():
    """AC3: the (system, panel, day) grain means a re-poll overwrites in place."""
    existing = PanelReading(
        system_id=1,
        panel_serial="482218012345",
        day=POLL_DAY,
        energy_wh=Decimal("41.000"),
    )
    session = _panel_session([existing])
    client = AsyncMock()
    client.get_panel_data = AsyncMock(
        return_value=[PanelEnergy(panel_serial="482218012345", energy_wh=44.0)]
    )

    fetched, inserted = await poll_panels(session, client, 1, POLL_DAY)

    assert (fetched, inserted) == (1, 0)
    assert existing.energy_wh == 44.0
    assert _added(session, PanelReading) == []


@pytest.mark.asyncio
async def test_poll_panels_records_a_partial_poll_when_no_panels_report():
    """An empty device list is how a plan without per-panel access can present."""
    session = _panel_session()
    client = AsyncMock()
    client.get_panel_data = AsyncMock(return_value=[])

    with pytest.raises(PanelDataUnavailableError, match="no microinverters"):
        await poll_panels(session, client, 1, POLL_DAY)

    session.rollback.assert_awaited_once()
    log = _added(session, PollLog)[-1]
    assert (log.poll_type, log.status) == ("panels", "partial")
    assert "no microinverters" in log.error_message


@pytest.mark.asyncio
async def test_poll_panels_records_a_partial_poll_when_the_plan_denies_access():
    """A 401/403 from Enphase is a capability limit, so not an error row."""
    session = _panel_session()
    client = AsyncMock()
    client.get_panel_data = AsyncMock(
        side_effect=PanelDataUnavailableError("Enphase answered 403")
    )

    with pytest.raises(PanelDataUnavailableError):
        await poll_panels(session, client, 1, POLL_DAY)

    log = _added(session, PollLog)[-1]
    assert log.status == "partial"
    assert _added(session, PanelReading) == []


@pytest.mark.asyncio
async def test_poll_panels_records_an_error_when_the_api_rate_limits():
    """A genuine fault must stay distinguishable from an unavailable plan."""
    session = _panel_session()
    client = AsyncMock()
    client.get_panel_data = AsyncMock(side_effect=RuntimeError("rate limit"))

    with pytest.raises(RuntimeError, match="rate limit"):
        await poll_panels(session, client, 1, POLL_DAY)

    log = _added(session, PollLog)[-1]
    assert (log.status, log.error_message) == ("error", "rate limit")


@pytest.mark.asyncio
async def test_poll_intervals_logs_error_and_reraises_on_failure():
    from datetime import date as d

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )
    )
    mock_session.flush = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    mock_client = AsyncMock()
    mock_client.get_intervals = AsyncMock(side_effect=RuntimeError("rate limit"))

    with pytest.raises(RuntimeError, match="rate limit"):
        await poll_intervals(
            session=mock_session,
            client=mock_client,
            system_id=1,
            start_date=d(2024, 4, 28),
            end_date=d(2024, 4, 28),
        )

    mock_session.rollback.assert_called_once()
