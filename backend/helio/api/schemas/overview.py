from datetime import date

from pydantic import BaseModel


class ComparisonPair(BaseModel):
    """A pair of current vs prior period values with percentage change."""

    current_kwh: float
    prior_kwh: float | None
    pct_change: float | None


class OverviewResponse(BaseModel):
    """Response model for the /api/overview endpoint."""

    today: date
    today_kwh: float
    current_power_w: float | None
    day_comparison: ComparisonPair
    day_vs_last_month: ComparisonPair
    month_comparison: ComparisonPair
    month_vs_last_year: ComparisonPair
    ytd_comparison: ComparisonPair
    best_day_kwh: float | None
    best_day_date: date | None
    all_time_kwh: float
