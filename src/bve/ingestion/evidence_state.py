"""
EvidenceState — explicit evidence classification schema v1.

Replaces the implicit "no record = missing signal" assumption with a
first-class distinction between:

    missing           — no evidence found; no score impact
    present_neutral   — evidence found; no directional signal
    present_positive  — evidence found; positive signal
    present_negative  — evidence found; negative signal

These must never be conflated. A company with zero trial records is
different from a company with 10 trial discontinuations.

schema_version on EvidenceRecord
---------------------------------
    None / "legacy"        — written before this schema; reader treats as
                             present_neutral, classification_confidence=low
    "evidence_state_v1"    — written with a full EvidenceState attached

Scoring rule
------------
When classification_confidence = low OR source_quality = low:
    effective_delta = raw_delta * 0.25

When signal_state = missing:
    effective_delta = 0.0  (never penalise absence of evidence)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SignalState(str, Enum):
    MISSING          = "missing"
    PRESENT_NEUTRAL  = "present_neutral"
    PRESENT_POSITIVE = "present_positive"
    PRESENT_NEGATIVE = "present_negative"


class MaterialityTier(str, Enum):
    IMMATERIAL      = "immaterial"    # no score impact; record kept for audit
    MINOR           = "minor"         # 25% of base delta
    MATERIAL        = "material"      # 60% of base delta
    THESIS_CHANGING = "thesis_changing"  # 100% of base delta


class SourceQuality(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


class Recency(str, Enum):
    STALE   = "stale"    # event > 24 months old
    CURRENT = "current"  # event <= 24 months old


class AppliesTo(str, Enum):
    LEAD_ASSET      = "lead_asset"
    PIPELINE_ASSET  = "pipeline_asset"
    NON_CORE        = "non_core"
    COMPANY_GENERAL = "company_general"


class ClassificationConfidence(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


# ---------------------------------------------------------------------------
# Delta scaling by materiality tier
# ---------------------------------------------------------------------------

MATERIALITY_DELTA_SCALE: dict[MaterialityTier, float] = {
    MaterialityTier.IMMATERIAL:      0.00,
    MaterialityTier.MINOR:           0.25,
    MaterialityTier.MATERIAL:        0.60,
    MaterialityTier.THESIS_CHANGING: 1.00,
}

# Additional downweight when detection quality is low
LOW_QUALITY_SCALE: float = 0.25


# ---------------------------------------------------------------------------
# EvidenceState
# ---------------------------------------------------------------------------

@dataclass
class EvidenceState:
    """
    Explicit evidence state for one ledger record.

    Attach to EvidenceRecord.evidence_state (serialised as dict).

    Fields
    ------
    signal_state : SignalState
        Whether evidence exists and in which direction.
    materiality : MaterialityTier
        Economic / M&A relevance of this specific event.
    source_quality : SourceQuality
        Reliability of the underlying data source.
    recency : Recency
        Whether the event is current (<=24 months) or stale.
    applies_to : AppliesTo
        Which part of the company the event concerns.
    classification_confidence : ClassificationConfidence
        Confidence in the signal_state assignment itself.
        LOW means a weak parser guess; HIGH means confirmed from primary source.
    """
    signal_state:              SignalState             = SignalState.PRESENT_NEUTRAL
    materiality:               MaterialityTier         = MaterialityTier.MINOR
    source_quality:            SourceQuality           = SourceQuality.MEDIUM
    recency:                   Recency                 = Recency.CURRENT
    applies_to:                AppliesTo               = AppliesTo.COMPANY_GENERAL
    classification_confidence: ClassificationConfidence = ClassificationConfidence.MEDIUM

    def effective_delta_scale(self) -> float:
        """
        Combined scale factor to apply to raw score_deltas.

        Returns 0.0 for missing signal (never penalise absence of evidence).
        Downgrades aggressively when source_quality or classification_confidence is low.
        """
        if self.signal_state == SignalState.MISSING:
            return 0.0

        scale = MATERIALITY_DELTA_SCALE[self.materiality]

        if (
            self.source_quality == SourceQuality.LOW
            or self.classification_confidence == ClassificationConfidence.LOW
        ):
            scale *= LOW_QUALITY_SCALE

        return scale

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EvidenceState":
        return cls(
            signal_state=SignalState(d.get("signal_state", "present_neutral")),
            materiality=MaterialityTier(d.get("materiality", "minor")),
            source_quality=SourceQuality(d.get("source_quality", "medium")),
            recency=Recency(d.get("recency", "current")),
            applies_to=AppliesTo(d.get("applies_to", "company_general")),
            classification_confidence=ClassificationConfidence(
                d.get("classification_confidence", "medium")
            ),
        )

    @classmethod
    def legacy(cls) -> "EvidenceState":
        """Default state for records written before evidence_state_v1."""
        return cls(
            signal_state=SignalState.PRESENT_NEUTRAL,
            materiality=MaterialityTier.MINOR,
            source_quality=SourceQuality.MEDIUM,
            recency=Recency.CURRENT,
            applies_to=AppliesTo.COMPANY_GENERAL,
            classification_confidence=ClassificationConfidence.LOW,
        )
