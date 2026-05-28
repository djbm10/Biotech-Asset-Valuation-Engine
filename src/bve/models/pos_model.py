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
import warnings
from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from bve.config.constants import PHASE_SUCCESS_RATES
from bve.entities.asset import ApprovalPathwayType, TherapeuticArea
from bve.entities.trial import BreakthroughDesignationType, EndpointType, GeneTherapyConcern, GeneTherapyModality, TrialPhase

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
    """
    Clinical tolerability risk from prior phase data.

    Six-tier scale reflecting risk that safety will block dosing, approval, or adoption.
    Score by the PATTERN of risk, not AE grade alone — a reversible Grade 3 lab
    abnormality is very different from irreversible organ toxicity or mechanism-linked deaths.

    Preferred values (new configs):
      clean, manageable, monitorable_concern, dose_limiting, serious, mechanism_linked_severe

    Legacy values (preserved for backward compatibility):
      minor     → treated as manageable (0.00)
      concerning → treated as dose_limiting (−0.40)
    """
    # ── Six-tier preferred values ────────────────────────────────────────────
    CLEAN                  = "clean"                   # Placebo-like; no meaningful AE/SAE imbalance (+0.10)
    MANAGEABLE             = "manageable"              # Grade 1-2; low discontinuation — baseline (0.00)
    MONITORABLE_CONCERN    = "monitorable_concern"     # Lab abnormalities or manageable Grade 3 (−0.20)
    DOSE_LIMITING          = "dose_limiting"           # DLTs, narrow therapeutic window, high discontinuation (−0.40)
    SERIOUS                = "serious"                 # SAE imbalance, organ toxicity, treatment-related death signal (−0.65)
    MECHANISM_LINKED_SEVERE = "mechanism_linked_severe"  # On-target / class-wide boxed-warning-level risk (−0.80)

    # ── Legacy values (backward-compatible) ─────────────────────────────────
    MINOR      = "minor"       # Alias for MANAGEABLE; Grade 1-2 AEs (0.00)
    CONCERNING = "concerning"  # Alias for DOSE_LIMITING; Grade 3+ AEs (−0.40)


class CompetitivePressure(str, Enum):
    """
    Regulatory / clinical bar the asset must clear given the existing treatment landscape.

    Reflects how hard it is to achieve approval and demonstrate clinically meaningful
    differentiation — not just how many competitors exist.

    Preferred values (new configs):
      low_bar, normal_bar, elevated_bar, high_bar

    Legacy values (preserved for backward compatibility):
      low      → low_bar (+0.10)
      moderate → normal_bar (0.00)
      high     → elevated_bar (−0.15)
    """
    # ── Preferred four-tier values ───────────────────────────────────────────
    LOW_BAR      = "low_bar"       # High unmet need; weak/no standard of care (+0.10)
    NORMAL_BAR   = "normal_bar"    # Accepted endpoint/design for current landscape (0.00)
    ELEVATED_BAR = "elevated_bar"  # Effective standard exists; meaningful differentiation needed (−0.15)
    HIGH_BAR     = "high_bar"      # Head-to-head or superiority trial likely required (−0.30)

    # ── Legacy values (backward-compatible) ─────────────────────────────────
    LOW      = "low"       # Alias for LOW_BAR (+0.10)
    MODERATE = "moderate"  # Alias for NORMAL_BAR (0.00)
    HIGH     = "high"      # Alias for ELEVATED_BAR (−0.15)


class RegulatoryApprovalBar(str, Enum):
    """
    How high is the regulatory / clinical approval bar for this asset?

    Reflects how competitive the approved treatment landscape is, which determines
    how differentiated the new drug must be to gain regulatory acceptance.
    This is a POS adjuster — use in POSAdjusters.regulatory_approval_bar.

    For commercial launch-time competition, use CommercialCrowding instead.

    Log-odds:
      UNCROWDED     +0.10  <3 approved drugs; regulator accepts monotherapy vs placebo
      MODERATE       0.00  3-5 approved drugs; reference bar (standard RCT design)
      CROWDED       -0.10  5-10 approved; meaningful differentiation required
      HIGHLY_CROWDED -0.20  >10 approved; head-to-head or superiority likely required
      UNKNOWN        0.00  No data; treated as MODERATE (adds confidence flag)
    """
    UNCROWDED      = "uncrowded"       # <3 approved drugs in class (+0.10)
    MODERATE       = "moderate"        # 3-5 approved (+0.00, reference)
    CROWDED        = "crowded"         # 5-10 approved (−0.10)
    HIGHLY_CROWDED = "highly_crowded"  # >10 approved (−0.20)
    UNKNOWN        = "unknown"         # No data (0.00 + flag)


class CommercialCrowding(str, Enum):
    """
    Market competition intensity at launch time. Affects REVENUE SHARE, not P(approval).

    Use this in CompetitionModel / MarketModel pricing assumptions — NOT in POSAdjusters.
    P(approval) is determined by regulatory bar (RegulatoryApprovalBar), which looks at
    how hard it is to demonstrate differentiation. Commercial crowding is a post-approval
    concept — how much of the market can the drug capture.
    """
    MONOPOLY        = "monopoly"        # No competing approved therapies at launch
    LOW             = "low"             # Few competitors; limited share pressure
    MODERATE        = "moderate"        # Standard competitive market
    HIGH            = "high"            # Multiple established competitors
    DOMINANT_PLAYER = "dominant_player" # One entrenched player controls >50% share


