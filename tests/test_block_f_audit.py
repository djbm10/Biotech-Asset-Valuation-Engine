"""Tests for Block F — no-lookahead audit of M&A calibration cases."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from bve.intelligence.ma_calibration_audit import (
    AuditResult,
    run_no_lookahead_audit,
    print_audit_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(tmp_path: Path, cases: list[dict]) -> Path:
    """Write a minimal YAML file with a ``cases:`` key and return its path."""
    p = tmp_path / "cases.yaml"
    p.write_text(yaml.dump({"cases": cases}))
    return p


def _minimal_negative(ticker: str = "NEG1", obs: str = "2020-01-01") -> dict:
    return {
        "ticker": ticker,
        "company_name": "Test Co",
        "observation_date": obs,
        "target_stage": "phase_2",
        "therapeutic_area": "oncology",
        "modality": "small_molecule",
        "cash_runway_months_as_of": 12.0,
        "seller_willingness_as_of": 0.4,
        "catalyst_days_as_of": None,
        "asset_quality_score_as_of": 0.5,
        "acquirer_fit_score_as_of": 0.5,
        "outcome_12m": False,
        "outcome_type": None,
        "outcome_date": None,
        "source_refs": ["test ref"],
        "feature_as_of_dates": {
            "cash_runway_months_as_of": obs,
            "seller_willingness_as_of": obs,
            "asset_quality_score_as_of": obs,
            "acquirer_fit_score_as_of": obs,
        },
        "lookahead_pass": True,
    }


def _minimal_positive(
    ticker: str = "POS1",
    obs: str = "2020-01-01",
    outcome_date: str = "2020-06-01",
) -> dict:
    case = _minimal_negative(ticker, obs)
    case.update(
        {
            "outcome_12m": True,
            "outcome_type": "acquisition",
            "outcome_date": outcome_date,
        }
    )
    return case


# ---------------------------------------------------------------------------
# test_clean_cases_no_violations
# ---------------------------------------------------------------------------

def test_clean_cases_no_violations(tmp_path: Path) -> None:
    cases = [
        _minimal_negative("NEG1"),
        _minimal_negative("NEG2"),
        _minimal_positive("POS1", obs="2020-01-01", outcome_date="2020-06-01"),
    ]
    yaml_path = _write_yaml(tmp_path, cases)
    result = run_no_lookahead_audit(yaml_path)

    assert isinstance(result, AuditResult)
    assert result.has_violations is False
    assert result.n_violations == 0
    assert result.n_total == 3
    assert result.n_positive == 1
    assert result.n_negative == 2
    assert result.n_clean == 3
    assert "PASS" in result.summary


# ---------------------------------------------------------------------------
# test_detects_lookahead_flag_false
# ---------------------------------------------------------------------------

def test_detects_lookahead_flag_false(tmp_path: Path) -> None:
    case = _minimal_negative("FLAGGED")
    case["lookahead_pass"] = False
    yaml_path = _write_yaml(tmp_path, [case])

    result = run_no_lookahead_audit(yaml_path)

    assert result.has_violations is True
    assert result.n_violations >= 1
    types = {v.violation_type for v in result.violations}
    assert "LOOKAHEAD_FLAG_FALSE" in types
    flagged = [v for v in result.violations if v.violation_type == "LOOKAHEAD_FLAG_FALSE"]
    assert flagged[0].ticker == "FLAGGED"


# ---------------------------------------------------------------------------
# test_detects_insufficient_lead_time
# ---------------------------------------------------------------------------

def test_detects_insufficient_lead_time(tmp_path: Path) -> None:
    # outcome_date only 10 days after observation — below the 30-day minimum
    case = _minimal_positive("FAST", obs="2020-03-01", outcome_date="2020-03-11")
    yaml_path = _write_yaml(tmp_path, [case])

    result = run_no_lookahead_audit(yaml_path)

    assert result.has_violations is True
    types = {v.violation_type for v in result.violations}
    assert "INSUFFICIENT_LEAD_TIME" in types
    v = next(v for v in result.violations if v.violation_type == "INSUFFICIENT_LEAD_TIME")
    assert v.ticker == "FAST"
    assert "10 days" in v.detail


def test_exactly_30_days_lead_time_is_clean(tmp_path: Path) -> None:
    """Boundary: outcome exactly 30 days out is acceptable."""
    case = _minimal_positive("BORDER", obs="2020-03-01", outcome_date="2020-03-31")
    yaml_path = _write_yaml(tmp_path, [case])

    result = run_no_lookahead_audit(yaml_path)
    insufficient = [v for v in result.violations if v.violation_type == "INSUFFICIENT_LEAD_TIME"]
    assert insufficient == []


# ---------------------------------------------------------------------------
# test_detects_feature_date_after_observation
# ---------------------------------------------------------------------------

def test_detects_feature_date_after_observation(tmp_path: Path) -> None:
    case = _minimal_negative("FUTURE_FEAT")
    # Set one feature as-of date to a day after the observation date
    case["feature_as_of_dates"]["asset_quality_score_as_of"] = "2020-01-15"
    yaml_path = _write_yaml(tmp_path, [case])

    result = run_no_lookahead_audit(yaml_path)

    assert result.has_violations is True
    types = {v.violation_type for v in result.violations}
    assert "FEATURE_DATE_AFTER_OBSERVATION" in types
    v = next(v for v in result.violations if v.violation_type == "FEATURE_DATE_AFTER_OBSERVATION")
    assert v.ticker == "FUTURE_FEAT"
    assert "asset_quality_score_as_of" in v.detail


# ---------------------------------------------------------------------------
# test_detects_missing_outcome_date
# ---------------------------------------------------------------------------

def test_detects_missing_outcome_date(tmp_path: Path) -> None:
    case = _minimal_positive("NODATE")
    case["outcome_date"] = None
    yaml_path = _write_yaml(tmp_path, [case])

    result = run_no_lookahead_audit(yaml_path)

    assert result.has_violations is True
    types = {v.violation_type for v in result.violations}
    assert "MISSING_OUTCOME_DATE" in types
    v = next(v for v in result.violations if v.violation_type == "MISSING_OUTCOME_DATE")
    assert v.ticker == "NODATE"


def test_missing_outcome_date_does_not_fire_for_negatives(tmp_path: Path) -> None:
    """Negative cases are allowed to have null outcome_date."""
    case = _minimal_negative("NEG_NULL")
    case["outcome_date"] = None
    yaml_path = _write_yaml(tmp_path, [case])

    result = run_no_lookahead_audit(yaml_path)
    missing = [v for v in result.violations if v.violation_type == "MISSING_OUTCOME_DATE"]
    assert missing == []


# ---------------------------------------------------------------------------
# test_real_cases_file_passes_audit
# ---------------------------------------------------------------------------

def test_real_cases_file_passes_audit() -> None:
    """Run the audit against the actual calibration YAML — must be violation-free."""
    repo_root = Path(__file__).resolve().parents[1]
    yaml_path = repo_root / "research" / "mna" / "historical_calibration_cases.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Calibration YAML not found at {yaml_path}")

    result = run_no_lookahead_audit(yaml_path)

    if result.has_violations:
        detail_lines = "\n".join(
            f"  [{v.violation_type}] {v.ticker} @ {v.observation_date}: {v.detail}"
            for v in result.violations
        )
        pytest.fail(
            f"Real calibration YAML has {result.n_violations} violation(s):\n{detail_lines}"
        )

    assert result.has_violations is False
    assert result.n_total >= 300
    assert result.n_positive >= 100
    assert result.n_negative >= 200


# ---------------------------------------------------------------------------
# test_print_audit_report — smoke test (no assertions on formatting, just no crash)
# ---------------------------------------------------------------------------

def test_print_audit_report_clean(tmp_path: Path, capsys) -> None:
    cases = [_minimal_negative("N1"), _minimal_positive("P1")]
    yaml_path = _write_yaml(tmp_path, cases)
    result = run_no_lookahead_audit(yaml_path)
    print_audit_report(result)
    captured = capsys.readouterr()
    assert "PASS" in captured.out
    assert "N_VIOLATIONS" not in captured.out


def test_print_audit_report_violations(tmp_path: Path, capsys) -> None:
    case = _minimal_negative("BAD")
    case["lookahead_pass"] = False
    yaml_path = _write_yaml(tmp_path, [case])
    result = run_no_lookahead_audit(yaml_path)
    print_audit_report(result)
    captured = capsys.readouterr()
    assert "FAIL" in captured.out
    assert "LOOKAHEAD_FLAG_FALSE" in captured.out


# ---------------------------------------------------------------------------
# CLI exit code tests
# ---------------------------------------------------------------------------

def test_cli_exits_zero_on_clean_file(tmp_path: Path) -> None:
    cases = [_minimal_negative("C1"), _minimal_positive("C2")]
    yaml_path = _write_yaml(tmp_path, cases)

    result = subprocess.run(
        [sys.executable, "-m", "bve.cli.ma_calibration_audit_cli", "--cases", str(yaml_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Expected exit code 0 for clean file.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "PASS" in result.stdout


def test_cli_exits_one_on_violations(tmp_path: Path) -> None:
    case = _minimal_negative("VIOL")
    case["lookahead_pass"] = False
    yaml_path = _write_yaml(tmp_path, [case])

    result = subprocess.run(
        [sys.executable, "-m", "bve.cli.ma_calibration_audit_cli", "--cases", str(yaml_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, (
        f"Expected exit code 1 for violations.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "FAIL" in result.stdout


def test_cli_exits_one_on_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.yaml"
    result = subprocess.run(
        [sys.executable, "-m", "bve.cli.ma_calibration_audit_cli", "--cases", str(missing)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
