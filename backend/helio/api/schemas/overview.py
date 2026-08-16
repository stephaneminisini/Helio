from datetime import date

from pydantic import BaseModel


class ComparisonPair(BaseModel):
    """A pair of current vs prior period values with percentage change."""

    current_kwh: float
    prior_kwh: float | None
    pct_change: float | None


class YtdPoint(BaseModel):
    """Production from 1 January to the anchor day, for one year."""

    year: int
    production_kwh: float
    # How the current year compares with this one, so a positive figure means
    # the current year is ahead. None for the current year itself and for any
    # year that produced nothing to divide by.
    pct_change: float | None
    # True when the window starts after 1 January because the system was
    # installed mid-year, which makes the figure lower for a reason that has
    # nothing to do with performance.
    is_partial: bool


class OverviewResponse(BaseModel):
    """Response model for the /api/overview endpoint."""

    today: date
    today_kwh: float
    current_power_w: float | None
    day_comparison: ComparisonPair
    day_vs_last_month: ComparisonPair
    month_comparison: ComparisonPair
    month_vs_last_year: ComparisonPair
    # One entry per year from the install year to the current year, ascending,
    # each covering 1 January to the same day of the year. Replaces a single
    # prior-year pair: BR-07 asks for prior years, plural.
    ytd_history: list[YtdPoint]
    best_day_kwh: float | None
    best_day_date: date | None
    all_time_kwh: float