# Mapping from legacy CompetitivePressure values to RegulatoryApprovalBar
_COMPETITIVE_PRESSURE_TO_RAB: dict[str, RegulatoryApprovalBar] = {
    "low_bar":      RegulatoryApprovalBar.UNCROWDED,
    "normal_bar":   RegulatoryApprovalBar.MODERATE,
    "elevated_bar": RegulatoryApprovalBar.CROWDED,
    "high_bar":     RegulatoryApprovalBar.HIGHLY_CROWDED,
    "low":          RegulatoryApprovalBar.UNCROWDED,
    "moderate":     RegulatoryApprovalBar.MODERATE,
    "high":         RegulatoryApprovalBar.CROWDED,
}


class BiomarkerSelectionStrength(str, Enum):
    """
    Strength of biomarker-based patient enrichment strategy.

    Score reflects both the quality of the predictive biomarker and the
    regulatory/clinical credibility of the enrichment rationale.
    Default is NO_SELECTION (0.00 adjustment — neutral).
    """
    VALIDATED          = "validated"           # Validated predictive biomarker; strong regulatory precedent (+0.40)
    STRONG_RATIONALE   = "strong_rationale"    # Strong biologic rationale / enriched subgroup; not yet fully validated (+0.25)
    EXPLORATORY        = "exploratory"         # Exploratory biomarker subgroup; hypothesis-generating (+0.10)
    NO_SELECTION       = "no_selection"        # No biomarker-based patient selection (0.00 — reference)
    POST_HOC_WEAK      = "post_hoc_weak"       # Post-hoc or weak biomarker rationale; potential selection bias (−0.10)


class PriorPhaseDataStrength(str, Enum):
    """
    Strength of efficacy signal from prior-phase clinical data.

    Captures both the magnitude of the observed signal and how reproducible
    it is across doses, studies, or patient populations.
    Default is MIXED (0.00 adjustment — neutral).
    """
    STRONG_REPLICATED  = "strong_replicated"   # Strong efficacy replicated across ≥2 studies or cohorts (+0.30)
    STRONG_SINGLE      = "strong_single"       # Strong efficacy in a single well-conducted study (+0.20)
    DOSE_RESPONSE      = "dose_response"       # Clean dose-response / exposure-response relationship (+0.15)
    MIXED              = "mixed"               # Mixed, immature, or inconsistent signal (0.00 — reference)
    WEAK               = "weak"                # Weak efficacy signal; numerically positive but unconvincing (−0.20)
    FAILED             = "failed"              # Prior study failed or signal inconsistent across studies (−0.35)


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
    # Block 32: 5 new concerns (EVIDENCE-INFORMED PRIORS)
    GeneTherapyConcern.CAPSID_IMMUNOGENICITY:           -0.225,  # pre-existing immunity; redose risk
    GeneTherapyConcern.INSERTIONAL_MUTAGENESIS_RISK:    -0.175,  # lentiviral/retroviral integration
    GeneTherapyConcern.SINGLE_DOSE_DURABILITY_UNPROVEN: -0.150,  # short F/U + no re-dosing option
    GeneTherapyConcern.MANUFACTURING_SCALE_RISK:        -0.250,  # vector yield / batch consistency
    GeneTherapyConcern.ALLOGENEIC_REJECTION_RISK:       -0.200,  # host rejection of allo product
}

# Block 32: stacking caps to prevent catastrophic over-penalisation
# Durability-related concerns: their combined log-odds are capped at this floor
_GT_DURABILITY_CONCERNS = frozenset([
    GeneTherapyConcern.SHORT_FOLLOWUP_ONLY,
    GeneTherapyConcern.WANING_EFFECT_RISK,
    GeneTherapyConcern.SINGLE_DOSE_DURABILITY_UNPROVEN,
])
_GT_MAX_DURABILITY_PENALTY: float = -0.30  # sum of durability concerns capped here

_GT_MAX_TOTAL_OVERLAY: float = -0.60  # total GT log-odds floor (all concerns combined)

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
    # Six-tier preferred values
    SafetyProfile.CLEAN:                   +0.10,
    SafetyProfile.MANAGEABLE:               0.00,
    SafetyProfile.MONITORABLE_CONCERN:     -0.20,
    SafetyProfile.DOSE_LIMITING:           -0.40,
    SafetyProfile.SERIOUS:                 -0.65,
    SafetyProfile.MECHANISM_LINKED_SEVERE: -0.80,
    # Legacy (backward-compatible)
    SafetyProfile.MINOR:                    0.00,   # = MANAGEABLE
    SafetyProfile.CONCERNING:             -0.40,   # ≈ DOSE_LIMITING (was −0.35)
}

_COMPETITION_LOGODDS: dict[CompetitivePressure, float] = {
    # Preferred four-tier values
    CompetitivePressure.LOW_BAR:      +0.10,   # High unmet need; minimal bar
    CompetitivePressure.NORMAL_BAR:    0.00,   # Standard landscape (reference)
    CompetitivePressure.ELEVATED_BAR: -0.15,   # Differentiation required
    CompetitivePressure.HIGH_BAR:     -0.30,   # Superiority / head-to-head required
    # Legacy (backward-compatible)
    CompetitivePressure.LOW:          +0.10,   # = LOW_BAR (was +0.15)
    CompetitivePressure.MODERATE:      0.00,   # = NORMAL_BAR
    CompetitivePressure.HIGH:         -0.15,   # = ELEVATED_BAR
}

# Block 25: new primary logodds table for RegulatoryApprovalBar
_REGULATORY_APPROVAL_BAR_LOGODDS: dict[RegulatoryApprovalBar, float] = {
    RegulatoryApprovalBar.UNCROWDED:      +0.10,  # <3 approved; low bar
    RegulatoryApprovalBar.MODERATE:        0.00,  # 3-5 approved; reference
    RegulatoryApprovalBar.CROWDED:        -0.10,  # 5-10 approved; differentiation required
    RegulatoryApprovalBar.HIGHLY_CROWDED: -0.20,  # >10 approved; superiority likely needed
    RegulatoryApprovalBar.UNKNOWN:         0.00,  # treated as MODERATE; adds confidence flag
}

