"""
Buyer Mandate Score — Block 1A.

Answers: Does the acquirer have a live BD mandate for this therapeutic area?

Key design rules:
  - executive_alignment_signal is EVIDENCE-BASED ONLY (dated statements, never inferred)
  - UNKNOWN inputs → no penalty, lower confidence only
  - Staleness warning when any guidance statement is > 90 days old
  - No target-level signals (target_ta, target_market_cap) are ever read here
  - Anti-double-counting: pipeline_gap_urgency here is BUYER-LEVEL
    (does the buyer have a gap?); pair-level urgency lives in strategic_urgency_score
"""
from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STALENESS_THRESHOLD_DAYS: int = 90

# Weights for mandate score sub-components
_MANDATE_WEIGHTS: dict[str, float] = {
    "executive_alignment": 0.35,
    "pipeline_gap_severity": 0.30,
    "recent_ma_cadence": 0.20,
    "rd_day_priority": 0.15,
}
assert abs(sum(_MANDATE_WEIGHTS.values()) - 1.0) < 1e-9

# Tier thresholds
_ACTIVE_MANDATE_THRESHOLD: float = 0.68
_TACTICAL_THRESHOLD: float = 0.50
_OPPORTUNISTIC_THRESHOLD: float = 0.32


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MandateTier(str, Enum):
    """Classification of acquirer BD mandate strength."""
    ACTIVE_MANDATE = "active_mandate"     # Live, stated mandate with exec backing
    TACTICAL = "tactical"                  # Selective, area-aligned, not loudly stated
    OPPORTUNISTIC = "opportunistic"        # Open to deals but no clear mandate
    MONITORING = "monitoring"              # No current mandate signal


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class ExecutiveAlignmentSignal(BaseModel):
    """A single dated evidence item supporting executive BD alignment."""
    model_config = ConfigDict(frozen=True)

    text: str
    source_date: date
    source: str


