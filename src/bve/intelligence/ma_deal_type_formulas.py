"""
Deal-Type Formula Scoring Engine — 0B overlay layer.

Six canonical formulas (A–F) compute a deal-type-specific quality score for each
eligible target.  The scores are then blended using the normalized weight vector
produced by DealTypeClassification so that multi-bucket targets receive a weighted
composite rather than a single-bucket approximation.

Architecture position:
  Layer 0 0B (classify) → THIS MODULE (score per type) → Layer 4 (routing + overlay)

Gate primacy: this module produces advisory overlay scores only.  Layer 3 gate caps
and Layer 0 hard-exclusions cannot be overridden by formula output.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from bve.intelligence.deal_type_classification import DealType


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class DealTypeFormulaInput(BaseModel):
    """Flat signal bag consumed by all six formula functions.

    Fields map directly to existing schema (AssetQualityInputs, StrategicFitInputs,
    TransactionTimingInputs, DealFeasibilityInputs) plus deal-type-specific signals
    that may not be present for every target.  Conservative defaults (0.40–0.50) are
    used when a signal is absent and recorded in ``data_gaps``.
    """
    model_config = ConfigDict(frozen=True)

    # ── Base asset quality (from AssetQualityInputs) ──────────────────────────
    clinical_evidence: float = Field(default=0.50, ge=0.0, le=1.0)
    differentiation: float = Field(default=0.50, ge=0.0, le=1.0)
    regulatory_path: float = Field(default=0.50, ge=0.0, le=1.0)
    ip_durability: float = Field(default=0.50, ge=0.0, le=1.0)
    cmc_feasibility: float = Field(default=0.50, ge=0.0, le=1.0)
    commercial_meaningfulness: float = Field(default=0.50, ge=0.0, le=1.0)

    # ── Pipeline / portfolio signals ───────────────────────────────────────────
    product_count: int = Field(default=1, ge=0,
        description="Number of distinct products in the pipeline")
    indication_count: int = Field(default=1, ge=0,
        description="Number of indications pursued across all products")

    # ── Acquirer strategic fit ─────────────────────────────────────────────────
    acquirer_ta_fit: float = Field(default=0.50, ge=0.0, le=1.0,
        description="Therapeutic-area alignment with the acquirer (from StrategicFitInputs.ta_fit)")

    # ── Platform signals ───────────────────────────────────────────────────────
    is_platform_company: bool = Field(default=False)
    platform_validated: bool = Field(default=False,
        description="True when platform has generated ≥1 clinical PoC dataset")
    platform_breadth: float = Field(default=0.40, ge=0.0, le=1.0,
        description="Breadth and tractability of the platform technology")

    # ── Commercial franchise signals ───────────────────────────────────────────
    approved_revenue_share: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Fraction of enterprise value attributable to approved-product revenue")
    salesforce_required: bool = Field(default=False,
        description="True when a primary-care or specialty salesforce is needed")
    revenue_durability: float = Field(default=0.50, ge=0.0, le=1.0,
        description="Expected durability of approved revenue (patent, LOE timing, etc.)")

    # ── Licensing / partnership signals ────────────────────────────────────────
    has_existing_partnership: bool = Field(default=False)
    asset_rights_scope: str = Field(default="owned",
        description="'owned', 'licensed_in', 'co_owned', or 'out_licensed'")
    royalty_stack_rate: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Cumulative royalty encumbrance on lead asset cash flows")

    # ── Distress / optionality signals ─────────────────────────────────────────
    financing_pressure_high: bool = Field(default=False)
    lead_asset_quality_low: bool = Field(default=False,
        description="True when lead asset has weak/failed clinical data")
    months_cash_runway: float = Field(default=24.0, ge=0.0,
        description="Estimated cash runway in months")
    catalyst_within_90_days: bool = Field(default=False,
        description="True when a near-term binary catalyst is within 90 days")

    # ── Blending weights (from DealTypeClassification.deal_type_weights) ───────
    deal_type_weights: dict[str, float] = Field(default_factory=dict,
        description="Normalized weight vector from Layer 0 0B classification")


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class DealTypeFormulaScore(BaseModel):
    """Score for a single deal-type formula."""
    model_config = ConfigDict(frozen=True)

    deal_type: str
    raw_score: float = Field(..., ge=0.0, le=1.0,
        description="Unweighted formula score for this deal type")
    weighted_score: float = Field(..., ge=0.0, le=1.0,
        description="raw_score × deal_type_weight")
    weight: float = Field(..., ge=0.0, le=1.0,
        description="Weight assigned to this deal type by Layer 0 0B")
    components: dict[str, float] = Field(default_factory=dict,
        description="Intermediate signal values used by the formula")
    rationale: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)


class DealTypeOverlayResult(BaseModel):
    """Full deal-type overlay produced by compute_deal_type_overlay()."""
    model_config = ConfigDict(frozen=True)

    primary_deal_type: str
    secondary_deal_types: list[str] = Field(default_factory=list)
    deal_type_weights: dict[str, float] = Field(default_factory=dict)
    formula_scores: list[DealTypeFormulaScore] = Field(default_factory=list)
    blended_deal_type_score: float = Field(..., ge=0.0, le=1.0,
        description="Weighted sum of active formula scores — the overlay signal")
    confidence: float = Field(..., ge=0.0, le=1.0,
        description="Confidence penalised for data gaps")
    rationale: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _base_target_quality(inp: DealTypeFormulaInput) -> float:
    """Equally-weighted mean of the six AssetQualityInputs sub-scores."""
    return (
        inp.clinical_evidence
        + inp.differentiation
        + inp.regulatory_path
        + inp.ip_durability
        + inp.cmc_feasibility
        + inp.commercial_meaningfulness
    ) / 6.0


# ---------------------------------------------------------------------------
# Formula A — Single-Asset Takeout
# ---------------------------------------------------------------------------

def score_single_asset(inp: DealTypeFormulaInput, weight: float) -> DealTypeFormulaScore:
    """Formula A: lead-asset rNPV driven by clinical quality + IP durability + concentration.

    Final = 0.50 × base_quality + 0.30 × lead_concentration + 0.20 × regulatory_path
    """
    base_quality = _base_target_quality(inp)

    # Lead concentration: penalty when product count > 1 (asset is not truly single-asset)
    lead_concentration = max(0.0, 1.0 - 0.20 * max(0, inp.product_count - 1))
    lead_concentration = min(1.0, lead_concentration)

    raw = (
        0.50 * base_quality
        + 0.30 * lead_concentration
        + 0.20 * inp.regulatory_path
    )
    raw = min(1.0, max(0.0, raw))

    gaps: list[str] = []
    rationale = [
        f"base_quality={base_quality:.2f}",
        f"lead_concentration={lead_concentration:.2f} (product_count={inp.product_count})",
        f"regulatory_path={inp.regulatory_path:.2f}",
    ]

    return DealTypeFormulaScore(
        deal_type=DealType.SINGLE_ASSET_TAKEOUT.value,
        raw_score=raw,
        weighted_score=raw * weight,
        weight=weight,
        components={
            "base_quality": base_quality,
            "lead_concentration": lead_concentration,
            "regulatory_path": inp.regulatory_path,
        },
        rationale=rationale,
        data_gaps=gaps,
    )


# ---------------------------------------------------------------------------
# Formula B — Pipeline Portfolio Takeout
# ---------------------------------------------------------------------------

def score_pipeline_portfolio(inp: DealTypeFormulaInput, weight: float) -> DealTypeFormulaScore:
    """Formula B: portfolio breadth × TA coherence × base asset quality.

    Final = 0.40 × base_quality + 0.35 × breadth + 0.25 × acquirer_ta_fit
    """
    base_quality = _base_target_quality(inp)

    product_norm = min(1.0, inp.product_count / 5.0)
    indication_norm = min(1.0, inp.indication_count / 4.0)
    breadth = 0.50 * product_norm + 0.50 * indication_norm

    raw = (
        0.40 * base_quality
        + 0.35 * breadth
        + 0.25 * inp.acquirer_ta_fit
    )
    raw = min(1.0, max(0.0, raw))

    gaps: list[str] = []
    if inp.acquirer_ta_fit == 0.50 and not inp.deal_type_weights:
        gaps.append("acquirer_ta_fit: using conservative default 0.50")

    rationale = [
        f"base_quality={base_quality:.2f}",
        f"breadth={breadth:.2f} ({inp.product_count} products, {inp.indication_count} indications)",
        f"acquirer_ta_fit={inp.acquirer_ta_fit:.2f}",
    ]

    return DealTypeFormulaScore(
        deal_type=DealType.PIPELINE_PORTFOLIO_TAKEOUT.value,
        raw_score=raw,
        weighted_score=raw * weight,
        weight=weight,
        components={
            "base_quality": base_quality,
            "breadth": breadth,
            "acquirer_ta_fit": inp.acquirer_ta_fit,
        },
        rationale=rationale,
        data_gaps=gaps,
    )


# ---------------------------------------------------------------------------
# Formula C — Platform Acquisition
# ---------------------------------------------------------------------------

def score_platform(inp: DealTypeFormulaInput, weight: float) -> DealTypeFormulaScore:
    """Formula C: platform credibility × validation bonus × base quality.

    Final = 0.45 × base_quality + 0.35 × platform_breadth + 0.20 × validation_bonus
    """
    base_quality = _base_target_quality(inp)
    validation_bonus = 0.20 if inp.platform_validated else 0.0
    # When platform is not validated, redistribute weight to breadth
    breadth_weight = 0.55 if not inp.platform_validated else 0.35
    quality_weight = 0.45

    raw = (
        quality_weight * base_quality
        + breadth_weight * inp.platform_breadth
        + validation_bonus
    )
    raw = min(1.0, max(0.0, raw))

    gaps: list[str] = []
    if inp.platform_breadth == 0.40:
        gaps.append("platform_breadth: using conservative default 0.40")

    rationale = [
        f"base_quality={base_quality:.2f}",
        f"platform_breadth={inp.platform_breadth:.2f}",
        f"platform_validated={inp.platform_validated} (bonus={validation_bonus:.2f})",
    ]

    return DealTypeFormulaScore(
        deal_type=DealType.PLATFORM_ACQUISITION.value,
        raw_score=raw,
        weighted_score=raw * weight,
        weight=weight,
        components={
            "base_quality": base_quality,
            "platform_breadth": inp.platform_breadth,
            "validation_bonus": validation_bonus,
        },
        rationale=rationale,
        data_gaps=gaps,
    )


# ---------------------------------------------------------------------------
# Formula D — Commercial Franchise Acquisition
# ---------------------------------------------------------------------------

def score_commercial_franchise(inp: DealTypeFormulaInput, weight: float) -> DealTypeFormulaScore:
    """Formula D: approved revenue quality × base quality × salesforce value.

    Final = 0.40 × revenue_quality + 0.35 × base_quality + 0.25 × salesforce_value
    """
    base_quality = _base_target_quality(inp)
    revenue_quality = inp.approved_revenue_share * inp.revenue_durability
    salesforce_value = 0.70 if inp.salesforce_required else 0.40

    raw = (
        0.40 * revenue_quality
        + 0.35 * base_quality
        + 0.25 * salesforce_value
    )
    raw = min(1.0, max(0.0, raw))

    gaps: list[str] = []
    if inp.revenue_durability == 0.50:
        gaps.append("revenue_durability: using conservative default 0.50")

    rationale = [
        f"revenue_quality={revenue_quality:.2f} "
        f"(approved_revenue_share={inp.approved_revenue_share:.2f} × durability={inp.revenue_durability:.2f})",
        f"base_quality={base_quality:.2f}",
        f"salesforce_required={inp.salesforce_required} (value={salesforce_value:.2f})",
    ]

    return DealTypeFormulaScore(
        deal_type=DealType.COMMERCIAL_FRANCHISE_ACQUISITION.value,
        raw_score=raw,
        weighted_score=raw * weight,
        weight=weight,
        components={
            "base_quality": base_quality,
            "revenue_quality": revenue_quality,
            "salesforce_value": salesforce_value,
        },
        rationale=rationale,
        data_gaps=gaps,
    )


# ---------------------------------------------------------------------------
# Formula E — Asset License / Partnership
# ---------------------------------------------------------------------------

def score_licensing(inp: DealTypeFormulaInput, weight: float) -> DealTypeFormulaScore:
    """Formula E: rights clarity × base quality × partnership signal.

    Final = 0.40 × base_quality + 0.35 × rights_fit + 0.25 × partnership_signal
    """
    base_quality = _base_target_quality(inp)

    # Encumbrance: royalty stack + rights scope penalty
    scope_penalty = 0.20 if inp.asset_rights_scope == "licensed_in" else 0.0
    encumbrance = min(1.0, inp.royalty_stack_rate + scope_penalty)
    rights_fit = 1.0 - encumbrance

    partnership_signal = 0.70 if inp.has_existing_partnership else 0.35

    raw = (
        0.40 * base_quality
        + 0.35 * rights_fit
        + 0.25 * partnership_signal
    )
    raw = min(1.0, max(0.0, raw))

    gaps: list[str] = []
    if inp.royalty_stack_rate == 0.0 and not inp.has_existing_partnership:
        gaps.append("royalty_stack_rate: no encumbrance data; assuming clean title")

    rationale = [
        f"base_quality={base_quality:.2f}",
        f"rights_fit={rights_fit:.2f} (encumbrance={encumbrance:.2f}, "
        f"scope={inp.asset_rights_scope})",
        f"has_existing_partnership={inp.has_existing_partnership} "
        f"(signal={partnership_signal:.2f})",
    ]

    return DealTypeFormulaScore(
        deal_type=DealType.ASSET_LICENSE_PARTNERSHIP.value,
        raw_score=raw,
        weighted_score=raw * weight,
        weight=weight,
        components={
            "base_quality": base_quality,
            "rights_fit": rights_fit,
            "encumbrance": encumbrance,
            "partnership_signal": partnership_signal,
        },
        rationale=rationale,
        data_gaps=gaps,
    )


# ---------------------------------------------------------------------------
# Formula F — Distressed Optionality
# ---------------------------------------------------------------------------

def score_distress(inp: DealTypeFormulaInput, weight: float) -> DealTypeFormulaScore:
    """Formula F: financial pressure × option value × near-term catalyst.

    Final = 0.45 × pressure_level + 0.35 × optionality + 0.20 × catalyst_signal
    """
    base_quality = _base_target_quality(inp)

    # Pressure: financing pressure flag is the primary signal; runway sharpens it
    if inp.financing_pressure_high:
        runway_mod = max(0.0, 1.0 - inp.months_cash_runway / 24.0)
        pressure_level = min(1.0, 0.65 + 0.35 * runway_mod)
    else:
        pressure_level = max(0.0, 1.0 - inp.months_cash_runway / 36.0) * 0.50

    # Option value: viable asset despite distress situation
    quality_haircut = 0.50 if inp.lead_asset_quality_low else 0.0
    optionality = base_quality * (1.0 - quality_haircut)

    catalyst_signal = 0.80 if inp.catalyst_within_90_days else 0.35

    raw = (
        0.45 * pressure_level
        + 0.35 * optionality
        + 0.20 * catalyst_signal
    )
    raw = min(1.0, max(0.0, raw))

    gaps: list[str] = []
    if inp.months_cash_runway == 24.0:
        gaps.append("months_cash_runway: using default 24 months")

    rationale = [
        f"pressure_level={pressure_level:.2f} "
        f"(financing_pressure_high={inp.financing_pressure_high}, "
        f"runway={inp.months_cash_runway:.0f}mo)",
        f"optionality={optionality:.2f} (base_quality={base_quality:.2f}, "
        f"lead_asset_quality_low={inp.lead_asset_quality_low})",
        f"catalyst_within_90_days={inp.catalyst_within_90_days} "
        f"(signal={catalyst_signal:.2f})",
    ]

    return DealTypeFormulaScore(
        deal_type=DealType.DISTRESSED_OPTIONALITY.value,
        raw_score=raw,
        weighted_score=raw * weight,
        weight=weight,
        components={
            "base_quality": base_quality,
            "pressure_level": pressure_level,
            "optionality": optionality,
            "catalyst_signal": catalyst_signal,
        },
        rationale=rationale,
        data_gaps=gaps,
    )


# ---------------------------------------------------------------------------
# Blending entry point
# ---------------------------------------------------------------------------

_FORMULA_MAP = {
    DealType.SINGLE_ASSET_TAKEOUT: score_single_asset,
    DealType.PIPELINE_PORTFOLIO_TAKEOUT: score_pipeline_portfolio,
    DealType.PLATFORM_ACQUISITION: score_platform,
    DealType.COMMERCIAL_FRANCHISE_ACQUISITION: score_commercial_franchise,
    DealType.ASSET_LICENSE_PARTNERSHIP: score_licensing,
    DealType.DISTRESSED_OPTIONALITY: score_distress,
}

_DEFAULT_WEIGHT = 1.0 / len(_FORMULA_MAP)


def compute_deal_type_overlay(
    inp: DealTypeFormulaInput,
    primary_deal_type: Optional[str] = None,
    secondary_deal_types: Optional[list[str]] = None,
) -> DealTypeOverlayResult:
    """Run all six formulas and blend using deal_type_weights.

    If ``deal_type_weights`` is empty, equal weights are assumed (useful when
    DealTypeClassification is not available or bypassed).

    Gate primacy: blended_deal_type_score is advisory only — caller must enforce
    that Layer 3 caps and Layer 0 hard-exclusions take precedence.
    """
    weights = inp.deal_type_weights
    if not weights:
        weights = {dt.value: _DEFAULT_WEIGHT for dt in DealType}

    formula_scores: list[DealTypeFormulaScore] = []
    all_data_gaps: list[str] = []
    all_rationale: list[str] = []

    for deal_type_enum, fn in _FORMULA_MAP.items():
        w = weights.get(deal_type_enum.value, 0.0)
        fs = fn(inp, w)
        formula_scores.append(fs)
        all_data_gaps.extend(fs.data_gaps)

    # Blended score: weighted sum of raw scores
    blended = sum(fs.raw_score * fs.weight for fs in formula_scores)
    blended = min(1.0, max(0.0, blended))

    # Confidence penalty: 0.05 per distinct data gap
    gap_penalty = min(0.20, len(set(all_data_gaps)) * 0.05)
    confidence = max(0.0, 1.0 - gap_penalty)

    # Derive primary/secondary from weights if not supplied
    sorted_types = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)
    if primary_deal_type is None and sorted_types:
        primary_deal_type = sorted_types[0][0]
    if secondary_deal_types is None:
        secondary_deal_types = [k for k, v in sorted_types[1:] if v >= 0.20]

    all_rationale.append(
        f"blended_score={blended:.3f} from {len(formula_scores)} formula(s)"
    )
    if all_data_gaps:
        all_rationale.append(
            f"confidence_penalty={gap_penalty:.2f} ({len(set(all_data_gaps))} data gap(s))"
        )

    return DealTypeOverlayResult(
        primary_deal_type=primary_deal_type or "",
        secondary_deal_types=secondary_deal_types or [],
        deal_type_weights=weights,
        formula_scores=formula_scores,
        blended_deal_type_score=blended,
        confidence=confidence,
        rationale=all_rationale,
        data_gaps=list(set(all_data_gaps)),
    )
