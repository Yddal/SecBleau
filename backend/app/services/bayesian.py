"""
SecBleau self-learning system — Bayesian parameter updates.

Each boulder has a `drying_rate_multiplier` and each area has an
`area_drying_offset`. These are updated using a Kalman-filter-style
conjugate Gaussian update whenever a user submits a condition report.

The multiplier scales k_evap WITHIN the physics model, so cold weather
still dries slowly even with a high multiplier. It captures structural
differences between boulders (drainage, lichen, overhang, moss) relative
to the area's general conditions.

Parameter bounds:
  drying_rate_multiplier: [0.3, 3.0]  (per boulder)
  area_drying_offset:     [-0.2, 0.2] (per area)
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.model_params import ModelParam
from ..models.report import BOULDER_CONDITION_SCORES, AREA_CONDITION_SCORES, UserReport

logger = logging.getLogger(__name__)

# Default priors
BOULDER_MULTIPLIER_PRIOR_MEAN = 1.0
BOULDER_MULTIPLIER_PRIOR_VAR = 0.25   # wide — high uncertainty at start

AREA_OFFSET_PRIOR_MEAN = 0.0
AREA_OFFSET_PRIOR_VAR = 0.04          # narrower — offset is small correction

# Observation noise — how much we trust a single user report
# Higher = less weight per report, more stable but slower learning
OBSERVATION_NOISE_VAR = 0.15 ** 2

# Outlier threshold — reports more than N std devs from rolling mean are rejected
OUTLIER_SIGMA_THRESHOLD = 2.5

# Minimum number of reports before marking boulder as having "direct data"
MIN_REPORTS_FOR_DIRECT_DATA = 3


async def get_or_create_param(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    param_key: str,
) -> ModelParam:
    """Fetch existing param or initialise with prior defaults."""
    result = await db.execute(
        select(ModelParam).where(
            ModelParam.entity_type == entity_type,
            ModelParam.entity_id == entity_id,
            ModelParam.param_key == param_key,
        )
    )
    param = result.scalar_one_or_none()

    if param is None:
        if param_key == "drying_rate_multiplier":
            mean, var = BOULDER_MULTIPLIER_PRIOR_MEAN, BOULDER_MULTIPLIER_PRIOR_VAR
        else:  # area_drying_offset
            mean, var = AREA_OFFSET_PRIOR_MEAN, AREA_OFFSET_PRIOR_VAR

        param = ModelParam(
            entity_type=entity_type,
            entity_id=entity_id,
            param_key=param_key,
            posterior_mean=mean,
            posterior_variance=var,
            n_observations=0,
        )
        db.add(param)
        await db.flush()

    return param


def _kalman_update(
    prior_mean: float,
    prior_var: float,
    observation: float,
    obs_noise_var: float,
) -> tuple[float, float]:
    """
    Single-step Kalman (conjugate Gaussian) update.

    Returns: (posterior_mean, posterior_variance)
    """
    # Kalman gain: how much to trust the new observation vs prior
    K = prior_var / (prior_var + obs_noise_var)
    posterior_mean = prior_mean + K * (observation - prior_mean)
    posterior_var = (1.0 - K) * prior_var
    return posterior_mean, max(0.001, posterior_var)


def _is_outlier(
    reported_score: float,
    recent_reports: list[UserReport],
    sigma_threshold: float = OUTLIER_SIGMA_THRESHOLD,
) -> bool:
    """
    Check if a new report is an outlier compared to recent reports.
    Requires at least 5 reports to perform outlier detection.
    """
    if len(recent_reports) < 5:
        return False

    scores = []
    for r in recent_reports:
        score_map = (
            BOULDER_CONDITION_SCORES if r.report_level == "boulder"
            else AREA_CONDITION_SCORES
        )
        s = score_map.get(r.condition)
        if s is not None:
            scores.append(s)

    if len(scores) < 5:
        return False

    mean = sum(scores) / len(scores)
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    std = math.sqrt(variance)

    if std < 0.05:  # too little variance to detect outliers meaningfully
        return False

    return abs(reported_score - mean) > sigma_threshold * std


async def update_boulder_params(
    db: AsyncSession,
    boulder_id: int,
    area_id: int,
    condition: str,
    physics_score_at_report: float,
    recent_reports: list[UserReport],
) -> float:
    """
    Update the `drying_rate_multiplier` for a boulder based on a new user report.

    The update logic:
    - Map condition → numeric score (climbable=1.0, drying=0.4, wet=0.0)
    - The residual (observed - predicted) tells us if the boulder dries faster/slower
      than the physics model expects
    - Positive residual → drying_rate_multiplier should increase (boulder dries faster)
    - Negative residual → multiplier should decrease (boulder stays wet longer)

    Returns the updated drying_rate_multiplier posterior mean.
    """
    observed_score = BOULDER_CONDITION_SCORES.get(condition, 0.5)

    if _is_outlier(observed_score, recent_reports):
        logger.info("Boulder %d: report '%s' flagged as outlier, skipping param update", boulder_id, condition)
        return (await get_or_create_param(db, "boulder", boulder_id, "drying_rate_multiplier")).posterior_mean

    param = await get_or_create_param(db, "boulder", boulder_id, "drying_rate_multiplier")

    # The multiplier affects dryness score non-linearly (through k_evap integration),
    # so we use a simplified linear approximation for the update:
    # residual in score space → proportional adjustment to multiplier
    residual = observed_score - physics_score_at_report

    # Scale residual to multiplier space (dampened: a 0.3 score gap → ~0.15 multiplier shift)
    target_multiplier = param.posterior_mean + residual * 0.5

    # Kalman update
    new_mean, new_var = _kalman_update(
        param.posterior_mean,
        param.posterior_variance,
        target_multiplier,
        OBSERVATION_NOISE_VAR,
    )

    # Clamp to physically plausible range
    param.posterior_mean = max(0.3, min(3.0, new_mean))
    param.posterior_variance = new_var
    param.n_observations += 1

    await db.flush()
    logger.debug(
        "Boulder %d multiplier updated: %.3f → %.3f (n=%d)",
        boulder_id, param.posterior_mean, new_mean, param.n_observations,
    )
    return param.posterior_mean


async def update_area_params(
    db: AsyncSession,
    area_id: int,
    condition: str,
    physics_score_at_report: float,
    recent_reports: list[UserReport],
) -> float:
    """
    Update the `area_drying_offset` for an area based on an area-level report.

    The offset is a simple additive correction to the area's dryness score.
    Range: [-0.2, +0.2].

    Returns the updated area_drying_offset posterior mean.
    """
    observed_score = AREA_CONDITION_SCORES.get(condition, 0.5)

    if _is_outlier(observed_score, recent_reports):
        logger.info("Area %d: report '%s' flagged as outlier, skipping param update", area_id, condition)
        return (await get_or_create_param(db, "area", area_id, "area_drying_offset")).posterior_mean

    param = await get_or_create_param(db, "area", area_id, "area_drying_offset")

    residual = observed_score - physics_score_at_report
    target_offset = param.posterior_mean + residual * 0.4

    new_mean, new_var = _kalman_update(
        param.posterior_mean,
        param.posterior_variance,
        target_offset,
        OBSERVATION_NOISE_VAR,
    )

    param.posterior_mean = max(-0.2, min(0.2, new_mean))
    param.posterior_variance = new_var
    param.n_observations += 1

    await db.flush()
    return param.posterior_mean


async def get_boulder_characteristics_params(
    db: AsyncSession,
    boulder_id: int,
    area_id: int,
) -> tuple[float, float]:
    """
    Return (drying_rate_multiplier, area_drying_offset) for a boulder.
    Creates default params if they don't exist yet.
    """
    multiplier_param = await get_or_create_param(db, "boulder", boulder_id, "drying_rate_multiplier")
    offset_param = await get_or_create_param(db, "area", area_id, "area_drying_offset")
    return multiplier_param.posterior_mean, offset_param.posterior_mean


async def compute_confidence(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    param_key: str,
) -> float:
    """
    Confidence [0, 1] based on posterior variance reduction.
    Starts at 0.3 (wide prior), approaches 1.0 as variance shrinks.
    """
    param = await get_or_create_param(db, entity_type, entity_id, param_key)

    if param_key == "drying_rate_multiplier":
        initial_var = BOULDER_MULTIPLIER_PRIOR_VAR
    else:
        initial_var = AREA_OFFSET_PRIOR_VAR

    # Confidence = 1 - (current_var / initial_var), floor at 0.3, ceil at 1.0
    variance_ratio = param.posterior_variance / initial_var
    confidence = max(0.3, min(1.0, 1.0 - variance_ratio * 0.7))
    return confidence
