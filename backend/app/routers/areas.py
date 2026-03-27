from __future__ import annotations

import hashlib
import json as json_mod
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.area import Area
from ..models.boulder import Boulder
from ..models.dryness import DrynessScore
from ..models.report import UserReport, AREA_CONDITION_SCORES
from ..models.weather import WeatherReading
from ..schemas.area import AreaFeatureCollection, AreaGeoJSON, AreaProperties, AreaDetail, WeatherSummary
from ..schemas.report import AreaReportIn, ReportOut
from ..services.bayesian import update_area_params, get_or_create_param
from ..config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/areas", tags=["areas"])


def _session_hash(request: Request) -> str:
    """Create an anonymised session fingerprint — no PII stored."""
    raw = f"{request.client.host}:{request.headers.get('user-agent', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()


@router.get("", response_model=AreaFeatureCollection)
async def list_areas(
    db: AsyncSession = Depends(get_db),
):
    """
    GeoJSON FeatureCollection of all areas with latest dryness scores.
    Used for the zoomed-out map layer.
    All per-area data loaded in batch queries (no N+1).
    """
    result = await db.execute(select(Area))
    areas = result.scalars().all()
    if not areas:
        return AreaFeatureCollection(features=[])

    area_ids = [a.id for a in areas]

    # ── Batch: convex hull per area from boulder positions ──────────────────
    hull_result = await db.execute(text("""
        SELECT
            area_id,
            ST_AsGeoJSON(
                ST_Buffer(
                    ST_ConvexHull(ST_Collect(geom)),
                    0.0005,
                    'quad_segs=6'
                )
            ) AS hull
        FROM boulders
        WHERE geom IS NOT NULL
        GROUP BY area_id
    """))
    hull_by_area: dict[int, dict] = {}
    for row in hull_result:
        if row.hull:
            import json as _json
            hull_by_area[row.area_id] = _json.loads(row.hull)

    # ── Batch: latest dryness score per area (DISTINCT ON = one pass) ───────
    scores_result = await db.execute(text("""
        SELECT DISTINCT ON (area_id)
            area_id, score, confidence, is_estimated,
            hours_since_rain, last_rain_at, last_rain_mm
        FROM dryness_scores
        WHERE boulder_id IS NULL
          AND area_id = ANY(:ids)
        ORDER BY area_id, computed_at DESC
    """), {"ids": area_ids})
    scores_by_area = {row.area_id: row for row in scores_result}

    # ── Batch: boulder count per area ────────────────────────────────────────
    counts_result = await db.execute(
        select(Boulder.area_id, func.count(Boulder.id).label("cnt"))
        .where(Boulder.area_id.in_(area_ids))
        .group_by(Boulder.area_id)
    )
    counts_by_area = {row.area_id: row.cnt for row in counts_result}

    # ── Batch: latest weather per area (DISTINCT ON) ─────────────────────────
    weather_result = await db.execute(text("""
        SELECT DISTINCT ON (area_id)
            area_id, temperature_c, humidity_pct, wind_speed_ms
        FROM weather_readings
        WHERE area_id = ANY(:ids)
        ORDER BY area_id, recorded_at DESC
    """), {"ids": area_ids})
    weather_by_area = {row.area_id: row for row in weather_result}

    # ── Build features ───────────────────────────────────────────────────────
    features = []
    for area in areas:
        s = scores_by_area.get(area.id)
        w = weather_by_area.get(area.id)

        props = AreaProperties(
            id=area.id,
            name=area.name,
            slug=area.slug,
            dryness_score=s.score if s else None,
            confidence=s.confidence if s else 0.0,
            is_estimated=s.is_estimated if s else True,
            hours_since_rain=s.hours_since_rain if s else None,
            last_rain_at=s.last_rain_at if s else None,
            last_rain_mm=s.last_rain_mm if s else None,
            boulder_count=counts_by_area.get(area.id, 0),
            aspect=area.aspect,
            elevation_m=area.elevation_m,
            temperature_c=w.temperature_c if w else None,
            humidity_pct=w.humidity_pct if w else None,
            wind_speed_ms=w.wind_speed_ms if w else None,
            precipitation_last_24h_mm=None,
            bbox_sw_lon=area.bbox_sw_lon,
            bbox_sw_lat=area.bbox_sw_lat,
            bbox_ne_lon=area.bbox_ne_lon,
            bbox_ne_lat=area.bbox_ne_lat,
            hull=hull_by_area.get(area.id),
        )

        features.append(AreaGeoJSON(
            geometry={"type": "Point", "coordinates": [area.lon, area.lat]},
            properties=props,
        ))

    collection = AreaFeatureCollection(features=features)
    return JSONResponse(
        content=collection.model_dump(mode="json"),
        headers={"Cache-Control": "public, max-age=300, stale-while-revalidate=600"},
    )


