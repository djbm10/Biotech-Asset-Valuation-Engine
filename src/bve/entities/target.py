"""Acquirable target entity — comprehensive Pydantic domain model.

Two tiers:
  WatchlistTarget  — lightweight Tier-1 record used by weekly_runner / actionable scoring.
  AcquirableTarget — full institutional-grade profile with clinical, regulatory,
                     commercial, IP, CMC, financing, governance, and M&A-readiness fields.

All fields beyond the identity keys are Optional so records can be partially populated
and enriched incrementally without validation failures.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CompanyClass(str, Enum):
    """Institutional classification for role in the M&A universe."""
    ACQUIRER        = "acquirer"        # big pharma / large biotech buyer
    TARGET          = "target"          # acquisition candidate
    HYBRID          = "hybrid"          # commercial standalone; acquirer AND acquirable
    ASIA_INNOVATOR  = "asia_innovator"  # China/Japan/Korea innovation source
    TOOLS_CDMO      = "tools_cdmo"      # manufacturing, CRO, discovery platform
    PRECEDENT       = "precedent"       # deal closed or pending — for historical reference


class CompanyType(str, Enum):
    THERAPEUTICS = "therapeutics"
    PLATFORM = "platform"
    DIAGNOSTICS = "diagnostics"
    TOOLS = "tools"
    CDMO = "cdmo"
    SPECIALTY_PHARMA = "specialty_pharma"


class TargetType(str, Enum):
    SINGLE_ASSET = "single_asset"
    PIPELINE_PORTFOLIO = "pipeline_portfolio"
    PLATFORM = "platform"
    COMMERCIAL_FRANCHISE = "commercial_franchise"
    DISTRESSED = "distressed"


class ManufacturingComplexity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RegulatoryPath(str, Enum):
    STANDARD = "standard"
    ACCELERATED = "accelerated"
    CONDITIONAL = "conditional"
    UNCERTAIN = "uncertain"


class CatalystType(str, Enum):
    PHASE_1_DATA = "phase_1_data"
    PHASE_2_DATA = "phase_2_data"
    PHASE_3_DATA = "phase_3_data"
    PDUFA = "pdufa"
    ADCOM = "adcom"
    FINANCING = "financing"
    COMPETITOR_DATA = "competitor_data"
    PATENT = "patent"
    PARTNERSHIP = "partnership"
    REGULATORY_DESIGNATION = "regulatory_designation"
    LABEL_EXPANSION = "label_expansion"
    MILESTONE = "milestone"


class DealRelevance(str, Enum):
    PRE_DATA_BUY = "pre_data_buy"
    POST_DATA_BUY = "post_data_buy"
    FINANCING_PRESSURE = "financing_pressure"
    COMPETITIVE_URGENCY = "competitive_urgency"


class SellerStrategy(str, Enum):
    INDEPENDENT = "independent"
    PARTNER = "partner"
    ACQUIRE = "acquire"
    STRATEGIC_OPTIONS = "strategic_options"


class DataConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SourceType(str, Enum):
    COMPANY_FILING = "company_filing"
    EARNINGS_CALL = "earnings_call"
    INVESTOR_DECK = "investor_deck"
    CLINICALTRIALS = "clinicaltrials"
    PUBMED = "pubmed"
    ANALYST_REPORT = "analyst_report"
    PRESS_RELEASE = "press_release"
    SEC_FILING = "sec_filing"
    MARKET_DATA = "market_data"
    EXPERT_OPINION = "expert_opinion"


# ---------------------------------------------------------------------------
# Section A: Company identity / classification
# ---------------------------------------------------------------------------

class CompanyIdentity(BaseModel):
    """Institutional identity and classification fields."""
    company_name: Optional[str] = None
    ticker: Optional[str] = None
    exchange: Optional[str] = None  # NASDAQ | NYSE | LSE | etc.
    country: Optional[str] = None
    region: Optional[str] = None  # US | EU | APAC | etc.
    company_type: Optional[CompanyType] = None
    target_type: Optional[TargetType] = None
    market_cap_millions: Optional[float] = None
    enterprise_value_millions: Optional[float] = None
    cash_millions: Optional[float] = None
    debt_millions: Optional[float] = None
    quarterly_burn_millions: Optional[float] = None
    runway_months: Optional[float] = None
    shares_outstanding_millions: Optional[float] = None
    float_millions: Optional[float] = None
    average_daily_volume_thousands: Optional[float] = None
    institutional_ownership_pct: Optional[float] = None
    insider_ownership_pct: Optional[float] = None


# ---------------------------------------------------------------------------
# Section B: Asset ownership / encumbrances
# ---------------------------------------------------------------------------

class RegionalRights(BaseModel):
    """Rights status per geography (True = acquirer can own, False = encumbered)."""
    us: Optional[bool] = None
    eu: Optional[bool] = None
    china: Optional[bool] = None
    japan: Optional[bool] = None
    rest_of_world: Optional[bool] = None


class AssetOwnership(BaseModel):
    """Ownership, encumbrances, and economic leakage on the asset."""
    global_rights_owned: Optional[bool] = None
    regional_rights: Optional[RegionalRights] = None
    existing_partners: list[str] = Field(default_factory=list)
    right_of_first_refusal: Optional[bool] = None
    change_of_control_clause: Optional[bool] = None
    royalty_stack_percent: Optional[float] = None  # total royalty burden on net sales
    licensed_in_asset: Optional[bool] = None
    co_development_obligations: Optional[str] = None
    profit_share_obligations: Optional[str] = None
    manufacturing_partner_dependencies: list[str] = Field(default_factory=list)
    ip_disputes: Optional[str] = None
    patent_challenges: Optional[str] = None


# ---------------------------------------------------------------------------
# Rights and Economics — normalized per-asset table (institutional-grade)
# ---------------------------------------------------------------------------

class RightsAndEconomics(BaseModel):
    """Normalized rights and economic encumbrances for one asset.

    This table captures the fields that most affect deal economics and deal
    feasibility for any buyer. Must be populated for assets with partnerships.

    Key rule: every asset with a non-zero royalty_stack_pct, a COC clause, or
    a licensor consent requirement MUST have this sub-model populated —
    not left in free-text notes.
    """
    licensor_partner: Optional[str] = None          # e.g. "Merck KGaA", "Sutro"
    co_dev_partner: Optional[str] = None            # e.g. "Kyowa Kirin"
    territory_split: Optional[str] = None           # e.g. "global rights", "ex-US"
    royalty_rate_pct: Optional[float] = None        # royalty on net sales paid OUT
    royalty_rate_note: Optional[str] = None         # e.g. "low teens"
    milestones_remaining_millions: Optional[float] = None
    milestone_triggers: list[str] = Field(default_factory=list)  # e.g. ["NDA approval", "1L launch"]
    opt_in_right: Optional[bool] = None             # partner has option to opt-in to Phase 3
    opt_out_right: Optional[bool] = None            # partner has option to opt-out
    change_of_control_clause: Optional[bool] = None
    coc_consequence: Optional[str] = None           # e.g. "termination right", "consent required"
    licensor_consent_required_for_coc: Optional[bool] = None
    supply_obligations: Optional[str] = None        # e.g. "Sutro supplies XpressCF API"
    profit_share_pct: Optional[float] = None
    sublicense_rights: Optional[bool] = None
    net_economics_to_buyer_pct: Optional[float] = None  # after royalty/profit-share
    encumbrance_severity: Optional[str] = None      # low | medium | high | deal_blocking


# ---------------------------------------------------------------------------
# Section C: Clinical asset detail
# ---------------------------------------------------------------------------

class TrialDesignDetail(BaseModel):
    """Granular trial design parameters."""
    randomized: Optional[bool] = None
    blinded: Optional[bool] = None
    controlled: Optional[bool] = None
    comparator: Optional[str] = None
    sample_size: Optional[int] = None
    powering_assumption: Optional[str] = None
    primary_endpoint: Optional[str] = None
    secondary_endpoints: list[str] = Field(default_factory=list)
    endpoint_objectivity: Optional[str] = None  # objective | subjective | surrogate
    endpoint_precedent: Optional[str] = None
    follow_up_duration_months: Optional[float] = None
    inclusion_exclusion_quality: Optional[str] = None  # broad | targeted | narrow
    geographic_trial_quality: Optional[str] = None  # us_only | us_eu | global
    dropout_rate_pct: Optional[float] = None


class ClinicalResults(BaseModel):
    """Key efficacy and safety results from the most recent data cut."""
    efficacy_effect_size: Optional[str] = None
    p_value: Optional[float] = None
    confidence_interval: Optional[str] = None
    responder_rate_pct: Optional[float] = None
    hazard_ratio: Optional[float] = None
    durability: Optional[str] = None  # e.g. "median DOR 18 months"
    subgroup_consistency: Optional[str] = None  # consistent | inconsistent | not_reported
    safety_events: Optional[str] = None
    serious_adverse_events_pct: Optional[float] = None
    discontinuation_rate_pct: Optional[float] = None
    treatment_related_deaths: Optional[int] = None


class ClinicalAssetDetail(BaseModel):
    """Full clinical asset characterisation."""
    lead_asset_name: Optional[str] = None
    asset_stage: Optional[str] = None  # phase_1 | phase_2 | phase_3 | nda | approved
    modality: Optional[str] = None
    target: Optional[str] = None  # molecular target (e.g. "EGFR", "PD-1")
    mechanism_of_action: Optional[str] = None
    biology_validation: Optional[str] = None  # genetic | clinical | preclinical | contested
    human_poc: Optional[bool] = None
    registrational_ready: Optional[bool] = None
    trial_phase: Optional[str] = None
    trial_name: Optional[str] = None
    nct_id: Optional[str] = None
    trial_design: Optional[TrialDesignDetail] = None
    clinical_results: Optional[ClinicalResults] = None


# ---------------------------------------------------------------------------
# Section D: Regulatory path
# ---------------------------------------------------------------------------

class RegulatoryDesignations(BaseModel):
    """FDA / EMA regulatory designations."""
    orphan: Optional[bool] = None
    fast_track: Optional[bool] = None
    breakthrough: Optional[bool] = None
    priority_review: Optional[bool] = None
    rmat: Optional[bool] = None
    accelerated_approval_possible: Optional[bool] = None


class RegulatoryProfile(BaseModel):
    """Regulatory strategy, path, and risk."""
    regulatory_designations: Optional[RegulatoryDesignations] = None
    fda_precedents: Optional[str] = None
    approval_endpoint_precedent: Optional[str] = None
    surrogate_endpoint_risk: Optional[str] = None  # low | medium | high
    required_trial_count: Optional[int] = None
    likely_regulatory_path: Optional[RegulatoryPath] = None
    regulatory_risk_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ex_us_regulatory_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Section E: Commercial model detail
# ---------------------------------------------------------------------------

class GeographicRevenueSplit(BaseModel):
    """Revenue fraction by geography (fractions need not sum to 1.0 if ex-US not modeled)."""
    us: Optional[float] = None
    eu5: Optional[float] = None
    japan: Optional[float] = None
    china: Optional[float] = None
    rest_of_world: Optional[float] = None


class CommercialModelDetail(BaseModel):
    """Institutional-grade patient funnel and commercial assumptions."""
    total_addressable_patients: Optional[int] = None
    diagnosed_patients: Optional[int] = None
    treated_patients: Optional[int] = None
    eligible_patients: Optional[int] = None
    line_of_therapy: Optional[str] = None  # 1L | 2L | 3L+ | maintenance
    treatment_duration_months: Optional[float] = None
    chronic_vs_acute: Optional[str] = None  # chronic | acute | episodic
    gross_price_usd: Optional[float] = None
    net_price_usd: Optional[float] = None
    gross_to_net_discount_pct: Optional[float] = None
    adherence_rate_pct: Optional[float] = None
    discontinuation_rate_annual_pct: Optional[float] = None
    peak_penetration_pct: Optional[float] = None
    launch_curve: Optional[str] = None  # description of ramp shape
    years_to_peak: Optional[float] = None
    payer_restriction_risk: Optional[str] = None  # low | medium | high
    prior_authorization_risk: Optional[str] = None  # low | medium | high
    step_edit_risk: Optional[str] = None  # low | medium | high
    site_of_care: Optional[str] = None  # outpatient | hospital | specialty_pharmacy | home
    physician_adoption_barriers: Optional[str] = None
    patient_access_barriers: Optional[str] = None
    geographic_split: Optional[GeographicRevenueSplit] = None


# ---------------------------------------------------------------------------
# Section F: Competitive landscape
# ---------------------------------------------------------------------------

class CompetitiveLandscape(BaseModel):
    """Competitive context: approved, pipeline, and strategic positioning."""
    approved_competitors: list[str] = Field(default_factory=list)
    pipeline_competitors: list[str] = Field(default_factory=list)
    same_moa_competitors: list[str] = Field(default_factory=list)
    better_moa_competitors: list[str] = Field(default_factory=list)
    first_mover_advantage: Optional[bool] = None
    best_in_class_potential: Optional[str] = None  # clear | plausible | unlikely
    me_too_risk: Optional[str] = None  # low | medium | high
    standard_of_care: Optional[str] = None
    switching_barriers: Optional[str] = None
    combination_potential: list[str] = Field(default_factory=list)
    competitor_readthrough_events: list[str] = Field(default_factory=list)
    expected_competitor_catalysts: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Section G: IP / exclusivity / LOE
# ---------------------------------------------------------------------------

class IPExclusivity(BaseModel):
    """Patent estate, exclusivity periods, and LOE risk."""
    composition_of_matter_expiry: Optional[int] = None  # year
    method_of_use_expiry: Optional[int] = None  # year
    formulation_patents: Optional[str] = None
    biologic_exclusivity: Optional[int] = None  # year of BLA exclusivity expiry
    orphan_exclusivity: Optional[int] = None  # year
    pediatric_extension_possible: Optional[bool] = None
    patent_term_extension_possible: Optional[bool] = None
    expected_loe_year: Optional[int] = None
    ip_strength_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    freedom_to_operate_risk: Optional[str] = None  # low | medium | high


# ---------------------------------------------------------------------------
# Section H: Manufacturing / CMC
# ---------------------------------------------------------------------------

class CMCProfile(BaseModel):
    """Manufacturing complexity, risk, and economics."""
    manufacturing_complexity: Optional[ManufacturingComplexity] = None
    modality_specific_cmc_risk: Optional[str] = None
    scale_up_risk: Optional[str] = None  # low | medium | high
    batch_failure_risk: Optional[str] = None  # low | medium | high
    cold_chain_required: Optional[bool] = None
    viral_vector_capacity_needed: Optional[bool] = None
    cell_therapy_complexity: Optional[str] = None
    supplier_concentration: Optional[str] = None  # single_source | dual | diversified
    tech_transfer_difficulty: Optional[str] = None  # low | medium | high
    cogs_percent: Optional[float] = None
    gross_margin_percent: Optional[float] = None


# ---------------------------------------------------------------------------
# Section I: Structured catalyst map
# ---------------------------------------------------------------------------

class StructuredCatalyst(BaseModel):
    """A specific upcoming catalyst with probability and deal relevance."""
    catalyst_type: Optional[CatalystType] = None
    description: Optional[str] = None
    expected_date: Optional[str] = None  # ISO date or "Q3 2025"
    date_confidence: Optional[DataConfidence] = None
    upside_case: Optional[str] = None
    downside_case: Optional[str] = None
    expected_stock_move_pct: Optional[float] = None
    probability_positive: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    probability_negative: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    readthrough_assets: list[str] = Field(default_factory=list)
    deal_relevance: Optional[DealRelevance] = None


# ---------------------------------------------------------------------------
# Section J: Market expectations / mispricing
# ---------------------------------------------------------------------------

class MarketExpectations(BaseModel):
    """Market-implied assumptions and vs-consensus positioning."""
    current_market_cap_millions: Optional[float] = None
    enterprise_value_millions: Optional[float] = None
    implied_peak_sales_millions: Optional[float] = None
    implied_pos: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    implied_approval_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    implied_takeout_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    analyst_consensus_peak_sales_millions: Optional[float] = None
    analyst_consensus_pos: Optional[float] = None
    short_interest_pct: Optional[float] = None
    options_implied_move_pct: Optional[float] = None
    options_skew: Optional[str] = None  # call_skew | put_skew | neutral
    borrow_cost_pct: Optional[float] = None
    recent_price_reaction: Optional[str] = None
    valuation_gap_millions: Optional[float] = None  # our_view − market_implied (positive = undervalued)


# ---------------------------------------------------------------------------
# Section K: Financing / distress
# ---------------------------------------------------------------------------

class FinancingProfile(BaseModel):
    """Cash position, runway, and financing pressure signals."""
    cash_millions: Optional[float] = None
    debt_millions: Optional[float] = None
    quarterly_burn_millions: Optional[float] = None
    runway_months: Optional[float] = None
    next_financing_need_date: Optional[str] = None
    atm_capacity_millions: Optional[float] = None
    shelf_registration: Optional[bool] = None
    recent_raise_date: Optional[str] = None
    likely_dilution_percent: Optional[float] = None
    debt_covenants: Optional[str] = None
    going_concern_risk: Optional[bool] = None
    strategic_alternative_pressure: Optional[bool] = None


# ---------------------------------------------------------------------------
# Section L: Management / governance / seller willingness
# ---------------------------------------------------------------------------

class SellerWillingness(BaseModel):
    """Governance, culture, and probability of willingness to sell."""
    founder_led: Optional[bool] = None
    activist_pressure: Optional[bool] = None
    recent_strategic_review: Optional[bool] = None
    board_mna_experience: Optional[str] = None
    management_sale_history: Optional[str] = None
    insider_ownership_pct: Optional[float] = None
    poison_pill: Optional[bool] = None
    dual_class_shares: Optional[bool] = None
    recent_partnering_language: Optional[str] = None
    stated_strategy: Optional[SellerStrategy] = None
    # Institutional-grade additions
    standalone_build_signals: Optional[str] = None  # e.g. "building manufacturing", "hiring salesforce"
    recent_financing: Optional[str] = None          # e.g. "$500M Series D Jan 2026"
    capital_runway_months: Optional[float] = None
    management_standalone_rhetoric: Optional[str] = None  # e.g. "CEO: 'building for independence'"
    sale_urgency_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)  # 0=not selling, 1=urgent
    preferred_outcome: Optional[str] = None         # acquisition | partnership | IPO | standalone


# ---------------------------------------------------------------------------
# Source / data quality tracking
# ---------------------------------------------------------------------------

class AssumptionSource(BaseModel):
    """Provenance and confidence for a specific data point."""
    url: Optional[str] = None
    source_type: Optional[SourceType] = None
    date: Optional[str] = None  # ISO date of source
    confidence: Optional[DataConfidence] = None
    extracted_value: Optional[str] = None
    notes: Optional[str] = None
    needs_refresh: bool = False
    manual_override: bool = False
    override_reason: Optional[str] = None


class DataQuality(BaseModel):
    """Overall data quality and completeness for a target record."""
    overall_confidence: Optional[DataConfidence] = None
    completeness_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    last_updated: Optional[str] = None  # ISO date
    main_data_gaps: list[str] = Field(default_factory=list)
    sources: dict[str, AssumptionSource] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Deal structure
# ---------------------------------------------------------------------------

class DealStructureProfile(BaseModel):
    """Recommended deal structure and feasibility assessment."""
    recommended_structure: Optional[str] = None  # full_acquisition | asset_deal | license | option | partnership
    full_acquisition_feasible: Optional[bool] = None
    asset_acquisition_feasible: Optional[bool] = None
    license_feasible: Optional[bool] = None
    option_to_acquire_feasible: Optional[bool] = None
    partnership_feasible: Optional[bool] = None
    likely_upfront_millions: Optional[float] = None
    likely_milestones_millions: Optional[float] = None
    likely_royalty_pct: Optional[float] = None
    likely_premium_pct: Optional[float] = None
    change_of_control_issues: Optional[str] = None
    tax_or_jurisdiction_issues: Optional[str] = None


# ---------------------------------------------------------------------------
# Tier 1 — Watchlist target (lightweight, used by weekly_runner)
# ---------------------------------------------------------------------------

class WatchlistTarget(BaseModel):
    """Lightweight Tier-1 watchlist record for weekly scoring and M&A scan.

    Extends the current 10-field UNIVERSE dict with richer metadata fields.
    All extended fields are Optional so existing UNIVERSE entries remain valid
    when instantiated from the plain dicts.

    Actionable score formula (evidence-weighted when quick scores are populated):
        0.25 × asset_quality_quick_score
      + 0.20 × strategic_scarcity_score
      + 0.15 × mna_relevance_score
      + 0.15 × financing_pressure_score
      + 0.10 × catalyst_importance_score
      + 0.10 × opportunity_score
      + 0.05 × ranking_score

    Falls back to legacy formula (ranking×0.50 + opportunity×0.20 + 0.30×0.5)
    when quick scores are absent.
    """

    # --- Existing 10 core fields ---
    ticker: str
    company_id: str
    asset_id: str
    indication: str
    ranking_score: float = Field(ge=0.0, le=1.0)
    opportunity_score: float = Field(ge=0.0, le=1.0)
    conviction: str  # high | medium | low | very-low
    catalyst: str
    claim_type: Optional[str] = None  # ClaimType value as string
    claim_assertion: Optional[str] = None

    # --- Extended identity ---
    company_name: Optional[str] = None
    target_type: Optional[TargetType] = None
    therapeutic_area: Optional[str] = None
    modality: Optional[str] = None
    stage: Optional[str] = None  # phase_1 | phase_2 | phase_3 | approved
    lead_asset: Optional[str] = None

    # --- Financials (quick) ---
    market_cap_millions: Optional[float] = None
    enterprise_value_millions: Optional[float] = None
    cash_millions: Optional[float] = None
    runway_months: Optional[float] = None

    # --- Ownership / encumbrance (quick) ---
    ownership_status: Optional[str] = None  # clean | encumbered | partnered
    key_partner: Optional[str] = None

    # --- Evidence-weighted quick scores (0–1) ---
    asset_quality_quick_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    strategic_scarcity_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    financing_pressure_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    mna_relevance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    # --- Structured catalyst ---
    upcoming_catalyst_date: Optional[str] = None
    upcoming_catalyst_type: Optional[CatalystType] = None
    catalyst_importance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    # --- Data quality ---
    data_confidence: Optional[DataConfidence] = None

    @property
    def actionable_score(self) -> float:
        """Composite actionable score (evidence-weighted when quick scores populated)."""
        aq = self.asset_quality_quick_score
        ss = self.strategic_scarcity_score
        fp = self.financing_pressure_score
        mr = self.mna_relevance_score
        ci = self.catalyst_importance_score

        if all(v is not None for v in [aq, ss, fp, mr, ci]):
            return (
                0.25 * aq
                + 0.20 * ss
                + 0.15 * mr
                + 0.15 * fp
                + 0.10 * ci
                + 0.10 * self.opportunity_score
                + 0.05 * self.ranking_score
            )
        # Legacy fallback: ranking×0.50 + opportunity×0.20 + neutral thesis 0.30×0.5
        return self.ranking_score * 0.50 + self.opportunity_score * 0.20 + 0.15


# ---------------------------------------------------------------------------
# Full institutional-grade acquirable target
# ---------------------------------------------------------------------------

class AcquirableTarget(BaseModel):
    """Full institutional-grade acquirable target profile.

    Aggregates all sub-models. All sections beyond the identity keys are Optional;
    records can be partially populated and enriched incrementally.
    """

    # Required identity keys (links to Tier-1 watchlist)
    ticker: str
    company_id: str
    asset_id: str

    # Institutional classification (acquirer | target | hybrid | asia_innovator | tools_cdmo | precedent)
    company_class: CompanyClass = CompanyClass.TARGET

    # Section A — Company identity / classification
    identity: Optional[CompanyIdentity] = None

    # Section B — Ownership / encumbrances
    asset_ownership: Optional[AssetOwnership] = None

    # Rights and economics (normalized; required for any encumbered asset)
    rights_and_economics: Optional[RightsAndEconomics] = None

    # Section C — Clinical asset detail
    clinical: Optional[ClinicalAssetDetail] = None

    # Section D — Regulatory path
    regulatory: Optional[RegulatoryProfile] = None

    # Section E — Commercial model detail
    commercial: Optional[CommercialModelDetail] = None

    # Section F — Competitive landscape
    competition: Optional[CompetitiveLandscape] = None

    # Section G — IP / exclusivity / LOE
    ip_exclusivity: Optional[IPExclusivity] = None

    # Section H — CMC / manufacturing
    cmc: Optional[CMCProfile] = None

    # Section I — Structured catalyst map
    catalysts: list[StructuredCatalyst] = Field(default_factory=list)

    # Section J — Market expectations / mispricing
    market_expectations: Optional[MarketExpectations] = None

    # Section K — Financing / distress
    financing: Optional[FinancingProfile] = None

    # Section L — Governance / seller willingness
    seller_willingness: Optional[SellerWillingness] = None

    # Deal structure recommendation
    deal_structure: Optional[DealStructureProfile] = None

    # Data quality
    data_quality: Optional[DataQuality] = None

    # Analyst commentary
    analyst_notes: Optional[str] = None
    limitations: list[str] = Field(default_factory=list)
