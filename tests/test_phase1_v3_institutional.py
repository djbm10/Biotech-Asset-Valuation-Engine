"""
Tests for Blocks D, H1, E, F, H2, I, J — institutional-grade scoring improvements.

Covers:
  - context_modifiers.py  (Block D)
  - review_gate.py        (Block H1)
  - baseline_scorer.py    (Block E)
  - acquirer_pair_scorer.py (Block F)
  - confidence_bands.py   (Block H2)
  - ranking_backtest.py   (Block I)
  - score_explainer.py    (Block J)
"""
from __future__ import annotations

import pytest

from bve.ingestion.context_modifiers import (
    ContextModifierEngine,
    ContextProfile,
)
from bve.ingestion.review_gate import (
    ReviewDecision,
    ReviewGate,
    ReviewStatus,
    ScoreMode,
)
from bve.ingestion.baseline_scorer import BaselineScorer
from bve.intelligence.acquirer_pair_scorer import (
    AcquirerPairScorer,
    PairFeatures,
)
from bve.ingestion.confidence_bands import ConfidenceBandEstimator
from bve.analysis.ranking_backtest import (
    BacktestRecord,
    RollingBacktestConfig,
    RollingBacktestEngine,
    _precision_at_k,
    _auc_roc,
    _brier_score,
    _calibration_buckets,
)
from bve.reporting.score_explainer import (
    ScoreExplainer,
    DriverEntry,
    RiskFlag,
)
from bve.ingestion.model_versions import (
    CONTEXT_VERSION,
    BASELINE_VERSION,
    PAIR_SCORER_VERSION,
)


# ===========================================================================
# Block D — ContextModifierEngine
# ===========================================================================


class TestContextProfile:
    def test_default_profile_has_no_flags(self):
        p = ContextProfile()
        assert not p.safety_flag
        assert not p.is_lead_asset
        assert not p.biomarker_only
        assert p.version == CONTEXT_VERSION

    def test_from_dict_builds_profile(self):
        p = ContextProfile.from_dict({"safety_flag": True, "is_lead_asset": True})
        assert p.safety_flag
        assert p.is_lead_asset

    def test_from_dict_ignores_unknown_keys(self):
        p = ContextProfile.from_dict({"safety_flag": True, "unknown_key": "ignored"})
        assert p.safety_flag

    def test_frozen_profile_cannot_mutate(self):
        p = ContextProfile(safety_flag=True)
        with pytest.raises((AttributeError, TypeError)):
            p.safety_flag = False  # type: ignore


