from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from helio.api.main import app
from helio.api.routes import compare as compare_route
from helio.db.models import System
from helio.db.session import get_db


def _fake_db(
    daily: dict[date, float], install_date: date = date(2020, 1, 1)
) -> AsyncMock:
    """Serve the compare queries from an in-memory day to kWh mapping.

    The route only ever reads the system row and bounded sums, so dispatching on
    the compiled statement keeps this fake indifferent to query order. Executed
    statements are recorded on `session.statements` so a test can assert which
    windows were queried.
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
        window = [
            kwh
            for day, kwh in daily.items()
            if params["day_1"] <= day <= params["day_2"]
        ]
        # An empty window sums to SQL NULL, which is not the same as 0 kWh.
        return MagicMock(scalar=MagicMock(return_value=sum(window) if window else None))

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


@pytest.fixture
def pinned_today(monkeypatch):
    """Pin the route's calendar so partial-period flags are deterministic."""

    def pin(day: date) -> date:
        monkeypatch.setattr(compare_route, "today", lambda: day)
        return day

    return pin


def _windows(session: AsyncMock) -> list[tuple[date, date]]:
    """The (start, end) window of every sum the route executed."""
    return [
        (params["day_1"], params["day_2"])
        for sql, params in session.statements
        if "sum(daily_summaries.production_kwh)" in sql
    ]


@pytest.mark.asyncio
async def test_compare_day_returns_the_same_calendar_day_in_prior_years(pinned_today):
    """AC1: the day, its counterpart in each prior year, and the deltas."""
    pinned_today(date(2025, 8, 16))
    session = _fake_db(
        {
            date(2023, 7, 12): 20.0,
            date(2024, 7, 12): 24.0,
            date(2025, 7, 12): 30.0,
            # A neighbouring day must not leak into a single-day total.
            date(2024, 7, 13): 100.0,
        },
        install_date=date(2023, 1, 1),
    )

    async with _client_with_db(session) as client:
        response = await client.get("/api/compare?period=day&date=2025-07-12")

    assert response.status_code == 200
    data = response.json()
    assert data["period"] == "day"
    assert data["anchor"] == "2025-07-12"
    assert data["periods"] == [
        {
            "label": "2023-07-12",
            "start": "2023-07-12",
            "end": "2023-07-12",
            "production_kwh": 20.0,
            "pct_change": 50.0,
            "is_partial": False,
        },
        {
            "label": "2024-07-12",
            "start": "2024-07-12",
            "end": "2024-07-12",
            "production_kwh": 24.0,
            "pct_change": 25.0,
            "is_partial": False,
        },
        {
            "label": "2025-07-12",
            "start": "2025-07-12",
            "end": "2025-07-12",
            "production_kwh": 30.0,
            "pct_change": None,
            "is_partial": False,
        },
    ]


@pytest.mark.asyncio
async def test_compare_day_anchors_on_today_when_no_date_is_given(pinned_today):
    """The anchor is optional, and omitting it means today."""
    pinned_today(date(2025, 8, 16))
    session = _fake_db({date(2025, 8, 16): 30.0}, install_date=date(2025, 1, 1))

    async with _client_with_db(session) as client:
        response = await client.get("/api/compare?period=day")

    assert response.json()["anchor"] == "2025-08-16"
    assert _windows(session) == [(date(2025, 8, 16), date(2025, 8, 16))]


@pytest.mark.asyncio
async def test_compare_day_falls_back_from_a_missing_leap_day(pinned_today):
    """29 February has no counterpart in a common year, so it uses the 28th."""
    pinned_today(date(2025, 8, 16))
    session = _fake_db({date(2024, 2, 29): 30.0}, install_date=date(2023, 1, 1))

    async with _client_with_db(session) as client:
        response = await client.get("/api/compare?period=day&date=2024-02-29")

    assert (date(2023, 2, 28), date(2023, 2, 28)) in _windows(session)
    assert [point["label"] for point in response.json()["periods"]] == ["2024-02-29"]


@pytest.mark.asyncio
async def test_compare_month_aggregates_the_whole_month(pinned_today):
    """AC2: whole months, against the same month in prior years."""
    pinned_today(date(2025, 8, 16))
    session = _fake_db(
        {
            date(2024, 2, 1): 100.0,
            date(2024, 2, 29): 50.0,
            date(2025, 2, 1): 120.0,
            date(2025, 2, 28): 60.0,
            # March belongs to another window.
            date(2025, 3, 1): 999.0,
        },
        install_date=date(2024, 1, 1),
    )

    async with _client_with_db(session) as client:
        response = await client.get("/api/compare?period=month&date=2025-02-14")

    windows = _windows(session)
    # February's last day comes from the calendar, so a leap year gets 29 days.
    assert (date(2024, 2, 1), date(2024, 2, 29)) in windows
    assert (date(2025, 2, 1), date(2025, 2, 28)) in windows
    data = response.json()
    assert [point["label"] for point in data["periods"]] == ["2024-02", "2025-02"]
    assert data["periods"][0]["production_kwh"] == 150.0
    assert data["periods"][0]["pct_change"] == 20.0
    assert data["periods"][1]["production_kwh"] == 180.0


