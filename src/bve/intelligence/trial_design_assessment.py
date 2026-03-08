"""
Wave 2C — Trial Design Assessment.

Computes a design quality multiplier and statistical power estimate from a
StructuredSignal.  Does not modify the signal; returns a separate
TrialDesignAssessment record.

Tier priority (highest to lowest — trial design strength > endpoint type):
  1. SINGLE_ARM  ×0.80  single-arm or no comparator
  2. OS_RCT      ×1.10  randomized trial with overall survival endpoint
  3. PFS         ×1.00  progression-free survival endpoint
  4. SURROGATE   ×0.85  surrogate / biomarker endpoint
  5. STANDARD    ×1.00  everything else

Statistical power uses a two-sided z-test:
  z_alpha   = norm.ppf(1 - alpha / 2)
  n_per_arm = n_patients / 2
  power     = norm.cdf(|effect_size| * sqrt(n_per_arm) - z_alpha)

Power is clamped to [0.0, 1.0] to handle numerical edge cases.
Power is not computed when any of n_patients, estimated_effect_size, or
alpha_level is missing or non-positive.

Alert rule: power < LOW_POWER_THRESHOLD (0.70) → HIGH severity alert.
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field
from scipy.stats import norm

from bve.alerts.alert_model import Alert, AlertSeverity, AlertTrigger
from bve.intelligence.schemas.signals import StructuredSignal

LOW_POWER_THRESHOLD = 0.70


class DesignQualityTier(str, Enum):
    SINGLE_ARM = "single_arm"  # ×0.80
    OS_RCT     = "os_rct"      # ×1.10
    PFS        = "pfs"         # ×1.00
    SURROGATE  = "surrogate"   # ×0.85
    STANDARD   = "standard"    # ×1.00


TIER_MULTIPLIERS: dict[DesignQualityTier, float] = {
    DesignQualityTier.SINGLE_ARM: 0.80,
    DesignQualityTier.OS_RCT:     1.10,
    DesignQualityTier.PFS:        1.00,
    DesignQualityTier.SURROGATE:  0.85,
    DesignQualityTier.STANDARD:   1.00,
}


class TrialDesignAssessment(BaseModel):
    """Result of assessing a single StructuredSignal's trial design quality."""

    # Identity
    signal_id: str
    asset_id: str

    # Design quality
    design_quality_tier: DesignQualityTier
    design_quality_multiplier: float

    # Statistical power
    power_computed: bool
    statistical_power: Optional[float] = None
    power_inputs: dict[str, Any] = Field(default_factory=dict)
    low_power_flag: bool = False  # True when statistical_power < LOW_POWER_THRESHOLD


def _is_single_arm(signal: StructuredSignal) -> bool:
    """Return True when the trial is single-arm or has no comparator."""
    if signal.randomization == "single_arm":
        return True
    if signal.comparator_type == "none":
        return True
    return False


def _classify_tier(signal: StructuredSignal) -> DesignQualityTier:
    """
    Classify design quality tier.

    Priority (highest design-strength concern first):
      1. SINGLE_ARM — overrides endpoint type
      2. OS_RCT     — randomized + OS
      3. PFS        — PFS endpoint
      4. SURROGATE  — surrogate endpoint
      5. STANDARD   — fallback
    """
    if _is_single_arm(signal):
        return DesignQualityTier.SINGLE_ARM

    if signal.randomization == "randomized" and signal.endpoint_type == "os":
        return DesignQualityTier.OS_RCT

    if signal.endpoint_type == "pfs":
        return DesignQualityTier.PFS

    if signal.endpoint_type == "surrogate":
        return DesignQualityTier.SURROGATE

    return DesignQualityTier.STANDARD


def _compute_power(
    n_patients: int,
    effect_size: float,
    alpha: float,
) -> float:
    """
    Two-sided z-test power estimate, clamped to [0.0, 1.0].

    z_alpha   = norm.ppf(1 - alpha / 2)
    n_per_arm = n_patients / 2
    power     = norm.cdf(|effect_size| * sqrt(n_per_arm) - z_alpha)
    """
    z_alpha = norm.ppf(1.0 - alpha / 2.0)
    n_per_arm = n_patients / 2.0
    raw_power = norm.cdf(abs(effect_size) * math.sqrt(n_per_arm) - z_alpha)
    return max(0.0, min(1.0, float(raw_power)))


def assess_trial_design(signal: StructuredSignal) -> TrialDesignAssessment:
    """
    Assess trial design quality and statistical power from a StructuredSignal.

    Parameters
    ----------
    signal:
        A StructuredSignal produced by the extraction pipeline.

    Returns
    -------
    TrialDesignAssessment
        Quality tier, multiplier, power estimate, and low-power flag.
    """
    tier = _classify_tier(signal)
    multiplier = TIER_MULTIPLIERS[tier]

    # Statistical power — requires all three inputs to be present and valid
    n = signal.n_patients
    effect = signal.estimated_effect_size
    alpha = signal.alpha_level

    can_compute = (
        n is not None and n > 0
        and effect is not None
        and alpha is not None and 0.0 < alpha < 1.0
    )

    if can_compute:
        power = _compute_power(n, effect, alpha)
        return TrialDesignAssessment(
            signal_id=signal.id,
            asset_id=signal.asset_id,
            design_quality_tier=tier,
            design_quality_multiplier=multiplier,
            power_computed=True,
            statistical_power=power,
            power_inputs={
                "n_patients": n,
                "effect_size": effect,
                "alpha": alpha,
            },
            low_power_flag=power < LOW_POWER_THRESHOLD,
        )

    return TrialDesignAssessment(
        signal_id=signal.id,
        asset_id=signal.asset_id,
        design_quality_tier=tier,
        design_quality_multiplier=multiplier,
        power_computed=False,
        statistical_power=None,
        power_inputs={},
        low_power_flag=False,
    )


def make_low_power_alert(
    assessment: TrialDesignAssessment,
    company_id: str,
) -> Alert:
    """
    Create a HIGH-severity alert for a low-power trial design.

    Parameters
    ----------
    assessment:
        A TrialDesignAssessment with ``low_power_flag=True``.
    company_id:
        Company identifier for the alert.

    Raises
    ------
    ValueError
        If ``assessment.low_power_flag`` is False — only fire when power is low.
    """
    if not assessment.low_power_flag:
        raise ValueError(
            "make_low_power_alert called on assessment with low_power_flag=False"
        )

    power_str = (
        f"{assessment.statistical_power:.2f}"
        if assessment.statistical_power is not None
        else "unknown"
    )
    message = (
        f"Estimated statistical power {power_str} below threshold {LOW_POWER_THRESHOLD:.2f}"
    )

    return Alert(
        severity=AlertSeverity.HIGH,
        trigger=AlertTrigger.LOW_STATISTICAL_POWER,
        asset_id=assessment.asset_id,
        company_id=company_id,
        message=message,
        detail={
            "signal_id": assessment.signal_id,
            "design_quality_tier": assessment.design_quality_tier.value,
            "statistical_power": assessment.statistical_power,
            "power_inputs": assessment.power_inputs,
            "threshold": LOW_POWER_THRESHOLD,
        },
    )
