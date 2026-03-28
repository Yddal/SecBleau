from __future__ import annotations

import asyncio
import hashlib
import json as json_mod
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text
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
        headers={"Cache-Control": "public, max-age=60, stale-while-revalidate=120"},
    )


AREA_CLUSTERS_PATH = Path("/app/data/area_clusters.json")


def _load_clusters() -> list[dict]:
    """Load canonical cluster definitions from area_clusters.json."""
    if not AREA_CLUSTERS_PATH.exists():
        return []
    return json_mod.loads(AREA_CLUSTERS_PATH.read_text(encoding="utf-8"))


@router.get("/clusters")
async def get_clusters(db: AsyncSession = Depends(get_db)):
    """
    GeoJSON FeatureCollection of cluster hull polygons coloured by best dryness score.
    Each cluster is defined by an explicit list of area IDs in area_clusters.json.
    """
    clusters = _load_clusters()
    if not clusters:
        return {"type": "FeatureCollection", "features": []}

    features = []
    for cluster in clusters:
        name = cluster["name"]
        area_ids = cluster["area_ids"]

        # Best dryness score across all areas in the cluster
        scores_result = await db.execute(text("""
            SELECT DISTINCT ON (area_id) score
            FROM dryness_scores
            WHERE area_id = ANY(:ids)
              AND boulder_id IS NULL
            ORDER BY area_id, computed_at DESC
        """), {"ids": area_ids})
        scores = [r.score for r in scores_result if r.score is not None]
        best_score = max(scores) if scores else None

        # Convex hull polygon buffered slightly so thin clusters don't collapse to a line
        hull_result = await db.execute(text("""
            SELECT ST_AsGeoJSON(
                ST_Buffer(
                    ST_ConvexHull(ST_Collect(ST_SetSRID(ST_MakePoint(lon, lat), 4326))),
                    0.004,
                    'quad_segs=6'
                )
            ) AS hull
            FROM areas
            WHERE id = ANY(:ids)
        """), {"ids": area_ids})
        hull_row = hull_result.fetchone()
        if not (hull_row and hull_row.hull):
            continue
        hull_geom = json_mod.loads(hull_row.hull)

        features.append({
            "type": "Feature",
            "geometry": hull_geom,
            "properties": {
                "name": name,
                "dryness_score": best_score,
                "area_count": len(area_ids),
            },
        })

    return {"type": "FeatureCollection", "features": features}