CLUSTERS_CACHE_PATH = Path("/app/data/boolder-data/clusters.geojson")


@router.get("/clusters")
async def get_clusters(db: AsyncSession = Depends(get_db)):
    """
    Returns clusters.geojson enriched with average dryness score.
    Clusters are the major sectors (Trois Pignons, Franchard, etc.)
    """
    if not CLUSTERS_CACHE_PATH.exists():
        return {"type": "FeatureCollection", "features": []}

    data = json_mod.loads(CLUSTERS_CACHE_PATH.read_text(encoding="utf-8"))

    enriched = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        sw_lat = float(props.get("southWestLat", 0))
        sw_lon = float(props.get("southWestLon", 0))
        ne_lat = float(props.get("northEastLat", 0))
        ne_lon = float(props.get("northEastLon", 0))

        area_result = await db.execute(
            select(Area.id, DrynessScore.score)
            .outerjoin(DrynessScore, and_(
                DrynessScore.area_id == Area.id,
                DrynessScore.boulder_id == None,
            ))
            .where(
                Area.lat >= sw_lat,
                Area.lat <= ne_lat,
                Area.lon >= sw_lon,
                Area.lon <= ne_lon,
            )
            .order_by(DrynessScore.computed_at.desc())
        )
        rows = area_result.all()
        scores = [r.score for r in rows if r.score is not None]
        avg_score = sum(scores) / len(scores) if scores else None

        # Compute convex-hull blob from area centre points using PostGIS
        hull_result = await db.execute(
            text("""
                SELECT ST_AsGeoJSON(
                    ST_Buffer(
                        ST_ConvexHull(ST_Collect(ST_MakePoint(lon, lat))),
                        0.004,
                        'quad_segs=6'
                    )
                ) AS hull
                FROM areas
                WHERE lat >= :sw_lat AND lat <= :ne_lat
                  AND lon >= :sw_lon AND lon <= :ne_lon
            """),
            {"sw_lat": sw_lat, "ne_lat": ne_lat, "sw_lon": sw_lon, "ne_lon": ne_lon},
        )
        hull_row = hull_result.fetchone()
        import json as _json
        hull_geom = _json.loads(hull_row.hull) if hull_row and hull_row.hull else None

        enriched.append({
            **feat,
            "properties": {
                **props,
                "dryness_score": avg_score,
                "area_count": len(rows),
                "hull": hull_geom,
            }
        })

    return {"type": "FeatureCollection", "features": enriched}


