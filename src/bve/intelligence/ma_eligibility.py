"""Layer 0 — Target Eligibility, Deal-Type Routing, and Data-Quality Gate.

Before M&A scoring, this module determines:
    0A. Whether a target is eligible for analysis (hard exclusion)
    0B. Which deal model to route to (deal-type classification)
    0C. Whether each target-acquirer pair is financially feasible (affordability)
    0D. Asset-control / encumbrance issues that reduce deal value
    0E. Target-level commercial integration complexity flag (no score penalty at Layer 0)
    0F. Distress quality guard — cap when distressed target lacks strategic value
    0G. Data confidence grade — how much to trust the model output

Layer 0 does NOT assign M&A probability.  It returns a ``Layer0Result`` that
the scoring layer can consume to:
    - hard-exclude or route a target
    - apply a score multiplier (encumbrance penalty only — 0E no longer penalises here)
    - apply a probability cap (distress guard)
    - annotate output with data-confidence grade

0E Design note:
    Layer 0E identifies the target's raw integration complexity and passes it
    downstream.  The buyer-specific integration penalty is computed in Layer 3
    via ``compute_pair_integration_adjustment()`` and applied through G8.
    This prevents double-counting between Layer 0 and Layer 3.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Forward reference for the rich ExclusionAssessment type (imported lazily in
# _evaluate_hard_exclusion to avoid a circular dependency at module load time).
# Typed as Any here so mypy does not need to resolve the deferred import.
ExclusionAssessmentRef = Any
ExclusionStatusRef = Any

# DealType and DealTypeClassification live in deal_type_classification; imported
# here so existing callers (e.g. test_sprint36_ma_layer0) can continue to import
# DealType directly from this module.
from bve.intelligence.deal_type_classification import (  # noqa: E402
    DealType,
    DealTypeClassification,
    classify_deal_type,
)

# 0D — Asset-Control / Encumbrance Gate (6-bucket system)
from bve.intelligence.ma_asset_control import (  # noqa: E402
    AssetControlResult,
    compute_asset_control,
    asset_control_from_target,
)

# 0E — Target-Level Commercial Integration Complexity Flag
from bve.intelligence.ma_integration_complexity import (  # noqa: E402
    TargetIntegrationComplexityFlag,
    compute_target_integration_complexity,
)

# Backward-compatibility alias — code that imports CommercialComplexityScore from
# this module continues to work.  The new model has richer fields (see 0E docs).
CommercialComplexityScore = TargetIntegrationComplexityFlag

# Backward-compatibility alias — existing code that imports EncumbranceFlags from
# this module (including test_sprint36_ma_layer0) continues to work unchanged.
EncumbranceFlags = AssetControlResult


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
    """Reason a target was hard-excluded by Layer 0 (0A).

    Legacy codes are preserved for backward compatibility.
    New codes (ALREADY_ACQUIRED, ROUTED_TO_OTHER_MODEL) were added when 0A
    was replaced by the structured 11-gate ExclusionEngine in
    ``bve.intelligence.exclusions``.
    """
    NON_BIOTECH_PHARMA = "non_biotech_pharma"
    KNOWN_ACQUIRER = "known_acquirer"
    SELF_ACQUISITION = "self_acquisition"
    SPAC_SHELL = "spac_shell"
    NO_IDENTIFIABLE_ASSET = "no_identifiable_asset"
    PERMANENTLY_IMPAIRED_LEAD = "permanently_impaired_lead"
    INSUFFICIENT_DATA = "insufficient_data"
    # Added with 11-gate exclusion engine
    ALREADY_ACQUIRED = "already_acquired"          # → HISTORICAL_ONLY in gate engine
    ROUTED_TO_OTHER_MODEL = "routed_to_other_model"  # → ROUTE_TO_OTHER_MODEL in gate engine


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
    """Financial capacity of one potential acquirer for the affordability gate (0C).

    Two paths for the stock component:

    **Formula path** (preferred — set ``acquirer_market_cap_millions``):
        realistic_stock_component =
            acquirer_market_cap_millions
            × max_stock_issuance_pct
            × stock_quality_multiplier

        ``stock_quality_multiplier`` is computed from P/B, volatility, and dilution
        tolerance unless supplied directly.

    **Pre-computed path** (backward compat — leave ``acquirer_market_cap_millions`` as None):
        ``realistic_stock_component_millions`` is used as-is.
    """

    acquirer_id: str
    cash_available_millions: float = Field(ge=0.0)
    estimated_debt_capacity_millions: float = Field(ge=0.0, default=0.0)
    minimum_balance_buffer_millions: float = Field(ge=0.0, default=0.0)
    expected_takeout_premium: float = Field(ge=0.0, le=2.0, default=0.35)

    # ── Pre-computed path (backward compat) ──────────────────────────────────
    realistic_stock_component_millions: float = Field(ge=0.0, default=0.0,
        description="Pre-computed stock deal capacity; used when acquirer_market_cap_millions "
                    "is not provided.")

    # ── Formula path: stock-deal realism ─────────────────────────────────────
    acquirer_market_cap_millions: Optional[float] = Field(default=None, ge=0.0,
        description="Acquirer market cap; when set, stock component is computed via formula.")
    max_stock_issuance_pct: float = Field(default=0.10, ge=0.0, le=1.0,
        description="Maximum fraction of market cap the acquirer can realistically issue "
                    "as deal consideration without triggering excessive dilution.")

    # Stock quality sub-signals (used to auto-compute stock_quality_multiplier)
    acquirer_price_to_book: Optional[float] = Field(default=None, ge=0.0,
        description="Acquirer P/B ratio; premium valuation → better stock currency.")
    acquirer_stock_volatility_pct: Optional[float] = Field(default=None, ge=0.0,
        description="Annualised stock volatility %; high vol → target demands cash premium.")
    investor_dilution_tolerance: float = Field(default=0.50, ge=0.0, le=1.0,
        description="How much dilution acquirer shareholders will accept (0=intolerant, "
                    "1=fully tolerant).  Base of the stock quality multiplier.")

    # Override: skip auto-computation and use this value directly
    stock_quality_multiplier: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="Explicit stock quality multiplier in [0, 1]. When provided, "
                    "P/B and volatility sub-signals are ignored.")


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class AffordabilityResult(BaseModel):
    """Affordability assessment for one acquirer-target pair (0C).

    IMPORTANT — pair-level scope: a HARD_FAIL here removes only this
    specific acquirer-target pair from consideration.  The target remains
    eligible for all other acquirers with sufficient capacity.
    """
    model_config = ConfigDict(frozen=True)

    acquirer_id: str
    expected_acquisition_cost_millions: float
    deal_capacity_millions: float
    affordability_ratio: float
    band: AffordabilityBand
    score_multiplier: float   # 1.0 → 0.90 → 0.60 → 0.0

    # Stock component breakdown
    stock_component_millions: float = Field(default=0.0, ge=0.0,
        description="Effective stock deal capacity used in this pair (computed or pre-supplied).")
    stock_quality_multiplier_applied: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="Stock quality multiplier used when formula path was active; "
                    "None when pre-computed realistic_stock_component_millions was used.")

    # Pair-level scope note
    pair_scope_note: str = Field(
        default="Pair-level result: a hard fail excludes only this acquirer-target pair, "
                "not the target globally.",
        description="Reminder that affordability results are pair-specific, not global.",
    )

    @property
    def is_hard_fail(self) -> bool:
        return self.band == AffordabilityBand.HARD_FAIL

    @property
    def is_pair_level_only(self) -> bool:
        """Always True — affordability gates never exclude a target globally."""
        return True




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
    # Rich multi-label classification — None when target fails hard exclusion.
    # deal_type is kept as the primary_deal_type for backward compatibility.
    deal_type_classification: Optional[DealTypeClassification] = None

    # 0C — per-acquirer affordability
    affordability: list[AffordabilityResult] = Field(default_factory=list)

    # 0D — encumbrance
    encumbrance: EncumbranceFlags

    # 0E — target-level integration complexity flag (no score penalty at Layer 0)
    # Buyer-specific penalty is computed in Layer 3 via compute_pair_integration_adjustment().
    commercial_complexity: CommercialComplexityScore  # alias for TargetIntegrationComplexityFlag

    # 0E convenience fields — surfaced at top level for Layer 3 / G8 consumers
    raw_integration_complexity_score: float = 0.0
    requires_buyer_capability_check: bool = False

    # 0F — distress guard
    distress_guard: DistressGuard

    # 0G — data confidence
    data_confidence: DataConfidenceResult

    # Combined score modifiers (applied regardless of exclusion status)
    score_cap: Optional[float] = None    # None = no cap; else clamp mna_probability
    score_multiplier: float = 1.0        # encumbrance penalty (0E no longer contributes)
    layer0_notes: list[str] = Field(default_factory=list)

    # Rich 11-gate exclusion assessment (None when not yet evaluated).
    # Downstream consumers that need gate-level detail should use this field.
    # The legacy passes_hard_exclusion / exclusion_code / exclusion_reason fields
    # remain the primary contract for existing callers.
    hard_exclusion_assessment: Optional["ExclusionAssessmentRef"] = Field(
        default=None, exclude=True
    )


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
# Section 0A — Hard Exclusion
#
# Replaced by the structured 11-gate ExclusionEngine in
# ``bve.intelligence.exclusions``.  The bridge function below converts
# ``TargetEligibilityInput`` → ``CompanyProfile``, runs the gate cascade,
# then maps the rich ExclusionAssessment back to the legacy
# (passes, ExclusionCode, reason_str) tuple so all downstream callers remain
# unchanged.
#
# Consumers that need gate-level detail should read
# ``Layer0Result.hard_exclusion_assessment`` directly.
# ---------------------------------------------------------------------------

# Taxonomy → entity_type mapping for the exclusion engine
_TAXONOMY_TO_ENTITY_TYPE: dict[str, str] = {
    CompanyTaxonomy.THERAPEUTICS.value:            "biotech",
    CompanyTaxonomy.DIAGNOSTICS.value:             "diagnostics",
    CompanyTaxonomy.TOOLS.value:                   "tools_reagents",
    CompanyTaxonomy.PLATFORM.value:                "platform",
    CompanyTaxonomy.LIFE_SCIENCE_SERVICES.value:   "cro_cdmo",
    CompanyTaxonomy.ACQUIRER.value:                "biotech",   # is_known_acquirer=True handles it
    CompanyTaxonomy.SPAC_SHELL.value:              "spac_shell",
    CompanyTaxonomy.DIVERSIFIED_CONGLOMERATE.value: "diversified_conglomerate",
    CompanyTaxonomy.OTHER.value:                   "other",
}

# lead_asset_status mapping from old domain to new
_LEAD_STATUS_MAP: dict[str, str] = {
    "active":         "active",
    # Map generic "failed" to "failed_pivotal" so Gate 4 checks has_salvage_path.
    # "failed_pivotal_no_path" is reserved for cases where we KNOW no path exists.
    "failed":         "failed_pivotal",
    "discontinued":   "discontinued",
    "safety_blocked": "safety_blocked",
}

# ExclusionStatus → ExclusionCode bridge (legacy callers need an ExclusionCode)
def _map_exclusion_status_to_code(
    status: "ExclusionStatusRef",
    triggered_rules: list[str],
) -> ExclusionCode:
    """Map the gate engine's ExclusionStatus to the legacy ExclusionCode enum."""
    from bve.intelligence.exclusions import ExclusionStatus as ES

    if status == ES.HISTORICAL_ONLY:
        return ExclusionCode.ALREADY_ACQUIRED
    if status == ES.ROUTE_TO_OTHER_MODEL:
        return ExclusionCode.ROUTED_TO_OTHER_MODEL
    if status in (ES.DILIGENCE_QUEUE, ES.REFRESH_REQUIRED):
        return ExclusionCode.INSUFFICIENT_DATA
    # HARD_FAIL — map via triggered rule IDs where possible
    first_rule = triggered_rules[0] if triggered_rules else ""
    if "SPAC" in first_rule:
        return ExclusionCode.SPAC_SHELL
    if "ACQUIRER" in first_rule:
        return ExclusionCode.KNOWN_ACQUIRER
    if "SELF_ACQ" in first_rule:
        return ExclusionCode.SELF_ACQUISITION
    if "NO_VALUE_DRIVER" in first_rule or "MISSING_PIPELINE" in first_rule:
        return ExclusionCode.NO_IDENTIFIABLE_ASSET
    if any(x in first_rule for x in ("FAILED_PIVOTAL", "SAFETY_BLOCKED", "DISCONTINUED",
                                      "ABANDONED", "MECHANISM", "DOSE_WINDOW")):
        return ExclusionCode.PERMANENTLY_IMPAIRED_LEAD
    return ExclusionCode.NON_BIOTECH_PHARMA


