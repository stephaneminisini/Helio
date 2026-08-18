from datetime import date, datetime, time

import pytest

from helio.core.dates import (
    month_to_date,
    now_local,
    same_day_in_year,
    same_day_last_month,
    same_day_last_year,
    today,
    whole_month,
    whole_year,
)


def test_now_local_agrees_with_today():
    """The overview subtracts one from the other to find how far today has got.

    Two clocks in different timezones would make that difference negative before
    the offset has passed, and the day comparison would read the wrong window.
    """
    elapsed = now_local() - datetime.combine(today(), time.min)

    assert 0 <= elapsed.total_seconds() < 24 * 3600


@pytest.mark.parametrize(
    ("anchor", "expected"),
    [
        # AC2: the day after a leap day still lands on the same calendar day.
        (date(2024, 3, 1), date(2023, 3, 1)),
        (date(2025, 3, 1), date(2024, 3, 1)),
        # A plain day, and the two boundaries of the year.
        (date(2025, 7, 12), date(2024, 7, 12)),
        (date(2025, 1, 1), date(2024, 1, 1)),
        (date(2025, 12, 31), date(2024, 12, 31)),
        # Leap day to leap day, four years apart, needs no fallback.
        (date(2024, 2, 29), date(2023, 2, 28)),
    ],
)
def test_same_day_last_year_keeps_the_calendar_day(anchor, expected):
    assert same_day_last_year(anchor) == expected


def test_same_day_last_year_never_drifts_by_a_day():
    """A 365-day subtraction lands on 29 February here; the calendar day does not."""
    assert same_day_last_year(date(2024, 3, 1)) == date(2023, 3, 1)
    assert date(2024, 3, 1).toordinal() - date(2023, 3, 1).toordinal() == 366


def test_same_day_last_year_falls_back_from_a_leap_day():
    """AC3: 29 February has no counterpart, so it resolves to 28 February."""
    assert same_day_last_year(date(2024, 2, 29)) == date(2023, 2, 28)


@pytest.mark.parametrize(
    ("anchor", "year", "expected"),
    [
        (date(2025, 7, 12), 2019, date(2019, 7, 12)),
        (date(2025, 7, 12), 2025, date(2025, 7, 12)),
        # A leap day in a common year falls back; in a leap year it survives.
        (date(2024, 2, 29), 2021, date(2021, 2, 28)),
        (date(2024, 2, 29), 2020, date(2020, 2, 29)),
    ],
)
def test_same_day_in_year_carries_the_month_and_day(anchor, year, expected):
    assert same_day_in_year(anchor, year) == expected


@pytest.mark.parametrize(
    ("anchor", "expected"),
    [
        (date(2025, 7, 12), date(2025, 6, 12)),
        # January steps back across the year boundary.
        (date(2025, 1, 15), date(2024, 12, 15)),
        # A day that the previous month does not have is clamped to its end.
        (date(2025, 3, 31), date(2025, 2, 28)),
        (date(2024, 3, 31), date(2024, 2, 29)),
        (date(2025, 5, 31), date(2025, 4, 30)),
        # 29 February steps back to a January that is long enough for it.
        (date(2024, 2, 29), date(2024, 1, 29)),
    ],
)
def test_same_day_last_month_clamps_to_the_shorter_month(anchor, expected):
    assert same_day_last_month(anchor) == expected


@pytest.mark.parametrize(
    ("anchor", "expected"),
    [
        (date(2025, 7, 12), (date(2025, 7, 1), date(2025, 7, 12))),
        (date(2025, 7, 1), (date(2025, 7, 1), date(2025, 7, 1))),
        (date(2024, 2, 29), (date(2024, 2, 1), date(2024, 2, 29))),
    ],
)
def test_month_to_date_spans_the_first_through_the_anchor(anchor, expected):
    assert month_to_date(anchor) == expected


@pytest.mark.parametrize(
    ("anchor", "expected"),
    [
        (date(2025, 7, 12), (date(2025, 7, 1), date(2025, 7, 31))),
        (date(2025, 4, 30), (date(2025, 4, 1), date(2025, 4, 30))),
        # February's length comes from the calendar, not from an assumption.
        (date(2025, 2, 14), (date(2025, 2, 1), date(2025, 2, 28))),
        (date(2024, 2, 14), (date(2024, 2, 1), date(2024, 2, 29))),
    ],
)
def test_whole_month_ends_on_the_calendar_last_day(anchor, expected):
    assert whole_month(anchor) == expected


def test_whole_year_spans_january_to_december():
    assert whole_year(2024) == (date(2024, 1, 1), date(2024, 12, 31))
