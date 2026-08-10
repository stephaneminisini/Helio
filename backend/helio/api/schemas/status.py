from datetime import date, datetime

from pydantic import BaseModel


class PollLogEntry(BaseModel):
    """A single poll_log row, exposed so the UI can tell 'no data yet' from 'broken'."""

    poll_type: str | None
    status: str | None
    started_at: datetime
    completed_at: datetime | None
    records_inserted: int
    error_message: str | None

    model_config = {"from_attributes": True}


class BackfillStatus(BaseModel):
    """Progress of the most recent or in-flight backfill run."""

    running: bool
    total_days: int
    completed_days: int
    failed_days: int
    error: str | None


class StatusResponse(BaseModel):
    """Response model for GET /api/status.

    Describes how far ingestion has got, so every surface can render an honest
    empty, partial, or broken state instead of a zeroed dashboard.
    """

    configured: bool
    location_configured: bool
    install_date: date | None
    first_day: date | None
    last_day: date | None
    days_with_data: int
    days_expected: int
    missing_days: int
    months_with_data: int
    irradiance_source: str | None
    weather_normalized: bool
    last_poll: PollLogEntry | None
    backfill: BackfillStatus
