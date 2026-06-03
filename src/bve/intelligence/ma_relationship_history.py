"""
Relationship History Score — Block 1C.

Answers: Does this buyer-target pair have a prior relationship that accelerates
or complicates deal execution?

Key design rules:
  - Default to UNKNOWN gate: no history → score=0.50 (neutral), confidence ≤ 0.50
  - Positive relationships (co-dev, acquisition option) → score > 0.50
  - Negative history (failed negotiation) → score < 0.50
  - No inference from buyer name, target name, or therapeutic area
  - is_unknown flag set when no relationship inputs are provided
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NEUTRAL_SCORE: float = 0.50
_UNKNOWN_CONFIDENCE_CAP: float = 0.50  # max confidence when all inputs unknown

# Relationship type bonus map (how much above neutral each type scores)
_PARTNERSHIP_TYPE_BONUS: dict[str, float] = {
    "co_development": 0.25,
    "licensing_in": 0.12,
    "licensing_out": 0.08,
    "option_to_acquire": 0.30,
    "co_promotion": 0.10,
    "research_collaboration": 0.15,
}

# Recency decay: score peaks at 0y and decays to 0 contribution at 8y
_RECENCY_PEAK_YEARS: float = 0.0
_RECENCY_ZERO_YEARS: float = 8.0


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class RelationshipHistoryScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    relationship_score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    is_unknown: bool = True
    positive_drivers: list[str] = Field(default_factory=list)
    negative_drivers: list[str] = Field(default_factory=list)
    rationale: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _recency_factor(years: float | None) -> float:
    """0.0–1.0 recency weight; None → 0.5 (moderate recency assumed if known partnership)."""
    if years is None:
        return 0.5
    if years <= _RECENCY_PEAK_YEARS:
        return 1.0
    if years >= _RECENCY_ZERO_YEARS:
        return 0.0
    return 1.0 - (years / _RECENCY_ZERO_YEARS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_relationship_history(inputs: dict[str, Any]) -> RelationshipHistoryScore:
    """
    Compute a RelationshipHistoryScore from raw input dict.

    Accepted input keys:
      - prior_partnership: bool | None
      - partnership_type: str | None  (e.g. 'co_development', 'option_to_acquire')
      - acquisition_option: bool | None
      - relationship_recency_years: float | None
      - prior_deal_attempts: int | None
      - prior_deal_outcome: str | None  (e.g. 'failed_negotiation', 'completed')

    Keys that MUST be ignored (no inference):
      - target_name, buyer_name, therapeutic_area, target_market_cap, etc.

    UNKNOWN inputs → is_unknown=True, score=0.50 (neutral), confidence ≤ 0.50
    """
    # Silently ignore inference-bait fields; only read the listed keys
    _ALLOWED_KEYS = {
        "prior_partnership", "partnership_type", "acquisition_option",
        "relationship_recency_years", "prior_deal_attempts", "prior_deal_outcome",
    }
    safe_inputs = {k: v for k, v in inputs.items() if k in _ALLOWED_KEYS}

    # If none of the allowed keys are present, return UNKNOWN gate
    if not safe_inputs:
        return RelationshipHistoryScore(
            relationship_score=_NEUTRAL_SCORE,
            confidence=_UNKNOWN_CONFIDENCE_CAP,
            is_unknown=True,
            rationale="no_relationship_history_provided",
        )

    positive_drivers: list[str] = []
    negative_drivers: list[str] = []
    score_delta: float = 0.0
    n_inputs = 0

    prior_partnership = safe_inputs.get("prior_partnership")
    partnership_type = safe_inputs.get("partnership_type")
    acquisition_option = safe_inputs.get("acquisition_option")
    recency_years = safe_inputs.get("relationship_recency_years")
    prior_attempts = safe_inputs.get("prior_deal_attempts") or 0
    prior_outcome = safe_inputs.get("prior_deal_outcome")

    # Prior partnership
    if prior_partnership is not None:
        n_inputs += 1
        if prior_partnership:
            ptype = str(partnership_type or "").lower()
            bonus = _PARTNERSHIP_TYPE_BONUS.get(ptype, 0.12)
            recency = _recency_factor(recency_years)
            score_delta += bonus * recency
            positive_drivers.append(f"prior_partnership:{ptype or 'unspecified'}")

    # Acquisition option clause
    if acquisition_option is not None:
        n_inputs += 1
        if acquisition_option:
            score_delta += 0.10
            positive_drivers.append("acquisition_option")

    # Failed prior deal attempts
    if prior_attempts > 0:
        n_inputs += 1
        if prior_outcome in {"failed_negotiation", "walked_away", "rejected"}:
            # Failed deal: moderate penalty (still better than cold outreach)
            score_delta -= 0.15 * min(prior_attempts, 2)
            negative_drivers.append(f"prior_deal_failed:{prior_outcome}")
        elif prior_outcome in {"completed", "closed"}:
            score_delta += 0.05
            positive_drivers.append("prior_deal_completed")

    # Clamp final score
    relationship_score = max(0.0, min(1.0, _NEUTRAL_SCORE + score_delta))

    # Confidence: base 0.70, capped at 0.50 if is_unknown, lower if few inputs
    is_unknown = len(safe_inputs) == 0
    if is_unknown:
        confidence = _UNKNOWN_CONFIDENCE_CAP
    else:
        confidence = min(0.85, 0.40 + 0.15 * n_inputs)
        if n_inputs <= 1:
            confidence = min(confidence, _UNKNOWN_CONFIDENCE_CAP)

    return RelationshipHistoryScore(
        relationship_score=round(relationship_score, 6),
        confidence=round(confidence, 6),
        is_unknown=is_unknown,
        positive_drivers=positive_drivers,
        negative_drivers=negative_drivers,
        rationale=(
            f"score_delta={score_delta:.3f}; n_inputs={n_inputs}; "
            f"is_unknown={is_unknown}"
        ),
    )
