"""
SecBleau — FastAPI application entry point.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import engine, Base

# Import models so SQLAlchemy registers them before create_all
from .models import Area, Boulder, WeatherReading, DrynessScore, UserReport, ModelParam  # noqa: F401

from .routers import areas, boulders, weather, reports
from .tasks.scheduler import create_scheduler
from .tasks.fetch_weather import fetch_weather_for_all_areas
from .tasks.update_scores import recompute_all_dryness_scores

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("SecBleau starting — environment: %s", settings.environment)

    # Create DB tables (Alembic handles migrations in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")

    # Start scheduler
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    # Run an immediate fetch + score compute so scores are never stale after restart
    logger.info("Running startup weather fetch and score computation...")
    from .database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await fetch_weather_for_all_areas(db)
    async with AsyncSessionLocal() as db:
        await recompute_all_dryness_scores(db)
    logger.info("Startup fetch and score computation complete")

    yield

    # Shutdown
    scheduler.shutdown(wait=False)
    await engine.dispose()
    logger.info("SecBleau shut down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="SecBleau API",
        description="Fontainebleau bouldering dryness prediction",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(areas.router, prefix="/api/v1")
    app.include_router(boulders.router, prefix="/api/v1")
    app.include_router(weather.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")

    @app.get("/api/health")
    async def health():
        from .tasks.scheduler import get_scheduler
        sched = get_scheduler()
        scheduler_ok = sched is not None and sched.running
        jobs = [j.id for j in sched.get_jobs()] if scheduler_ok else []
        return {
            "status": "ok" if scheduler_ok else "degraded",
            "service": "secbleau",
            "scheduler": "running" if scheduler_ok else "stopped",
            "jobs": jobs,
        }

    return app


app = create_app()
