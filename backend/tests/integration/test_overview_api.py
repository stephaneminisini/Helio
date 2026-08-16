from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from helio.api.main import app
from helio.api.routes import overview as overview_route
from helio.db.models import System
from helio.db.session import get_db
from helio.ingestion.enphase_client import CurrentProduction


def _fake_db(
    daily: dict[date, float], install_date: date = date(2020, 1, 1)
) -> AsyncMock:
    """Serve the overview queries from an in-memory day to kWh mapping.

    The route's reads carry their meaning entirely in their SQL, so dispatching
    on the compiled statement keeps this fake indifferent to the order they
    happen to run in. Executed statements are recorded on `session.statements`
    so a test can assert which window was queried.
    """
    system = MagicMock(spec=System)
    system.id = 1
    system.install_date = install_date
    statements: list[tuple[str, dict]] = []

    async def execute(stmt):
        sql = str(stmt)
        params = stmt.compile().params
        statements.append((sql, params))
        if "FROM systems" in sql:
            return MagicMock(scalar_one_or_none=MagicMock(return_value=system))
        if "sum(daily_summaries.production_kwh)" in sql:
            start = params.get("day_1", date.min)
            end = params.get("day_2", date.max)
            window = [kwh for day, kwh in daily.items() if start <= day <= end]
            # An empty window sums to SQL NULL, which is not the same as 0 kWh.
            return MagicMock(
                scalar=MagicMock(return_value=sum(window) if window else None)
            )
        if "ORDER BY daily_summaries.production_kwh DESC" in sql:
            best = max(daily.items(), key=lambda item: item[1], default=None)
            row = MagicMock(day=best[0], production_kwh=best[1]) if best else None
            return MagicMock(scalar_one_or_none=MagicMock(return_value=row))
        stored = daily.get(params["day_1"])
        row = MagicMock(production_kwh=stored) if stored is not None else None
        return MagicMock(scalar_one_or_none=MagicMock(return_value=row))

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=execute)
    session.statements = statements
    return session


@asynccontextmanager
async def _client_with_db(session):
    """Serve the app with `session` injected as the request-scoped database."""

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def live_reading(monkeypatch):
    """Stand in for the Enphase read, which would otherwise leave the process.

    Returns a setter for the reading the route should see; nothing reported is
    the default, since most of these tests are about stored history.
    """
    reported = {"reading": None}

    async def fake_get_live_power(session, system):
        return reported["reading"]

    monkeypatch.setattr(overview_route, "get_live_power", fake_get_live_power)

    def set_reading(reading):
        reported["reading"] = reading

    return set_reading


@pytest.fixture
def pinned_today(monkeypatch):
    """Pin the route's calendar so the comparison windows are deterministic."""

    def pin(day: date) -> date:
        monkeypatch.setattr(overview_route, "today", lambda: day)
        return day

    return pin


def _single_day_lookups(session: AsyncMock) -> list[date]:
    """The day of every single-row daily_summaries read, in order."""
    return [
        params["day_1"]
        for sql, params in session.statements
        if sql.startswith("SELECT daily_summaries.id") and "ORDER BY" not in sql
    ]


def _sum_windows(session: AsyncMock) -> list[tuple[date, date]]:
    """The (start, end) window of every bounded SUM the route executed."""
    return [
        (params["day_1"], params["day_2"])
        for sql, params in session.statements
        if "sum(daily_summaries.production_kwh)" in sql and "day_2" in params
    ]


@pytest.mark.asyncio
async def test_overview_returns_all_four_comparison_pairs(pinned_today):
    """AC1: BR-05 and BR-06 each want two prior periods, not one."""
    pinned_today(date(2025, 7, 12))
    session = _fake_db(
        {
            date(2025, 7, 12): 30.0,
            date(2025, 7, 1): 10.0,
            date(2025, 6, 12): 24.0,
            date(2025, 6, 1): 5.0,
            date(2024, 7, 12): 20.0,
            date(2024, 7, 1): 8.0,
            # Days past the 12th must not leak into a prior-period total.
            date(2025, 6, 30): 100.0,
            date(2024, 7, 31): 100.0,
        }
    )

    async with _client_with_db(session) as client:
        response = await client.get("/api/overview")

    assert response.status_code == 200
    data = response.json()
    assert data["day_comparison"] == {
        "current_kwh": 30.0,
        "prior_kwh": 20.0,
        "pct_change": 50.0,
    }
    assert data["day_vs_last_month"] == {
        "current_kwh": 30.0,
        "prior_kwh": 24.0,
        "pct_change": 25.0,
    }
    assert data["month_comparison"] == {
        "current_kwh": 40.0,
        "prior_kwh": 29.0,
        "pct_change": 37.9,
    }
    assert data["month_vs_last_year"] == {
        "current_kwh": 40.0,
        "prior_kwh": 28.0,
        "pct_change": 42.9,
    }


