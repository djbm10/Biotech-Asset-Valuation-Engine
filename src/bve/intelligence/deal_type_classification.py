"""0B. Deal-Type Classification — multi-label routing layer.

Replaces the old single-bucket ``_classify_deal_type`` in ``ma_eligibility.py``.

Design principle
----------------
Classification does NOT predict whether a deal will happen.
It tells the scoring system **which deal model is allowed to predict the deal**.

A company may fit multiple deal archetypes simultaneously (Revolution Medicines =
pipeline portfolio with platform overlay; Alnylam = commercial franchise with
platform). The old single-label approach forced an artificial choice.  This module
produces a primary type, optional secondary types, per-type weights, modifiers
for nuanced signals, a recommended model, and an audit trail.

Six canonical deal types (no bucket explosion)
-----------------------------------------------
SINGLE_ASSET_TAKEOUT            - one lead asset drives ≥ 70% of value
PIPELINE_PORTFOLIO_TAKEOUT      - multiple distinct clinical programs
PLATFORM_ACQUISITION            - repeatable technology engine is the primary value
COMMERCIAL_FRANCHISE_ACQUISITION- approved-revenue-dominant company
ASSET_LICENSE_PARTNERSHIP       - full takeout unlikely; rights or economics encumbered
DISTRESSED_OPTIONALITY          - value driven by financial pressure / option value

Modifiers (handle nuance instead of new top-level buckets)
-----------------------------------------------------------
LEAD_ASSET_HEAVY          - portfolio/platform co., but one asset drives bulk of value
PIPELINE_IN_A_PRODUCT     - single molecule across multiple indications
PLATFORM_LITE             - platform exists but one lead asset dominates
COMMERCIAL_PIPELINE_HYBRID- meaningful revenue + active mid-stage pipeline
RIGHTS_ENCUMBERED         - licensing / royalty burden materially complicates acquisition
DISTRESS_OVERLAY          - distress signal present even if not the primary driver
HISTORICAL_ONLY           - already acquired; training use only

Recommended models
------------------
LEAD_ASSET_RNPV     - rNPV of lead asset
PORTFOLIO_MNA       - portfolio-weighted rNPV across programs
PLATFORM_FIT        - platform fit / optionality model
COMMERCIAL_SYNERGY  - commercial synergy + franchise valuation
LICENSING           - licensing economics / royalty model
DISTRESS_ADJUSTED   - distress-adjusted option value model
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DealType(str, Enum):
    """Six canonical deal archetypes.  No new buckets — use DealModifier for nuance."""
    SINGLE_ASSET_TAKEOUT = "single_asset_takeout"
    PIPELINE_PORTFOLIO_TAKEOUT = "pipeline_portfolio_takeout"
    PLATFORM_ACQUISITION = "platform_acquisition"
    COMMERCIAL_FRANCHISE_ACQUISITION = "commercial_franchise_acquisition"
    ASSET_LICENSE_PARTNERSHIP = "asset_license_partnership"
    DISTRESSED_OPTIONALITY = "distressed_optionality"


class DealModifier(str, Enum):
    """Nuance flags applied on top of the primary deal type.

    Modifiers prevent bucket explosion: instead of creating
    "commercial_platform_hybrid" as a seventh deal type, we label the company
    COMMERCIAL_FRANCHISE_ACQUISITION + PLATFORM_LITE.
    """
    LEAD_ASSET_HEAVY = "lead_asset_heavy"
    PIPELINE_IN_A_PRODUCT = "pipeline_in_a_product"
    PLATFORM_LITE = "platform_lite"
    COMMERCIAL_PIPELINE_HYBRID = "commercial_pipeline_hybrid"
    RIGHTS_ENCUMBERED = "rights_encumbered"
    DISTRESS_OVERLAY = "distress_overlay"
    HISTORICAL_ONLY = "historical_only"


class RecommendedModel(str, Enum):
    """Scoring model that should evaluate this company."""
    LEAD_ASSET_RNPV = "lead_asset_rnpv_model"
    PORTFOLIO_MNA = "portfolio_mna_model"
    PLATFORM_FIT = "platform_fit_model"
    COMMERCIAL_SYNERGY = "commercial_synergy_model"
    LICENSING = "licensing_model"
    DISTRESS_ADJUSTED = "distress_adjusted_model"


# Model routing: primary deal type → recommended model
_PRIMARY_TO_MODEL: dict[DealType, RecommendedModel] = {
    DealType.SINGLE_ASSET_TAKEOUT:            RecommendedModel.LEAD_ASSET_RNPV,
    DealType.PIPELINE_PORTFOLIO_TAKEOUT:      RecommendedModel.PORTFOLIO_MNA,
    DealType.PLATFORM_ACQUISITION:            RecommendedModel.PLATFORM_FIT,
    DealType.COMMERCIAL_FRANCHISE_ACQUISITION: RecommendedModel.COMMERCIAL_SYNERGY,
    DealType.ASSET_LICENSE_PARTNERSHIP:       RecommendedModel.LICENSING,
    DealType.DISTRESSED_OPTIONALITY:          RecommendedModel.DISTRESS_ADJUSTED,
}


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class DealTypeClassification(BaseModel):
    """Multi-label deal-type classification with weights, modifiers, and routing.

    Fields
    ------
    primary_deal_type
        Deal type with the highest weight; drives model routing.
    secondary_deal_types
        All deal types with weight >= SECONDARY_WEIGHT_THRESHOLD, excluding primary.
    deal_type_weights
        Fractional weight assigned to each of the six DealType values (sum ≈ 1.0).
    modifiers
        Nuance flags that do not create new top-level buckets.
    recommended_model
        Scoring model that should evaluate this company.
    model_routing_reason
        Human-readable explanation of why this model was selected.
    *_value_share fields
        Estimated fractional contribution of each component to total company value.
        None when the field cannot be estimated from available data.
    lead_asset_dependency
        Qualitative assessment of how much value rests on a single asset:
        low / medium / high / very_high.
    licensing_encumbrance
        Degree to which licensing / royalty obligations complicate an acquisition:
        none / low / medium / high.
    distress_flag
        True when financial distress is a material factor.
    confidence
        [0, 1] — confidence in the classification.  Reduced for each data gap.
    rationale
        Ordered list of human-readable classification reasons.
    data_gaps
        Fields that could not be populated; reduces confidence.

    Backward compatibility
    ----------------------
    ``deal_type`` property returns ``primary_deal_type`` so callers that
    consumed the old single-label field continue to work unchanged.
    """
    model_config = ConfigDict(frozen=True)

    primary_deal_type: DealType
    secondary_deal_types: list[DealType] = Field(default_factory=list)

    # Keys are DealType.value strings (JSON-serializable)
    deal_type_weights: dict[str, float] = Field(
        description="Per-deal-type fractional weight; values sum to ≈ 1.0"
    )

    modifiers: list[DealModifier] = Field(default_factory=list)

    recommended_model: RecommendedModel
    model_routing_reason: str

    # Estimated value-share decomposition (all optional — may not be computable)
    lead_asset_value_share: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    pipeline_value_share: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    platform_value_share: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    approved_revenue_value_share: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    licensing_value_share: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    distress_option_value_share: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    lead_asset_dependency: Optional[str] = None   # low / medium / high / very_high
    licensing_encumbrance: Optional[str] = None   # none / low / medium / high
    distress_flag: bool = False

    confidence: float = Field(ge=0.0, le=1.0)
    rationale: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_weights(self) -> "DealTypeClassification":
        w = self.deal_type_weights
        # All six keys must be present
        for dt in DealType:
            if dt.value not in w:
                raise ValueError(f"deal_type_weights missing key: {dt.value!r}")
        # Weights must sum to ~1.0
        total = sum(w.values())
        if abs(total - 1.0) > 0.05:
            raise ValueError(
                f"deal_type_weights sum to {total:.4f}; expected 1.0 ± 0.05"
            )
        # Primary must be the highest weight (or a tie is acceptable)
        max_weight = max(w.values())
        primary_w = w[self.primary_deal_type.value]
        if primary_w < max_weight - 0.05:
            raise ValueError(
                f"primary_deal_type '{self.primary_deal_type.value}' has weight "
                f"{primary_w:.3f} but max weight is {max_weight:.3f}. "
                "Primary must be the highest-weight type (±0.05)."
            )
        return self

    @property
    def deal_type(self) -> DealType:
        """Backward-compatibility alias for primary_deal_type."""
        return self.primary_deal_type

    @property
    def deal_type_routing_note(self) -> str:
        """Backward-compatibility alias for model_routing_reason."""
        return self.model_routing_reason


# ---------------------------------------------------------------------------
# Classification thresholds
# ---------------------------------------------------------------------------

# Primary type thresholds
_THRESH_SINGLE_ASSET_PRIMARY = 0.70       # lead_asset dominates
_THRESH_PIPELINE_PRIMARY = 0.50           # portfolio dominates
_THRESH_PLATFORM_PRIMARY = 0.35           # platform as primary (when highest)
_THRESH_COMMERCIAL_PRIMARY = 0.60         # approved revenue dominates
_THRESH_LICENSING_PRIMARY = 0.50          # licensing/partnership encumbrance dominates
_THRESH_DISTRESS_PRIMARY = 0.50           # distress option value dominates

# Secondary inclusion threshold
_THRESH_SECONDARY = 0.20                  # weight >= this → include as secondary

# Modifier thresholds
_THRESH_LEAD_HEAVY = 0.60                 # lead asset heavy even in portfolio
_THRESH_PLATFORM_LITE = 0.20             # platform signal present but not primary
_THRESH_COMMERCIAL_HYBRID_LO = 0.30      # commercial/pipeline hybrid lower bound
_THRESH_COMMERCIAL_HYBRID_HI = 0.60      # commercial/pipeline hybrid upper bound
_THRESH_RIGHTS_ENCUMBERED_ROYALTY = 0.15 # royalty stack rate above this → encumbered
_THRESH_DISTRESS_OVERLAY = 0.10          # distress signal but not primary

# Confidence penalties per data gap
_CONFIDENCE_PENALTY_PER_GAP = 0.08
_BASE_CONFIDENCE = 0.90


# ---------------------------------------------------------------------------
# Input helper: extract signals from TargetEligibilityInput
# ---------------------------------------------------------------------------

def _extract_signals(t: Any) -> dict[str, Any]:
    """Pull classification-relevant signals from a TargetEligibilityInput.

    Returns a dict of signals.  All values default to safe/conservative
    fallbacks so the classifier can run even with partial data.
    """
    def _get(field: str, default: Any = None) -> Any:
        return getattr(t, field, default)

    return {
        # Platform signals
        "is_platform_company":      bool(_get("is_platform_company", False)),
        "platform_validated":       bool(_get("platform_validated", False)),

        # Revenue / commercial signals
        "approved_revenue_share":   _get("approved_revenue_share"),       # 0–1 or None
        "revenue_concentration":    _get("revenue_concentration"),         # 0–1 or None

        # Pipeline breadth
        "product_count":            int(_get("product_count", 1)),
        "indication_count":         int(_get("indication_count", 1)),

        # Lead asset
        "lead_asset_present":       bool(_get("lead_asset_present", True)),
        "lead_asset_stage":         _get("lead_asset_stage"),
        "lead_asset_status":        _get("lead_asset_status", "active"),

        # Rights / licensing
        "has_existing_partnership": bool(_get("has_existing_partnership", False)),
        "asset_rights_scope":       _get("asset_rights_scope", "global"),
        "royalty_stack_rate":       _get("royalty_stack_rate"),             # 0–1 or None
        "has_right_of_first_refusal": bool(_get("has_right_of_first_refusal", False)),

        # Financial / distress
        "financing_pressure_high":  bool(_get("financing_pressure_high", False)),
        "lead_asset_quality_low":   bool(_get("lead_asset_quality_low", False)),
        "enterprise_value_millions": _get("enterprise_value_millions"),

        # Market / commercial
        "salesforce_required":      bool(_get("salesforce_required", False)),
        "geographic_complexity":    _get("geographic_complexity", "local"),
    }


# ---------------------------------------------------------------------------
# Value share estimator
# ---------------------------------------------------------------------------

def _estimate_value_shares(sig: dict[str, Any]) -> tuple[
    float, float, float, float, float, float, list[str]
]:
    """Estimate (lead_asset, pipeline, platform, approved_revenue, licensing, distress) shares.

    Shares are returned normalised to sum to 1.0.
    Returns a 7-tuple: 6 share floats + list[str] of data_gaps.
    """
    data_gaps: list[str] = []

    # ---- Platform share ----
    if sig["is_platform_company"]:
        platform_raw = 0.55 if sig["platform_validated"] else 0.30
    else:
        platform_raw = 0.0

    # ---- Approved revenue share ----
    if sig["approved_revenue_share"] is not None:
        rev_raw = float(sig["approved_revenue_share"])
    elif sig["lead_asset_stage"] in ("approved", "commercial", "nda_bla", "nda bla"):
        rev_raw = 0.60   # conservative inference for approved-stage companies
        data_gaps.append("approved_revenue_share")
    else:
        rev_raw = 0.0

    # ---- Distress share ----
    if sig["financing_pressure_high"] and sig["lead_asset_quality_low"]:
        distress_raw = 0.40
    elif sig["financing_pressure_high"]:
        distress_raw = 0.15
    else:
        distress_raw = 0.0

    # ---- Licensing share ----
    royalty_rate = sig["royalty_stack_rate"]
    rights_scope = sig["asset_rights_scope"]
    has_partnership = sig["has_existing_partnership"]
    ev = sig["enterprise_value_millions"]

    licensing_raw = 0.0
    if royalty_rate is not None and royalty_rate > _THRESH_RIGHTS_ENCUMBERED_ROYALTY:
        licensing_raw += 0.15
    if rights_scope in ("regional_split", "licensed_in"):
        licensing_raw += 0.10
    if has_partnership and ev is not None and ev < 500.0:
        licensing_raw += 0.20
    if sig["has_right_of_first_refusal"]:
        licensing_raw += 0.05
    licensing_raw = min(licensing_raw, 0.60)

    # ---- Pipeline vs single-asset share (residual) ----
    product_count = sig["product_count"]
    indication_count = sig["indication_count"]
    revenue_concentration = sig["revenue_concentration"]

    # Residual to allocate between pipeline and lead_asset
    residual = max(0.0, 1.0 - platform_raw - rev_raw - distress_raw - licensing_raw)

    if product_count >= 3 and indication_count >= 2:
        # True portfolio
        pipeline_frac = 0.65
    elif indication_count >= 2 and product_count >= 2:
        # Multi-indication single molecule or two distinct assets
        pipeline_frac = 0.45
    elif revenue_concentration is not None:
        # revenue_concentration near 1.0 → single asset; near 0 → portfolio
        pipeline_frac = max(0.0, 1.0 - revenue_concentration) * 0.5
    else:
        data_gaps.append("revenue_concentration")
        # Default conservative: single asset
        pipeline_frac = 0.20

    pipeline_raw = residual * pipeline_frac
    lead_asset_raw = residual * (1.0 - pipeline_frac)

    # ---- Normalise ----
    total = lead_asset_raw + pipeline_raw + platform_raw + rev_raw + licensing_raw + distress_raw
    if total <= 0:
        # Degenerate case — all unknown
        data_gaps.extend(["all_value_shares_unknown"])
        return (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, data_gaps)

    norm = 1.0 / total
    return (
        round(lead_asset_raw * norm, 4),
        round(pipeline_raw * norm, 4),
        round(platform_raw * norm, 4),
        round(rev_raw * norm, 4),
        round(licensing_raw * norm, 4),
        round(distress_raw * norm, 4),
        data_gaps,
    )


# ---------------------------------------------------------------------------
# Modifier computation
# ---------------------------------------------------------------------------

def _compute_modifiers(
    sig: dict[str, Any],
    lead_share: float,
    pipeline_share: float,
    platform_share: float,
    rev_share: float,
    licensing_share: float,
    distress_share: float,
    primary: DealType,
) -> list[DealModifier]:
    mods: list[DealModifier] = []

    # LEAD_ASSET_HEAVY: portfolio or platform primary but one asset dominates
    if primary in (DealType.PIPELINE_PORTFOLIO_TAKEOUT, DealType.PLATFORM_ACQUISITION):
        if lead_share >= _THRESH_LEAD_HEAVY:
            mods.append(DealModifier.LEAD_ASSET_HEAVY)

    # PIPELINE_IN_A_PRODUCT: single molecule in multiple indications
    if sig["indication_count"] >= 2 and sig["product_count"] <= 2:
        mods.append(DealModifier.PIPELINE_IN_A_PRODUCT)

    # PLATFORM_LITE: platform signal present but not primary
    if platform_share >= _THRESH_PLATFORM_LITE and primary != DealType.PLATFORM_ACQUISITION:
        mods.append(DealModifier.PLATFORM_LITE)

    # COMMERCIAL_PIPELINE_HYBRID: meaningful approved revenue + active pipeline
    if _THRESH_COMMERCIAL_HYBRID_LO <= rev_share < _THRESH_COMMERCIAL_HYBRID_HI and pipeline_share >= 0.20:
        mods.append(DealModifier.COMMERCIAL_PIPELINE_HYBRID)

    # RIGHTS_ENCUMBERED: royalty stack or licensed-in rights
    royalty_rate = sig["royalty_stack_rate"]
    if (
        (royalty_rate is not None and royalty_rate > _THRESH_RIGHTS_ENCUMBERED_ROYALTY)
        or sig["asset_rights_scope"] in ("regional_split", "licensed_in")
        or sig["has_right_of_first_refusal"]
    ):
        mods.append(DealModifier.RIGHTS_ENCUMBERED)

    # DISTRESS_OVERLAY: distress present but not primary
    if distress_share >= _THRESH_DISTRESS_OVERLAY and primary != DealType.DISTRESSED_OPTIONALITY:
        mods.append(DealModifier.DISTRESS_OVERLAY)

    return mods


# ---------------------------------------------------------------------------
# Lead-asset dependency level
# ---------------------------------------------------------------------------

def _lead_asset_dependency(lead_share: float) -> str:
    if lead_share >= 0.75:
        return "very_high"
    if lead_share >= 0.55:
        return "high"
    if lead_share >= 0.35:
        return "medium"
    return "low"


def _licensing_encumbrance_level(sig: dict[str, Any]) -> str:
    royalty_rate = sig["royalty_stack_rate"] or 0.0
    rights_scope = sig["asset_rights_scope"]
    rofr = sig["has_right_of_first_refusal"]

    score = 0
    if royalty_rate > 0.20:
        score += 2
    elif royalty_rate > _THRESH_RIGHTS_ENCUMBERED_ROYALTY:
        score += 1
    if rights_scope in ("regional_split", "licensed_in"):
        score += 1
    if rofr:
        score += 1

    if score >= 3:
        return "high"
    if score == 2:
        return "medium"
    if score == 1:
        return "low"
    return "none"


# ---------------------------------------------------------------------------
# Main classification function
# ---------------------------------------------------------------------------

def classify_deal_type(
    t: Any,
    context: Optional[Any] = None,
) -> DealTypeClassification:
    """Classify a target into multi-label deal archetypes.

    Parameters
    ----------
    t : TargetEligibilityInput (or any object with compatible attributes)
        Target eligibility data.  Only fields present on ``t`` are used;
        missing fields default conservatively.
    context : optional
        Reserved for future enrichment (e.g. screen context, comparable deals).
        Currently unused.

    Returns
    -------
    DealTypeClassification
        Multi-label classification with weights, modifiers, recommended model,
        confidence, rationale, and data gaps.
    """
    sig = _extract_signals(t)

    lead_share, pipeline_share, platform_share, rev_share, lic_share, distress_share, data_gaps = (
        _estimate_value_shares(sig)
    )

    rationale: list[str] = []

    # ---- Determine primary deal type ----
    # Build a raw weight vector from share estimates, then pick highest

    weights: dict[str, float] = {
        DealType.SINGLE_ASSET_TAKEOUT.value:            lead_share,
        DealType.PIPELINE_PORTFOLIO_TAKEOUT.value:      pipeline_share,
        DealType.PLATFORM_ACQUISITION.value:            platform_share,
        DealType.COMMERCIAL_FRANCHISE_ACQUISITION.value: rev_share,
        DealType.ASSET_LICENSE_PARTNERSHIP.value:       lic_share,
        DealType.DISTRESSED_OPTIONALITY.value:          distress_share,
    }

    # Normalise weights to sum to exactly 1.0
    total_w = sum(weights.values())
    if total_w > 0:
        weights = {k: round(v / total_w, 4) for k, v in weights.items()}
    # Fix floating-point drift: adjust largest to make sum exactly 1.0
    diff = round(1.0 - sum(weights.values()), 6)
    if diff != 0:
        max_k = max(weights, key=lambda k: weights[k])
        weights[max_k] = round(weights[max_k] + diff, 6)

    # Primary = highest weight
    primary_key = max(weights, key=lambda k: weights[k])
    primary = DealType(primary_key)

    # Rationale for primary
    rationale.append(
        f"primary={primary.value} "
        f"(weight={weights[primary_key]:.2f}, "
        f"lead={lead_share:.2f}, pipeline={pipeline_share:.2f}, "
        f"platform={platform_share:.2f}, revenue={rev_share:.2f}, "
        f"licensing={lic_share:.2f}, distress={distress_share:.2f})"
    )

    # ---- Secondary deal types (weight >= threshold, excluding primary) ----
    secondaries = [
        DealType(k)
        for k, v in sorted(weights.items(), key=lambda x: -x[1])
        if k != primary_key and v >= _THRESH_SECONDARY
    ]
    if secondaries:
        rationale.append(
            f"secondary_types={[s.value for s in secondaries]}"
        )

    # ---- Modifiers ----
    modifiers = _compute_modifiers(
        sig, lead_share, pipeline_share, platform_share,
        rev_share, lic_share, distress_share, primary,
    )
    if modifiers:
        rationale.append(f"modifiers={[m.value for m in modifiers]}")

    # ---- Recommended model ----
    # For distress overlay: if distress is secondary and asset is viable,
    # keep primary model but note distress
    recommended_model = _PRIMARY_TO_MODEL[primary]
    model_routing_reason = (
        f"{primary.value} dominates (weight={weights[primary_key]:.2f})"
        f" → {recommended_model.value}"
    )

    # ---- Lead asset dependency & licensing encumbrance ----
    lead_dep = _lead_asset_dependency(lead_share)
    lic_enc = _licensing_encumbrance_level(sig)

    # ---- Confidence ----
    # Start at base confidence; deduct per data gap
    n_gaps = len(data_gaps)
    confidence = max(0.10, round(_BASE_CONFIDENCE - n_gaps * _CONFIDENCE_PENALTY_PER_GAP, 2))
    if not sig["lead_asset_present"]:
        confidence = max(0.10, confidence - 0.10)
        data_gaps.append("lead_asset_present:False")

    # ---- Distress flag ----
    distress_flag = sig["financing_pressure_high"]

    return DealTypeClassification(
        primary_deal_type=primary,
        secondary_deal_types=secondaries,
        deal_type_weights=weights,
        modifiers=modifiers,
        recommended_model=recommended_model,
        model_routing_reason=model_routing_reason,
        lead_asset_value_share=round(lead_share, 4),
        pipeline_value_share=round(pipeline_share, 4),
        platform_value_share=round(platform_share, 4),
        approved_revenue_value_share=round(rev_share, 4),
        licensing_value_share=round(lic_share, 4),
        distress_option_value_share=round(distress_share, 4),
        lead_asset_dependency=lead_dep,
        licensing_encumbrance=lic_enc,
        distress_flag=distress_flag,
        confidence=confidence,
        rationale=rationale,
        data_gaps=data_gaps,
    )
