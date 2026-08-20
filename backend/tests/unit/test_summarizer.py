import math
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from helio.analytics import summarizer
from helio.analytics.degradation import estimate_lost_production
from helio.analytics.summarizer import (
    apply_expected_pr,
    build_daily_summary,
    build_monthly_summary,
    rebuild_all_summaries,
)
from helio.db.models import MonthlySummary, System


def _session_returning_days(days: list[date]) -> AsyncMock:
    """Build a mocked session whose SELECT returns `days`."""
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=days)))
        )
    )
    return session


@pytest.mark.asyncio
async def test_rebuild_all_summaries_covers_every_day_and_month(monkeypatch):
    """Each stored day is rebuilt once, and each month it belongs to once."""
    days = [date(2024, 4, 28), date(2024, 4, 29), date(2024, 5, 1)]
    daily = AsyncMock()
    monthly = AsyncMock()
    expected = AsyncMock()
    monkeypatch.setattr(summarizer, "build_daily_summary", daily)
    monkeypatch.setattr(summarizer, "build_monthly_summary", monthly)
    monkeypatch.setattr(summarizer, "apply_expected_pr", expected)

    result = await rebuild_all_summaries(_session_returning_days(days), MagicMock(id=1))

    assert result == (3, 2)
    assert [call.args[2] for call in daily.await_args_list] == days
    assert [call.args[2] for call in monthly.await_args_list] == [
        date(2024, 4, 1),
        date(2024, 5, 1),
    ]
    # Once for the whole series rather than once per month: the baseline needs
    # every month to exist before anything can be expected of any of them.
    expected.assert_awaited_once()


@pytest.mark.asyncio
async def test_rebuild_all_summaries_is_a_no_op_without_intervals(monkeypatch):
    """Nothing to aggregate must not write empty summaries."""
    daily = AsyncMock()
    monkeypatch.setattr(summarizer, "build_daily_summary", daily)

    result = await rebuild_all_summaries(_session_returning_days([]), MagicMock(id=1))

    assert result == (0, 0)
    daily.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_daily_summary_aggregates_correctly():
    """Test insert path: no existing row, session.add is called with correct values."""
    mock_session = AsyncMock()
    mock_intervals = [
        MagicMock(
            production_wh=Decimal("500"),
            interval_start=datetime(2024, 4, 28, 10, 0, tzinfo=UTC),
        ),
        MagicMock(
            production_wh=Decimal("800"),
            interval_start=datetime(2024, 4, 28, 12, 0, tzinfo=UTC),
        ),
        MagicMock(
            production_wh=Decimal("400"),
            interval_start=datetime(2024, 4, 28, 14, 0, tzinfo=UTC),
        ),
    ]

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: fetch intervals
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=mock_intervals))
                )
            )
        # Second call: upsert lookup — no existing row
        return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    result = await build_daily_summary(mock_session, system_id=1, day=date(2024, 4, 28))

    mock_session.add.assert_called_once()
    added_row = mock_session.add.call_args[0][0]
    assert added_row.production_kwh == pytest.approx(Decimal("1.700"), rel=1e-3)
    assert added_row.peak_power_w is not None
    assert result is added_row


@pytest.mark.asyncio
async def test_build_daily_summary_updates_existing_row():
    """Test update path: existing row found, attributes updated, add not called."""
    mock_session = AsyncMock()
    mock_intervals = [
        MagicMock(
            production_wh=Decimal("600"),
            interval_start=datetime(2024, 4, 28, 10, 0, tzinfo=UTC),
        ),
    ]

    existing_row = MagicMock()
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=mock_intervals))
                )
            )
        return MagicMock(scalar_one_or_none=MagicMock(return_value=existing_row))

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    result = await build_daily_summary(mock_session, system_id=1, day=date(2024, 4, 28))

    mock_session.add.assert_not_called()
    assert result is existing_row
    assert existing_row.production_kwh == Decimal(str(round(600 / 1000, 3)))
    assert existing_row.interval_count == 1
    assert existing_row.peak_power_w is not None
    assert existing_row.is_complete is not None


