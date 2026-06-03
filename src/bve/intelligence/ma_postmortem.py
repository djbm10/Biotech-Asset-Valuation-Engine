"""Layer 5 — 5F: Postmortem & Error Attribution Engine.

Learns from resolved cases.

For every resolved case, creates a PostmortemRecord with:
  - Initial layer scores captured at prediction time
  - Actual outcome
  - Prediction error classification
  - Root cause narrative
  - Model update recommendations

Layer 5 recommends model updates but does NOT automatically rewrite
layer weights or thresholds unless explicitly configured.
"""
from __future__ import annotations

from typing import Optional

from bve.intelligence.ma_calibration_models import (
    ErrorType,
    HistoricalMAOutcome,
    OutcomeType,
    PostmortemRecord,
)

# Outcome types that should have been caught (false negatives)
_FALSE_NEGATIVE_OUTCOMES = frozenset({
    OutcomeType.FULL_ACQUISITION_ANNOUNCED,
    OutcomeType.FULL_ACQUISITION_CLOSED,
    OutcomeType.ASSET_ACQUISITION,
    OutcomeType.CVR_HEAVY_ACQUISITION,
    OutcomeType.STRUCTURED_ACQUISITION_WITH_MILESTONES,
    OutcomeType.FALSE_NEGATIVE_TRANSACTION_OCCURRED,
})

# Outcome types that indicate model over-optimism (false positives)
_FALSE_POSITIVE_OUTCOMES = frozenset({
    OutcomeType.REMAINED_INDEPENDENT_PERFORMED_WELL,
    OutcomeType.REMAINED_INDEPENDENT_FAILED,
    OutcomeType.FALSE_POSITIVE_NO_TRANSACTION,
    OutcomeType.ACQUIRER_FILLED_GAP_ELSEWHERE,
})

# Route classes that represent high-priority predictions
_HIGH_PRIORITY_ROUTES = frozenset({
    "active_pursuit",
    "high_priority_diligence",
    "partner_or_license_candidate",
})


