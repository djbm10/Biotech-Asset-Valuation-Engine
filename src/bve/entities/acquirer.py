"""Acquirer entity — Pydantic domain model for big pharma / big biotech acquirers.

This is the domain-layer representation (Pydantic), separate from the ORM
model in persistence/models.py which handles storage.  The two are kept
independent so the domain layer has no SQLAlchemy dependency.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BDStyle(str, Enum):
    """Observed business development style for the acquirer."""
    BOLT_ON = "bolt_on"           # Small tuck-ins, early/mid stage
    PLATFORM = "platform"         # Platform/technology acquisitions
    BLOCKBUSTER = "blockbuster"   # Large late-stage or commercial buys
    PARTNERSHIP_FIRST = "partnership_first"  # Prefers partnerships before acquisition
    MIXED = "mixed"


class LOECliff(BaseModel):
    """Expected loss-of-exclusivity event for a branded product."""
    product_name: str
    indication: str
    peak_sales_millions: float
    loe_year: int
    revenue_at_risk_millions: float  # expected post-LOE revenue loss
    percent_of_company_revenue: Optional[float] = None  # fraction of total company revenue at risk
    replacement_urgency: Optional[str] = None  # low | medium | high | critical

    @property
    def urgency_score(self) -> float:
        """Higher = more urgent gap to fill. Normalised 0→1 based on revenue at risk."""
        return min(1.0, self.revenue_at_risk_millions / 10_000.0)


class PipelineGap(BaseModel):
    """A strategic TA/modality area where the acquirer has a thin pipeline."""
    therapeutic_area: str
    modality: Optional[str] = None
    rationale: str  # why this is a gap (e.g., "no Phase 3 assets in oncology IO")
    priority: str = "medium"  # low | medium | high | critical
    stage_needed: Optional[str] = None  # early | mid | late | commercial
    revenue_gap_millions: Optional[float] = None  # estimated revenue shortfall to fill


class BDHistoryItem(BaseModel):
    """One historical acquisition or major partnership."""
    target_name: str
    deal_type: str  # acquisition | license_in | partnership
    announced_year: int
    deal_value_millions: Optional[float] = None
    therapeutic_area: Optional[str] = None
    phase_at_deal: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Extended acquirer sub-models (institutional-grade BD scoring)
# ---------------------------------------------------------------------------

class DealCapacity(BaseModel):
    """Buyer's financial capacity to execute acquisitions."""
    cash_available_for_deals_millions: Optional[float] = None
    estimated_debt_capacity_millions: Optional[float] = None
    stock_component_capacity_millions: Optional[float] = None
    minimum_balance_sheet_buffer_millions: Optional[float] = None
    max_comfortable_deal_size_millions: Optional[float] = None
    leverage_limit_net_debt_ebitda: Optional[float] = None
    rating_sensitivity: Optional[str] = None  # e.g. "deal >$20B risks Baa2 downgrade"
    recent_large_deals: list[str] = Field(default_factory=list)


class ModalityCapabilities(BaseModel):
    """Technical capability per drug modality (0–1 score; 0 = no capability)."""
    small_molecule: float = Field(default=0.0, ge=0.0, le=1.0)
    monoclonal_antibody: float = Field(default=0.0, ge=0.0, le=1.0)
    antibody_drug_conjugate: float = Field(default=0.0, ge=0.0, le=1.0)
    bispecific: float = Field(default=0.0, ge=0.0, le=1.0)
    cell_therapy: float = Field(default=0.0, ge=0.0, le=1.0)
    gene_therapy: float = Field(default=0.0, ge=0.0, le=1.0)
    mrna: float = Field(default=0.0, ge=0.0, le=1.0)
    rnai: float = Field(default=0.0, ge=0.0, le=1.0)
    antisense: float = Field(default=0.0, ge=0.0, le=1.0)
    gene_editing: float = Field(default=0.0, ge=0.0, le=1.0)
    radiopharmaceutical: float = Field(default=0.0, ge=0.0, le=1.0)
    peptide: float = Field(default=0.0, ge=0.0, le=1.0)
    vaccine: float = Field(default=0.0, ge=0.0, le=1.0)