_BIOMARKER_LOGODDS: dict[BiomarkerSelectionStrength, float] = {
    BiomarkerSelectionStrength.VALIDATED:        +0.40,  # Validated predictive biomarker
    BiomarkerSelectionStrength.STRONG_RATIONALE: +0.25,  # Strong biologic rationale / enriched subgroup
    BiomarkerSelectionStrength.EXPLORATORY:      +0.10,  # Exploratory biomarker subgroup
    BiomarkerSelectionStrength.NO_SELECTION:      0.00,  # No biomarker selection (reference)
    BiomarkerSelectionStrength.POST_HOC_WEAK:    -0.10,  # Post-hoc or weak biomarker rationale
}

_PRIOR_PHASE_LOGODDS: dict[PriorPhaseDataStrength, float] = {
    PriorPhaseDataStrength.STRONG_REPLICATED: +0.30,  # Strong; replicated across ≥2 studies
    PriorPhaseDataStrength.STRONG_SINGLE:     +0.20,  # Strong; single well-conducted study
    PriorPhaseDataStrength.DOSE_RESPONSE:     +0.15,  # Clean dose-response / exposure-response
    PriorPhaseDataStrength.MIXED:              0.00,  # Mixed / immature signal (reference)
    PriorPhaseDataStrength.WEAK:              -0.20,  # Weak but positive
    PriorPhaseDataStrength.FAILED:            -0.35,  # Prior failure or inconsistent signal
}

# ---------------------------------------------------------------------------
# Block 18 — Scientific Realism adjusters
# ---------------------------------------------------------------------------

class DoseSelectionConfidence(str, Enum):
    """
    Confidence that the dose being advanced is clinically optimal.

    PK/PD characterisation is a consistent Phase 2→3 failure contributor.
    Use UNKNOWN when dose justification is absent — this reduces POS confidence
    (output flag) but does not penalise the point estimate.

    Design: downside-only.  Good dose selection avoids a penalty; it does not
    make the biology more likely to work.

    Log-odds:
      PK_PD_MODELED                    0.00  (no penalty — optimal)
      EXPOSURE_RESPONSE_CHARACTERIZED  0.00  (no penalty)
      EMPIRICAL_FROM_MTD              -0.10  (empirical dose, no exposure model)
      EMPIRICAL_NO_PD_CONFIRMATION    -0.25  (no PD readout confirming dose)
      UNKNOWN                          0.00  + confidence_flag "dose_selection_unknown"
    """
    PK_PD_MODELED                   = "pk_pd_modeled"
    EXPOSURE_RESPONSE_CHARACTERIZED = "exposure_response_characterized"
    EMPIRICAL_FROM_MTD              = "empirical_from_mtd"
    EMPIRICAL_NO_PD_CONFIRMATION    = "empirical_no_pd_confirmation"
    UNKNOWN                         = "unknown"


class ClinicalEffectMagnitude(str, Enum):
    """
    Magnitude of observed clinical effect relative to the minimum clinically
    important difference (MCID) for the primary endpoint.

    IMPORTANT: MCID is user-curated and endpoint-context dependent.  The model
    does not know MCID automatically — you must assess it relative to the
    specific endpoint and TA (e.g., HbA1c reduction, eGFR slope, MADRS score,
    FEV1, ORR).  Do not assign a tier without knowing the relevant MCID.

    Applies only to Phase 2 and Phase 3.  Silent no-op at Phase 1 and NDA/BLA.

    Log-odds (Phase 2/3 only):
      EXCEEDS_MCID  +0.25
      MEETS_MCID     0.00  (reference)
      BELOW_MCID    -0.30
      UNKNOWN        0.00  + confidence_flag "clinical_effect_unknown"

    Default: UNKNOWN — not MEETS_MCID.  Unknown ≠ meets threshold.
    """
    EXCEEDS_MCID = "exceeds_mcid"
    MEETS_MCID   = "meets_mcid"
    BELOW_MCID   = "below_mcid"
    UNKNOWN      = "unknown"


class PlaceboResponseConcern(str, Enum):
    """
    Risk that high placebo response will inflate apparent treatment effect and
    prevent clean statistical separation.

    Applies only to Phase 2 and Phase 3 in CNS, psychiatry, gastroenterology,
    and pain indications.  Silent no-op for all other TAs and phases.

    Log-odds (applicable TAs and phases only):
      UNKNOWN   0.00  + confidence_flag "placebo_response_unassessed"
      NONE      0.00  (explicitly assessed — no placebo inflation risk)
      MODERATE -0.15
      HIGH     -0.30

    Default: UNKNOWN — not NONE.  Unassessed ≠ no risk.
    """
    UNKNOWN  = "unknown"
    NONE     = "none"
    MODERATE = "moderate"
    HIGH     = "high"


_DOSE_SELECTION_LOGODDS: dict[DoseSelectionConfidence, float] = {
    DoseSelectionConfidence.PK_PD_MODELED:                    0.00,
    DoseSelectionConfidence.EXPOSURE_RESPONSE_CHARACTERIZED:  0.00,
    DoseSelectionConfidence.EMPIRICAL_FROM_MTD:              -0.10,
    DoseSelectionConfidence.EMPIRICAL_NO_PD_CONFIRMATION:    -0.25,
    DoseSelectionConfidence.UNKNOWN:                          0.00,  # flag only
}

_CLINICAL_EFFECT_LOGODDS: dict[ClinicalEffectMagnitude, float] = {
    ClinicalEffectMagnitude.EXCEEDS_MCID: +0.25,
    ClinicalEffectMagnitude.MEETS_MCID:   0.00,
    ClinicalEffectMagnitude.BELOW_MCID:  -0.30,
    ClinicalEffectMagnitude.UNKNOWN:      0.00,  # flag only
}

