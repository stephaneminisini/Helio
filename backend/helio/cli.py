"""Single command line surface behind the Makefile data targets.

Usage:
    python -m helio.cli {backfill,poll-now,poll-status,rebuild-summaries,seed-mock}

Every command needs a configured system, so each one resolves it up front and
exits with EXIT_NO_SYSTEM and a pointer to the Setup page rather than a
traceback when the install has not been set up yet.
"""

import argparse
import asyncio
import sys
from argparse import Namespace

from loguru import logger
from sqlalchemy import select

from helio.analytics.summarizer import rebuild_all_summaries
from helio.db.models import System
from helio.db.seed_mock import DEFAULT_YEARS, RealDataError, seed_mock
from helio.db.session import AsyncSessionLocal
from helio.ingestion.backfill import backfill
from helio.ingestion.poller import recent_polls
from helio.ingestion.scheduler import run_daily_poll

EXIT_NO_SYSTEM = 2
EXIT_REAL_DATA = 3
POLL_STATUS_LIMIT = 10
NO_SYSTEM_MESSAGE = (
    "No system is configured yet. Open the dashboard at http://localhost:3000, "
    "fill in the Setup tab, and run this command again."
)


class SystemNotConfiguredError(RuntimeError):
    """Raised when a command needs a system row and the systems table is empty."""


async def _require_system(session) -> System:
    """Return the configured system.

    Args:
        session: Active async database session.

    Returns:
        The single System row.

    Raises:
        SystemNotConfiguredError: If no system has been configured.
    """
    system = (await session.execute(select(System).limit(1))).scalar_one_or_none()
    if system is None:
        raise SystemNotConfiguredError(NO_SYSTEM_MESSAGE)
    return system


async def _backfill(args: Namespace) -> None:
    """Fetch every missing day between the install date and yesterday."""
    async with AsyncSessionLocal() as session:
        system = await _require_system(session)
        await backfill(session, system)


async def _poll_now(args: Namespace) -> None:
    """Run the scheduled daily poll immediately."""
    async with AsyncSessionLocal() as session:
        await _require_system(session)
    await run_daily_poll()


async def _poll_status(args: Namespace) -> None:
    """Print the most recent poll_log rows with their status and error text."""
    async with AsyncSessionLocal() as session:
        await _require_system(session)
        rows = await recent_polls(session, POLL_STATUS_LIMIT)

    if not rows:
        print("No polls have run yet.")
        return

    print(f"{'STARTED (UTC)':<20} {'TYPE':<12} {'STATUS':<8} {'FETCHED':>7} {'NEW':>7}")
    for row in rows:
        started = row.started_at.strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"{started:<20} {row.poll_type or '-':<12} {row.status or '-':<8} "
            f"{row.records_fetched:>7} {row.records_inserted:>7}"
        )
        if row.error_message:
            print(f"{'':<20} error: {row.error_message}")


async def _rebuild_summaries(args: Namespace) -> None:
    """Recompute every daily and monthly summary from the stored intervals."""
    async with AsyncSessionLocal() as session:
        system = await _require_system(session)
        days, months = await rebuild_all_summaries(session, system)
    print(f"Rebuilt {days} daily and {months} monthly summaries.")


async def _seed_mock(args: Namespace) -> None:
    """Insert synthetic production, irradiance and per-panel data."""
    async with AsyncSessionLocal() as session:
        system = await _require_system(session)
        intervals, irradiance, panels = await seed_mock(
            session, system, years=args.years
        )
    print(
        f"Seeded {intervals} intervals, {irradiance} irradiance days "
        f"and {panels} panel readings."
    )


def _build_parser() -> argparse.ArgumentParser:
    """Return the argument parser with one subcommand per Makefile data target."""
    parser = argparse.ArgumentParser(
        prog="python -m helio.cli",
        description="Helio Monitor maintenance commands.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name, handler, help_text in (
        ("backfill", _backfill, "Fetch all historical data from the install date"),
        ("poll-now", _poll_now, "Run the daily poll immediately"),
        ("poll-status", _poll_status, f"Show the last {POLL_STATUS_LIMIT} poll runs"),
        (
            "rebuild-summaries",
            _rebuild_summaries,
            "Rebuild all summaries from raw intervals",
        ),
        ("seed-mock", _seed_mock, "Insert synthetic data for development"),
    ):
        subparser = subparsers.add_parser(name, help=help_text)
        subparser.set_defaults(handler=handler)

    subparsers.choices["seed-mock"].add_argument(
        "--years",
        type=int,
        default=DEFAULT_YEARS,
        help=f"Years of history to generate (default: {DEFAULT_YEARS})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the requested command.

    Args:
        argv: Argument list, defaulting to sys.argv[1:].

    Returns:
        Process exit code: 0 on success, EXIT_NO_SYSTEM if no system exists,
        EXIT_REAL_DATA if seeding would overwrite real production data.
    """
    args = _build_parser().parse_args(argv)
    try:
        asyncio.run(args.handler(args))
    except SystemNotConfiguredError as exc:
        logger.error("{}", exc)
        return EXIT_NO_SYSTEM
    except RealDataError as exc:
        logger.error("{}", exc)
        return EXIT_REAL_DATA
    return 0


if __name__ == "__main__":
    sys.exit(main())