@pytest.mark.asyncio
async def test_overview_compares_a_month_against_the_equivalent_window(pinned_today):
    """A month-to-date figure must not be measured against a full prior month."""
    pinned_today(date(2025, 7, 12))
    session = _fake_db({date(2025, 7, 12): 30.0})

    async with _client_with_db(session) as client:
        await client.get("/api/overview")

    windows = _sum_windows(session)
    assert (date(2025, 7, 1), date(2025, 7, 12)) in windows
    assert (date(2025, 6, 1), date(2025, 6, 12)) in windows
    assert (date(2024, 7, 1), date(2024, 7, 12)) in windows
    assert (date(2024, 1, 1), date(2024, 7, 12)) in windows


@pytest.mark.asyncio
async def test_overview_compares_the_calendar_day_across_a_leap_year(pinned_today):
    """AC2: 1 March is compared with 1 March, which is 366 days earlier."""
    pinned_today(date(2024, 3, 1))
    session = _fake_db({date(2024, 3, 1): 30.0, date(2023, 3, 1): 25.0})

    async with _client_with_db(session) as client:
        response = await client.get("/api/overview")

    assert _single_day_lookups(session) == [
        date(2024, 3, 1),
        date(2024, 2, 1),
        date(2023, 3, 1),
    ]
    assert response.json()["day_comparison"]["prior_kwh"] == 25.0


@pytest.mark.asyncio
async def test_overview_survives_a_leap_day_anchor(pinned_today):
    """AC3: 29 February has no counterpart last year, so it uses 28 February."""
    pinned_today(date(2024, 2, 29))
    session = _fake_db({date(2024, 2, 29): 30.0, date(2023, 2, 28): 18.0})

    async with _client_with_db(session) as client:
        response = await client.get("/api/overview")

    assert response.status_code == 200
    assert _single_day_lookups(session) == [
        date(2024, 2, 29),
        date(2024, 1, 29),
        date(2023, 2, 28),
    ]
    assert response.json()["day_comparison"]["prior_kwh"] == 18.0


@pytest.mark.asyncio
async def test_overview_clamps_a_month_end_anchor_to_a_shorter_month(pinned_today):
    """31 March has no 31 February; the window ends on the 28th instead."""
    pinned_today(date(2025, 3, 31))
    session = _fake_db({date(2025, 3, 31): 30.0})

    async with _client_with_db(session) as client:
        await client.get("/api/overview")

    assert date(2025, 2, 28) in _single_day_lookups(session)
    assert (date(2025, 2, 1), date(2025, 2, 28)) in _sum_windows(session)


@pytest.mark.asyncio
async def test_overview_reports_null_for_a_prior_period_with_no_data(pinned_today):
    """AC4: an unmeasured period is unknown, not a 100 percent improvement."""
    pinned_today(date(2025, 7, 12))
    session = _fake_db({date(2025, 7, 12): 30.0})

    async with _client_with_db(session) as client:
        response = await client.get("/api/overview")

    data = response.json()
    for field in (
        "day_comparison",
        "day_vs_last_month",
        "month_comparison",
        "month_vs_last_year",
    ):
        assert data[field]["prior_kwh"] is None, field
        assert data[field]["pct_change"] is None, field
    assert data["month_comparison"]["current_kwh"] == 30.0
    # Only the current year has anything stored, so it is the whole series.
    assert [point["year"] for point in data["ytd_history"]] == [2025]
    assert data["ytd_history"][0]["pct_change"] is None


