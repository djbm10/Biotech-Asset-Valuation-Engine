"""
Layer 3 — Institutional Gate System / Deal Realism Engine.

After Layer 2 produces the BD Action Score, Layer 3 applies institutional
deal gates that prevent the model from ranking a target highly unless the
opportunity is:

  1. Scientifically credible        (Gate 1 — Broken Asset)
  2. Strategically owned            (Gate 2 — No Right-to-Win)
  3. Transactionally plausible      (Gates 3 & 4 — Driver Bucket System)
  4. Seller-ready                   (Gate 5 — Seller Not Ready)
  5. Quality-driven, not distress   (Gate 6 — Capital Pressure Without Quality)
  6. Economically executable        (Gates 7 & 8 — Control + Feasibility)

Layer 3 is PAIR-SPECIFIC.  It scores each (target, acquirer) pair independently:
  • G7  — pair affordability from Layer 3A (ma_pair_affordability.py)
  • G8  — pair integration capability (buyer-specific complexity adjustment)
  • 3B  — pair asset control / ROFR / partner / manufacturing fit
          (ma_pair_asset_control.py → compute_pair_asset_control())

Key architectural principles:
  • Six transaction driver BUCKETS replace raw signal counting.  Each bucket
    aggregates multiple signals and produces a continuous strength score.
  • Driver strength is a weighted average of all bucket scores, not a binary
    count.  A barely-triggered bucket contributes less than a strong one.
  • All gates are evaluated independently; the MOST RESTRICTIVE cap wins.
  • final_score = min(pre_gate_score, most_restrictive_active_cap)
  • Layer 0 encumbrance / distress caps are applied BEFORE Layer 3 gates
    (pre_gate_score already reflects Layer 0 score_multiplier and score_cap).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Constants — activation thresholds
# ---------------------------------------------------------------------------

_CAPITAL_PRESSURE_THRESHOLD: float = 0.35
_BUYER_URGENCY_THRESHOLD: float = 0.30
_SELLER_WILLINGNESS_THRESHOLD: float = 0.30
_CATALYST_TIMING_THRESHOLD: float = 0.35
_ASSET_SCARCITY_THRESHOLD: float = 0.60
_VALUATION_DISLOCATION_DISCOUNT_MIN: float = 0.45
_VALUATION_DISLOCATION_DERISKING_MIN: float = 0.50

# Driver strength classification bands
_STRENGTH_STRONG: float = 0.75
_STRENGTH_PLAUSIBLE: float = 0.55
_STRENGTH_WATCHLIST: float = 0.35

# Near-term transaction threshold
_NEAR_TERM_BUCKET_MIN: int = 2
_NEAR_TERM_STRENGTH_MIN: float = 0.60

# Gate caps — all are maximum composite scores when the gate triggers
_GATE_CAPS: dict[str, float] = {
    "G1": 0.35,   # Broken asset: do not let cheapness rescue broken science
    "G2": 0.50,   # No right-to-win: this acquirer is not the logical owner
    "G3": 0.45,   # No transaction rationale: strategic watch only
    "G4": 0.65,   # Weak transaction setup: one bucket or low strength
    "G5": 0.55,   # Seller not ready: company will not engage
    "G6": 0.45,   # Capital pressure without quality: distress ≠ deal thesis
    "G7": 0.50,   # Encumbrance / control: rights split blocks full acquisition
    "G8": 0.60,   # Deal feasibility: logistics prevent execution
}

# Bucket weights within BuyerUrgency and SellerWillingness composites
_BUYER_URGENCY_EXTERNAL_WEIGHT: float = 0.60
_BUYER_URGENCY_GAP_WEIGHT: float = 0.40
_SELLER_WS_ACTIVIST_WEIGHT: float = 0.60
_SELLER_WS_REVIEW_WEIGHT: float = 0.40
_SCARCITY_SCARCITY_WEIGHT: float = 0.60
_SCARCITY_FIT_WEIGHT: float = 0.40


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class DriverBucketInputs(BaseModel):
    """Raw sub-scores for the six transaction driver buckets.

    All values are in [0, 1] unless otherwise noted.
    """
    model_config = ConfigDict(frozen=True)

    # Capital Pressure
    financing_pressure: float = Field(..., ge=0.0, le=1.0,
        description="Cash runway pressure (0=well-funded, 1=critical)")

    # Buyer Urgency
    external_deal_activity: float = Field(..., ge=0.0, le=1.0,
        description="Same-TA deal wave / competitive BD activity")
    pipeline_gap_urgency: float = Field(default=0.50, ge=0.0, le=1.0,
        description="Acquirer pipeline gap urgency for this asset type")

    # Seller Willingness
    activist_signal: float = Field(..., ge=0.0, le=1.0,
        description="Insider / board-change / activist ownership signal")
    strategic_review_signal: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Strategic alternatives review or public process signal")

    # Catalyst Timing
    catalyst_proximity: float = Field(..., ge=0.0, le=1.0,
        description="Proximity to next catalyst (1=imminent, 0=distant/none)")

    # Asset Scarcity
    scarcity_score: float = Field(..., ge=0.0, le=1.0,
        description="Scarcity of comparable late-stage assets in indication")
    acquirer_fit_score: float = Field(default=0.50, ge=0.0, le=1.0,
        description="How well the acquirer fits the asset (from AF decomposition)")

    # Valuation Dislocation
    valuation_discount: float = Field(..., ge=0.0, le=1.0,
        description="EV discount vs risk-adjusted NPV (0=fairly valued, 1=deeply discounted)")
    de_risking_stage: float = Field(..., ge=0.0, le=1.0,
        description="Clinical/regulatory stage de-risking (0=preclinical, 1=approved)")


class GateInputs(BaseModel):
    """Inputs for the 8 institutional deal gates.

    All boolean flags default to False (no adverse condition).
    """
    model_config = ConfigDict(frozen=True)

    # Gate 1 — Broken Asset
    asset_quality: float = Field(..., ge=0.0, le=1.0,
        description="Overall asset quality score (from Layer 1 1A)")
    severe_safety_issue: bool = Field(default=False,
        description="Unresolved black-box warning or clinical hold")
    failed_pivotal_no_rescue: bool = Field(default=False,
        description="Failed primary endpoint in pivotal trial with no credible rescue path")
    regulatory_path_unacceptable: bool = Field(default=False,
        description="FDA/EMA endpoint or pathway deemed unacceptable for approval")

    # Gate 2 — No Right-to-Win
    acquirer_right_to_win: float = Field(..., ge=0.0, le=1.0,
        description="Acquirer strategic fit / right-to-win score (from Layer 1 1D)")

    # Gate 5 — Seller Not Ready
    seller_willingness: float = Field(..., ge=0.0, le=1.0,
        description="Management/board willingness to transact (from Layer 1 1C)")
    financing_pressure: float = Field(..., ge=0.0, le=1.0,
        description="Target financing pressure (from Layer 1 1C / driver buckets)")
    no_active_process_signal: bool = Field(default=True,
        description="True = no known strategic review, banker engagement, or BD process")

    # Gate 7 — Encumbrance / Control
    asset_control: float = Field(..., ge=0.0, le=1.0,
        description="Degree of clean title and absence of blocking rights (from Layer 1 1E)")

    # Gate 8 — Deal Feasibility
    affordability: float = Field(..., ge=0.0, le=1.0,
        description="Deal affordability relative to acquirer capacity (from Layer 1 1E)")
    antitrust_risk_high: bool = Field(default=False,
        description="Elevated antitrust / competition law risk")
    # Legacy flag — kept for backward compatibility.
    # When adjusted_integration_penalty is provided, it supersedes this flag.
    integration_complexity_severe: bool = Field(default=False,
        description="Severe integration complexity (manufacturing, platform, geography)")
    # Pair-specific integration penalty from compute_pair_integration_adjustment().
    # When set, G8 uses this value with tiered caps instead of the legacy flag.
    # Penalty 0.50–0.70 → cap 0.60; penalty > 0.70 → cap 0.50 (pair fail if < 0.25 capability).
    adjusted_integration_penalty: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="Pair-specific integration penalty from Layer 3 / 0E+acquirer capability")


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class DriverBucketScore(BaseModel):
    """Scored output for a single driver bucket."""
    model_config = ConfigDict(frozen=True)

    name: str
    strength: float = Field(..., ge=0.0, le=1.0)
    active: bool
    activation_threshold: float
    sub_scores: dict[str, float]


class DriverBucketResult(BaseModel):
    """All six driver bucket scores plus aggregate metrics."""
    model_config = ConfigDict(frozen=True)

    buckets: dict[str, DriverBucketScore]
    driver_strength_score: float = Field(..., ge=0.0, le=1.0,
        description="Equal-weight mean of all six bucket strength scores")
    active_bucket_count: int = Field(..., ge=0)
    strength_classification: str = Field(...,
        description="Strong / Plausible / Watchlist / Low")
    near_term_transaction_possible: bool = Field(...,
        description="True if ≥2 buckets active AND driver_strength ≥ 0.60")


class GateResult(BaseModel):
    """Result for a single gate evaluation."""
    model_config = ConfigDict(frozen=True)

    gate_id: str
    triggered: bool
    cap_applied: float
    description: str


class Layer3Output(BaseModel):
    """Full Layer 3 deal realism engine output."""
    model_config = ConfigDict(frozen=True)

    target_name: str
    acquirer_id: Optional[str]

    pre_gate_score: float = Field(..., ge=0.0, le=1.0)
    final_score: float = Field(..., ge=0.0, le=1.0)
    most_restrictive_cap: Optional[float] = Field(default=None,
        description="The cap that was binding, or None if no gates triggered")

    classification: str
    active_gate_ids: list[str]
    gate_results: list[GateResult]

    driver_buckets: DriverBucketResult
    near_term_transaction_possible: bool

    interpretation: str

    # G8 pair-specific integration adjustment diagnostics (populated when
    # adjusted_integration_penalty is provided in GateInputs)
    adjusted_integration_penalty: Optional[float] = Field(default=None,
        description="Pair-level integration penalty used for G8 (None = legacy flag path)")
    integration_cap_applied: Optional[float] = Field(default=None,
        description="Actual G8 cap used (0.60 for penalty 0.50-0.70; 0.50 for >0.70)")


# ---------------------------------------------------------------------------
# Bucket compute functions
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _compute_capital_pressure_bucket(inputs: DriverBucketInputs) -> DriverBucketScore:
    """Capital Pressure: how urgently does the target need money?"""
    strength = _clamp(inputs.financing_pressure)
    return DriverBucketScore(
        name="capital_pressure",
        strength=round(strength, 6),
        active=strength >= _CAPITAL_PRESSURE_THRESHOLD,
        activation_threshold=_CAPITAL_PRESSURE_THRESHOLD,
        sub_scores={"financing_pressure": round(inputs.financing_pressure, 6)},
    )


def _compute_buyer_urgency_bucket(inputs: DriverBucketInputs) -> DriverBucketScore:
    """Buyer Urgency: does a specific acquirer need to act now?"""
    strength = _clamp(
        _BUYER_URGENCY_EXTERNAL_WEIGHT * inputs.external_deal_activity
        + _BUYER_URGENCY_GAP_WEIGHT * inputs.pipeline_gap_urgency
    )
    return DriverBucketScore(
        name="buyer_urgency",
        strength=round(strength, 6),
        active=strength >= _BUYER_URGENCY_THRESHOLD,
        activation_threshold=_BUYER_URGENCY_THRESHOLD,
        sub_scores={
            "external_deal_activity": round(inputs.external_deal_activity, 6),
            "pipeline_gap_urgency": round(inputs.pipeline_gap_urgency, 6),
        },
    )


def _compute_seller_willingness_bucket(inputs: DriverBucketInputs) -> DriverBucketScore:
    """Seller Willingness: is management likely to engage?"""
    strength = _clamp(
        _SELLER_WS_ACTIVIST_WEIGHT * inputs.activist_signal
        + _SELLER_WS_REVIEW_WEIGHT * inputs.strategic_review_signal
    )
    return DriverBucketScore(
        name="seller_willingness",
        strength=round(strength, 6),
        active=strength >= _SELLER_WILLINGNESS_THRESHOLD,
        activation_threshold=_SELLER_WILLINGNESS_THRESHOLD,
        sub_scores={
            "activist_signal": round(inputs.activist_signal, 6),
            "strategic_review_signal": round(inputs.strategic_review_signal, 6),
        },
    )


def _compute_catalyst_timing_bucket(inputs: DriverBucketInputs) -> DriverBucketScore:
    """Catalyst Timing: does a near-term event create deal urgency?"""
    strength = _clamp(inputs.catalyst_proximity)
    return DriverBucketScore(
        name="catalyst_timing",
        strength=round(strength, 6),
        active=strength >= _CATALYST_TIMING_THRESHOLD,
        activation_threshold=_CATALYST_TIMING_THRESHOLD,
        sub_scores={"catalyst_proximity": round(inputs.catalyst_proximity, 6)},
    )


def _compute_asset_scarcity_bucket(inputs: DriverBucketInputs) -> DriverBucketScore:
    """Asset Scarcity: how few comparable assets exist for this acquirer?"""
    strength = _clamp(
        _SCARCITY_SCARCITY_WEIGHT * inputs.scarcity_score
        + _SCARCITY_FIT_WEIGHT * inputs.acquirer_fit_score
    )
    return DriverBucketScore(
        name="asset_scarcity",
        strength=round(strength, 6),
        active=strength >= _ASSET_SCARCITY_THRESHOLD,
        activation_threshold=_ASSET_SCARCITY_THRESHOLD,
        sub_scores={
            "scarcity_score": round(inputs.scarcity_score, 6),
            "acquirer_fit_score": round(inputs.acquirer_fit_score, 6),
        },
    )


def _compute_valuation_dislocation_bucket(inputs: DriverBucketInputs) -> DriverBucketScore:
    """Valuation Dislocation: is the asset meaningfully cheap vs its risk-adjusted value?

    Requires BOTH valuation_discount ≥ 0.45 AND de_risking_stage ≥ 0.50.
    Cheap but pre-clinical assets do not qualify — the discount must be on a
    de-risked asset to represent genuine dislocation.
    """
    discount_meets = inputs.valuation_discount >= _VALUATION_DISLOCATION_DISCOUNT_MIN
    derisking_meets = inputs.de_risking_stage >= _VALUATION_DISLOCATION_DERISKING_MIN
    active = discount_meets and derisking_meets

    if active:
        strength = _clamp((inputs.valuation_discount + inputs.de_risking_stage) / 2.0)
    else:
        # Still report a partial strength for diagnostics, but bucket is inactive
        strength = _clamp((inputs.valuation_discount + inputs.de_risking_stage) / 2.0) * 0.5

    return DriverBucketScore(
        name="valuation_dislocation",
        strength=round(strength, 6),
        active=active,
        activation_threshold=max(_VALUATION_DISLOCATION_DISCOUNT_MIN,
                                  _VALUATION_DISLOCATION_DERISKING_MIN),
        sub_scores={
            "valuation_discount": round(inputs.valuation_discount, 6),
            "de_risking_stage": round(inputs.de_risking_stage, 6),
            "discount_qualifies": float(discount_meets),
            "derisking_qualifies": float(derisking_meets),
        },
    )


def compute_driver_buckets(inputs: DriverBucketInputs) -> DriverBucketResult:
    """Compute all six transaction driver buckets from raw inputs.

    Returns DriverBucketResult with per-bucket scores, aggregate driver
    strength (equal-weight mean of all six bucket strengths), active count,
    and strength classification.
    """
    cp = _compute_capital_pressure_bucket(inputs)
    bu = _compute_buyer_urgency_bucket(inputs)
    sw = _compute_seller_willingness_bucket(inputs)
    ct = _compute_catalyst_timing_bucket(inputs)
    as_ = _compute_asset_scarcity_bucket(inputs)
    vd = _compute_valuation_dislocation_bucket(inputs)

    bucket_map: dict[str, DriverBucketScore] = {
        "capital_pressure":     cp,
        "buyer_urgency":        bu,
        "seller_willingness":   sw,
        "catalyst_timing":      ct,
        "asset_scarcity":       as_,
        "valuation_dislocation": vd,
    }

    # Equal-weight mean over all 6 bucket strengths (active or not)
    driver_strength = round(
        sum(b.strength for b in bucket_map.values()) / len(bucket_map),
        6,
    )
    active_count = sum(1 for b in bucket_map.values() if b.active)

    if driver_strength >= _STRENGTH_STRONG:
        classification = "Strong"
    elif driver_strength >= _STRENGTH_PLAUSIBLE:
        classification = "Plausible"
    elif driver_strength >= _STRENGTH_WATCHLIST:
        classification = "Watchlist"
    else:
        classification = "Low"

    near_term = (
        active_count >= _NEAR_TERM_BUCKET_MIN
        and driver_strength >= _NEAR_TERM_STRENGTH_MIN
    )

    return DriverBucketResult(
        buckets=bucket_map,
        driver_strength_score=driver_strength,
        active_bucket_count=active_count,
        strength_classification=classification,
        near_term_transaction_possible=near_term,
    )


# ---------------------------------------------------------------------------
# Gate system
# ---------------------------------------------------------------------------

def _evaluate_gates(
    pre_gate_score: float,
    buckets: DriverBucketResult,
    gate_inputs: GateInputs,
) -> tuple[float, list[GateResult], Optional[float]]:
    """Evaluate all 8 institutional gates and apply the most restrictive cap.

    All gates are evaluated independently. The final score is:
        final_score = min(pre_gate_score, most_restrictive_active_cap)

    Returns (final_score, list[GateResult for all 8 gates]).
    """
    gate_results: list[GateResult] = []
    active_caps: list[float] = []

    def _gate(gate_id: str, triggered: bool, desc: str) -> GateResult:
        cap = _GATE_CAPS[gate_id]
        if triggered:
            active_caps.append(cap)
        return GateResult(
            gate_id=gate_id,
            triggered=triggered,
            cap_applied=cap,
            description=desc,
        )

    # G1 — Broken Asset Gate
    g1 = (
        gate_inputs.asset_quality < 0.35
        or gate_inputs.severe_safety_issue
        or gate_inputs.failed_pivotal_no_rescue
        or gate_inputs.regulatory_path_unacceptable
    )
    gate_results.append(_gate("G1", g1,
        f"asset_quality={gate_inputs.asset_quality:.2f} < 0.35 or clinical/regulatory flag: "
        f"composite ≤ {_GATE_CAPS['G1']}"))

    # G2 — No Right-to-Win Gate
    g2 = gate_inputs.acquirer_right_to_win < 0.45
    gate_results.append(_gate("G2", g2,
        f"acquirer_right_to_win={gate_inputs.acquirer_right_to_win:.2f} < 0.45: "
        f"composite ≤ {_GATE_CAPS['G2']}"))

    # G3 — No Transaction Rationale Gate
    g3 = buckets.active_bucket_count == 0
    gate_results.append(_gate("G3", g3,
        f"active_bucket_count={buckets.active_bucket_count}: no transaction rationale, "
        f"composite ≤ {_GATE_CAPS['G3']}"))

    # G4 — Weak Transaction Setup Gate
    g4 = (
        buckets.active_bucket_count == 1
        or buckets.driver_strength_score < _STRENGTH_PLAUSIBLE
    )
    gate_results.append(_gate("G4", g4,
        f"active_buckets={buckets.active_bucket_count}, "
        f"strength={buckets.driver_strength_score:.2f}: "
        f"weak setup, composite ≤ {_GATE_CAPS['G4']}"))

    # G5 — Seller Not Ready Gate
    g5 = (
        gate_inputs.seller_willingness < 0.30
        and gate_inputs.financing_pressure < 0.35
        and gate_inputs.no_active_process_signal
    )
    gate_results.append(_gate("G5", g5,
        f"seller_willingness={gate_inputs.seller_willingness:.2f} < 0.30, "
        f"financing_pressure={gate_inputs.financing_pressure:.2f} < 0.35, "
        f"no active process: composite ≤ {_GATE_CAPS['G5']}"))

    # G6 — Capital Pressure Without Quality Gate
    g6 = (
        gate_inputs.financing_pressure >= 0.60
        and gate_inputs.asset_quality < 0.50
    )
    gate_results.append(_gate("G6", g6,
        f"financing_pressure={gate_inputs.financing_pressure:.2f} ≥ 0.60 "
        f"AND asset_quality={gate_inputs.asset_quality:.2f} < 0.50: "
        f"distress ≠ deal thesis, composite ≤ {_GATE_CAPS['G6']}"))

    # G7 — Encumbrance / Control Gate
    g7 = gate_inputs.asset_control < 0.40
    gate_results.append(_gate("G7", g7,
        f"asset_control={gate_inputs.asset_control:.2f} < 0.40: "
        f"rights encumbered, composite ≤ {_GATE_CAPS['G7']}"))

    # G8 — Deal Feasibility Gate (tiered cap when adjusted_integration_penalty provided)
    adj_penalty = gate_inputs.adjusted_integration_penalty
    if adj_penalty is not None:
        # Pair-specific path: use adjusted_integration_penalty with tiered caps.
        # No double-counting: Layer 0E did not apply a score penalty.
        integration_trigger = adj_penalty >= 0.50
        if adj_penalty > 0.70:
            g8_cap = 0.50
        else:
            g8_cap = _GATE_CAPS["G8"]  # 0.60
        integration_desc = f"adjusted_integration_penalty={adj_penalty:.2f}"
    else:
        # Legacy path: fall back to integration_complexity_severe boolean flag
        integration_trigger = gate_inputs.integration_complexity_severe
        g8_cap = _GATE_CAPS["G8"]  # 0.60
        integration_desc = f"integration_complexity_severe={gate_inputs.integration_complexity_severe}"

    g8 = (
        gate_inputs.affordability < 0.40
        or gate_inputs.antitrust_risk_high
        or integration_trigger
    )
    # Apply dynamic G8 cap (may differ from _GATE_CAPS["G8"] under tiered logic)
    if g8:
        active_caps.append(g8_cap)
    gate_results.append(GateResult(
        gate_id="G8",
        triggered=g8,
        cap_applied=g8_cap,
        description=(
            f"affordability={gate_inputs.affordability:.2f} < 0.40 "
            f"or antitrust_risk_high={gate_inputs.antitrust_risk_high} "
            f"or {integration_desc}: "
            f"composite ≤ {g8_cap}"
        ),
    ))

    # Apply most restrictive cap
    if active_caps:
        binding_cap = min(active_caps)
        final_score = round(_clamp(min(pre_gate_score, binding_cap)), 6)
    else:
        binding_cap = None
        final_score = round(_clamp(pre_gate_score), 6)

    return final_score, gate_results, binding_cap


# ---------------------------------------------------------------------------
# Classification and narrative
# ---------------------------------------------------------------------------

def _classify_final_score(
    final_score: float,
    buckets: DriverBucketResult,
    active_gate_ids: list[str],
) -> str:
    if "G1" in active_gate_ids:
        return "Broken asset — pass"
    if "G2" in active_gate_ids and final_score < 0.45:
        return "No right-to-win — pass"
    if buckets.near_term_transaction_possible and final_score >= 0.65:
        return "Active BD pursuit"
    if buckets.near_term_transaction_possible and final_score >= 0.50:
        return "Opportunistic outreach"
    if final_score >= 0.55 and not active_gate_ids:
        return "Begin relationship / monitor catalyst"
    if final_score >= 0.45:
        return "Strategic watch"
    return "Pass"


def _build_interpretation(
    buckets: DriverBucketResult,
    active_gate_ids: list[str],
    pre_gate_score: float,
    final_score: float,
) -> str:
    parts: list[str] = []

    if buckets.near_term_transaction_possible:
        parts.append(
            f"Transaction setup is {buckets.strength_classification.lower()} "
            f"with {buckets.active_bucket_count} active driver buckets "
            f"(strength={buckets.driver_strength_score:.2f})."
        )
    else:
        if buckets.active_bucket_count == 0:
            parts.append("No transaction drivers are active. Strategic watch only.")
        else:
            parts.append(
                f"Only {buckets.active_bucket_count} driver bucket(s) active "
                f"(need ≥2 at strength ≥0.60 for near-term transaction thesis)."
            )

    if active_gate_ids:
        gate_str = ", ".join(active_gate_ids)
        delta = round(pre_gate_score - final_score, 2)
        parts.append(
            f"Gates [{gate_str}] reduced score by {delta:.2f} "
            f"({pre_gate_score:.2f} → {final_score:.2f})."
        )
    else:
        parts.append(
            f"No institutional gates triggered. Score maintained at {final_score:.2f}."
        )

    # Active bucket highlights
    active = [b for b in buckets.buckets.values() if b.active]
    if active:
        highlights = ", ".join(f"{b.name}:{b.strength:.2f}" for b in active)
        parts.append(f"Active buckets: {highlights}.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_layer3(
    pre_gate_score: float,
    driver_inputs: DriverBucketInputs,
    gate_inputs: GateInputs,
    target_name: str = "Unknown",
    acquirer_id: Optional[str] = None,
) -> Layer3Output:
    """Layer 3 Deal Realism Engine.

    Takes the Layer 2 BD Action Score (pre_gate_score), evaluates all six
    transaction driver buckets, applies 8 institutional gates using the
    most-restrictive-cap rule, and returns a full Layer3Output.

    Args:
        pre_gate_score: Layer 2 bd_action_score (0–1).
        driver_inputs: Raw sub-scores for the six driver buckets.
        gate_inputs: Parameters for all 8 institutional gates.
        target_name: Display name of the target company.
        acquirer_id: Identifier of the acquirer being evaluated.

    Returns:
        Layer3Output with final_score, classification, gate diagnostics,
        driver bucket details, and interpretation text.
    """
    pre_gate_score = _clamp(pre_gate_score)

    # Step 1: compute driver buckets
    buckets = compute_driver_buckets(driver_inputs)

    # Step 2: apply gate system
    final_score, gate_results, binding_cap = _evaluate_gates(
        pre_gate_score, buckets, gate_inputs
    )

    active_gate_ids = [g.gate_id for g in gate_results if g.triggered]

    # Step 3: classify
    classification = _classify_final_score(final_score, buckets, active_gate_ids)

    # Step 4: narrative
    interpretation = _build_interpretation(
        buckets, active_gate_ids, pre_gate_score, final_score
    )

    # Derive G8 integration cap diagnostics for the output
    adj_penalty = gate_inputs.adjusted_integration_penalty
    g8_result = next((g for g in gate_results if g.gate_id == "G8"), None)
    integration_cap = g8_result.cap_applied if g8_result and g8_result.triggered else None

    return Layer3Output(
        target_name=target_name,
        acquirer_id=acquirer_id,
        pre_gate_score=round(pre_gate_score, 6),
        final_score=final_score,
        most_restrictive_cap=binding_cap,
        classification=classification,
        active_gate_ids=active_gate_ids,
        gate_results=gate_results,
        driver_buckets=buckets,
        near_term_transaction_possible=buckets.near_term_transaction_possible,
        interpretation=interpretation,
        adjusted_integration_penalty=adj_penalty,
        integration_cap_applied=integration_cap,
    )
