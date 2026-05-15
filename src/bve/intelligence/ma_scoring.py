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
# Composite score cap when BOTH financing_not_pressured AND no_buyer_urgency fire
COMPOSITE_MAX_DUAL_GATE = 0.50

# Transaction driver thresholds — sub-scores must clear these to count as a real driver
_DRIVER_FINANCING_PRESSURE_MIN = 0.35  # target under meaningful capital pressure
_DRIVER_EXTERNAL_ACTIVITY_MIN = 0.30   # active same-space deal wave
_DRIVER_CATALYST_MIN = 0.35            # near-term binary event present
_DRIVER_SCARCITY_MIN = 0.60            # asset is genuinely scarce for acquirers
_DRIVER_ACTIVIST_MIN = 0.30            # insider/board/activist signal present
_DRIVER_VALUATION_MIN = 0.45           # asset trading at meaningful discount to NPV

# Composite caps based on number of independent transaction drivers
COMPOSITE_MAX_ONE_DRIVER = 0.65   # only 1 driver → same ceiling as DL gate
COMPOSITE_MAX_ZERO_DRIVERS = 0.45  # pure strategic attractiveness, no urgency signals


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


def _count_transaction_drivers(
    ta: TargetAttractivenessScore,
    dl: DealLikelihoodScore,
    af: AcquirerFitDecomposed,
) -> tuple[int, list[str]]:
    """Count independent transaction drivers beyond pure strategic attractiveness.

    A transaction driver is a signal that the deal could happen NOW, not just
    that the target is attractive in principle.

    Drivers assessed:
      1. financing_pressure — target under meaningful capital pressure
      2. external_deal_activity — same-space deal wave creating buyer urgency
      3. catalyst_proximity — near-term binary event accelerating deal timeline
      4. scarcity_plus_fit — asset is genuinely scarce AND a specific acquirer needs it
      5. activist_ownership — insider / board-change / activist ownership signal
      6. valuation_distress — deep discount on a de-risked asset (motivated seller)

    Returns (n_drivers, driver_name_list).
    """
    drivers: list[str] = []

    if dl.financing_pressure >= _DRIVER_FINANCING_PRESSURE_MIN:
        drivers.append("financing_pressure")
    if dl.external_deal_activity >= _DRIVER_EXTERNAL_ACTIVITY_MIN:
        drivers.append("external_deal_activity")
    if dl.catalyst_proximity >= _DRIVER_CATALYST_MIN:
        drivers.append("catalyst_proximity")
    if ta.scarcity >= _DRIVER_SCARCITY_MIN and af.pipeline_gap_alignment >= 0.50:
        drivers.append("scarcity_plus_fit")
    if dl.insider_board_signals >= _DRIVER_ACTIVIST_MIN:
        drivers.append("activist_ownership")
    if ta.valuation_discount >= _DRIVER_VALUATION_MIN and ta.de_risking_stage >= 0.50:
        drivers.append("valuation_distress")

    return len(drivers), drivers


