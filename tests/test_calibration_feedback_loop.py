from __future__ import annotations

from datetime import date, datetime, timezone

import yaml

from bve.analysis.pos_recalibrator import PoSCalibrationReport, SegmentCalibration
from bve.analysis.ranking_calibrator import CalibrationReport
from bve.intelligence.calibration_feedback_loop import (
    CalibrationFeedbackLoop,
    CalibrationFeedbackValue,
)
from bve.intelligence.decision_layer import OutcomeAttribution
from bve.intelligence.weekly_review import (
    FundamentalAccuracy,
    MarketTimingAccuracy,
    PolicyAudit,
    SizingQuality,
    ThesisAccuracy,
    WeeklyReviewReport,
)


def _pos_report() -> PoSCalibrationReport:
    return PoSCalibrationReport(
        run_date="2026-04-18",
        n_resolved_forecasts=42,
        n_segments=2,
        segments=[
            SegmentCalibration(
                trial_phase="phase_2",
                indication="oncology",
                n_observations=22,
                n_correct=14,
                empirical_success_rate=0.6364,
                prior_rate=0.37,
                updated_rate=0.45,
                updated_from_data=True,
                drift_pct=21.62,
            ),
            SegmentCalibration(
                trial_phase="phase_3",
                indication="rare_disease",
                n_observations=10,
                n_correct=6,
                empirical_success_rate=0.60,
                prior_rate=0.60,
                updated_rate=0.60,
                updated_from_data=False,
                drift_pct=None,
            ),
        ],
        drift_alerts=["phase_2/oncology drift"],
    )


def _ranking_report() -> CalibrationReport:
    return CalibrationReport(
        run_date=date(2026, 4, 18),
        n_resolved_forecasts=55,
        event_type_weights={"trial_readout": 0.52},
        event_type_weights_prior={"trial_readout": 0.45},
        confidence_scaling_factor=1.10,
        brier_score=0.18,
        calibration_curve=[],
        drift_alerts=["trial_readout drift"],
    )


def _weekly_review() -> WeeklyReviewReport:
    return WeeklyReviewReport(
        week_ending=date(2026, 4, 18),
        lookback_days=7,
        fundamental=FundamentalAccuracy(
            n_resolved=10,
            n_correct=6,
            hit_rate=0.6,
            n_pos_error=2,
            n_timing_error=2,
            n_market_drift=1,
            n_confirmed_thesis=4,
            n_unclassified=1,
        ),
        market_timing=MarketTimingAccuracy(
            n_forecasts_checked=10,
            n_stale_signals=3,
            pct_stale=0.3,
            avg_signal_age_days=18.0,
            stale_threshold_days=30,
        ),
        thesis=ThesisAccuracy(
            n_key_claims_confirmed=3,
            n_key_claims_refuted=2,
            n_all_claims_confirmed=4,
            n_all_claims_refuted=3,
            n_assets_with_refuted_key_claim=1,
            net_thesis_score=0.2,
        ),
        sizing=SizingQuality(
            n_decisions_checked=8,
            n_with_execution=6,
            n_recommended_vs_executed_diverged=2,
            pct_diverged=0.3333,
            avg_size_divergence_pct=0.025,
            n_oversized=1,
        ),
        policy_audit=PolicyAudit(),
        calibration_drift_fired=True,
    )


def _attributions() -> list[OutcomeAttribution]:
    now = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
    return [
        OutcomeAttribution(
            decision_id="d1",
            asset_id="asset-1",
            return_pct=-0.25,
            attribution_type="sizing_error",
            resolved_at=now,
            notes="financing overhang",
        ),
        OutcomeAttribution(
            decision_id="d2",
            asset_id="asset-2",
            return_pct=-0.18,
            attribution_type="thesis_error",
            resolved_at=now,
            notes="competition underestimated",
        ),
        OutcomeAttribution(
            decision_id="d3",
            asset_id="asset-3",
            return_pct=0.05,
            attribution_type="market_drift",
            resolved_at=now,
            notes="squeeze",
        ),
    ]


def test_phase_n_builds_feedback_adjustments_across_layers(tmp_path) -> None:
    engine = CalibrationFeedbackLoop()
    assessment = engine.build(
        pos_report=_pos_report(),
        ranking_report=_ranking_report(),
        weekly_review=_weekly_review(),
        attributions=_attributions(),
        freshness=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )
    value = CalibrationFeedbackValue.model_validate(assessment.output.value)

    assert value.pos_prior_adjustments
    assert any(item.dimension.startswith("scenario_weight:") for item in value.scenario_weight_adjustments)
    assert value.timeline_distribution_adjustments
    assert value.financing_penalty_adjustments
    assert value.competition_penalty_adjustments
    assert value.access_modifier_adjustments
    assert value.analyst_vs_model_drift_score == 0.3333
    assert assessment.output.confidence >= 0.8

    out = tmp_path / "calibration_feedback.yaml"
    engine.write_feedback_artifact(assessment, out)
    payload = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert payload["run_date"] == "2026-04-18"
    assert payload["pos_prior_adjustments"]


def test_phase_n_handles_sparse_inputs_without_crashing() -> None:
    engine = CalibrationFeedbackLoop()
    sparse = engine.build(
        pos_report=PoSCalibrationReport(
            run_date="2026-04-18",
            n_resolved_forecasts=0,
            n_segments=0,
            segments=[],
            drift_alerts=[],
        ),
        ranking_report=CalibrationReport(
            run_date=date(2026, 4, 18),
            n_resolved_forecasts=0,
            event_type_weights={},
            event_type_weights_prior={},
            confidence_scaling_factor=1.0,
            brier_score=0.0,
            calibration_curve=[],
            drift_alerts=[],
        ),
        weekly_review=WeeklyReviewReport(
            week_ending=date(2026, 4, 18),
            fundamental=FundamentalAccuracy(),
            market_timing=MarketTimingAccuracy(),
            thesis=ThesisAccuracy(),
            sizing=SizingQuality(),
            policy_audit=PolicyAudit(),
        ),
        attributions=[],
        freshness=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )
    value = CalibrationFeedbackValue.model_validate(sparse.output.value)
    assert value.pos_prior_adjustments == []
    assert sparse.output.confidence >= 0.55
