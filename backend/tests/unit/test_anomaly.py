from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from helio.analytics.anomaly import flag_underperforming_panels

WINDOW_START = date(2024, 4, 1)
WINDOW_END = date(2024, 4, 30)


def _session(rows: list[tuple[str, Decimal | None]]) -> AsyncMock:
    """Mock session whose grouped panel query returns (serial, sum) rows."""
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(all=MagicMock(return_value=rows))
    )
    return session


def _fleet(*totals: int | None) -> list[tuple[str, Decimal | None]]:
    """Name a panel per total, so tests only state the production spread."""
    return [
        (f"panel-{index}", None if total is None else Decimal(total))
        for index, total in enumerate(totals)
    ]


@pytest.mark.asyncio
async def test_flags_only_the_panel_more_than_two_sigma_below_the_fleet():
    """AC1: five healthy panels and one at 40 percent puts it past -2 sigma."""
    session = _session(_fleet(100, 100, 100, 100, 100, 40))

    fleet = await flag_underperforming_panels(session, 1, WINDOW_START, WINDOW_END)

    flagged = [panel.panel_serial for panel in fleet.panels if panel.is_underperforming]
    assert flagged == ["panel-5"]
    outlier = fleet.panels[-1]
    assert outlier.deviation_sigma == pytest.approx(-2.236, abs=1e-3)
    assert outlier.normalized_efficiency == pytest.approx(0.4444, abs=1e-4)


@pytest.mark.asyncio
async def test_flags_nothing_when_the_fleet_is_evenly_matched():
    """AC2: ordinary panel-to-panel scatter is not an anomaly."""
    session = _session(_fleet(100, 95, 105, 100))

    fleet = await flag_underperforming_panels(session, 1, WINDOW_START, WINDOW_END)

    assert [panel.is_underperforming for panel in fleet.panels] == [False] * 4
    assert fleet.average_wh == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_reports_a_two_panel_fleet_without_measuring_its_spread():
    """AC3: with two panels every spread is one sigma, so the flag is unusable."""
    session = _session(_fleet(100, 10))

    fleet = await flag_underperforming_panels(session, 1, WINDOW_START, WINDOW_END)

    assert [panel.panel_serial for panel in fleet.panels] == ["panel-0", "panel-1"]
    assert [panel.deviation_sigma for panel in fleet.panels] == [None, None]
    assert [panel.is_underperforming for panel in fleet.panels] == [False, False]
    assert fleet.stdev_wh == 0.0


@pytest.mark.asyncio
async def test_flags_nothing_when_every_panel_produced_the_same():
    """A zero spread must not become a division by zero."""
    session = _session(_fleet(100, 100, 100))

    fleet = await flag_underperforming_panels(session, 1, WINDOW_START, WINDOW_END)

    assert fleet.stdev_wh == 0.0
    assert [panel.deviation_sigma for panel in fleet.panels] == [None] * 3
    assert [panel.normalized_efficiency for panel in fleet.panels] == [1.0] * 3


@pytest.mark.asyncio
async def test_counts_a_silent_panel_as_zero_rather_than_dropping_it():
    """A panel that reported no intervals produced nothing, which is the point."""
    session = _session(_fleet(100, 100, None))

    fleet = await flag_underperforming_panels(session, 1, WINDOW_START, WINDOW_END)

    assert [panel.energy_wh for panel in fleet.panels] == [100.0, 100.0, 0.0]
    assert fleet.panels[-1].normalized_efficiency == 0.0


@pytest.mark.asyncio
async def test_returns_zeroed_statistics_for_a_fleet_with_no_readings():
    session = _session([])

    fleet = await flag_underperforming_panels(session, 1, WINDOW_START, WINDOW_END)

    assert fleet.panels == []
    assert (fleet.average_wh, fleet.stdev_wh) == (0.0, 0.0)
