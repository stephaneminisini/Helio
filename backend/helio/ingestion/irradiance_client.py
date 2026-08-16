import math
from abc import ABC, abstractmethod
from datetime import date

import httpx
import pandas as pd  # required by pvlib internals
import pvlib
from loguru import logger

from helio.core.config import IRRADIANCE_SOURCES

NASA_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
# NASA POWER reports absent measurements as -999 rather than omitting the key.
# Clamping that to 0.0 would store a real "the sun did not shine" day, which
# drives theoretical_kwh to 0 and makes the month's PR meaningless.
NASA_FILL_VALUE = -999.0


class IrradianceSourceError(RuntimeError):
    """Raised when a configured irradiance source cannot supply data."""


class IrradianceUnavailableError(RuntimeError):
    """Raised when a source has no usable measurement for the requested date."""


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
            Dict with keys 'ghi' and 'dni' in kWh/m2/day for `target_date`.

        Raises:
            httpx.HTTPStatusError: On API errors.
            IrradianceUnavailableError: If the source has no usable measurement
                for `target_date`. Callers write no row rather than storing a
                fabricated value.
        """


def _nasa_measurement(
    props: dict[str, dict[str, float]], parameter: str, date_str: str
) -> float:
    """Read one NASA POWER parameter, rejecting absent measurements.

    Args:
        props: The `properties.parameter` object from a NASA POWER response.
        parameter: Parameter name to read, e.g. 'ALLSKY_SFC_SW_DWN'.
        date_str: The requested date as YYYYMMDD.

    Returns:
        The measurement in kWh/m2/day.

    Raises:
        IrradianceUnavailableError: If the parameter or date is missing, or the
            value is the -999 fill marker.
    """
    raw = props.get(parameter, {}).get(date_str)
    if raw is None:
        raise IrradianceUnavailableError(
            f"NASA POWER returned no {parameter} for {date_str}"
        )
    value = float(raw)
    if value <= NASA_FILL_VALUE:
        raise IrradianceUnavailableError(
            f"NASA POWER reported {parameter} as unavailable ({value}) for {date_str}"
        )
    return max(0.0, value)


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
            Dict with keys 'ghi' and 'dni' in kWh/m2/day, measured on
            `target_date`.

        Raises:
            httpx.HTTPStatusError: On API errors.
            IrradianceUnavailableError: If either parameter is absent or carries
                the -999 fill value for `target_date`.
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
        ghi = _nasa_measurement(props, "ALLSKY_SFC_SW_DWN", date_str)
        dni = _nasa_measurement(props, "ALLSKY_SFC_SW_DNI", date_str)
        logger.debug("NASA irradiance for {}: ghi={}, dni={}", target_date, ghi, dni)
        return {"ghi": ghi, "dni": dni}


def build_irradiance_client(source: str) -> IrradianceClient | None:
    """Return the client for a configured irradiance source.

    Callers pass the source stored on the system record rather than the
    IRRADIANCE_SOURCE environment variable, which only seeds new systems. A
    source chosen on the Setup tab therefore takes effect on the next poll with
    no restart.

    Args:
        source: Source identifier stored on the system record.

    Returns:
        The matching client, or None when source is 'manual' and irradiance rows
        are entered by hand so nothing should be fetched.

    Raises:
        IrradianceSourceError: If source is not a supported value.
    """
    if source not in IRRADIANCE_SOURCES:
        raise IrradianceSourceError(
            f"irradiance_source '{source}' is not supported; expected one of "
            f"{', '.join(IRRADIANCE_SOURCES)}"
        )
    if source == "manual":
        return None
    return NASAClient()
