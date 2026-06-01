"""
Block 5C — Acquirer-Fit Calibration Report.

Analyses resolved prediction errors from AcquirerFitLog and surfaces:
  1. Per-dimension error rates (which dimensions contributed to misranked deals)
  2. Systematic biases by TA / stage
  3. Suggested SCORE_VERSIONS weight adjustments

The report is advisory — it does NOT automatically overwrite scoring weights.
Weight updates must be reviewed and applied by a human.

Usage::

    from bve.intelligence.acquirer_fit_calibration import build_calibration_report

    report = build_calibration_report(
        store_path="outputs/intelligence/fit_log.sqlite",
        graded_predictions=graded,   # from acquirer_fit_log.grade_fit_predictions()
        current_weights={"therapeutic_area": 0.25, ...},
    )
    print(report.summary_text)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from bve.intelligence.acquirer_fit_log import (
    FitGradeReport,
    FitPredictionRecord,
    get_fit_predictions,
)


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

@dataclass
class WeightSuggestion:
    dimension: str
    current_weight: float
    suggested_weight: float
    delta: float
    reason: str

    def __str__(self) -> str:
        direction = "↑" if self.delta > 0 else "↓"
        return (
            f"  {self.dimension}: {self.current_weight:.2f} → "
            f"{self.suggested_weight:.2f} ({direction}{abs(self.delta):.2f}) — {self.reason}"
        )


@dataclass
class CalibrationReport:
    """Calibration analysis and weight suggestions for the acquirer-fit scorer."""
    n_resolved: int
    n_deals: int
    precision_at_1: float
    precision_at_3: float
    mean_reciprocal_rank: float
    # Dimensions where deals ranked lower than non-deals
    underweighted_dimensions: list[str]
    # Dimensions that ranked non-deals above deals
    overweighted_dimensions: list[str]
    # Suggested weight updates
    weight_suggestions: list[WeightSuggestion]
    # TA / stage bias summary
    ta_error_rates: dict[str, float]   # TA → fraction of deal assets that ranked > 3
    stage_error_rates: dict[str, float]
    # Human-readable summary
    summary_text: str


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

_SCORE_DIMENSIONS = [
    "therapeutic_area", "modality", "stage",
    "strategic_priority", "valuation", "budget",
]

_DEFAULT_WEIGHTS: dict[str, float] = {
    "therapeutic_area": 0.25,
    "modality": 0.20,
    "stage": 0.15,
    "strategic_priority": 0.15,
    "valuation": 0.10,
    "budget": 0.15,
}

# Adjustment magnitude per dimension per unit of error
_LEARNING_RATE = 0.02
_MAX_WEIGHT_DELTA = 0.05
_MIN_WEIGHT = 0.05
_MAX_WEIGHT = 0.45


def _compute_ta_error_rates(records: list[FitPredictionRecord]) -> dict[str, float]:
    """
    For each TA, fraction of deal-assets that ranked > 3 (misranked).
    Higher = TA deals are being systematically undervalued.
    """
    _deal_outcomes = {"acquisition", "license", "partnership"}
    ta_totals: dict[str, int] = {}
    ta_missed: dict[str, int] = {}

    for r in records:
        if r.outcome not in _deal_outcomes:
            continue
        ta = r.therapeutic_area or "unknown"
        ta_totals[ta] = ta_totals.get(ta, 0) + 1
        if r.rank > 3:
            ta_missed[ta] = ta_missed.get(ta, 0) + 1

    return {
        ta: ta_missed.get(ta, 0) / total
        for ta, total in ta_totals.items()
        if total >= 2  # minimum sample size
    }


def _compute_stage_error_rates(records: list[FitPredictionRecord]) -> dict[str, float]:
    _deal_outcomes = {"acquisition", "license", "partnership"}
    stage_totals: dict[str, int] = {}
    stage_missed: dict[str, int] = {}

    for r in records:
        if r.outcome not in _deal_outcomes:
            continue
        stage = r.stage or "unknown"
        stage_totals[stage] = stage_totals.get(stage, 0) + 1
        if r.rank > 3:
            stage_missed[stage] = stage_missed.get(stage, 0) + 1

    return {
        stage: stage_missed.get(stage, 0) / total
        for stage, total in stage_totals.items()
        if total >= 2
    }


def _suggest_weights(
    grade: FitGradeReport,
    ta_errors: dict[str, float],
    stage_errors: dict[str, float],
    current_weights: dict[str, float],
) -> tuple[list[str], list[str], list[WeightSuggestion]]:
    """
    Derive weight adjustments from error signals.

    Rules:
    - High TA error rate → TA dimension underweighted; suggest increasing it
    - High stage error rate → stage dimension underweighted
    - P@1 < 0.20 and P@3 < 0.35 → system-level under-performance; focus on top-2 dims
    - Uses small learning steps; deltas capped at ±0.05 per run

    Returns:
        (underweighted_dims, overweighted_dims, suggestions)
    """
    suggestions: list[WeightSuggestion] = []
    underweighted: list[str] = []
    overweighted: list[str] = []

    new_weights = dict(current_weights)

    # Signal 1: High TA error rate → TA probably underweighted
    if ta_errors:
        avg_ta_err = sum(ta_errors.values()) / len(ta_errors)
        if avg_ta_err > 0.5:
            underweighted.append("therapeutic_area")
            new_weights["therapeutic_area"] = min(
                _MAX_WEIGHT,
                new_weights.get("therapeutic_area", 0.25) + _LEARNING_RATE,
            )

    # Signal 2: High stage error rate → stage probably underweighted
    if stage_errors:
        avg_stage_err = sum(stage_errors.values()) / len(stage_errors)
        if avg_stage_err > 0.5:
            underweighted.append("stage")
            new_weights["stage"] = min(
                _MAX_WEIGHT,
                new_weights.get("stage", 0.15) + _LEARNING_RATE,
            )

    # Signal 3: Low MRR overall → strategic_priority may be too high (noise)
    if grade.mean_reciprocal_rank < 0.20 and grade.n_screens >= 3:
        overweighted.append("strategic_priority")
        new_weights["strategic_priority"] = max(
            _MIN_WEIGHT,
            new_weights.get("strategic_priority", 0.15) - _LEARNING_RATE,
        )

    # Signal 4: Low P@1 but decent P@3 → valuation is noisy; reduce weight
    if grade.precision_at_1 < 0.15 and grade.precision_at_3 >= 0.35 and grade.n_screens >= 5:
        overweighted.append("valuation")
        new_weights["valuation"] = max(
            _MIN_WEIGHT,
            new_weights.get("valuation", 0.10) - _LEARNING_RATE,
        )

    # Renormalize so weights sum to 1.0
    total = sum(new_weights.values())
    if total > 0:
        new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}

    # Build suggestions for changed dimensions
    for dim in _SCORE_DIMENSIONS:
        current = current_weights.get(dim, _DEFAULT_WEIGHTS.get(dim, 0.0))
        suggested = new_weights.get(dim, current)
        delta = round(suggested - current, 4)
        if abs(delta) >= 0.005:
            if dim in underweighted:
                reason = "deal assets ranked too low; increase weight to boost deal recall"
            elif dim in overweighted:
                reason = "high-ranked non-deals suggest dimension is adding noise"
            else:
                reason = "renormalization after other dimension adjustments"
            suggestions.append(WeightSuggestion(
                dimension=dim,
                current_weight=current,
                suggested_weight=suggested,
                delta=delta,
                reason=reason,
            ))

    # Sort by abs(delta) desc
    suggestions.sort(key=lambda s: abs(s.delta), reverse=True)
    return sorted(set(underweighted)), sorted(set(overweighted)), suggestions


def _build_summary(
    grade: FitGradeReport,
    weight_suggestions: list[WeightSuggestion],
    ta_errors: dict[str, float],
    stage_errors: dict[str, float],
) -> str:
    lines = [
        "Acquirer-Fit Calibration Report",
        f"  Resolved records:  {grade.n_total}",
        f"  Deals in dataset:  {grade.n_deals}",
        f"  P@1:               {grade.precision_at_1:.1%}",
        f"  P@3:               {grade.precision_at_3:.1%}",
        f"  MRR:               {grade.mean_reciprocal_rank:.3f}",
    ]

    if ta_errors:
        worst_ta = max(ta_errors, key=ta_errors.get)  # type: ignore[arg-type]
        lines.append(f"  Worst TA miss rate: {worst_ta} ({ta_errors[worst_ta]:.1%} of deals ranked >3)")

    if stage_errors:
        worst_stage = max(stage_errors, key=stage_errors.get)  # type: ignore[arg-type]
        lines.append(f"  Worst stage miss:  {worst_stage} ({stage_errors[worst_stage]:.1%} of deals ranked >3)")

    if weight_suggestions:
        lines.append(f"\n  Suggested weight adjustments ({len(weight_suggestions)}):")
        for s in weight_suggestions:
            lines.append(str(s))
    else:
        lines.append("\n  No weight adjustments suggested (performance is adequate).")

    lines.append(
        "\n  NOTE: These are advisory suggestions only. Apply weight changes "
        "by updating SCORE_VERSIONS in acquirer_fit.py after human review."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_calibration_report(
    store_path: str,
    *,
    grade: Optional[FitGradeReport] = None,
    acquirer_id: Optional[str] = None,
    current_weights: Optional[dict[str, float]] = None,
) -> CalibrationReport:
    """
    Build a calibration report from resolved acquirer-fit predictions.

    Args:
        store_path: SQLite path containing FitPredictionLog.
        grade: Pre-computed FitGradeReport (optional; computed from store if None).
        acquirer_id: Limit analysis to one acquirer.
        current_weights: Current SCORE_VERSIONS weights to compare against.
                         Defaults to SCORE_VERSIONS["v1.0"].

    Returns:
        CalibrationReport with weight suggestions and error breakdown.
    """
    if current_weights is None:
        current_weights = dict(_DEFAULT_WEIGHTS)

    if grade is None:
        from bve.intelligence.acquirer_fit_log import grade_fit_predictions
        grade = grade_fit_predictions(store_path, acquirer_id=acquirer_id)

    if grade.n_total == 0:
        return CalibrationReport(
            n_resolved=0,
            n_deals=0,
            precision_at_1=0.0,
            precision_at_3=0.0,
            mean_reciprocal_rank=0.0,
            underweighted_dimensions=[],
            overweighted_dimensions=[],
            weight_suggestions=[],
            ta_error_rates={},
            stage_error_rates={},
            summary_text="No resolved predictions available. Log and resolve predictions first.",
        )

    records = get_fit_predictions(store_path, acquirer_id=acquirer_id, resolved_only=True)
    ta_errors = _compute_ta_error_rates(records)
    stage_errors = _compute_stage_error_rates(records)

    underweighted, overweighted, suggestions = _suggest_weights(
        grade, ta_errors, stage_errors, current_weights
    )

    summary = _build_summary(grade, suggestions, ta_errors, stage_errors)

    return CalibrationReport(
        n_resolved=grade.n_total,
        n_deals=grade.n_deals,
        precision_at_1=grade.precision_at_1,
        precision_at_3=grade.precision_at_3,
        mean_reciprocal_rank=grade.mean_reciprocal_rank,
        underweighted_dimensions=underweighted,
        overweighted_dimensions=overweighted,
        weight_suggestions=suggestions,
        ta_error_rates=ta_errors,
        stage_error_rates=stage_errors,
        summary_text=summary,
    )
