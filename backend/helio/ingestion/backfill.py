"""Historical backfill of production and irradiance data since the install date.

Runs either as a one-shot CLI (`python -m helio.ingestion.backfill`) or as a
background task started by POST /api/backfill. Progress is published on the
module-level `progress` singleton so the API can report it; that is sound here
only because a deployment runs a single API process - the same assumption the
in-process scheduler already makes.
"""

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta

import httpx
from loguru import logger
from sqlalchemy import select

from helio.analytics.summarizer import build_daily_summary
from helio.core.config import settings
from helio.db.models import System
from helio.db.session import AsyncSessionLocal
from helio.ingestion.enphase_client import EnphaseClient
from helio.ingestion.irradiance_client import NASAClient, NRELClient
from helio.ingestion.poller import detect_gaps, poll_intervals, poll_irradiance

INTER_DAY_PAUSE_SECONDS = 0.5


@dataclass
class BackfillProgress:
    """Counters for the most recent or in-flight backfill run.

    Attributes:
        running: Whether a run is currently in flight.
        total_days: Number of missing days the run set out to fill.
        completed_days: Days attempted so far, successful or not.
        failed_days: Days whose interval fetch failed.
        error: Reason the run could not start or could not finish, if any.
    """

    running: bool = False
    total_days: int = 0
    completed_days: int = 0
    failed_days: int = 0
    error: str | None = None

    def start(self) -> None:
        """Mark a run as started and clear the previous run's counters."""
        self.running = True
        self.total_days = 0
        self.completed_days = 0
        self.failed_days = 0
        self.error = None


progress = BackfillProgress()


async def backfill() -> None:
    """Fill every missing day of production and irradiance since the install date.

    Never raises: a background task that dies takes its diagnosis with it, so
    failures are logged and recorded on `progress.error` instead. Concurrent
    starts are refused rather than queued.
    """
    if progress.running:
        logger.warning("Backfill already running - ignoring duplicate start")
        return

    progress.start()
    try:
        await _backfill_missing_days()
    except Exception as exc:
        logger.error("Backfill aborted: {}", exc)
        progress.error = str(exc)
    finally:
        progress.running = False


async def _backfill_missing_days() -> None:
    """Detect gaps from install date to yesterday and fill them one day at a time.

    Each day's interval fetch, irradiance fetch, and summary build are isolated so
    one bad day does not lose the rest of the run.

    Raises:
        Exception: Re-raises anything the enclosing session context manager fails
            with; per-day and per-step failures are caught and logged instead.
    """
    async with AsyncSessionLocal() as session:
        system = (await session.execute(select(System).limit(1))).scalar_one_or_none()
        if system is None:
            progress.error = "No system configured. Complete setup first."
            logger.error("No system found. Configure your system in Setup first.")
            return

        client = EnphaseClient(
            client_id=settings.enphase_client_id,
            client_secret=settings.enphase_client_secret,
            system_id=settings.enphase_system_id,
            access_token=settings.enphase_access_token,
            refresh_token=settings.enphase_refresh_token,
        )
        try:
            await client.refresh_access_token()
        except (httpx.HTTPStatusError, ValueError) as exc:
            progress.error = (
                "Enphase rejected the stored credentials. Check "
                "ENPHASE_ACCESS_TOKEN and ENPHASE_REFRESH_TOKEN."
            )
            logger.error(
                "Token refresh failed - verify ENPHASE_ACCESS_TOKEN and "
                "ENPHASE_REFRESH_TOKEN in .env: {}",
                exc,
            )
            return
        except Exception as exc:
            progress.error = f"Unexpected error during token refresh: {exc}"
            logger.error("Unexpected error during token refresh: {}", exc)
            return

        irr_client: NRELClient | NASAClient
        if settings.irradiance_source == "nrel":
            irr_client = NRELClient(settings.nrel_api_key)
        else:
            irr_client = NASAClient()

        start = system.install_date
        end = date.today() - timedelta(days=1)
        try:
            gaps = await detect_gaps(session, system.id, start, end)
        except Exception as exc:
            progress.error = f"Could not determine which days are missing: {exc}"
            logger.error(
                "Failed to detect gaps in date range {}-{}: {}", start, end, exc
            )
            return

        progress.total_days = len(gaps)
        logger.info(
            "Backfill: {} days missing between {} and {}", len(gaps), start, end
        )

        for day in gaps:
            logger.info("Backfilling {}", day)
            intervals_ok = False

            try:
                await poll_intervals(session, client, system.id, day, day)
                intervals_ok = True
            except (RuntimeError, httpx.HTTPStatusError) as exc:
                logger.error("Interval backfill failed for {}: {}", day, exc)
            except Exception as exc:
                logger.error("Unexpected interval error for {}: {}", day, exc)

            try:
                await poll_irradiance(
                    session,
                    irr_client,
                    system.id,
                    float(system.latitude or 0),
                    float(system.longitude or 0),
                    float(system.tilt_angle_deg or 30),
                    float(system.azimuth_deg or 180),
                    day,
                    settings.irradiance_source,
                )
            except httpx.HTTPStatusError as exc:
                logger.error("Irradiance backfill failed for {}: {}", day, exc)
            except Exception as exc:
                logger.error("Unexpected irradiance error for {}: {}", day, exc)

            if intervals_ok:
                try:
                    await build_daily_summary(session, system.id, day)
                except Exception as exc:
                    logger.error("Summary build failed for {}: {}", day, exc)
            else:
                progress.failed_days += 1

            progress.completed_days += 1
            await asyncio.sleep(INTER_DAY_PAUSE_SECONDS)

        logger.info("Backfill complete")


if __name__ == "__main__":
    asyncio.run(backfill())
