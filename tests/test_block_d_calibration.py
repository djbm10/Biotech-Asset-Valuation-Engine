"""Tests for Block D: retroactive calibration fitting from historical_calibration_cases.yaml."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_cases_yaml(tmp_path: Path, n_pos: int = 5, n_neg: int = 10) -> Path:
    """Write a minimal cases YAML with n_pos positives and n_neg negatives."""
    cases = []
    for i in range(n_pos):
        cases.append({
            "ticker": f"POS{i}",
            "company_name": f"Positive Co {i}",
            "observation_date": "2022-01-01",
            "target_stage": "phase_3",
            "therapeutic_area": "oncology",
            "modality": "small_molecule",
            "cash_runway_months_as_of": 18.0,
            "seller_willingness_as_of": 0.65,
            "catalyst_days_as_of": 60,
            "asset_quality_score_as_of": 0.80,
            "acquirer_fit_score_as_of": 0.85,
            "outcome_12m": True,
            "outcome_type": "acquisition",
            "outcome_date": "2022-10-01",
            "lookahead_pass": True,
        })
    for i in range(n_neg):
        cases.append({
            "ticker": f"NEG{i}",
            "company_name": f"Negative Co {i}",
            "observation_date": "2022-01-01",
            "target_stage": "phase_2",
            "therapeutic_area": "oncology",
            "modality": "small_molecule",
            "cash_runway_months_as_of": 12.0,
            "seller_willingness_as_of": 0.35,
            "catalyst_days_as_of": None,
            "asset_quality_score_as_of": 0.45,
            "acquirer_fit_score_as_of": 0.40,
            "outcome_12m": False,
            "outcome_type": None,
            "outcome_date": None,
            "lookahead_pass": True,
        })
    p = tmp_path / "cases.yaml"
    p.write_text(yaml.dump({"cases": cases}))
    return p


# ---------------------------------------------------------------------------
# build_backtest_records_from_calibration_cases
# ---------------------------------------------------------------------------

def test_builder_returns_correct_count(tmp_path):
    cases_path = _minimal_cases_yaml(tmp_path, n_pos=5, n_neg=10)
    from bve.intelligence.ma_backtest import build_backtest_records_from_calibration_cases
    records = build_backtest_records_from_calibration_cases(cases_path)
    assert len(records) == 15


def test_builder_labels_correct(tmp_path):
    cases_path = _minimal_cases_yaml(tmp_path, n_pos=5, n_neg=10)
    from bve.intelligence.ma_backtest import build_backtest_records_from_calibration_cases
    records = build_backtest_records_from_calibration_cases(cases_path)
    assert sum(r.label for r in records) == 5


def test_builder_scores_bounded(tmp_path):
    cases_path = _minimal_cases_yaml(tmp_path, n_pos=5, n_neg=10)
    from bve.intelligence.ma_backtest import build_backtest_records_from_calibration_cases
    records = build_backtest_records_from_calibration_cases(cases_path)
    for r in records:
        assert 0.0 <= r.score <= 1.0, f"score {r.score} out of range"


def test_builder_positives_score_higher_than_negatives(tmp_path):
    """Positive cases (high features) should score above negative cases (low features)."""
    cases_path = _minimal_cases_yaml(tmp_path, n_pos=5, n_neg=10)
    from bve.intelligence.ma_backtest import build_backtest_records_from_calibration_cases
    records = build_backtest_records_from_calibration_cases(cases_path)
    pos_scores = [r.score for r in records if r.label == 1]
    neg_scores = [r.score for r in records if r.label == 0]
    assert sum(pos_scores) / len(pos_scores) > sum(neg_scores) / len(neg_scores)


def test_builder_observation_date_parsed(tmp_path):
    cases_path = _minimal_cases_yaml(tmp_path, n_pos=2, n_neg=3)
    from bve.intelligence.ma_backtest import build_backtest_records_from_calibration_cases
    records = build_backtest_records_from_calibration_cases(cases_path)
    for r in records:
        assert r.prediction_date == date(2022, 1, 1)


def test_builder_uses_real_cases_file():
    """The real historical_calibration_cases.yaml loads without error."""
    from bve.intelligence.ma_backtest import build_backtest_records_from_calibration_cases
    records = build_backtest_records_from_calibration_cases()
    assert len(records) >= 50
    assert sum(r.label for r in records) >= 10
    assert len(records) - sum(r.label for r in records) >= 10


# ---------------------------------------------------------------------------
# composite_score_from_yaml_features
# ---------------------------------------------------------------------------

def test_composite_score_approved_stage():
    from bve.intelligence.ma_backtest import _composite_score_from_yaml_features
    score = _composite_score_from_yaml_features(0.80, 0.85, 0.65, "approved")
    assert 0.70 <= score <= 0.90


def test_composite_score_preclinical_stage():
    from bve.intelligence.ma_backtest import _composite_score_from_yaml_features
    score = _composite_score_from_yaml_features(0.40, 0.35, 0.30, "preclinical")
    assert 0.30 <= score <= 0.50


def test_composite_score_unknown_stage_uses_default():
    from bve.intelligence.ma_backtest import (
        _composite_score_from_yaml_features,
        _STAGE_FACTOR_DEFAULT,
    )
    score_known = _composite_score_from_yaml_features(0.60, 0.60, 0.55, None)
    score_unk = _composite_score_from_yaml_features(0.60, 0.60, 0.55, "unknown_stage")
    assert score_known == score_unk


def test_composite_score_bounded():
    from bve.intelligence.ma_backtest import _composite_score_from_yaml_features
    score_high = _composite_score_from_yaml_features(1.0, 1.0, 1.0, "approved")
    score_low = _composite_score_from_yaml_features(0.0, 0.0, 0.0, "preclinical")
    assert 0.0 <= score_low <= 1.0
    assert 0.0 <= score_high <= 1.0


# ---------------------------------------------------------------------------
# Full pipeline: build → fit → save → load
# ---------------------------------------------------------------------------

def test_fit_calibration_from_cases_file(tmp_path):
    cases_path = _minimal_cases_yaml(tmp_path, n_pos=10, n_neg=20)
    from bve.intelligence.ma_backtest import (
        build_backtest_records_from_calibration_cases,
        fit_logistic_calibration,
    )
    records = build_backtest_records_from_calibration_cases(cases_path)
    params = fit_logistic_calibration(records)
    assert params.n_positive == 10
    assert params.n_negative == 20
    assert params.source == "fitted"
    assert isinstance(params.slope, float)
    assert isinstance(params.midpoint, float)


def test_fit_and_save_produces_json(tmp_path):
    cases_path = _minimal_cases_yaml(tmp_path, n_pos=10, n_neg=20)
    out_path = tmp_path / "params.json"
    from bve.intelligence.ma_backtest import (
        build_backtest_records_from_calibration_cases,
        fit_logistic_calibration,
        save_calibration_params,
        load_calibration_params,
    )
    records = build_backtest_records_from_calibration_cases(cases_path)
    params = fit_logistic_calibration(records)
    saved = save_calibration_params(params, out_path)
    assert saved.exists()
    data = json.loads(saved.read_text())
    assert "slope" in data
    assert "midpoint" in data
    assert data["source"] == "fitted"


def test_load_calibration_params_roundtrip(tmp_path):
    cases_path = _minimal_cases_yaml(tmp_path, n_pos=10, n_neg=20)
    out_path = tmp_path / "params.json"
    from bve.intelligence.ma_backtest import (
        build_backtest_records_from_calibration_cases,
        fit_logistic_calibration,
        save_calibration_params,
        load_calibration_params,
    )
    records = build_backtest_records_from_calibration_cases(cases_path)
    params = fit_logistic_calibration(records)
    save_calibration_params(params, out_path)
    slope, midpoint = load_calibration_params(out_path)
    assert slope == params.slope
    assert midpoint == params.midpoint


# ---------------------------------------------------------------------------
# CLI smoke tests
# ---------------------------------------------------------------------------

def test_cli_dry_run(tmp_path, capsys):
    """CLI --dry-run prints report and does not write the JSON file."""
    cases_path = _minimal_cases_yaml(tmp_path, n_pos=10, n_neg=20)
    out_path = tmp_path / "params.json"
    from bve.cli.ma_retroactive_calibrate import main
    with patch("sys.argv", [
        "bve-ma-calibrate",
        "--cases", str(cases_path),
        "--out", str(out_path),
        "--dry-run",
    ]):
        main()
    assert not out_path.exists()
    out = capsys.readouterr().out
    assert "dry-run" in out


def test_cli_writes_params_file(tmp_path, capsys):
    """CLI without --dry-run writes the JSON params file."""
    cases_path = _minimal_cases_yaml(tmp_path, n_pos=10, n_neg=20)
    out_path = tmp_path / "params.json"
    from bve.cli.ma_retroactive_calibrate import main
    with patch("sys.argv", [
        "bve-ma-calibrate",
        "--cases", str(cases_path),
        "--out", str(out_path),
    ]):
        main()
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert "slope" in data and "midpoint" in data


def test_cli_missing_cases_exits_with_error(tmp_path, capsys):
    from bve.cli.ma_retroactive_calibrate import main
    with patch("sys.argv", [
        "bve-ma-calibrate",
        "--cases", str(tmp_path / "nonexistent.yaml"),
    ]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 1


def test_real_calibration_params_file_exists():
    """The saved ma_calibration_params.json must exist after running bve-ma-calibrate."""
    params_path = (
        Path(__file__).resolve().parents[1]
        / "src" / "bve" / "config" / "ma_calibration_params.json"
    )
    assert params_path.exists(), (
        "ma_calibration_params.json not found. Run 'bve-ma-calibrate' to generate it."
    )
    data = json.loads(params_path.read_text())
    assert "slope" in data
    assert "midpoint" in data
    assert data.get("source") == "fitted"
    assert data.get("n_positive", 0) >= 10
    assert data.get("n_negative", 0) >= 10