def classify_prediction_error(
    case: HistoricalMAOutcome,
    *,
    bd_action_score: Optional[float] = None,
    layer4_route: Optional[str] = None,
    predicted_acquisition: bool = False,
) -> tuple[ErrorType, list[ErrorType], str]:
    """Classify the primary and secondary error types for a resolved case.

    Args:
        case: The historical case with known outcome.
        bd_action_score: The BD action score at prediction time.
        layer4_route: The Layer 4 route at prediction time.
        predicted_acquisition: Whether the model predicted an acquisition.

    Returns:
        (primary_error_type, secondary_error_types, root_cause_description)
    """
    outcome = case.outcome_type
    secondary: list[ErrorType] = []

    # -----------------------------------------------------------------------
    # False Negative: model missed a deal that happened
    # -----------------------------------------------------------------------
    if outcome in _FALSE_NEGATIVE_OUTCOMES:
        if layer4_route in _HIGH_PRIORITY_ROUTES and not predicted_acquisition:
            primary = ErrorType.FALSE_NEGATIVE_WRONG_ROUTE
            root = (
                "Opportunity routed but acquisition probability underestimated. "
                "Review Layer 3 pair feasibility and Layer 2 BD action weights."
            )
        else:
            # Determine why it was missed
            l1 = case.layer1_snapshot.get("layer1_score")
            if l1 is not None and float(l1) < 0.50:
                primary = ErrorType.FALSE_NEGATIVE_UNDERESTIMATED_SCARCITY
                root = (
                    f"Layer 1 score={l1:.2f} below typical threshold at prediction time. "
                    "Asset scarcity or quality underestimated."
                )
            elif case.target_features.distress_level in ("low", None):
                primary = ErrorType.FALSE_NEGATIVE_HIDDEN_BUYER
                root = (
                    "No distress signal; acquisition driven by hidden buyer thesis "
                    "not captured in acquirer mapping."
                )
            else:
                primary = ErrorType.FALSE_NEGATIVE_UNDERESTIMATED_BUYER_URGENCY
                root = (
                    "Buyer urgency (pipeline gap, LoE pressure) was underestimated "
                    "at prediction time."
                )
            secondary.append(ErrorType.FALSE_NEGATIVE_WRONG_STRUCTURE)

        return primary, secondary, root

    # -----------------------------------------------------------------------
    # False Positive: model predicted deal, none occurred
    # -----------------------------------------------------------------------
    if outcome in _FALSE_POSITIVE_OUTCOMES or (
        predicted_acquisition
        and outcome in (
            OutcomeType.DISTRESSED_FINANCING,
            OutcomeType.CLINICAL_FAILURE,
            OutcomeType.STRATEGIC_REVIEW_NO_DEAL,
            OutcomeType.RUMORED_PROCESS_NO_DEAL,
        )
    ):
        # Diagnose which layer drove the error
        l3_cap = case.layer3_snapshot.get("pair_level_cap") if case.layer3_snapshot else None
        affordability = (
            case.layer3_snapshot.get("affordability_realism")
            if case.layer3_snapshot
            else None
        )
        if outcome == OutcomeType.DISTRESSED_FINANCING:
            primary = ErrorType.FALSE_POSITIVE_TRANSACTION_MOMENTUM
            secondary = [ErrorType.FALSE_POSITIVE_SELLER_WILLINGNESS]
            root = (
                "Overweighted financing pressure; target raised capital and remained "
                "independent. Reduce transaction_momentum contribution unless "
                "capital-market-access risk is also high."
            )
        elif outcome in (OutcomeType.STRATEGIC_REVIEW_NO_DEAL, OutcomeType.RUMORED_PROCESS_NO_DEAL):
            primary = ErrorType.FALSE_POSITIVE_SELLER_WILLINGNESS
            secondary = [ErrorType.FALSE_POSITIVE_TRANSACTION_MOMENTUM]
            root = (
                "Strategic review did not lead to a deal. Seller willingness or "
                "valuation gap was the gating factor."
            )
        elif outcome == OutcomeType.CLINICAL_FAILURE:
            primary = ErrorType.FALSE_POSITIVE_ASSET_QUALITY
            secondary = [ErrorType.TIMING_ERROR]
            root = (
                "Clinical failure occurred; asset quality was overestimated at "
                "prediction time."
            )
        elif affordability is not None and float(affordability) < 0.50:
            primary = ErrorType.FALSE_POSITIVE_AFFORDABILITY
            root = "Deal was not affordable; affordability cap should have blocked routing."
        elif l3_cap is not None and float(l3_cap) < 0.60:
            primary = ErrorType.FALSE_POSITIVE_RIGHTS_CONTROL
            root = "Pair-level cap from rights/control blocked deal execution."
        else:
            primary = ErrorType.FALSE_POSITIVE_BUYER_FIT
            secondary = [ErrorType.FALSE_POSITIVE_MARKET_HYPE]
            root = (
                "No deal occurred despite high BD action score. "
                "Buyer fit or market hype may have been overestimated."
            )

        return primary, secondary, root

    # -----------------------------------------------------------------------
    # Timing error: deal happened but outside predicted window
    # -----------------------------------------------------------------------
    if case.time_to_outcome_days is not None and not case.labels.acquired_within_12m:
        return (
            ErrorType.TIMING_ERROR,
            [],
            f"Deal occurred but took {case.time_to_outcome_days} days — "
            "outside the predicted 12-month window.",
        )

    # -----------------------------------------------------------------------
    # Structure error: deal happened but wrong structure
    # -----------------------------------------------------------------------
    if case.layer4_snapshot and case.deal_structure:
        predicted_struct = case.layer4_snapshot.get("recommended_deal_structure")
        if predicted_struct and predicted_struct != case.deal_structure:
            return (
                ErrorType.STRUCTURE_ERROR,
                [],
                f"Predicted structure={predicted_struct}, actual={case.deal_structure}. "
                "Deal structure recommendation calibration needed.",
            )

    # Default: data staleness or unknown
    return (
        ErrorType.UNKNOWN_ERROR,
        [],
        "Outcome does not clearly map to a known error taxonomy. "
        "Manual review recommended.",
    )


