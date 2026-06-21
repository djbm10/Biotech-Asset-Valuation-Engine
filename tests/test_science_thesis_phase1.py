from bve.intelligence.science_thesis import (
    BDRoute,
    BindingConstraintSource,
    BuyerProblem,
    CalibrationStatus,
    ClinicalMeaningfulnessContext,
    EvidenceLayerUse,
    EvidencePolarity,
    EvidenceQualityFactors,
    EvidenceResolution,
    EvidenceResolutionBasis,
    NegativeHumanPOCInterpretability,
    SafetyRiskContext,
    ScienceEvidenceItem,
    ScienceComponentScore,
    ScienceKillFlag,
    ScienceMode,
    ScienceQuestion,
    ScienceThesis,
    ScienceThesisScoringInput,
    compute_bd_actionability,
    compute_science_modifier,
    evaluate_bd_hard_gates,
    post_phase2_enough_drug_resolved,
    recommend_bd_route,
    score_evidence_quality,
    score_science_thesis,
)
from bve.models.probability_stack import compute_probability_stack


def _components(**scores: float) -> dict[str, ScienceComponentScore]:
    defaults = {"T": 0.70, "D": 0.70, "B": 0.70, "H": 0.70, "M": 0.70, "S": 0.70, "Q": 0.70}
    defaults.update(scores)
    return {
        key: ScienceComponentScore(name=key, score=value, confidence=0.8, rationale=f"{key} rationale")
        for key, value in defaults.items()
    }


def _thesis(**kwargs) -> ScienceThesis:
    values = {
        "asset_id": "asset-1",
        "asset_name": "Test Asset",
        "phase": "phase2",
        "mode": ScienceMode.DISCOVERY_INVESTMENT,
        "core_biological_hypothesis": "Target modulation improves disease biology.",
        "binding_science_question": ScienceQuestion.ENOUGH_DRUG,
        "components": _components(),
    }
    values.update(kwargs)
    return ScienceThesis(**values)


def test_science_modifier_keeps_score_belief_and_modifier_separate() -> None:
    thesis = _thesis()
    scored = score_science_thesis(ScienceThesisScoringInput(thesis=thesis))

    assert scored.belief_state.current_belief == 0.5
    assert scored.modifier_result is not None
    assert scored.modifier_result.calibration_status == CalibrationStatus.HEURISTIC
    assert scored.modifier_result.science_score > 0
    assert scored.modifier_result.heuristic_science_modifier > 0
    assert scored.modifier_result.science_score_confidence == 0.8


def test_binding_constraint_caps_strong_weighted_score() -> None:
    result = compute_science_modifier(
        phase="phase2",
        binding_science_question=ScienceQuestion.ENOUGH_DRUG,
        components=_components(T=0.95, D=0.25, B=0.95, H=0.95, M=0.95, S=0.95, Q=0.95),
    )

    assert result.binding_constraint == 0.25
    assert result.science_score == 0.40
    assert result.heuristic_science_modifier == 0.86


def test_biomarker_translation_can_be_binding() -> None:
    result = compute_science_modifier(
        phase="phase2",
        binding_science_question=ScienceQuestion.BIOMARKER_TRANSLATION,
        components=_components(T=0.90, D=0.90, B=0.30, H=0.75, M=0.80, S=0.80, Q=0.80),
    )

    assert result.binding_constraint == 0.30
    assert result.science_score <= 0.45


def test_evidence_quality_uses_explicit_relevance_factors() -> None:
    result = score_evidence_quality(
        EvidenceQualityFactors(
            species_relevance=1.0,
            model_relevance=0.8,
            endpoint_relevance=0.7,
            sample_size=0.6,
            reproducibility=0.5,
            independent_validation=0.4,
            recency=0.9,
            source_credibility=0.9,
        )
    )

    assert result.name == "Q"
    assert result.score == 0.725
    assert "source credibility" in result.rationale


def test_biomarker_double_counting_warning_is_carried_to_modifier() -> None:
    bridge_evidence = ScienceEvidenceItem(
        claim="Biomarker bridges target engagement to clinical benefit.",
        polarity=EvidencePolarity.SUPPORTS,
        confidence=0.8,
        component="B",
        evidence_tags=["biomarker_clinical_bridge"],
        layer_uses=[EvidenceLayerUse.LAYER0, EvidenceLayerUse.POS],
    )
    components = _components()
    components["B"] = ScienceComponentScore(
        name="B",
        score=0.8,
        confidence=0.8,
        evidence_for=[bridge_evidence],
    )
    scored = score_science_thesis(
        ScienceThesisScoringInput(thesis=_thesis(components=components))
    )

    assert scored.modifier_result is not None
    assert "biomarker_double_counting_risk" in scored.modifier_result.warnings


