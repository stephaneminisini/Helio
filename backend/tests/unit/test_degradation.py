from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from helio.analytics.degradation import (
    calculate_annual_degradation,
    estimate_lost_production,
)


@pytest.mark.asyncio
async def test_calculate_annual_degradation_two_years():
    mock_session = AsyncMock()

    monthly_rows = [
        MagicMock(month=date(2023, m, 1), performance_ratio=Decimal("0.82"))
        for m in range(1, 13)
    ] + [
        MagicMock(month=date(2024, m, 1), performance_ratio=Decimal("0.80"))
        for m in range(1, 5)
    ]

    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=monthly_rows))
            )
        )
    )

    result = await calculate_annual_degradation(mock_session, system_id=1)
    assert 2023 in result
    assert result[2023]["avg_pr"] == pytest.approx(0.82, rel=1e-3)


def _session_with_one_shortfall_month() -> AsyncMock:
    """A session whose only month produced below its expected PR."""
    monthly_rows = [
        MagicMock(
            month=date(2024, 4, 1),
            production_kwh=Decimal("400"),
            performance_ratio=Decimal("0.78"),
            expected_pr=Decimal("0.82"),
        )
    ]
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=monthly_rows))
            )
        )
    )
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize("rate", [0.15, 0.42])
async def test_estimate_lost_production_prices_at_the_given_rate(rate):
    """AC3: lost_dollars is lost_kwh times the configured rate, nothing hidden."""
    result = await estimate_lost_production(
        _session_with_one_shortfall_month(), system_id=1, rate_per_kwh=rate
    )

    assert result["lost_kwh"] > 0
    assert result["lost_dollars"] == pytest.approx(result["lost_kwh"] * rate, abs=0.01)


@pytest.mark.asyncio
async def test_estimate_lost_production_at_a_zero_rate_costs_nothing():
    """A zero tariff is legitimate: the kWh shortfall stands, the price is 0."""
    result = await estimate_lost_production(
        _session_with_one_shortfall_month(), system_id=1, rate_per_kwh=0.0
    )

    assert result["lost_kwh"] > 0
    assert result["lost_dollars"] == 0.0