_PLACEBO_RESPONSE_LOGODDS: dict[PlaceboResponseConcern, float] = {
    PlaceboResponseConcern.UNKNOWN:   0.00,  # flag only
    PlaceboResponseConcern.NONE:      0.00,
    PlaceboResponseConcern.MODERATE: -0.15,
    PlaceboResponseConcern.HIGH:     -0.30,
}

# TAs where placebo response concern is clinically meaningful
_PLACEBO_CONCERN_TAS: frozenset[str] = frozenset([
    "cns", "psychiatry", "gastroenterology", "pain",
])

# Phases where ClinicalEffectMagnitude and PlaceboResponseConcern apply
_REALISM_APPLICABLE_PHASES: frozenset[TrialPhase] = frozenset([
    TrialPhase.PHASE_2, TrialPhase.PHASE_3,
])

# Legacy single-value constants — kept for empirical engine backward compat
_BIOMARKER_SELECTION_BONUS: float = 0.40
_PRIOR_PHASE_SUCCESS_BONUS: float = 0.25

# Layer 1 combined cap — applies to the net adjustment from the base rate.
# Rationale: ±0.80 prevents implausible outputs for standard evidence.
# Extraordinary evidence override: when POSAdjusters.extraordinary_evidence=True,
# the positive cap expands to +1.00 to credit rare cases with truly exceptional
# replicated human data (e.g., validated genetic disease with 90% biomarker response).
# Negative cap remains at −0.80 regardless.
_L1_CAP_POSITIVE: float = 0.80
_L1_CAP_POSITIVE_EXTRAORDINARY: float = 1.00
_L1_CAP_NEGATIVE: float = -0.80

# Block 34D — Combined Layer 1 + Layer 2 cap.
# L1 cap is ±0.80; L2 cap is +0.30/−0.60. Without a combined cap, stacking both
# layers allows total adjustment up to +1.10 or −1.40, which is implausible.
# Combined cap: ±0.90 (tighter than the sum of individual caps).
# Applied via compute_design_adjusted_pos(base_rate=...) in trial_design_features.py
# and in _apply_design_adjustments() in valuation_engine.py.
COMBINED_L1_L2_CAP_POSITIVE: float = 0.90
COMBINED_L1_L2_CAP_NEGATIVE: float = -0.90

# Breakthrough Therapy Designation: process designation, not approval probability.
# Primary effect is faster FDA review, not higher binary approval likelihood.
# Block 28: type-conditional table replaces flat constant.
# EVIDENCE-INFORMED PRIORS — conservative values per reviewer guidance.
_BTD_LOGODDS: float = 0.05  # kept for backward compat; GRANTED_STANDARD maps here

_BTD_LOGODDS_BY_TYPE: dict[BreakthroughDesignationType, float] = {
    BreakthroughDesignationType.NONE:                  0.00,
    BreakthroughDesignationType.FAST_TRACK_ONLY:      +0.02,  # process only; minimal POS signal
    BreakthroughDesignationType.GRANTED_STANDARD:     +0.05,  # same as pre-Block-28 default
    BreakthroughDesignationType.GRANTED_RARE_HEME:    +0.10,  # best translation evidence
    BreakthroughDesignationType.GRANTED_SOLID_TUMOR:  +0.03,  # selection-bias adjusted
    BreakthroughDesignationType.GRANTED_EARLY_PHASE:  +0.08,  # strong early FDA engagement
    BreakthroughDesignationType.BREAKTHROUGH_REVOKED: -0.15,  # loss of FDA confidence signal
}

# BTD types that trigger the timeline_acceleration_flag
_BTD_TIMELINE_ACCELERATION_TYPES = frozenset([
    BreakthroughDesignationType.GRANTED_STANDARD,
    BreakthroughDesignationType.GRANTED_RARE_HEME,
    BreakthroughDesignationType.GRANTED_SOLID_TUMOR,
    BreakthroughDesignationType.GRANTED_EARLY_PHASE,
])

