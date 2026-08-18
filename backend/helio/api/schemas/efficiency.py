from datetime import date
from typing import Literal

from pydantic import BaseModel


class MonthlyPRPoint(BaseModel):
    """A single month's performance ratio data point.

    anomaly_reason carries the summarizer's explanation of the flag so the chart
    can say how far below expected the month fell; it is null whenever
    is_anomaly is false.
    """

    month: date
    production_kwh: float
    performance_ratio: float | None
    expected_pr: float | None
    is_anomaly: bool
    anomaly_reason: str | None


class AnnualRateEntry(BaseModel):
    """Annual degradation stats for a single year."""

    avg_pr: float
    annual_drop: float | None


class DegradationSummary(BaseModel):
    """Aggregated degradation metrics across all years.

    warranty_threshold and energy_rate_per_kwh are echoed back so the client can
    show what the figures were computed against; lost_dollars is meaningless
    without the rate that produced it.

    So is the baseline: both the anomaly flags and the lost-production figure are
    measured against it, so baseline_pr and baseline_source say what standard was
    used. baseline_pr is null, and baseline_source "none", when the system has
    neither a configured baseline nor a full year of history, in which case
    nothing is flagged and nothing is counted as lost.
    """

    annual_rates: dict[int, AnnualRateEntry]
    lost_kwh: float
    lost_dollars: float
    warranty_threshold: float
    exceeds_warranty: bool
    energy_rate_per_kwh: float
    energy_rate_currency: str
    baseline_pr: float | None
    baseline_source: Literal["configured", "measured", "none"]


class ProjectedYear(BaseModel):
    """One projected calendar year, valued at the year's mid-point."""

    year: int
    projected_pr: float


class ProjectionSummary(BaseModel):
    """Forward extrapolation of the measured Performance Ratio trend.

    annual_rate is the PR fraction the trend loses per year, so it compares
    directly against DegradationSummary.warranty_threshold divided by 100. It is
    null, low_confidence true and years empty whenever the stored history cannot
    support a trend line at all.
    """

    months_of_history: int
    annual_rate: float | None
    low_confidence: bool
    warranty_breach_year: int | None
    years: list[ProjectedYear]


class EfficiencyResponse(BaseModel):
    """Response model for the /api/efficiency endpoint."""

    pr_history: list[MonthlyPRPoint]
    degradation: DegradationSummary
    projection: ProjectionSummary
