"""What a natural-language question was understood to mean (M9C).

:class:`SearchIntent` is the audited middle step between a typed question and a
:class:`~bve.se.schemas.contracts.BuyerProblemV2`. It exists so the shortlist can answer
"why did you interpret my query this way?" with spans rather than a post-hoc story: every
resolved element records the substring it came from and the rule that fired, and every
term that did *not* resolve is carried forward rather than dropped.
"""

from __future__ import annotations

import hashlib
from enum import Enum

from pydantic import Field

from bve.se.schemas.contracts import (
    PhaseConstraint,
    PhaseConstraintOperator,
    StrictModel,
    TargetOperator,
    TargetTerm,
)

INTENT_COMPILER_VERSION = "intent_v1"


class SpanKind(str, Enum):
    TARGET = "TARGET"
    MODALITY = "MODALITY"
    PHASE = "PHASE"
    STATUS = "STATUS"
    #: Matched a known vocabulary but resolved to more than one entity.
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
    #: An evidence requirement the contract can actually enforce ("human efficacy").
    EVIDENCE = "EVIDENCE"
    #: Recognized as scientifically meaningful, and *not* faithfully representable as a
    #: constraint. Escalated by name rather than quietly demoted to free text.
    UNRESOLVED_SCIENTIFIC = "UNRESOLVED_SCIENTIFIC"
    #: Left over after every vocabulary was tried; kept as free text, never as an assertion.
    RESIDUAL = "RESIDUAL"


class IntentSpan(StrictModel):
    """One substring of the query and what it was taken to mean."""

    text: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    kind: SpanKind
    resolved_to: str | None = None
    #: Named rule that fired, so an interpretation can be argued with.
    rule: str
    candidates: list[str] = Field(default_factory=list)
    #: ``ResolutionBasis.explain`` output for target spans.
    explanation: str | None = None


class SearchIntent(StrictModel):
    original_query: str
    compiler_version: str = INTENT_COMPILER_VERSION
    #: Snapshot the targets were resolved against. ``no_snapshot__…`` means no target
    #: could resolve, which is why intents built without a snapshot do not compile.
    ontology_version: str

    spans: list[IntentSpan] = Field(default_factory=list)

    targets: list[TargetTerm] = Field(default_factory=list)
    target_operator: TargetOperator = TargetOperator.ANY
    modalities: list[str] = Field(default_factory=list)
    phases: list[str] = Field(default_factory=list)
    #: How ``phases`` is meant to be read. "phase 2" is EXACT, not a floor.
    phase_operator: PhaseConstraintOperator = PhaseConstraintOperator.EXACT
    statuses: list[str] = Field(default_factory=list)

    #: Evidence requirements the question stated and the contract can enforce. Both map onto
    #: fields of :class:`~bve.se.schemas.contracts.EvidenceFloor` that the gate engine
    #: already evaluates; neither is inferred from anything vaguer than a controlled phrase.
    human_poc_required: bool = False
    #: Stage *floor*, never a phase selection: "clinical-stage" says the asset entered human
    #: development, and says nothing whatever about which phase it reached.
    minimum_stage: str | None = None

    #: Phrases recognized as scientifically meaningful that no constraint can carry
    #: faithfully. They block compilation by name rather than becoming silent free text.
    unresolved_scientific_terms: list[str] = Field(default_factory=list)

    #: Query text that matched no vocabulary. Usable as free-text condition terms, but
    #: never promoted to a resolved indication — an unrecognized phrase is a gap, not a fact.
    residual_terms: list[str] = Field(default_factory=list)
    #: Terms that matched several entities. Escalated, never silently disambiguated.
    ambiguous_terms: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def problem_id(self) -> str:
        """Deterministic id for the question, so the same query replays to the same run."""

        normalized = " ".join(self.original_query.casefold().split())
        return "nlq_" + hashlib.sha256(normalized.encode()).hexdigest()[:16]

    @property
    def phase_constraint(self) -> PhaseConstraint | None:
        """The phase requirement this question states, or ``None`` if it states none."""

        if not self.phases:
            return None
        return PhaseConstraint(operator=self.phase_operator, phases=list(self.phases))

    @property
    def is_compilable(self) -> bool:
        return bool(self.targets) and bool(self.modalities)

    def blockers(self, *, indication_supplied: bool = False) -> list[str]:
        """Why this intent cannot become a buyer problem, in the user's own terms.

        ``indication_supplied`` is the caller answering the clarification: once a
        therapeutic area or indication is stated explicitly, an unenforceable disease class
        is no longer an unanswered part of the question.
        """

        reasons: list[str] = []
        if not self.targets:
            if self.ambiguous_terms:
                reasons.append(
                    "no target resolved unambiguously; ambiguous: "
                    + ", ".join(self.ambiguous_terms)
                )
            else:
                reasons.append("no biological target recognized in the query")
        if not self.modalities:
            reasons.append("no modality recognized in the query")
        if self.unresolved_scientific_terms and not indication_supplied:
            reasons.append(
                "NEEDS_CLARIFICATION: "
                + ", ".join(f"{term!r}" for term in self.unresolved_scientific_terms)
                + " is a scientific constraint this engine cannot enforce faithfully — the"
                " indication gate tests an asset's own indication, never a disease class."
                " State it with --therapeutic-area or --indication, or drop it; it will not"
                " be applied silently."
            )
        return reasons

    def explain(self) -> list[str]:
        """One line per span: what was read, and why it was read that way."""

        return [
            f"{span.text!r} -> {span.kind.value}"
            + (f" {span.resolved_to}" if span.resolved_to else "")
            + f" [{span.rule}]"
            + (f" ({', '.join(span.candidates)})" if span.candidates else "")
            for span in self.spans
        ]
