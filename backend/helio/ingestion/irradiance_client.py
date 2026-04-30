import math
from abc import ABC, abstractmethod
from datetime import date

import httpx
import pandas as pd  # required by pvlib internals
import pvlib
from loguru import logger

NREL_URL = "https://developer.nrel.gov/api/solar/solar_resource/v1.json"
NASA_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"


def compute_poa(
    ghi: float,
    dni: float,
    tilt: float,
    azimuth: float,
    latitude: float,
    longitude: float,
    target_date: date,
) -> float:
    """Compute Plane-of-Array irradiance using pvlib Hay-Davies transposition model.

    Args:
        ghi: Global Horizontal Irradiance in kWh/m2/day.
        dni: Direct Normal Irradiance in kWh/m2/day.
        tilt: Panel tilt angle in degrees from horizontal.
        azimuth: Panel azimuth in degrees (180 = south-facing).
        latitude: Site latitude in decimal degrees.
        longitude: Site longitude in decimal degrees.
        target_date: The date for solar position calculation.

    Returns:
        Plane-of-Array irradiance in kWh/m2/day. Returns 0.0 if both ghi and dni are 0.
    """
    if ghi <= 0.0 and dni <= 0.0:
        return 0.0

    times = pd.date_range(
        start=f"{target_date} 12:00:00", periods=1, freq="h", tz="UTC"
    )
    location = pvlib.location.Location(latitude=latitude, longitude=longitude)
    solar_position = location.get_solarposition(times)

    zenith_deg = float(solar_position["apparent_zenith"].iloc[0])
    zenith_cos = math.cos(math.radians(zenith_deg))
    dhi = max(0.0, ghi - dni * zenith_cos)

    dni_extra = pvlib.irradiance.get_extra_radiation(times)

    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt,
        surface_azimuth=azimuth,
        solar_zenith=solar_position["apparent_zenith"].iloc[0],
        solar_azimuth=solar_position["azimuth"].iloc[0],
        dni=dni * 1000,
        ghi=ghi * 1000,
        dhi=max(0.0, dhi * 1000),
        dni_extra=float(dni_extra.iloc[0]),
        model="haydavies",
    )
    return round(float(poa["poa_global"]) / 1000, 4)


class IrradianceClient(ABC):
    """Abstract base for irradiance data providers."""

    @abstractmethod
    async def get_daily_irradiance(
        self, latitude: float, longitude: float, target_date: date
    ) -> dict[str, float]:
        """Fetch daily GHI and DNI for a location and date.

        Args:
            latitude: Site latitude in decimal degrees.
            longitude: Site longitude in decimal degrees.
            target_date: Date to fetch irradiance for.

        Returns:
            Dict with keys 'ghi' and 'dni' in kWh/m2/day.

        Raises:
            httpx.HTTPStatusError: On API errors.
        """


class NRELClient(IrradianceClient):
    """NREL Solar Resource Data API client.

    Args:
        api_key: NREL developer API key.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def get_daily_irradiance(
        self, latitude: float, longitude: float, target_date: date
    ) -> dict[str, float]:
        """Fetch long-term annual average GHI and DNI from NREL Solar Resource API.

        Note: The NREL Solar Resource API v1 returns long-term statistical averages
        (typically 30-year TMY data), not actual daily measured values. The
        target_date parameter is accepted for interface compatibility but does not
        affect the returned values. All days at the same location return the same
        annual average irradiance. Use NASAClient for actual daily historical data.

        Args:
            latitude: Site latitude in decimal degrees.
            longitude: Site longitude in decimal degrees.
            target_date: Accepted for interface compatibility; does not affect result.

        Returns:
            Dict with keys 'ghi' and 'dni' in kWh/m2/day (annual averages).

        Raises:
            httpx.HTTPStatusError: On API errors.
        """
        params = {
            "api_key": self._api_key,
            "lat": latitude,
            "lon": longitude,
        }
        async with httpx.AsyncClient() as http:
            response = await http.get(NREL_URL, params=params)
        response.raise_for_status()
        outputs = response.json().get("outputs", {})
        ghi = float(outputs.get("avg_ghi", {}).get("annual", 0))
        dni = float(outputs.get("avg_dni", {}).get("annual", 0))
        logger.debug("NREL irradiance for {}: ghi={}, dni={}", target_date, ghi, dni)
        return {"ghi": ghi, "dni": dni}


class NASAClient(IrradianceClient):
    """NASA POWER daily irradiance API client (no API key required)."""

    async def get_daily_irradiance(
        self, latitude: float, longitude: float, target_date: date
    ) -> dict[str, float]:
        """Fetch daily GHI and DNI from NASA POWER API.

        Args:
            latitude: Site latitude in decimal degrees.
            longitude: Site longitude in decimal degrees.
            target_date: Date to fetch irradiance for.

        Returns:
            Dict with keys 'ghi' and 'dni' in kWh/m2/day.

        Raises:
            httpx.HTTPStatusError: On API errors.
        """
        date_str = target_date.strftime("%Y%m%d")
        params = {
            "parameters": "ALLSKY_SFC_SW_DWN,ALLSKY_SFC_SW_DNI",
            "community": "RE",
            "longitude": longitude,
            "latitude": latitude,
            "start": date_str,
            "end": date_str,
            "format": "JSON",
        }
        async with httpx.AsyncClient() as http:
            response = await http.get(NASA_URL, params=params)
        response.raise_for_status()
        props = response.json().get("properties", {}).get("parameter", {})
        ghi = max(0.0, float(props.get("ALLSKY_SFC_SW_DWN", {}).get(date_str, 0) or 0))
        dni = max(0.0, float(props.get("ALLSKY_SFC_SW_DNI", {}).get(date_str, 0) or 0))
        logger.debug("NASA irradiance for {}: ghi={}, dni={}", target_date, ghi, dni)
        return {"ghi": ghi, "dni": dni}
