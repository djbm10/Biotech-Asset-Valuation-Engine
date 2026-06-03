"""Pydantic models for the M&A hard exclusion / routing layer.

Input
-----
CompanyProfile — all signals required to run the full gate cascade.
AcquirerProfile — signals needed for pair-level gates (Gate 2).

Output
------
GateResult — outcome from a single gate.
ExclusionAssessment — final verdict after running all applicable gates.

Integration
-----------
Apply ExclusionAssessment via apply_exclusion_assessment_to_score():
  - HARD_FAIL / HISTORICAL_ONLY / ROUTE_TO_OTHER_MODEL  →  score = None (excluded)
  - DILIGENCE_QUEUE / REFRESH_REQUIRED                 →  score = None (hold)
  - SEVERE_CAP                                          →  score capped at max_score_cap
  - PAIR_LEVEL_FAIL                                     →  pair score = None
  - PAIR_LEVEL_CAP                                      →  pair score capped
  - PASS                                                →  score unchanged
"""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from .enums import ExclusionStatus, GateName, RoutingModel


# ---------------------------------------------------------------------------
# Input: company-level profile
# ---------------------------------------------------------------------------

class CompanyProfile(BaseModel):
    """All signals needed to run the full 11-gate exclusion cascade.

    Fields default to the most permissive / least-risk value so that callers
    need only populate the fields they actually know.  Unknown fields do not
    trigger exclusions; insufficient data may trigger DILIGENCE_QUEUE on
    Gate 7 if too many market-data fields are missing.
    """
    model_config = ConfigDict(frozen=True)

    # --- Identity ---
    company_id: str
    ticker: Optional[str] = None

    # --- Gate 0: Entity Validity ---
    # Entity type from a controlled vocabulary.
    entity_type: Literal[
        "biotech",
        "pharma",
        "diagnostics",
        "medical_device",
        "tools_reagents",
        "platform",
        "spac_shell",
        "holding_company",
        "investment_vehicle",
        "royalty_company",
        "cro_cdmo",
        "consulting_staffing",
        "research_nonprofit",
        "academic_entity",
        "government_controlled",
        "diversified_conglomerate",
        "other",
    ] = "biotech"
    is_government_restricted: bool = False  # formal restriction on foreign ownership

    # --- Gate 1: Corporate Status ---
    corporate_status: Literal[
        "active",
        "acquired",           # already taken out; should be HISTORICAL_ONLY
        "merged",             # merged into another entity
        "delisted_takeout",   # delisted due to acquisition
        "pending_acquisition",  # definitive agreement signed
        "post_spin",          # recently spun off; entity/ticker may be stale
        "ticker_mismatch",    # ticker no longer matches original entity
        "duplicate_entity",   # same company with two entries
        "bankrupt",
        "liquidating",
    ] = "active"
    is_duplicate: bool = False

    # --- Gate 2: Buyer-Target Validity (pair-level — set by engine when acquirer is known) ---
    # These are populated dynamically by evaluate_pair_exclusions(); not required for
    # company-level assessment.
    is_known_acquirer: bool = False  # company is itself a large-cap acquirer profile

    # --- Gate 3: Asset Visibility ---
    has_lead_asset: bool = True
    has_platform: bool = False
    has_active_pipeline: bool = True
    has_commercial_product: bool = False   # for approved/commercial-stage companies
    pipeline_description_quality: Literal["clear", "vague", "missing"] = "clear"
    therapeutic_area_known: bool = True
    modality_known: bool = True

    # --- Gate 4: Asset Viability ---
    lead_asset_status: Literal[
        "active",
        "discontinued",
        "failed_pivotal",         # pivotal trial failed; possible salvage path
        "failed_pivotal_no_path", # failed with no credible salvage route
        "safety_blocked",         # fatal safety signal / clinical hold
        "regulatory_rejected_no_path",
        "mechanism_invalidated",
        "no_dose_window",
        "weak_signal_single_study",
        "abandoned",
    ] = "active"
    has_salvage_path: bool = False     # credible alternative path if lead fails
    clinical_hold_unresolved: bool = False

    # --- Gate 5: Rights / IP / Ownership ---
    ip_ownership_status: Literal[
        "owned",
        "licensed_in",             # licensed from third party; acquirer gets sublicense
        "fully_licensed_away",     # company has no remaining rights
        "co_owned_disputed",       # disputed ownership
        "key_territory_unavailable",
    ] = "owned"
    ip_durability: Literal["strong", "moderate", "weak", "short_exclusivity"] = "strong"
    has_blocking_third_party_rights: bool = False
    royalty_stack_rate: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Cumulative royalty obligation rate (e.g. 0.18 = 18%)."
    )
    has_ip_dispute: bool = False

    # --- Gate 6: Financial / Going Concern ---
    financial_status: Literal[
        "healthy",
        "going_concern_warning",
        "bankrupt",
        "liquidating",
        "negative_ev_distressed",
        "no_data",
        "unreliable_financials",
    ] = "healthy"
    market_cap_millions: Optional[float] = Field(default=None, ge=0.0)
    enterprise_value_millions: Optional[float] = None
    # Set to True if there is no useful financial data at all
    financial_data_missing: bool = False

    # --- Gate 7: Market Data Quality ---
    market_data_staleness_days: Optional[int] = None  # days since last price update
    avg_daily_volume_usd_millions: Optional[float] = None
    listing_type: Literal["major_exchange", "otc_pink", "foreign_adr", "unknown"] = "major_exchange"
    recent_corporate_action_unresolved: bool = False  # reverse split, merger confusion, etc.

    # --- Gate 8: Legal / Integrity ---
    has_sanctions: bool = False
    has_fraud_allegation: bool = False
    has_clinical_data_integrity_issue: bool = False
    has_sec_enforcement_cloud: bool = False
    has_major_asset_litigation: bool = False
    has_gmp_failure: bool = False
    fraud_severity: Literal["none", "allegation", "confirmed"] = "none"

    # --- Gate 9: Commercial Relevance ---
    addressable_market_size: Literal["large", "medium", "small", "tiny", "unknown"] = "large"
    has_unmet_need: bool = True
    is_differentiated: bool = True
    generic_biosimilar_pressure: Literal["none", "moderate", "severe"] = "none"
    reimbursement_feasibility: Literal["clear", "uncertain", "impossible"] = "clear"
    adoption_barriers: Literal["low", "moderate", "high"] = "low"

    # --- Gate 10: Model Routing classification ---
    # Inform the routing gate if the company is pre-classified as a specific deal type.
    #
    # Two sets of values are accepted:
    #   Legacy literals  — original Gate 10 bucket names (backward compatible via
    #                      _LEGACY_GATE10_MAP in rules.py)
    #   Canonical values — DealType enum values from deal_type_classification.py
    #                      (preferred for new callers)
    #   Special sentinel — "historical_training" is not a DealType; it marks a
    #                      company as already-acquired training data only.
    deal_type_classification: Optional[Literal[
        # Legacy Gate 10 literals (maintained for backward compatibility)
        "standard_pipeline",
        "licensing_only",
        "distress_only",
        "commercial_only",
        "platform_only",
        # Special sentinel — not a DealType value
        "historical_training",
        # Canonical DealType values (preferred; normalised by _LEGACY_GATE10_MAP)
        "single_asset_takeout",
        "pipeline_portfolio_takeout",
        "platform_acquisition",
        "commercial_franchise_acquisition",
        "asset_license_partnership",
        "distressed_optionality",
    ]] = None


