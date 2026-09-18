"""Deterministic :class:`SearchIntent` → :class:`BuyerProblemV2` compilation (M9C).

Compilation is a pure function of the intent plus the caller's buyer identity: the same
question compiles to the same problem, byte for byte, which is what makes an
NL-originated shortlist reproducible.

A question that did not resolve does not compile. Filling in a plausible target or
modality to make the pipeline run would reintroduce exactly the guessing M9A removed, so
:func:`compile_intent` raises with the blockers named instead.
"""

from __future__ import annotations

from datetime import date

from bve.se.intent.intent import SearchIntent
from bve.se.ontology.targets import target_aliases
from bve.se.schemas.contracts import (
    BuyerIdentity,
    BuyerProblemV2,
    EvidenceFloor,
    StrategicGap,
    TargetExpression,
    TargetTerm,
)
from bve.se.universe.provider import TrialQuery

#: Placeholder used when the question names no therapeutic area. ``StrategicGap`` requires
#: one; inventing a specific area from the target would be an unearned inference, so the
#: gap is stated explicitly and carried into the intent's warnings instead.
UNSPECIFIED_THERAPEUTIC_AREA = "UNSPECIFIED"


class IntentNotCompilable(ValueError):
    """Raised when an intent is too underdetermined to become a buyer problem."""

    def __init__(self, intent: SearchIntent, *, indication_supplied: bool = False) -> None:
        self.intent = intent
        self.blockers = intent.blockers(indication_supplied=indication_supplied)
        super().__init__(
            f"cannot compile {intent.original_query!r}: " + "; ".join(self.blockers)
        )


def compile_intent(
    intent: SearchIntent,
    *,
    buyer: BuyerIdentity,
    therapeutic_areas: list[str] | None = None,
    indications: list[str] | None = None,
) -> BuyerProblemV2:
    """Compile an intent into a buyer problem.

    ``therapeutic_areas`` and ``indications`` are caller-supplied because neither can be
    derived from the question without a disease ontology; when omitted, the therapeutic
    area is recorded as ``UNSPECIFIED`` and the intent's residual terms become the
    indications, flagged as unverified free text rather than resolved concepts.

    They are also the answer to a ``NEEDS_CLARIFICATION`` blocker. A question naming a
    disease *class* does not compile on its own, because the class cannot be enforced; once
    the caller states the area or indication they mean, the unanswered part of the question
    has been answered and the run proceeds.
    """

    indication_supplied = bool(therapeutic_areas) or bool(indications)
    # A phrase the engine recognized as scientific and cannot enforce stops the run rather
    # than riding along unapplied: the user would otherwise read a shortlist believing their
    # whole question was honoured. Stating the area or indication explicitly answers it.
    if not intent.is_compilable or (
        intent.unresolved_scientific_terms and not indication_supplied
    ):
        raise IntentNotCompilable(intent, indication_supplied=indication_supplied)

    targets = [
        TargetTerm(
            canonical_id=target.canonical_id,
            label=target.label,
            aliases=list(target_aliases(target.canonical_id)),
        )
        for target in intent.targets
    ]

    gap = StrategicGap(
        therapeutic_areas=list(therapeutic_areas or [UNSPECIFIED_THERAPEUTIC_AREA]),
        indications=list(indications if indications is not None else intent.residual_terms),
        target_expression=TargetExpression(operator=intent.target_operator, targets=targets),
        modalities=list(intent.modalities),
        # Phase intent is a gating constraint, not a display filter: it is compiled into the
        # buyer problem so the gate engine decides it against the asset's own stage evidence.
        phase_constraint=intent.phase_constraint,
        # Evidence phrases become the floor the gate already enforces. A stage floor is not
        # a phase constraint and never sets one: "clinical-stage" admits every phase.
        evidence_floor=EvidenceFloor(
            minimum_stage=intent.minimum_stage,
            human_poc_required=intent.human_poc_required,
        ),
    )

    return BuyerProblemV2(
        problem_id=intent.problem_id,
        # Both halves matter for replay: the compiler and the snapshot it resolved against.
        version=f"{intent.compiler_version}__{intent.ontology_version}",
        buyer=buyer,
        strategic_gap=gap,
    )


def build_buyer_identity(name: str, *, as_of_date: date, buyer_id: str | None = None) -> BuyerIdentity:
    """Buyer identity for an ad-hoc natural-language search.

    A typed question has no standing buyer profile, so the identity is synthesized rather
    than looked up — recorded honestly as ``nl_query`` so a shortlist is never mistaken
    for one produced against a real buyer's capability profile.
    """

    return BuyerIdentity(
        buyer_id=buyer_id or "nl_query",
        name=name,
        as_of_date=as_of_date,
    )


def intent_to_trial_query(intent: SearchIntent, *, as_of_date: date | None = None, max_records: int = 1000) -> TrialQuery:
    """Compile an intent straight into a backend-neutral trial query.

    Terms are the resolved targets plus every alias the ontology snapshot knows for them,
    so recall does not depend on which spelling the question happened to use.
    """

    terms: list[str] = []
    for target in intent.targets:
        for term in (target.canonical_id, *target_aliases(target.canonical_id)):
            if term and term not in terms:
                terms.append(term)

    # Conditions widen retrieval; they decide nothing. An unenforceable disease class is
    # still a useful thing to search for, which is why it appears here and not in the gate.
    return TrialQuery(
        terms=terms,
        conditions=[*intent.unresolved_scientific_terms, *intent.residual_terms],
        statuses=list(intent.statuses),
        as_of_date=as_of_date,
        max_records=max_records,
    )