class DevelopmentCapability(BaseModel):
    """Clinical development execution capability (0–1 scores)."""
    phase_1: float = Field(default=0.0, ge=0.0, le=1.0)
    phase_2: float = Field(default=0.0, ge=0.0, le=1.0)
    phase_3: float = Field(default=0.0, ge=0.0, le=1.0)
    registrational_trials: float = Field(default=0.0, ge=0.0, le=1.0)
    global_trial_execution: float = Field(default=0.0, ge=0.0, le=1.0)
    rare_disease_trials: float = Field(default=0.0, ge=0.0, le=1.0)
    oncology_trials: float = Field(default=0.0, ge=0.0, le=1.0)
    biomarker_driven_trials: float = Field(default=0.0, ge=0.0, le=1.0)
    regulatory_accelerated_pathways: float = Field(default=0.0, ge=0.0, le=1.0)


class CommercialCapability(BaseModel):
    """Commercialization and launch capability (0–1 scores)."""
    us_specialty_salesforce: float = Field(default=0.0, ge=0.0, le=1.0)
    global_salesforce: float = Field(default=0.0, ge=0.0, le=1.0)
    hospital_salesforce: float = Field(default=0.0, ge=0.0, le=1.0)
    primary_care_salesforce: float = Field(default=0.0, ge=0.0, le=1.0)
    oncology_salesforce: float = Field(default=0.0, ge=0.0, le=1.0)
    rare_disease_salesforce: float = Field(default=0.0, ge=0.0, le=1.0)
    payer_access_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    launch_execution_score: float = Field(default=0.0, ge=0.0, le=1.0)
    us_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    eu_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    japan_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    china_strength: float = Field(default=0.0, ge=0.0, le=1.0)


class CMCCapability(BaseModel):
    """Manufacturing / CMC capability per modality (0–1 scores)."""
    biologics: float = Field(default=0.0, ge=0.0, le=1.0)
    small_molecule: float = Field(default=0.0, ge=0.0, le=1.0)
    sterile_fill_finish: float = Field(default=0.0, ge=0.0, le=1.0)
    viral_vectors: float = Field(default=0.0, ge=0.0, le=1.0)
    cell_therapy: float = Field(default=0.0, ge=0.0, le=1.0)
    gene_therapy: float = Field(default=0.0, ge=0.0, le=1.0)
    mrna_lnp: float = Field(default=0.0, ge=0.0, le=1.0)
    adc: float = Field(default=0.0, ge=0.0, le=1.0)
    radiopharmaceuticals: float = Field(default=0.0, ge=0.0, le=1.0)
    peptides: float = Field(default=0.0, ge=0.0, le=1.0)
    supply_chain_strength: float = Field(default=0.0, ge=0.0, le=1.0)


class AcquisitionRecord(BaseModel):
    """One completed acquisition in BD history."""
    target: str
    year: int
    deal_value_millions: Optional[float] = None
    therapeutic_area: Optional[str] = None
    modality: Optional[str] = None
    stage: Optional[str] = None  # Phase 1 | Phase 2 | Phase 3 | Approved
    structure: Optional[str] = None  # all_cash | stock | mixed
    premium: Optional[float] = None  # fraction (e.g. 0.45 = 45% premium paid)
    outcome: Optional[str] = None  # success | mixed | failure | too_early


class LicenseRecord(BaseModel):
    """One licensing deal in BD history."""
    partner: str
    year: int
    upfront_millions: Optional[float] = None
    total_biobucks_millions: Optional[float] = None
    royalty_percent: Optional[float] = None
    therapeutic_area: Optional[str] = None
    modality: Optional[str] = None
    geography: Optional[str] = None  # global | US | ex-US | China | etc.


