from pathlib import Path

import pytest

from bve.intelligence.buyer_problem_library import BuyerProblemLibrary, load_buyer_problem_config
from bve.intelligence.layer15_buyer_match import Layer15BuyerMatchInput, Layer15BuyerMatcher
from bve.intelligence.science_thesis import BDRoute, ScienceQuestion
from bve.intelligence.science_thesis_builder import ScienceThesisBuilder, ScienceThesisBuilderInput
from bve.models.probability_stack import compute_probability_stack


def test_builder_missing_pkpd_does_not_create_positive_d_score() -> None:
    thesis = ScienceThesisBuilder().build(
        ScienceThesisBuilderInput(
            asset_id="asset-1",
            asset_name="Sparse Asset",
            indication="autoimmune",
            phase="phase2",
            modality="antibody",
            target="BAFF",
            mechanism="BAFF inhibition",
            has_target_rationale=True,
            has_pkpd_evidence=False,
        )
    )

    assert thesis.components["D"].score < 0.5
    assert "PK/PD or exposure evidence" in thesis.missing_critical_evidence
    assert thesis.binding_science_question == ScienceQuestion.ENOUGH_DRUG
    assert thesis.modifier_result is not None
    assert thesis.modifier_result.heuristic_science_modifier < 1.0


def test_builder_missing_biomarker_and_human_poc_are_explicit() -> None:
    thesis = ScienceThesisBuilder().build(
        ScienceThesisBuilderInput(
            asset_id="asset-1",
            indication="oncology",
            phase="phase1",
            target="KRAS",
            mechanism="pathway inhibition",
            has_target_rationale=True,
            has_pkpd_evidence=True,
            has_biomarker_validation=False,
            has_human_poc=False,
        )
    )

    assert "biomarker/translational validation" in thesis.missing_critical_evidence
    assert "human proof-of-concept" in thesis.missing_critical_evidence
    assert any("biomarker" in question.lower() for question in thesis.bd_diligence_questions)
    assert thesis.next_readout_requirement


def test_builder_output_feeds_probability_stack() -> None:
    thesis = ScienceThesisBuilder().build(
        ScienceThesisBuilderInput(asset_id="asset-1", phase="phase2", has_target_rationale=True)
    )
    baseline = compute_probability_stack("asset-1", "phase2")
    adjusted = compute_probability_stack("asset-1", "phase2", science_thesis=thesis)

    assert adjusted.technical_success_prob.probability <= baseline.technical_success_prob.probability


def test_buyer_problem_library_loads_vertex_and_regeneron_configs() -> None:
    library = BuyerProblemLibrary.from_directory("examples/configs/buyer_problems")
    buyer_ids = {problem.buyer_id for problem in library.problems}

    assert "vertex" in buyer_ids
    assert "regeneron" in buyer_ids
    assert library.for_buyer("vertex")[0].scarcity_value == 0.70
    assert library.for_buyer("regeneron")[0].required_ta == ["ophthalmology"]


def test_buyer_problem_library_rejects_malformed_config(tmp_path: Path) -> None:
    malformed = tmp_path / "bad.yaml"
    malformed.write_text("buyer_id: bad\nproblems:\n  - strategic_gap: missing problem id\n")

    with pytest.raises(ValueError):
        load_buyer_problem_config(malformed)


def test_layer15_gates_out_of_sandbox_asset() -> None:
    buyer_problem = BuyerProblemLibrary.from_yaml("examples/configs/buyer_problems/vertex.yaml").problems[0]
    thesis = ScienceThesisBuilder().build(
        ScienceThesisBuilderInput(asset_id="asset-1", phase="phase2", has_target_rationale=True)
    )

    result = Layer15BuyerMatcher().match(
        Layer15BuyerMatchInput(
            science_thesis=thesis,
            buyer_problem=buyer_problem,
            therapeutic_area="oncology",
            target="KRAS",
            modality="small molecule",
            solves_buyer_problem=False,
        )
    )

    assert result.recommended_bd_route == BDRoute.AVOID
    assert "ta_outside_buyer_strategy" in result.failed_gates


def test_layer15_scores_in_sandbox_asset_and_generates_route() -> None:
    buyer_problem = BuyerProblemLibrary.from_yaml("examples/configs/buyer_problems/vertex.yaml").problems[0]
    thesis = ScienceThesisBuilder().build(
        ScienceThesisBuilderInput(
            asset_id="asset-1",
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
            has_clinically_meaningful_effect=True,
        )
    )

    result = Layer15BuyerMatcher().match(
        Layer15BuyerMatchInput(
            science_thesis=thesis,
            buyer_problem=buyer_problem,
            therapeutic_area="autoimmune",
            target="BAFF",
            modality="antibody",
            solves_buyer_problem=True,
            problem_solution_fit=0.85,
            internal_overlap_risk=0.10,
        )
    )

    assert result.passed_hard_gates
    assert result.bd_actionability > 0.6
    assert result.recommended_bd_route in {BDRoute.LICENSE, BDRoute.ACQUISITION, BDRoute.COLLABORATION}
    assert result.route_rationale