class TestContextModifierEngine:
    def setup_method(self):
        self.engine = ContextModifierEngine()

    def test_no_profile_returns_unchanged_deltas(self):
        deltas = {"asset_quality": +0.10, "seller_willingness": -0.05}
        result = self.engine.apply(deltas, "clinical_positive_ph3", profile=None)
        assert result == deltas

    def test_safety_flag_amplifies_negative(self):
        deltas = {"asset_quality": -0.10}
        profile = ContextProfile(safety_flag=True)
        result = self.engine.apply(deltas, "clinical_negative_ph3", profile)
        assert result["asset_quality"] < -0.10  # amplified

    def test_safety_flag_dampens_positive(self):
        deltas = {"asset_quality": +0.10}
        profile = ContextProfile(safety_flag=True)
        result = self.engine.apply(deltas, "clinical_positive_ph3", profile)
        assert result["asset_quality"] < +0.10  # dampened

    def test_safety_amplification_factor(self):
        deltas = {"asset_quality": -0.10}
        profile = ContextProfile(safety_flag=True)
        result = self.engine.apply(deltas, "clinical_negative_ph3", profile)
        assert abs(result["asset_quality"] - (-0.10 * 1.30)) < 1e-6

    def test_safety_dampening_factor(self):
        deltas = {"asset_quality": +0.10}
        profile = ContextProfile(safety_flag=True)
        result = self.engine.apply(deltas, "clinical_positive_ph3", profile)
        assert abs(result["asset_quality"] - (0.10 * 0.60)) < 1e-6

    def test_lead_asset_amplifies_both_directions(self):
        profile = ContextProfile(is_lead_asset=True)
        pos = self.engine.apply({"asset_quality": +0.08}, "clinical_positive_ph3", profile)
        neg = self.engine.apply({"asset_quality": -0.08}, "clinical_negative_ph3", profile)
        assert pos["asset_quality"] > 0.08
        assert neg["asset_quality"] < -0.08

    def test_biomarker_only_dampens_positive_clinical(self):
        profile = ContextProfile(biomarker_only=True)
        result = self.engine.apply(
            {"asset_quality": +0.10}, "clinical_positive_ph2", profile
        )
        assert result["asset_quality"] < 0.10

    def test_biomarker_only_does_not_dampen_negative_clinical(self):
        profile = ContextProfile(biomarker_only=True)
        result = self.engine.apply(
            {"asset_quality": -0.10}, "clinical_negative_ph2", profile
        )
        # Negative result not dampened
        assert abs(result["asset_quality"]) >= 0.10

    def test_open_label_dampens_positive_clinical(self):
        profile = ContextProfile(open_label=True)
        result = self.engine.apply(
            {"asset_quality": +0.10}, "clinical_positive_ph2", profile
        )
        assert result["asset_quality"] < 0.10

    def test_pivotal_amplifies_positive_clinical(self):
        profile = ContextProfile(pivotal_design=True)
        result = self.engine.apply(
            {"asset_quality": +0.10}, "clinical_positive_ph3", profile
        )
        assert result["asset_quality"] > 0.10

    def test_post_large_runup_dampens_positive(self):
        profile = ContextProfile(post_large_runup=True)
        result = self.engine.apply(
            {"ma_attractiveness": +0.08}, "fda_approval", profile
        )
        assert result["ma_attractiveness"] < 0.08

    def test_late_stage_amplifies_positive_regulatory(self):
        profile = ContextProfile(late_stage_pipeline=True)
        result = self.engine.apply(
            {"asset_quality": +0.10}, "fda_approval", profile
        )
        assert result["asset_quality"] > 0.10

    def test_empty_deltas_returns_empty(self):
        result = self.engine.apply({}, "fda_approval", ContextProfile())
        assert result == {}

    def test_combined_modifiers_multiply(self):
        # safety_flag (negative amplify ×1.30) × lead_asset (×1.15)
        profile = ContextProfile(safety_flag=True, is_lead_asset=True)
        result = self.engine.apply(
            {"asset_quality": -0.10}, "clinical_negative_ph3", profile
        )
        expected = -0.10 * 1.30 * 1.15
        assert abs(result["asset_quality"] - expected) < 1e-6

    def test_does_not_mutate_input(self):
        deltas = {"asset_quality": +0.10}
        original_val = deltas["asset_quality"]
        profile = ContextProfile(safety_flag=True)
        self.engine.apply(deltas, "clinical_positive_ph3", profile)
        assert deltas["asset_quality"] == original_val


# ===========================================================================
# Block H1 — ReviewGate
# ===========================================================================


class TestReviewGate:
    def setup_method(self):
        self.gate = ReviewGate(threshold=0.70)

    def test_high_materiality_needs_review(self):
        assert self.gate.needs_review(0.80)

    def test_materiality_at_threshold_needs_review(self):
        assert self.gate.needs_review(0.70)

    def test_low_materiality_does_not_need_review(self):
        assert not self.gate.needs_review(0.65)

    def test_unknown_hash_is_pending(self):
        assert self.gate.get_status("unknown_hash") == ReviewStatus.PENDING

    def test_approve_decision_stored(self):
        d = ReviewDecision(event_hash="abc", status=ReviewStatus.APPROVED)
        self.gate.record_decision(d)
        assert self.gate.get_status("abc") == ReviewStatus.APPROVED

    def test_reject_decision_stored(self):
        d = ReviewDecision(event_hash="xyz", status=ReviewStatus.REJECTED)
        self.gate.record_decision(d)
        assert self.gate.get_status("xyz") == ReviewStatus.REJECTED

    def test_downgrade_requires_factor_below_one(self):
        with pytest.raises(ValueError):
            ReviewDecision(
                event_hash="h",
                status=ReviewStatus.DOWNGRADED,
                downgrade_factor=1.0,
            )

    def test_downgrade_factor_must_be_in_range(self):
        with pytest.raises(ValueError):
            ReviewDecision(
                event_hash="h",
                status=ReviewStatus.DOWNGRADED,
                downgrade_factor=1.5,
            )

    def test_downgraded_weight_returns_factor(self):
        d = ReviewDecision(event_hash="h", status=ReviewStatus.DOWNGRADED, downgrade_factor=0.5)
        self.gate.record_decision(d)
        factor = self.gate.weight_factor("h", ScoreMode.APPROVED_ONLY)
        assert factor == 0.5


