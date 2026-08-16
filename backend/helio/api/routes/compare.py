from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.api.schemas.compare import CompareResponse, Period, PeriodTotal
from helio.core.comparisons import pct_change
from helio.core.dates import same_day_in_year, today, whole_month, whole_year
from helio.db.models import DailySummary, System
from helio.db.session import get_db

router = APIRouter()


def _window(period: Period, anchor: date, year: int) -> tuple[date, date]:
    """Return the stretch of `year` that corresponds to the anchor.

    Args:
        period: The grain of the comparison.
        anchor: The day the caller asked about.
        year: The year to find the counterpart window in.

    Returns:
        An inclusive (start, end) pair. Unlike /api/overview these windows are
        whole: a caller naming a period wants that period's total, and the
        is_partial flag says when the total covers less than the window.
    """
    if period == "day":
        day = same_day_in_year(anchor, year)
        return day, day
    if period == "month":
        return whole_month(date(year, anchor.month, 1))
    return whole_year(year)


def _label(period: Period, start: date) -> str:
    """Return a human-readable name for a window, given its first day.

    Args:
        period: The grain of the comparison.
        start: The window's first day.

    Returns:
        The window's ISO-style label at the requested grain.
    """
    if period == "day":
        return start.isoformat()
    if period == "month":
        return f"{start.year:04d}-{start.month:02d}"
    return str(start.year)


def _is_partial(start: date, end: date, install_date: date | None, as_of: date) -> bool:
    """Report whether production can cover the whole window.

    Args:
        start: The window's first day.
        end: The window's last day.
        install_date: When the system started producing, or None when no system
            is configured yet.
        as_of: Today, against which an unfinished window is recognised.

    Returns:
        True when the window runs past today or begins before the install date,
        either of which caps the total below what the period could hold.
    """
    return end > as_of or (install_date is not None and install_date > start)


@router.get("/compare", response_model=CompareResponse)
async def compare(
    period: Period,
    anchor_date: date | None = Query(
        None,
        alias="date",
        description="Day to anchor the comparison on. Defaults to today.",
    ),
    db: AsyncSession = Depends(get_db),
) -> CompareResponse:
    """Compare one period against its counterpart in every prior year.

    Args:
        period: Whether to compare a single day, a whole month or a whole year.
        anchor_date: The day the period is taken from; today when omitted.
        db: Async database session (injected).

    Returns:
        A CompareResponse listing the anchor period and each prior year's
        equivalent window, oldest first. A window with nothing stored is left
        out rather than reported as zero, so the caller can tell a gap in the
        history from a period that genuinely produced nothing. An anchor before
        the install date yields a single entry with null values rather than an
        error, since asking about a date the system predates is a fair question
        with an empty answer.
    """
    system = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    install_date = system.install_date if system else None
    now = today()
    anchor = anchor_date or now

    # The anchor year is always included, even when it precedes the install
    # date, so the response always describes the period that was asked about.
    first_year = min(install_date.year, anchor.year) if install_date else anchor.year
    windows = {
        year: _window(period, anchor, year)
        for year in range(first_year, anchor.year + 1)
    }

    totals: dict[int, float | None] = {}
    if system is not None:
        # SQLAlchemy AsyncSession is not safe for concurrent use; one indexed
        # sum per year, run in sequence.
        for year, (start, end) in windows.items():
            result = await db.execute(
                select(func.sum(DailySummary.production_kwh)).where(
                    DailySummary.system_id == system.id,
                    DailySummary.day >= start,
                    DailySummary.day <= end,
                )
            )
            total = result.scalar()
            totals[year] = float(total) if total is not None else None

    anchor_total = totals.get(anchor.year)
    periods = [
        PeriodTotal(
            label=_label(period, start),
            start=start,
            end=end,
            production_kwh=(
                round(totals[year], 3) if totals.get(year) is not None else None
            ),
            pct_change=(
                None
                if year == anchor.year
                else pct_change(anchor_total or 0.0, totals.get(year))
            ),
            is_partial=_is_partial(start, end, install_date, now),
        )
        for year, (start, end) in windows.items()
        if totals.get(year) is not None or year == anchor.year
    ]
    return CompareResponse(period=period, anchor=anchor, periods=periods)
