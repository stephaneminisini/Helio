from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from sqlalchemy import select

from helio.analytics.summarizer import build_daily_summary, build_monthly_summary
from helio.core.config import settings
from helio.db.models import System
from helio.db.session import AsyncSessionLocal
from helio.ingestion.enphase_client import EnphaseClient
from helio.ingestion.irradiance_client import NASAClient, NRELClient
from helio.ingestion.poller import poll_intervals, poll_irradiance

scheduler = AsyncIOScheduler(timezone=settings.tz)


async def _daily_poll() -> None:
    """Run the daily data ingestion job: intervals, irradiance, and summary rebuild.

    Fetches yesterday's production data from Enphase, irradiance from the configured
    source, builds the daily summary, and triggers a monthly summary on the first
    day of each month.
    """
    yesterday = date.today() - timedelta(days=1)
    logger.info("Daily poll starting for {}", yesterday)

    async with AsyncSessionLocal() as session:
        system = (await session.execute(select(System).limit(1))).scalar_one_or_none()
        if system is None:
            logger.warning("No system found in DB - skipping poll")
            return

        client = EnphaseClient(
            client_id=settings.enphase_client_id,
            client_secret=settings.enphase_client_secret,
            system_id=settings.enphase_system_id,
            access_token=settings.enphase_access_token,
            refresh_token=settings.enphase_refresh_token,
            fernet_key=settings.fernet_key,
        )

        try:
            await client.refresh_access_token()
        except Exception as exc:
            logger.error("Token refresh failed, skipping daily poll: {}", exc)
            return

        try:
            await poll_intervals(session, client, system.id, yesterday, yesterday)
        except Exception as exc:
            logger.error("Interval poll failed for {}: {}", yesterday, exc)

        irr_client: NRELClient | NASAClient
        if settings.irradiance_source == "nrel":
            irr_client = NRELClient(api_key=settings.nrel_api_key)
        else:
            irr_client = NASAClient()

        try:
            await poll_irradiance(
                session,
                irr_client,
                system.id,
                float(system.latitude or 0),
                float(system.longitude or 0),
                float(system.tilt_angle_deg or 30),
                float(system.azimuth_deg or 180),
                yesterday,
                settings.irradiance_source,
            )
        except Exception as exc:
            logger.error("Irradiance poll failed for {}: {}", yesterday, exc)

        try:
            await build_daily_summary(session, system.id, yesterday)
        except Exception as exc:
            logger.error("Daily summary build failed for {}: {}", yesterday, exc)

        if yesterday.day == 1:
            prev_month = (yesterday - timedelta(days=1)).replace(day=1)
            try:
                await build_monthly_summary(session, system.id, prev_month, system)
            except Exception as exc:
                logger.error("Monthly summary build failed for {}: {}", prev_month, exc)

    logger.info("Daily poll complete for {}", yesterday)


def start_scheduler() -> None:
    """Register cron jobs and start the APScheduler instance."""
    scheduler.add_job(
        _daily_poll,
        "cron",
        hour=settings.poll_hour,
        minute=settings.poll_minute,
        id="daily_poll",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started - daily poll at {:02d}:{:02d} {}",
        settings.poll_hour,
        settings.poll_minute,
        settings.tz,
    )
