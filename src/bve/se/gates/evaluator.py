"""Deterministic PASS/FAIL/UNKNOWN evaluation over normalized evidence facts."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from bve.se.schemas.contracts import (
    BuyerRequirement,
    GateDecision,
    GateStatus,
    NormalizedFact,
    RequirementOperator,
    TargetExpression,
    TargetOperator,
    TemporalFact,
)


def _claim_ids(facts: Iterable[NormalizedFact]) -> list[str]:
    return list(
        dict.fromkeys(
            claim_id
            for fact in facts
            for claim_id in [*fact.supporting_claim_ids, *fact.contradicting_claim_ids]
        )
    )


def _compare(actual: Any, expected: Any, operator: RequirementOperator) -> bool:
    if operator == RequirementOperator.EQ:
        return actual == expected
    if operator == RequirementOperator.NE:
        return actual != expected
    if operator == RequirementOperator.IN:
        return actual in expected
    if operator == RequirementOperator.NOT_IN:
        return actual not in expected
    if operator == RequirementOperator.GTE:
        return actual >= expected
    if operator == RequirementOperator.LTE:
        return actual <= expected
    if operator == RequirementOperator.CONTAINS_ALL:
        return set(expected).issubset(set(actual))
    if operator == RequirementOperator.CONTAINS_ANY:
        return bool(set(expected).intersection(actual))
    if operator == RequirementOperator.EXISTS:
        return actual is not None
    raise ValueError(f"unsupported requirement operator: {operator}")


def _undecidable(
    requirement: BuyerRequirement,
    *,
    subject_id: str,
    matching: list[NormalizedFact],
    gate_id: str,
) -> GateDecision | None:
    """UNKNOWN when the facts are missing, conflicting or stale; None when they can decide."""

    if not matching:
        return GateDecision(
            gate_id=gate_id,
            requirement_id=requirement.requirement_id,
            subject_id=subject_id,
            status=GateStatus.UNKNOWN,
            rationale=requirement.unknown_condition,
            next_action=f"Research fact type {requirement.fact_type!r}.",
        )

    if any(fact.contradicting_claim_ids for fact in matching):
        return GateDecision(
            gate_id=gate_id,
            requirement_id=requirement.requirement_id,
            subject_id=subject_id,
            status=GateStatus.UNKNOWN,
            observed_fact_ids=[fact.fact_id for fact in matching],
            supporting_or_contradictory_claim_ids=_claim_ids(matching),
            rationale="Material evidence conflicts prevent a deterministic gate decision.",
            next_action="Reconcile the conflicting claims.",
        )

    if any(isinstance(fact, TemporalFact) and fact.is_stale for fact in matching):
        return GateDecision(
            gate_id=gate_id,
            requirement_id=requirement.requirement_id,
            subject_id=subject_id,
            status=GateStatus.UNKNOWN,
            observed_fact_ids=[fact.fact_id for fact in matching],
            supporting_or_contradictory_claim_ids=_claim_ids(matching),
            rationale="The decisive evidence is stale under the requirement freshness policy.",
            next_action="Refresh the stale evidence.",
        )

    return None


def evaluate_requirement(
    requirement: BuyerRequirement,
    *,
    subject_id: str,
    facts: Iterable[NormalizedFact],
    gate_id: str,
) -> GateDecision:
    """Evaluate one requirement without treating missing/conflicting/stale data as truth."""

    matching = [fact for fact in facts if fact.fact_type == requirement.fact_type]
    undecidable = _undecidable(requirement, subject_id=subject_id, matching=matching, gate_id=gate_id)
    if undecidable is not None:
        return undecidable

    results = [_compare(fact.value, requirement.expected_value, requirement.operator) for fact in matching]
    if all(results):
        status = GateStatus.PASS
        rationale = requirement.pass_condition
    elif not any(results):
        status = GateStatus.FAIL
        rationale = requirement.fail_condition
    else:
        return GateDecision(
            gate_id=gate_id,
            requirement_id=requirement.requirement_id,
            subject_id=subject_id,
            status=GateStatus.UNKNOWN,
            observed_fact_ids=[fact.fact_id for fact in matching],
            supporting_or_contradictory_claim_ids=_claim_ids(matching),
            rationale="Normalized facts disagree on the requirement outcome.",
            next_action="Resolve the inconsistent normalized facts.",
        )

    return GateDecision(
        gate_id=gate_id,
        requirement_id=requirement.requirement_id,
        subject_id=subject_id,
        status=status,
        observed_fact_ids=[fact.fact_id for fact in matching],
        supporting_or_contradictory_claim_ids=_claim_ids(matching),
        rationale=rationale,
    )


def evaluate_therapeutic_area(
    requirement: BuyerRequirement,
    *,
    subject_id: str,
    facts: Iterable[NormalizedFact],
    gate_id: str,
) -> GateDecision:
    """Decide a therapeutic-area request over the union of every area the evidence supports.

    Not the per-fact ``IN`` of :func:`evaluate_requirement`. An asset with one oncology trial
    and one lupus trial has no disagreeing facts: it supports both areas, and either one
    answers the request. Both sides are compared in canonical form, because ``ONCOLOGY``
    against ``oncology`` compared as strings excluded every oncology asset from an oncology
    question. A disjoint result is FAIL only when every requested area is one the evidence
    layer classifies; an area it cannot see is absent from the evidence by construction.
    """

    from bve.se.ontology.therapeutic_areas import CLASSIFIED_AREAS, canonical_therapeutic_area

    matching = [fact for fact in facts if fact.fact_type == requirement.fact_type]
    undecidable = _undecidable(requirement, subject_id=subject_id, matching=matching, gate_id=gate_id)
    if undecidable is not None:
        return undecidable

    requested = {canonical_therapeutic_area(area) for area in requirement.expected_value}
    observed = {
        canonical_therapeutic_area(area)
        for fact in matching
        for area in (fact.value if isinstance(fact.value, list) else [fact.value])
    }
    decided = {
        "gate_id": gate_id,
        "requirement_id": requirement.requirement_id,
        "subject_id": subject_id,
        "observed_fact_ids": [fact.fact_id for fact in matching],
        "supporting_or_contradictory_claim_ids": _claim_ids(matching),
    }
    if observed & requested:
        return GateDecision(**decided, status=GateStatus.PASS, rationale=requirement.pass_condition)
    unseeable = sorted(requested - CLASSIFIED_AREAS)
    if unseeable:
        return GateDecision(
            **decided,
            status=GateStatus.UNKNOWN,
            rationale=(
                f"Requested area(s) {unseeable} are not classified by the evidence layer, so "
                f"observed {sorted(observed)} cannot rule them out."
            ),
            next_action="Review the asset's indications against the requested area.",
        )
    return GateDecision(**decided, status=GateStatus.FAIL, rationale=requirement.fail_condition)


def evaluate_indication(
    requirement: BuyerRequirement,
    *,
    subject_id: str,
    facts: Iterable[NormalizedFact],
    gate_id: str,
) -> GateDecision:
    """Decide an indication request that names a concept, over the union of the evidence.

    A condition satisfies a concept when it names the concept or a subtype of it
    ("Relapsed/Refractory DLBCL" for B-cell lymphoma). An asset developed in several
    indications addresses the request if any of them does. A condition naming only an
    ancestor ("Lymphoma") cannot confirm or rule out the subtype, so it is UNKNOWN, never
    PASS. Literal entries in the same request keep the exact comparison.
    """

    from bve.se.ontology.indications import ConditionMatch, classify_condition, is_indication_concept

    matching = [fact for fact in facts if fact.fact_type == requirement.fact_type]
    undecidable = _undecidable(requirement, subject_id=subject_id, matching=matching, gate_id=gate_id)
    if undecidable is not None:
        return undecidable

    concepts = [value for value in requirement.expected_value if is_indication_concept(value)]
    literals = [value for value in requirement.expected_value if not is_indication_concept(value)]
    outcomes: set[ConditionMatch] = set()
    for fact in matching:
        for condition in fact.value if isinstance(fact.value, list) else [fact.value]:
            if condition in literals:
                outcomes.add(ConditionMatch.MATCH)
            elif isinstance(condition, str):
                outcomes.update(classify_condition(condition, concept) for concept in concepts)

    decided = {
        "gate_id": gate_id,
        "requirement_id": requirement.requirement_id,
        "subject_id": subject_id,
        "observed_fact_ids": [fact.fact_id for fact in matching],
        "supporting_or_contradictory_claim_ids": _claim_ids(matching),
    }
    if ConditionMatch.MATCH in outcomes:
        return GateDecision(**decided, status=GateStatus.PASS, rationale=requirement.pass_condition)
    if ConditionMatch.UNDETERMINED in outcomes:
        return GateDecision(
            **decided,
            status=GateStatus.UNKNOWN,
            rationale=(
                f"Observed indications name only a broader disease than {concepts}, which "
                "neither confirms nor rules out the requested indication."
            ),
            next_action="Confirm the specific indication the asset is developed in.",
        )
    return GateDecision(**decided, status=GateStatus.FAIL, rationale=requirement.fail_condition)


def _target_key(value: object) -> str:
    """One comparison space for target identifiers, whichever space they arrived in.

    The intent layer writes a target expression in approved symbols (``CD19``), while
    mechanism evidence is keyed by the resolver's canonical id (``TARGET:CD19``). Both
    name the same gene, and comparing them as strings makes every multi-target question
    unsatisfiable while looking exactly like an absence of evidence. Resolving is not a
    convenience here: it is what makes the two sides the same question.

    An identifier the ontology cannot resolve keeps its literal form. That preserves the
    behaviour of runs with no snapshot loaded, and an unresolvable id matching only itself
    is the conservative reading.
    """

    from bve.se.ontology.targets import normalize_target

    text = str(value).strip()
    if not text:
        return ""
    return (normalize_target(text) or text).upper()


def evaluate_target_expression(
    expression: TargetExpression,
    *,
    subject_id: str,
    target_fact: NormalizedFact | None,
    requirement_id: str = "target.expression",
) -> GateDecision:
    """Evaluate canonical construct targets with explicit ANY/ALL/exact semantics."""

    if target_fact is None:
        return GateDecision(
            gate_id="target_logic",
            requirement_id=requirement_id,
            subject_id=subject_id,
            status=GateStatus.UNKNOWN,
            rationale="No canonical construct-level target fact is available.",
            next_action="Resolve the asset's construct-level target set.",
        )
    if target_fact.contradicting_claim_ids:
        return GateDecision(
            gate_id="target_logic",
            requirement_id=requirement_id,
            subject_id=subject_id,
            status=GateStatus.UNKNOWN,
            observed_fact_ids=[target_fact.fact_id],
            supporting_or_contradictory_claim_ids=_claim_ids([target_fact]),
            rationale="Target evidence is conflicting.",
            next_action="Reconcile the target claims.",
        )

    observed = {_target_key(value) for value in target_fact.value}
    required = {_target_key(target.canonical_id) for target in expression.targets}
    if expression.operator == TargetOperator.ANY:
        passed = bool(observed & required)
    elif expression.operator == TargetOperator.ALL:
        passed = required.issubset(observed)
    else:
        passed = observed == required

    return GateDecision(
        gate_id="target_logic",
        requirement_id=requirement_id,
        subject_id=subject_id,
        status=GateStatus.PASS if passed else GateStatus.FAIL,
        observed_fact_ids=[target_fact.fact_id],
        supporting_or_contradictory_claim_ids=_claim_ids([target_fact]),
        rationale=(
            "Canonical construct targets satisfy the configured expression."
            if passed
            else "Canonical construct targets do not satisfy the configured expression."
        ),
    )
