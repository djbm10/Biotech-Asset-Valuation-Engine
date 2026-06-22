from __future__ import annotations

from bve.intelligence.science_calibration import (
    ScienceCalibrationRecommendation,
    evaluate_calibration_readiness,
)
from bve.intelligence.science_outcomes import (
    ScienceOutcomeLabel,
    ScienceOutcomeRecord,
    build_science_diagnostics,
)


def test_science_outcome_diagnostics_group_failures_without_weight_changes() -> None:
    report = build_science_diagnostics(
        [
            ScienceOutcomeRecord(
                asset_id="a1",
                outcome_label=ScienceOutcomeLabel.TARGET_PATHWAY_FAILURE,
                science_binding_question="right_target",
                science_modifier=0.75,
                missing_critical_evidence_count=2,
            ),
            ScienceOutcomeRecord(
                asset_id="a2",
                outcome_label=ScienceOutcomeLabel.TARGET_PATHWAY_FAILURE,
                science_binding_question="right_target",
                science_modifier=0.65,
                missing_critical_evidence_count=4,
            ),
            ScienceOutcomeRecord(
                asset_id="a3",
                outcome_label=ScienceOutcomeLabel.EXPOSURE_DOSE_FAILURE,
                science_binding_question="enough_drug",
                science_modifier=0.8,
                missing_critical_evidence_count=1,
            ),
            ScienceOutcomeRecord(asset_id="a4", outcome_label=ScienceOutcomeLabel.UNKNOWN),
        ]
    )

    assert report.n_records == 4
    assert report.n_labeled == 3
    assert report.outcome_counts["target_pathway_failure"] == 2
    assert report.binding_question_by_outcome["target_pathway_failure"] == {"right_target": 2}
    assert report.average_modifier_by_outcome["target_pathway_failure"] == 0.7
    assert report.average_missing_evidence_by_outcome["target_pathway_failure"] == 3.0
    assert report.average_modifier_by_outcome["unknown"] is None


def test_calibration_readiness_is_diagnostics_only_until_explicit_review() -> None:
    insufficient = evaluate_calibration_readiness(12, min_cases_required=50)
    assert insufficient.recommendation == ScienceCalibrationRecommendation.INSUFFICIENT_DATA
    assert insufficient.calibration_status == "heuristic"
    assert insufficient.weight_update_allowed is False

    ready = evaluate_calibration_readiness(75, min_cases_required=50)
    assert ready.recommendation == ScienceCalibrationRecommendation.READY_FOR_RECALIBRATION_REVIEW
    assert ready.calibration_status == "heuristic"
    assert ready.weight_update_allowed is False
