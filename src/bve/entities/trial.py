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
    """Quality and type of primary trial endpoint.

    Four legacy values (backward-compatible):
      HARD_CLINICAL, SURROGATE_VALIDATED, SURROGATE_NOVEL, BIOMARKER_ONLY

    Specific endpoint values (TA-aware scoring in pos_model._ENDPOINT_LOGODDS_BY_TA):
      Use these when the clinical endpoint is known for more precise scoring.
      Log-odds look-up is keyed by (therapeutic_area, endpoint_type); the generic
      fallback table covers all TAs and endpoint types not in the TA-specific table.
    """
    # ---- Legacy / generic buckets (backward-compatible) ----
    HARD_CLINICAL = "hard_clinical"          # OS, DFS, mortality — any TA
    SURROGATE_VALIDATED = "surrogate_validated"   # PFS, HbA1c, LDL-C — accepted surrogates
    SURROGATE_NOVEL = "surrogate_novel"      # Novel surrogate, limited regulatory precedent
    BIOMARKER_ONLY = "biomarker_only"        # PK/PD, target engagement — weak alone

    # ---- Hard clinical outcomes (specific) ----
    EFS_DFS = "efs_dfs"                      # Event-free / disease-free survival
    MACE = "mace"                            # CV death + MI + stroke composite
    HOSPITALIZATION_REDUCTION = "hospitalization_reduction"
    EXACERBATION_REDUCTION = "exacerbation_reduction"   # Asthma/COPD flare reduction
    CLINICAL_CURE = "clinical_cure"          # Infectious disease: cure endpoint
    DISEASE_PREVENTION = "disease_prevention"    # Vaccine: infection / severe disease
    SEIZURE_RELAPSE_REDUCTION = "seizure_relapse_reduction"  # Epilepsy / MS

    # ---- Strong validated surrogates ----
    PFS = "pfs"                              # Progression-free survival (oncology)
    ORR = "orr"                              # Objective response rate
    CR_CRI = "cr_cri"                        # Complete remission / CRi (hematology)
    DOR = "dor"                              # Duration of response
    MRD_NEGATIVITY = "mrd_negativity"        # Minimal residual disease (hematology)
    TRANSFUSION_INDEPENDENCE = "transfusion_independence"   # MDS / blood disorders
    CLINICAL_REMISSION = "clinical_remission"  # IBD, rheumatology, steroid-free remission
    VALIDATED_CLINICAL_SCORE = "validated_clinical_score"  # ACR50/70, PASI90, EASI75
    VISUAL_ACUITY = "visual_acuity"          # BCVA letters, VA gain/loss (ophthalmology)
    FUNCTIONAL_IMPROVEMENT = "functional_improvement"  # ALSFRS-R, 6MWT, FEV1

    # ---- Moderate / context-dependent surrogates ----
    QOL_PRO = "qol_pro"                      # QoL / validated patient-reported outcomes
    HBA1C_VALIDATED = "hba1c_validated"      # HbA1c, LDL-C, BP, weight loss
    VIRAL_LOAD_REDUCTION = "viral_load_reduction"   # Viral load, eGFR slope
    COGNITIVE_SCALE = "cognitive_scale"      # ADAS-Cog, UPDRS, CDR-SB, MADRS, PANSS
    IMAGING_ANATOMIC = "imaging_anatomic"    # MRI lesions, OCT, plaque regression
    MOLECULAR_BIOMARKER = "molecular_biomarker"  # ctDNA, amyloid, NfL, MRD by PCR
    BIOMARKER_CORRECTION = "biomarker_correction"   # Protein / enzyme replacement

    # ---- Weak / mechanistic ----
    LIVER_ENZYME = "liver_enzyme"            # ALT/AST, insulin sensitivity markers


class GeneTherapyConcern(str, Enum):
    """Gene / cell therapy–specific overlay adjustments.

    Applied additively in log-odds space on top of the TA endpoint score.
    Add multiple concerns to POSAdjusters.gene_cell_therapy_concerns when
    modality is gene therapy or cell therapy.

    These are NOT substitutes for endpoint_type — they are overlays that
    capture modality-specific risk and durability signals.
    """
    DURABLE_FUNCTIONAL_CORRECTION = "durable_functional_correction"   # +0.275
    DURABLE_BIOMARKER_CAUSAL = "durable_biomarker_causal"             # +0.175
    SHORT_FOLLOWUP_ONLY = "short_followup_only"                        # −0.175
    WANING_EFFECT_RISK = "waning_effect_risk"                          # −0.225
    SERIOUS_SAFETY_CONCERN = "serious_safety_concern"                  # −0.425
    MANUFACTURING_INCONSISTENCY = "manufacturing_inconsistency"        # −0.300
    BIOMARKER_ONLY_NO_FUNCTION = "biomarker_only_no_function"          # −0.300


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
