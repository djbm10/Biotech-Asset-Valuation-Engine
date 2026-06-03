"""Step 6 tests — structured science diligence layer (deterministic, no LLM)."""

from __future__ import annotations

import pytest

from bve.models.endpoint_validity import (
    EndpointCategory,
    EndpointProfile,
    EndpointValidityScoreV2,
    ENDPOINT_LIBRARY,
    RegulatoryWeight,
    score_endpoint,
)
from bve.models.analog_matcher import (
    AnalogMatchResult,
    AnalogOutcome,
    DrugAnalog,
    find_analogs,
)
from bve.models.safety_context import (
    SafetyContextV2,
    SafetySignalType,
    SafetySignalV2,
    compute_safety_context,
)
from bve.models.trial_design_score import (
    DesignDimensionScore,
    TrialDesignDimension,
    TrialDesignQualityScore,
    score_trial_design,
)
from bve.models.science_score import (
    ScienceDiligenceResult,
    ScienceSubScore,
    compute_science_score,
)


# =============================================================================
# TestEndpointValidity (15+ tests)
# =============================================================================


class TestEndpointValidity:
    def test_overall_survival_gold_score_1(self):
        result = score_endpoint("overall survival")
        assert result.regulatory_weight == RegulatoryWeight.GOLD
        assert result.validity_score == pytest.approx(1.0)
        assert result.matched_profile is not None
        assert result.matched_profile.category == EndpointCategory.OS

    def test_os_alias(self):
        result = score_endpoint("os")
        assert result.regulatory_weight == RegulatoryWeight.GOLD
        assert result.validity_score == pytest.approx(1.0)

    def test_pfs_alias(self):
        result = score_endpoint("pfs")
        assert result.regulatory_weight == RegulatoryWeight.SILVER
        assert result.validity_score == pytest.approx(0.85)

    def test_orr_silver(self):
        result = score_endpoint("orr")
        assert result.regulatory_weight == RegulatoryWeight.SILVER
        assert result.validity_score == pytest.approx(0.85)
        assert result.matched_profile.category == EndpointCategory.ORR

    def test_overall_response_rate_alias(self):
        result = score_endpoint("overall response rate")
        assert result.regulatory_weight == RegulatoryWeight.SILVER

    def test_unknown_endpoint_exploratory(self):
        result = score_endpoint("novel biomarker xyz")
        assert result.regulatory_weight == RegulatoryWeight.EXPLORATORY
        assert result.validity_score == pytest.approx(0.50)
        assert result.matched_profile is None
        assert result.requires_comparator is False

    def test_secondary_endpoint_multiplier(self):
        primary = score_endpoint("os", is_primary=True)
        secondary = score_endpoint("os", is_primary=False)
        assert secondary.validity_score == pytest.approx(primary.validity_score * 0.90)
        assert secondary.is_primary is False

    def test_gold_highest_score(self):
        gold = score_endpoint("overall survival")
        silver = score_endpoint("pfs")
        bronze = score_endpoint("dor")
        assert gold.validity_score > silver.validity_score > bronze.validity_score

    def test_bronze_lower_than_silver(self):
        silver = score_endpoint("pfs")
        bronze = score_endpoint("dor")
        assert bronze.validity_score < silver.validity_score

    def test_requires_comparator_true_for_os(self):
        result = score_endpoint("overall survival")
        assert result.requires_comparator is True

    def test_requires_comparator_false_for_unmatched(self):
        result = score_endpoint("completely unknown metric abc123")
        assert result.requires_comparator is False

    def test_case_insensitive(self):
        lower = score_endpoint("overall survival")
        upper = score_endpoint("OVERALL SURVIVAL")
        mixed = score_endpoint("Overall Survival")
        assert lower.validity_score == upper.validity_score == mixed.validity_score

    def test_substring_match_pfs(self):
        """'progression-free survival data' should match PFS via substring."""
        result = score_endpoint("progression-free survival")
        assert result.regulatory_weight == RegulatoryWeight.SILVER

    def test_orr_is_primary_flag(self):
        result = score_endpoint("orr", is_primary=True)
        assert result.is_primary is True

    def test_mrd_biomarker_bronze(self):
        result = score_endpoint("mrd")
        assert result.matched_profile.category == EndpointCategory.BIOMARKER
        assert result.regulatory_weight == RegulatoryWeight.BRONZE

    def test_hba1c_silver(self):
        result = score_endpoint("hba1c")
        assert result.regulatory_weight == RegulatoryWeight.SILVER

    def test_endpoint_library_has_entries(self):
        assert len(ENDPOINT_LIBRARY) >= 15

    def test_panss_psych_pro(self):
        result = score_endpoint("panss")
        assert result.matched_profile is not None
        assert result.matched_profile.category == EndpointCategory.PRO