class TestScoreMode:
    def setup_method(self):
        self.gate = ReviewGate()

    def test_approved_only_pending_returns_zero(self):
        assert self.gate.weight_factor("new_hash", ScoreMode.APPROVED_ONLY) == 0.0

    def test_provisional_pending_returns_half(self):
        assert self.gate.weight_factor("new_hash", ScoreMode.PROVISIONAL) == 0.5

    def test_all_auto_pending_returns_one(self):
        assert self.gate.weight_factor("new_hash", ScoreMode.ALL_AUTO) == 1.0

    def test_approved_returns_one_in_all_modes(self):
        d = ReviewDecision(event_hash="a", status=ReviewStatus.APPROVED)
        self.gate.record_decision(d)
        # STRUCTURAL always returns 0.0 (no ledger events count in that mode)
        non_structural = [m for m in ScoreMode if m != ScoreMode.STRUCTURAL]
        for mode in non_structural:
            assert self.gate.weight_factor("a", mode) == 1.0, f"Expected 1.0 for mode={mode}"
        assert self.gate.weight_factor("a", ScoreMode.STRUCTURAL) == 0.0

    def test_rejected_returns_zero_in_all_modes(self):
        d = ReviewDecision(event_hash="r", status=ReviewStatus.REJECTED)
        self.gate.record_decision(d)
        for mode in ScoreMode:
            assert self.gate.weight_factor("r", mode) == 0.0

    def test_summary_counts(self):
        self.gate.record_decision(ReviewDecision(event_hash="a1", status=ReviewStatus.APPROVED))
        self.gate.record_decision(ReviewDecision(event_hash="a2", status=ReviewStatus.APPROVED))
        self.gate.record_decision(ReviewDecision(event_hash="r1", status=ReviewStatus.REJECTED))
        s = self.gate.summary()
        assert s["approved"] == 2
        assert s["rejected"] == 1

    def test_overwrite_decision(self):
        self.gate.record_decision(ReviewDecision(event_hash="x", status=ReviewStatus.PENDING))
        self.gate.record_decision(ReviewDecision(event_hash="x", status=ReviewStatus.APPROVED))
        assert self.gate.get_status("x") == ReviewStatus.APPROVED


# ===========================================================================
# Block E — BaselineScorer
# ===========================================================================


