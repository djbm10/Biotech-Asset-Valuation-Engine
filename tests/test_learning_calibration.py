"""Tests for learning calibration loop: prediction log, outcome linker,
postmortem, calibration metrics, shadow backtest, and weight promoter."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from bve.learning.prediction_log import (
    PredictionLog,
    DecisionPredictionOutcome as PredictionOutcome,
    DecisionPredictionRecord as PredictionRecord,
)
from bve.learning.outcome_linker import OutcomeLinker, OutcomeSource
from bve.learning.postmortem import (
    ErrorCategory,
    PostmortemResult,
    PostmortemStore,
    binary_outcome,
    classify_error,
    run_postmortem,
)
from bve.learning.calibration import (
    CalibrationBucket,
    CalibrationReport,
    build_calibration_report,
    compute_brier_score,
    compute_calibration_buckets,
)
from bve.learning.shadow_backtest import BacktestEntry, BacktestSummary as ShadowBacktestResult, run_shadow_backtest
from bve.learning.weight_promoter import (
    PromotionStatus,
    SuggestionType,
    WeightPromoter,
    WeightSuggestion,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 21, 12, 0, 0, tzinfo=timezone.utc)


def _make_record(
    asset_id: str = "ASSET-1",
    ticker: str = "TICK",
    predicted_pos: float = 0.70,
    predicted_return: float = 0.30,
    asymmetry_score: float = 2.0,
    thesis_strength: str = "strong",
    action_taken: str = "add",
    domain_scores: dict | None = None,
    outcome: PredictionOutcome = PredictionOutcome.PENDING,
    realized_return: float | None = None,
    resolved_at: datetime | None = None,
) -> PredictionRecord:
    if domain_scores is None:
        domain_scores = {"science": 0.70, "competition": 0.60, "financing": 0.50}
    return PredictionRecord(
        prediction_id=str(uuid.uuid4()),
        asset_id=asset_id,
        ticker=ticker,
        predicted_pos=predicted_pos,
        predicted_return=predicted_return,
        asymmetry_score=asymmetry_score,
        thesis_strength=thesis_strength,
        action_taken=action_taken,
        domain_scores=domain_scores,
        predicted_at=_NOW,
        outcome=outcome,
        realized_return=realized_return,
        resolved_at=resolved_at,
    )


def _make_log(*records: PredictionRecord) -> PredictionLog:
    log = PredictionLog(":memory:")
    for r in records:
        log.log(r)
    return log


# ---------------------------------------------------------------------------
# TestPredictionLog
# ---------------------------------------------------------------------------


class TestPredictionLog:
    def test_log_inserts_and_returns_prediction_id(self):
        log = PredictionLog(":memory:")
        record = _make_record()
        pid = log.log(record)
        assert pid == record.prediction_id

    def test_get_retrieves_by_id(self):
        log = PredictionLog(":memory:")
        record = _make_record(asset_id="AAA")
        log.log(record)
        fetched = log.get(record.prediction_id)
        assert fetched is not None
        assert fetched.asset_id == "AAA"

    def test_get_returns_none_for_missing(self):
        log = PredictionLog(":memory:")
        assert log.get("nonexistent") is None

    def test_resolve_updates_outcome(self):
        log = PredictionLog(":memory:")
        record = _make_record()
        log.log(record)
        log.resolve(record.prediction_id, PredictionOutcome.CORRECT, 0.25)
        fetched = log.get(record.prediction_id)
        assert fetched.outcome == PredictionOutcome.CORRECT

    def test_resolve_updates_realized_return(self):
        log = PredictionLog(":memory:")
        record = _make_record()
        log.log(record)
        log.resolve(record.prediction_id, PredictionOutcome.CORRECT, 0.35)
        fetched = log.get(record.prediction_id)
        assert fetched.realized_return == pytest.approx(0.35)

    def test_resolve_sets_resolved_at(self):
        log = PredictionLog(":memory:")
        record = _make_record()
        log.log(record)
        ts = datetime(2026, 5, 1, tzinfo=timezone.utc)
        log.resolve(record.prediction_id, PredictionOutcome.CORRECT, 0.20, resolved_at=ts)
        fetched = log.get(record.prediction_id)
        assert fetched.resolved_at is not None

    def test_pending_returns_unresolved(self):
        log = PredictionLog(":memory:")
        r1 = _make_record()
        r2 = _make_record()
        log.log(r1)
        log.log(r2)
        log.resolve(r1.prediction_id, PredictionOutcome.CORRECT, 0.20)
        pending = log.pending()
        assert len(pending) == 1
        assert pending[0].prediction_id == r2.prediction_id

    def test_pending_filters_by_asset_id(self):
        log = PredictionLog(":memory:")
        r1 = _make_record(asset_id="A1")
        r2 = _make_record(asset_id="A2")
        log.log(r1)
        log.log(r2)
        pending = log.pending(asset_id="A1")
        assert len(pending) == 1
        assert pending[0].asset_id == "A1"

    def test_resolved_returns_resolved_records(self):
        log = PredictionLog(":memory:")
        r1 = _make_record()
        r2 = _make_record()
        log.log(r1)
        log.log(r2)
        log.resolve(r1.prediction_id, PredictionOutcome.CORRECT, 0.20)
        resolved = log.resolved()
        assert len(resolved) == 1
        assert resolved[0].prediction_id == r1.prediction_id

    def test_all_returns_everything(self):
        log = PredictionLog(":memory:")
        r1 = _make_record()
        r2 = _make_record()
        log.log(r1)
        log.log(r2)
        log.resolve(r1.prediction_id, PredictionOutcome.CORRECT, 0.20)
        all_records = log.all()
        assert len(all_records) == 2

    def test_count_is_correct(self):
        log = PredictionLog(":memory:")
        assert log.count() == 0
        log.log(_make_record())
        log.log(_make_record())
        assert log.count() == 2

    def test_matched_pairs_returns_tuples(self):
        log = PredictionLog(":memory:")
        r = _make_record(predicted_pos=0.70)
        log.log(r)
        log.resolve(r.prediction_id, PredictionOutcome.CORRECT, 0.25)
        pairs = log.matched_pairs()
        assert len(pairs) == 1
        predicted, actual = pairs[0]
        assert predicted == pytest.approx(0.70)
        assert actual == pytest.approx(1.0)

    def test_matched_pairs_correct_is_1(self):
        log = PredictionLog(":memory:")
        r = _make_record(predicted_pos=0.8)
        log.log(r)
        log.resolve(r.prediction_id, PredictionOutcome.CORRECT, 0.40)
        pairs = log.matched_pairs()
        assert pairs[0][1] == pytest.approx(1.0)

    def test_matched_pairs_incorrect_is_0(self):
        log = PredictionLog(":memory:")
        r = _make_record(predicted_pos=0.8)
        log.log(r)
        log.resolve(r.prediction_id, PredictionOutcome.INCORRECT, -0.30)
        pairs = log.matched_pairs()
        assert pairs[0][1] == pytest.approx(0.0)

    def test_matched_pairs_partial_is_half(self):
        log = PredictionLog(":memory:")
        r = _make_record(predicted_pos=0.6)
        log.log(r)
        log.resolve(r.prediction_id, PredictionOutcome.PARTIAL, 0.05)
        pairs = log.matched_pairs()
        assert pairs[0][1] == pytest.approx(0.5)

    def test_pending_excluded_from_matched_pairs(self):
        log = PredictionLog(":memory:")
        r = _make_record()
        log.log(r)
        # not resolved
        pairs = log.matched_pairs()
        assert len(pairs) == 0

    def test_multiple_assets_correct_filtering(self):
        log = PredictionLog(":memory:")
        r1 = _make_record(asset_id="X")
        r2 = _make_record(asset_id="Y")
        log.log(r1)
        log.log(r2)
        log.resolve(r1.prediction_id, PredictionOutcome.CORRECT, 0.20)
        pending_x = log.pending(asset_id="X")
        pending_y = log.pending(asset_id="Y")
        assert len(pending_x) == 0
        assert len(pending_y) == 1

    def test_resolved_filters_by_asset_id(self):
        log = PredictionLog(":memory:")
        r1 = _make_record(asset_id="X")
        r2 = _make_record(asset_id="Y")
        log.log(r1)
        log.log(r2)
        log.resolve(r1.prediction_id, PredictionOutcome.CORRECT, 0.20)
        resolved_x = log.resolved(asset_id="X")
        assert len(resolved_x) == 1
        resolved_y = log.resolved(asset_id="Y")
        assert len(resolved_y) == 0


# ---------------------------------------------------------------------------
# TestOutcomeLinker
# ---------------------------------------------------------------------------


class TestOutcomeLinker:
    def _setup(self):
        log = PredictionLog(":memory:")
        linker = OutcomeLinker(log)
        return log, linker

    def test_link_price_return_correct_same_sign_above_threshold(self):
        log, linker = self._setup()
        r = _make_record(asset_id="A", predicted_return=0.30)
        log.log(r)
        outcomes = linker.link_price_return("A", 0.25, _NOW)
        assert len(outcomes) == 1
        assert outcomes[0].outcome == PredictionOutcome.CORRECT

    def test_link_price_return_incorrect_opposite_sign_above_threshold(self):
        log, linker = self._setup()
        r = _make_record(asset_id="A", predicted_return=0.30)
        log.log(r)
        outcomes = linker.link_price_return("A", -0.20, _NOW)
        assert outcomes[0].outcome == PredictionOutcome.INCORRECT

    def test_link_price_return_partial_within_threshold(self):
        log, linker = self._setup()
        r = _make_record(asset_id="A", predicted_return=0.30)
        log.log(r)
        outcomes = linker.link_price_return("A", 0.05, _NOW, threshold=0.10)
        assert outcomes[0].outcome == PredictionOutcome.PARTIAL

    def test_link_price_return_resolves_all_pending(self):
        log, linker = self._setup()
        r1 = _make_record(asset_id="A", predicted_return=0.20)
        r2 = _make_record(asset_id="A", predicted_return=0.15)
        log.log(r1)
        log.log(r2)
        outcomes = linker.link_price_return("A", 0.25, _NOW)
        assert len(outcomes) == 2
        assert len(log.pending(asset_id="A")) == 0

    def test_link_event_trial_success_positive_prediction_correct(self):
        log, linker = self._setup()
        r = _make_record(asset_id="B", predicted_return=0.40)
        log.log(r)
        outcomes = linker.link_event("B", "trial_success", 0.45, "Phase 3 win", _NOW)
        assert outcomes[0].outcome == PredictionOutcome.CORRECT

    def test_link_event_trial_failure_positive_prediction_incorrect(self):
        log, linker = self._setup()
        r = _make_record(asset_id="B", predicted_return=0.40)
        log.log(r)
        outcomes = linker.link_event("B", "trial_failure", -0.45, "Phase 3 failed", _NOW)
        assert outcomes[0].outcome == PredictionOutcome.INCORRECT

    def test_link_event_fda_approval_correct(self):
        log, linker = self._setup()
        r = _make_record(asset_id="C", predicted_return=0.25)
        log.log(r)
        outcomes = linker.link_event("C", "fda_approval", 0.30, "FDA approved", _NOW)
        assert outcomes[0].outcome == PredictionOutcome.CORRECT

    def test_link_event_crl_negative_prediction_correct(self):
        log, linker = self._setup()
        r = _make_record(asset_id="C", predicted_return=-0.20)
        log.log(r)
        outcomes = linker.link_event("C", "crl", -0.30, "CRL received", _NOW)
        assert outcomes[0].outcome == PredictionOutcome.CORRECT

    def test_link_event_returns_outcome_record_list(self):
        log, linker = self._setup()
        r = _make_record(asset_id="D", predicted_return=0.30)
        log.log(r)
        outcomes = linker.link_event("D", "trial_success", 0.35, "win", _NOW)
        assert isinstance(outcomes, list)
        assert len(outcomes) == 1
        assert outcomes[0].prediction_id == r.prediction_id

    def test_unresolved_count_decrements_after_linking(self):
        log, linker = self._setup()
        r1 = _make_record(asset_id="E", predicted_return=0.30)
        r2 = _make_record(asset_id="E", predicted_return=0.20)
        log.log(r1)
        log.log(r2)
        assert linker.unresolved_count(asset_id="E") == 2
        linker.link_price_return("E", 0.25, _NOW)
        assert linker.unresolved_count(asset_id="E") == 0

    def test_all_outcomes_accumulates(self):
        log, linker = self._setup()
        r1 = _make_record(asset_id="F", predicted_return=0.30)
        r2 = _make_record(asset_id="G", predicted_return=0.20)
        log.log(r1)
        log.log(r2)
        linker.link_price_return("F", 0.25, _NOW)
        linker.link_price_return("G", 0.30, _NOW)
        assert len(linker.all_outcomes()) == 2

    def test_link_price_return_correct_negative_direction(self):
        log, linker = self._setup()
        r = _make_record(asset_id="H", predicted_return=-0.20)
        log.log(r)
        outcomes = linker.link_price_return("H", -0.25, _NOW)
        assert outcomes[0].outcome == PredictionOutcome.CORRECT

    def test_link_event_crl_positive_prediction_incorrect(self):
        log, linker = self._setup()
        r = _make_record(asset_id="I", predicted_return=0.30)
        log.log(r)
        outcomes = linker.link_event("I", "crl", -0.30, "CRL received", _NOW)
        assert outcomes[0].outcome == PredictionOutcome.INCORRECT

    def test_unresolved_count_all_assets(self):
        log, linker = self._setup()
        r1 = _make_record(asset_id="J1", predicted_return=0.20)
        r2 = _make_record(asset_id="J2", predicted_return=0.30)
        log.log(r1)
        log.log(r2)
        assert linker.unresolved_count() == 2


# ---------------------------------------------------------------------------
# TestPostmortem
# ---------------------------------------------------------------------------


class TestPostmortem:
    def _correct_record(self) -> PredictionRecord:
        return _make_record(
            predicted_pos=0.70,
            predicted_return=0.30,
            outcome=PredictionOutcome.CORRECT,
            realized_return=0.25,
        )

    def _incorrect_record(self, **kwargs) -> PredictionRecord:
        defaults = dict(
            predicted_pos=0.70,
            predicted_return=0.30,
            outcome=PredictionOutcome.INCORRECT,
            realized_return=-0.20,
        )
        defaults.update(kwargs)
        return _make_record(**defaults)

    def test_binary_outcome_correct_is_1(self):
        r = _make_record(outcome=PredictionOutcome.CORRECT)
        assert binary_outcome(r) == pytest.approx(1.0)

    def test_binary_outcome_incorrect_is_0(self):
        r = _make_record(outcome=PredictionOutcome.INCORRECT)
        assert binary_outcome(r) == pytest.approx(0.0)

    def test_binary_outcome_partial_is_half(self):
        r = _make_record(outcome=PredictionOutcome.PARTIAL)
        assert binary_outcome(r) == pytest.approx(0.5)

    def test_binary_outcome_pending_is_half(self):
        r = _make_record(outcome=PredictionOutcome.PENDING)
        assert binary_outcome(r) == pytest.approx(0.5)

    def test_classify_error_correct(self):
        r = self._correct_record()
        assert classify_error(r) == ErrorCategory.CORRECT

    def test_classify_error_unclassified_for_pending(self):
        r = _make_record(outcome=PredictionOutcome.PENDING)
        assert classify_error(r) == ErrorCategory.UNCLASSIFIED

    def test_classify_error_pos_error_large_miss(self):
        # predicted_pos=0.95, INCORRECT → binary=0.0 → pos_error=0.95 > 0.25
        r = _make_record(
            predicted_pos=0.95,
            predicted_return=0.30,
            domain_scores={"science": 0.60, "competition": 0.60, "financing": 0.60},
            outcome=PredictionOutcome.INCORRECT,
            realized_return=-0.30,
        )
        assert classify_error(r) == ErrorCategory.POS_ERROR

    def test_classify_error_timing_error_for_partial(self):
        # predicted_pos=0.65, PARTIAL → binary=0.5 → pos_error=0.15, not > 0.25 → TIMING
        r = _make_record(
            predicted_pos=0.65,
            predicted_return=0.20,
            domain_scores={"science": 0.60, "competition": 0.60, "financing": 0.60},
            outcome=PredictionOutcome.PARTIAL,
            realized_return=0.05,
        )
        assert classify_error(r) == ErrorCategory.TIMING_ERROR

    def test_classify_error_financing_error(self):
        # predicted_pos=0.20, INCORRECT → binary=0.0, pos_error=0.20 ≤ 0.25 → check domains
        r = _make_record(
            predicted_pos=0.20,
            predicted_return=0.30,
            domain_scores={"science": 0.60, "competition": 0.60, "financing": 0.20},
            outcome=PredictionOutcome.INCORRECT,
            realized_return=-0.25,
        )
        assert classify_error(r) == ErrorCategory.FINANCING_ERROR

    def test_classify_error_science_error(self):
        # predicted_pos=0.20, INCORRECT → binary=0.0, pos_error=0.20 ≤ 0.25 → check domains
        r = _make_record(
            predicted_pos=0.20,
            predicted_return=0.30,
            domain_scores={"science": 0.25, "competition": 0.60, "financing": 0.60},
            outcome=PredictionOutcome.INCORRECT,
            realized_return=-0.25,
        )
        assert classify_error(r) == ErrorCategory.SCIENCE_ERROR

    def test_classify_error_competition_error(self):
        # predicted_pos=0.20, INCORRECT → binary=0.0, pos_error=0.20 ≤ 0.25 → check domains
        r = _make_record(
            predicted_pos=0.20,
            predicted_return=0.30,
            domain_scores={"science": 0.60, "competition": 0.20, "financing": 0.60},
            outcome=PredictionOutcome.INCORRECT,
            realized_return=-0.25,
        )
        assert classify_error(r) == ErrorCategory.COMPETITION_ERROR

    def test_classify_error_market_drift_low_conviction(self):
        # predicted_pos=0.20, predicted_return=0.05 (small conviction), no domain triggers
        r = _make_record(
            predicted_pos=0.20,
            predicted_return=0.05,
            domain_scores={"science": 0.60, "competition": 0.60, "financing": 0.60},
            outcome=PredictionOutcome.INCORRECT,
            realized_return=-0.10,
        )
        assert classify_error(r) == ErrorCategory.MARKET_DRIFT

    def test_classify_error_thesis_error_default(self):
        # predicted_pos=0.20, INCORRECT, no domain triggers, high predicted_return → THESIS_ERROR
        r = _make_record(
            predicted_pos=0.20,
            predicted_return=0.40,
            domain_scores={"science": 0.60, "competition": 0.60, "financing": 0.60},
            outcome=PredictionOutcome.INCORRECT,
            realized_return=-0.20,
        )
        assert classify_error(r) == ErrorCategory.THESIS_ERROR

    def test_run_postmortem_returns_result(self):
        r = self._correct_record()
        result = run_postmortem(r)
        assert isinstance(result, PostmortemResult)
        assert result.prediction_id == r.prediction_id

    def test_postmortem_store_add_get(self):
        store = PostmortemStore()
        r = self._correct_record()
        result = run_postmortem(r)
        store.add(result)
        fetched = store.get(r.prediction_id)
        assert fetched is not None
        assert fetched.prediction_id == r.prediction_id

    def test_postmortem_store_all(self):
        store = PostmortemStore()
        for _ in range(3):
            r = _make_record(outcome=PredictionOutcome.CORRECT, realized_return=0.20)
            store.add(run_postmortem(r))
        assert len(store.all()) == 3

    def test_postmortem_store_by_category(self):
        store = PostmortemStore()
        r_correct = _make_record(outcome=PredictionOutcome.CORRECT, realized_return=0.20)
        r_incorrect = _make_record(
            predicted_pos=0.60,
            predicted_return=0.40,
            domain_scores={"science": 0.60, "competition": 0.60, "financing": 0.60},
            outcome=PredictionOutcome.INCORRECT,
            realized_return=-0.20,
        )
        store.add(run_postmortem(r_correct))
        store.add(run_postmortem(r_incorrect))
        correct_list = store.by_category(ErrorCategory.CORRECT)
        assert len(correct_list) == 1

    def test_postmortem_store_error_distribution(self):
        store = PostmortemStore()
        r1 = _make_record(outcome=PredictionOutcome.CORRECT, realized_return=0.20)
        r2 = _make_record(
            predicted_pos=0.60,
            predicted_return=0.40,
            domain_scores={"science": 0.60, "competition": 0.60, "financing": 0.60},
            outcome=PredictionOutcome.INCORRECT,
            realized_return=-0.20,
        )
        store.add(run_postmortem(r1))
        store.add(run_postmortem(r2))
        dist = store.error_distribution()
        assert dist.get("correct", 0) == 1
        assert "thesis_error" in dist or "market_drift" in dist or "pos_error" in dist


# ---------------------------------------------------------------------------
# TestCalibration
# ---------------------------------------------------------------------------


class TestCalibration:
    def test_compute_brier_score_perfect(self):
        pairs = [(1.0, 1.0), (0.0, 0.0), (1.0, 1.0)]
        assert compute_brier_score(pairs) == pytest.approx(0.0)

    def test_compute_brier_score_all_wrong(self):
        pairs = [(1.0, 0.0), (1.0, 0.0)]
        assert compute_brier_score(pairs) == pytest.approx(1.0)

    def test_compute_brier_score_empty(self):
        assert compute_brier_score([]) == pytest.approx(0.0)

    def test_compute_brier_score_formula(self):
        pairs = [(0.8, 1.0), (0.4, 0.0)]
        expected = ((0.8 - 1.0) ** 2 + (0.4 - 0.0) ** 2) / 2
        assert compute_brier_score(pairs) == pytest.approx(expected)

    def test_compute_calibration_buckets_correct_binning(self):
        pairs = [(0.05, 1.0), (0.15, 0.0), (0.85, 1.0)]
        buckets = compute_calibration_buckets(pairs, n_bins=10)
        # Should have 3 buckets (0-0.1, 0.1-0.2, 0.8-0.9)
        assert len(buckets) == 3
        bucket_lowers = [b.bin_lower for b in buckets]
        assert pytest.approx(0.0) in bucket_lowers
        assert pytest.approx(0.1) in bucket_lowers

    def test_compute_calibration_buckets_skips_empty(self):
        pairs = [(0.05, 1.0)]
        buckets = compute_calibration_buckets(pairs, n_bins=10)
        # Only 1 non-empty bucket
        assert len(buckets) == 1

    def test_compute_calibration_buckets_empty_input(self):
        buckets = compute_calibration_buckets([])
        assert buckets == []

    def test_build_calibration_report_n_total(self):
        log = PredictionLog(":memory:")
        for _ in range(5):
            r = _make_record()
            log.log(r)
        report = build_calibration_report(log)
        assert report.n_total == 5

    def test_build_calibration_report_n_resolved(self):
        log = PredictionLog(":memory:")
        r1 = _make_record()
        r2 = _make_record()
        log.log(r1)
        log.log(r2)
        log.resolve(r1.prediction_id, PredictionOutcome.CORRECT, 0.20)
        report = build_calibration_report(log)
        assert report.n_resolved == 1

    def test_build_calibration_report_brier_score(self):
        log = PredictionLog(":memory:")
        r = _make_record(predicted_pos=1.0)
        log.log(r)
        log.resolve(r.prediction_id, PredictionOutcome.CORRECT, 0.20)
        report = build_calibration_report(log)
        # perfect: (1.0 - 1.0)^2 = 0
        assert report.brier_score == pytest.approx(0.0)

    def test_build_calibration_report_overall_bias_overconfident(self):
        log = PredictionLog(":memory:")
        # predict pos=0.9, outcome=INCORRECT → binary=0.0 → bias = 0.9 > 0
        r = _make_record(predicted_pos=0.9)
        log.log(r)
        log.resolve(r.prediction_id, PredictionOutcome.INCORRECT, -0.20)
        report = build_calibration_report(log)
        assert report.overall_bias > 0

    def test_build_calibration_report_overall_bias_underconfident(self):
        log = PredictionLog(":memory:")
        # predict pos=0.1, outcome=CORRECT → binary=1.0 → bias = 0.1 - 1.0 < 0
        r = _make_record(predicted_pos=0.1)
        log.log(r)
        log.resolve(r.prediction_id, PredictionOutcome.CORRECT, 0.20)
        report = build_calibration_report(log)
        assert report.overall_bias < 0

    def test_skill_score_positive_for_useful_model(self):
        log = PredictionLog(":memory:")
        # Good predictions: high pos → CORRECT, low pos → INCORRECT (well calibrated)
        for _ in range(4):
            r = _make_record(predicted_pos=0.80)
            log.log(r)
            log.resolve(r.prediction_id, PredictionOutcome.CORRECT, 0.25)
        for _ in range(2):
            r = _make_record(predicted_pos=0.20)
            log.log(r)
            log.resolve(r.prediction_id, PredictionOutcome.INCORRECT, -0.15)
        report = build_calibration_report(log)
        assert report.skill_score > 0

    def test_skill_score_nonpositive_for_no_skill_model(self):
        log = PredictionLog(":memory:")
        # All predictions wrong: high pos → INCORRECT
        for _ in range(5):
            r = _make_record(predicted_pos=0.90)
            log.log(r)
            log.resolve(r.prediction_id, PredictionOutcome.INCORRECT, -0.25)
        report = build_calibration_report(log)
        # Model worse than or equal to no-skill baseline
        assert report.skill_score <= 0

    def test_buckets_have_correct_bin_boundaries(self):
        pairs = [(0.05, 1.0), (0.15, 0.0)]
        buckets = compute_calibration_buckets(pairs, n_bins=10)
        # First bucket [0.0, 0.1)
        first = next(b for b in buckets if b.bin_lower == pytest.approx(0.0))
        assert first.bin_upper == pytest.approx(0.1)

    def test_empty_log_report(self):
        log = PredictionLog(":memory:")
        report = build_calibration_report(log)
        assert report.n_total == 0
        assert report.n_resolved == 0
        assert report.brier_score == pytest.approx(0.0)

    def test_brier_score_half_prediction(self):
        pairs = [(0.5, 1.0)]
        assert compute_brier_score(pairs) == pytest.approx(0.25)

    def test_calibration_bucket_calibration_error(self):
        # mean_predicted=0.8, mean_actual=0.0 → error=0.8
        pairs = [(0.8, 0.0)]
        buckets = compute_calibration_buckets(pairs)
        assert buckets[0].calibration_error == pytest.approx(0.8)

    def test_build_report_buckets_non_empty(self):
        log = PredictionLog(":memory:")
        r = _make_record(predicted_pos=0.7)
        log.log(r)
        log.resolve(r.prediction_id, PredictionOutcome.CORRECT, 0.20)
        report = build_calibration_report(log)
        assert len(report.buckets) >= 1


# ---------------------------------------------------------------------------
# TestShadowBacktest
# ---------------------------------------------------------------------------


def _make_entry(
    predicted_return: float = 0.30,
    realized_return: float = 0.25,
    predicted_pos: float = 0.70,
    action_taken: str = "add",
    asset_id: str = "A",
) -> BacktestEntry:
    return BacktestEntry(
        asset_id=asset_id,
        ticker="TICK",
        predicted_pos=predicted_pos,
        predicted_return=predicted_return,
        asymmetry_score=2.0,
        thesis_strength="strong",
        action_taken=action_taken,
        domain_scores={"science": 0.70},
        predicted_at=_NOW,
        realized_return=realized_return,
        realized_at=_NOW,
    )


class TestShadowBacktest:
    def test_n_entries_correct(self):
        entries = [_make_entry() for _ in range(5)]
        result = run_shadow_backtest(entries)
        assert result.n_entries == 5

    def test_brier_score_computed(self):
        entries = [_make_entry(predicted_pos=1.0, realized_return=0.20)]
        result = run_shadow_backtest(entries)
        # realized > 0 → binary=1.0; predicted_pos=1.0 → brier=(1-1)^2=0
        assert result.brier_score == pytest.approx(0.0)

    def test_hit_rate_all_correct(self):
        entries = [_make_entry(predicted_return=0.30, realized_return=0.25) for _ in range(4)]
        result = run_shadow_backtest(entries)
        assert result.hit_rate == pytest.approx(1.0)

    def test_hit_rate_all_wrong(self):
        entries = [_make_entry(predicted_return=0.30, realized_return=-0.25) for _ in range(4)]
        result = run_shadow_backtest(entries)
        assert result.hit_rate == pytest.approx(0.0)

    def test_return_correlation_perfect(self):
        entries = [_make_entry(predicted_return=x, realized_return=x) for x in [0.1, 0.2, 0.3]]
        result = run_shadow_backtest(entries)
        assert result.return_correlation == pytest.approx(1.0, abs=1e-6)

    def test_return_correlation_opposite(self):
        # perfectly opposite
        entries = [
            _make_entry(predicted_return=0.10, realized_return=-0.10),
            _make_entry(predicted_return=0.20, realized_return=-0.20),
            _make_entry(predicted_return=0.30, realized_return=-0.30),
        ]
        result = run_shadow_backtest(entries)
        assert result.return_correlation == pytest.approx(-1.0, abs=1e-6)

    def test_return_correlation_zero_std(self):
        # All same predicted return → std=0 → correlation=0
        entries = [_make_entry(predicted_return=0.20, realized_return=x) for x in [0.1, 0.2, 0.3]]
        result = run_shadow_backtest(entries)
        assert result.return_correlation == pytest.approx(0.0)

    def test_mean_abs_return_error(self):
        entries = [_make_entry(predicted_return=0.30, realized_return=0.20)]
        result = run_shadow_backtest(entries)
        assert result.mean_abs_return_error == pytest.approx(0.10)

    def test_entries_by_action_count(self):
        entries = [
            _make_entry(action_taken="add"),
            _make_entry(action_taken="add"),
            _make_entry(action_taken="hold"),
        ]
        result = run_shadow_backtest(entries)
        assert result.entries_by_action["add"] == 2
        assert result.entries_by_action["hold"] == 1

    def test_empty_entries(self):
        result = run_shadow_backtest([])
        assert result.n_entries == 0
        assert result.brier_score == pytest.approx(0.0)
        assert result.hit_rate == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# TestWeightPromoter
# ---------------------------------------------------------------------------


def _make_calibration_report(
    brier_score: float = 0.30,
    overall_bias: float = 0.15,
    n_resolved: int = 10,
) -> CalibrationReport:
    return CalibrationReport(
        n_total=n_resolved,
        n_resolved=n_resolved,
        brier_score=brier_score,
        mean_calibration_error=0.10,
        max_calibration_error=0.20,
        overall_bias=overall_bias,
        buckets=[],
        skill_score=0.30,
    )


def _make_postmortem_store_with_errors(
    category: ErrorCategory, count: int
) -> PostmortemStore:
    store = PostmortemStore()
    for _ in range(count):
        result = PostmortemResult(
            prediction_id=str(uuid.uuid4()),
            asset_id="A",
            error_category=category,
            predicted_pos=0.70,
            realized_outcome=PredictionOutcome.INCORRECT,
            realized_return=-0.20,
            predicted_return=0.30,
            pos_error=0.20,
            return_error=0.50,
            notes="",
        )
        store.add(result)
    return store


class TestWeightPromoter:
    def test_generate_suggestions_recalibrate_pos_prior(self):
        promoter = WeightPromoter()
        calibration = _make_calibration_report(brier_score=0.30, overall_bias=0.15)
        store = PostmortemStore()
        suggestions = promoter.generate_suggestions(calibration, store, {})
        types = [s.suggestion_type for s in suggestions]
        assert SuggestionType.RECALIBRATE_POS_PRIOR in types

    def test_generate_suggestions_increase_competition_weight(self):
        promoter = WeightPromoter()
        calibration = _make_calibration_report(brier_score=0.10, overall_bias=0.05)
        store = _make_postmortem_store_with_errors(ErrorCategory.COMPETITION_ERROR, 5)
        suggestions = promoter.generate_suggestions(
            calibration, store, {"competition": 0.10}
        )
        types = [s.suggestion_type for s in suggestions]
        assert SuggestionType.INCREASE_DOMAIN_WEIGHT in types
        domains = [s.domain for s in suggestions if s.suggestion_type == SuggestionType.INCREASE_DOMAIN_WEIGHT]
        assert "competition" in domains

    def test_generate_suggestions_increase_science_weight(self):
        promoter = WeightPromoter()
        calibration = _make_calibration_report(brier_score=0.10, overall_bias=0.05)
        store = _make_postmortem_store_with_errors(ErrorCategory.SCIENCE_ERROR, 5)
        suggestions = promoter.generate_suggestions(
            calibration, store, {"science": 0.10}
        )
        types = [s.suggestion_type for s in suggestions]
        assert SuggestionType.INCREASE_DOMAIN_WEIGHT in types
        domains = [s.domain for s in suggestions if s.suggestion_type == SuggestionType.INCREASE_DOMAIN_WEIGHT]
        assert "science" in domains

    def test_generate_suggestions_flag_for_review_market_drift(self):
        promoter = WeightPromoter()
        calibration = _make_calibration_report(brier_score=0.10, overall_bias=0.05)
        store = _make_postmortem_store_with_errors(ErrorCategory.MARKET_DRIFT, 5)
        suggestions = promoter.generate_suggestions(calibration, store, {})
        types = [s.suggestion_type for s in suggestions]
        assert SuggestionType.FLAG_FOR_REVIEW in types

    def test_generate_suggestions_decrease_high_weight(self):
        promoter = WeightPromoter()
        calibration = _make_calibration_report(brier_score=0.10, overall_bias=0.05)
        store = PostmortemStore()
        suggestions = promoter.generate_suggestions(
            calibration, store, {"some_domain": 0.50}
        )
        types = [s.suggestion_type for s in suggestions]
        assert SuggestionType.DECREASE_DOMAIN_WEIGHT in types

    def test_suggestions_do_not_exceed_competition_cap(self):
        promoter = WeightPromoter()
        calibration = _make_calibration_report(brier_score=0.10, overall_bias=0.05)
        store = _make_postmortem_store_with_errors(ErrorCategory.COMPETITION_ERROR, 5)
        suggestions = promoter.generate_suggestions(
            calibration, store, {"competition": 0.19}  # near cap of 0.20
        )
        increase_suggestions = [
            s for s in suggestions
            if s.suggestion_type == SuggestionType.INCREASE_DOMAIN_WEIGHT
            and s.domain == "competition"
        ]
        for s in increase_suggestions:
            assert s.suggested_value <= 0.20

    def test_all_suggestions_require_human_review(self):
        promoter = WeightPromoter()
        calibration = _make_calibration_report(brier_score=0.30, overall_bias=0.15)
        store = _make_postmortem_store_with_errors(ErrorCategory.COMPETITION_ERROR, 5)
        suggestions = promoter.generate_suggestions(
            calibration, store, {"science": 0.45}
        )
        for s in suggestions:
            assert s.requires_human_review is True

    def test_approve_sets_approved_status(self):
        promoter = WeightPromoter()
        calibration = _make_calibration_report(brier_score=0.30, overall_bias=0.15)
        store = PostmortemStore()
        suggestions = promoter.generate_suggestions(calibration, store, {})
        assert len(suggestions) > 0
        sid = suggestions[0].suggestion_id
        promoter.approve(sid, reviewer_note="Looks good")
        approved = [s for s in promoter.all_suggestions() if s.suggestion_id == sid]
        assert approved[0].status == PromotionStatus.APPROVED
        assert approved[0].reviewer_note == "Looks good"

    def test_veto_sets_vetoed_status(self):
        promoter = WeightPromoter()
        calibration = _make_calibration_report(brier_score=0.30, overall_bias=0.15)
        store = PostmortemStore()
        suggestions = promoter.generate_suggestions(calibration, store, {})
        sid = suggestions[0].suggestion_id
        promoter.veto(sid, reviewer_note="Not applicable")
        vetoed = [s for s in promoter.all_suggestions() if s.suggestion_id == sid]
        assert vetoed[0].status == PromotionStatus.VETOED

    def test_pending_only_returns_pending_review(self):
        promoter = WeightPromoter()
        calibration = _make_calibration_report(brier_score=0.30, overall_bias=0.15)
        store = PostmortemStore()
        suggestions = promoter.generate_suggestions(calibration, store, {})
        assert len(suggestions) > 0
        # Approve first one
        promoter.approve(suggestions[0].suggestion_id)
        pending = promoter.pending()
        for s in pending:
            assert s.status == PromotionStatus.PENDING_REVIEW

    def test_no_suggestions_with_empty_postmortem_good_calibration(self):
        promoter = WeightPromoter()
        calibration = _make_calibration_report(brier_score=0.10, overall_bias=0.02)
        store = PostmortemStore()
        suggestions = promoter.generate_suggestions(calibration, store, {})
        # No triggers fire
        assert len(suggestions) == 0

    def test_generate_suggestions_increase_financing_weight(self):
        promoter = WeightPromoter()
        calibration = _make_calibration_report(brier_score=0.10, overall_bias=0.05)
        store = _make_postmortem_store_with_errors(ErrorCategory.FINANCING_ERROR, 5)
        suggestions = promoter.generate_suggestions(
            calibration, store, {"financing": 0.10}
        )
        domains = [
            s.domain for s in suggestions
            if s.suggestion_type == SuggestionType.INCREASE_DOMAIN_WEIGHT
        ]
        assert "financing" in domains