# BTD types that can trigger overlap warning (high-tier BTD with strong prior + exceeds_mcid)
_BTD_OVERLAP_WARNING_TYPES = frozenset([
    BreakthroughDesignationType.GRANTED_RARE_HEME,
    BreakthroughDesignationType.GRANTED_EARLY_PHASE,
])


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

    # Block 25: primary field — use regulatory_approval_bar in new code
    regulatory_approval_bar: RegulatoryApprovalBar = Field(
        default=RegulatoryApprovalBar.MODERATE,
        description=(
            "Regulatory approval bar (Block 25). How differentiated must the drug be? "
            "UNCROWDED (+0.10): minimal standard-of-care; MODERATE (0.00): reference; "
            "CROWDED (-0.10): meaningful differentiation required; "
            "HIGHLY_CROWDED (-0.20): head-to-head or superiority needed."
        ),
    )
    # Block 25: deprecated — kept for backward compatibility only
    competitive_pressure: Optional[CompetitivePressure] = Field(
        default=None,
        description="[Deprecated] Use regulatory_approval_bar instead.",
    )

    # Graded qualitative factors (preferred — use these for new configs)
    biomarker_selection: BiomarkerSelectionStrength = Field(
        default=BiomarkerSelectionStrength.NO_SELECTION,
        description=(
            "Strength of biomarker-based patient enrichment. "
            "VALIDATED (+0.40): regulatory precedent; STRONG_RATIONALE (+0.25): biologic enrichment; "
            "EXPLORATORY (+0.10): hypothesis-generating; NO_SELECTION (0.00); POST_HOC_WEAK (−0.10)."
        ),
    )
    prior_phase_data: PriorPhaseDataStrength = Field(
        default=PriorPhaseDataStrength.MIXED,
        description=(
            "Strength of prior-phase efficacy evidence. "
            "STRONG_REPLICATED (+0.30): ≥2 studies; STRONG_SINGLE (+0.20); DOSE_RESPONSE (+0.15); "
            "MIXED (0.00); WEAK (−0.20); FAILED (−0.35)."
        ),
    )
    has_breakthrough_designation: bool = Field(
        default=False,
        description=(
            "FDA Breakthrough Therapy Designation. Process signal; kept small (+0.05). "
            "Does NOT represent a meaningful biological probability boost. "
            "Block 28: use breakthrough_designation (BreakthroughDesignationType) for "
            "type-conditional log-odds. When breakthrough_designation is set, it takes "
            "precedence over this bool."
        ),
    )
    # --- Block 28: type-conditional BTD field ---
    breakthrough_designation: Optional[BreakthroughDesignationType] = Field(
        default=None,
        description=(
            "Block 28: FDA BTD context. Overrides has_breakthrough_designation when set. "
            "GRANTED_STANDARD (+0.05) is backward-compatible with has_breakthrough_designation=True. "
            "BREAKTHROUGH_REVOKED (-0.15) penalises loss of FDA confidence. "
            "None: falls back to has_breakthrough_designation bool."
        ),
    )
    extraordinary_evidence: bool = Field(
        default=False,
        description=(
            "Expert override: expands the positive Layer 1 cap from +0.80 to +1.00. "
            "Requires ALL of: prior_phase_data=STRONG_REPLICATED, biomarker_selection=VALIDATED, "
            "clinical_effect_magnitude=EXCEEDS_MCID, AND a non-empty extraordinary_evidence_rationale. "
            "If any condition is missing, emits UserWarning and resets to False. Block 34B."
        ),
    )
    extraordinary_evidence_rationale: str = Field(
        default="",
        description=(
            "Block 34B: Required text justification when extraordinary_evidence=True. "
            "Must be non-empty to activate the expanded cap. "
            "Example: '91%% biomarker correction replicated across 3 independent cohorts'. "
            "Do not populate without meeting all three evidentiary conditions."
        ),
    )

    # --- Block 18: Scientific Realism adjusters ---
    dose_selection_confidence: DoseSelectionConfidence = Field(
        default=DoseSelectionConfidence.UNKNOWN,
        description=(
            "Confidence in clinical dose optimality. Downside-only adjuster. "
            "PK_PD_MODELED (0.00) through EMPIRICAL_NO_PD_CONFIRMATION (-0.25). "
            "UNKNOWN: no point-estimate change; sets confidence_flag 'dose_selection_unknown'."
        ),
    )
    clinical_effect_magnitude: ClinicalEffectMagnitude = Field(
        default=ClinicalEffectMagnitude.UNKNOWN,
        description=(
            "Observed effect size vs MCID. Phase 2/3 only; silent no-op elsewhere. "
            "MCID is user-curated and endpoint-specific — do not assign without knowing "
            "the relevant threshold for this TA/endpoint. "
            "EXCEEDS_MCID (+0.25), MEETS_MCID (0.00), BELOW_MCID (-0.30). "
            "UNKNOWN: no point-estimate change; sets confidence_flag 'clinical_effect_unknown'."
        ),
    )
    placebo_response_concern: PlaceboResponseConcern = Field(
        default=PlaceboResponseConcern.UNKNOWN,
        description=(
            "Placebo inflation risk. CNS/psychiatry/GI/pain, Phase 2/3 only; silent no-op elsewhere. "
            "UNKNOWN (default): unassessed — 0.00 delta + flag 'placebo_response_unassessed'. "
            "NONE: explicitly assessed as no risk (0.00). MODERATE (-0.15), HIGH (-0.30)."
        ),
    )

    # --- Block 33: indication subtype base rate ---
    indication_subtype: Optional[str] = Field(
        default=None,
        description=(
            "Block 33: Indication subtype key from indication_subtype_rates in "
            "industry_assumptions.yaml. Overrides the broad TA base rate when set. "
            "Emits subtype_key_used, subtype_base_rate_used, subtype_confidence, "
            "subtype_ta_fallback in POSComputeResult. "
            "Falls back to TA rate with UserWarning if key unknown."
        ),
    )

    # --- Block 32: gene therapy modality (context-only; zero baseline) ---
    gene_therapy_modality: GeneTherapyModality = Field(
        default=GeneTherapyModality.UNKNOWN,
        description=(
            "Block 32: Gene/cell therapy delivery modality. Context-only — modality "
            "does NOT independently adjust POS (all modality_adjustment=0.00). "
            "Use gene_cell_therapy_concerns for actual POS adjustment. "
            "Modality informs which concerns are relevant but does not score them."
        ),
    )

    # Deprecated boolean fields — kept for backward compatibility with existing YAML
    # configs, backtest datasets, and older code. Prefer the graded enum fields above.
    # When set, these are automatically mapped to the corresponding enum tier via the
    # model_validator below (biomarker_selected_population → VALIDATED,
    # strong_prior_phase_data → STRONG_SINGLE).
    biomarker_selected_population: bool = Field(
        default=False,
        description="[Deprecated] Use biomarker_selection instead.",
    )
    strong_prior_phase_data: bool = Field(
        default=False,
        description="[Deprecated] Use prior_phase_data instead.",
    )

    @model_validator(mode="after")
    def _gate_extraordinary_evidence(self) -> "POSAdjusters":
        """
        Block 34B: extraordinary_evidence=True is only valid when ALL of:
          1. prior_phase_data == STRONG_REPLICATED
          2. biomarker_selection == VALIDATED
          3. clinical_effect_magnitude == EXCEEDS_MCID
          4. extraordinary_evidence_rationale is non-empty
        If any condition is unmet, emit UserWarning and reset to False.
        """
        if not self.extraordinary_evidence:
            return self
        conditions_met = (
            self.prior_phase_data == PriorPhaseDataStrength.STRONG_REPLICATED
            and self.biomarker_selection == BiomarkerSelectionStrength.VALIDATED
            and self.clinical_effect_magnitude == ClinicalEffectMagnitude.EXCEEDS_MCID
            and bool(self.extraordinary_evidence_rationale)
        )
        if not conditions_met:
            warnings.warn(
                "extraordinary_evidence=True requires ALL of: "
                "prior_phase_data=STRONG_REPLICATED, biomarker_selection=VALIDATED, "
                "clinical_effect_magnitude=EXCEEDS_MCID, AND non-empty "
                "extraordinary_evidence_rationale. Resetting to False.",
                UserWarning,
                stacklevel=2,
            )
            object.__setattr__(self, "extraordinary_evidence", False)
        return self

    @model_validator(mode="after")
    def _backfill_legacy_bools(self) -> "POSAdjusters":
        """Map deprecated boolean fields to new enum fields when new field is at default."""
        if (
            self.biomarker_selected_population
            and self.biomarker_selection == BiomarkerSelectionStrength.NO_SELECTION
        ):
            object.__setattr__(self, "biomarker_selection", BiomarkerSelectionStrength.VALIDATED)
        if (
            self.strong_prior_phase_data
            and self.prior_phase_data == PriorPhaseDataStrength.MIXED
        ):
            object.__setattr__(self, "prior_phase_data", PriorPhaseDataStrength.STRONG_SINGLE)
        return self

    @model_validator(mode="after")
    def _handle_competitive_pressure_alias(self) -> "POSAdjusters":
        """Block 25: map deprecated competitive_pressure → regulatory_approval_bar."""
        if self.competitive_pressure is None:
            return self
        warnings.warn(
            "POSAdjusters.competitive_pressure is deprecated. "
            "Use regulatory_approval_bar (RegulatoryApprovalBar) instead.",
            DeprecationWarning,
            stacklevel=3,
        )
        # Only override regulatory_approval_bar when caller did not set it explicitly
        if self.regulatory_approval_bar == RegulatoryApprovalBar.MODERATE:
            mapped = _COMPETITIVE_PRESSURE_TO_RAB.get(
                self.competitive_pressure.value, RegulatoryApprovalBar.MODERATE
            )
            object.__setattr__(self, "regulatory_approval_bar", mapped)
        return self

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

