from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.area import Area
from ..models.boulder import Boulder
from ..models.dryness import DrynessScore
from ..models.model_params import ModelParam
from ..models.report import UserReport
from ..schemas.boulder import BoulderFeatureCollection, BoulderGeoJSON, BoulderProperties, BoulderDetail, RecentReport
from ..schemas.report import BoulderReportIn, ReportOut
from ..services.bayesian import update_boulder_params, BOULDER_MULTIPLIER_PRIOR_VAR
from ..config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["boulders"])


def _session_hash(request: Request) -> str:
    raw = f"{request.client.host}:{request.headers.get('user-agent', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _confidence_from_variance(posterior_var: float, initial_var: float) -> float:
    """Replicate compute_confidence inline to avoid one DB round-trip per boulder."""
    ratio = posterior_var / initial_var if initial_var > 0 else 1.0
    return round(max(0.0, min(1.0, 1.0 - ratio * 0.7)), 3)


@router.get("/areas/{area_id}/boulders", response_model=BoulderFeatureCollection)
async def list_area_boulders(
    area_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    GeoJSON FeatureCollection of boulders in an area, with dryness scores.
    All data loaded in batch queries — no N+1 regardless of boulder count.
    """
    result = await db.execute(select(Area).where(Area.id == area_id))
    area = result.scalar_one_or_none()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    boulders_result = await db.execute(
        select(Boulder).where(Boulder.area_id == area_id)
    )
    boulders = boulders_result.scalars().all()
    if not boulders:
        return BoulderFeatureCollection(features=[])

    boulder_ids = [b.id for b in boulders]
    cutoff_48h = datetime.now(timezone.utc) - timedelta(hours=48)

    # ── Batch: latest score per boulder (DISTINCT ON) ────────────────────────
    scores_result = await db.execute(text("""
        SELECT DISTINCT ON (boulder_id)
            boulder_id, score, confidence, is_estimated,
            hours_since_rain, last_rain_at
        FROM dryness_scores
        WHERE boulder_id = ANY(:ids)
        ORDER BY boulder_id, computed_at DESC
    """), {"ids": boulder_ids})
    scores_by_boulder = {row.boulder_id: row for row in scores_result}

    # ── Area score fallback (single query) ───────────────────────────────────
    area_score_result = await db.execute(
        select(DrynessScore)
        .where(DrynessScore.area_id == area_id, DrynessScore.boulder_id == None)
        .order_by(DrynessScore.computed_at.desc())
        .limit(1)
    )
    area_score = area_score_result.scalar_one_or_none()

    # ── Batch: recent report count per boulder (last 48h) ────────────────────
    recent_result = await db.execute(
        select(UserReport.boulder_id, func.count(UserReport.id).label("cnt"))
        .where(
            UserReport.boulder_id.in_(boulder_ids),
            UserReport.reported_at >= cutoff_48h,
            UserReport.is_valid == True,
        )
        .group_by(UserReport.boulder_id)
    )
    recent_by_boulder = {row.boulder_id: row.cnt for row in recent_result}

    # ── Batch: total report count per boulder ────────────────────────────────
    total_result = await db.execute(
        select(UserReport.boulder_id, func.count(UserReport.id).label("cnt"))
        .where(
            UserReport.boulder_id.in_(boulder_ids),
            UserReport.is_valid == True,
        )
        .group_by(UserReport.boulder_id)
    )
    total_by_boulder = {row.boulder_id: row.cnt for row in total_result}

    # ── Area recent report count (single query) ──────────────────────────────
    area_recent_result = await db.execute(
        select(func.count(UserReport.id)).where(
            UserReport.area_id == area_id,
            UserReport.report_level == "area",
            UserReport.reported_at >= cutoff_48h,
            UserReport.is_valid == True,
        )
    )
    area_recent = area_recent_result.scalar() or 0

    # ── Batch: model params for confidence (all boulders, one query) ─────────
    params_result = await db.execute(
        select(ModelParam).where(
            ModelParam.entity_type == "boulder",
            ModelParam.entity_id.in_(boulder_ids),
            ModelParam.param_key == "drying_rate_multiplier",
        )
    )
    params_by_boulder = {p.entity_id: p for p in params_result.scalars().all()}

    # ── Build features (pure dict lookups, zero DB queries) ──────────────────
    features = []
    for boulder in boulders:
        s = scores_by_boulder.get(boulder.id)
        if s is None:
            s = area_score  # estimated from area

        param = params_by_boulder.get(boulder.id)
        if param:
            confidence = _confidence_from_variance(param.posterior_variance, BOULDER_MULTIPLIER_PRIOR_VAR)
        else:
            confidence = 0.3  # prior default — no reports yet

        has_recent = (recent_by_boulder.get(boulder.id, 0) > 0) or (area_recent > 0)
        total_reports = total_by_boulder.get(boulder.id, 0)
        is_estimated = s.is_estimated if s else True

        props = BoulderProperties(
            id=boulder.id,
            name=boulder.name,
            grade=boulder.grade,
            area_id=area_id,
            area_name=area.name,
            dryness_score=s.score if s else None,
            confidence=confidence,
            is_estimated=is_estimated,
            has_recent_reports=has_recent,
            hours_since_rain=s.hours_since_rain if s else None,
            last_rain_at=s.last_rain_at if s else None,
            report_count=total_reports,
        )

        features.append(BoulderGeoJSON(
            geometry={"type": "Point", "coordinates": [boulder.lon, boulder.lat]},
            properties=props,
        ))

    collection = BoulderFeatureCollection(features=features)
    return JSONResponse(
        content=collection.model_dump(mode="json"),
        headers={"Cache-Control": "public, max-age=60, stale-while-revalidate=120"},
    )


@router.get("/boulders/search")
async def search_boulders(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Search boulders by name across all areas.
    Returns id, name, grade, area_name, lat, lon for map fly-to.
    """
    result = await db.execute(
        select(
            Boulder.id,
            Boulder.name,
            Boulder.grade,
            Boulder.lat,
            Boulder.lon,
            Boulder.area_id,
            Area.name.label("area_name"),
        )
        .join(Area, Boulder.area_id == Area.id)
        .where(Boulder.name.ilike(f"%{q}%"))
        .order_by(Boulder.name)
        .limit(limit)
    )
    rows = result.all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "grade": r.grade,
            "lat": r.lat,
            "lon": r.lon,
            "area_id": r.area_id,
            "area_name": r.area_name,
        }
        for r in rows
    ]


