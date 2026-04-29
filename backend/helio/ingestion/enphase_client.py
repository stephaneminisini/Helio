import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
from loguru import logger

BASE_URL = "https://api.enphaseenergy.com/api/v4"
TOKEN_URL = "https://api.enphaseenergy.com/oauth/token"
MAX_RETRIES = 3


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


class EnphaseClient:
    """Async client for Enphase API v4 with token management and retry logic.

    Args:
        client_id: Enphase OAuth application client ID.
        client_secret: Enphase OAuth application client secret.
        system_id: Enphase system ID to query.
        access_token: Current OAuth access token (may be empty on first run).
        refresh_token: OAuth refresh token for renewing access.
        fernet_key: Fernet key used to encrypt tokens before DB storage.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        system_id: str,
        access_token: str,
        refresh_token: str,
        fernet_key: str,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._system_id = system_id
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._fernet_key = fernet_key

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

    async def refresh_access_token(self) -> str:
        """Refresh the OAuth access token using the stored refresh token.

        Returns:
            The new access token string.

        Raises:
            httpx.HTTPStatusError: On token refresh failure.
        """
        async with httpx.AsyncClient() as http:
            response = await http.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
                auth=(self._client_id, self._client_secret),
            )
        response.raise_for_status()
        body = response.json()
        new_token = body.get("access_token")
        if new_token is None:
            raise ValueError(
                f"Token refresh response missing access_token: {list(body.keys())}"
            )
        self._access_token = new_token
        self._refresh_token = body.get("refresh_token", self._refresh_token)
        logger.info("Enphase access token refreshed successfully")
        return self._access_token