def _pos_ceiling(base_rate: float) -> float:
    """
    Block 34E: Absolute POS ceiling formula.

    Prevents implausible output highs without trapping low-base-rate programs:
        ceiling = min(0.75, max(base_rate * 2.5, base_rate + 0.25))

    Examples:
        base_rate=0.10 → min(0.75, max(0.25, 0.35)) = 0.35
        base_rate=0.40 → min(0.75, max(1.00, 0.65)) = 0.75
        base_rate=0.60 → min(0.75, max(1.50, 0.85)) = 0.75
        GBM (0.12)     → min(0.75, max(0.30, 0.37)) = 0.37
    """
    return min(0.75, max(base_rate * 2.5, base_rate + 0.25))


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
    adjusters_provided = adjusters is not None
    if adjusters is None:
        adjusters = POSAdjusters()

    ta_key = therapeutic_area.value
    phase_key = phase.value

    # Look up base rate; fall back to "all" if TA not found
    base_rates = PHASE_SUCCESS_RATES.get(ta_key) or PHASE_SUCCESS_RATES["all"]
    base_rate = base_rates.get(phase_key, 0.40)

    # Block 33: indication subtype base rate override
    _subtype_key = adjusters.indication_subtype
    if _subtype_key is not None:
        from bve.config.assumptions_loader import AssumptionsLoader as _AL
        _sub_rate = _AL.get().get_indication_subtype_rate(_subtype_key, phase_key)
        if _sub_rate is not None:
            base_rate = _sub_rate

    # Block 34E: capture raw base rate (before AA discount) for absolute ceiling
    _raw_base_rate = base_rate

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
    if phase == TrialPhase.NDA_BLA and not adjusters_provided:
        adjustment = 0.0
    else:
        adjustment, _flags = _compute_layer1_adjustment(adjusters, ta_value=ta_key, phase=phase)

    # Cap the combined adjustment (not the absolute log-odds) so the TA base
    # rate is preserved; only analyst qualitative input is bounded.
    # extraordinary_evidence=True expands the positive cap to +1.00 for cases
    # with truly exceptional replicated human data.
    cap_pos = _L1_CAP_POSITIVE_EXTRAORDINARY if adjusters.extraordinary_evidence else _L1_CAP_POSITIVE
    adjustment = max(_L1_CAP_NEGATIVE, min(cap_pos, adjustment))
    log_odds += adjustment

    # Convert back
    pos = 1.0 / (1.0 + math.exp(-log_odds))

    # Block 34E: apply absolute POS ceiling
    pos = min(pos, _pos_ceiling(_raw_base_rate))

    return round(pos, 4)


def _endpoint_logodds(endpoint_type: EndpointType, ta_value: str) -> float:
    """Look up endpoint log-odds with TA-specific override, generic fallback."""
    ta_table = _ENDPOINT_LOGODDS_BY_TA.get(ta_value, {})
    if endpoint_type in ta_table:
        return ta_table[endpoint_type]
    return _ENDPOINT_LOGODDS_GENERIC.get(endpoint_type, 0.0)