@router.get("/boulders/{boulder_id}", response_model=BoulderDetail)
async def get_boulder(boulder_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Boulder).where(Boulder.id == boulder_id))
    boulder = result.scalar_one_or_none()
    if not boulder:
        raise HTTPException(status_code=404, detail="Boulder not found")

    area_result = await db.execute(select(Area).where(Area.id == boulder.area_id))
    area = area_result.scalar_one_or_none()

    score_result = await db.execute(
        select(DrynessScore)
        .where(DrynessScore.boulder_id == boulder_id)
        .order_by(DrynessScore.computed_at.desc())
        .limit(1)
    )
    score = score_result.scalar_one_or_none()

    cutoff_48h = datetime.now(timezone.utc) - timedelta(hours=48)
    recent_result = await db.execute(
        select(UserReport)
        .where(UserReport.boulder_id == boulder_id, UserReport.is_valid == True)
        .order_by(UserReport.reported_at.desc())
        .limit(10)
    )
    recent_reports = recent_result.scalars().all()
    has_recent = any(r.reported_at >= cutoff_48h for r in recent_reports)

    param_result = await db.execute(
        select(ModelParam).where(
            ModelParam.entity_type == "boulder",
            ModelParam.entity_id == boulder_id,
            ModelParam.param_key == "drying_rate_multiplier",
        )
    )
    param = param_result.scalar_one_or_none()
    confidence = (
        _confidence_from_variance(param.posterior_variance, BOULDER_MULTIPLIER_PRIOR_VAR)
        if param else 0.3
    )

    return BoulderDetail(
        id=boulder.id,
        name=boulder.name,
        grade=boulder.grade,
        lat=boulder.lat,
        lon=boulder.lon,
        area_id=boulder.area_id,
        area_name=area.name if area else None,
        dryness_score=score.score if score else None,
        confidence=confidence,
        is_estimated=score.is_estimated if score else True,
        has_recent_reports=has_recent,
        hours_since_rain=score.hours_since_rain if score else None,
        last_rain_at=score.last_rain_at if score else None,
        recent_reports=[
            RecentReport(
                reported_at=r.reported_at,
                condition=r.condition,
                report_level=r.report_level,
            )
            for r in recent_reports
        ],
    )


@router.post("/boulders/{boulder_id}/reports", response_model=ReportOut)
async def submit_boulder_report(
    boulder_id: int,
    body: BoulderReportIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Submit a wet/drying/climbable report for a specific boulder."""
    result = await db.execute(select(Boulder).where(Boulder.id == boulder_id))
    boulder = result.scalar_one_or_none()
    if not boulder:
        raise HTTPException(status_code=404, detail="Boulder not found")

    session_hash = _session_hash(request)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=4)
    existing = await db.execute(
        select(UserReport).where(
            UserReport.boulder_id == boulder_id,
            UserReport.session_hash == session_hash,
            UserReport.reported_at >= cutoff,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=429, detail="You can report this boulder once every 4 hours.")

    score_result = await db.execute(
        select(DrynessScore)
        .where(DrynessScore.boulder_id == boulder_id)
        .order_by(DrynessScore.computed_at.desc())
        .limit(1)
    )
    current_score = score_result.scalar_one_or_none()
    physics_score = current_score.physics_score if current_score else 0.5

    since_7d = datetime.now(timezone.utc) - timedelta(days=7)
    recent_result = await db.execute(
        select(UserReport).where(
            UserReport.boulder_id == boulder_id,
            UserReport.reported_at >= since_7d,
            UserReport.is_valid == True,
        ).order_by(UserReport.reported_at.desc()).limit(20)
    )
    recent_reports = recent_result.scalars().all()

    now = datetime.now(timezone.utc)
    report = UserReport(
        report_level="boulder",
        boulder_id=boulder_id,
        area_id=boulder.area_id,
        reported_at=now,
        condition=body.condition,
        predicted_score=physics_score,
        session_hash=session_hash,
        notes=body.notes,
        is_valid=True,
    )
    db.add(report)
    await db.flush()

    await update_boulder_params(
        db, boulder_id, boulder.area_id, body.condition, physics_score, list(recent_reports)
    )

    settings = get_settings()
    total_result = await db.execute(
        select(func.count(UserReport.id)).where(
            UserReport.boulder_id == boulder_id,
            UserReport.is_valid == True,
        )
    )
    total = total_result.scalar() or 0
    if total >= settings.min_reports_for_full_opacity:
        boulder.has_direct_data = True

    await db.commit()
    await db.refresh(report)

    return ReportOut(
        id=report.id,
        report_level="boulder",
        condition=body.condition,
        reported_at=now,
    )
