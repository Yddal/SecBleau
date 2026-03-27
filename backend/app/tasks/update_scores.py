"""
Recompute dryness scores for all areas and boulders after a weather fetch.

For each area:
  1. Load last 7 days of weather readings
  2. Run moisture simulation with area-level params
  3. Upsert DrynessScore (area-level, boulder_id=None)

For each boulder in the area:
  4. Use boulder-specific params (drying_rate_multiplier) — inherit area if missing
  5. Upsert DrynessScore (boulder-level)
  6. Mark is_estimated based on whether the boulder has direct user reports
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.area import Area
from ..models.boulder import Boulder
from ..models.dryness import DrynessScore
from ..models.weather import WeatherReading
from ..services.dryness_model import (
    AreaCharacteristics,
    WeatherSnapshot,
    simulate_moisture,
    moisture_to_dryness_score,
    hours_to_climbable,
)
from ..services.bayesian import get_or_create_param, BOULDER_MULTIPLIER_PRIOR_VAR, AREA_OFFSET_PRIOR_VAR
from ..config import get_settings

logger = logging.getLogger(__name__)


async def recompute_all_dryness_scores(db: AsyncSession) -> None:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    history_cutoff = now - timedelta(days=settings.weather_history_days)

    areas_result = await db.execute(select(Area))
    areas = areas_result.scalars().all()

    # Prune old DrynessScore rows to prevent unbounded table growth.
    # Keep one extra day beyond the weather history window as a safety margin.
    retention_cutoff = now - timedelta(days=settings.weather_history_days + 1)
    await db.execute(delete(DrynessScore).where(DrynessScore.computed_at < retention_cutoff))

    for area in areas:
        # Load weather history for this area
        weather_result = await db.execute(
            select(WeatherReading)
            .where(
                WeatherReading.area_id == area.id,
                WeatherReading.recorded_at >= history_cutoff,
                WeatherReading.recorded_at <= now,
            )
            .order_by(WeatherReading.recorded_at.asc())
        )
        weather_rows = weather_result.scalars().all()

        if not weather_rows:
            continue

        history_snaps = _rows_to_snapshots(weather_rows)

        # Get area-level learned params
        area_offset_param = await get_or_create_param(db, "area", area.id, "area_drying_offset")
        area_offset = area_offset_param.posterior_mean
        area_var_ratio = area_offset_param.posterior_variance / AREA_OFFSET_PRIOR_VAR
        area_confidence = max(0.3, min(1.0, 1.0 - area_var_ratio * 0.7))

        area_chars = AreaCharacteristics(
            aspect=area.aspect,
            shade_factor=area.shade_factor or 0.5,
            canopy_factor=area.canopy_factor or 0.5,
            drying_rate_multiplier=1.0,  # area uses raw physics; multiplier is per-boulder
            area_drying_offset=area_offset,
        )

        moisture, rain_meta = simulate_moisture(history_snaps, area_chars)
        area_score = moisture_to_dryness_score(moisture, area_offset)

        # Upsert area-level score
        await _upsert_score(
            db,
            area_id=area.id,
            boulder_id=None,
            score=area_score,
            physics_score=1.0 - moisture,
            confidence=area_confidence,
            is_estimated=True,
            rain_meta=rain_meta,
            computed_at=now,
        )

        # Recompute per-boulder scores
        boulders_result = await db.execute(
            select(Boulder).where(Boulder.area_id == area.id)
        )
        boulders = boulders_result.scalars().all()

        for boulder in boulders:
            # Single DB call per boulder — area offset already known
            boulder_param = await get_or_create_param(db, "boulder", boulder.id, "drying_rate_multiplier")
            multiplier = boulder_param.posterior_mean
            # Confidence computed inline — avoids a second fetch of the same param
            b_var_ratio = boulder_param.posterior_variance / BOULDER_MULTIPLIER_PRIOR_VAR
            b_confidence = max(0.3, min(1.0, 1.0 - b_var_ratio * 0.7))

            boulder_chars = AreaCharacteristics(
                aspect=boulder.aspect or area.aspect,
                shade_factor=(boulder.shade_factor if boulder.shade_factor is not None else area.shade_factor) or 0.5,
                canopy_factor=(boulder.canopy_factor if boulder.canopy_factor is not None else area.canopy_factor) or 0.5,
                drying_rate_multiplier=multiplier,
                area_drying_offset=area_offset,
            )

            b_moisture, b_rain_meta = simulate_moisture(history_snaps, boulder_chars)
            b_score = moisture_to_dryness_score(b_moisture, area_offset)

            # is_estimated = True if boulder has no direct user reports
            is_estimated = not boulder.has_direct_data

            await _upsert_score(
                db,
                area_id=area.id,
                boulder_id=boulder.id,
                score=b_score,
                physics_score=1.0 - b_moisture,
                confidence=b_confidence,
                is_estimated=is_estimated,
                rain_meta=b_rain_meta,
                computed_at=now,
            )

    await db.commit()
    logger.info("Dryness scores recomputed for %d areas", len(areas))


async def _upsert_score(
    db: AsyncSession,
    area_id: int,
    boulder_id: int | None,
    score: float,
    physics_score: float,
    confidence: float,
    is_estimated: bool,
    rain_meta: dict,
    computed_at: datetime,
) -> None:
    entry = DrynessScore(
        area_id=area_id,
        boulder_id=boulder_id,
        computed_at=computed_at,
        score=score,
        confidence=confidence,
        is_estimated=is_estimated,
        hours_since_rain=rain_meta.get("hours_since_rain"),
        last_rain_at=rain_meta.get("last_rain_at"),
        last_rain_mm=rain_meta.get("last_rain_mm"),
        physics_score=physics_score,
        ml_correction=score - physics_score,
    )
    db.add(entry)


def _rows_to_snapshots(rows: list[WeatherReading]) -> list[WeatherSnapshot]:
    return [
        WeatherSnapshot(
            recorded_at=r.recorded_at,
            temperature_c=r.temperature_c or 10.0,
            humidity_pct=r.humidity_pct or 80.0,
            precipitation_mm=r.precipitation_mm or 0.0,
            wind_speed_ms=r.wind_speed_ms or 0.0,
            solar_radiation_wm2=r.solar_radiation_wm2 or 0.0,
        )
        for r in rows
    ]
