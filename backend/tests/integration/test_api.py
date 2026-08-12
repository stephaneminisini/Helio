from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from helio.api.main import app
from helio.db.models import System
from helio.db.session import get_db


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


def _apply_server_defaults(system: System) -> None:
    """Simulate the column defaults the database applies on insert."""
    if system.degradation_rate is None:
        system.degradation_rate = Decimal("0.500")
    if system.irradiance_source is None:
        system.irradiance_source = "nrel"


@pytest.mark.asyncio
async def test_post_settings_creates_system():
    added: list[System] = []

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    mock_session.add = MagicMock(side_effect=added.append)
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock(side_effect=_apply_server_defaults)

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json={
                    "enphase_system_id": "test-001",
                    "install_date": "2023-01-01",
                    "name": "Roof Array",
                    "panel_count": 30,
                },
                headers={"Content-Type": "application/json"},
            )
        assert response.status_code == 201
        data = response.json()
        assert data["enphase_system_id"] == "test-001"
        assert data["install_date"] == "2023-01-01"
        assert data["name"] == "Roof Array"
        assert data["panel_count"] == 30
        assert data["degradation_rate"] == "0.500"
        assert data["irradiance_source"] == "nrel"
        assert len(added) == 1
        assert added[0].enphase_system_id == "test-001"
        assert added[0].install_date == date(2023, 1, 1)
        mock_session.commit.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_settings_409_when_system_exists():
    mock_system = MagicMock(spec=System)

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_system))
    )
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json={
                    "enphase_system_id": "test-002",
                    "install_date": "2023-01-01",
                },
                headers={"Content-Type": "application/json"},
            )
        assert response.status_code == 409
        mock_session.add.assert_not_called()
        mock_session.commit.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload,missing_field",
    [
        ({"install_date": "2023-01-01"}, "enphase_system_id"),
        ({"enphase_system_id": "test-003"}, "install_date"),
        ({}, "enphase_system_id"),
    ],
)
async def test_post_settings_422_when_required_field_missing(payload, missing_field):
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        assert response.status_code == 422
        fields = [error["loc"][-1] for error in response.json()["detail"]]
        assert missing_field in fields
        mock_session.add.assert_not_called()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_settings_returns_persisted_system():
    system = System(
        enphase_system_id="test-004",
        install_date=date(2022, 6, 15),
        name="Roof Array",
        system_size_kw=Decimal("10.000"),
        degradation_rate=Decimal("0.500"),
        irradiance_source="nrel",
    )

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=system))
    )

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["enphase_system_id"] == "test-004"
        assert data["install_date"] == "2022-06-15"
        assert data["name"] == "Roof Array"
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
