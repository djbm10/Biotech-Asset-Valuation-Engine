"""Stage A of the two-stage M&A model: acquisition likelihood scoring.

Stage A answers: "Is this company a likely acquisition target within the horizon?"
Stage B (acquirer ranking in ma_probability.py) then answers: "Which acquirer is most likely,
conditional on an acquisition occurring?"

Separating the two stages prevents the acquirer-fit score from dominating the decision
about whether an acquisition is even plausible.  A company can be a poor strategic fit
for every specific acquirer in the database yet still be a likely target (e.g., for a
buyer not yet in the profile list), and vice-versa.

Stage A features
----------------
- valuation_discount_score:  deep discount → higher likelihood (acquirer extracts value)
- capital_vulnerability_score: financing stress → target more motivated to sell
- de_risking_stage_score: Phase 2+ PoC data → acquirer can underwrite the asset
- scarcity_score: unique mechanism/target class → acquisition premium for scarcity
- ta_heat_score: recent deal activity in same TA → elevated M&A environment
- catalyst_proximity_score: near-term readout → binary event that can catalyse a process
- affordability_score: mid-cap sweet spot → large acquirers can execute; not too small
"""
from __future__ import annotations

import math
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Feature weights for Stage A probability
# ---------------------------------------------------------------------------

# These weights are evidence-informed priors, not statistically estimated coefficients.
# They encode the relative importance of each signal for whether an acquisition occurs,
# independent of which acquirer might be involved.
STAGE_A_FEATURE_WEIGHTS: dict[str, float] = {
    "de_risking_stage_score": 0.25,       # clinical readiness is the strongest signal
    "strategic_scarcity": 0.20,           # unique assets command the highest premiums
    "capital_vulnerability_score": 0.20,  # stressed companies more likely to sell
    "ta_heat_score": 0.15,                # hot TA → elevated probability of any deal
    "valuation_discount_score": 0.10,     # discounted to model → acquirer value creation
    "catalyst_proximity_score": 0.10,     # near binary event creates process momentum
}

# EV thresholds for affordability scoring (millions USD).
# Mid-cap sweet spot: large enough to move the needle for a Big Pharma acquirer,
# small enough to execute without requiring mega-deal board approval.
_AFFORDABILITY_EV_SWEET_SPOT_LOW_M = 300.0
_AFFORDABILITY_EV_SWEET_SPOT_HIGH_M = 5_000.0
_AFFORDABILITY_EV_MEGA_CAP_M = 15_000.0


class AcquisitionLikelihoodFeatures(BaseModel):
    """Deterministic feature vector for Stage A acquisition likelihood scoring."""

    # From MAProbabilityRow / MACalibrationRow
    de_risking_stage_score: float = Field(default=0.0, ge=0.0, le=1.0)
    scarcity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    capital_vulnerability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    ta_heat_score: float = Field(default=0.0, ge=0.0, le=1.0)
    valuation_discount_score: float = Field(default=0.0, ge=0.0, le=1.0)
    # Derived features
    days_to_catalyst: Optional[int] = None
    enterprise_value_millions: Optional[float] = None


def _catalyst_proximity_score(days_to_catalyst: Optional[int]) -> float:
    """Map days-to-catalyst to a 0-1 proximity score.

    Score peaks at 30-90 days (optimal process window), falls off for very
    near-term (no time to run a process) and long-horizon catalysts.
    """
    if days_to_catalyst is None:
        return 0.0
    d = int(days_to_catalyst)
    if d <= 0:
        return 0.0
    if d > 730:
        return 0.0
    # Gaussian-shaped peak centred at 60 days, width ≈ 120 days
    return round(math.exp(-((d - 60.0) ** 2) / (2.0 * 120.0 ** 2)), 6)


def _affordability_score(enterprise_value_millions: Optional[float]) -> float:
    """Return 1.0 for mid-cap sweet spot, taper to 0 at mega-cap extremes."""
    if enterprise_value_millions is None:
        return 0.5  # neutral — no data
    ev = max(0.0, float(enterprise_value_millions))
    if ev < _AFFORDABILITY_EV_SWEET_SPOT_LOW_M:
        # Too small — may not move the needle for large acquirers; still possible
        return 0.5
    if ev <= _AFFORDABILITY_EV_SWEET_SPOT_HIGH_M:
        return 1.0
    if ev >= _AFFORDABILITY_EV_MEGA_CAP_M:
        return 0.0
    # Linear taper between sweet-spot high and mega-cap threshold
    fraction = (ev - _AFFORDABILITY_EV_SWEET_SPOT_HIGH_M) / (
        _AFFORDABILITY_EV_MEGA_CAP_M - _AFFORDABILITY_EV_SWEET_SPOT_HIGH_M
    )
    return round(max(0.0, 1.0 - fraction), 6)


def compute_acquisition_likelihood(features: AcquisitionLikelihoodFeatures) -> float:
    """Compute deterministic Stage A acquisition likelihood score in [0, 1].

    The score is a weighted average of the Stage A feature vector.  Affordability
    is used as a multiplier rather than a weighted term to hard-gate mega-cap names.
    """
    catalyst_prox = _catalyst_proximity_score(features.days_to_catalyst)
    affordability = _affordability_score(features.enterprise_value_millions)

    weighted = (
        STAGE_A_FEATURE_WEIGHTS["de_risking_stage_score"] * features.de_risking_stage_score
        + STAGE_A_FEATURE_WEIGHTS["strategic_scarcity"] * features.scarcity_score
        + STAGE_A_FEATURE_WEIGHTS["capital_vulnerability_score"] * features.capital_vulnerability_score
        + STAGE_A_FEATURE_WEIGHTS["ta_heat_score"] * features.ta_heat_score
        + STAGE_A_FEATURE_WEIGHTS["valuation_discount_score"] * features.valuation_discount_score
        + STAGE_A_FEATURE_WEIGHTS["catalyst_proximity_score"] * catalyst_prox
    )

    # Affordability acts as a scalar: keeps the full score in the sweet spot,
    # reduces it progressively for mega-caps, and floors at 0 when EV is known
    # to be too large for any typical acquirer.
    raw = weighted * affordability
    return round(max(0.0, min(1.0, raw)), 6)


def features_from_calibration_row(row: object) -> AcquisitionLikelihoodFeatures:
    """Extract Stage A features from a MACalibrationRow (or any object with those attrs)."""
    def _f(name: str, default: float = 0.0) -> float:
        v = getattr(row, name, None)
        return float(v) if v is not None else default

    return AcquisitionLikelihoodFeatures(
        de_risking_stage_score=_f("de_risking_stage_score"),
        scarcity_score=_f("scarcity_score"),
        capital_vulnerability_score=_f("capital_vulnerability_score"),
        ta_heat_score=_f("ta_heat_score"),
        valuation_discount_score=_f("valuation_discount_score"),
        days_to_catalyst=getattr(row, "days_to_catalyst", None),
        enterprise_value_millions=getattr(row, "enterprise_value_millions", None)
        or getattr(row, "ev_millions", None),
    )
