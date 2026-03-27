from pydantic import BaseModel
from datetime import datetime


class DrynessPoint(BaseModel):
    """One point on a dryness timeline chart."""
    timestamp: datetime
    score: float
    is_forecast: bool = False


class ForecastResponse(BaseModel):
    area_id: int
    area_name: str
    current_score: float | None
    timeline: list[DrynessPoint]
    hours_to_climbable: float | None  # None if already climbable or won't dry in 48h
