"""Layer 5 — 5E: Threshold Optimizer.

Recommends operating thresholds for Layers 2–4 based on historical
performance data.

IMPORTANT: Layer 5 never silently overwrites production thresholds.
  - should_auto_apply = False by default on ALL recommendations
  - requires_human_review = True by default on ALL recommendations

Supported operating modes:
  HIGH_PRECISION     → favor fewer but more certain actions
  HIGH_RECALL        → catch more opportunities even at FP cost
  BALANCED           → equal weight on precision and recall
  STRATEGIC_SCARCITY → emphasize rare high-quality assets
  CAPITAL_DISCIPLINE → aggressively prune false positives
  RELATIONSHIP_BUILDING → maximize coverage, minimize missed targets
"""
from __future__ import annotations

from typing import Optional

from bve.intelligence.ma_calibration_models import (
    HistoricalMAOutcome,
    OperatingMode,
    ThresholdRecommendation,
)

# Default threshold values (current production thresholds)
_CURRENT_THRESHOLDS: dict[str, float] = {
    "active_pursuit": 0.75,
    "high_priority_diligence": 0.70,
    "catalyst_watch": 0.65,
    "strategic_watch": 0.70,
    "pass": 0.40,
    "pair_hard_fail_cap": 0.70,
    "information_readiness": 0.60,
    "route_confidence": 0.50,
    "outreach_ready": 0.60,
}

# Operating mode modifier: (precision_bias, recall_bias) where positive = more conservative
_MODE_MODIFIERS: dict[OperatingMode, tuple[float, float]] = {
    OperatingMode.HIGH_PRECISION:       (+0.06, -0.04),
    OperatingMode.HIGH_RECALL:          (-0.06, +0.04),
    OperatingMode.BALANCED:             (0.00,  0.00),
    OperatingMode.STRATEGIC_SCARCITY:   (+0.04, -0.02),
    OperatingMode.CAPITAL_DISCIPLINE:   (+0.08, -0.06),
    OperatingMode.RELATIONSHIP_BUILDING: (-0.08, +0.06),
}

# Cost matrix defaults
_DEFAULT_COST: dict[str, float] = {
    "false_active_pursuit_cost": 1.0,
    "false_pass_cost": 2.0,        # missing a deal is usually worse than false positive
    "false_watch_cost": 0.5,
    "missed_deal_cost": 3.0,
    "premature_outreach_cost": 1.5,
    "wasted_diligence_cost": 1.0,
    "relationship_damage_cost": 2.0,
}


def compute_precision_recall_tradeoff(
    cases: list[HistoricalMAOutcome],
    threshold_name: str,
    threshold_range: tuple[float, float] = (0.30, 0.95),
    n_steps: int = 14,
) -> list[dict]:
    """Evaluate precision/recall at various threshold levels.

    Args:
        cases: Historical outcome records with layer2_snapshot containing bd_action_score.
        threshold_name: Name of the threshold being optimized.
        threshold_range: (min_threshold, max_threshold) to evaluate.
        n_steps: Number of threshold levels.

    Returns:
        List of dicts: {"threshold", "precision", "recall", "f1", "n_above"}.
    """
    lo, hi = threshold_range
    step = (hi - lo) / max(n_steps - 1, 1)
    thresholds = [round(lo + i * step, 4) for i in range(n_steps)]

    results = []
    for t in thresholds:
        tp = fp = fn = tn = 0
        for case in cases:
            score = _extract_score(case, threshold_name)
            if score is None:
                continue
            predicted_positive = score >= t
            actual_positive = case.labels.acquired_within_12m
            if predicted_positive and actual_positive:
                tp += 1
            elif predicted_positive and not actual_positive:
                fp += 1
            elif not predicted_positive and actual_positive:
                fn += 1
            else:
                tn += 1

        precision = tp / (tp + fp) if (tp + fp) > 0 else None
        recall = tp / (tp + fn) if (tp + fn) > 0 else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and (precision + recall) > 0
            else None
        )
        results.append({
            "threshold": t,
            "precision": round(precision, 4) if precision is not None else None,
            "recall": round(recall, 4) if recall is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
            "n_above": tp + fp,
        })
    return results


def _extract_score(case: HistoricalMAOutcome, threshold_name: str) -> Optional[float]:
    """Extract the relevant score for a threshold from a case's snapshots."""
    # Try layer2 first for BD-related scores
    for snap in (case.layer2_snapshot, case.layer1_snapshot, case.layer3_snapshot):
        if not snap:
            continue
        for field in ("bd_action_score", "layer2_score", "layer1_score", "pair_feasibility_score"):
            val = snap.get(field)
            if val is not None:
                return float(val)
    return None


