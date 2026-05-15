"""
Tests for Layer 4 — BD Watchlist Classification and Action Routing (Sprint 40).

Coverage:
- All 7 classification paths: trigger condition, non-trigger, boundary
- Classification priority ordering (pass > data_insufficient > process_ready > …)
- All 8 deal structures
- Persistence logic: suppression, allow after 2 observations, major-event override
- Promotion and demotion trigger lists per class
- All 9 required spec output fields present
- Review cadence and time horizon mapping per class
- Confidence level mapping
- End-to-end integration scenarios
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_layer4_routing import (
    ConfidenceLevel,
    DealStructure,
    Layer4Inputs,
    Layer4Output,
    ReviewCadence,
    TimeHorizon,
    WatchlistClass,
    _AP_DRIVER_BUCKETS_MIN,
    _AP_SELLER_WILLINGNESS_MIN,
    _AP_STRATEGIC_PRIORITY_MIN,
    _AP_TRANSACTION_READINESS_MIN,
    _CW_ASSET_QUALITY_MIN,
    _CW_STRATEGIC_FIT_MIN,
    _DATA_CONFIDENCE_MIN,
    _DEMOTION_TRIGGERS,
    _PASS_ASSET_QUALITY_MIN,
    _PASS_DEAL_FEASIBILITY_MIN,
    _PASS_STRATEGIC_FIT_MIN,
    _PERSISTENCE_MIN_CONSECUTIVE,
    _PR_DEAL_FEASIBILITY_MIN,
    _PR_SELLER_WILLINGNESS_MIN,
    _PR_STRATEGIC_PRIORITY_MIN,
    _PR_TRANSACTION_READINESS_MIN,
    _PROMOTION_TRIGGERS,
    _RB_SELLER_WILLINGNESS_MAX,
    _RB_STRATEGIC_PRIORITY_MIN,
    _RB_TRANSACTION_READINESS_HI,
    _RB_TRANSACTION_READINESS_LO,
    _REVIEW_CADENCES,
    _SR_STRATEGIC_PRIORITY_MIN,
    _SR_TRANSACTION_READINESS_MAX,
    _TIME_HORIZONS,
    compute_layer4,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _inp(**overrides) -> Layer4Inputs:
    """Default inputs: a strong target that clears all gates cleanly."""
    defaults = dict(
        asset_quality=0.75,
        strategic_fit=0.72,
        deal_feasibility=0.65,
        seller_willingness=0.55,
        de_risking_stage=0.70,
        asset_control=0.80,
        strategic_priority=0.72,
        transaction_probability=0.62,
        data_confidence_score=0.90,
        active_driver_bucket_count=3,
        final_score=0.68,
        catalyst_within_180_days=False,
        prior_classification=None,
        consecutive_new_class_signals=0,
        major_event_override=False,
    )
    defaults.update(overrides)
    return Layer4Inputs(**defaults)


def _run(**overrides) -> Layer4Output:
    return compute_layer4(_inp(**overrides), target_name="TestBio", acquirer_id="ACQ-1")


# ---------------------------------------------------------------------------
# 1. Pass class
# ---------------------------------------------------------------------------

class TestPassClass:
    def test_low_asset_quality_gives_pass(self):
        result = _run(asset_quality=_PASS_ASSET_QUALITY_MIN - 0.01)
        assert result.watchlist_class == WatchlistClass.PASS.value

    def test_low_strategic_fit_gives_pass(self):
        result = _run(strategic_fit=_PASS_STRATEGIC_FIT_MIN - 0.01)
        assert result.watchlist_class == WatchlistClass.PASS.value

    def test_low_deal_feasibility_gives_pass(self):
        result = _run(deal_feasibility=_PASS_DEAL_FEASIBILITY_MIN - 0.01)
        assert result.watchlist_class == WatchlistClass.PASS.value

    def test_exactly_at_asset_quality_threshold_not_pass(self):
        """asset_quality == threshold → NOT < threshold → no pass."""
        result = _run(asset_quality=_PASS_ASSET_QUALITY_MIN)
        assert result.watchlist_class != WatchlistClass.PASS.value

    def test_good_inputs_not_pass(self):
        result = _run()
        assert result.watchlist_class != WatchlistClass.PASS.value

    def test_pass_reason_code_includes_field(self):
        result = _run(asset_quality=0.20)
        assert any("asset_quality" in c for c in result.reason_codes)

    def test_pass_action_is_archive(self):
        result = _run(asset_quality=0.20)
        assert "archive" in result.recommended_bd_action.lower()

    def test_pass_structure_is_monitor_only(self):
        result = _run(asset_quality=0.20)
        assert result.recommended_structure == DealStructure.MONITOR_ONLY.value


# ---------------------------------------------------------------------------
# 2. Data Insufficient class
# ---------------------------------------------------------------------------

class TestDataInsufficientClass:
    def test_low_confidence_gives_data_insufficient(self):
        result = _run(data_confidence_score=_DATA_CONFIDENCE_MIN - 0.01)
        assert result.watchlist_class == WatchlistClass.DATA_INSUFFICIENT.value

    def test_at_confidence_threshold_not_data_insufficient(self):
        """data_confidence_score == threshold → NOT < threshold → no data_insufficient."""
        result = _run(data_confidence_score=_DATA_CONFIDENCE_MIN)
        assert result.watchlist_class != WatchlistClass.DATA_INSUFFICIENT.value

    def test_pass_has_priority_over_data_insufficient(self):
        """Low asset_quality (pass) + low confidence → pass wins."""
        result = _run(asset_quality=0.20, data_confidence_score=0.30)
        assert result.watchlist_class == WatchlistClass.PASS.value

    def test_data_insufficient_action_is_diligence(self):
        result = _run(data_confidence_score=0.40)
        assert "diligence" in result.recommended_bd_action.lower()

    def test_data_insufficient_confidence_is_insufficient(self):
        result = _run(data_confidence_score=0.40)
        assert result.confidence_level == ConfidenceLevel.INSUFFICIENT.value

    def test_data_insufficient_structure_is_monitor_only(self):
        result = _run(data_confidence_score=0.40)
        assert result.recommended_structure == DealStructure.MONITOR_ONLY.value


# ---------------------------------------------------------------------------
# 3. Process Ready class
# ---------------------------------------------------------------------------

class TestProcessReadyClass:
    def _pr_inputs(self, **overrides):
        base = dict(
            strategic_priority=_PR_STRATEGIC_PRIORITY_MIN,
            transaction_probability=_PR_TRANSACTION_READINESS_MIN,
            seller_willingness=_PR_SELLER_WILLINGNESS_MIN,
            deal_feasibility=_PR_DEAL_FEASIBILITY_MIN,
            active_driver_bucket_count=3,
        )
        base.update(overrides)
        return base

    def test_all_conditions_met_gives_process_ready(self):
        result = _run(**self._pr_inputs())
        assert result.watchlist_class == WatchlistClass.PROCESS_READY.value

    def test_low_sp_not_process_ready(self):
        result = _run(**self._pr_inputs(strategic_priority=_PR_STRATEGIC_PRIORITY_MIN - 0.01))
        assert result.watchlist_class != WatchlistClass.PROCESS_READY.value

    def test_low_transaction_readiness_not_process_ready(self):
        result = _run(**self._pr_inputs(transaction_probability=_PR_TRANSACTION_READINESS_MIN - 0.01))
        assert result.watchlist_class != WatchlistClass.PROCESS_READY.value

    def test_low_seller_willingness_not_process_ready(self):
        result = _run(**self._pr_inputs(seller_willingness=_PR_SELLER_WILLINGNESS_MIN - 0.01))
        assert result.watchlist_class != WatchlistClass.PROCESS_READY.value

    def test_low_deal_feasibility_not_process_ready(self):
        result = _run(**self._pr_inputs(deal_feasibility=_PR_DEAL_FEASIBILITY_MIN - 0.01))
        assert result.watchlist_class != WatchlistClass.PROCESS_READY.value

    def test_process_ready_cadence_is_weekly(self):
        result = _run(**self._pr_inputs())
        assert result.review_cadence == ReviewCadence.WEEKLY.value

    def test_process_ready_time_horizon_is_zero_to_six(self):
        result = _run(**self._pr_inputs())
        assert result.time_horizon == TimeHorizon.ZERO_TO_6_MONTHS.value


# ---------------------------------------------------------------------------
# 4. Active Pursuit class
# ---------------------------------------------------------------------------

class TestActivePursuitClass:
    def _ap_inputs(self, **overrides):
        base = dict(
            strategic_priority=_AP_STRATEGIC_PRIORITY_MIN,
            transaction_probability=_AP_TRANSACTION_READINESS_MIN,
            seller_willingness=_AP_SELLER_WILLINGNESS_MIN,
            active_driver_bucket_count=_AP_DRIVER_BUCKETS_MIN,
            # Keep below process_ready thresholds
            deal_feasibility=0.55,
        )
        base.update(overrides)
        return base

    def test_all_conditions_met_gives_active_pursuit(self):
        result = _run(**self._ap_inputs())
        assert result.watchlist_class == WatchlistClass.ACTIVE_PURSUIT.value

    def test_insufficient_driver_buckets_not_active_pursuit(self):
        result = _run(**self._ap_inputs(active_driver_bucket_count=_AP_DRIVER_BUCKETS_MIN - 1))
        assert result.watchlist_class != WatchlistClass.ACTIVE_PURSUIT.value

    def test_low_sp_not_active_pursuit(self):
        result = _run(**self._ap_inputs(strategic_priority=_AP_STRATEGIC_PRIORITY_MIN - 0.01))
        assert result.watchlist_class != WatchlistClass.ACTIVE_PURSUIT.value

    def test_low_seller_willingness_not_active_pursuit(self):
        result = _run(**self._ap_inputs(seller_willingness=_AP_SELLER_WILLINGNESS_MIN - 0.01))
        assert result.watchlist_class != WatchlistClass.ACTIVE_PURSUIT.value

    def test_process_ready_has_priority_over_active_pursuit(self):
        """When process_ready conditions are met, active_pursuit is NOT selected."""
        result = _run(
            strategic_priority=0.80, transaction_probability=0.75,
            seller_willingness=0.65, deal_feasibility=0.65,
            active_driver_bucket_count=3,
        )
        assert result.watchlist_class == WatchlistClass.PROCESS_READY.value

    def test_active_pursuit_cadence_is_weekly(self):
        result = _run(**self._ap_inputs())
        assert result.review_cadence == ReviewCadence.WEEKLY.value

    def test_active_pursuit_action_contains_memo(self):
        result = _run(**self._ap_inputs())
        assert "memo" in result.recommended_bd_action.lower()


# ---------------------------------------------------------------------------
# 5. Catalyst Watch class
# ---------------------------------------------------------------------------

class TestCatalystWatchClass:
    def _cw_inputs(self, **overrides):
        base = dict(
            catalyst_within_180_days=True,
            asset_quality=_CW_ASSET_QUALITY_MIN,
            strategic_fit=_CW_STRATEGIC_FIT_MIN,
            # Ensure lower classes are not triggered first
            strategic_priority=0.60,
            transaction_probability=0.38,
            seller_willingness=0.35,
            active_driver_bucket_count=1,
            deal_feasibility=0.55,
        )
        base.update(overrides)
        return base

    def test_catalyst_with_quality_gives_catalyst_watch(self):
        result = _run(**self._cw_inputs())
        assert result.watchlist_class == WatchlistClass.CATALYST_WATCH.value

    def test_no_catalyst_not_catalyst_watch(self):
        result = _run(**self._cw_inputs(catalyst_within_180_days=False))
        assert result.watchlist_class != WatchlistClass.CATALYST_WATCH.value

    def test_low_asset_quality_not_catalyst_watch(self):
        result = _run(**self._cw_inputs(asset_quality=_CW_ASSET_QUALITY_MIN - 0.01))
        assert result.watchlist_class != WatchlistClass.CATALYST_WATCH.value

    def test_low_strategic_fit_not_catalyst_watch(self):
        result = _run(**self._cw_inputs(strategic_fit=_CW_STRATEGIC_FIT_MIN - 0.01))
        assert result.watchlist_class != WatchlistClass.CATALYST_WATCH.value

    def test_catalyst_watch_cadence_is_bi_weekly(self):
        result = _run(**self._cw_inputs())
        assert result.review_cadence == ReviewCadence.BI_WEEKLY.value

    def test_catalyst_watch_time_horizon_is_zero_to_six(self):
        result = _run(**self._cw_inputs())
        assert result.time_horizon == TimeHorizon.ZERO_TO_6_MONTHS.value


# ---------------------------------------------------------------------------
# 6. Relationship Build class
# ---------------------------------------------------------------------------

class TestRelationshipBuildClass:
    def _rb_inputs(self, **overrides):
        base = dict(
            strategic_priority=_RB_STRATEGIC_PRIORITY_MIN,
            seller_willingness=_RB_SELLER_WILLINGNESS_MAX - 0.01,
            transaction_probability=(_RB_TRANSACTION_READINESS_LO + _RB_TRANSACTION_READINESS_HI) / 2,
            catalyst_within_180_days=False,
            active_driver_bucket_count=1,
            deal_feasibility=0.55,
        )
        base.update(overrides)
        return base

    def test_conditions_met_gives_relationship_build(self):
        result = _run(**self._rb_inputs())
        assert result.watchlist_class == WatchlistClass.RELATIONSHIP_BUILD.value

    def test_high_seller_willingness_not_relationship_build(self):
        result = _run(**self._rb_inputs(seller_willingness=_RB_SELLER_WILLINGNESS_MAX))
        assert result.watchlist_class != WatchlistClass.RELATIONSHIP_BUILD.value

    def test_low_sp_not_relationship_build(self):
        result = _run(**self._rb_inputs(strategic_priority=_RB_STRATEGIC_PRIORITY_MIN - 0.01))
        assert result.watchlist_class != WatchlistClass.RELATIONSHIP_BUILD.value

    def test_tp_above_range_not_relationship_build(self):
        result = _run(**self._rb_inputs(transaction_probability=_RB_TRANSACTION_READINESS_HI + 0.01))
        assert result.watchlist_class != WatchlistClass.RELATIONSHIP_BUILD.value

    def test_tp_below_range_not_relationship_build(self):
        result = _run(**self._rb_inputs(transaction_probability=_RB_TRANSACTION_READINESS_LO - 0.01))
        assert result.watchlist_class != WatchlistClass.RELATIONSHIP_BUILD.value

    def test_relationship_build_cadence_is_monthly(self):
        result = _run(**self._rb_inputs())
        assert result.review_cadence == ReviewCadence.MONTHLY.value

    def test_relationship_build_structure_is_minority_equity(self):
        # Moderate asset quality and TA fit that don't trigger higher structures
        result = _run(**self._rb_inputs(asset_quality=0.60, de_risking_stage=0.65,
                                        strategic_fit=0.60, asset_control=0.85))
        assert result.recommended_structure == DealStructure.MINORITY_EQUITY.value


# ---------------------------------------------------------------------------
# 7. Strategic Radar class
# ---------------------------------------------------------------------------

class TestStrategicRadarClass:
    def _sr_inputs(self, **overrides):
        base = dict(
            strategic_priority=_SR_STRATEGIC_PRIORITY_MIN,
            transaction_probability=_SR_TRANSACTION_READINESS_MAX - 0.01,
            catalyst_within_180_days=False,
            seller_willingness=0.20,
            active_driver_bucket_count=0,
            deal_feasibility=0.55,
        )
        base.update(overrides)
        return base

    def test_high_sp_low_tp_gives_strategic_radar(self):
        result = _run(**self._sr_inputs())
        assert result.watchlist_class == WatchlistClass.STRATEGIC_RADAR.value

    def test_low_sp_not_strategic_radar(self):
        result = _run(**self._sr_inputs(strategic_priority=_SR_STRATEGIC_PRIORITY_MIN - 0.01))
        assert result.watchlist_class != WatchlistClass.STRATEGIC_RADAR.value

    def test_high_tp_not_strategic_radar(self):
        result = _run(**self._sr_inputs(transaction_probability=_SR_TRANSACTION_READINESS_MAX))
        assert result.watchlist_class != WatchlistClass.STRATEGIC_RADAR.value

    def test_strategic_radar_cadence_is_quarterly(self):
        result = _run(**self._sr_inputs())
        assert result.review_cadence == ReviewCadence.QUARTERLY.value

    def test_strategic_radar_time_horizon_is_24_plus(self):
        result = _run(**self._sr_inputs())
        assert result.time_horizon == TimeHorizon.BEYOND_24_MONTHS.value


# ---------------------------------------------------------------------------
# 8. Classification priority ordering
# ---------------------------------------------------------------------------

class TestClassificationPriority:
    def test_pass_before_data_insufficient(self):
        """Low quality + low confidence → pass wins."""
        result = _run(asset_quality=0.20, data_confidence_score=0.30)
        assert result.watchlist_class == WatchlistClass.PASS.value

    def test_data_insufficient_before_process_ready(self):
        """Low confidence + process_ready conditions → data_insufficient wins."""
        result = _run(
            data_confidence_score=0.40,
            strategic_priority=0.80, transaction_probability=0.75,
            seller_willingness=0.65, deal_feasibility=0.65,
        )
        assert result.watchlist_class == WatchlistClass.DATA_INSUFFICIENT.value

    def test_process_ready_before_active_pursuit(self):
        result = _run(
            strategic_priority=0.80, transaction_probability=0.75,
            seller_willingness=0.65, deal_feasibility=0.65,
            active_driver_bucket_count=3,
        )
        assert result.watchlist_class == WatchlistClass.PROCESS_READY.value

    def test_active_pursuit_before_catalyst_watch(self):
        """Active pursuit conditions + catalyst → active pursuit wins."""
        result = _run(
            strategic_priority=_AP_STRATEGIC_PRIORITY_MIN,
            transaction_probability=_AP_TRANSACTION_READINESS_MIN,
            seller_willingness=_AP_SELLER_WILLINGNESS_MIN,
            active_driver_bucket_count=_AP_DRIVER_BUCKETS_MIN,
            catalyst_within_180_days=True,
            deal_feasibility=0.55,
        )
        assert result.watchlist_class == WatchlistClass.ACTIVE_PURSUIT.value

    def test_catalyst_watch_before_relationship_build(self):
        """Catalyst + quality + fit → catalyst_watch wins over relationship_build."""
        result = _run(
            catalyst_within_180_days=True,
            asset_quality=_CW_ASSET_QUALITY_MIN,
            strategic_fit=_CW_STRATEGIC_FIT_MIN,
            strategic_priority=_RB_STRATEGIC_PRIORITY_MIN,
            seller_willingness=_RB_SELLER_WILLINGNESS_MAX - 0.01,
            transaction_probability=0.45,
            active_driver_bucket_count=1,
            deal_feasibility=0.55,
        )
        assert result.watchlist_class == WatchlistClass.CATALYST_WATCH.value

    def test_relationship_build_before_strategic_radar(self):
        """Relationship-build conditions → relationship_build, not strategic_radar."""
        result = _run(
            strategic_priority=_RB_STRATEGIC_PRIORITY_MIN,
            seller_willingness=_RB_SELLER_WILLINGNESS_MAX - 0.01,
            transaction_probability=0.45,
            catalyst_within_180_days=False,
            active_driver_bucket_count=1,
            deal_feasibility=0.55,
        )
        assert result.watchlist_class == WatchlistClass.RELATIONSHIP_BUILD.value


# ---------------------------------------------------------------------------
# 9. Deal structure recommendations
# ---------------------------------------------------------------------------

class TestDealStructure:
    def test_full_acquisition_when_high_quality_readiness(self):
        result = _run(asset_quality=0.80, transaction_probability=0.70, asset_control=0.90,
                      de_risking_stage=0.80)
        assert result.recommended_structure == DealStructure.FULL_ACQUISITION.value

    def test_option_when_high_quality_early_stage(self):
        # asset_quality ≥ 0.65 but de_risking < 0.55; tp too low for full_acquisition
        # strategic_radar class (SP ≥ 0.65, TP < 0.40) ensures structure logic executes
        result = _run(asset_quality=0.70, de_risking_stage=0.40,
                      transaction_probability=0.32, asset_control=0.90,
                      strategic_fit=0.65, strategic_priority=0.68)
        assert result.watchlist_class == WatchlistClass.STRATEGIC_RADAR.value
        assert result.recommended_structure == DealStructure.OPTION_TO_ACQUIRE.value

    def test_asset_license_when_poor_feasibility(self):
        # strategic_fit ≥ 0.65 AND deal_feasibility < 0.50 (full co unattractive)
        # strategic_radar class so structure logic runs (asset_license check precedes radar fallback)
        result = _run(strategic_fit=0.70, deal_feasibility=0.40,
                      asset_quality=0.60, transaction_probability=0.32,
                      asset_control=0.90, de_risking_stage=0.60,
                      strategic_priority=0.68)
        assert result.watchlist_class == WatchlistClass.STRATEGIC_RADAR.value
        assert result.recommended_structure == DealStructure.ASSET_LICENSE.value

    def test_research_collab_when_early_platform(self):
        # strategic_fit ≥ 0.60, de_risking < 0.35; deal_feasibility ≥ 0.50 (no asset_license)
        # strategic_radar class ensures structure logic runs
        result = _run(strategic_fit=0.65, de_risking_stage=0.25,
                      asset_quality=0.60, transaction_probability=0.30,
                      asset_control=0.90, deal_feasibility=0.60,
                      strategic_priority=0.68)
        assert result.watchlist_class == WatchlistClass.STRATEGIC_RADAR.value
        assert result.recommended_structure == DealStructure.RESEARCH_COLLABORATION.value

    def test_regional_rights_when_encumbered(self):
        result = _run(asset_control=0.30)
        assert result.recommended_structure == DealStructure.REGIONAL_RIGHTS.value

    def test_monitor_only_for_pass(self):
        result = _run(asset_quality=0.20)
        assert result.recommended_structure == DealStructure.MONITOR_ONLY.value

    def test_monitor_only_for_data_insufficient(self):
        result = _run(data_confidence_score=0.30)
        assert result.recommended_structure == DealStructure.MONITOR_ONLY.value

    def test_co_development_for_moderate_signals(self):
        # Decent quality and fit; catalyst_watch class avoids strategic_radar/relationship_build
        # fallbacks that would return monitor_only/minority_equity before co_development
        result = _run(
            asset_quality=0.60, strategic_fit=0.63, de_risking_stage=0.65,
            transaction_probability=0.38, asset_control=0.90, deal_feasibility=0.60,
            seller_willingness=0.30, strategic_priority=0.62,
            catalyst_within_180_days=True, active_driver_bucket_count=1,
        )
        assert result.watchlist_class == WatchlistClass.CATALYST_WATCH.value
        assert result.recommended_structure == DealStructure.CO_DEVELOPMENT.value


# ---------------------------------------------------------------------------
# 10. Persistence / churn suppression
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_no_prior_no_suppression(self):
        result = _run(prior_classification=None)
        assert not result.classification_suppressed

    def test_same_class_no_suppression(self):
        result = _run(prior_classification=WatchlistClass.ACTIVE_PURSUIT.value,
                      consecutive_new_class_signals=0)
        assert not result.classification_suppressed

    def test_suppresses_change_when_only_one_signal(self):
        """Candidate changes class but only 1 consecutive signal → hold prior."""
        result = compute_layer4(
            Layer4Inputs(
                asset_quality=0.75, strategic_fit=0.72, deal_feasibility=0.65,
                seller_willingness=0.55, de_risking_stage=0.70, asset_control=0.80,
                strategic_priority=0.72, transaction_probability=0.62,
                data_confidence_score=0.90, active_driver_bucket_count=3,
                final_score=0.68, catalyst_within_180_days=False,
                # Prior is strategic_radar, candidate would be active_pursuit
                prior_classification=WatchlistClass.STRATEGIC_RADAR.value,
                consecutive_new_class_signals=1,  # only 1 — below threshold
                major_event_override=False,
            ),
            target_name="TestBio",
        )
        assert result.classification_suppressed
        assert result.watchlist_class == WatchlistClass.STRATEGIC_RADAR.value
        assert result.candidate_class == WatchlistClass.ACTIVE_PURSUIT.value

    def test_allows_change_after_two_observations(self):
        result = compute_layer4(
            Layer4Inputs(
                asset_quality=0.75, strategic_fit=0.72, deal_feasibility=0.65,
                seller_willingness=0.55, de_risking_stage=0.70, asset_control=0.80,
                strategic_priority=0.72, transaction_probability=0.62,
                data_confidence_score=0.90, active_driver_bucket_count=3,
                final_score=0.68, catalyst_within_180_days=False,
                prior_classification=WatchlistClass.STRATEGIC_RADAR.value,
                consecutive_new_class_signals=_PERSISTENCE_MIN_CONSECUTIVE,
                major_event_override=False,
            ),
            target_name="TestBio",
        )
        assert not result.classification_suppressed
        assert result.watchlist_class == WatchlistClass.ACTIVE_PURSUIT.value

    def test_major_event_overrides_persistence(self):
        result = compute_layer4(
            Layer4Inputs(
                asset_quality=0.75, strategic_fit=0.72, deal_feasibility=0.65,
                seller_willingness=0.55, de_risking_stage=0.70, asset_control=0.80,
                strategic_priority=0.72, transaction_probability=0.62,
                data_confidence_score=0.90, active_driver_bucket_count=3,
                final_score=0.68, catalyst_within_180_days=False,
                prior_classification=WatchlistClass.STRATEGIC_RADAR.value,
                consecutive_new_class_signals=0,
                major_event_override=True,   # override even with 0 signals
            ),
            target_name="TestBio",
        )
        assert not result.classification_suppressed
        assert result.watchlist_class == WatchlistClass.ACTIVE_PURSUIT.value

    def test_suppression_code_added_to_reason_codes(self):
        result = compute_layer4(
            Layer4Inputs(
                asset_quality=0.75, strategic_fit=0.72, deal_feasibility=0.65,
                seller_willingness=0.55, de_risking_stage=0.70, asset_control=0.80,
                strategic_priority=0.72, transaction_probability=0.62,
                data_confidence_score=0.90, active_driver_bucket_count=3,
                final_score=0.68, catalyst_within_180_days=False,
                prior_classification=WatchlistClass.STRATEGIC_RADAR.value,
                consecutive_new_class_signals=1,
                major_event_override=False,
            ),
            target_name="TestBio",
        )
        assert any("persistence_suppressed" in c for c in result.reason_codes)

    def test_invalid_prior_does_not_crash(self):
        """An unrecognised prior_classification string → no suppression."""
        result = compute_layer4(
            Layer4Inputs(
                asset_quality=0.75, strategic_fit=0.72, deal_feasibility=0.65,
                seller_willingness=0.55, de_risking_stage=0.70, asset_control=0.80,
                strategic_priority=0.72, transaction_probability=0.62,
                data_confidence_score=0.90, active_driver_bucket_count=3,
                final_score=0.68, catalyst_within_180_days=False,
                prior_classification="unknown_class_xyz",
                consecutive_new_class_signals=1,
                major_event_override=False,
            ),
            target_name="TestBio",
        )
        # Should not raise; no suppression because prior is unrecognised
        assert not result.classification_suppressed


# ---------------------------------------------------------------------------
# 11. Promotion and demotion triggers
# ---------------------------------------------------------------------------

class TestPromotionDemotionTriggers:
    @pytest.mark.parametrize("wc", [
        WatchlistClass.STRATEGIC_RADAR,
        WatchlistClass.RELATIONSHIP_BUILD,
        WatchlistClass.CATALYST_WATCH,
        WatchlistClass.ACTIVE_PURSUIT,
        WatchlistClass.PROCESS_READY,
    ])
    def test_promotion_triggers_non_empty_for_actionable_classes(self, wc):
        assert len(_PROMOTION_TRIGGERS[wc]) > 0

    @pytest.mark.parametrize("wc", [
        WatchlistClass.STRATEGIC_RADAR,
        WatchlistClass.RELATIONSHIP_BUILD,
        WatchlistClass.CATALYST_WATCH,
        WatchlistClass.ACTIVE_PURSUIT,
        WatchlistClass.PROCESS_READY,
    ])
    def test_demotion_triggers_non_empty_for_actionable_classes(self, wc):
        assert len(_DEMOTION_TRIGGERS[wc]) > 0

    def test_pass_has_no_demotion_triggers(self):
        """Pass is the lowest class; there's nowhere to demote."""
        assert len(_DEMOTION_TRIGGERS[WatchlistClass.PASS]) == 0

    def test_output_promotion_triggers_match_constant(self):
        # Active pursuit
        result = _run(
            strategic_priority=_AP_STRATEGIC_PRIORITY_MIN,
            transaction_probability=_AP_TRANSACTION_READINESS_MIN,
            seller_willingness=_AP_SELLER_WILLINGNESS_MIN,
            active_driver_bucket_count=_AP_DRIVER_BUCKETS_MIN,
            deal_feasibility=0.55,
        )
        assert result.promotion_trigger == _PROMOTION_TRIGGERS[WatchlistClass.ACTIVE_PURSUIT]

    def test_output_demotion_triggers_match_constant(self):
        result = _run(
            strategic_priority=_AP_STRATEGIC_PRIORITY_MIN,
            transaction_probability=_AP_TRANSACTION_READINESS_MIN,
            seller_willingness=_AP_SELLER_WILLINGNESS_MIN,
            active_driver_bucket_count=_AP_DRIVER_BUCKETS_MIN,
            deal_feasibility=0.55,
        )
        assert result.demotion_trigger == _DEMOTION_TRIGGERS[WatchlistClass.ACTIVE_PURSUIT]


