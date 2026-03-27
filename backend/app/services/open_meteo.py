"""
Open-Meteo API client.
Free, no authentication required. Rate limit: 600 calls/min, 10k/day.

One call per area fetches 7 days history + 2 days forecast (hourly).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from .dryness_model import WeatherSnapshot

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_VARS = [
    "temperature_2m",
    "relativehumidity_2m",
    "precipitation",
    "windspeed_10m",
    "winddirection_10m",
    "shortwave_radiation",
    "soil_moisture_0_to_1cm",
]


async def fetch_weather(
    lat: float,
    lon: float,
    past_days: int = 7,
    forecast_days: int = 2,
) -> dict:
    """
    Fetch hourly weather for the given coordinates.
    Returns the raw Open-Meteo JSON response.
    """
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "hourly": ",".join(HOURLY_VARS),
        "past_days": past_days,
        "forecast_days": forecast_days,
        "timezone": "Europe/Paris",
        "wind_speed_unit": "ms",  # metres per second
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(OPEN_METEO_URL, params=params)
        resp.raise_for_status()
        return resp.json()


def parse_weather_snapshots(raw: dict) -> list[WeatherSnapshot]:
    """
    Convert raw Open-Meteo response into a list of WeatherSnapshot objects.
    Skips hours where all values are None (can occur at forecast edges).
    """
    hourly = raw.get("hourly", {})
    times = hourly.get("time", [])

    snapshots = []
    for i, t in enumerate(times):
        temp = _get(hourly, "temperature_2m", i)
        humidity = _get(hourly, "relativehumidity_2m", i)
        precip = _get(hourly, "precipitation", i)
        wind = _get(hourly, "windspeed_10m", i)
        solar = _get(hourly, "shortwave_radiation", i)

        # Skip completely empty rows
        if temp is None and humidity is None and precip is None:
            continue

        snapshots.append(WeatherSnapshot(
            recorded_at=datetime.fromisoformat(t).replace(tzinfo=timezone.utc),
            temperature_c=temp if temp is not None else 10.0,
            humidity_pct=humidity if humidity is not None else 80.0,
            precipitation_mm=precip if precip is not None else 0.0,
            wind_speed_ms=wind if wind is not None else 0.0,
            solar_radiation_wm2=solar if solar is not None else 0.0,
        ))

    return snapshots


def split_history_forecast(
    snapshots: list[WeatherSnapshot],
) -> tuple[list[WeatherSnapshot], list[WeatherSnapshot]]:
    """
    Split snapshots into past (history) and future (forecast) based on current time.
    """
    now = datetime.now(timezone.utc)
    history = [s for s in snapshots if s.recorded_at <= now]
    forecast = [s for s in snapshots if s.recorded_at > now]
    return history, forecast


def _get(hourly: dict, key: str, i: int) -> Optional[float]:
    values = hourly.get(key, [])
    if i < len(values):
        return values[i]
    return None