def _evaluate_hard_exclusion(
    t: TargetEligibilityInput,
    data_confidence: DataConfidenceResult,
) -> tuple[bool, Optional[ExclusionCode], Optional[str], "ExclusionAssessmentRef"]:
    """Return (passes, exclusion_code, reason_detail, assessment) for 0A.

    Delegates to the 11-gate ExclusionEngine.  The legacy 3-tuple fields are
    derived from the richer ExclusionAssessment for backward compatibility.

    A fourth value, the full ExclusionAssessment, is returned so that
    ``evaluate_layer0()`` can attach it to ``Layer0Result.hard_exclusion_assessment``.
    """
    from bve.intelligence.exclusions import (
        CompanyProfile as GateCompanyProfile,
        ExclusionStatus as ES,
        evaluate_company_exclusions,
    )

    # Self-acquisition check (Gate 2 is pair-level; handle here for company gate)
    if (
        t.acquirer_ticker
        and t.ticker
        and t.acquirer_ticker.upper() == t.ticker.upper()
    ):
        # Return a minimal "assessment-like" object so the bridge stays consistent.
        # We use a namedtuple-style stand-in so callers can read overall_status.
        class _SelfAcqAssessment:
            overall_status = ES.HARD_FAIL if hasattr(ES, "HARD_FAIL") else "HARD_FAIL"
            live_ranking_eligible = False
            historical_training_eligible = False
            max_score_cap = None
            triggered_exclusion_rules = ["G2.SELF_ACQ"]
            exclusion_reason_summary = "self_acquisition:target_is_acquirer"
            all_gate_results = []
            diligence_flags = []

        # Dynamically resolve ES so the isinstance check works
        try:
            from bve.intelligence.exclusions import ExclusionStatus as _ES
            _SelfAcqAssessment.overall_status = _ES.HARD_FAIL
        except Exception:
            pass

        return (
            False,
            ExclusionCode.SELF_ACQUISITION,
            "self_acquisition:target_ticker_matches_acquirer_ticker",
            _SelfAcqAssessment(),
        )

    # Convert TargetEligibilityInput → CompanyProfile
    entity_type = _TAXONOMY_TO_ENTITY_TYPE.get(
        t.company_taxonomy.value, "other"
    )
    lead_status = _LEAD_STATUS_MAP.get(t.lead_asset_status, "active")

    # Data-confidence LOW maps to financial_data_missing so Gate 6 fires
    financial_data_missing = data_confidence.grade == DataConfidenceGrade.LOW

    profile = GateCompanyProfile(
        company_id=t.ticker or "unknown",
        ticker=t.ticker,
        entity_type=entity_type,
        is_known_acquirer=(t.company_taxonomy == CompanyTaxonomy.ACQUIRER),
        # Gate 3: asset visibility
        has_lead_asset=t.lead_asset_present,
        has_platform=t.is_platform_company,
        has_active_pipeline=t.lead_asset_present or t.is_platform_company,
        # Gate 4: asset viability
        lead_asset_status=lead_status,
        has_salvage_path=t.has_replacement_asset,
        # Gate 5: IP
        royalty_stack_rate=t.royalty_stack_rate,
        has_ip_dispute=t.has_ip_dispute,
        # Gate 6: financial
        financial_data_missing=financial_data_missing,
        # Gate 7: market data — no direct mapping, defaults to PASS
    )

    assessment = evaluate_company_exclusions(profile)
    s = assessment.overall_status

    # PASS / SEVERE_CAP / PAIR_LEVEL_CAP → company is eligible
    if s in (ES.PASS, ES.SEVERE_CAP, ES.PAIR_LEVEL_CAP):
        return True, None, None, assessment

    # All other statuses block the company from live scoring
    excl_code = _map_exclusion_status_to_code(s, assessment.triggered_exclusion_rules)
    reason = assessment.exclusion_reason_summary or s.value
    return False, excl_code, reason, assessment