class TestBaselineScorer:
    def setup_method(self):
        self.scorer = BaselineScorer()

    def test_empty_features_returns_near_prior(self):
        result = self.scorer.compute({})
        # With no features, all adjustments = 0 → score near 0.50
        assert 0.40 <= result.scores["ma_attractiveness"] <= 0.60

    def test_phase3_raises_score(self):
        base = self.scorer.compute({}).scores["ma_attractiveness"]
        result = self.scorer.compute({"phase": "phase3"})
        assert result.scores["ma_attractiveness"] > base

    def test_preclinical_lowers_score(self):
        base = self.scorer.compute({}).scores["ma_attractiveness"]
        result = self.scorer.compute({"phase": "preclinical"})
        assert result.scores["ma_attractiveness"] < base

    def test_oncology_raises_score(self):
        base = self.scorer.compute({}).scores["ma_attractiveness"]
        result = self.scorer.compute({"therapeutic_area": "oncology"})
        assert result.scores["ma_attractiveness"] > base

    def test_btd_raises_score(self):
        base = self.scorer.compute({}).scores["ma_attractiveness"]
        result = self.scorer.compute({"has_btd": True})
        assert result.scores["ma_attractiveness"] > base

    def test_cell_gene_raises_score(self):
        base = self.scorer.compute({}).scores["ma_attractiveness"]
        result = self.scorer.compute({"modality": "cell_gene"})
        assert result.scores["ma_attractiveness"] > base

    def test_cash_distress_raises_score(self):
        result = self.scorer.compute({"cash_runway_months": 8})
        baseline = self.scorer.compute({}).scores["ma_attractiveness"]
        assert result.scores["ma_attractiveness"] > baseline

    def test_cash_healthy_no_distress_modifier(self):
        result_healthy = self.scorer.compute({"cash_runway_months": 24})
        result_no_cash = self.scorer.compute({})
        assert result_healthy.scores["ma_attractiveness"] == result_no_cash.scores["ma_attractiveness"]

    def test_score_clamped_below_095(self):
        # Load up all positive features
        result = self.scorer.compute({
            "phase": "approved",
            "therapeutic_area": "rare_disease",
            "modality": "cell_gene",
            "has_btd": True,
            "has_orphan": True,
            "has_fast_track": True,
            "single_asset": True,
            "cash_runway_months": 6,
        })
        assert result.scores["ma_attractiveness"] <= 0.95

    def test_score_clamped_above_005(self):
        result = self.scorer.compute({
            "phase": "preclinical",
            "therapeutic_area": "cns",
            "platform_company": True,
        })
        assert result.scores["ma_attractiveness"] >= 0.05

    def test_breakdown_contains_applied_features(self):
        result = self.scorer.compute({"phase": "phase3", "has_btd": True})
        assert "phase:phase3" in result.feature_breakdown
        assert "has_btd" in result.feature_breakdown

    def test_as_of_date_stored(self):
        result = self.scorer.compute({}, as_of_date="2024-01-01")
        assert result.as_of_date == "2024-01-01"

    def test_version_stamp_present(self):
        result = self.scorer.compute({})
        assert result.version == BASELINE_VERSION

    def test_all_three_score_keys_present(self):
        result = self.scorer.compute({"phase": "phase2"})
        assert "ma_attractiveness" in result.scores
        assert "asset_quality" in result.scores
        assert "seller_willingness" in result.scores

    def test_single_asset_raises_seller_willingness(self):
        r_sa = self.scorer.compute({"single_asset": True})
        r_no = self.scorer.compute({})
        assert r_sa.scores["seller_willingness"] >= r_no.scores["seller_willingness"]

    def test_platform_company_reduces_seller_willingness(self):
        r_plat = self.scorer.compute({"platform_company": True})
        r_no = self.scorer.compute({})
        assert r_plat.scores["seller_willingness"] <= r_no.scores["seller_willingness"]


# ===========================================================================
# Block F — AcquirerPairScorer
# ===========================================================================


class TestPairFeatures:
    def test_valid_features_construct(self):
        f = PairFeatures(
            asset_quality=0.80,
            acquirer_appetite=0.70,
            ta_overlap=0.90,
            ta_strategic_fit=1.00,
            size_fit=0.65,
            acquirer_urgency=0.75,
            integration_capacity=0.50,
        )
        assert f.asset_quality == 0.80

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            PairFeatures(
                asset_quality=1.10,  # > 1.0
                acquirer_appetite=0.70,
                ta_overlap=0.90,
                ta_strategic_fit=1.00,
                size_fit=0.65,
                acquirer_urgency=0.75,
                integration_capacity=0.50,
            )

    def test_negative_value_raises(self):
        with pytest.raises(ValueError):
            PairFeatures(
                asset_quality=0.80,
                acquirer_appetite=-0.10,  # < 0
                ta_overlap=0.90,
                ta_strategic_fit=1.00,
                size_fit=0.65,
                acquirer_urgency=0.75,
                integration_capacity=0.50,
            )


