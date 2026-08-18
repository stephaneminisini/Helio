from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from helio.api.main import app
from helio.api.routes import efficiency as efficiency_route
from helio.db.models import MonthlySummary, System
from helio.db.session import get_db


def _session(
    system: System | MagicMock | None,
    monthly: list[MagicMock] | None = None,
) -> AsyncMock:
    """A session whose System lookup yields `system` and month query `monthly`.

    The route selects the system and then the monthly summaries; both go through
    the same execute(), so the mock satisfies either shape at once.
    """
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=system),
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=monthly or []))
            ),
        )
    )
    return session


def _month(is_anomaly: bool, reason: str | None) -> MagicMock:
    """A monthly summary row carrying whatever anomaly verdict a test needs."""
    row = MagicMock(spec=MonthlySummary)
    row.month = date(2024, 6, 1)
    row.production_kwh = Decimal("880.5")
    row.performance_ratio = Decimal("0.7600")
    row.expected_pr = Decimal("0.9800")
    row.is_anomaly = is_anomaly
    row.anomaly_reason = reason
    return row


@asynccontextmanager
async def _client_with_db(session):
    """Serve the app with `session` injected as the request-scoped database."""

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _system(
    warranty: str = "0.7",
    rate: str = "0.15",
    currency: str = "USD",
    baseline: str | None = None,
) -> MagicMock:
    system = MagicMock(spec=System)
    system.id = 1
    # The projection measures elapsed years from the install date, so it has to
    # be a real date even on tests that only care about the warranty figures.
    system.install_date = date(2020, 1, 1)
    system.warranty_degradation_rate = Decimal(warranty)
    system.energy_rate_per_kwh = Decimal(rate)
    system.energy_rate_currency = currency
    system.degradation_rate = Decimal("0.5")
    # Explicitly null unless a test configures one: spec'd mocks answer every
    # attribute, so leaving it unset would look like a configured override.
    system.baseline_pr = Decimal(baseline) if baseline else None
    return system


@pytest.fixture
def two_years_dropping(monkeypatch):
    """Stub the analytics so only the warranty comparison is under test.

    Returns a setter that fixes the year-over-year drop, expressed as a
    difference of Performance Ratio fractions.
    """

    def set_drop(drop: float) -> None:
        monkeypatch.setattr(
            efficiency_route,
            "calculate_annual_degradation",
            AsyncMock(
                return_value={
                    2023: {"avg_pr": 0.82, "annual_drop": None},
                    2024: {"avg_pr": 0.82 - drop, "annual_drop": drop},
                }
            ),
        )

    return set_drop


@pytest.fixture
def lost_production(monkeypatch) -> AsyncMock:
    """Replace estimate_lost_production and record the rate it was handed."""
    stub = AsyncMock(return_value={"lost_kwh": 120.0, "lost_dollars": 18.0})
    monkeypatch.setattr(efficiency_route, "estimate_lost_production", stub)
    return stub


