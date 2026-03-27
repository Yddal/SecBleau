"""
APScheduler job definitions.
Registered in app lifespan (main.py).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..database import AsyncSessionLocal
from .fetch_weather import fetch_weather_for_all_areas
from .update_scores import recompute_all_dryness_scores

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler


def create_scheduler() -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="Europe/Paris")

    # Fetch weather at the top of every hour (:00)
    _scheduler.add_job(
        _run_fetch_weather,
        CronTrigger(minute=0),
        id="fetch_weather",
        name="Fetch Open-Meteo weather for all areas",
        replace_existing=True,
        misfire_grace_time=120,
    )

    # Recompute dryness scores 5 minutes after fetch (:05)
    _scheduler.add_job(
        _run_recompute_scores,
        CronTrigger(minute=5),
        id="recompute_scores",
        name="Recompute dryness scores",
        replace_existing=True,
        misfire_grace_time=120,
    )

    # Clean up old weather readings (keep last 14 days) at 3am Paris time
    _scheduler.add_job(
        _run_cleanup,
        CronTrigger(hour=3, minute=0),
        id="cleanup_old_weather",
        name="Prune old weather data",
        replace_existing=True,
    )

    return _scheduler


async def _run_fetch_weather():
    logger.info("Scheduler: starting weather fetch")
    async with AsyncSessionLocal() as db:
        await fetch_weather_for_all_areas(db)


async def _run_recompute_scores():
    logger.info("Scheduler: starting score recomputation")
    async with AsyncSessionLocal() as db:
        await recompute_all_dryness_scores(db)


async def _run_cleanup():
    from datetime import timedelta
    from sqlalchemy import delete
    from ..models.weather import WeatherReading
    from ..models.report import UserReport

    async with AsyncSessionLocal() as db:
        # Prune weather readings older than 14 days
        weather_cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        await db.execute(delete(WeatherReading).where(WeatherReading.recorded_at < weather_cutoff))

        # Prune user reports older than 1 year (GDPR / privacy notice commitment)
        report_cutoff = datetime.now(timezone.utc) - timedelta(days=365)
        await db.execute(delete(UserReport).where(UserReport.reported_at < report_cutoff))

        await db.commit()
    logger.info("Scheduler: old weather readings and reports pruned")