# ---------------------------------------------------------------------------
# Section 0B — Deal-Type Classification
# ---------------------------------------------------------------------------

def _classify_deal_type(t: TargetEligibilityInput) -> tuple[DealType, str]:
    """Thin wrapper around classify_deal_type() for backward compatibility.

    Returns (primary_deal_type, model_routing_reason) matching the old
    two-tuple contract.  Callers that need the full multi-label classification
    should use classify_deal_type() directly or read
    Layer0Result.deal_type_classification.
    """
    classification = classify_deal_type(t)
    return classification.primary_deal_type, classification.model_routing_reason


# ---------------------------------------------------------------------------
# Section 0C — Pair-Specific Affordability Gate
# ---------------------------------------------------------------------------

def _compute_stock_quality_multiplier(acq: AcquirerCapacityInput) -> float:
    """Derive how much of the theoretical max stock issuance is usable as currency.

    Returns a value in [0.10, 1.0] based on three signals:
      - investor_dilution_tolerance: base (how tolerant shareholders are of EPS dilution)
      - acquirer_price_to_book:      premium valuation = stock is valuable deal currency
      - acquirer_stock_volatility:   high vol = target demands cash; stock heavily discounted

    If ``acq.stock_quality_multiplier`` is provided directly, that value is returned as-is
    (after clamping).  If sub-signals are unavailable, defaults produce a neutral 0.50.
    """
    # Explicit override — skip computation
    if acq.stock_quality_multiplier is not None:
        return max(0.10, min(1.0, acq.stock_quality_multiplier))

    base = acq.investor_dilution_tolerance  # default 0.50

    # Price-to-book adjustment
    pb_adj = 0.0
    if acq.acquirer_price_to_book is not None:
        if acq.acquirer_price_to_book >= 4.0:
            pb_adj = 0.15   # premium acquirer; stock is strong currency
        elif acq.acquirer_price_to_book < 1.5:
            pb_adj = -0.20  # depressed acquirer; target discounts stock heavily

    # Volatility adjustment
    vol_adj = 0.0
    if acq.acquirer_stock_volatility_pct is not None:
        if acq.acquirer_stock_volatility_pct < 20.0:
            vol_adj = 0.10   # stable large-cap; stock broadly accepted
        elif acq.acquirer_stock_volatility_pct > 40.0:
            vol_adj = -0.25  # speculative biotech; target demands cash premium
        else:
            vol_adj = -0.10  # moderate biotech volatility range

    return max(0.10, min(1.0, base + pb_adj + vol_adj))


