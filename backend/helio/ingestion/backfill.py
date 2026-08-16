"""Backfill all historical data from the system install date to yesterday.

Usage:
    make backfill
"""

import asyncio
from datetime import date, timedelta

import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from helio.analytics.summarizer import build_daily_summary
from helio.core.config import settings
from helio.db.models import System
from helio.ingestion.irradiance_client import (
    IrradianceSourceError,
    build_irradiance_client,
)
from helio.ingestion.poller import (
    detect_gaps,
    irradiance_location,
    poll_intervals,
    poll_irradiance,
)
from helio.ingestion.tokens import TokenError, build_authenticated_client


async def backfill(session: AsyncSession, system: System) -> None:
    """Fetch all missing production and irradiance data since the install date.

    Detects missing days by comparing daily_summaries against the full date range
    from install_date to yesterday, then fills gaps one day at a time. Every step
    is logged and skipped on failure so one bad day cannot abort the run.

    Args:
        session: Active async database session.
        system: The configured system to backfill.
    """
    try:
        client = await build_authenticated_client(session, system)
    except (TokenError, httpx.HTTPStatusError, ValueError) as exc:
        logger.error("Enphase authentication failed, backfill aborted: {}", exc)
        return
    except Exception as exc:
        logger.error("Unexpected error during token refresh: {}", exc)
        return

    # Both resolved once, not per day, so an unconfigured site logs one warning
    # rather than one per backfilled day.
    try:
        irr_client = build_irradiance_client(
            system.irradiance_source, settings.nrel_api_key
        )
    except IrradianceSourceError as exc:
        logger.error("Irradiance backfill skipped: {}", exc)
        irr_client = None
    location = irradiance_location(system)

    start = system.install_date
    end = date.today() - timedelta(days=1)
    try:
        gaps = await detect_gaps(session, system.id, start, end)
    except Exception as exc:
        logger.error("Failed to detect gaps in date range {}-{}: {}", start, end, exc)
        return
    logger.info("Backfill: {} days missing between {} and {}", len(gaps), start, end)

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

        if location is not None and irr_client is not None:
            try:
                await poll_irradiance(
                    session,
                    irr_client,
                    system.id,
                    *location,
                    float(system.tilt_angle_deg or 30),
                    float(system.azimuth_deg or 180),
                    day,
                    system.irradiance_source,
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
