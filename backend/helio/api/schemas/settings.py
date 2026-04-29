from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class SettingsResponse(BaseModel):
    """Response model for GET /api/settings."""

    enphase_system_id: str
    name: str | None
    location: str | None
    system_size_kw: Decimal | None
    panel_count: int | None
    panel_wattage_w: int | None
    install_date: date
    tilt_angle_deg: Decimal | None
    azimuth_deg: Decimal | None
    degradation_rate: Decimal
    irradiance_source: str

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    """Request body for PUT /api/settings."""

    name: str | None = None
    location: str | None = None
    system_size_kw: Decimal | None = None
    panel_count: int | None = None
    panel_wattage_w: int | None = None
    install_date: date | None = None
    tilt_angle_deg: Decimal | None = None
    azimuth_deg: Decimal | None = None
    degradation_rate: Decimal | None = None
    irradiance_source: str | None = None
