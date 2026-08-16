from contextlib import asynccontextmanager
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from helio.analytics.anomaly import FleetPerformance, PanelPerformance
from helio.api.main import app
from helio.api.routes import panels as panels_route
from helio.api.routes.panels import (
    NO_POLL_MESSAGE,
    NO_READINGS_MESSAGE,
    NO_SYSTEM_MESSAGE,
)
from helio.db.models import PollLog, System
from helio.db.session import get_db


def _session(system: System | MagicMock | None, poll_log: PollLog | None = None):
    """Session answering the system lookup, then the last-panels-poll lookup."""
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=system)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=poll_log)),
        ]
    )
    return session


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


def _system() -> MagicMock:
    system = MagicMock(spec=System)
    system.id = 1
    return system


@pytest.fixture
def fleet(monkeypatch):
    """Stub the analytics so only the endpoint's own behaviour is under test.

    Returns a setter taking the FleetPerformance the route should serve, and
    exposes the stub so tests can assert the window it was handed.
    """
    stub = AsyncMock()
    monkeypatch.setattr(panels_route, "flag_underperforming_panels", stub)

    def serve(performance: FleetPerformance) -> AsyncMock:
        stub.return_value = performance
        return stub

    return serve


def _panel(serial: str, energy: float, sigma: float | None, flagged: bool):
    return PanelPerformance(
        panel_serial=serial,
        energy_wh=energy,
        normalized_efficiency=round(energy / 100, 4),
        deviation_sigma=sigma,
        is_underperforming=flagged,
    )


@pytest.mark.asyncio
async def test_panels_reports_the_outlier_and_the_fleet_it_was_judged_against(fleet):
    """AC1: the flag travels with the distribution that produced it."""
    fleet(
        FleetPerformance(
            panels=[
                _panel("panel-a", 100.0, 0.45, False),
                _panel("panel-b", 40.0, -2.236, True),
            ],
            average_wh=90.0,
            stdev_wh=22.361,
        )
    )

    async with _client_with_db(_session(_system())) as client:
        response = await client.get("/api/panels")

    assert response.status_code == 200
    body = response.json()
    assert [(p["panel_serial"], p["is_underperforming"]) for p in body["panels"]] == [
        ("panel-a", False),
        ("panel-b", True),
    ]
    assert body["fleet_average_wh"] == pytest.approx(90.0)
    assert body["fleet_stdev_wh"] == pytest.approx(22.361)
    assert body["data_available"] is True
    assert body["unavailable_reason"] is None


@pytest.mark.asyncio
async def test_panels_serves_an_unmeasurable_fleet_without_flags(fleet):
    """AC3: a fleet too small to rank still shows the owner its production."""
    fleet(
        FleetPerformance(
            panels=[
                _panel("panel-a", 100.0, None, False),
                _panel("panel-b", 10.0, None, False),
            ],
            average_wh=55.0,
            stdev_wh=0.0,
        )
    )

    async with _client_with_db(_session(_system())) as client:
        response = await client.get("/api/panels")

    body = response.json()
    assert [p["deviation_sigma"] for p in body["panels"]] == [None, None]
    assert body["data_available"] is True


@pytest.mark.asyncio
async def test_panels_explains_an_enphase_plan_without_device_access(fleet):
    """AC4: the partial poll already holds the sentence the UI should show."""
    fleet(FleetPerformance(panels=[], average_wh=0.0, stdev_wh=0.0))
    last_poll = PollLog(
        system_id=1,
        poll_type="panels",
        status="partial",
        error_message="Enphase answered 403 for device-level telemetry.",
    )

    async with _client_with_db(_session(_system(), last_poll)) as client:
        response = await client.get("/api/panels")

    assert response.status_code == 200
    body = response.json()
    assert body["panels"] == []
    assert body["data_available"] is False
    assert (
        body["unavailable_reason"] == "Enphase answered 403 for device-level telemetry."
    )


@pytest.mark.asyncio
async def test_panels_explains_that_no_poll_has_run_yet(fleet):
    """AC4: a fresh install has no panel data and no failure to report either."""
    fleet(FleetPerformance(panels=[], average_wh=0.0, stdev_wh=0.0))

    async with _client_with_db(_session(_system(), None)) as client:
        response = await client.get("/api/panels")

    assert response.json()["unavailable_reason"] == NO_POLL_MESSAGE


@pytest.mark.asyncio
async def test_panels_explains_a_window_that_predates_the_readings(fleet):
    """A successful poll with nothing in this window is a window problem."""
    fleet(FleetPerformance(panels=[], average_wh=0.0, stdev_wh=0.0))
    last_poll = PollLog(system_id=1, poll_type="panels", status="success")

    async with _client_with_db(_session(_system(), last_poll)) as client:
        response = await client.get("/api/panels?days=1")

    assert response.json()["unavailable_reason"] == NO_READINGS_MESSAGE


@pytest.mark.asyncio
async def test_panels_answers_before_a_system_is_configured(fleet):
    """AC4: a fresh install must get an explanation, not a 404."""
    async with _client_with_db(_session(None)) as client:
        response = await client.get("/api/panels")

    assert response.status_code == 200
    body = response.json()
    assert body["data_available"] is False
    assert body["unavailable_reason"] == NO_SYSTEM_MESSAGE


@pytest.mark.asyncio
async def test_panels_window_ends_today_and_spans_the_requested_days(fleet):
    stub = fleet(FleetPerformance(panels=[], average_wh=0.0, stdev_wh=0.0))

    async with _client_with_db(_session(_system())) as client:
        response = await client.get("/api/panels?days=7")

    body = response.json()
    today = date.today()
    assert body["window_end"] == today.isoformat()
    assert body["window_start"] == (today - timedelta(days=6)).isoformat()
    assert stub.await_args.args[2:] == (today - timedelta(days=6), today)


@pytest.mark.asyncio
async def test_panels_rejects_a_window_of_zero_days(fleet):
    async with _client_with_db(_session(_system())) as client:
        response = await client.get("/api/panels?days=0")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_panels_is_documented_with_a_typed_response_schema():
    """AC5: the endpoint has to be usable from /docs, not just from code."""
    async with _client_with_db(_session(_system())) as client:
        schema = (await client.get("/openapi.json")).json()

    operation = schema["paths"]["/api/panels"]["get"]
    ref = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert ref["$ref"].endswith("/PanelsResponse")
    properties = schema["components"]["schemas"]["PanelsResponse"]["properties"]
    assert {
        "panels",
        "fleet_average_wh",
        "fleet_stdev_wh",
        "window_start",
        "window_end",
        "data_available",
        "unavailable_reason",
    } <= set(properties)
    panel_properties = schema["components"]["schemas"]["PanelPoint"]["properties"]
    assert "is_underperforming" in panel_properties