# =============================================================================
# TestAnalogMatcher (12+ tests)
# =============================================================================


class TestAnalogMatcher:
    def test_glp1_obesity_finds_semaglutide(self):
        result = find_analogs("GLP-1 agonist", "obesity diabetes")
        names = [a.drug_name for a in result.matched_analogs]
        assert any("semaglutide" in n.lower() or "tirzepatide" in n.lower() for n in names)

    def test_pd1_oncology_finds_pembrolizumab(self):
        result = find_analogs("PD-1 inhibitor", "oncology solid tumor")
        names = [a.drug_name for a in result.matched_analogs]
        assert any("pembrolizumab" in n.lower() or "nivolumab" in n.lower() for n in names)

    def test_high_success_rate_analog_score_above_0_6(self):
        result = find_analogs("CDK4/6 inhibitor", "breast cancer")
        if result.matched_analogs:
            assert result.analog_score >= 0.5

    def test_no_match_empty_list_neutral_score(self):
        result = find_analogs("completely fictional mechanism xyz", "martian disease zzz")
        assert result.matched_analogs == []
        assert result.analog_score == pytest.approx(0.5)

    def test_success_rate_plus_failure_rate_lte_1(self):
        result = find_analogs("PD-1 inhibitor", "oncology")
        assert result.success_rate + result.failure_rate <= 1.0 + 1e-9

    def test_success_rate_in_range(self):
        result = find_analogs("GLP-1 agonist", "diabetes")
        assert 0.0 <= result.success_rate <= 1.0

    def test_failure_rate_in_range(self):
        result = find_analogs("GLP-1 agonist", "diabetes")
        assert 0.0 <= result.failure_rate <= 1.0

    def test_median_peak_sales_computed(self):
        result = find_analogs("BTK inhibitor", "hematology CLL")
        if result.matched_analogs and any(a.peak_sales_millions for a in result.matched_analogs):
            assert result.median_peak_sales_millions is not None
            assert result.median_peak_sales_millions > 0

    def test_summary_non_empty(self):
        result = find_analogs("PARP inhibitor", "ovarian breast cancer")
        assert isinstance(result.summary, str)
        assert len(result.summary) > 0

    def test_max_results_respected(self):
        result = find_analogs("PD-1 inhibitor", "oncology", max_results=2)
        assert len(result.matched_analogs) <= 2

    def test_query_fields_preserved(self):
        result = find_analogs("BTK inhibitor", "CLL lymphoma")
        assert result.query_mechanism == "BTK inhibitor"
        assert result.query_indication == "CLL lymphoma"

    def test_factor_xi_failure_analog(self):
        result = find_analogs("factor XI inhibitor", "stroke atrial fibrillation")
        if result.matched_analogs:
            outcomes = [a.outcome for a in result.matched_analogs]
            assert AnalogOutcome.FAILURE in outcomes


# =============================================================================
# TestSafetyContext (12+ tests)
# =============================================================================


