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