@pytest.mark.asyncio
async def test_build_monthly_summary_calculates_pr():
    """Test insert path: no existing row, session.add called with correct PR values."""
    mock_session = AsyncMock()

    daily_rows = [
        MagicMock(production_kwh=Decimal("30")),
        MagicMock(production_kwh=Decimal("35")),
    ]
    irradiance_rows = [
        MagicMock(poa_kwh_m2=Decimal("5.0")),
        MagicMock(poa_kwh_m2=Decimal("6.0")),
    ]

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Daily summaries query
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=daily_rows))
                )
            )
        if call_count == 2:
            # Irradiance query
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=irradiance_rows))
                )
            )
        # Third call: upsert lookup — no existing row
        return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_system = MagicMock(
        system_size_kw=Decimal("10"),
        install_date=date(2023, 1, 1),
        degradation_rate=Decimal("0.5"),
    )

    result = await build_monthly_summary(
        mock_session,
        system_id=1,
        month=date(2024, 4, 1),
        system=mock_system,
    )

    mock_session.add.assert_called_once()
    added_row = mock_session.add.call_args[0][0]
    assert added_row.production_kwh == pytest.approx(Decimal("65"), rel=1e-3)
    assert added_row.performance_ratio is not None
    assert 0 < float(added_row.performance_ratio) < 2
    assert result is added_row


@pytest.mark.asyncio
async def test_build_monthly_summary_updates_existing_row():
    """Test update path: existing monthly row found, attributes updated."""
    mock_session = AsyncMock()

    daily_rows = [MagicMock(production_kwh=Decimal("40"))]
    irradiance_rows = [MagicMock(poa_kwh_m2=Decimal("4.0"))]
    existing_row = MagicMock()

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=daily_rows))
                )
            )
        if call_count == 2:
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=irradiance_rows))
                )
            )
        return MagicMock(scalar_one_or_none=MagicMock(return_value=existing_row))

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_system = MagicMock(
        system_size_kw=Decimal("10"),
        install_date=date(2023, 1, 1),
        degradation_rate=Decimal("0.5"),
    )

    result = await build_monthly_summary(
        mock_session,
        system_id=1,
        month=date(2024, 4, 1),
        system=mock_system,
    )

    mock_session.add.assert_not_called()
    assert result is existing_row
    assert existing_row.production_kwh == Decimal("40")
    assert existing_row.performance_ratio is not None


INSTALL_DATE = date(2020, 1, 1)
DEGRADATION_RATE = 0.005
TRUE_BASELINE = 0.82


def _system_on_the_curve() -> MagicMock:
    """A system with no configured baseline, degrading at DEGRADATION_RATE."""
    system = MagicMock(spec=System)
    system.id = 1
    system.install_date = INSTALL_DATE
    system.degradation_rate = Decimal(str(DEGRADATION_RATE * 100))
    system.baseline_pr = None
    return system


def _healthy_months(count: int) -> list[MagicMock]:
    """`count` monthly rows whose PR follows the configured curve exactly.

    Built from the same (1 - rate) ** years shape the expected curve uses, and
    rounded the way the summarizer stores it, so a test can assert that a system
    tracking its own degradation is left alone.
    """
    rows = []
    for offset in range(count):
        month = date(INSTALL_DATE.year + offset // 12, offset % 12 + 1, 1)
        elapsed = (month - INSTALL_DATE).days / 365.25
        row = MagicMock(spec=MonthlySummary)
        row.month = month
        row.production_kwh = Decimal("900")
        row.performance_ratio = Decimal(
            str(round(TRUE_BASELINE * (1 - DEGRADATION_RATE) ** elapsed, 4))
        )
        row.expected_pr = None
        row.is_anomaly = False
        row.anomaly_reason = None
        rows.append(row)
    return rows


def _series_session(rows: list[MagicMock], window: list[MagicMock] | None = None):
    """A session answering both selects apply_expected_pr issues.

    The baseline's first-year window carries a LIMIT and the full-series query
    does not, so the two are told apart by the compiled statement. That lets a
    test hand the baseline a clean year while the series under test also holds
    the month being judged.
    """
    session = AsyncMock()

    async def execute(stmt):
        chosen = window if window is not None and "LIMIT" in str(stmt) else rows
        return MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=chosen))
            )
        )

    session.execute = execute
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_apply_expected_pr_flags_nothing_on_a_system_tracking_its_curve():
    """AC1: a system degrading exactly as configured is not an anomaly, ever.

    This is the whole bug: against a baseline of 1.0 every one of these months
    was flagged, because a real array never converts all of its irradiance.
    """
    rows = _healthy_months(24)

    flagged = await apply_expected_pr(_series_session(rows), _system_on_the_curve())

    assert flagged == 0
    assert not any(row.is_anomaly for row in rows)
    assert all(row.anomaly_reason is None for row in rows)
    # The baseline is the system's own output, so expected lands on the measured
    # ratio rather than a point twenty percent above it.
    for row in rows:
        assert float(row.expected_pr) == pytest.approx(
            float(row.performance_ratio), abs=0.002
        )


