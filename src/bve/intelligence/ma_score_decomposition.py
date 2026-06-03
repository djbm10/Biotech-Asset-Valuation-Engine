"""
M&A Score Decomposition — Attribution / Explainability Layer (Block 21).

IMPORTANT: This module is an ATTRIBUTION layer, not a new scoring model.
It explains how an existing Layer 3/5 score was constructed by mapping upstream
inputs to 8 conceptual driver buckets.  The decomposition does NOT produce new
scores, reorder results, or modify probabilities.

Design principles
-----------------
- ``_EXPLANATORY_DRIVER_WEIGHTS`` maps 8 conceptual buckets to attribution
  weights that approximate the relative contribution of each signal domain.
  Weights are labelled "approximate attribution" — they are NOT independently
  calibrated regression coefficients.
- ``ScoreComposition`` is the output artifact.  It is attached to
  ``Layer5Output.score_composition`` when ``Layer5Inputs.include_decomposition=True``.
- All DriverComponent.notes fields contain the word "approximate" to make the
  explainability-not-calibration distinction explicit in every output.
- Gate triggers are reproduced from upstream active_gate_ids without modification.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Attribution weight table
# ---------------------------------------------------------------------------

_EXPLANATORY_DRIVER_WEIGHTS: dict[str, float] = {
    "target_quality":        0.25,
    "buyer_mandate":         0.15,
    "strategic_fit":         0.15,
    "strategic_urgency":     0.10,
    "deal_momentum":         0.10,
    "seller_readiness":      0.15,
    "transaction_realism":   0.05,
    "information_readiness": 0.05,
}
# Invariant: sum == 1.0
assert abs(sum(_EXPLANATORY_DRIVER_WEIGHTS.values()) - 1.0) < 1e-9, (
    "_EXPLANATORY_DRIVER_WEIGHTS must sum to 1.0"
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DriverComponent:
    """Attribution of one driver bucket to the composite score.

    All fields are descriptive; ``contribution`` is an *approximate* attribution,
    not a model-estimated coefficient.

    Attributes
    ----------
    driver:
        Key name matching a bucket in ``_EXPLANATORY_DRIVER_WEIGHTS``.
    label:
        Human-readable bucket label.
    raw_score:
        Normalised upstream signal value fed into this bucket (0–1).
    weight:
        Attribution weight from ``_EXPLANATORY_DRIVER_WEIGHTS``.
    contribution:
        ``weight × raw_score`` — approximate share of the final score
        attributable to this bucket.
    data_available:
        False when the underlying signal was missing or defaulted.
    source_layer:
        Which layer produced the primary input (e.g. "Layer 1", "Layer 2").
    notes:
        Free-text clarification.  Always contains the word "approximate"
        to distinguish attribution from calibrated coefficients.
    """
    driver: str
    label: str
    raw_score: float
    weight: float
    contribution: float
    data_available: bool
    source_layer: str
    notes: str


@dataclass
class GateSummary:
    """Record of one gate trigger and its effect on the score.

    Attributes
    ----------
    gate_id:
        Short gate identifier (e.g. "G1", "G5").
    description:
        Plain-English description of the gate condition.
    triggered:
        True when this gate fired on the scored target.
    effect:
        One of: "pass" | "score_cap:<value>" | "hard_fail" | "no_effect"
    """
    gate_id: str
    description: str
    triggered: bool
    effect: str


@dataclass
class ScoreComposition:
    """Full attribution breakdown of a Layer 5 M&A score.

    This is an explainability artifact — it does not alter any score.

    Attributes
    ----------
    target_name:
        Name of the scored target company.
    acquirer_id:
        Optional acquirer identifier.
    final_score:
        The Layer 3/5 score being explained (unchanged).
    weighted_sum:
        Sum of component contributions (approximate total attribution).
    components:
        One DriverComponent per bucket in _EXPLANATORY_DRIVER_WEIGHTS.
    gate_summary:
        List of GateSummary records for gates that were evaluated.
    calibration_shrinkage_weights:
        (base_rate_weight, logistic_weight, bucket_weight) used in Layer 5.
    calibration_base_rate:
        TA/stage historical base rate used in shrinkage blend.
    calibration_comparable_rate:
        Comparable-bucket historical rate used in shrinkage blend.
    calibration_comparable_rate_source:
        'segment_report' or 'fallback'.
    n_comparable_observations:
        Sample size behind comparable_bucket_rate.
    score_floor_applied:
        True if a floor was applied to the final score.
    score_cap_applied:
        True if a cap was applied to the final score.
    cap_value:
        The cap threshold, when score_cap_applied is True.
    """
    target_name: str
    acquirer_id: Optional[str]
    final_score: float
    weighted_sum: float
    components: list[DriverComponent]
    gate_summary: list[GateSummary]
    calibration_shrinkage_weights: tuple[float, float, float]
    calibration_base_rate: float
    calibration_comparable_rate: float
    calibration_comparable_rate_source: str
    n_comparable_observations: int
    score_floor_applied: bool
    score_cap_applied: bool
    cap_value: Optional[float] = None


# ---------------------------------------------------------------------------
# Gate description lookup
# ---------------------------------------------------------------------------

_GATE_DESCRIPTIONS: dict[str, str] = {
    "G1": "Minimum BD score threshold",
    "G2": "Asset quality floor",
    "G3": "Seller willingness minimum",
    "G4": "Strategic priority minimum",
    "G5": "Transaction readiness gate",
    "G6": "Data confidence minimum",
    "G7": "Acquirer financial capacity gate",
    "G8": "Integration complexity cap",
}


# ---------------------------------------------------------------------------
# Driver signal mapping
# ---------------------------------------------------------------------------

_DRIVER_SIGNAL_MAP: dict[str, dict] = {
    "target_quality": {
        "label": "Target Quality",
        "source_layer": "Layer 1",
        "signal_key": "asset_quality",
    },
    "buyer_mandate": {
        "label": "Buyer Mandate",
        "source_layer": "Layer 2",
        "signal_key": "strategic_priority",
    },
    "strategic_fit": {
        "label": "Strategic Fit",
        "source_layer": "Layer 2",
        "signal_key": "strategic_priority",
    },
    "strategic_urgency": {
        "label": "Strategic Urgency",
        "source_layer": "Layer 3",
        "signal_key": "active_driver_bucket_count",
        "normalise": True,
    },
    "deal_momentum": {
        "label": "Deal Momentum",
        "source_layer": "Layer 3",
        "signal_key": "transaction_probability",
    },
    "seller_readiness": {
        "label": "Seller Readiness",
        "source_layer": "Layer 1",
        "signal_key": "seller_willingness",
    },
    "transaction_realism": {
        "label": "Transaction Realism",
        "source_layer": "Layer 3",
        "signal_key": "rank_score",
    },
    "information_readiness": {
        "label": "Information Readiness",
        "source_layer": "Layer 4",
        "signal_key": "data_confidence_score",
    },
}

_MAX_ACTIVE_DRIVER_BUCKETS: int = 8  # normalisation denominator


def _extract_raw_score(driver: str, kwargs: dict) -> tuple[float, bool]:
    """Extract the raw score for a driver bucket from the inputs dict.

    Returns (score, data_available).
    """
    meta = _DRIVER_SIGNAL_MAP[driver]
    key = meta["signal_key"]
    normalise = meta.get("normalise", False)
    val = kwargs.get(key)
    if val is None:
        return 0.5, False  # neutral default when data absent
    if normalise:
        return round(min(1.0, float(val) / _MAX_ACTIVE_DRIVER_BUCKETS), 4), True
    return round(float(val), 4), True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_score_decomposition(
    *,
    target_name: str,
    acquirer_id: Optional[str],
    final_score: float,
    rank_score: float,
    asset_quality: float,
    seller_willingness: float,
    strategic_priority: float,
    transaction_probability: float,
    active_driver_bucket_count: int,
    active_gate_ids: list[str],
    watchlist_class: str,
    data_confidence_score: float,
    base_rate: float,
    comparable_bucket_rate: float,
    comparable_bucket_rate_source: str,
    n_comparable_observations: int,
    shrinkage_weights: tuple[float, float, float],
    calibration_base_rate: float,
    calibration_comparable_rate: float,
    **_ignored,
) -> ScoreComposition:
    """Compute attribution-only score decomposition for an M&A scoring result.

    Parameters
    ----------
    target_name, acquirer_id:
        Target/acquirer identifiers.
    final_score:
        The existing final score to explain (NOT recomputed here).
    rank_score, asset_quality, seller_willingness, strategic_priority,
    transaction_probability, active_driver_bucket_count:
        Upstream signal values from Layers 1–3.
    active_gate_ids:
        Gate IDs that triggered during scoring.
    watchlist_class, data_confidence_score:
        Layer 4 metadata.
    base_rate, comparable_bucket_rate, comparable_bucket_rate_source,
    n_comparable_observations, shrinkage_weights:
        Calibration parameters from Layer 5.
    calibration_base_rate, calibration_comparable_rate:
        Values used in the shrinkage blend.

    Returns
    -------
    ScoreComposition
        Attribution breakdown; does not modify final_score or any probability.
    """
    signal_lookup = dict(
        asset_quality=asset_quality,
        seller_willingness=seller_willingness,
        strategic_priority=strategic_priority,
        transaction_probability=transaction_probability,
        active_driver_bucket_count=active_driver_bucket_count,
        rank_score=rank_score,
        data_confidence_score=data_confidence_score,
    )

    components: list[DriverComponent] = []
    for driver, weight in _EXPLANATORY_DRIVER_WEIGHTS.items():
        raw_score, data_avail = _extract_raw_score(driver, signal_lookup)
        contribution = round(weight * raw_score, 4)
        meta = _DRIVER_SIGNAL_MAP[driver]
        components.append(DriverComponent(
            driver=driver,
            label=meta["label"],
            raw_score=raw_score,
            weight=weight,
            contribution=contribution,
            data_available=data_avail,
            source_layer=meta["source_layer"],
            notes=(
                "Approximate attribution — weight reflects signal domain importance, "
                "not a calibrated regression coefficient."
            ),
        ))

    weighted_sum = round(sum(c.contribution for c in components), 4)

    # Gate summary
    gate_summary: list[GateSummary] = []
    for gate_id in active_gate_ids:
        desc = _GATE_DESCRIPTIONS.get(gate_id, f"Gate {gate_id}")
        gate_summary.append(GateSummary(
            gate_id=gate_id,
            description=desc,
            triggered=True,
            effect="score_cap:0.5" if gate_id in ("G4", "G5", "G6") else "pass",
        ))

    return ScoreComposition(
        target_name=target_name,
        acquirer_id=acquirer_id,
        final_score=final_score,
        weighted_sum=weighted_sum,
        components=components,
        gate_summary=gate_summary,
        calibration_shrinkage_weights=shrinkage_weights,
        calibration_base_rate=calibration_base_rate,
        calibration_comparable_rate=calibration_comparable_rate,
        calibration_comparable_rate_source=comparable_bucket_rate_source,
        n_comparable_observations=n_comparable_observations,
        score_floor_applied=False,
        score_cap_applied=bool(active_gate_ids),
        cap_value=None,
    )
