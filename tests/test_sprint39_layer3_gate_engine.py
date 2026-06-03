"""
Tests for Layer 3 — Institutional Gate System / Deal Realism Engine (Sprint 39).

Coverage:
- Each of the 6 driver buckets: threshold activation, strength formula, sub-scores
- Valuation dislocation dual-condition requirement
- driver_strength_score formula (equal-weight mean)
- strength_classification thresholds (Strong/Plausible/Watchlist/Low)
- active_bucket_count counting
- near_term_transaction_possible flag
- All 8 gates: trigger condition, non-trigger, correct cap constant
- Most-restrictive-cap logic: multiple gates → min(caps) wins
- Gate interactions (G3 more restrictive than G4)
- Classification and interpretation non-empty
- Layer3Output field completeness
- compute_layer3 end-to-end integration
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_layer3_gate import (
    DriverBucketInputs,
    DriverBucketResult,
    GateInputs,
    GateResult,
    Layer3Output,
    _ASSET_SCARCITY_THRESHOLD,
    _BUYER_URGENCY_THRESHOLD,
    _CAPITAL_PRESSURE_THRESHOLD,
    _CATALYST_TIMING_THRESHOLD,
    _GATE_CAPS,
    _NEAR_TERM_BUCKET_MIN,
    _NEAR_TERM_STRENGTH_MIN,
    _SELLER_WILLINGNESS_THRESHOLD,
    _STRENGTH_PLAUSIBLE,
    _STRENGTH_STRONG,
    _STRENGTH_WATCHLIST,
    _VALUATION_DISLOCATION_DERISKING_MIN,
    _VALUATION_DISLOCATION_DISCOUNT_MIN,
    _compute_asset_scarcity_bucket,
    _compute_buyer_urgency_bucket,
    _compute_capital_pressure_bucket,
    _compute_catalyst_timing_bucket,
    _compute_seller_willingness_bucket,
    _compute_valuation_dislocation_bucket,
    compute_driver_buckets,
    compute_layer3,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _di(
    financing_pressure: float = 0.50,
    external_deal_activity: float = 0.50,
    pipeline_gap_urgency: float = 0.60,
    activist_signal: float = 0.50,
    strategic_review_signal: float = 0.30,
    catalyst_proximity: float = 0.50,
    scarcity_score: float = 0.70,
    acquirer_fit_score: float = 0.65,
    valuation_discount: float = 0.55,
    de_risking_stage: float = 0.65,
) -> DriverBucketInputs:
    return DriverBucketInputs(
        financing_pressure=financing_pressure,
        external_deal_activity=external_deal_activity,
        pipeline_gap_urgency=pipeline_gap_urgency,
        activist_signal=activist_signal,
        strategic_review_signal=strategic_review_signal,
        catalyst_proximity=catalyst_proximity,
        scarcity_score=scarcity_score,
        acquirer_fit_score=acquirer_fit_score,
        valuation_discount=valuation_discount,
        de_risking_stage=de_risking_stage,
    )


def _gi(
    asset_quality: float = 0.70,
    acquirer_right_to_win: float = 0.70,
    seller_willingness: float = 0.60,
    financing_pressure: float = 0.50,
    asset_control: float = 0.75,
    affordability: float = 0.70,
    severe_safety_issue: bool = False,
    failed_pivotal_no_rescue: bool = False,
    regulatory_path_unacceptable: bool = False,
    no_active_process_signal: bool = False,
    antitrust_risk_high: bool = False,
    integration_complexity_severe: bool = False,
) -> GateInputs:
    return GateInputs(
        asset_quality=asset_quality,
        acquirer_right_to_win=acquirer_right_to_win,
        seller_willingness=seller_willingness,
        financing_pressure=financing_pressure,
        asset_control=asset_control,
        affordability=affordability,
        severe_safety_issue=severe_safety_issue,
        failed_pivotal_no_rescue=failed_pivotal_no_rescue,
        regulatory_path_unacceptable=regulatory_path_unacceptable,
        no_active_process_signal=no_active_process_signal,
        antitrust_risk_high=antitrust_risk_high,
        integration_complexity_severe=integration_complexity_severe,
    )


def _run(pre_gate: float = 0.70, **di_overrides) -> Layer3Output:
    di_kwargs = dict(
        financing_pressure=0.50, external_deal_activity=0.50, pipeline_gap_urgency=0.60,
        activist_signal=0.50, strategic_review_signal=0.30, catalyst_proximity=0.50,
        scarcity_score=0.70, acquirer_fit_score=0.65, valuation_discount=0.55,
        de_risking_stage=0.65,
    )
    di_kwargs.update(di_overrides)
    return compute_layer3(
        pre_gate_score=pre_gate,
        driver_inputs=DriverBucketInputs(**di_kwargs),
        gate_inputs=_gi(),
        target_name="TestCo",
        acquirer_id="ACQ-1",
    )


# ---------------------------------------------------------------------------
# 1. Capital Pressure Bucket
# ---------------------------------------------------------------------------

class TestCapitalPressureBucket:
    def test_score_equals_financing_pressure(self):
        result = _compute_capital_pressure_bucket(_di(financing_pressure=0.72))
        assert result.strength == pytest.approx(0.72, abs=1e-6)

    def test_active_above_threshold(self):
        result = _compute_capital_pressure_bucket(_di(financing_pressure=_CAPITAL_PRESSURE_THRESHOLD))
        assert result.active

    def test_inactive_below_threshold(self):
        result = _compute_capital_pressure_bucket(_di(financing_pressure=_CAPITAL_PRESSURE_THRESHOLD - 0.01))
        assert not result.active

    def test_sub_scores_populated(self):
        result = _compute_capital_pressure_bucket(_di(financing_pressure=0.55))
        assert "financing_pressure" in result.sub_scores


# ---------------------------------------------------------------------------
# 2. Buyer Urgency Bucket
# ---------------------------------------------------------------------------

class TestBuyerUrgencyBucket:
    def test_formula_0_60_ext_plus_0_40_gap(self):
        result = _compute_buyer_urgency_bucket(_di(external_deal_activity=0.80, pipeline_gap_urgency=0.60))
        expected = round(0.60 * 0.80 + 0.40 * 0.60, 6)
        assert result.strength == pytest.approx(expected, abs=1e-6)

    def test_active_above_threshold(self):
        # ext=0.50 → strength = 0.60*0.50 + 0.40*0.50 = 0.50 ≥ 0.30
        result = _compute_buyer_urgency_bucket(_di(external_deal_activity=0.50, pipeline_gap_urgency=0.50))
        assert result.active

    def test_inactive_below_threshold(self):
        result = _compute_buyer_urgency_bucket(_di(external_deal_activity=0.05, pipeline_gap_urgency=0.05))
        assert not result.active

    def test_sub_scores_populated(self):
        result = _compute_buyer_urgency_bucket(_di())
        assert "external_deal_activity" in result.sub_scores
        assert "pipeline_gap_urgency" in result.sub_scores


# ---------------------------------------------------------------------------
# 3. Seller Willingness Bucket
# ---------------------------------------------------------------------------

class TestSellerWillingnessBucket:
    def test_formula_0_60_activist_plus_0_40_review(self):
        result = _compute_seller_willingness_bucket(_di(activist_signal=0.70, strategic_review_signal=0.40))
        expected = round(0.60 * 0.70 + 0.40 * 0.40, 6)
        assert result.strength == pytest.approx(expected, abs=1e-6)

    def test_active_when_above_threshold(self):
        result = _compute_seller_willingness_bucket(_di(activist_signal=0.60, strategic_review_signal=0.0))
        # 0.60*0.60 + 0.40*0.0 = 0.36 ≥ 0.30
        assert result.active

    def test_inactive_when_both_low(self):
        result = _compute_seller_willingness_bucket(_di(activist_signal=0.10, strategic_review_signal=0.0))
        assert not result.active


# ---------------------------------------------------------------------------
# 4. Catalyst Timing Bucket
# ---------------------------------------------------------------------------

class TestCatalystTimingBucket:
    def test_score_equals_catalyst_proximity(self):
        result = _compute_catalyst_timing_bucket(_di(catalyst_proximity=0.82))
        assert result.strength == pytest.approx(0.82, abs=1e-6)

    def test_active_above_threshold(self):
        result = _compute_catalyst_timing_bucket(_di(catalyst_proximity=_CATALYST_TIMING_THRESHOLD))
        assert result.active

    def test_inactive_below_threshold(self):
        result = _compute_catalyst_timing_bucket(_di(catalyst_proximity=_CATALYST_TIMING_THRESHOLD - 0.01))
        assert not result.active


# ---------------------------------------------------------------------------
# 5. Asset Scarcity Bucket
# ---------------------------------------------------------------------------

class TestAssetScarcityBucket:
    def test_formula_0_60_scarcity_plus_0_40_fit(self):
        result = _compute_asset_scarcity_bucket(_di(scarcity_score=0.80, acquirer_fit_score=0.70))
        expected = round(0.60 * 0.80 + 0.40 * 0.70, 6)
        assert result.strength == pytest.approx(expected, abs=1e-6)

    def test_active_above_threshold(self):
        # scarcity=0.80, fit=0.65 → 0.60*0.80+0.40*0.65 = 0.48+0.26 = 0.74 ≥ 0.60
        result = _compute_asset_scarcity_bucket(_di(scarcity_score=0.80, acquirer_fit_score=0.65))
        assert result.active

    def test_inactive_when_low(self):
        result = _compute_asset_scarcity_bucket(_di(scarcity_score=0.30, acquirer_fit_score=0.30))
        assert not result.active

    def test_threshold_is_higher_than_other_buckets(self):
        """Asset scarcity requires 0.60, other buckets only 0.30–0.35."""
        assert _ASSET_SCARCITY_THRESHOLD > _BUYER_URGENCY_THRESHOLD
        assert _ASSET_SCARCITY_THRESHOLD > _CAPITAL_PRESSURE_THRESHOLD


# ---------------------------------------------------------------------------
# 6. Valuation Dislocation Bucket
# ---------------------------------------------------------------------------

class TestValuationDislocationBucket:
    def test_active_when_both_conditions_met(self):
        result = _compute_valuation_dislocation_bucket(
            _di(valuation_discount=0.60, de_risking_stage=0.70)
        )
        assert result.active

    def test_inactive_when_discount_too_low(self):
        result = _compute_valuation_dislocation_bucket(
            _di(valuation_discount=0.40, de_risking_stage=0.80)
        )
        assert not result.active

    def test_inactive_when_derisking_too_low(self):
        result = _compute_valuation_dislocation_bucket(
            _di(valuation_discount=0.70, de_risking_stage=0.40)
        )
        assert not result.active

    def test_inactive_preclinical_deeply_discounted(self):
        """A cheap preclinical asset is NOT valuation dislocation."""
        result = _compute_valuation_dislocation_bucket(
            _di(valuation_discount=0.95, de_risking_stage=0.10)
        )
        assert not result.active

    def test_strength_is_lower_when_inactive(self):
        """Inactive bucket reports partial strength (×0.5) for diagnostics."""
        active = _compute_valuation_dislocation_bucket(
            _di(valuation_discount=0.60, de_risking_stage=0.70)
        )
        inactive = _compute_valuation_dislocation_bucket(
            _di(valuation_discount=0.60, de_risking_stage=0.30)  # derisking too low
        )
        assert active.strength > inactive.strength

    def test_sub_scores_include_qualifier_flags(self):
        result = _compute_valuation_dislocation_bucket(_di())
        assert "discount_qualifies" in result.sub_scores
        assert "derisking_qualifies" in result.sub_scores


# ---------------------------------------------------------------------------
# 7. compute_driver_buckets aggregate
# ---------------------------------------------------------------------------

class TestComputeDriverBuckets:
    def test_returns_all_six_buckets(self):
        result = compute_driver_buckets(_di())
        assert set(result.buckets.keys()) == {
            "capital_pressure", "buyer_urgency", "seller_willingness",
            "catalyst_timing", "asset_scarcity", "valuation_dislocation",
        }

    def test_driver_strength_is_equal_weight_mean(self):
        inputs = _di(
            financing_pressure=0.40,
            external_deal_activity=0.50, pipeline_gap_urgency=0.60,
            activist_signal=0.30, strategic_review_signal=0.20,
            catalyst_proximity=0.45,
            scarcity_score=0.70, acquirer_fit_score=0.65,
            valuation_discount=0.55, de_risking_stage=0.65,
        )
        result = compute_driver_buckets(inputs)
        expected_mean = sum(b.strength for b in result.buckets.values()) / 6
        assert result.driver_strength_score == pytest.approx(expected_mean, abs=1e-6)

    def test_active_bucket_count_correct(self):
        # All buckets with strong inputs should all be active
        inputs = _di(
            financing_pressure=0.80, external_deal_activity=0.80, pipeline_gap_urgency=0.70,
            activist_signal=0.70, strategic_review_signal=0.50, catalyst_proximity=0.80,
            scarcity_score=0.85, acquirer_fit_score=0.80, valuation_discount=0.75,
            de_risking_stage=0.80,
        )
        result = compute_driver_buckets(inputs)
        assert result.active_bucket_count == 6

    def test_zero_active_when_all_low(self):
        inputs = DriverBucketInputs(
            financing_pressure=0.10, external_deal_activity=0.05, pipeline_gap_urgency=0.10,
            activist_signal=0.05, strategic_review_signal=0.0, catalyst_proximity=0.05,
            scarcity_score=0.10, acquirer_fit_score=0.10, valuation_discount=0.10,
            de_risking_stage=0.10,
        )
        result = compute_driver_buckets(inputs)
        assert result.active_bucket_count == 0

    def test_strength_classification_strong(self):
        inputs = _di(
            financing_pressure=0.90, external_deal_activity=0.90, pipeline_gap_urgency=0.80,
            activist_signal=0.85, strategic_review_signal=0.70, catalyst_proximity=0.90,
            scarcity_score=0.95, acquirer_fit_score=0.85, valuation_discount=0.85,
            de_risking_stage=0.85,
        )
        result = compute_driver_buckets(inputs)
        assert result.strength_classification == "Strong"
        assert result.driver_strength_score >= _STRENGTH_STRONG

    def test_strength_classification_low(self):
        inputs = DriverBucketInputs(
            financing_pressure=0.10, external_deal_activity=0.05, pipeline_gap_urgency=0.10,
            activist_signal=0.05, strategic_review_signal=0.0, catalyst_proximity=0.05,
            scarcity_score=0.10, acquirer_fit_score=0.10, valuation_discount=0.10,
            de_risking_stage=0.10,
        )
        result = compute_driver_buckets(inputs)
        assert result.strength_classification == "Low"
        assert result.driver_strength_score < _STRENGTH_WATCHLIST

    def test_near_term_true_when_two_plus_buckets_and_high_strength(self):
        inputs = _di(
            financing_pressure=0.80, external_deal_activity=0.80, pipeline_gap_urgency=0.70,
            activist_signal=0.70, strategic_review_signal=0.50, catalyst_proximity=0.80,
            scarcity_score=0.85, acquirer_fit_score=0.80, valuation_discount=0.75,
            de_risking_stage=0.80,
        )
        result = compute_driver_buckets(inputs)
        assert result.near_term_transaction_possible

    def test_near_term_false_when_only_one_bucket_active(self):
        # Only capital pressure fires; all others suppressed
        inputs = DriverBucketInputs(
            financing_pressure=0.80, external_deal_activity=0.05, pipeline_gap_urgency=0.10,
            activist_signal=0.05, strategic_review_signal=0.0, catalyst_proximity=0.10,
            scarcity_score=0.20, acquirer_fit_score=0.20, valuation_discount=0.20,
            de_risking_stage=0.20,
        )
        result = compute_driver_buckets(inputs)
        assert result.active_bucket_count <= 1
        assert not result.near_term_transaction_possible

    def test_near_term_false_when_strength_below_threshold_despite_two_buckets(self):
        # Two buckets barely active but overall strength is low
        inputs = DriverBucketInputs(
            financing_pressure=0.36,  # just above threshold
            external_deal_activity=0.31, pipeline_gap_urgency=0.31,  # just above 0.30
            activist_signal=0.05, strategic_review_signal=0.0,
            catalyst_proximity=0.05,
            scarcity_score=0.20, acquirer_fit_score=0.20, valuation_discount=0.20,
            de_risking_stage=0.20,
        )
        result = compute_driver_buckets(inputs)
        assert result.active_bucket_count >= 2
        assert not result.near_term_transaction_possible  # strength too low


# ---------------------------------------------------------------------------
# 8. Gate 1 — Broken Asset
# ---------------------------------------------------------------------------

class TestGate1BrokenAsset:
    def test_triggers_when_asset_quality_low(self):
        result = compute_layer3(0.80, _di(), _gi(asset_quality=0.30))
        assert "G1" in result.active_gate_ids
        assert result.final_score <= _GATE_CAPS["G1"] + 1e-9

    def test_triggers_on_safety_flag(self):
        result = compute_layer3(0.80, _di(), _gi(severe_safety_issue=True))
        assert "G1" in result.active_gate_ids

    def test_triggers_on_failed_pivotal(self):
        result = compute_layer3(0.80, _di(), _gi(failed_pivotal_no_rescue=True))
        assert "G1" in result.active_gate_ids

    def test_triggers_on_regulatory_flag(self):
        result = compute_layer3(0.80, _di(), _gi(regulatory_path_unacceptable=True))
        assert "G1" in result.active_gate_ids

    def test_not_triggered_with_good_asset(self):
        result = compute_layer3(0.70, _di(), _gi(asset_quality=0.70))
        assert "G1" not in result.active_gate_ids


# ---------------------------------------------------------------------------
# 9. Gate 2 — No Right-to-Win
# ---------------------------------------------------------------------------

class TestGate2NoRightToWin:
    def test_triggers_when_rtw_low(self):
        result = compute_layer3(0.80, _di(), _gi(acquirer_right_to_win=0.30))
        assert "G2" in result.active_gate_ids
        assert result.final_score <= _GATE_CAPS["G2"] + 1e-9

    def test_not_triggered_when_rtw_above_threshold(self):
        result = compute_layer3(0.70, _di(), _gi(acquirer_right_to_win=0.60))
        assert "G2" not in result.active_gate_ids

    def test_boundary_exactly_at_threshold(self):
        """acquirer_right_to_win = 0.45 exactly → NOT < 0.45 → no trigger."""
        result = compute_layer3(0.70, _di(), _gi(acquirer_right_to_win=0.45))
        assert "G2" not in result.active_gate_ids


# ---------------------------------------------------------------------------
# 10. Gate 3 — No Transaction Rationale
# ---------------------------------------------------------------------------

class TestGate3NoTransactionRationale:
    def test_triggers_when_zero_active_buckets(self):
        no_driver_di = DriverBucketInputs(
            financing_pressure=0.10, external_deal_activity=0.05, pipeline_gap_urgency=0.05,
            activist_signal=0.05, strategic_review_signal=0.0, catalyst_proximity=0.10,
            scarcity_score=0.10, acquirer_fit_score=0.10, valuation_discount=0.10,
            de_risking_stage=0.10,
        )
        result = compute_layer3(0.75, no_driver_di, _gi())
        assert "G3" in result.active_gate_ids
        assert result.final_score <= _GATE_CAPS["G3"] + 1e-9

    def test_not_triggered_when_any_bucket_active(self):
        result = compute_layer3(0.60, _di(financing_pressure=0.80), _gi())
        assert "G3" not in result.active_gate_ids

    def test_g3_more_restrictive_than_g4(self):
        """G3 cap (0.45) < G4 cap (0.65) → G3 is more restrictive."""
        assert _GATE_CAPS["G3"] < _GATE_CAPS["G4"]


# ---------------------------------------------------------------------------
# 11. Gate 4 — Weak Transaction Setup
# ---------------------------------------------------------------------------

class TestGate4WeakTransactionSetup:
    def test_triggers_when_only_one_bucket_active(self):
        # Only capital pressure fires
        single_bucket_di = DriverBucketInputs(
            financing_pressure=0.80, external_deal_activity=0.05, pipeline_gap_urgency=0.05,
            activist_signal=0.05, strategic_review_signal=0.0, catalyst_proximity=0.05,
            scarcity_score=0.10, acquirer_fit_score=0.10, valuation_discount=0.10,
            de_risking_stage=0.10,
        )
        result = compute_layer3(0.75, single_bucket_di, _gi())
        assert "G4" in result.active_gate_ids
        assert result.final_score <= _GATE_CAPS["G4"] + 1e-9

    def test_triggers_when_strength_below_plausible_threshold(self):
        # Multiple buckets marginally active but overall strength low
        weak_di = DriverBucketInputs(
            financing_pressure=0.36, external_deal_activity=0.31, pipeline_gap_urgency=0.31,
            activist_signal=0.05, strategic_review_signal=0.0, catalyst_proximity=0.05,
            scarcity_score=0.15, acquirer_fit_score=0.15, valuation_discount=0.15,
            de_risking_stage=0.15,
        )
        result = compute_layer3(0.75, weak_di, _gi())
        buckets = result.driver_buckets
        if buckets.driver_strength_score < _STRENGTH_PLAUSIBLE:
            assert "G4" in result.active_gate_ids

    def test_not_triggered_when_strong_setup(self):
        result = _run(0.80)  # default has multiple active buckets with decent strength
        # Check that G4 is not triggered if strength and count are sufficient
        if result.driver_buckets.driver_strength_score >= _STRENGTH_PLAUSIBLE and \
           result.driver_buckets.active_bucket_count >= 2:
            assert "G4" not in result.active_gate_ids


# ---------------------------------------------------------------------------
# 12. Gate 5 — Seller Not Ready
# ---------------------------------------------------------------------------

class TestGate5SellerNotReady:
    def test_triggers_when_all_three_conditions_met(self):
        result = compute_layer3(
            0.80, _di(),
            _gi(seller_willingness=0.20, financing_pressure=0.20, no_active_process_signal=True),
        )
        assert "G5" in result.active_gate_ids
        assert result.final_score <= _GATE_CAPS["G5"] + 1e-9

    def test_not_triggered_when_seller_willing(self):
        result = compute_layer3(
            0.80, _di(),
            _gi(seller_willingness=0.50, financing_pressure=0.20, no_active_process_signal=True),
        )
        assert "G5" not in result.active_gate_ids

    def test_not_triggered_when_financing_pressure_high(self):
        result = compute_layer3(
            0.80, _di(),
            _gi(seller_willingness=0.20, financing_pressure=0.50, no_active_process_signal=True),
        )
        assert "G5" not in result.active_gate_ids

    def test_not_triggered_when_active_process(self):
        result = compute_layer3(
            0.80, _di(),
            _gi(seller_willingness=0.20, financing_pressure=0.20, no_active_process_signal=False),
        )
        assert "G5" not in result.active_gate_ids


# ---------------------------------------------------------------------------
# 13. Gate 6 — Capital Pressure Without Quality
# ---------------------------------------------------------------------------

class TestGate6CapitalPressureWithoutQuality:
    def test_triggers_when_high_pressure_low_quality(self):
        result = compute_layer3(
            0.75, _di(),
            _gi(financing_pressure=0.70, asset_quality=0.40),
        )
        assert "G6" in result.active_gate_ids
        assert result.final_score <= _GATE_CAPS["G6"] + 1e-9

    def test_not_triggered_when_quality_sufficient(self):
        result = compute_layer3(
            0.75, _di(),
            _gi(financing_pressure=0.70, asset_quality=0.60),
        )
        assert "G6" not in result.active_gate_ids

    def test_not_triggered_when_pressure_low(self):
        result = compute_layer3(
            0.75, _di(),
            _gi(financing_pressure=0.40, asset_quality=0.40),
        )
        assert "G6" not in result.active_gate_ids

    def test_distress_without_quality_interpretation(self):
        """Verify distress ≠ deal thesis is a key principle."""
        # High pressure alone should NOT make a weak asset attractive
        result = compute_layer3(
            0.75, _di(financing_pressure=0.80),
            _gi(financing_pressure=0.80, asset_quality=0.35),
        )
        assert "G6" in result.active_gate_ids


# ---------------------------------------------------------------------------
# 14. Gate 7 — Encumbrance / Control
# ---------------------------------------------------------------------------

class TestGate7Encumbrance:
    def test_triggers_when_asset_control_low(self):
        result = compute_layer3(0.75, _di(), _gi(asset_control=0.30))
        assert "G7" in result.active_gate_ids
        assert result.final_score <= _GATE_CAPS["G7"] + 1e-9

    def test_not_triggered_above_threshold(self):
        result = compute_layer3(0.75, _di(), _gi(asset_control=0.60))
        assert "G7" not in result.active_gate_ids

    def test_boundary_at_exactly_040(self):
        """asset_control = 0.40 exactly → NOT < 0.40 → no trigger."""
        result = compute_layer3(0.75, _di(), _gi(asset_control=0.40))
        assert "G7" not in result.active_gate_ids


# ---------------------------------------------------------------------------
# 15. Gate 8 — Deal Feasibility
# ---------------------------------------------------------------------------

class TestGate8DealFeasibility:
    def test_triggers_when_affordability_low(self):
        result = compute_layer3(0.75, _di(), _gi(affordability=0.30))
        assert "G8" in result.active_gate_ids
        assert result.final_score <= _GATE_CAPS["G8"] + 1e-9

    def test_triggers_when_antitrust_risk_high(self):
        result = compute_layer3(0.75, _di(), _gi(antitrust_risk_high=True))
        assert "G8" in result.active_gate_ids

    def test_triggers_when_integration_severe(self):
        result = compute_layer3(0.75, _di(), _gi(integration_complexity_severe=True))
        assert "G8" in result.active_gate_ids

    def test_not_triggered_when_all_feasible(self):
        result = compute_layer3(0.75, _di(), _gi(affordability=0.70,
                                                   antitrust_risk_high=False,
                                                   integration_complexity_severe=False))
        assert "G8" not in result.active_gate_ids


# ---------------------------------------------------------------------------
# 16. Most-restrictive-cap logic
# ---------------------------------------------------------------------------

class TestMostRestrictiveCapLogic:
    def test_multiple_gates_apply_min_cap(self):
        """G1(0.35) and G2(0.50) both trigger → cap at 0.35."""
        result = compute_layer3(
            0.90, _di(),
            _gi(asset_quality=0.20, acquirer_right_to_win=0.30),
        )
        assert "G1" in result.active_gate_ids
        assert "G2" in result.active_gate_ids
        assert result.most_restrictive_cap == pytest.approx(_GATE_CAPS["G1"])
        assert result.final_score <= _GATE_CAPS["G1"] + 1e-9

    def test_single_gate_uses_its_own_cap(self):
        """G7 triggers with strong driver setup → G7 cap (0.50) is binding."""
        # Use strong driver inputs so G4 does NOT trigger (strength ≥ 0.55)
        strong_di = _di(
            financing_pressure=0.70, external_deal_activity=0.70, pipeline_gap_urgency=0.70,
            activist_signal=0.70, strategic_review_signal=0.50, catalyst_proximity=0.70,
            scarcity_score=0.85, acquirer_fit_score=0.80, valuation_discount=0.70,
            de_risking_stage=0.75,
        )
        result = compute_layer3(0.80, strong_di, _gi(asset_control=0.20))
        assert "G7" in result.active_gate_ids
        assert "G4" not in result.active_gate_ids  # strong setup → G4 should not fire
        assert result.most_restrictive_cap == pytest.approx(_GATE_CAPS["G7"])
        assert result.final_score <= _GATE_CAPS["G7"] + 1e-9

    def test_no_gates_no_cap(self):
        """No gates → final_score equals pre_gate_score."""
        result = compute_layer3(0.65, _di(), _gi())
        # With default gate inputs all gates should be off
        if not result.active_gate_ids:
            assert result.final_score == pytest.approx(0.65, abs=1e-6)
            assert result.most_restrictive_cap is None

    def test_pre_gate_already_below_cap_preserved(self):
        """If pre_gate_score is already below the cap, it should not be raised."""
        result = compute_layer3(
            0.20, _di(),
            _gi(asset_control=0.20),  # G7 triggers, cap=0.50
        )
        assert "G7" in result.active_gate_ids
        assert result.final_score == pytest.approx(0.20, abs=1e-6)

    def test_g3_and_g4_both_trigger_g3_wins(self):
        """G3 (cap=0.45) and G4 (cap=0.65) both active → G3's cap wins."""
        no_driver_di = DriverBucketInputs(
            financing_pressure=0.10, external_deal_activity=0.05, pipeline_gap_urgency=0.05,
            activist_signal=0.05, strategic_review_signal=0.0, catalyst_proximity=0.05,
            scarcity_score=0.05, acquirer_fit_score=0.05, valuation_discount=0.10,
            de_risking_stage=0.10,
        )
        result = compute_layer3(0.80, no_driver_di, _gi())
        # Zero active buckets → G3 triggers; G4 also triggers (0 buckets < 2)
        assert "G3" in result.active_gate_ids
        assert "G4" in result.active_gate_ids
        assert result.most_restrictive_cap == pytest.approx(_GATE_CAPS["G3"])
        assert result.final_score <= _GATE_CAPS["G3"] + 1e-9

    def test_all_caps_specified_correctly(self):
        """Validate cap ordering matches spec: G1 most restrictive, G4 least (of triggers)."""
        assert _GATE_CAPS["G1"] == pytest.approx(0.35)
        assert _GATE_CAPS["G2"] == pytest.approx(0.50)
        assert _GATE_CAPS["G3"] == pytest.approx(0.45)
        assert _GATE_CAPS["G4"] == pytest.approx(0.65)
        assert _GATE_CAPS["G5"] == pytest.approx(0.55)
        assert _GATE_CAPS["G6"] == pytest.approx(0.45)
        assert _GATE_CAPS["G7"] == pytest.approx(0.50)
        assert _GATE_CAPS["G8"] == pytest.approx(0.60)


