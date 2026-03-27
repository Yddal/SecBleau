from sqlalchemy import Column, Integer, BigInteger, String, Float, DateTime, ForeignKey, Boolean, Enum, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from ..database import Base


class ReportLevel(str, enum.Enum):
    boulder = "boulder"
    area = "area"


class BoulderCondition(str, enum.Enum):
    wet = "wet"
    drying = "drying"
    climbable = "climbable"


class AreaCondition(str, enum.Enum):
    wet = "wet"
    drying = "drying"
    some_boulders_dry = "some_boulders_dry"
    dry = "dry"


# Numeric mapping used by the Bayesian updater
BOULDER_CONDITION_SCORES = {
    "wet": 0.0,
    "drying": 0.4,
    "climbable": 1.0,
}

AREA_CONDITION_SCORES = {
    "wet": 0.0,
    "drying": 0.35,
    "some_boulders_dry": 0.65,
    "dry": 1.0,
}


class UserReport(Base):
    """
    Condition report from a user. Can be at boulder or area level.
    No PII stored — session_hash is SHA-256 of (IP + User-Agent), salted.
    """
    __tablename__ = "user_reports"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    report_level = Column(String(10), nullable=False)  # 'boulder' | 'area'

    # Exactly one of these will be set
    boulder_id = Column(Integer, ForeignKey("boulders.id"), nullable=True, index=True)
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=False, index=True)

    reported_at = Column(DateTime(timezone=True), nullable=False)

    # Condition string — validated against BoulderCondition or AreaCondition at API layer
    condition = Column(String(30), nullable=False)

    # Physics model score at the time this report was submitted — used for Bayesian update
    predicted_score = Column(Float)

    # Anonymised session fingerprint for rate-limiting (no PII)
    session_hash = Column(String(64))

    notes = Column(String(500))  # Optional freetext from user, max 500 chars

    # Flagged by outlier detection
    is_valid = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    boulder = relationship("Boulder", back_populates="reports")

    __table_args__ = (
        Index("ix_reports_boulder_time", "boulder_id", "reported_at"),
        Index("ix_reports_area_time", "area_id", "reported_at"),
        Index("ix_reports_session_boulder", "session_hash", "boulder_id", "reported_at"),
    )
