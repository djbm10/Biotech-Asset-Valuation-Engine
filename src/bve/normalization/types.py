"""
Canonical normalization data models.

Every normalizer call returns a NormalizationResult that carries both the
canonical identifier and an explicit confidence tier.  Callers MUST check
``confidence`` or ``is_trustworthy`` before trusting ``canonical_id``.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class NormalizationConfidence(str, Enum):
    HIGH = "high"      # Exact synonym match in registry
    MEDIUM = "medium"  # Fuzzy match, score >= 85
    LOW = "low"        # Fuzzy match, 70 <= score < 85; populated but flagged
    FAILED = "failed"  # No match >= 70; canonical_id is None


class NormalizationResult(BaseModel):
    """Result of normalizing a single raw string to a canonical entity."""

    raw_input: str
    canonical_id: Optional[str] = None
    canonical_name: Optional[str] = None
    confidence: NormalizationConfidence
    match_score: float = 0.0
    method: Literal["exact", "fuzzy", "split", "none"] = "none"
    # Top-3 alternatives for human review (canonical_id, score)
    alternatives: list[tuple[str, float]] = Field(default_factory=list)
    # Structural notes set by normalizer (e.g. "multi_indication_detected")
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_trustworthy(self) -> bool:
        """True only for HIGH and MEDIUM confidence results."""
        return self.confidence in (NormalizationConfidence.HIGH, NormalizationConfidence.MEDIUM)


class CanonicalIndication(BaseModel):
    """Registry entry for a single canonical disease/indication."""

    id: str                             # e.g. "IND_ulcerative_colitis"
    name: str                           # Human-readable: "Ulcerative Colitis"
    aliases: list[str]                  # All synonym strings that map here
    therapeutic_area: Optional[str] = None   # Links to TherapeuticArea enum value


class CanonicalTarget(BaseModel):
    """Registry entry for a single canonical biological target."""

    id: str                             # e.g. "TGT_pd1"
    name: str                           # "PD-1"
    aliases: list[str]


class CanonicalMOA(BaseModel):
    """Registry entry for a single canonical mechanism of action."""

    id: str                             # e.g. "MOA_pd1_checkpoint_inhibitor"
    name: str                           # "PD-1/PD-L1 Checkpoint Inhibitor"
    aliases: list[str]
