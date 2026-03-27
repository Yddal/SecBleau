from pydantic import BaseModel, field_validator, model_validator
from datetime import datetime
from typing import Literal


VALID_BOULDER_CONDITIONS = {"wet", "drying", "climbable"}
VALID_AREA_CONDITIONS = {"wet", "drying", "some_boulders_dry", "dry"}


class BoulderReportIn(BaseModel):
    condition: str
    notes: str | None = None

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, v: str) -> str:
        if v not in VALID_BOULDER_CONDITIONS:
            raise ValueError(f"condition must be one of: {', '.join(sorted(VALID_BOULDER_CONDITIONS))}")
        return v

    @field_validator("notes")
    @classmethod
    def truncate_notes(cls, v: str | None) -> str | None:
        if v:
            return v[:500]
        return v


class AreaReportIn(BaseModel):
    condition: str
    notes: str | None = None

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, v: str) -> str:
        if v not in VALID_AREA_CONDITIONS:
            raise ValueError(f"condition must be one of: {', '.join(sorted(VALID_AREA_CONDITIONS))}")
        return v

    @field_validator("notes")
    @classmethod
    def truncate_notes(cls, v: str | None) -> str | None:
        if v:
            return v[:500]
        return v


class ReportOut(BaseModel):
    id: int
    report_level: str
    condition: str
    reported_at: datetime
    # Updated score after Bayesian adjustment
    updated_score: float | None = None
    message: str = "Report recorded. Thank you for helping the community!"
