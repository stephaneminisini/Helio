from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from helio.analytics.degradation import (
    calculate_annual_degradation,
    estimate_lost_production,
    project_future_efficiency,
)
from helio.db.models import System


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


INSTALL_DATE = date(2020, 1, 1)


def _projection_system(warranty: str = "0.7") -> MagicMock:
    """A system installed on INSTALL_DATE with the given warranty, in percent/yr."""
    system = MagicMock(spec=System)
    system.id = 1
    system.install_date = INSTALL_DATE
    system.warranty_degradation_rate = Decimal(warranty)
    return system


def _session_with_history(
    months: int,
    annual_loss: float,
    start: date = date(2021, 1, 1),
    baseline: float = 0.85,
) -> AsyncMock:
    """A session whose monthly PR declines by `annual_loss` per year, exactly.

    Building the series from the same straight line the projection fits lets the
    tests assert recovered slopes and projected values rather than ranges.
    """
    rows = []
    for offset in range(months):
        month = date(
            start.year + (start.month - 1 + offset) // 12,
            (start.month - 1 + offset) % 12 + 1,
            1,
        )
        elapsed = (month - INSTALL_DATE).days / 365.25
        rows.append(
            MagicMock(
                month=month,
                performance_ratio=Decimal(
                    str(round(baseline - annual_loss * elapsed, 6))
                ),
            )
        )
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
        )
    )
    return session


@pytest.mark.asyncio
async def test_projection_extrapolates_the_observed_rate_per_year():
    """AC1: three years of history yield a rate, a per-year series and its size."""
    session = _session_with_history(months=36, annual_loss=0.008)

    result = await project_future_efficiency(session, _projection_system(), 5)

    assert result["months_of_history"] == 36
    assert result["low_confidence"] is False
    assert result["annual_rate"] == pytest.approx(0.008, abs=1e-4)
    assert [entry["year"] for entry in result["years"]] == [
        2024,
        2025,
        2026,
        2027,
        2028,
    ]
    # 2028-07-01 is 8.5 years after install: 0.85 - 0.008 * 8.5.
    assert result["years"][-1]["projected_pr"] == pytest.approx(0.782, abs=1e-3)


@pytest.mark.asyncio
async def test_projection_from_under_a_year_is_flagged_low_confidence():
    """AC2: a partial year cannot be presented as a firm forecast."""
    session = _session_with_history(months=6, annual_loss=0.008)

    result = await project_future_efficiency(session, _projection_system(), 5)

    assert result["months_of_history"] == 6
    assert result["low_confidence"] is True
    assert result["annual_rate"] is not None


@pytest.mark.asyncio
async def test_projection_at_exactly_twelve_months_is_confident():
    """The confidence boundary is a full year of months, not more."""
    session = _session_with_history(months=12, annual_loss=0.008)

    result = await project_future_efficiency(session, _projection_system(), 5)

    assert result["low_confidence"] is False


@pytest.mark.asyncio
async def test_projection_refuses_a_single_month():
    """AC2: one point has no trend, so no numbers are invented from it."""
    session = _session_with_history(months=1, annual_loss=0.008)

    result = await project_future_efficiency(session, _projection_system(), 5)

    assert result == {
        "months_of_history": 1,
        "annual_rate": None,
        "low_confidence": True,
        "warranty_breach_year": None,
        "years": [],
    }


@pytest.mark.asyncio
async def test_projection_reports_no_history_at_all():
    """An install whose summaries have not been built yet still answers."""
    session = _session_with_history(months=0, annual_loss=0.008)

    result = await project_future_efficiency(session, _projection_system(), 5)

    assert result["months_of_history"] == 0
    assert result["years"] == []


@pytest.mark.asyncio
async def test_projection_names_the_year_the_warranty_curve_is_breached():
    """AC4: a trend steeper than the warranty crosses it inside the window."""
    session = _session_with_history(months=36, annual_loss=0.012)

    result = await project_future_efficiency(session, _projection_system("0.7"), 5)

    assert result["warranty_breach_year"] == 2024
    assert result["annual_rate"] == pytest.approx(0.012, abs=1e-4)


@pytest.mark.asyncio
async def test_projection_reports_no_breach_when_the_trend_is_within_warranty():
    """A system degrading slower than its warranty has nothing to call out."""
    session = _session_with_history(months=36, annual_loss=0.004)

    result = await project_future_efficiency(session, _projection_system("0.7"), 5)

    assert result["warranty_breach_year"] is None


@pytest.mark.asyncio
async def test_projection_never_reports_a_negative_ratio():
    """A collapsing trend runs out at zero rather than below it."""
    session = _session_with_history(months=36, annual_loss=0.2)

    result = await project_future_efficiency(session, _projection_system(), 5)

    assert result["years"][-1]["projected_pr"] == 0.0


@pytest.mark.asyncio
async def test_projection_of_an_improving_system_reports_a_negative_rate():
    """A rising PR is reported as it is, not clipped to zero degradation."""
    session = _session_with_history(months=24, annual_loss=-0.005)

    result = await project_future_efficiency(session, _projection_system(), 5)

    assert result["annual_rate"] == pytest.approx(-0.005, abs=1e-4)
    assert result["warranty_breach_year"] is None
