from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from bve.config.constants import PHASE_ORDER


class TrialPhase(str, Enum):
    PHASE_1 = "phase_1"
    PHASE_2 = "phase_2"
    PHASE_3 = "phase_3"
    NDA_BLA = "nda_bla"


class TrialStatus(str, Enum):
    NOT_YET_RECRUITING = "not_yet_recruiting"
    RECRUITING = "recruiting"
    ACTIVE_NOT_RECRUITING = "active_not_recruiting"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    WITHDRAWN = "withdrawn"
    UNKNOWN = "unknown"


class EndpointType(str, Enum):
    """Quality of primary endpoint — major driver of regulatory and POS confidence."""
    HARD_CLINICAL = "hard_clinical"    # OS, DFS, cardiovascular events
    SURROGATE_VALIDATED = "surrogate_validated"  # PFS in oncology (regulatory precedent)
    SURROGATE_NOVEL = "surrogate_novel"  # Biomarker surrogate, limited validation
    BIOMARKER_ONLY = "biomarker_only"    # PK/PD, target engagement


class TrialArm(BaseModel):
    label: str
    arm_type: str    # EXPERIMENTAL | ACTIVE_COMPARATOR | PLACEBO_COMPARATOR
    intervention: Optional[str] = None


class ClinicalTrial(BaseModel):
    asset_id: str
    phase: TrialPhase

    # Identification
    nct_id: Optional[str] = None
    title: Optional[str] = None

    # Outcome
    success_probability: float = Field(
        gt=0.0, le=1.0,
        description="Analyst estimate of passing this phase. Use pos_model to derive."
    )
    primary_endpoint: Optional[str] = None
    endpoint_type: EndpointType = EndpointType.SURROGATE_VALIDATED

    # Timeline + cost
    duration_years: float = Field(gt=0.0)
    cost_millions: float = Field(gt=0.0)
    cost_source: str = Field(
        default="default",
        description=(
            "'default' if cost_millions is the industry median from assumptions.yaml. "
            "'override' if cost_millions was set from asset-specific research (SEC filings, "
            "partner disclosures, analyst estimates). Engine warns at run time when 'default' "
            "is used, because rare-disease Phase 2 (~$15M) and large oncology RCT (~$500M) "
            "can differ 2-4× from the industry median."
        )
    )
    start_date: Optional[str] = None
    primary_completion_date: Optional[str] = None

    # Design
    enrollment: Optional[int] = Field(default=None, gt=0)
    arms: list[TrialArm] = Field(default_factory=list)
    status: TrialStatus = TrialStatus.UNKNOWN
    is_randomized: bool = True
    is_blinded: bool = True

    # Source of truth
    data_source: str = "manual"   # manual | clinicaltrials_gov | sec_filing

    notes: Optional[str] = None

    @property
    def phase_order(self) -> int:
        return PHASE_ORDER[self.phase.value]