@pytest.mark.asyncio
async def test_lost_production_is_negligible_on_a_system_tracking_its_curve():
    """AC2: the dollar figure follows the flags, so it has to collapse too."""
    rows = _healthy_months(24)
    session = _series_session(rows)
    await apply_expected_pr(session, _system_on_the_curve())

    lost = await estimate_lost_production(session, system_id=1, rate_per_kwh=0.15)

    # 24 months at 900 kWh is 21600 kWh of production; anything the rounding
    # leaves behind is a rounding artefact, not a loss worth pricing.
    assert lost["lost_kwh"] < 21600 * 0.001


@pytest.mark.asyncio
async def test_apply_expected_pr_still_flags_a_month_below_the_measured_trend():
    """AC3: #18's flag has to keep firing on a month that really did fall short."""
    window = _healthy_months(12)
    bad = MagicMock(spec=MonthlySummary)
    bad.month = date(2021, 1, 1)
    bad.production_kwh = Decimal("900")
    bad.performance_ratio = Decimal("0.7400")
    bad.expected_pr = None
    bad.is_anomaly = False
    bad.anomaly_reason = None

    flagged = await apply_expected_pr(
        _series_session([*window, bad], window=window), _system_on_the_curve()
    )

    assert flagged == 1
    assert bad.is_anomaly is True
    assert "below expected" in bad.anomaly_reason
    assert not any(row.is_anomaly for row in window)


@pytest.mark.asyncio
async def test_apply_expected_pr_expects_nothing_below_a_full_year():
    """AC4: the documented no-baseline case, rather than an invented standard."""
    rows = _healthy_months(11)

    flagged = await apply_expected_pr(_series_session(rows), _system_on_the_curve())

    assert flagged == 0
    assert all(row.expected_pr is None for row in rows)
    assert all(row.is_anomaly is False for row in rows)


@pytest.mark.asyncio
async def test_apply_expected_pr_clears_a_flag_a_previous_run_left_behind():
    """A rebuild has to be able to unflag: the old baseline flagged everything."""
    rows = _healthy_months(12)
    for row in rows:
        row.is_anomaly = True
        row.anomaly_reason = "PR 82.0% is 18.0% below expected 100.0%"

    flagged = await apply_expected_pr(_series_session(rows), _system_on_the_curve())

    assert flagged == 0
    assert all(row.anomaly_reason is None for row in rows)


@pytest.mark.asyncio
async def test_apply_expected_pr_expects_a_month_that_has_no_ratio_of_its_own():
    """A month with no irradiance still has a standard; it just cannot be judged."""
    window = _healthy_months(12)
    dark = _healthy_months(13)[-1]
    # The baseline query skips months without a ratio, so this one is outside the
    # window rather than in it.
    dark.performance_ratio = None

    flagged = await apply_expected_pr(
        _series_session([*window, dark], window=window), _system_on_the_curve()
    )

    assert flagged == 0
    assert dark.expected_pr is not None
    assert dark.is_anomaly is False


@pytest.mark.asyncio
async def test_apply_expected_pr_uses_a_configured_baseline_over_the_history():
    """A commissioning figure the system never reaches flags every month."""
    rows = _healthy_months(12)
    system = _system_on_the_curve()
    system.baseline_pr = Decimal("0.9500")

    flagged = await apply_expected_pr(_series_session(rows), system)

    assert flagged == len(rows)


# A seasonal swing of this size is ordinary rather than extreme: cell temperature
# alone moves PR several points between midwinter and midsummer, and the whole
# point of #76 is that a fixed 1.5 point threshold cannot survive it.
SEASONAL_AMPLITUDE = 0.04


