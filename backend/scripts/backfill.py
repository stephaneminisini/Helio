"""One-shot script to backfill all historical data from install date to today.

Usage:
    docker compose exec api python scripts/backfill.py
"""

import asyncio
from datetime import date, timedelta

from loguru import logger
from sqlalchemy import select

from helio.analytics.summarizer import build_daily_summary
from helio.core.config import settings
from helio.db.models import System
from helio.db.session import AsyncSessionLocal
from helio.ingestion.enphase_client import EnphaseClient
from helio.ingestion.irradiance_client import NASAClient, NRELClient
from helio.ingestion.poller import detect_gaps, poll_intervals, poll_irradiance


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

        client = EnphaseClient(
            client_id=settings.enphase_client_id,
            client_secret=settings.enphase_client_secret,
            system_id=settings.enphase_system_id,
            access_token=settings.enphase_access_token,
            refresh_token=settings.enphase_refresh_token,
            fernet_key=settings.fernet_key,
        )
        await client.refresh_access_token()

        irr_client: NRELClient | NASAClient
        if settings.irradiance_source == "nrel":
            irr_client = NRELClient(settings.nrel_api_key)
        else:
            irr_client = NASAClient()

        start = system.install_date
        end = date.today() - timedelta(days=1)
        gaps = await detect_gaps(session, system.id, start, end)
        logger.info(
            "Backfill: {} days missing between {} and {}", len(gaps), start, end
        )

        for day in gaps:
            logger.info("Backfilling {}", day)
            try:
                await poll_intervals(session, client, system.id, day, day)
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
                await build_daily_summary(session, system.id, day)
            except Exception as exc:
                logger.error("Backfill failed for {}: {}", day, exc)
            await asyncio.sleep(0.5)

        logger.info("Backfill complete")


if __name__ == "__main__":
    asyncio.run(backfill())