class BuyerMandateScore(BaseModel):
    """Output of compute_buyer_mandate_score."""
    model_config = ConfigDict(frozen=True)

    mandate_score: float = Field(..., ge=0.0, le=1.0)
    mandate_tier: MandateTier
    confidence: float = Field(..., ge=0.0, le=1.0)
    executive_alignment_signal: ExecutiveAlignmentSignal | None = None
    staleness_warning: bool = False
    missing_data: list[str] = Field(default_factory=list)
    positive_drivers: list[str] = Field(default_factory=list)
    rationale: str = ""

    # Sub-component scores for diagnostics
    executive_alignment_score: float = Field(default=0.0, ge=0.0, le=1.0)
    pipeline_gap_score: float = Field(default=0.0, ge=0.0, le=1.0)
    recent_ma_cadence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    rd_day_priority_score: float = Field(default=0.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_score(
    raw: float | None,
    *,
    missing_list: list[str],
    field_name: str,
    default: float = 0.50,
) -> tuple[float, bool]:
    """Return (score, is_known).

    UNKNOWN → neutral default, lower confidence via missing_list,
    no penalty applied.
    """
    if raw is None:
        missing_list.append(field_name)
        return default, False
    return float(raw), True


def _parse_guidance_statements(
    raw: list[dict] | None,
) -> tuple[list[ExecutiveAlignmentSignal], bool, bool]:
    """
    Parse bd_guidance_statements list.

    Returns:
        (signals, any_found, any_stale)
    """
    if not raw:
        return [], False, False

    signals: list[ExecutiveAlignmentSignal] = []
    any_stale = False
    cutoff = date.today() - timedelta(days=_STALENESS_THRESHOLD_DAYS)

    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            raw_date = item.get("date")
            if isinstance(raw_date, str):
                parsed_date = date.fromisoformat(raw_date)
            elif isinstance(raw_date, date):
                parsed_date = raw_date
            else:
                continue
            text = str(item.get("text", ""))
            source = str(item.get("source", "unknown"))
            signals.append(ExecutiveAlignmentSignal(text=text, source_date=parsed_date, source=source))
            if parsed_date < cutoff:
                any_stale = True
        except (ValueError, TypeError):
            continue

    return signals, bool(signals), any_stale


def _score_executive_alignment(signals: list[ExecutiveAlignmentSignal]) -> float:
    """Convert evidence signals to a 0–1 alignment score."""
    if not signals:
        return 0.0
    # More recent signals score higher; cap at 1.0
    today = date.today()
    scores = []
    for sig in signals:
        days_old = (today - sig.source_date).days
        recency_factor = max(0.0, 1.0 - days_old / 365.0)
        scores.append(recency_factor)
    return min(1.0, max(scores) * 0.90 + 0.10)


def _score_rd_day_priority(rd_areas: list[str] | None, missing_list: list[str]) -> tuple[float, bool]:
    if rd_areas is None:
        missing_list.append("rd_day_priority_areas")
        return 0.50, False  # neutral, UNKNOWN
    if len(rd_areas) == 0:
        return 0.10, True  # known: no R&D Day priority areas
    return min(1.0, 0.40 + 0.20 * len(rd_areas)), True


def _classify_tier(score: float) -> MandateTier:
    if score >= _ACTIVE_MANDATE_THRESHOLD:
        return MandateTier.ACTIVE_MANDATE
    if score >= _TACTICAL_THRESHOLD:
        return MandateTier.TACTICAL
    if score >= _OPPORTUNISTIC_THRESHOLD:
        return MandateTier.OPPORTUNISTIC
    return MandateTier.MONITORING


def _compute_confidence(n_known: int, n_total: int, base: float = 0.70) -> float:
    """Lower confidence proportional to fraction of unknown inputs."""
    if n_total == 0:
        return base
    fraction_known = n_known / n_total
    return max(0.20, base * (0.40 + 0.60 * fraction_known))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_buyer_mandate_score(inputs: dict[str, Any]) -> BuyerMandateScore:
    """
    Compute a BuyerMandateScore from raw input dict.

    Accepted input keys:
      - bd_guidance_statements: list[dict] — each with 'text', 'date', 'source'
      - rd_day_priority_areas: list[str] | None
      - pipeline_gap_severity: float [0,1] | None
      - recent_ma_cadence: float [0,1] | None

    Target-level keys (target_market_cap_billions, target_therapeutic_area, etc.)
    are silently ignored to prevent anti-double-counting.
    """
    missing_data: list[str] = []
    positive_drivers: list[str] = []

    # Parse guidance statements (evidence-based executive alignment)
    raw_guidance = inputs.get("bd_guidance_statements")
    signals, has_signals, any_stale = _parse_guidance_statements(raw_guidance)
    exec_score = _score_executive_alignment(signals)
    if has_signals:
        positive_drivers.append("bd_guidance_statements")
    else:
        missing_data.append("bd_guidance_statements")

    # Best signal for the output field (most recent)
    best_signal: ExecutiveAlignmentSignal | None = None
    if signals:
        best_signal = max(signals, key=lambda s: s.source_date)

    # Pipeline gap severity (buyer-level: does buyer have a gap?)
    raw_gap = inputs.get("pipeline_gap_severity")
    if isinstance(raw_gap, (int, float)):
        gap_score = float(raw_gap)
        gap_known = True
        if gap_score > 0.5:
            positive_drivers.append("pipeline_gap_severity")
    else:
        gap_score, gap_known = 0.50, False  # neutral unknown
        missing_data.append("pipeline_gap_severity")

    # Recent M&A cadence
    raw_cadence = inputs.get("recent_ma_cadence")
    if isinstance(raw_cadence, (int, float)):
        cadence_score = float(raw_cadence)
        cadence_known = True
        if cadence_score > 0.5:
            positive_drivers.append("recent_ma_cadence")
    else:
        cadence_score, cadence_known = 0.50, False
        missing_data.append("recent_ma_cadence")

    # R&D Day priority areas
    rd_areas = inputs.get("rd_day_priority_areas")
    rd_score, rd_known = _score_rd_day_priority(rd_areas, missing_data)
    if rd_known and rd_areas:
        positive_drivers.append("rd_day_priority_areas")

    # Composite mandate score (weighted sum)
    mandate_score = (
        _MANDATE_WEIGHTS["executive_alignment"] * exec_score
        + _MANDATE_WEIGHTS["pipeline_gap_severity"] * gap_score
        + _MANDATE_WEIGHTS["recent_ma_cadence"] * cadence_score
        + _MANDATE_WEIGHTS["rd_day_priority"] * rd_score
    )
    mandate_score = max(0.0, min(1.0, mandate_score))

    # Confidence
    n_known = sum([has_signals, gap_known, cadence_known, rd_known])
    confidence = _compute_confidence(n_known, 4)

    tier = _classify_tier(mandate_score)

    rationale_parts = [f"tier={tier.value}", f"score={mandate_score:.3f}"]
    if any_stale:
        rationale_parts.append("staleness_warning=True")

    return BuyerMandateScore(
        mandate_score=round(mandate_score, 6),
        mandate_tier=tier,
        confidence=round(confidence, 6),
        executive_alignment_signal=best_signal,
        staleness_warning=any_stale,
        missing_data=missing_data,
        positive_drivers=positive_drivers,
        rationale="; ".join(rationale_parts),
        executive_alignment_score=round(exec_score, 6),
        pipeline_gap_score=round(gap_score, 6),
        recent_ma_cadence_score=round(cadence_score, 6),
        rd_day_priority_score=round(rd_score, 6),
    )
