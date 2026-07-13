from __future__ import annotations

from datetime import date

from bve.se.gates.evaluator import evaluate_requirement, evaluate_target_expression
from bve.se.schemas.contracts import (
    BuyerRequirement,
    GateStatus,
    NormalizedFact,
    RequirementDomain,
    RequirementOperator,
    TargetExpression,
    TargetOperator,
    TargetTerm,
    TemporalFact,
)


def _requirement() -> BuyerRequirement:
    return BuyerRequirement(
        requirement_id="evidence.minimum_patients",
        domain=RequirementDomain.EVIDENCE_SUFFICIENCY,
        fact_type="evaluable_patients",
        operator=RequirementOperator.GTE,
        expected_value=10,
        pass_condition="At least ten evaluable patients are reported.",
        fail_condition="Fewer than ten evaluable patients are reported.",
        unknown_condition="Evaluable-patient evidence is insufficient.",
    )


def _fact(value: object = 12) -> NormalizedFact:
    return NormalizedFact(
        fact_id="fact:1",
        subject_id="asset:1",
        fact_type="evaluable_patients",
        value=value,
        supporting_claim_ids=["claim:1"],
        confidence=0.9,
    )


def test_missing_fact_is_unknown() -> None:
    decision = evaluate_requirement(
        _requirement(), subject_id="asset:1", facts=[], gate_id="evidence_floor"
    )
    assert decision.status == GateStatus.UNKNOWN
    assert decision.next_action


def test_requirement_pass_and_fail_are_evidence_backed() -> None:
    passed = evaluate_requirement(
        _requirement(), subject_id="asset:1", facts=[_fact(12)], gate_id="evidence_floor"
    )
    failed = evaluate_requirement(
        _requirement(), subject_id="asset:1", facts=[_fact(4)], gate_id="evidence_floor"
    )
    assert passed.status == GateStatus.PASS
    assert failed.status == GateStatus.FAIL
    assert passed.supporting_or_contradictory_claim_ids == ["claim:1"]


def test_stale_or_conflicting_fact_is_unknown() -> None:
    stale = TemporalFact(
        **_fact().model_dump(),
        effective_from=date(2025, 1, 1),
        evaluated_as_of=date(2026, 7, 10),
        is_stale=True,
    )
    conflict = _fact().model_copy(update={"contradicting_claim_ids": ["claim:2"]})
    assert evaluate_requirement(
        _requirement(), subject_id="asset:1", facts=[stale], gate_id="evidence_floor"
    ).status == GateStatus.UNKNOWN
    assert evaluate_requirement(
        _requirement(), subject_id="asset:1", facts=[conflict], gate_id="evidence_floor"
    ).status == GateStatus.UNKNOWN


def test_target_operators_are_not_presentation_modes() -> None:
    targets = [TargetTerm(canonical_id="CD19", label="CD19"), TargetTerm(canonical_id="BCMA", label="BCMA")]
    fact = NormalizedFact(
        fact_id="fact:targets",
        subject_id="asset:1",
        fact_type="construct_target_set",
        value=["CD19"],
        supporting_claim_ids=["claim:targets"],
        confidence=0.9,
    )
    any_decision = evaluate_target_expression(
        TargetExpression(operator=TargetOperator.ANY, targets=targets),
        subject_id="asset:1",
        target_fact=fact,
    )
    exact_decision = evaluate_target_expression(
        TargetExpression(operator=TargetOperator.EXACT_COMBINATION, targets=targets),
        subject_id="asset:1",
        target_fact=fact,
    )
    assert any_decision.status == GateStatus.PASS
    assert exact_decision.status == GateStatus.FAIL
