"""
Internal Conflict Score — Block 1E.

Answers: Does this buyer have internal barriers that would make pursuing this
target structurally problematic regardless of strategic fit?

Conflict sources:
  - Existing pipeline overlap (cannibalisation risk)
  - Commercial channel conflict
  - Partner ROFR (right of first refusal / first negotiation)
  - Pending portfolio acquisition (integration bandwidth exhausted)

Key design rules:
  - UNKNOWN inputs → benefit of doubt (do not inflate conflict score)
  - Lower confidence only when inputs are unknown
  - ConflictLevel.BLOCKING is reserved for combinations that make a deal
    unlikely to proceed, not just difficult
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Weights for conflict sub-components
_CONFLICT_WEIGHTS: dict[str, float] = {
    "existing_pipeline_overlap": 0.35,
    "commercial_channel_conflict": 0.30,
    "partner_rofr_present": 0.20,
    "pending_portfolio_acquisition": 0.15,
}
assert abs(sum(_CONFLICT_WEIGHTS.values()) - 1.0) < 1e-9

_BLOCKING_THRESHOLD: float = 0.72
_MODERATE_THRESHOLD: float = 0.45
_MINOR_THRESHOLD: float = 0.20


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ConflictLevel(str, Enum):
    """Severity of internal conflict for this buyer-target pair."""
    NONE = "none"
    MINOR = "minor"
    MODERATE = "moderate"
    BLOCKING = "blocking"


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class InternalConflictScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    conflict_score: float = Field(..., ge=0.0, le=1.0)
    conflict_level: ConflictLevel
    confidence: float = Field(..., ge=0.0, le=1.0)
    conflict_drivers: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    rationale: str = ""

    # Sub-component scores for diagnostics
    pipeline_overlap_score: float = Field(default=0.0, ge=0.0, le=1.0)
    channel_conflict_score: float = Field(default=0.0, ge=0.0, le=1.0)
    rofr_score: float = Field(default=0.0, ge=0.0, le=1.0)
    pending_acq_score: float = Field(default=0.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_float(
    raw: Any,
    *,
    field_name: str,
    missing_list: list[str],
    default_unknown: float = 0.0,  # benefit of doubt for unknown conflict
) -> tuple[float, bool]:
    """Return (score, is_known). UNKNOWN → 0.0 (no inflation)."""
    if raw is None:
        missing_list.append(field_name)
        return default_unknown, False
    try:
        return float(raw), True
    except (TypeError, ValueError):
        missing_list.append(field_name)
        return default_unknown, False


def _resolve_bool(
    raw: Any,
    *,
    field_name: str,
    missing_list: list[str],
) -> tuple[float, bool]:
    """Convert boolean flag to float (True=1.0, False=0.0, None=unknown→0.0)."""
    if raw is None:
        missing_list.append(field_name)
        return 0.0, False  # benefit of doubt: assume no ROFR/pending if unknown
    return 1.0 if bool(raw) else 0.0, True


def _classify_level(score: float) -> ConflictLevel:
    if score >= _BLOCKING_THRESHOLD:
        return ConflictLevel.BLOCKING
    if score >= _MODERATE_THRESHOLD:
        return ConflictLevel.MODERATE
    if score >= _MINOR_THRESHOLD:
        return ConflictLevel.MINOR
    return ConflictLevel.NONE


def _compute_confidence(n_known: int, n_total: int, base: float = 0.75) -> float:
    if n_total == 0:
        return base
    fraction_known = n_known / n_total
    return max(0.20, base * (0.40 + 0.60 * fraction_known))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_internal_conflict(inputs: dict[str, Any]) -> InternalConflictScore:
    """
    Compute an InternalConflictScore from raw input dict.

    Accepted input keys:
      - existing_pipeline_overlap: float [0,1] | None
      - commercial_channel_conflict: float [0,1] | None
      - partner_rofr_present: bool | None
      - pending_portfolio_acquisition: bool | None

    UNKNOWN inputs: benefit of doubt → treated as 0.0 (no conflict assumed),
    confidence reduced.
    """
    missing_data: list[str] = []
    conflict_drivers: list[str] = []

    overlap_score, overlap_known = _resolve_float(
        inputs.get("existing_pipeline_overlap"),
        field_name="existing_pipeline_overlap",
        missing_list=missing_data,
    )
    channel_score, channel_known = _resolve_float(
        inputs.get("commercial_channel_conflict"),
        field_name="commercial_channel_conflict",
        missing_list=missing_data,
    )
    rofr_score, rofr_known = _resolve_bool(
        inputs.get("partner_rofr_present"),
        field_name="partner_rofr_present",
        missing_list=missing_data,
    )
    pending_score, pending_known = _resolve_bool(
        inputs.get("pending_portfolio_acquisition"),
        field_name="pending_portfolio_acquisition",
        missing_list=missing_data,
    )

    composite = (
        _CONFLICT_WEIGHTS["existing_pipeline_overlap"] * overlap_score
        + _CONFLICT_WEIGHTS["commercial_channel_conflict"] * channel_score
        + _CONFLICT_WEIGHTS["partner_rofr_present"] * rofr_score
        + _CONFLICT_WEIGHTS["pending_portfolio_acquisition"] * pending_score
    )
    composite = max(0.0, min(1.0, composite))

    # Track notable drivers
    if overlap_score > 0.40:
        conflict_drivers.append("high_pipeline_overlap")
    if channel_score > 0.40:
        conflict_drivers.append("commercial_channel_conflict")
    if rofr_score > 0.5:
        conflict_drivers.append("partner_rofr_present")
    if pending_score > 0.5:
        conflict_drivers.append("pending_portfolio_acquisition")

    n_known = sum([overlap_known, channel_known, rofr_known, pending_known])
    confidence = _compute_confidence(n_known, 4)
    level = _classify_level(composite)

    return InternalConflictScore(
        conflict_score=round(composite, 6),
        conflict_level=level,
        confidence=round(confidence, 6),
        conflict_drivers=conflict_drivers,
        missing_data=missing_data,
        rationale=f"level={level.value}; score={composite:.3f}",
        pipeline_overlap_score=round(overlap_score, 6),
        channel_conflict_score=round(channel_score, 6),
        rofr_score=round(rofr_score, 6),
        pending_acq_score=round(pending_score, 6),
    )