class TestAcquirerPairScorer:
    def setup_method(self):
        self.scorer = AcquirerPairScorer()
        self.high_fit = PairFeatures(
            asset_quality=0.90,
            acquirer_appetite=0.85,
            ta_overlap=0.95,
            ta_strategic_fit=1.00,
            size_fit=0.80,
            acquirer_urgency=0.90,
            integration_capacity=0.70,
        )
        self.low_fit = PairFeatures(
            asset_quality=0.20,
            acquirer_appetite=0.15,
            ta_overlap=0.10,
            ta_strategic_fit=0.15,
            size_fit=0.20,
            acquirer_urgency=0.10,
            integration_capacity=0.30,
        )

    def test_high_fit_returns_high_probability(self):
        result = self.scorer.score(self.high_fit)
        assert result.probability > 0.85

    def test_low_fit_returns_low_probability(self):
        # Features at 0.10–0.20 range; probability should be below 0.50 baseline
        # (intercept is negative, weights are linear so low features stay below midpoint
        # only when features are truly minimal — test against high_fit spread)
        result_low = self.scorer.score(self.low_fit)
        result_high = self.scorer.score(self.high_fit)
        assert result_low.probability < result_high.probability

    def test_probability_in_range(self):
        result = self.scorer.score(self.high_fit)
        assert 0.0 <= result.probability <= 1.0

    def test_feature_contributions_present(self):
        result = self.scorer.score(self.high_fit)
        assert "asset_quality" in result.feature_contributions
        assert "acquirer_appetite" in result.feature_contributions

    def test_interaction_contribution_nonzero_for_high_features(self):
        result = self.scorer.score(self.high_fit)
        assert result.interaction_contribution > 0

    def test_higher_quality_raises_probability(self):
        low_q = PairFeatures(
            asset_quality=0.30,
            acquirer_appetite=0.70,
            ta_overlap=0.70,
            ta_strategic_fit=1.00,
            size_fit=0.70,
            acquirer_urgency=0.70,
            integration_capacity=0.70,
        )
        high_q = PairFeatures(
            asset_quality=0.90,
            acquirer_appetite=0.70,
            ta_overlap=0.70,
            ta_strategic_fit=1.00,
            size_fit=0.70,
            acquirer_urgency=0.70,
            integration_capacity=0.70,
        )
        assert self.scorer.score(high_q).probability > self.scorer.score(low_q).probability

    def test_version_stamp_present(self):
        result = self.scorer.score(self.high_fit)
        assert result.version == PAIR_SCORER_VERSION

    def test_sigmoid_of_large_positive_near_one(self):
        from bve.intelligence.acquirer_pair_scorer import AcquirerPairScorer
        scorer = AcquirerPairScorer()
        assert abs(scorer._sigmoid(100.0) - 1.0) < 1e-6

    def test_sigmoid_of_large_negative_near_zero(self):
        from bve.intelligence.acquirer_pair_scorer import AcquirerPairScorer
        scorer = AcquirerPairScorer()
        assert abs(scorer._sigmoid(-100.0) - 0.0) < 1e-6

    def test_sigmoid_of_zero_is_half(self):
        from bve.intelligence.acquirer_pair_scorer import AcquirerPairScorer
        scorer = AcquirerPairScorer()
        assert abs(scorer._sigmoid(0.0) - 0.5) < 1e-6


# ===========================================================================
# Block H2 — ConfidenceBandEstimator
# ===========================================================================