class BDHistoryDetailed(BaseModel):
    """Structured BD history: acquisitions, licenses, and style preferences."""
    acquisitions: list[AcquisitionRecord] = Field(default_factory=list)
    licenses: list[LicenseRecord] = Field(default_factory=list)
    preferred_deal_size: Optional[str] = None  # e.g. "$1–5B bolt-on"
    preferred_stage: Optional[str] = None  # Phase 2 | Phase 3 | Approved | Any
    preferred_structure: Optional[str] = None  # all_cash | mixed | stock
    typical_premium_range: Optional[str] = None  # e.g. "35–65%"


class AcquirerRelationships(BaseModel):
    """Existing relationships that may affect M&A probability."""
    existing_partnerships: list[str] = Field(default_factory=list)
    prior_collaborations: list[str] = Field(default_factory=list)
    equity_stakes: list[str] = Field(default_factory=list)
    board_relationships: list[str] = Field(default_factory=list)
    co_development_relationships: list[str] = Field(default_factory=list)
    right_of_first_refusal_assets: list[str] = Field(default_factory=list)
    existing_supply_relationships: list[str] = Field(default_factory=list)


class AntitrustProfile(BaseModel):
    """Antitrust and regulatory concentration risk for the acquirer."""
    therapeutic_area_concentration: list[str] = Field(default_factory=list)
    overlapping_products: list[str] = Field(default_factory=list)
    market_share_overlap: Optional[str] = None
    ftc_risk: Optional[str] = None  # low | medium | high
    eu_commission_risk: Optional[str] = None  # low | medium | high
    divestiture_likelihood: Optional[str] = None  # low | medium | high


class AcquirerProfile(BaseModel):
    """Strategic profile of a potential acquirer (big pharma or large biotech).

    Used as the domain representation in acquisition fit scoring.
    """
    company_id: str
    name: str
    ticker: Optional[str] = None

    # Financial capacity
    cash_millions: float = Field(ge=0.0)
    debt_millions: float = Field(default=0.0, ge=0.0)
    annual_fcf_millions: float = Field(default=0.0)
    market_cap_millions: Optional[float] = None

    # Strategic priorities
    strategic_areas: list[str] = Field(
        default_factory=list,
        description="Therapeutic areas of active interest (oncology, immunology, …)"
    )
    preferred_modalities: list[str] = Field(
        default_factory=list,
        description="Preferred drug modalities (small_molecule, biologic, cell_therapy, …)"
    )
    geography_focus: list[str] = Field(default_factory=list)  # e.g. ["US", "EU", "global"]

    # Pipeline gaps
    pipeline_gaps: list[PipelineGap] = Field(default_factory=list)

    # LOE exposure
    loe_cliffs: list[LOECliff] = Field(default_factory=list)

    # BD behaviour
    bd_style: BDStyle = BDStyle.MIXED
    bd_history: list[BDHistoryItem] = Field(default_factory=list)
    preferred_phase: Optional[str] = None  # Phase 2 | Phase 3 | Approved | Any
    max_deal_size_millions: Optional[float] = None

    # Derived
    notes: Optional[str] = None

    # ---------------------------------------------------------------------------
    # Extended profile (institutional-grade BD scoring)
    # ---------------------------------------------------------------------------

    # Identity / financials
    country: Optional[str] = None
    enterprise_value_millions: Optional[float] = None
    net_debt_millions: Optional[float] = None
    ebitda_millions: Optional[float] = None
    credit_rating: Optional[str] = None  # e.g. "A3", "BBB+"

    # Deal capacity (buyer-specific affordability breakdown)
    deal_capacity: Optional[DealCapacity] = None

    # TA priority weights (0–1 per area; graduated scoring vs. binary strategic_areas match)
    ta_priorities: dict[str, float] = Field(
        default_factory=dict,
        description="TA name → priority weight (0–1). Supplements strategic_areas list.",
    )

    # Capability profiles (all Optional; populated as data is available)
    modality_capabilities: Optional[ModalityCapabilities] = None
    development_capability: Optional[DevelopmentCapability] = None
    commercial_capability: Optional[CommercialCapability] = None
    cmc_capability: Optional[CMCCapability] = None

    # Structured BD history (supplements simple bd_history list)
    bd_history_detailed: Optional[BDHistoryDetailed] = None

    # Relationship map
    relationships: Optional[AcquirerRelationships] = None

    # Antitrust
    antitrust: Optional[AntitrustProfile] = None

    @property
    def cash_firepower_millions(self) -> float:
        """Estimated acquisition capacity: cash + 2× annual FCF (rough 2-year FCF)."""
        return self.cash_millions + 2 * max(0, self.annual_fcf_millions)

    @property
    def total_loe_revenue_at_risk_millions(self) -> float:
        return sum(c.revenue_at_risk_millions for c in self.loe_cliffs)

    @property
    def loe_urgency(self) -> float:
        """Composite LOE urgency [0–1]: higher → more urgent need to replace revenue."""
        if not self.loe_cliffs:
            return 0.0
        return min(1.0, sum(c.urgency_score for c in self.loe_cliffs) / max(1, len(self.loe_cliffs)))

    def covers_ta(self, therapeutic_area: str) -> bool:
        return therapeutic_area.lower() in [s.lower() for s in self.strategic_areas]

    def covers_modality(self, modality: str) -> bool:
        if not self.preferred_modalities:
            return True  # no filter → accepts all
        return modality.lower() in [m.lower() for m in self.preferred_modalities]

    def can_afford(self, deal_size_millions: float, ratio: float = 0.25) -> bool:
        """True if deal_size ≤ ratio × firepower (conservative affordability gate)."""
        return deal_size_millions <= self.cash_firepower_millions * ratio


