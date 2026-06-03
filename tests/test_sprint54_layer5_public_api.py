"""Sprint 54 — Layer 5 public API: new governance wrapper tests.

Covers three wrappers added to ma_layer5_calibration.py in Sprint 54:
  - generate_layer_validation_report(): delegates to ma_model_governance
  - build_prediction_audit_record(): delegates to ma_model_governance
  - write_prediction_audit_log(): delegates to ma_model_governance

All tests verify that the public API wrapper correctly delegates to the
underlying submodule and returns identical results, preserving the single
import-path contract for callers of ma_layer5_calibration.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date

import pytest

from bve.intelligence.ma_calibration_models import (
    CalibrationDiagnostics,
    CalibrationGovernanceMetadata,
    CalibrationMethod,
    CalibrationQualityLabel,
    CalibratedProbabilitySet,
    Layer5CalibrationOutput,
    LayerValidated,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _governance() -> CalibrationGovernanceMetadata:
    return CalibrationGovernanceMetadata(
        model_version="v1.0",
        calibration_dataset_version="2024-Q2",
        calibration_date=date(2024, 6, 1),
    )


def _diagnostics() -> CalibrationDiagnostics:
    return CalibrationDiagnostics(
        calibration_method=CalibrationMethod.BAYESIAN_BIN_CALIBRATION,
        sample_size=50,
        effective_sample_size=45.0,
        brier_score=0.19,
        auc=0.68,
    )


def _l5_output() -> Layer5CalibrationOutput:
    return Layer5CalibrationOutput(
        target_id="TARGET-X",
        acquirer_id="ACQUIRER-Y",
        prediction_date=date(2024, 7, 1),
        raw_scores={"bd_action_score": 0.68},
        layer4_route="active_pursuit",
        calibrated_probabilities=CalibratedProbabilitySet(p_full_acquisition_12m=0.28),
        calibration_quality=CalibrationQualityLabel.MEDIUM_CONFIDENCE,
        calibration_diagnostics=_diagnostics(),
        governance=_governance(),
    )


# ---------------------------------------------------------------------------
# generate_layer_validation_report wrapper
# ---------------------------------------------------------------------------

class TestGenerateLayerValidationReportWrapper:
    def test_delegates_to_submodule(self):
        from bve.intelligence.ma_layer5_calibration import generate_layer_validation_report
        from bve.intelligence.ma_model_governance import generate_layer_validation_report as _direct

        cases = {LayerValidated.LAYER_1: 15, LayerValidated.END_TO_END: 25}
        wrapper_result = generate_layer_validation_report(cases, known_answer_cases=25)
        direct_result = _direct(cases, known_answer_cases=25)

        assert wrapper_result["summary_status"] == direct_result["summary_status"]
        assert wrapper_result["known_answer_cases"] == direct_result["known_answer_cases"]

    def test_pass_status_when_all_layers_have_sufficient_data(self):
        from bve.intelligence.ma_layer5_calibration import generate_layer_validation_report

        result = generate_layer_validation_report(
            {LayerValidated.LAYER_1: 12, LayerValidated.LAYER_2: 14, LayerValidated.END_TO_END: 30},
            known_answer_cases=30,
        )
        assert result["summary_status"] == "pass"

    def test_partial_status_when_some_layers_insufficient(self):
        from bve.intelligence.ma_layer5_calibration import generate_layer_validation_report

        result = generate_layer_validation_report(
            {LayerValidated.LAYER_3: 3},   # below threshold
            known_answer_cases=3,
        )
        assert result["summary_status"] == "partial"

    def test_optional_metrics_passed_through(self):
        from bve.intelligence.ma_layer5_calibration import generate_layer_validation_report

        result = generate_layer_validation_report(
            {LayerValidated.END_TO_END: 20},
            top_k_precision=0.75,
            base_rate_coverage=0.90,
        )
        assert result["top_k_precision"] == pytest.approx(0.75)
        assert result["base_rate_coverage"] == pytest.approx(0.90)

    def test_empty_cases_returns_valid_structure(self):
        from bve.intelligence.ma_layer5_calibration import generate_layer_validation_report

        result = generate_layer_validation_report({})
        assert "validation_date" in result
        assert "layers" in result
        assert isinstance(result["layers"], list)


# ---------------------------------------------------------------------------
# build_prediction_audit_record wrapper
# ---------------------------------------------------------------------------

class TestBuildPredictionAuditRecordWrapper:
    def test_delegates_to_submodule(self):
        from bve.intelligence.ma_layer5_calibration import build_prediction_audit_record
        from bve.intelligence.ma_model_governance import build_audit_record as _direct

        output = _l5_output()
        wrapper_result = build_prediction_audit_record(output, run_id="r99")
        direct_result = _direct(output, run_id="r99")

        assert wrapper_result["run_id"] == direct_result["run_id"]
        assert wrapper_result["target_id"] == direct_result["target_id"]

    def test_returns_dict(self):
        from bve.intelligence.ma_layer5_calibration import build_prediction_audit_record

        record = build_prediction_audit_record(_l5_output())
        assert isinstance(record, dict)

    def test_audit_version_present(self):
        from bve.intelligence.ma_layer5_calibration import build_prediction_audit_record

        record = build_prediction_audit_record(_l5_output())
        assert record["audit_version"] == "1.0"

    def test_run_id_user_id_propagated(self):
        from bve.intelligence.ma_layer5_calibration import build_prediction_audit_record

        record = build_prediction_audit_record(
            _l5_output(), run_id="run-abc", user_id="bd-analyst"
        )
        assert record["run_id"] == "run-abc"
        assert record["user_id"] == "bd-analyst"

    def test_is_json_serialisable(self):
        from bve.intelligence.ma_layer5_calibration import build_prediction_audit_record

        record = build_prediction_audit_record(_l5_output())
        serialised = json.dumps(record, default=str)
        assert json.loads(serialised)["target_id"] == "TARGET-X"


# ---------------------------------------------------------------------------
# write_prediction_audit_log wrapper
# ---------------------------------------------------------------------------

class TestWritePredictionAuditLogWrapper:
    def _make_record(self, run_id: str = "r1") -> dict:
        from bve.intelligence.ma_layer5_calibration import build_prediction_audit_record
        return build_prediction_audit_record(_l5_output(), run_id=run_id)

    def test_creates_jsonl_file(self):
        from bve.intelligence.ma_layer5_calibration import write_prediction_audit_log

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "audit.jsonl")
            write_prediction_audit_log([self._make_record()], path)
            assert os.path.exists(path)

    def test_each_line_is_valid_json(self):
        from bve.intelligence.ma_layer5_calibration import write_prediction_audit_log

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "audit.jsonl")
            write_prediction_audit_log(
                [self._make_record("r1"), self._make_record("r2")], path
            )
            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 2
            for line in lines:
                loaded = json.loads(line)
                assert "run_id" in loaded

    def test_appends_on_second_call(self):
        from bve.intelligence.ma_layer5_calibration import write_prediction_audit_log

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "audit.jsonl")
            write_prediction_audit_log([self._make_record("r1")], path)
            write_prediction_audit_log([self._make_record("r2")], path)
            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 2
            run_ids = [json.loads(l)["run_id"] for l in lines]
            assert "r1" in run_ids and "r2" in run_ids

    def test_creates_parent_directories(self):
        from bve.intelligence.ma_layer5_calibration import write_prediction_audit_log

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "nested", "deep", "audit.jsonl")
            write_prediction_audit_log([self._make_record()], path)
            assert os.path.exists(path)

    def test_empty_records_creates_empty_file(self):
        from bve.intelligence.ma_layer5_calibration import write_prediction_audit_log

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "empty.jsonl")
            write_prediction_audit_log([], path)
            assert os.path.exists(path)
            with open(path) as f:
                assert f.read() == ""
