"""Sprint 53 — Layer 5 5H: Model Governance tests.

Covers:
  - generate_layer_validation_report: layer-by-layer validation status
  - generate_model_card: Markdown output, sections, governance metadata
  - generate_governance_checklist: pass/warn/fail checks + overall status
  - build_audit_record: structured audit dict for a Layer5CalibrationOutput
  - write_audit_log: JSONL append to path
  - generate_governance_report: full convenience wrapper
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date

import pytest

from bve.intelligence.ma_calibration_models import (
    CalibrationArtifact,
    CalibrationDiagnostics,
    CalibrationGovernanceMetadata,
    CalibrationMethod,
    CalibrationQualityLabel,
    CalibratedProbabilitySet,
    DriftReport,
    DriftType,
    Layer5CalibrationConfig,
    Layer5CalibrationOutput,
    LayerValidated,
    OperatingMode,
    SegmentDiagnostics,
    ThresholdRecommendation,
)
from bve.intelligence.ma_model_governance import (
    build_audit_record,
    generate_governance_checklist,
    generate_governance_report,
    generate_layer_validation_report,
    generate_model_card,
    write_audit_log,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _governance() -> CalibrationGovernanceMetadata:
    return CalibrationGovernanceMetadata(
        model_version="v2.0",
        calibration_dataset_version="2024-Q2",
        calibration_date=date(2024, 6, 1),
        feature_schema_version="v1",
        calibration_artifact_id="artifact-001",
        training_window_start=date(2020, 1, 1),
        training_window_end=date(2024, 3, 31),
        excluded_case_count=3,
        known_limitations=["Sparse outcome data in rare disease segment."],
    )


def _diagnostics(sample_size: int = 80, brier: float = 0.18, auc: float = 0.70) -> CalibrationDiagnostics:
    return CalibrationDiagnostics(
        calibration_method=CalibrationMethod.BAYESIAN_BIN_CALIBRATION,
        sample_size=sample_size,
        effective_sample_size=float(sample_size) * 0.9,
        base_rate=0.22,
        brier_score=brier,
        auc=auc,
    )


def _drift_report(status: str = "none") -> DriftReport:
    return DriftReport(
        drift_status=status,
        requires_recalibration=status in {"moderate", "severe"},
    )


def _threshold_rec(auto_apply: bool = False) -> ThresholdRecommendation:
    return ThresholdRecommendation(
        threshold_name="bd_action_score",
        current_threshold=0.60,
        recommended_threshold=0.55,
        operating_mode=OperatingMode.BALANCED,
        tradeoff_explanation="Lower threshold increases recall.",
        should_auto_apply=auto_apply,
        requires_human_review=True,
    )


def _artifact() -> CalibrationArtifact:
    return CalibrationArtifact(
        artifact_id="artifact-001",
        governance=_governance(),
        global_sample_size=80,
        global_base_rate=0.22,
        global_calibration_method=CalibrationMethod.BAYESIAN_BIN_CALIBRATION,
        training_diagnostics=_diagnostics(),
    )


def _layer5_output() -> Layer5CalibrationOutput:
    return Layer5CalibrationOutput(
        target_id="ACME",
        acquirer_id="bigpharma",
        prediction_date=date(2024, 7, 1),
        raw_scores={"bd_action_score": 0.72, "layer1_score": 0.65},
        layer4_route="pursue_acquisition",
        calibrated_probabilities=CalibratedProbabilitySet(
            p_full_acquisition_12m=0.35,
            p_any_strategic_transaction_12m=0.52,
        ),
        calibration_quality=CalibrationQualityLabel.MEDIUM_CONFIDENCE,
        calibration_diagnostics=_diagnostics(),
        governance=_governance(),
        do_not_use_as_probability=False,
        warnings=["Segment N too small for high confidence."],
        drift_warnings=[],
        missing_data=["recent_deal_activity"],
    )


# ---------------------------------------------------------------------------
# generate_layer_validation_report
# ---------------------------------------------------------------------------

class TestGenerateLayerValidationReport:
    def test_all_layers_validated_returns_pass(self):
        cases_validated = {
            LayerValidated.LAYER_1: 15,
            LayerValidated.LAYER_2: 12,
            LayerValidated.END_TO_END: 30,
        }
        result = generate_layer_validation_report(cases_validated, known_answer_cases=30)
        assert result["summary_status"] == "pass"

    def test_insufficient_cases_returns_partial(self):
        cases_validated = {
            LayerValidated.LAYER_1: 5,  # below threshold of 10
            LayerValidated.END_TO_END: 20,
        }
        result = generate_layer_validation_report(cases_validated, known_answer_cases=5)
        assert result["summary_status"] == "partial"

    def test_layer_status_validated_when_n_ge_10(self):
        cases_validated = {LayerValidated.LAYER_1: 10}
        result = generate_layer_validation_report(cases_validated)
        assert result["layers"][0]["status"] == "validated"

    def test_layer_status_insufficient_when_n_lt_10(self):
        cases_validated = {LayerValidated.LAYER_3: 4}
        result = generate_layer_validation_report(cases_validated)
        assert result["layers"][0]["status"] == "insufficient_data"

    def test_low_known_answer_count_adds_limitation(self):
        result = generate_layer_validation_report({}, known_answer_cases=5)
        assert any("5" in lim for lim in result["limitations"])

    def test_optional_metrics_included(self):
        result = generate_layer_validation_report(
            {LayerValidated.END_TO_END: 20},
            top_k_precision=0.73,
            base_rate_coverage=0.88,
        )
        assert result["top_k_precision"] == pytest.approx(0.73)
        assert result["base_rate_coverage"] == pytest.approx(0.88)

    def test_validation_date_is_iso_string(self):
        result = generate_layer_validation_report({}, validation_date=date(2024, 6, 15))
        assert result["validation_date"] == "2024-06-15"


# ---------------------------------------------------------------------------
# generate_model_card
# ---------------------------------------------------------------------------

class TestGenerateModelCard:
    def test_returns_string(self):
        card = generate_model_card(_governance())
        assert isinstance(card, str)
        assert len(card) > 100

    def test_includes_model_version(self):
        card = generate_model_card(_governance())
        assert "v2.0" in card

    def test_includes_calibration_date(self):
        card = generate_model_card(_governance())
        assert "2024-06-01" in card

    def test_includes_architecture_table(self):
        card = generate_model_card(_governance())
        assert "Layer" in card and "L1" in card

    def test_includes_intended_use_section(self):
        card = generate_model_card(_governance())
        assert "Intended Use" in card

    def test_includes_diagnostics_when_provided(self):
        card = generate_model_card(_governance(), diagnostics=_diagnostics())
        assert "Brier score" in card
        assert "AUC-ROC" in card

    def test_includes_drift_status_when_provided(self):
        card = generate_model_card(_governance(), drift_report=_drift_report("mild"))
        assert "Drift Status" in card
        assert "mild" in card

    def test_includes_known_limitations(self):
        card = generate_model_card(_governance())
        assert "Known Limitations" in card
        assert "Sparse outcome data" in card

    def test_includes_governance_section(self):
        card = generate_model_card(_governance())
        assert "Governance" in card
        assert "human review" in card.lower() or "Human review" in card

    def test_segment_detail_excluded_by_default(self):
        seg = SegmentDiagnostics(
            segment_key="oncology",
            sample_size=20,
            effective_sample_size=18.0,
            reliability_label=CalibrationQualityLabel.MEDIUM_CONFIDENCE,
        )
        card = generate_model_card(_governance(), segment_diagnostics=[seg])
        assert "Per-Segment Detail" not in card

    def test_segment_detail_included_when_flag_set(self):
        seg = SegmentDiagnostics(
            segment_key="oncology",
            sample_size=20,
            effective_sample_size=18.0,
            reliability_label=CalibrationQualityLabel.HIGH_CONFIDENCE,
        )
        card = generate_model_card(
            _governance(), segment_diagnostics=[seg], include_segment_detail=True
        )
        assert "Per-Segment Detail" in card
        assert "oncology" in card


# ---------------------------------------------------------------------------
# generate_governance_checklist
# ---------------------------------------------------------------------------

class TestGenerateGovernanceChecklist:
    def test_pass_with_good_diagnostics_no_drift(self):
        result = generate_governance_checklist(
            _governance(),
            diagnostics=_diagnostics(sample_size=120, brier=0.17, auc=0.72),
            drift_report=_drift_report("none"),
        )
        assert result["overall"] in {"pass", "warn"}
        assert result["deployment_allowed"] is True

    def test_fail_with_small_sample(self):
        result = generate_governance_checklist(
            _governance(),
            diagnostics=_diagnostics(sample_size=10, brier=0.17, auc=0.72),
        )
        assert result["overall"] == "fail"
        assert result["deployment_allowed"] is False

    def test_fail_with_bad_brier(self):
        result = generate_governance_checklist(
            _governance(),
            diagnostics=_diagnostics(brier=0.30),
        )
        checks = {c["item"]: c for c in result["checks"]}
        assert checks["Brier score"]["status"] == "fail"

    def test_warn_with_mild_drift(self):
        result = generate_governance_checklist(
            _governance(),
            drift_report=_drift_report("mild"),
        )
        checks = {c["item"]: c for c in result["checks"]}
        assert checks["Drift status"]["status"] == "warn"

    def test_fail_with_severe_drift(self):
        result = generate_governance_checklist(
            _governance(),
            drift_report=_drift_report("severe"),
        )
        checks = {c["item"]: c for c in result["checks"]}
        assert checks["Drift status"]["status"] == "fail"
        assert result["overall"] == "fail"

    def test_auto_apply_threshold_fails_checklist(self):
        result = generate_governance_checklist(
            _governance(),
            threshold_recs=[_threshold_rec(auto_apply=True)],
        )
        checks = {c["item"]: c for c in result["checks"]}
        assert checks["Threshold auto-apply"]["status"] == "fail"

    def test_no_auto_apply_threshold_passes_checklist(self):
        result = generate_governance_checklist(
            _governance(),
            threshold_recs=[_threshold_rec(auto_apply=False)],
        )
        checks = {c["item"]: c for c in result["checks"]}
        assert checks["Threshold auto-apply"]["status"] == "pass"

    def test_sign_off_always_required(self):
        result = generate_governance_checklist(_governance())
        assert result["sign_off_required"] is True

    def test_human_review_always_in_checks(self):
        result = generate_governance_checklist(_governance())
        items = [c["item"] for c in result["checks"]]
        assert "Human review required" in items

    def test_leakage_exclusions_warn_when_nonzero(self):
        gov = CalibrationGovernanceMetadata(
            model_version="v1",
            calibration_dataset_version="v1",
            calibration_date=date.today(),
            excluded_case_count=5,
        )
        result = generate_governance_checklist(gov)
        checks = {c["item"]: c for c in result["checks"]}
        assert checks["Leakage exclusions"]["status"] == "warn"

    def test_leakage_passes_when_zero(self):
        gov = CalibrationGovernanceMetadata(
            model_version="v1",
            calibration_dataset_version="v1",
            calibration_date=date.today(),
            excluded_case_count=0,
        )
        result = generate_governance_checklist(gov)
        checks = {c["item"]: c for c in result["checks"]}
        assert checks["Leakage exclusions"]["status"] == "pass"


# ---------------------------------------------------------------------------
# build_audit_record
# ---------------------------------------------------------------------------

class TestBuildAuditRecord:
    def test_returns_dict(self):
        output = _layer5_output()
        record = build_audit_record(output)
        assert isinstance(record, dict)

    def test_includes_required_fields(self):
        output = _layer5_output()
        record = build_audit_record(output)
        for field in ("target_id", "acquirer_id", "calibration_quality",
                      "do_not_use_as_probability", "governance_version",
                      "diagnostics_summary"):
            assert field in record

    def test_audit_version_is_set(self):
        record = build_audit_record(_layer5_output())
        assert record["audit_version"] == "1.0"

    def test_run_id_and_user_id_propagated(self):
        record = build_audit_record(
            _layer5_output(), run_id="run-abc", user_id="analyst-1"
        )
        assert record["run_id"] == "run-abc"
        assert record["user_id"] == "analyst-1"

    def test_calibrated_probs_serialised(self):
        record = build_audit_record(_layer5_output())
        probs = record["calibrated_probabilities"]
        assert isinstance(probs, dict)
        assert "p_full_acquisition_12m" in probs

    def test_diagnostics_summary_contains_key_fields(self):
        record = build_audit_record(_layer5_output())
        ds = record["diagnostics_summary"]
        assert "method" in ds
        assert "sample_size" in ds
        assert "brier_score" in ds

    def test_warnings_list_present(self):
        record = build_audit_record(_layer5_output())
        assert isinstance(record["warnings"], list)

    def test_missing_data_list_present(self):
        record = build_audit_record(_layer5_output())
        assert isinstance(record["missing_data"], list)
        assert "recent_deal_activity" in record["missing_data"]

    def test_is_json_serialisable(self):
        record = build_audit_record(_layer5_output())
        serialised = json.dumps(record, default=str)
        loaded = json.loads(serialised)
        assert loaded["target_id"] == "ACME"


# ---------------------------------------------------------------------------
# write_audit_log
# ---------------------------------------------------------------------------

class TestWriteAuditLog:
    def test_writes_jsonl_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "audit.jsonl")
            records = [build_audit_record(_layer5_output(), run_id="r1")]
            write_audit_log(records, path)
            assert os.path.exists(path)
            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 1
            loaded = json.loads(lines[0])
            assert loaded["run_id"] == "r1"

    def test_appends_multiple_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "audit.jsonl")
            rec1 = build_audit_record(_layer5_output(), run_id="r1")
            rec2 = build_audit_record(_layer5_output(), run_id="r2")
            write_audit_log([rec1], path)
            write_audit_log([rec2], path)
            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 2

    def test_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "subdir", "deep", "audit.jsonl")
            write_audit_log([build_audit_record(_layer5_output())], path)
            assert os.path.exists(path)


# ---------------------------------------------------------------------------
# generate_governance_report
# ---------------------------------------------------------------------------

class TestGenerateGovernanceReport:
    def test_returns_dict(self):
        result = generate_governance_report(_artifact())
        assert isinstance(result, dict)

    def test_includes_artifact_id(self):
        result = generate_governance_report(_artifact())
        assert result["artifact_id"] == "artifact-001"

    def test_includes_model_card_by_default(self):
        result = generate_governance_report(_artifact())
        assert "model_card" in result
        assert "# M&A Probability Scoring" in result["model_card"]

    def test_includes_checklist_by_default(self):
        result = generate_governance_report(_artifact())
        assert "checklist" in result
        assert "overall" in result["checklist"]

    def test_model_card_excluded_when_flag_false(self):
        result = generate_governance_report(_artifact(), include_model_card=False)
        assert "model_card" not in result

    def test_checklist_excluded_when_flag_false(self):
        result = generate_governance_report(_artifact(), include_checklist=False)
        assert "checklist" not in result

    def test_drift_report_included_when_provided(self):
        result = generate_governance_report(_artifact(), drift_report=_drift_report("mild"))
        assert "drift_report" in result
        assert result["drift_report"]["drift_status"] == "mild"

    def test_threshold_recs_included_when_provided(self):
        result = generate_governance_report(
            _artifact(), threshold_recs=[_threshold_rec()]
        )
        assert "threshold_recommendations" in result
        assert len(result["threshold_recommendations"]) == 1

    def test_layer_validation_included_when_flag_set(self):
        result = generate_governance_report(_artifact(), include_layer_validation=True)
        assert "layer_validation" in result
        assert "layers" in result["layer_validation"]

    def test_generated_at_is_today(self):
        result = generate_governance_report(_artifact())
        assert result["generated_at"] == date.today().isoformat()
