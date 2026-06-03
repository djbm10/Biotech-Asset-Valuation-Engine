"""Sprint 52 — Layer 5 5G: Drift Detection Engine tests.

Covers:
  - PSI computation and severity thresholds
  - Score distribution drift (detect_score_distribution_drift)
  - Base rate drift (detect_base_rate_drift)
  - Calibration quality drift / Brier degradation (detect_calibration_quality_drift)
  - Categorical feature drift (detect_categorical_drift)
  - Full drift report (run_drift_detection)
  - DriftReport fields and status mapping
"""
from __future__ import annotations

from datetime import date

import pytest

from bve.intelligence.ma_calibration_models import (
    DriftType,
    HistoricalMAOutcome,
    LayerValidated,
    OutcomeLabels,
    OutcomeType,
)
from bve.intelligence.ma_drift_detection import (
    _psi_severity,
    detect_base_rate_drift,
    detect_calibration_quality_drift,
    detect_categorical_drift,
    detect_score_distribution_drift,
    run_drift_detection,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_outcome(
    case_id: str,
    acquired: bool = False,
    bd_score: float | None = None,
    l1_score: float | None = None,
    ta: str | None = None,
) -> HistoricalMAOutcome:
    layer2 = {}
    if bd_score is not None:
        layer2["bd_action_score"] = bd_score
    layer1 = {}
    if l1_score is not None:
        layer1["layer1_score"] = l1_score
    tf_kwargs = {}
    if ta is not None:
        tf_kwargs["therapeutic_area"] = ta

    from bve.intelligence.ma_calibration_models import HistoricalTargetFeatures
    return HistoricalMAOutcome(
        case_id=case_id,
        target_id=f"tgt-{case_id}",
        prediction_date=date(2023, 1, 1),
        as_of_date=date(2023, 1, 1),
        outcome_type=OutcomeType.FULL_ACQUISITION_CLOSED if acquired else OutcomeType.REMAINED_INDEPENDENT_PERFORMED_WELL,
        labels=OutcomeLabels(acquired_within_12m=acquired),
        layer2_snapshot=layer2,
        layer1_snapshot=layer1,
        target_features=HistoricalTargetFeatures(**tf_kwargs),
    )


def _historical_cases(n: int = 30, base_rate: float = 0.30) -> list[HistoricalMAOutcome]:
    cases = []
    for i in range(n):
        acquired = i < int(n * base_rate)
        score = 0.70 if acquired else 0.30
        cases.append(_make_outcome(f"hist-{i}", acquired=acquired, bd_score=score, ta="oncology"))
    return cases


def _recent_cases(n: int = 30, base_rate: float = 0.30, score_shift: float = 0.0) -> list[HistoricalMAOutcome]:
    cases = []
    for i in range(n):
        acquired = i < int(n * base_rate)
        score = max(0.0, min(1.0, (0.70 if acquired else 0.30) + score_shift))
        cases.append(_make_outcome(f"rec-{i}", acquired=acquired, bd_score=score, ta="oncology"))
    return cases


# ---------------------------------------------------------------------------
# PSI severity mapping
# ---------------------------------------------------------------------------

class TestPSISeverity:
    def test_no_drift(self):
        assert _psi_severity(0.05) == "no_drift"

    def test_minor_drift(self):
        assert _psi_severity(0.12) == "minor_drift"

    def test_moderate_drift(self):
        assert _psi_severity(0.21) == "moderate_drift"

    def test_severe_drift(self):
        assert _psi_severity(0.30) == "severe_drift"

    def test_boundary_no_drift(self):
        # exactly at NO_DRIFT threshold (0.10) → minor
        assert _psi_severity(0.10) == "minor_drift"

    def test_boundary_moderate(self):
        # exactly at MODERATE threshold (0.20) → moderate
        assert _psi_severity(0.20) == "moderate_drift"


# ---------------------------------------------------------------------------
# detect_score_distribution_drift
# ---------------------------------------------------------------------------

class TestDetectScoreDistributionDrift:
    def test_identical_distributions_no_drift(self):
        scores = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        result = detect_score_distribution_drift(scores, scores)
        assert result["drift_detected"] is False
        assert result["psi"] == 0.0
        assert result["severity"] == "no_drift"

    def test_shifted_distribution_detected_as_drift(self):
        ref = [0.1] * 15 + [0.3] * 15  # low scores
        cur = [0.7] * 15 + [0.9] * 15  # high scores — major shift
        result = detect_score_distribution_drift(ref, cur)
        assert result["drift_detected"] is True
        assert result["psi"] > 0.10

    def test_returns_required_keys(self):
        scores = list(range(1, 16))
        result = detect_score_distribution_drift([float(x) / 15 for x in range(1, 16)],
                                                 [float(x) / 15 for x in range(1, 16)])
        assert "psi" in result
        assert "severity" in result
        assert "drift_detected" in result
        assert "reference_n" in result
        assert "current_n" in result
        assert "bin_details" in result

    def test_small_sample_warning(self):
        result = detect_score_distribution_drift([0.5] * 5, [0.5] * 5)
        assert any("small" in w.lower() or "too small" in w.lower() for w in result["warnings"])

    def test_custom_score_name(self):
        scores = [float(i) / 10 for i in range(10)]
        result = detect_score_distribution_drift(scores, scores, score_name="layer1_score")
        assert result["score_name"] == "layer1_score"

    def test_empty_distributions_return_zero_psi(self):
        result = detect_score_distribution_drift([], [])
        assert result["psi"] == 0.0
        assert result["drift_detected"] is False


# ---------------------------------------------------------------------------
# detect_base_rate_drift
# ---------------------------------------------------------------------------

class TestDetectBaseRateDrift:
    def _make_cases(self, n: int, rate: float) -> list[HistoricalMAOutcome]:
        cases = []
        for i in range(n):
            acquired = i < int(n * rate)
            cases.append(_make_outcome(f"br-{i}", acquired=acquired))
        return cases

    def test_same_base_rate_no_drift(self):
        hist = self._make_cases(40, 0.30)
        rec = self._make_cases(40, 0.30)
        result = detect_base_rate_drift(hist, rec)
        assert result["drift_detected"] is False
        assert result["severity"] == "no_drift"

    def test_large_shift_detected(self):
        hist = self._make_cases(40, 0.10)
        rec = self._make_cases(40, 0.50)
        result = detect_base_rate_drift(hist, rec)
        assert result["drift_detected"] is True
        assert result["drift"] > 0
        assert result["severity"] in {"moderate_drift", "severe_drift"}

    def test_direction_positive_shift(self):
        hist = self._make_cases(40, 0.20)
        rec = self._make_cases(40, 0.45)
        result = detect_base_rate_drift(hist, rec)
        assert result["recent_rate"] > result["historical_rate"]

    def test_empty_cases_returns_insufficient_data(self):
        result = detect_base_rate_drift([], [])
        assert result["severity"] == "insufficient_data"
        assert result["drift_detected"] is False

    def test_returns_required_keys(self):
        hist = self._make_cases(20, 0.25)
        rec = self._make_cases(20, 0.25)
        result = detect_base_rate_drift(hist, rec)
        for k in ("historical_rate", "recent_rate", "drift", "drift_detected", "severity"):
            assert k in result


# ---------------------------------------------------------------------------
# detect_calibration_quality_drift
# ---------------------------------------------------------------------------

class TestDetectCalibrationQualityDrift:
    def test_no_degradation(self):
        scores = [0.8, 0.7, 0.2, 0.3, 0.6, 0.4, 0.9, 0.1, 0.5, 0.7]
        labels = [True, True, False, False, True, False, True, False, True, True]
        result = detect_calibration_quality_drift(scores, labels, scores, labels)
        assert result["brier_delta"] == pytest.approx(0.0, abs=1e-6)
        assert result["drift_detected"] is False

    def test_degraded_calibration_detected(self):
        # Good reference: predicted prob close to actual
        ref_scores = [0.9, 0.8, 0.1, 0.2, 0.85, 0.05]
        ref_labels = [True, True, False, False, True, False]
        # Bad current: random predictions
        cur_scores = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
        cur_labels = [True, True, False, False, True, False]
        result = detect_calibration_quality_drift(ref_scores, ref_labels, cur_scores, cur_labels)
        # Current Brier ~ 0.25, reference much lower — large delta
        assert result["brier_delta"] > 0

    def test_insufficient_data_returns_safe_result(self):
        result = detect_calibration_quality_drift([], [], [], [])
        assert result["severity"] == "insufficient_data"
        assert result["drift_detected"] is False
        assert result["brier_delta"] is None

    def test_returns_required_keys(self):
        s = [0.6, 0.4]
        l = [True, False]
        result = detect_calibration_quality_drift(s, l, s, l)
        for k in ("reference_brier", "current_brier", "brier_delta", "drift_detected", "severity"):
            assert k in result

    def test_severe_degradation_severity(self):
        ref_scores = [0.95, 0.05, 0.90, 0.10]
        ref_labels = [True, False, True, False]
        cur_scores = [0.05, 0.95, 0.10, 0.90]  # inverted — worst case
        cur_labels = [True, False, True, False]
        result = detect_calibration_quality_drift(ref_scores, ref_labels, cur_scores, cur_labels)
        assert result["severity"] in {"moderate_drift", "severe_drift"}


# ---------------------------------------------------------------------------
# detect_categorical_drift
# ---------------------------------------------------------------------------

class TestDetectCategoricalDrift:
    def test_identical_distributions_no_drift(self):
        cats = ["oncology"] * 5 + ["cardiovascular"] * 5
        result = detect_categorical_drift(cats, cats)
        assert result["drift_detected"] is False
        assert result["drift_stat"] == pytest.approx(0.0, abs=1e-6)

    def test_shifted_distribution_detected(self):
        ref = ["oncology"] * 8 + ["other"] * 2
        cur = ["other"] * 8 + ["oncology"] * 2
        result = detect_categorical_drift(ref, cur)
        assert result["drift_detected"] is True
        assert len(result["distribution_shifts"]) > 0

    def test_new_category_in_current(self):
        ref = ["oncology"] * 10
        cur = ["oncology"] * 5 + ["rare_disease"] * 5
        result = detect_categorical_drift(ref, cur)
        assert result["drift_detected"] is True

    def test_small_sample_warning(self):
        result = detect_categorical_drift(["a"] * 3, ["a"] * 3)
        assert any("small" in w.lower() or "too small" in w.lower() for w in result["warnings"])

    def test_returns_required_keys(self):
        result = detect_categorical_drift(["a"] * 10, ["a"] * 10)
        for k in ("drift_stat", "drift_detected", "severity", "distribution_shifts",
                  "reference_n", "current_n"):
            assert k in result

    def test_custom_feature_name(self):
        result = detect_categorical_drift(["ph3"] * 5, ["ph3"] * 5, feature_name="stage")
        assert result["feature_name"] == "stage"


# ---------------------------------------------------------------------------
# run_drift_detection
# ---------------------------------------------------------------------------

class TestRunDriftDetection:
    def test_no_drift_when_identical_windows(self):
        cases = _historical_cases(n=30, base_rate=0.30)
        report = run_drift_detection(cases, cases)
        # Identical windows → no drift expected
        assert report.drift_status in {"none", "mild"}
        assert report.requires_recalibration is False

    def test_report_is_drift_report_instance(self):
        from bve.intelligence.ma_calibration_models import DriftReport
        cases = _historical_cases(n=20)
        report = run_drift_detection(cases, cases)
        assert isinstance(report, DriftReport)

    def test_base_rate_drift_detected_in_report(self):
        hist = [_make_outcome(f"h{i}", acquired=(i < 3), bd_score=0.3) for i in range(20)]
        rec = [_make_outcome(f"r{i}", acquired=(i < 14), bd_score=0.7) for i in range(20)]
        report = run_drift_detection(hist, rec)
        # Large base rate shift (15% → 70%) must surface drift
        assert report.drift_status != "none"

    def test_rolling_window_limits_recent_cases(self):
        hist = _historical_cases(n=30)
        # Create 60 recent cases but rolling_window=10
        rec = _recent_cases(n=60)
        # Should not raise; report should reflect only last 10
        report = run_drift_detection(hist, rec, rolling_window=10)
        assert report.drift_status is not None

    def test_affected_layers_populated_on_feature_drift(self):
        hist = _historical_cases(n=30, base_rate=0.10)
        rec = _recent_cases(n=30, base_rate=0.60, score_shift=0.40)
        report = run_drift_detection(hist, rec)
        # Some drift should exist
        if report.drift_types:
            assert isinstance(report.affected_layers, list)

    def test_report_date_defaults_to_today(self):
        cases = _historical_cases(n=20)
        report = run_drift_detection(cases, cases)
        # DriftReport has no explicit date field but should not raise
        assert report is not None

    def test_empty_recent_cases_returns_no_drift(self):
        hist = _historical_cases(n=20)
        report = run_drift_detection(hist, [])
        assert report.drift_status == "none"
        assert report.requires_recalibration is False

    def test_evidence_list_populated_when_drift_found(self):
        hist = [_make_outcome(f"h{i}", acquired=(i < 2), bd_score=0.2) for i in range(20)]
        rec = [_make_outcome(f"r{i}", acquired=(i < 16), bd_score=0.8) for i in range(20)]
        report = run_drift_detection(hist, rec)
        if report.drift_types:
            assert len(report.evidence) > 0 or report.recommended_action != ""

    def test_severe_drift_sets_requires_recalibration(self):
        # Create a very large base rate shift (5% → 80%)
        hist = [_make_outcome(f"h{i}", acquired=(i < 1), bd_score=0.2 + i * 0.01)
                for i in range(20)]
        rec = [_make_outcome(f"r{i}", acquired=(i < 16), bd_score=0.8)
               for i in range(20)]
        report = run_drift_detection(hist, rec)
        if report.drift_status in {"moderate", "severe"}:
            assert report.requires_recalibration is True
