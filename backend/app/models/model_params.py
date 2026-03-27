from sqlalchemy import Column, Integer, Float, DateTime, String, UniqueConstraint
from sqlalchemy.sql import func
from ..database import Base


class ModelParam(Base):
    """
    Bayesian parameter store — one row per (entity, param_key).

    entity_type: 'boulder' or 'area'
    entity_id:   id from boulders or areas table

    param_key values:
      - 'drying_rate_multiplier'  (per boulder, init 1.0)
        Scales k_evap within the physics model. Captures boulder-specific structural
        factors (drainage, moss, orientation) that make it dry faster or slower than
        typical for its weather conditions.

      - 'area_drying_offset'      (per area, init 0.0)
        Additive correction to the area-level dryness score.
        Range [-0.2, +0.2]. Updated by area-level user reports.
    """
    __tablename__ = "model_params"

    id = Column(Integer, primary_key=True)
    entity_type = Column(String(10), nullable=False)  # 'boulder' | 'area'
    entity_id = Column(Integer, nullable=False)
    param_key = Column(String(50), nullable=False)

    # Current best estimate (posterior mean after N observations)
    posterior_mean = Column(Float, nullable=False)
    # Uncertainty — starts high (wide prior), shrinks with each report
    posterior_variance = Column(Float, nullable=False)

    # Count of valid reports that have updated this parameter
    n_observations = Column(Integer, default=0)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "param_key", name="uq_model_param"),
    )
