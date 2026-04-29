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


@pytest.mark.asyncio
async def test_estimate_lost_production_returns_kwh_and_dollars():
    mock_session = AsyncMock()

    monthly_rows = [
        MagicMock(
            month=date(2024, 4, 1),
            production_kwh=Decimal("400"),
            performance_ratio=Decimal("0.78"),
            expected_pr=Decimal("0.82"),
        )
    ]

    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=monthly_rows))
            )
        )
    )

    result = await estimate_lost_production(
        mock_session, system_id=1, rate_per_kwh=0.15
    )
    assert result["lost_kwh"] > 0
    assert result["lost_dollars"] > 0
    assert result["lost_dollars"] == pytest.approx(result["lost_kwh"] * 0.15, rel=1e-3)
