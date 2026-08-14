"""One-shot script to backfill all historical data from install date to today.

Usage:
    docker compose exec api python scripts/backfill.py
"""

import asyncio
from datetime import date, timedelta

import httpx
from loguru import logger
from sqlalchemy import select

from helio.analytics.summarizer import build_daily_summary
from helio.core.config import settings
from helio.db.models import System
from helio.db.session import AsyncSessionLocal
from helio.ingestion.irradiance_client import NASAClient, NRELClient
from helio.ingestion.poller import (
    detect_gaps,
    irradiance_location,
    poll_intervals,
    poll_irradiance,
)
from helio.ingestion.tokens import TokenError, build_authenticated_client


async def backfill() -> None:
    """Fetch all missing production and irradiance data since the system install date.

    Detects missing days by comparing daily_summaries against the full date range
    from install_date to yesterday, then fills gaps one day at a time.
    """
    async with AsyncSessionLocal() as session:
        system = (await session.execute(select(System).limit(1))).scalar_one_or_none()
        if system is None:
            logger.error("No system found. Configure your system in Setup first.")
            return

        try:
            client = await build_authenticated_client(session, system)
        except (TokenError, httpx.HTTPStatusError, ValueError) as exc:
            logger.error("Enphase authentication failed, backfill aborted: {}", exc)
            return
        except Exception as exc:
            logger.error("Unexpected error during token refresh: {}", exc)
            return

        irr_client: NRELClient | NASAClient
        if settings.irradiance_source == "nrel":
            irr_client = NRELClient(settings.nrel_api_key)
        else:
            irr_client = NASAClient()

        # Checked once, not per day, so an unconfigured site logs one warning
        # rather than one per backfilled day.
        location = irradiance_location(system)

        start = system.install_date
        end = date.today() - timedelta(days=1)
        try:
            gaps = await detect_gaps(session, system.id, start, end)
        except Exception as exc:
            logger.error(
                "Failed to detect gaps in date range {}-{}: {}", start, end, exc
            )
            return
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

            if location is not None:
                try:
                    await poll_irradiance(
                        session,
                        irr_client,
                        system.id,
                        *location,
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

            await asyncio.sleep(0.5)

        logger.info("Backfill complete")


if __name__ == "__main__":
    asyncio.run(backfill())
