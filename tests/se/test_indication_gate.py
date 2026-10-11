"""Indication gate: one disease phrase is one concept, matched by subtype (parser defect #3).

Frozen by ``docs/se_policies/indication_gate_semantics.md``. The live defect: "relapsed or
refractory B-cell lymphoma" compiled to four exact-match literals, so every reference CD19
CAR-T failed ``strategy.indication`` on "Relapsed/Refractory Diffuse Large B-cell Lymphoma".
"""

from __future__ import annotations

from datetime import date

import pytest

from bve.se.gates.engine import GateEngine
from bve.se.intent.compiler import (
    build_buyer_identity,
    compile_intent,
    intent_to_trial_query,
    residual_indications,
)
from bve.se.intent.parser import parse_query
from bve.se.ontology.indications import (
    B_CELL_LYMPHOMA,
    ConditionMatch,
    classify_condition,
    resolve_indication_phrase,
)
from bve.se.schemas.contracts import BuyerProblemV2, GateStatus, NormalizedFact

TAC01 = "Find clinical-stage CD19 cell therapies for relapsed or refractory B-cell lymphoma."
MINT5 = "dual CD19 BCMA CAR-T for autoimmune disease"


class TestPhraseResolution:
    @pytest.mark.parametrize(
        "phrase",
        [
            "relapsed or refractory B-cell lymphoma",
            "relapsed/refractory B-cell lymphoma",
            "r/r B-NHL",
            "B-cell lymphoma",
            "recurrent B cell non-Hodgkin lymphoma",
        ],
    )
    def test_disease_phrase_is_one_concept(self, phrase: str) -> None:
        assert resolve_indication_phrase(phrase) == B_CELL_LYMPHOMA

    @pytest.mark.parametrize(
        "phrase", ["lymphoma", "refractory lymphoma", "lupus nephritis", "B-cell", "relapsed"]
    )
    def test_anything_else_does_not_resolve(self, phrase: str) -> None:
        assert resolve_indication_phrase(phrase) is None


class TestCompiler:
    def test_tac01_compiles_to_one_concept(self) -> None:
        intent = parse_query(TAC01)
        assert residual_indications(intent) == [B_CELL_LYMPHOMA]
        problem = compile_intent(
            intent,
            buyer=build_buyer_identity("x", as_of_date=date(2026, 9, 24)),
            therapeutic_areas=["ONCOLOGY"],
        )
        assert problem.strategic_gap.indications == [B_CELL_LYMPHOMA]

    def test_residual_terms_and_retrieval_are_unchanged(self) -> None:
        # residual_terms also drive trial retrieval; the sealed replay depends on them.
        intent = parse_query(TAC01)
        assert intent.residual_terms == ["relapsed", "refractory", "B-cell", "lymphoma"]
        query = intent_to_trial_query(intent, as_of_date=date(2026, 9, 24))
        assert query.conditions == ["relapsed", "refractory", "B-cell", "lymphoma"]

    def test_unresolved_phrase_keeps_todays_literals(self) -> None:
        intent = parse_query("CD19 CAR-T for lupus nephritis")
        assert residual_indications(intent) == intent.residual_terms

    def test_words_separated_by_a_stopword_are_not_one_phrase(self) -> None:
        # "for" is not phrase glue, so "B-cell ... lymphoma" never spans it.
        intent = parse_query("CD19 B-cell CAR-T for lymphoma")
        assert B_CELL_LYMPHOMA not in residual_indications(intent)

    def test_query_without_residue_compiles_no_indication(self) -> None:
        intent = parse_query(MINT5)
        problem = compile_intent(
            intent,
            buyer=build_buyer_identity("x", as_of_date=date(2026, 9, 24)),
            therapeutic_areas=["AUTOIMMUNE"],
        )
        assert problem.strategic_gap.indications == []

    def test_caller_supplied_indication_stays_literal(self) -> None:
        problem = compile_intent(
            parse_query(TAC01),
            buyer=build_buyer_identity("x", as_of_date=date(2026, 9, 24)),
            indications=["B-cell lymphoma"],
        )
        assert problem.strategic_gap.indications == ["B-cell lymphoma"]


