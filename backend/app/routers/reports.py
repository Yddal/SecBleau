from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.area import Area
from ..models.boulder import Boulder
from ..models.report import UserReport

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/recent")
async def get_recent_reports(
    hours: int = Query(48, ge=1, le=168),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """
    Recent condition reports for the live status feed on the Analysis page.
    Returns valid reports from the last N hours with area and boulder names,
    sorted newest-first.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    result = await db.execute(
        select(
            UserReport.id,
            UserReport.report_level,
            UserReport.condition,
            UserReport.reported_at,
            UserReport.notes,
            UserReport.area_id,
            UserReport.boulder_id,
            Area.name.label("area_name"),
            Boulder.name.label("boulder_name"),
        )
        .join(Area, UserReport.area_id == Area.id)
        .outerjoin(Boulder, UserReport.boulder_id == Boulder.id)
        .where(
            UserReport.reported_at >= cutoff,
            UserReport.is_valid == True,
        )
        .order_by(UserReport.reported_at.desc())
        .limit(limit)
    )
    rows = result.all()

    return JSONResponse(
        content={
            "generated_at": now.isoformat(),
            "reports": [
                {
                    "id":           r.id,
                    "report_level": r.report_level,
                    "condition":    r.condition,
                    "reported_at":  r.reported_at.isoformat(),
                    "notes":        r.notes,
                    "area_id":      r.area_id,
                    "area_name":    r.area_name,
                    "boulder_id":   r.boulder_id,
                    "boulder_name": r.boulder_name,
                }
                for r in rows
            ],
        },
        headers={"Cache-Control": "no-store"},
    )
