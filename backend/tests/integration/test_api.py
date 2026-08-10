from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from helio.api.main import app
from helio.core.config import settings as app_settings
from helio.db.models import System
from helio.db.session import get_db
from helio.ingestion.backfill import progress


def _no_system_session():
    """Build a mock session whose every lookup resolves to no system."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    return mock_session


def _override_db(mock_session):
    """Install mock_session as the get_db dependency.

    Args:
        mock_session: Session the override should yield.
    """

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_overview_returns_200_with_no_system():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/overview")
        assert response.status_code == 200
        data = response.json()
        assert "today_kwh" in data
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_settings_404_with_no_system():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/settings")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_put_settings_404_with_no_system():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.put(
                "/api/settings",
                json={"name": "New Name"},
                headers={"Content-Type": "application/json"},
            )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_put_settings_updates_system():
    mock_system = MagicMock(spec=System)
    mock_system.enphase_system_id = "test-001"
    mock_system.name = "Old Name"
    mock_system.location = None
    mock_system.system_size_kw = Decimal("10.0")
    mock_system.panel_count = 30
    mock_system.panel_wattage_w = 400
    mock_system.install_date = date(2023, 1, 1)
    mock_system.latitude = Decimal("45.5017")
    mock_system.longitude = Decimal("-73.5673")
    mock_system.tilt_angle_deg = Decimal("30.0")
    mock_system.azimuth_deg = Decimal("180.0")
    mock_system.degradation_rate = Decimal("0.5")
    mock_system.irradiance_source = "nrel"

    async def mock_execute(stmt):
        return MagicMock(scalar_one_or_none=MagicMock(return_value=mock_system))

    mock_session = AsyncMock()
    mock_session.execute = mock_execute
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.put(
                "/api/settings",
                json={"name": "New Name"},
                headers={"Content-Type": "application/json"},
            )
        assert response.status_code == 200
        assert mock_system.name == "New Name"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_put_settings_rejects_unknown_irradiance_source():
    _override_db(_no_system_session())
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.put(
                "/api/settings", json={"irradiance_source": "manual"}
            )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_settings_creates_system():
    mock_session = _no_system_session()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    _override_db(mock_session)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json={
                    "enphase_system_id": "1234567",
                    "install_date": "2023-05-01",
                    "latitude": "45.5017",
                    "longitude": "-73.5673",
                    "name": "Roof array",
                    "degradation_rate": "0.5",
                    "irradiance_source": "nasa",
                },
            )
        assert response.status_code == 201
        body = response.json()
        assert body["enphase_system_id"] == "1234567"
        assert Decimal(body["latitude"]) == Decimal("45.5017")
        mock_session.add.assert_called_once()
        created = mock_session.add.call_args.args[0]
        assert isinstance(created, System)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_settings_conflicts_when_system_exists():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=MagicMock(spec=System))
        )
    )

    _override_db(mock_session)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json={
                    "enphase_system_id": "1234567",
                    "install_date": "2023-05-01",
                    "latitude": "45.5",
                    "longitude": "-73.5",
                },
            )
        assert response.status_code == 409
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_settings_requires_coordinates():
    _override_db(_no_system_session())
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json={"enphase_system_id": "1234567", "install_date": "2023-05-01"},
            )
        assert response.status_code == 422
        missing = {tuple(err["loc"])[-1] for err in response.json()["detail"]}
        assert {"latitude", "longitude"} <= missing
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_settings_rejects_future_install_date():
    _override_db(_no_system_session())
    tomorrow = date.today() + timedelta(days=1)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json={
                    "enphase_system_id": "1234567",
                    "install_date": tomorrow.isoformat(),
                    "latitude": "45.5",
                    "longitude": "-73.5",
                },
            )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_status_reports_unconfigured_deployment():
    _override_db(_no_system_session())
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/status")
        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is False
        assert body["days_with_data"] == 0
        assert body["last_poll"] is None
        assert body["backfill"]["running"] is False
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_status_reports_partial_coverage_and_last_poll_error(monkeypatch):
    # Ingestion reads IRRADIANCE_SOURCE from the environment, so status must too -
    # the systems row deliberately disagrees here.
    monkeypatch.setattr(app_settings, "irradiance_source", "nrel")

    mock_system = MagicMock(spec=System)
    mock_system.id = 1
    mock_system.install_date = date.today() - timedelta(days=10)
    mock_system.latitude = Decimal("45.5")
    mock_system.longitude = Decimal("-73.5")
    mock_system.irradiance_source = "nasa"

    mock_poll = MagicMock()
    mock_poll.poll_type = "intervals"
    mock_poll.status = "error"
    mock_poll.started_at = datetime(2026, 8, 9, 4, 0, tzinfo=UTC)
    mock_poll.completed_at = datetime(2026, 8, 9, 4, 0, 2, tzinfo=UTC)
    mock_poll.records_inserted = 0
    mock_poll.error_message = "401 Unauthorized"

    first_day = date.today() - timedelta(days=10)
    last_day = date.today() - timedelta(days=8)

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_system)),
            MagicMock(one=MagicMock(return_value=(first_day, last_day, 3))),
            MagicMock(scalar_one=MagicMock(return_value=0)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_poll)),
        ]
    )

    _override_db(mock_session)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/status")
        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is True
        assert body["location_configured"] is True
        assert body["days_with_data"] == 3
        assert body["days_expected"] == 10
        assert body["missing_days"] == 7
        assert body["months_with_data"] == 0
        # NREL returns typical-year averages, so PR is not weather-sensitive.
        assert body["irradiance_source"] == "nrel"
        assert body["weather_normalized"] is False
        assert body["last_poll"]["status"] == "error"
        assert body["last_poll"]["error_message"] == "401 Unauthorized"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_backfill_404_without_system():
    _override_db(_no_system_session())
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/backfill")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_backfill_conflicts_while_already_running():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=MagicMock(spec=System))
        )
    )

    _override_db(mock_session)
    progress.running = True
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/backfill")
        assert response.status_code == 409
    finally:
        progress.running = False
        app.dependency_overrides.clear()
