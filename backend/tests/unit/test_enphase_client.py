import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from helio.ingestion.enphase_client import EnphaseClient, IntervalData

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