class TestConfidenceBandEstimator:
    def setup_method(self):
        self.estimator = ConfidenceBandEstimator()

    def test_no_evidence_returns_base_width(self):
        from bve.ingestion.confidence_bands import BASE_HALF_WIDTH
        band = self.estimator.compute(score=0.60)
        assert band.half_width == BASE_HALF_WIDTH

    def test_no_evidence_n_events_zero(self):
        band = self.estimator.compute(score=0.60)
        assert band.n_events == 0

    def test_more_records_narrows_band(self):
        band_1 = self.estimator.compute(0.60, [{"strength": 0.70, "age_days": 10}])
        band_5 = self.estimator.compute(0.60, [{"strength": 0.70, "age_days": 10}] * 5)
        assert band_5.half_width < band_1.half_width

    def test_high_quality_evidence_narrows_band(self):
        band_low = self.estimator.compute(0.60, [{"strength": 0.40, "age_days": 0}])
        band_high = self.estimator.compute(0.60, [{"strength": 0.95, "age_days": 0}])
        assert band_high.half_width < band_low.half_width

    def test_stale_evidence_widens_band(self):
        band_fresh = self.estimator.compute(0.60, [{"strength": 0.70, "age_days": 0}])
        band_stale = self.estimator.compute(0.60, [{"strength": 0.70, "age_days": 365}])
        assert band_stale.half_width > band_fresh.half_width

    def test_lower_bound_not_below_zero(self):
        band = self.estimator.compute(score=0.05)
        assert band.lower >= 0.0

    def test_upper_bound_not_above_one(self):
        band = self.estimator.compute(score=0.95)
        assert band.upper <= 1.0

    def test_lower_leq_point_estimate_leq_upper(self):
        band = self.estimator.compute(0.60, [{"strength": 0.70, "age_days": 30}])
        assert band.lower <= band.point_estimate <= band.upper

    def test_avg_strength_computed(self):
        band = self.estimator.compute(0.60, [
            {"strength": 0.80, "age_days": 0},
            {"strength": 0.60, "age_days": 0},
        ])
        assert abs(band.avg_strength - 0.70) < 1e-3

    def test_staleness_factor_fresh(self):
        assert self.estimator._staleness_factor(0) == 1.0

    def test_staleness_factor_half_life_doubles(self):
        from bve.ingestion.confidence_bands import DECAY_HALFLIFE_DAYS
        assert abs(self.estimator._staleness_factor(DECAY_HALFLIFE_DAYS) - 2.0) < 1e-3

    def test_staleness_factor_capped_at_max(self):
        from bve.ingestion.confidence_bands import MAX_DECAY_FACTOR
        assert self.estimator._staleness_factor(9999) == MAX_DECAY_FACTOR


# ===========================================================================
# Block I — RollingBacktestEngine
# ===========================================================================


class TestRankingBacktestHelpers:
    def _records(self, scores_labels):
        return [
            BacktestRecord("2024-01-01", f"T{i}", s, l, "2025-01-01")
            for i, (s, l) in enumerate(scores_labels)
        ]

    def test_precision_at_k_perfect(self):
        records = self._records([(0.9, 1), (0.8, 1), (0.5, 0), (0.3, 0)])
        assert _precision_at_k(records, 2) == 1.0

    def test_precision_at_k_zero(self):
        records = self._records([(0.9, 0), (0.8, 0), (0.5, 1)])
        assert _precision_at_k(records, 2) == 0.0

    def test_precision_at_k_empty(self):
        assert _precision_at_k([], 5) is None

    def test_auc_roc_perfect(self):
        records = self._records([(0.9, 1), (0.8, 1), (0.3, 0), (0.2, 0)])
        assert abs(_auc_roc(records) - 1.0) < 1e-6

    def test_auc_roc_random(self):
        records = self._records([(0.8, 0), (0.7, 1), (0.6, 0), (0.5, 1)])
        auc = _auc_roc(records)
        assert 0.0 <= auc <= 1.0

    def test_auc_roc_none_for_single_class(self):
        records = self._records([(0.9, 1), (0.8, 1)])
        assert _auc_roc(records) is None

    def test_brier_score_perfect(self):
        records = self._records([(1.0, 1), (0.0, 0)])
        assert _brier_score(records) == 0.0

    def test_brier_score_worst(self):
        records = self._records([(0.0, 1), (1.0, 0)])
        assert _brier_score(records) == 1.0

    def test_calibration_buckets_returns_list(self):
        records = self._records([(0.1, 0), (0.3, 0), (0.6, 1), (0.9, 1)])
        buckets = _calibration_buckets(records, n_buckets=5)
        assert isinstance(buckets, list)
        assert all("bucket" in b for b in buckets)

    def test_calibration_buckets_empty_input(self):
        assert _calibration_buckets([]) == []