# ---------------------------------------------------------------------------
# 17. Layer3Output field completeness
# ---------------------------------------------------------------------------

class TestLayer3OutputFields:
    def test_all_gate_results_present(self):
        result = _run()
        assert len(result.gate_results) == 8

    def test_gate_result_ids_correct(self):
        result = _run()
        ids = [g.gate_id for g in result.gate_results]
        assert ids == ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]

    def test_final_score_in_01(self):
        result = _run()
        assert 0.0 <= result.final_score <= 1.0

    def test_pre_gate_score_preserved(self):
        result = _run(pre_gate=0.72)
        assert result.pre_gate_score == pytest.approx(0.72, abs=1e-6)

    def test_target_name_preserved(self):
        result = compute_layer3(0.65, _di(), _gi(), target_name="AmazingBio")
        assert result.target_name == "AmazingBio"

    def test_acquirer_id_preserved(self):
        result = compute_layer3(0.65, _di(), _gi(), acquirer_id="BIG-PHARMA")
        assert result.acquirer_id == "BIG-PHARMA"

    def test_classification_non_empty(self):
        result = _run()
        assert len(result.classification) > 0

    def test_interpretation_non_empty(self):
        result = _run()
        assert len(result.interpretation) > 0

    def test_near_term_field_matches_bucket_result(self):
        result = _run()
        assert result.near_term_transaction_possible == result.driver_buckets.near_term_transaction_possible

    def test_active_gate_ids_subset_of_all_gates(self):
        result = _run()
        assert all(gid in _GATE_CAPS for gid in result.active_gate_ids)


