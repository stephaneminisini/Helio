from datetime import date

import pytest

from helio.core.dates import month_to_date, same_day_last_month, same_day_last_year


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
