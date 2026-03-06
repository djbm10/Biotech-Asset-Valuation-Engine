"""
Trial design feature adjustment: 3-dimensional endpoint classification.

Separates the single endpoint_type adjuster (in POSAdjusters) into three
orthogonal dimensions that capture distinct regulatory risk factors:

  1. EndpointBasis:    WHAT is being measured (hard outcome vs. surrogate)
  2. EvidenceDesign:  HOW the evidence is generated (RCT vs. single-arm)
  3. ApprovalPathway: WHICH regulatory pathway is expected

These adjustments are EVIDENCE-INFORMED PRIORS intended for scenario
differentiation and sensitivity analysis. They are not statistically estimated
coefficients. A 10-15pp swing in POS is plausible given the difference between
an RCT with hard endpoints vs a single-arm trial using a novel surrogate, but
the exact values are judgment calls — not regression outputs.

Phase is required
-----------------
compute_design_adjusted_pos() requires an explicit `phase` argument because:
  - Design effects are NOT the same across phases. Single-arm at Phase 1 is
    universal and appropriate; single-arm at Phase 3 pivotal is a risk.
  - Defaulting to Phase 3 (maximum effect) would silently overstate impact for
    any Phase 1 or Phase 2 trial where phase was not specified.
  - Institutional principle: missing data should not increase estimated effect
    sizes. Require explicit phase to avoid silent amplification.

Valid phase values: "phase_1", "phase_2", "phase_3", "nda_bla"
Use TRIAL_DESIGN_PHASE_NEUTRAL ("neutral") ONLY when phase is genuinely unknown
and you want explicit maximum-effect estimates as a stress test.

Anti-double-counting policy
----------------------------
This module introduces a second layer of POS adjustment on top of POSAdjusters
(in pos_model.py). Several signals overlap between layers:

  1. Endpoint quality: POSAdjusters.endpoint_type ↔ TrialDesignFeatureSet.endpoint_basis
     → Use ONE, not both. TrialDesignFeatureSet.endpoint_basis is more granular.

  2. BTD signal: POSAdjusters.has_breakthrough_designation ↔ ApprovalPathway.BREAKTHROUGH_DESIGNATION
     → Use ONE. POSAdjusters version has the primary calibrated effect (+0.20 log-odds).
     → ApprovalPathway.BREAKTHROUGH_DESIGNATION is a weak residual (+0.10 log-odds × phase scale)
       intended for analysts using TrialDesignFeatureSet WITHOUT POSAdjusters.

Use check_pos_layer_overlap() to audit a specific combination before accepting results.

Log-odds adjustment values, phase scaling, and full provenance are in
bve.config.constants (TRIAL_DESIGN_LOGODDS, TRIAL_DESIGN_PHASE_SCALING).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
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
    from bve.models.pos_model import POSAdjusters


class EndpointBasis(str, Enum):
    """
    Primary endpoint type — WHAT is being measured.

    Captures the regulatory weight given to the measured outcome:
      - HARD_CLINICAL: directly observed clinical outcome (OS, EFS, time to
        dialysis, complete remission). Most accepted for regular approval.
      - SURROGATE_VALIDATED: surrogate correlated with clinical benefit and
        FDA-accepted as primary for the indication (PFS in oncology, HbA1c
        in diabetes, FEV1 in CF, SVR35 in myelofibrosis).
      - SURROGATE_NOVEL: proposed surrogate without established FDA acceptance
        for this indication. Higher regulatory risk.
      - BIOMARKER_ONLY: pharmacodynamic or biomarker endpoint; insufficient
        as standalone primary for regular approval in most indications.
    """
    HARD_CLINICAL = "hard_clinical"
    SURROGATE_VALIDATED = "surrogate_validated"
    SURROGATE_NOVEL = "surrogate_novel"
    BIOMARKER_ONLY = "biomarker_only"


class EvidenceDesign(str, Enum):
    """
    Study design — HOW the evidence is generated.

    NOTE: single-arm trials are standard at Phase 1 and common in rare/refractory
    oncology. The SINGLE_ARM penalty is attenuated to ~zero at Phase 1 via
    phase-conditional scaling. Always provide phase to get appropriate attenuation.

      - RCT_COMPARATIVE: randomized, controlled with active or placebo
        comparator (gold standard). Baseline reference.
      - RCT_NON_COMPARATIVE: randomized but without a meaningful comparator.
      - SINGLE_ARM: non-randomized; meaningful regulatory risk only at Phase 3.
      - REGISTRY_BASED: observational evidence; highest regulatory risk.
    """
    RCT_COMPARATIVE = "rct_comparative"
    RCT_NON_COMPARATIVE = "rct_non_comparative"
    SINGLE_ARM = "single_arm"
    REGISTRY_BASED = "registry_based"


class ApprovalPathway(str, Enum):
    """
    Regulatory approval pathway — WHICH FDA mechanism is expected.

    CAUTION: Pathway designations primarily affect time-to-approval and commercial
    adoption, not binary approval probability. Adjustments here are WEAK MODIFIERS
    (+0.05–0.10 log-odds, further attenuated by phase scaling).

    DOUBLE-COUNTING RISK: POSAdjusters.has_breakthrough_designation (pos_model.py)
    has the primary BTD signal (+0.20 log-odds). Do NOT use BREAKTHROUGH_DESIGNATION
    here AND has_breakthrough_designation=True in the same computation.
    Use check_pos_layer_overlap() to audit.

      - STANDARD: standard review; baseline reference.
      - ACCELERATED_APPROVAL: FDA AA; surrogate endpoint accepted as primary.
      - BREAKTHROUGH_DESIGNATION: BTD. Weak residual prior here — prefer
        POSAdjusters.has_breakthrough_designation for the primary signal.
      - ORPHAN_DRUG: ODD; regulatory flexibility; lower enrollment burden.
    """
    STANDARD = "standard"
    ACCELERATED_APPROVAL = "accelerated_approval"
    BREAKTHROUGH_DESIGNATION = "breakthrough_designation"
    ORPHAN_DRUG = "orphan_drug"


class TrialDesignFeatureSet(BaseModel):
    """
    Three-dimensional trial design feature set.

    Defaults represent the reference/baseline scenario:
      - Surrogate-validated endpoint (most common Phase 3 scenario)
      - RCT with comparator (gold standard design)
      - Standard regulatory pathway (no special designation)

    Always pass `phase` to compute_adjusted_pos() — the appropriate attenuation
    depends on which trial phase is being evaluated.
    """
    endpoint_basis: EndpointBasis = EndpointBasis.SURROGATE_VALIDATED
    evidence_design: EvidenceDesign = EvidenceDesign.RCT_COMPARATIVE
    approval_pathway: ApprovalPathway = ApprovalPathway.STANDARD

    def compute_adjusted_pos(
        self,
        base_pos: float,
        phase: str,
    ) -> "DesignAdjustedPOSResult":
        """Apply design adjustment to base_pos. phase is required."""
        return compute_design_adjusted_pos(base_pos, self, phase=phase)


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
    phase_scaling_applied : dict[str, float]
        The scaling factor used for each dimension. All 1.0 when phase="neutral".
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


# Valid phase values recognized by compute_design_adjusted_pos
_VALID_PHASES = frozenset(TRIAL_DESIGN_PHASE_SCALING.keys()) | {TRIAL_DESIGN_PHASE_NEUTRAL}
_NEUTRAL_SCALING: dict[str, float] = {
    "endpoint_basis": 1.0,
    "evidence_design": 1.0,
    "approval_pathway": 1.0,
}


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
        or from a TA-specific base rate in PHASE_SUCCESS_RATES.
    features : TrialDesignFeatureSet
        The 3-dimensional endpoint feature set to apply.
    phase : str
        Trial phase key. REQUIRED — design effects differ materially by phase.
        Valid values: "phase_1", "phase_2", "phase_3", "nda_bla",
        or TRIAL_DESIGN_PHASE_NEUTRAL ("neutral") for explicit maximum-effect
        estimates when phase is genuinely unknown.

        Institutional rationale: missing phase must not silently increase effect
        sizes. Phase 3 has the highest endpoint/evidence scaling (1.0); using
        Phase 3 as a default would overstate impact for Phase 1 and Phase 2 trials.

    settings : dict, optional
        Override for TRIAL_DESIGN_LOGODDS constants. Optional keys
        "cap_logodds_positive" and "cap_logodds_negative" override cap values.
        When None, reads from bve.config.constants.

    Returns
    -------
    DesignAdjustedPOSResult
        Adjusted POS with full breakdown of each dimension's contribution,
        phase scaling applied, and cap metadata.

    Raises
    ------
    ValueError
        If phase is not a recognized value. The error message lists valid options.

    Notes
    -----
    - Phase scaling is applied to each dimension's raw log-odds value before
      summation and capping.
    - This function should NOT be combined with POSAdjusters.endpoint_type
      on the same trial — double-counting risk. Use check_pos_layer_overlap()
      to audit any combination before accepting results.
    """
    if phase not in _VALID_PHASES:
        raise ValueError(
            f"Invalid phase {phase!r}. Valid values: {sorted(_VALID_PHASES)}. "
            f"Use TRIAL_DESIGN_PHASE_NEUTRAL={TRIAL_DESIGN_PHASE_NEUTRAL!r} for "
            f"explicit maximum-effect mode when phase is genuinely unknown."
        )

    if settings is not None:
        logodds_table = settings
        cap_pos = float(settings.get("cap_logodds_positive", TRIAL_DESIGN_CAP_POSITIVE))
        cap_neg = float(settings.get("cap_logodds_negative", TRIAL_DESIGN_CAP_NEGATIVE))
    else:
        logodds_table = TRIAL_DESIGN_LOGODDS
        cap_pos = TRIAL_DESIGN_CAP_POSITIVE
        cap_neg = TRIAL_DESIGN_CAP_NEGATIVE

    # Phase scaling: "neutral" → all 1.0 (documented maximum-effect mode)
    if phase == TRIAL_DESIGN_PHASE_NEUTRAL:
        scaling = _NEUTRAL_SCALING
    else:
        scaling = TRIAL_DESIGN_PHASE_SCALING[phase]

    base_pos = max(0.001, min(0.999, base_pos))
    base_logodds = math.log(base_pos / (1.0 - base_pos))

    eb_raw = logodds_table["endpoint_basis"].get(features.endpoint_basis.value, 0.0)
    ed_raw = logodds_table["evidence_design"].get(features.evidence_design.value, 0.0)
    ap_raw = logodds_table["approval_pathway"].get(features.approval_pathway.value, 0.0)

    eb_adj = eb_raw * scaling.get("endpoint_basis", 1.0)
    ed_adj = ed_raw * scaling.get("evidence_design", 1.0)
    ap_adj = ap_raw * scaling.get("approval_pathway", 1.0)

    uncapped = eb_adj + ed_adj + ap_adj

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

    return DesignAdjustedPOSResult(
        adjusted_pos=round(adjusted_pos, 4),
        base_pos=round(base_pos, 4),
        total_logodds_adjustment=round(capped, 4),
        uncapped_logodds_adjustment=round(uncapped, 4),
        adjustment_breakdown={
            "endpoint_basis": round(eb_adj, 4),
            "evidence_design": round(ed_adj, 4),
            "approval_pathway": round(ap_adj, 4),
        },
        phase_scaling_applied={
            "endpoint_basis": scaling.get("endpoint_basis", 1.0),
            "evidence_design": scaling.get("evidence_design", 1.0),
            "approval_pathway": scaling.get("approval_pathway", 1.0),
        },
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

    This is an AUDIT tool — it does not prevent computation, only reports
    whether the combination is methodologically sound.

    Attributes
    ----------
    overlapping_signals : list[str]
        Human-readable descriptions of each detected overlap.
    recommendations : list[str]
        Specific actions to resolve each overlap.
    has_critical_overlap : bool
        True if any overlap is classified as "critical" (likely to materially
        double-count). A critical overlap invalidates the combined POS estimate
        unless the analyst can justify the combination.
    estimated_double_count_logodds : float
        Conservative lower bound on the log-odds magnitude being double-counted.
        This is the overlap contribution that would need to be removed to avoid
        double-counting. Not exact — for order-of-magnitude awareness only.
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
) -> LayerOverlapReport:
    """
    Audit a POSAdjusters + TrialDesignFeatureSet combination for double-counting.

    Two signals are considered overlapping when the same real-world factor
    (endpoint quality, BTD status) is independently counted in both layers,
    resulting in its effect being amplified beyond what a single-layer model
    would produce.

    Parameters
    ----------
    pos_adjusters : POSAdjusters
        The heuristic layer (from pos_model.compute_pos).
    design_features : TrialDesignFeatureSet
        The design layer (from compute_design_adjusted_pos).
    phase : str, optional
        Phase context for estimating scaled magnitudes. None uses raw values.

    Returns
    -------
    LayerOverlapReport
        Lists all detected overlaps and resolution recommendations.

    Policy
    ------
    Critical overlaps (likely invalidate combined estimate):
      1. Endpoint quality: pos_adjusters.endpoint_type non-default AND
         design_features.endpoint_basis non-default
         → The same endpoint quality signal counted in both layers.
         → Resolution: set endpoint_type=SURROGATE_VALIDATED (neutral) in POSAdjusters.

      2. BTD status: pos_adjusters.has_breakthrough_designation=True AND
         design_features.approval_pathway=BREAKTHROUGH_DESIGNATION
         → BTD signal counted in both layers.
         → Resolution: set has_breakthrough_designation=False in POSAdjusters
           OR set approval_pathway=STANDARD in TrialDesignFeatureSet.
    """
    from bve.entities.trial import EndpointType

    overlapping: list[str] = []
    recommendations: list[str] = []
    double_count_lo: float = 0.0
    has_critical = False

    # Check 1: endpoint quality overlap
    endpoint_type_is_default = (pos_adjusters.endpoint_type == EndpointType.SURROGATE_VALIDATED)
    endpoint_basis_is_default = (design_features.endpoint_basis == EndpointBasis.SURROGATE_VALIDATED)
    if not endpoint_type_is_default and not endpoint_basis_is_default:
        has_critical = True
        # Rough magnitude: both layers have non-zero endpoint adjustment
        from bve.models.pos_model import _ENDPOINT_LOGODDS
        pa_lo = abs(_ENDPOINT_LOGODDS.get(pos_adjusters.endpoint_type, 0.0))
        td_lo_raw = abs(TRIAL_DESIGN_LOGODDS["endpoint_basis"].get(
            design_features.endpoint_basis.value, 0.0
        ))
        # Scale design contribution by phase if available
        td_lo_scale = 1.0
        if phase and phase != TRIAL_DESIGN_PHASE_NEUTRAL:
            td_lo_scale = TRIAL_DESIGN_PHASE_SCALING.get(phase, {}).get("endpoint_basis", 1.0)
        td_lo = td_lo_raw * td_lo_scale
        overlap_lo = min(pa_lo, td_lo)  # conservative: minimum of the two
        double_count_lo += overlap_lo
        overlapping.append(
            f"Endpoint quality: pos_adjusters.endpoint_type={pos_adjusters.endpoint_type.value!r} "
            f"(non-default) AND design_features.endpoint_basis={design_features.endpoint_basis.value!r} "
            f"(non-default). Both count endpoint quality. "
            f"Estimated overlap: {overlap_lo:+.2f} log-odds."
        )
        recommendations.append(
            "Set pos_adjusters.endpoint_type=EndpointType.SURROGATE_VALIDATED (neutral) when using "
            "TrialDesignFeatureSet.endpoint_basis for endpoint quality, OR set "
            "design_features.endpoint_basis=EndpointBasis.SURROGATE_VALIDATED (neutral) and keep "
            "endpoint_type in POSAdjusters."
        )

    # Check 2: BTD overlap
    btd_in_pos = pos_adjusters.has_breakthrough_designation
    btd_in_design = (design_features.approval_pathway == ApprovalPathway.BREAKTHROUGH_DESIGNATION)
    if btd_in_pos and btd_in_design:
        has_critical = True
        pa_btd_lo = 0.20  # from _BREAKTHROUGH_BONUS in pos_model.py
        td_btd_raw = TRIAL_DESIGN_LOGODDS["approval_pathway"].get("breakthrough_designation", 0.0)
        td_btd_scale = 1.0
        if phase and phase != TRIAL_DESIGN_PHASE_NEUTRAL:
            td_btd_scale = TRIAL_DESIGN_PHASE_SCALING.get(phase, {}).get("approval_pathway", 1.0)
        td_btd = td_btd_raw * td_btd_scale
        overlap_btd = min(pa_btd_lo, td_btd)
        double_count_lo += overlap_btd
        overlapping.append(
            f"Breakthrough designation: pos_adjusters.has_breakthrough_designation=True AND "
            f"design_features.approval_pathway=BREAKTHROUGH_DESIGNATION. "
            f"BTD signal counted in both layers. "
            f"Estimated overlap: {overlap_btd:+.2f} log-odds."
        )
        recommendations.append(
            "Set pos_adjusters.has_breakthrough_designation=False when using "
            "ApprovalPathway.BREAKTHROUGH_DESIGNATION in TrialDesignFeatureSet, OR "
            "set design_features.approval_pathway=ApprovalPathway.STANDARD and keep "
            "has_breakthrough_designation in POSAdjusters (which has the primary calibrated signal)."
        )

    return LayerOverlapReport(
        overlapping_signals=overlapping,
        recommendations=recommendations,
        has_critical_overlap=has_critical,
        estimated_double_count_logodds=round(double_count_lo, 4),
    )


