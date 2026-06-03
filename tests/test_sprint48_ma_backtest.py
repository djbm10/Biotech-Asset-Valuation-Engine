"""Tests for Block 7: M&A Backtest & Calibration (ma_backtest.py).

Covers:
- run_backtest: AUC, Brier score, precision@k, recall@k, base_rate,
  mean acquired/non-acquired scores, calibration buckets.
- fit_logistic_calibration: slope/midpoint fitting, fallback to defaults on
  degenerate data.
- save_calibration_params / load_calibration_params: round-trip JSON
  persistence and fallback behavior when file is absent.
- adjust_for_base_rate: log-odds prior-shift formula correctness.
- ma_layer5_calibration._try_load_calibration_params: module-level
  loading from JSON; fallback emits UserWarning.
- _derive_logistic_probability: uses loaded params, not just hard-coded.
"""
from __future__ import annotations

import importlib
import json
import warnings
from datetime import date
from pathlib import Path

import pytest

from bve.intelligence.ma_backtest import (
    MABacktestRecord,
    MABacktestResult,
    CalibrationParams,
    run_backtest,
    fit_logistic_calibration,
    save_calibration_params,
    load_calibration_params,
    adjust_for_base_rate,
    build_backtest_records_from_deal_universe,
    _binary_auc,
    _brier_score,
    _precision_at_k,
    _recall_at_k,
    _calibration_buckets,
    _DEFAULT_SLOPE,
    _DEFAULT_MIDPOINT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_records(n_pos: int = 10, n_neg: int = 10) -> list[MABacktestRecord]:
    """Build simple synthetic records: positives score high, negatives low."""
    from datetime import timedelta
    base = date(2022, 1, 1)
    positives = [
        MABacktestRecord(
            score=min(0.99, 0.75 + i * 0.01),
            label=1,
            prediction_date=base + timedelta(days=i),
        )
        for i in range(n_pos)
    ]
    negatives = [
        MABacktestRecord(
            score=min(0.69, 0.20 + i * 0.01),
            label=0,
            prediction_date=base + timedelta(days=180 + i),
        )
        for i in range(n_neg)
    ]
    return positives + negatives


# ---------------------------------------------------------------------------
# Tests: run_backtest metrics
# ---------------------------------------------------------------------------

class TestRunBacktest:

    def test_basic_fields_present(self):
        records = _make_records(10, 10)
        result = run_backtest(records)
        assert isinstance(result, MABacktestResult)
        assert result.n == 20
        assert result.n_positive == 10
        assert result.n_negative == 10

    def test_base_rate(self):
        records = _make_records(5, 15)
        result = run_backtest(records)
        assert result.base_rate == pytest.approx(0.25, abs=1e-4)

    def test_auc_well_separated(self):
        # Positives score well above negatives → AUC should be near 1.0
        records = _make_records(10, 10)
        result = run_backtest(records)
        assert result.auc is not None
        assert result.auc > 0.9

    def test_auc_none_when_single_class(self):
        records = [MABacktestRecord(score=0.5, label=1) for _ in range(5)]
        result = run_backtest(records)
        assert result.auc is None
        assert any("AUC undefined" in n for n in result.notes)

    def test_brier_score_range(self):
        records = _make_records(10, 10)
        result = run_backtest(records)
        assert 0.0 <= result.brier_score <= 1.0

    def test_brier_perfect_scores(self):
        # Labels and scores perfectly aligned → low Brier score
        records = [
            MABacktestRecord(score=1.0, label=1),
            MABacktestRecord(score=0.0, label=0),
        ]
        result = run_backtest(records)
        assert result.brier_score == pytest.approx(0.0, abs=1e-6)

    def test_precision_at_k(self):
        records = _make_records(10, 10)
        result = run_backtest(records, k_values=(5, 10))
        assert 5 in result.precision_at_k
        assert 10 in result.precision_at_k
        # Positives scored 0.75–0.84; top-5 should all be positive
        assert result.precision_at_k[5] == pytest.approx(1.0, abs=1e-4)

    def test_recall_at_k(self):
        records = _make_records(10, 10)
        result = run_backtest(records, k_values=(10,))
        assert 10 in result.recall_at_k
        assert 0.0 <= result.recall_at_k[10] <= 1.0

    def test_mean_scores(self):
        records = _make_records(10, 10)
        result = run_backtest(records)
        assert result.mean_acquired_score is not None
        assert result.mean_non_acquired_score is not None
        assert result.mean_acquired_score > result.mean_non_acquired_score

    def test_score_separation(self):
        records = _make_records(10, 10)
        result = run_backtest(records)
        assert result.score_separation is not None
        assert result.score_separation > 0.0

    def test_calibration_buckets_non_empty(self):
        records = _make_records(10, 10)
        result = run_backtest(records)
        assert len(result.calibration_buckets) > 0
        for b in result.calibration_buckets:
            assert b.count > 0
            assert 0.0 <= b.acquisition_rate <= 1.0
            assert b.bucket_lower < b.bucket_upper

    def test_training_window_passthrough(self):
        records = _make_records(5, 5)
        result = run_backtest(records, training_window="2020-01-01 to 2025-12-31")
        assert result.training_window == "2020-01-01 to 2025-12-31"

    def test_empty_records_raises(self):
        with pytest.raises(ValueError, match="empty"):
            run_backtest([])

    def test_warning_on_few_positives(self):
        records = [MABacktestRecord(score=0.8, label=1)] + [
            MABacktestRecord(score=0.2, label=0) for _ in range(10)
        ]
        result = run_backtest(records)
        assert any("positive" in n for n in result.notes)


# ---------------------------------------------------------------------------
# Tests: metric helpers
# ---------------------------------------------------------------------------

class TestMetricHelpers:

    def test_binary_auc_perfect(self):
        labels = [1, 1, 0, 0]
        scores = [0.9, 0.8, 0.3, 0.2]
        auc = _binary_auc(labels, scores)
        assert auc == pytest.approx(1.0, abs=1e-9)

    def test_binary_auc_random(self):
        labels = [1, 0, 1, 0]
        scores = [0.5, 0.5, 0.5, 0.5]
        # All ties → AUC = 0.5
        auc = _binary_auc(labels, scores)
        assert auc == pytest.approx(0.5, abs=1e-9)

    def test_binary_auc_none_when_single_class(self):
        assert _binary_auc([1, 1], [0.8, 0.9]) is None
        assert _binary_auc([0, 0], [0.2, 0.3]) is None

    def test_brier_score_known(self):
        labels = [1, 0]
        probs = [0.9, 0.1]
        expected = ((0.9 - 1) ** 2 + (0.1 - 0) ** 2) / 2
        assert _brier_score(labels, probs) == pytest.approx(expected, rel=1e-6)

    def test_precision_at_k_all_positive(self):
        labels = [1, 1, 1, 0, 0]
        scores = [0.9, 0.8, 0.7, 0.3, 0.2]
        assert _precision_at_k(labels, scores, 3) == pytest.approx(1.0, abs=1e-9)

    def test_recall_at_k_half(self):
        labels = [1, 1, 0, 0]
        scores = [0.9, 0.4, 0.8, 0.3]
        # Top-1: score=0.9 → label=1 → recall = 1/2
        assert _recall_at_k(labels, scores, 1) == pytest.approx(0.5, abs=1e-9)

    def test_calibration_buckets_coverage(self):
        labels = [1, 0, 1, 0, 0]
        scores = [0.85, 0.15, 0.65, 0.35, 0.45]
        buckets = _calibration_buckets(labels, scores)
        total_in_buckets = sum(b.count for b in buckets)
        assert total_in_buckets == len(labels)


# ---------------------------------------------------------------------------
# Tests: fit_logistic_calibration
# ---------------------------------------------------------------------------

class TestFitLogisticCalibration:

    def test_returns_calibration_params(self):
        records = _make_records(15, 15)
        params = fit_logistic_calibration(records)
        assert isinstance(params, CalibrationParams)

    def test_slope_and_midpoint_are_floats(self):
        records = _make_records(15, 15)
        params = fit_logistic_calibration(records)
        assert isinstance(params.slope, float)
        assert isinstance(params.midpoint, float)

    def test_fitted_slope_positive_for_separable(self):
        # Positives score higher → slope should be positive (higher score → higher prob)
        records = _make_records(15, 15)
        params = fit_logistic_calibration(records)
        assert params.slope > 0

    def test_metadata_counts(self):
        records = _make_records(12, 18)
        params = fit_logistic_calibration(records)
        assert params.n_positive == 12
        assert params.n_negative == 18
        assert params.source == "fitted"

    def test_base_rate_correct(self):
        records = _make_records(10, 40)
        params = fit_logistic_calibration(records)
        assert params.base_rate == pytest.approx(0.2, abs=1e-4)

    def test_training_window_inferred_from_dates(self):
        records = _make_records(10, 10)
        params = fit_logistic_calibration(records)
        assert params.training_window is not None
        assert "2022" in params.training_window

    def test_training_window_none_when_no_dates(self):
        records = [
            MABacktestRecord(score=0.8, label=1),
            MABacktestRecord(score=0.8, label=1),
            MABacktestRecord(score=0.8, label=1),
            MABacktestRecord(score=0.2, label=0),
            MABacktestRecord(score=0.2, label=0),
            MABacktestRecord(score=0.2, label=0),
            MABacktestRecord(score=0.5, label=1),
            MABacktestRecord(score=0.3, label=0),
            MABacktestRecord(score=0.7, label=1),
            MABacktestRecord(score=0.4, label=0),
        ]
        params = fit_logistic_calibration(records)
        assert params.training_window is None

    def test_auc_present_when_two_classes(self):
        records = _make_records(10, 10)
        params = fit_logistic_calibration(records)
        assert params.auc is not None

    def test_raises_on_too_few_records(self):
        records = _make_records(3, 3)
        with pytest.raises(ValueError, match="records"):
            fit_logistic_calibration(records)

    def test_raises_on_too_few_positives(self):
        records = (
            [MABacktestRecord(score=0.8, label=1)] * 2
            + [MABacktestRecord(score=0.2, label=0)] * 12
        )
        with pytest.raises(ValueError, match="positive"):
            fit_logistic_calibration(records)

    def test_raises_on_too_few_negatives(self):
        records = (
            [MABacktestRecord(score=0.8, label=1)] * 12
            + [MABacktestRecord(score=0.2, label=0)] * 2
        )
        with pytest.raises(ValueError, match="negative"):
            fit_logistic_calibration(records)


# ---------------------------------------------------------------------------
# Tests: save / load calibration params
# ---------------------------------------------------------------------------

class TestSaveLoadCalibrationParams:

    def test_round_trip(self, tmp_path):
        records = _make_records(10, 10)
        params = fit_logistic_calibration(records)
        dest = tmp_path / "calib.json"
        returned_path = save_calibration_params(params, dest)
        assert returned_path == dest
        assert dest.exists()

        slope, midpoint = load_calibration_params(dest)
        assert slope == pytest.approx(params.slope, rel=1e-9)
        assert midpoint == pytest.approx(params.midpoint, rel=1e-9)

    def test_json_contains_metadata(self, tmp_path):
        records = _make_records(10, 10)
        params = fit_logistic_calibration(records)
        dest = tmp_path / "calib.json"
        save_calibration_params(params, dest)
        raw = json.loads(dest.read_text())
        for key in ("slope", "midpoint", "n_positive", "n_negative", "base_rate",
                    "auc", "brier_score", "training_window", "created_at", "source"):
            assert key in raw

    def test_fallback_when_file_missing(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            slope, midpoint = load_calibration_params(missing)
        assert slope == _DEFAULT_SLOPE
        assert midpoint == _DEFAULT_MIDPOINT
        assert len(caught) == 1
        assert issubclass(caught[0].category, UserWarning)
        assert "hard-coded defaults" in str(caught[0].message)

    def test_fallback_on_malformed_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            slope, midpoint = load_calibration_params(bad)
        assert slope == _DEFAULT_SLOPE
        assert midpoint == _DEFAULT_MIDPOINT
        assert len(caught) == 1

    def test_fallback_on_missing_keys(self, tmp_path):
        incomplete = tmp_path / "incomplete.json"
        incomplete.write_text('{"slope": 5.0}')  # missing "midpoint"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            slope, midpoint = load_calibration_params(incomplete)
        assert slope == _DEFAULT_SLOPE
        assert midpoint == _DEFAULT_MIDPOINT


# ---------------------------------------------------------------------------
# Tests: adjust_for_base_rate
# ---------------------------------------------------------------------------

class TestAdjustForBaseRate:

    def test_identity_when_same_base_rate(self):
        p = 0.30
        adjusted = adjust_for_base_rate(p, training_base_rate=0.10, target_base_rate=0.10)
        assert adjusted == pytest.approx(p, abs=1e-5)

    def test_higher_target_base_rate_raises_probability(self):
        # If deployment environment has more acquisitions, inflate probability
        p = adjust_for_base_rate(0.20, training_base_rate=0.05, target_base_rate=0.20)
        assert p > 0.20

    def test_lower_target_base_rate_lowers_probability(self):
        # If deployment environment has fewer acquisitions, deflate probability
        p = adjust_for_base_rate(0.40, training_base_rate=0.30, target_base_rate=0.05)
        assert p < 0.40

    def test_output_in_unit_interval(self):
        for raw in (0.01, 0.10, 0.50, 0.90, 0.99):
            p = adjust_for_base_rate(raw, training_base_rate=0.25, target_base_rate=0.10)
            assert 0.0 <= p <= 1.0

    def test_invalid_training_base_rate_raises(self):
        with pytest.raises(ValueError, match="training_base_rate"):
            adjust_for_base_rate(0.5, training_base_rate=0.0, target_base_rate=0.1)
        with pytest.raises(ValueError, match="training_base_rate"):
            adjust_for_base_rate(0.5, training_base_rate=1.0, target_base_rate=0.1)

    def test_invalid_target_base_rate_raises(self):
        with pytest.raises(ValueError, match="target_base_rate"):
            adjust_for_base_rate(0.5, training_base_rate=0.1, target_base_rate=0.0)
        with pytest.raises(ValueError, match="target_base_rate"):
            adjust_for_base_rate(0.5, training_base_rate=0.1, target_base_rate=1.0)

    def test_log_odds_shift_formula_explicit(self):
        import math
        # Manual computation
        raw_prob = 0.30
        train_br = 0.10
        target_br = 0.20
        raw_lo = math.log(raw_prob / (1 - raw_prob))
        train_lo = math.log(train_br / (1 - train_br))
        target_lo = math.log(target_br / (1 - target_br))
        adj_lo = raw_lo - train_lo + target_lo
        expected = 1.0 / (1.0 + math.exp(-adj_lo))
        result = adjust_for_base_rate(raw_prob, train_br, target_br)
        assert result == pytest.approx(expected, rel=1e-5)


# ---------------------------------------------------------------------------
# Tests: ma_layer5_calibration — _try_load_calibration_params and
#         _derive_logistic_probability integration
# ---------------------------------------------------------------------------

class TestLayer5CalibrationParamLoading:

    def test_fallback_when_no_json(self, tmp_path, monkeypatch):
        """When calibration JSON is absent, _try_load_calibration_params warns and returns defaults."""
        import bve.intelligence.ma_layer5_calibration as l5
        missing = tmp_path / "absent.json"
        monkeypatch.setattr(l5, "_CALIBRATION_PARAMS_PATH", missing)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            slope, midpoint = l5._try_load_calibration_params()
        assert slope == l5._LOGISTIC_SLOPE
        assert midpoint == l5._LOGISTIC_MIDPOINT
        assert any(issubclass(w.category, UserWarning) for w in caught)

    def test_loads_from_json_when_present(self, tmp_path, monkeypatch):
        """When JSON is present, _try_load_calibration_params returns its values."""
        import bve.intelligence.ma_layer5_calibration as l5
        params_path = tmp_path / "calib.json"
        params_path.write_text(json.dumps({"slope": 12.5, "midpoint": 0.55}))
        monkeypatch.setattr(l5, "_CALIBRATION_PARAMS_PATH", params_path)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            slope, midpoint = l5._try_load_calibration_params()
        assert slope == pytest.approx(12.5, rel=1e-9)
        assert midpoint == pytest.approx(0.55, rel=1e-9)

    def test_derive_logistic_probability_uses_effective_params(self, tmp_path, monkeypatch):
        """_derive_logistic_probability uses _EFFECTIVE_SLOPE and _EFFECTIVE_MIDPOINT."""
        import bve.intelligence.ma_layer5_calibration as l5
        import math

        # Patch effective params to known values
        monkeypatch.setattr(l5, "_EFFECTIVE_SLOPE", 4.0)
        monkeypatch.setattr(l5, "_EFFECTIVE_MIDPOINT", 0.50)

        score = 0.70
        expected = 1.0 / (1.0 + math.exp(-(4.0 * (score - 0.50))))
        result = l5._derive_logistic_probability(score)
        assert result == pytest.approx(expected, rel=1e-5)

    def test_derive_logistic_probability_with_default_params(self):
        """_derive_logistic_probability falls back correctly when no JSON exists."""
        import bve.intelligence.ma_layer5_calibration as l5
        import math

        # Compute expected with defaults (8.0, 0.68) — might be loaded or defaults
        score = 0.75
        expected = 1.0 / (1.0 + math.exp(-(l5._EFFECTIVE_SLOPE * (score - l5._EFFECTIVE_MIDPOINT))))
        result = l5._derive_logistic_probability(score)
        assert result == pytest.approx(expected, rel=1e-5)


# ---------------------------------------------------------------------------
# Tests: build_backtest_records_from_deal_universe
# ---------------------------------------------------------------------------

class TestBuildBacktestRecordsFromDealUniverse:

    def _make_yaml(self, tmp_path, deals: list[dict]) -> Path:
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml not installed")
        p = tmp_path / "deals.yaml"
        p.write_text(yaml.dump({"deals": deals}))
        return p

    def test_positives_and_negatives_created(self, tmp_path):
        deals = [
            {"announcement_date": "2022-06-01", "target_ticker": "TGTA",
             "phase_at_acquisition": "phase_3"},
            {"announcement_date": "2023-03-15", "target_ticker": "TGTB",
             "phase_at_acquisition": "approved"},
        ]
        yaml_path = self._make_yaml(tmp_path, deals)
        records = build_backtest_records_from_deal_universe(
            yaml_path, n_negatives_per_positive=2
        )
        positives = [r for r in records if r.label == 1]
        negatives = [r for r in records if r.label == 0]
        assert len(positives) == 2
        assert len(negatives) == 4  # 2 × 2

    def test_prediction_date_is_12_months_before_announcement(self, tmp_path):
        deals = [{"announcement_date": "2023-09-01", "target_ticker": "ABC",
                  "phase_at_acquisition": "phase_2"}]
        yaml_path = self._make_yaml(tmp_path, deals)
        records = build_backtest_records_from_deal_universe(yaml_path)
        positives = [r for r in records if r.label == 1]
        assert positives[0].prediction_date == date(2022, 9, 1)

    def test_heuristic_score_for_approved(self, tmp_path):
        deals = [{"announcement_date": "2022-01-01", "target_ticker": "X",
                  "phase_at_acquisition": "approved"}]
        yaml_path = self._make_yaml(tmp_path, deals)
        records = build_backtest_records_from_deal_universe(yaml_path)
        positives = [r for r in records if r.label == 1]
        assert positives[0].score == pytest.approx(0.80, abs=1e-9)

    def test_heuristic_score_for_phase3(self, tmp_path):
        deals = [{"announcement_date": "2022-01-01", "target_ticker": "X",
                  "phase_at_acquisition": "phase_3"}]
        yaml_path = self._make_yaml(tmp_path, deals)
        records = build_backtest_records_from_deal_universe(yaml_path)
        positives = [r for r in records if r.label == 1]
        assert positives[0].score == pytest.approx(0.70, abs=1e-9)

    def test_negative_scores_in_range(self, tmp_path):
        deals = [
            {"announcement_date": "2022-06-01", "phase_at_acquisition": "phase_2"}
            for _ in range(5)
        ]
        yaml_path = self._make_yaml(tmp_path, deals)
        lo, hi = 0.15, 0.55
        records = build_backtest_records_from_deal_universe(
            yaml_path, negative_score_lo=lo, negative_score_hi=hi
        )
        for r in records:
            if r.label == 0:
                assert lo <= r.score <= hi

    def test_reproducible_negatives_same_seed(self, tmp_path):
        deals = [{"announcement_date": "2022-06-01", "phase_at_acquisition": "phase_2"}
                 for _ in range(3)]
        yaml_path = self._make_yaml(tmp_path, deals)
        r1 = build_backtest_records_from_deal_universe(yaml_path, seed=77)
        r2 = build_backtest_records_from_deal_universe(yaml_path, seed=77)
        neg1 = [r.score for r in r1 if r.label == 0]
        neg2 = [r.score for r in r2 if r.label == 0]
        assert neg1 == neg2

    def test_different_seeds_produce_different_negatives(self, tmp_path):
        deals = [{"announcement_date": "2022-06-01", "phase_at_acquisition": "phase_2"}
                 for _ in range(5)]
        yaml_path = self._make_yaml(tmp_path, deals)
        r1 = build_backtest_records_from_deal_universe(yaml_path, seed=1)
        r2 = build_backtest_records_from_deal_universe(yaml_path, seed=2)
        neg1 = [r.score for r in r1 if r.label == 0]
        neg2 = [r.score for r in r2 if r.label == 0]
        assert neg1 != neg2

    def test_deals_missing_announcement_date_skipped(self, tmp_path):
        deals = [
            {"phase_at_acquisition": "phase_2"},  # no announcement_date
            {"announcement_date": "2023-05-01", "phase_at_acquisition": "phase_3"},
        ]
        yaml_path = self._make_yaml(tmp_path, deals)
        records = build_backtest_records_from_deal_universe(yaml_path)
        positives = [r for r in records if r.label == 1]
        assert len(positives) == 1  # only the one with a date
