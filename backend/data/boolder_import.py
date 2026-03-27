#!/usr/bin/env python3
"""
Boolder data import/update script.

First run: downloads areas.geojson and problems.geojson from the Boolder
open dataset (https://github.com/boolder-org/boolder-data, CC BY 4.0),
imports everything into the database, and saves files + a version stamp
to disk.

Subsequent runs: checks the Boolder GitHub repo for a new commit on the
export/ folder. If the commit SHA matches the stored stamp, the import
is skipped entirely (startup stays fast). If there is a new version,
files are re-downloaded and new/changed areas + boulders are upserted.

Usage:
    python data/boolder_import.py              # smart update check (default)
    python data/boolder_import.py --force      # force re-download + full upsert
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal, engine, Base
from app.models import Area, Boulder
from app.models import WeatherReading, DrynessScore, UserReport, ModelParam  # noqa
from sqlalchemy import select, text, update

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "boolder-data"
AREAS_CACHE = DATA_DIR / "areas.geojson"
PROBLEMS_CACHE = DATA_DIR / "problems.geojson"
CLUSTERS_CACHE = DATA_DIR / "clusters.geojson"
VERSION_FILE = DATA_DIR / ".version"

# ── Remote URLs ───────────────────────────────────────────────────────────────

GITHUB_API_COMMITS = (
    "https://api.github.com/repos/boolder-org/boolder-data/commits"
    "?path=geojson&per_page=1"
)
AREAS_URL = (
    "https://raw.githubusercontent.com/boolder-org/boolder-data/main"
    "/geojson/areas.geojson"
)
PROBLEMS_URL = (
    "https://raw.githubusercontent.com/boolder-org/boolder-data/main"
    "/geojson/problems.geojson"
)
CLUSTERS_URL = (
    "https://raw.githubusercontent.com/boolder-org/boolder-data/main"
    "/geojson/clusters.geojson"
)


# ── Version check ─────────────────────────────────────────────────────────────

async def fetch_latest_sha() -> str | None:
    """Ask GitHub for the latest commit SHA that touched export/."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                GITHUB_API_COMMITS,
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            resp.raise_for_status()
            commits = resp.json()
            if commits:
                return commits[0]["sha"]
    except Exception as e:
        logger.warning("Could not reach GitHub API: %s — will use cached data if available", e)
    return None


def read_stored_sha() -> str | None:
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip() or None
    return None


