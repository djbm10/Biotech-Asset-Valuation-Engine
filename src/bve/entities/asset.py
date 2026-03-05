from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DevelopmentStage(str, Enum):
    PRECLINICAL = "preclinical"
    PHASE_1 = "phase_1"
    PHASE_2 = "phase_2"
    PHASE_3 = "phase_3"
    NDA_BLA = "nda_bla"
    APPROVED = "approved"


class TherapeuticArea(str, Enum):
    ONCOLOGY = "oncology"
    RARE_DISEASE = "rare_disease"
    CNS = "cns"
    CARDIOVASCULAR = "cardiovascular"
    IMMUNOLOGY = "immunology"
    INFECTIOUS_DISEASE = "infectious_disease"
    OTHER = "other"


class Modality(str, Enum):
    SMALL_MOLECULE = "small_molecule"
    BIOLOGIC = "biologic"
    GENE_THERAPY = "gene_therapy"
    CELL_THERAPY = "cell_therapy"
    ADC = "adc"
    RNA_THERAPY = "rna_therapy"
    OTHER = "other"


class Catalyst(BaseModel):
    description: str
    expected_date: Optional[str] = None     # ISO date or "Q3 2025" style
    catalyst_type: str = "readout"          # readout | fda_action | partnership | milestone
    probability_positive: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class Asset(BaseModel):
    id: str
    name: str
    indication: str
    indication_id: Optional[str] = None     # links to Indication entity
    therapeutic_area: TherapeuticArea
    stage: DevelopmentStage
    modality: Modality = Modality.SMALL_MOLECULE
    mechanism_of_action: Optional[str] = None

    # Development timeline
    launch_year: Optional[int] = None
    patent_expiry_year: Optional[int] = None

    # Economics
    discount_rate: float = Field(
        default=0.10, gt=0.0, lt=1.0,
        description="WACC used to discount cash flows"
    )
    royalty_rate: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Royalty paid to licensor (net ownership = 1 - royalty_rate)"
    )
    milestones_payable_millions: float = Field(
        default=0.0, ge=0.0,
        description="Future milestone payments owed to partners (PV-adjusted separately)"
    )

    # Catalysts and competitive context
    upcoming_catalysts: list[Catalyst] = Field(default_factory=list)
    competitor_assets: list[str] = Field(
        default_factory=list,
        description="Names or IDs of key competitive assets"
    )
    differentiation_notes: Optional[str] = None
    notes: Optional[str] = None

    @property
    def net_ownership(self) -> float:
        return 1.0 - self.royalty_rate
