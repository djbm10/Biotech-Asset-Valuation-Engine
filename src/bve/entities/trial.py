import warnings
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class SpendProfile(str, Enum):
    """
    How cost_millions is modelled as cash flowing within the phase.

    UNIFORM (default)
        All cost treated as occurring at the phase midpoint.
        Backward-compatible — bit-for-bit identical to pre-E1 results.
        PV = cost / (1+r)^((year_start + year_end) / 2)

    ANNUAL_UNIFORM
        Cost spread uniformly across integer-year intervals within the phase.
        Each sub-interval [t, t+1] contributes a fraction proportional to its
        length; the PV is computed at that sub-interval's midpoint.
        Produces a slightly lower PV for long phases because spending early in
        the phase is discounted at a shorter horizon than the overall midpoint.
    """
    UNIFORM = "uniform"
    ANNUAL_UNIFORM = "annual_uniform"


class TrialArm(BaseModel):
    label: str
    arm_type: str    # EXPERIMENTAL | ACTIVE_COMPARATOR | PLACEBO_COMPARATOR
    intervention: Optional[str] = None


class TrialCostBreakdown(BaseModel):
    """
    Audit-only decomposition of ClinicalTrial.cost_millions into sub-components.

    Does NOT affect any computation — the engine uses cost_millions directly.
    Provides source traceability for cost estimates (CRO bid grids, SEC filings,
    partner disclosures, analyst estimates).

    All components default to 0.0. Set only the components that are known;
    any residual can go in other_millions.

    A UserWarning is emitted at ClinicalTrial construction when this breakdown is
    provided and the sum deviates from cost_millions by more than 5%.
    """
    model_config = ConfigDict(frozen=True)

    cro_fees_millions: float = Field(
        default=0.0, ge=0.0,
        description="CRO fees: site monitoring, project management, data entry.",
    )
    investigator_fees_millions: float = Field(
        default=0.0, ge=0.0,
        description="Investigator and site fees: PI grants, site activation, patient visits.",
    )
    clinical_supply_millions: float = Field(
        default=0.0, ge=0.0,
        description="Drug supply for trial: API, formulation batches, comparator.",
    )
    data_management_millions: float = Field(
        default=0.0, ge=0.0,
        description="Data management, biostatistics, DSMB, medical monitoring.",
    )
    regulatory_millions: float = Field(
        default=0.0, ge=0.0,
        description="Regulatory activities: IND/CTA amendments, FDA meeting prep.",
    )
    internal_overhead_millions: float = Field(
        default=0.0, ge=0.0,
        description="Internal FTE, program management, finance overhead.",
    )
    other_millions: float = Field(
        default=0.0, ge=0.0,
        description="Other costs not captured in the above categories.",
    )

    source: Optional[str] = Field(
        default=None,
        description="Provenance of this breakdown (e.g. 'CRO bid grid Q3-2026', 'SEC 10-K FY2025').",
    )
    notes: Optional[str] = None

    @property
    def total_millions(self) -> float:
        """Sum of all cost components in USD millions."""
        return (
            self.cro_fees_millions
            + self.investigator_fees_millions
            + self.clinical_supply_millions
            + self.data_management_millions
            + self.regulatory_millions
            + self.internal_overhead_millions
            + self.other_millions
        )


# Maximum allowed deviation between cost_breakdown.total_millions and cost_millions.
_BREAKDOWN_DEVIATION_THRESHOLD = 0.05   # 5%


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
    spend_profile: SpendProfile = Field(
        default=SpendProfile.UNIFORM,
        description=(
            "How cost_millions is modelled within the phase for discounting. "
            "'uniform' (default): all cost at midpoint — backward-compatible. "
            "'annual_uniform': cost spread across integer-year intervals within the phase."
        ),
    )
    cost_source: str = Field(
        default="override",
        description=(
            "'override' (default): cost_millions is the analyst's asset-specific estimate "
            "(SEC filings, partner disclosures, CRO quotes). Engine uses it as-is. "
            "'default': requests TA-calibrated substitution — engine replaces cost_millions "
            "with the industry median for this TA and phase from phase_cost_defaults "
            "in industry_assumptions.yaml, and emits a UserWarning. "
            "'default_applied': set by the engine after substitution (audit trail only). "
            "Rare-disease Phase 2 (~$30M) vs large oncology RCT (~$300M) differ 10x "
            "from the cross-TA flat default — always prefer 'override' with a real estimate."
        )
    )
    cost_breakdown: Optional[TrialCostBreakdown] = Field(
        default=None,
        description=(
            "Audit-only decomposition of cost_millions into sub-components. "
            "Does not affect computation. If provided, the sum should be within 5% "
            "of cost_millions; a UserWarning is emitted if it deviates more."
        ),
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

    @model_validator(mode="after")
    def _check_breakdown_consistency(self) -> "ClinicalTrial":
        """Warn when cost_breakdown total deviates more than 5% from cost_millions."""
        bd = self.cost_breakdown
        if bd is None or bd.total_millions == 0.0:
            return self
        deviation = abs(bd.total_millions - self.cost_millions) / self.cost_millions
        if deviation > _BREAKDOWN_DEVIATION_THRESHOLD:
            warnings.warn(
                f"ClinicalTrial '{self.phase.value}' for asset '{self.asset_id}': "
                f"cost_breakdown total ${bd.total_millions:.2f}M deviates "
                f"{deviation:.1%} from cost_millions ${self.cost_millions:.2f}M "
                f"(threshold {_BREAKDOWN_DEVIATION_THRESHOLD:.0%}). "
                "Align the breakdown components or update cost_millions.",
                UserWarning,
                stacklevel=2,
            )
        return self

    @property
    def phase_order(self) -> int:
        return PHASE_ORDER[self.phase.value]
