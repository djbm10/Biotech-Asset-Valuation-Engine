"""
Tests for Layer 1 — BD Decision Decomposition (Sprint 37).

Coverage:
- 1A AssetQuality: weights, clinical_evidence cap
- 1B ValueCreation: weights, valuation-discount gate
- 1C TransactionTiming: weights
- 1D StrategicFit: weights
- 1E DealFeasibility: weights
- 5 institutional gates (trigger + cap semantics)
- Composite formula correctness
- Recommended action + structure logic
- Narrative non-empty assertions
- Integration: compute_bd_mna_composite end-to-end
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_bd_decomposition import (
    AssetQualityInputs,
    BDMAOutput,
    ComponentScore,
    DealFeasibilityInputs,
    RecommendedAction,
    RecommendedStructure,
    StrategicFitInputs,
    TransactionTimingInputs,
    ValueCreationInputs,
    _CLINICAL_EVIDENCE_CAP_THRESHOLD,
    _CLINICAL_EVIDENCE_ASSET_QUALITY_CAP,
    _COMPONENT_WEIGHTS,
    _VALUE_CREATION_ASSET_QUALITY_MIN,
    _GATE1_ASSET_QUALITY_THRESHOLD,
    _GATE1_COMPOSITE_CAP,
    _GATE2_STRATEGIC_FIT_THRESHOLD,
    _GATE2_COMPOSITE_CAP,
    _GATE3_RNPV_GAP_THRESHOLD,
    _GATE3_COMPOSITE_CAP,
    _GATE4_SELLER_WILLINGNESS_THRESHOLD,
    _GATE4_FINANCING_PRESSURE_THRESHOLD,
    _GATE4_COMPOSITE_CAP,
    _GATE5_ASSET_CONTROL_THRESHOLD,
    _GATE5_COMPOSITE_CAP,
    compute_asset_quality,
    compute_bd_mna_composite,
    compute_deal_feasibility,
    compute_strategic_fit,
    compute_transaction_timing,
    compute_value_creation,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _aq(
    clinical_evidence=0.70,
    differentiation=0.70,
    regulatory_path=0.70,
    ip_durability=0.70,
    cmc_feasibility=0.70,
    commercial_meaningfulness=0.70,
) -> AssetQualityInputs:
    return AssetQualityInputs(
        clinical_evidence=clinical_evidence,
        differentiation=differentiation,
        regulatory_path=regulatory_path,
        ip_durability=ip_durability,
        cmc_feasibility=cmc_feasibility,
        commercial_meaningfulness=commercial_meaningfulness,
    )


def _vc(
    premium_adjusted_rnpv_gap=0.70,
    synergy_upside=0.60,
    downside_protection=0.60,
    cost_to_complete=0.60,
    capital_solution_value=0.60,
    premium_adjusted_rnpv_gap_raw=200.0,
) -> ValueCreationInputs:
    return ValueCreationInputs(
        premium_adjusted_rnpv_gap=premium_adjusted_rnpv_gap,
        synergy_upside=synergy_upside,
        downside_protection=downside_protection,
        cost_to_complete=cost_to_complete,
        capital_solution_value=capital_solution_value,
        premium_adjusted_rnpv_gap_raw=premium_adjusted_rnpv_gap_raw,
    )


def _tt(
    financing_pressure=0.65,
    seller_willingness=0.65,
    transaction_window_quality=0.60,
    external_deal_activity=0.60,
    catalyst_setup=0.60,
) -> TransactionTimingInputs:
    return TransactionTimingInputs(
        financing_pressure=financing_pressure,
        seller_willingness=seller_willingness,
        transaction_window_quality=transaction_window_quality,
        external_deal_activity=external_deal_activity,
        catalyst_setup=catalyst_setup,
    )


def _sf(
    ta_fit=0.70,
    modality_fit=0.70,
    pipeline_gap_urgency=0.70,
    development_capability=0.70,
    commercial_capability=0.70,
    cmc_capability=0.70,
    relationship_control=0.70,
) -> StrategicFitInputs:
    return StrategicFitInputs(
        ta_fit=ta_fit,
        modality_fit=modality_fit,
        pipeline_gap_urgency=pipeline_gap_urgency,
        development_capability=development_capability,
        commercial_capability=commercial_capability,
        cmc_capability=cmc_capability,
        relationship_control=relationship_control,
    )


def _df(
    affordability=0.75,
    antitrust_feasibility=0.80,
    asset_control=0.80,
    integration_feasibility=0.75,
    bidder_competition_risk_adjusted=0.65,
) -> DealFeasibilityInputs:
    return DealFeasibilityInputs(
        affordability=affordability,
        antitrust_feasibility=antitrust_feasibility,
        asset_control=asset_control,
        integration_feasibility=integration_feasibility,
        bidder_competition_risk_adjusted=bidder_competition_risk_adjusted,
    )


def _full_run(**overrides) -> BDMAOutput:
    """Run compute_bd_mna_composite with default good inputs, allowing overrides."""
    kwargs = dict(
        target_name="TestCo",
        asset_quality_inputs=_aq(),
        value_creation_inputs=_vc(),
        transaction_timing_inputs=_tt(),
        strategic_fit_inputs=_sf(),
        deal_feasibility_inputs=_df(),
        acquirer_id="AQ-001",
    )
    kwargs.update(overrides)
    return compute_bd_mna_composite(**kwargs)


# ---------------------------------------------------------------------------
# 1A: Asset Quality
# ---------------------------------------------------------------------------

class TestAssetQuality:
    def test_uniform_score(self):
        result = compute_asset_quality(_aq())
        assert 0.0 < result.score <= 1.0

    def test_all_zeros_score_is_zero(self):
        inputs = _aq(0, 0, 0, 0, 0, 0)
        result = compute_asset_quality(inputs)
        assert result.score == pytest.approx(0.0)

    def test_all_ones_score_is_one(self):
        result = compute_asset_quality(_aq(1, 1, 1, 1, 1, 1))
        assert result.score == pytest.approx(1.0)

    def test_clinical_evidence_cap_triggered(self):
        """clinical_evidence < 0.35 and raw > 0.55 → score capped at 0.55."""
        inputs = _aq(
            clinical_evidence=0.10,   # below threshold
            differentiation=1.0,
            regulatory_path=1.0,
            ip_durability=1.0,
            cmc_feasibility=1.0,
            commercial_meaningfulness=1.0,
        )
        result = compute_asset_quality(inputs)
        assert result.cap_applied
        assert result.score <= _CLINICAL_EVIDENCE_ASSET_QUALITY_CAP + 1e-9

    def test_clinical_evidence_cap_not_triggered_when_above_threshold(self):
        inputs = _aq(clinical_evidence=0.36)
        result = compute_asset_quality(inputs)
        assert not result.cap_applied

    def test_sub_scores_populated(self):
        result = compute_asset_quality(_aq())
        assert "clinical_evidence" in result.sub_scores
        assert "differentiation" in result.sub_scores

    def test_clinical_evidence_cap_not_triggered_when_low_raw(self):
        """clinical_evidence < 0.35 but raw <= 0.55 → no cap."""
        inputs = _aq(
            clinical_evidence=0.10,
            differentiation=0.30,
            regulatory_path=0.30,
            ip_durability=0.30,
            cmc_feasibility=0.30,
            commercial_meaningfulness=0.30,
        )
        result = compute_asset_quality(inputs)
        assert not result.cap_applied


# ---------------------------------------------------------------------------
# 1B: Value Creation
# ---------------------------------------------------------------------------

class TestValueCreation:
    def test_uniform_score(self):
        result = compute_value_creation(_vc(), asset_quality_score=0.70)
        assert 0.0 < result.score <= 1.0

    def test_all_zeros_score_is_zero(self):
        inputs = _vc(0, 0, 0, 0, 0)
        result = compute_value_creation(inputs, asset_quality_score=0.70)
        assert result.score == pytest.approx(0.0)

    def test_valuation_discount_clamped_for_low_quality_asset(self):
        """High gap but asset_quality < 0.50 → gap clamped to 0.50."""
        inputs = _vc(premium_adjusted_rnpv_gap=0.95)
        result_low_aq = compute_value_creation(inputs, asset_quality_score=0.40)
        result_high_aq = compute_value_creation(inputs, asset_quality_score=0.70)
        assert result_low_aq.cap_applied
        assert result_low_aq.score < result_high_aq.score

    def test_valuation_discount_not_clamped_above_quality_threshold(self):
        inputs = _vc(premium_adjusted_rnpv_gap=0.95)
        result = compute_value_creation(inputs, asset_quality_score=0.50)
        assert not result.cap_applied

    def test_sub_scores_populated(self):
        result = compute_value_creation(_vc(), asset_quality_score=0.70)
        assert "premium_adjusted_rnpv_gap" in result.sub_scores


# ---------------------------------------------------------------------------
# 1C: Transaction Timing
# ---------------------------------------------------------------------------

class TestTransactionTiming:
    def test_uniform_score(self):
        result = compute_transaction_timing(_tt())
        assert 0.0 < result.score <= 1.0

    def test_all_zeros(self):
        result = compute_transaction_timing(_tt(0, 0, 0, 0, 0))
        assert result.score == pytest.approx(0.0)

    def test_sub_scores_populated(self):
        result = compute_transaction_timing(_tt())
        assert "financing_pressure" in result.sub_scores
        assert "seller_willingness" in result.sub_scores


# ---------------------------------------------------------------------------
# 1D: Strategic Fit
# ---------------------------------------------------------------------------

class TestStrategicFit:
    def test_uniform_score(self):
        result = compute_strategic_fit(_sf())
        assert 0.0 < result.score <= 1.0

    def test_all_zeros(self):
        result = compute_strategic_fit(_sf(0, 0, 0, 0, 0, 0, 0))
        assert result.score == pytest.approx(0.0)

    def test_sub_scores_populated(self):
        result = compute_strategic_fit(_sf())
        assert "ta_fit" in result.sub_scores
        assert "pipeline_gap_urgency" in result.sub_scores


# ---------------------------------------------------------------------------
# 1E: Deal Feasibility
# ---------------------------------------------------------------------------

class TestDealFeasibility:
    def test_uniform_score(self):
        result = compute_deal_feasibility(_df())
        assert 0.0 < result.score <= 1.0

    def test_all_zeros(self):
        result = compute_deal_feasibility(_df(0, 0, 0, 0, 0))
        assert result.score == pytest.approx(0.0)

    def test_sub_scores_populated(self):
        result = compute_deal_feasibility(_df())
        assert "asset_control" in result.sub_scores


# ---------------------------------------------------------------------------
# Composite formula
# ---------------------------------------------------------------------------

class TestCompositeFormula:
    def test_weights_sum_to_1(self):
        assert abs(sum(_COMPONENT_WEIGHTS.values()) - 1.0) < 1e-9

    def test_composite_within_01(self):
        result = _full_run()
        assert 0.0 <= result.bd_ma_score <= 1.0

    def test_pre_gate_score_gte_final_score(self):
        """Gates can only reduce score."""
        result = _full_run()
        assert result.pre_gate_score >= result.bd_ma_score - 1e-9

    def test_all_ones_gives_max_composite_before_gates(self):
        result = _full_run(
            asset_quality_inputs=_aq(1, 1, 1, 1, 1, 1),
            value_creation_inputs=_vc(1, 1, 1, 1, 1, 500.0),
            transaction_timing_inputs=_tt(1, 1, 1, 1, 1),
            strategic_fit_inputs=_sf(1, 1, 1, 1, 1, 1, 1),
            deal_feasibility_inputs=_df(1, 1, 1, 1, 1),
        )
        assert result.pre_gate_score == pytest.approx(1.0)

    def test_all_zeros_gives_zero_composite(self):
        result = _full_run(
            asset_quality_inputs=_aq(0, 0, 0, 0, 0, 0),
            value_creation_inputs=_vc(0, 0, 0, 0, 0, -100.0),
            transaction_timing_inputs=_tt(0, 0, 0, 0, 0),
            strategic_fit_inputs=_sf(0, 0, 0, 0, 0, 0, 0),
            deal_feasibility_inputs=_df(0, 0, 0, 0, 0),
        )
        assert result.bd_ma_score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Gate 1: Asset Quality
# ---------------------------------------------------------------------------

class TestGate1:
    def test_gate1_triggered_when_aq_below_threshold(self):
        result = _full_run(
            asset_quality_inputs=_aq(
                clinical_evidence=0.10,
                differentiation=0.10,
                regulatory_path=0.10,
                ip_durability=0.10,
                cmc_feasibility=0.10,
                commercial_meaningfulness=0.10,
            )
        )
        assert "G1" in result.gate_codes_applied
        assert result.bd_ma_score <= _GATE1_COMPOSITE_CAP + 1e-9

    def test_gate1_not_triggered_when_aq_above_threshold(self):
        result = _full_run()  # default aq=0.70 everywhere
        assert "G1" not in result.gate_codes_applied


# ---------------------------------------------------------------------------
# Gate 2: Strategic Fit
# ---------------------------------------------------------------------------

class TestGate2:
    def test_gate2_triggered_when_sf_below_threshold(self):
        result = _full_run(
            strategic_fit_inputs=_sf(0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10)
        )
        assert "G2" in result.gate_codes_applied
        assert result.bd_ma_score <= _GATE2_COMPOSITE_CAP + 1e-9

    def test_gate2_not_triggered_when_sf_above_threshold(self):
        result = _full_run()
        assert "G2" not in result.gate_codes_applied


# ---------------------------------------------------------------------------
# Gate 3: Value-destructive deal
# ---------------------------------------------------------------------------

class TestGate3:
    def test_gate3_triggered_when_raw_gap_negative(self):
        result = _full_run(
            value_creation_inputs=_vc(premium_adjusted_rnpv_gap_raw=-50.0)
        )
        assert "G3" in result.gate_codes_applied
        assert result.bd_ma_score <= _GATE3_COMPOSITE_CAP + 1e-9

    def test_gate3_not_triggered_when_raw_gap_positive(self):
        result = _full_run(
            value_creation_inputs=_vc(premium_adjusted_rnpv_gap_raw=200.0)
        )
        assert "G3" not in result.gate_codes_applied

    def test_gate3_not_triggered_at_exactly_zero(self):
        """Boundary: raw_gap = 0 → not triggered (strictly negative triggers)."""
        result = _full_run(
            value_creation_inputs=_vc(premium_adjusted_rnpv_gap_raw=0.0)
        )
        assert "G3" not in result.gate_codes_applied


# ---------------------------------------------------------------------------
# Gate 4: Neither seller willing nor under pressure
# ---------------------------------------------------------------------------

class TestGate4:
    def test_gate4_triggered_when_both_below_threshold(self):
        result = _full_run(
            transaction_timing_inputs=_tt(
                financing_pressure=0.10,
                seller_willingness=0.10,
            )
        )
        assert "G4" in result.gate_codes_applied
        assert result.bd_ma_score <= _GATE4_COMPOSITE_CAP + 1e-9

    def test_gate4_not_triggered_when_financing_pressure_sufficient(self):
        result = _full_run(
            transaction_timing_inputs=_tt(
                financing_pressure=0.50,
                seller_willingness=0.10,  # below threshold but pressure is fine
            )
        )
        assert "G4" not in result.gate_codes_applied

    def test_gate4_not_triggered_when_seller_willingness_sufficient(self):
        result = _full_run(
            transaction_timing_inputs=_tt(
                financing_pressure=0.10,
                seller_willingness=0.50,
            )
        )
        assert "G4" not in result.gate_codes_applied


# ---------------------------------------------------------------------------
# Gate 5: Asset control
# ---------------------------------------------------------------------------

class TestGate5:
    def test_gate5_triggered_when_asset_control_low(self):
        result = _full_run(
            deal_feasibility_inputs=_df(asset_control=0.10)
        )
        assert "G5" in result.gate_codes_applied
        assert result.bd_ma_score <= _GATE5_COMPOSITE_CAP + 1e-9

    def test_gate5_not_triggered_when_asset_control_above_threshold(self):
        result = _full_run()
        assert "G5" not in result.gate_codes_applied


# ---------------------------------------------------------------------------
# Multiple gates compound
# ---------------------------------------------------------------------------

class TestMultipleGates:
    def test_two_gates_both_capped(self):
        """Both G1 and G2 trigger → composite ≤ min(G1_cap, G2_cap)."""
        result = _full_run(
            asset_quality_inputs=_aq(0.10, 0.10, 0.10, 0.10, 0.10, 0.10),
            strategic_fit_inputs=_sf(0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10),
        )
        assert "G1" in result.gate_codes_applied
        assert "G2" in result.gate_codes_applied
        lowest_cap = min(_GATE1_COMPOSITE_CAP, _GATE2_COMPOSITE_CAP)
        assert result.bd_ma_score <= lowest_cap + 1e-9


# ---------------------------------------------------------------------------
# Recommended Action
# ---------------------------------------------------------------------------

class TestRecommendedAction:
    def test_pursue_when_high_score_no_gates(self):
        result = _full_run(
            asset_quality_inputs=_aq(1, 1, 1, 1, 1, 1),
            value_creation_inputs=_vc(1, 1, 1, 1, 1, 500.0),
            transaction_timing_inputs=_tt(1, 1, 1, 1, 1),
            strategic_fit_inputs=_sf(1, 1, 1, 1, 1, 1, 1),
            deal_feasibility_inputs=_df(1, 1, 1, 1, 1),
        )
        assert result.recommended_action == RecommendedAction.PURSUE

    def test_pass_when_two_gates_triggered(self):
        result = _full_run(
            asset_quality_inputs=_aq(0.10, 0.10, 0.10, 0.10, 0.10, 0.10),
            strategic_fit_inputs=_sf(0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10),
        )
        assert result.recommended_action == RecommendedAction.PASS

    def test_pass_when_score_below_35(self):
        result = _full_run(
            asset_quality_inputs=_aq(0, 0, 0, 0, 0, 0),
            value_creation_inputs=_vc(0, 0, 0, 0, 0, -10.0),
            transaction_timing_inputs=_tt(0, 0, 0, 0, 0),
            strategic_fit_inputs=_sf(0, 0, 0, 0, 0, 0, 0),
            deal_feasibility_inputs=_df(0, 0, 0, 0, 0),
        )
        assert result.recommended_action == RecommendedAction.PASS


# ---------------------------------------------------------------------------
# Recommended Structure
# ---------------------------------------------------------------------------

class TestRecommendedStructure:
    def test_full_acquisition_when_all_high(self):
        result = _full_run(
            asset_quality_inputs=_aq(1, 1, 1, 1, 1, 1),
            value_creation_inputs=_vc(1, 1, 1, 1, 1, 500.0),
            transaction_timing_inputs=_tt(1, 1, 1, 1, 1),
            strategic_fit_inputs=_sf(1, 1, 1, 1, 1, 1, 1),
            deal_feasibility_inputs=_df(1, 1, 1, 1, 1),
        )
        assert result.recommended_structure == RecommendedStructure.FULL_ACQUISITION

    def test_option_when_negative_rnpv_gap(self):
        result = _full_run(
            value_creation_inputs=_vc(
                premium_adjusted_rnpv_gap=0.60,
                synergy_upside=0.60,
                downside_protection=0.60,
                cost_to_complete=0.60,
                capital_solution_value=0.60,
                premium_adjusted_rnpv_gap_raw=-30.0,   # negative → option structure
            )
        )
        # If aq and sf are not both >= 0.70, option is expected
        assert result.recommended_structure in {
            RecommendedStructure.OPTION_TO_ACQUIRE,
            RecommendedStructure.ASSET_ACQUISITION,
        }


# ---------------------------------------------------------------------------
# Narrative
# ---------------------------------------------------------------------------

class TestNarrative:
    def test_primary_rationale_non_empty(self):
        result = _full_run()
        assert len(result.primary_rationale) > 0

    def test_main_risks_non_empty(self):
        result = _full_run()
        assert len(result.main_risks) > 0

    def test_kill_criteria_non_empty(self):
        result = _full_run()
        assert len(result.kill_criteria) > 0

    def test_diligence_questions_non_empty(self):
        result = _full_run()
        assert len(result.diligence_questions) > 0

    def test_gate_code_in_risks_when_triggered(self):
        result = _full_run(
            asset_quality_inputs=_aq(0.10, 0.10, 0.10, 0.10, 0.10, 0.10),
        )
        risk_text = " ".join(result.main_risks)
        assert "G1" in risk_text


# ---------------------------------------------------------------------------
# Integration — BDMAOutput fields
# ---------------------------------------------------------------------------

class TestBDMAOutput:
    def test_acquirer_id_preserved(self):
        result = _full_run(acquirer_id="BIG-PHARMA-42")
        assert result.best_acquirer_id == "BIG-PHARMA-42"

    def test_target_name_preserved(self):
        result = _full_run(target_name="InnovateCo")
        assert result.target_name == "InnovateCo"

    def test_component_scores_has_all_five_keys(self):
        result = _full_run()
        assert set(result.component_scores.keys()) == {
            "asset_quality", "value_creation", "transaction_timing",
            "strategic_fit", "deal_feasibility",
        }

    def test_no_gates_when_all_strong(self):
        result = _full_run(
            asset_quality_inputs=_aq(1, 1, 1, 1, 1, 1),
            value_creation_inputs=_vc(1, 1, 1, 1, 1, 500.0),
            transaction_timing_inputs=_tt(1, 1, 1, 1, 1),
            strategic_fit_inputs=_sf(1, 1, 1, 1, 1, 1, 1),
            deal_feasibility_inputs=_df(1, 1, 1, 1, 1),
        )
        assert result.gate_codes_applied == []

    def test_score_is_clamped_between_0_and_1(self):
        result = _full_run()
        assert 0.0 <= result.bd_ma_score <= 1.0
        assert 0.0 <= result.pre_gate_score <= 1.0
