"""Phase N calibration feedback loop."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import yaml
from pydantic import BaseModel, Field

from bve.intelligence.decision_layer import OutcomeAttribution
from bve.intelligence.weekly_review import WeeklyReviewReport

if TYPE_CHECKING:
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CalibrationFeedbackModuleOutput(BaseModel):
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[str] = Field(default_factory=list)
    freshness: datetime
    explainability: str
    downstream_dependencies: list[str] = Field(default_factory=list)


class CalibrationAdjustment(BaseModel):
    dimension: str
    current_value: float
    updated_value: float
    change: float
    reason: str


class CalibrationFeedbackValue(BaseModel):
    run_date: str
    pos_prior_adjustments: list[CalibrationAdjustment] = Field(default_factory=list)
    scenario_weight_adjustments: list[CalibrationAdjustment] = Field(default_factory=list)
    timeline_distribution_adjustments: list[CalibrationAdjustment] = Field(default_factory=list)
    financing_penalty_adjustments: list[CalibrationAdjustment] = Field(default_factory=list)
    competition_penalty_adjustments: list[CalibrationAdjustment] = Field(default_factory=list)
    access_modifier_adjustments: list[CalibrationAdjustment] = Field(default_factory=list)
    analyst_vs_model_drift_score: float = Field(ge=0.0, le=1.0, default=0.0)


class CalibrationFeedbackAssessment(BaseModel):
    output: CalibrationFeedbackModuleOutput
    plain_english_summary: str


class CalibrationFeedbackLoop:
    """Turn post-mortems and realized outcomes into parameter updates."""

    def build(
        self,
        *,
        pos_report: Any,
        ranking_report: Any,
        weekly_review: WeeklyReviewReport,
        attributions: list[OutcomeAttribution],
        freshness: Optional[datetime] = None,
    ) -> CalibrationFeedbackAssessment:
        freshness = freshness or _utcnow()
        pos_adjustments = self._pos_prior_adjustments(pos_report)
        scenario_adjustments = self._scenario_adjustments(weekly_review)
        timeline_adjustments = self._timeline_adjustments(weekly_review)
        financing_adjustments = self._financing_adjustments(attributions)
        competition_adjustments = self._competition_adjustments(weekly_review, attributions)
        access_adjustments = self._access_adjustments(ranking_report, weekly_review)
        drift_score = self._analyst_vs_model_drift_score(weekly_review)

        value = CalibrationFeedbackValue(
            run_date=pos_report.run_date,
            pos_prior_adjustments=pos_adjustments,
            scenario_weight_adjustments=scenario_adjustments,
            timeline_distribution_adjustments=timeline_adjustments,
            financing_penalty_adjustments=financing_adjustments,
            competition_penalty_adjustments=competition_adjustments,
            access_modifier_adjustments=access_adjustments,
            analyst_vs_model_drift_score=drift_score,
        )
        output = CalibrationFeedbackModuleOutput(
            value=value.model_dump(),
            confidence=self._confidence(pos_report, ranking_report, weekly_review, attributions),
            provenance=[
                f"pos_recalibration:{pos_report.run_date}",
                f"ranking_calibration:{ranking_report.run_date.isoformat()}",
                f"weekly_review:{weekly_review.week_ending.isoformat()}",
                f"attributions:{len(attributions)}",
            ],
            freshness=freshness,
            explainability=(
                "Calibration feedback converts realized forecast quality, execution drift, and "
                "post-mortem attribution into explicit parameter updates for priors, scenario weights, "
                "timeline assumptions, and penalty layers."
            ),
            downstream_dependencies=["operating_layer"],
        )
        summary = (
            f"Calibration feedback generated {len(pos_adjustments)} PoS update(s), "
            f"{len(scenario_adjustments)} scenario update(s), and drift score {drift_score:.2f}."
        )
        return CalibrationFeedbackAssessment(output=output, plain_english_summary=summary)

    def write_feedback_artifact(
        self,
        assessment: CalibrationFeedbackAssessment,
        path: str | Path,
    ) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            yaml.safe_dump(assessment.output.value, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    @staticmethod
    def _pos_prior_adjustments(pos_report: Any) -> list[CalibrationAdjustment]:
        out: list[CalibrationAdjustment] = []
        for seg in pos_report.segments:
            if not seg.updated_from_data:
                continue
            change = round(seg.updated_rate - seg.prior_rate, 6)
            if abs(change) < 0.01:
                continue
            out.append(
                CalibrationAdjustment(
                    dimension=f"pos_prior:{seg.trial_phase}:{seg.indication}",
                    current_value=round(seg.prior_rate, 6),
                    updated_value=round(seg.updated_rate, 6),
                    change=change,
                    reason=f"Bayesian update from {seg.n_observations} resolved forecasts.",
                )
            )
        return out

    @staticmethod
    def _scenario_adjustments(weekly_review: WeeklyReviewReport) -> list[CalibrationAdjustment]:
        fundamental = weekly_review.fundamental
        total = max(fundamental.n_resolved, 1)
        setback_rate = (fundamental.n_pos_error + fundamental.n_market_drift) / total
        delayed_rate = fundamental.n_timing_error / total
        full_approval_current = 0.45
        delayed_current = 0.15
        setback_current = 0.20
        full_approval_new = max(0.10, min(0.80, full_approval_current - (0.20 * setback_rate)))
        delayed_new = max(0.05, min(0.50, delayed_current + (0.25 * delayed_rate)))
        setback_new = max(0.05, min(0.60, setback_current + (0.20 * setback_rate)))
        return [
            CalibrationAdjustment(
                dimension="scenario_weight:full_approval",
                current_value=full_approval_current,
                updated_value=round(full_approval_new, 6),
                change=round(full_approval_new - full_approval_current, 6),
                reason="Reduced when realized misses and market-drift cases accumulate.",
            ),
            CalibrationAdjustment(
                dimension="scenario_weight:delayed_approval",
                current_value=delayed_current,
                updated_value=round(delayed_new, 6),
                change=round(delayed_new - delayed_current, 6),
                reason="Increased when timing errors indicate underestimated delays.",
            ),
            CalibrationAdjustment(
                dimension="scenario_weight:crl_major_setback",
                current_value=setback_current,
                updated_value=round(setback_new, 6),
                change=round(setback_new - setback_current, 6),
                reason="Raised when realized errors show more setback risk than expected.",
            ),
        ]

    @staticmethod
    def _timeline_adjustments(weekly_review: WeeklyReviewReport) -> list[CalibrationAdjustment]:
        pct_stale = weekly_review.market_timing.pct_stale or 0.0
        current_delay_mean = 6.0
        updated_delay_mean = round(current_delay_mean * (1.0 + pct_stale), 6)
        return [
            CalibrationAdjustment(
                dimension="timeline_distribution:delay_mean_months",
                current_value=current_delay_mean,
                updated_value=updated_delay_mean,
                change=round(updated_delay_mean - current_delay_mean, 6),
                reason="Extended when stale-signal rate implies timelines are slipping faster than expected.",
            )
        ]

    @staticmethod
    def _financing_adjustments(attributions: list[OutcomeAttribution]) -> list[CalibrationAdjustment]:
        if not attributions:
            return []
        financing_like = [a for a in attributions if a.attribution_type in {"sizing_error", "market_drift"}]
        pressure = len(financing_like) / len(attributions)
        current_penalty = 0.25
        updated = round(min(0.60, current_penalty + (0.20 * pressure)), 6)
        return [
            CalibrationAdjustment(
                dimension="financing_penalty:base",
                current_value=current_penalty,
                updated_value=updated,
                change=round(updated - current_penalty, 6),
                reason="Raised when realized outcomes show sizing/market drift consistent with financing overhang.",
            )
        ]

    @staticmethod
    def _competition_adjustments(
        weekly_review: WeeklyReviewReport,
        attributions: list[OutcomeAttribution],
    ) -> list[CalibrationAdjustment]:
        current_penalty = 0.15
        competitor_refutes = weekly_review.thesis.n_assets_with_refuted_key_claim
        attr_pressure = sum(1 for a in attributions if a.attribution_type == "thesis_error")
        updated = round(min(0.50, current_penalty + 0.05 * competitor_refutes + 0.03 * attr_pressure), 6)
        return [
            CalibrationAdjustment(
                dimension="competition_penalty:base",
                current_value=current_penalty,
                updated_value=updated,
                change=round(updated - current_penalty, 6),
                reason="Raised when key claims fail and realized thesis errors imply competition was underestimated.",
            )
        ]

    @staticmethod
    def _access_adjustments(
        ranking_report: Any,
        weekly_review: WeeklyReviewReport,
    ) -> list[CalibrationAdjustment]:
        current_modifier = 1.0
        brier = ranking_report.brier_score
        thesis_drag = max(0, weekly_review.thesis.n_key_claims_refuted - weekly_review.thesis.n_key_claims_confirmed)
        updated = round(max(0.70, min(1.10, current_modifier - 0.20 * brier - 0.03 * thesis_drag)), 6)
        return [
            CalibrationAdjustment(
                dimension="access_modifier:base",
                current_value=current_modifier,
                updated_value=updated,
                change=round(updated - current_modifier, 6),
                reason="Tightened when calibration error and thesis refutations imply commercial/access assumptions were too generous.",
            )
        ]

    @staticmethod
    def _analyst_vs_model_drift_score(weekly_review: WeeklyReviewReport) -> float:
        return round(weekly_review.sizing.pct_diverged or 0.0, 6)

    @staticmethod
    def _confidence(
        pos_report: Any,
        ranking_report: Any,
        weekly_review: WeeklyReviewReport,
        attributions: list[OutcomeAttribution],
    ) -> float:
        confidence = 0.55
        if pos_report.n_resolved_forecasts >= 20:
            confidence += 0.10
        if ranking_report.n_resolved_forecasts >= 20:
            confidence += 0.10
        if weekly_review.fundamental.n_resolved >= 5:
            confidence += 0.10
        confidence += min(0.10, len(attributions) * 0.01)
        return round(min(0.95, confidence), 4)