def compute_mna_composite_score(
    ta: TargetAttractivenessScore,
    dl: DealLikelihoodScore,
    af: AcquirerFitDecomposed,
) -> tuple[float, list[str]]:
    """Compute the composite M&A screening score from three sub-scores.

    Applies gate caps and a transaction-driver requirement:

    1. Dual gate (financing_not_pressured AND no_buyer_urgency): composite ≤ 0.50
    2. Single DL gate (financing_not_pressured only): composite ≤ 0.65
    3. Two-driver requirement: composite > 0.65 requires ≥ 2 independent transaction
       drivers.  With only 1 driver the ceiling is 0.65; with 0 drivers, 0.45.

    Strategic fit alone (high TA + AF, no urgency signals) cannot produce a
    composite score above 0.45 when no transaction drivers are present, or 0.65
    when only one driver fires.

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
    n_drivers, driver_names = _count_transaction_drivers(ta, dl, af)

    # Detect dual gate: both financing_not_pressured AND no_buyer_urgency
    dual_gate = (
        FINANCING_REASON_NOT_PRESSURED in dl.financing_reason_codes
        and FINANCING_REASON_NO_BUYER_URGENCY in dl.financing_reason_codes
    )

    # Apply gate caps from most to least restrictive
    if dual_gate and penalised > COMPOSITE_MAX_DUAL_GATE:
        penalised = COMPOSITE_MAX_DUAL_GATE
        cap_reasons.append("composite_capped_by_dual_gate")
    elif dl.financing_gate_applied and penalised > COMPOSITE_MAX_WITH_DL_GATE:
        penalised = COMPOSITE_MAX_WITH_DL_GATE
        cap_reasons.append("composite_capped_by_dl_gate")

    # Two-driver requirement: scores above 0.65 require ≥ 2 independent drivers
    if n_drivers < 2 and penalised > COMPOSITE_MAX_ONE_DRIVER:
        penalised = COMPOSITE_MAX_ONE_DRIVER
        cap_reasons.append("composite_needs_two_drivers")

    # Zero-driver floor: no urgency signal at all → hard cap at 0.45
    if n_drivers == 0 and penalised > COMPOSITE_MAX_ZERO_DRIVERS:
        penalised = COMPOSITE_MAX_ZERO_DRIVERS
        cap_reasons.append("composite_capped_zero_drivers")

    # Propagate financing reason codes and attach driver diagnostics
    if dl.financing_gate_applied:
        cap_reasons.extend(dl.financing_reason_codes)

    cap_reasons.append(f"n_drivers:{n_drivers}")
    for d in driver_names:
        cap_reasons.append(f"driver:{d}")

    return round(min(max(penalised, 0.0), 1.0), 6), cap_reasons


# ---------------------------------------------------------------------------
# Watchlist type classification (Sprint 23 Task 3)
# ---------------------------------------------------------------------------

class WatchlistType:
    """Two-class taxonomy for M&A watchlist separation.

    STRATEGIC_WATCH: high strategic fit but lacking near-term transaction urgency.
        - Gate-reason codes include ``financing_not_pressured`` AND ``no_buyer_urgency``, OR
        - transaction_driver_count < 2

    NEAR_TERM_TRANSACTION: ≥ 2 transaction drivers fired; actionable within typical BD window.
    """

    STRATEGIC_WATCH = "strategic_watch"
    NEAR_TERM_TRANSACTION = "near_term_transaction"


_GATE_CODE_DUAL_LOW_PRESSURE = "dual_gate:low_pressure"
_GATE_CODE_MISSING_ALL = "missing_trigger:all"


def classify_watchlist_type(
    *,
    transaction_driver_count: Optional[int],
    gate_reason_codes: list[str],
) -> str:
    """Classify a scored row as STRATEGIC_WATCH or NEAR_TERM_TRANSACTION.

    Rules (applied in priority order):
    1. If ``transaction_driver_count`` is known and < 2 → strategic_watch.
    2. If gate codes include ``"dual_gate:low_pressure"`` (both financing_not_pressured
       AND no_buyer_urgency fired inside ``_apply_transaction_likelihood_gate``) OR
       ``"missing_trigger:all"`` (zero triggers) → strategic_watch.
    3. Otherwise → near_term_transaction.

    Args:
        transaction_driver_count: Number of transaction triggers that fired for the
            best acquirer candidate (from ``_apply_transaction_likelihood_gate``).
            ``None`` means the full live scorer was not run (rescore path); in this
            case we fall back to gate code inspection.
        gate_reason_codes: Reason codes from ``transaction_gate_reason_codes`` on the
            best acquirer candidate (e.g. ``"dual_gate:low_pressure"``,
            ``"missing_trigger:all"``, ``"missing_trigger:second"``).

    Returns:
        ``WatchlistType.STRATEGIC_WATCH`` or ``WatchlistType.NEAR_TERM_TRANSACTION``.
    """
    if transaction_driver_count is not None and transaction_driver_count < 2:
        return WatchlistType.STRATEGIC_WATCH

    codes_set = set(gate_reason_codes)
    if _GATE_CODE_DUAL_LOW_PRESSURE in codes_set or _GATE_CODE_MISSING_ALL in codes_set:
        return WatchlistType.STRATEGIC_WATCH

    return WatchlistType.NEAR_TERM_TRANSACTION


# ---------------------------------------------------------------------------
# Layer 2 — BD Decision Engine
# ---------------------------------------------------------------------------

from enum import Enum


class DataConfidence(str, Enum):
    """Data quality level for a scored target.

    Controls a multiplicative confidence adjustment on the final BD Action Score.
    VERY_LOW targets should be excluded from ranked output entirely.
    """
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"


_DATA_CONFIDENCE_MULTIPLIER: dict[DataConfidence, float] = {
    DataConfidence.HIGH: 1.00,
    DataConfidence.MEDIUM: 0.93,
    DataConfidence.LOW: 0.85,
    DataConfidence.VERY_LOW: 0.00,  # excluded from ranking
}


class BDActionClassification:
    """Strategic × transaction-probability decision matrix (2×3 taxonomy)."""
    ACTIVE_PURSUIT = "Active BD pursuit"
    BEGIN_RELATIONSHIP = "Begin relationship / monitor catalyst"
    STRATEGIC_WATCHLIST = "Strategic watchlist"
    OPPORTUNISTIC_OUTREACH = "Opportunistic outreach"
    DISTRESSED_NON_CORE = "Distressed but likely non-core"
    PASS = "Pass"


# Thresholds for the 2×3 classification grid
_SP_HIGH = 0.75   # strategic priority ≥ this → "High"
_SP_MED = 0.45    # strategic priority ≥ this → "Medium" (else "Low")
_TP_HIGH = 0.60   # transaction probability ≥ this → "High"
_TP_MED = 0.40    # transaction probability ≥ this → "Medium" (else "Low")

# Interaction bonus thresholds
_BONUS_TA_MIN = 0.65
_BONUS_AF_MIN_CONVERGENCE = 0.65
_BONUS_AF_MIN_ACTIONABLE = 0.60
_BONUS_DL_MIN = 0.60
_BONUS_CAP = 0.08

# Balance / fragility penalty thresholds
_BALANCE_SEVERE = 0.35   # min/max ratio below this → 0.10 penalty
_BALANCE_WEAK = 0.50     # min/max ratio below this → 0.05 penalty

# Number of possible transaction drivers (used for normalisation)
_N_DRIVER_MAX = 6


class Layer2Output(BaseModel):
    """Full BD decision engine output for a single target-acquirer pair."""
    model_config = {"frozen": True}

    # Three diagnostic scores
    strategic_priority: float = Field(..., ge=0.0, le=1.0,
        description="How much the acquirer should want this asset (0.45×AF + 0.35×TA + 0.20×TA.scarcity)")
    transaction_probability: float = Field(..., ge=0.0, le=1.0,
        description="Likelihood of a transaction in the next 6–18 months")
    bd_action_score: float = Field(..., ge=0.0, le=1.0,
        description="Final composite BD action score after bonuses, penalties, and confidence adjustment")

    # Intermediate values for transparency
    bd_action_score_raw: float = Field(..., ge=0.0, le=1.0,
        description="0.50×SP + 0.35×TP + 0.15×AF before bonuses/penalties")
    bd_action_score_pre_confidence: float = Field(..., ge=0.0, le=1.0,
        description="Score after bonuses and penalties, before confidence multiplier")

    # Decision output
    classification: str = Field(...,
        description="BD action classification from the 2×3 strategic/transaction matrix")
    recommended_action: str = Field(...,
        description="Short recommended action string")
    reason: str = Field(...,
        description="Plain-English explanation of the classification")

    # Diagnostics
    n_drivers: int = Field(..., ge=0,
        description="Number of independent transaction drivers that fired")
    driver_names: list[str]
    interaction_bonuses_applied: float = Field(..., ge=0.0, le=_BONUS_CAP)
    imbalance_penalty_applied: float = Field(..., ge=0.0)
    data_confidence: DataConfidence
    confidence_multiplier: float = Field(..., ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Layer 2 helpers
# ---------------------------------------------------------------------------

def _compute_strategic_priority(ta: TargetAttractivenessScore, af: AcquirerFitDecomposed) -> float:
    """Strategic Priority = 0.45×AF + 0.35×TA + 0.20×TA.scarcity."""
    raw = 0.45 * af.score + 0.35 * ta.score + 0.20 * ta.scarcity
    return round(min(max(raw, 0.0), 1.0), 6)


def _compute_transaction_probability(
    ta: TargetAttractivenessScore,
    dl: DealLikelihoodScore,
    af: AcquirerFitDecomposed,
    n_drivers: int,
) -> float:
    """Transaction Probability = 0.45×DL + 0.25×AF + 0.15×TA + 0.15×driver_strength."""
    driver_strength = min(n_drivers / _N_DRIVER_MAX, 1.0)
    raw = (
        0.45 * dl.score
        + 0.25 * af.score
        + 0.15 * ta.score
        + 0.15 * driver_strength
    )
    return round(min(max(raw, 0.0), 1.0), 6)


def _compute_balance_penalty(ta_score: float, dl_score: float, af_score: float) -> float:
    """Fragility penalty when one sub-score is much weaker than the others."""
    lo = min(ta_score, dl_score, af_score)
    hi = max(ta_score, dl_score, af_score)
    if hi == 0.0:
        return 0.0
    balance = lo / hi
    if balance < _BALANCE_SEVERE:
        return 0.10
    if balance < _BALANCE_WEAK:
        return 0.05
    return 0.0


def _compute_interaction_bonuses(
    ta: TargetAttractivenessScore,
    dl: DealLikelihoodScore,
    af: AcquirerFitDecomposed,
) -> float:
    """Interaction bonuses when independent signals reinforce each other.

    Returns total bonus, capped at 0.08.
    Bonuses only added when signals genuinely converge — they never substitute
    for a weak base score.
    """
    strategic_convergence = 0.04 if (ta.score >= _BONUS_TA_MIN and af.score >= _BONUS_AF_MIN_CONVERGENCE) else 0.0
    actionable_buyer = 0.04 if (af.score >= _BONUS_AF_MIN_ACTIONABLE and dl.score >= _BONUS_DL_MIN) else 0.0
    full_convergence = 0.05 if (
        ta.score >= _BONUS_TA_MIN and dl.score >= _BONUS_DL_MIN and af.score >= _BONUS_AF_MIN_CONVERGENCE
    ) else 0.0
    total = strategic_convergence + actionable_buyer + full_convergence
    return round(min(total, _BONUS_CAP), 6)


def _classify_bd_action(
    strategic_priority: float,
    transaction_probability: float,
) -> tuple[str, str, str]:
    """2×3 decision matrix → (classification, recommended_action, reason)."""
    if strategic_priority >= _SP_HIGH:
        sp_tier = "high"
    elif strategic_priority >= _SP_MED:
        sp_tier = "medium"
    else:
        sp_tier = "low"

    if transaction_probability >= _TP_HIGH:
        tp_tier = "high"
    elif transaction_probability >= _TP_MED:
        tp_tier = "medium"
    else:
        tp_tier = "low"

    matrix: dict[tuple[str, str], tuple[str, str, str]] = {
        ("high", "high"): (
            BDActionClassification.ACTIVE_PURSUIT,
            "Pursue full acquisition",
            "Strong strategic fit and near-term transaction urgency are both present.",
        ),
        ("high", "medium"): (
            BDActionClassification.BEGIN_RELATIONSHIP,
            "Begin BD dialogue / monitor catalyst",
            "High strategic priority but transaction is not yet imminent; build relationship now.",
        ),
        ("high", "low"): (
            BDActionClassification.STRATEGIC_WATCHLIST,
            "Add to strategic watchlist",
            "Strong fit and asset attractiveness, but weak seller pressure and limited transaction drivers.",
        ),
        ("medium", "high"): (
            BDActionClassification.OPPORTUNISTIC_OUTREACH,
            "Opportunistic outreach",
            "Transaction conditions are favorable but strategic fit is moderate; act if valuation is right.",
        ),
        ("medium", "medium"): (
            BDActionClassification.OPPORTUNISTIC_OUTREACH,
            "Monitor and reassess",
            "Moderate fit and moderate transaction urgency; revisit after next catalyst.",
        ),
        ("medium", "low"): (
            BDActionClassification.PASS,
            "Pass",
            "Limited strategic relevance and no near-term transaction drivers.",
        ),
        ("low", "high"): (
            BDActionClassification.DISTRESSED_NON_CORE,
            "Monitor for distressed transaction",
            "High transaction pressure but low strategic fit; asset is likely non-core for this acquirer.",
        ),
        ("low", "medium"): (
            BDActionClassification.PASS,
            "Pass",
            "Insufficient strategic priority to justify BD resources.",
        ),
        ("low", "low"): (
            BDActionClassification.PASS,
            "Pass",
            "Low strategic relevance and no transaction urgency.",
        ),
    }
    return matrix[(sp_tier, tp_tier)]


# ---------------------------------------------------------------------------
# Main Layer 2 entry point
# ---------------------------------------------------------------------------

def compute_bd_layer2(
    ta: TargetAttractivenessScore,
    dl: DealLikelihoodScore,
    af: AcquirerFitDecomposed,
    data_confidence: DataConfidence = DataConfidence.HIGH,
) -> Layer2Output:
    """Layer 2 BD Decision Engine.

    Replaces the single composite with three diagnostic scores:
      1. Strategic Priority   — does the acquirer want this asset?
      2. Transaction Probability — can it transact in the next 6–18 months?
      3. BD Action Score      — should we act now?

    Applies:
      - Balance / fragility penalty when one sub-score dominates
      - Interaction bonuses when signals genuinely converge (capped at 0.08)
      - Saturation penalty via apply_saturation_penalty
      - Data confidence multiplier (VERY_LOW → bd_action_score = 0)
    """
    n_drivers, driver_names = _count_transaction_drivers(ta, dl, af)

    strategic_priority = _compute_strategic_priority(ta, af)
    transaction_probability = _compute_transaction_probability(ta, dl, af, n_drivers)

    # Raw composite
    bd_action_score_raw = round(min(max(
        0.50 * strategic_priority + 0.35 * transaction_probability + 0.15 * af.score,
        0.0,
    ), 1.0), 6)

    # Fragility penalty
    penalty = _compute_balance_penalty(ta.score, dl.score, af.score)

    # Interaction bonuses
    bonuses = _compute_interaction_bonuses(ta, dl, af)

    # Pre-confidence score
    pre_conf = apply_saturation_penalty(
        min(max(bd_action_score_raw + bonuses - penalty, 0.0), 1.0),
        sub_scores=[strategic_priority, transaction_probability, af.score],
    )

    # Confidence multiplier
    multiplier = _DATA_CONFIDENCE_MULTIPLIER[data_confidence]
    bd_action_score = round(min(max(pre_conf * multiplier, 0.0), 1.0), 6)

    classification, recommended_action, reason = _classify_bd_action(
        strategic_priority, transaction_probability
    )

    return Layer2Output(
        strategic_priority=strategic_priority,
        transaction_probability=transaction_probability,
        bd_action_score=bd_action_score,
        bd_action_score_raw=bd_action_score_raw,
        bd_action_score_pre_confidence=round(pre_conf, 6),
        classification=classification,
        recommended_action=recommended_action,
        reason=reason,
        n_drivers=n_drivers,
        driver_names=driver_names,
        interaction_bonuses_applied=bonuses,
        imbalance_penalty_applied=penalty,
        data_confidence=data_confidence,
        confidence_multiplier=multiplier,
    )


def compute_mna_composite_score(
    ta: TargetAttractivenessScore,
    dl: DealLikelihoodScore,
    af: AcquirerFitDecomposed,
) -> tuple[float, list[str]]:
    """Backward-compatible wrapper — delegates to compute_bd_layer2.

    Returns (bd_action_score, reason_codes) where reason_codes preserves
    the gate-code strings that downstream code (tests, ma_probability.py) inspects.
    """
    result = compute_bd_layer2(ta, dl, af, data_confidence=DataConfidence.HIGH)

    # Reconstruct legacy reason code list from Layer2Output diagnostics
    reason_codes: list[str] = []
    if dl.financing_gate_applied:
        reason_codes.extend(dl.financing_reason_codes)
        reason_codes.append("composite_capped_by_dl_gate")
    if (
        FINANCING_REASON_NOT_PRESSURED in dl.financing_reason_codes
        and FINANCING_REASON_NO_BUYER_URGENCY in dl.financing_reason_codes
    ):
        reason_codes.append("composite_capped_by_dual_gate")
    if result.n_drivers < 2:
        reason_codes.append("composite_needs_two_drivers")
    if result.n_drivers == 0:
        reason_codes.append("composite_capped_zero_drivers")
    reason_codes.append(f"n_drivers:{result.n_drivers}")
    for d in result.driver_names:
        reason_codes.append(f"driver:{d}")

    return result.bd_action_score, reason_codes