def optimize_for_operating_mode(
    current_threshold: float,
    operating_mode: OperatingMode,
    *,
    cost_matrix: Optional[dict[str, float]] = None,
) -> tuple[float, float, float]:
    """Compute recommended threshold for a given operating mode.

    Uses cost matrix and mode modifier to adjust threshold.

    Returns:
        (recommended_threshold, expected_precision_delta, expected_recall_delta)
    """
    costs = {**_DEFAULT_COST, **(cost_matrix or {})}
    precision_bias, recall_bias = _MODE_MODIFIERS[operating_mode]

    # Additional cost-driven adjustment
    fp_cost = costs.get("false_active_pursuit_cost", 1.0)
    fn_cost = costs.get("missed_deal_cost", 2.0)
    cost_ratio = fp_cost / (fp_cost + fn_cost)  # 0..1; higher → be more conservative

    # Map cost ratio to threshold delta: [0..0.5] → [-0.02..+0.02]
    cost_adj = (cost_ratio - 0.5) * 0.08

    raw_threshold = current_threshold + precision_bias + cost_adj
    recommended = round(max(0.10, min(0.95, raw_threshold)), 4)

    # Expected performance deltas (approximations)
    precision_delta = precision_bias * 0.5
    recall_delta = recall_bias * 0.5

    return recommended, round(precision_delta, 4), round(recall_delta, 4)


def generate_threshold_recommendations(
    cases: list[HistoricalMAOutcome],
    operating_mode: OperatingMode,
    *,
    cost_matrix: Optional[dict[str, float]] = None,
    threshold_names: Optional[list[str]] = None,
) -> list[ThresholdRecommendation]:
    """Generate threshold recommendations for the given operating mode.

    SAFETY: All recommendations have should_auto_apply=False and
    requires_human_review=True. Layer 5 never silently rewrites production thresholds.

    Args:
        cases: Historical outcome records.
        operating_mode: Desired operating mode.
        cost_matrix: Override default cost matrix.
        threshold_names: Subset of thresholds to evaluate (all if None).

    Returns:
        List of ThresholdRecommendation, one per threshold.
    """
    names = threshold_names or list(_CURRENT_THRESHOLDS.keys())
    recs: list[ThresholdRecommendation] = []

    for name in names:
        current = _CURRENT_THRESHOLDS.get(name, 0.5)
        recommended, prec_delta, recall_delta = optimize_for_operating_mode(
            current, operating_mode, cost_matrix=cost_matrix
        )

        # Sample precision/recall from historical data if available
        tradeoff = compute_precision_recall_tradeoff(cases, name) if cases else []
        hist_prec: Optional[float] = None
        hist_recall: Optional[float] = None
        for row in tradeoff:
            if abs(row["threshold"] - current) < 0.05:
                hist_prec = row["precision"]
                hist_recall = row["recall"]
                break

        # Estimate expected metrics
        exp_prec = (
            round(hist_prec + prec_delta, 4) if hist_prec is not None else None
        )
        exp_recall = (
            round(hist_recall + recall_delta, 4) if hist_recall is not None else None
        )

        explanation = (
            f"Operating mode: {operating_mode.value}. "
            f"Current threshold: {current}. "
            f"Recommended: {recommended}. "
        )
        if recommended > current:
            explanation += (
                f"Raising threshold by {recommended - current:.3f} "
                "reduces false active pursuits at the cost of lower recall."
            )
        elif recommended < current:
            explanation += (
                f"Lowering threshold by {current - recommended:.3f} "
                "increases recall at the cost of more false active pursuits."
            )
        else:
            explanation += "No change recommended for this mode."

        if hist_prec is not None:
            explanation += (
                f" Historical precision@current: {hist_prec:.2%}. "
                f"Historical recall@current: {hist_recall:.2%}."
            ) if hist_recall is not None else f" Historical precision@current: {hist_prec:.2%}."

        recs.append(ThresholdRecommendation(
            threshold_name=name,
            current_threshold=current,
            recommended_threshold=recommended,
            operating_mode=operating_mode,
            expected_precision=exp_prec,
            expected_recall=exp_recall,
            tradeoff_explanation=explanation,
            should_auto_apply=False,       # NEVER auto-apply
            requires_human_review=True,    # ALWAYS require human review
        ))

    return recs


def recommend_active_pursuit_threshold(
    cases: list[HistoricalMAOutcome],
    operating_mode: OperatingMode,
    *,
    cost_matrix: Optional[dict[str, float]] = None,
) -> ThresholdRecommendation:
    """Single-threshold helper for Active Pursuit threshold."""
    recs = generate_threshold_recommendations(
        cases, operating_mode,
        cost_matrix=cost_matrix,
        threshold_names=["active_pursuit"],
    )
    return recs[0]


def optimize_thresholds(
    cases: list[HistoricalMAOutcome],
    operating_mode: OperatingMode,
    *,
    cost_matrix: Optional[dict[str, float]] = None,
) -> list[ThresholdRecommendation]:
    """Main entry point for threshold optimization.

    Wrapper around generate_threshold_recommendations.
    """
    return generate_threshold_recommendations(cases, operating_mode, cost_matrix=cost_matrix)