# ---------------------------------------------------------------------------
# Canonical acquirer universe (v1)
# ---------------------------------------------------------------------------

# Financial figures sourced from Q1 2026 earnings releases and finance snapshots.
# Refresh against current 10-Q/annual report before use in live deal analysis.
ACQUIRER_UNIVERSE: list[AcquirerProfile] = [
    AcquirerProfile(
        company_id="pfizer",
        name="Pfizer",
        ticker="PFE",
        country="United States",
        cash_millions=15_000,
        annual_fcf_millions=8_000,
        market_cap_millions=145_166,
        strategic_areas=["oncology", "immunology", "rare_disease", "vaccines"],
        preferred_modalities=["small_molecule", "biologic", "mRNA"],
        bd_style=BDStyle.BLOCKBUSTER,
        preferred_phase="Phase 3",
        max_deal_size_millions=20_000,
        loe_cliffs=[
            LOECliff(product_name="Eliquis", indication="AF/VTE", peak_sales_millions=6_500, loe_year=2028, revenue_at_risk_millions=4_000),
        ],
        deal_capacity=DealCapacity(max_comfortable_deal_size_millions=18_000),
        ta_priorities={"oncology": 0.9, "obesity_metabolic": 0.8, "immunology": 0.7, "vaccines": 0.8},
        modality_capabilities=ModalityCapabilities(small_molecule=0.9, monoclonal_antibody=0.9, vaccine=0.95),
        notes=(
            "Q1 2026: Market cap ~$145.2B. Explicit interest in oncology and obesity. "
            "Received ~$1.65B cash from ViiV exit. Data confidence: medium (0.62). "
            "Diligence: refresh net leverage; clarify platform vs. late-stage preference; test antitrust exposure in obesity."
        ),
    ),
    AcquirerProfile(
        company_id="eli_lilly",
        name="Eli Lilly",
        ticker="LLY",
        country="United States",
        cash_millions=5_282,
        annual_fcf_millions=12_000,
        market_cap_millions=900_308,
        strategic_areas=["diabetes", "obesity", "oncology", "immunology", "neuroscience"],
        preferred_modalities=["small_molecule", "biologic", "antibody", "peptide"],
        bd_style=BDStyle.PLATFORM,
        preferred_phase="Phase 2",
        max_deal_size_millions=15_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=5_282,
            max_comfortable_deal_size_millions=50_000,
        ),
        ta_priorities={"obesity_metabolic": 1.0, "immunology": 0.8, "oncology": 0.8, "neuroscience": 0.7},
        modality_capabilities=ModalityCapabilities(small_molecule=0.9, monoclonal_antibody=0.85, peptide=0.95),
        notes=(
            "Q1 2026: Market cap ~$900.3B, cash ~$5.3B. Highest-capacity buyer in universe by a wide margin. "
            "Growth emphasis: obesity/metabolic, immunology, oncology, neuroscience. Data confidence: medium-high (0.73). "
            "Diligence: verify real appetite for external obesity vs. internal build; map LOE urgency; test platform vs. late-stage preference."
        ),
    ),
    AcquirerProfile(
        company_id="merck",
        name="Merck & Co",
        ticker="MRK",
        country="United States",
        cash_millions=8_000,
        annual_fcf_millions=14_000,
        market_cap_millions=275_089,
        strategic_areas=["oncology", "vaccines", "infectious_disease", "cardiometabolic"],
        preferred_modalities=["biologic", "small_molecule", "antibody_drug_conjugate"],
        bd_style=BDStyle.PLATFORM,
        preferred_phase="Phase 2",
        loe_cliffs=[
            LOECliff(product_name="Keytruda", indication="multiple oncology", peak_sales_millions=25_000, loe_year=2028, revenue_at_risk_millions=15_000),
        ],
        deal_capacity=DealCapacity(max_comfortable_deal_size_millions=30_000),
        ta_priorities={"oncology": 1.0, "vaccines": 0.85, "cardiometabolic": 0.5, "immunology": 0.6},
        modality_capabilities=ModalityCapabilities(small_molecule=0.9, monoclonal_antibody=0.85, vaccine=0.95),
        notes=(
            "Market cap ~$275.1B. Keytruda LOE pressure from 2028 ($15B revenue at risk) is the primary deal urgency driver. "
            "Data confidence: medium-low (0.48). "
            "Diligence: refresh Keytruda LOE cash/debt headroom; compare RAS/MAPK targets vs. internal pipeline."
        ),
    ),
    AcquirerProfile(
        company_id="astrazeneca",
        name="AstraZeneca",
        ticker="AZN",
        country="United Kingdom",
        cash_millions=7_560,
        annual_fcf_millions=9_000,
        market_cap_millions=281_479,
        net_debt_millions=25_944,
        ebitda_millions=5_612,
        credit_rating="A1/A+",
        strategic_areas=["oncology", "cardiovascular", "respiratory", "rare_disease"],
        preferred_modalities=["biologic", "antibody_drug_conjugate", "small_molecule"],
        bd_style=BDStyle.BOLT_ON,
        preferred_phase="Phase 2",
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=7_560,
            max_comfortable_deal_size_millions=28_000,
        ),
        ta_priorities={"oncology": 1.0, "rare_disease": 0.8, "cardiovascular": 0.8, "immunology": 0.7},
        modality_capabilities=ModalityCapabilities(small_molecule=0.9, monoclonal_antibody=0.9, cell_therapy=0.6),
        notes=(
            "Q1 2026: Cash $7.56B, net debt $25.94B, EBITDA $5.61B, rated A1/A+. One of the strongest institutional buyers. "
            "Data confidence: high (0.82). "
            "Diligence: quantify post-Alexion integration bandwidth; map ophthalmology vs. oncology/CVRM priority; screen overlap risk."
        ),
    ),
    AcquirerProfile(
        company_id="bristol_myers_squibb",
        name="Bristol-Myers Squibb",
        ticker="BMY",
        country="United States",
        cash_millions=10_853,
        debt_millions=44_460,
        annual_fcf_millions=7_000,
        market_cap_millions=116_398,
        net_debt_millions=33_607,
        strategic_areas=["oncology", "hematology", "immunology", "cardiovascular"],
        preferred_modalities=["biologic", "small_molecule", "cell_therapy"],
        bd_style=BDStyle.BLOCKBUSTER,
        preferred_phase="Phase 3",
        loe_cliffs=[
            LOECliff(product_name="Revlimid", indication="myeloma", peak_sales_millions=7_000, loe_year=2026, revenue_at_risk_millions=5_000),
            LOECliff(product_name="Opdivo", indication="NSCLC", peak_sales_millions=8_000, loe_year=2028, revenue_at_risk_millions=5_000),
        ],
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=10_853,
            max_comfortable_deal_size_millions=15_000,
        ),
        ta_priorities={"oncology": 1.0, "hematology": 0.9, "immunology": 0.8, "cardiovascular": 0.6, "neuroscience": 0.4},
        modality_capabilities=ModalityCapabilities(small_molecule=0.8, monoclonal_antibody=0.9, cell_therapy=0.75),
        notes=(
            "Q1 2026: Cash $10.85B, debt $44.46B, net debt $33.61B. Levered; buyer discipline assumed. "
            "Management explicitly pursuing BD to diversify. Data confidence: high (0.82). "
            "Diligence: inspect post-Eliquis-cliff urgency; test cell-therapy/high-CMC tolerance; model stock vs. cash structures."
        ),
    ),
    AcquirerProfile(
        company_id="novartis",
        name="Novartis",
        ticker="NVS",
        country="Switzerland",
        cash_millions=11_000,
        annual_fcf_millions=3_300,
        market_cap_millions=289_717,
        net_debt_millions=38_100,
        strategic_areas=["oncology", "cardiovascular", "immunology", "neuroscience"],
        preferred_modalities=["small_molecule", "biologic", "radioligand"],
        bd_style=BDStyle.MIXED,
        preferred_phase="Phase 2",
        deal_capacity=DealCapacity(max_comfortable_deal_size_millions=30_000),
        ta_priorities={"cardiovascular": 0.8, "immunology": 0.8, "oncology": 0.9, "neuroscience": 0.7},
        modality_capabilities=ModalityCapabilities(small_molecule=0.9, monoclonal_antibody=0.9, antisense=0.7),
        bd_history_detailed=BDHistoryDetailed(
            acquisitions=[
                AcquisitionRecord(target="Avidity Biosciences", year=2026, therapeutic_area="cardiovascular", modality="oligonucleotide"),
            ],
        ),
        notes=(
            "Q1 2026: Market cap $289.7B, FCF $3.3B, net debt $38.1B (rose from Avidity deal). "
            "Active M&A confirmed. Data confidence: medium-high (0.74). "
            "Diligence: map appetite for more RNA/editing post-Avidity; refresh covenant/rating posture; prioritize assets with clean global rights."
        ),
    ),
    AcquirerProfile(
        company_id="roche",
        name="Roche",
        ticker="RHHBY",
        country="Switzerland",
        cash_millions=14_000,
        annual_fcf_millions=15_000,
        market_cap_millions=240_000,
        strategic_areas=["oncology", "immunology", "neuroscience", "infectious_disease"],
        preferred_modalities=["biologic", "antibody", "small_molecule"],
        bd_style=BDStyle.PLATFORM,
        preferred_phase="Phase 2",
        deal_capacity=DealCapacity(max_comfortable_deal_size_millions=25_000),
        ta_priorities={"oncology": 1.0, "ophthalmology": 0.8, "neuroscience": 0.7},
        modality_capabilities=ModalityCapabilities(monoclonal_antibody=1.0, small_molecule=0.7),
        notes=(
            "Diagnostics-linked medicine focus; continued strategic biotech M&A participation. "
            "Balance-sheet fields not fully retrieved in current run. Data confidence: low-medium (0.35). "
            "Diligence: refresh cash/leverage from latest finance report; separate pharma vs. diagnostics fit; review CNS and ophthalmology appetite."
        ),
    ),
    AcquirerProfile(
        company_id="abbvie",
        name="AbbVie",
        ticker="ABBV",
        country="United States",
        cash_millions=5_100,
        debt_millions=36_465,
        annual_fcf_millions=16_000,
        market_cap_millions=373_232,
        strategic_areas=["immunology", "oncology", "neuroscience", "aesthetics"],
        preferred_modalities=["biologic", "small_molecule"],
        bd_style=BDStyle.BLOCKBUSTER,
        preferred_phase="Phase 3",
        loe_cliffs=[
            LOECliff(product_name="Humira", indication="immunology", peak_sales_millions=9_000, loe_year=2023, revenue_at_risk_millions=5_000),
        ],
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=5_100,
            max_comfortable_deal_size_millions=22_000,
        ),
        ta_priorities={"immunology": 1.0, "neuroscience": 0.9, "oncology": 0.8, "aesthetics": 0.7},
        modality_capabilities=ModalityCapabilities(small_molecule=0.9, monoclonal_antibody=0.9, antibody_drug_conjugate=0.7),
        notes=(
            "Market cap $373.2B, cash $5.1B, debt $36.5B. Motivated but balance-sheet-selective buyer. "
            "Strongest fit: immunology, neuroscience, oncology, ophthalmology/aesthetics. Data confidence: medium (0.58). "
            "Diligence: refresh post-Q1 debt/paydown from 10-Q; test bolt-on vs. platform preference; rank immunology assets first."
        ),
    ),
    AcquirerProfile(
        company_id="amgen",
        name="Amgen",
        ticker="AMGN",
        country="United States",
        cash_millions=12_000,
        debt_millions=57_300,
        annual_fcf_millions=9_000,
        market_cap_millions=177_513,
        strategic_areas=["oncology", "cardiovascular", "bone", "inflammation"],
        preferred_modalities=["biologic", "small_molecule", "bispecific"],
        bd_style=BDStyle.BOLT_ON,
        preferred_phase="Phase 2",
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=12_000,
            max_comfortable_deal_size_millions=16_000,
        ),
        ta_priorities={"inflammation": 0.8, "rare_disease": 0.8, "cardiometabolic": 0.7, "oncology": 0.7},
        modality_capabilities=ModalityCapabilities(monoclonal_antibody=1.0, small_molecule=0.7, gene_therapy=0.4),
        notes=(
            "Q1 2026: Cash $12.0B, debt $57.3B (highly levered post-Horizon), Q1 FCF ~$0.7B. "
            "More likely selective assets than giant auctions. Data confidence: medium-high (0.76). "
            "Diligence: examine appetite for another large deal post-Horizon; prioritize biologics/rare-disease strengths; discount complex CMC/cell-therapy deals."
        ),
    ),
    AcquirerProfile(
        company_id="gilead",
        name="Gilead Sciences",
        ticker="GILD",
        country="United States",
        cash_millions=10_600,
        annual_fcf_millions=8_000,
        market_cap_millions=162_493,
        strategic_areas=["oncology", "hiv", "liver_disease", "inflammation"],
        preferred_modalities=["small_molecule", "biologic", "cell_therapy"],
        bd_style=BDStyle.MIXED,
        preferred_phase="Phase 2",
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=10_600,
            max_comfortable_deal_size_millions=15_000,
        ),
        ta_priorities={"virology": 1.0, "oncology": 0.8, "inflammation": 0.8},
        modality_capabilities=ModalityCapabilities(small_molecule=0.8, monoclonal_antibody=0.8, cell_therapy=0.75),
        notes=(
            "Market cap $162.5B, cash $10.6B (YE 2025). Focus: virology, oncology, inflammation. "
            "Active partnering; fit question sharper than size question. Data confidence: medium-high (0.68). "
            "Diligence: update current-quarter cash/debt from 10-Q; focus on immunology/inflammation and cell-therapy gaps; test control vs. partnership preference."
        ),
    ),
]

