"""Three-model M&A scoring decomposition.

Separates the composite M&A score into three independently interpretable
sub-scores to reduce saturation and improve false-positive diagnosis.

This module is ANALYSIS ONLY — it does not change model training data,
calibration thresholds, or the main `MAProbabilityScanner` ranking order.
The three sub-scores are additive diagnostics attached to each row.
"""
from __future__ import annotations

import math
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Saturation diagnostics helpers
# ---------------------------------------------------------------------------

SATURATION_THRESHOLD = 0.95  # score considered "at cap"
_SATURATION_PENALTY_PER_EXTRA_MAX = 0.12  # reduce 12% per sub-score beyond 1 at cap


def _gini(values: list[float]) -> float:
    """Gini coefficient for a list of non-negative floats."""
    if not values:
        return 0.0
    n = len(values)
    s = sorted(values)
    cumsum = 0.0
    cumulative_sum = sum(s)
    if cumulative_sum == 0.0:
        return 0.0
    weighted_rank_sum = 0.0
    for i, v in enumerate(s):
        cumsum += v
        weighted_rank_sum += (2 * (i + 1) - n - 1) * v
    return weighted_rank_sum / (n * cumulative_sum)


def compute_score_saturation_diagnostics(scores: list[float]) -> dict[str, float]:
    """Distribution statistics for a list of composite scores.

    Returns mean, median, p10, p90, pct_at_cap, entropy (normalised), gini.
    """
    if not scores:
        return {
            "mean": 0.0,
            "median": 0.0,
            "p10": 0.0,
            "p90": 0.0,
            "pct_at_cap": 0.0,
            "entropy": 0.0,
            "gini": 0.0,
            "n": 0,
        }
    n = len(scores)
    sorted_s = sorted(scores)
    mean = sum(sorted_s) / n
    median = sorted_s[n // 2] if n % 2 == 1 else (sorted_s[n // 2 - 1] + sorted_s[n // 2]) / 2.0
    p10 = sorted_s[max(0, int(0.10 * n) - 1)]
    p90 = sorted_s[min(n - 1, int(0.90 * n))]
    pct_at_cap = sum(1 for s in scores if s >= SATURATION_THRESHOLD) / n

    # Normalised entropy over 10 equal-width bins
    bin_size = 0.10
    bins = [0] * 10
    for s in scores:
        idx = min(int(s / bin_size), 9)
        bins[idx] += 1
    probs = [b / n for b in bins if b > 0]
    entropy_raw = -sum(p * math.log(p) for p in probs)
    entropy_max = math.log(10)
    entropy_norm = entropy_raw / entropy_max if entropy_max > 0 else 0.0

    return {
        "mean": round(mean, 6),
        "median": round(median, 6),
        "p10": round(p10, 6),
        "p90": round(p90, 6),
        "pct_at_cap": round(pct_at_cap, 6),
        "entropy": round(entropy_norm, 6),
        "gini": round(_gini(sorted_s), 6),
        "n": n,
    }


def apply_saturation_penalty(
    raw_score: float,
    *,
    sub_scores: list[float],
) -> float:
    """Reduce `raw_score` when multiple sub-scores are simultaneously at cap.

    The first sub-score at or above SATURATION_THRESHOLD is not penalised.
    Each additional one reduces the score by SATURATION_PENALTY_PER_EXTRA_MAX.

    This keeps scores below 1.0 unless ALL signals are at maximum with
    distinct evidence (rare in practice).
    """
    n_at_cap = sum(1 for s in sub_scores if s >= SATURATION_THRESHOLD)
    if n_at_cap <= 1:
        return min(max(raw_score, 0.0), 1.0)
    excess = n_at_cap - 1
    penalty = excess * _SATURATION_PENALTY_PER_EXTRA_MAX
    penalised = raw_score * max(0.0, 1.0 - penalty)
    return round(min(max(penalised, 0.0), 1.0), 6)


# ---------------------------------------------------------------------------
# Sub-score models
# ---------------------------------------------------------------------------

class TargetAttractivenessScore(BaseModel):
    """How attractive the target asset is for acquisition, independent of any one buyer.

    Components:
    - de_risking_stage: clinical stage advancement (Phase 3 / NDA = 1.0)
    - valuation_discount: current EV vs model rNPV discount
    - scarcity: scarcity of same-indication late-stage assets
    - peak_sales_signal: log-normalised expected peak revenue
    """

    score: float = Field(ge=0.0, le=1.0)
    de_risking_stage: float = Field(ge=0.0, le=1.0)
    valuation_discount: float = Field(ge=0.0, le=1.0)
    scarcity: float = Field(ge=0.0, le=1.0)
    peak_sales_signal: float = Field(ge=0.0, le=1.0)
    diagnostics: dict[str, float] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Financing-pressure reason codes
# ---------------------------------------------------------------------------

# Codes attached when financing pressure gate is applied.
# These are diagnostic reason codes, not model labels.
FINANCING_REASON_NOT_PRESSURED = "financing_not_pressured"
FINANCING_REASON_LONG_RUNWAY = "long_runway"
FINANCING_REASON_NO_NEAR_TERM_NEED = "no_near_term_funding_need"
FINANCING_REASON_STANDALONE_VIABLE = "standalone_viability_high"
FINANCING_REASON_NO_BUYER_URGENCY = "no_buyer_urgency"
FINANCING_REASON_RECENT_FINANCING = "recent_financing"
FINANCING_REASON_NO_ACTIVIST_PRESSURE = "no_ownership_activist_pressure"

# Threshold below which financing pressure is considered low (weak pressure)
_LOW_FINANCING_PRESSURE_THRESHOLD = 0.25
# Cap applied to deal_likelihood_score when pressure is low and no override signal
_LOW_PRESSURE_SCORE_CAP = 0.40
# Scarcity or activist signal that can override the gate (threshold)
_OVERRIDE_SCARCITY_THRESHOLD = 0.75
# External deal activity below this → no_buyer_urgency code
_LOW_EXTERNAL_ACTIVITY_THRESHOLD = 0.20
# Days since last financing below this → recent_financing code
_RECENT_FINANCING_DAYS = 180
# Composite score cap when DL financing gate fires (strategic fit alone insufficient)
COMPOSITE_MAX_WITH_DL_GATE = 0.65


class DealLikelihoodScore(BaseModel):
    """How likely the target is to transact in the near term.

    Components:
    - financing_pressure: cash runway / capital vulnerability
    - external_deal_activity: same-space deal signals that pressure standalone path
    - insider_board_signals: management / board change signals
    - catalyst_proximity: inverse distance to next catalyst event

    Gate:
    - When financing_pressure is below _LOW_FINANCING_PRESSURE_THRESHOLD
      AND no strong scarcity/activist override signal is present,
      the final score is capped at _LOW_PRESSURE_SCORE_CAP.
      Reason codes explain why the gate was applied.
    """

    score: float = Field(ge=0.0, le=1.0)
    financing_pressure: float = Field(ge=0.0, le=1.0)
    external_deal_activity: float = Field(ge=0.0, le=1.0)
    insider_board_signals: float = Field(ge=0.0, le=1.0)
    catalyst_proximity: float = Field(ge=0.0, le=1.0)
    # Reason codes populated when financing pressure gate fires
    financing_reason_codes: list[str] = Field(default_factory=list)
    # True when the low-pressure gate was applied
    financing_gate_applied: bool = False
    diagnostics: dict[str, float] = Field(default_factory=dict)


class AcquirerFitDecomposed(BaseModel):
    """How well a specific acquirer fits this target.

    Components:
    - ta_modality_fit: therapeutic area + modality alignment
    - pipeline_gap_alignment: gap urgency and sub-area specificity
    - deal_affordability: budget headroom and EV vs deal history
    - existing_partnership_bonus: partnership / option agreement bonus
    """

    score: float = Field(ge=0.0, le=1.0)
    ta_modality_fit: float = Field(ge=0.0, le=1.0)
    pipeline_gap_alignment: float = Field(ge=0.0, le=1.0)
    deal_affordability: float = Field(ge=0.0, le=1.0)
    existing_partnership_bonus: float = Field(ge=0.0, le=1.0)
    diagnostics: dict[str, float] = Field(default_factory=dict)


# Weights for each decomposed model's contribution to the composite
TARGET_ATTRACTIVENESS_WEIGHT = 0.35
DEAL_LIKELIHOOD_WEIGHT = 0.25
ACQUIRER_FIT_WEIGHT = 0.40

# Weights within TargetAttractivenessScore
_TA_WEIGHTS = {
    "de_risking_stage": 0.35,
    "valuation_discount": 0.30,
    "scarcity": 0.20,
    "peak_sales_signal": 0.15,
}

# Weights within DealLikelihoodScore
_DL_WEIGHTS = {
    "financing_pressure": 0.40,
    "external_deal_activity": 0.25,
    "insider_board_signals": 0.20,
    "catalyst_proximity": 0.15,
}

# Weights within AcquirerFitDecomposed
_AF_WEIGHTS = {
    "ta_modality_fit": 0.40,
    "pipeline_gap_alignment": 0.30,
    "deal_affordability": 0.20,
    "existing_partnership_bonus": 0.10,
}

# Maximum peak_sales used for log-normalisation ($10B)
_PEAK_SALES_LOG_MAX = math.log1p(10_000.0)


def _log_normalise_peak_sales(peak_sales_millions: Optional[float]) -> float:
    """Map peak sales to [0, 1] using log scale capped at $10B."""
    if peak_sales_millions is None or peak_sales_millions <= 0:
        return 0.30  # neutral when missing
    log_val = math.log1p(max(float(peak_sales_millions), 0.0))
    return round(min(log_val / _PEAK_SALES_LOG_MAX, 1.0), 6)


def apply_financing_pressure_gate(
    raw_score: float,
    *,
    financing_pressure_score: float,
    scarcity_score: float = 0.0,
    activist_signal_score: float = 0.0,
    cash_runway_quarters: Optional[float] = None,
    has_near_term_catalyst: bool = False,
    external_deal_activity_score: float = 0.0,
    days_since_last_financing: Optional[int] = None,
) -> tuple[float, bool, list[str]]:
    """Apply low-pressure cap to deal likelihood score.

    When financing pressure is low (company is well-funded with no near-term
    capital need), deal likelihood is capped unless a strong scarcity or
    activist/ownership signal overrides the gate.

    Strategic fit alone cannot create high deal likelihood — when the financing
    gate fires, the DL score is capped at _LOW_PRESSURE_SCORE_CAP.

    Returns (capped_score, gate_applied, reason_codes).

    Args:
        raw_score: The uncapped deal_likelihood score.
        financing_pressure_score: Score [0, 1] reflecting cash runway pressure /
            capital vulnerability. Low = company is well-funded.
        scarcity_score: [0, 1] scarcity of this asset class; high scarcity can
            override the low-pressure gate.
        activist_signal_score: [0, 1] insider / activist / board-change signal.
        cash_runway_quarters: Quarters of runway (if known); >= 8 quarters (2 years)
            contributes to long_runway code.
        has_near_term_catalyst: True if a catalyst is within 90 days (can partially
            offset low financing pressure).
        external_deal_activity_score: [0, 1] score reflecting external deal pressure
            in the same therapeutic area / modality.
        days_since_last_financing: Days since last capital raise; < 180 days indicates
            recent financing that reduces near-term capital pressure.
    """
    reason_codes: list[str] = []

    pressure_is_low = financing_pressure_score < _LOW_FINANCING_PRESSURE_THRESHOLD
    override_active = (
        scarcity_score >= _OVERRIDE_SCARCITY_THRESHOLD
        or activist_signal_score >= _OVERRIDE_SCARCITY_THRESHOLD
    )

    if not pressure_is_low:
        return min(max(raw_score, 0.0), 1.0), False, reason_codes

    # Pressure is low — build reason codes explaining why deal is unlikely
    reason_codes.append(FINANCING_REASON_NOT_PRESSURED)
    if cash_runway_quarters is not None and cash_runway_quarters >= 8.0:
        reason_codes.append(FINANCING_REASON_LONG_RUNWAY)
    if not has_near_term_catalyst:
        reason_codes.append(FINANCING_REASON_NO_NEAR_TERM_NEED)
    if financing_pressure_score < 0.10:
        reason_codes.append(FINANCING_REASON_STANDALONE_VIABLE)
    if external_deal_activity_score < _LOW_EXTERNAL_ACTIVITY_THRESHOLD:
        reason_codes.append(FINANCING_REASON_NO_BUYER_URGENCY)
    if days_since_last_financing is not None and days_since_last_financing < _RECENT_FINANCING_DAYS:
        reason_codes.append(FINANCING_REASON_RECENT_FINANCING)
    if activist_signal_score < 0.20:
        reason_codes.append(FINANCING_REASON_NO_ACTIVIST_PRESSURE)

    if override_active:
        # Strong scarcity or activist signal overrides the cap
        return min(max(raw_score, 0.0), 1.0), False, reason_codes

    # Apply cap
    capped = min(raw_score, _LOW_PRESSURE_SCORE_CAP)
    return round(min(max(capped, 0.0), 1.0), 6), True, reason_codes


def _catalyst_proximity_score(days_to_catalyst: Optional[int]) -> float:
    """Map days-to-next-catalyst to [0, 1]; 0 days = 1.0, >365 days = 0.0."""
    if days_to_catalyst is None or days_to_catalyst < 0:
        return 0.0
    if days_to_catalyst == 0:
        return 1.0
    # Exponential decay: score = exp(-days/90); 90-day half-life
    return round(min(math.exp(-days_to_catalyst / 90.0), 1.0), 6)


def compute_target_attractiveness(
    *,
    de_risking_stage_score: float,
    valuation_discount_score: float,
    scarcity_score: float,
    peak_sales_millions: Optional[float],
) -> TargetAttractivenessScore:
    """Compute TargetAttractivenessScore from existing sub-scores."""
    ps_signal = _log_normalise_peak_sales(peak_sales_millions)

    raw = (
        de_risking_stage_score * _TA_WEIGHTS["de_risking_stage"]
        + valuation_discount_score * _TA_WEIGHTS["valuation_discount"]
        + scarcity_score * _TA_WEIGHTS["scarcity"]
        + ps_signal * _TA_WEIGHTS["peak_sales_signal"]
    )
    sub = [de_risking_stage_score, valuation_discount_score, scarcity_score, ps_signal]
    score = apply_saturation_penalty(raw, sub_scores=sub)

    return TargetAttractivenessScore(
        score=round(score, 6),
        de_risking_stage=round(de_risking_stage_score, 6),
        valuation_discount=round(valuation_discount_score, 6),
        scarcity=round(scarcity_score, 6),
        peak_sales_signal=round(ps_signal, 6),
        diagnostics={
            "n_at_cap": float(sum(1 for s in sub if s >= SATURATION_THRESHOLD)),
            "raw_weighted_sum": round(raw, 6),
        },
    )


def compute_deal_likelihood(
    *,
    cash_runway_pressure_score: float,
    external_deal_pressure_score: float,
    target_signal_score: float,
    days_to_catalyst: Optional[int],
    scarcity_score: float = 0.0,
    cash_runway_quarters: Optional[float] = None,
    days_since_last_financing: Optional[int] = None,
) -> DealLikelihoodScore:
    """Compute DealLikelihoodScore from vulnerability and catalyst signals.

    Applies a financing-pressure gate: when the target is well-funded
    (cash_runway_pressure_score < 0.25) and no strong scarcity/activist
    override signal is present, the score is capped at 0.40 to reduce
    false positives driven purely by strategic attractiveness without any
    transactional urgency.
    """
    cat_score = _catalyst_proximity_score(days_to_catalyst)
    has_near_term_catalyst = days_to_catalyst is not None and days_to_catalyst <= 90

    raw = (
        cash_runway_pressure_score * _DL_WEIGHTS["financing_pressure"]
        + external_deal_pressure_score * _DL_WEIGHTS["external_deal_activity"]
        + target_signal_score * _DL_WEIGHTS["insider_board_signals"]
        + cat_score * _DL_WEIGHTS["catalyst_proximity"]
    )
    sub = [cash_runway_pressure_score, external_deal_pressure_score, target_signal_score, cat_score]
    raw_penalised = apply_saturation_penalty(raw, sub_scores=sub)

    # Apply financing-pressure gate
    score, gate_applied, reason_codes = apply_financing_pressure_gate(
        raw_penalised,
        financing_pressure_score=cash_runway_pressure_score,
        scarcity_score=scarcity_score,
        activist_signal_score=target_signal_score,
        cash_runway_quarters=cash_runway_quarters,
        has_near_term_catalyst=has_near_term_catalyst,
        external_deal_activity_score=external_deal_pressure_score,
        days_since_last_financing=days_since_last_financing,
    )

    return DealLikelihoodScore(
        score=round(score, 6),
        financing_pressure=round(cash_runway_pressure_score, 6),
        external_deal_activity=round(external_deal_pressure_score, 6),
        insider_board_signals=round(target_signal_score, 6),
        catalyst_proximity=round(cat_score, 6),
        financing_reason_codes=reason_codes,
        financing_gate_applied=gate_applied,
        diagnostics={
            "n_at_cap": float(sum(1 for s in sub if s >= SATURATION_THRESHOLD)),
            "raw_weighted_sum": round(raw, 6),
            "raw_penalised": round(raw_penalised, 6),
            "gate_applied": float(gate_applied),
        },
    )


def compute_acquirer_fit_decomposed(
    *,
    therapeutic_area_score: float,
    modality_score: float,
    strategic_priority_score: float,
    budget_score: float,
    matched_partnership: Optional[str],
) -> AcquirerFitDecomposed:
    """Compute AcquirerFitDecomposed from AcquirerFitRow sub-scores."""
    ta_modality = min(
        (therapeutic_area_score * 0.55 + modality_score * 0.45),
        1.0,
    )
    pipeline_gap = round(strategic_priority_score, 6)
    deal_afford = round(budget_score, 6)
    partnership_bonus = 1.0 if matched_partnership is not None else 0.0

    raw = (
        ta_modality * _AF_WEIGHTS["ta_modality_fit"]
        + pipeline_gap * _AF_WEIGHTS["pipeline_gap_alignment"]
        + deal_afford * _AF_WEIGHTS["deal_affordability"]
        + partnership_bonus * _AF_WEIGHTS["existing_partnership_bonus"]
    )
    sub = [ta_modality, pipeline_gap, deal_afford, partnership_bonus]
    score = apply_saturation_penalty(raw, sub_scores=sub)

    return AcquirerFitDecomposed(
        score=round(score, 6),
        ta_modality_fit=round(ta_modality, 6),
        pipeline_gap_alignment=round(pipeline_gap, 6),
        deal_affordability=round(deal_afford, 6),
        existing_partnership_bonus=round(partnership_bonus, 6),
        diagnostics={
            "n_at_cap": float(sum(1 for s in sub if s >= SATURATION_THRESHOLD)),
            "raw_weighted_sum": round(raw, 6),
        },
    )


def compute_mna_composite_score(
    ta: TargetAttractivenessScore,
    dl: DealLikelihoodScore,
    af: AcquirerFitDecomposed,
) -> tuple[float, list[str]]:
    """Compute the composite M&A screening score from three sub-scores.

    Applies a secondary composite cap when the DL financing gate fired, ensuring
    that strategic fit alone (high TA + AF) cannot produce a high composite score
    when deal urgency signals are absent.

    Returns (composite_score, cap_reason_codes).
    """
    raw = (
        ta.score * TARGET_ATTRACTIVENESS_WEIGHT
        + dl.score * DEAL_LIKELIHOOD_WEIGHT
        + af.score * ACQUIRER_FIT_WEIGHT
    )
    sub = [ta.score, dl.score, af.score]
    penalised = apply_saturation_penalty(raw, sub_scores=sub)

    cap_reasons: list[str] = []
    if dl.financing_gate_applied:
        # Strategic fit (TA + AF) alone is insufficient when DL signals low urgency
        if penalised > COMPOSITE_MAX_WITH_DL_GATE:
            penalised = COMPOSITE_MAX_WITH_DL_GATE
            cap_reasons.append("composite_capped_by_dl_gate")
        cap_reasons.extend(dl.financing_reason_codes)

    return round(min(max(penalised, 0.0), 1.0), 6), cap_reasons
