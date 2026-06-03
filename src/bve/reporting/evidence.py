"""
Structured evidence reference models for memo sections.

Design principles:
- Every major memo claim should trace to a MemoEvidenceRef.
- Evidence is never faked: if a source is absent, it is flagged in
  ``unsupported_claims`` rather than silently omitted.
- Confidence is always explicit; "—" is the only acceptable placeholder.
- Renderers treat ``MemoSectionEvidence`` as a self-contained unit:
  they can display it as a table, footnotes, or collapse it entirely
  without knowing what populated it.

Source types:
    assumption      KeyAssumption from AssumptionLog (structured, auditable)
    signal          StructuredSignal extracted from a document (LLM-parsed)
    event           Event object (observed fact with source_url)
    deal_comp       ComparableDeal record from the M&A database
    knowledge_art   KnowledgeArtifact (analyst synthesis with signal FKs)
    manual          Analyst-entered free-text citation (lowest trust)
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    ASSUMPTION = "assumption"
    SIGNAL = "signal"
    EVENT = "event"
    DEAL_COMP = "deal_comp"
    KNOWLEDGE_ART = "knowledge_art"
    MANUAL = "manual"


class MemoEvidenceRef(BaseModel):
    """
    A single traceable evidence reference for one memo claim.

    Normalized across all source types so templates only need one rendering path.
    """

    source_type: SourceType
    label: str                              # Human-readable: "WACC: 12% · Damodaran biotech WACC"
    source_id: Optional[str] = None        # FK to source object (signal_id, deal target_name, etc.)
    url: Optional[str] = None             # Direct link to primary source
    confidence_label: str = "—"           # "High" | "Medium" | "Low" | "—"
    confidence_score: Optional[float] = None   # 0.0–1.0 numeric when available
    as_of_date: Optional[str] = None      # ISO date or "YYYY-Q#" string
    notes: Optional[str] = None
    # True when this ref marks a KNOWN GAP — the claim exists but evidence is absent
    is_gap: bool = False

    @property
    def confidence_display(self) -> str:
        """Render confidence as label if available, else format score, else '—'."""
        if self.confidence_label and self.confidence_label != "—":
            return self.confidence_label
        if self.confidence_score is not None:
            return f"{self.confidence_score:.0%}"
        return "—"


class MemoSectionEvidence(BaseModel):
    """
    All evidence refs for one named memo section.

    ``refs`` contains structured evidence.
    ``unsupported_claims`` names specific claims that have NO supporting
    structured data — surfaced explicitly so the analyst knows what to fill.
    """

    section_key: str                            # "biology" | "trial" | "competitive" | etc.
    refs: list[MemoEvidenceRef] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)

    @property
    def has_evidence(self) -> bool:
        return bool(self.refs)

    @property
    def has_gaps(self) -> bool:
        return bool(self.unsupported_claims)

    @property
    def is_empty(self) -> bool:
        return not self.refs and not self.unsupported_claims


class MemoEvidence(BaseModel):
    """
    Six-section evidence bundle attached to one ValuationOutput.

    Each section tolerates absence gracefully — templates check ``has_evidence``
    and ``has_gaps`` before rendering.
    """

    biology: MemoSectionEvidence = Field(
        default_factory=lambda: MemoSectionEvidence(section_key="biology")
    )
    trial: MemoSectionEvidence = Field(
        default_factory=lambda: MemoSectionEvidence(section_key="trial")
    )
    competitive: MemoSectionEvidence = Field(
        default_factory=lambda: MemoSectionEvidence(section_key="competitive")
    )
    assumptions: MemoSectionEvidence = Field(
        default_factory=lambda: MemoSectionEvidence(section_key="assumptions")
    )
    comps: MemoSectionEvidence = Field(
        default_factory=lambda: MemoSectionEvidence(section_key="comps")
    )
    falsification: MemoSectionEvidence = Field(
        default_factory=lambda: MemoSectionEvidence(section_key="falsification")
    )

    @property
    def total_refs(self) -> int:
        return sum(
            len(s.refs)
            for s in [self.biology, self.trial, self.competitive,
                      self.assumptions, self.comps, self.falsification]
        )

    @property
    def total_gaps(self) -> int:
        return sum(
            len(s.unsupported_claims)
            for s in [self.biology, self.trial, self.competitive,
                      self.assumptions, self.comps, self.falsification]
        )

    @property
    def has_any_evidence(self) -> bool:
        return self.total_refs > 0

    def section(self, key: str) -> MemoSectionEvidence:
        """Retrieve a section by key string (safe; returns empty section on unknown key)."""
        return getattr(self, key, MemoSectionEvidence(section_key=key))
