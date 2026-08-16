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
) -> MagicMock:
    system = MagicMock(spec=System)
    system.id = 1
    system.warranty_degradation_rate = Decimal(warranty)
    system.energy_rate_per_kwh = Decimal(rate)
    system.energy_rate_currency = currency
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
