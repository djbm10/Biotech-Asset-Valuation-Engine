"""
Block 37B — M&A Calibration Dataset Framework
TDD tests written BEFORE implementation.

Tests for:
  A: MACalibrationCase schema (all required fields + types)
  B: No-lookahead validator (source_refs postdate observation_date → flag)
  C: MACalibrationDataset container (load, iterate, summary)
  D: Fit gating (fit blocked unless ≥50 positives, ≥100 negatives, all lookahead pass)
  E: YAML load / save round-trip
"""
from __future__ import annotations

import datetime
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_case(**overrides):
    """Return a minimal valid MACalibrationCase dict (all required fields)."""
    base = {
        "ticker": "EXMP",
        "company_name": "Example Bio",
        "observation_date": datetime.date(2022, 1, 1),
        "target_stage": "phase_2",
        "therapeutic_area": "oncology_solid",
        "modality": "small_molecule",
        "cash_runway_months_as_of": 18.0,
        "seller_willingness_as_of": 0.6,
        "catalyst_days_as_of": 120,
        "asset_quality_score_as_of": 0.55,
        "acquirer_fit_score_as_of": 0.50,
        "outcome_12m": True,
        "outcome_type": "acquisition",
        "outcome_date": datetime.date(2022, 9, 15),
        "source_refs": ["https://sec.gov/Archives/example1", "https://sec.gov/Archives/example2"],
        "feature_as_of_dates": {
            "cash_runway_months": "2022-01-01",
            "seller_willingness": "2022-01-01",
        },
        "lookahead_pass": True,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Block 37B-A: MACalibrationCase schema
# ---------------------------------------------------------------------------

class TestMACalibrationCaseSchema:

    def test_importable(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        assert MACalibrationCase is not None

    def test_valid_case_constructs(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert case.ticker == "EXMP"

    def test_ticker_field(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert hasattr(case, "ticker")

    def test_company_name_field(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert hasattr(case, "company_name")

    def test_observation_date_field(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert isinstance(case.observation_date, datetime.date)

    def test_target_stage_field(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert case.target_stage == "phase_2"

    def test_therapeutic_area_field(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert hasattr(case, "therapeutic_area")

    def test_modality_field(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert hasattr(case, "modality")

    def test_cash_runway_field(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert case.cash_runway_months_as_of == pytest.approx(18.0)

    def test_seller_willingness_field(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert 0.0 <= case.seller_willingness_as_of <= 1.0

    def test_catalyst_days_field(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert case.catalyst_days_as_of == 120

    def test_asset_quality_score_field(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert 0.0 <= case.asset_quality_score_as_of <= 1.0

    def test_acquirer_fit_score_field(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert 0.0 <= case.acquirer_fit_score_as_of <= 1.0

    def test_outcome_12m_bool(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert isinstance(case.outcome_12m, bool)

    def test_outcome_type_field(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert case.outcome_type in ("acquisition", "license", "partnership", "none")

    def test_outcome_date_optional(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case(outcome_date=None))
        assert case.outcome_date is None

    def test_source_refs_is_list(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert isinstance(case.source_refs, list)
        assert len(case.source_refs) >= 1

    def test_feature_as_of_dates_is_dict(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert isinstance(case.feature_as_of_dates, dict)

    def test_lookahead_pass_bool(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case())
        assert isinstance(case.lookahead_pass, bool)

    def test_negative_outcome_type_none(self):
        """outcome_12m=False cases should have outcome_type='none'."""
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase
        case = MACalibrationCase(**_make_valid_case(
            outcome_12m=False,
            outcome_type="none",
            outcome_date=None,
        ))
        assert case.outcome_12m is False
        assert case.outcome_type == "none"


# ---------------------------------------------------------------------------
# Block 37B-B: No-lookahead validator
# ---------------------------------------------------------------------------

class TestNoLookaheadValidator:

    def test_validator_importable(self):
        from bve.intelligence.ma_calibration_dataset import validate_no_lookahead
        assert validate_no_lookahead is not None

    def test_valid_case_passes(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase, validate_no_lookahead
        case = MACalibrationCase(**_make_valid_case(
            observation_date=datetime.date(2022, 1, 1),
            source_refs=["https://sec.gov/2021-q4-filing"],
            feature_as_of_dates={"cash_runway_months": "2021-12-31"},
        ))
        result = validate_no_lookahead(case)
        assert result.passed is True

    def test_postdated_feature_fails(self):
        """feature_as_of_dates date AFTER observation_date should flag as lookahead."""
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase, validate_no_lookahead
        case = MACalibrationCase(**_make_valid_case(
            observation_date=datetime.date(2022, 1, 1),
            feature_as_of_dates={"cash_runway_months": "2022-06-01"},  # 5 months AFTER
            lookahead_pass=False,
        ))
        result = validate_no_lookahead(case)
        assert result.passed is False

    def test_postdated_feature_reports_field(self):
        """Validator reports which fields have lookahead."""
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase, validate_no_lookahead
        case = MACalibrationCase(**_make_valid_case(
            observation_date=datetime.date(2022, 1, 1),
            feature_as_of_dates={"seller_willingness": "2022-08-01"},
            lookahead_pass=False,
        ))
        result = validate_no_lookahead(case)
        assert not result.passed
        assert "seller_willingness" in result.violations

    def test_result_has_violations_list(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase, validate_no_lookahead
        case = MACalibrationCase(**_make_valid_case())
        result = validate_no_lookahead(case)
        assert hasattr(result, "violations")
        assert isinstance(result.violations, list)

    def test_all_as_of_before_observation_passes(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase, validate_no_lookahead
        case = MACalibrationCase(**_make_valid_case(
            observation_date=datetime.date(2022, 6, 1),
            feature_as_of_dates={
                "cash_runway_months": "2022-05-31",
                "seller_willingness": "2022-04-01",
                "catalyst_days": "2022-06-01",
            },
        ))
        result = validate_no_lookahead(case)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Block 37B-C: MACalibrationDataset container
# ---------------------------------------------------------------------------

class TestMACalibrationDataset:

    def test_importable(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationDataset
        assert MACalibrationDataset is not None

    def test_empty_dataset(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationDataset
        ds = MACalibrationDataset(cases=[])
        assert len(ds.cases) == 0

    def test_add_case(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase, MACalibrationDataset
        case = MACalibrationCase(**_make_valid_case())
        ds = MACalibrationDataset(cases=[case])
        assert len(ds.cases) == 1

    def test_positive_count(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase, MACalibrationDataset
        pos = MACalibrationCase(**_make_valid_case(outcome_12m=True))
        neg = MACalibrationCase(**_make_valid_case(
            ticker="NEG1", outcome_12m=False, outcome_type="none", outcome_date=None
        ))
        ds = MACalibrationDataset(cases=[pos, neg])
        assert ds.positive_count == 1

    def test_negative_count(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase, MACalibrationDataset
        neg1 = MACalibrationCase(**_make_valid_case(
            ticker="NEG1", outcome_12m=False, outcome_type="none", outcome_date=None
        ))
        neg2 = MACalibrationCase(**_make_valid_case(
            ticker="NEG2", outcome_12m=False, outcome_type="none", outcome_date=None
        ))
        pos = MACalibrationCase(**_make_valid_case())
        ds = MACalibrationDataset(cases=[pos, neg1, neg2])
        assert ds.negative_count == 2

    def test_lookahead_passed_count(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase, MACalibrationDataset
        ok = MACalibrationCase(**_make_valid_case(lookahead_pass=True))
        bad = MACalibrationCase(**_make_valid_case(
            ticker="BAD1", lookahead_pass=False,
            feature_as_of_dates={"cash_runway_months": "2023-01-01"},
        ))
        ds = MACalibrationDataset(cases=[ok, bad])
        assert ds.lookahead_passed_count == 1

    def test_summary_has_counts(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase, MACalibrationDataset
        case = MACalibrationCase(**_make_valid_case())
        ds = MACalibrationDataset(cases=[case])
        summary = ds.summary()
        assert "total" in summary
        assert "positives" in summary
        assert "negatives" in summary

    def test_summary_total_matches_len(self):
        from bve.intelligence.ma_calibration_dataset import MACalibrationCase, MACalibrationDataset
        cases = [
            MACalibrationCase(**_make_valid_case(ticker=f"T{i}"))
            for i in range(3)
        ]
        ds = MACalibrationDataset(cases=cases)
        summary = ds.summary()
        assert summary["total"] == 3


# ---------------------------------------------------------------------------
# Block 37B-D: Fit gating
# ---------------------------------------------------------------------------

class TestFitGating:

    def test_fit_gating_importable(self):
        from bve.intelligence.ma_calibration_dataset import check_fit_readiness
        assert check_fit_readiness is not None

    def test_not_ready_too_few_positives(self):
        from bve.intelligence.ma_calibration_dataset import (
            MACalibrationCase, MACalibrationDataset, check_fit_readiness
        )
        # Only 5 positives, 100 negatives
        positives = [
            MACalibrationCase(**_make_valid_case(ticker=f"P{i}"))
            for i in range(5)
        ]
        negatives = [
            MACalibrationCase(**_make_valid_case(
                ticker=f"N{i}", outcome_12m=False, outcome_type="none", outcome_date=None
            ))
            for i in range(100)
        ]
        ds = MACalibrationDataset(cases=positives + negatives)
        result = check_fit_readiness(ds)
        assert result.ready is False
        assert "positives" in result.reason.lower()

    def test_not_ready_too_few_negatives(self):
        from bve.intelligence.ma_calibration_dataset import (
            MACalibrationCase, MACalibrationDataset, check_fit_readiness
        )
        positives = [
            MACalibrationCase(**_make_valid_case(ticker=f"P{i}"))
            for i in range(50)
        ]
        negatives = [
            MACalibrationCase(**_make_valid_case(
                ticker=f"N{i}", outcome_12m=False, outcome_type="none", outcome_date=None
            ))
            for i in range(30)  # too few
        ]
        ds = MACalibrationDataset(cases=positives + negatives)
        result = check_fit_readiness(ds)
        assert result.ready is False
        assert "negatives" in result.reason.lower()

    def test_not_ready_lookahead_violations(self):
        from bve.intelligence.ma_calibration_dataset import (
            MACalibrationCase, MACalibrationDataset, check_fit_readiness
        )
        # 50 positives + 100 negatives, but some fail lookahead
        positives = [
            MACalibrationCase(**_make_valid_case(ticker=f"P{i}"))
            for i in range(50)
        ]
        negatives = [
            MACalibrationCase(**_make_valid_case(
                ticker=f"N{i}", outcome_12m=False, outcome_type="none", outcome_date=None
            ))
            for i in range(99)
        ]
        bad = MACalibrationCase(**_make_valid_case(
            ticker="BAD",
            outcome_12m=False, outcome_type="none", outcome_date=None,
            lookahead_pass=False,
            feature_as_of_dates={"seller_willingness": "2025-01-01"},
        ))
        ds = MACalibrationDataset(cases=positives + negatives + [bad])
        result = check_fit_readiness(ds)
        assert result.ready is False
        assert "lookahead" in result.reason.lower()

    def test_ready_with_sufficient_data(self):
        from bve.intelligence.ma_calibration_dataset import (
            MACalibrationCase, MACalibrationDataset, check_fit_readiness
        )
        positives = [
            MACalibrationCase(**_make_valid_case(ticker=f"P{i}"))
            for i in range(50)
        ]
        negatives = [
            MACalibrationCase(**_make_valid_case(
                ticker=f"N{i}", outcome_12m=False, outcome_type="none", outcome_date=None
            ))
            for i in range(100)
        ]
        ds = MACalibrationDataset(cases=positives + negatives)
        result = check_fit_readiness(ds)
        assert result.ready is True

    def test_fit_readiness_result_has_reason(self):
        from bve.intelligence.ma_calibration_dataset import (
            MACalibrationDataset, check_fit_readiness
        )
        ds = MACalibrationDataset(cases=[])
        result = check_fit_readiness(ds)
        assert hasattr(result, "reason")
        assert isinstance(result.reason, str)


# ---------------------------------------------------------------------------
# Block 37B-E: YAML round-trip
# ---------------------------------------------------------------------------

class TestYAMLRoundTrip:

    def test_load_from_yaml_importable(self):
        from bve.intelligence.ma_calibration_dataset import load_dataset_from_yaml
        assert load_dataset_from_yaml is not None

    def test_save_to_yaml_importable(self):
        from bve.intelligence.ma_calibration_dataset import save_dataset_to_yaml
        assert save_dataset_to_yaml is not None

    def test_round_trip_preserves_case_count(self, tmp_path):
        from bve.intelligence.ma_calibration_dataset import (
            MACalibrationCase, MACalibrationDataset,
            save_dataset_to_yaml, load_dataset_from_yaml,
        )
        cases = [MACalibrationCase(**_make_valid_case(ticker=f"T{i}")) for i in range(3)]
        ds = MACalibrationDataset(cases=cases)
        path = tmp_path / "test_dataset.yaml"
        save_dataset_to_yaml(ds, path)
        loaded = load_dataset_from_yaml(path)
        assert len(loaded.cases) == 3

    def test_round_trip_preserves_ticker(self, tmp_path):
        from bve.intelligence.ma_calibration_dataset import (
            MACalibrationCase, MACalibrationDataset,
            save_dataset_to_yaml, load_dataset_from_yaml,
        )
        case = MACalibrationCase(**_make_valid_case(ticker="ROUNDTRIP"))
        ds = MACalibrationDataset(cases=[case])
        path = tmp_path / "test_rt.yaml"
        save_dataset_to_yaml(ds, path)
        loaded = load_dataset_from_yaml(path)
        assert loaded.cases[0].ticker == "ROUNDTRIP"

    def test_round_trip_preserves_outcome(self, tmp_path):
        from bve.intelligence.ma_calibration_dataset import (
            MACalibrationCase, MACalibrationDataset,
            save_dataset_to_yaml, load_dataset_from_yaml,
        )
        case = MACalibrationCase(**_make_valid_case(outcome_12m=False, outcome_type="none", outcome_date=None))
        ds = MACalibrationDataset(cases=[case])
        path = tmp_path / "test_outcome.yaml"
        save_dataset_to_yaml(ds, path)
        loaded = load_dataset_from_yaml(path)
        assert loaded.cases[0].outcome_12m is False

    def test_empty_dataset_round_trip(self, tmp_path):
        from bve.intelligence.ma_calibration_dataset import (
            MACalibrationDataset,
            save_dataset_to_yaml, load_dataset_from_yaml,
        )
        ds = MACalibrationDataset(cases=[])
        path = tmp_path / "empty.yaml"
        save_dataset_to_yaml(ds, path)
        loaded = load_dataset_from_yaml(path)
        assert len(loaded.cases) == 0
