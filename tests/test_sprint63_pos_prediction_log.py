"""
Block 23 — POS Prediction Log
TDD tests written BEFORE implementation.

Tests for:
  1. POSPredictionRecord dataclass fields
  2. log_pos_prediction() — creates + persists record
  3. resolve_pos_prediction() — sets outcome + resolved=True
  4. resolve_pos_prediction() — rejects outcome_date < prediction_date
  5. get_pos_predictions() — filter by ticker, phase, resolved_only, as_of_date
"""
from __future__ import annotations

import pytest

from bve.models.pos_prediction_log import (
    POSPredictionRecord,
    log_pos_prediction,
    resolve_pos_prediction,
    get_pos_predictions,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_store(tmp_path):
    return tmp_path / "pos_predictions.db"


def _log_one(store_path, **kwargs) -> str:
    defaults = dict(
        trial_id="NCT00000001",
        ticker="VKTX",
        phase="phase_2",
        therapeutic_area="oncology",
        predicted_pos=0.35,
        confidence_flags=["small_n"],
        model_version="v1.0.0",
        adjuster_snapshot={"moa_precedent": "validated_class"},
        prediction_date="2026-01-15",
    )
    defaults.update(kwargs)
    return log_pos_prediction(store_path, **defaults)


# ---------------------------------------------------------------------------
# Block 23-A: POSPredictionRecord dataclass
# ---------------------------------------------------------------------------

class TestPOSPredictionRecord:

    def test_fields_present(self):
        r = POSPredictionRecord(
            record_id="abc123",
            trial_id="NCT00000001",
            ticker="VKTX",
            phase="phase_2",
            therapeutic_area="oncology",
            predicted_pos=0.35,
            confidence_flags=["small_n"],
            model_version="v1.0.0",
            adjuster_snapshot={"moa_precedent": "validated_class"},
            prediction_date="2026-01-15",
            outcome=None,
            outcome_date=None,
            resolved=False,
        )
        assert r.record_id == "abc123"
        assert r.trial_id == "NCT00000001"
        assert r.ticker == "VKTX"
        assert r.phase == "phase_2"
        assert r.therapeutic_area == "oncology"
        assert r.predicted_pos == pytest.approx(0.35)
        assert r.confidence_flags == ["small_n"]
        assert r.model_version == "v1.0.0"
        assert r.adjuster_snapshot == {"moa_precedent": "validated_class"}
        assert r.prediction_date == "2026-01-15"
        assert r.outcome is None
        assert r.outcome_date is None
        assert r.resolved is False

    def test_unresolved_by_default(self):
        r = POSPredictionRecord(
            record_id="x",
            trial_id="T",
            ticker="T",
            phase="phase_2",
            therapeutic_area="oncology",
            predicted_pos=0.4,
            confidence_flags=[],
            model_version="v1",
            adjuster_snapshot={},
            prediction_date="2026-01-15",
            outcome=None,
            outcome_date=None,
            resolved=False,
        )
        assert not r.resolved


# ---------------------------------------------------------------------------
# Block 23-B: log_pos_prediction()
# ---------------------------------------------------------------------------

class TestLogPosPrediction:

    def test_log_creates_record(self, tmp_path):
        store = _make_store(tmp_path)
        _log_one(store)
        records = get_pos_predictions(store)
        assert len(records) == 1

    def test_log_returns_record_id(self, tmp_path):
        store = _make_store(tmp_path)
        rid = _log_one(store)
        assert isinstance(rid, str)
        assert len(rid) > 0

    def test_log_returns_unique_ids(self, tmp_path):
        store = _make_store(tmp_path)
        rid1 = _log_one(store, trial_id="NCT00000001")
        rid2 = _log_one(store, trial_id="NCT00000002")
        assert rid1 != rid2

    def test_log_persists_pos(self, tmp_path):
        store = _make_store(tmp_path)
        _log_one(store, predicted_pos=0.42)
        records = get_pos_predictions(store)
        assert records[0].predicted_pos == pytest.approx(0.42)

    def test_log_persists_confidence_flags(self, tmp_path):
        store = _make_store(tmp_path)
        _log_one(store, confidence_flags=["small_n", "open_label"])
        records = get_pos_predictions(store)
        assert records[0].confidence_flags == ["small_n", "open_label"]

    def test_log_persists_adjuster_snapshot(self, tmp_path):
        store = _make_store(tmp_path)
        snap = {"endpoint_type": "primary_endpoint", "moa_precedent": "validated_class"}
        _log_one(store, adjuster_snapshot=snap)
        records = get_pos_predictions(store)
        assert records[0].adjuster_snapshot == snap

    def test_log_model_version_stored(self, tmp_path):
        store = _make_store(tmp_path)
        _log_one(store, model_version="v2.3.1")
        records = get_pos_predictions(store)
        assert records[0].model_version == "v2.3.1"

    def test_log_record_unresolved_on_creation(self, tmp_path):
        store = _make_store(tmp_path)
        _log_one(store)
        records = get_pos_predictions(store)
        assert not records[0].resolved
        assert records[0].outcome is None
        assert records[0].outcome_date is None

    def test_log_multiple_records(self, tmp_path):
        store = _make_store(tmp_path)
        _log_one(store, trial_id="NCT00000001", ticker="VKTX")
        _log_one(store, trial_id="NCT00000002", ticker="ALNY")
        _log_one(store, trial_id="NCT00000003", ticker="ALNY")
        records = get_pos_predictions(store)
        assert len(records) == 3


# ---------------------------------------------------------------------------
# Block 23-C: resolve_pos_prediction()
# ---------------------------------------------------------------------------

class TestResolvePosPrediction:

    def test_resolve_sets_outcome(self, tmp_path):
        store = _make_store(tmp_path)
        rid = _log_one(store, prediction_date="2026-01-15")
        resolve_pos_prediction(store, record_id=rid, outcome="success", outcome_date="2026-06-01")
        records = get_pos_predictions(store)
        assert records[0].outcome == "success"

    def test_resolve_sets_resolved_true(self, tmp_path):
        store = _make_store(tmp_path)
        rid = _log_one(store, prediction_date="2026-01-15")
        resolve_pos_prediction(store, record_id=rid, outcome="failure", outcome_date="2026-06-01")
        records = get_pos_predictions(store)
        assert records[0].resolved is True

    def test_resolve_sets_outcome_date(self, tmp_path):
        store = _make_store(tmp_path)
        rid = _log_one(store, prediction_date="2026-01-15")
        resolve_pos_prediction(store, record_id=rid, outcome="success", outcome_date="2026-08-20")
        records = get_pos_predictions(store)
        assert records[0].outcome_date == "2026-08-20"

    def test_resolve_rejects_outcome_before_prediction_date(self, tmp_path):
        store = _make_store(tmp_path)
        rid = _log_one(store, prediction_date="2026-06-01")
        with pytest.raises(ValueError, match="outcome_date.*before.*prediction_date"):
            resolve_pos_prediction(store, record_id=rid, outcome="success", outcome_date="2026-01-01")

    def test_resolve_accepts_same_day(self, tmp_path):
        """outcome_date == prediction_date is acceptable."""
        store = _make_store(tmp_path)
        rid = _log_one(store, prediction_date="2026-06-01")
        resolve_pos_prediction(store, record_id=rid, outcome="success", outcome_date="2026-06-01")
        records = get_pos_predictions(store)
        assert records[0].resolved is True

    def test_resolve_nonexistent_record_raises(self, tmp_path):
        store = _make_store(tmp_path)
        with pytest.raises((ValueError, KeyError)):
            resolve_pos_prediction(store, record_id="nonexistent", outcome="success", outcome_date="2026-06-01")

    def test_resolve_outcome_values(self, tmp_path):
        """Both 'success' and 'failure' are valid outcomes."""
        store = _make_store(tmp_path)
        rid1 = _log_one(store, trial_id="NCT00000001", prediction_date="2026-01-01")
        rid2 = _log_one(store, trial_id="NCT00000002", prediction_date="2026-01-01")
        resolve_pos_prediction(store, record_id=rid1, outcome="success", outcome_date="2026-06-01")
        resolve_pos_prediction(store, record_id=rid2, outcome="failure", outcome_date="2026-06-01")
        records = get_pos_predictions(store, resolved_only=True)
        outcomes = {r.outcome for r in records}
        assert outcomes == {"success", "failure"}


# ---------------------------------------------------------------------------
# Block 23-D: get_pos_predictions() — filtering
# ---------------------------------------------------------------------------

class TestGetPosPredictions:

    def _seed(self, store):
        _log_one(store, trial_id="NCT1", ticker="VKTX", phase="phase_2", prediction_date="2026-01-10")
        _log_one(store, trial_id="NCT2", ticker="ALNY", phase="phase_3", prediction_date="2026-02-10")
        _log_one(store, trial_id="NCT3", ticker="ALNY", phase="phase_2", prediction_date="2026-03-10")

    def test_no_filter_returns_all(self, tmp_path):
        store = _make_store(tmp_path)
        self._seed(store)
        assert len(get_pos_predictions(store)) == 3

    def test_filter_by_ticker(self, tmp_path):
        store = _make_store(tmp_path)
        self._seed(store)
        records = get_pos_predictions(store, ticker="ALNY")
        assert len(records) == 2
        assert all(r.ticker == "ALNY" for r in records)

    def test_filter_by_phase(self, tmp_path):
        store = _make_store(tmp_path)
        self._seed(store)
        records = get_pos_predictions(store, phase="phase_2")
        assert len(records) == 2
        assert all(r.phase == "phase_2" for r in records)

    def test_filter_by_trial_id(self, tmp_path):
        store = _make_store(tmp_path)
        self._seed(store)
        records = get_pos_predictions(store, trial_id="NCT2")
        assert len(records) == 1
        assert records[0].trial_id == "NCT2"

    def test_resolved_only_filter(self, tmp_path):
        store = _make_store(tmp_path)
        rid1 = _log_one(store, trial_id="NCT1", ticker="VKTX", prediction_date="2026-01-10")
        _log_one(store, trial_id="NCT2", ticker="ALNY", prediction_date="2026-01-10")
        resolve_pos_prediction(store, record_id=rid1, outcome="success", outcome_date="2026-06-01")
        records = get_pos_predictions(store, resolved_only=True)
        assert len(records) == 1
        assert records[0].resolved is True

    def test_as_of_date_excludes_future(self, tmp_path):
        store = _make_store(tmp_path)
        _log_one(store, trial_id="NCT1", prediction_date="2026-01-15")
        _log_one(store, trial_id="NCT2", prediction_date="2026-06-15")
        _log_one(store, trial_id="NCT3", prediction_date="2026-12-31")
        records = get_pos_predictions(store, as_of_date="2026-06-15")
        assert len(records) == 2
        for r in records:
            assert r.prediction_date <= "2026-06-15"

    def test_combined_filters(self, tmp_path):
        store = _make_store(tmp_path)
        self._seed(store)
        records = get_pos_predictions(store, ticker="ALNY", phase="phase_3")
        assert len(records) == 1
        assert records[0].trial_id == "NCT2"

    def test_empty_store_returns_empty_list(self, tmp_path):
        store = _make_store(tmp_path)
        assert get_pos_predictions(store) == []
