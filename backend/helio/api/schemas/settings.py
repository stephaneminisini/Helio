from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field


def _not_in_future(value: date) -> date:
    """Reject dates after today.

    Args:
        value: The candidate date.

    Returns:
        The validated date.

    Raises:
        ValueError: If the date is after today.
    """
    if value > date.today():
        raise ValueError("install_date cannot be in the future")
    return value


PastDate = Annotated[date, AfterValidator(_not_in_future)]

Latitude = Annotated[Decimal, Field(ge=-90, le=90)]
Longitude = Annotated[Decimal, Field(ge=-180, le=180)]


class SettingsResponse(BaseModel):
    """Response model for the /api/settings endpoints."""

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

    model_config = {"from_attributes": True}


class SettingsCreate(BaseModel):
    """Request body for POST /api/settings.

    Coordinates are required: irradiance is fetched for a point on the globe, and
    a system registered without one would silently derive its Performance Ratio
    from irradiance at 0N 0E.
    """

    enphase_system_id: str = Field(min_length=1, max_length=64)
    install_date: PastDate
    latitude: Latitude
    longitude: Longitude
    name: str | None = Field(default=None, max_length=128)
    location: str | None = Field(default=None, max_length=256)
    system_size_kw: Decimal | None = Field(default=None, gt=0, le=999)
    panel_count: int | None = Field(default=None, gt=0)
    panel_wattage_w: int | None = Field(default=None, gt=0)
    tilt_angle_deg: Decimal | None = Field(default=None, ge=0, le=90)
    azimuth_deg: Decimal | None = Field(default=None, ge=0, le=360)
    degradation_rate: Decimal | None = Field(default=None, ge=0, le=10)
    irradiance_source: Literal["nrel", "nasa"] | None = None


class SettingsUpdate(BaseModel):
    """Request body for PUT /api/settings. All fields optional for partial updates."""

    name: str | None = Field(default=None, max_length=128)
    location: str | None = Field(default=None, max_length=256)
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    system_size_kw: Decimal | None = Field(default=None, gt=0, le=999)
    panel_count: int | None = Field(default=None, gt=0)
    panel_wattage_w: int | None = Field(default=None, gt=0)
    install_date: PastDate | None = None
    tilt_angle_deg: Decimal | None = Field(default=None, ge=0, le=90)
    azimuth_deg: Decimal | None = Field(default=None, ge=0, le=360)
    degradation_rate: Decimal | None = Field(default=None, ge=0, le=10)
    irradiance_source: Literal["nrel", "nasa"] | None = None
