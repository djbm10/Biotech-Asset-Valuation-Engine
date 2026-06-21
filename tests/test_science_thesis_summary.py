import json

from bve.intelligence.buyer_problem_library import BuyerProblemLibrary
from bve.intelligence.layer15_buyer_match import Layer15BuyerMatchInput, Layer15BuyerMatcher
from bve.intelligence.science_thesis_builder import ScienceThesisBuilder, ScienceThesisBuilderInput
from bve.intelligence.science_thesis_summary import build_bd_summary, build_science_summary


def _thesis():
    return ScienceThesisBuilder().build(
        ScienceThesisBuilderInput(
            asset_id="asset-1",
            asset_name="Asset 1",
            indication="autoimmune",
            phase="phase2",
            modality="antibody",
            target="BAFF",
            mechanism="BAFF inhibition",
            has_target_rationale=True,
            has_pkpd_evidence=True,
            has_human_pkpd_evidence=True,
            has_biomarker_validation=True,
            has_human_poc=True,
        )
    )


def test_science_summary_is_json_safe_and_compact() -> None:
    summary = build_science_summary(_thesis(), modifier_applied=False)

    dumped = json.dumps(summary)
    assert "science_binding_question" in summary
    assert summary["science_modifier_applied"] is False
    assert isinstance(summary["warnings"], list)
    assert "ScienceThesis" not in dumped
    assert "components" not in summary


def test_bd_summary_is_json_safe_and_compact() -> None:
    thesis = _thesis()
    buyer_problem = BuyerProblemLibrary.from_yaml(
        "examples/configs/buyer_problems/vertex.yaml"
    ).problems[0]
    bd_result = Layer15BuyerMatcher().match(
        Layer15BuyerMatchInput(
            science_thesis=thesis,
            buyer_problem=buyer_problem,
            therapeutic_area="autoimmune",
            target="BAFF",
            modality="antibody",
            solves_buyer_problem=True,
            problem_solution_fit=0.8,
        )
    )

    summary = build_bd_summary(
        bd_result,
        buyer_problem=buyer_problem,
        buyer_problem_id=buyer_problem.problem_id,
    )

    dumped = json.dumps(summary)
    assert summary["bd_route"]
    assert summary["bd_hard_gate_passed"] is True
    assert 0.0 <= summary["bd_actionability_score"] <= 1.0
    assert summary["buyer_problem_id"] == buyer_problem.problem_id
    assert "BDActionabilityResult" not in dumped
