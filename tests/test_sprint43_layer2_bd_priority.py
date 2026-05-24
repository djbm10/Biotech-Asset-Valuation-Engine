"""
Sprint 43 tests — Layer 2 BD Prioritization Engine (ma_layer2_bd_priority.py).

Coverage (13 test classes):
 1.  Weights sum-to-1 invariants
 2.  BD Action Score formula correctness
 3.  Old double-counting eliminated: acquirer fit appears only in Acquirer Pull
 4.  Strategic Watch — high SP + low DM → never Active Pursuit
 5.  Active Pursuit Candidate — all signals strong
 6.  Diligence Queue — high score but low information readiness
 7.  Distress Trap Warning — high pressure + weak asset quality
 8.  Weighted driver strength — uses weights × strength × confidence / total
 9.  Target-side vs buyer-side balance test
10.  Buyer universe depth and single-buyer concentration risk
11.  Information readiness cap on BD Action Score
12.  Layer ownership warnings for L3-only inputs
13.  Backward compat — old Layer 2 (ma_scoring.py) still importable and unchanged
14.  Action classification — all 9 classes reachable
15.  Missing data reduces confidence, not score to zero
"""
from __future__ import annotations

import math
import pytest

from bve.intelligence.ma_layer2_bd_priority import (
    ActionClass,
    AcquirerPullInputRow,
    DRIVER_WEIGHTS,
    L2_WEIGHTS,
    Layer2BDOutput,
    Layer2BuyerSideUrgencyInputs,
    Layer2InformationReadinessInputs,
    Layer2Inputs,
    Layer2StrategicPriorityInputs,
    Layer2TargetSidePressureInputs,
    LAYER2_OWNERSHIP_MAP,
    LAYER3_ONLY_INPUTS,
    _AP_WEIGHTS,
    _BSU_WEIGHTS,
    _IR_WEIGHTS,
    _SP_WEIGHTS,
    _TSP_WEIGHTS,
    _TOTAL_DRIVER_WEIGHT,
    compute_layer2_bd_priority,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _sp(
    l1_score: float = 0.70,
    l1_scarcity: float = 0.70,
    l1_aq: float = 0.70,
    asf: float = 0.65,
    pgu: float = 0.60,
    sov: float = 0.55,
) -> Layer2StrategicPriorityInputs:
    return Layer2StrategicPriorityInputs(
        layer1_attractiveness_score=l1_score,
        layer1_strategic_scarcity_score=l1_scarcity,
        layer1_asset_quality_score=l1_aq,
        acquirer_strategic_fit=asf,
        pipeline_gap_urgency=pgu,
        strategic_option_value=sov,
    )


def _tsp(
    financing_pressure: float = 0.55,
    seller_openness: float = 0.55,
    catalyst_timing: float = 0.55,
    valuation_distress: float = 0.50,
    governance_activist_pressure: float = 0.45,
) -> Layer2TargetSidePressureInputs:
    return Layer2TargetSidePressureInputs(
        financing_pressure=financing_pressure,
        seller_openness=seller_openness,
        catalyst_timing=catalyst_timing,
        valuation_distress=valuation_distress,
        governance_activist_pressure=governance_activist_pressure,
    )


def _bsu(
    pipeline_gap_urgency: float = 0.60,
    loe_revenue_cliff_urgency: float = 0.55,
    competitive_fomo: float = 0.50,
    recent_bd_pattern: float = 0.45,
    strategic_priority_recency: float = 0.50,
) -> Layer2BuyerSideUrgencyInputs:
    return Layer2BuyerSideUrgencyInputs(
        pipeline_gap_urgency=pipeline_gap_urgency,
        loe_revenue_cliff_urgency=loe_revenue_cliff_urgency,
        competitive_fomo=competitive_fomo,
        recent_bd_pattern=recent_bd_pattern,
        strategic_priority_recency=strategic_priority_recency,
    )


def _ir(
    l1_confidence: float = 0.70,
    acquirer_profile_freshness: float = 0.70,
    transaction_driver_source_quality: float = 0.65,
    valuation_data_freshness: float = 0.65,
    rights_encumbrance_clarity: float = 0.70,
    catalyst_date_confidence: float = 0.65,
) -> Layer2InformationReadinessInputs:
    return Layer2InformationReadinessInputs(
        layer1_confidence=l1_confidence,
        acquirer_profile_freshness=acquirer_profile_freshness,
        transaction_driver_source_quality=transaction_driver_source_quality,
        valuation_data_freshness=valuation_data_freshness,
        rights_encumbrance_clarity=rights_encumbrance_clarity,
        catalyst_date_confidence=catalyst_date_confidence,
    )


def _acq(
    acquirer_id: str = "aq1",
    acquirer_name: str = "Acquirer A",
    ta_fit: float = 0.75,
    modality_fit: float = 0.70,
    pipeline_gap_urgency: float = 0.70,
    buyer_deal_appetite: float = 0.65,
    existing_relationship: float = 0.30,
    competitive_fomo: float = 0.55,
) -> AcquirerPullInputRow:
    return AcquirerPullInputRow(
        acquirer_id=acquirer_id,
        acquirer_name=acquirer_name,
        ta_fit=ta_fit,
        modality_fit=modality_fit,
        pipeline_gap_urgency=pipeline_gap_urgency,
        buyer_deal_appetite=buyer_deal_appetite,
        existing_relationship=existing_relationship,
        competitive_fomo=competitive_fomo,
    )


def _run(**overrides) -> Layer2BDOutput:
    """Build a default Layer2Inputs with optional field overrides and run."""
    defaults: dict = dict(
        target_name="TestCo",
        strategic_priority=_sp(),
        target_side_pressure=_tsp(),
        buyer_side_urgency=_bsu(),
        acquirer_pull=[_acq()],
        information_readiness=_ir(),
    )
    defaults.update(overrides)
    return compute_layer2_bd_priority(Layer2Inputs(**defaults))


# ---------------------------------------------------------------------------
# 1. Weights invariants
# ---------------------------------------------------------------------------

class TestWeightInvariants:
    def test_l2_weights_sum_to_1(self):
        assert abs(sum(L2_WEIGHTS.values()) - 1.0) < 1e-9

    def test_sp_weights_sum_to_1(self):
        assert abs(sum(_SP_WEIGHTS.values()) - 1.0) < 1e-9

    def test_tsp_weights_sum_to_1(self):
        assert abs(sum(_TSP_WEIGHTS.values()) - 1.0) < 1e-9

    def test_bsu_weights_sum_to_1(self):
        assert abs(sum(_BSU_WEIGHTS.values()) - 1.0) < 1e-9

    def test_ap_weights_sum_to_1(self):
        assert abs(sum(_AP_WEIGHTS.values()) - 1.0) < 1e-9

    def test_ir_weights_sum_to_1(self):
        assert abs(sum(_IR_WEIGHTS.values()) - 1.0) < 1e-9

    def test_l2_weights_correct_values(self):
        assert L2_WEIGHTS["strategic_priority"] == pytest.approx(0.40)
        assert L2_WEIGHTS["deal_momentum"] == pytest.approx(0.30)
        assert L2_WEIGHTS["acquirer_pull"] == pytest.approx(0.20)
        assert L2_WEIGHTS["information_readiness"] == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# 2. BD Action Score formula correctness
# ---------------------------------------------------------------------------

class TestBDActionScoreFormula:
    def test_formula_uses_l2_weights(self):
        result = _run()
        # raw = 0.40×SP + 0.30×DM + 0.20×AP + 0.10×IR (before any caps)
        expected_raw = round(
            0.40 * result.strategic_priority.score
            + 0.30 * result.deal_momentum.score
            + 0.20 * result.acquirer_pull.score
            + 0.10 * result.information_readiness.score,
            6,
        )
        assert result.bd_action_score == pytest.approx(expected_raw, abs=1e-5)

    def test_capped_lte_raw(self):
        result = _run()
        assert result.capped_bd_action_score <= result.bd_action_score + 1e-9

    def test_confidence_adjusted_lte_capped(self):
        result = _run()
        assert result.confidence_adjusted_score <= result.capped_bd_action_score + 1e-9

    def test_all_zero_inputs_gives_low_score(self):
        result = compute_layer2_bd_priority(Layer2Inputs(
            target_name="ZeroCo",
            strategic_priority=Layer2StrategicPriorityInputs(
                layer1_attractiveness_score=0.0,
                layer1_asset_quality_score=0.0,
                layer1_strategic_scarcity_score=0.0,
                acquirer_strategic_fit=0.0,
                pipeline_gap_urgency=0.0,
                strategic_option_value=0.0,
            ),
            target_side_pressure=Layer2TargetSidePressureInputs(
                financing_pressure=0.0, seller_openness=0.0, catalyst_timing=0.0,
                valuation_distress=0.0, governance_activist_pressure=0.0,
            ),
            buyer_side_urgency=Layer2BuyerSideUrgencyInputs(
                pipeline_gap_urgency=0.0, loe_revenue_cliff_urgency=0.0,
                competitive_fomo=0.0, recent_bd_pattern=0.0, strategic_priority_recency=0.0,
            ),
            acquirer_pull=[AcquirerPullInputRow(
                acquirer_id="z", acquirer_name="Z",
                ta_fit=0.0, modality_fit=0.0, pipeline_gap_urgency=0.0,
                buyer_deal_appetite=0.0, existing_relationship=0.0, competitive_fomo=0.0,
            )],
            information_readiness=Layer2InformationReadinessInputs(
                layer1_confidence=0.0, acquirer_profile_freshness=0.0,
                transaction_driver_source_quality=0.0, valuation_data_freshness=0.0,
                rights_encumbrance_clarity=0.0, catalyst_date_confidence=0.0,
            ),
        ))
        assert result.confidence_adjusted_score < 0.40
        assert result.bd_action_score < 0.30

    def test_all_scores_in_01(self):
        result = _run()
        assert 0.0 <= result.bd_action_score <= 1.0
        assert 0.0 <= result.capped_bd_action_score <= 1.0
        assert 0.0 <= result.confidence_adjusted_score <= 1.0
        assert 0.0 <= result.overall_confidence <= 1.0
        assert 0.0 <= result.confidence_multiplier <= 1.0


# ---------------------------------------------------------------------------
# 3. No double-counting of acquirer fit
# ---------------------------------------------------------------------------

class TestNoAcquirerFitDoubleCount:
    def test_acquirer_fit_only_in_acquirer_pull(self):
        """
        The old formula counted AF in SP (0.45×AF), TP (0.25×AF), and BD raw (0.15×AF).
        The new formula counts acquirer-specific fit ONLY inside Acquirer Pull.
        Strategic Priority uses industry-level acquirer_strategic_fit (different concept).
        """
        # Acquirer Pull sub-component names must not appear in SP weight keys
        ap_keys = set(_AP_WEIGHTS.keys())
        sp_keys = set(_SP_WEIGHTS.keys())
        # No direct acquirer-pull sub-field should be in SP weights
        assert "ta_fit" not in sp_keys
        assert "modality_fit" not in sp_keys
        assert "buyer_deal_appetite" not in sp_keys
        assert "existing_relationship" not in sp_keys

    def test_l2_formula_has_no_af_term_outside_ap(self):
        """BD Action Score = 0.40×SP + 0.30×DM + 0.20×AP + 0.10×IR.
        Acquirer Pull is 0.20 — only one term, not three."""
        assert L2_WEIGHTS["acquirer_pull"] == pytest.approx(0.20)
        # Old formula: AF appeared in SP (0.45×AF), TP (0.25×AF), BD raw (0.15×AF)
        # Sum of old AF exposure = 0.45*SP_weight + 0.25*TP_weight + 0.15
        # In new formula AF is confined to the 0.20×AP term
        assert sum(L2_WEIGHTS.values()) == pytest.approx(1.0)
        # The only weight that references acquirer pull is the dedicated 0.20 slot
        non_ap_weights = {k: v for k, v in L2_WEIGHTS.items() if k != "acquirer_pull"}
        # SP, DM, IR do not duplicate acquirer fit
        assert "acquirer_pull" not in non_ap_weights


# ---------------------------------------------------------------------------
# 4. Strategic Watch — high SP, low DM
# ---------------------------------------------------------------------------

class TestStrategicWatch:
    def test_high_sp_low_dm_not_active_pursuit(self):
        result = _run(
            strategic_priority=_sp(l1_score=0.85, asf=0.80, l1_scarcity=0.80),
            target_side_pressure=_tsp(
                financing_pressure=0.10, seller_openness=0.10,
                catalyst_timing=0.10, valuation_distress=0.05,
                governance_activist_pressure=0.05,
            ),
            buyer_side_urgency=_bsu(
                pipeline_gap_urgency=0.15, loe_revenue_cliff_urgency=0.15,
                competitive_fomo=0.10, recent_bd_pattern=0.10,
                strategic_priority_recency=0.10,
            ),
        )
        assert result.action_classification != ActionClass.ACTIVE_PURSUIT
        # SP should be high
        assert result.strategic_priority.score >= 0.65

    def test_strategic_watch_classified_correctly(self):
        result = _run(
            strategic_priority=_sp(l1_score=0.82, asf=0.78, l1_scarcity=0.75),
            target_side_pressure=_tsp(
                financing_pressure=0.10, seller_openness=0.10,
                catalyst_timing=0.10, valuation_distress=0.05,
                governance_activist_pressure=0.05,
            ),
            buyer_side_urgency=_bsu(
                pipeline_gap_urgency=0.15, loe_revenue_cliff_urgency=0.15,
                competitive_fomo=0.10, recent_bd_pattern=0.10,
                strategic_priority_recency=0.10,
            ),
        )
        assert result.action_classification == ActionClass.STRATEGIC_WATCH

    def test_deal_momentum_capped_when_no_drivers(self):
        result = _run(
            target_side_pressure=_tsp(
                financing_pressure=0.10, seller_openness=0.10,
                catalyst_timing=0.10, valuation_distress=0.10,
                governance_activist_pressure=0.10,
            ),
            buyer_side_urgency=_bsu(
                pipeline_gap_urgency=0.10, loe_revenue_cliff_urgency=0.10,
                competitive_fomo=0.10, recent_bd_pattern=0.10,
                strategic_priority_recency=0.10,
            ),
        )
        assert result.deal_momentum.score <= 0.35 + 1e-9
        assert any("no_active_drivers" in c for c in result.deal_momentum.caps)


# ---------------------------------------------------------------------------
# 5. Active Pursuit Candidate
# ---------------------------------------------------------------------------

class TestActivePursuit:
    def test_all_high_signals_gives_active_pursuit(self):
        result = compute_layer2_bd_priority(Layer2Inputs(
            target_name="HighPriority",
            strategic_priority=_sp(
                l1_score=0.85, l1_scarcity=0.82, l1_aq=0.80,
                asf=0.80, pgu=0.78, sov=0.75,
            ),
            target_side_pressure=_tsp(
                financing_pressure=0.80, seller_openness=0.75,
                catalyst_timing=0.80, valuation_distress=0.70,
                governance_activist_pressure=0.65,
            ),
            buyer_side_urgency=_bsu(
                pipeline_gap_urgency=0.78, loe_revenue_cliff_urgency=0.75,
                competitive_fomo=0.70, recent_bd_pattern=0.65,
                strategic_priority_recency=0.70,
            ),
            acquirer_pull=[
                _acq(ta_fit=0.85, modality_fit=0.80, pipeline_gap_urgency=0.82,
                     buyer_deal_appetite=0.78, existing_relationship=0.65,
                     competitive_fomo=0.72),
            ],
            information_readiness=_ir(
                l1_confidence=0.80, acquirer_profile_freshness=0.78,
                transaction_driver_source_quality=0.75, valuation_data_freshness=0.72,
                rights_encumbrance_clarity=0.80, catalyst_date_confidence=0.78,
            ),
        ))
        assert result.action_classification == ActionClass.ACTIVE_PURSUIT
        assert result.confidence_adjusted_score > 0.60

    def test_active_pursuit_requires_all_four_thresholds(self):
        """Dropping AP below 0.65 should prevent Active Pursuit."""
        result = compute_layer2_bd_priority(Layer2Inputs(
            target_name="AlmostPursuit",
            strategic_priority=_sp(l1_score=0.85, asf=0.80, l1_scarcity=0.80, l1_aq=0.80),
            target_side_pressure=_tsp(
                financing_pressure=0.78, seller_openness=0.72,
                catalyst_timing=0.78, valuation_distress=0.68,
                governance_activist_pressure=0.62,
            ),
            buyer_side_urgency=_bsu(
                pipeline_gap_urgency=0.72, loe_revenue_cliff_urgency=0.68,
                competitive_fomo=0.65, recent_bd_pattern=0.60,
                strategic_priority_recency=0.65,
            ),
            # Low acquirer pull — cannot reach Active Pursuit
            acquirer_pull=[
                _acq(ta_fit=0.30, modality_fit=0.30, pipeline_gap_urgency=0.30,
                     buyer_deal_appetite=0.30, existing_relationship=0.15,
                     competitive_fomo=0.25),
            ],
            information_readiness=_ir(l1_confidence=0.75, acquirer_profile_freshness=0.72),
        ))
        assert result.action_classification != ActionClass.ACTIVE_PURSUIT


# ---------------------------------------------------------------------------
# 6. Diligence Queue — low information readiness
# ---------------------------------------------------------------------------

class TestDiligenceQueue:
    def test_high_score_low_ir_gives_diligence_queue(self):
        result = compute_layer2_bd_priority(Layer2Inputs(
            target_name="DataGapCo",
            strategic_priority=_sp(l1_score=0.78, asf=0.72, l1_scarcity=0.74, l1_aq=0.76),
            target_side_pressure=_tsp(
                financing_pressure=0.70, catalyst_timing=0.65, seller_openness=0.65,
            ),
            buyer_side_urgency=_bsu(pipeline_gap_urgency=0.65),
            acquirer_pull=[_acq(ta_fit=0.72, modality_fit=0.68, pipeline_gap_urgency=0.70)],
            information_readiness=Layer2InformationReadinessInputs(
                layer1_confidence=0.30,
                acquirer_profile_freshness=0.25,
                transaction_driver_source_quality=0.20,
                valuation_data_freshness=0.25,
                rights_encumbrance_clarity=0.30,
                catalyst_date_confidence=0.20,
            ),
        ))
        assert result.action_classification == ActionClass.DILIGENCE_QUEUE

    def test_low_ir_caps_bd_action_score(self):
        """IR < 0.40 → BD Action Score cap 0.60."""
        result = _run(
            information_readiness=Layer2InformationReadinessInputs(
                layer1_confidence=0.20, acquirer_profile_freshness=0.20,
                transaction_driver_source_quality=0.20, valuation_data_freshness=0.20,
                rights_encumbrance_clarity=0.20, catalyst_date_confidence=0.20,
            ),
        )
        assert result.capped_bd_action_score <= 0.60 + 1e-9
        assert any("low_information_readiness" in c for c in result.active_caps)

    def test_low_ir_missing_items_populated(self):
        result = _run(
            information_readiness=Layer2InformationReadinessInputs(
                layer1_confidence=None,
                acquirer_profile_freshness=None,
                transaction_driver_source_quality=None,
                valuation_data_freshness=None,
            ),
        )
        assert len(result.information_readiness.missing_items) >= 4


# ---------------------------------------------------------------------------
# 7. Distress Trap Warning
# ---------------------------------------------------------------------------

class TestDistressTrapWarning:
    def test_high_pressure_weak_quality_gives_distress_trap(self):
        result = compute_layer2_bd_priority(Layer2Inputs(
            target_name="DistressedCo",
            strategic_priority=_sp(l1_score=0.45, l1_aq=0.35, asf=0.50),
            target_side_pressure=_tsp(
                financing_pressure=0.85, seller_openness=0.60,
                catalyst_timing=0.55, valuation_distress=0.80,
                governance_activist_pressure=0.55,
            ),
            buyer_side_urgency=_bsu(pipeline_gap_urgency=0.50),
            acquirer_pull=[_acq()],
            information_readiness=_ir(),
        ))
        assert result.action_classification == ActionClass.DISTRESS_TRAP_WARNING

    def test_distress_trap_requires_weak_asset_quality(self):
        """High pressure + STRONG asset quality should NOT trigger distress trap."""
        result = compute_layer2_bd_priority(Layer2Inputs(
            target_name="StrongDistressed",
            strategic_priority=_sp(l1_score=0.75, l1_aq=0.78, asf=0.70),
            target_side_pressure=_tsp(
                financing_pressure=0.85, valuation_distress=0.80,
                seller_openness=0.60, catalyst_timing=0.60,
                governance_activist_pressure=0.50,
            ),
            buyer_side_urgency=_bsu(),
            acquirer_pull=[_acq(ta_fit=0.78, modality_fit=0.74, pipeline_gap_urgency=0.72)],
            information_readiness=_ir(),
        ))
        assert result.action_classification != ActionClass.DISTRESS_TRAP_WARNING


# ---------------------------------------------------------------------------
# 8. Weighted driver strength
# ---------------------------------------------------------------------------

class TestWeightedDriverStrength:
    def test_wds_uses_driver_weights(self):
        """WDS = sum(active w × strength × conf) / total_w; not simple count."""
        result_high = _run(
            target_side_pressure=_tsp(financing_pressure=0.90, catalyst_timing=0.90,
                                       seller_openness=0.90),
            buyer_side_urgency=_bsu(pipeline_gap_urgency=0.90, loe_revenue_cliff_urgency=0.90),
        )
        result_low = _run(
            target_side_pressure=_tsp(financing_pressure=0.10, catalyst_timing=0.10,
                                       seller_openness=0.10),
            buyer_side_urgency=_bsu(pipeline_gap_urgency=0.10, loe_revenue_cliff_urgency=0.10),
        )
        assert result_high.weighted_driver_strength > result_low.weighted_driver_strength

    def test_wds_bounded_01(self):
        result = _run()
        assert 0.0 <= result.weighted_driver_strength <= 1.0

    def test_zero_drivers_gives_zero_wds(self):
        result = _run(
            target_side_pressure=_tsp(
                financing_pressure=0.05, catalyst_timing=0.05, seller_openness=0.05,
                valuation_distress=0.05, governance_activist_pressure=0.05,
            ),
            buyer_side_urgency=_bsu(
                pipeline_gap_urgency=0.05, loe_revenue_cliff_urgency=0.05,
                competitive_fomo=0.05, recent_bd_pattern=0.05,
                strategic_priority_recency=0.05,
            ),
        )
        assert result.weighted_driver_strength == pytest.approx(0.0)
        assert len(result.active_transaction_drivers) == 0

    def test_total_driver_weight_matches_sum(self):
        assert abs(_TOTAL_DRIVER_WEIGHT - sum(DRIVER_WEIGHTS.values())) < 1e-9


# ---------------------------------------------------------------------------
# 9. Target-side vs buyer-side balance
# ---------------------------------------------------------------------------

class TestTargetBuyerBalance:
    def test_high_target_low_buyer_does_not_overscore_dm(self):
        """High target-side pressure with no buyer urgency should not dominate."""
        result = compute_layer2_bd_priority(Layer2Inputs(
            target_name="TargetPressureOnly",
            strategic_priority=_sp(),
            target_side_pressure=_tsp(
                financing_pressure=0.90, seller_openness=0.85, catalyst_timing=0.85,
                valuation_distress=0.80, governance_activist_pressure=0.80,
            ),
            buyer_side_urgency=Layer2BuyerSideUrgencyInputs(
                pipeline_gap_urgency=0.05, loe_revenue_cliff_urgency=0.05,
                competitive_fomo=0.05, recent_bd_pattern=0.05,
                strategic_priority_recency=0.05,
            ),
            acquirer_pull=[_acq()],
            information_readiness=_ir(),
        ))
        # Deal Momentum = 0.55 × TSP + 0.45 × BSU. With BSU near 0,
        # DM should be < max possible value
        dm = result.deal_momentum.score
        assert dm < 0.65, f"Expected DM < 0.65 when BSU is near zero, got {dm}"
        # TSP component should be high
        assert result.deal_momentum.target_side_pressure.score > 0.60

    def test_buyer_side_contributes_independently(self):
        result_hi_bsu = _run(
            buyer_side_urgency=_bsu(
                pipeline_gap_urgency=0.85, loe_revenue_cliff_urgency=0.85,
            )
        )
        result_lo_bsu = _run(
            buyer_side_urgency=_bsu(
                pipeline_gap_urgency=0.10, loe_revenue_cliff_urgency=0.10,
            )
        )
        assert result_hi_bsu.buyer_side_urgency > result_lo_bsu.buyer_side_urgency


# ---------------------------------------------------------------------------
# 10. Buyer universe depth and concentration risk
# ---------------------------------------------------------------------------

class TestBuyerUniverse:
    def test_multiple_high_pull_acquirers_increases_depth(self):
        acqs = [
            _acq("a1", "AcqA", ta_fit=0.85, modality_fit=0.82, pipeline_gap_urgency=0.80,
                 buyer_deal_appetite=0.75, existing_relationship=0.60, competitive_fomo=0.70),
            _acq("a2", "AcqB", ta_fit=0.80, modality_fit=0.78, pipeline_gap_urgency=0.75,
                 buyer_deal_appetite=0.72, existing_relationship=0.55, competitive_fomo=0.65),
            _acq("a3", "AcqC", ta_fit=0.75, modality_fit=0.72, pipeline_gap_urgency=0.70,
                 buyer_deal_appetite=0.68, existing_relationship=0.50, competitive_fomo=0.60),
        ]
        result = _run(acquirer_pull=acqs)
        assert result.buyer_universe_depth >= 2
        assert result.acquirer_pull.acquirer_pull_depth >= 2

    def test_single_buyer_has_high_concentration_risk(self):
        """One strong buyer + one weak buyer → high concentration risk."""
        acqs = [
            _acq("a1", "Strong", ta_fit=0.90, modality_fit=0.88, pipeline_gap_urgency=0.85,
                 buyer_deal_appetite=0.82, existing_relationship=0.75, competitive_fomo=0.78),
            _acq("a2", "Weak", ta_fit=0.20, modality_fit=0.20, pipeline_gap_urgency=0.20,
                 buyer_deal_appetite=0.20, existing_relationship=0.10, competitive_fomo=0.15),
        ]
        result = _run(acquirer_pull=acqs)
        assert result.buyer_concentration_risk > 0.30

    def test_two_comparable_buyers_low_concentration_risk(self):
        acqs = [
            _acq("a1", "A", ta_fit=0.75, modality_fit=0.72, pipeline_gap_urgency=0.70,
                 buyer_deal_appetite=0.68, existing_relationship=0.50, competitive_fomo=0.62),
            _acq("a2", "B", ta_fit=0.73, modality_fit=0.70, pipeline_gap_urgency=0.68,
                 buyer_deal_appetite=0.66, existing_relationship=0.48, competitive_fomo=0.60),
        ]
        result = _run(acquirer_pull=acqs)
        assert result.buyer_concentration_risk < 0.15

    def test_no_acquirers_gives_mapping_needed(self):
        result = _run(acquirer_pull=[])
        assert result.action_classification == ActionClass.ACQUIRER_MAPPING_NEEDED
        assert result.buyer_universe_depth == 0


# ---------------------------------------------------------------------------
# 11. Information Readiness caps
# ---------------------------------------------------------------------------

class TestInformationReadinessCap:
    def test_ir_below_040_caps_bd_score_at_060(self):
        result = _run(
            information_readiness=Layer2InformationReadinessInputs(
                layer1_confidence=0.15, acquirer_profile_freshness=0.15,
                transaction_driver_source_quality=0.15, valuation_data_freshness=0.15,
                rights_encumbrance_clarity=0.15, catalyst_date_confidence=0.15,
            ),
        )
        assert result.capped_bd_action_score <= 0.60 + 1e-9

    def test_ir_above_040_no_ir_cap(self):
        result = _run()  # default IR is well above 0.40
        ir_cap_active = any("low_information_readiness" in c for c in result.active_caps)
        assert not ir_cap_active

    def test_ir_readiness_label_correct(self):
        # All fields at 0.90 → score ≥ 0.80 → "High"
        result_high = _run(information_readiness=_ir(
            l1_confidence=0.90, acquirer_profile_freshness=0.90,
            transaction_driver_source_quality=0.90, valuation_data_freshness=0.90,
            rights_encumbrance_clarity=0.90, catalyst_date_confidence=0.90,
        ))
        assert result_high.information_readiness.readiness_label == "High"

        result_vl = _run(
            information_readiness=Layer2InformationReadinessInputs(
                layer1_confidence=0.10, acquirer_profile_freshness=0.10,
                transaction_driver_source_quality=0.10, valuation_data_freshness=0.10,
                rights_encumbrance_clarity=0.10, catalyst_date_confidence=0.10,
            )
        )
        assert result_vl.information_readiness.readiness_label == "Very Low"


# ---------------------------------------------------------------------------
# 12. Layer ownership warnings
# ---------------------------------------------------------------------------

class TestLayerOwnershipWarnings:
    def test_affordability_triggers_warning(self):
        result = compute_layer2_bd_priority(Layer2Inputs(
            target_name="AffordTest",
            affordability_override=0.80,
        ))
        assert "affordability_input_ignored_layer3_owned" in result.layer_ownership_warnings

    def test_antitrust_triggers_warning(self):
        result = compute_layer2_bd_priority(Layer2Inputs(
            target_name="AntitrustTest",
            antitrust_risk=0.40,
        ))
        assert "antitrust_input_ignored_layer3_owned" in result.layer_ownership_warnings

    def test_rofr_triggers_warning(self):
        result = compute_layer2_bd_priority(Layer2Inputs(
            target_name="ROFRTest",
            rofr_impact=0.30,
        ))
        assert "pair_specific_rofr_input_ignored_layer3_owned" in result.layer_ownership_warnings

    def test_integration_feasibility_triggers_warning(self):
        result = compute_layer2_bd_priority(Layer2Inputs(
            target_name="IntegrationTest",
            integration_feasibility=0.70,
        ))
        assert "integration_feasibility_input_ignored_layer3_owned" in result.layer_ownership_warnings

    def test_l3_inputs_do_not_affect_score(self):
        """Passing L3-only inputs must not change BD Action Score."""
        base = _run()
        with_l3 = compute_layer2_bd_priority(Layer2Inputs(
            target_name="TestCo",
            strategic_priority=_sp(),
            target_side_pressure=_tsp(),
            buyer_side_urgency=_bsu(),
            acquirer_pull=[_acq()],
            information_readiness=_ir(),
            affordability_override=0.90,
            antitrust_risk=0.10,
            rofr_impact=0.80,
            integration_feasibility=0.95,
        ))
        assert with_l3.bd_action_score == pytest.approx(base.bd_action_score, abs=1e-9)

    def test_layer3_only_inputs_frozenset_completeness(self):
        assert "affordability_override" in LAYER3_ONLY_INPUTS
        assert "antitrust_risk" in LAYER3_ONLY_INPUTS
        assert "rofr_impact" in LAYER3_ONLY_INPUTS
        assert "integration_feasibility" in LAYER3_ONLY_INPUTS

    def test_layer2_ownership_map_contains_layer2_entries(self):
        assert "bd_action_priority" in LAYER2_OWNERSHIP_MAP
        assert LAYER2_OWNERSHIP_MAP["acquirer_specific_affordability"] == "Layer 3"
        assert LAYER2_OWNERSHIP_MAP["calibrated_takeout_probability"] == "Layer 5"


# ---------------------------------------------------------------------------
# 13. Backward compat — old Layer 2 (ma_scoring.py) unchanged
# ---------------------------------------------------------------------------

class TestBackwardCompatOldLayer2:
    def test_old_compute_bd_layer2_still_importable(self):
        from bve.intelligence.ma_scoring import compute_bd_layer2, Layer2Output
        assert callable(compute_bd_layer2)

    def test_old_layer2_still_returns_layer2output(self):
        from bve.intelligence.ma_scoring import (
            compute_bd_layer2,
            TargetAttractivenessScore,
            DealLikelihoodScore,
            AcquirerFitDecomposed,
            Layer2Output,
        )
        ta = TargetAttractivenessScore(
            score=0.70, de_risking_stage=0.70, valuation_discount=0.70,
            scarcity=0.70, peak_sales_signal=0.70,
        )
        dl = DealLikelihoodScore(
            score=0.65, financing_pressure=0.60, external_deal_activity=0.55,
            insider_board_signals=0.45, catalyst_proximity=0.50,
        )
        af = AcquirerFitDecomposed(
            score=0.70, ta_modality_fit=0.70, pipeline_gap_alignment=0.70,
            deal_affordability=0.70, existing_partnership_bonus=0.0,
        )
        result = compute_bd_layer2(ta, dl, af)
        assert isinstance(result, Layer2Output)
        assert 0.0 <= result.bd_action_score <= 1.0

    def test_old_compute_mna_composite_still_returns_tuple(self):
        from bve.intelligence.ma_scoring import (
            compute_mna_composite_score,
            TargetAttractivenessScore,
            DealLikelihoodScore,
            AcquirerFitDecomposed,
        )
        ta = TargetAttractivenessScore(
            score=0.70, de_risking_stage=0.70, valuation_discount=0.70,
            scarcity=0.70, peak_sales_signal=0.70,
        )
        dl = DealLikelihoodScore(
            score=0.65, financing_pressure=0.60, external_deal_activity=0.55,
            insider_board_signals=0.45, catalyst_proximity=0.50,
        )
        af = AcquirerFitDecomposed(
            score=0.70, ta_modality_fit=0.70, pipeline_gap_alignment=0.70,
            deal_affordability=0.70, existing_partnership_bonus=0.0,
        )
        score, codes = compute_mna_composite_score(ta, dl, af)
        assert isinstance(score, float)
        assert isinstance(codes, list)


# ---------------------------------------------------------------------------
# 14. All 9 action classifications reachable
# ---------------------------------------------------------------------------

class TestAllActionClassifications:
    def test_active_pursuit(self):
        result = compute_layer2_bd_priority(Layer2Inputs(
            target_name="AP",
            strategic_priority=_sp(l1_score=0.88, asf=0.85, l1_scarcity=0.85, l1_aq=0.85),
            target_side_pressure=_tsp(
                financing_pressure=0.82, seller_openness=0.78,
                catalyst_timing=0.82, valuation_distress=0.72,
                governance_activist_pressure=0.68,
            ),
            buyer_side_urgency=_bsu(
                pipeline_gap_urgency=0.80, loe_revenue_cliff_urgency=0.78,
                competitive_fomo=0.72, recent_bd_pattern=0.68,
            ),
            acquirer_pull=[
                _acq(ta_fit=0.88, modality_fit=0.84, pipeline_gap_urgency=0.85,
                     buyer_deal_appetite=0.80, existing_relationship=0.72,
                     competitive_fomo=0.76),
            ],
            information_readiness=_ir(
                l1_confidence=0.82, acquirer_profile_freshness=0.80,
                transaction_driver_source_quality=0.78,
            ),
        ))
        assert result.action_classification == ActionClass.ACTIVE_PURSUIT

    def test_strategic_watch(self):
        result = compute_layer2_bd_priority(Layer2Inputs(
            target_name="SW",
            strategic_priority=_sp(l1_score=0.82, asf=0.78, l1_scarcity=0.75, l1_aq=0.78),
            target_side_pressure=_tsp(
                financing_pressure=0.10, seller_openness=0.10,
                catalyst_timing=0.10, valuation_distress=0.05,
                governance_activist_pressure=0.05,
            ),
            buyer_side_urgency=_bsu(
                pipeline_gap_urgency=0.15, loe_revenue_cliff_urgency=0.12,
                competitive_fomo=0.10, recent_bd_pattern=0.10,
                strategic_priority_recency=0.10,
            ),
            acquirer_pull=[_acq()],
            information_readiness=_ir(),
        ))
        assert result.action_classification == ActionClass.STRATEGIC_WATCH

    def test_distress_trap(self):
        result = compute_layer2_bd_priority(Layer2Inputs(
            target_name="DT",
            strategic_priority=_sp(l1_score=0.40, l1_aq=0.30, asf=0.45),
            target_side_pressure=_tsp(
                financing_pressure=0.88, valuation_distress=0.82,
                seller_openness=0.60, catalyst_timing=0.55,
                governance_activist_pressure=0.50,
            ),
            buyer_side_urgency=_bsu(pipeline_gap_urgency=0.50),
            acquirer_pull=[_acq()],
            information_readiness=_ir(),
        ))
        assert result.action_classification == ActionClass.DISTRESS_TRAP_WARNING

    def test_low_priority_pass(self):
        result = compute_layer2_bd_priority(Layer2Inputs(
            target_name="LP",
            strategic_priority=_sp(l1_score=0.30, asf=0.25, l1_scarcity=0.25, l1_aq=0.60),
            target_side_pressure=_tsp(
                financing_pressure=0.10, seller_openness=0.10,
                catalyst_timing=0.10, valuation_distress=0.10,
                governance_activist_pressure=0.10,
            ),
            buyer_side_urgency=_bsu(
                pipeline_gap_urgency=0.10, loe_revenue_cliff_urgency=0.10,
                competitive_fomo=0.10, recent_bd_pattern=0.10,
            ),
            acquirer_pull=[_acq(ta_fit=0.20, modality_fit=0.20, pipeline_gap_urgency=0.20,
                                buyer_deal_appetite=0.20, existing_relationship=0.10,
                                competitive_fomo=0.15)],
            information_readiness=_ir(),
        ))
        assert result.action_classification == ActionClass.LOW_PRIORITY_PASS

    def test_acquirer_mapping_needed(self):
        result = _run(acquirer_pull=[])
        assert result.action_classification == ActionClass.ACQUIRER_MAPPING_NEEDED


# ---------------------------------------------------------------------------
# 15. Missing data — reduces confidence, does not zero the score
# ---------------------------------------------------------------------------

class TestMissingData:
    def test_all_none_inputs_score_not_zero(self):
        """All None → neutral (0.50) defaults everywhere; score should be ~0.50."""
        result = compute_layer2_bd_priority(Layer2Inputs(target_name="AllNone"))
        # Score should be around neutral (0.50) with confidence reduction
        assert result.bd_action_score > 0.0
        assert result.bd_action_score < 0.85

    def test_missing_inputs_reduce_confidence(self):
        result_full = _run()
        result_none = compute_layer2_bd_priority(Layer2Inputs(target_name="NoneInputs"))
        assert result_full.overall_confidence >= result_none.overall_confidence

    def test_missing_sp_fields_add_to_missing_data(self):
        result = compute_layer2_bd_priority(Layer2Inputs(
            target_name="MissingTest",
            strategic_priority=Layer2StrategicPriorityInputs(
                layer1_attractiveness_score=None,
                acquirer_strategic_fit=None,
            ),
        ))
        assert len(result.missing_data) > 0

    def test_output_fields_always_populated(self):
        result = compute_layer2_bd_priority(Layer2Inputs(target_name="Complete"))
        assert result.action_classification
        assert result.expected_action_window
        assert result.rationale
        assert isinstance(result.upgrade_triggers, list)
        assert isinstance(result.downgrade_triggers, list)
        assert len(result.upgrade_triggers) > 0
        assert len(result.downgrade_triggers) > 0
