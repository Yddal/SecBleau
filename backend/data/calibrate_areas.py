#!/usr/bin/env python3
"""
Area calibration — sets realistic drying parameters for all 90 Fontainebleau areas.

Two-pass approach:
  1. Known quick-drying sectors (per Boolder guidebook): shade_factor=0.90, canopy_factor=0.10
  2. All other areas: parameters scaled linearly by GPS elevation fetched from Open-Meteo.
     Higher elevation → more exposed → faster drying.

Elevation formula (Fontainebleau range roughly 50–180 m):
  norm = (elev - elev_min) / (elev_max - elev_min)   # 0=lowest, 1=highest
  shade_factor  = 0.55 + 0.30 * norm   # 0.55 (sheltered valley) → 0.85 (exposed plateau)
  canopy_factor = 0.55 - 0.40 * norm   # 0.55 (dense low canopy) → 0.15 (open ridge)

Usage (from project root):
    docker compose exec -T api python data/calibrate_areas.py
    docker compose exec -T api python data/calibrate_areas.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal, engine, Base
from app.models.area import Area
from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Quick-drying sector name fragments (case-insensitive substring match) ─────
# Source: Boolder guidebook "quick-drying" annotations.
QUICK_DRYING_PATTERNS = [
    "drei zinnen",
    "rocher de la reine",
    "demoiselles",
    "gorge aux ch",       # "Gorge aux Châts"
    "apremont",           # entire Apremont cluster
    "beauvais",           # Beauvais / Nainville
    "95.2",
    "91.1",
    "cul de chien",
    "gros sablons",
]

# Parameters
QUICK_SHADE   = 0.90
QUICK_CANOPY  = 0.10

OPEN_METEO_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
# Maximum locations per API call (Open-Meteo supports up to 100)
ELEVATION_BATCH_SIZE = 100


def _is_quick_drying(name: str) -> bool:
    lower = name.lower()
    return any(pat in lower for pat in QUICK_DRYING_PATTERNS)


async def fetch_elevations(areas: list[Area]) -> dict[int, float]:
    """
    Batch-fetch elevations from Open-Meteo elevation API.
    Returns {area.id: elevation_m}.
    """
    elevations: dict[int, float] = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(0, len(areas), ELEVATION_BATCH_SIZE):
            batch = areas[i : i + ELEVATION_BATCH_SIZE]
            lats = ",".join(str(round(a.lat, 4)) for a in batch)
            lons = ",".join(str(round(a.lon, 4)) for a in batch)

            resp = await client.get(
                OPEN_METEO_ELEVATION_URL,
                params={"latitude": lats, "longitude": lons},
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("elevation", [])

            for j, area in enumerate(batch):
                elev = raw[j] if j < len(raw) else None
                if elev is not None:
                    elevations[area.id] = float(elev)

            logger.info(
                "Elevations fetched: batch %d/%d (%d areas)",
                i // ELEVATION_BATCH_SIZE + 1,
                (len(areas) + ELEVATION_BATCH_SIZE - 1) // ELEVATION_BATCH_SIZE,
                len(batch),
            )

    return elevations


async def calibrate(dry_run: bool = False) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Area).order_by(Area.id))
        areas: list[Area] = result.scalars().all()

    if not areas:
        logger.error("No areas found in database — run boolder_import.py first.")
        return

    logger.info("Found %d areas. Fetching elevations…", len(areas))
    elevations = await fetch_elevations(areas)
    logger.info("Got elevation data for %d/%d areas.", len(elevations), len(areas))

    # Separate quick-drying vs. regular areas
    quick_ids: set[int] = set()
    regular: list[tuple[Area, float]] = []  # (area, elevation_m)

    for area in areas:
        if _is_quick_drying(area.name):
            quick_ids.add(area.id)
        else:
            elev = elevations.get(area.id)
            if elev is not None:
                regular.append((area, elev))
            else:
                # No elevation — treat as mid-range
                regular.append((area, 100.0))
                logger.warning("No elevation for area %d '%s' — using 100 m default", area.id, area.name)

    logger.info(
        "Quick-drying areas: %d  |  Regular areas: %d",
        len(quick_ids), len(regular),
    )

    # Compute elevation range for normalization (regular areas only)
    if regular:
        elev_values = [e for _, e in regular]
        elev_min = min(elev_values)
        elev_max = max(elev_values)
        elev_range = elev_max - elev_min if elev_max > elev_min else 1.0
        logger.info("Elevation range: %.0f m – %.0f m", elev_min, elev_max)
    else:
        elev_min = elev_max = elev_range = 1.0

    async with AsyncSessionLocal() as db:
        # --- Quick-drying sectors ---
        for area in areas:
            if area.id not in quick_ids:
                continue

            elev = elevations.get(area.id)
            new_shade = QUICK_SHADE
            new_canopy = QUICK_CANOPY
            new_elev = round(elev) if elev is not None else area.elevation_m

            if dry_run:
                logger.info(
                    "[DRY RUN] QUICK  %-40s  shade=%.2f  canopy=%.2f  elev=%s m",
                    area.name, new_shade, new_canopy, new_elev,
                )
            else:
                result = await db.execute(select(Area).where(Area.id == area.id))
                a = result.scalar_one()
                a.shade_factor = new_shade
                a.canopy_factor = new_canopy
                if new_elev is not None:
                    a.elevation_m = new_elev

        # --- Regular areas (elevation-scaled) ---
        for area, elev in regular:
            norm = (elev - elev_min) / elev_range
            new_shade  = round(0.55 + 0.30 * norm, 3)
            new_canopy = round(0.55 - 0.40 * norm, 3)
            # Clamp to valid range
            new_shade  = max(0.0, min(1.0, new_shade))
            new_canopy = max(0.0, min(1.0, new_canopy))
            new_elev   = round(elev)

            if dry_run:
                logger.info(
                    "[DRY RUN] ELEV   %-40s  elev=%3.0f m  norm=%.2f  shade=%.2f  canopy=%.2f",
                    area.name, elev, norm, new_shade, new_canopy,
                )
            else:
                result = await db.execute(select(Area).where(Area.id == area.id))
                a = result.scalar_one()
                a.shade_factor  = new_shade
                a.canopy_factor = new_canopy
                a.elevation_m   = new_elev

        if not dry_run:
            await db.commit()
            logger.info("Committed calibration for %d areas.", len(areas))
        else:
            logger.info("[DRY RUN] No changes written.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calibrate area drying parameters")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without writing to the database",
    )
    args = parser.parse_args()
    asyncio.run(calibrate(dry_run=args.dry_run))
