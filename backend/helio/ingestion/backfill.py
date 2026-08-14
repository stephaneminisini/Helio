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
from helio.ingestion.enphase_client import EnphaseClient
from helio.ingestion.irradiance_client import NASAClient, NRELClient
from helio.ingestion.poller import detect_gaps, poll_intervals, poll_irradiance


async def backfill(session: AsyncSession, system: System) -> None:
    """Fetch all missing production and irradiance data since the install date.

    Detects missing days by comparing daily_summaries against the full date range
    from install_date to yesterday, then fills gaps one day at a time. Every step
    is logged and skipped on failure so one bad day cannot abort the run.

    Args:
        session: Active async database session.
        system: The configured system to backfill.
    """
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
        logger.error(
            "Token refresh failed - verify ENPHASE_ACCESS_TOKEN and "
            "ENPHASE_REFRESH_TOKEN in .env: {}",
            exc,
        )
        return
    except Exception as exc:
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

        await asyncio.sleep(0.5)

    logger.info("Backfill complete")