def _effective_stock_component(acq: AcquirerCapacityInput) -> tuple[float, Optional[float]]:
    """Return (stock_component_millions, sqm_applied).

    When acquirer_market_cap_millions is set, uses the formula:
        stock = market_cap × max_stock_issuance_pct × stock_quality_multiplier

    Otherwise falls back to the pre-supplied realistic_stock_component_millions
    and returns sqm_applied=None (pre-computed path).
    """
    if acq.acquirer_market_cap_millions is not None:
        sqm = _compute_stock_quality_multiplier(acq)
        stock_m = acq.acquirer_market_cap_millions * acq.max_stock_issuance_pct * sqm
        return max(0.0, stock_m), sqm
    return acq.realistic_stock_component_millions, None


def _evaluate_affordability(
    target_ev_millions: Optional[float],
    acquirers: list[AcquirerCapacityInput],
) -> list[AffordabilityResult]:
    """Compute per-acquirer-target-pair affordability.

    Returns empty list when EV is unknown.

    Each result is pair-level only: a HARD_FAIL for one acquirer does not
    exclude the target from consideration by any other acquirer.
    """
    if target_ev_millions is None:
        return []

    results: list[AffordabilityResult] = []
    for acq in acquirers:
        stock_component, sqm_applied = _effective_stock_component(acq)
        deal_capacity = max(
            acq.cash_available_millions
            + acq.estimated_debt_capacity_millions
            + stock_component
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
            stock_component_millions=round(stock_component, 2),
            stock_quality_multiplier_applied=round(sqm_applied, 4) if sqm_applied is not None else None,
        ))
    return results


