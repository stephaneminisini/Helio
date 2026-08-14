import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from helio.db import seed_mock as seed_module
from helio.db.seed_mock import (
    INTERVALS_PER_DAY,
    SOURCE,
    _day_profile,
    _interval_rows,
    _interval_weights,
    _seasonal_factor,
    seed_mock,
)


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


async def test_seed_mock_writes_a_full_year_of_intervals(no_rebuild):
    session = AsyncMock()

    intervals, irradiance = await seed_mock(session, _system(), years=1)

    assert irradiance == 365
    assert intervals == 365 * INTERVALS_PER_DAY
    no_rebuild.assert_awaited_once()


async def test_seed_mock_upserts_in_chunks_and_commits(no_rebuild):
    session = AsyncMock()

    await seed_mock(session, _system(), years=1)

    # 35040 interval rows at 2000 per chunk, plus one chunk of irradiance.
    assert session.execute.await_count == 19
    assert session.commit.await_count == 2


async def test_seed_mock_tags_irradiance_with_the_mock_source(no_rebuild):
    session = AsyncMock()

    await seed_mock(session, _system(), years=1)

    irradiance_rows = session.execute.await_args_list[-1].args[1]
    assert {row["source"] for row in irradiance_rows} == {SOURCE}
    assert all(row["poa_kwh_m2"] > 0 for row in irradiance_rows)


async def test_seed_mock_stops_at_yesterday(no_rebuild):
    """Seeding today would produce a partial day that reads as a production drop."""
    session = AsyncMock()

    await seed_mock(session, _system(), years=1)

    seeded_days = {row["day"] for row in session.execute.await_args_list[-1].args[1]}
    assert max(seeded_days) == date.today() - timedelta(days=1)
