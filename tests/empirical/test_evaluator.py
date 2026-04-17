"""
Tests for the evaluator module — Brier score, AUC, ECE, and time-split evaluation.
"""
from __future__ import annotations

import pytest

from bve.empirical.evaluator import (
    EvaluationResult,
    TimeSplitResult,
    _auc_roc,
    _brier_score,
    _ece,
    evaluate,
    evaluate_time_split,
)
from bve.empirical.pos_outcome import POSOutcomeRecord, load_bundled_records


def _make_record(
    success: bool,
    phase: str = "phase_2",
    moa: str | None = "partial",
    biomarker: bool = False,
    year: str = "2020",
    drug: str = "drug",
) -> POSOutcomeRecord:
    return POSOutcomeRecord(
        program_id=f"{drug}_{year}",
        sponsor="S",
        asset_name=drug,
        indication_raw="X",
        phase_at_entry=phase,
        moa_precedent=moa,
        biomarker_selected=biomarker,
        success=success,
        outcome_raw="approved" if success else "failed",
        outcome_date=year,
    )


class TestBrierScore:
    def test_perfect_predictions(self):
        preds = [1.0, 0.0, 1.0, 0.0]
        outcomes = [True, False, True, False]
        assert _brier_score(preds, outcomes) == 0.0

    def test_worst_predictions(self):
        preds = [0.0, 1.0, 0.0, 1.0]
        outcomes = [True, False, True, False]
        assert abs(_brier_score(preds, outcomes) - 1.0) < 1e-9

    def test_uninformative_predictions(self):
        """All 0.5 → Brier = 0.25."""
        preds = [0.5] * 10
        outcomes = [True, False] * 5
        assert abs(_brier_score(preds, outcomes) - 0.25) < 1e-9

    def test_empty_returns_zero(self):
        assert _brier_score([], []) == 0.0

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            _brier_score([0.5, 0.5], [True])


class TestAUCROC:
    def test_perfect_discrimination(self):
        """Predictions perfectly separate classes → AUC = 1.0."""
        preds = [0.9, 0.8, 0.2, 0.1]
        outcomes = [True, True, False, False]
        assert _auc_roc(preds, outcomes) == 1.0

    def test_random_discrimination(self):
        """Predictions are constant → AUC ≈ 0.5."""
        preds = [0.5] * 100
        outcomes = [True, False] * 50
        auc = _auc_roc(preds, outcomes)
        assert auc is not None
        assert abs(auc - 0.5) < 0.05

    def test_inverse_discrimination(self):
        """Inversed predictions → AUC ≈ 0.0."""
        preds = [0.1, 0.2, 0.8, 0.9]
        outcomes = [True, True, False, False]
        auc = _auc_roc(preds, outcomes)
        assert auc is not None
        assert auc < 0.1

    def test_single_class_returns_none(self):
        preds = [0.8, 0.7, 0.9]
        outcomes = [True, True, True]
        assert _auc_roc(preds, outcomes) is None

    def test_auc_in_zero_one(self):
        import random
        rng = random.Random(42)
        preds = [rng.random() for _ in range(50)]
        outcomes = [rng.choice([True, False]) for _ in range(50)]
        auc = _auc_roc(preds, outcomes)
        if auc is not None:
            assert 0.0 <= auc <= 1.0


class TestECE:
    def test_perfectly_calibrated(self):
        """Predictions == observed rates per bin → ECE ≈ 0."""
        # 10 bins × 10 examples each; pred = 0.05, 0.15, ... all with matching obs rate
        preds = []
        outcomes = []
        for b in range(10):
            centre = b * 0.1 + 0.05
            n = 20
            n_pos = round(centre * n)
            preds += [centre] * n
            outcomes += [True] * n_pos + [False] * (n - n_pos)
        ece, bins = _ece(preds, outcomes)
        assert ece < 0.10  # Allow some slack for rounding

    def test_miscalibrated_model(self):
        """Model always predicts 0.9 but only 10% succeed → ECE ≈ 0.8."""
        n = 100
        preds = [0.9] * n
        outcomes = [True] * 10 + [False] * 90
        ece, bins = _ece(preds, outcomes)
        assert ece > 0.5

    def test_bins_structure(self):
        preds = [0.2, 0.8, 0.5]
        outcomes = [True, False, True]
        _, bins = _ece(preds, outcomes)
        assert len(bins) == 10
        for b in bins:
            assert "lower" in b and "upper" in b and "n" in b

    def test_empty_returns_zero(self):
        ece, bins = _ece([], [])
        assert ece == 0.0
        assert bins == []