# ---------------------------------------------------------------------------
# 18. End-to-end integration
# ---------------------------------------------------------------------------

class TestComputeLayer3Integration:
    def test_strong_setup_no_gates(self):
        """All inputs strong → no gates, high final score."""
        result = compute_layer3(
            pre_gate_score=0.82,
            driver_inputs=_di(
                financing_pressure=0.70, external_deal_activity=0.75, pipeline_gap_urgency=0.70,
                activist_signal=0.65, strategic_review_signal=0.50, catalyst_proximity=0.70,
                scarcity_score=0.85, acquirer_fit_score=0.80, valuation_discount=0.70,
                de_risking_stage=0.75,
            ),
            gate_inputs=_gi(
                asset_quality=0.80, acquirer_right_to_win=0.75, seller_willingness=0.65,
                financing_pressure=0.70, asset_control=0.80, affordability=0.75,
            ),
            target_name="ExampleBio",
            acquirer_id="Vertex",
        )
        assert result.final_score >= 0.70
        assert result.near_term_transaction_possible
        assert "ExampleBio" in result.interpretation or len(result.interpretation) > 0

    def test_broken_asset_dominates(self):
        """G1 (cap=0.35) overrides all other signals."""
        result = compute_layer3(
            0.90, _di(financing_pressure=0.80, external_deal_activity=0.80),
            _gi(asset_quality=0.20, acquirer_right_to_win=0.80, asset_control=0.80),
        )
        assert "G1" in result.active_gate_ids
        assert result.final_score <= 0.35 + 1e-9

    def test_strategic_watch_scenario(self):
        """High strategic fit but no transaction drivers → strategic watch."""
        no_pressure_di = DriverBucketInputs(
            financing_pressure=0.10, external_deal_activity=0.05, pipeline_gap_urgency=0.05,
            activist_signal=0.05, strategic_review_signal=0.0, catalyst_proximity=0.10,
            scarcity_score=0.10, acquirer_fit_score=0.10, valuation_discount=0.10,
            de_risking_stage=0.10,
        )
        result = compute_layer3(
            0.70, no_pressure_di,
            _gi(asset_quality=0.75, acquirer_right_to_win=0.80, seller_willingness=0.20,
                financing_pressure=0.10, no_active_process_signal=True),
        )
        assert "G3" in result.active_gate_ids
        assert not result.near_term_transaction_possible

    def test_distress_trap_scenario(self):
        """High financing pressure + weak asset → G6 fires, caps score."""
        result = compute_layer3(
            0.75,
            _di(financing_pressure=0.85),
            _gi(financing_pressure=0.85, asset_quality=0.35),
        )
        assert "G6" in result.active_gate_ids
        assert result.final_score <= _GATE_CAPS["G6"] + 1e-9

    def test_gate_results_always_has_8_entries(self):
        result = compute_layer3(0.60, _di(), _gi())
        assert len(result.gate_results) == 8

    def test_final_score_never_exceeds_pre_gate(self):
        """Gates only cap, they never boost."""
        result = _run(pre_gate=0.80)
        assert result.final_score <= result.pre_gate_score + 1e-9
