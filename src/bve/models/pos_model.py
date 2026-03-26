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
from bve.entities.trial import EndpointType, TrialPhase

_AA_NDA_DISCOUNT: float = 0.18  # confirmatory trial risk discount for accelerated approval


# ---------------------------------------------------------------------------
# Adjuster enumerations
# ---------------------------------------------------------------------------

class MoAPrecedent(str, Enum):
    VALIDATED = "validated"          # Multiple approved drugs in class; well-understood biology
    PARTIAL = "partial"              # 1-2 approved drugs or strong preclinical validation
    NOVEL = "novel"                  # First-in-class; unvalidated target


class SampleSizeAdequacy(str, Enum):
    WELL_POWERED = "well_powered"    # ≥ 90% power for primary endpoint
    ADEQUATE = "adequate"            # ~80% power
    BORDERLINE = "borderline"        # 70–80% power or borderline effect size
    UNDERPOWERED = "underpowered"    # < 70% power


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

_ENDPOINT_LOGODDS: dict[EndpointType, float] = {
    EndpointType.HARD_CLINICAL: +0.35,      # OS/DFS; most accepted by regulators
    EndpointType.SURROGATE_VALIDATED: 0.00, # Baseline (PFS, HbA1c, etc.)
    EndpointType.SURROGATE_NOVEL: -0.30,    # Novel surrogate; uncertain regulatory acceptance
    EndpointType.BIOMARKER_ONLY: -0.55,     # Phase 2 biomarker; low regulatory weight
}

_MOA_LOGODDS: dict[MoAPrecedent, float] = {
    MoAPrecedent.VALIDATED: +0.35,
    MoAPrecedent.PARTIAL: 0.00,
    MoAPrecedent.NOVEL: -0.35,
}

_SAMPLE_LOGODDS: dict[SampleSizeAdequacy, float] = {
    SampleSizeAdequacy.WELL_POWERED: +0.20,
    SampleSizeAdequacy.ADEQUATE: 0.00,
    SampleSizeAdequacy.BORDERLINE: -0.25,
    SampleSizeAdequacy.UNDERPOWERED: -0.50,
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
    adjustment = _compute_layer1_adjustment(adjusters)

    # Cap the combined adjustment (not the absolute log-odds) so the TA base
    # rate is preserved; only analyst qualitative input is bounded.
    adjustment = max(_L1_CAP_NEGATIVE, min(_L1_CAP_POSITIVE, adjustment))
    log_odds += adjustment

    # Convert back
    pos = 1.0 / (1.0 + math.exp(-log_odds))
    return round(pos, 4)


def _compute_layer1_adjustment(adjusters: POSAdjusters) -> float:
    """
    Sum all Layer 1 qualitative adjusters into a single log-odds delta.

    Extracted as a named function so tests can verify the raw adjustment
    (pre-cap) and cap boundary behaviour independently.
    """
    delta = 0.0
    delta += _ENDPOINT_LOGODDS[adjusters.endpoint_type]
    delta += _MOA_LOGODDS[adjusters.moa_precedent]
    delta += _SAMPLE_LOGODDS[adjusters.sample_size_adequacy]
    delta += _SAFETY_LOGODDS[adjusters.safety_profile]
    delta += _COMPETITION_LOGODDS[adjusters.competitive_pressure]

    if adjusters.biomarker_selected_population:
        delta += _BIOMARKER_SELECTION_BONUS
    if adjusters.strong_prior_phase_data:
        delta += _PRIOR_PHASE_SUCCESS_BONUS
    if adjusters.has_breakthrough_designation:
        # BTD is a process designation; primary effect is faster review, not higher
        # binary approval probability. No significant PoS lift once controlling for
        # indication and target quality (prior literature). +0.05 retains a tiny
        # signal for FDA engagement level. (Was +0.20 pre-Sprint-9.)
        delta += _BTD_LOGODDS

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