@router.get("/{area_id}", response_model=AreaDetail)
async def get_area(area_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Area).where(Area.id == area_id))
    area = result.scalar_one_or_none()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    score_result = await db.execute(
        select(DrynessScore)
        .where(DrynessScore.area_id == area_id, DrynessScore.boulder_id == None)
        .order_by(DrynessScore.computed_at.desc())
        .limit(1)
    )
    score = score_result.scalar_one_or_none()

    # Recent weather (last 48h)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    weather_result = await db.execute(
        select(WeatherReading)
        .where(WeatherReading.area_id == area_id, WeatherReading.recorded_at >= cutoff)
        .order_by(WeatherReading.recorded_at.desc())
        .limit(48)
    )
    weather_rows = weather_result.scalars().all()

    # Report count last 24h
    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    report_count_result = await db.execute(
        select(func.count(UserReport.id)).where(
            UserReport.area_id == area_id,
            UserReport.reported_at >= since_24h,
            UserReport.is_valid == True,
        )
    )
    report_count_24h = report_count_result.scalar() or 0

    from ..models.boulder import Boulder
    count_result = await db.execute(
        select(func.count(Boulder.id)).where(Boulder.area_id == area_id)
    )
    boulder_count = count_result.scalar() or 0

    return AreaDetail(
        id=area.id,
        name=area.name,
        slug=area.slug,
        lat=area.lat,
        lon=area.lon,
        aspect=area.aspect,
        shade_factor=area.shade_factor,
        canopy_factor=area.canopy_factor,
        elevation_m=area.elevation_m,
        dryness_score=score.score if score else None,
        confidence=score.confidence if score else 0.0,
        hours_since_rain=score.hours_since_rain if score else None,
        last_rain_at=score.last_rain_at if score else None,
        last_rain_mm=score.last_rain_mm if score else None,
        boulder_count=boulder_count,
        recent_weather=[
            WeatherSummary(
                recorded_at=w.recorded_at,
                temperature_c=w.temperature_c,
                humidity_pct=w.humidity_pct,
                precipitation_mm=w.precipitation_mm,
                wind_speed_ms=w.wind_speed_ms,
                solar_radiation_wm2=w.solar_radiation_wm2,
            )
            for w in weather_rows
        ],
        report_count_24h=report_count_24h,
    )


@router.post("/{area_id}/reports", response_model=ReportOut)
async def submit_area_report(
    area_id: int,
    body: AreaReportIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Submit a condition report for an entire area."""
    result = await db.execute(select(Area).where(Area.id == area_id))
    area = result.scalar_one_or_none()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    session_hash = _session_hash(request)
    settings = get_settings()

    # Rate limit: 1 area report per session per 4h
    cutoff = datetime.now(timezone.utc) - timedelta(hours=4)
    existing = await db.execute(
        select(UserReport).where(
            UserReport.area_id == area_id,
            UserReport.report_level == "area",
            UserReport.session_hash == session_hash,
            UserReport.reported_at >= cutoff,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=429, detail="You can report this area once every 4 hours.")

    # Get current physics score for Bayesian update
    score_result = await db.execute(
        select(DrynessScore)
        .where(DrynessScore.area_id == area_id, DrynessScore.boulder_id == None)
        .order_by(DrynessScore.computed_at.desc())
        .limit(1)
    )
    current_score_row = score_result.scalar_one_or_none()
    physics_score = current_score_row.physics_score if current_score_row else 0.5

    # Get recent reports for outlier detection
    since_7d = datetime.now(timezone.utc) - timedelta(days=7)
    recent_result = await db.execute(
        select(UserReport).where(
            UserReport.area_id == area_id,
            UserReport.report_level == "area",
            UserReport.reported_at >= since_7d,
            UserReport.is_valid == True,
        ).order_by(UserReport.reported_at.desc()).limit(20)
    )
    recent_reports = recent_result.scalars().all()

    now = datetime.now(timezone.utc)
    report = UserReport(
        report_level="area",
        area_id=area_id,
        boulder_id=None,
        reported_at=now,
        condition=body.condition,
        predicted_score=physics_score,
        session_hash=session_hash,
        notes=body.notes,
        is_valid=True,
    )
    db.add(report)
    await db.flush()

    # Bayesian update
    updated_offset = await update_area_params(
        db, area_id, body.condition, physics_score, list(recent_reports)
    )

    await db.commit()
    await db.refresh(report)

    return ReportOut(
        id=report.id,
        report_level="area",
        condition=body.condition,
        reported_at=now,
        updated_score=min(1.0, max(0.0, physics_score + updated_offset)),
    )