class TestSafetyContext:
    def test_no_signals_score_1_low_risk(self):
        ctx = compute_safety_context("asset-1", [])
        assert ctx.overall_safety_score == pytest.approx(1.0)
        assert ctx.class_risk_level == "low"
        assert ctx.controversy_score == pytest.approx(0.0)

    def test_black_box_significant_deduction(self):
        sig = SafetySignalV2(
            signal_type=SafetySignalType.BLACK_BOX_WARNING,
            description="Severe cardiac events",
            severity="severe",
            manageable=False,
        )
        ctx = compute_safety_context("asset-1", [sig])
        assert ctx.overall_safety_score < 0.80

    def test_manageable_signal_half_deduction(self):
        unmanaged = SafetySignalV2(
            signal_type=SafetySignalType.SERIOUS_ADVERSE_EVENT,
            description="Grade 3 neutropenia",
            severity="moderate",
            manageable=False,
        )
        managed = SafetySignalV2(
            signal_type=SafetySignalType.SERIOUS_ADVERSE_EVENT,
            description="Grade 3 neutropenia",
            severity="moderate",
            manageable=True,
        )
        ctx_unmanaged = compute_safety_context("a", [unmanaged])
        ctx_managed = compute_safety_context("a", [managed])
        assert ctx_managed.overall_safety_score > ctx_unmanaged.overall_safety_score

    def test_severe_multiplier_1_5(self):
        mild = SafetySignalV2(
            signal_type=SafetySignalType.GI,
            description="Nausea",
            severity="mild",
            manageable=False,
        )
        severe = SafetySignalV2(
            signal_type=SafetySignalType.GI,
            description="Severe GI toxicity",
            severity="severe",
            manageable=False,
        )
        ctx_mild = compute_safety_context("a", [mild])
        ctx_severe = compute_safety_context("a", [severe])
        assert ctx_severe.overall_safety_score < ctx_mild.overall_safety_score

    def test_life_threatening_larger_deduction_than_severe(self):
        severe = SafetySignalV2(
            signal_type=SafetySignalType.CARDIAC,
            description="Cardiac arrhythmia",
            severity="severe",
            manageable=False,
        )
        life_threat = SafetySignalV2(
            signal_type=SafetySignalType.CARDIAC,
            description="Fatal arrhythmia",
            severity="life_threatening",
            manageable=False,
        )
        ctx_s = compute_safety_context("a", [severe])
        ctx_l = compute_safety_context("a", [life_threat])
        assert ctx_l.overall_safety_score < ctx_s.overall_safety_score

    def test_score_floors_at_0_05(self):
        signals = [
            SafetySignalV2(
                signal_type=SafetySignalType.BLACK_BOX_WARNING,
                description="Fatal",
                severity="life_threatening",
                manageable=False,
            )
            for _ in range(10)
        ]
        ctx = compute_safety_context("a", signals)
        assert ctx.overall_safety_score >= 0.05

    def test_class_risk_level_low_above_0_8(self):
        ctx = compute_safety_context("a", [])
        assert ctx.class_risk_level == "low"

    def test_class_risk_level_very_high_below_0_4(self):
        signals = [
            SafetySignalV2(
                signal_type=SafetySignalType.BLACK_BOX_WARNING,
                description="x",
                severity="life_threatening",
                manageable=False,
            ),
            SafetySignalV2(
                signal_type=SafetySignalType.SERIOUS_ADVERSE_EVENT,
                description="y",
                severity="severe",
                manageable=False,
            ),
            SafetySignalV2(
                signal_type=SafetySignalType.IMMUNE_MEDIATED,
                description="z",
                severity="severe",
                manageable=False,
            ),
        ]
        ctx = compute_safety_context("a", signals)
        assert ctx.class_risk_level in ("high", "very_high")

    def test_controversy_score_positive_for_black_box(self):
        sig = SafetySignalV2(
            signal_type=SafetySignalType.BLACK_BOX_WARNING,
            description="BBW",
            severity="severe",
            manageable=False,
        )
        ctx = compute_safety_context("a", [sig])
        assert ctx.controversy_score > 0.0

    def test_controversy_score_positive_for_immune_mediated(self):
        sig = SafetySignalV2(
            signal_type=SafetySignalType.IMMUNE_MEDIATED,
            description="irAE",
            severity="moderate",
            manageable=True,
        )
        ctx = compute_safety_context("a", [sig])
        assert ctx.controversy_score > 0.0

    def test_manageable_fraction_correct(self):
        signals = [
            SafetySignalV2(
                signal_type=SafetySignalType.GI,
                description="nausea",
                severity="mild",
                manageable=True,
            ),
            SafetySignalV2(
                signal_type=SafetySignalType.HEMATOLOGIC,
                description="neutropenia",
                severity="severe",
                manageable=False,
            ),
        ]
        ctx = compute_safety_context("a", signals)
        assert ctx.manageable_fraction == pytest.approx(0.5)

    def test_rationale_non_empty(self):
        ctx = compute_safety_context("a", [])
        assert isinstance(ctx.rationale, str)
        assert len(ctx.rationale) > 0

    def test_asset_id_preserved(self):
        ctx = compute_safety_context("my-asset-xyz", [])
        assert ctx.asset_id == "my-asset-xyz"


# =============================================================================
# TestTrialDesignScore (15+ tests)
# =============================================================================