class TestClassification:
    @pytest.mark.parametrize(
        "condition",
        [
            "Relapsed/Refractory Diffuse Large B-cell Lymphoma",
            "Refractory Diffuse Large B Cell Lymphoma (DLBCL)",
            "High-risk R/R LBCL",
            "B-cell Non-Hodgkin Lymphoma",
            "Lymphoma, B-Cell",
            "Mantle Cell Lymphoma",
            "Follicular Lymphoma",
            "Primary Mediastinal Large B-cell Lymphoma",
            "B-NHL",
        ],
    )
    def test_subtypes_match(self, condition: str) -> None:
        assert classify_condition(condition, B_CELL_LYMPHOMA) is ConditionMatch.MATCH

    @pytest.mark.parametrize(
        "condition",
        ["Lymphoma", "Non-Hodgkin Lymphoma", "NHL", "Hematologic Malignancies", "Haematological cancer"],
    )
    def test_ancestors_are_undetermined(self, condition: str) -> None:
        assert classify_condition(condition, B_CELL_LYMPHOMA) is ConditionMatch.UNDETERMINED

    @pytest.mark.parametrize(
        "condition",
        [
            "Hodgkin Lymphoma",
            "Peripheral T-cell Lymphoma",
            "Anaplastic Large Cell Lymphoma",
            "Mycosis Fungoides",
            "Acute Lymphoblastic Leukemia",
            "Multiple Myeloma",
            "Systemic Lupus Erythematosus",
            "Tumor",
        ],
    )
    def test_everything_else_does_not_match(self, condition: str) -> None:
        assert classify_condition(condition, B_CELL_LYMPHOMA) is ConditionMatch.NO


def _problem(indications: list[str]) -> BuyerProblemV2:
    return BuyerProblemV2.model_validate(
        {
            "problem_id": "p",
            "version": "1",
            "buyer": {"buyer_id": "b", "name": "Buyer", "as_of_date": "2026-09-26"},
            "strategic_gap": {
                "therapeutic_areas": ["ONCOLOGY"],
                "indications": indications,
                "target_expression": {
                    "operator": "ANY",
                    "targets": [{"canonical_id": "CD19", "label": "CD19"}],
                },
                "acceptable_deal_routes": ["LICENSE"],
            },
        }
    )


def _indication(fact_id: str, value: str, *, contradicted: bool = False) -> NormalizedFact:
    return NormalizedFact(
        fact_id=fact_id,
        subject_id="asset:1",
        fact_type="indication",
        value=value,
        supporting_claim_ids=[f"claim:{fact_id}"],
        contradicting_claim_ids=[f"claim:x{fact_id}"] if contradicted else [],
        confidence=0.9,
    )


def _decisions(indications: list[str], facts: list[NormalizedFact]):
    evaluation = GateEngine().evaluate(_problem(indications), subject_id="asset:1", facts=facts)
    return {d.requirement_id: d for d in evaluation.decisions}


def _status(indications: list[str], facts: list[NormalizedFact]) -> GateStatus:
    return _decisions(indications, facts)["strategy.indication"].status


class TestGate:
    def test_axi_cel_wording_passes(self) -> None:
        # The live defect, with axi-cel's own registry conditions.
        facts = [
            _indication("a", "Relapsed/Refractory Diffuse Large B-cell Lymphoma"),
            _indication("b", "Lymphoma"),
        ]
        assert _status([B_CELL_LYMPHOMA], facts) == GateStatus.PASS

    def test_any_matching_indication_passes(self) -> None:
        facts = [_indication("a", "Acute Lymphoblastic Leukemia"), _indication("b", "DLBCL")]
        assert _status([B_CELL_LYMPHOMA], facts) == GateStatus.PASS

    def test_only_an_ancestor_is_unknown(self) -> None:
        assert _status([B_CELL_LYMPHOMA], [_indication("a", "Lymphoma")]) == GateStatus.UNKNOWN

    def test_unrelated_indications_fail(self) -> None:
        facts = [_indication("a", "Multiple Myeloma"), _indication("b", "Hodgkin Lymphoma")]
        assert _status([B_CELL_LYMPHOMA], facts) == GateStatus.FAIL

    def test_no_fact_is_unknown(self) -> None:
        assert _status([B_CELL_LYMPHOMA], []) == GateStatus.UNKNOWN

    def test_contradicted_fact_is_unknown(self) -> None:
        facts = [_indication("a", "DLBCL", contradicted=True)]
        assert _status([B_CELL_LYMPHOMA], facts) == GateStatus.UNKNOWN

    def test_all_literal_request_keeps_exact_membership(self) -> None:
        # Unchanged path: a literal request is the old per-fact IN.
        facts = [_indication("a", "Relapsed/Refractory Diffuse Large B-cell Lymphoma")]
        assert _status(["lymphoma"], facts) == GateStatus.FAIL
        assert _status(["DLBCL"], [_indication("a", "DLBCL")]) == GateStatus.PASS

    def test_literal_beside_a_concept_matches_exactly(self) -> None:
        assert _status([B_CELL_LYMPHOMA, "CLL"], [_indication("a", "CLL")]) == GateStatus.PASS

    def test_other_gates_do_not_move(self) -> None:
        facts = [_indication("a", "DLBCL")]
        literal = _decisions(["relapsed", "lymphoma"], facts)
        concept = _decisions([B_CELL_LYMPHOMA], facts)
        strip = lambda d: {k: v.status for k, v in d.items() if k != "strategy.indication"}  # noqa: E731
        assert strip(literal) == strip(concept)

    def test_empty_indications_build_no_requirement(self) -> None:
        assert "strategy.indication" not in _decisions([], [_indication("a", "DLBCL")])
