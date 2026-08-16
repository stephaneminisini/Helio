from datetime import date

from pydantic import BaseModel


class PanelPoint(BaseModel):
    """One panel's production over the requested window, relative to the fleet.

    deviation_sigma is None when the spread cannot be measured, so a client must
    not read a missing value as zero deviation.
    """

    panel_serial: str
    energy_wh: float
    normalized_efficiency: float
    deviation_sigma: float | None
    is_underperforming: bool


class PanelsResponse(BaseModel):
    """Response model for the /api/panels endpoint.

    fleet_average_wh and fleet_stdev_wh are echoed back because a panel's flag
    is meaningless without the distribution it was judged against.
    unavailable_reason carries the explanation the UI shows when panels is empty.
    """

    panels: list[PanelPoint]
    fleet_average_wh: float
    fleet_stdev_wh: float
    window_start: date
    window_end: date
    data_available: bool
    unavailable_reason: str | None = None