ACQUIRER_BY_ID: dict[str, AcquirerProfile] = {a.company_id: a for a in ACQUIRER_UNIVERSE}
ACQUIRER_BY_TICKER: dict[str, AcquirerProfile] = {
    a.ticker: a for a in ACQUIRER_UNIVERSE if a.ticker
}


# ---------------------------------------------------------------------------
# Acquirer ranking (v0)
# ---------------------------------------------------------------------------

class AcquirerMatch(BaseModel):
    """
    A single ranked acquirer result.

    Attributes
    ----------
    company_id          : Canonical acquirer identifier.
    name                : Human-readable name.
    ticker              : Exchange ticker.
    ta_match            : True if target's TA is in acquirer's strategic_areas.
    modality_match      : True if target's modality is in acquirer's preferred_modalities.
    loe_urgency         : Composite LOE urgency score [0–1].
    budget_ok           : True if acquirer can afford the target at the specified deal size.
    cash_firepower_millions : Estimated acquisition capacity.
    composite_score     : Combined ranking score (0–1). Higher is a better fit.
    rationale           : One-sentence human-readable explanation.
    """
    company_id: str
    name: str
    ticker: Optional[str] = None
    ta_match: bool
    modality_match: bool
    loe_urgency: float = Field(ge=0.0, le=1.0)
    budget_ok: bool
    cash_firepower_millions: float
    composite_score: float = Field(ge=0.0, le=1.0)
    rationale: str