# ---------------------------------------------------------------------------
# Section 0D — Asset-Control / Encumbrance Gate
# ---------------------------------------------------------------------------

def _evaluate_encumbrance(t: TargetEligibilityInput) -> EncumbranceFlags:
    """Evaluate 0D asset-control / encumbrance gate using the 6-bucket scoring system.

    Maps coarse TargetEligibilityInput signals to the detailed AssetControlInput
    sub-scores via ``asset_control_from_target()``, then runs ``compute_asset_control()``
    to produce an ``AssetControlResult`` (aliased as ``EncumbranceFlags`` for backward
    compatibility).
    """
    inp = asset_control_from_target(t)
    return compute_asset_control(inp)


# ---------------------------------------------------------------------------
# Section 0E — Target-Level Integration Complexity Flag
# ---------------------------------------------------------------------------

def _compute_commercial_complexity(t: TargetEligibilityInput) -> CommercialComplexityScore:
    """Compute 0E target-level integration complexity flag.

    Delegates to compute_target_integration_complexity().  No score penalty
    is applied here — the buyer-specific penalty belongs in Layer 3 G8 via
    compute_pair_integration_adjustment().
    """
    return compute_target_integration_complexity(t)


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

    # 0A — hard exclusion (delegated to 11-gate ExclusionEngine)
    passes, excl_code, excl_reason, hard_excl_assessment = _evaluate_hard_exclusion(
        target, data_confidence
    )

    # 0D, 0E, 0F — always computed (useful diagnostics even for excluded targets)
    encumbrance = _evaluate_encumbrance(target)
    commercial_complexity = _compute_commercial_complexity(target)
    distress_guard = _evaluate_distress_guard(target)

    # 0B, 0C — only meaningful when target passes hard exclusion
    deal_type: Optional[DealType] = None
    deal_type_note = ""
    deal_type_cls: Optional[DealTypeClassification] = None
    affordability: list[AffordabilityResult] = []

    if passes:
        deal_type_cls = classify_deal_type(target)
        deal_type = deal_type_cls.primary_deal_type
        deal_type_note = deal_type_cls.model_routing_reason
        affordability = _evaluate_affordability(target.enterprise_value_millions, acquirers)

    # Combined score modifiers
    # NOTE: 0E no longer contributes to the score multiplier — integration penalty
    # is applied pair-specifically in Layer 3 via G8.  Only encumbrance (0D) here.
    notes: list[str] = []
    combined_multiplier = round(encumbrance.penalty_multiplier, 6)

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
    # 0E: append integration risk drivers as informational notes (no penalty)
    notes.extend(commercial_complexity.complexity_flags)

    # Honour any score cap from the exclusion engine (e.g. SEVERE_CAP gates)
    engine_cap = (
        hard_excl_assessment.max_score_cap
        if hard_excl_assessment is not None and hard_excl_assessment.max_score_cap is not None
        else None
    )
    if engine_cap is not None:
        score_cap = (
            min(score_cap, engine_cap) if score_cap is not None else engine_cap
        )
        notes.append(f"exclusion_engine_cap:{engine_cap:.2f}")

    return Layer0Result(
        passes_hard_exclusion=passes,
        exclusion_code=excl_code,
        exclusion_reason=excl_reason,
        deal_type=deal_type,
        deal_type_routing_note=deal_type_note,
        deal_type_classification=deal_type_cls,
        affordability=affordability,
        encumbrance=encumbrance,
        commercial_complexity=commercial_complexity,
        raw_integration_complexity_score=commercial_complexity.raw_integration_complexity_score,
        requires_buyer_capability_check=commercial_complexity.requires_buyer_capability_check,
        distress_guard=distress_guard,
        data_confidence=data_confidence,
        score_cap=score_cap,
        score_multiplier=combined_multiplier,
        layer0_notes=notes,
        hard_exclusion_assessment=hard_excl_assessment,
    )