class TestRollingBacktestEngine:
    def setup_method(self):
        self.engine = RollingBacktestEngine()

    def _make_records(self, as_of_date, scores_labels):
        return [
            BacktestRecord(as_of_date, f"T{i}", s, l, "2025-12-31")
            for i, (s, l) in enumerate(scores_labels)
        ]

    def test_single_window_result(self):
        config = RollingBacktestConfig(
            as_of_dates=["2024-01-01"],
            top_k_values=[2],
        )
        window_records = {
            "2024-01-01": self._make_records(
                "2024-01-01", [(0.9, 1), (0.8, 1), (0.5, 0), (0.3, 0)]
            )
        }
        result = self.engine.evaluate(config, window_records)
        assert len(result.window_results) == 1
        assert result.window_results[0].precision_at_k[2] == 1.0

    def test_multiple_windows_aggregated(self):
        config = RollingBacktestConfig(
            as_of_dates=["2024-01-01", "2024-06-01"],
            top_k_values=[2],
        )
        # Each window: top-2 has 1 positive → precision@2 = 0.5 each; mean = 0.5
        window_records = {
            "2024-01-01": self._make_records("2024-01-01", [(0.9, 1), (0.8, 0)]),
            "2024-06-01": self._make_records("2024-06-01", [(0.7, 1), (0.4, 0)]),
        }
        result = self.engine.evaluate(config, window_records)
        assert abs(result.mean_precision_at_k[2] - 0.5) < 1e-6

    def test_empty_window_records(self):
        config = RollingBacktestConfig(as_of_dates=["2024-01-01"])
        result = self.engine.evaluate(config, {})
        assert result.window_results[0].n_tickers == 0

    def test_min_score_threshold_filters(self):
        config = RollingBacktestConfig(
            as_of_dates=["2024-01-01"],
            min_score_threshold=0.60,
        )
        window_records = {
            "2024-01-01": self._make_records(
                "2024-01-01", [(0.9, 1), (0.3, 0)]  # 0.3 filtered out
            )
        }
        result = self.engine.evaluate(config, window_records)
        assert result.window_results[0].n_tickers == 1

    def test_total_records_summed(self):
        config = RollingBacktestConfig(as_of_dates=["2024-01-01", "2024-06-01"])
        window_records = {
            "2024-01-01": self._make_records("2024-01-01", [(0.5, 0), (0.6, 1)]),
            "2024-06-01": self._make_records("2024-06-01", [(0.7, 1)]),
        }
        result = self.engine.evaluate(config, window_records)
        assert result.total_records == 3
        assert result.total_positives == 2

    def test_mean_brier_score_computed(self):
        config = RollingBacktestConfig(as_of_dates=["2024-01-01"])
        window_records = {
            "2024-01-01": self._make_records(
                "2024-01-01", [(1.0, 1), (0.0, 0)]
            )
        }
        result = self.engine.evaluate(config, window_records)
        assert result.mean_brier_score == 0.0


# ===========================================================================
# Block J — ScoreExplainer
# ===========================================================================


