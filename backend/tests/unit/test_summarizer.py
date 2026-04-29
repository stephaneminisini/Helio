from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from helio.analytics.summarizer import build_daily_summary, build_monthly_summary


@pytest.mark.asyncio
async def test_build_daily_summary_aggregates_correctly():
    """Test insert path: no existing row, session.add is called with correct values."""
    mock_session = AsyncMock()
    mock_intervals = [
        MagicMock(
            production_wh=Decimal("500"),
            interval_start=datetime(2024, 4, 28, 10, 0, tzinfo=UTC),
        ),
        MagicMock(
            production_wh=Decimal("800"),
            interval_start=datetime(2024, 4, 28, 12, 0, tzinfo=UTC),
        ),
        MagicMock(
            production_wh=Decimal("400"),
            interval_start=datetime(2024, 4, 28, 14, 0, tzinfo=UTC),
        ),
    ]

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: fetch intervals
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=mock_intervals))
                )
            )
        # Second call: upsert lookup — no existing row
        return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    result = await build_daily_summary(mock_session, system_id=1, day=date(2024, 4, 28))

    mock_session.add.assert_called_once()
    added_row = mock_session.add.call_args[0][0]
    assert added_row.production_kwh == pytest.approx(Decimal("1.700"), rel=1e-3)
    assert added_row.peak_power_w is not None
    assert result is added_row


@pytest.mark.asyncio
async def test_build_daily_summary_updates_existing_row():
    """Test update path: existing row found, attributes updated, session.add not called."""
    mock_session = AsyncMock()
    mock_intervals = [
        MagicMock(
            production_wh=Decimal("600"),
            interval_start=datetime(2024, 4, 28, 10, 0, tzinfo=UTC),
        ),
    ]

    existing_row = MagicMock()
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=mock_intervals))
                )
            )
        return MagicMock(scalar_one_or_none=MagicMock(return_value=existing_row))

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    result = await build_daily_summary(mock_session, system_id=1, day=date(2024, 4, 28))

    mock_session.add.assert_not_called()
    assert result is existing_row
    assert existing_row.production_kwh == Decimal(str(round(600 / 1000, 3)))
    assert existing_row.interval_count == 1


@pytest.mark.asyncio
async def test_build_monthly_summary_calculates_pr():
    """Test insert path: no existing row, session.add is called with correct PR values."""
    mock_session = AsyncMock()

    daily_rows = [
        MagicMock(production_kwh=Decimal("30")),
        MagicMock(production_kwh=Decimal("35")),
    ]
    irradiance_rows = [
        MagicMock(poa_kwh_m2=Decimal("5.0")),
        MagicMock(poa_kwh_m2=Decimal("6.0")),
    ]

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Daily summaries query
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=daily_rows))
                )
            )
        if call_count == 2:
            # Irradiance query
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=irradiance_rows))
                )
            )
        # Third call: upsert lookup — no existing row
        return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_system = MagicMock(
        system_size_kw=Decimal("10"),
        install_date=date(2023, 1, 1),
        degradation_rate=Decimal("0.5"),
    )

    result = await build_monthly_summary(
        mock_session,
        system_id=1,
        month=date(2024, 4, 1),
        system=mock_system,
    )

    mock_session.add.assert_called_once()
    added_row = mock_session.add.call_args[0][0]
    assert added_row.production_kwh == pytest.approx(Decimal("65"), rel=1e-3)
    assert added_row.performance_ratio is not None
    assert 0 < float(added_row.performance_ratio) < 2
    assert result is added_row


@pytest.mark.asyncio
async def test_build_monthly_summary_updates_existing_row():
    """Test update path: existing monthly row found, attributes updated, add not called."""
    mock_session = AsyncMock()

    daily_rows = [MagicMock(production_kwh=Decimal("40"))]
    irradiance_rows = [MagicMock(poa_kwh_m2=Decimal("4.0"))]
    existing_row = MagicMock()

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=daily_rows))
                )
            )
        if call_count == 2:
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=irradiance_rows))
                )
            )
        return MagicMock(scalar_one_or_none=MagicMock(return_value=existing_row))

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_system = MagicMock(
        system_size_kw=Decimal("10"),
        install_date=date(2023, 1, 1),
        degradation_rate=Decimal("0.5"),
    )

    result = await build_monthly_summary(
        mock_session,
        system_id=1,
        month=date(2024, 4, 1),
        system=mock_system,
    )

    mock_session.add.assert_not_called()
    assert result is existing_row
    assert existing_row.production_kwh == Decimal("40")
