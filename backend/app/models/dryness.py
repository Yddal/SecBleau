from sqlalchemy import Column, Integer, BigInteger, Float, DateTime, ForeignKey, Boolean, String, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class DrynessScore(Base):
    """
    Cached dryness prediction for an area or a specific boulder.
    Recomputed hourly by the scheduler after each weather fetch.

    boulder_id=None  → area-level aggregate score
    boulder_id=N     → per-boulder score
    """
    __tablename__ = "dryness_scores"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=False, index=True)
    boulder_id = Column(Integer, ForeignKey("boulders.id"), nullable=True, index=True)

    computed_at = Column(DateTime(timezone=True), nullable=False)

    # 0.0 = soaked, 1.0 = bone dry. Threshold for "climbable" is 0.70.
    score = Column(Float, nullable=False)

    # confidence: 0-1, based on how many user reports have calibrated this boulder/area
    confidence = Column(Float, default=0.5)

    # Whether this score is estimated from area data (no direct boulder reports)
    is_estimated = Column(Boolean, default=True)

    # For display: "last rain X hours ago, Y mm"
    hours_since_rain = Column(Float)
    last_rain_at = Column(DateTime(timezone=True))
    last_rain_mm = Column(Float)

    # Score breakdown for debugging / transparency
    physics_score = Column(Float)   # Raw output of evaporation model
    ml_correction = Column(Float, default=0.0)  # Bayesian correction applied

    model_version = Column(String(20), default="1.0")

    # Relationships
    boulder = relationship("Boulder", back_populates="dryness_scores")

    __table_args__ = (
        # Speeds up "latest score per area" and "latest score per boulder" queries
        Index("ix_dryness_area_boulder_time", "area_id", "boulder_id", "computed_at"),
    )
