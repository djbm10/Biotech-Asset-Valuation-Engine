from bve.intelligence.science_engine import ScienceAssessment, ScienceSubscore
from bve.intelligence.science_thesis import ScienceQuestion
from bve.intelligence.science_thesis_builder import ScienceThesisBuilder, ScienceThesisBuilderInput
from bve.models.science_score import ScienceDiligenceResult, ScienceSubScore


def _assessment(subscores: list[ScienceSubscore] | None = None, design_score: float = 0.8):
    return ScienceAssessment(
        asset_id="asset-1",
        asset_name="Asset One",
        science_score=0.70,
        design_score=design_score,
        confidence_band="medium",
        subscores=subscores or [],
        plain_english_summary="summary",
    )


def _science_result(sub_scores: dict[str, ScienceSubScore]):
    return ScienceDiligenceResult(
        asset_id="asset-1",
        overall_score=0.70,
        confidence=0.70,
        sub_scores=sub_scores,
        top_positives=[],
        top_risks=[],
        rationale="result",
        endpoint_validity=None,
        trial_design=None,
        analog_result=None,
        safety=None,
    )


def test_from_existing_evidence_uses_science_assessment_target_subscore_for_t() -> None:
    thesis = ScienceThesisBuilder().from_existing_evidence(
        science_assessment=_assessment(
            [ScienceSubscore(name="target_validation", value=0.8, confidence=0.8, rationale="target linked")]
        )
    )

    assert thesis.components["T"].score > 0.5
    assert "target/pathway causal rationale" not in thesis.missing_critical_evidence


def test_from_existing_evidence_uses_biomarker_subscore_for_b() -> None:
    thesis = ScienceThesisBuilder().from_existing_evidence(
        science_assessment=_assessment(
            [
                ScienceSubscore(
                    name="biomarker_logic_quality",
                    value=0.8,
                    confidence=0.8,
                    rationale="proximal biomarker bridge",
                )
            ]
        )
    )

    assert thesis.components["B"].score > 0.5
    assert "biomarker/translational validation" not in thesis.missing_critical_evidence


def test_design_score_does_not_become_human_poc() -> None:
    thesis = ScienceThesisBuilder().from_existing_evidence(science_assessment=_assessment(design_score=0.95))

    assert thesis.components["H"].score < 0.5
    assert "human proof-of-concept" in thesis.missing_critical_evidence
    assert thesis.modifier_result is not None
    assert "design_score_not_human_poc" in thesis.modifier_result.warnings


def test_translational_subscore_without_pkpd_terms_maps_to_biomarker_or_ambiguous() -> None:
    thesis = ScienceThesisBuilder().from_existing_evidence(
        science_assessment=_assessment(
            [
                ScienceSubscore(
                    name="translational_evidence_quality",
                    value=0.8,
                    confidence=0.8,
                    rationale="clinical benefit bridge from biomarker",
                )
            ]
        )
    )

    assert thesis.components["D"].score < 0.5
    assert thesis.components["B"].score > 0.5


def test_translational_subscore_with_pkpd_terms_maps_to_d() -> None:
    thesis = ScienceThesisBuilder().from_existing_evidence(
        science_assessment=_assessment(
            [
                ScienceSubscore(
                    name="translational_evidence_quality",
                    value=0.8,
                    confidence=0.8,
                    rationale="human PK/PD exposure and dose target engagement",
                )
            ]
        )
    )

    assert thesis.components["D"].score > 0.5
    assert thesis.components["D"].resolution_basis.value == "human_pkpd"


def test_ambiguous_subscore_adds_warning_instead_of_credit() -> None:
    thesis = ScienceThesisBuilder().from_existing_evidence(
        science_assessment=_assessment(
            [ScienceSubscore(name="novel_quality", value=0.9, confidence=0.8, rationale="good vibes")]
        )
    )

    assert thesis.modifier_result is not None
    assert "ambiguous_existing_science_subscore_mapping" in thesis.modifier_result.warnings


def test_science_result_endpoint_and_trial_design_mapping() -> None:
    thesis = ScienceThesisBuilder().from_existing_evidence(
        science_result=_science_result(
            {
                "endpoint_validity": ScienceSubScore(
                    name="endpoint_validity",
                    score=0.8,
                    confidence=0.8,
                    top_positives=[],
                    top_risks=[],
                    rationale="validated endpoint",
                ),
                "trial_design": ScienceSubScore(
                    name="trial_design",
                    score=0.9,
                    confidence=0.8,
                    top_positives=[],
                    top_risks=[],
                    rationale="randomized controlled design",
                ),
            }
        )
    )

    assert thesis.components["M"].score > 0.5
    assert thesis.components["H"].score < 0.5
    assert thesis.modifier_result is not None
    assert "design_score_not_human_poc" in thesis.modifier_result.warnings