class TestTrialDesignScore:
    def test_rct_phase3_active_comparator_large_excellent_or_good(self):
        result = score_trial_design(
            phase="phase3",
            is_randomized=True,
            is_blinded=True,
            has_active_comparator=True,
            enrollment=600,
            primary_endpoint="overall survival",
        )
        assert result.quality_tier in ("EXCELLENT", "GOOD")
        assert result.overall_score >= 0.70

    def test_single_arm_phase2_adequate_or_weak(self):
        result = score_trial_design(
            phase="phase2",
            is_randomized=False,
            is_blinded=False,
            has_active_comparator=False,
            enrollment=80,
            primary_endpoint="orr",
        )
        assert result.quality_tier in ("ADEQUATE", "WEAK")

    def test_phase1_adequate_or_good(self):
        result = score_trial_design(
            phase="phase1",
            is_randomized=False,
            is_blinded=False,
            has_active_comparator=False,
            enrollment=30,
            primary_endpoint="safety",
        )
        assert result.quality_tier in ("ADEQUATE", "GOOD")

    def test_biomarker_enrichment_raises_score(self):
        base = score_trial_design(
            phase="phase2",
            is_randomized=True,
            is_blinded=False,
            has_active_comparator=False,
            enrollment=100,
            primary_endpoint="pfs",
            has_biomarker_enrichment=False,
        )
        enriched = score_trial_design(
            phase="phase2",
            is_randomized=True,
            is_blinded=False,
            has_active_comparator=False,
            enrollment=100,
            primary_endpoint="pfs",
            has_biomarker_enrichment=True,
        )
        assert enriched.overall_score > base.overall_score

    def test_adaptive_design_bonus(self):
        base = score_trial_design(
            phase="phase3",
            is_randomized=True,
            is_blinded=True,
            has_active_comparator=True,
            enrollment=400,
            primary_endpoint="pfs",
            has_adaptive_design=False,
        )
        adaptive = score_trial_design(
            phase="phase3",
            is_randomized=True,
            is_blinded=True,
            has_active_comparator=True,
            enrollment=400,
            primary_endpoint="pfs",
            has_adaptive_design=True,
        )
        assert adaptive.overall_score >= base.overall_score

    def test_quality_tier_excellent_threshold(self):
        result = score_trial_design(
            phase="phase3",
            is_randomized=True,
            is_blinded=True,
            has_active_comparator=True,
            enrollment=800,
            primary_endpoint="overall survival",
            has_biomarker_enrichment=True,
            has_adaptive_design=True,
        )
        assert result.quality_tier == "EXCELLENT"
        assert result.pos_multiplier == pytest.approx(1.10)

    def test_quality_tier_weak_pos_multiplier(self):
        result = score_trial_design(
            phase="phase3",
            is_randomized=False,
            is_blinded=False,
            has_active_comparator=False,
            enrollment=50,
            primary_endpoint="novel biomarker xyz",
        )
        if result.quality_tier == "WEAK":
            assert result.pos_multiplier == pytest.approx(0.80)

    def test_pos_multiplier_matches_quality_tier(self):
        result = score_trial_design(
            phase="phase2",
            is_randomized=True,
            is_blinded=True,
            has_active_comparator=False,
            enrollment=120,
            primary_endpoint="pfs",
        )
        tier_map = {"EXCELLENT": 1.10, "GOOD": 1.00, "ADEQUATE": 0.90, "WEAK": 0.80}
        assert result.pos_multiplier == pytest.approx(tier_map[result.quality_tier])

    def test_key_strengths_populated_for_good_design(self):
        result = score_trial_design(
            phase="phase3",
            is_randomized=True,
            is_blinded=True,
            has_active_comparator=True,
            enrollment=600,
            primary_endpoint="overall survival",
        )
        assert len(result.key_strengths) > 0

    def test_key_concerns_populated_for_weak_design(self):
        result = score_trial_design(
            phase="phase3",
            is_randomized=False,
            is_blinded=False,
            has_active_comparator=False,
            enrollment=40,
            primary_endpoint="novel biomarker",
        )
        assert len(result.key_concerns) > 0

    def test_nct_id_passed_through(self):
        result = score_trial_design(
            phase="phase2",
            is_randomized=True,
            is_blinded=False,
            has_active_comparator=False,
            enrollment=100,
            primary_endpoint="orr",
            nct_id="NCT12345678",
        )
        assert result.nct_id == "NCT12345678"

    def test_nct_id_none_when_not_provided(self):
        result = score_trial_design(
            phase="phase2",
            is_randomized=True,
            is_blinded=False,
            has_active_comparator=False,
            enrollment=100,
            primary_endpoint="orr",
        )
        assert result.nct_id is None

    def test_overall_score_in_range(self):
        result = score_trial_design(
            phase="phase3",
            is_randomized=True,
            is_blinded=True,
            has_active_comparator=True,
            enrollment=500,
            primary_endpoint="pfs",
        )
        assert 0.0 <= result.overall_score <= 1.0

    def test_eight_dimension_scores_returned(self):
        result = score_trial_design(
            phase="phase2",
            is_randomized=True,
            is_blinded=False,
            has_active_comparator=False,
            enrollment=150,
            primary_endpoint="orr",
        )
        assert len(result.dimension_scores) == 8

    def test_phase3_small_enrollment_low_sample_size_score(self):
        result = score_trial_design(
            phase="phase3",
            is_randomized=True,
            is_blinded=True,
            has_active_comparator=True,
            enrollment=50,
            primary_endpoint="pfs",
        )
        sample_size_dim = next(
            d for d in result.dimension_scores if d.dimension == TrialDesignDimension.SAMPLE_SIZE
        )
        assert sample_size_dim.score < 0.70

    def test_none_enrollment_returns_moderate_score(self):
        result = score_trial_design(
            phase="phase2",
            is_randomized=True,
            is_blinded=False,
            has_active_comparator=False,
            enrollment=None,
            primary_endpoint="pfs",
        )
        assert result.overall_score > 0.0