def test_post_phase2_enough_drug_resolution_uses_human_data_state() -> None:
    components = _components(D=0.75, H=0.70)
    components["D"] = components["D"].model_copy(
        update={
            "resolution": EvidenceResolution.RESOLVED,
            "resolution_basis": EvidenceResolutionBasis.HUMAN_PKPD,
        }
    )

    assert post_phase2_enough_drug_resolved("phase3", components)
    assert not post_phase2_enough_drug_resolved("phase1", components)


def test_post_phase2_enough_drug_resolution_rejects_preclinical_basis() -> None:
    components = _components(D=0.75, H=0.70)
    components["D"] = components["D"].model_copy(
        update={
            "resolution": EvidenceResolution.RESOLVED,
            "resolution_basis": EvidenceResolutionBasis.PRECLINICAL,
        }
    )

    assert not post_phase2_enough_drug_resolved("phase3", components)


def test_post_phase2_enough_drug_resolution_accepts_human_evidence_tag() -> None:
    human_pkpd = ScienceEvidenceItem(
        claim="Human dose-response supports target engagement.",
        evidence_tags=["human_dose_response"],
    )
    components = _components(D=0.75, H=0.70)
    components["D"] = components["D"].model_copy(
        update={"resolution": EvidenceResolution.PARTIALLY_RESOLVED, "evidence_for": [human_pkpd]}
    )

    assert post_phase2_enough_drug_resolved("phase3", components)


def test_thesis_carries_clinical_and_safety_context() -> None:
    thesis = _thesis(
        clinical_meaningfulness_context=ClinicalMeaningfulnessContext(
            standard_of_care_context="Current SoC requires monthly injections.",
            competitive_effect_threshold=0.2,
            clinically_meaningful_delta=0.1,
        ),
        safety_context=SafetyRiskContext(
            mechanistic_safety_risk="On-target immunosuppression.",
            observed_clinical_safety_signal="Mild infections to date.",
            tolerability_adherence_risk="Injection-site reactions.",
            regulatory_safety_burden="Long-term infection follow-up.",
        ),
    )

    assert thesis.clinical_meaningfulness_context.competitive_effect_threshold == 0.2
    assert thesis.safety_context.mechanistic_safety_risk == "On-target immunosuppression."


def test_clear_negative_human_poc_caps_modifier() -> None:
    result = compute_science_modifier(
        phase="phase2",
        binding_science_question=ScienceQuestion.HUMAN_POC,
        components=_components(H=0.95),
        direct_negative_human_poc=True,
        negative_human_poc_interpretability=NegativeHumanPOCInterpretability.CLEAR,
    )

    assert result.heuristic_science_modifier == 0.60
    assert ScienceKillFlag.NEGATIVE_HUMAN_POC in result.kill_flags


def test_ambiguous_negative_human_poc_warns_without_hard_cap() -> None:
    result = compute_science_modifier(
        phase="phase2",
        binding_science_question=ScienceQuestion.HUMAN_POC,
        components=_components(H=0.80),
        direct_negative_human_poc=True,
        negative_human_poc_interpretability=NegativeHumanPOCInterpretability.AMBIGUOUS,
    )

    assert "ambiguous_negative_human_poc" in result.warnings
    assert result.modifier_cap == 1.10


def test_manual_binding_constraint_override_warns() -> None:
    result = compute_science_modifier(
        phase="phase2",
        binding_science_question=ScienceQuestion.RIGHT_TARGET,
        components=_components(T=0.90),
        binding_constraint_override=0.40,
    )

    assert result.binding_constraint == 0.40
    assert result.binding_constraint_source == BindingConstraintSource.MANUAL_OVERRIDE
    assert "manual_binding_constraint_override" in result.warnings