@pytest.mark.asyncio
async def test_efficiency_flags_a_drop_above_the_configured_warranty(
    two_years_dropping, lost_production
):
    """AC1: a 0.6 percent drop against a 0.5 percent warranty is a breach."""
    two_years_dropping(0.006)

    async with _client_with_db(_session(_system(warranty="0.5"))) as client:
        response = await client.get("/api/efficiency")

    assert response.status_code == 200
    degradation = response.json()["degradation"]
    assert degradation["exceeds_warranty"] is True
    assert degradation["warranty_threshold"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_efficiency_accepts_a_drop_below_the_configured_warranty(
    two_years_dropping, lost_production
):
    """AC2: the same drop against a 0.8 percent warranty is within spec."""
    two_years_dropping(0.006)

    async with _client_with_db(_session(_system(warranty="0.8"))) as client:
        response = await client.get("/api/efficiency")

    degradation = response.json()["degradation"]
    assert degradation["exceeds_warranty"] is False
    assert degradation["warranty_threshold"] == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_efficiency_prices_lost_production_at_the_configured_rate(
    two_years_dropping, lost_production
):
    """AC3: the stored rate reaches the estimator and is echoed to the client."""
    two_years_dropping(0.001)

    async with _client_with_db(
        _session(_system(rate="0.2350", currency="EUR"))
    ) as client:
        response = await client.get("/api/efficiency")

    degradation = response.json()["degradation"]
    assert lost_production.await_args.args[2] == pytest.approx(0.235)
    assert degradation["energy_rate_per_kwh"] == pytest.approx(0.235)
    assert degradation["energy_rate_currency"] == "EUR"


@pytest.mark.asyncio
async def test_efficiency_exposes_the_stored_anomaly_reason(
    two_years_dropping, lost_production
):
    """The chart cannot explain a flag the API keeps to itself."""
    two_years_dropping(0.001)
    reason = "PR 76.0% is 22.0% below expected 98.0%"

    async with _client_with_db(_session(_system(), [_month(True, reason)])) as client:
        response = await client.get("/api/efficiency")

    assert response.status_code == 200
    point = response.json()["pr_history"][0]
    assert point["is_anomaly"] is True
    assert point["anomaly_reason"] == reason


@pytest.mark.asyncio
async def test_efficiency_leaves_the_reason_null_on_a_healthy_month(
    two_years_dropping, lost_production
):
    """An unflagged month has nothing to explain, so the client gets no text."""
    two_years_dropping(0.001)

    async with _client_with_db(_session(_system(), [_month(False, None)])) as client:
        response = await client.get("/api/efficiency")

    point = response.json()["pr_history"][0]
    assert point["is_anomaly"] is False
    assert point["anomaly_reason"] is None


def _pr_month(month: date, performance_ratio: str) -> MagicMock:
    """A monthly summary row with just enough for the trend fit."""
    row = MagicMock(spec=MonthlySummary)
    row.month = month
    row.production_kwh = Decimal("880.5")
    row.performance_ratio = Decimal(performance_ratio)
    row.expected_pr = Decimal("0.8500")
    row.is_anomaly = False
    row.anomaly_reason = None
    return row


@pytest.mark.asyncio
async def test_efficiency_projects_the_measured_trend_forward(
    two_years_dropping, lost_production
):
    """AC1 and AC3: the response carries the projected years and its confidence."""
    two_years_dropping(0.001)
    history = [
        _pr_month(date(2023, 1, 1), "0.8400"),
        _pr_month(date(2024, 1, 1), "0.8200"),
    ]

    async with _client_with_db(_session(_system(), history)) as client:
        response = await client.get("/api/efficiency")

    assert response.status_code == 200
    projection = response.json()["projection"]
    assert projection["months_of_history"] == 2
    assert projection["annual_rate"] == pytest.approx(0.02, abs=1e-3)
    # Two points cannot average the seasons out, so the client is warned.
    assert projection["low_confidence"] is True
    assert [entry["year"] for entry in projection["years"]] == [
        2025,
        2026,
        2027,
        2028,
        2029,
    ]


@pytest.mark.asyncio
async def test_efficiency_projection_is_empty_without_enough_history(
    two_years_dropping, lost_production
):
    """AC2: a single month yields no projected years and no rate."""
    two_years_dropping(0.001)

    async with _client_with_db(_session(_system(), [_month(False, None)])) as client:
        response = await client.get("/api/efficiency")

    projection = response.json()["projection"]
    assert projection["months_of_history"] == 1
    assert projection["annual_rate"] is None
    assert projection["low_confidence"] is True
    assert projection["years"] == []


@pytest.mark.asyncio
async def test_efficiency_reports_the_documented_defaults_with_no_system():
    """AC4: an install with nothing configured still answers, on the defaults."""
    async with _client_with_db(_session(None)) as client:
        response = await client.get("/api/efficiency")

    assert response.status_code == 200
    degradation = response.json()["degradation"]
    assert degradation["warranty_threshold"] == pytest.approx(0.7)
    assert degradation["energy_rate_per_kwh"] == pytest.approx(0.15)
    assert degradation["energy_rate_currency"] == "USD"
    assert degradation["exceeds_warranty"] is False
    assert degradation["baseline_pr"] is None
    assert degradation["baseline_source"] == "none"
    assert response.json()["projection"]["years"] == []


@pytest.mark.asyncio
async def test_efficiency_reports_a_configured_baseline_as_configured(
    two_years_dropping, lost_production
):
    """The owner's commissioning figure is echoed back with its provenance."""
    two_years_dropping(0.001)

    async with _client_with_db(_session(_system(baseline="0.8600"))) as client:
        response = await client.get("/api/efficiency")

    degradation = response.json()["degradation"]
    assert degradation["baseline_pr"] == pytest.approx(0.86)
    assert degradation["baseline_source"] == "configured"


@pytest.mark.asyncio
async def test_efficiency_reports_a_derived_baseline_as_measured(
    two_years_dropping, lost_production
):
    """A full year of history is enough to state a baseline the system earned."""
    two_years_dropping(0.001)
    history = [_pr_month(date(2023, month, 1), "0.8200") for month in range(1, 13)]

    async with _client_with_db(_session(_system(), history)) as client:
        response = await client.get("/api/efficiency")

    degradation = response.json()["degradation"]
    assert degradation["baseline_source"] == "measured"
    # Above the measured 0.82: the window's average is walked back up the
    # degradation curve to the install date, three and a half years earlier.
    assert degradation["baseline_pr"] > 0.82


@pytest.mark.asyncio
async def test_efficiency_states_no_baseline_before_a_full_year(
    two_years_dropping, lost_production
):
    """AC4: eleven months is not a standard, and the client is told so."""
    two_years_dropping(0.001)
    history = [_pr_month(date(2023, month, 1), "0.8200") for month in range(1, 12)]

    async with _client_with_db(_session(_system(), history)) as client:
        response = await client.get("/api/efficiency")

    degradation = response.json()["degradation"]
    assert degradation["baseline_pr"] is None
    assert degradation["baseline_source"] == "none"
