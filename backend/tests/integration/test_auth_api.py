from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from helio.api.main import app
from helio.core.config import settings
from helio.core.crypto import decrypt
from helio.db.models import System
from helio.db.session import get_db

TOKEN_URL = "https://api.enphaseenergy.com/oauth/token"
REDIRECT_URI = "http://localhost:8000/api/auth/enphase/callback"


@pytest.fixture
def credentials(monkeypatch):
    """Configure the server-side Enphase application credentials."""
    monkeypatch.setattr(settings, "enphase_client_id", "client-id-123")
    monkeypatch.setattr(settings, "enphase_client_secret", "client-secret-456")
    monkeypatch.setattr(settings, "enphase_redirect_uri", REDIRECT_URI)
    monkeypatch.setattr(settings, "frontend_base_url", "http://localhost:3000")
    monkeypatch.setattr(settings, "fernet_key", Fernet.generate_key().decode())


def _system(**overrides) -> System:
    """Build an unpersisted System row, by default with no stored tokens."""
    defaults = {
        "id": 1,
        "enphase_system_id": "sys-001",
        "install_date": date(2023, 1, 1),
    }
    return System(**{**defaults, **overrides})


def _session(system: System | None, last_poll: datetime | None = None) -> AsyncMock:
    """Mock a session yielding `system`, then the last successful poll time."""
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=system)),
            MagicMock(scalar=MagicMock(return_value=last_poll)),
        ]
    )
    return session


async def _get(path: str, session: AsyncMock | None = None) -> httpx.Response:
    """Call the API with `session` injected as the database dependency."""

    async def override_get_db():
        yield session

    if session is not None:
        app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get(path)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_authorize_returns_consent_url_with_client_id_and_redirect_uri(
    credentials,
):
    """AC1: the consent URL must carry the configured client ID and redirect."""
    response = await _get("/api/auth/enphase/authorize")

    assert response.status_code == 200
    url = urlparse(response.json()["authorization_url"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == (
        "https://api.enphaseenergy.com/oauth/authorize"
    )
    query = parse_qs(url.query)
    assert query["client_id"] == ["client-id-123"]
    assert query["redirect_uri"] == [REDIRECT_URI]
    assert query["response_type"] == ["code"]
    assert "client-secret-456" not in response.text


@pytest.mark.asyncio
async def test_authorize_503_when_credentials_are_missing(credentials, monkeypatch):
    """Without a client ID there is nothing to redirect to, so say so."""
    monkeypatch.setattr(settings, "enphase_client_id", "")

    response = await _get("/api/auth/enphase/authorize")

    assert response.status_code == 503
    assert "ENPHASE_CLIENT_ID" in response.json()["detail"]


@respx.mock
@pytest.mark.asyncio
async def test_callback_exchanges_the_code_and_stores_tokens_encrypted(credentials):
    """AC2: an approved consent stores an encrypted pair and reports connected."""
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "fresh-access", "refresh_token": "fresh-refresh"},
        )
    )
    system = _system()

    response = await _get(
        "/api/auth/enphase/callback?code=auth-code-789", _session(system)
    )

    assert response.headers["location"] == "http://localhost:3000/?enphase=connected"
    assert system.enphase_access_token not in (None, "fresh-access")
    assert decrypt(system.enphase_access_token, settings.fernet_key) == "fresh-access"
    assert decrypt(system.enphase_refresh_token, settings.fernet_key) == "fresh-refresh"
    assert system.token_updated_at is not None

    request = respx.calls.last.request
    assert b"grant_type=authorization_code" in request.content
    assert b"code=auth-code-789" in request.content


@respx.mock
@pytest.mark.asyncio
async def test_callback_stores_nothing_when_enphase_rejects_the_code(credentials):
    """AC3: an expired or reused code must leave no partial credentials."""
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    system = _system()

    response = await _get(
        "/api/auth/enphase/callback?code=expired-code", _session(system)
    )

    assert response.headers["location"] == (
        "http://localhost:3000/?enphase=exchange_failed"
    )
    assert system.enphase_access_token is None
    assert system.enphase_refresh_token is None
    assert system.token_updated_at is None


@respx.mock
@pytest.mark.asyncio
async def test_callback_stores_nothing_on_a_half_populated_token_response(credentials):
    """AC3: an access token without its refresh token is unusable, so reject it."""
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "lonely-access"})
    )
    system = _system()

    response = await _get("/api/auth/enphase/callback?code=odd-code", _session(system))

    assert response.headers["location"] == (
        "http://localhost:3000/?enphase=exchange_failed"
    )
    assert system.enphase_access_token is None
    assert system.enphase_refresh_token is None


@pytest.mark.asyncio
async def test_callback_reports_a_declined_consent(credentials):
    """Enphase sends `error` instead of a code when the user says no."""
    response = await _get(
        "/api/auth/enphase/callback?error=access_denied", _session(_system())
    )

    assert response.headers["location"] == "http://localhost:3000/?enphase=denied"


@pytest.mark.asyncio
async def test_callback_reports_when_no_system_exists_yet(credentials):
    """There is no row to attach tokens to until the system is created."""
    response = await _get("/api/auth/enphase/callback?code=abc", _session(None))

    assert response.headers["location"] == "http://localhost:3000/?enphase=no_system"


@pytest.mark.asyncio
async def test_status_reports_connection_and_last_poll_without_secrets(credentials):
    """AC4: status and last poll time are shown, tokens and secrets are not."""
    stored_access = "encrypted-access-ciphertext"
    stored_refresh = "encrypted-refresh-ciphertext"
    rotated_at = datetime(2026, 8, 1, 4, 0, tzinfo=UTC)
    system = _system(
        enphase_access_token=stored_access,
        enphase_refresh_token=stored_refresh,
        token_updated_at=rotated_at,
    )
    last_poll = datetime(2026, 8, 13, 4, 1, tzinfo=UTC)

    response = await _get("/api/auth/enphase/status", _session(system, last_poll))

    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["client_configured"] is True
    assert body["last_successful_poll_at"].startswith("2026-08-13T04:01")
    assert body["token_updated_at"].startswith("2026-08-01T04:00")
    for secret in (stored_access, stored_refresh, "client-secret-456"):
        assert secret not in response.text


@pytest.mark.asyncio
async def test_status_reports_not_connected_without_a_system(credentials):
    """A fresh install has nothing stored, which is not an error."""
    response = await _get("/api/auth/enphase/status", _session(None))

    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False
    assert body["last_successful_poll_at"] is None


@pytest.mark.asyncio
async def test_status_reports_not_connected_when_no_refresh_token_is_stored(
    credentials,
):
    """Tokens from .env are not a connection; only a stored pair counts."""
    response = await _get("/api/auth/enphase/status", _session(_system()))

    body = response.json()
    assert body["connected"] is False
    assert body["client_configured"] is True