def _compute_layer1_adjustment(
    adjusters: POSAdjusters,
    ta_value: str = "other",
    phase: Optional[TrialPhase] = None,
) -> tuple[float, list[str]]:
    """
    Sum all Layer 1 qualitative adjusters into a single log-odds delta.

    Parameters
    ----------
    adjusters : POSAdjusters
    ta_value  : TherapeuticArea.value string for TA-specific endpoint scoring.
    phase     : TrialPhase — required for Block 18 phase-gated adjusters
                (ClinicalEffectMagnitude, PlaceboResponseConcern).
                When None, phase-gated adjusters are skipped.

    Returns
    -------
    tuple[float, list[str]]
        (total_delta, confidence_flags)
        confidence_flags: list of string keys where an UNKNOWN/unassessed tier
        was used.  The caller decides how to surface these.
    """
    delta: float = 0.0
    confidence_flags: list[str] = []

    delta += _endpoint_logodds(adjusters.endpoint_type, ta_value)
    delta += _MOA_LOGODDS[adjusters.moa_precedent]
    # MoA exception flags: partial override for weak precedent (additive)
    for flag in adjusters.moa_exception_flags:
        delta += _MOA_EXCEPTION_LOGODDS.get(flag, 0.0)
    delta += _SAMPLE_LOGODDS[adjusters.sample_size_adequacy]
    delta += _SAFETY_LOGODDS[adjusters.safety_profile]
    delta += _REGULATORY_APPROVAL_BAR_LOGODDS[adjusters.regulatory_approval_bar]

    delta += _BIOMARKER_LOGODDS[adjusters.biomarker_selection]
    delta += _PRIOR_PHASE_LOGODDS[adjusters.prior_phase_data]
    # Block 28: BTD type-conditional log-odds
    # breakthrough_designation takes precedence over has_breakthrough_designation bool.
    _btd_type: Optional[BreakthroughDesignationType] = adjusters.breakthrough_designation
    if _btd_type is None:
        # Backward compat: map bool to type
        _btd_type = (
            BreakthroughDesignationType.GRANTED_STANDARD
            if adjusters.has_breakthrough_designation
            else BreakthroughDesignationType.NONE
        )
    delta += _BTD_LOGODDS_BY_TYPE[_btd_type]

    # Gene / cell therapy overlays (Block 32: capped to prevent stacking abuse)
    _gt_durability_sum: float = 0.0
    _gt_total_sum: float = 0.0
    for concern in adjusters.gene_cell_therapy_concerns:
        _logodds = _GENE_THERAPY_LOGODDS.get(concern, 0.0)
        if concern in _GT_DURABILITY_CONCERNS and _logodds < 0:
            _gt_durability_sum += _logodds
        _gt_total_sum += _logodds
    # Apply durability cap (negative penalties only)
    if _gt_durability_sum < _GT_MAX_DURABILITY_PENALTY:
        _non_durability_sum = _gt_total_sum - _gt_durability_sum
        _gt_total_sum = _GT_MAX_DURABILITY_PENALTY + _non_durability_sum
    # Apply total overlay cap
    if _gt_total_sum < _GT_MAX_TOTAL_OVERLAY:
        _gt_total_sum = _GT_MAX_TOTAL_OVERLAY
    delta += _gt_total_sum

    # --- Block 18: Scientific Realism adjusters ---

    # Dose selection: downside-only; always applies (not phase-gated)
    delta += _DOSE_SELECTION_LOGODDS[adjusters.dose_selection_confidence]
    if adjusters.dose_selection_confidence == DoseSelectionConfidence.UNKNOWN:
        confidence_flags.append("dose_selection_unknown")

    # Clinical effect magnitude: Phase 2/3 only
    if phase in _REALISM_APPLICABLE_PHASES:
        delta += _CLINICAL_EFFECT_LOGODDS[adjusters.clinical_effect_magnitude]
        if adjusters.clinical_effect_magnitude == ClinicalEffectMagnitude.UNKNOWN:
            confidence_flags.append("clinical_effect_unknown")
    elif phase == TrialPhase.NDA_BLA and adjusters.clinical_effect_magnitude != ClinicalEffectMagnitude.UNKNOWN:
        # Block 34C: field is non-UNKNOWN at NDA/BLA — not applicable; emit informational flag
        confidence_flags.append("clinical_effect_magnitude_not_applicable_at_nda")

    # Placebo response concern: Phase 2/3, applicable TAs only
    if phase in _REALISM_APPLICABLE_PHASES and ta_value in _PLACEBO_CONCERN_TAS:
        delta += _PLACEBO_RESPONSE_LOGODDS[adjusters.placebo_response_concern]
        if adjusters.placebo_response_concern == PlaceboResponseConcern.UNKNOWN:
            confidence_flags.append("placebo_response_unassessed")

    return delta, confidence_flags


@dataclass
class POSComputeResult:
    """
    Detailed output from compute_pos_detailed().

    Attributes
    ----------
    pos : float
        Probability of success for this phase. Identical to what compute_pos() returns.
    confidence_flags : list[str]
        Keys where an UNKNOWN/unassessed tier was used in Layer 1 adjusters.
        These do not change the point estimate but indicate where analyst input
        is missing.  Surface to the user as data-quality warnings.
        Possible values:
          "dose_selection_unknown"       — DoseSelectionConfidence.UNKNOWN
          "clinical_effect_unknown"      — ClinicalEffectMagnitude.UNKNOWN (Phase 2/3 only)
          "placebo_response_unassessed"  — PlaceboResponseConcern.UNKNOWN (applicable TA/phase)
          "btd_may_overlap_prior_data_and_effect_magnitude" — Block 28 overlap warning
    phase_realism_applied : bool
        True when phase-gated Block 18 adjusters (ClinicalEffectMagnitude,
        PlaceboResponseConcern) were active — i.e., phase is Phase 2 or Phase 3.
    btd_timeline_acceleration_flag : bool
        Block 28: True when a GRANTED_* BTD type is set (not NONE, FAST_TRACK, or REVOKED).
        Signals faster FDA review timeline — useful in M&A urgency scoring.
    btd_overlap_warning : Optional[str]
        Block 28: Set when high-tier BTD (RARE_HEME/EARLY_PHASE) co-occurs with
        strong prior phase data AND EXCEEDS_MCID clinical effect magnitude.
        Signals potential double-counting; analyst should review log-odds manually.
    """
    pos: float
    confidence_flags: list[str] = dc_field(default_factory=list)
    phase_realism_applied: bool = False
    btd_timeline_acceleration_flag: bool = False
    btd_overlap_warning: Optional[str] = None
    # Block 33: subtype base rate audit fields
    subtype_base_rate_used: Optional[float] = None
    subtype_key_used: Optional[str] = None
    subtype_confidence: Optional[str] = None
    subtype_ta_fallback: Optional[str] = None
    # Block 34E: absolute POS ceiling audit field
    ceiling_applied: bool = False


