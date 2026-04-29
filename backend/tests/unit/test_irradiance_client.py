from datetime import date

import httpx
import pytest
import respx

from helio.ingestion.irradiance_client import NASAClient, NRELClient, compute_poa


def test_compute_poa_returns_positive_value():
    poa = compute_poa(
        ghi=5.0,
        dni=4.0,
        tilt=30.0,
        azimuth=180.0,
        latitude=45.0,
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
        target_date=date(2024, 6, 21),
    )
    assert poa == 0.0


@respx.mock
@pytest.mark.asyncio
async def test_nrel_client_returns_irradiance():
    respx.get("https://developer.nrel.gov/api/solar/solar_resource/v1.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "outputs": {
                    "avg_ghi": {"annual": 4.5},
                    "avg_dni": {"annual": 4.0},
                }
            },
        )
    )
    client = NRELClient(api_key="test-key")
    result = await client.get_daily_irradiance(
        latitude=45.5,
        longitude=-73.6,
        target_date=date(2024, 4, 28),
    )
    assert result["ghi"] > 0
    assert result["dni"] > 0


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
