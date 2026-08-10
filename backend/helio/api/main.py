from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from apscheduler.schedulers.base import SchedulerAlreadyRunningError
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from helio.api.routes.efficiency import router as efficiency_router
from helio.api.routes.overview import router as overview_router
from helio.api.routes.settings import router as settings_router
from helio.api.routes.status import router as status_router
from helio.core.config import settings
from helio.ingestion.scheduler import scheduler, start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """FastAPI lifespan context manager - startup and shutdown hooks.

    Args:
        app: The FastAPI application instance.

    Yields:
        None during the application's lifetime.
    """
    try:
        start_scheduler()
    except SchedulerAlreadyRunningError:
        logger.warning("Scheduler already running")
    except Exception as exc:
        logger.error("Scheduler failed to start: {}", exc)
        raise
    logger.info("Helio Monitor API starting")
    yield
    logger.info("Helio Monitor API shutting down")
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Helio Monitor API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)

app.include_router(overview_router, prefix="/api")
app.include_router(efficiency_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(status_router, prefix="/api")


@app.get("/api/health")
async def health() -> dict:
    """Health check endpoint.

    Returns:
        Status dict with key 'status' = 'ok'.
    """
    return {"status": "ok"}
