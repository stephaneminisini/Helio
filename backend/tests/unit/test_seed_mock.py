import random
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from statistics import mean, pstdev
from unittest.mock import AsyncMock, MagicMock

import pytest

from helio.analytics.anomaly import MIN_FLEET_SIZE, SIGMA_THRESHOLD
from helio.db import seed_mock as seed_module
from helio.db.seed_mock import (
    CHUNK_ROWS,
    INTERVALS_PER_DAY,
    PANEL_WATTS,
    SOURCE,
    RealDataError,
    _day_profile,
    _elapsed_intervals,
    _interval_rows,
    _interval_weights,
    _panel_factors,
    _panel_rows,
    _seasonal_factor,
    seed_mock,
)

PANEL_COUNT = 24


def _session(unseeded: int = 0, unseeded_panels: int = 0) -> AsyncMock:
    """A session whose two guard queries report pre-existing rows.

    execute() is awaitable but the Result it yields is not, so the result has to
    be a plain MagicMock or scalar_one() hands back a coroutine. Only the guards
    call scalar_one, so the two counts can be served in the order they are asked
    for: intervals first, then panel readings.
    """
    session = AsyncMock()
    session.execute.return_value = MagicMock(
        scalar_one=MagicMock(side_effect=[unseeded, unseeded_panels])
    )
    return session


def _system(**overrides) -> MagicMock:
    """Build a stand-in system with plausible defaults."""
    defaults = {
        "id": 1,
        "system_size_kw": Decimal("10"),
        "latitude": Decimal("45.5"),
        "install_date": date(2020, 1, 1),
        "degradation_rate": Decimal("0.5"),
        "panel_count": PANEL_COUNT,
    }
    return MagicMock(**{**defaults, **overrides})


def test_seasonal_factor_peaks_in_summer_for_northern_sites():
    june = _seasonal_factor(date(2024, 6, 21), latitude=45.0)
    december = _seasonal_factor(date(2024, 12, 21), latitude=45.0)

    assert june > december
    assert 0.29 < december < june <= 1.0


def test_seasonal_factor_flips_below_the_equator():
    june = _seasonal_factor(date(2024, 6, 21), latitude=-33.0)
    december = _seasonal_factor(date(2024, 12, 21), latitude=-33.0)

    assert december > june


