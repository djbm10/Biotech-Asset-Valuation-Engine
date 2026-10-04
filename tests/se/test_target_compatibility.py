"""TARGET_COMPATIBILITY v1: a positively established other entity, never an absence.

Policy: ``docs/se_policies/target_compatibility_v1.md``.
"""

from __future__ import annotations

from datetime import date

from bve.se.evidence.target_compatibility import (
    compatibility_evidence,
    complex_entities,
    nongene_entities,
)
from bve.se.gates.evaluator import evaluate_target_expression
from bve.se.ontology.mechanisms import DrugTargetEdge, EdgeStatus, TargetRelationship
from bve.se.schemas.contracts import GateStatus, TargetExpression, TargetOperator

AS_OF = date(2026, 9, 24)


def _edge(target, relationship, status=EdgeStatus.USABLE, record="r1"):
    return DrugTargetEdge(
        canonical_drug_id="DRUG:X", canonical_target_id=target, relationship_type=relationship,
        source="open_targets", source_release="26.06", source_record_id=record,
        evidence_hash=f"h{target}{record}", status=status,
    )


COMPLEX = TargetRelationship.FAMILY_OR_COMPLEX_ASSOCIATION
DIRECT = TargetRelationship.DIRECT_TARGET


def _expression(*targets, operator=TargetOperator.ANY):
    return TargetExpression.model_validate(
        {"operator": operator, "targets": [{"canonical_id": t, "label": t} for t in targets]}
    )


def _fact(entities):
    return compatibility_evidence("asset:1", entities, basis="t", as_of_date=AS_OF).fact


class TestEntities:
    def test_a_complex_is_one_entity_not_member_claims(self) -> None:
        (entity,) = complex_entities([_edge("TARGET:CRBN", COMPLEX), _edge("TARGET:DDB1", COMPLEX)])
        assert entity["entity"] == "COMPLEX:open_targets:r1"
        assert entity["members"] == ["TARGET:CRBN", "TARGET:DDB1"]

    def test_a_usable_direct_edge_disables_the_rule(self) -> None:
        assert complex_entities([_edge("TARGET:CRBN", COMPLEX), _edge("TARGET:Y", DIRECT)]) is None

    def test_unusable_rows_are_not_evidence(self) -> None:
        assert complex_entities([_edge(None, DIRECT, EdgeStatus.TARGET_NOT_IN_SNAPSHOT)]) is None

    def test_no_edges_is_not_evidence(self) -> None:
        assert complex_entities([]) is None

    def test_nongene_class_is_kept_as_an_antigen(self) -> None:
        (entity,) = nongene_entities(["C201172"])
        assert entity == {"entity": "NONGENE:C201172", "source": "ncit", "source_release": "26.08e", "members": []}

    def test_a_mixed_class_product_is_not_eligible(self) -> None:
        assert nongene_entities(["C201172", "C176018"]) is None
        assert nongene_entities([]) is None

    def test_the_fact_value_never_holds_a_target_id_at_top_level(self) -> None:
        fact = _fact(complex_entities([_edge("TARGET:CRBN", COMPLEX)]))
        assert all(not str(entity["entity"]).startswith("TARGET:") for entity in fact.value)


class TestGate:
    def test_an_unrelated_complex_fails_the_query(self) -> None:
        fact = _fact(complex_entities([_edge("TARGET:CRBN", COMPLEX)]))
        decision = evaluate_target_expression(
            _expression("TARGET:CD19"), subject_id="a", target_fact=None, compatibility_facts=[fact]
        )
        assert decision.status is GateStatus.FAIL

    def test_a_queried_target_inside_the_complex_is_unknown(self) -> None:
        fact = _fact(complex_entities([_edge("TARGET:CD19", COMPLEX), _edge("TARGET:CD81", COMPLEX)]))
        decision = evaluate_target_expression(
            _expression("TARGET:CD19"), subject_id="a", target_fact=None, compatibility_facts=[fact]
        )
        assert decision.status is GateStatus.UNKNOWN

    def test_a_nongene_antigen_fails_a_gene_query(self) -> None:
        fact = _fact(nongene_entities(["C201491"]))
        decision = evaluate_target_expression(
            _expression("TARGET:CD19", "TARGET:TNFRSF17", operator=TargetOperator.ALL),
            subject_id="a", target_fact=None, compatibility_facts=[fact],
        )
        assert decision.status is GateStatus.FAIL

    def test_no_compatibility_evidence_stays_unknown(self) -> None:
        decision = evaluate_target_expression(
            _expression("TARGET:CD19"), subject_id="a", target_fact=None, compatibility_facts=[]
        )
        assert decision.status is GateStatus.UNKNOWN

    def test_two_compatibility_facts_stay_unknown(self) -> None:
        fact = _fact(complex_entities([_edge("TARGET:CRBN", COMPLEX)]))
        other = _fact(nongene_entities(["C201491"]))
        decision = evaluate_target_expression(
            _expression("TARGET:CD19"), subject_id="a", target_fact=None,
            compatibility_facts=[fact, other],
        )
        assert decision.status is GateStatus.UNKNOWN
