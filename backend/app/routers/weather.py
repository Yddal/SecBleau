from __future__ import annotations

import json as json_mod
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.area import Area
from ..models.dryness import DrynessScore  # for avg dryness score
from ..models.weather import WeatherReading

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/weather", tags=["weather"])

CLUSTERS_CACHE_PATH = Path("/app/data/boolder-data/clusters.geojson")


def _make_tz_aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@router.get("/conditions")
async def get_conditions(db: AsyncSession = Depends(get_db)):
    """
    Per-cluster weather summary for the last 72 h.
    Returns precipitation history, current conditions, and drying factors
    used by the physics model.
    """
    if not CLUSTERS_CACHE_PATH.exists():
        return {"generated_at": datetime.now(timezone.utc).isoformat(), "clusters": []}

    data = json_mod.loads(CLUSTERS_CACHE_PATH.read_text(encoding="utf-8"))

    now = datetime.now(timezone.utc)
    cutoff_72h = now - timedelta(hours=72)
    cutoff_48h = now - timedelta(hours=48)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d  = now - timedelta(days=7)
    RAIN_THRESHOLD = 0.1  # mm/h — matches dryness model

    result = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        sw_lat = float(props.get("southWestLat", 0))
        sw_lon = float(props.get("southWestLon", 0))
        ne_lat = float(props.get("northEastLat", 0))
        ne_lon = float(props.get("northEastLon", 0))
        name = props.get("name", "")
        center_lat = round((sw_lat + ne_lat) / 2, 4)
        center_lon = round((sw_lon + ne_lon) / 2, 4)

        # Areas in cluster bbox
        area_result = await db.execute(
            select(Area.id).where(
                Area.lat >= sw_lat, Area.lat <= ne_lat,
                Area.lon >= sw_lon, Area.lon <= ne_lon,
            )
        )
        area_ids = [r.id for r in area_result.all()]
        if not area_ids:
            continue

        # Hourly precipitation averaged across areas
        # Hourly precipitation over 7 days — used for hours_since_rain and chart
        hourly_result = await db.execute(
            select(
                func.date_trunc("hour", WeatherReading.recorded_at).label("hour"),
                func.avg(WeatherReading.precipitation_mm).label("avg_mm"),
            )
            .where(
                WeatherReading.area_id.in_(area_ids),
                WeatherReading.recorded_at >= cutoff_7d,
                WeatherReading.precipitation_mm.isnot(None),
            )
            .group_by(text("1"))
            .order_by(text("1"))
        )
        hourly_rows = hourly_result.all()

        # Rain totals — past observations only (exclude forecast rows > now)
        rain_72h = round(sum(
            float(r.avg_mm or 0) for r in hourly_rows
            if cutoff_72h <= _make_tz_aware(r.hour) <= now
        ), 2)
        rain_48h = round(sum(
            float(r.avg_mm or 0) for r in hourly_rows
            if cutoff_48h <= _make_tz_aware(r.hour) <= now
        ), 2)
        rain_24h = round(sum(
            float(r.avg_mm or 0) for r in hourly_rows
            if cutoff_24h <= _make_tz_aware(r.hour) <= now
        ), 2)

        # hours_since_rain — most recent *past* hour with avg precipitation >= threshold
        last_rain_hour = None
        last_rain_mm_val = None
        for row in reversed(list(hourly_rows)):
            if _make_tz_aware(row.hour) > now:
                continue  # skip forecast rows
            if float(row.avg_mm or 0) >= RAIN_THRESHOLD:
                last_rain_hour = _make_tz_aware(row.hour)
                last_rain_mm_val = round(float(row.avg_mm), 2)
                break
        hours_since_rain = round((now - last_rain_hour).total_seconds() / 3600, 1) if last_rain_hour else None

        # Chart shows only last 72 h
        hourly_rain = [
            {"hour": _make_tz_aware(r.hour).isoformat(), "mm": round(float(r.avg_mm or 0), 2)}
            for r in hourly_rows
            if _make_tz_aware(r.hour) >= cutoff_72h
        ]

        # Most recent *past* weather reading for current conditions (exclude forecast rows)
        latest_result = await db.execute(
            select(WeatherReading)
            .where(
                WeatherReading.area_id.in_(area_ids),
                WeatherReading.recorded_at <= now,
            )
            .order_by(WeatherReading.recorded_at.desc())
            .limit(1)
        )
        latest = latest_result.scalar_one_or_none()

        # Latest dryness score per area (DISTINCT ON avoids averaging stale scores)
        score_result = await db.execute(text("""
            SELECT DISTINCT ON (area_id) score
            FROM dryness_scores
            WHERE area_id = ANY(:ids)
              AND boulder_id IS NULL
            ORDER BY area_id, computed_at DESC
        """), {"ids": area_ids})
        scores = [r.score for r in score_result if r.score is not None]

        data_last_updated = _make_tz_aware(latest.recorded_at) if latest else None
        data_next_update = (data_last_updated + timedelta(hours=1)) if data_last_updated else None

        # Meteoblue history URL — format: {lat}N{lon}E  (Fontainebleau is always N/E)
        lat_str = f"{abs(center_lat):.3f}N"
        lon_str = f"{abs(center_lon):.3f}E"
        meteoblue_url = f"https://www.meteoblue.com/en/weather/historyclimate/weatherarchive/{lat_str}{lon_str}"

        result.append({
            "name": name,
            "area_count": len(area_ids),
            "center_lat": center_lat,
            "center_lon": center_lon,
            "dryness_score": round(sum(scores) / len(scores), 3) if scores else None,
            "hours_since_rain": hours_since_rain,
            "last_rain_mm": last_rain_mm_val,
            "rain_72h_mm": rain_72h,
            "rain_48h_mm": rain_48h,
            "rain_24h_mm": rain_24h,
            "temperature_c": latest.temperature_c if latest else None,
            "humidity_pct": latest.humidity_pct if latest else None,
            "wind_speed_ms": latest.wind_speed_ms if latest else None,
            "solar_radiation_wm2": latest.solar_radiation_wm2 if latest else None,
            "hourly_rain": hourly_rain,
            "data_last_updated_at": data_last_updated.isoformat() if data_last_updated else None,
            "data_next_update_at": data_next_update.isoformat() if data_next_update else None,
            "source_url": meteoblue_url,
        })

    return JSONResponse(
        content={"generated_at": now.isoformat(), "clusters": result},
        headers={"Cache-Control": "public, max-age=300, stale-while-revalidate=3300"},
    )