def test_conflicting_explicit_input_and_existing_evidence_adds_warning() -> None:
    explicit = ScienceThesisBuilderInput(asset_id="asset-1", has_human_poc=False)
    thesis = ScienceThesisBuilder().from_existing_evidence(
        science_assessment=_assessment(
            [ScienceSubscore(name="target_validation", value=0.8, confidence=0.8, rationale="target linked")]
        ),
        explicit_inputs=explicit,
    )

    assert thesis.modifier_result is not None
    assert "conflicting_existing_science_evidence" not in thesis.modifier_result.warnings

    conflicting = ScienceThesisBuilder().from_existing_evidence(
        science_assessment=_assessment(
            [ScienceSubscore(name="target_validation", value=0.8, confidence=0.8, rationale="target linked")]
        ),
        explicit_inputs=ScienceThesisBuilderInput(asset_id="asset-1", has_target_rationale=False),
    )
    assert conflicting.modifier_result is not None
    assert "conflicting_existing_science_evidence" in conflicting.modifier_result.warnings


def test_missing_pkpd_remains_missing_when_existing_objects_do_not_support_it() -> None:
    thesis = ScienceThesisBuilder().from_existing_evidence(
        science_assessment=_assessment(
            [ScienceSubscore(name="target_validation", value=0.8, confidence=0.8, rationale="target linked")]
        )
    )

    assert thesis.components["D"].score < 0.5
    assert "PK/PD or exposure evidence" in thesis.missing_critical_evidence
    assert thesis.binding_science_question in {
        ScienceQuestion.ENOUGH_DRUG,
        ScienceQuestion.BIOMARKER_TRANSLATION,
        ScienceQuestion.HUMAN_POC,
    }


def test_from_existing_evidence_supports_provenance_wrapped_dossier() -> None:
    from datetime import date

    from bve.dossier.dossier import AssetDossier, ProvenanceField

    dossier = AssetDossier(program_id="prog-1", asset_name="Drug A", company="BioCo")
    dossier.current_phase = ProvenanceField("phase2", "unit", date(2026, 1, 1), 0.9)
    dossier.target = ProvenanceField("BAFF", "unit", date(2026, 1, 1), 0.9)
    dossier.modality = ProvenanceField("antibody", "unit", date(2026, 1, 1), 0.9)
    dossier.indication = ProvenanceField("autoimmune", "unit", date(2026, 1, 1), 0.9)
    dossier.mechanism_of_action = ProvenanceField("BAFF inhibition", "unit", date(2026, 1, 1), 0.9)

    thesis = ScienceThesisBuilder().from_existing_evidence(asset_dossier=dossier)

    assert thesis.asset_id == "prog-1"
    assert thesis.asset_name == "Drug A"
    assert thesis.phase == "phase2"
    assert "BAFF" in thesis.core_biological_hypothesis
    assert "ProvenanceField" not in thesis.core_biological_hypothesis


def test_from_existing_evidence_supports_nested_pydantic_dossier() -> None:
    from datetime import datetime

    from bve.dossier.asset_dossier import AssetDossier, AssetIdentity, ScienceContext, TrialSnapshot

    dossier = AssetDossier(
        asset_id="asset-2",
        as_of=datetime(2026, 1, 1),
        identity=AssetIdentity(
            asset_id="asset-2",
            drug_name="Drug B",
            indication="ophthalmology",
            modality="bispecific",
        ),
        science=ScienceContext(
            mechanism_summary="dual VEGF/ANG2 blockade",
            target="VEGF",
            biomarker_strategy="retinal fluid reduction",
        ),
        trials=[TrialSnapshot(nct_id="NCT1", phase="phase2", status="recruiting")],
    )

    thesis = ScienceThesisBuilder().from_existing_evidence(asset_dossier=dossier)

    assert thesis.asset_id == "asset-2"
    assert thesis.asset_name == "Drug B"
    assert thesis.indication == "ophthalmology"
    assert thesis.modality == "bispecific"
    assert thesis.phase == "phase2"
    assert "VEGF" in thesis.core_biological_hypothesis
