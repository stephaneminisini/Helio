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
class CurrentProduction:
    """The most recent instantaneous output Enphase has on record.

    Attributes:
        watts: Reported output in watts.
        reported_at: UTC datetime the envoy took the reading. Carried alongside
            the value because envoys report in batches, so a figure without its
            timestamp cannot be told apart from a stale one.
    """

    watts: float
    reported_at: datetime


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

    async def get_current_power(self) -> CurrentProduction | None:
        """Fetch the system's latest reported output.

        Returns:
            The reading and the time it was taken, or None when the summary
            omits either field, which is what a system that has never reported
            looks like.

        Raises:
            RuntimeError: After MAX_RETRIES rate-limit responses.
            httpx.HTTPStatusError: On non-retryable API errors.
        """
        url = f"{BASE_URL}/systems/{self._system_id}/summary"
        data = await self._request("GET", url)
        watts = data.get("current_power")
        reported_at = data.get("last_report_at")
        if watts is None or reported_at is None:
            logger.warning(
                "Enphase summary has no current power reading: {}", sorted(data)
            )
            return None
        return CurrentProduction(
            watts=float(watts),
            reported_at=datetime.fromtimestamp(reported_at, tz=UTC),
        )

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
