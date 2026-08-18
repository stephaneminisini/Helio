import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from helio.db import seed_mock as seed_module
from helio.db.seed_mock import (
    CHUNK_ROWS,
    INTERVALS_PER_DAY,
    SOURCE,
    RealDataError,
    _day_profile,
    _elapsed_intervals,
    _interval_rows,
    _interval_weights,
    _seasonal_factor,
    seed_mock,
)


def _session(unseeded: int = 0) -> AsyncMock:
    """A session whose guard query reports `unseeded` pre-existing intervals.

    execute() is awaitable but the Result it yields is not, so the result has to
    be a plain MagicMock or scalar_one() hands back a coroutine.
    """
    session = AsyncMock()
    session.execute.return_value = MagicMock(
        scalar_one=MagicMock(return_value=unseeded)
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


async def test_seed_mock_writes_a_full_year_of_intervals(no_rebuild, midday):
    session = _session()

    intervals, irradiance = await seed_mock(session, _system(), years=1)

    assert irradiance == 365
    # 364 whole days plus today, cut off at the current interval.
    assert intervals == 364 * INTERVALS_PER_DAY + midday
    no_rebuild.assert_awaited_once()


async def test_seed_mock_upserts_in_chunks_and_commits(no_rebuild, midday):
    session = _session()

    await seed_mock(session, _system(), years=1)

    # The guard query, then the interval rows at CHUNK_ROWS per chunk, then one
    # chunk of irradiance.
    interval_rows = 364 * INTERVALS_PER_DAY + midday
    expected_chunks = -(-interval_rows // CHUNK_ROWS)
    assert session.execute.await_count == 1 + expected_chunks + 1
    assert session.commit.await_count == 2


async def test_seed_mock_tags_irradiance_with_the_mock_source(no_rebuild, midday):
    session = _session()

    await seed_mock(session, _system(), years=1)

    irradiance_rows = session.execute.await_args_list[-1].args[1]
    assert {row["source"] for row in irradiance_rows} == {SOURCE}
    assert all(row["poa_kwh_m2"] > 0 for row in irradiance_rows)


async def test_seed_mock_includes_today(no_rebuild):
    """AC1: stopping at yesterday left the Overview's headline card on 0.0 kWh."""
    session = _session()

    await seed_mock(session, _system(), years=1)

    seeded_days = {row["day"] for row in session.execute.await_args_list[-1].args[1]}
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

    todays = [
        row
        for call in session.execute.await_args_list[1:-1]
        for row in call.args[1]
        if row["interval_start"].date() == date.today()
    ]
    assert len(todays) == midday
    yesterday = [
        row
        for call in session.execute.await_args_list[1:-1]
        for row in call.args[1]
        if row["interval_start"].date() == date.today() - timedelta(days=1)
    ]
    assert len(yesterday) == INTERVALS_PER_DAY


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
        row["day"]: row["poa_kwh_m2"]
        for row in session.execute.await_args_list[-1].args[1]
    }
    production = {}
    for call in session.execute.await_args_list[1:-1]:
        for row in call.args[1]:
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

    interval_upsert = str(session.execute.await_args_list[1].args[0])
    assert "ON CONFLICT (system_id, interval_start) DO UPDATE" in interval_upsert
    assert "production_wh" in interval_upsert.split("DO UPDATE")[1]


async def test_seed_mock_refuses_a_database_holding_real_production_data(no_rebuild):
    """AC4: real measurements are unrecoverable, so overwriting them is refused."""
    session = _session(unseeded=4321)

    with pytest.raises(RealDataError, match="4321"):
        await seed_mock(session, _system(), years=1)

    session.commit.assert_not_awaited()
    no_rebuild.assert_not_awaited()


async def test_seed_mock_counts_only_days_it_did_not_seed_itself(no_rebuild):
    """AC3 needs reseeding to stay free, so mock-sourced days are excluded."""
    session = _session()

    await seed_mock(session, _system(), years=1)

    guard_query = str(session.execute.await_args_list[0].args[0])
    assert "count(*)" in guard_query
    assert "FROM energy_intervals" in guard_query
    assert "NOT IN (SELECT irradiance.day" in guard_query
    assert "irradiance.source =" in guard_query
