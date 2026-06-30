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
    ScienceGuardrail,
    ScienceGuardrailEffect,
    ScienceKillFlag,
    ScienceMode,
    ScienceQuestion,
    ScienceScoredQuestions,
    ScienceThesis,
    ScienceThesisScoringInput,
    GuardrailSeverity,
    _has_unresolved,
    apply_science_guardrail,
    check_science_pos_overlap,
    compute_bd_actionability,
    compute_science_modifier,
    evaluate_bd_hard_gates,
    post_phase2_enough_drug_resolved,
    recommend_bd_route,
    route_science_key,
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


def test_phase_b_science_thesis_defaults_to_split_model_versions() -> None:
    thesis = _thesis()

    assert thesis.scoring_version == "science_thesis_phase2"
    assert thesis.weight_set_version == "phase2_tdb_v1"
    assert isinstance(thesis.scored_questions, ScienceScoredQuestions)
    assert thesis.scored_questions.right_target.name == "T"
    assert thesis.scored_questions.enough_drug.name == "D"
    assert thesis.scored_questions.translation_bridge.name == "B"
    assert thesis.science_context.clinical_meaningfulness.standard_of_care_context == ""
    assert isinstance(thesis.science_guardrail, ScienceGuardrail)


def test_phase_b_modifier_result_carries_guardrail_audit_fields() -> None:
    result = compute_science_modifier(
        phase="phase2",
        binding_science_question=ScienceQuestion.RIGHT_TARGET,
        components=_components(),
    )

    assert result.scoring_version == "science_thesis_phase2"
    assert result.weight_set_version == "phase2_tdb_v1"
    assert result.guardrail_effects == []
    assert result.combined_soft_derate == 1.0


def test_phase_b_guardrail_effect_model_supports_cap_and_derate() -> None:
    effect = ScienceGuardrailEffect(
        key="negative_human_poc_ambiguous",
        triggered=True,
        soft_derate=0.85,
        severity=GuardrailSeverity.WARN,
        rationale="Ambiguous negative readout still reduces confidence.",
    )

    assert effect.hard_cap is None
    assert effect.soft_derate == 0.85
    assert effect.severity == GuardrailSeverity.WARN


def test_phase_b_legacy_science_keys_route_to_new_owners() -> None:
    assert route_science_key("T") == "scored_questions.right_target"
    assert route_science_key("D") == "scored_questions.enough_drug"
    assert route_science_key("B") == "scored_questions.translation_bridge"
    assert route_science_key("H") == "science_context.human_poc"
    assert route_science_key("M") == "science_context.clinical_meaningfulness"
    assert route_science_key("S") == "science_guardrail"
    assert route_science_key("Q") == "science_context.evidence_quality"


def test_phase_c_modifier_scores_tdb_only_not_hms() -> None:
    high_hms = compute_science_modifier(
        phase="phase2",
        binding_science_question=ScienceQuestion.RIGHT_TARGET,
        components=_components(T=0.40, D=0.40, B=0.40, H=1.0, M=1.0, S=1.0),
    )
    low_hms = compute_science_modifier(
        phase="phase2",
        binding_science_question=ScienceQuestion.RIGHT_TARGET,
        components=_components(T=0.40, D=0.40, B=0.40, H=0.0, M=0.0, S=0.0),
    )

    assert high_hms.science_score == low_hms.science_score == 0.40
    assert high_hms.heuristic_science_modifier == low_hms.heuristic_science_modifier


def test_phase_c_guardrail_composes_hard_cap_and_soft_derates() -> None:
    modifier, effects, combined_soft, cap, kill_flags, warnings = apply_science_guardrail(
        1.05,
        ScienceGuardrail(
            target_refuted=True,
            negative_human_poc=True,
            negative_human_poc_interpretability=NegativeHumanPOCInterpretability.AMBIGUOUS,
            manageable_safety_concern=True,
        ),
    )

    assert cap == 0.20
    assert combined_soft == 0.7225
    assert modifier == 0.1445
    assert ScienceKillFlag.TARGET_REFUTED in kill_flags
    assert "ambiguous_negative_human_poc" in warnings
    assert {effect.key for effect in effects} == {
        "target_refuted",
        "negative_human_poc_ambiguous",
        "manageable_safety_concern",
    }


def test_phase_c_soft_derate_floor_prevents_hidden_hard_cap() -> None:
    caps = {
        "soft_derate_floor": 0.70,
        "negative_human_poc_ambiguous": {"soft_derate": 0.50},
        "manageable_safety_concern": {"soft_derate": 0.50},
    }

    modifier, _effects, combined_soft, cap, _kill_flags, _warnings = apply_science_guardrail(
        1.0,
        ScienceGuardrail(
            negative_human_poc=True,
            negative_human_poc_interpretability=NegativeHumanPOCInterpretability.AMBIGUOUS,
            manageable_safety_concern=True,
        ),
        caps=caps,
    )

    assert cap == 1.10
    assert combined_soft == 0.70
    assert modifier == 0.70


