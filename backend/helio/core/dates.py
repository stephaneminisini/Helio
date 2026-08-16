"""Calendar arithmetic for like-for-like period comparisons.

Production comparisons are only meaningful between equivalent stretches of the
calendar, so every helper here answers "which dates were the counterpart of this
one?" rather than doing plain day arithmetic. Subtracting 365 days drifts by a
day across a leap year and subtracting 30 walks off the month boundary; both
show up as a wrong-day comparison on the dashboard.
"""

from calendar import monthrange
from datetime import date


def today() -> date:
    """Return the current local date.

    Returns:
        Today's date. Routing every comparison through this one call gives the
        tests a single place to pin the calendar, which is the only way to
        exercise the leap-year paths below on a fixed date.
    """
    return date.today()


def same_day_last_month(anchor: date) -> date:
    """Return the same day of the month one month before the anchor.

    Args:
        anchor: The day to step back from.

    Returns:
        The same day-of-month in the previous month, clamped to that month's
        last day when it is shorter (31 March gives 28 or 29 February).
    """
    year = anchor.year - 1 if anchor.month == 1 else anchor.year
    month = 12 if anchor.month == 1 else anchor.month - 1
    return date(year, month, min(anchor.day, monthrange(year, month)[1]))


def same_day_last_year(anchor: date) -> date:
    """Return the same calendar day one year before the anchor.

    Args:
        anchor: The day to step back from.

    Returns:
        The same month and day in the previous year. 29 February has no
        counterpart in a common year, so it falls back to 28 February, which
        keeps the comparison exactly one calendar year and one season apart.
    """
    try:
        return anchor.replace(year=anchor.year - 1)
    except ValueError:
        return date(anchor.year - 1, 2, 28)


def month_to_date(anchor: date) -> tuple[date, date]:
    """Return the window from the first of the anchor's month to the anchor.

    Args:
        anchor: The last day of the window.

    Returns:
        A (start, end) pair, inclusive of both ends.
    """
    return anchor.replace(day=1), anchor