# ---------------------------------------------------------------------------
# Cap stress analysis (decision robustness)
# ---------------------------------------------------------------------------

@dataclass
class CapStressResult:
    """
    Output of cap_stress_analysis().

    Shows how adjusted_pos changes as the cap value is varied by ±fraction.
    Institutional use: if the decision conclusion (e.g., adjusted_pos > 0.50)
    changes with cap variation, the conclusion is not robust to cap choice.

    Attributes
    ----------
    base_result : DesignAdjustedPOSResult
        The result at the nominal cap values.
    stress_results : list[tuple[float, float, DesignAdjustedPOSResult]]
        List of (cap_pos_multiplier, cap_neg_multiplier, result) for each
        stress scenario tested.
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

    Reruns compute_design_adjusted_pos with caps scaled by each multiplier in
    cap_multipliers. If the binary decision (adjusted_pos > threshold) changes
    across scenarios, the result is flagged as not conclusion-stable.

    Parameters
    ----------
    base_pos : float
        Base POS to adjust.
    features : TrialDesignFeatureSet
        Trial design features.
    phase : str
        Trial phase (required, same as compute_design_adjusted_pos).
    cap_multipliers : list[float], optional
        Multipliers applied to both TRIAL_DESIGN_CAP_POSITIVE and
        TRIAL_DESIGN_CAP_NEGATIVE. Default: [0.80, 0.90, 1.00, 1.10, 1.20].
    threshold : float
        Decision threshold for conclusion stability. Default 0.50 (pass/fail).
    settings : dict, optional
        Base settings override (same as compute_design_adjusted_pos).

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
        stressed_settings = dict(settings or TRIAL_DESIGN_LOGODDS)
        stressed_settings["cap_logodds_positive"] = base_cap_pos * mult
        stressed_settings["cap_logodds_negative"] = base_cap_neg * mult
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
