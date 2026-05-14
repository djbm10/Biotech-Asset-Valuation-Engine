"""Layer 0 — Target Eligibility, Deal-Type Routing, and Data-Quality Gate.

Before M&A scoring, this module determines:
    0A. Whether a target is eligible for analysis (hard exclusion)
    0B. Which deal model to route to (deal-type classification)
    0C. Whether each target-acquirer pair is financially feasible (affordability)
    0D. Asset-control / encumbrance issues that reduce deal value
    0E. Commercial complexity as a function-based integration penalty
    0F. Distress quality guard — cap when distressed target lacks strategic value
    0G. Data confidence grade — how much to trust the model output

Layer 0 does NOT assign M&A probability.  It returns a ``Layer0Result`` that
the scoring layer can consume to:
    - hard-exclude or route a target
    - apply a score multiplier (encumbrance × complexity)
    - apply a probability cap (distress guard)
    - annotate output with data-confidence grade
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CompanyTaxonomy(str, Enum):
    """Taxonomy used to classify a company for M&A eligibility."""
    THERAPEUTICS = "therapeutics"
    DIAGNOSTICS = "diagnostics"
    TOOLS = "tools"
    PLATFORM = "platform"
    LIFE_SCIENCE_SERVICES = "life_science_services"
    ACQUIRER = "acquirer"                     # known large-cap acquirer
    SPAC_SHELL = "spac_shell"                 # SPAC / shell / holding company
    DIVERSIFIED_CONGLOMERATE = "diversified_conglomerate"
    OTHER = "other"


_ELIGIBLE_TAXONOMIES: frozenset[CompanyTaxonomy] = frozenset({
    CompanyTaxonomy.THERAPEUTICS,
    CompanyTaxonomy.DIAGNOSTICS,
    CompanyTaxonomy.TOOLS,
    CompanyTaxonomy.PLATFORM,
    CompanyTaxonomy.LIFE_SCIENCE_SERVICES,
})


class ExclusionCode(str, Enum):
    """Reason a target was hard-excluded by Layer 0 (0A)."""
    NON_BIOTECH_PHARMA = "non_biotech_pharma"
    KNOWN_ACQUIRER = "known_acquirer"
    SELF_ACQUISITION = "self_acquisition"
    SPAC_SHELL = "spac_shell"
    NO_IDENTIFIABLE_ASSET = "no_identifiable_asset"
    PERMANENTLY_IMPAIRED_LEAD = "permanently_impaired_lead"
    INSUFFICIENT_DATA = "insufficient_data"


class DealType(str, Enum):
    """Deal model the target is routed to (0B)."""
    SINGLE_ASSET_TAKEOUT = "single_asset_takeout"
    PIPELINE_PORTFOLIO_TAKEOUT = "pipeline_portfolio_takeout"
    PLATFORM_ACQUISITION = "platform_acquisition"
    COMMERCIAL_FRANCHISE_ACQUISITION = "commercial_franchise_acquisition"
    ASSET_LICENSE_PARTNERSHIP = "asset_license_partnership"
    DISTRESSED_OPTIONALITY = "distressed_optionality"


class AffordabilityBand(str, Enum):
    """Affordability bracket for a single acquirer-target pair (0C)."""
    NO_PENALTY = "no_penalty"       # ratio ≤ 0.50
    MILD_PENALTY = "mild_penalty"   # 0.50 < ratio ≤ 0.85
    SEVERE_PENALTY = "severe_penalty"   # 0.85 < ratio ≤ 1.10
    HARD_FAIL = "hard_fail"         # ratio > 1.10


class DataConfidenceGrade(str, Enum):
    """Data completeness grade (0G)."""
    HIGH = "high"     # score ≥ 0.75 → eligible for ranked output
    MEDIUM = "medium" # 0.50 ≤ score < 0.75 → eligible but flagged
    LOW = "low"       # score < 0.50 → diligence queue only


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class TargetEligibilityInput(BaseModel):
    """All signals needed to run a full Layer 0 assessment for one target."""

    ticker: str
    acquirer_ticker: Optional[str] = None  # populated to enable self-acquisition check

    # --- Company classification ---
    company_taxonomy: CompanyTaxonomy = CompanyTaxonomy.THERAPEUTICS

    # --- Asset profile ---
    lead_asset_present: bool = True
    lead_asset_stage: Optional[str] = None        # "phase_1" … "approved" / "discontinued"
    lead_asset_status: Literal[
        "active", "failed", "discontinued", "safety_blocked"
    ] = "active"
    has_replacement_asset: bool = False            # replacement available if lead impaired
    is_platform_company: bool = False
    platform_validated: bool = False               # validated by deal comps / published data

    # --- Commercial profile ---
    product_count: int = Field(default=1, ge=0)
    indication_count: int = Field(default=1, ge=0)
    approved_revenue_share: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    revenue_concentration: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Share of revenue from top product (1.0 = single-product).",
    )
    salesforce_required: bool = False
    manufacturing_complexity: Literal["low", "medium", "high"] = "low"
    geographic_complexity: Literal["local", "regional", "global"] = "local"
    payer_access_complexity: Literal["low", "medium", "high"] = "low"

    # --- Financials (used for affordability and data confidence) ---
    market_cap_millions: Optional[float] = Field(default=None, ge=0.0)
    enterprise_value_millions: Optional[float] = None  # may be negative (net cash > EV)

    # --- Asset ownership / encumbrances (0D) ---
    asset_rights_scope: Literal[
        "global", "regional_split", "licensed_in", "unknown"
    ] = "global"
    has_existing_partnership: bool = False
    has_right_of_first_refusal: bool = False
    royalty_stack_rate: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Cumulative royalty obligation rate (e.g. 0.18 = 18%).",
    )
    has_co_development_obligation: bool = False
    has_ip_dispute: bool = False
    has_manufacturing_dependency: bool = False

    # --- Distress signals (0F) ---
    financing_pressure_high: bool = False
    lead_asset_quality_low: bool = False

    # --- Data completeness flags (0G) — True when field is known / populated ---
    has_market_cap: bool = False
    has_enterprise_value: bool = False
    has_cash_debt: bool = False
    has_quarterly_burn: bool = False
    has_revenue_mix: bool = False
    has_asset_ownership_data: bool = False
    has_clinical_stage: bool = False
    has_trial_status: bool = False
    has_partner_rights_data: bool = False
    has_patent_loe_data: bool = False
    has_acquirer_profile_data: bool = False


class AcquirerCapacityInput(BaseModel):
    """Financial capacity of one potential acquirer for the affordability gate."""

    acquirer_id: str
    cash_available_millions: float = Field(ge=0.0)
    estimated_debt_capacity_millions: float = Field(ge=0.0, default=0.0)
    realistic_stock_component_millions: float = Field(ge=0.0, default=0.0)
    minimum_balance_buffer_millions: float = Field(ge=0.0, default=0.0)
    expected_takeout_premium: float = Field(ge=0.0, le=2.0, default=0.35)


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class AffordabilityResult(BaseModel):
    """Affordability assessment for one acquirer-target pair (0C)."""
    model_config = ConfigDict(frozen=True)

    acquirer_id: str
    expected_acquisition_cost_millions: float
    deal_capacity_millions: float
    affordability_ratio: float
    band: AffordabilityBand
    score_multiplier: float   # 1.0 → 0.90 → 0.60 → 0.0

    @property
    def is_hard_fail(self) -> bool:
        return self.band == AffordabilityBand.HARD_FAIL


class EncumbranceFlags(BaseModel):
    """Asset-control and encumbrance issues (0D)."""
    model_config = ConfigDict(frozen=True)

    asset_rights_scope: Literal["global", "regional_split", "licensed_in", "unknown"]
    has_existing_partnership: bool
    has_right_of_first_refusal: bool
    royalty_stack_high: bool          # stack > 15%
    has_co_development_obligation: bool
    has_ip_dispute: bool
    has_manufacturing_dependency: bool
    penalty_multiplier: float = Field(ge=0.0, le=1.0)   # 1.0 = no penalty
    encumbrance_codes: list[str]


class CommercialComplexityScore(BaseModel):
    """Function-based integration complexity score (0E)."""
    model_config = ConfigDict(frozen=True)

    complexity_score: float = Field(ge=0.0, le=1.0)  # 0 = simple, 1 = complex
    penalty_multiplier: float = Field(ge=0.0, le=1.0) # applied to M&A score
    components: dict[str, float]
    notes: list[str]


class DistressGuard(BaseModel):
    """Cap guard applied when distress has no strategic backing (0F)."""
    model_config = ConfigDict(frozen=True)

    guard_active: bool
    mna_probability_cap: Optional[float] = None
    reason_code: Optional[str] = None


class DataConfidenceResult(BaseModel):
    """Data completeness grade and output eligibility (0G)."""
    model_config = ConfigDict(frozen=True)

    grade: DataConfidenceGrade
    score: float = Field(ge=0.0, le=1.0)
    missing_fields: list[str]
    eligible_for_ranked_output: bool   # HIGH or MEDIUM
    eligible_for_diligence_queue: bool # MEDIUM or LOW


class Layer0Result(BaseModel):
    """Complete Layer 0 M&A eligibility assessment output.

    Consult ``passes_hard_exclusion`` first; if False, the target should not
    enter the M&A scoring pipeline.  ``score_multiplier`` and ``score_cap``
    carry the structural adjustments that the scorer should apply even when
    the target passes.
    """
    model_config = ConfigDict(frozen=True)

    # 0A — hard exclusion
    passes_hard_exclusion: bool
    exclusion_code: Optional[ExclusionCode] = None
    exclusion_reason: Optional[str] = None

    # 0B — deal-type routing (None when excluded)
    deal_type: Optional[DealType] = None
    deal_type_routing_note: str = ""

    # 0C — per-acquirer affordability
    affordability: list[AffordabilityResult] = Field(default_factory=list)

    # 0D — encumbrance
    encumbrance: EncumbranceFlags

    # 0E — commercial complexity
    commercial_complexity: CommercialComplexityScore

    # 0F — distress guard
    distress_guard: DistressGuard

    # 0G — data confidence
    data_confidence: DataConfidenceResult

    # Combined score modifiers (applied regardless of exclusion status)
    score_cap: Optional[float] = None    # None = no cap; else clamp mna_probability
    score_multiplier: float = 1.0        # encumbrance × complexity penalty
    layer0_notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 0C — Affordability band configuration
# ---------------------------------------------------------------------------

# (upper_bound_inclusive, band, score_multiplier)
_AFFORDABILITY_BANDS: list[tuple[float, AffordabilityBand, float]] = [
    (0.50, AffordabilityBand.NO_PENALTY, 1.00),
    (0.85, AffordabilityBand.MILD_PENALTY, 0.90),
    (1.10, AffordabilityBand.SEVERE_PENALTY, 0.60),
    (float("inf"), AffordabilityBand.HARD_FAIL, 0.00),
]


def _affordability_band(ratio: float) -> tuple[AffordabilityBand, float]:
    for upper, band, mult in _AFFORDABILITY_BANDS:
        if ratio <= upper:
            return band, mult
    return AffordabilityBand.HARD_FAIL, 0.00


# ---------------------------------------------------------------------------
# 0G — Data confidence field weights
# ---------------------------------------------------------------------------

_DATA_CONFIDENCE_FIELDS: dict[str, float] = {
    "has_market_cap":           0.12,
    "has_enterprise_value":     0.12,
    "has_cash_debt":            0.10,
    "has_quarterly_burn":       0.08,
    "has_revenue_mix":          0.08,
    "has_asset_ownership_data": 0.09,
    "has_clinical_stage":       0.12,
    "has_trial_status":         0.09,
    "has_partner_rights_data":  0.07,
    "has_patent_loe_data":      0.07,
    "has_acquirer_profile_data": 0.06,
}
# Weights must sum to 1.0 (verified at module import)
assert abs(sum(_DATA_CONFIDENCE_FIELDS.values()) - 1.0) < 1e-9, "weight sum mismatch"

_DATA_CONFIDENCE_HIGH_THRESHOLD = 0.75
_DATA_CONFIDENCE_MEDIUM_THRESHOLD = 0.50


# ---------------------------------------------------------------------------
# 0D — Encumbrance penalty table
# ---------------------------------------------------------------------------

_ENCUMBRANCE_PENALTIES: dict[str, float] = {
    "regional_rights_split":    0.10,
    "licensed_in_rights":       0.08,
    "right_of_first_refusal":   0.12,
    "royalty_stack_high":       0.12,
    "co_development_obligation": 0.08,
    "ip_dispute":               0.25,
    "manufacturing_dependency": 0.10,
}

_ROYALTY_STACK_HIGH_THRESHOLD = 0.15   # 15% cumulative stack is considered "high"
_ENCUMBRANCE_FLOOR = 0.20              # minimum penalty_multiplier (floor)


# ---------------------------------------------------------------------------
# 0E — Commercial complexity component weights and scorers
# ---------------------------------------------------------------------------

_COMPLEXITY_WEIGHTS: dict[str, float] = {
    "product_count":    0.20,
    "indication_count": 0.12,
    "revenue_dispersion": 0.10,
    "salesforce":       0.15,
    "manufacturing":    0.18,
    "geography":        0.12,
    "payer_access":     0.13,
}


def _product_count_complexity(n: int) -> float:
    if n <= 1:
        return 0.0
    if n == 2:
        return 0.25
    if n <= 5:
        return 0.50
    if n <= 10:
        return 0.75
    return 1.00


def _indication_count_complexity(n: int) -> float:
    if n <= 1:
        return 0.0
    if n == 2:
        return 0.40
    return 0.80


def _revenue_dispersion_complexity(concentration: Optional[float]) -> float:
    """High concentration (single dominant product) = low complexity."""
    if concentration is None:
        return 0.40   # neutral when unknown
    return round(1.0 - concentration, 6)


_MANUFACTURING_SCORES: dict[str, float] = {"low": 0.0, "medium": 0.45, "high": 1.0}
_GEOGRAPHY_SCORES: dict[str, float] = {"local": 0.0, "regional": 0.40, "global": 1.0}
_PAYER_SCORES: dict[str, float] = {"low": 0.0, "medium": 0.50, "high": 1.0}


# ---------------------------------------------------------------------------
# Section 0A — Hard Exclusion
# ---------------------------------------------------------------------------

def _evaluate_hard_exclusion(
    t: TargetEligibilityInput,
    data_confidence: DataConfidenceResult,
) -> tuple[bool, Optional[ExclusionCode], Optional[str]]:
    """Return (passes, exclusion_code, reason_detail) for 0A hard-exclusion rules.

    Rules are applied in priority order; first match wins.
    """
    # Non-biotech / non-pharma entity (taxonomy-driven, not ticker-driven)
    if t.company_taxonomy not in _ELIGIBLE_TAXONOMIES:
        if t.company_taxonomy == CompanyTaxonomy.ACQUIRER:
            return False, ExclusionCode.KNOWN_ACQUIRER, "taxonomy:known_acquirer"
        if t.company_taxonomy == CompanyTaxonomy.SPAC_SHELL:
            return False, ExclusionCode.SPAC_SHELL, "taxonomy:spac_shell"
        return False, ExclusionCode.NON_BIOTECH_PHARMA, f"taxonomy:{t.company_taxonomy.value}"

    # Self-acquisition check
    if t.acquirer_ticker and t.ticker.upper() == t.acquirer_ticker.upper():
        return False, ExclusionCode.SELF_ACQUISITION, "self_acquisition"

    # No identifiable lead asset or platform
    if not t.lead_asset_present and not t.is_platform_company:
        return False, ExclusionCode.NO_IDENTIFIABLE_ASSET, "no_lead_asset_or_platform"

    # Permanently impaired lead asset with no replacement
    if t.lead_asset_status in ("failed", "discontinued", "safety_blocked"):
        if not t.has_replacement_asset:
            return (
                False,
                ExclusionCode.PERMANENTLY_IMPAIRED_LEAD,
                f"lead_status:{t.lead_asset_status}:no_replacement",
            )

    # Insufficient minimum data
    if data_confidence.grade == DataConfidenceGrade.LOW:
        return False, ExclusionCode.INSUFFICIENT_DATA, "data_confidence:low"

    return True, None, None


# ---------------------------------------------------------------------------
# Section 0B — Deal-Type Classification
# ---------------------------------------------------------------------------

def _classify_deal_type(t: TargetEligibilityInput) -> tuple[DealType, str]:
    """Route target to the correct deal model. Returns (deal_type, routing_note).

    Replaces the old ``approved_revenue_share > 50% = hard fail`` rule:
    commercial companies are valid acquisition targets — they are simply
    routed to the commercial_franchise_acquisition model instead of the
    pipeline M&A model.
    """
    # Platform acquisition: value tied to technology platform, not one drug
    if t.is_platform_company and t.platform_validated:
        return DealType.PLATFORM_ACQUISITION, "platform_validated"

    # Commercial franchise: approved revenue dominant
    if t.approved_revenue_share is not None and t.approved_revenue_share > 0.50:
        return (
            DealType.COMMERCIAL_FRANCHISE_ACQUISITION,
            f"approved_revenue_share:{t.approved_revenue_share:.0%}",
        )

    # Distressed optionality: financial pressure + uncertain asset quality
    if t.financing_pressure_high and t.lead_asset_quality_low:
        return DealType.DISTRESSED_OPTIONALITY, "financing_pressure_high:lead_quality_low"

    # Pipeline portfolio: multiple distinct clinical assets in same TA/modality
    if t.product_count >= 3 and t.indication_count >= 2:
        return DealType.PIPELINE_PORTFOLIO_TAKEOUT, f"product_count:{t.product_count}"

    # Asset license / partnership: attractive asset, full takeout unlikely
    if (
        t.has_existing_partnership
        and t.enterprise_value_millions is not None
        and t.enterprise_value_millions < 500.0
    ):
        return DealType.ASSET_LICENSE_PARTNERSHIP, "existing_partnership:ev<500M"

    # Default: single-asset clinical-stage takeout
    return DealType.SINGLE_ASSET_TAKEOUT, "default:single_lead_asset"


# ---------------------------------------------------------------------------
# Section 0C — Pair-Specific Affordability Gate
# ---------------------------------------------------------------------------

def _evaluate_affordability(
    target_ev_millions: Optional[float],
    acquirers: list[AcquirerCapacityInput],
) -> list[AffordabilityResult]:
    """Compute per-acquirer affordability.  Returns empty list when EV is unknown."""
    if target_ev_millions is None:
        return []

    results: list[AffordabilityResult] = []
    for acq in acquirers:
        deal_capacity = max(
            acq.cash_available_millions
            + acq.estimated_debt_capacity_millions
            + acq.realistic_stock_component_millions
            - acq.minimum_balance_buffer_millions,
            0.0,
        )
        expected_cost = target_ev_millions * (1.0 + acq.expected_takeout_premium)
        ratio = expected_cost / deal_capacity if deal_capacity > 0.0 else float("inf")
        band, mult = _affordability_band(ratio)

        results.append(AffordabilityResult(
            acquirer_id=acq.acquirer_id,
            expected_acquisition_cost_millions=round(expected_cost, 2),
            deal_capacity_millions=round(deal_capacity, 2),
            affordability_ratio=round(ratio, 4),
            band=band,
            score_multiplier=mult,
        ))
    return results


# ---------------------------------------------------------------------------
# Section 0D — Asset-Control / Encumbrance Gate
# ---------------------------------------------------------------------------

def _evaluate_encumbrance(t: TargetEligibilityInput) -> EncumbranceFlags:
    """Flag encumbrance issues and compute cumulative penalty multiplier."""
    codes: list[str] = []
    cumulative_penalty = 0.0

    def _penalise(code: str) -> None:
        codes.append(code)
        nonlocal cumulative_penalty
        cumulative_penalty += _ENCUMBRANCE_PENALTIES[code]

    if t.asset_rights_scope == "global":
        codes.append("global_rights:positive")
    elif t.asset_rights_scope == "regional_split":
        _penalise("regional_rights_split")
    elif t.asset_rights_scope == "licensed_in":
        _penalise("licensed_in_rights")
    else:  # unknown
        codes.append("asset_rights_scope:unknown")

    if t.has_right_of_first_refusal:
        _penalise("right_of_first_refusal")

    royalty_stack_high = bool(
        t.royalty_stack_rate is not None
        and t.royalty_stack_rate > _ROYALTY_STACK_HIGH_THRESHOLD
    )
    if royalty_stack_high:
        _penalise("royalty_stack_high")

    if t.has_co_development_obligation:
        _penalise("co_development_obligation")

    if t.has_ip_dispute:
        _penalise("ip_dispute")

    if t.has_manufacturing_dependency:
        _penalise("manufacturing_dependency")

    penalty_multiplier = round(max(1.0 - cumulative_penalty, _ENCUMBRANCE_FLOOR), 6)

    return EncumbranceFlags(
        asset_rights_scope=t.asset_rights_scope,
        has_existing_partnership=t.has_existing_partnership,
        has_right_of_first_refusal=t.has_right_of_first_refusal,
        royalty_stack_high=royalty_stack_high,
        has_co_development_obligation=t.has_co_development_obligation,
        has_ip_dispute=t.has_ip_dispute,
        has_manufacturing_dependency=t.has_manufacturing_dependency,
        penalty_multiplier=penalty_multiplier,
        encumbrance_codes=codes,
    )


# ---------------------------------------------------------------------------
# Section 0E — Commercial Complexity / Integration Penalty
# ---------------------------------------------------------------------------

def _compute_commercial_complexity(t: TargetEligibilityInput) -> CommercialComplexityScore:
    """Score integration complexity; high complexity reduces the score multiplier.

    Unlike the old flat 0.50 multi-product penalty, this function accounts for
    all seven integration dimensions and partially offsets the penalty when the
    target has an established commercial infrastructure (approved_revenue > 50%).
    """
    components: dict[str, float] = {
        "product_count":    _product_count_complexity(t.product_count),
        "indication_count": _indication_count_complexity(t.indication_count),
        "revenue_dispersion": _revenue_dispersion_complexity(t.revenue_concentration),
        "salesforce":       1.0 if t.salesforce_required else 0.0,
        "manufacturing":    _MANUFACTURING_SCORES[t.manufacturing_complexity],
        "geography":        _GEOGRAPHY_SCORES[t.geographic_complexity],
        "payer_access":     _PAYER_SCORES[t.payer_access_complexity],
    }

    complexity_score = round(
        min(sum(components[k] * _COMPLEXITY_WEIGHTS[k] for k in _COMPLEXITY_WEIGHTS), 1.0),
        6,
    )

    # Max penalty is 50% reduction; offset by 40% when approved revenue is high
    # (existing commercial infrastructure reduces integration cost)
    penalty = complexity_score * 0.50
    if t.approved_revenue_share is not None and t.approved_revenue_share > 0.50:
        penalty *= 0.60

    penalty_multiplier = round(max(1.0 - penalty, 0.50), 6)

    notes: list[str] = []
    if complexity_score > 0.60:
        if t.revenue_concentration is not None and t.revenue_concentration > 0.70:
            notes.append("high_complexity_but_concentrated_revenue:manageable")
        else:
            notes.append("high_commercial_complexity:integration_risk")
    if t.salesforce_required and t.manufacturing_complexity == "high":
        notes.append("dual_execution_risk:salesforce_and_complex_manufacturing")

    return CommercialComplexityScore(
        complexity_score=complexity_score,
        penalty_multiplier=penalty_multiplier,
        components=components,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Section 0F — Distress Quality Guard
# ---------------------------------------------------------------------------

_DISTRESS_GUARD_CAP = 0.25


def _evaluate_distress_guard(t: TargetEligibilityInput) -> DistressGuard:
    """Cap M&A probability when a distressed target has no strategic asset value.

    A company in financial distress (high financing pressure) with low-quality
    lead assets AND no validated platform provides little strategic value beyond
    a fire-sale option.  Capping prevents the model from ranking broken biotechs
    highly just because they are cheap.
    """
    if (
        t.financing_pressure_high
        and t.lead_asset_quality_low
        and not t.is_platform_company
    ):
        return DistressGuard(
            guard_active=True,
            mna_probability_cap=_DISTRESS_GUARD_CAP,
            reason_code="distress_without_strategic_asset",
        )
    return DistressGuard(guard_active=False)


# ---------------------------------------------------------------------------
# Section 0G — Data Confidence Scoring
# ---------------------------------------------------------------------------

def _compute_data_confidence(t: TargetEligibilityInput) -> DataConfidenceResult:
    """Grade data completeness and determine output eligibility."""
    score = 0.0
    missing: list[str] = []

    for field_name, weight in _DATA_CONFIDENCE_FIELDS.items():
        if getattr(t, field_name, False):
            score += weight
        else:
            missing.append(field_name[4:])  # strip "has_" prefix for readability

    score = round(min(score, 1.0), 6)

    if score >= _DATA_CONFIDENCE_HIGH_THRESHOLD:
        grade = DataConfidenceGrade.HIGH
    elif score >= _DATA_CONFIDENCE_MEDIUM_THRESHOLD:
        grade = DataConfidenceGrade.MEDIUM
    else:
        grade = DataConfidenceGrade.LOW

    return DataConfidenceResult(
        grade=grade,
        score=score,
        missing_fields=missing,
        eligible_for_ranked_output=grade != DataConfidenceGrade.LOW,
        eligible_for_diligence_queue=grade != DataConfidenceGrade.HIGH,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def evaluate_layer0(
    target: TargetEligibilityInput,
    acquirers: Optional[list[AcquirerCapacityInput]] = None,
) -> Layer0Result:
    """Run all Layer 0 checks for a single target.

    Evaluation order:
        0G (data confidence) → 0A (hard exclusion) → 0D, 0E, 0F (always)
        → 0B, 0C (only when target passes 0A)

    Args:
        target: All eligibility signals for the target company.
        acquirers: Optional list of acquirer capacity records.  When provided,
            a per-pair affordability result is computed for each.

    Returns:
        ``Layer0Result`` with all 7 sub-assessments and combined score modifiers.
    """
    if acquirers is None:
        acquirers = []

    # 0G first — informs 0A (insufficient data exclusion)
    data_confidence = _compute_data_confidence(target)

    # 0A — hard exclusion
    passes, excl_code, excl_reason = _evaluate_hard_exclusion(target, data_confidence)

    # 0D, 0E, 0F — always computed (useful diagnostics even for excluded targets)
    encumbrance = _evaluate_encumbrance(target)
    commercial_complexity = _compute_commercial_complexity(target)
    distress_guard = _evaluate_distress_guard(target)

    # 0B, 0C — only meaningful when target passes hard exclusion
    deal_type: Optional[DealType] = None
    deal_type_note = ""
    affordability: list[AffordabilityResult] = []

    if passes:
        deal_type, deal_type_note = _classify_deal_type(target)
        affordability = _evaluate_affordability(target.enterprise_value_millions, acquirers)

    # Combined score modifiers
    notes: list[str] = []
    combined_multiplier = round(
        encumbrance.penalty_multiplier * commercial_complexity.penalty_multiplier, 6
    )

    score_cap: Optional[float] = None
    if distress_guard.guard_active and distress_guard.mna_probability_cap is not None:
        score_cap = distress_guard.mna_probability_cap
        notes.append(f"distress_guard_cap:{score_cap}")

    # Propagate encumbrance penalty codes (skip positive / informational entries)
    penalty_codes = [
        c for c in encumbrance.encumbrance_codes
        if not c.endswith(":positive") and not c.endswith(":unknown") and "unknown" not in c
    ]
    notes.extend(penalty_codes)
    notes.extend(commercial_complexity.notes)

    return Layer0Result(
        passes_hard_exclusion=passes,
        exclusion_code=excl_code,
        exclusion_reason=excl_reason,
        deal_type=deal_type,
        deal_type_routing_note=deal_type_note,
        affordability=affordability,
        encumbrance=encumbrance,
        commercial_complexity=commercial_complexity,
        distress_guard=distress_guard,
        data_confidence=data_confidence,
        score_cap=score_cap,
        score_multiplier=combined_multiplier,
        layer0_notes=notes,
    )