def _season(month: int) -> float:
    """The share of the annual mean this calendar month normally returns.

    A cosine trough in July and peak in January, which averages to 1.0 over a
    full year, so a system following it exactly has no year-round loss to find.
    """
    return 1 - SEASONAL_AMPLITUDE * math.cos(2 * math.pi * (month - 7) / 12)


def _seasonal_months(count: int) -> list[MagicMock]:
    """`count` monthly rows following the degradation curve and the season.

    Nothing is wrong with this system: it degrades exactly as configured, and
    its summers are lower than its winters the way every real array's are.
    """
    rows = []
    for offset in range(count):
        month = date(INSTALL_DATE.year + offset // 12, offset % 12 + 1, 1)
        elapsed = (month - INSTALL_DATE).days / 365.25
        row = MagicMock(spec=MonthlySummary)
        row.month = month
        row.production_kwh = Decimal("900")
        row.performance_ratio = Decimal(
            str(
                round(
                    TRUE_BASELINE
                    * (1 - DEGRADATION_RATE) ** elapsed
                    * _season(month.month),
                    4,
                )
            )
        )
        row.expected_pr = None
        row.is_anomaly = False
        row.anomaly_reason = None
        rows.append(row)
    return rows


@pytest.mark.asyncio
async def test_apply_expected_pr_flags_no_month_on_a_healthy_seasonal_system():
    """AC1: an ordinary summer dip on a sound array is not an anomaly.

    Against the annual mean these months are flagged every year, which is the
    bug: the mean sits above every summer by construction.
    """
    rows = _seasonal_months(36)

    flagged = await apply_expected_pr(
        _series_session(rows, window=rows[:12]), _system_on_the_curve()
    )

    assert flagged == 0
    assert not any(row.is_anomaly for row in rows)
    # The expected curve now follows the season rather than cutting across it,
    # so it lands on each month's own measured ratio.
    for row in rows:
        assert float(row.expected_pr) == pytest.approx(
            float(row.performance_ratio), abs=0.005
        )


@pytest.mark.asyncio
async def test_apply_expected_pr_flags_a_month_that_missed_its_own_season():
    """AC2: a real shortfall is still caught, and the reason names the season."""
    rows = _seasonal_months(36)
    # The third July, five points below what this system's Julys return. That is
    # still well above its own January, so only a seasonal expectation finds it.
    bad = next(row for row in rows if row.month == date(2022, 7, 1))
    bad.performance_ratio = Decimal(str(round(float(bad.performance_ratio) - 0.05, 4)))

    flagged = await apply_expected_pr(
        _series_session(rows, window=rows[:12]), _system_on_the_curve()
    )

    assert flagged == 1
    assert bad.is_anomaly is True
    assert "expected for July" in bad.anomaly_reason
    assert not any(row.is_anomaly for row in rows if row is not bad)


@pytest.mark.asyncio
async def test_apply_expected_pr_invents_no_season_from_a_single_year():
    """AC3: below two measurements of a month there is no shape worth trusting.

    Asserted as the shape of the expected curve rather than as a flag count: a
    pure degradation curve only ever falls, so an expected series that never
    rises is proof no season was read into one year of weather.
    """
    rows = _seasonal_months(18)

    await apply_expected_pr(
        _series_session(rows, window=rows[:12]), _system_on_the_curve()
    )

    expected = [float(row.expected_pr) for row in rows]
    assert all(later <= earlier for earlier, later in zip(expected, expected[1:]))


@pytest.mark.asyncio
async def test_apply_expected_pr_keeps_a_year_round_loss_out_of_the_season():
    """A uniform shortfall must survive the correction, or it hides real faults.

    The factors are normalised to average 1.0 precisely so that a system losing
    output in every month has nothing to redistribute the loss into.
    """
    rows = _seasonal_months(36)
    for row in rows[12:]:
        row.performance_ratio = Decimal(
            str(round(float(row.performance_ratio) - 0.03, 4))
        )

    flagged = await apply_expected_pr(
        _series_session(rows, window=rows[:12]), _system_on_the_curve()
    )

    assert flagged > 0