@pytest.mark.asyncio
async def test_overview_lists_year_to_date_for_every_year_since_install(pinned_today):
    """AC1: BR-07 asks for prior years, plural, each over the same window."""
    pinned_today(date(2025, 7, 12))
    session = _fake_db(
        {
            date(2023, 3, 1): 1000.0,
            date(2024, 3, 1): 1200.0,
            date(2025, 3, 1): 900.0,
            # Later in each year, outside the 1 January to 12 July window.
            date(2023, 9, 1): 500.0,
            date(2024, 9, 1): 500.0,
        },
        install_date=date(2023, 1, 1),
    )

    async with _client_with_db(session) as client:
        response = await client.get("/api/overview")

    assert response.status_code == 200
    assert response.json()["ytd_history"] == [
        {
            "year": 2023,
            "production_kwh": 1000.0,
            "pct_change": -10.0,
            "is_partial": False,
        },
        {
            "year": 2024,
            "production_kwh": 1200.0,
            "pct_change": -25.0,
            "is_partial": False,
        },
        {
            "year": 2025,
            "production_kwh": 900.0,
            "pct_change": None,
            "is_partial": False,
        },
    ]


@pytest.mark.asyncio
async def test_overview_marks_the_install_year_partial(pinned_today):
    """AC2: a year the system only worked half of is not a like-for-like year."""
    pinned_today(date(2025, 7, 12))
    session = _fake_db(
        {date(2023, 6, 1): 400.0, date(2024, 3, 1): 1200.0, date(2025, 3, 1): 900.0},
        install_date=date(2023, 5, 20),
    )

    async with _client_with_db(session) as client:
        response = await client.get("/api/overview")

    partial = {
        point["year"]: point["is_partial"] for point in response.json()["ytd_history"]
    }
    assert partial == {2023: True, 2024: False, 2025: False}


@pytest.mark.asyncio
async def test_overview_omits_a_year_with_no_stored_data(pinned_today):
    """AC3: a gap in the history is a gap, not a year that produced 0 kWh."""
    pinned_today(date(2025, 7, 12))
    session = _fake_db(
        {date(2023, 3, 1): 1000.0, date(2025, 3, 1): 900.0},
        install_date=date(2023, 1, 1),
    )

    async with _client_with_db(session) as client:
        response = await client.get("/api/overview")

    assert [point["year"] for point in response.json()["ytd_history"]] == [2023, 2025]


@pytest.mark.asyncio
async def test_overview_year_to_date_windows_end_on_the_same_calendar_day(pinned_today):
    """Each year is measured to 29 February's fallback, not to a drifting day."""
    pinned_today(date(2024, 2, 29))
    session = _fake_db({date(2024, 2, 29): 30.0}, install_date=date(2022, 6, 1))

    async with _client_with_db(session) as client:
        await client.get("/api/overview")

    windows = _sum_windows(session)
    assert (date(2022, 1, 1), date(2022, 2, 28)) in windows
    assert (date(2023, 1, 1), date(2023, 2, 28)) in windows
    assert (date(2024, 1, 1), date(2024, 2, 29)) in windows


@pytest.mark.asyncio
async def test_overview_reports_the_live_reading_with_its_timestamp(
    pinned_today, live_reading
):
    """AC1: the latest output, together with the time it was measured."""
    pinned_today(date(2025, 7, 12))
    live_reading(
        CurrentProduction(
            watts=4210.0, reported_at=datetime(2025, 7, 12, 13, 0, tzinfo=UTC)
        )
    )
    session = _fake_db({date(2025, 7, 12): 30.0})

    async with _client_with_db(session) as client:
        response = await client.get("/api/overview")

    data = response.json()
    assert data["current_power_w"] == 4210.0
    assert data["current_power_at"] == "2025-07-12T13:00:00Z"


@pytest.mark.asyncio
async def test_overview_serves_the_history_without_a_live_reading(pinned_today):
    """AC3: an unreachable Enphase costs the reading, not the whole payload."""
    pinned_today(date(2025, 7, 12))
    session = _fake_db({date(2025, 7, 12): 30.0})

    async with _client_with_db(session) as client:
        response = await client.get("/api/overview")

    assert response.status_code == 200
    data = response.json()
    assert data["current_power_w"] is None
    assert data["current_power_at"] is None
    assert data["today_kwh"] == 30.0


@pytest.mark.asyncio
async def test_overview_returns_empty_comparisons_with_no_system():
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    async with _client_with_db(session) as client:
        response = await client.get("/api/overview")

    assert response.status_code == 200
    data = response.json()
    # AC4: nothing is configured, so there is nothing to ask Enphase about.
    assert data["current_power_w"] is None
    assert data["current_power_at"] is None
    for field in ("day_comparison", "day_vs_last_month", "month_vs_last_year"):
        assert data[field] == {
            "current_kwh": 0.0,
            "prior_kwh": None,
            "pct_change": None,
        }
