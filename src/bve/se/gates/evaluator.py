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


def evaluate_requirement(
    requirement: BuyerRequirement,
    *,
    subject_id: str,
    facts: Iterable[NormalizedFact],
    gate_id: str,
) -> GateDecision:
    """Evaluate one requirement without treating missing/conflicting/stale data as truth."""

    matching = [fact for fact in facts if fact.fact_type == requirement.fact_type]
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

    observed = {str(value).upper() for value in target_fact.value}
    required = {target.canonical_id.upper() for target in expression.targets}
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
