from datetime import date, timedelta

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from sqlalchemy import select

from helio.analytics.summarizer import build_daily_summary, build_monthly_summary
from helio.core.config import settings
from helio.db.models import System
from helio.db.session import AsyncSessionLocal
from helio.ingestion.enphase_client import PanelDataUnavailableError
from helio.ingestion.irradiance_client import (
    IrradianceSourceError,
    IrradianceUnavailableError,
    build_irradiance_client,
)
from helio.ingestion.poller import (
    irradiance_location,
    poll_intervals,
    poll_irradiance,
    poll_panels,
)
from helio.ingestion.tokens import TokenError, build_authenticated_client

scheduler = AsyncIOScheduler(timezone=settings.tz)


async def run_daily_poll() -> None:
    """Run the daily ingestion job: intervals, panels, irradiance, and summaries.

    Fetches yesterday's production data from Enphase, per-panel telemetry where
    the plan exposes it, irradiance from the configured source, builds the daily
    summary, and triggers a monthly summary on the first day of each month.
    Public because `make poll-now` runs the same job on demand.
    """
    yesterday = date.today() - timedelta(days=1)
    logger.info("Daily poll starting for {}", yesterday)
    failed_steps: list[str] = []

    async with AsyncSessionLocal() as session:
        system = (await session.execute(select(System).limit(1))).scalar_one_or_none()
        if system is None:
            logger.warning("No system found in DB - skipping poll")
            return

        try:
            client = await build_authenticated_client(session, system)
        except (TokenError, httpx.HTTPStatusError, ValueError) as exc:
            logger.error("Enphase authentication failed, skipping daily poll: {}", exc)
            return
        except Exception as exc:
            logger.error("Unexpected token refresh error: {}", exc)
            return

        try:
            await poll_intervals(session, client, system.id, yesterday, yesterday)
        except (RuntimeError, httpx.HTTPStatusError) as exc:
            logger.error("Interval poll failed for {}: {}", yesterday, exc)
            failed_steps.append("intervals")
        except Exception as exc:
            logger.error("Unexpected interval poll error for {}: {}", yesterday, exc)
            failed_steps.append("intervals")

        try:
            await poll_panels(session, client, system.id, yesterday)
        except PanelDataUnavailableError as exc:
            # Device-level telemetry is not part of every Enphase plan, so its
            # absence is a capability limit rather than a poll failure: one
            # warning, and it stays out of failed_steps so an install that will
            # never have panel data does not report a failing poll every day.
            logger.warning("Panel poll skipped for {}: {}", yesterday, exc)
        except (RuntimeError, httpx.HTTPStatusError) as exc:
            logger.error("Panel poll failed for {}: {}", yesterday, exc)
            failed_steps.append("panels")
        except Exception as exc:
            logger.error("Unexpected panel poll error for {}: {}", yesterday, exc)
            failed_steps.append("panels")

        location = irradiance_location(system)
        try:
            irr_client = build_irradiance_client(system.irradiance_source)
        except IrradianceSourceError as exc:
            logger.error("Irradiance skipped for {}: {}", yesterday, exc)
            failed_steps.append("irradiance")
        else:
            if location is None:
                failed_steps.append("irradiance")
            # None means the source is 'manual': rows are entered by hand, so
            # fetching nothing is the configured outcome, not a failure.
            elif irr_client is not None:
                try:
                    await poll_irradiance(
                        session,
                        irr_client,
                        system.id,
                        *location,
                        float(system.tilt_angle_deg or 30),
                        float(system.azimuth_deg or 180),
                        yesterday,
                        system.irradiance_source,
                    )
                except IrradianceUnavailableError as exc:
                    # No row is written, so the day stays a gap a later backfill
                    # can fill once the source publishes the measurement.
                    logger.warning(
                        "No irradiance available for {}, left for backfill: {}",
                        yesterday,
                        exc,
                    )
                    failed_steps.append("irradiance")
                except httpx.HTTPStatusError as exc:
                    logger.error("Irradiance poll failed for {}: {}", yesterday, exc)
                    failed_steps.append("irradiance")
                except Exception as exc:
                    logger.error(
                        "Unexpected irradiance poll error for {}: {}", yesterday, exc
                    )
                    failed_steps.append("irradiance")

        try:
            await build_daily_summary(session, system.id, yesterday)
        except (RuntimeError, ValueError) as exc:
            logger.error("Daily summary build failed for {}: {}", yesterday, exc)
            failed_steps.append("daily_summary")
        except Exception as exc:
            logger.error("Unexpected daily summary error for {}: {}", yesterday, exc)
            failed_steps.append("daily_summary")

        if yesterday.day == 1:
            prev_month = (yesterday - timedelta(days=1)).replace(day=1)
            try:
                await build_monthly_summary(session, system.id, prev_month, system)
            except (RuntimeError, ValueError) as exc:
                logger.error("Monthly summary build failed for {}: {}", prev_month, exc)
                failed_steps.append("monthly_summary")
            except Exception as exc:
                logger.error(
                    "Unexpected monthly summary error for {}: {}", prev_month, exc
                )
                failed_steps.append("monthly_summary")

    if failed_steps:
        logger.warning(
            "Daily poll completed with failures for {}: {}",
            yesterday,
            ", ".join(failed_steps),
        )
    else:
        logger.info("Daily poll complete for {}", yesterday)


def start_scheduler() -> None:
    """Register cron jobs and start the APScheduler instance."""
    scheduler.add_job(
        run_daily_poll,
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