# ---------------------------------------------------------------------------
# 12. Output field completeness (9 spec fields)
# ---------------------------------------------------------------------------

class TestOutputFields:
    def test_watchlist_class_present(self):
        assert _run().watchlist_class is not None

    def test_recommended_bd_action_present(self):
        assert len(_run().recommended_bd_action) > 0

    def test_recommended_structure_present(self):
        assert _run().recommended_structure is not None

    def test_time_horizon_present(self):
        assert _run().time_horizon is not None

    def test_review_cadence_present(self):
        assert _run().review_cadence is not None

    def test_promotion_trigger_is_list(self):
        assert isinstance(_run().promotion_trigger, list)

    def test_demotion_trigger_is_list(self):
        assert isinstance(_run().demotion_trigger, list)

    def test_confidence_level_present(self):
        assert _run().confidence_level is not None

    def test_owner_next_step_present(self):
        assert len(_run().owner_next_step) > 0

    def test_reason_codes_non_empty(self):
        assert len(_run().reason_codes) > 0

    def test_target_name_preserved(self):
        result = compute_layer4(_inp(), target_name="TargetBio")
        assert result.target_name == "TargetBio"

    def test_acquirer_id_preserved(self):
        result = compute_layer4(_inp(), acquirer_id="ACQ-777")
        assert result.acquirer_id == "ACQ-777"

    def test_candidate_class_always_set(self):
        assert _run().candidate_class is not None

    def test_classification_suppressed_is_bool(self):
        assert isinstance(_run().classification_suppressed, bool)


