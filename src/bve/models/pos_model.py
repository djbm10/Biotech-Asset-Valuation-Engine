"""
Probability-of-Success (POS) model.

Two-layer approach:
  1. Start with industry-prior base rate for (therapeutic_area, phase)
  2. Apply trial-specific adjusters in log-odds space to produce
     an asset-specific POS estimate

Log-odds approach ensures adjusters are additive and the result stays
bounded in (0, 1). Each adjuster is calibrated to shift the probability
by a plausible magnitude around the base rate.

Reference: Lee et al. (2019) "Predicting drug development pipeline results"
           Biomedtracker/IQVIA phase transition data
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from bve.config.constants import PHASE_SUCCESS_RATES
from bve.entities.asset import ApprovalPathwayType, TherapeuticArea
from bve.entities.trial import EndpointType, GeneTherapyConcern, TrialPhase

_AA_NDA_DISCOUNT: float = 0.18  # confirmatory trial risk discount for accelerated approval


# ---------------------------------------------------------------------------
# Adjuster enumerations
# ---------------------------------------------------------------------------

class MoAPrecedent(str, Enum):
    """
    How clinically validated is the target / mechanism?

    Eight tiers, from established class down to known liability.
    Legacy values (VALIDATED, PARTIAL, NOVEL) preserved for backward
    compatibility with existing YAML configs and CSV backtest datasets.
    """
    # ── Positive precedent ──────────────────────────────────────────────────
    VALIDATED = "validated"                   # Multiple approved drugs, same target/MoA (+0.35)
    VALIDATED_CLASS = "validated_class"       # Explicit alias for VALIDATED; preferred in new configs
    CLINICALLY_VALIDATED_TARGET = "clinically_validated_target"  # Human efficacy shown, few/no approved (+0.20)
    PATHWAY_VALIDATED = "pathway_validated"   # Same pathway validated, exact target not (+0.05)

    # ── Neutral ─────────────────────────────────────────────────────────────
    PARTIAL = "partial"                       # Early human signal or strong translational rationale (0.00)

    # ── Negative precedent ──────────────────────────────────────────────────
    PRECLINICAL_ONLY = "preclinical_only"     # Animal/in vitro only, no human efficacy (−0.20)
    NOVEL = "novel"                           # Novel FIC target, no human validation (−0.35)
    PRIOR_FAILURES = "prior_failures"         # Prior class/target failures in same indication (−0.50)
    KNOWN_LIABILITY = "known_liability"       # Known translational or safety liability (−0.60)


class MoAExceptionFlag(str, Enum):
    """
    Override signals that can partially rescue a weak MoA precedent score.

    Applied ADDITIVELY in log-odds space on top of the MoAPrecedent base value.
    Example: NOVEL (−0.35) + GENETICALLY_VALIDATED_TARGET (+0.20) → −0.15.

    Use in POSAdjusters.moa_exception_flags when evidence warrants it.
    Do NOT stack flags speculatively; each should be supportable by data.
    """
    GENETICALLY_VALIDATED_TARGET = "genetically_validated_target"    # +0.20: strong human genetics (GWAS, Mendelian)
    HUMAN_PROOF_OF_MECHANISM = "human_proof_of_mechanism"            # +0.15: human POM shown (biomarker, PK/PD)
    STRONG_BIOMARKER_RESPONSE = "strong_biomarker_response"          # +0.10: clear, dose-dependent biomarker signal
    PRIOR_FAILURES_DUE_TO_BAD_DRUG = "prior_failures_due_to_bad_drug"  # +0.25: prior failures were drug quality, not target


class SampleSizeAdequacy(str, Enum):
    """
    Statistical power and design adequacy for the primary endpoint.

    Score by power and design quality, NOT raw patient count alone.
    80 patients can be adequate in rare disease; insufficient in CVOT.
    Use TA context and expected effect size when assigning this tier.

    TA guidance:
      Oncology:            50–300 may be adequate depending on endpoint
      Rare disease:        20–100 acceptable if effect size is large
      Cardiovascular:      often thousands needed for event reduction
      CNS/Psychiatry:      larger N due to high placebo response
      Ophthalmology:       smaller N feasible with paired-eye designs
      Renal/Metabolic:     large N for hard outcomes (eGFR slope, MACE)
    """
    WELL_POWERED  = "well_powered"    # ≥90% power, realistic effect-size assumptions (+0.20)
    ADEQUATE      = "adequate"        # 80–89% power, standard registrational design (0.00)
    BORDERLINE    = "borderline"      # 70–79% power or aggressive effect-size assumptions (−0.20)
    UNDERPOWERED  = "underpowered"    # <70% power; may be too small to prove the claim (−0.45)
    UNVERIFIABLE  = "unverifiable"    # No disclosed power calc or unclear stat plan (−0.25)
    EXPLORATORY   = "exploratory"     # Tiny/open-label/signal-seeking; not confirmatory (−0.50)


class SafetyProfile(str, Enum):
    CLEAN = "clean"                  # No clinically meaningful safety signals
    MINOR = "minor"                  # Grade 1-2 AEs; manageable; no Grade 4/5
    CONCERNING = "concerning"        # Grade 3+ SAEs; dose-limiting toxicities
    SERIOUS = "serious"              # On-target toxicity, black box warnings


class CompetitivePressure(str, Enum):
    LOW = "low"                      # Limited / no approved competitors
    MODERATE = "moderate"            # 1-3 approved competitors; differentiated profile
    HIGH = "high"                    # Crowded class; commodity-like differentiation


# ---------------------------------------------------------------------------
# Log-odds adjusters (calibrated empirically)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Generic endpoint log-odds fallback (all TAs not in _ENDPOINT_LOGODDS_BY_TA,
# and all EndpointType values not in a given TA-specific sub-dict).
# Midpoints are used for user-specified ranges (e.g. "+0.25 to +0.35" → +0.30).
# ---------------------------------------------------------------------------
_ENDPOINT_LOGODDS_GENERIC: dict[EndpointType, float] = {
    # Legacy buckets — preserved for backward compatibility
    EndpointType.HARD_CLINICAL: +0.40,
    EndpointType.SURROGATE_VALIDATED: 0.00,
    EndpointType.SURROGATE_NOVEL: -0.30,
    EndpointType.BIOMARKER_ONLY: -0.55,

    # Specific hard clinical outcomes
    EndpointType.EFS_DFS: +0.30,
    EndpointType.MACE: +0.40,
    EndpointType.HOSPITALIZATION_REDUCTION: +0.30,
    EndpointType.EXACERBATION_REDUCTION: +0.25,
    EndpointType.CLINICAL_CURE: +0.325,
    EndpointType.DISEASE_PREVENTION: +0.45,
    EndpointType.SEIZURE_RELAPSE_REDUCTION: +0.30,

    # Strong validated surrogates
    EndpointType.PFS: +0.15,
    EndpointType.ORR: 0.00,
    EndpointType.CR_CRI: +0.15,
    EndpointType.DOR: 0.00,
    EndpointType.MRD_NEGATIVITY: +0.10,
    EndpointType.TRANSFUSION_INDEPENDENCE: +0.175,
    EndpointType.CLINICAL_REMISSION: +0.35,
    EndpointType.VALIDATED_CLINICAL_SCORE: +0.25,
    EndpointType.VISUAL_ACUITY: +0.425,
    EndpointType.FUNCTIONAL_IMPROVEMENT: +0.20,

    # Moderate / context-dependent
    EndpointType.QOL_PRO: +0.075,
    EndpointType.HBA1C_VALIDATED: +0.175,
    EndpointType.VIRAL_LOAD_REDUCTION: +0.10,
    EndpointType.COGNITIVE_SCALE: +0.075,
    EndpointType.IMAGING_ANATOMIC: -0.05,
    EndpointType.MOLECULAR_BIOMARKER: -0.125,
    EndpointType.BIOMARKER_CORRECTION: 0.00,

    # Weak / mechanistic
    EndpointType.LIVER_ENZYME: -0.175,
}

# Backward-compatible alias — empirical engine imports this name.
_ENDPOINT_LOGODDS = _ENDPOINT_LOGODDS_GENERIC

# ---------------------------------------------------------------------------
# Therapeutic-area–specific endpoint log-odds tables.
# Keys: TherapeuticArea.value strings.  For each TA, only overrides are listed;
# anything not in the TA sub-dict falls through to _ENDPOINT_LOGODDS_GENERIC.
#
# Score derivation: midpoints of user-specified ranges rounded to 3 dp.
#   "+0.25 to +0.35" → +0.30   "−0.05 to 0.00" → −0.025 → −0.025
# ---------------------------------------------------------------------------
_ENDPOINT_LOGODDS_BY_TA: dict[str, dict[EndpointType, float]] = {
    # ------------------------------------------------------------------
    # Oncology — solid tumors (default oncology TA)
    # OS strongest; PFS accepted but not survival-linked; ORR for accel. approval.
    # ------------------------------------------------------------------
    "oncology": {
        EndpointType.HARD_CLINICAL:       +0.45,   # OS
        EndpointType.EFS_DFS:             +0.30,   # EFS/DFS: adjuvant/curative settings
        EndpointType.PFS:                 +0.15,   # PFS: accepted surrogate
        EndpointType.ORR:                 -0.025,  # ORR: accel. approval, weaker
        EndpointType.DOR:                  0.00,   # DoR: contextual
        EndpointType.CR_CRI:              -0.05,   # CR/PR: response depth, not enough alone
        EndpointType.MOLECULAR_BIOMARKER: -0.175,  # ctDNA: midpoint −0.25 to −0.10
        EndpointType.QOL_PRO:             +0.075,  # QoL: midpoint 0.00 to +0.15
        EndpointType.BIOMARKER_ONLY:      -0.55,   # PD biomarker only
        EndpointType.SURROGATE_VALIDATED:  +0.15,  # Treated as PFS in this TA
        EndpointType.SURROGATE_NOVEL:     -0.25,
    },

    # ------------------------------------------------------------------
    # Oncology — hematology
    # CR/MRD/transfusion independence are very meaningful in blood cancers.
    # ------------------------------------------------------------------
    "hematology": {
        EndpointType.HARD_CLINICAL:           +0.45,   # OS
        EndpointType.EFS_DFS:                 +0.30,   # EFS/PFS: midpoint +0.25 to +0.35
        EndpointType.CR_CRI:                  +0.20,   # CR/CRi: midpoint +0.15 to +0.25
        EndpointType.MRD_NEGATIVITY:          +0.125,  # MRD: midpoint 0.00 to +0.25
        EndpointType.DOR:                     +0.10,   # Durability matters
        EndpointType.TRANSFUSION_INDEPENDENCE:+0.175,  # MDS/blood disorders
        EndpointType.ORR:                     +0.05,   # Hematologic response
        EndpointType.MOLECULAR_BIOMARKER:     -0.475,  # Biomarker: midpoint −0.40 to −0.55
        EndpointType.BIOMARKER_ONLY:          -0.475,
        EndpointType.SURROGATE_VALIDATED:     +0.20,
    },

    # ------------------------------------------------------------------
    # Rare disease
    # Indication-specific logic essential; biomarker value context-dependent.
    # ------------------------------------------------------------------
    "rare_disease": {
        EndpointType.HARD_CLINICAL:           +0.45,   # Survival / ventilator-free
        EndpointType.FUNCTIONAL_IMPROVEMENT:  +0.325,  # Validated function: midpoint +0.25 to +0.40
        EndpointType.HOSPITALIZATION_REDUCTION:+0.275, # Event reduction: midpoint +0.20 to +0.35
        EndpointType.VALIDATED_CLINICAL_SCORE: +0.20,  # Disease-specific scale
        EndpointType.QOL_PRO:                 +0.10,   # Caregiver/PRO: midpoint 0.00 to +0.20
        EndpointType.BIOMARKER_CORRECTION:     0.00,   # Context-dependent: midpoint −0.20 to +0.20
        EndpointType.HBA1C_VALIDATED:         -0.15,   # Protein expression: midpoint −0.30 to 0.00
        EndpointType.MOLECULAR_BIOMARKER:     -0.15,   # PD biomarker: context-specific
        EndpointType.BIOMARKER_ONLY:          -0.55,
        EndpointType.SURROGATE_VALIDATED:     +0.20,
        EndpointType.SURROGATE_NOVEL:         -0.20,
    },

    # ------------------------------------------------------------------
    # Cardiovascular
    # Hard outcomes dominate; validated surrogates (LDL-C, BP) accepted.
    # ------------------------------------------------------------------
    "cardiovascular": {
        EndpointType.HARD_CLINICAL:           +0.45,   # All-cause / CV mortality
        EndpointType.MACE:                    +0.40,   # MACE composite
        EndpointType.EFS_DFS:                 +0.40,   # Stroke/MI reduction: midpoint +0.35 to +0.45
        EndpointType.HOSPITALIZATION_REDUCTION:+0.30,  # HF hospitalization: midpoint +0.25 to +0.35
        EndpointType.HBA1C_VALIDATED:         +0.175,  # LDL-C: midpoint +0.10 to +0.25
        EndpointType.QOL_PRO:                 +0.15,   # BP reduction: midpoint +0.10 to +0.20
        EndpointType.IMAGING_ANATOMIC:        -0.05,   # Plaque regression: midpoint −0.10 to 0.00
        EndpointType.BIOMARKER_ONLY:          -0.475,  # midpoint −0.40 to −0.55
        EndpointType.SURROGATE_VALIDATED:     +0.175,
        EndpointType.SURROGATE_NOVEL:         -0.25,
    },

    # ------------------------------------------------------------------
    # Immunology / inflammation
    # Validated clinical scores (ACR/PASI/EASI) are NOT generic biomarkers.
    # ------------------------------------------------------------------
    "immunology": {
        EndpointType.HARD_CLINICAL:           +0.45,
        EndpointType.CLINICAL_REMISSION:      +0.35,   # Clinical / steroid-free remission
        EndpointType.IMAGING_ANATOMIC:        +0.275,  # Endoscopic remission: midpoint +0.20 to +0.35
        EndpointType.VALIDATED_CLINICAL_SCORE:+0.30,   # ACR50/70, PASI90/100, EASI75/90
        EndpointType.ORR:                     +0.10,   # ACR20: midpoint +0.05 to +0.15
        EndpointType.QOL_PRO:                 +0.225,  # Flare reduction: midpoint +0.15 to +0.30
        EndpointType.BIOMARKER_ONLY:          -0.475,  # midpoint −0.40 to −0.55
        EndpointType.SURROGATE_VALIDATED:     +0.175,
        EndpointType.SURROGATE_NOVEL:         -0.25,
    },

    # ------------------------------------------------------------------
    # CNS / neurology + psychiatry
    # Conservative: high placebo rates, subjective scales, trial noise.
    # ------------------------------------------------------------------
    "cns": {
        EndpointType.HARD_CLINICAL:           +0.45,   # Mortality
        EndpointType.FUNCTIONAL_IMPROVEMENT:  +0.35,   # Disability progression: midpoint +0.30 to +0.40
        EndpointType.SEIZURE_RELAPSE_REDUCTION:+0.30,  # Seizure/relapse reduction
        EndpointType.CLINICAL_REMISSION:      +0.20,   # Psychiatric remission rate
        EndpointType.COGNITIVE_SCALE:         +0.075,  # Functional scales: midpoint 0.00 to +0.15
        EndpointType.QOL_PRO:                 +0.05,   # ADAS-Cog / cognitive: 0.00 to +0.15
        EndpointType.IMAGING_ANATOMIC:        +0.125,  # MRI lesions: midpoint +0.05 to +0.20
        EndpointType.MOLECULAR_BIOMARKER:     -0.125,  # Amyloid/tau/NfL: midpoint −0.30 to +0.05
        EndpointType.BIOMARKER_ONLY:          -0.55,
        EndpointType.SURROGATE_VALIDATED:     +0.10,
        EndpointType.SURROGATE_NOVEL:         -0.35,   # High-noise field; conservative
    },

    # ------------------------------------------------------------------
    # Infectious disease + vaccines
    # Hard endpoints (mortality, hospitalization, cure) dominate.
    # ------------------------------------------------------------------
    "infectious_disease": {
        EndpointType.HARD_CLINICAL:           +0.45,   # Mortality
        EndpointType.DISEASE_PREVENTION:      +0.45,   # Vaccine: disease / severe disease
        EndpointType.HOSPITALIZATION_REDUCTION:+0.40,  # midpoint +0.35 to +0.45
        EndpointType.CLINICAL_CURE:           +0.325,  # midpoint +0.25 to +0.40
        EndpointType.MOLECULAR_BIOMARKER:     +0.175,  # Microbiological eradication: midpoint +0.10 to +0.25
        EndpointType.VIRAL_LOAD_REDUCTION:    +0.125,  # Viral load: midpoint 0.00 to +0.25
        EndpointType.QOL_PRO:                 +0.075,  # Symptom resolution / resistance
        EndpointType.BIOMARKER_ONLY:          -0.475,  # midpoint −0.40 to −0.55
        EndpointType.SURROGATE_VALIDATED:     +0.125,
    },

    # ------------------------------------------------------------------
    # Oncology — solid tumor (granular alias; identical to "oncology" entry)
    # New configs should prefer oncology_solid when TA is solid tumor.
    # ------------------------------------------------------------------
    "oncology_solid": {
        EndpointType.HARD_CLINICAL:       +0.45,
        EndpointType.EFS_DFS:             +0.30,
        EndpointType.PFS:                 +0.15,
        EndpointType.ORR:                 -0.025,
        EndpointType.DOR:                  0.00,
        EndpointType.CR_CRI:              -0.05,
        EndpointType.MOLECULAR_BIOMARKER: -0.175,
        EndpointType.QOL_PRO:             +0.075,
        EndpointType.BIOMARKER_ONLY:      -0.55,
        EndpointType.SURROGATE_VALIDATED:  +0.15,
        EndpointType.SURROGATE_NOVEL:     -0.25,
    },

    # ------------------------------------------------------------------
    # Psychiatry (split from CNS/neurology 2026-Q2)
    # High placebo response in MDD/anxiety RCTs; PANSS/MADRS/HDRS validated.
    # ------------------------------------------------------------------
    "psychiatry": {
        EndpointType.HARD_CLINICAL:       +0.45,   # Suicidality endpoints
        EndpointType.CLINICAL_REMISSION:  +0.30,   # Remission rate (HDRS, PANSS)
        EndpointType.COGNITIVE_SCALE:     +0.10,   # MADRS, PANSS negative/cognitive
        EndpointType.QOL_PRO:             +0.05,   # Patient-reported outcomes
        EndpointType.FUNCTIONAL_IMPROVEMENT: +0.20, # Functional impairment scales
        EndpointType.IMAGING_ANATOMIC:    +0.05,   # Neuroimaging biomarker
        EndpointType.MOLECULAR_BIOMARKER: -0.15,   # CSF/plasma biomarkers
        EndpointType.BIOMARKER_ONLY:      -0.55,
        EndpointType.SURROGATE_VALIDATED: +0.10,
        EndpointType.SURROGATE_NOVEL:     -0.35,   # Conservative; high noise field
    },

    # ------------------------------------------------------------------
    # Metabolic / endocrine (diabetes, obesity, lipids, NASH)
    # Well-validated surrogates (HbA1c, weight loss, LDL-C); strong precedent.
    # ------------------------------------------------------------------
    "metabolic": {
        EndpointType.HARD_CLINICAL:       +0.45,   # CV death, HF hospitalization
        EndpointType.MACE:                +0.40,   # CVOT MACE endpoint
        EndpointType.HOSPITALIZATION_REDUCTION: +0.30,
        EndpointType.HBA1C_VALIDATED:     +0.25,   # HbA1c, LDL-C, weight loss — core metabolic
        EndpointType.FUNCTIONAL_IMPROVEMENT: +0.15, # Liver histology, fibrosis regression
        EndpointType.QOL_PRO:             +0.10,
        EndpointType.IMAGING_ANATOMIC:    +0.05,   # MRI-PDFF, liver fat fraction
        EndpointType.LIVER_ENZYME:        -0.10,   # ALT/AST alone insufficient
        EndpointType.MOLECULAR_BIOMARKER: -0.15,   # Biomarker-only weak
        EndpointType.BIOMARKER_ONLY:      -0.50,
        EndpointType.SURROGATE_VALIDATED: +0.20,
        EndpointType.SURROGATE_NOVEL:     -0.20,
    },

    # ------------------------------------------------------------------
    # Dermatology (psoriasis, atopic dermatitis, alopecia, urticaria)
    # Objective validated scales (PASI, IGA, EASI); strong IL-17/IL-23 precedent.
    # ------------------------------------------------------------------
    "dermatology": {
        EndpointType.HARD_CLINICAL:       +0.40,
        EndpointType.VALIDATED_CLINICAL_SCORE: +0.35, # PASI90/100, EASI75/90, IGA 0/1
        EndpointType.CLINICAL_REMISSION:  +0.30,   # Complete clearance
        EndpointType.QOL_PRO:             +0.20,   # DLQI, patient-reported itch/NRS
        EndpointType.IMAGING_ANATOMIC:    +0.10,   # Histology
        EndpointType.BIOMARKER_ONLY:      -0.50,
        EndpointType.SURROGATE_VALIDATED: +0.20,
        EndpointType.SURROGATE_NOVEL:     -0.20,
    },

    # ------------------------------------------------------------------
    # Gastroenterology / non-IBD (GERD, IBS, NASH liver-specific, cholestatic)
    # PRO endpoints carry high placebo response; histologic endpoints more robust.
    # IBD (Crohn's, UC) should use immunology TA — same ACR/endoscopy framework.
    # ------------------------------------------------------------------
    "gastroenterology": {
        EndpointType.HARD_CLINICAL:       +0.40,   # Mortality, hepatic events
        EndpointType.FUNCTIONAL_IMPROVEMENT: +0.25, # Histologic fibrosis regression
        EndpointType.CLINICAL_REMISSION:  +0.20,   # Symptom-free / clinical cure
        EndpointType.VALIDATED_CLINICAL_SCORE: +0.20, # IBS-SSS, CDAI (shared use)
        EndpointType.QOL_PRO:             +0.075,  # Symptom PROs; high placebo
        EndpointType.IMAGING_ANATOMIC:    +0.05,   # MRI-PDFF, liver stiffness
        EndpointType.LIVER_ENZYME:        -0.10,   # ALT/AST alone insufficient
        EndpointType.MOLECULAR_BIOMARKER: -0.10,
        EndpointType.BIOMARKER_ONLY:      -0.50,
        EndpointType.SURROGATE_VALIDATED: +0.10,
        EndpointType.SURROGATE_NOVEL:     -0.25,
    },

    # ------------------------------------------------------------------
    # Pulmonary / respiratory (COPD, asthma, IPF, PAH, bronchiectasis)
    # FEV1/FVC and exacerbation reduction accepted; spirometry has placebo noise.
    # ------------------------------------------------------------------
    "pulmonary": {
        EndpointType.HARD_CLINICAL:       +0.45,   # Mortality / transplant-free survival
        EndpointType.EXACERBATION_REDUCTION: +0.35, # Exacerbation rate reduction
        EndpointType.HOSPITALIZATION_REDUCTION: +0.30,
        EndpointType.FUNCTIONAL_IMPROVEMENT: +0.25, # FEV1, 6MWT, DLCO
        EndpointType.QOL_PRO:             +0.10,   # SGRQ, CAT score; placebo response
        EndpointType.IMAGING_ANATOMIC:    +0.05,   # CT quantitative imaging
        EndpointType.MOLECULAR_BIOMARKER: -0.10,   # Biomarker (FeNO, blood eos alone)
        EndpointType.BIOMARKER_ONLY:      -0.50,
        EndpointType.SURROGATE_VALIDATED: +0.15,
        EndpointType.SURROGATE_NOVEL:     -0.25,
    },

    # ------------------------------------------------------------------
    # Renal (CKD, IgA nephropathy, FSGS, glomerulonephritis)
    # eGFR slope accepted by FDA/EMA as approvable endpoint since 2020.
    # ------------------------------------------------------------------
    "renal": {
        EndpointType.HARD_CLINICAL:       +0.45,   # Kidney failure / ESKD
        EndpointType.HOSPITALIZATION_REDUCTION: +0.30, # AKI hospitalization
        EndpointType.FUNCTIONAL_IMPROVEMENT: +0.30, # eGFR slope / CKD progression
        EndpointType.HBA1C_VALIDATED:     +0.20,   # eGFR (analogous to validated surrogate)
        EndpointType.MOLECULAR_BIOMARKER: -0.10,   # Proteinuria alone borderline
        EndpointType.BIOMARKER_ONLY:      -0.50,
        EndpointType.SURROGATE_VALIDATED: +0.20,
        EndpointType.SURROGATE_NOVEL:     -0.20,
    },

    # ------------------------------------------------------------------
    # Ophthalmology
    # Visual acuity is the core regulatory endpoint; anatomic biomarkers weak alone.
    # ------------------------------------------------------------------
    "ophthalmology": {
        EndpointType.HARD_CLINICAL:           +0.425,  # Avoided vision loss: midpoint +0.35 to +0.45
        EndpointType.VISUAL_ACUITY:           +0.425,  # BCVA letters / VA gain/loss
        EndpointType.HBA1C_VALIDATED:         +0.175,  # Injection burden reduction
        EndpointType.QOL_PRO:                 +0.10,   # Durability interval: midpoint 0.00 to +0.20
        EndpointType.IMAGING_ANATOMIC:        +0.075,  # Retinal thickness / OCT
        EndpointType.MOLECULAR_BIOMARKER:     -0.20,   # Anatomic biomarker: midpoint −0.30 to −0.10
        EndpointType.BIOMARKER_ONLY:          -0.55,
        EndpointType.SURROGATE_VALIDATED:     +0.175,
    },
}

# ---------------------------------------------------------------------------
# Gene / cell therapy overlay log-odds (additive on top of TA endpoint score).
# Applied per GeneTherapyConcern listed in POSAdjusters.gene_cell_therapy_concerns.
# ---------------------------------------------------------------------------
_GENE_THERAPY_LOGODDS: dict[GeneTherapyConcern, float] = {
    GeneTherapyConcern.DURABLE_FUNCTIONAL_CORRECTION: +0.275,  # midpoint +0.20 to +0.35
    GeneTherapyConcern.DURABLE_BIOMARKER_CAUSAL:      +0.175,  # midpoint +0.10 to +0.25
    GeneTherapyConcern.SHORT_FOLLOWUP_ONLY:            -0.175,  # midpoint −0.10 to −0.25
    GeneTherapyConcern.WANING_EFFECT_RISK:             -0.225,  # midpoint −0.15 to −0.30
    GeneTherapyConcern.SERIOUS_SAFETY_CONCERN:         -0.425,  # midpoint −0.25 to −0.60
    GeneTherapyConcern.MANUFACTURING_INCONSISTENCY:    -0.300,  # midpoint −0.20 to −0.40
    GeneTherapyConcern.BIOMARKER_ONLY_NO_FUNCTION:     -0.300,  # midpoint −0.20 to −0.40
}

_MOA_LOGODDS: dict[MoAPrecedent, float] = {
    # Positive precedent
    MoAPrecedent.VALIDATED:                   +0.35,  # legacy: same as VALIDATED_CLASS
    MoAPrecedent.VALIDATED_CLASS:             +0.35,  # multiple approved drugs, same target/MoA
    MoAPrecedent.CLINICALLY_VALIDATED_TARGET: +0.20,  # human efficacy shown; few/no approved
    MoAPrecedent.PATHWAY_VALIDATED:           +0.05,  # same pathway valid; exact target not
    # Neutral
    MoAPrecedent.PARTIAL:                      0.00,  # early human signal / strong translational
    # Negative precedent
    MoAPrecedent.PRECLINICAL_ONLY:            -0.20,  # animal/in vitro only; no human efficacy
    MoAPrecedent.NOVEL:                       -0.35,  # FIC, no human validation
    MoAPrecedent.PRIOR_FAILURES:              -0.50,  # prior class failures in same indication
    MoAPrecedent.KNOWN_LIABILITY:             -0.60,  # known translational or safety liability
}

_MOA_EXCEPTION_LOGODDS: dict[MoAExceptionFlag, float] = {
    MoAExceptionFlag.GENETICALLY_VALIDATED_TARGET:    +0.20,  # strong human genetics (GWAS, Mendelian)
    MoAExceptionFlag.HUMAN_PROOF_OF_MECHANISM:        +0.15,  # human POM shown in biomarker/PK-PD
    MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE:       +0.10,  # clear dose-dependent biomarker signal
    MoAExceptionFlag.PRIOR_FAILURES_DUE_TO_BAD_DRUG:  +0.25,  # prior failures = drug quality, not target
}

_SAMPLE_LOGODDS: dict[SampleSizeAdequacy, float] = {
    SampleSizeAdequacy.WELL_POWERED:  +0.20,   # ≥90% power; strong design
    SampleSizeAdequacy.ADEQUATE:       0.00,   # 80–89%; standard registrational (reference)
    SampleSizeAdequacy.UNVERIFIABLE:  -0.25,   # No disclosed power calc; cannot confirm adequacy
    SampleSizeAdequacy.BORDERLINE:    -0.20,   # 70–79% or aggressive effect size (was −0.25)
    SampleSizeAdequacy.UNDERPOWERED:  -0.45,   # <70% power; real risk of false negative (was −0.50)
    SampleSizeAdequacy.EXPLORATORY:   -0.50,   # Signal-seeking only; hypothesis-generating
}

_SAFETY_LOGODDS: dict[SafetyProfile, float] = {
    SafetyProfile.CLEAN: +0.10,
    SafetyProfile.MINOR: 0.00,
    SafetyProfile.CONCERNING: -0.35,
    SafetyProfile.SERIOUS: -0.80,
}

_COMPETITION_LOGODDS: dict[CompetitivePressure, float] = {
    CompetitivePressure.LOW: +0.15,       # Less pressure to show superiority
    CompetitivePressure.MODERATE: 0.00,
    CompetitivePressure.HIGH: -0.15,
}

_BIOMARKER_SELECTION_BONUS: float = 0.40  # log-odds bonus for biomarker-enriched population
_PRIOR_PHASE_SUCCESS_BONUS: float = 0.25  # log-odds bonus for strong prior-phase data

# Layer 1 combined cap (Sprint 9): applies to the net adjustment from the base rate.
# Rationale: +0.80 at 32% Phase 2 oncology base → ~47% adjusted POS (plausible for
# biomarker-selected BTD assets). +1.80 (pre-cap max) → 62% — implausible.
_L1_CAP_POSITIVE: float = 0.80
_L1_CAP_NEGATIVE: float = -0.80

# Breakthrough Therapy Designation: process designation, not approval probability.
# Primary effect is faster FDA review, not higher binary approval likelihood.
# +0.05 retains a tiny signal for FDA engagement level. (Was +0.20 pre-Sprint-9.)
_BTD_LOGODDS: float = 0.05


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class POSAdjusters(BaseModel):
    """
    Trial-specific qualitative adjusters applied on top of the base rate.
    Defaults represent the "average" trial with no special circumstances.

    endpoint_type — use the specific EndpointType value when the primary endpoint
    is known (e.g. EndpointType.OS, EndpointType.PFS). The TA-specific lookup in
    _ENDPOINT_LOGODDS_BY_TA will apply the correct score; the generic fallback covers
    all other cases.  Legacy values (HARD_CLINICAL, SURROGATE_VALIDATED, etc.) are
    still accepted for backward compatibility.

    gene_cell_therapy_concerns — add one or more GeneTherapyConcern values when the
    modality is gene therapy or cell therapy.  Each concern applies an additive
    log-odds adjustment on top of the endpoint type score.  This field has no effect
    for other modalities (empty list = no adjustment).
    """
    endpoint_type: EndpointType = EndpointType.SURROGATE_VALIDATED
    moa_precedent: MoAPrecedent = MoAPrecedent.PARTIAL
    sample_size_adequacy: SampleSizeAdequacy = SampleSizeAdequacy.ADEQUATE
    safety_profile: SafetyProfile = SafetyProfile.MINOR
    competitive_pressure: CompetitivePressure = CompetitivePressure.MODERATE

    # Boolean qualitative factors
    biomarker_selected_population: bool = Field(
        default=False,
        description="Is the trial in a biomarker-selected (enriched) population?"
    )
    strong_prior_phase_data: bool = Field(
        default=False,
        description="Did prior phase show strong, consistent efficacy signals?"
    )
    has_breakthrough_designation: bool = Field(
        default=False,
        description="Does the asset have FDA Breakthrough Therapy designation?"
    )

    # Gene / cell therapy overlay (list of concerns; empty = no modality overlay)
    gene_cell_therapy_concerns: list[GeneTherapyConcern] = Field(
        default_factory=list,
        description=(
            "Gene/cell therapy–specific risk and durability signals. "
            "Apply additively on top of the endpoint type score. "
            "No effect for non-gene/cell therapy modalities."
        ),
    )

    # MoA exception flags — partial override for weak precedent tiers
    moa_exception_flags: list[MoAExceptionFlag] = Field(
        default_factory=list,
        description=(
            "Evidence signals that partially rescue a weak MoA precedent score. "
            "Applied additively in log-odds space on top of the moa_precedent value. "
            "Example: NOVEL (−0.35) + GENETICALLY_VALIDATED_TARGET (+0.20) → −0.15. "
            "Do not stack flags speculatively — each must be supportable by data."
        ),
    )


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_pos(
    phase: TrialPhase,
    therapeutic_area: TherapeuticArea,
    adjusters: Optional[POSAdjusters] = None,
    approval_pathway: Optional[ApprovalPathwayType] = None,
) -> float:
    """
    Compute probability of success for a given trial phase.

    Parameters
    ----------
    phase:             the trial phase being evaluated
    therapeutic_area:  used to select the base rate
    adjusters:         optional qualitative adjusters (defaults = average trial)
    approval_pathway:  when ACCELERATED, applies an 18% discount to the NDA/BLA
                       base rate (confirmatory trial risk for AA programs)

    Returns
    -------
    float in (0, 1) — estimated probability of passing this phase
    """
    if adjusters is None:
        adjusters = POSAdjusters()

    ta_key = therapeutic_area.value
    phase_key = phase.value

    # Look up base rate; fall back to "all" if TA not found
    base_rates = PHASE_SUCCESS_RATES.get(ta_key) or PHASE_SUCCESS_RATES["all"]
    base_rate = base_rates.get(phase_key, 0.40)

    # Accelerated approval: apply confirmatory trial risk discount at NDA/BLA phase.
    # AA programs using surrogate endpoints face ~15-20% post-market withdrawal/
    # conversion failure rate. This is a BASE RATE correction, not a log-odds adjuster.
    if (
        approval_pathway is not None
        and approval_pathway == ApprovalPathwayType.ACCELERATED
        and phase == TrialPhase.NDA_BLA
    ):
        base_rate = base_rate * (1.0 - _AA_NDA_DISCOUNT)

    # Convert to log-odds
    base_rate = max(0.01, min(0.99, base_rate))  # avoid ±inf
    log_odds = math.log(base_rate / (1.0 - base_rate))

    # Apply adjusters — sum into a named delta for cap enforcement
    adjustment = _compute_layer1_adjustment(adjusters, ta_value=ta_key)

    # Cap the combined adjustment (not the absolute log-odds) so the TA base
    # rate is preserved; only analyst qualitative input is bounded.
    adjustment = max(_L1_CAP_NEGATIVE, min(_L1_CAP_POSITIVE, adjustment))
    log_odds += adjustment

    # Convert back
    pos = 1.0 / (1.0 + math.exp(-log_odds))
    return round(pos, 4)


def _endpoint_logodds(endpoint_type: EndpointType, ta_value: str) -> float:
    """Look up endpoint log-odds with TA-specific override, generic fallback."""
    ta_table = _ENDPOINT_LOGODDS_BY_TA.get(ta_value, {})
    if endpoint_type in ta_table:
        return ta_table[endpoint_type]
    return _ENDPOINT_LOGODDS_GENERIC.get(endpoint_type, 0.0)


def _compute_layer1_adjustment(adjusters: POSAdjusters, ta_value: str = "other") -> float:
    """
    Sum all Layer 1 qualitative adjusters into a single log-odds delta.

    ta_value: TherapeuticArea.value string used for TA-specific endpoint scoring.
    Extracted as a named function so tests can verify the raw adjustment
    (pre-cap) and cap boundary behaviour independently.
    """
    delta = 0.0
    delta += _endpoint_logodds(adjusters.endpoint_type, ta_value)
    delta += _MOA_LOGODDS[adjusters.moa_precedent]
    # MoA exception flags: partial override for weak precedent (additive)
    for flag in adjusters.moa_exception_flags:
        delta += _MOA_EXCEPTION_LOGODDS.get(flag, 0.0)
    delta += _SAMPLE_LOGODDS[adjusters.sample_size_adequacy]
    delta += _SAFETY_LOGODDS[adjusters.safety_profile]
    delta += _COMPETITION_LOGODDS[adjusters.competitive_pressure]

    if adjusters.biomarker_selected_population:
        delta += _BIOMARKER_SELECTION_BONUS
    if adjusters.strong_prior_phase_data:
        delta += _PRIOR_PHASE_SUCCESS_BONUS
    if adjusters.has_breakthrough_designation:
        # BTD is a process designation; primary effect is faster review, not higher
        # binary approval probability. +0.05 retains a tiny signal for FDA engagement.
        delta += _BTD_LOGODDS

    # Gene / cell therapy overlays (additive; no effect when list is empty)
    for concern in adjusters.gene_cell_therapy_concerns:
        delta += _GENE_THERAPY_LOGODDS.get(concern, 0.0)

    return delta


def compute_cumulative_pos(phase_pos_list: list[float]) -> float:
    """Compound individual phase POS values to overall approval probability."""
    result = 1.0
    for p in phase_pos_list:
        result *= p
    return round(result, 6)


# ---------------------------------------------------------------------------
# Convenience: apply POS model to a list of trials
# ---------------------------------------------------------------------------

def apply_pos_to_trials(
    trials: list,  # list[ClinicalTrial] - avoiding circular import
    therapeutic_area: TherapeuticArea,
    per_phase_adjusters: Optional[dict[TrialPhase, POSAdjusters]] = None,
    approval_pathway: Optional[ApprovalPathwayType] = None,
) -> list:
    """
    Return a new list of trials with success_probability overwritten by POS model.

    per_phase_adjusters: dict mapping TrialPhase → POSAdjusters.
    Phases not in the dict use default POSAdjusters().
    approval_pathway: when ACCELERATED, applies NDA/BLA confirmatory risk discount.
    """
    if per_phase_adjusters is None:
        per_phase_adjusters = {}

    updated = []
    for trial in trials:
        adj = per_phase_adjusters.get(trial.phase, POSAdjusters())
        pos = compute_pos(trial.phase, therapeutic_area, adj, approval_pathway=approval_pathway)
        updated.append(trial.model_copy(update={"success_probability": pos}))
    return updated