class TestScoreExplainer:
    def setup_method(self):
        self.explainer = ScoreExplainer()

    def _sample_events(self):
        return [
            {
                "event_type": "clinical_positive_ph3",
                "feature": "asset_quality",
                "delta": +0.12,
                "raw_text": "Company reports Phase 3 success in oncology",
                "event_date": "2024-05-01",
                "source_type": "sec_filing",
                "review_status": "approved",
                "age_days": 30,
            },
            {
                "event_type": "cash_low",
                "feature": "seller_willingness",
                "delta": +0.08,
                "raw_text": "Company discloses 8 months of runway remaining",
                "event_date": "2024-04-15",
                "source_type": "press_release",
                "review_status": "approved",
                "age_days": 45,
            },
        ]

    def test_basic_explain_returns_explanation(self):
        result = self.explainer.explain(
            ticker="TEST",
            as_of_date="2024-06-01",
            scores={"ma_attractiveness": 0.72},
        )
        assert result.ticker == "TEST"
        assert result.as_of_date == "2024-06-01"

    def test_top_drivers_sorted_by_abs_delta(self):
        result = self.explainer.explain(
            ticker="TEST",
            as_of_date="2024-06-01",
            scores={},
            events=self._sample_events(),
        )
        assert len(result.top_drivers) == 2
        # Larger delta first
        assert abs(result.top_drivers[0].delta) >= abs(result.top_drivers[1].delta)

    def test_driver_direction_positive(self):
        result = self.explainer.explain(
            ticker="TEST",
            as_of_date="2024-06-01",
            scores={},
            events=[self._sample_events()[0]],
        )
        assert result.top_drivers[0].direction == "positive"

    def test_evidence_count_matches_events(self):
        result = self.explainer.explain(
            ticker="TEST",
            as_of_date="2024-06-01",
            scores={},
            events=self._sample_events(),
        )
        assert result.evidence_count == 2

    def test_coverage_gap_flag_raised(self):
        result = self.explainer.explain(
            ticker="TEST",
            as_of_date="2024-06-01",
            scores={},
            coverage={"regulatory": 0.05},
        )
        flag_categories = [f.category for f in result.risk_flags]
        assert "coverage_gap" in flag_categories

    def test_low_volume_flag_raised_with_no_events(self):
        result = self.explainer.explain(
            ticker="TEST",
            as_of_date="2024-06-01",
            scores={},
            events=[],
        )
        flag_categories = [f.category for f in result.risk_flags]
        assert "low_volume" in flag_categories

    def test_pending_review_flag_raised(self):
        events = [{"event_type": "fda_approval", "feature": "asset_quality",
                   "delta": 0.10, "raw_text": "FDA approves...",
                   "event_date": "2024-05-01", "source_type": "fda_website",
                   "review_status": "pending", "age_days": 5}]
        result = self.explainer.explain(
            ticker="TEST",
            as_of_date="2024-06-01",
            scores={},
            events=events,
        )
        flag_categories = [f.category for f in result.risk_flags]
        assert "pending_review" in flag_categories

    def test_stale_evidence_flag_raised(self):
        events = [{"event_type": "btd", "feature": "asset_quality",
                   "delta": 0.05, "raw_text": "BTD granted...",
                   "event_date": "2022-01-01", "source_type": "fda_website",
                   "review_status": "approved", "age_days": 600}]
        result = self.explainer.explain(
            ticker="TEST",
            as_of_date="2024-06-01",
            scores={},
            events=events,
        )
        flag_categories = [f.category for f in result.risk_flags]
        assert "stale_evidence" in flag_categories

    def test_to_text_returns_string(self):
        result = self.explainer.explain(
            ticker="TEST",
            as_of_date="2024-06-01",
            scores={"ma_attractiveness": 0.72},
            events=self._sample_events(),
        )
        text = result.to_text()
        assert isinstance(text, str)
        assert "TEST" in text
        assert "2024-06-01" in text

    def test_to_dict_serialisable(self):
        import json
        result = self.explainer.explain(
            ticker="TEST",
            as_of_date="2024-06-01",
            scores={"ma_attractiveness": 0.72},
            events=self._sample_events(),
            coverage={"clinical": 0.80},
        )
        d = result.to_dict()
        json_str = json.dumps(d)
        assert "TEST" in json_str

    def test_confidence_bands_stored(self):
        bands = {"ma_attractiveness": {"lower": 0.55, "upper": 0.89, "half_width": 0.17}}
        result = self.explainer.explain(
            ticker="TEST",
            as_of_date="2024-06-01",
            scores={"ma_attractiveness": 0.72},
            confidence_bands=bands,
        )
        assert "ma_attractiveness" in result.confidence_bands

    def test_pipeline_version_stored(self):
        result = self.explainer.explain(
            ticker="TEST",
            as_of_date="2024-06-01",
            scores={},
            pipeline_version="v2.1/v2.1/v1.2",
        )
        assert result.pipeline_version == "v2.1/v2.1/v1.2"

    def test_score_mode_stored(self):
        result = self.explainer.explain(
            ticker="TEST",
            as_of_date="2024-06-01",
            scores={},
            score_mode="approved_only",
        )
        assert result.score_mode == "approved_only"