# ---------------------------------------------------------------------------
# 13. Review cadence and time horizon mapping
# ---------------------------------------------------------------------------

class TestCadenceAndTimeHorizon:
    @pytest.mark.parametrize("wc,expected_cadence", [
        (WatchlistClass.PASS, ReviewCadence.NONE),
        (WatchlistClass.DATA_INSUFFICIENT, ReviewCadence.AS_NEEDED),
        (WatchlistClass.STRATEGIC_RADAR, ReviewCadence.QUARTERLY),
        (WatchlistClass.RELATIONSHIP_BUILD, ReviewCadence.MONTHLY),
        (WatchlistClass.CATALYST_WATCH, ReviewCadence.BI_WEEKLY),
        (WatchlistClass.ACTIVE_PURSUIT, ReviewCadence.WEEKLY),
        (WatchlistClass.PROCESS_READY, ReviewCadence.WEEKLY),
    ])
    def test_cadence_per_class(self, wc, expected_cadence):
        assert _REVIEW_CADENCES[wc] == expected_cadence

    @pytest.mark.parametrize("wc,expected_horizon", [
        (WatchlistClass.PASS, TimeHorizon.NOT_APPLICABLE),
        (WatchlistClass.DATA_INSUFFICIENT, TimeHorizon.NOT_APPLICABLE),
        (WatchlistClass.STRATEGIC_RADAR, TimeHorizon.BEYOND_24_MONTHS),
        (WatchlistClass.RELATIONSHIP_BUILD, TimeHorizon.TWELVE_TO_24_MONTHS),
        (WatchlistClass.CATALYST_WATCH, TimeHorizon.ZERO_TO_6_MONTHS),
        (WatchlistClass.ACTIVE_PURSUIT, TimeHorizon.THREE_TO_12_MONTHS),
        (WatchlistClass.PROCESS_READY, TimeHorizon.ZERO_TO_6_MONTHS),
    ])
    def test_time_horizon_per_class(self, wc, expected_horizon):
        assert _TIME_HORIZONS[wc] == expected_horizon