# ---------------------------------------------------------------------------
# Input: acquirer-level profile (for pair-level gates)
# ---------------------------------------------------------------------------

class AcquirerProfile(BaseModel):
    """Minimal acquirer signals needed for pair-level gate evaluation."""
    model_config = ConfigDict(frozen=True)

    acquirer_id: str
    ticker: Optional[str] = None
    cash_available_millions: float = Field(default=0.0, ge=0.0)
    debt_capacity_millions: float = Field(default=0.0, ge=0.0)
    realistic_stock_component_millions: float = Field(default=0.0, ge=0.0)
    # True when the acquirer already owns or controls a majority stake
    has_majority_control: bool = False
    # True when there is a direct product/TA conflict (same indication + same MoA)
    has_direct_strategic_conflict: bool = False
    # Estimated probability that antitrust regulators would block this deal
    antitrust_block_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    # True when this is a merger-of-equals scenario (similar market caps)
    is_merger_of_equals: bool = False
    # Expected takeout premium (e.g. 0.35 = 35%)
    expected_premium: float = Field(default=0.35, ge=0.0, le=2.0)


# ---------------------------------------------------------------------------
# Output: per-gate result
# ---------------------------------------------------------------------------

class GateResult(BaseModel):
    """Outcome of evaluating one gate for a company (or company-acquirer pair).

    Guidance on fields:
    - triggered_rules: machine-readable rule IDs that fired (e.g. "G0.SPAC_SHELL").
    - evidence_fields_used: CompanyProfile field names that drove the decision.
    - score_cap: applicable only when status == SEVERE_CAP or PAIR_LEVEL_CAP.
    - route_to_model: applicable only when status == ROUTE_TO_OTHER_MODEL.
    - is_company_level: True when the gate outcome applies to the company regardless
      of acquirer (most gates).
    - is_pair_level: True when the gate outcome is specific to one buyer-target pair.
    """
    model_config = ConfigDict(frozen=True)

    gate_name: GateName
    status: ExclusionStatus
    triggered_rules: list[str] = Field(default_factory=list)
    reason: str
    evidence_fields_used: list[str] = Field(default_factory=list)
    recommended_action: str
    score_cap: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    route_to_model: Optional[RoutingModel] = None
    is_company_level: bool = True
    is_pair_level: bool = False


# ---------------------------------------------------------------------------
# Output: final assessment
# ---------------------------------------------------------------------------

class ExclusionAssessment(BaseModel):
    """Final verdict after running all applicable gates for a company.

    Interpretation:
      live_ranking_eligible=True  → proceed to scoring pipeline
      live_ranking_eligible=False, historical_training_eligible=True
                                  → move to training / backtest set only
      live_ranking_eligible=False, historical_training_eligible=False
                                  → exclude entirely or route to specialist model

    When max_score_cap is set, the downstream scorer must clamp
    mna_probability_score to ≤ max_score_cap before ranking.
    """
    model_config = ConfigDict(frozen=True)

    # Who was assessed
    company_id: str
    ticker: Optional[str] = None
    acquirer_id: Optional[str] = None   # set when pair-level gates were evaluated

    # Overall verdict
    overall_status: ExclusionStatus
    live_ranking_eligible: bool
    historical_training_eligible: bool

    # Routing — set when overall_status == ROUTE_TO_OTHER_MODEL
    routed_model: Optional[RoutingModel] = None

    # Score cap — set when any SEVERE_CAP gate fired
    # Final score must not exceed this value.
    max_score_cap: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    # Diligence flags — human-readable strings for the diligence export
    diligence_flags: list[str] = Field(default_factory=list)

    # All gate results for full auditability
    all_gate_results: list[GateResult] = Field(default_factory=list)

    # Convenience roll-ups
    triggered_exclusion_rules: list[str] = Field(default_factory=list)
    exclusion_reason_summary: str = ""