def compute_pos_detailed(
    phase: TrialPhase,
    therapeutic_area: TherapeuticArea,
    adjusters: Optional[POSAdjusters] = None,
    approval_pathway: Optional[ApprovalPathwayType] = None,
) -> POSComputeResult:
    """
    Compute POS with full confidence flag output.

    Same logic as compute_pos() but returns a POSComputeResult carrying
    the confidence_flags list from _compute_layer1_adjustment().

    Use this when you need to surface data-quality warnings alongside the
    point estimate (e.g., in decision reports, validation output).
    Use compute_pos() when only the float is needed.
    """
    adjusters_provided = adjusters is not None
    if adjusters is None:
        adjusters = POSAdjusters()

    ta_key = therapeutic_area.value
    base_rates = PHASE_SUCCESS_RATES.get(ta_key) or PHASE_SUCCESS_RATES["all"]
    base_rate = base_rates.get(phase.value, 0.40)

    # Block 33: indication subtype base rate override (adjusters is always set by here)
    _subtype_key = adjusters.indication_subtype
    _subtype_base_rate: Optional[float] = None
    _subtype_confidence: Optional[str] = None
    _subtype_ta_fallback: Optional[str] = None
    if _subtype_key is not None:
        from bve.config.assumptions_loader import AssumptionsLoader as _AL
        _loader = _AL.get()
        _sub_rate = _loader.get_indication_subtype_rate(_subtype_key, phase.value)
        if _sub_rate is not None:
            base_rate = _sub_rate
            _subtype_base_rate = _sub_rate
            _meta = _loader.get_indication_subtype_metadata(_subtype_key)
            if _meta:
                _subtype_confidence = _meta.get("confidence")
                _subtype_ta_fallback = _meta.get("ta_fallback")

    # Block 34E: capture raw base rate (before AA discount) for absolute ceiling
    _raw_base_rate = base_rate

    if (
        approval_pathway is not None
        and approval_pathway == ApprovalPathwayType.ACCELERATED
        and phase == TrialPhase.NDA_BLA
    ):
        base_rate = base_rate * (1.0 - _AA_NDA_DISCOUNT)

    base_rate = max(0.01, min(0.99, base_rate))
    log_odds = math.log(base_rate / (1.0 - base_rate))

    if phase == TrialPhase.NDA_BLA and not adjusters_provided:
        adjustment = 0.0
        confidence_flags: list[str] = []
    else:
        adjustment, confidence_flags = _compute_layer1_adjustment(
            adjusters, ta_value=ta_key, phase=phase
        )

    cap_pos = _L1_CAP_POSITIVE_EXTRAORDINARY if adjusters.extraordinary_evidence else _L1_CAP_POSITIVE
    adjustment = max(_L1_CAP_NEGATIVE, min(cap_pos, adjustment))
    log_odds += adjustment

    _raw_pos = 1.0 / (1.0 + math.exp(-log_odds))

    # Block 34E: apply absolute POS ceiling
    _ceiling = _pos_ceiling(_raw_base_rate)
    _ceiling_applied = _raw_pos > _ceiling
    pos = round(min(_raw_pos, _ceiling), 4)
    phase_realism_applied = phase in _REALISM_APPLICABLE_PHASES

    # Block 28: BTD timeline acceleration flag + overlap warning
    _btd_effective = adjusters.breakthrough_designation
    if _btd_effective is None:
        _btd_effective = (
            BreakthroughDesignationType.GRANTED_STANDARD
            if adjusters.has_breakthrough_designation
            else BreakthroughDesignationType.NONE
        )
    _btd_timeline_flag = _btd_effective in _BTD_TIMELINE_ACCELERATION_TYPES

    _btd_overlap_warning: Optional[str] = None
    if _btd_effective in _BTD_OVERLAP_WARNING_TYPES:
        _strong_prior = adjusters.prior_phase_data in (
            PriorPhaseDataStrength.STRONG_REPLICATED,
            PriorPhaseDataStrength.STRONG_SINGLE,
        )
        _exceeds_mcid = adjusters.clinical_effect_magnitude == ClinicalEffectMagnitude.EXCEEDS_MCID
        if _strong_prior and _exceeds_mcid:
            _btd_overlap_warning = (
                "BTD signal may partially overlap strong prior phase data + effect magnitude; "
                "review log-odds to avoid double-counting."
            )
            confidence_flags = list(confidence_flags) + ["btd_may_overlap_prior_data_and_effect_magnitude"]

    return POSComputeResult(
        pos=pos,
        confidence_flags=confidence_flags,
        phase_realism_applied=phase_realism_applied,
        btd_timeline_acceleration_flag=_btd_timeline_flag,
        btd_overlap_warning=_btd_overlap_warning,
        subtype_base_rate_used=_subtype_base_rate,
        subtype_key_used=_subtype_key if _subtype_base_rate is not None else None,
        subtype_confidence=_subtype_confidence,
        subtype_ta_fallback=_subtype_ta_fallback,
        ceiling_applied=_ceiling_applied,
    )


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
