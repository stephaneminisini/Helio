from dataclasses import dataclass
from datetime import date
from statistics import mean, pstdev

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.db.models import PanelReading

# BR-16 defines an underperforming panel as more than two standard deviations
# below the fleet average. A population sigma bounds the most extreme deviation
# in a fleet of n panels at -sqrt(n-1), so a single dead panel only clears this
# threshold once the fleet reaches six.
SIGMA_THRESHOLD = 2.0
# Below three panels the standard deviation is degenerate: with two panels every
# spread is exactly one sigma either side of the mean, so nothing can ever be an
# outlier and the arithmetic only invites false confidence.
MIN_FLEET_SIZE = 3


@dataclass
class PanelPerformance:
    """How one panel performed relative to the rest of the fleet.

    Attributes:
        panel_serial: Microinverter serial number.
        energy_wh: Total energy produced across the window, in watt-hours.
        normalized_efficiency: energy_wh as a fraction of the fleet average, so
            1.0 is exactly average and 0.8 is 20 percent below it.
        deviation_sigma: Distance from the fleet mean in standard deviations,
            negative when below it. None when the spread cannot be measured,
            which is the case for a fleet under MIN_FLEET_SIZE and for a fleet
            whose panels all produced the same amount.
        is_underperforming: True when the panel is more than SIGMA_THRESHOLD
            standard deviations below the fleet mean.
    """

    panel_serial: str
    energy_wh: float
    normalized_efficiency: float
    deviation_sigma: float | None
    is_underperforming: bool


@dataclass
class FleetPerformance:
    """Per-panel results plus the fleet statistics they were measured against.

    Attributes:
        panels: One entry per panel that reported in the window, by serial.
        average_wh: Mean energy across those panels, in watt-hours.
        stdev_wh: Population standard deviation of that energy, in watt-hours.
            Zero when the fleet is too small to measure or perfectly uniform.
    """

    panels: list[PanelPerformance]
    average_wh: float
    stdev_wh: float


async def flag_underperforming_panels(
    session: AsyncSession,
    system_id: int,
    start: date,
    end: date,
) -> FleetPerformance:
    """Rank every panel against its own fleet over a date window.

    Panels are compared to each other rather than to a nameplate rating, so
    shared conditions (weather, season, soiling) cancel out and what is left is
    the difference between panels.

    Args:
        session: Active async database session.
        system_id: System whose panels to analyze.
        start: First day of the window (inclusive).
        end: Last day of the window (inclusive).

    Returns:
        FleetPerformance with one entry per panel that reported in the window,
        ordered by serial number. Empty, with zeroed statistics, when no panel
        reported.
    """
    stmt = (
        select(
            PanelReading.panel_serial,
            func.sum(PanelReading.energy_wh).label("energy_wh"),
        )
        .where(
            PanelReading.system_id == system_id,
            PanelReading.day >= start,
            PanelReading.day <= end,
        )
        .group_by(PanelReading.panel_serial)
        .order_by(PanelReading.panel_serial)
    )
    rows = (await session.execute(stmt)).all()
    # SUM skips NULLs and yields NULL for a panel that stayed silent all window;
    # that panel produced nothing, which is exactly what the comparison needs.
    totals = [(serial, float(energy or 0)) for serial, energy in rows]
    if not totals:
        return FleetPerformance(panels=[], average_wh=0.0, stdev_wh=0.0)

    values = [energy for _, energy in totals]
    average = mean(values)
    # Population, not sample: these are every panel on the roof, not a draw
    # from a larger population.
    stdev = pstdev(values) if len(values) >= MIN_FLEET_SIZE else 0.0

    panels = []
    for serial, energy in totals:
        sigma = (energy - average) / stdev if stdev else None
        panels.append(
            PanelPerformance(
                panel_serial=serial,
                energy_wh=round(energy, 3),
                normalized_efficiency=(round(energy / average, 4) if average else 0.0),
                deviation_sigma=round(sigma, 3) if sigma is not None else None,
                is_underperforming=sigma is not None and sigma < -SIGMA_THRESHOLD,
            )
        )
    return FleetPerformance(
        panels=panels,
        average_wh=round(average, 3),
        stdev_wh=round(stdev, 3),
    )
