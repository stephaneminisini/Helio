from datetime import date
from typing import Literal

from pydantic import BaseModel

# The grain of a comparison. Kept as a Literal so an unsupported value is
# rejected at the boundary with a 422 naming the values that are accepted.
Period = Literal["day", "month", "year"]


class PeriodTotal(BaseModel):
    """Production over one comparable stretch of the calendar."""

    # "2025-07-12", "2025-07" or "2025", matching the requested period.
    label: str
    start: date
    end: date
    # None when the window has nothing stored, which is not the same as a
    # window that is known to have produced 0 kWh.
    production_kwh: float | None
    # How the anchor period compares with this one, so a positive figure means
    # the anchor is ahead. None for the anchor's own entry.
    pct_change: float | None
    # True when production cannot cover the whole window: it either runs past
    # today or starts before the system was installed. Such a total is lower
    # for reasons that have nothing to do with performance.
    is_partial: bool


class CompareResponse(BaseModel):
    """Response model for the /api/compare endpoint."""

    period: Period
    anchor: date
    # Oldest first, with the anchor period last. Prior periods with nothing
    # stored are left out; the anchor is always present, even when empty.
    periods: list[PeriodTotal]
