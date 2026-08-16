import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.parse import urlencode

import httpx
from loguru import logger

BASE_URL = "https://api.enphaseenergy.com/api/v4"
TOKEN_URL = "https://api.enphaseenergy.com/oauth/token"
AUTHORIZE_URL = "https://api.enphaseenergy.com/oauth/authorize"
MAX_RETRIES = 3
# The device-level telemetry endpoint caps a page at 20 devices, so a larger
# value is silently clamped and would make the pagination arithmetic wrong.
PANEL_PAGE_SIZE = 20
PANEL_ACCESS_DENIED_MESSAGE = (
    "Enphase answered {} for device-level telemetry. Per-panel monitoring needs "
    "an Enphase plan that exposes microinverter data; the rest of the poll is "
    "unaffected."
)


class PanelDataUnavailableError(Exception):
    """Raised when Enphase will not serve device-level telemetry.

    Per-panel data is not part of every Enphase plan, so this is a capability
    limit rather than a fault: callers skip the panel step and let the rest of
    the poll run.
    """


def authorize_url(client_id: str, redirect_uri: str) -> str:
    """Build the Enphase consent-screen URL for the authorization-code flow.

    Args:
        client_id: Enphase OAuth application client ID.
        redirect_uri: Callback URL registered with the Enphase application. It
            must match the one sent to the token endpoint or Enphase rejects
            the code exchange.

    Returns:
        The fully-formed consent URL to send the user's browser to.
    """
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


@dataclass
class IntervalData:
    """A single 15-minute production interval.

    Attributes:
        interval_start: UTC datetime marking the start of the interval.
        duration_seconds: Duration of the interval in seconds.
        production_wh: Energy produced during the interval in watt-hours.
    """

    interval_start: datetime
    duration_seconds: int
    production_wh: float


@dataclass
class PanelEnergy:
    """Energy produced by one microinverter over a single day.

    Attributes:
        panel_serial: Serial number of the microinverter, as reported by Enphase.
        energy_wh: Energy produced across every interval of the day, in
            watt-hours.
    """

    panel_serial: str
    energy_wh: float


