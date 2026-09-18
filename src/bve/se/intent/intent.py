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
    #: A word that constrains how the *other* resolved elements combine -- "dual" says one
    #: molecule must hit every named target. It resolves to no entity of its own.
    TARGET_LOGIC = "TARGET_LOGIC"
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
    #: The question used a word ("dual") that *states* the conjunction rather than leaving
    #: it to be inferred from the connector. Kept separate from ``target_operator`` so the
    #: stated requirement can be checked against what actually resolved.
    conjunction_stated: bool = False
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
        return not self.blockers(indication_supplied=True)

    @property
    def conjunction_unsatisfiable(self) -> bool:
        """The question *stated* a conjunction that the resolved targets cannot express.

        "dual CD19" names a two-target molecule and one target; "dual CD19 or BCMA" states
        the conjunction and its own negation. Either way the stated requirement cannot be
        compiled, and compiling the rest would answer a wider question in silence.
        """

        if not self.conjunction_stated:
            return False
        return len(self.targets) < 2 or self.target_operator is not TargetOperator.ALL

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
        if self.conjunction_unsatisfiable:
            reasons.append(
                "the question states 'dual' -- one molecule hitting every named target --"
                " but that cannot be compiled from what resolved: "
                + (
                    f"only {len(self.targets)} target resolved"
                    if len(self.targets) < 2
                    else "the connector between the targets reads as 'either'"
                )
                + ". Name both targets conjunctively, or drop 'dual'; it will not be"
                " dropped silently, because a run without it can return single-target"
                " assets."
            )
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

    def warnings_for(self, *, indication_supplied: bool = False) -> list[str]:
        """Parse-time warnings, plus the ones that depend on what the caller supplied.

        An unenforceable disease class is only unapplied for as long as the caller has not
        answered it. Repeating "this run will NOT apply it unless you state
        --therapeutic-area" *after* they stated one describes a run that did not happen.
        """

        lines = list(self.warnings)
        if not self.unresolved_scientific_terms:
            return lines
        named = ", ".join(self.unresolved_scientific_terms)
        if indication_supplied:
            lines.append(
                "recognized but unenforceable scientific phrases, answered by the"
                f" therapeutic area / indication you supplied: {named}"
            )
        else:
            lines.append(
                "recognized but unenforceable scientific phrases, which this run will NOT"
                " apply unless you state them with --therapeutic-area or --indication: "
                + named
            )
        return lines

    def explain_constraints(self) -> list[str]:
        """What this question will actually gate on, including the gates it does *not* set.

        An absent constraint is invisible in a list of present ones, and "no modality gate"
        is the difference between a deliberately wide search and a narrowed one.
        """

        lines = [
            "target constraint: "
            + (
                f"{self.target_operator.value} of "
                + ", ".join(target.canonical_id for target in self.targets)
                if self.targets
                else "none"
            ),
            "modality constraint: "
            + (", ".join(self.modalities) if self.modalities else "none"),
            "phase constraint: "
            + (
                f"{self.phase_operator.value} {', '.join(self.phases)}"
                if self.phases
                else "none"
            ),
            "evidence floor: "
            + (
                ", ".join(
                    filter(
                        None,
                        [
                            f"minimum_stage={self.minimum_stage}" if self.minimum_stage else "",
                            "human_poc_required" if self.human_poc_required else "",
                        ],
                    )
                )
                or "none"
            ),
        ]
        return lines

    def explain(self) -> list[str]:
        """One line per span: what was read, and why it was read that way."""

        return [
            f"{span.text!r} -> {span.kind.value}"
            + (f" {span.resolved_to}" if span.resolved_to else "")
            + f" [{span.rule}]"
            + (f" ({', '.join(span.candidates)})" if span.candidates else "")
            for span in self.spans
        ]