# =============================================================================
# TestScienceDiligenceResult (12+ tests)
# =============================================================================


class TestScienceDiligenceResult:
    def test_compute_science_score_no_error(self):
        result = compute_science_score(
            asset_id="test-asset-1",
            mechanism="PD-1 inhibitor",
            indication="oncology solid tumor",
            primary_endpoint="overall survival",
            phase="phase3",
            is_randomized=True,
            is_blinded=True,
            has_active_comparator=True,
            enrollment=500,
        )
        assert isinstance(result, ScienceDiligenceResult)

    def test_overall_score_in_range(self):
        result = compute_science_score(asset_id="a")
        assert 0.0 <= result.overall_score <= 1.0

    def test_sub_scores_has_expected_keys(self):
        result = compute_science_score(
            asset_id="a",
            mechanism="BTK inhibitor",
            indication="CLL",
            primary_endpoint="pfs",
        )
        assert "endpoint_validity" in result.sub_scores
        assert "trial_design" in result.sub_scores
        assert "analog" in result.sub_scores
        assert "safety" in result.sub_scores

    def test_sub_scores_without_mechanism_no_analog(self):
        result = compute_science_score(asset_id="a", primary_endpoint="orr")
        assert "analog" not in result.sub_scores

    def test_top_positives_is_list(self):
        result = compute_science_score(asset_id="a")
        assert isinstance(result.top_positives, list)

    def test_top_risks_is_list(self):
        result = compute_science_score(asset_id="a")
        assert isinstance(result.top_risks, list)

    def test_endpoint_validity_populated_when_endpoint_provided(self):
        result = compute_science_score(asset_id="a", primary_endpoint="overall survival")
        assert result.endpoint_validity is not None
        assert result.endpoint_validity.regulatory_weight == RegulatoryWeight.GOLD

    def test_endpoint_validity_none_when_no_endpoint(self):
        result = compute_science_score(asset_id="a")
        assert result.endpoint_validity is None

    def test_trial_design_always_populated(self):
        result = compute_science_score(asset_id="a")
        assert result.trial_design is not None
        assert isinstance(result.trial_design, TrialDesignQualityScore)

    def test_analog_result_populated_when_mechanism_and_indication_provided(self):
        result = compute_science_score(
            asset_id="a",
            mechanism="GLP-1 agonist",
            indication="obesity diabetes",
        )
        assert result.analog_result is not None
        assert isinstance(result.analog_result, AnalogMatchResult)

    def test_safety_populated_with_empty_signals(self):
        result = compute_science_score(asset_id="a", safety_signals=[])
        assert result.safety is not None
        assert isinstance(result.safety, SafetyContextV2)

    def test_safety_populated_with_signals(self):
        sig = SafetySignalV2(
            signal_type=SafetySignalType.GI,
            description="nausea",
            severity="mild",
            manageable=True,
        )
        result = compute_science_score(asset_id="a", safety_signals=[sig])
        assert result.safety is not None
        assert result.safety.overall_safety_score < 1.0

    def test_rationale_non_empty(self):
        result = compute_science_score(asset_id="a")
        assert isinstance(result.rationale, str)
        assert len(result.rationale) > 0

    def test_confidence_in_range(self):
        result = compute_science_score(asset_id="a")
        assert 0.0 <= result.confidence <= 1.0

    def test_top_positives_max_3(self):
        result = compute_science_score(
            asset_id="a",
            mechanism="PD-1 inhibitor",
            indication="oncology",
            primary_endpoint="overall survival",
            is_randomized=True,
            is_blinded=True,
            has_active_comparator=True,
            enrollment=600,
            has_biomarker_enrichment=True,
        )
        assert len(result.top_positives) <= 3

    def test_top_risks_max_3(self):
        result = compute_science_score(asset_id="a")
        assert len(result.top_risks) <= 3
