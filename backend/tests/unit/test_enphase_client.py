import json
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from helio.ingestion.enphase_client import (
    CurrentProduction,
    EnphaseClient,
    IntervalData,
    authorize_url,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def client():
    return EnphaseClient(
        client_id="test-id",
        client_secret="test-secret",
        system_id="12345",
        access_token="test-token",
        refresh_token="test-refresh",
    )


@pytest.fixture
def intervals_payload():
    return json.loads((FIXTURES / "enphase_intervals.json").read_text())


@respx.mock
@pytest.mark.asyncio
async def test_get_intervals_returns_interval_data(client, intervals_payload):
    respx.get(
        "https://api.enphaseenergy.com/api/v4/systems/12345/telemetry/production_micro"
    ).mock(return_value=httpx.Response(200, json=intervals_payload))

    result = await client.get_intervals(date(2024, 4, 28), date(2024, 4, 28))

    assert len(result) == 3
    assert isinstance(result[0], IntervalData)
    assert result[0].production_wh == 1250


@respx.mock
@pytest.mark.asyncio
async def test_get_intervals_retries_on_429(client):
    respx.get(
        "https://api.enphaseenergy.com/api/v4/systems/12345/telemetry/production_micro"
    ).mock(
        side_effect=[
            httpx.Response(429, json={"message": "rate limit"}),
            httpx.Response(200, json={"system_id": 12345, "intervals": []}),
        ]
    )

    result = await client.get_intervals(date(2024, 4, 28), date(2024, 4, 28))
    assert result == []


@respx.mock
@pytest.mark.asyncio
async def test_get_intervals_raises_after_max_retries(client):
    respx.get(
        "https://api.enphaseenergy.com/api/v4/systems/12345/telemetry/production_micro"
    ).mock(return_value=httpx.Response(429, json={"message": "rate limit"}))

    with pytest.raises(RuntimeError, match="rate limit"):
        await client.get_intervals(date(2024, 4, 28), date(2024, 4, 28))


@respx.mock
@pytest.mark.asyncio
async def test_get_current_power_returns_the_reading_and_its_timestamp(client):
    """AC1: a bare figure cannot be told apart from a stale one."""
    respx.get("https://api.enphaseenergy.com/api/v4/systems/12345/summary").mock(
        return_value=httpx.Response(
            200,
            json={
                "system_id": 12345,
                "current_power": 4210,
                "energy_today": 18500,
                "last_report_at": 1721394000,
            },
        )
    )

    reading = await client.get_current_power()

    assert reading == CurrentProduction(
        watts=4210.0,
        reported_at=datetime(2024, 7, 19, 13, 0, tzinfo=UTC),
    )


@respx.mock
@pytest.mark.asyncio
async def test_get_current_power_returns_none_when_the_summary_is_bare(client):
    """A system that has never reported has no reading to carry."""
    respx.get("https://api.enphaseenergy.com/api/v4/systems/12345/summary").mock(
        return_value=httpx.Response(200, json={"system_id": 12345})
    )

    assert await client.get_current_power() is None


@respx.mock
@pytest.mark.asyncio
async def test_get_current_power_raises_after_max_retries(client):
    """AC3: the caller decides what a rate-limited reading means, not the client."""
    respx.get("https://api.enphaseenergy.com/api/v4/systems/12345/summary").mock(
        return_value=httpx.Response(429, json={"message": "rate limit"})
    )

    with pytest.raises(RuntimeError, match="rate limit"):
        await client.get_current_power()


@respx.mock
@pytest.mark.asyncio
async def test_refresh_access_token_updates_stored_token(client):
    respx.post("https://api.enphaseenergy.com/oauth/token").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "new-token-123", "refresh_token": "new-refresh-456"},
        )
    )

    new_token = await client.refresh_access_token()

    assert new_token == "new-token-123"
    assert client._access_token == "new-token-123"
    assert client._refresh_token == "new-refresh-456"


@respx.mock
@pytest.mark.asyncio
async def test_refresh_access_token_raises_on_missing_token(client):
    respx.post("https://api.enphaseenergy.com/oauth/token").mock(
        return_value=httpx.Response(200, json={"error": "invalid_grant"})
    )

    with pytest.raises(ValueError, match="access_token"):
        await client.refresh_access_token()


@respx.mock
@pytest.mark.asyncio
async def test_refresh_access_token_raises_on_http_error(client):
    respx.post("https://api.enphaseenergy.com/oauth/token").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.refresh_access_token()


def test_authorize_url_carries_client_id_and_redirect_uri():
    """The consent link is what AC1 checks, so build it from settings verbatim."""
    url = authorize_url("client-id-123", "http://localhost:8000/cb")

    assert url.startswith("https://api.enphaseenergy.com/oauth/authorize?")
    query = parse_qs(urlparse(url).query)
    assert query == {
        "response_type": ["code"],
        "client_id": ["client-id-123"],
        "redirect_uri": ["http://localhost:8000/cb"],
    }


@respx.mock
@pytest.mark.asyncio
async def test_authenticate_exchanges_the_code_for_both_tokens(client):
    route = respx.post("https://api.enphaseenergy.com/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "code-access", "refresh_token": "code-refresh"}
        )
    )

    tokens = await client.authenticate("the-code", "http://localhost:8000/cb")

    assert tokens == ("code-access", "code-refresh")
    assert client.access_token == "code-access"
    assert client.refresh_token == "code-refresh"
    body = parse_qs(route.calls.last.request.content.decode())
    assert body["grant_type"] == ["authorization_code"]
    assert body["code"] == ["the-code"]
    assert body["redirect_uri"] == ["http://localhost:8000/cb"]


@respx.mock
@pytest.mark.asyncio
async def test_authenticate_raises_on_an_expired_code(client):
    respx.post("https://api.enphaseenergy.com/oauth/token").mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.authenticate("expired", "http://localhost:8000/cb")


@respx.mock
@pytest.mark.asyncio
async def test_authenticate_rejects_a_response_without_a_refresh_token(client):
    """Keeping an access token with no refresh token would strand the install."""
    respx.post("https://api.enphaseenergy.com/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "only-access"})
    )

    with pytest.raises(ValueError, match="refresh_token"):
        await client.authenticate("the-code", "http://localhost:8000/cb")

    assert client.access_token == "test-token"
    assert client.refresh_token == "test-refresh"
