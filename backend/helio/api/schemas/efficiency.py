from datetime import date

from pydantic import BaseModel


class MonthlyPRPoint(BaseModel):
    """A single month's performance ratio data point."""

    month: date
    production_kwh: float
    performance_ratio: float | None
    expected_pr: float | None
    is_anomaly: bool


class AnnualRateEntry(BaseModel):
    """Annual degradation stats for a single year."""

    avg_pr: float
    annual_drop: float | None


class DegradationSummary(BaseModel):
    """Aggregated degradation metrics across all years."""

    annual_rates: dict[int, AnnualRateEntry]
    lost_kwh: float
    lost_dollars: float
    warranty_threshold: float
    exceeds_warranty: bool


class EfficiencyResponse(BaseModel):
    """Response model for the /api/efficiency endpoint."""

    pr_history: list[MonthlyPRPoint]
    degradation: DegradationSummary