def write_sha(sha: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_text(sha)


# ── Download + cache ──────────────────────────────────────────────────────────

async def download_and_cache() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        for url, path in (
            (AREAS_URL, AREAS_CACHE),
            (PROBLEMS_URL, PROBLEMS_CACHE),
            (CLUSTERS_URL, CLUSTERS_CACHE),
        ):
            logger.info("Downloading %s …", url)
            resp = await client.get(url)
            resp.raise_for_status()
            path.write_bytes(resp.content)
            count = len(resp.json().get("features", []))
            logger.info("  → %d features saved to %s", count, path.name)


def load_cached(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("features", [])


# ── Database helpers ──────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:100]


async def _ensure_postgis(db) -> None:
    try:
        await db.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await db.commit()
    except Exception as e:
        logger.warning("PostGIS: %s", e)


async def upsert_areas(db, features: list[dict]) -> tuple[dict[int, int], list[dict]]:
    """
    Insert new areas and update changed ones (name, coordinates, description).
    Returns (boolder_id → db id mapping, list of area bbox dicts for spatial lookup).
    """
    boolder_to_db: dict[int, int] = {}
    area_bboxes: list[dict] = []  # [{db_id, sw_lat, sw_lon, ne_lat, ne_lon}]
    inserted = updated = skipped = 0

    for feat in features:
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        boolder_id = props.get("id") or props.get("areaId")
        if not boolder_id:
            continue

        coords = geom.get("coordinates")
        if not coords or geom.get("type") != "Point":
            skipped += 1
            continue

        lon, lat = float(coords[0]), float(coords[1])
        name = props.get("name") or props.get("short_name") or f"Area {boolder_id}"
        description = props.get("description")

        # BBox fields
        sw_lat = props.get("southWestLat")
        sw_lon = props.get("southWestLon")
        ne_lat = props.get("northEastLat")
        ne_lon = props.get("northEastLon")
        bbox_sw_lat = float(sw_lat) if sw_lat is not None else None
        bbox_sw_lon = float(sw_lon) if sw_lon is not None else None
        bbox_ne_lat = float(ne_lat) if ne_lat is not None else None
        bbox_ne_lon = float(ne_lon) if ne_lon is not None else None

        result = await db.execute(select(Area).where(Area.boolder_id == boolder_id))
        existing: Area | None = result.scalar_one_or_none()

        if existing:
            boolder_to_db[boolder_id] = existing.id
            # Update if anything changed
            if existing.name != name or existing.lat != lat or existing.lon != lon:
                existing.name = name
                existing.lat = lat
                existing.lon = lon
                existing.geom = f"SRID=4326;POINT({lon} {lat})"
                if description:
                    existing.description = description
                updated += 1
            else:
                skipped += 1
            # Always update bbox fields
            existing.bbox_sw_lat = bbox_sw_lat
            existing.bbox_sw_lon = bbox_sw_lon
            existing.bbox_ne_lat = bbox_ne_lat
            existing.bbox_ne_lon = bbox_ne_lon
            if bbox_sw_lat is not None and bbox_sw_lon is not None and bbox_ne_lat is not None and bbox_ne_lon is not None:
                area_bboxes.append({
                    "db_id": existing.id,
                    "sw_lat": bbox_sw_lat, "sw_lon": bbox_sw_lon,
                    "ne_lat": bbox_ne_lat, "ne_lon": bbox_ne_lon,
                })
            continue

        # New area — generate unique slug
        slug = _slugify(name)
        base_slug = slug
        suffix = 0
        while True:
            check = await db.execute(select(Area.id).where(Area.slug == slug))
            if not check.scalar_one_or_none():
                break
            suffix += 1
            slug = f"{base_slug}-{suffix}"

        area = Area(
            boolder_id=boolder_id,
            name=name,
            slug=slug,
            lat=lat,
            lon=lon,
            geom=f"SRID=4326;POINT({lon} {lat})",
            shade_factor=0.5,
            canopy_factor=0.6,
            rock_type="sandstone",
            description=description,
            bbox_sw_lat=bbox_sw_lat,
            bbox_sw_lon=bbox_sw_lon,
            bbox_ne_lat=bbox_ne_lat,
            bbox_ne_lon=bbox_ne_lon,
        )
        db.add(area)
        await db.flush()
        boolder_to_db[boolder_id] = area.id
        if bbox_sw_lat is not None and bbox_sw_lon is not None and bbox_ne_lat is not None and bbox_ne_lon is not None:
            area_bboxes.append({
                "db_id": area.id,
                "sw_lat": bbox_sw_lat, "sw_lon": bbox_sw_lon,
                "ne_lat": bbox_ne_lat, "ne_lon": bbox_ne_lon,
            })
        inserted += 1

    await db.commit()
    logger.info("Areas  — inserted: %d  updated: %d  unchanged: %d", inserted, updated, skipped)
    return boolder_to_db, area_bboxes


async def upsert_problems(db, features: list[dict], area_map: dict[int, int], area_bboxes: list[dict]) -> None:
    """Insert new boulders and update coordinates/grade/name if changed.

    Since the new Boolder geojson format no longer includes area_id on problems,
    we assign each problem to an area by checking which area's bbox contains the
    problem's coordinates. area_bboxes is a list of dicts with keys:
    db_id, sw_lat, sw_lon, ne_lat, ne_lon.
    """
    inserted = updated = skipped = no_area = 0

    for feat in features:
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        problem_id = props.get("id") or props.get("problemId")
        if not problem_id:
            continue

        coords = geom.get("coordinates")
        if not coords or geom.get("type") != "Point":
            skipped += 1
            continue

        lon, lat = float(coords[0]), float(coords[1])

        # Try legacy area_id first, then fall back to spatial bbox lookup
        boolder_area_id = props.get("area_id") or props.get("areaId")
        db_area_id = area_map.get(boolder_area_id) if boolder_area_id else None

        if db_area_id is None:
            # Spatial assignment: find the area whose bbox contains this point
            for bbox in area_bboxes:
                if (bbox["sw_lat"] <= lat <= bbox["ne_lat"] and
                        bbox["sw_lon"] <= lon <= bbox["ne_lon"]):
                    db_area_id = bbox["db_id"]
                    break

        if db_area_id is None:
            no_area += 1
            continue

        name = props.get("name") or props.get("local_name")
        grade = (props.get("grade") or "").lower().strip() or None

        result = await db.execute(
            select(Boulder).where(Boulder.boolder_problem_id == problem_id)
        )
        existing: Boulder | None = result.scalar_one_or_none()

        if existing:
            changed = False
            if existing.lat != lat or existing.lon != lon:
                existing.lat = lat
                existing.lon = lon
                existing.geom = f"SRID=4326;POINT({lon} {lat})"
                changed = True
            if name and existing.name != name:
                existing.name = name
                changed = True
            if grade and existing.grade != grade:
                existing.grade = grade
                changed = True
            if changed:
                updated += 1
            else:
                skipped += 1
            continue

        db.add(Boulder(
            boolder_problem_id=problem_id,
            area_id=db_area_id,
            name=name,
            grade=grade,
            lat=lat,
            lon=lon,
            geom=f"SRID=4326;POINT({lon} {lat})",
            has_direct_data=False,
        ))
        inserted += 1

        if inserted % 500 == 0:
            await db.flush()
            logger.info("  … %d boulders inserted so far", inserted)

    await db.commit()
    logger.info(
        "Boulders — inserted: %d  updated: %d  unchanged: %d  skipped (no area): %d",
        inserted, updated, skipped, no_area,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(force: bool = False) -> None:
    logger.info("SecBleau — Boolder data sync")
    logger.info("=" * 50)

    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        await _ensure_postgis(db)

    # Migration: add bbox columns if they don't exist yet
    async with AsyncSessionLocal() as db:
        await db.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS bbox_sw_lon FLOAT"))
        await db.commit()
        await db.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS bbox_sw_lat FLOAT"))
        await db.commit()
        await db.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS bbox_ne_lon FLOAT"))
        await db.commit()
        await db.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS bbox_ne_lat FLOAT"))
        await db.commit()

    # ── Check whether a download is needed ────────────────────────────────────

    stored_sha = read_stored_sha()
    latest_sha = await fetch_latest_sha()

    logger.info("Stored version : %s", stored_sha or "none")
    logger.info("Latest version : %s", latest_sha or "unknown (offline?)")

    need_download = (
        force
        or not AREAS_CACHE.exists()
        or not PROBLEMS_CACHE.exists()
        or (latest_sha is not None and latest_sha != stored_sha)
    )

    if not need_download:
        async with AsyncSessionLocal() as db:
            count_result = await db.execute(text("SELECT COUNT(*) FROM areas"))
            count = count_result.scalar()
        if not count or count == 0:
            logger.info("Cache is current but DB is empty — re-importing from cache.")
            # Don't set need_download — files already exist, just re-import
        else:
            logger.info("Data is up to date (SHA: %s) and DB has %d areas — nothing to do.", stored_sha, count)
            return

    # ── Download (if needed) ──────────────────────────────────────────────────

    if need_download:
        if force:
            logger.info("Force mode — re-downloading Boolder data.")
        elif not AREAS_CACHE.exists():
            logger.info("No cached data found — downloading for the first time.")
        else:
            logger.info("New Boolder dataset available — downloading update.")
        await download_and_cache()

    # ── Import / upsert ───────────────────────────────────────────────────────

    logger.info("Importing from cache into database …")
    area_features = load_cached(AREAS_CACHE)
    problem_features = load_cached(PROBLEMS_CACHE)

    logger.info("Areas: %d features", len(area_features))
    logger.info("Problems: %d features", len(problem_features))

    async with AsyncSessionLocal() as db:
        await _ensure_postgis(db)
        area_map, area_bboxes = await upsert_areas(db, area_features)
        logger.info("Area bbox index: %d areas with bbox data", len(area_bboxes))
        await upsert_problems(db, problem_features, area_map, area_bboxes)

    # ── Save version stamp ────────────────────────────────────────────────────

    if latest_sha:
        write_sha(latest_sha)
        logger.info("Version stamp saved: %s", latest_sha)
    elif not stored_sha:
        # Offline first run — stamp with "offline" so we still know data exists
        write_sha("offline")

    logger.info("Sync complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Boolder climbing data into SecBleau")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if version is up to date",
    )
    args = parser.parse_args()
    asyncio.run(main(force=args.force))
