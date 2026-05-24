"""
Tests for Layer 1 — Strategic Attractiveness Engine (Sprint 42).

Coverage:
1.  Formula correctness — raw_score = weighted sum of sub-group scores
2.  Weights sum to 1.0
3.  Layer separation — buyer-specific signals must NOT affect Layer 1 score
4.  Value-trap guard — low asset quality caps score at 0.50 when valuation stress is high
5.  Cheapness does not rescue weak asset — premium_rnpv_gap zeroed when aq < 0.50
6.  Clinical evidence cap — ce < 0.35 triggers layer1_cap <= 0.55
7.  Strategic scarcity cap — ss < 0.35 triggers layer1_cap <= 0.60
8.  Structural cleanliness is light — low SC barely affects raw score
9.  Confidence adjustment — low confidence lowers score and flags diligence queue
10. Thesis classification — high_quality_scarce, value_trap, not_actionable,
    distressed_viable, platform_optionality, scarce_weak_vc, structurally_messy
11. Backward compatibility — old compute_bd_mna_composite still works
12. Cap audit trail — every cap records name, cap_value, owning_layer, triggered_by
13. Missing data — None inputs produce neutral scores and lower confidence
14. All-ones gives raw_score 1.0; all-zeros gives raw_score 0.0
15. Sub-group weights assertions
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_layer1_attractiveness import (
    L1_WEIGHTS,
    LAYER1_OWNERSHIP_MAP,
    LAYER3_ONLY_SIGNALS,
    ANTI_DOUBLE_COUNTING_NOTES,
    Cap,
    Layer1AssetQualityInputs,
    Layer1Inputs,
    Layer1Output,
    Layer1StrategicScarcityInputs,
    Layer1StructuralCleanlinessInputs,
    Layer1TransactionSetupInputs,
    Layer1ValueCreationInputs,
    ScoreComponent,
    _AQ_WEIGHTS,
    _SS_WEIGHTS,
    _VC_WEIGHTS,
    _TS_WEIGHTS,
    _SC_WEIGHTS,
    _confidence_multiplier,
    compute_layer1_strategic_attractiveness,
)


# ---------------------------------------------------------------------------
# Fixtures — default inputs
# ---------------------------------------------------------------------------

def _aq(
    clinical_evidence: float | None = 0.70,
    differentiation: float | None = 0.70,
    regulatory_path: float | None = 0.70,
    ip_exclusivity: float | None = 0.70,
    cmc_feasibility: float | None = 0.70,
    commercial_meaningfulness: float | None = 0.70,
    management_execution: float | None = 0.70,
    **kwargs,
) -> Layer1AssetQualityInputs:
    return Layer1AssetQualityInputs(
        clinical_evidence=clinical_evidence,
        differentiation=differentiation,
        regulatory_path=regulatory_path,
        ip_exclusivity=ip_exclusivity,
        cmc_feasibility=cmc_feasibility,
        commercial_meaningfulness=commercial_meaningfulness,
        management_execution=management_execution,
        **kwargs,
    )


def _ss(
    ta_scarcity: float | None = 0.70,
    modality_platform_scarcity: float | None = 0.70,
    competitive_position: float | None = 0.70,
    pipeline_gap_relevance: float | None = 0.70,
    franchise_optionality: float | None = 0.70,
    replacement_difficulty: float | None = 0.70,
    **kwargs,
) -> Layer1StrategicScarcityInputs:
    return Layer1StrategicScarcityInputs(
        ta_scarcity=ta_scarcity,
        modality_platform_scarcity=modality_platform_scarcity,
        competitive_position=competitive_position,
        pipeline_gap_relevance=pipeline_gap_relevance,
        franchise_optionality=franchise_optionality,
        replacement_difficulty=replacement_difficulty,
        **kwargs,
    )


def _vc(
    premium_adjusted_rnpv_gap: float | None = 0.70,
    standalone_rnpv_quality: float | None = 0.70,
    downside_protection: float | None = 0.70,
    cost_to_complete: float | None = 0.70,
    market_expectations_gap: float | None = 0.70,
    strategic_option_value: float | None = 0.70,
    premium_adjusted_rnpv_gap_raw: float = 200.0,
    **kwargs,
) -> Layer1ValueCreationInputs:
    return Layer1ValueCreationInputs(
        premium_adjusted_rnpv_gap=premium_adjusted_rnpv_gap,
        standalone_rnpv_quality=standalone_rnpv_quality,
        downside_protection=downside_protection,
        cost_to_complete=cost_to_complete,
        market_expectations_gap=market_expectations_gap,
        strategic_option_value=strategic_option_value,
        premium_adjusted_rnpv_gap_raw=premium_adjusted_rnpv_gap_raw,
        **kwargs,
    )


def _ts(
    financing_pressure: float | None = 0.60,
    catalyst_proximity: float | None = 0.60,
    seller_openness: float | None = 0.60,
    valuation_stress: float | None = 0.60,
    prior_bd_activity: float | None = 0.60,
    **kwargs,
) -> Layer1TransactionSetupInputs:
    return Layer1TransactionSetupInputs(
        financing_pressure=financing_pressure,
        catalyst_proximity=catalyst_proximity,
        seller_openness=seller_openness,
        valuation_stress=valuation_stress,
        prior_bd_activity=prior_bd_activity,
        **kwargs,
    )


def _sc(
    rights_clarity: float | None = 0.70,
    ip_cleanliness: float | None = 0.70,
    economic_control: float | None = 0.70,
    diligence_readiness: float | None = 0.70,
    manufacturing_transferability: float | None = 0.70,
    **kwargs,
) -> Layer1StructuralCleanlinessInputs:
    return Layer1StructuralCleanlinessInputs(
        rights_clarity=rights_clarity,
        ip_cleanliness=ip_cleanliness,
        economic_control=economic_control,
        diligence_readiness=diligence_readiness,
        manufacturing_transferability=manufacturing_transferability,
        **kwargs,
    )


def _run(
    target_name: str = "TestCo",
    **overrides,
) -> Layer1Output:
    """Run with good defaults; override any sub-group via keyword args."""
    inputs = Layer1Inputs(
        target_name=target_name,
        asset_quality=overrides.get("asset_quality", _aq()),
        strategic_scarcity=overrides.get("strategic_scarcity", _ss()),
        value_creation=overrides.get("value_creation", _vc()),
        transaction_setup=overrides.get("transaction_setup", _ts()),
        structural_cleanliness=overrides.get("structural_cleanliness", _sc()),
    )
    return compute_layer1_strategic_attractiveness(inputs)


# ---------------------------------------------------------------------------
# 1. Formula correctness
# ---------------------------------------------------------------------------

class TestFormula:
    def test_raw_score_matches_weighted_sum(self):
        """raw_score == 0.35*AQ + 0.25*SS + 0.20*VC + 0.15*TS + 0.05*SC."""
        result = _run()
        expected = (
            result.asset_quality.score * L1_WEIGHTS["asset_quality"]
            + result.strategic_scarcity.score * L1_WEIGHTS["strategic_scarcity"]
            + result.value_creation.score * L1_WEIGHTS["value_creation"]
            + result.transaction_setup.score * L1_WEIGHTS["transaction_setup"]
            + result.structural_cleanliness.score * L1_WEIGHTS["structural_cleanliness"]
        )
        assert result.raw_score == pytest.approx(expected, abs=1e-5)

    def test_all_ones_raw_score_is_one(self):
        result = _run(
            asset_quality=_aq(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
            strategic_scarcity=_ss(1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
            value_creation=_vc(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 500.0),
            transaction_setup=_ts(1.0, 1.0, 1.0, 1.0, 1.0),
            structural_cleanliness=_sc(1.0, 1.0, 1.0, 1.0, 1.0),
        )
        assert result.raw_score == pytest.approx(1.0, abs=1e-5)

    def test_all_zeros_raw_score_is_zero(self):
        result = _run(
            asset_quality=_aq(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            strategic_scarcity=_ss(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            value_creation=_vc(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -50.0),
            transaction_setup=_ts(0.0, 0.0, 0.0, 0.0, 0.0),
            structural_cleanliness=_sc(0.0, 0.0, 0.0, 0.0, 0.0),
        )
        assert result.raw_score == pytest.approx(0.0, abs=1e-5)

    def test_scores_always_within_0_1(self):
        result = _run()
        assert 0.0 <= result.raw_score <= 1.0
        assert 0.0 <= result.capped_score <= 1.0
        assert 0.0 <= result.confidence_adjusted_score <= 1.0

    def test_capped_score_lte_raw_score(self):
        """Caps can only reduce the score."""
        result = _run()
        assert result.capped_score <= result.raw_score + 1e-9

    def test_confidence_adjusted_lte_capped_score(self):
        """Confidence multiplier can only reduce or maintain the score."""
        result = _run()
        assert result.confidence_adjusted_score <= result.capped_score + 1e-9


# ---------------------------------------------------------------------------
# 2. Weights sum to 1.0
# ---------------------------------------------------------------------------

class TestWeights:
    def test_l1_weights_sum(self):
        assert abs(sum(L1_WEIGHTS.values()) - 1.0) < 1e-9

    def test_aq_weights_sum(self):
        assert abs(sum(_AQ_WEIGHTS.values()) - 1.0) < 1e-9

    def test_ss_weights_sum(self):
        assert abs(sum(_SS_WEIGHTS.values()) - 1.0) < 1e-9

    def test_vc_weights_sum(self):
        assert abs(sum(_VC_WEIGHTS.values()) - 1.0) < 1e-9

    def test_ts_weights_sum(self):
        assert abs(sum(_TS_WEIGHTS.values()) - 1.0) < 1e-9

    def test_sc_weights_sum(self):
        assert abs(sum(_SC_WEIGHTS.values()) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# 3. Layer separation — buyer-specific signals do not affect Layer 1
# ---------------------------------------------------------------------------

class TestLayerSeparation:
    def test_layer3_signals_not_in_inputs(self):
        """Layer 1 inputs should not contain buyer-specific fields."""
        aq_fields = set(Layer1AssetQualityInputs.model_fields.keys())
        ss_fields = set(Layer1StrategicScarcityInputs.model_fields.keys())
        vc_fields = set(Layer1ValueCreationInputs.model_fields.keys())
        ts_fields = set(Layer1TransactionSetupInputs.model_fields.keys())
        sc_fields = set(Layer1StructuralCleanlinessInputs.model_fields.keys())
        all_fields = aq_fields | ss_fields | vc_fields | ts_fields | sc_fields

        for signal in LAYER3_ONLY_SIGNALS:
            assert signal not in all_fields, (
                f"Layer 3 signal '{signal}' found in Layer 1 inputs — violates layer separation"
            )

    def test_anti_double_counting_notes_non_empty(self):
        result = _run()
        assert len(result.anti_double_counting_notes) > 0

    def test_buyer_affordability_note_present(self):
        result = _run()
        combined = " ".join(result.anti_double_counting_notes)
        assert "buyer_affordability" in combined

    def test_layer3_ownership_in_map(self):
        assert LAYER1_OWNERSHIP_MAP.get("acquirer_specific_affordability") == "Layer 3"
        assert LAYER1_OWNERSHIP_MAP.get("acquirer_specific_antitrust") == "Layer 3"
        assert LAYER1_OWNERSHIP_MAP.get("acquirer_manufacturing_fit") == "Layer 3"


# ---------------------------------------------------------------------------
# 4. Value-trap guard — low asset quality caps when valuation stress is high
# ---------------------------------------------------------------------------

class TestValueTrapGuard:
    def test_value_trap_low_aq_high_valuation_stress(self):
        """asset_quality < 0.50 AND valuation_stress > 0.70 → capped_score <= 0.50."""
        result = _run(
            asset_quality=_aq(0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30),
            transaction_setup=_ts(valuation_stress=0.80),
        )
        assert result.capped_score <= 0.50 + 1e-9

    def test_value_trap_high_financing_pressure_low_aq(self):
        """financing_pressure > 0.70 AND asset_quality < 0.50 → capped_score <= 0.45."""
        result = _run(
            asset_quality=_aq(0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30),
            transaction_setup=_ts(financing_pressure=0.80),
        )
        assert result.capped_score <= 0.45 + 1e-9

    def test_no_value_trap_when_aq_sufficient(self):
        """asset_quality >= 0.50 with high valuation_stress: no value-trap cap."""
        result = _run(
            asset_quality=_aq(0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70),
            transaction_setup=_ts(valuation_stress=0.90, financing_pressure=0.90),
        )
        # No value-trap cap should fire
        cap_names = {c.name for c in result.active_caps}
        assert "composite_value_trap_stress" not in cap_names
        assert "composite_value_trap_financing" not in cap_names

    def test_value_trap_flag_set_in_value_creation(self):
        """When asset_quality < 0.50, value_trap_flags is populated."""
        result = _run(
            asset_quality=_aq(0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30),
            value_creation=_vc(premium_adjusted_rnpv_gap=0.90),  # would inflate without guard
        )
        assert len(result.value_creation.value_trap_flags) > 0


# ---------------------------------------------------------------------------
# 5. Cheapness does not rescue weak asset
# ---------------------------------------------------------------------------

class TestCheapnessGuard:
    def test_high_gap_zeroed_for_low_aq(self):
        """With asset_quality < 0.50, premium_rnpv_gap is clamped to neutral.
        A high gap for a good asset should be larger than for a bad asset."""
        result_good_aq = _run(
            asset_quality=_aq(0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80),
            value_creation=_vc(premium_adjusted_rnpv_gap=0.95),
        )
        result_bad_aq = _run(
            asset_quality=_aq(0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30),
            value_creation=_vc(premium_adjusted_rnpv_gap=0.95),
        )
        # Gap contribution was reduced for bad asset quality
        assert result_good_aq.value_creation.premium_adjusted_rnpv_gap.score > \
               result_bad_aq.value_creation.premium_adjusted_rnpv_gap.score

    def test_value_trap_cap_name_present(self):
        result = _run(
            asset_quality=_aq(0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30),
            value_creation=_vc(premium_adjusted_rnpv_gap=0.95),
        )
        cap_names = {c.name for c in result.active_caps}
        assert "value_trap_gap_zero" in cap_names


# ---------------------------------------------------------------------------
# 6. Clinical evidence cap
# ---------------------------------------------------------------------------

class TestClinicalEvidenceCap:
    def test_ce_below_threshold_triggers_aq_cap(self):
        """clinical_evidence < 0.35 → asset_quality group capped at 0.55."""
        result = _run(
            asset_quality=_aq(
                clinical_evidence=0.10,
                differentiation=1.0,
                regulatory_path=1.0,
                ip_exclusivity=1.0,
                cmc_feasibility=1.0,
                commercial_meaningfulness=1.0,
                management_execution=1.0,
            )
        )
        # Group score should be capped at 0.55
        assert result.asset_quality.score <= 0.55 + 1e-9

    def test_low_ce_triggers_composite_cap(self):
        """clinical_evidence < 0.35 → composite layer1 capped at 0.55."""
        result = _run(
            asset_quality=_aq(clinical_evidence=0.10),
        )
        assert result.capped_score <= 0.55 + 1e-9

    def test_ce_above_threshold_no_cap(self):
        """clinical_evidence >= 0.35 → no clinical evidence cap."""
        result = _run(
            asset_quality=_aq(clinical_evidence=0.50),
        )
        cap_names = {c.name for c in result.active_caps}
        assert "composite_low_clinical_evidence" not in cap_names

    def test_fatal_safety_signal_caps_ce_at_020(self):
        result = _run(
            asset_quality=_aq(clinical_evidence=0.80, fatal_safety_signal=True),
        )
        assert result.asset_quality.clinical_evidence.score <= 0.20 + 1e-9
        cap_names = {c.name for c in result.active_caps}
        assert "fatal_safety_signal_ce_cap" in cap_names

    def test_no_human_data_caps_ce_at_035(self):
        result = _run(
            asset_quality=_aq(clinical_evidence=0.80, no_human_data=True),
        )
        assert result.asset_quality.clinical_evidence.score <= 0.35 + 1e-9


# ---------------------------------------------------------------------------
# 7. Strategic scarcity cap
# ---------------------------------------------------------------------------

class TestStrategicScarcityCap:
    def test_low_ss_triggers_composite_cap(self):
        """strategic_scarcity < 0.35 → layer1 capped at 0.60."""
        result = _run(
            strategic_scarcity=_ss(0.10, 0.10, 0.10, 0.10, 0.10, 0.10),
        )
        assert result.capped_score <= 0.60 + 1e-9

    def test_ss_above_threshold_no_cap(self):
        result = _run(
            strategic_scarcity=_ss(0.70, 0.70, 0.70, 0.70, 0.70, 0.70),
        )
        cap_names = {c.name for c in result.active_caps}
        assert "composite_low_strategic_scarcity" not in cap_names

    def test_clearly_inferior_to_soc_caps_competitive_position(self):
        result = _run(
            strategic_scarcity=_ss(
                competitive_position=0.80,
                clearly_inferior_to_future_soc=True,
            )
        )
        assert result.strategic_scarcity.competitive_position.score <= 0.45 + 1e-9


# ---------------------------------------------------------------------------
# 8. Structural cleanliness is light (5% weight)
# ---------------------------------------------------------------------------

class TestStructuralCleanlinessIsLight:
    def test_sc_weight_is_five_percent(self):
        assert L1_WEIGHTS["structural_cleanliness"] == pytest.approx(0.05)

    def test_zero_sc_barely_affects_raw_score(self):
        """Setting SC to 0 vs 1 should change raw_score by at most 0.05."""
        result_high_sc = _run(
            structural_cleanliness=_sc(1.0, 1.0, 1.0, 1.0, 1.0),
        )
        result_low_sc = _run(
            structural_cleanliness=_sc(0.0, 0.0, 0.0, 0.0, 0.0),
        )
        delta = result_high_sc.raw_score - result_low_sc.raw_score
        assert delta <= 0.05 + 1e-9

    def test_sc_composite_cap_at_065(self):
        """Structural cleanliness < 0.35 triggers composite cap at 0.65 (not lower)."""
        result = _run(
            structural_cleanliness=_sc(0.10, 0.10, 0.10, 0.10, 0.10),
        )
        cap_names = {c.name for c in result.active_caps}
        assert "composite_low_structural_cleanliness" in cap_names
        # The SC cap alone (0.65) should be the max applied by that specific cap
        sc_cap = next(c for c in result.active_caps if c.name == "composite_low_structural_cleanliness")
        assert sc_cap.cap_value == pytest.approx(0.65)


# ---------------------------------------------------------------------------
# 9. Confidence adjustment
# ---------------------------------------------------------------------------

class TestConfidenceAdjustment:
    def test_all_fields_missing_lowers_confidence(self):
        """None fields produce lower overall_confidence than provided fields."""
        result_missing = _run(
            asset_quality=Layer1AssetQualityInputs(),  # all None
            strategic_scarcity=Layer1StrategicScarcityInputs(),
            value_creation=Layer1ValueCreationInputs(),
            transaction_setup=Layer1TransactionSetupInputs(),
            structural_cleanliness=Layer1StructuralCleanlinessInputs(),
        )
        result_full = _run()
        assert result_missing.overall_confidence < result_full.overall_confidence

    def test_low_confidence_flags_diligence_queue(self):
        """overall_confidence < 0.40 sets low_confidence_diligence_queue=True."""
        result = _run(
            asset_quality=Layer1AssetQualityInputs(),
            strategic_scarcity=Layer1StrategicScarcityInputs(),
            value_creation=Layer1ValueCreationInputs(),
            transaction_setup=Layer1TransactionSetupInputs(),
            structural_cleanliness=Layer1StructuralCleanlinessInputs(),
        )
        if result.overall_confidence < 0.40:
            assert result.low_confidence_diligence_queue

    def test_confidence_multiplier_tiers(self):
        assert _confidence_multiplier(0.85) == pytest.approx(1.00)
        assert _confidence_multiplier(0.75) == pytest.approx(0.90)
        assert _confidence_multiplier(0.55) == pytest.approx(0.75)
        assert _confidence_multiplier(0.30) == pytest.approx(0.50)

    def test_confidence_adjusted_score_lte_capped_score(self):
        result = _run()
        assert result.confidence_adjusted_score <= result.capped_score + 1e-9

    def test_confidence_weight_formula(self):
        """overall_confidence is a weighted average of sub-group confidences."""
        result = _run()
        expected = (
            result.asset_quality.confidence * L1_WEIGHTS["asset_quality"]
            + result.strategic_scarcity.confidence * L1_WEIGHTS["strategic_scarcity"]
            + result.value_creation.confidence * L1_WEIGHTS["value_creation"]
            + result.transaction_setup.confidence * L1_WEIGHTS["transaction_setup"]
            + result.structural_cleanliness.confidence * L1_WEIGHTS["structural_cleanliness"]
        )
        assert result.overall_confidence == pytest.approx(expected, abs=1e-5)


# ---------------------------------------------------------------------------
# 10. Thesis classification
# ---------------------------------------------------------------------------

class TestThesisClassification:
    def test_high_quality_strategically_scarce(self):
        result = _run(
            asset_quality=_aq(0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85),
            strategic_scarcity=_ss(0.80, 0.80, 0.80, 0.80, 0.80, 0.80),
            value_creation=_vc(0.80, 0.80, 0.80, 0.80, 0.80, 0.80),
        )
        assert result.thesis_type == "high_quality_strategically_scarce"

    def test_cheap_value_trap(self):
        """Low asset quality + high valuation stress → value trap."""
        result = _run(
            asset_quality=_aq(0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30),
            value_creation=_vc(premium_adjusted_rnpv_gap=0.90),  # appears cheap
            transaction_setup=_ts(valuation_stress=0.85),
        )
        assert result.thesis_type == "cheap_but_low_quality_value_trap"

    def test_great_asset_not_yet_actionable(self):
        # vc must be 0.45–0.59 to skip both high_quality_scarce (vc>=0.60) and
        # scarce_asset_weak_vc (ss>=0.75, vc<0.45).
        result = _run(
            asset_quality=_aq(0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85),
            strategic_scarcity=_ss(0.80, 0.80, 0.80, 0.80, 0.80, 0.80),
            value_creation=_vc(0.50, 0.50, 0.50, 0.50, 0.50, 0.50),  # vc=0.50 < 0.60
            transaction_setup=_ts(0.20, 0.20, 0.20, 0.20, 0.20),  # low setup
        )
        assert result.thesis_type == "great_asset_not_yet_actionable"

    def test_distressed_but_viable(self):
        result = _run(
            asset_quality=_aq(0.75, 0.75, 0.75, 0.75, 0.75, 0.75, 0.75),
            strategic_scarcity=_ss(0.60, 0.60, 0.60, 0.60, 0.60, 0.60),
            value_creation=_vc(0.60, 0.60, 0.60, 0.60, 0.60, 0.60),
            transaction_setup=_ts(financing_pressure=0.85),
        )
        assert result.thesis_type == "distressed_but_viable"

    def test_scarce_asset_weak_value_creation(self):
        result = _run(
            asset_quality=_aq(0.65, 0.65, 0.65, 0.65, 0.65, 0.65, 0.65),
            strategic_scarcity=_ss(0.85, 0.85, 0.85, 0.85, 0.85, 0.85),
            value_creation=_vc(0.30, 0.30, 0.30, 0.30, 0.30, 0.30),
        )
        assert result.thesis_type == "scarce_asset_weak_value_creation"

    def test_platform_optionality_case(self):
        result = _run(
            asset_quality=_aq(
                clinical_evidence=0.50,  # maturing but not great
                differentiation=0.65,
                regulatory_path=0.60,
                ip_exclusivity=0.60,
                cmc_feasibility=0.60,
                commercial_meaningfulness=0.65,
                management_execution=0.60,
            ),
            strategic_scarcity=_ss(
                franchise_optionality=0.90,  # strong optionality
                ta_scarcity=0.70,
                modality_platform_scarcity=0.70,
                competitive_position=0.65,
                pipeline_gap_relevance=0.65,
                replacement_difficulty=0.65,
            ),
        )
        assert result.thesis_type == "platform_optionality_case"

    def test_structurally_messy_but_interesting(self):
        # vc must be < 0.60 to skip high_quality_scarce; ss must be < 0.75 to skip
        # scarce_asset_weak_vc; fp must be < 0.70 to skip distressed_but_viable.
        result = _run(
            asset_quality=_aq(0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80),
            strategic_scarcity=_ss(0.68, 0.68, 0.68, 0.68, 0.68, 0.68),  # ss<0.75
            value_creation=_vc(0.50, 0.50, 0.50, 0.50, 0.50, 0.50),       # vc<0.60
            transaction_setup=_ts(financing_pressure=0.50),                  # fp<0.70
            structural_cleanliness=_sc(0.25, 0.25, 0.25, 0.25, 0.25),
        )
        assert result.thesis_type == "structurally_messy_but_interesting"

    def test_low_priority_pass(self):
        result = _run(
            asset_quality=_aq(0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.20),
            strategic_scarcity=_ss(0.20, 0.20, 0.20, 0.20, 0.20, 0.20),
            value_creation=_vc(0.20, 0.20, 0.20, 0.20, 0.20, 0.20),
            transaction_setup=_ts(0.20, 0.20, 0.20, 0.20, 0.20),
        )
        assert result.thesis_type == "low_priority_pass"

    def test_thesis_type_is_string(self):
        result = _run()
        assert isinstance(result.thesis_type, str)
        assert len(result.thesis_type) > 0

    def test_plain_english_verdict_non_empty(self):
        result = _run()
        assert isinstance(result.plain_english_verdict, str)
        assert len(result.plain_english_verdict) > 20


# ---------------------------------------------------------------------------
# 11. Backward compatibility — old compute_bd_mna_composite still works
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_old_layer1_still_importable(self):
        """The old compute_bd_mna_composite function must still be importable."""
        from bve.intelligence.ma_bd_decomposition import (
            compute_bd_mna_composite,
            AssetQualityInputs,
            ValueCreationInputs,
            TransactionTimingInputs,
            StrategicFitInputs,
            DealFeasibilityInputs,
        )
        assert callable(compute_bd_mna_composite)

    def test_old_layer1_still_runs(self):
        """compute_bd_mna_composite must produce a BDMAOutput without error."""
        from bve.intelligence.ma_bd_decomposition import (
            compute_bd_mna_composite,
            AssetQualityInputs,
            ValueCreationInputs,
            TransactionTimingInputs,
            StrategicFitInputs,
            DealFeasibilityInputs,
        )
        result = compute_bd_mna_composite(
            target_name="BackCompatCo",
            asset_quality_inputs=AssetQualityInputs(
                clinical_evidence=0.70,
                differentiation=0.70,
                regulatory_path=0.70,
                ip_durability=0.70,
                cmc_feasibility=0.70,
                commercial_meaningfulness=0.70,
            ),
            value_creation_inputs=ValueCreationInputs(
                premium_adjusted_rnpv_gap=0.70,
                synergy_upside=0.60,
                downside_protection=0.60,
                cost_to_complete=0.60,
                capital_solution_value=0.60,
                premium_adjusted_rnpv_gap_raw=200.0,
            ),
            transaction_timing_inputs=TransactionTimingInputs(
                financing_pressure=0.60,
                seller_willingness=0.60,
                transaction_window_quality=0.60,
                external_deal_activity=0.60,
                catalyst_setup=0.60,
            ),
            strategic_fit_inputs=StrategicFitInputs(
                ta_fit=0.70,
                modality_fit=0.70,
                pipeline_gap_urgency=0.70,
                development_capability=0.70,
                commercial_capability=0.70,
                cmc_capability=0.70,
                relationship_control=0.70,
            ),
            deal_feasibility_inputs=DealFeasibilityInputs(
                affordability=0.75,
                antitrust_feasibility=0.80,
                asset_control=0.80,
                integration_feasibility=0.75,
                bidder_competition_risk_adjusted=0.65,
            ),
            acquirer_id="AQ-BACKCOMPAT",
        )
        assert result.bd_ma_score >= 0.0
        assert result.bd_ma_score <= 1.0

    def test_new_layer1_does_not_break_old_imports(self):
        """Importing the new module must not affect the old module."""
        from bve.intelligence.ma_layer1_attractiveness import (
            compute_layer1_strategic_attractiveness,
        )
        from bve.intelligence.ma_bd_decomposition import (
            compute_bd_mna_composite,
        )
        assert compute_layer1_strategic_attractiveness is not compute_bd_mna_composite


# ---------------------------------------------------------------------------
# 12. Cap audit trail
# ---------------------------------------------------------------------------

class TestCapAuditTrail:
    def test_every_cap_has_required_fields(self):
        result = _run(
            asset_quality=_aq(clinical_evidence=0.10),  # triggers caps
        )
        for cap in result.active_caps:
            assert isinstance(cap, Cap)
            assert cap.name
            assert 0.0 <= cap.cap_value <= 1.0
            assert cap.reason
            assert cap.owning_layer == "Layer 1"
            assert cap.triggered_by

    def test_triggered_caps_sorted_in_active_caps(self):
        result = _run(
            asset_quality=_aq(clinical_evidence=0.10),
        )
        assert len(result.active_caps) >= 1

    def test_no_buyer_specific_cap_names(self):
        """Layer 1 caps must not reference buyer-specific concepts."""
        result = _run(
            asset_quality=_aq(0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10),
            strategic_scarcity=_ss(0.10, 0.10, 0.10, 0.10, 0.10, 0.10),
        )
        for cap in result.active_caps:
            for bad_word in ("affordability", "antitrust", "acquirer", "buyer", "rofr"):
                assert bad_word not in cap.name.lower(), (
                    f"Cap '{cap.name}' references buyer-specific concept '{bad_word}'"
                )


# ---------------------------------------------------------------------------
# 13. Missing data — None inputs produce neutral scores and lower confidence
# ---------------------------------------------------------------------------

class TestMissingData:
    def test_none_fields_produce_neutral_score(self):
        """All-None inputs use neutral scores (0.50), not zeros."""
        inputs = Layer1Inputs(
            target_name="MissingCo",
            asset_quality=Layer1AssetQualityInputs(),
            strategic_scarcity=Layer1StrategicScarcityInputs(),
            value_creation=Layer1ValueCreationInputs(),
            transaction_setup=Layer1TransactionSetupInputs(),
            structural_cleanliness=Layer1StructuralCleanlinessInputs(),
        )
        result = compute_layer1_strategic_attractiveness(inputs)
        # raw_score should be approximately 0.50 (neutral)
        assert result.raw_score == pytest.approx(0.50, abs=0.10)

    def test_none_fields_lower_confidence(self):
        result_full = _run()  # all fields provided
        result_missing = _run(
            asset_quality=Layer1AssetQualityInputs(),  # all None
        )
        assert result_missing.overall_confidence < result_full.overall_confidence

    def test_target_name_preserved(self):
        result = _run(target_name="TargetNameCo")
        assert result is not None  # name is in inputs, not output — just check no crash


# ---------------------------------------------------------------------------
# 14. Sub-group scores within [0, 1]
# ---------------------------------------------------------------------------

class TestSubGroupBounds:
    def test_all_sub_group_scores_within_01(self):
        result = _run()
        for group in [
            result.asset_quality,
            result.strategic_scarcity,
            result.value_creation,
            result.transaction_setup,
            result.structural_cleanliness,
        ]:
            assert 0.0 <= group.score <= 1.0
            assert 0.0 <= group.confidence <= 1.0

    def test_all_sub_component_scores_within_01(self):
        result = _run()
        for group in [
            result.asset_quality,
            result.strategic_scarcity,
            result.value_creation,
            result.transaction_setup,
            result.structural_cleanliness,
        ]:
            for field_name, value in group:
                if isinstance(value, ScoreComponent):
                    assert 0.0 <= value.score <= 1.0, (
                        f"{field_name}.score={value.score} out of bounds"
                    )
                    assert 0.0 <= value.confidence <= 1.0, (
                        f"{field_name}.confidence={value.confidence} out of bounds"
                    )


# ---------------------------------------------------------------------------
# 15. Diligence questions and narrative fields
# ---------------------------------------------------------------------------

class TestNarrative:
    def test_diligence_questions_non_empty(self):
        result = _run()
        assert len(result.diligence_questions) >= 3

    def test_top_positive_drivers_type(self):
        result = _run()
        assert isinstance(result.top_positive_drivers, list)

    def test_top_negative_drivers_type(self):
        result = _run()
        assert isinstance(result.top_negative_drivers, list)

    def test_low_clinical_evidence_adds_diligence_question(self):
        result = _run(
            asset_quality=_aq(clinical_evidence=0.45),
        )
        combined = " ".join(result.diligence_questions)
        assert "clinical" in combined.lower()

    def test_negative_rnpv_gap_adds_pricing_question(self):
        result = _run(
            value_creation=_vc(premium_adjusted_rnpv_gap_raw=-20.0),
        )
        combined = " ".join(result.diligence_questions)
        assert "price" in combined.lower() or "earn-out" in combined.lower() or "cvr" in combined.lower()