@router.get("/analysis")
async def get_areas_analysis(db: AsyncSession = Depends(get_db)):
    """
    Per-area analysis data for the Analysis page.
    Returns all areas grouped by cluster with dryness breakdown,
    physical characteristics, and report counts for 4h / 12h / 24h windows.
    Cluster membership is defined by area_clusters.json.
    """
    clusters = _load_clusters()

    result = await db.execute(select(Area))
    all_areas = result.scalars().all()
    now = datetime.now(timezone.utc)
    if not all_areas:
        return JSONResponse(content={"generated_at": now.isoformat(), "clusters": []})

    area_ids = [a.id for a in all_areas]
    cutoff_4h  = now - timedelta(hours=4)
    cutoff_12h = now - timedelta(hours=12)
    cutoff_24h = now - timedelta(hours=24)

    # Batch: latest dryness score per area (including breakdown fields)
    scores_result = await db.execute(text("""
        SELECT DISTINCT ON (area_id)
            area_id, score, physics_score, ml_correction, confidence, is_estimated,
            hours_since_rain, last_rain_at, last_rain_mm
        FROM dryness_scores
        WHERE boulder_id IS NULL
          AND area_id = ANY(:ids)
        ORDER BY area_id, computed_at DESC
    """), {"ids": area_ids})
    scores_by_area = {row.area_id: row for row in scores_result}

    # Batch: report counts per area across 4h / 12h / 24h windows
    counts_result = await db.execute(text("""
        SELECT
            area_id,
            COUNT(*) FILTER (WHERE reported_at >= :cut4h)  AS count_4h,
            COUNT(*) FILTER (WHERE reported_at >= :cut12h) AS count_12h,
            COUNT(*) FILTER (WHERE reported_at >= :cut24h) AS count_24h
        FROM user_reports
        WHERE area_id = ANY(:ids)
          AND is_valid = true
        GROUP BY area_id
    """), {"ids": area_ids, "cut4h": cutoff_4h, "cut12h": cutoff_12h, "cut24h": cutoff_24h})
    report_counts = {row.area_id: row for row in counts_result}

    # Batch: hourly weather per area for the last 72 h (used for charts)
    cutoff_72h = now - timedelta(hours=72)
    weather_hourly_result = await db.execute(text("""
        SELECT
            area_id,
            date_trunc('hour', recorded_at)         AS hour,
            AVG(temperature_c)::float               AS temp,
            AVG(humidity_pct)::float                AS humidity,
            AVG(wind_speed_ms)::float               AS wind,
            SUM(precipitation_mm)::float            AS precip
        FROM weather_readings
        WHERE area_id = ANY(:ids)
          AND recorded_at >= :cutoff
          AND recorded_at <= :now
        GROUP BY area_id, date_trunc('hour', recorded_at)
        ORDER BY area_id, hour ASC
    """), {"ids": area_ids, "cutoff": cutoff_72h, "now": now})
    weather_hourly: dict[int, list] = defaultdict(list)
    for row in weather_hourly_result:
        weather_hourly[row.area_id].append({
            "h":  row.hour.isoformat(),
            "t":  round(row.temp,     1) if row.temp     is not None else None,
            "hu": round(row.humidity, 1) if row.humidity is not None else None,
            "w":  round(row.wind,     2) if row.wind     is not None else None,
            "p":  round(row.precip,   2) if row.precip   is not None else None,
        })

    def _area_dict(area: Area) -> dict:
        s  = scores_by_area.get(area.id)
        rc = report_counts.get(area.id)
        return {
            "id":            area.id,
            "name":          area.name,
            "aspect":        area.aspect,
            "shade_factor":  area.shade_factor,
            "canopy_factor": area.canopy_factor,
            "elevation_m":   area.elevation_m,
            "dryness_score": s.score          if s else None,
            "physics_score": s.physics_score  if s else None,
            "ml_correction": s.ml_correction  if s else None,
            "confidence":    s.confidence     if s else 0.0,
            "is_estimated":  s.is_estimated   if s else True,
            "hours_since_rain": s.hours_since_rain if s else None,
            "last_rain_mm":     s.last_rain_mm     if s else None,
            "report_count_4h":  int(rc.count_4h)  if rc else 0,
            "report_count_12h": int(rc.count_12h) if rc else 0,
            "report_count_24h": int(rc.count_24h) if rc else 0,
            "weather_72h":      weather_hourly.get(area.id, []),
        }

    area_by_id = {a.id: a for a in all_areas}
    assigned_ids: set[int] = set()
    clusters_out = []

    for cluster in clusters:
        cluster_name = cluster["name"]
        cluster_area_ids = cluster["area_ids"]
        cluster_areas = [
            _area_dict(area_by_id[aid])
            for aid in cluster_area_ids
            if aid in area_by_id
        ]
        for aid in cluster_area_ids:
            if aid in area_by_id:
                assigned_ids.add(aid)
        if cluster_areas:
            clusters_out.append({
                "name":  cluster_name,
                "areas": sorted(cluster_areas, key=lambda x: x["name"]),
            })

    # Areas not listed in any cluster go into "Other"
    unassigned = [_area_dict(a) for a in all_areas if a.id not in assigned_ids]
    if unassigned:
        clusters_out.append({
            "name":  "Other",
            "areas": sorted(unassigned, key=lambda x: x["name"]),
        })

    return JSONResponse(
        content={"generated_at": now.isoformat(), "clusters": clusters_out},
        headers={"Cache-Control": "public, max-age=60, stale-while-revalidate=120"},
    )