class EnphaseClient:
    """Async client for Enphase API v4 with token management and retry logic.

    Args:
        client_id: Enphase OAuth application client ID.
        client_secret: Enphase OAuth application client secret.
        system_id: Enphase system ID to query.
        access_token: Current OAuth access token (may be empty on first run).
        refresh_token: OAuth refresh token for renewing access.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        system_id: str,
        access_token: str,
        refresh_token: str,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._system_id = system_id
        self._access_token = access_token
        self._refresh_token = refresh_token

    @property
    def system_id(self) -> str:
        """The Enphase system ID this client queries."""
        return self._system_id

    @property
    def access_token(self) -> str:
        """The current access token, updated by refresh_access_token()."""
        return self._access_token

    @property
    def refresh_token(self) -> str:
        """The current refresh token, rotated by refresh_access_token()."""
        return self._refresh_token

    async def _request(
        self,
        method: str,
        url: str,
        params: dict | None = None,
    ) -> dict:
        """Execute an authenticated request with exponential backoff on 429/503.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: Full URL to request.
            params: Optional query parameters.

        Returns:
            Parsed JSON response body.

        Raises:
            RuntimeError: After MAX_RETRIES failed attempts due to rate limiting.
            httpx.HTTPStatusError: On non-retryable HTTP errors.
        """
        headers = {"Authorization": f"Bearer {self._access_token}"}
        response: httpx.Response | None = None
        async with httpx.AsyncClient() as http:
            for attempt in range(MAX_RETRIES):
                response = await http.request(
                    method, url, params=params, headers=headers
                )
                if response.status_code in (429, 503):
                    if attempt == MAX_RETRIES - 1:
                        body = response.json()
                        raise RuntimeError(
                            body.get("message", f"API error {response.status_code}")
                        )
                    wait = 2**attempt
                    logger.warning(
                        "API returned {} (attempt {}/{}), retrying in {}s",
                        response.status_code,
                        attempt + 1,
                        MAX_RETRIES,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                response.raise_for_status()
                return response.json()
        return {}

    async def get_intervals(self, start: date, end: date) -> list[IntervalData]:
        """Fetch 15-minute production intervals for a date range.

        Args:
            start: Start date (inclusive).
            end: End date (inclusive).

        Returns:
            List of IntervalData ordered by interval_start ascending.

        Raises:
            RuntimeError: After MAX_RETRIES rate-limit responses.
            httpx.HTTPStatusError: On non-retryable API errors.
        """
        url = f"{BASE_URL}/systems/{self._system_id}/telemetry/production_micro"
        params = {
            "start_at": int(
                datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp()
            ),
            "end_at": int(
                datetime(
                    end.year, end.month, end.day, 23, 59, 59, tzinfo=UTC
                ).timestamp()
            ),
        }
        data = await self._request("GET", url, params=params)
        result = []
        for item in data.get("intervals", []):
            end_at_ts = item.get("end_at")
            if end_at_ts is None:
                logger.warning("Interval missing end_at field, skipping: {}", item)
                continue
            interval_start = datetime.fromtimestamp(end_at_ts - 900, tz=UTC)
            result.append(
                IntervalData(
                    interval_start=interval_start,
                    duration_seconds=900,
                    production_wh=float(item.get("wh_del", 0)),
                )
            )
        return result

    async def get_panel_data(self, day: date) -> list[PanelEnergy]:
        """Fetch per-microinverter production for a single day.

        Enphase reports device-level telemetry as 5-minute intervals grouped by
        serial number, paginated at PANEL_PAGE_SIZE devices per response, and
        resolves the day boundary in the system's own timezone. The intervals
        are summed here so one record per panel per day reaches the caller.

        Args:
            day: Calendar date to fetch, interpreted in the system's timezone.

        Returns:
            One PanelEnergy per microinverter that reported, in the order
            Enphase returned them. Empty if Enphase reports no devices, which is
            also how a plan without device-level access can present.

        Raises:
            PanelDataUnavailableError: If Enphase answers 401 or 403, which is
                what a plan without device-level access looks like.
            RuntimeError: After MAX_RETRIES rate-limit responses.
            httpx.HTTPStatusError: On any other non-retryable API error.
        """
        url = f"{BASE_URL}/systems/{self._system_id}/devices/micros/telemetry"
        readings: list[PanelEnergy] = []
        page = 1
        while True:
            try:
                data = await self._request(
                    "GET",
                    url,
                    params={
                        "granularity": "day",
                        "start_date": day.isoformat(),
                        "page": page,
                        "size": PANEL_PAGE_SIZE,
                    },
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (401, 403):
                    raise PanelDataUnavailableError(
                        PANEL_ACCESS_DENIED_MESSAGE.format(exc.response.status_code)
                    ) from exc
                raise
            devices = data.get("devices") or []
            if not devices:
                break
            for device in devices:
                serial = device.get("serial_number")
                if not serial:
                    logger.warning(
                        "Microinverter telemetry without a serial number, skipping "
                        "(fields: {})",
                        sorted(device),
                    )
                    continue
                intervals = device.get("intervals") or []
                readings.append(
                    PanelEnergy(
                        panel_serial=serial,
                        energy_wh=float(
                            sum(interval.get("enwh") or 0 for interval in intervals)
                        ),
                    )
                )
            # total_devices counts every device across all pages, so it is what
            # says whether another page exists.
            if page * PANEL_PAGE_SIZE >= (data.get("total_devices") or 0):
                break
            page += 1
        return readings

    async def get_system_info(self) -> dict:
        """Fetch system metadata from the Enphase API.

        Returns:
            Raw system metadata dict.

        Raises:
            RuntimeError: After MAX_RETRIES rate-limit responses.
            httpx.HTTPStatusError: On API errors.
        """
        url = f"{BASE_URL}/systems/{self._system_id}"
        return await self._request("GET", url)

    async def _post_token(self, data: dict[str, str]) -> dict:
        """Call the Enphase token endpoint with the application credentials.

        Args:
            data: Form body identifying the grant being exchanged.

        Returns:
            Parsed JSON response body.

        Raises:
            httpx.HTTPStatusError: If Enphase rejects the grant.
        """
        async with httpx.AsyncClient() as http:
            response = await http.post(
                TOKEN_URL,
                data=data,
                auth=(self._client_id, self._client_secret),
            )
        response.raise_for_status()
        return response.json()

    async def authenticate(self, auth_code: str, redirect_uri: str) -> tuple[str, str]:
        """Exchange an OAuth authorization code for an access/refresh token pair.

        Args:
            auth_code: Single-use code Enphase appended to the callback URL.
            redirect_uri: The same redirect URI used to obtain the code.

        Returns:
            The (access_token, refresh_token) pair, also stored on the client.

        Raises:
            httpx.HTTPStatusError: If Enphase rejects the code, which is what
                an expired, reused, or mismatched-redirect code looks like.
            ValueError: If either token is missing from the response. Both are
                required, so a half-populated pair is never stored.
        """
        body = await self._post_token(
            {
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": redirect_uri,
            }
        )
        access_token = body.get("access_token")
        refresh_token = body.get("refresh_token")
        if not access_token or not refresh_token:
            raise ValueError(
                f"Token response missing access_token or refresh_token: {sorted(body)}"
            )
        self._access_token = access_token
        self._refresh_token = refresh_token
        logger.info("Enphase authorization code exchanged for tokens")
        return access_token, refresh_token

    async def refresh_access_token(self) -> str:
        """Refresh the OAuth access token using the stored refresh token.

        Returns:
            The new access token string.

        Raises:
            httpx.HTTPStatusError: On token refresh failure.
            ValueError: If the response omits access_token.
        """
        body = await self._post_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            }
        )
        new_token = body.get("access_token")
        if new_token is None:
            raise ValueError(
                f"Token refresh response missing access_token: {list(body.keys())}"
            )
        self._access_token = new_token
        self._refresh_token = body.get("refresh_token", self._refresh_token)
        logger.info("Enphase access token refreshed successfully")
        return self._access_token
