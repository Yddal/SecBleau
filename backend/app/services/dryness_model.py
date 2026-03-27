"""
SecBleau dryness prediction — physics-based evaporation model.

Core equation:
    dM/dt = precipitation_input(t) - k_evap(t) × M(t)

Where:
    M(t)  = moisture state ∈ [0, 1]  (0 = bone dry, 1 = saturated)
    k_evap = evaporation rate coefficient (fraction of moisture lost per hour)
             computed from temperature, humidity, wind, solar radiation, and
             area/boulder physical characteristics.

Dryness score = 1.0 - M(t), clamped to [0, 1].
Climbable threshold is fixed at 0.70 (score ≥ 0.70 means dry enough).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


# Fontainebleau sandstone absorption coefficient.
# mm of rain → moisture units. Sandstone is quite absorbent.
# A value of 0.18 means ~5.5mm of rain saturates the rock, which is more realistic
# for Bleau sandstone — especially under on/off rain where the surface never drains fully.
PRECIP_TO_MOISTURE = 0.18   # 5.5 mm of rain saturates the rock

# Minimum drying rate even at night / in fog (very slow but never zero)
K_EVAP_MIN = 0.004  # ~0.4% moisture loss per hour at worst conditions

# Maximum drying rate (hot, windy, full sun, south-facing)
K_EVAP_MAX = 0.30   # ~30% moisture loss per hour at best conditions

# Aspect multipliers for solar radiation — how much of the solar radiation
# actually hits the rock face depending on its orientation.
# These apply an average correction; actual value depends on time of day.
ASPECT_SOLAR_MULTIPLIERS = {
    "N":   0.15,
    "NE":  0.35,
    "E":   0.65,
    "SE":  0.85,
    "S":   1.00,
    "SW":  0.85,
    "W":   0.65,
    "NW":  0.35,
    "flat": 0.60,
}


@dataclass
class WeatherSnapshot:
    """One hourly weather observation."""
    recorded_at: datetime
    temperature_c: float
    humidity_pct: float
    precipitation_mm: float
    wind_speed_ms: float
    solar_radiation_wm2: float


@dataclass
class AreaCharacteristics:
    """Physical properties of an area or boulder."""
    aspect: Optional[str]          # facing direction
    shade_factor: float            # 0=full shade, 1=full sun
    canopy_factor: float           # 0=open, 1=dense canopy
    drying_rate_multiplier: float  # learned Bayesian parameter, default 1.0
    area_drying_offset: float      # learned Bayesian parameter, default 0.0


def _saturation_vapor_pressure(temp_c: float) -> float:
    """Magnus formula — saturation vapor pressure in hPa."""
    return 6.112 * math.exp(17.67 * temp_c / (temp_c + 243.5))


def _aspect_solar_multiplier(aspect: Optional[str]) -> float:
    if not aspect:
        return 0.60  # default — assume mixed
    return ASPECT_SOLAR_MULTIPLIERS.get(aspect.upper(), 0.60)


def compute_evap_rate(
    snapshot: WeatherSnapshot,
    chars: AreaCharacteristics,
) -> float:
    """
    Compute k_evap (evaporation rate coefficient, 1/hour) for a given
    weather snapshot and location characteristics.

    The drying_rate_multiplier scales this result to capture boulder-specific
    structural factors (drainage quality, lichen, overhang shelter, etc.)
    in context of the actual weather — it does NOT bypass weather physics.

    Returns: k_evap ∈ [K_EVAP_MIN, K_EVAP_MAX]
    """
    temp = snapshot.temperature_c
    humidity = max(0.0, min(100.0, snapshot.humidity_pct))
    wind = max(0.0, snapshot.wind_speed_ms)
    solar = max(0.0, snapshot.solar_radiation_wm2)

    # --- Vapour Pressure Deficit (VPD) ---
    # VPD is the primary driver of evaporation. High VPD = dry air = fast drying.
    e_sat = _saturation_vapor_pressure(temp)
    e_act = e_sat * (humidity / 100.0)
    vpd = max(0.0, e_sat - e_act)  # hPa

    # Base evaporation from VPD (range ~0 to 0.10/hr at extreme VPD)
    k_vpd = (vpd / 25.0) * 0.08

    # Wind contribution — convective drying
    # Wind of 5 m/s adds ~0.04/hr; above 10 m/s diminishing returns
    k_wind = 0.025 * (1 - math.exp(-wind / 4.0))

    # Solar radiation — direct heating of rock surface accelerates evaporation
    # Adjusted for aspect and shade
    solar_effective = solar * chars.shade_factor * _aspect_solar_multiplier(chars.aspect)
    k_solar = (solar_effective / 700.0) * 0.06

    # Canopy reduces effective wind and solar at rock surface
    canopy_damping = 1.0 - chars.canopy_factor * 0.45

    # Total base evaporation rate
    k_base = (k_vpd + k_wind + k_solar) * canopy_damping

    # Apply learned per-boulder multiplier IN CONTEXT of current weather.
    # A multiplier of 1.5 means "50% faster than typical for these conditions".
    k_effective = k_base * chars.drying_rate_multiplier

    return max(K_EVAP_MIN, min(K_EVAP_MAX, k_effective))


def simulate_moisture(
    weather_history: list[WeatherSnapshot],
    chars: AreaCharacteristics,
    initial_moisture: float = 0.0,
) -> tuple[float, dict]:
    """
    Integrate the moisture ODE over the weather history using Euler steps (hourly).

    Returns:
        (final_moisture, metadata_dict)
        metadata includes: last_rain_at, last_rain_mm, hours_since_rain
    """
    if not weather_history:
        return 0.0, {"last_rain_at": None, "last_rain_mm": None, "hours_since_rain": None}

    history = sorted(weather_history, key=lambda w: w.recorded_at)
    M = initial_moisture
    dt = 1.0  # 1 hour steps

    last_rain_at = None
    last_rain_mm = 0.0

    for snap in history:
        # Precipitation increases moisture (sandstone absorption)
        rain = max(0.0, snap.precipitation_mm)
        raining = rain > 0.1  # ignore dew/trace
        if raining:
            moisture_input = rain * PRECIP_TO_MOISTURE
            M = min(1.0, M + moisture_input)
            last_rain_at = snap.recorded_at
            last_rain_mm = rain

        # Evaporation dries the rock — suppressed during active rain hours
        # (surface is being re-wetted; air is saturated, net flux is zero)
        if not raining:
            k = compute_evap_rate(snap, chars)
            M = M - k * M * dt
            M = max(0.0, min(1.0, M))

    # Hours since last significant rain
    hours_since_rain = None
    if last_rain_at:
        now = history[-1].recorded_at
        delta = now - last_rain_at
        hours_since_rain = delta.total_seconds() / 3600.0

    return M, {
        "last_rain_at": last_rain_at,
        "last_rain_mm": last_rain_mm,
        "hours_since_rain": hours_since_rain,
    }


def moisture_to_dryness_score(
    moisture: float,
    area_drying_offset: float = 0.0,
) -> float:
    """
    Convert moisture state to a dryness score [0, 1].

    score = (1 - moisture) + area_drying_offset
    Clamped to [0, 1].

    Score ≥ 0.70 → climbable (yellow-green or green on map).
    Score < 0.70 → not ready (orange to red on map).
    """
    raw = 1.0 - moisture + area_drying_offset
    return max(0.0, min(1.0, raw))


def score_to_color(score: float) -> str:
    """
    Map a dryness score to a hex color for the map.
    Fixed thresholds — not user-adjustable. Yellow-green appears at exactly 0.70.
    """
    if score < 0.30:
        return "#d73027"   # red — wet, unclimbable
    elif score < 0.55:
        return "#f46d43"   # orange-red — damp
    elif score < 0.70:
        return "#fdae61"   # orange — drying, approaching threshold
    elif score < 0.85:
        return "#a6d96a"   # yellow-green — climbable
    else:
        return "#1a9641"   # green — excellent, bone dry


def opacity_for_boulder(
    has_recent_boulder_reports: bool,
    has_area_reports: bool,
) -> float:
    """
    Map confidence level to map opacity.
    Full opacity only when direct boulder reports exist in last 48h.
    """
    if has_recent_boulder_reports:
        return 1.0
    elif has_area_reports:
        return 0.60
    else:
        return 0.35


def hours_to_climbable(
    current_moisture: float,
    forecast_weather: list[WeatherSnapshot],
    chars: AreaCharacteristics,
    threshold: float = 0.70,  # dryness score threshold
) -> Optional[float]:
    """
    Given current moisture and a weather forecast, estimate how many hours
    until dryness score crosses the climbable threshold.

    Returns None if already climbable, or if won't dry within the forecast window.
    """
    current_score = moisture_to_dryness_score(current_moisture, chars.area_drying_offset)
    if current_score >= threshold:
        return None  # already climbable

    M = current_moisture
    for i, snap in enumerate(sorted(forecast_weather, key=lambda w: w.recorded_at)):
        rain = max(0.0, snap.precipitation_mm)
        raining = rain > 0.1
        if raining:
            M = min(1.0, M + rain * PRECIP_TO_MOISTURE)
        else:
            k = compute_evap_rate(snap, chars)
            M = max(0.0, M - k * M)

        score = moisture_to_dryness_score(M, chars.area_drying_offset)
        if score >= threshold:
            return float(i + 1)

    return None  # won't dry in forecast window