@pytest.mark.asyncio
async def test_compare_year_marks_an_unfinished_year_partial(pinned_today):
    """AC3: full-year totals, with the year still in progress flagged."""
    pinned_today(date(2025, 8, 16))
    session = _fake_db(
        {date(2024, 6, 1): 4000.0, date(2025, 6, 1): 2500.0},
        install_date=date(2024, 1, 1),
    )

    async with _client_with_db(session) as client:
        response = await client.get("/api/compare?period=year")

    assert _windows(session) == [
        (date(2024, 1, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2025, 12, 31)),
    ]
    data = response.json()
    assert [point["label"] for point in data["periods"]] == ["2024", "2025"]
    assert data["periods"][0]["is_partial"] is False
    # 2025 runs to 31 December, which is still ahead of the pinned today.
    assert data["periods"][1]["is_partial"] is True


@pytest.mark.asyncio
async def test_compare_marks_the_install_period_partial(pinned_today):
    """A window that starts before the system existed cannot be filled."""
    pinned_today(date(2025, 8, 16))
    session = _fake_db(
        {date(2023, 8, 1): 300.0, date(2024, 8, 1): 500.0},
        install_date=date(2023, 8, 20),
    )

    async with _client_with_db(session) as client:
        response = await client.get("/api/compare?period=month&date=2024-08-05")

    partial = {
        point["label"]: point["is_partial"] for point in response.json()["periods"]
    }
    assert partial == {"2023-08": True, "2024-08": False}


@pytest.mark.asyncio
async def test_compare_omits_a_prior_period_with_no_data(pinned_today):
    """A gap in the history is a gap, not a period that produced 0 kWh."""
    pinned_today(date(2025, 8, 16))
    session = _fake_db(
        {date(2023, 7, 12): 20.0, date(2025, 7, 12): 30.0},
        install_date=date(2023, 1, 1),
    )

    async with _client_with_db(session) as client:
        response = await client.get("/api/compare?period=day&date=2025-07-12")

    assert [point["label"] for point in response.json()["periods"]] == [
        "2023-07-12",
        "2025-07-12",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    ["period=week", "period=day&date=not-a-date", "period=day&date=2025-13-01"],
)
async def test_compare_rejects_an_unsupported_request(query):
    """AC4: a bad period or date is a 422 that names what is accepted."""
    session = _fake_db({})

    async with _client_with_db(session) as client:
        response = await client.get(f"/api/compare?{query}")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_compare_names_the_accepted_periods_in_the_error(pinned_today):
    """AC4: the caller should not have to guess the vocabulary."""
    pinned_today(date(2025, 8, 16))
    session = _fake_db({})

    async with _client_with_db(session) as client:
        response = await client.get("/api/compare?period=week")

    detail = str(response.json()["detail"])
    for value in ("day", "month", "year"):
        assert value in detail


@pytest.mark.asyncio
async def test_compare_returns_nulls_for_a_date_before_install(pinned_today):
    """AC5: asking about a date the system predates is empty, not an error."""
    pinned_today(date(2025, 8, 16))
    session = _fake_db({date(2025, 7, 12): 30.0}, install_date=date(2024, 1, 1))

    async with _client_with_db(session) as client:
        response = await client.get("/api/compare?period=day&date=2019-05-04")

    assert response.status_code == 200
    assert response.json()["periods"] == [
        {
            "label": "2019-05-04",
            "start": "2019-05-04",
            "end": "2019-05-04",
            "production_kwh": None,
            "pct_change": None,
            "is_partial": True,
        }
    ]


@pytest.mark.asyncio
async def test_compare_returns_the_anchor_period_with_no_system(pinned_today):
    """With nothing configured there is still a period to describe."""
    pinned_today(date(2025, 8, 16))
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    async with _client_with_db(session) as client:
        response = await client.get("/api/compare?period=month&date=2025-08-16")

    assert response.status_code == 200
    assert response.json()["periods"] == [
        {
            "label": "2025-08",
            "start": "2025-08-01",
            "end": "2025-08-31",
            "production_kwh": None,
            "pct_change": None,
            "is_partial": True,
        }
    ]
