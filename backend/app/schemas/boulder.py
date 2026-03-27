from pydantic import BaseModel
from datetime import datetime
from typing import Any


class BoulderProperties(BaseModel):
    id: int
    name: str | None
    grade: str | None
    area_id: int
    area_name: str | None
    dryness_score: float | None
    confidence: float
    # True = pure area estimate (lowest opacity); False but no recent reports = mid opacity
    is_estimated: bool
    # True = has reports in last 48h (full opacity)
    has_recent_reports: bool
    hours_since_rain: float | None
    last_rain_at: datetime | None
    report_count: int  # Total all-time reports for this boulder


class BoulderGeoJSON(BaseModel):
    """Single boulder feature for zoomed-in map layer."""
    type: str = "Feature"
    geometry: dict[str, Any]
    properties: BoulderProperties


class BoulderFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[BoulderGeoJSON]


class RecentReport(BaseModel):
    reported_at: datetime
    condition: str
    report_level: str


class BoulderDetail(BaseModel):
    id: int
    name: str | None
    grade: str | None
    lat: float
    lon: float
    area_id: int
    area_name: str | None
    dryness_score: float | None
    confidence: float
    is_estimated: bool
    has_recent_reports: bool
    hours_since_rain: float | None
    last_rain_at: datetime | None
    recent_reports: list[RecentReport]

    model_config = {"from_attributes": True}
