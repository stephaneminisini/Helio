import math
from datetime import date

import httpx
import pandas as pd
import pvlib
import pytest
import respx

from helio.ingestion.irradiance_client import (
    IrradianceSourceError,
    IrradianceUnavailableError,
    NASAClient,
    build_irradiance_client,
    compute_poa,
)


def test_compute_poa_returns_positive_value():
    poa = compute_poa(
        ghi=5.0,
        dni=4.0,
        tilt=30.0,
        azimuth=180.0,
        latitude=45.0,
        longitude=-73.6,
        target_date=date(2024, 6, 21),
    )
    assert poa > 0


def test_compute_poa_zero_ghi_returns_zero():
    poa = compute_poa(
        ghi=0.0,
        dni=0.0,
        tilt=30.0,
        azimuth=180.0,
        latitude=45.0,
        longitude=-73.6,
        target_date=date(2024, 6, 21),
    )
    assert poa == 0.0


@respx.mock
@pytest.mark.asyncio
async def test_nasa_client_returns_irradiance():
    respx.get("https://power.larc.nasa.gov/api/temporal/daily/point").mock(
        return_value=httpx.Response(
            200,
            json={
                "properties": {
                    "parameter": {
                        "ALLSKY_SFC_SW_DWN": {"20240428": 5.1},
                        "ALLSKY_SFC_SW_DNI": {"20240428": 4.2},
                    }
                }
            },
        )
    )
    client = NASAClient()
    result = await client.get_daily_irradiance(
        latitude=45.5,
        longitude=-73.6,
        target_date=date(2024, 4, 28),
    )
    assert result["ghi"] == pytest.approx(5.1)
    assert result["dni"] == pytest.approx(4.2)


def test_build_irradiance_client_returns_nasa_client():
    assert isinstance(build_irradiance_client("nasa"), NASAClient)


def test_build_irradiance_client_returns_none_for_manual():
    """'manual' means the rows are entered by hand, so nothing is fetched."""
    assert build_irradiance_client("manual") is None


def test_build_irradiance_client_rejects_unsupported_source():
    with pytest.raises(IrradianceSourceError) as exc_info:
        build_irradiance_client("NASA")

    assert "not supported" in str(exc_info.value)


def test_build_irradiance_client_rejects_nrel_as_a_daily_source():
    """NREL only ever returned annual averages, so it is no longer selectable."""
    with pytest.raises(IrradianceSourceError) as exc_info:
        build_irradiance_client("nrel")

    assert "not supported" in str(exc_info.value)


def _nasa_response(ghi, dni, date_str="20240428"):
    """Build a NASA POWER response body carrying the given measurements."""
    return httpx.Response(
        200,
        json={
            "properties": {
                "parameter": {
                    "ALLSKY_SFC_SW_DWN": {date_str: ghi},
                    "ALLSKY_SFC_SW_DNI": {date_str: dni},
                }
            }
        },
    )


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("ghi,dni", [(-999.0, 4.2), (5.1, -999.0), (-999.0, -999.0)])
async def test_nasa_client_rejects_the_fill_value(ghi, dni):
    """AC3: -999 means 'no measurement', not a day with no sunshine."""
    respx.get("https://power.larc.nasa.gov/api/temporal/daily/point").mock(
        return_value=_nasa_response(ghi, dni)
    )

    with pytest.raises(IrradianceUnavailableError) as exc_info:
        await NASAClient().get_daily_irradiance(
            latitude=45.5, longitude=-73.6, target_date=date(2024, 4, 28)
        )

    assert "20240428" in str(exc_info.value)


@respx.mock
@pytest.mark.asyncio
async def test_nasa_client_rejects_a_missing_date():
    """A response that omits the requested day must not yield a zero row."""
    respx.get("https://power.larc.nasa.gov/api/temporal/daily/point").mock(
        return_value=_nasa_response(5.1, 4.2, date_str="20240101")
    )

    with pytest.raises(IrradianceUnavailableError):
        await NASAClient().get_daily_irradiance(
            latitude=45.5, longitude=-73.6, target_date=date(2024, 4, 28)
        )


@respx.mock
@pytest.mark.asyncio
async def test_nasa_client_rejects_a_null_measurement():
    respx.get("https://power.larc.nasa.gov/api/temporal/daily/point").mock(
        return_value=_nasa_response(None, 4.2)
    )

    with pytest.raises(IrradianceUnavailableError):
        await NASAClient().get_daily_irradiance(
            latitude=45.5, longitude=-73.6, target_date=date(2024, 4, 28)
        )


def test_compute_poa_matches_the_pvlib_reference():
    """AC4: POA must track a pvlib transposition computed independently.

    The reference is assembled from pvlib primitives step by step rather than by
    calling compute_poa, so a regression in the wiring it does around them - the
    kWh/W unit conversion, the DHI derivation, the transposition model - shows up
    as a mismatch here.
    """
    ghi_kwh, dni_kwh = 5.0, 4.0
    tilt, azimuth = 30.0, 180.0
    latitude, longitude = 45.0, -73.6
    target_date = date(2024, 6, 21)

    times = pd.date_range(
        start=f"{target_date} 12:00:00", periods=1, freq="h", tz="UTC"
    )
    solar_position = pvlib.location.Location(
        latitude=latitude, longitude=longitude
    ).get_solarposition(times)
    zenith = float(solar_position["apparent_zenith"].iloc[0])
    dhi_kwh = max(0.0, ghi_kwh - dni_kwh * math.cos(math.radians(zenith)))

    expected = (
        float(
            pvlib.irradiance.get_total_irradiance(
                surface_tilt=tilt,
                surface_azimuth=azimuth,
                solar_zenith=solar_position["apparent_zenith"].iloc[0],
                solar_azimuth=solar_position["azimuth"].iloc[0],
                dni=dni_kwh * 1000,
                ghi=ghi_kwh * 1000,
                dhi=dhi_kwh * 1000,
                dni_extra=float(pvlib.irradiance.get_extra_radiation(times).iloc[0]),
                model="haydavies",
            )["poa_global"]
        )
        / 1000
    )

    actual = compute_poa(
        ghi=ghi_kwh,
        dni=dni_kwh,
        tilt=tilt,
        azimuth=azimuth,
        latitude=latitude,
        longitude=longitude,
        target_date=target_date,
    )

    assert actual == pytest.approx(expected, rel=1e-3)
