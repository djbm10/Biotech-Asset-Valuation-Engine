"""Brier decomposition math + calibration regression anchors.

Two layers:
1. Pure-math properties of ``brier_decomposition`` (dataset-independent).
2. Regression anchors pinning the in-sample calibration of the oncology POS
   backtest. These use the *authoritative* model path — ``run_backtest_from_csv``
   → ``BacktestReport.to_calibration_records()`` (real model scores), NOT the
   deprecated ``pos_calibration.load_from_backtest_csv`` proxy whose own warning
   states its metrics "do not reflect true model performance".

   The anchors are deliberately coupled to
   ``research/data/oncology_phase_transitions.csv``: if that dataset or the POS
   model changes, these assertions SHOULD fail — re-baseline the constants below
   only after confirming the new numbers are intended. Tolerances are wide
   enough to ignore formatting / bucket-boundary noise but narrow enough to
   catch genuine calibration drift.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from bve.analysis import pos_calibration as pc
from bve.analysis.backtest import run_backtest_from_csv
from bve.analysis.calibration_metrics import brier_decomposition

_PHASE_TRANSITIONS_CSV = Path("research/data/phase_transitions.csv")
_ONCOLOGY_CSV = Path("research/data/oncology_phase_transitions.csv")

# --- regression anchors (re-baseline only on intended dataset/model change) ---
# Authoritative model path; values captured 2026-06-22.
_ANCHOR_N = 155
_ANCHOR_BRIER = 0.2318
_ANCHOR_AUC = 0.6980
_ANCHOR_ECE = 0.1330
_ANCHOR_RELIABILITY = 0.021
_ANCHOR_RESOLUTION = 0.030
_ANCHOR_UNCERTAINTY = 0.250
_METRIC_TOL = 0.01


# ---------------------------------------------------------------------------
# Pure-math properties
# ---------------------------------------------------------------------------


def test_identity_holds_exactly_random():
    import random

    random.seed(0)
    probs = [random.random() for _ in range(300)]
    labels = [1 if random.random() < p else 0 for p in probs]
    d = brier_decomposition(probs, labels)
    # binned Brier == reliability − resolution + uncertainty, to fp precision
    assert abs(d.identity_residual) < 1e-9


def test_perfect_calibration_zero_reliability():
    probs = [0.0] * 50 + [1.0] * 50
    labels = [0] * 50 + [1] * 50
    d = brier_decomposition(probs, labels)
    assert d.reliability < 1e-9
    assert d.uncertainty == pytest.approx(0.25)
    assert abs(d.identity_residual) < 1e-9


def test_top_bin_includes_forecast_of_one():
    # A forecast of exactly 1.0 must not be dropped from the top bin.
    d = brier_decomposition([1.0] * 10, [1] * 10)
    assert d.n == 10
    assert abs(d.identity_residual) < 1e-9


def test_uncertainty_is_base_rate_variance():
    labels = [1] * 30 + [0] * 70
    probs = [0.5] * 100
    d = brier_decomposition(probs, labels)
    assert d.uncertainty == pytest.approx(0.3 * 0.7)


def test_empty_input_is_safe():
    d = brier_decomposition([], [])
    assert d.n == 0
    assert d.reconstructed == 0.0


def test_resolution_higher_when_model_separates_classes():
    # Model that separates outcomes well has higher resolution than a flat one.
    sep = brier_decomposition([0.1] * 50 + [0.9] * 50, [0] * 50 + [1] * 50)
    flat = brier_decomposition([0.5] * 100, [0] * 50 + [1] * 50)
    assert sep.resolution > flat.resolution


# ---------------------------------------------------------------------------
# Regression anchors — oncology backtest calibration
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def phase_transitions_overall():
    if not _PHASE_TRANSITIONS_CSV.exists():
        pytest.skip(f"dataset not present: {_PHASE_TRANSITIONS_CSV}")
    # Authoritative model scores (see module docstring) rather than the
    # deprecated proxy loader.
    report = run_backtest_from_csv(str(_PHASE_TRANSITIONS_CSV))
    records = report.to_calibration_records()
    suite = pc.run_pos_calibration_from_records(records)
    assert suite.overall is not None
    return suite.overall, len(records)


def _rebaseline_msg(name, actual, anchor):
    return (
        f"{name}={actual:.4f} drifted from anchor {anchor:.4f}. "
        "If the dataset/model change is intended, update the anchor constant."
    )


def test_record_count_anchor(phase_transitions_overall):
    _, n = phase_transitions_overall
    assert n == _ANCHOR_N, _rebaseline_msg("n_records", n, _ANCHOR_N)


def test_brier_anchor(phase_transitions_overall):
    overall, _ = phase_transitions_overall
    assert overall.brier_score == pytest.approx(_ANCHOR_BRIER, abs=_METRIC_TOL), (
        _rebaseline_msg("brier", overall.brier_score, _ANCHOR_BRIER)
    )


def test_auc_anchor(phase_transitions_overall):
    overall, _ = phase_transitions_overall
    assert overall.auc == pytest.approx(_ANCHOR_AUC, abs=_METRIC_TOL), (
        _rebaseline_msg("auc", overall.auc, _ANCHOR_AUC)
    )


def test_ece_anchor(phase_transitions_overall):
    overall, _ = phase_transitions_overall
    assert overall.ece == pytest.approx(_ANCHOR_ECE, abs=_METRIC_TOL), (
        _rebaseline_msg("ece", overall.ece, _ANCHOR_ECE)
    )


def test_decomposition_anchor_and_identity(phase_transitions_overall):
    overall, _ = phase_transitions_overall
    d = overall.decomposition
    assert d is not None
    assert d.reliability == pytest.approx(_ANCHOR_RELIABILITY, abs=_METRIC_TOL)
    assert d.resolution == pytest.approx(_ANCHOR_RESOLUTION, abs=_METRIC_TOL)
    assert d.uncertainty == pytest.approx(_ANCHOR_UNCERTAINTY, abs=_METRIC_TOL)
    # identity exact on the real dataset
    assert abs(d.identity_residual) < 1e-9
    # binned Brier tracks the raw headline Brier within bucketing noise
    assert math.isclose(d.binned_brier, overall.brier_score, abs_tol=0.02)


def test_headline_backtest_report_prints_in_sample_and_oos_metrics():
    from bve.analysis.backtest import print_report

    if not _PHASE_TRANSITIONS_CSV.exists():
        pytest.skip(f"dataset not present: {_PHASE_TRANSITIONS_CSV}")

    report = run_backtest_from_csv(str(_PHASE_TRANSITIONS_CSV))
    suite = report.calibration_suite

    assert suite is not None
    assert suite.time_split_year == 2022
    assert suite.overall is not None
    assert suite.oos_overall is not None
    assert suite.overall.brier_score is not None
    assert suite.overall.auc is not None
    assert suite.overall.ece is not None
    assert suite.oos_overall.brier_score is not None
    assert suite.oos_overall.auc is not None
    assert suite.oos_overall.ece is not None

    rendered = print_report(report)
    assert "Calibration Metrics: in-sample vs OOS (split year 2022)" in rendered
    assert "In-sample" in rendered
    assert "OOS" in rendered


def test_headline_backtest_reports_oos_recalibration_metrics():
    from bve.analysis.backtest import print_report

    if not _PHASE_TRANSITIONS_CSV.exists():
        pytest.skip(f"dataset not present: {_PHASE_TRANSITIONS_CSV}")

    report = run_backtest_from_csv(str(_PHASE_TRANSITIONS_CSV))
    suite = report.calibration_suite

    assert suite is not None
    recalibration = suite.recalibration
    assert recalibration is not None
    assert recalibration.method == "isotonic"
    assert recalibration.time_split_year == 2022
    assert recalibration.n_train > 0
    assert recalibration.n_oos > 0
    assert recalibration.raw_oos is not None
    assert recalibration.calibrated_oos is not None
    assert recalibration.raw_oos.n == suite.oos_overall.n
    assert recalibration.calibrated_oos.n == suite.oos_overall.n
    assert recalibration.raw_oos.brier_score is not None
    assert recalibration.calibrated_oos.brier_score is not None
    assert recalibration.raw_oos.ece is not None
    assert recalibration.calibrated_oos.ece is not None

    payload = suite.to_dict()
    assert payload["recalibration"]["raw_oos"]["n"] == suite.oos_overall.n
    assert payload["recalibration"]["calibrated_oos"]["n"] == suite.oos_overall.n

    rendered = print_report(report)
    assert "OOS Recalibration (isotonic, fit <2022)" in rendered
    assert "Raw OOS" in rendered
    assert "Calibrated OOS" in rendered


def test_expanded_backtest_dataset_includes_non_oncology_tas():
    if not _PHASE_TRANSITIONS_CSV.exists():
        pytest.skip(f"dataset not present: {_PHASE_TRANSITIONS_CSV}")

    report = run_backtest_from_csv(str(_PHASE_TRANSITIONS_CSV))
    tas = {r.case.therapeutic_area for r in report.results}

    assert "oncology" in tas
    assert {"immunology", "cns", "metabolic"}.issubset(tas)


def test_legacy_oncology_dataset_remains_oncology_only():
    if not _ONCOLOGY_CSV.exists():
        pytest.skip(f"dataset not present: {_ONCOLOGY_CSV}")

    report = run_backtest_from_csv(str(_ONCOLOGY_CSV))
    tas = {r.case.therapeutic_area for r in report.results}

    assert tas == {"oncology"}