def test_target_pathway_refutation_emits_kill_flag() -> None:
    result = compute_science_modifier(
        phase="phase2",
        binding_science_question=ScienceQuestion.RIGHT_TARGET,
        components=_components(T=0.95, D=0.95, B=0.95, H=0.95, M=0.95, S=0.95, Q=0.95),
        target_pathway_refuted=True,
    )

    assert ScienceKillFlag.TARGET_REFUTED in result.kill_flags
    assert result.heuristic_science_modifier == 0.40
    assert result.modifier_cap == 0.40
    assert "target_pathway_refuted_program_kill" in result.warnings


def test_target_pathway_refutation_cannot_increase_technical_pos() -> None:
    thesis = score_science_thesis(
        ScienceThesisScoringInput(
            thesis=_thesis(
                binding_science_question=ScienceQuestion.RIGHT_TARGET,
                components=_components(T=0.95, D=0.95, B=0.95, H=0.95, M=0.95, S=0.95, Q=0.95),
            ),
            target_pathway_refuted=True,
        )
    )

    baseline = compute_probability_stack("asset-1", "phase2")
    adjusted = compute_probability_stack("asset-1", "phase2", science_thesis=thesis)

    assert adjusted.technical_success_prob.probability < baseline.technical_success_prob.probability


def test_probability_stack_accepts_science_thesis_modifier() -> None:
    thesis = score_science_thesis(
        ScienceThesisScoringInput(thesis=_thesis(components=_components(D=0.25)))
    )

    baseline = compute_probability_stack("asset-1", "phase2")
    adjusted = compute_probability_stack("asset-1", "phase2", science_thesis=thesis)

    assert thesis.modifier_result is not None
    assert adjusted.technical_success_prob.probability < baseline.technical_success_prob.probability


def test_bd_hard_gates_exclude_out_of_sandbox_asset() -> None:
    buyer_problem = BuyerProblem(
        buyer_id="vrtx",
        required_ta=["autoimmune"],
        required_targets=["BAFF"],
        required_modalities=["antibody"],
    )

    failed = evaluate_bd_hard_gates(
        buyer_problem,
        therapeutic_area="oncology",
        target="KRAS",
        modality="small molecule",
        solves_buyer_problem=False,
    )

    assert "ta_outside_buyer_strategy" in failed
    assert "target_outside_buyer_sandbox" in failed
    assert "does_not_solve_buyer_problem" in failed

    result = compute_bd_actionability(passed_hard_gates=False, failed_gates=failed)
    assert result.bd_actionability == 0
    assert result.recommended_bd_route == BDRoute.AVOID


def test_bd_actionability_science_is_only_one_component() -> None:
    result = compute_bd_actionability(
        passed_hard_gates=True,
        buyer_problem_fit=0.90,
        science_thesis_fit=0.50,
        evidence_quality=0.50,
        diligence_readiness=0.50,
        modality_capability_fit=0.80,
        buyer_owner_advantage=0.80,
        deal_feasibility=0.70,
        confidence_inputs=[0.7, 0.8],
    )

    assert result.bd_actionability == 0.71
    assert result.bd_actionability_confidence == 0.75


def test_bd_actionability_uses_portfolio_scarcity_and_overlap_fields() -> None:
    result = compute_bd_actionability(
        passed_hard_gates=True,
        buyer_problem_fit=0.60,
        science_thesis_fit=0.55,
        evidence_quality=0.60,
        diligence_readiness=0.60,
        modality_capability_fit=0.70,
        buyer_owner_advantage=0.60,
        internal_portfolio_fit=0.80,
        assessed_internal_overlap_risk=0.60,
        combination_or_lifecycle_fit=0.80,
        alternative_assets_available=["asset-a", "asset-b"],
        scarcity_value=0.90,
        time_sensitivity=0.80,
        deal_feasibility=0.70,
    )

    assert result.buyer_problem_fit == 0.64
    assert result.buyer_owner_advantage == 0.725
    assert result.deal_feasibility == 0.67
    assert result.alternative_assets_available == ["asset-a", "asset-b"]
    assert result.assessed_internal_overlap_risk == 0.60


def test_deal_route_logic_for_strong_human_poc_and_urgent_fit() -> None:
    route, confidence, rationale = recommend_bd_route(
        passed_hard_gates=True,
        science_thesis_fit=0.80,
        human_poc_strength=0.85,
        strategic_fit=0.85,
        urgency=0.85,
    )

    assert route == BDRoute.ACQUISITION
    assert confidence > 0.5
    assert "urgent strategic fit" in rationale
