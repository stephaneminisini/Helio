from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

IrradianceSource = Literal["nasa", "manual"]


class SettingsResponse(BaseModel):
    """Response model for the /api/settings endpoints.

    All fields except `enphase_connected` map directly to `systems` columns.
    `enphase_connected` is derived from the application configuration and is
    filled in by the route, so it defaults to False when the model is built
    straight from an ORM row.
    """

    enphase_system_id: str
    name: str | None
    location: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    system_size_kw: Decimal | None
    panel_count: int | None
    panel_wattage_w: int | None
    install_date: date
    tilt_angle_deg: Decimal | None
    azimuth_deg: Decimal | None
    degradation_rate: Decimal
    irradiance_source: str
    enphase_connected: bool = False

    model_config = {"from_attributes": True}


class SettingsCreate(BaseModel):
    """Request body for POST /api/settings.

    Bounds mirror the `systems` column definitions so out-of-range input is
    rejected at the boundary with a 422 rather than reaching Postgres and
    surfacing as a 500.
    """

    enphase_system_id: str = Field(min_length=1, max_length=64)
    install_date: date
    name: str | None = Field(default=None, max_length=128)
    location: str | None = Field(default=None, max_length=256)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    system_size_kw: Decimal | None = Field(default=None, gt=0, lt=1000)
    panel_count: int | None = Field(default=None, gt=0, lt=100_000)
    panel_wattage_w: int | None = Field(default=None, gt=0, lt=10_000)
    tilt_angle_deg: Decimal | None = Field(default=None, ge=0, le=90)
    azimuth_deg: Decimal | None = Field(default=None, ge=0, le=360)
    degradation_rate: Decimal | None = Field(default=None, ge=0, le=99)
    irradiance_source: IrradianceSource | None = None


class SettingsUpdate(BaseModel):
    """Request body for PUT /api/settings. All fields optional for partial updates.

    `irradiance_source` is constrained to the supported sources because ingestion
    selects its client from the stored value: an unrecognised source would be
    accepted here and then skip irradiance on every subsequent poll.
    """

    name: str | None = None
    location: str | None = None
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    system_size_kw: Decimal | None = None
    panel_count: int | None = None
    panel_wattage_w: int | None = None
    install_date: date | None = None
    tilt_angle_deg: Decimal | None = None
    azimuth_deg: Decimal | None = None
    degradation_rate: Decimal | None = None
    irradiance_source: IrradianceSource | None = None
