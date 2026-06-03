"""
Regulatory risk inference model for FDA approval scenarios.

Produces a probability distribution over five regulatory outcome scenarios
(clean approval, delayed approval, narrow label, complete response letter,
high post-market burden) by applying a transparent, score-accumulation
approach to observable signals from a drug's regulatory profile.

No machine learning is used; all adjusters are documented and calibrated
to industry data on FDA approval rates by pathway, prior CRL history,
endpoint type, safety signals, and AdCom precedent.

The model outputs:
  - scenario probabilities (sum to 1.0)
  - dominant scenario
  - approval_probability: P(any approval outcome)
  - expected_pdufa_months: probability-weighted months to FDA action
  - pos_modifier: log-odds adjustment for use in a trial-phase POS model
  - risk_flags: human-readable warning strings for analysts

Reference: FDA PDUFA performance reports; Mullard (2016) Nature Reviews Drug
Discovery analysis of CRL drivers; Biomedtracker NDA/BLA approval rate data.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ApprovalPathway(str, Enum):
    STANDARD = "standard"
    PRIORITY = "priority"
    BREAKTHROUGH = "breakthrough"
    ACCELERATED = "accelerated"
    FAST_TRACK = "fast_track"


class RegulatoryScenario(str, Enum):
    CLEAN_APPROVAL = "clean_approval"
    DELAYED_APPROVAL = "delayed_approval"           # PDUFA miss, >6 mo delay
    NARROW_LABEL = "narrow_label"                   # approved but narrower than filed
    CRL = "complete_response_letter"                # major deficiency
    HIGH_POSTMARKET_BURDEN = "high_postmarket_burden"  # heavy REMS / confirmatory studies


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RegulatoryProfile:
    """Observable signals for FDA posture inference."""
    approval_pathway: ApprovalPathway
    prior_crl_count: int = 0                        # prior CRLs in same drug / class
    endpoint_type: str = "surrogate_validated"      # maps to EndpointType values
    safety_serious_events: bool = False
    adcom_precedent: str = "none"                   # "positive", "negative", "mixed", "none"
    manufacturing_inspections_clear: bool = True
    confirmatory_study_required: bool = False       # accelerated approval burden
    class_prior_crl_rate: float = 0.0              # fraction of same-class drugs that got CRL
    modality: str = "small_molecule"                # small_molecule, biologic, cell_gene, adc


@dataclass(frozen=True)
class RegulatoryScenarioProbability:
    scenario: RegulatoryScenario
    probability: float          # sums to 1.0 across all scenarios for a given profile
    pdufa_months: int           # expected months to action (from NDA/BLA filing)
    rationale: str


@dataclass
class RegulatoryInferenceResult:
    profile: RegulatoryProfile
    scenarios: list[RegulatoryScenarioProbability]
    dominant_scenario: RegulatoryScenario
    approval_probability: float         # P(clean) + P(narrow) + P(high_postmarket)
    expected_pdufa_months: float        # probability-weighted PDUFA estimate
    risk_flags: list[str]               # human-readable warning strings
    pos_modifier: float                 # log-odds adjustment for trial-phase POS
                                        # negative = regulatory headwind, positive = tailwind


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_BASE_APPROVAL_PROBABILITY: dict[ApprovalPathway, float] = {
    ApprovalPathway.STANDARD:     0.85,
    ApprovalPathway.PRIORITY:     0.88,
    ApprovalPathway.BREAKTHROUGH: 0.91,
    ApprovalPathway.ACCELERATED:  0.78,
    ApprovalPathway.FAST_TRACK:   0.87,
}

_BASE_PDUFA_MONTHS: dict[ApprovalPathway, int] = {
    ApprovalPathway.STANDARD:     12,
    ApprovalPathway.PRIORITY:     6,
    ApprovalPathway.BREAKTHROUGH: 6,
    ApprovalPathway.ACCELERATED:  6,
    ApprovalPathway.FAST_TRACK:   10,
}

# Scenario allocation fractions applied to approval_probability (p_a)
# and rejection probability (1 - p_a).
_SCENARIO_APPROVAL_FRACTIONS: dict[RegulatoryScenario, float] = {
    RegulatoryScenario.CLEAN_APPROVAL:         0.70,
    RegulatoryScenario.NARROW_LABEL:           0.20,
    RegulatoryScenario.HIGH_POSTMARKET_BURDEN: 0.10,
}
_SCENARIO_REJECTION_FRACTIONS: dict[RegulatoryScenario, float] = {
    RegulatoryScenario.DELAYED_APPROVAL: 0.55,
    RegulatoryScenario.CRL:              0.45,
}

# PDUFA months per scenario (relative to base pathway PDUFA months).
_SCENARIO_PDUFA_OFFSETS: dict[RegulatoryScenario, int] = {
    RegulatoryScenario.CLEAN_APPROVAL:          0,
    RegulatoryScenario.NARROW_LABEL:            1,
    RegulatoryScenario.HIGH_POSTMARKET_BURDEN:  2,
    RegulatoryScenario.DELAYED_APPROVAL:        6,   # >6 mo delay by definition
    RegulatoryScenario.CRL:                     0,   # CRL issued at action date
}

_APPROVAL_PROB_FLOOR: float = 0.30
_APPROVAL_PROB_CEILING: float = 0.97
_POS_MODIFIER_FLOOR: float = -0.40
_POS_MODIFIER_CEILING: float = +0.15
_POS_MODIFIER_SCALE: float = 0.40   # downward adjusters applied at 40% magnitude


# ---------------------------------------------------------------------------
# Core inference function
# ---------------------------------------------------------------------------

def infer_regulatory_risk(profile: RegulatoryProfile) -> RegulatoryInferenceResult:
    """
    Infer FDA approval risk from observable regulatory signals.

    Parameters
    ----------
    profile:
        RegulatoryProfile populated with signals known at NDA/BLA filing.

    Returns
    -------
    RegulatoryInferenceResult with scenario distribution, approval probability,
    PDUFA estimate, risk flags, and a log-odds POS modifier.
    """
    risk_flags: list[str] = []

    approval_probability, pos_modifier = _compute_probabilities(profile, risk_flags)

    base_pdufa = _BASE_PDUFA_MONTHS[profile.approval_pathway]
    pdufa_adjustment = _compute_pdufa_adjustment(profile)
    adjusted_pdufa = base_pdufa + pdufa_adjustment

    scenarios = _build_scenario_distribution(
        approval_probability=approval_probability,
        base_pdufa_months=adjusted_pdufa,
    )

    dominant_scenario = max(scenarios, key=lambda s: s.probability).scenario

    expected_pdufa_months = sum(
        s.probability * s.pdufa_months for s in scenarios
    )

    return RegulatoryInferenceResult(
        profile=profile,
        scenarios=scenarios,
        dominant_scenario=dominant_scenario,
        approval_probability=approval_probability,
        expected_pdufa_months=round(expected_pdufa_months, 2),
        risk_flags=risk_flags,
        pos_modifier=pos_modifier,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_probabilities(
    profile: RegulatoryProfile,
    risk_flags: list[str],
) -> tuple[float, float]:
    """
    Return (approval_probability, pos_modifier) after applying all adjusters.

    Side-effect: appends human-readable strings to risk_flags.
    """
    base = _BASE_APPROVAL_PROBABILITY[profile.approval_pathway]
    delta = 0.0

    # -- Downward adjusters --------------------------------------------------

    if profile.prior_crl_count >= 1:
        crl_penalty = -0.08 * profile.prior_crl_count
        crl_penalty = max(crl_penalty, -0.20)
        delta += crl_penalty
        risk_flags.append("Prior CRL detected: regulatory credibility reduced")

    if profile.safety_serious_events:
        delta -= 0.12
        risk_flags.append("Serious adverse events: safety review likely")

    if profile.adcom_precedent == "negative":
        delta -= 0.15
        risk_flags.append("Negative AdCom precedent: approval risk elevated")
    elif profile.adcom_precedent == "mixed":
        delta -= 0.05

    if not profile.manufacturing_inspections_clear:
        delta -= 0.08

    if profile.class_prior_crl_rate > 0.20:
        delta -= 0.05
        risk_flags.append("Class CRL rate >20%: sector-level regulatory headwind")

    if profile.endpoint_type == "biomarker_only":
        delta -= 0.10
        risk_flags.append("Novel surrogate endpoint: label restriction risk")
    elif profile.endpoint_type == "surrogate_novel":
        delta -= 0.05
        risk_flags.append("Novel surrogate endpoint: label restriction risk")

    if profile.approval_pathway == ApprovalPathway.ACCELERATED and profile.confirmatory_study_required:
        risk_flags.append("Accelerated approval: confirmatory study burden")

    # -- Upward adjusters ----------------------------------------------------

    if profile.adcom_precedent == "positive":
        delta += 0.05

    if profile.endpoint_type == "hard_clinical":
        delta += 0.02

    # -- Final approval probability ------------------------------------------

    approval_probability = float(
        max(_APPROVAL_PROB_FLOOR, min(_APPROVAL_PROB_CEILING, base + delta))
    )

    # -- POS modifier (log-odds; same direction, 40% magnitude, clipped) -----

    pos_modifier = float(
        max(_POS_MODIFIER_FLOOR, min(_POS_MODIFIER_CEILING, delta * _POS_MODIFIER_SCALE))
    )

    return approval_probability, pos_modifier


def _compute_pdufa_adjustment(profile: RegulatoryProfile) -> int:
    """Return the number of additional months to add to the base PDUFA timeline."""
    extra = 0
    if profile.safety_serious_events:
        extra += 3
    if profile.prior_crl_count >= 1:
        extra += 2
    return extra


def _build_scenario_distribution(
    approval_probability: float,
    base_pdufa_months: int,
) -> list[RegulatoryScenarioProbability]:
    """
    Allocate probabilities across the five regulatory scenarios.

    Approval scenarios share approval_probability; rejection scenarios share
    (1 - approval_probability). Fractions within each group are fixed constants.
    """
    rejection_probability = 1.0 - approval_probability
    scenarios: list[RegulatoryScenarioProbability] = []

    approval_rationales: dict[RegulatoryScenario, str] = {
        RegulatoryScenario.CLEAN_APPROVAL: (
            "Full approval on first action; label consistent with filed indication."
        ),
        RegulatoryScenario.NARROW_LABEL: (
            "Approved with a more restricted population or indication than filed."
        ),
        RegulatoryScenario.HIGH_POSTMARKET_BURDEN: (
            "Approval granted but with substantial REMS or confirmatory study requirements."
        ),
    }
    rejection_rationales: dict[RegulatoryScenario, str] = {
        RegulatoryScenario.DELAYED_APPROVAL: (
            "PDUFA date missed; FDA issues information request or extends review >6 months."
        ),
        RegulatoryScenario.CRL: (
            "Complete response letter issued citing major efficacy, safety, or CMC deficiency."
        ),
    }

    for scenario, fraction in _SCENARIO_APPROVAL_FRACTIONS.items():
        prob = approval_probability * fraction
        pdufa = base_pdufa_months + _SCENARIO_PDUFA_OFFSETS[scenario]
        scenarios.append(
            RegulatoryScenarioProbability(
                scenario=scenario,
                probability=round(prob, 6),
                pdufa_months=pdufa,
                rationale=approval_rationales[scenario],
            )
        )

    for scenario, fraction in _SCENARIO_REJECTION_FRACTIONS.items():
        prob = rejection_probability * fraction
        pdufa = base_pdufa_months + _SCENARIO_PDUFA_OFFSETS[scenario]
        scenarios.append(
            RegulatoryScenarioProbability(
                scenario=scenario,
                probability=round(prob, 6),
                pdufa_months=pdufa,
                rationale=rejection_rationales[scenario],
            )
        )

    return scenarios