_VALID_ASPECTS = {"N", "NE", "E", "SE", "S", "SW", "W", "NW", "flat"}


class AreaSettingsPatch(BaseModel):
    aspect: Optional[str] = None
    shade_factor: Optional[float] = Field(None, ge=0.0, le=1.0)
    canopy_factor: Optional[float] = Field(None, ge=0.0, le=1.0)
    elevation_m: Optional[int] = Field(None, ge=0, le=5000)


@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db)):
    """
    Returns all areas with their physical factors and current dryness scores,
    grouped by cluster — used by the /settings admin page.
    """
    clusters = _load_clusters()
    result = await db.execute(select(Area))
    all_areas = result.scalars().all()

    area_ids = [a.id for a in all_areas]
    scores_result = await db.execute(text("""
        SELECT DISTINCT ON (area_id)
            area_id, score, hours_since_rain
        FROM dryness_scores
        WHERE boulder_id IS NULL AND area_id = ANY(:ids)
        ORDER BY area_id, computed_at DESC
    """), {"ids": area_ids})
    scores_by_area = {row.area_id: row for row in scores_result}

    def _area_row(a: Area) -> dict:
        s = scores_by_area.get(a.id)
        return {
            "id": a.id,
            "name": a.name,
            "aspect": a.aspect,
            "shade_factor": a.shade_factor,
            "canopy_factor": a.canopy_factor,
            "elevation_m": a.elevation_m,
            "dryness_score": s.score if s else None,
            "hours_since_rain": s.hours_since_rain if s else None,
        }

    area_by_id = {a.id: a for a in all_areas}
    assigned_ids: set[int] = set()
    clusters_out = []

    for cluster in clusters:
        cluster_areas = [
            _area_row(area_by_id[aid])
            for aid in cluster["area_ids"]
            if aid in area_by_id
        ]
        for aid in cluster["area_ids"]:
            if aid in area_by_id:
                assigned_ids.add(aid)
        if cluster_areas:
            clusters_out.append({
                "name": cluster["name"],
                "areas": sorted(cluster_areas, key=lambda x: x["name"]),
            })

    unassigned = [_area_row(a) for a in all_areas if a.id not in assigned_ids]
    if unassigned:
        clusters_out.append({"name": "Other", "areas": sorted(unassigned, key=lambda x: x["name"])})

    return JSONResponse(content={"clusters": clusters_out})


@router.post("/{area_id}/settings")
async def update_area_settings(
    area_id: int,
    body: AreaSettingsPatch,
    db: AsyncSession = Depends(get_db),
):
    """Update physical drying factors for an area."""
    result = await db.execute(select(Area).where(Area.id == area_id))
    area = result.scalar_one_or_none()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    if body.aspect is not None:
        if body.aspect not in _VALID_ASPECTS:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid aspect '{body.aspect}'. Valid values: {', '.join(sorted(_VALID_ASPECTS))}",
            )
        area.aspect = body.aspect
    if body.shade_factor is not None:
        area.shade_factor = body.shade_factor
    if body.canopy_factor is not None:
        area.canopy_factor = body.canopy_factor
    if body.elevation_m is not None:
        area.elevation_m = body.elevation_m

    await db.commit()
    return {
        "id": area.id,
        "aspect": area.aspect,
        "shade_factor": area.shade_factor,
        "canopy_factor": area.canopy_factor,
        "elevation_m": area.elevation_m,
    }


@router.post("/recalculate")
async def recalculate_scores():
    """Trigger a background recompute of all dryness scores."""
    from ..database import AsyncSessionLocal
    from ..tasks.update_scores import recompute_all_dryness_scores

    async def _bg() -> None:
        async with AsyncSessionLocal() as db:
            await recompute_all_dryness_scores(db)
        logger.info("Manual recalculation complete")

    asyncio.create_task(_bg())
    return {"status": "started", "message": "Score recomputation started. Refresh in ~30 seconds."}


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