def test_phase_c_late_stage_unresolved_gate_is_strict_and_pos_aware() -> None:
    resolved_components = _components(T=0.65, D=0.65, B=0.65)
    for key in ("T", "D", "B"):
        resolved_components[key] = resolved_components[key].model_copy(
            update={"resolution": EvidenceResolution.RESOLVED}
        )
    assert not _has_unresolved(phase="phase3", components=resolved_components)

    unresolved_components = _components(T=0.65, D=0.65, B=0.35)
    unresolved_components["B"] = unresolved_components["B"].model_copy(
        update={"resolution": EvidenceResolution.UNRESOLVED}
    )
    assert _has_unresolved(phase="phase3", components=unresolved_components)
    assert not _has_unresolved(
        phase="phase3",
        components=unresolved_components,
        pos_fired_adjusters={"biomarker_selection"},
    )


def test_science_modifier_keeps_score_belief_and_modifier_separate() -> None:
    thesis = _thesis()
    scored = score_science_thesis(ScienceThesisScoringInput(thesis=thesis))

    assert scored.belief_state.current_belief == 0.5
    assert scored.modifier_result is not None
    assert scored.modifier_result.calibration_status == CalibrationStatus.HEURISTIC
    assert scored.modifier_result.science_score > 0
    assert scored.modifier_result.heuristic_science_modifier > 0
    # Q now controls confidence; T/D/B drive point estimate.
    assert scored.modifier_result.science_score_confidence == 0.7


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
    assert (
        "science_pos_overlap_kill:shared_science_pos_evidence"
        in scored.modifier_result.warnings
    )


def test_phase_d_overlap_guard_fails_on_shared_source_evidence() -> None:
    shared = ScienceEvidenceItem(
        source_id="doc-1:span-2",
        claim="Same biomarker item drives science and POS.",
        component="B",
        evidence_tags=["biomarker_clinical_bridge"],
        layer_uses=[EvidenceLayerUse.LAYER0, EvidenceLayerUse.POS],
    )
    components = _components()
    components["B"] = ScienceComponentScore(
        name="B",
        score=0.70,
        confidence=0.80,
        evidence_for=[shared],
    )

    warnings = check_science_pos_overlap(components)

    assert len(warnings) == 1
    assert warnings[0].key == "shared_science_pos_evidence"
    assert warnings[0].severity == GuardrailSeverity.KILL
    assert warnings[0].shared_source_id == "doc-1:span-2"


def test_phase_d_overlap_guard_warns_on_related_signal_without_shared_source() -> None:
    related = ScienceEvidenceItem(
        source_id="doc-2:span-4",
        claim="Biomarker evidence is related to a POS factor but not shared.",
        component="B",
        evidence_tags=["biomarker_selection"],
        layer_uses=[EvidenceLayerUse.LAYER0],
    )
    components = _components()
    components["B"] = ScienceComponentScore(
        name="B",
        score=0.70,
        confidence=0.80,
        evidence_for=[related],
    )

    warnings = check_science_pos_overlap(components)

    assert len(warnings) == 1
    assert warnings[0].key == "related_science_pos_signal"
    assert warnings[0].severity == GuardrailSeverity.WARN


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
    assert result.heuristic_science_modifier == 0.20
    assert result.modifier_cap == 0.20
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

    # Chris-aligned Stage 2 weights (0.25 fit / 0.20 human-POC / 0.15 clinical /
    # 0.10 each evidence, modality, owner, deal); science_thesis_fit maps onto both
    # human-POC and clinical terms via backward compatibility. Idea 15: scarcity no
    # longer adds a duplicate scorer term, so the default scarcity=0.5 case scores 0.68.
    assert result.bd_actionability == 0.68
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

    # No time_sensitivity bump on fit any more (Chris: deal urgency is a routing
    # signal, not a fit driver); buyer_problem_fit passes through unchanged.
    assert result.buyer_problem_fit == 0.60
    # Idea 15: scarcity no longer adds a duplicate scorer term, so owner advantage
    # reflects only portfolio + combination fit: 0.60 + 0.05*0.80 + 0.05*0.80 = 0.68.
    assert result.buyer_owner_advantage == 0.68
    # And high scarcity alongside named alternatives is flagged as inconsistent.
    assert "scarcity_inconsistent_with_alternatives" in result.warnings
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