def rank_acquirers(
    therapeutic_area: str,
    modality: str,
    deal_size_millions: float,
    top_n: int = 2,
    universe: Optional[list[AcquirerProfile]] = None,
    ta_weight: float = 0.45,
    loe_weight: float = 0.35,
    budget_weight: float = 0.20,
) -> list[AcquirerMatch]:
    """
    Rank acquirers from ``ACQUIRER_UNIVERSE`` for a given target.

    Composite score = ta_weight × ta_match
                    + loe_weight × loe_urgency
                    + budget_weight × budget_ok

    Parameters
    ----------
    therapeutic_area    : Target's TA (e.g. "oncology").
    modality            : Target's modality (e.g. "small_molecule").
    deal_size_millions  : Estimated deal size (use rNPV or NAV as proxy).
    top_n               : How many top acquirers to return.
    universe            : Custom acquirer list (defaults to ACQUIRER_UNIVERSE).
    ta_weight           : Weight for TA match (0–1).
    loe_weight          : Weight for LOE urgency (0–1).
    budget_weight       : Weight for budget fit (0–1).

    Returns
    -------
    List of up to *top_n* AcquirerMatch objects, sorted by composite_score desc.
    """
    if universe is None:
        universe = ACQUIRER_UNIVERSE

    results: list[AcquirerMatch] = []
    for acq in universe:
        ta = acq.covers_ta(therapeutic_area)
        mod = acq.covers_modality(modality)
        loe = acq.loe_urgency
        budget = acq.can_afford(deal_size_millions)

        score = (
            ta_weight * float(ta)
            + loe_weight * loe
            + budget_weight * float(budget)
        )
        score = round(min(1.0, max(0.0, score)), 4)

        reasons: list[str] = []
        if ta:
            reasons.append(f"{therapeutic_area} is a strategic area")
        if loe > 0.1:
            reasons.append(f"LOE urgency={loe:.2f}")
        if budget:
            reasons.append(f"firepower ${acq.cash_firepower_millions:,.0f}M covers deal")
        elif not budget:
            reasons.append(f"firepower ${acq.cash_firepower_millions:,.0f}M may be tight")
        rationale = "; ".join(reasons) if reasons else "no strong strategic fit signals"

        results.append(AcquirerMatch(
            company_id=acq.company_id,
            name=acq.name,
            ticker=acq.ticker,
            ta_match=ta,
            modality_match=mod,
            loe_urgency=loe,
            budget_ok=budget,
            cash_firepower_millions=acq.cash_firepower_millions,
            composite_score=score,
            rationale=rationale,
        ))

    results.sort(key=lambda r: r.composite_score, reverse=True)
    return results[:top_n]
