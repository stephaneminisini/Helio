from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from helio.api.main import app
from helio.core.config import settings as app_settings
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


def _apply_insert_defaults(system: System) -> None:
    """Stand in for db.refresh(), which is a no-op on a mocked session.

    degradation_rate and irradiance_source are NOT NULL and get their values
    from SQLAlchemy column defaults applied at flush; a real refresh() then
    reads them back. SettingsResponse types both as required, so without this
    the handler would 500 on validation instead of returning 201. Expected
    values are read off the model rather than hardcoded so a change to the
    declared defaults fails the test instead of silently diverging.
    """
    for column in ("degradation_rate", "irradiance_source"):
        if getattr(system, column) is None:
            setattr(system, column, System.__table__.c[column].default.arg)


def _mock_session(existing: System | None = None, **overrides) -> AsyncMock:
    """Build a mocked AsyncSession whose SELECT returns `existing`."""
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing))
    )
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock(side_effect=_apply_insert_defaults)
    for name, value in overrides.items():
        setattr(session, name, value)
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


@pytest.mark.asyncio
async def test_post_settings_creates_system():
    added: list[System] = []
    session = _mock_session(add=MagicMock(side_effect=added.append))

    async with _client_with_db(session) as client:
        response = await client.post(
            "/api/settings",
            json={
                "enphase_system_id": "test-001",
                "install_date": "2023-01-01",
                "name": "Roof Array",
                "panel_count": 30,
                "latitude": "45.523100",
                "longitude": "-122.676500",
            },
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["enphase_system_id"] == "test-001"
    assert data["install_date"] == "2023-01-01"
    assert data["name"] == "Roof Array"
    assert data["panel_count"] == 30
    assert data["latitude"] == "45.523100"
    assert data["longitude"] == "-122.676500"
    assert data["degradation_rate"] == "0.5"
    assert data["irradiance_source"] == "nasa"
    assert len(added) == 1
    assert added[0].enphase_system_id == "test-001"
    assert added[0].install_date == date(2023, 1, 1)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_settings_omits_none_so_column_defaults_apply():
    """An explicit null must be dropped, not written to a NOT NULL column."""
    # Snapshot at add() time: refresh() populates the defaults afterwards.
    columns_written: list[set[str]] = []
    session = _mock_session(
        add=MagicMock(
            side_effect=lambda system: columns_written.append(
                set(system.__dict__) - {"_sa_instance_state"}
            )
        )
    )

    async with _client_with_db(session) as client:
        response = await client.post(
            "/api/settings",
            json={
                "enphase_system_id": "test-005",
                "install_date": "2023-01-01",
                "degradation_rate": None,
                "irradiance_source": None,
            },
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 201
    assert columns_written == [{"enphase_system_id", "install_date"}]


@pytest.mark.asyncio
async def test_post_settings_409_when_insert_races():
    """The singleton index rejects the loser of a concurrent create."""
    session = _mock_session(
        commit=AsyncMock(
            side_effect=IntegrityError("INSERT", {}, Exception("uq_systems_singleton"))
        )
    )

    async with _client_with_db(session) as client:
        response = await client.post(
            "/api/settings",
            json={"enphase_system_id": "test-006", "install_date": "2023-01-01"},
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 409
    session.rollback.assert_awaited_once()
    session.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_settings_409_when_system_exists():
    session = _mock_session(existing=MagicMock(spec=System))

    async with _client_with_db(session) as client:
        response = await client.post(
            "/api/settings",
            json={
                "enphase_system_id": "test-002",
                "install_date": "2023-01-01",
            },
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 409
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload,expected_fields",
    [
        ({"install_date": "2023-01-01"}, ["enphase_system_id"]),
        ({"enphase_system_id": "test-003"}, ["install_date"]),
        ({}, ["enphase_system_id", "install_date"]),
    ],
)
async def test_post_settings_422_when_required_field_missing(payload, expected_fields):
    session = _mock_session()

    async with _client_with_db(session) as client:
        response = await client.post(
            "/api/settings",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    fields = [error["loc"][-1] for error in response.json()["detail"]]
    assert sorted(fields) == sorted(expected_fields)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("enphase_system_id", ""),
        ("enphase_system_id", "x" * 65),
        ("name", "x" * 129),
        ("location", "x" * 257),
        ("latitude", "91.0"),
        ("longitude", "-181.0"),
        ("system_size_kw", "0"),
        ("system_size_kw", "1000"),
        ("panel_count", -30),
        ("panel_count", 100_000),
        ("panel_wattage_w", 0),
        ("tilt_angle_deg", "-1.0"),
        ("tilt_angle_deg", "12345.67"),
        ("azimuth_deg", "361.0"),
        ("degradation_rate", "1234.5"),
        ("irradiance_source", "totally-made-up"),
    ],
)
async def test_post_settings_422_when_value_out_of_bounds(field, value):
    """Bad values must be rejected at the boundary, not by Postgres as a 500."""
    session = _mock_session()
    payload = {
        "enphase_system_id": "test-007",
        "install_date": "2023-01-01",
        field: value,
    }

    async with _client_with_db(session) as client:
        response = await client.post(
            "/api/settings",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert [error["loc"][-1] for error in response.json()["detail"]] == [field]
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_get_settings_returns_values_persisted_by_post():
    """AC4: the fields POST writes are the fields GET reads back."""
    stored: list[System] = []
    session = _mock_session(add=MagicMock(side_effect=stored.append))
    # Mirror the DB: SELECT finds nothing until the insert has happened.
    session.execute = AsyncMock(
        side_effect=lambda stmt: MagicMock(
            scalar_one_or_none=MagicMock(
                return_value=stored[0] if stored else None,
            )
        )
    )
    body = {
        "enphase_system_id": "test-004",
        "install_date": "2022-06-15",
        "name": "Roof Array",
        "location": "Portland, OR",
        "latitude": "45.523100",
        "longitude": "-122.676500",
        "system_size_kw": "10.000",
        "panel_count": 25,
        "panel_wattage_w": 400,
        "tilt_angle_deg": "30.00",
        "azimuth_deg": "180.00",
        "degradation_rate": "0.500",
        "irradiance_source": "nasa",
    }

    async with _client_with_db(session) as client:
        created = await client.post(
            "/api/settings", json=body, headers={"Content-Type": "application/json"}
        )
        fetched = await client.get("/api/settings")

    assert created.status_code == 201
    assert fetched.status_code == 200
    assert fetched.json() == created.json()
    for field, value in body.items():
        assert fetched.json()[field] == value


def _configured_system() -> MagicMock:
    """A stored system with every SettingsResponse field populated."""
    system = MagicMock(spec=System)
    system.enphase_system_id = "test-001"
    system.name = "Roof Array"
    system.location = "Portland, OR"
    system.latitude = None
    system.longitude = None
    system.system_size_kw = Decimal("10.0")
    system.panel_count = 30
    system.panel_wattage_w = 400
    system.install_date = date(2023, 1, 1)
    system.tilt_angle_deg = Decimal("30.0")
    system.azimuth_deg = Decimal("180.0")
    system.degradation_rate = Decimal("0.5")
    system.irradiance_source = "nasa"
    return system


@pytest.mark.asyncio
async def test_put_settings_persists_coordinates():
    """AC2: coordinates saved from the Setup form come back on reload."""
    system = _configured_system()
    session = _mock_session(existing=system)

    async with _client_with_db(session) as client:
        saved = await client.put(
            "/api/settings",
            json={"latitude": "45.523100", "longitude": "-122.676500"},
            headers={"Content-Type": "application/json"},
        )
        reloaded = await client.get("/api/settings")

    assert saved.status_code == 200
    assert system.latitude == Decimal("45.523100")
    assert system.longitude == Decimal("-122.676500")
    assert reloaded.json()["latitude"] == "45.523100"
    assert reloaded.json()["longitude"] == "-122.676500"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("latitude", "91.0"),
        ("latitude", "-90.1"),
        ("longitude", "180.5"),
        ("longitude", "-181.0"),
    ],
)
async def test_put_settings_422_when_coordinates_out_of_range(field, value):
    """AC3: an out-of-range coordinate is rejected and nothing is written."""
    system = _configured_system()
    session = _mock_session(existing=system)

    async with _client_with_db(session) as client:
        response = await client.put(
            "/api/settings",
            json={field: value},
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert [error["loc"][-1] for error in response.json()["detail"]] == [field]
    assert getattr(system, field) is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_put_settings_422_when_irradiance_source_unsupported():
    """AC3: ingestion reads this value, so an unusable source is rejected here."""
    system = _configured_system()
    session = _mock_session(existing=system)

    async with _client_with_db(session) as client:
        response = await client.put(
            "/api/settings",
            json={"irradiance_source": "totally-made-up"},
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert [error["loc"][-1] for error in detail] == ["irradiance_source"]
    assert "nasa" in str(detail)
    assert system.irradiance_source == "nasa"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_put_settings_updates_system():
    mock_system = MagicMock(spec=System)
    mock_system.enphase_system_id = "test-001"
    mock_system.name = "Old Name"
    mock_system.location = None
    mock_system.latitude = None
    mock_system.longitude = None
    mock_system.system_size_kw = Decimal("10.0")
    mock_system.panel_count = 30
    mock_system.panel_wattage_w = 400
    mock_system.install_date = date(2023, 1, 1)
    mock_system.tilt_angle_deg = Decimal("30.0")
    mock_system.azimuth_deg = Decimal("180.0")
    mock_system.degradation_rate = Decimal("0.5")
    mock_system.irradiance_source = "nasa"

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


@pytest.mark.parametrize(
    ("client_id", "client_secret", "connected"),
    [
        ("client-id", "client-secret", True),
        ("", "", False),
        ("client-id", "", False),
        ("", "client-secret", False),
    ],
)
@pytest.mark.asyncio
async def test_get_settings_reports_enphase_connection_state(
    monkeypatch, client_id, client_secret, connected
):
    """A missing Enphase credential surfaces as "not connected", not a failure."""
    monkeypatch.setattr(app_settings, "enphase_client_id", client_id)
    monkeypatch.setattr(app_settings, "enphase_client_secret", client_secret)
    system = System(
        enphase_system_id="test-005",
        install_date=date(2023, 1, 1),
        degradation_rate=Decimal("0.5"),
        irradiance_source="nasa",
    )

    async with _client_with_db(_mock_session(existing=system)) as client:
        response = await client.get("/api/settings")

    assert response.status_code == 200
    assert response.json()["enphase_connected"] is connected
