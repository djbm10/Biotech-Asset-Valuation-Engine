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


class BDHistoryItem(BaseModel):
    """One historical acquisition or major partnership."""
    target_name: str
    deal_type: str  # acquisition | license_in | partnership
    announced_year: int
    deal_value_millions: Optional[float] = None
    therapeutic_area: Optional[str] = None
    phase_at_deal: Optional[str] = None
    notes: Optional[str] = None


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

# Seeded with the largest acquirers by historical deal activity.
# financial figures are approximate and should be refreshed from market data.
ACQUIRER_UNIVERSE: list[AcquirerProfile] = [
    AcquirerProfile(
        company_id="pfizer",
        name="Pfizer",
        ticker="PFE",
        cash_millions=15_000,
        annual_fcf_millions=8_000,
        market_cap_millions=145_000,
        strategic_areas=["oncology", "immunology", "rare_disease", "vaccines"],
        preferred_modalities=["small_molecule", "biologic", "mRNA"],
        bd_style=BDStyle.BLOCKBUSTER,
        preferred_phase="Phase 3",
        max_deal_size_millions=20_000,
        loe_cliffs=[
            LOECliff(product_name="Eliquis", indication="AF/VTE", peak_sales_millions=6_500, loe_year=2028, revenue_at_risk_millions=4_000),
        ],
    ),
    AcquirerProfile(
        company_id="eli_lilly",
        name="Eli Lilly",
        ticker="LLY",
        cash_millions=3_000,
        annual_fcf_millions=12_000,
        market_cap_millions=750_000,
        strategic_areas=["diabetes", "obesity", "oncology", "immunology", "neuroscience"],
        preferred_modalities=["small_molecule", "biologic", "antibody"],
        bd_style=BDStyle.PLATFORM,
        preferred_phase="Phase 2",
        max_deal_size_millions=15_000,
    ),
    AcquirerProfile(
        company_id="merck",
        name="Merck & Co",
        ticker="MRK",
        cash_millions=8_000,
        annual_fcf_millions=14_000,
        market_cap_millions=250_000,
        strategic_areas=["oncology", "vaccines", "infectious_disease", "cardiometabolic"],
        preferred_modalities=["biologic", "small_molecule", "antibody_drug_conjugate"],
        bd_style=BDStyle.PLATFORM,
        preferred_phase="Phase 2",
        loe_cliffs=[
            LOECliff(product_name="Keytruda", indication="multiple oncology", peak_sales_millions=25_000, loe_year=2028, revenue_at_risk_millions=15_000),
        ],
    ),
    AcquirerProfile(
        company_id="astrazeneca",
        name="AstraZeneca",
        ticker="AZN",
        cash_millions=7_000,
        annual_fcf_millions=9_000,
        market_cap_millions=280_000,
        strategic_areas=["oncology", "cardiovascular", "respiratory", "rare_disease"],
        preferred_modalities=["biologic", "antibody_drug_conjugate", "small_molecule"],
        bd_style=BDStyle.BOLT_ON,
        preferred_phase="Phase 2",
    ),
    AcquirerProfile(
        company_id="bristol_myers_squibb",
        name="Bristol-Myers Squibb",
        ticker="BMY",
        cash_millions=8_500,
        annual_fcf_millions=7_000,
        market_cap_millions=135_000,
        strategic_areas=["oncology", "hematology", "immunology", "cardiovascular"],
        preferred_modalities=["biologic", "small_molecule", "cell_therapy"],
        bd_style=BDStyle.BLOCKBUSTER,
        preferred_phase="Phase 3",
        loe_cliffs=[
            LOECliff(product_name="Revlimid", indication="myeloma", peak_sales_millions=7_000, loe_year=2026, revenue_at_risk_millions=5_000),
            LOECliff(product_name="Opdivo", indication="NSCLC", peak_sales_millions=8_000, loe_year=2028, revenue_at_risk_millions=5_000),
        ],
    ),
    AcquirerProfile(
        company_id="novartis",
        name="Novartis",
        ticker="NVS",
        cash_millions=11_000,
        annual_fcf_millions=10_000,
        market_cap_millions=220_000,
        strategic_areas=["oncology", "cardiovascular", "immunology", "neuroscience"],
        preferred_modalities=["small_molecule", "biologic", "radioligand"],
        bd_style=BDStyle.MIXED,
        preferred_phase="Phase 2",
    ),
    AcquirerProfile(
        company_id="roche",
        name="Roche",
        ticker="RHHBY",
        cash_millions=14_000,
        annual_fcf_millions=15_000,
        market_cap_millions=240_000,
        strategic_areas=["oncology", "immunology", "neuroscience", "infectious_disease"],
        preferred_modalities=["biologic", "antibody", "small_molecule"],
        bd_style=BDStyle.PLATFORM,
        preferred_phase="Phase 2",
    ),
    AcquirerProfile(
        company_id="abbvie",
        name="AbbVie",
        ticker="ABBV",
        cash_millions=9_000,
        annual_fcf_millions=16_000,
        market_cap_millions=310_000,
        strategic_areas=["immunology", "oncology", "neuroscience", "aesthetics"],
        preferred_modalities=["biologic", "small_molecule"],
        bd_style=BDStyle.BLOCKBUSTER,
        preferred_phase="Phase 3",
        loe_cliffs=[
            LOECliff(product_name="Humira", indication="immunology", peak_sales_millions=9_000, loe_year=2023, revenue_at_risk_millions=5_000),
        ],
    ),
    AcquirerProfile(
        company_id="amgen",
        name="Amgen",
        ticker="AMGN",
        cash_millions=10_000,
        annual_fcf_millions=9_000,
        market_cap_millions=160_000,
        strategic_areas=["oncology", "cardiovascular", "bone", "inflammation"],
        preferred_modalities=["biologic", "small_molecule", "bispecific"],
        bd_style=BDStyle.BOLT_ON,
        preferred_phase="Phase 2",
    ),
    AcquirerProfile(
        company_id="gilead",
        name="Gilead Sciences",
        ticker="GILD",
        cash_millions=7_000,
        annual_fcf_millions=8_000,
        market_cap_millions=90_000,
        strategic_areas=["oncology", "hiv", "liver_disease", "inflammation"],
        preferred_modalities=["small_molecule", "biologic", "cell_therapy"],
        bd_style=BDStyle.MIXED,
        preferred_phase="Phase 2",
    ),
]

ACQUIRER_BY_ID: dict[str, AcquirerProfile] = {a.company_id: a for a in ACQUIRER_UNIVERSE}
ACQUIRER_BY_TICKER: dict[str, AcquirerProfile] = {
    a.ticker: a for a in ACQUIRER_UNIVERSE if a.ticker
}