def test_interval_weights_are_a_normalised_daytime_curve():
    weights = _interval_weights(daylight_hours=12.0)

    assert len(weights) == INTERVALS_PER_DAY
    assert sum(weights) == pytest.approx(1.0)
    assert weights[0] == 0.0  # midnight
    assert weights[INTERVALS_PER_DAY // 2] > weights[INTERVALS_PER_DAY // 4]


def test_interval_weights_never_leave_the_calendar_day():
    """A window that crossed midnight would land energy in the wrong summary."""
    weights = _interval_weights(daylight_hours=16.0)

    assert weights[0] == 0.0
    assert weights[-1] == 0.0


def test_interval_rows_distribute_the_whole_day_inside_that_day():
    day = date(2024, 6, 21)
    rows = _interval_rows(1, day, kwh=40.0, weights=_interval_weights(14.0))

    assert len(rows) == INTERVALS_PER_DAY
    assert sum(row["production_wh"] for row in rows) == pytest.approx(40_000, rel=1e-6)
    assert min(row["interval_start"] for row in rows) == datetime(
        2024, 6, 21, tzinfo=UTC
    )
    assert max(row["interval_start"] for row in rows) < datetime(
        2024, 6, 22, tzinfo=UTC
    )


def test_day_profile_scales_with_system_size():
    rng_args = (date(2024, 6, 21), _system(system_size_kw=Decimal("5")))
    _, small_kwh, _ = _day_profile(*rng_args, random.Random(1))
    _, large_kwh, _ = _day_profile(
        date(2024, 6, 21), _system(system_size_kw=Decimal("20")), random.Random(1)
    )

    assert large_kwh == pytest.approx(small_kwh * 4)


def test_day_profile_degrades_with_system_age():
    """Production must decay at the system's own rate so PR stays believable."""
    system = _system(degradation_rate=Decimal("2.0"))
    _, first_year, _ = _day_profile(date(2020, 6, 21), system, random.Random(7))
    _, tenth_year, _ = _day_profile(date(2030, 6, 21), system, random.Random(7))

    assert tenth_year < first_year * 0.85


def test_day_profile_is_deterministic_for_a_given_seed():
    system = _system()
    first = _day_profile(date(2024, 3, 1), system, random.Random(42))
    second = _day_profile(date(2024, 3, 1), system, random.Random(42))

    assert first == second


@pytest.fixture
def no_rebuild(monkeypatch):
    """Stub the summary rebuild so seed tests stay in-memory."""
    rebuild = AsyncMock(return_value=(0, 0))
    monkeypatch.setattr(seed_module, "rebuild_all_summaries", rebuild)
    return rebuild


def _upserted(session: AsyncMock, table: str) -> list[dict]:
    """Every row the seeder bulk-upserted into `table`, across all its chunks.

    The guard queries and the upserts go through the same mock, and only an
    upsert passes its rows as a second argument, so dispatching on the compiled
    statement keeps these assertions independent of how many guard queries run
    first and of the order the tables are written in.
    """
    return [
        row
        for call in session.execute.await_args_list
        if len(call.args) > 1 and f"INTO {table}" in str(call.args[0])
        for row in call.args[1]
    ]


async def test_seed_mock_writes_a_full_year_of_intervals(no_rebuild, midday):
    session = _session()

    intervals, irradiance, panels = await seed_mock(session, _system(), years=1)

    assert irradiance == 365
    # 364 whole days plus today, cut off at the current interval.
    assert intervals == 364 * INTERVALS_PER_DAY + midday
    # AC1: one row per panel per seeded day, today included.
    assert panels == 365 * PANEL_COUNT
    no_rebuild.assert_awaited_once()


async def test_seed_mock_upserts_in_chunks_and_commits(no_rebuild, midday):
    session = _session()

    await seed_mock(session, _system(), years=1)

    # Two guard queries, then each table's rows at CHUNK_ROWS per chunk.
    def chunks(rows: int) -> int:
        return -(-rows // CHUNK_ROWS)

    interval_chunks = chunks(364 * INTERVALS_PER_DAY + midday)
    panel_chunks = chunks(len(_upserted(session, "panel_readings")))
    assert session.execute.await_count == 2 + interval_chunks + 1 + panel_chunks
    assert session.commit.await_count == 3


async def test_seed_mock_tags_irradiance_with_the_mock_source(no_rebuild, midday):
    session = _session()

    await seed_mock(session, _system(), years=1)

    irradiance_rows = _upserted(session, "irradiance")
    assert {row["source"] for row in irradiance_rows} == {SOURCE}
    assert all(row["poa_kwh_m2"] > 0 for row in irradiance_rows)


async def test_seed_mock_includes_today(no_rebuild):
    """AC1: stopping at yesterday left the Overview's headline card on 0.0 kWh."""
    session = _session()

    await seed_mock(session, _system(), years=1)

    seeded_days = {row["day"] for row in _upserted(session, "irradiance")}
    assert max(seeded_days) == date.today()


@pytest.fixture
def midday(monkeypatch):
    """Pin the cutoff to mid-afternoon, so a partial day is deterministic.

    The real clock would make these assertions depend on the hour CI happens to
    run at, including a pre-dawn run where today produces nothing at all.
    """
    cutoff = 60  # 15:00 UTC, past the seeder's 13:00 solar noon
    monkeypatch.setattr(seed_module, "_elapsed_intervals", lambda now: cutoff)
    return cutoff


async def test_seed_mock_truncates_today_at_the_last_closed_interval(
    no_rebuild, midday
):
    """A day in progress must carry only the energy already produced."""
    session = _session()

    await seed_mock(session, _system(), years=1)

    rows = _upserted(session, "energy_intervals")
    by_day = Counter(row["interval_start"].date() for row in rows)
    assert by_day[date.today()] == midday
    assert by_day[date.today() - timedelta(days=1)] == INTERVALS_PER_DAY


def test_elapsed_intervals_counts_closed_windows_only():
    midnight = datetime(2024, 6, 21, tzinfo=UTC)

    assert _elapsed_intervals(midnight) == 0
    # 15 minutes in, the first window has just closed; at 14 it has not.
    assert _elapsed_intervals(midnight + timedelta(minutes=15)) == 1
    assert _elapsed_intervals(midnight + timedelta(minutes=14)) == 0
    assert _elapsed_intervals(midnight + timedelta(hours=12)) == 48
    assert (
        _elapsed_intervals(midnight + timedelta(hours=24, seconds=-1))
        == INTERVALS_PER_DAY - 1
    )


def test_interval_rows_stop_at_the_limit():
    rows = _interval_rows(
        1, date(2024, 6, 21), kwh=40.0, weights=_interval_weights(14.0), limit=40
    )

    assert len(rows) == 40
    # Not renormalised: a truncated day is worth less than a whole one, which is
    # what a live install would have recorded by that hour.
    assert sum(row["production_wh"] for row in rows) < 40_000


async def test_seed_mock_keeps_todays_implied_pr_equal_to_a_whole_days(
    no_rebuild, midday
):
    """A whole day of sun over part of a day's output reads as a real PR drop.

    The monthly performance ratio divides summed production by summed irradiance,
    and the anomaly threshold is a 1.5 percent shortfall, so a today whose
    irradiance covered more hours than its production would flag the current
    month.
    """
    session = _session()
    system = _system()

    await seed_mock(session, system, years=1)

    irradiance = {
        row["day"]: row["poa_kwh_m2"] for row in _upserted(session, "irradiance")
    }
    production: dict[date, float] = {}
    for row in _upserted(session, "energy_intervals"):
        day = row["interval_start"].date()
        production[day] = production.get(day, 0.0) + row["production_wh"]

    size_kw = float(system.system_size_kw)

    def implied_pr(day):
        return production[day] / 1000 / (irradiance[day] * size_kw)

    today_pr = implied_pr(date.today())
    yesterday_pr = implied_pr(date.today() - timedelta(days=1))

    assert today_pr == pytest.approx(yesterday_pr, rel=1e-3)


async def test_seed_mock_tops_up_a_partial_day_rather_than_duplicating_it(
    no_rebuild, midday
):
    """AC3: a second run later in the day must complete today, not double it.

    Every interval is keyed on its own start, so re-running rewrites the ones
    already stored with the same values and inserts only the newly elapsed ones.
    """
    session = _session()

    await seed_mock(session, _system(), years=1)

    interval_upsert = next(
        str(call.args[0])
        for call in session.execute.await_args_list
        if len(call.args) > 1 and "INTO energy_intervals" in str(call.args[0])
    )
    assert "ON CONFLICT (system_id, interval_start) DO UPDATE" in interval_upsert
    assert "production_wh" in interval_upsert.split("DO UPDATE")[1]


async def test_seed_mock_refuses_a_database_holding_real_production_data(no_rebuild):
    """AC4: real measurements are unrecoverable, so overwriting them is refused."""
    session = _session(unseeded=4321)

    with pytest.raises(RealDataError, match="4321 production intervals"):
        await seed_mock(session, _system(), years=1)

    session.commit.assert_not_awaited()
    no_rebuild.assert_not_awaited()


async def test_seed_mock_refuses_a_database_holding_real_panel_readings(no_rebuild):
    """AC4: the guard has to cover the table this seeder has started writing.

    Per-panel readings are as unrecoverable as intervals, and an install could
    hold them without holding raw intervals, so the interval guard alone would
    let a live roof be overwritten.
    """
    session = _session(unseeded=0, unseeded_panels=99)

    with pytest.raises(RealDataError, match="99 panel readings"):
        await seed_mock(session, _system(), years=1)

    session.commit.assert_not_awaited()
    no_rebuild.assert_not_awaited()


async def test_seed_mock_counts_only_days_it_did_not_seed_itself(no_rebuild, midday):
    """Reseeding has to stay free, so mock-sourced days are excluded.

    Both measurement tables are guarded, and both exclusions have to key off the
    mock irradiance rows or a second run would refuse its own data.
    """
    session = _session()

    await seed_mock(session, _system(), years=1)

    guards = [
        str(call.args[0])
        for call in session.execute.await_args_list
        if len(call.args) == 1 and "count(*)" in str(call.args[0])
    ]
    assert [
        table
        for table in ("energy_intervals", "panel_readings")
        if any(f"FROM {table}" in guard for guard in guards)
    ] == ["energy_intervals", "panel_readings"]
    for guard in guards:
        assert "NOT IN (SELECT irradiance.day" in guard
        assert "irradiance.source =" in guard


async def test_seed_mock_gives_every_panel_a_row_on_every_day(no_rebuild, midday):
    """AC1/AC2: a gap in the fleet leaves the heatmap on its empty state."""
    session = _session()

    await seed_mock(session, _system(), years=1)

    rows = _upserted(session, "panel_readings")
    per_day = Counter(row["day"] for row in rows)
    assert len(per_day) == 365
    assert set(per_day.values()) == {PANEL_COUNT}
    # Today is only part of a day but still gets its full set of panels, so the
    # heatmap's most recent column is not a hole.
    assert per_day[date.today()] == PANEL_COUNT
    assert {row["panel_serial"] for row in rows if row["day"] == date.today()} == {
        f"MOCK{index:04d}" for index in range(1, PANEL_COUNT + 1)
    }


async def test_seed_mock_panel_readings_sum_to_their_days_production(
    no_rebuild, midday
):
    """The Panels tab and the Overview must not disagree about a day.

    Today matters most: its intervals stop at the current one, so the panels have
    to split the part-day actually produced rather than a whole day's output.
    """
    session = _session()

    await seed_mock(session, _system(), years=1)

    intervals = Counter()
    for row in _upserted(session, "energy_intervals"):
        intervals[row["interval_start"].date()] += row["production_wh"]
    panels = Counter()
    for row in _upserted(session, "panel_readings"):
        panels[row["day"]] += row["energy_wh"]

    for day in (date.today(), date.today() - timedelta(days=1)):
        assert panels[day] == pytest.approx(intervals[day], rel=1e-6)


async def test_seed_mock_leaves_one_panel_below_the_anomaly_threshold(
    no_rebuild, midday
):
    """AC3: a roof where every panel is average demonstrates nothing.

    Mirrors the arithmetic in the anomaly detector, a population sigma over each
    panel's window total, because that is what the Panels tab actually flags on.
    """
    session = _session()

    await seed_mock(session, _system(), years=1)

    totals = Counter()
    for row in _upserted(session, "panel_readings"):
        totals[row["panel_serial"]] += row["energy_wh"]
    values = list(totals.values())
    assert len(values) >= MIN_FLEET_SIZE
    average, spread = mean(values), pstdev(values)
    sigmas = [(value - average) / spread for value in values]

    assert min(sigmas) < -SIGMA_THRESHOLD
    # Exactly one: ordinary scatter between healthy modules must stay unflagged,
    # or the heatmap cries wolf and the flag stops meaning anything.
    assert sum(1 for sigma in sigmas if sigma < -SIGMA_THRESHOLD) == 1


async def test_seed_mock_keeps_the_same_panel_weak_across_the_whole_range(
    no_rebuild, midday
):
    """A panel that is weak on alternate days is noise, not an outlier.

    The per-panel comparison sums a window, so a fleet reshuffled per day would
    average out and nothing would ever be flagged.
    """
    session = _session()

    await seed_mock(session, _system(), years=1)

    by_day: dict[date, dict[str, float]] = {}
    for row in _upserted(session, "panel_readings"):
        by_day.setdefault(row["day"], {})[row["panel_serial"]] = row["energy_wh"]
    # Shares rather than raw energy, since each day produced a different total.
    weakest = {
        day: min(panels, key=panels.get)
        for day, panels in by_day.items()
        if sum(panels.values()) > 0
    }

    assert len(set(weakest.values())) == 1


async def test_seed_mock_upserts_panel_readings_on_their_own_key(no_rebuild, midday):
    """Reseeding must rewrite a panel's day, not add a second row for it."""
    session = _session()

    await seed_mock(session, _system(), years=1)

    panel_upsert = next(
        str(call.args[0])
        for call in session.execute.await_args_list
        if len(call.args) > 1 and "INTO panel_readings" in str(call.args[0])
    )
    assert "ON CONFLICT (system_id, panel_serial, day) DO UPDATE" in panel_upsert
    assert "energy_wh" in panel_upsert.split("DO UPDATE")[1]


def test_panel_rows_split_the_whole_day_across_the_fleet():
    factors = [1.0, 1.0, 0.5]
    rows = _panel_rows(1, date(2024, 6, 21), kwh=40.0, factors=factors)

    assert len(rows) == 3
    assert sum(row["energy_wh"] for row in rows) == pytest.approx(40_000, rel=1e-6)
    assert rows[-1]["energy_wh"] == pytest.approx(rows[0]["energy_wh"] / 2, rel=1e-6)


def test_panel_rows_survive_a_day_that_produced_nothing():
    """Seeding before dawn still has to write today, or AC1's column is missing."""
    rows = _panel_rows(1, date(2024, 6, 21), kwh=0.0, factors=[1.0, 1.0, 0.5])

    assert [row["energy_wh"] for row in rows] == [0.0, 0.0, 0.0]


def test_panel_factors_size_a_fleet_when_the_panel_count_is_unknown():
    """An install that never recorded its panel count still gets a roof."""
    factors = _panel_factors(_system(panel_count=None), random.Random(42))

    assert len(factors) == round(10 * 1000 / PANEL_WATTS)


def test_panel_factors_never_fall_below_a_usable_fleet_size():
    """Below MIN_FLEET_SIZE the sigma is degenerate and nothing can be flagged."""
    tiny = _system(panel_count=None, system_size_kw=Decimal("0.2"))

    assert len(_panel_factors(tiny, random.Random(42))) == MIN_FLEET_SIZE


def test_panel_factors_are_deterministic_for_a_given_seed():
    """A reseed must not turn the weak panel into a healthy one."""
    assert _panel_factors(_system(), random.Random(7)) == _panel_factors(
        _system(), random.Random(7)
    )
