"""Dual-source buyer-problem intake (spec Part 2.1 / 2.2).

A ``BuyerProblem`` (the Stage 0 sandbox) can arrive two ways:

1. **Analyst-defined** — written directly by the analyst; always authoritative.
2. **Inferred** — drafted from public data (SEC filings, press/news, CT.gov)
   by an LLM-over-ingestion extractor, then reviewed and corrected by an analyst.

To keep the core ``BuyerProblem`` model clean (and to avoid editing it while it
is owned elsewhere), provenance lives in a sidecar wrapper, ``BuyerProblemDraft``,
rather than as fields on ``BuyerProblem`` itself. The downstream gates and scoring
consume ``draft.buyer_problem`` unchanged.

The LLM call is abstracted behind the ``BuyerProblemExtractor`` protocol so this
module has no network/LLM dependency and is fully unit-testable with a fake.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Protocol, Sequence

from pydantic import BaseModel, Field

from bve.intelligence.science_thesis import BuyerProblem


class BuyerProblemProvenance(str, Enum):
    """Where a buyer problem came from. Analyst input always outranks inference."""

    ANALYST = "analyst"
    INFERRED = "inferred"
    ANALYST_CORRECTED = "analyst_corrected"


class EvidenceRef(BaseModel):
    """A citation backing an inferred field — url / filing / press, with as-of date."""

    source_type: str = ""  # e.g. "sec_edgar", "press", "clinicaltrials_gov"
    citation: str = ""  # url, accession number, or document id
    as_of_date: str = ""  # ISO date the source was published / retrieved
    snippet: str = ""  # short supporting quote


class BuyerProblemDraft(BaseModel):
    """A buyer problem plus its provenance metadata.

    ``inference_confidence`` is only meaningful for inferred drafts (analyst input
    is 1.0 by definition). ``corrected_fields`` records which fields an analyst
    overrode relative to the inferred draft, so the inferred-vs-corrected diff can
    later be measured as a free, growing accuracy dataset for the extractor.
    """

    buyer_problem: BuyerProblem
    provenance: BuyerProblemProvenance = BuyerProblemProvenance.INFERRED
    inference_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_citations: list[EvidenceRef] = Field(default_factory=list)
    inferred_by_model: str | None = None
    corrected_fields: list[str] = Field(default_factory=list)
    reviewed: bool = False

    @classmethod
    def from_analyst(cls, buyer_problem: BuyerProblem) -> "BuyerProblemDraft":
        """Wrap an analyst-authored buyer problem (authoritative, fully trusted)."""
        return cls(
            buyer_problem=buyer_problem,
            provenance=BuyerProblemProvenance.ANALYST,
            inference_confidence=1.0,
            reviewed=True,
        )

    @property
    def is_trusted(self) -> bool:
        """Analyst-authored or analyst-reviewed drafts are safe to act on."""
        return self.provenance in (
            BuyerProblemProvenance.ANALYST,
            BuyerProblemProvenance.ANALYST_CORRECTED,
        )


class InferenceResult(BaseModel):
    """Raw output of a ``BuyerProblemExtractor`` before it is wrapped in a draft."""

    buyer_problem: BuyerProblem
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    citations: list[EvidenceRef] = Field(default_factory=list)
    model_name: str = ""


class BuyerProblemExtractor(Protocol):
    """The LLM-over-ingestion seam.

    A real implementation reads already-ingested sources for the buyer (filings,
    press, CT.gov) and fills the ``BuyerProblem`` schema. Tests inject a fake.
    """

    def extract(self, buyer_id: str, sources: Sequence[EvidenceRef]) -> InferenceResult:
        ...


# A correction record is logged for each analyst override; the sink persists it
# (e.g. to KnowledgeStore) so accuracy can be measured later.
CorrectionRecord = dict[str, Any]
CorrectionSink = Callable[[list[CorrectionRecord]], None]


class BuyerProblemInferencer:
    """Drafts a ``BuyerProblem`` from public data; never transacts on its own guess."""

    def __init__(self, extractor: BuyerProblemExtractor) -> None:
        self._extractor = extractor

    def infer(self, buyer_id: str, sources: Sequence[EvidenceRef]) -> BuyerProblemDraft:
        """Produce an unreviewed inferred draft for analyst correction."""
        result = self._extractor.extract(buyer_id, sources)
        return BuyerProblemDraft(
            buyer_problem=result.buyer_problem,
            provenance=BuyerProblemProvenance.INFERRED,
            inference_confidence=result.confidence,
            evidence_citations=list(result.citations),
            inferred_by_model=result.model_name or None,
            reviewed=False,
        )


def apply_analyst_correction(
    draft: BuyerProblemDraft,
    corrections: dict[str, Any],
    *,
    sink: CorrectionSink | None = None,
) -> BuyerProblemDraft:
    """Apply analyst overrides to an inferred draft.

    Returns a new draft (provenance ``analyst_corrected``, ``reviewed=True``) with
    only the changed fields applied. Each field that actually changed is logged as
    a ``{field, inferred_value, corrected_value}`` record and, if a ``sink`` is
    supplied, persisted (e.g. to KnowledgeStore) for later accuracy measurement.
    Immutable: the input draft and buyer_problem are never mutated.
    """
    current = draft.buyer_problem
    changed_fields: list[str] = []
    records: list[CorrectionRecord] = []
    field_updates: dict[str, Any] = {}

    for field, corrected_value in corrections.items():
        if field not in type(current).model_fields:
            raise ValueError(f"Unknown BuyerProblem field: {field!r}")
        inferred_value = getattr(current, field)
        if inferred_value == corrected_value:
            continue
        changed_fields.append(field)
        field_updates[field] = corrected_value
        records.append(
            {
                "field": field,
                "inferred_value": inferred_value,
                "corrected_value": corrected_value,
            }
        )

    corrected_problem = current.model_copy(update=field_updates) if field_updates else current
    if sink is not None and records:
        sink(records)

    return draft.model_copy(
        update={
            "buyer_problem": corrected_problem,
            "provenance": BuyerProblemProvenance.ANALYST_CORRECTED,
            "corrected_fields": changed_fields,
            "reviewed": True,
        }
    )
