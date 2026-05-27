"""
POS Layer 2 — Trial Design / Regulatory Evidence Quality.

Applies a second, orthogonal adjustment on top of Layer 1 POS based on whether
the clinical evidence package is designed well enough to support approval.

  Layer 1 scores WHAT evidence is being generated (endpoint type, MoA, safety…).
  Layer 2 scores HOW trustworthy and regulator-acceptable that evidence is.

Three orthogonal dimensions
---------------------------
1. EvidenceDesignQuality — bias control and study design rigor
2. ComparatorFit         — does the comparator match current clinical practice?
3. RegulatoryPathwayRisk — interpretability / confirmatory risk from the pathway

Phase-dependent scaling (single multiplier)
-------------------------------------------
Design quality matters more as the drug approaches approval:

  Phase 1: 0.20  (design almost irrelevant; single-arm is universal)
  Phase 2: 0.50
  Phase 3: 1.00  (every design choice directly determines FDA probability)
  NDA/BLA: 0.90

Cap: +0.30 / −0.60 (asymmetric)
Good design helps, but modestly. Bad design can kill interpretability.

Anti-double-counting
--------------------
The new Layer 2 dimensions are orthogonal to Layer 1 by design:
  - EvidenceDesignQuality: study design rigor → not in Layer 1
  - ComparatorFit: comparator appropriateness → not in Layer 1
  - RegulatoryPathwayRisk: pathway interpretability risk → not in Layer 1

BTD (breakthrough designation) lives only in Layer 1 (POSAdjusters.
has_breakthrough_designation). It is intentionally absent from
RegulatoryPathwayRisk to prevent double-counting.

Use check_pos_layer_overlap() to formally verify any combination.

Valid phase values: "phase_1", "phase_2", "phase_3", "nda_bla"
Use TRIAL_DESIGN_PHASE_NEUTRAL ("neutral") for explicit maximum-effect mode
when phase is genuinely unknown (all scaling = 1.0).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

from bve.config.constants import (
    TRIAL_DESIGN_CAP_NEGATIVE,
    TRIAL_DESIGN_CAP_POSITIVE,
    TRIAL_DESIGN_LOGODDS,
    TRIAL_DESIGN_PHASE_NEUTRAL,
    TRIAL_DESIGN_PHASE_SCALING,
)

if TYPE_CHECKING:
    from bve.models.pos_model import (
        BiomarkerSelectionStrength,
        MoAExceptionFlag,
        POSAdjusters,
    )

# Surrogate endpoint types that overlap with ACCELERATED_NOVEL_SURROGATE pathway risk
_SURROGATE_OVERLAP_ENDPOINT_TYPES: frozenset[str] = frozenset([
    "surrogate_novel",
    "biomarker_only",
    "molecular_biomarker",
])

# Log-odds magnitude used by ACCELERATED_NOVEL_SURROGATE (for double-count estimation)
_ACCELERATED_NOVEL_SURROGATE_LOGODDS_MAGNITUDE: float = 0.20


# ---------------------------------------------------------------------------
# Dimension 1 — Evidence Design Quality
# ---------------------------------------------------------------------------

class EvidenceDesignQuality(str, Enum):
    """
    Study design rigor — HOW well bias is controlled.

    Phase-conditional scaling attenuates penalties at Phase 1 where
    single-arm is universal and appropriate.

    Log-odds (pre-scaling, Phase 3 baseline):
      RCT_DOUBLE_BLIND      +0.20   Strongest bias control
      RCT_OPEN_LABEL        +0.10   Good design, some bias risk
      RCT_WEAK_COMPARATOR   −0.05   Comparator limits interpretability
      SINGLE_ARM_OBJECTIVE  −0.10   Acceptable in some oncology/rare settings
      SINGLE_ARM_SUBJECTIVE −0.30   High bias risk
      REGISTRY_OBSERVATIONAL−0.35   Weakest confirmatory evidence
    """
    RCT_DOUBLE_BLIND       = "rct_double_blind"
    RCT_OPEN_LABEL         = "rct_open_label"
    RCT_WEAK_COMPARATOR    = "rct_weak_comparator"
    SINGLE_ARM_OBJECTIVE   = "single_arm_objective"
    SINGLE_ARM_SUBJECTIVE  = "single_arm_subjective"
    REGISTRY_OBSERVATIONAL = "registry_observational"


# ---------------------------------------------------------------------------
# Dimension 2 — Comparator / Standard-of-Care Fit
# ---------------------------------------------------------------------------

class ComparatorFit(str, Enum):
    """
    Does the comparator match current clinical practice?

    A mismatched comparator limits regulatory and clinical interpretability
    even in a well-run RCT.

    Log-odds (pre-scaling):
      MATCHES_SOC          +0.10   Comparator matches current standard of care
      PLACEBO_ACCEPTABLE   +0.05   Placebo acceptable (no good SoC exists)
      ACCEPTABLE_NOT_IDEAL  0.00   Baseline: acceptable but not ideal
      OUTDATED_COMPARATOR  −0.15   Comparator outdated or clinically weak
      NO_VALID_COMPARATOR  −0.30   No valid comparator where one is expected
    """
    MATCHES_SOC          = "matches_soc"
    PLACEBO_ACCEPTABLE   = "placebo_acceptable"
    ACCEPTABLE_NOT_IDEAL = "acceptable_not_ideal"
    OUTDATED_COMPARATOR  = "outdated_comparator"
    NO_VALID_COMPARATOR  = "no_valid_comparator"


# ---------------------------------------------------------------------------
# Dimension 3 — Regulatory Pathway Risk
# ---------------------------------------------------------------------------

class RegulatoryPathwayRisk(str, Enum):
    """
    Regulatory pathway interpretability / confirmatory risk.

    Note: Breakthrough Designation (BTD) is handled exclusively in Layer 1
    (POSAdjusters.has_breakthrough_designation). It is intentionally absent
    here to prevent double-counting.

    Log-odds (pre-scaling):
      STANDARD                          0.00   Standard path, accepted precedent
      ORPHAN_RARE_DISEASE              +0.10   Regulatory flexibility with strong rationale
      ACCELERATED_VALIDATED_SURROGATE  −0.05   AA with validated surrogate (confirmatory risk)
      ACCELERATED_NOVEL_SURROGATE      −0.20   AA with novel/uncertain surrogate (higher risk)
      NO_CLEAR_PRECEDENT               −0.30   No clear regulatory path
    """
    STANDARD                         = "standard"
    ORPHAN_RARE_DISEASE              = "orphan_rare_disease"
    ACCELERATED_VALIDATED_SURROGATE  = "accelerated_validated_surrogate"
    ACCELERATED_NOVEL_SURROGATE      = "accelerated_novel_surrogate"
    NO_CLEAR_PRECEDENT               = "no_clear_precedent"


# ---------------------------------------------------------------------------
# Dimension 4 — Clinical Effect Magnitude
# ---------------------------------------------------------------------------

class ClinicalEffectMagnitude(str, Enum):
    """
    Observed effect size relative to minimal clinically important difference (MCID).

    Captures whether early efficacy data suggest a clinically meaningful benefit.
    UNKNOWN is the reference (zero adjustment) — use when no Phase 2 data yet.

    Log-odds (pre-scaling, Phase 3 baseline):
      EXCEEDS_MCID   +0.25  Clearly exceeds MCID (e.g., ΔFEV1 >200 ml, ORR >30%)
      MEETS_MCID     +0.10  Meets but does not clearly exceed MCID
      UNKNOWN         0.00  No MCID data available (reference; no adjustment)
      BELOW_MCID     −0.15  Effect below MCID threshold; regulatory concern

    Overlap warning: EXCEEDS_MCID partially overlaps with Layer 1
    BiomarkerSelectionStrength.VALIDATED / STRONG_RATIONALE and with
    MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE / HUMAN_PROOF_OF_MECHANISM.
    Use check_pos_layer_overlap() to detect and quantify.
    """
    EXCEEDS_MCID = "exceeds_mcid"
    MEETS_MCID   = "meets_mcid"
    UNKNOWN      = "unknown"
    BELOW_MCID   = "below_mcid"


# Log-odds table for ClinicalEffectMagnitude (not in TRIAL_DESIGN_LOGODDS — internal only)
_EFFECT_MAGNITUDE_LOGODDS: dict[ClinicalEffectMagnitude, float] = {
    ClinicalEffectMagnitude.EXCEEDS_MCID: +0.25,
    ClinicalEffectMagnitude.MEETS_MCID:   +0.10,
    ClinicalEffectMagnitude.UNKNOWN:       0.00,
    ClinicalEffectMagnitude.BELOW_MCID:   -0.15,
}

# Overlap magnitudes for Pattern 3 and Pattern 4 detection
_PATTERN3_BIOMARKER_MCID_DOUBLE_COUNT: float = 0.15
_PATTERN4_MOA_EXCEPTION_MCID_DOUBLE_COUNT: float = 0.10


# ---------------------------------------------------------------------------
# Feature set
# ---------------------------------------------------------------------------

class TrialDesignFeatureSet(BaseModel):
    """
    Four-dimensional trial design feature set for POS Layer 2.

    Defaults represent the reference design scenario:
      - rct_double_blind: randomized, double-blind, controlled (+0.20)
      - acceptable_not_ideal: comparator is adequate (0.00)
      - standard: standard regulatory path (0.00)
      - unknown: no MCID data available (0.00)

    Always pass `phase` to compute_adjusted_pos() — the appropriate phase
    scaling depends on which trial phase is being evaluated.
    """
    evidence_design_quality: EvidenceDesignQuality = EvidenceDesignQuality.RCT_DOUBLE_BLIND
    comparator_fit: ComparatorFit = ComparatorFit.ACCEPTABLE_NOT_IDEAL
    regulatory_pathway_risk: RegulatoryPathwayRisk = RegulatoryPathwayRisk.STANDARD
    clinical_effect_magnitude: ClinicalEffectMagnitude = ClinicalEffectMagnitude.UNKNOWN

    def compute_adjusted_pos(
        self,
        base_pos: float,
        phase: str,
    ) -> "DesignAdjustedPOSResult":
        """Apply design adjustment to base_pos. phase is required."""
        return compute_design_adjusted_pos(base_pos, self, phase=phase)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DesignAdjustedPOSResult:
    """
    Output of compute_design_adjusted_pos().

    Attributes
    ----------
    adjusted_pos : float
        Final POS after applying design adjustments. Bounded in (0, 1).
    base_pos : float
        Input base POS before design adjustment.
    total_logodds_adjustment : float
        Combined log-odds shift applied (after phase scaling and cap).
    uncapped_logodds_adjustment : float
        Combined log-odds shift before cap (post-scaling).
    adjustment_breakdown : dict[str, float]
        Phase-scaled log-odds contribution from each dimension (pre-cap).
        Keys: "evidence_design_quality", "comparator_fit", "regulatory_pathway_risk".
    phase_scaling_applied : dict[str, float]
        The scaling factor applied. All keys hold the same scalar multiplier.
    was_capped : bool
        True if the combined adjustment was clipped by the configured cap.
    cap_applied : str | None
        "positive" if positive cap applied, "negative" if negative, None otherwise.
    """
    adjusted_pos: float
    base_pos: float
    total_logodds_adjustment: float
    uncapped_logodds_adjustment: float
    adjustment_breakdown: dict[str, float]
    phase_scaling_applied: dict[str, float]
    was_capped: bool
    cap_applied: Optional[str]


# ---------------------------------------------------------------------------
# Phase validation helpers
# ---------------------------------------------------------------------------

_VALID_PHASES = frozenset(TRIAL_DESIGN_PHASE_SCALING.keys()) | {TRIAL_DESIGN_PHASE_NEUTRAL}
_NEUTRAL_SCALING_FACTOR: float = 1.0


def _get_scaling_factor(phase: str) -> float:
    if phase == TRIAL_DESIGN_PHASE_NEUTRAL:
        return _NEUTRAL_SCALING_FACTOR
    return float(TRIAL_DESIGN_PHASE_SCALING[phase])


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def compute_design_adjusted_pos(
    base_pos: float,
    features: TrialDesignFeatureSet,
    phase: str,
    settings: Optional[dict] = None,
) -> DesignAdjustedPOSResult:
    """
    Apply trial design feature adjustments to a base POS estimate.

    Parameters
    ----------
    base_pos : float
        Starting probability of success in (0, 1). Typically from compute_pos()
        or from a TA-specific base rate.
    features : TrialDesignFeatureSet
        The 3-dimensional design feature set to apply.
    phase : str
        Trial phase key. REQUIRED — design effects differ materially by phase.
        Valid values: "phase_1", "phase_2", "phase_3", "nda_bla",
        or TRIAL_DESIGN_PHASE_NEUTRAL ("neutral") for explicit maximum-effect
        estimates when phase is genuinely unknown.
    settings : dict, optional
        Override cap values only. Keys: "cap_logodds_positive", "cap_logodds_negative".
        When None, reads from bve.config.constants.

    Returns
    -------
    DesignAdjustedPOSResult

    Raises
    ------
    ValueError
        If phase is not a recognized value.
    """
    if phase not in _VALID_PHASES:
        raise ValueError(
            f"Invalid phase {phase!r}. Valid values: {sorted(_VALID_PHASES)}. "
            f"Use TRIAL_DESIGN_PHASE_NEUTRAL={TRIAL_DESIGN_PHASE_NEUTRAL!r} for "
            f"explicit maximum-effect mode when phase is genuinely unknown."
        )

    cap_pos = TRIAL_DESIGN_CAP_POSITIVE
    cap_neg = TRIAL_DESIGN_CAP_NEGATIVE
    if settings is not None:
        cap_pos = float(settings.get("cap_logodds_positive", cap_pos))
        cap_neg = float(settings.get("cap_logodds_negative", cap_neg))

    scaling = _get_scaling_factor(phase)

    base_pos = max(0.001, min(0.999, base_pos))
    base_logodds = math.log(base_pos / (1.0 - base_pos))

    logodds = TRIAL_DESIGN_LOGODDS
    edq_raw = logodds["evidence_design_quality"].get(features.evidence_design_quality.value, 0.0)
    cf_raw  = logodds["comparator_fit"].get(features.comparator_fit.value, 0.0)
    rpr_raw = logodds["regulatory_pathway_risk"].get(features.regulatory_pathway_risk.value, 0.0)
    cem_raw = _EFFECT_MAGNITUDE_LOGODDS.get(features.clinical_effect_magnitude, 0.0)

    edq_adj = edq_raw * scaling
    cf_adj  = cf_raw  * scaling
    rpr_adj = rpr_raw * scaling
    cem_adj = cem_raw * scaling

    uncapped = edq_adj + cf_adj + rpr_adj + cem_adj

    capped = uncapped
    cap_applied: Optional[str] = None
    if uncapped > cap_pos:
        capped = cap_pos
        cap_applied = "positive"
    elif uncapped < cap_neg:
        capped = cap_neg
        cap_applied = "negative"

    adjusted_logodds = base_logodds + capped
    adjusted_pos = 1.0 / (1.0 + math.exp(-adjusted_logodds))

    scaling_dict = {
        "evidence_design_quality": scaling,
        "comparator_fit": scaling,
        "regulatory_pathway_risk": scaling,
        "clinical_effect_magnitude": scaling,
    }

    return DesignAdjustedPOSResult(
        adjusted_pos=round(adjusted_pos, 4),
        base_pos=round(base_pos, 4),
        total_logodds_adjustment=round(capped, 4),
        uncapped_logodds_adjustment=round(uncapped, 4),
        adjustment_breakdown={
            "evidence_design_quality": round(edq_adj, 4),
            "comparator_fit": round(cf_adj, 4),
            "regulatory_pathway_risk": round(rpr_adj, 4),
            "clinical_effect_magnitude": round(cem_adj, 4),
        },
        phase_scaling_applied=scaling_dict,
        was_capped=cap_applied is not None,
        cap_applied=cap_applied,
    )


# ---------------------------------------------------------------------------
# Anti-double-counting audit tool
# ---------------------------------------------------------------------------

@dataclass
class LayerOverlapReport:
    """
    Report on signal overlaps between POSAdjusters and TrialDesignFeatureSet.

    The new Layer 2 (EvidenceDesignQuality, ComparatorFit, RegulatoryPathwayRisk)
    is designed to be orthogonal to Layer 1. BTD is in Layer 1 only; endpoint
    quality is not a Layer 2 dimension. In practice this function always returns
    a clean report for the current Layer 2 design.

    Attributes
    ----------
    overlapping_signals : list[str]
        Human-readable descriptions of each detected overlap.
    recommendations : list[str]
        Specific actions to resolve each overlap.
    has_critical_overlap : bool
        True if any overlap is classified as "critical".
    estimated_double_count_logodds : float
        Conservative lower bound on the log-odds magnitude being double-counted.
    """
    overlapping_signals: list[str]
    recommendations: list[str]
    has_critical_overlap: bool
    estimated_double_count_logodds: float

    def is_clean(self) -> bool:
        """True if no overlaps detected."""
        return len(self.overlapping_signals) == 0

    def summary(self) -> str:
        if self.is_clean():
            return "No signal overlaps detected between POSAdjusters and TrialDesignFeatureSet."
        status = "CRITICAL" if self.has_critical_overlap else "WARNING"
        n = len(self.overlapping_signals)
        return (
            f"{status}: {n} overlap(s) detected. "
            f"Estimated double-count magnitude: {self.estimated_double_count_logodds:+.2f} log-odds. "
            f"Call .recommendations for resolution steps."
        )


def check_pos_layer_overlap(
    pos_adjusters: "POSAdjusters",
    design_features: TrialDesignFeatureSet,
    phase: Optional[str] = None,
    *,
    allow_overlap: bool = False,
) -> LayerOverlapReport:
    """
    Audit a POSAdjusters + TrialDesignFeatureSet combination for double-counting.

    The current Layer 2 (EvidenceDesignQuality, ComparatorFit, RegulatoryPathwayRisk)
    is orthogonal to Layer 1 by design — BTD is in Layer 1 only, and endpoint
    quality is not a Layer 2 dimension. This function always returns a clean report
    for the current Layer 2 design.

    Parameters
    ----------
    pos_adjusters : POSAdjusters
    design_features : TrialDesignFeatureSet
    phase : str, optional
        Kept for API compatibility; used for future phase-specific checks.
    allow_overlap : bool, optional
        When True, return a clean report without checks (used for explicit overrides).

    Returns
    -------
    LayerOverlapReport
        Clean when no overlaps detected; non-clean otherwise.

    Detected overlaps
    -----------------
    1. Surrogate endpoint double-count (Layer 1 ↔ Layer 2)
       POSAdjusters.endpoint_type in {SURROGATE_NOVEL, BIOMARKER_ONLY, MOLECULAR_BIOMARKER}
       AND TrialDesignFeatureSet.regulatory_pathway_risk == ACCELERATED_NOVEL_SURROGATE
       → Both penalise the same "novel surrogate" risk.
       Classified as CRITICAL.

    2. Biomarker selection double-count (intra-Layer-1)
       MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE in pos_adjusters.moa_exception_flags
       AND pos_adjusters.biomarker_selection in {STRONG_RATIONALE, VALIDATED}
       → The same biomarker evidence is credited via both the MoA exception flag
         (mechanism engagement) and the patient-selection enrichment strength.
    """
    if allow_overlap:
        return LayerOverlapReport(
            overlapping_signals=[],
            recommendations=[],
            has_critical_overlap=False,
            estimated_double_count_logodds=0.0,
        )

    # Lazy import to avoid circular at module level (pos_model imports from this module)
    from bve.models.pos_model import (  # noqa: PLC0415
        BiomarkerSelectionStrength,
        MoAExceptionFlag,
        MoAPrecedent,
        _BIOMARKER_LOGODDS,
        _MOA_EXCEPTION_LOGODDS,
    )

    overlapping: list[str] = []
    recommendations: list[str] = []
    double_count: float = 0.0
    has_critical = False

    # -------------------------------------------------------------------
    # Overlap 1: surrogate endpoint type + accelerated novel surrogate pathway
    # -------------------------------------------------------------------
    endpoint_value = pos_adjusters.endpoint_type.value
    is_surrogate_type = endpoint_value in _SURROGATE_OVERLAP_ENDPOINT_TYPES
    is_novel_acc_pathway = (
        design_features.regulatory_pathway_risk
        == RegulatoryPathwayRisk.ACCELERATED_NOVEL_SURROGATE
    )
    if is_surrogate_type and is_novel_acc_pathway:
        # Look up the Layer 2 logodds magnitude for this endpoint type (generic fallback)
        from bve.models.pos_model import _ENDPOINT_LOGODDS_GENERIC  # noqa: PLC0415
        from bve.entities.trial import EndpointType  # noqa: PLC0415
        try:
            ep = EndpointType(endpoint_value)
            lo_endpoint = abs(_ENDPOINT_LOGODDS_GENERIC.get(ep, 0.0))
        except ValueError:
            lo_endpoint = 0.20
        overlap_mag = round(min(lo_endpoint, _ACCELERATED_NOVEL_SURROGATE_LOGODDS_MAGNITUDE), 4)
        overlapping.append(
            f"endpoint_type={endpoint_value!r} (Layer 1) + "
            "regulatory_pathway_risk=ACCELERATED_NOVEL_SURROGATE (Layer 2): "
            "both penalise the novel-surrogate regulatory risk."
        )
        recommendations.append(
            "In Layer 1, endpoint_type scores scientific endpoint quality. "
            "In Layer 2, RegulatoryPathwayRisk scores regulatory interpretability risk. "
            "These partially overlap for novel surrogates. "
            "Consider reducing one dimension by the estimated overlap magnitude "
            f"({overlap_mag:+.2f} log-odds) or accepting the conservative double-penalisation."
        )
        double_count += overlap_mag
        has_critical = True

    # -------------------------------------------------------------------
    # Overlap 2: intra-Layer-1 biomarker double-count
    # -------------------------------------------------------------------
    _biomarker_overlap_tiers = {
        BiomarkerSelectionStrength.STRONG_RATIONALE,
        BiomarkerSelectionStrength.VALIDATED,
    }
    has_sbr_flag = MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE in pos_adjusters.moa_exception_flags
    has_strong_biomarker = pos_adjusters.biomarker_selection in _biomarker_overlap_tiers

    if has_sbr_flag and has_strong_biomarker:
        sbr_lo = _MOA_EXCEPTION_LOGODDS[MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE]
        bsel_lo = _BIOMARKER_LOGODDS[pos_adjusters.biomarker_selection]
        overlap_mag = round(min(sbr_lo, bsel_lo), 4)
        overlapping.append(
            f"MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE (Layer 1 MoA exception) + "
            f"BiomarkerSelectionStrength.{pos_adjusters.biomarker_selection.value} "
            "(Layer 1 patient enrichment): "
            "the same biomarker evidence is credited twice."
        )
        recommendations.append(
            "Use MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE only for MoA target validation "
            "(dose-dependent biomarker confirms mechanism engagement). "
            "Use BiomarkerSelectionStrength for patient-enrichment enrichment quality. "
            "If the same biomarker serves both purposes, credit the higher-value tier and "
            "set the other to its reference/neutral value to avoid double-counting."
        )
        double_count += overlap_mag

    # -------------------------------------------------------------------
    # Overlap 3: strong biomarker selection + ClinicalEffectMagnitude.EXCEEDS_MCID
    # -------------------------------------------------------------------
    _strong_biomarker_tiers = {
        BiomarkerSelectionStrength.VALIDATED,
        BiomarkerSelectionStrength.STRONG_RATIONALE,
    }
    is_strong_biomarker = pos_adjusters.biomarker_selection in _strong_biomarker_tiers
    is_exceeds_mcid = design_features.clinical_effect_magnitude == ClinicalEffectMagnitude.EXCEEDS_MCID

    if is_strong_biomarker and is_exceeds_mcid:
        overlapping.append(
            f"BiomarkerSelectionStrength.{pos_adjusters.biomarker_selection.value} "
            "(Layer 1 patient enrichment) + ClinicalEffectMagnitude.EXCEEDS_MCID "
            "(Layer 2): strong biomarker selection already implies an enriched population "
            "with large effect size; EXCEEDS_MCID further credits that same enrichment."
        )
        recommendations.append(
            "When a validated/strong predictive biomarker is used for patient enrichment, "
            "the associated effect size uplift is partly captured in Layer 1. "
            "Consider reducing ClinicalEffectMagnitude to MEETS_MCID, or reduce the "
            "biomarker selection tier, to avoid double-counting the enrichment benefit. "
            f"Estimated overlap: {_PATTERN3_BIOMARKER_MCID_DOUBLE_COUNT:+.2f} log-odds."
        )
        double_count += _PATTERN3_BIOMARKER_MCID_DOUBLE_COUNT

    # -------------------------------------------------------------------
    # Overlap 4: MoA exception flag (STRONG_BIOMARKER_RESPONSE / HUMAN_POM) + EXCEEDS_MCID
    # -------------------------------------------------------------------
    _mcid_overlap_flags = {
        MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE,
        MoAExceptionFlag.HUMAN_PROOF_OF_MECHANISM,
    }
    active_mcid_flags = [f for f in pos_adjusters.moa_exception_flags if f in _mcid_overlap_flags]

    if active_mcid_flags and is_exceeds_mcid:
        flag_names = ", ".join(f.value for f in active_mcid_flags)
        overlapping.append(
            f"MoAExceptionFlag({flag_names}) (Layer 1 MoA exception) + "
            "ClinicalEffectMagnitude.EXCEEDS_MCID (Layer 2): "
            "both flags reference the same early clinical signal "
            "(strong human data = high effect magnitude)."
        )
        recommendations.append(
            "Strong early clinical signal is already reflected in "
            f"MoAExceptionFlag({flag_names}). "
            "Setting ClinicalEffectMagnitude.EXCEEDS_MCID additionally credits "
            "the same human evidence. Consider reducing ClinicalEffectMagnitude to "
            f"MEETS_MCID or UNKNOWN. Estimated overlap: "
            f"{_PATTERN4_MOA_EXCEPTION_MCID_DOUBLE_COUNT:+.2f} log-odds."
        )
        double_count += _PATTERN4_MOA_EXCEPTION_MCID_DOUBLE_COUNT

    # -------------------------------------------------------------------
    # Overlap 5: intra-Layer-1 — HUMAN_PROOF_OF_MECHANISM + CLINICALLY_VALIDATED_TARGET
    # -------------------------------------------------------------------
    has_human_pom = MoAExceptionFlag.HUMAN_PROOF_OF_MECHANISM in pos_adjusters.moa_exception_flags
    has_cvt = pos_adjusters.moa_precedent == MoAPrecedent.CLINICALLY_VALIDATED_TARGET

    if has_human_pom and has_cvt:
        overlapping.append(
            "MoAExceptionFlag.HUMAN_PROOF_OF_MECHANISM (Layer 1 MoA exception) + "
            "MoAPrecedent.CLINICALLY_VALIDATED_TARGET (Layer 1 MoA precedent): "
            "CLINICALLY_VALIDATED_TARGET means human efficacy is shown, which IS the "
            "definition of human proof of mechanism — the same evidence is credited twice."
        )
        recommendations.append(
            "CLINICALLY_VALIDATED_TARGET already encodes that human efficacy/POM has been "
            "demonstrated. Remove HUMAN_PROOF_OF_MECHANISM from moa_exception_flags, or "
            "downgrade moa_precedent to PATHWAY_VALIDATED if only mechanism (not clinical "
            "outcome) has been shown. Estimated overlap: +0.15 log-odds."
        )
        double_count += 0.15
        has_critical = True

    return LayerOverlapReport(
        overlapping_signals=overlapping,
        recommendations=recommendations,
        has_critical_overlap=has_critical,
        estimated_double_count_logodds=round(double_count, 4),
    )


# ---------------------------------------------------------------------------
# Cap stress analysis (decision robustness)
# ---------------------------------------------------------------------------

@dataclass
class CapStressResult:
    """
    Output of cap_stress_analysis().

    Shows how adjusted_pos changes as the cap value is varied by ±fraction.

    Attributes
    ----------
    base_result : DesignAdjustedPOSResult
        The result at the nominal cap values.
    stress_results : list[tuple[float, float, DesignAdjustedPOSResult]]
        List of (cap_pos_multiplier, cap_neg_multiplier, result) for each stress scenario.
    conclusion_stable : bool
        True if the binary conclusion (adjusted_pos > threshold) does not change
        across any stress scenario.
    threshold : float
        The threshold used for conclusion stability check.
    """
    base_result: DesignAdjustedPOSResult
    stress_results: list[tuple[float, float, "DesignAdjustedPOSResult"]]
    conclusion_stable: bool
    threshold: float

    def pos_range(self) -> tuple[float, float]:
        """Min and max adjusted_pos across all stress scenarios."""
        all_pos = [r.adjusted_pos for _, _, r in self.stress_results]
        return (min(all_pos), max(all_pos))

    def summary(self) -> str:
        lo, hi = self.pos_range()
        stable_str = "STABLE" if self.conclusion_stable else "UNSTABLE"
        return (
            f"Cap stress: adjusted_pos range [{lo:.3f}, {hi:.3f}] "
            f"(base: {self.base_result.adjusted_pos:.3f}). "
            f"Conclusion at threshold {self.threshold:.2f}: {stable_str}."
        )


def cap_stress_analysis(
    base_pos: float,
    features: TrialDesignFeatureSet,
    phase: str,
    cap_multipliers: Optional[list[float]] = None,
    threshold: float = 0.50,
    settings: Optional[dict] = None,
) -> CapStressResult:
    """
    Test robustness of adjusted_pos to variation in cap values.

    Parameters
    ----------
    base_pos : float
    features : TrialDesignFeatureSet
    phase : str
    cap_multipliers : list[float], optional
        Multipliers applied to both caps. Default: [0.80, 0.90, 1.00, 1.10, 1.20].
    threshold : float
        Decision threshold for conclusion stability. Default 0.50.
    settings : dict, optional
        Base settings override.

    Returns
    -------
    CapStressResult
    """
    if cap_multipliers is None:
        cap_multipliers = [0.80, 0.90, 1.00, 1.10, 1.20]

    base_cap_pos = TRIAL_DESIGN_CAP_POSITIVE if settings is None else settings.get(
        "cap_logodds_positive", TRIAL_DESIGN_CAP_POSITIVE
    )
    base_cap_neg = TRIAL_DESIGN_CAP_NEGATIVE if settings is None else settings.get(
        "cap_logodds_negative", TRIAL_DESIGN_CAP_NEGATIVE
    )

    base_result = compute_design_adjusted_pos(base_pos, features, phase=phase, settings=settings)
    stress_results = []
    base_decision = base_result.adjusted_pos > threshold

    for mult in cap_multipliers:
        stressed_settings = {
            "cap_logodds_positive": base_cap_pos * mult,
            "cap_logodds_negative": base_cap_neg * mult,
        }
        result = compute_design_adjusted_pos(base_pos, features, phase=phase, settings=stressed_settings)
        stress_results.append((mult, mult, result))

    decisions = {(r.adjusted_pos > threshold) for _, _, r in stress_results}
    conclusion_stable = len(decisions) == 1 and list(decisions)[0] == base_decision

    return CapStressResult(
        base_result=base_result,
        stress_results=stress_results,
        conclusion_stable=conclusion_stable,
        threshold=threshold,
    )
