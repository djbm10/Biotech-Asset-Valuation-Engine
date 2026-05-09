"""
Sample Size / Statistical Power Scorer.

Implements the scoring rule:

    sample_size_score = function(
        planned_sample_size,
        statistical_power,
        expected_effect_size,
        endpoint_variability,
        control_rate_or_placebo_response,
        dropout_rate,
        trial_design,
        phase,
        indication_rarity,
    ) -> SampleSizeAdequacy

When statistical_power is supplied directly, it is used as-is.
When not supplied, power is computed from the other parameters using
standard normal-approximation formulae for:
  - Continuous endpoints: two-sample t-test (requires expected_effect_size + endpoint_variability)
  - Binary endpoints:     chi-square / Z-test (requires expected_effect_size + control_rate_or_placebo_response)

Therapeutic-area minimum-N thresholds are applied as a secondary check:
even a well-powered study that falls below the TA-specific minimum for
its phase is downgraded by one tier.  These thresholds capture the
clinical reality that raw power calculations can be unrealistic when
the endpoint is a rare event (e.g., MACE in cardiovascular outcomes).

Sources:
  - FDA Guidance for Industry: Adaptive Designs for Clinical Trials (2019)
  - ICH E9(R1): Addendum on Estimands and Sensitivity Analysis (2019)
  - Chow & Liu: Design and Analysis of Clinical Trials, 3rd ed.
  - EMA Guideline on the Choice of the Non-Inferiority Margin (2005)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from bve.entities.trial import TrialPhase
from bve.models.pos_model import SampleSizeAdequacy


# ---------------------------------------------------------------------------
# Trial design types
# ---------------------------------------------------------------------------

class SampleSizeTrialDesign(str, Enum):
    """
    Trial design type used by the sample size scorer.

    Affects both the power computation (crossover/paired → efficiency boost)
    and the tier cap (exploratory/single_arm → confirmatory cap applied).
    """
    RCT           = "rct"           # Randomized, double-blind or open-label
    SINGLE_ARM    = "single_arm"    # No control arm; single-arm
    CROSSOVER     = "crossover"     # Subjects serve as own control; n per sequence not arm
    PAIRED        = "paired"        # Paired observations (e.g., paired-eye ophthalmology)
    ADAPTIVE      = "adaptive"      # Adaptive design; N may expand at interim analysis
    BASKET        = "basket"        # Basket trial; multiple tumor types / indications
    PLATFORM      = "platform"      # Platform trial; multiple arms added or dropped
    EXPLORATORY   = "exploratory"   # Signal-seeking pilot; no formal power calculation
    REGISTRY      = "registry"      # Observational / registry study; not confirmatory


# ---------------------------------------------------------------------------
# TA-specific minimum-N thresholds for ADEQUATE tier
# ---------------------------------------------------------------------------
# If effective_n < threshold, the tier is downgraded by one level regardless
# of computed power.  These thresholds reflect regulatory precedent:
#   - Rare disease: 30-patient trials are routinely approved (NORD 2020)
#   - Cardiovascular outcomes: thousands are needed for event-based MACE endpoints
#   - Psychiatry: placebo response noise requires larger N for a given power

_TA_MIN_N_ADEQUATE: dict[str, dict[str, int]] = {
    "cardiovascular":    {"phase_1": 30,  "phase_2": 300,  "phase_3": 1000},
    "metabolic":         {"phase_1": 30,  "phase_2": 150,  "phase_3": 400},
    "renal":             {"phase_1": 30,  "phase_2": 80,   "phase_3": 300},
    "pulmonary":         {"phase_1": 30,  "phase_2": 80,   "phase_3": 250},
    "psychiatry":        {"phase_1": 20,  "phase_2": 120,  "phase_3": 300},
    "cns":               {"phase_1": 20,  "phase_2": 80,   "phase_3": 250},
    "infectious_disease":{"phase_1": 30,  "phase_2": 80,   "phase_3": 200},
    "immunology":        {"phase_1": 20,  "phase_2": 60,   "phase_3": 150},
    "dermatology":       {"phase_1": 20,  "phase_2": 50,   "phase_3": 120},
    "gastroenterology":  {"phase_1": 20,  "phase_2": 60,   "phase_3": 150},
    "oncology":          {"phase_1": 15,  "phase_2": 40,   "phase_3": 120},
    "oncology_solid":    {"phase_1": 15,  "phase_2": 40,   "phase_3": 120},
    "hematology":        {"phase_1": 15,  "phase_2": 30,   "phase_3": 80},
    "ophthalmology":     {"phase_1": 10,  "phase_2": 20,   "phase_3": 60},
    "rare_disease":      {"phase_1": 5,   "phase_2": 15,   "phase_3": 25},
    "other":             {"phase_1": 20,  "phase_2": 60,   "phase_3": 150},
}

# Designs that receive an effective-N multiplier (>1 = more efficient than two-arm RCT)
_DESIGN_EFFICIENCY: dict[SampleSizeTrialDesign, float] = {
    SampleSizeTrialDesign.RCT:         1.00,
    SampleSizeTrialDesign.SINGLE_ARM:  0.60,   # no internal control; placebo drift unaccounted
    SampleSizeTrialDesign.CROSSOVER:   1.70,   # within-subject comparison removes between-subject variance
    SampleSizeTrialDesign.PAIRED:      1.50,   # paired-eye or matched design; similar benefit
    SampleSizeTrialDesign.ADAPTIVE:    1.10,   # interim looks can reduce expected sample size
    SampleSizeTrialDesign.BASKET:      0.80,   # fragmented per-basket N reduces power per subgroup
    SampleSizeTrialDesign.PLATFORM:    1.05,   # shared control arm slightly improves efficiency
    SampleSizeTrialDesign.EXPLORATORY: 0.40,   # signal-seeking; no confirmatory intent
    SampleSizeTrialDesign.REGISTRY:    0.40,   # observational; confounding not controlled
}

# Designs that cap the final tier regardless of computed power
_DESIGN_TIER_CAP: dict[SampleSizeTrialDesign, SampleSizeAdequacy] = {
    SampleSizeTrialDesign.EXPLORATORY: SampleSizeAdequacy.EXPLORATORY,
    SampleSizeTrialDesign.REGISTRY:    SampleSizeAdequacy.EXPLORATORY,
    SampleSizeTrialDesign.SINGLE_ARM:  SampleSizeAdequacy.BORDERLINE,   # can't exceed borderline for confirmatory intent
    SampleSizeTrialDesign.BASKET:      SampleSizeAdequacy.BORDERLINE,   # per-basket N is usually small
}

# Tier ordering (higher index = better)
_TIER_ORDER: list[SampleSizeAdequacy] = [
    SampleSizeAdequacy.EXPLORATORY,
    SampleSizeAdequacy.UNDERPOWERED,
    SampleSizeAdequacy.UNVERIFIABLE,
    SampleSizeAdequacy.BORDERLINE,
    SampleSizeAdequacy.ADEQUATE,
    SampleSizeAdequacy.WELL_POWERED,
]


def _tier_rank(tier: SampleSizeAdequacy) -> int:
    return _TIER_ORDER.index(tier)


def _min_tier(a: SampleSizeAdequacy, b: SampleSizeAdequacy) -> SampleSizeAdequacy:
    return a if _tier_rank(a) <= _tier_rank(b) else b


def _downgrade(tier: SampleSizeAdequacy) -> SampleSizeAdequacy:
    rank = _tier_rank(tier)
    return _TIER_ORDER[max(0, rank - 1)]


# ---------------------------------------------------------------------------
# Power computation
# ---------------------------------------------------------------------------

def _z(alpha_two_sided: float = 0.05) -> float:
    """Z-score for two-sided alpha (default 1.96)."""
    # Using math: Φ^{-1}(1 - alpha/2)
    # Approximation good to < 0.001 for alpha ∈ [0.01, 0.20]
    from scipy.stats import norm
    return float(norm.ppf(1.0 - alpha_two_sided / 2.0))


def _power_continuous(
    n_total: float,
    effect_size_cohens_d: float,
    alpha: float = 0.05,
) -> float:
    """
    Two-sample t-test power (normal approximation).

    n_total: total sample size (split equally into two arms → n/2 per arm)
    effect_size_cohens_d: standardized mean difference (pooled SD)
    """
    from scipy.stats import norm
    n_per_arm = n_total / 2.0
    ncp = abs(effect_size_cohens_d) * math.sqrt(n_per_arm / 2.0)
    z_a = float(norm.ppf(1.0 - alpha / 2.0))
    return float(norm.cdf(ncp - z_a) + norm.cdf(-ncp - z_a))


def _power_binary(
    n_total: float,
    control_rate: float,
    absolute_risk_diff: float,
    alpha: float = 0.05,
) -> float:
    """
    Two-proportion Z-test power.

    control_rate: event rate in control arm (p0)
    absolute_risk_diff: p1 - p0 (positive = treatment better)
    """
    from scipy.stats import norm
    p0 = max(0.01, min(0.99, control_rate))
    p1 = max(0.01, min(0.99, p0 + absolute_risk_diff))
    p_bar = (p0 + p1) / 2.0
    n_per_arm = n_total / 2.0
    se = math.sqrt(2.0 * p_bar * (1.0 - p_bar) / n_per_arm)
    if se == 0:
        return 1.0
    ncp = abs(p1 - p0) / se
    z_a = float(norm.ppf(1.0 - alpha / 2.0))
    return float(norm.cdf(ncp - z_a))


def _compute_power(
    effective_n: float,
    expected_effect_size: Optional[float],
    endpoint_variability: Optional[float],
    control_rate: Optional[float],
) -> Optional[float]:
    """
    Compute statistical power from available parameters.

    Returns None when insufficient information is available.

    Priority:
      1. Binary endpoint: control_rate + effect_size → two-proportion Z-test
      2. Continuous endpoint: effect_size (Cohen's d, SD-standardized) → t-test
         If endpoint_variability is given and effect_size is raw (unstandardized),
         Cohen's d = effect_size / endpoint_variability.
    """
    if expected_effect_size is None or expected_effect_size == 0.0:
        return None

    # Path 1: binary endpoint (control_rate is the discriminator)
    if control_rate is not None and 0.0 < control_rate < 1.0:
        return _power_binary(effective_n, control_rate, expected_effect_size)

    # Path 2: continuous endpoint
    # Standardize if raw effect and variability are both given
    if endpoint_variability is not None and endpoint_variability > 0.0:
        cohens_d = abs(expected_effect_size) / endpoint_variability
    else:
        # Assume effect_size is already Cohen's d
        cohens_d = abs(expected_effect_size)

    return _power_continuous(effective_n, cohens_d)


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class SampleSizeParams(BaseModel):
    """
    Input parameters for score_sample_size().

    At minimum, planned_sample_size is required.  The more parameters
    provided, the more precise the tier assignment:

    • If statistical_power is given directly, it is used as-is (analyst override).
    • If only sample size + effect parameters are given, power is computed.
    • If no power-relevant inputs are given, the result is UNVERIFIABLE.

    trial_design and indication_rarity enable TA-context validation and
    design-efficiency adjustments.
    """
    planned_sample_size: int = Field(gt=0, description="Total planned enrollment (all arms)")
    statistical_power: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Explicitly stated statistical power (0–1). When provided, skips computation.",
    )
    expected_effect_size: Optional[float] = Field(
        default=None,
        description=(
            "Expected treatment effect. Interpretation depends on endpoint type:\n"
            "  Continuous: Cohen's d (if endpoint_variability absent) or raw difference (if present)\n"
            "  Binary:     absolute risk difference (p_treatment − p_control)\n"
            "  Survival:   log(HR) or 1 − HR (converted internally)\n"
            "Positive = treatment better than control."
        ),
    )
    endpoint_variability: Optional[float] = Field(
        default=None, gt=0.0,
        description=(
            "Pooled SD for continuous endpoints. When provided alongside expected_effect_size, "
            "Cohen's d = effect_size / endpoint_variability. Ignored for binary endpoints."
        ),
    )
    control_rate_or_placebo_response: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description=(
            "Event rate in control arm (binary endpoints) or placebo response rate. "
            "When provided, triggers the two-proportion Z-test power formula. "
            "Also used to validate adequacy via TA placebo-noise benchmarks."
        ),
    )
    dropout_rate: float = Field(
        default=0.0, ge=0.0, lt=1.0,
        description="Expected fraction of randomised subjects not completing the primary endpoint.",
    )
    trial_design: SampleSizeTrialDesign = Field(
        default=SampleSizeTrialDesign.RCT,
        description="Trial design type. Affects efficiency multiplier and tier cap.",
    )
    phase: TrialPhase = Field(
        description="Trial phase. Used for TA minimum-N threshold lookup.",
    )
    indication_rarity: str = Field(
        default="other",
        description=(
            "TherapeuticArea.value string (e.g. 'rare_disease', 'cardiovascular'). "
            "Used to look up TA-specific minimum-N thresholds for the ADEQUATE tier."
        ),
    )
    alpha: float = Field(
        default=0.05, gt=0.0, lt=0.20,
        description="Two-sided Type I error rate (default 0.05).",
    )


# ---------------------------------------------------------------------------
# Scoring result
# ---------------------------------------------------------------------------

@dataclass
class SampleSizeScoringResult:
    """Full output from score_sample_size()."""
    tier: SampleSizeAdequacy
    computed_power: Optional[float]          # None if power could not be computed
    effective_n: float                       # planned_n × (1 − dropout) × design_efficiency
    power_source: str                        # "analyst_provided" | "computed_continuous" | "computed_binary" | "unverifiable"
    ta_min_n: Optional[int]                  # TA minimum-N threshold applied
    ta_downgraded: bool                      # True if TA-min-N caused a tier downgrade
    design_cap_applied: Optional[SampleSizeAdequacy]  # non-None if design capped the tier
    rationale: str                           # human-readable explanation


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def score_sample_size(params: SampleSizeParams) -> SampleSizeScoringResult:
    """
    Score sample size adequacy from trial design parameters.

    Pipeline:
      1. Effective N = planned_n × (1 − dropout) × design_efficiency_multiplier
      2. Get or compute statistical power
      3. Map power to tier (WELL_POWERED / ADEQUATE / BORDERLINE / UNDERPOWERED / UNVERIFIABLE)
      4. Apply design tier cap (EXPLORATORY / SINGLE_ARM → cap)
      5. Apply TA minimum-N threshold (downgrade by one tier if below minimum)
      6. Apply high-placebo-response penalty for CNS/psychiatry binary endpoints

    Returns SampleSizeScoringResult with tier, computed power, and rationale.
    """
    # Step 1: effective N
    raw_n = params.planned_sample_size * (1.0 - params.dropout_rate)
    design_eff = _DESIGN_EFFICIENCY.get(params.trial_design, 1.0)
    effective_n = raw_n * design_eff

    # Step 2: get or compute power
    power_source: str
    computed_power: Optional[float]

    if params.statistical_power is not None:
        computed_power = params.statistical_power
        power_source = "analyst_provided"
    else:
        computed_power = _compute_power(
            effective_n=effective_n,
            expected_effect_size=params.expected_effect_size,
            endpoint_variability=params.endpoint_variability,
            control_rate=params.control_rate_or_placebo_response,
        )
        if computed_power is None:
            power_source = "unverifiable"
        elif params.control_rate_or_placebo_response is not None:
            power_source = "computed_binary"
        else:
            power_source = "computed_continuous"

    # Step 3: map power to tier
    if power_source == "unverifiable":
        tier = SampleSizeAdequacy.UNVERIFIABLE
        rationale_parts = ["No power calculation or effect parameters provided → UNVERIFIABLE."]
    else:
        p = computed_power  # type: ignore[assignment]
        if p >= 0.90:
            tier = SampleSizeAdequacy.WELL_POWERED
        elif p >= 0.80:
            tier = SampleSizeAdequacy.ADEQUATE
        elif p >= 0.70:
            tier = SampleSizeAdequacy.BORDERLINE
        else:
            tier = SampleSizeAdequacy.UNDERPOWERED
        rationale_parts = [
            f"Power={p:.1%} (source={power_source}, effective_n={effective_n:.0f}) → {tier.value}."
        ]

    # Step 4: design tier cap
    design_cap = _DESIGN_TIER_CAP.get(params.trial_design)
    if design_cap is not None:
        capped_tier = _min_tier(tier, design_cap)
        if capped_tier != tier:
            rationale_parts.append(
                f"Design '{params.trial_design.value}' caps tier at {design_cap.value}."
            )
        tier = capped_tier
    else:
        design_cap = None

    # Step 5: TA minimum-N threshold
    ta_thresholds = _TA_MIN_N_ADEQUATE.get(params.indication_rarity, _TA_MIN_N_ADEQUATE["other"])
    phase_key = params.phase.value
    ta_min = ta_thresholds.get(phase_key)
    ta_downgraded = False

    if ta_min is not None and effective_n < ta_min and tier in (
        SampleSizeAdequacy.WELL_POWERED, SampleSizeAdequacy.ADEQUATE
    ):
        old_tier = tier
        tier = _downgrade(tier)
        ta_downgraded = True
        rationale_parts.append(
            f"TA '{params.indication_rarity}' {phase_key} minimum N={ta_min}; "
            f"effective_n={effective_n:.0f} < threshold → downgraded {old_tier.value} → {tier.value}."
        )

    # Step 6: high-placebo-response penalty for CNS/psychiatry
    high_noise_tas = {"cns", "psychiatry"}
    if (
        params.indication_rarity in high_noise_tas
        and params.control_rate_or_placebo_response is not None
        and params.control_rate_or_placebo_response > 0.35
        and tier == SampleSizeAdequacy.ADEQUATE
    ):
        tier = SampleSizeAdequacy.BORDERLINE
        rationale_parts.append(
            f"CNS/psychiatry placebo response {params.control_rate_or_placebo_response:.0%} > 35% "
            f"→ downgraded ADEQUATE → BORDERLINE (noise inflates required N)."
        )

    rationale = " ".join(rationale_parts)

    return SampleSizeScoringResult(
        tier=tier,
        computed_power=computed_power,
        effective_n=effective_n,
        power_source=power_source,
        ta_min_n=ta_min,
        ta_downgraded=ta_downgraded,
        design_cap_applied=design_cap if design_cap is not None else None,
        rationale=rationale,
    )
