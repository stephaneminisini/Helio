from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from helio.analytics.summarizer import build_daily_summary, build_monthly_summary


@pytest.mark.asyncio
async def test_build_daily_summary_aggregates_correctly():
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
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=mock_intervals))
            )
        )
    )
    mock_session.merge = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()

    await build_daily_summary(mock_session, system_id=1, day=date(2024, 4, 28))

    mock_session.merge.assert_called_once()
    call_arg = mock_session.merge.call_args[0][0]
    assert call_arg.production_kwh == pytest.approx(Decimal("1.700"), rel=1e-3)
    assert call_arg.peak_power_w is not None


@pytest.mark.asyncio
async def test_build_monthly_summary_calculates_pr():
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
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=daily_rows))
                )
            )
        return MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=irradiance_rows))
            )
        )

    mock_session.execute = mock_execute
    mock_session.merge = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()

    mock_system = MagicMock(
        system_size_kw=Decimal("10"),
        install_date=date(2023, 1, 1),
        degradation_rate=Decimal("0.5"),
    )

    await build_monthly_summary(
        mock_session,
        system_id=1,
        month=date(2024, 4, 1),
        system=mock_system,
    )

    mock_session.merge.assert_called_once()
    call_arg = mock_session.merge.call_args[0][0]
    assert call_arg.production_kwh == pytest.approx(Decimal("65"), rel=1e-3)
    assert call_arg.performance_ratio is not None
    assert 0 < float(call_arg.performance_ratio) < 2
