"""
Sprint 16 tests — Calibration database.

Tests:
- CalibrationMetrics: Brier, AUC, ECE, buckets, min_n gate
- KnowledgeStore: pos_predictions insert/read, pos_outcomes upsert/read
- Integration: predictions + outcomes → compute_calibration()
"""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest

from bve.analysis.calibration_metrics import (
    CalibrationReport,
    OutcomeRecord,
    PredictionRecord,
    _auc_roc,
    _brier_score,
    _reliability_buckets,
    compute_calibration,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pred(program_id="P1", ticker="VKTX", model_pos=0.50, ta="oncology", phase="phase_3"):
    return PredictionRecord(
        program_id=program_id,
        ticker=ticker,
        ta=ta,
        phase=phase,
        model_pos=model_pos,
        predicted_at=date(2025, 1, 1),
    )


def _outcome(program_id="P1", outcome_type="approval"):
    return OutcomeRecord(
        program_id=program_id,
        outcome_date=date(2026, 1, 1),
        outcome_type=outcome_type,
    )


def _build_dataset(n_success: int, n_fail: int, pos_success: float = 0.70, pos_fail: float = 0.30):
    """Build a synthetic matched dataset."""
    preds, outcomes = [], []
    for i in range(n_success):
        pid = f"S{i}"
        preds.append(_pred(program_id=pid, model_pos=pos_success))
        outcomes.append(_outcome(program_id=pid, outcome_type="approval"))
    for i in range(n_fail):
        pid = f"F{i}"
        preds.append(_pred(program_id=pid, model_pos=pos_fail))
        outcomes.append(_outcome(program_id=pid, outcome_type="failure_efficacy"))
    return preds, outcomes


# ===========================================================================
# TestBrierScore
# ===========================================================================

class TestBrierScore:
    def test_perfect_predictions(self):
        assert _brier_score([1.0, 0.0], [1, 0]) == pytest.approx(0.0)

    def test_worst_predictions(self):
        assert _brier_score([0.0, 1.0], [1, 0]) == pytest.approx(1.0)

    def test_null_model_symmetric(self):
        # Predicting 0.5 for everything → Brier = 0.25
        probs = [0.5] * 4
        labels = [1, 1, 0, 0]
        assert _brier_score(probs, labels) == pytest.approx(0.25)

    def test_empty_returns_zero(self):
        assert _brier_score([], []) == 0.0


# ===========================================================================
# TestAucRoc
# ===========================================================================

class TestAucRoc:
    def test_perfect_separation(self):
        probs = [0.9, 0.8, 0.2, 0.1]
        labels = [1, 1, 0, 0]
        assert _auc_roc(probs, labels) == pytest.approx(1.0, abs=0.01)

    def test_random_classifier(self):
        # 50/50 — AUC near 0.5
        probs = [0.5] * 100
        labels = [1] * 50 + [0] * 50
        auc = _auc_roc(probs, labels)
        assert 0.40 <= auc <= 0.60

    def test_no_positives_returns_half(self):
        assert _auc_roc([0.8, 0.2], [0, 0]) == pytest.approx(0.5)


# ===========================================================================
# TestReliabilityBuckets
# ===========================================================================

class TestReliabilityBuckets:
    def test_five_buckets_returned(self):
        probs = [0.1, 0.3, 0.5, 0.7, 0.9]
        labels = [0, 0, 1, 1, 1]
        buckets = _reliability_buckets(probs, labels)
        assert len(buckets) == 5

    def test_bucket_n_sums_to_total(self):
        preds, outcomes = _build_dataset(n_success=10, n_fail=10)
        probs = [p.model_pos for p in preds]
        labels = [1] * 10 + [0] * 10
        buckets = _reliability_buckets(probs, labels)
        assert sum(b.n for b in buckets) == 20

    def test_high_bucket_high_success_rate(self):
        probs = [0.85] * 10
        labels = [1] * 8 + [0] * 2
        buckets = _reliability_buckets(probs, labels)
        high_bucket = [b for b in buckets if b.lo >= 0.80][0]
        assert high_bucket.actual_success_rate == pytest.approx(0.80)


# ===========================================================================
# TestComputeCalibration
# ===========================================================================

class TestComputeCalibration:
    def test_returns_none_below_min_n(self):
        preds, outcomes = _build_dataset(n_success=5, n_fail=5)
        result = compute_calibration(preds, outcomes, min_n=20)
        assert result is None

    def test_returns_report_above_min_n(self):
        preds, outcomes = _build_dataset(n_success=15, n_fail=15)
        result = compute_calibration(preds, outcomes, min_n=20)
        assert isinstance(result, CalibrationReport)

    def test_brier_score_in_range(self):
        preds, outcomes = _build_dataset(n_success=15, n_fail=15)
        result = compute_calibration(preds, outcomes, min_n=20)
        assert 0.0 <= result.brier_score <= 0.25

    def test_auc_roc_in_range(self):
        preds, outcomes = _build_dataset(n_success=15, n_fail=15)
        result = compute_calibration(preds, outcomes, min_n=20)
        assert 0.0 <= result.auc_roc <= 1.0

    def test_perfect_discrimination_auc_near_1(self):
        preds, outcomes = _build_dataset(15, 15, pos_success=0.95, pos_fail=0.05)
        result = compute_calibration(preds, outcomes, min_n=20)
        assert result.auc_roc >= 0.95

    def test_ongoing_outcomes_excluded(self):
        preds = [_pred(program_id="P1"), _pred(program_id="P2")]
        outcomes = [
            _outcome("P1", "approval"),
            _outcome("P2", "ongoing"),  # should be excluded
        ]
        result = compute_calibration(preds, outcomes, min_n=1)
        assert result.n_pairs == 1

    def test_unmatched_prediction_excluded(self):
        preds = [_pred("P1"), _pred("P999")]  # P999 has no outcome
        outcomes = [_outcome("P1")]
        result = compute_calibration(preds, outcomes, min_n=1)
        assert result.n_pairs == 1

    def test_n_pairs_counts(self):
        preds, outcomes = _build_dataset(10, 10)
        result = compute_calibration(preds, outcomes, min_n=5)
        assert result.n_pairs == 20
        assert result.n_success == 10
        assert result.n_failure == 10

    def test_base_rate_computed(self):
        preds, outcomes = _build_dataset(15, 15)
        result = compute_calibration(preds, outcomes, min_n=20)
        assert result.base_rate == pytest.approx(0.50)

    def test_brier_skill_score_positive_when_discriminating(self):
        preds, outcomes = _build_dataset(15, 15, pos_success=0.8, pos_fail=0.2)
        result = compute_calibration(preds, outcomes, min_n=20)
        assert result.brier_skill_score > 0

    def test_high_base_rate_triggers_warning(self):
        preds = [_pred(program_id=f"P{i}", model_pos=0.6) for i in range(30)]
        outcomes = [_outcome(f"P{i}", "approval") for i in range(30)]  # 100% success
        result = compute_calibration(preds, outcomes, min_n=20)
        assert any("survivor" in w.lower() or "bias" in w.lower() for w in result.warnings)

    def test_five_buckets_in_report(self):
        preds, outcomes = _build_dataset(15, 15)
        result = compute_calibration(preds, outcomes, min_n=20)
        assert len(result.buckets) == 5

    def test_ece_is_non_negative(self):
        preds, outcomes = _build_dataset(15, 15)
        result = compute_calibration(preds, outcomes, min_n=20)
        assert result.ece >= 0.0


# ===========================================================================
# TestKnowledgeStoreCalibration — persistence
# ===========================================================================

class TestKnowledgeStoreCalibration:
    @pytest.fixture()
    def store(self):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            ks = KnowledgeStore(db_path)
            yield ks
            ks.close()

    def test_insert_and_read_prediction(self, store):
        pred = _pred()
        row_id = store.insert_pos_prediction(pred)
        assert isinstance(row_id, str)
        rows = store.get_pos_predictions()
        assert len(rows) == 1
        assert rows[0]["program_id"] == "P1"
        assert rows[0]["model_pos"] == pytest.approx(0.50)

    def test_insert_multiple_predictions(self, store):
        store.insert_pos_prediction(_pred(program_id="A"))
        store.insert_pos_prediction(_pred(program_id="B"))
        rows = store.get_pos_predictions()
        assert len(rows) == 2

    def test_filter_by_ticker(self, store):
        store.insert_pos_prediction(_pred(program_id="A", ticker="VKTX"))
        store.insert_pos_prediction(_pred(program_id="B", ticker="ALNY"))
        rows = store.get_pos_predictions(ticker="VKTX")
        assert len(rows) == 1
        assert rows[0]["ticker"] == "VKTX"

    def test_upsert_outcome(self, store):
        outcome = _outcome("P1", "approval")
        store.upsert_pos_outcome(outcome)
        rows = store.get_pos_outcomes()
        assert len(rows) == 1
        assert rows[0]["outcome_type"] == "approval"

    def test_outcome_upsert_replaces(self, store):
        store.upsert_pos_outcome(_outcome("P1", "ongoing"))
        store.upsert_pos_outcome(_outcome("P1", "approval"))  # updates
        rows = store.get_pos_outcomes(program_id="P1")
        assert len(rows) == 1
        assert rows[0]["outcome_type"] == "approval"

    def test_filter_outcome_by_type(self, store):
        store.upsert_pos_outcome(_outcome("P1", "approval"))
        store.upsert_pos_outcome(_outcome("P2", "failure_efficacy"))
        rows = store.get_pos_outcomes(outcome_type="approval")
        assert len(rows) == 1

    def test_empty_tables_return_empty(self, store):
        assert store.get_pos_predictions() == []
        assert store.get_pos_outcomes() == []
