from pydantic import BaseModel
from datetime import datetime
from typing import Any


class AreaProperties(BaseModel):
    id: int
    name: str
    slug: str | None
    dryness_score: float | None
    confidence: float
    is_estimated: bool
    hours_since_rain: float | None
    last_rain_at: datetime | None
    last_rain_mm: float | None
    boulder_count: int
    aspect: str | None
    elevation_m: int | None
    # For the weather panel
    temperature_c: float | None = None
    humidity_pct: float | None = None
    wind_speed_ms: float | None = None
    precipitation_last_24h_mm: float | None = None
    bbox_sw_lon: float | None = None
    bbox_sw_lat: float | None = None
    bbox_ne_lon: float | None = None
    bbox_ne_lat: float | None = None
    hull: Any = None  # GeoJSON geometry object (Polygon) computed from boulder positions


class AreaGeoJSON(BaseModel):
    """Single area feature for map rendering."""
    type: str = "Feature"
    geometry: dict[str, Any]
    properties: AreaProperties


class AreaFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[AreaGeoJSON]


class WeatherSummary(BaseModel):
    recorded_at: datetime
    temperature_c: float | None
    humidity_pct: float | None
    precipitation_mm: float | None
    wind_speed_ms: float | None
    solar_radiation_wm2: float | None


class AreaDetail(BaseModel):
    id: int
    name: str
    slug: str | None
    lat: float
    lon: float
    aspect: str | None
    shade_factor: float
    canopy_factor: float
    elevation_m: int | None
    dryness_score: float | None
    confidence: float
    hours_since_rain: float | None
    last_rain_at: datetime | None
    last_rain_mm: float | None
    boulder_count: int
    recent_weather: list[WeatherSummary]
    report_count_24h: int

    model_config = {"from_attributes": True}