class TestEvaluate:
    def test_basic_evaluate(self):
        records = [_make_record(True, drug=f"a{i}") for i in range(5)] + \
                  [_make_record(False, drug=f"b{i}") for i in range(5)]
        preds = [0.8] * 5 + [0.2] * 5
        result = evaluate(preds, records)
        assert isinstance(result, EvaluationResult)
        assert result.n == 10
        assert result.brier_score < 0.2  # good predictions
        assert result.auc is not None
        assert result.auc > 0.5

    def test_length_mismatch_raises(self):
        records = [_make_record(True)]
        with pytest.raises(ValueError):
            evaluate([0.5, 0.5], records)

    def test_empty_records_raises(self):
        with pytest.raises(ValueError):
            evaluate([], [])

    def test_result_str_representation(self):
        records = [_make_record(True), _make_record(False)]
        result = evaluate([0.8, 0.3], records)
        s = str(result)
        assert "Brier" in s and "AUC" in s and "ECE" in s

    def test_single_class_auc_none(self):
        records = [_make_record(True, drug=f"a{i}") for i in range(3)]
        preds = [0.7, 0.6, 0.8]
        result = evaluate(preds, records)
        assert result.auc is None


class TestEvaluateTimeSplit:
    class _MockEngine:
        """Minimal engine duck-type for time-split testing."""
        def predict(self, phase, moa_precedent=None, biomarker_selected=None):
            return 0.5  # constant prediction

    def _records(self) -> list[POSOutcomeRecord]:
        return [
            _make_record(True, year="2015", drug="a"),
            _make_record(False, year="2016", drug="b"),
            _make_record(True, year="2016", drug="c"),
            _make_record(False, year="2019", drug="d"),
            _make_record(True, year="2020", drug="e"),
            _make_record(False, year="2021", drug="f"),
        ]

    def test_split_counts(self):
        result = evaluate_time_split(self._MockEngine(), self._records(), cutoff_year=2018)
        assert result.n_train == 3
        assert result.n_test == 3

    def test_result_type(self):
        result = evaluate_time_split(self._MockEngine(), self._records(), cutoff_year=2018)
        assert isinstance(result, TimeSplitResult)

    def test_brier_drift_computed(self):
        result = evaluate_time_split(self._MockEngine(), self._records(), cutoff_year=2018)
        assert abs(result.brier_drift - (result.test_brier - result.train_brier)) < 1e-9

    def test_empty_test_fold(self):
        """When cutoff is after all records, test_brier=0 and n_test=0."""
        result = evaluate_time_split(self._MockEngine(), self._records(), cutoff_year=2030)
        assert result.n_test == 0
        assert result.test_brier == 0.0

    def test_str_representation(self):
        result = evaluate_time_split(self._MockEngine(), self._records(), cutoff_year=2018)
        assert "cutoff=2018" in str(result)

    def test_missing_year_goes_to_train(self):
        """Records with no outcome_date are assigned to the train fold."""
        records = self._records()
        no_year = _make_record(True, year="", drug="no_year")
        result = evaluate_time_split(self._MockEngine(), records + [no_year], cutoff_year=2018)
        # no_year should land in train
        assert result.n_train == 4  # 3 original + 1 no_year


class TestEndToEndEvaluation:
    def test_bundled_data_evaluate(self):
        """Smoke test: load bundled records, predict constant, evaluate."""
        records = load_bundled_records()
        preds = [0.4] * len(records)  # constant prediction at oncology-ish rate
        result = evaluate(preds, records)
        assert result.n == len(records)
        assert 0.0 < result.brier_score < 0.5

    def test_bundled_time_split(self):
        from bve.empirical.engine import EmpiricalPOSEngine
        records = load_bundled_records()
        engine = EmpiricalPOSEngine(records)
        result = evaluate_time_split(engine, records, cutoff_year=2020)
        assert result.n_train + result.n_test == len(records)
        assert 0.0 <= result.train_brier <= 1.0
        assert 0.0 <= result.test_brier <= 1.0
