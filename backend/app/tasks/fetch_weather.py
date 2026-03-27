"""Fetch hourly weather from Open-Meteo for all areas and store in DB."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.area import Area
from ..models.weather import WeatherReading
from ..services.open_meteo import fetch_weather, parse_weather_snapshots
from ..config import get_settings

logger = logging.getLogger(__name__)

# Batch size — stay well under Open-Meteo's 600 calls/min free limit
BATCH_SIZE = 10
BATCH_DELAY_SEC = 2.0


async def fetch_weather_for_all_areas(db: AsyncSession) -> int:
    """
    Fetch weather for every area in the database.
    Processes areas in batches to respect rate limits.
    Returns the number of areas successfully updated.
    """
    settings = get_settings()
    result = await db.execute(select(Area.id, Area.lat, Area.lon))
    areas = result.all()

    if not areas:
        logger.warning("No areas in DB — run boolder_import.py first")
        return 0

    logger.info("Fetching weather for %d areas", len(areas))
    updated = 0

    for i in range(0, len(areas), BATCH_SIZE):
        batch = areas[i : i + BATCH_SIZE]
        tasks = [
            _fetch_and_store(db, area_id, lat, lon, settings)
            for area_id, lat, lon in batch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for j, r in enumerate(results):
            if isinstance(r, Exception):
                area_id = batch[j][0]
                logger.error("Weather fetch failed for area %d: %s", area_id, r)
            else:
                updated += 1

        if i + BATCH_SIZE < len(areas):
            await asyncio.sleep(BATCH_DELAY_SEC)

    await db.commit()
    logger.info("Weather fetch complete: %d/%d areas updated", updated, len(areas))
    return updated


async def _fetch_and_store(
    db: AsyncSession,
    area_id: int,
    lat: float,
    lon: float,
    settings,
) -> None:
    raw = await fetch_weather(
        lat=lat,
        lon=lon,
        past_days=settings.weather_history_days,
        forecast_days=settings.weather_forecast_days,
    )

    snapshots = parse_weather_snapshots(raw)
    now = datetime.now(timezone.utc)

    # Pre-load all existing timestamps for this area in one query
    existing_result = await db.execute(
        select(WeatherReading.recorded_at).where(
            WeatherReading.area_id == area_id,
            WeatherReading.source == "open_meteo",
        )
    )
    existing_timestamps = {row.recorded_at for row in existing_result}

    # Only insert hours we don't already have
    for snap in snapshots:
        if snap.recorded_at in existing_timestamps:
            continue

        reading = WeatherReading(
            area_id=area_id,
            source="open_meteo",
            recorded_at=snap.recorded_at,
            temperature_c=snap.temperature_c,
            humidity_pct=snap.humidity_pct,
            precipitation_mm=snap.precipitation_mm,
            wind_speed_ms=snap.wind_speed_ms,
            solar_radiation_wm2=snap.solar_radiation_wm2,
            raw_response=None,  # skip storing full response to save space
        )
        db.add(reading)
