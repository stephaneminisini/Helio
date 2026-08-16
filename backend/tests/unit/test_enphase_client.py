import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from loguru import logger

from helio.ingestion.enphase_client import (
    PANEL_PAGE_SIZE,
    EnphaseClient,
    IntervalData,
    PanelDataUnavailableError,
    PanelEnergy,
    authorize_url,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"
PANELS_URL = (
    "https://api.enphaseenergy.com/api/v4/systems/12345/devices/micros/telemetry"
)


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


@pytest.fixture
def panels_payload():
    return json.loads((FIXTURES / "enphase_panel_telemetry.json").read_text())


@pytest.fixture
def logged() -> list[str]:
    """Collect loguru messages; its default sink bypasses capsys."""
    messages: list[str] = []
    handler_id = logger.add(messages.append, format="{message}")
    yield messages
    logger.remove(handler_id)


def _panel_page(serials: list[str], total_devices: int, page: int) -> dict:
    """Build a device-level telemetry page with one 20 Wh interval per serial."""
    return {
        "system_id": 12345,
        "total_devices": total_devices,
        "page": page,
        "page_size": PANEL_PAGE_SIZE,
        "granularity": "day",
        "items": "intervals",
        "devices": [
            {
                "serial_number": serial,
                "intervals": [{"end_at": 1714299900, "powr": 240, "enwh": 20}],
            }
            for serial in serials
        ],
    }


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
async def test_get_panel_data_sums_intervals_per_microinverter(client, panels_payload):
    """AC1: one typed record per panel, with the day's intervals summed."""
    route = respx.get(PANELS_URL).mock(
        return_value=httpx.Response(200, json=panels_payload)
    )

    result = await client.get_panel_data(date(2024, 4, 28))

    assert all(isinstance(reading, PanelEnergy) for reading in result)
    assert [(r.panel_serial, r.energy_wh) for r in result] == [
        ("482218012345", 41.0),
        ("482218012346", 19.0),
        # A panel that reported no intervals is still present, at zero.
        ("482218012347", 0.0),
    ]
    query = parse_qs(urlparse(str(route.calls.last.request.url)).query)
    assert query["granularity"] == ["day"]
    assert query["start_date"] == ["2024-04-28"]


@respx.mock
@pytest.mark.asyncio
async def test_get_panel_data_walks_every_page(client):
    """Enphase caps a page at 20 devices, so a 25-panel system needs two calls."""
    first = [f"48221801{index:04d}" for index in range(PANEL_PAGE_SIZE)]
    second = [
        "482218019001",
        "482218019002",
        "482218019003",
        "482218019004",
        "482218019005",
    ]
    route = respx.get(PANELS_URL).mock(
        side_effect=[
            httpx.Response(200, json=_panel_page(first, 25, 1)),
            httpx.Response(200, json=_panel_page(second, 25, 2)),
        ]
    )

    result = await client.get_panel_data(date(2024, 4, 28))

    assert [reading.panel_serial for reading in result] == first + second
    pages = [
        parse_qs(urlparse(str(call.request.url)).query)["page"][0]
        for call in route.calls
    ]
    assert pages == ["1", "2"]


@respx.mock
@pytest.mark.asyncio
async def test_get_panel_data_stops_on_an_empty_page(client):
    """A page with no devices ends the walk even if total_devices disagrees."""
    route = respx.get(PANELS_URL).mock(
        return_value=httpx.Response(200, json=_panel_page([], 25, 1))
    )

    assert await client.get_panel_data(date(2024, 4, 28)) == []
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_get_panel_data_reports_a_plan_without_device_access(client, status):
    """Per-panel data is not in every Enphase plan: a capability limit, not a fault."""
    respx.get(PANELS_URL).mock(
        return_value=httpx.Response(status, json={"message": "denied"})
    )

    with pytest.raises(PanelDataUnavailableError, match=str(status)):
        await client.get_panel_data(date(2024, 4, 28))


@respx.mock
@pytest.mark.asyncio
async def test_get_panel_data_propagates_other_http_errors(client):
    """A server fault must stay an error rather than look like a plan limit."""
    respx.get(PANELS_URL).mock(
        return_value=httpx.Response(500, json={"message": "boom"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.get_panel_data(date(2024, 4, 28))


@respx.mock
@pytest.mark.asyncio
async def test_get_panel_data_never_logs_the_access_token(client, logged):
    """AC1: the bearer token must not reach the log, on any code path."""
    respx.get(PANELS_URL).mock(
        side_effect=[
            httpx.Response(429, json={"message": "rate limit"}),
            httpx.Response(
                200,
                json={
                    "system_id": 12345,
                    "total_devices": 1,
                    "devices": [{"intervals": [{"enwh": 20}]}],
                },
            ),
        ]
    )

    result = await client.get_panel_data(date(2024, 4, 28))

    # A device with no serial number is unusable but must be reported, so this
    # run produces both log lines get_panel_data can emit.
    assert result == []
    assert any("serial number" in line for line in logged)
    assert logged
    assert not [line for line in logged if "test-token" in line]


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