def attribute_error_root_cause(
    case: HistoricalMAOutcome,
    primary_error: ErrorType,
    *,
    bd_action_score: Optional[float] = None,
) -> tuple[str, bool, bool]:
    """Attribute root cause and recommend whether to update thresholds/weights.

    Returns:
        (root_cause, should_update_thresholds, should_update_weights)
    """
    update_thresholds = primary_error in {
        ErrorType.THRESHOLD_ERROR,
        ErrorType.CALIBRATION_ERROR,
        ErrorType.FALSE_POSITIVE_TRANSACTION_MOMENTUM,
    }
    update_weights = primary_error in {
        ErrorType.FALSE_POSITIVE_ASSET_QUALITY,
        ErrorType.FALSE_POSITIVE_BUYER_FIT,
        ErrorType.FALSE_NEGATIVE_UNDERESTIMATED_SCARCITY,
        ErrorType.FALSE_NEGATIVE_UNDERESTIMATED_BUYER_URGENCY,
        ErrorType.CALIBRATION_ERROR,
    }

    cause_map = {
        ErrorType.FALSE_POSITIVE_TRANSACTION_MOMENTUM: (
            "Overweighted transaction momentum; financing pressure alone is "
            "not sufficient for acquisition prediction."
        ),
        ErrorType.FALSE_POSITIVE_SELLER_WILLINGNESS: (
            "Seller willingness signals were too optimistic; strategic review "
            "announcements are noisy predictors."
        ),
        ErrorType.FALSE_POSITIVE_ASSET_QUALITY: (
            "Clinical data quality was overestimated; consider requiring "
            "more conservative asset quality scoring."
        ),
        ErrorType.FALSE_NEGATIVE_HIDDEN_BUYER: (
            "Buyer was not in the top-acquirer list; acquirer mapping needs "
            "broader universe coverage."
        ),
        ErrorType.TIMING_ERROR: (
            "Deal timing was outside the predicted window; consider horizon "
            "calibration at 18m and 24m."
        ),
    }

    root = cause_map.get(
        primary_error,
        f"Primary error type {primary_error.value}; manual review recommended.",
    )
    return root, update_thresholds, update_weights


def create_postmortem(
    case: HistoricalMAOutcome,
    *,
    layer4_route: Optional[str] = None,
    predicted_probabilities: Optional[dict] = None,
    predicted_acquisition: bool = False,
) -> PostmortemRecord:
    """Create a PostmortemRecord for a resolved case.

    Args:
        case: The historical case with known outcome.
        layer4_route: Layer 4 route at prediction time.
        predicted_probabilities: Dict of predicted probabilities at prediction time.
        predicted_acquisition: Whether the model predicted an acquisition.

    Returns:
        PostmortemRecord with full attribution.
    """
    bd_score = case.layer2_snapshot.get("bd_action_score")
    l1_score = case.layer1_snapshot.get("layer1_score")
    l2_score = case.layer2_snapshot.get("layer2_score") or bd_score
    l3_score = (
        case.layer3_snapshot.get("adjusted_score")
        if case.layer3_snapshot
        else None
    )

    primary, secondary, auto_root = classify_prediction_error(
        case,
        bd_action_score=bd_score,
        layer4_route=layer4_route,
        predicted_acquisition=predicted_acquisition,
    )

    root, update_thresh, update_weights = attribute_error_root_cause(
        case, primary, bd_action_score=bd_score
    )

    # Combine auto-generated and attribute-based root causes
    full_root = f"{auto_root} {root}".strip()

    # Prediction error for continuous probabilities
    pred_probs = predicted_probabilities or {}
    pred_p = pred_probs.get("p_full_acquisition_12m") or pred_probs.get("p_takeout_12m")
    actual_p = 1.0 if case.labels.acquired_within_12m else 0.0
    pred_error = round(abs(actual_p - float(pred_p)), 6) if pred_p is not None else None

    rec_update = (
        f"Error type: {primary.value}. "
        f"{'Recommend threshold review. ' if update_thresh else ''}"
        f"{'Recommend weight recalibration. ' if update_weights else ''}"
        "Manual review required before applying any changes."
    )

    return PostmortemRecord(
        target_id=case.target_id,
        acquirer_id=case.acquirer_id,
        prediction_date=case.prediction_date,
        outcome_date=case.outcome_date,
        initial_layer0_snapshot=dict(case.layer0_snapshot),
        initial_layer1_score=(float(l1_score) if l1_score is not None else None),
        initial_layer2_score=(float(l2_score) if l2_score is not None else None),
        initial_layer3_score=(float(l3_score) if l3_score is not None else None),
        initial_layer4_route=layer4_route or case.layer4_snapshot.get("route_class") if case.layer4_snapshot else None,
        predicted_probabilities=pred_probs,
        actual_outcome=case.outcome_type,
        time_to_outcome_days=case.time_to_outcome_days,
        prediction_error=pred_error,
        primary_error_type=primary,
        secondary_error_types=secondary,
        root_cause=full_root,
        recommended_model_update=rec_update,
        should_update_thresholds=update_thresh,
        should_update_weights=update_weights,
        data_quality_issue=not case.leakage_checks_passed,
        notes=list(case.leakage_warnings),
    )


def write_postmortem_ledger(
    postmortems: list[PostmortemRecord],
    path: str,
) -> None:
    """Append postmortems to a JSONL file (one record per line)."""
    import json
    from pathlib import Path
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("a", encoding="utf-8") as f:
        for pm in postmortems:
            f.write(json.dumps(pm.model_dump(mode="json")) + "\n")