# ---------------------------------------------------------------------------
# 14. Confidence level mapping
# ---------------------------------------------------------------------------

class TestConfidenceLevel:
    def test_high_confidence_when_score_above_85pct(self):
        result = _run(data_confidence_score=0.90)
        assert result.confidence_level == ConfidenceLevel.HIGH.value

    def test_medium_confidence_when_score_between_70_and_85(self):
        result = _run(data_confidence_score=0.75)
        assert result.confidence_level == ConfidenceLevel.MEDIUM.value

    def test_low_confidence_when_score_between_60_and_70(self):
        result = _run(data_confidence_score=0.65)
        assert result.confidence_level == ConfidenceLevel.LOW.value

    def test_insufficient_confidence_for_data_insufficient_class(self):
        result = _run(data_confidence_score=0.40)
        assert result.confidence_level == ConfidenceLevel.INSUFFICIENT.value


# ---------------------------------------------------------------------------
# 15. End-to-end integration scenarios
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_strong_target_process_ready(self):
        """All signals strong → process_ready, weekly cadence, prepare now."""
        result = compute_layer4(
            Layer4Inputs(
                asset_quality=0.82, strategic_fit=0.78, deal_feasibility=0.72,
                seller_willingness=0.68, de_risking_stage=0.80, asset_control=0.88,
                strategic_priority=0.80, transaction_probability=0.75,
                data_confidence_score=0.92, active_driver_bucket_count=4,
                final_score=0.78, catalyst_within_180_days=True,
            ),
            target_name="AmazingBio",
            acquirer_id="BigPharma",
        )
        assert result.watchlist_class == WatchlistClass.PROCESS_READY.value
        assert result.review_cadence == ReviewCadence.WEEKLY.value
        assert "prepare" in result.recommended_bd_action.lower() or "outreach" in result.recommended_bd_action.lower()

    def test_broken_target_pass(self):
        """Poor science → pass regardless of financing pressure."""
        result = compute_layer4(
            Layer4Inputs(
                asset_quality=0.20, strategic_fit=0.70, deal_feasibility=0.65,
                seller_willingness=0.80, de_risking_stage=0.40, asset_control=0.80,
                strategic_priority=0.70, transaction_probability=0.80,
                data_confidence_score=0.90, active_driver_bucket_count=4,
                final_score=0.75, catalyst_within_180_days=False,
            ),
            target_name="BrokenBio",
        )
        assert result.watchlist_class == WatchlistClass.PASS.value
        assert result.review_cadence == ReviewCadence.NONE.value
        assert result.recommended_structure == DealStructure.MONITOR_ONLY.value

    def test_catalyst_setup_catalyst_watch(self):
        """Near-term readout + decent quality → catalyst_watch."""
        result = compute_layer4(
            Layer4Inputs(
                asset_quality=0.65, strategic_fit=0.68, deal_feasibility=0.55,
                seller_willingness=0.30, de_risking_stage=0.60, asset_control=0.75,
                strategic_priority=0.62, transaction_probability=0.35,
                data_confidence_score=0.80, active_driver_bucket_count=1,
                final_score=0.55, catalyst_within_180_days=True,
            ),
            target_name="PhaseThreeBio",
        )
        assert result.watchlist_class == WatchlistClass.CATALYST_WATCH.value

    def test_reluctant_seller_relationship_build(self):
        """High strategic fit but management won't engage → relationship_build."""
        result = compute_layer4(
            Layer4Inputs(
                asset_quality=0.75, strategic_fit=0.78, deal_feasibility=0.60,
                seller_willingness=0.25, de_risking_stage=0.65, asset_control=0.85,
                strategic_priority=0.75, transaction_probability=0.48,
                data_confidence_score=0.88, active_driver_bucket_count=1,
                final_score=0.60, catalyst_within_180_days=False,
            ),
            target_name="PrivateBio",
        )
        assert result.watchlist_class == WatchlistClass.RELATIONSHIP_BUILD.value

    def test_data_gap_blocks_classification(self):
        """Excellent signals but data confidence low → data_insufficient first."""
        result = compute_layer4(
            Layer4Inputs(
                asset_quality=0.80, strategic_fit=0.80, deal_feasibility=0.75,
                seller_willingness=0.70, de_risking_stage=0.80, asset_control=0.90,
                strategic_priority=0.82, transaction_probability=0.78,
                data_confidence_score=0.45,  # data gap
                active_driver_bucket_count=4,
                final_score=0.80, catalyst_within_180_days=False,
            ),
            target_name="UncertainBio",
        )
        assert result.watchlist_class == WatchlistClass.DATA_INSUFFICIENT.value
        assert any("data_confidence" in c for c in result.reason_codes)

    def test_strategic_radar_for_quality_asset_no_urgency(self):
        """High strategic relevance but no transaction urgency → strategic_radar."""
        result = compute_layer4(
            Layer4Inputs(
                asset_quality=0.72, strategic_fit=0.70, deal_feasibility=0.60,
                seller_willingness=0.20, de_risking_stage=0.65, asset_control=0.85,
                strategic_priority=0.68, transaction_probability=0.28,
                data_confidence_score=0.85, active_driver_bucket_count=0,
                final_score=0.52, catalyst_within_180_days=False,
            ),
            target_name="LongRunwayBio",
        )
        assert result.watchlist_class == WatchlistClass.STRATEGIC_RADAR.value
        assert result.review_cadence == ReviewCadence.QUARTERLY.value
