"""
Buyer-Target Thesis Aggregator — Block 1D.

Assembles BuyerMandateScore, InternalConflictScore, and RelationshipHistoryScore
into a single BuyerTargetThesis with an UnderwriteThesis classification.

Rules:
  - BLOCKING conflict → always PASS regardless of mandate strength
  - ACTIVE_MANDATE + low conflict + positive relationship → STRONG_BUY
  - Overall confidence is the minimum of its components (conservative propagation)
  - UNKNOWN components lower confidence; they do not change the thesis tier
    unless conflict is forced BLOCKING
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from bve.intelligence.ma_buyer_mandate import BuyerMandateScore, MandateTier
from bve.intelligence.ma_internal_conflict import InternalConflictScore, ConflictLevel
from bve.intelligence.ma_relationship_history import RelationshipHistoryScore


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------

class UnderwriteThesis(str, Enum):
    """Top-level buyer-target pair thesis classification."""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    MONITOR = "monitor"
    PASS = "pass"


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class BuyerTargetThesis(BaseModel):
    model_config = ConfigDict(frozen=True)

    underwrite_thesis: UnderwriteThesis
    thesis_score: float = Field(..., ge=0.0, le=1.0)
    overall_confidence: float = Field(..., ge=0.0, le=1.0)

    mandate_tier: MandateTier
    conflict_level: ConflictLevel
    relationship_is_unknown: bool

    positive_signals: list[str] = Field(default_factory=list)
    negative_signals: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    rationale: str = ""

    # Component scores for transparency
    mandate_score: float = Field(..., ge=0.0, le=1.0)
    conflict_score: float = Field(..., ge=0.0, le=1.0)
    relationship_score: float = Field(..., ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Thesis weights
# ---------------------------------------------------------------------------

_THESIS_WEIGHTS: dict[str, float] = {
    "mandate": 0.50,
    "relationship": 0.30,
    "conflict_penalty": 0.20,
}
assert abs(sum(_THESIS_WEIGHTS.values()) - 1.0) < 1e-9

# Thesis tier thresholds (applied to thesis_score after conflict adjustment)
_STRONG_BUY_THRESHOLD: float = 0.70
_BUY_THRESHOLD: float = 0.52
_MONITOR_THRESHOLD: float = 0.35


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _conflict_penalty(conflict_score: float) -> float:
    """Convert conflict score to a 0–1 penalty term (higher = more penalty)."""
    return conflict_score


def _classify_thesis(score: float, conflict_level: ConflictLevel) -> UnderwriteThesis:
    if conflict_level == ConflictLevel.BLOCKING:
        return UnderwriteThesis.PASS
    if score >= _STRONG_BUY_THRESHOLD:
        return UnderwriteThesis.STRONG_BUY
    if score >= _BUY_THRESHOLD:
        return UnderwriteThesis.BUY
    if score >= _MONITOR_THRESHOLD:
        return UnderwriteThesis.MONITOR
    return UnderwriteThesis.PASS


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_buyer_target_thesis(
    *,
    mandate_score: BuyerMandateScore,
    conflict_score: InternalConflictScore,
    relationship_score: RelationshipHistoryScore,
) -> BuyerTargetThesis:
    """
    Aggregate component scores into a BuyerTargetThesis.

    Confidence is propagated conservatively: overall_confidence = min of components.
    BLOCKING conflict → PASS immediately.
    """
    positive_signals: list[str] = []
    negative_signals: list[str] = []
    missing_data: list[str] = list(mandate_score.missing_data)

    # Mandate contribution (0–1, higher = better)
    mandate_contrib = mandate_score.mandate_score
    if mandate_score.mandate_tier in {MandateTier.ACTIVE_MANDATE, MandateTier.TACTICAL}:
        positive_signals.extend(mandate_score.positive_drivers)

    # Relationship contribution (0–1; 0.50 neutral for unknown)
    rel_contrib = relationship_score.relationship_score
    if relationship_score.positive_drivers:
        positive_signals.extend(relationship_score.positive_drivers)
    if relationship_score.negative_drivers:
        negative_signals.extend(relationship_score.negative_drivers)
    if relationship_score.is_unknown:
        missing_data.append("relationship_history")

    # Conflict penalty (inverted: 0 = clean, 1 = blocking)
    conflict_penalty = _conflict_penalty(conflict_score.conflict_score)
    if conflict_score.conflict_drivers:
        negative_signals.extend(conflict_score.conflict_drivers)
    if conflict_score.missing_data:
        missing_data.extend(conflict_score.missing_data)

    # Thesis score:
    #   mandate * 0.50 + relationship * 0.30 - conflict_penalty * 0.20
    raw_score = (
        _THESIS_WEIGHTS["mandate"] * mandate_contrib
        + _THESIS_WEIGHTS["relationship"] * rel_contrib
        - _THESIS_WEIGHTS["conflict_penalty"] * conflict_penalty
    )
    thesis_score = max(0.0, min(1.0, raw_score))

    # Conservative confidence propagation
    overall_confidence = min(
        mandate_score.confidence,
        conflict_score.confidence,
        relationship_score.confidence,
    )

    thesis = _classify_thesis(thesis_score, conflict_score.conflict_level)

    return BuyerTargetThesis(
        underwrite_thesis=thesis,
        thesis_score=round(thesis_score, 6),
        overall_confidence=round(overall_confidence, 6),
        mandate_tier=mandate_score.mandate_tier,
        conflict_level=conflict_score.conflict_level,
        relationship_is_unknown=relationship_score.is_unknown,
        positive_signals=positive_signals,
        negative_signals=negative_signals,
        missing_data=list(dict.fromkeys(missing_data)),  # dedup preserving order
        rationale=(
            f"thesis={thesis.value}; score={thesis_score:.3f}; "
            f"mandate={mandate_contrib:.3f}; conflict={conflict_penalty:.3f}; "
            f"rel={rel_contrib:.3f}"
        ),
        mandate_score=round(mandate_contrib, 6),
        conflict_score=round(conflict_score.conflict_score, 6),
        relationship_score=round(rel_contrib, 6),
    )
