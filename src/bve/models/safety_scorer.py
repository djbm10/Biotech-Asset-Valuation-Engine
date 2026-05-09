"""
Safety Profile Scorer.

Implements the scoring rule:

    safety_adjustment = score_safety(SafetyParams) -> SafetyScoringResult

Pipeline:
  1. Base log-odds from SafetyProfile category
  2. Apply additive modifiers (reversible, monitorable, comparable_to_control,
     high_discontinuation_rate, treatment_related_death_signal,
     organ_toxicity_signal, class_known_risk)
  3. Clamp total to [−0.90, +0.15]

Design principle: do NOT score by AE grade alone.  A reversible, monitorable
Grade 3 lab abnormality is very different from irreversible organ toxicity or
mechanism-linked deaths at the same grade.

Sources:
  - FDA Guidance: Drug-Induced Liver Injury (2009, 2023)
  - ICH E2A: Clinical Safety Data Management (1994)
  - NCI CTCAE v5.0 grading conventions
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, Field

from bve.models.pos_model import SafetyProfile, _SAFETY_LOGODDS


# ---------------------------------------------------------------------------
# Modifier constants
# ---------------------------------------------------------------------------

_MOD_REVERSIBLE: float           = +0.05
_MOD_MONITORABLE: float          = +0.05
_MOD_COMPARABLE_TO_CONTROL: float = +0.05
_MOD_HIGH_DISCONTINUATION: float = -0.10
_MOD_TREATMENT_RELATED_DEATH: float = -0.20
_MOD_ORGAN_TOXICITY: float       = -0.15
_MOD_CLASS_KNOWN_RISK: float     = -0.15

# Threshold above which discontinuation_rate is considered "high"
_HIGH_DISCONTINUATION_RATE_THRESHOLD: float = 0.15  # 15%

_CAP_MIN: float = -0.90
_CAP_MAX: float = +0.15


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class SafetyParams(BaseModel):
    """
    Input parameters for score_safety().

    category is required.  All other fields are optional; when provided they
    enable modifier adjustments that can shift the base category score.

    Modifier rules:
      reversible=True             → +0.05  (AEs resolve on discontinuation)
      monitorable=True            → +0.05  (lab monitoring protocol exists)
      comparable_to_control=True  → +0.05  (AE rate not notably higher than control)
      discontinuation_rate > 15%  → −0.10  (high dropout signals durability risk)
      treatment_related_deaths > 0 → −0.20 (death signal is a hard regulatory flag)
      organ_toxicity_signal=True  → −0.15  (hepatotox, cardiotox, nephrotox, etc.)
      class_known_risk=True       → −0.15  (mechanism-shared risk; hard to fix)
    """
    category: SafetyProfile = Field(
        description="Primary safety tier. Drives the base log-odds adjustment.",
    )
    grade_3_plus_rate: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Fraction of subjects with Grade 3+ AEs (0–1). Informational; does not trigger a modifier directly.",
    )
    serious_adverse_event_rate: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Fraction of subjects with SAEs (0–1). Informational.",
    )
    discontinuation_rate: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description=(
            "Fraction of randomised subjects who discontinued due to AEs. "
            "Triggers the high_discontinuation_rate modifier when > 15%."
        ),
    )
    dose_limiting_toxicity_rate: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Fraction of subjects with a DLT in Phase 1 dose-escalation. Informational.",
    )
    treatment_related_deaths: int = Field(
        default=0, ge=0,
        description=(
            "Number of treatment-related deaths observed. Any value > 0 triggers "
            "the treatment_related_death_signal modifier (−0.20)."
        ),
    )
    organ_toxicity_signal: bool = Field(
        default=False,
        description=(
            "True when there is a clinically meaningful signal of organ toxicity "
            "(hepatotoxicity, cardiotoxicity, nephrotoxicity, neurotoxicity, etc.)."
        ),
    )
    reversible: bool = Field(
        default=True,
        description="True when AEs typically resolve on dose reduction or discontinuation.",
    )
    monitorable: bool = Field(
        default=True,
        description="True when AEs can be detected early via standard lab monitoring.",
    )
    comparable_to_control: bool = Field(
        default=True,
        description="True when the AE rate is not meaningfully higher than the control arm.",
    )
    class_known_risk: bool = Field(
        default=False,
        description=(
            "True when the safety risk is a class effect shared across the mechanism, "
            "making it structurally difficult to mitigate through drug design."
        ),
    )
    notes: str = Field(default="", description="Free-text safety notes.")


# ---------------------------------------------------------------------------
# Scoring result
# ---------------------------------------------------------------------------

@dataclass
class SafetyScoringResult:
    """Full output from score_safety()."""
    adjustment: float                  # final log-odds adjustment (after cap)
    base_adjustment: float             # from category alone
    modifier_delta: float              # sum of all modifier contributions
    modifiers_applied: list[str]       # modifier names that fired
    capped: bool                       # True if cap was hit
    rationale: str                     # human-readable explanation


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def score_safety(params: SafetyParams) -> SafetyScoringResult:
    """
    Compute the safety log-odds adjustment from SafetyParams.

    Pipeline:
      1. Base = _SAFETY_LOGODDS[category]
      2. Positive modifiers: reversible, monitorable, comparable_to_control
      3. Negative modifiers: high_discontinuation_rate, treatment_related_death_signal,
         organ_toxicity_signal, class_known_risk
      4. Clamp total to [−0.90, +0.15]

    Returns SafetyScoringResult with adjustment, base, delta, modifiers, cap flag,
    and rationale string.
    """
    base = _SAFETY_LOGODDS[params.category]
    delta = 0.0
    modifiers: list[str] = []
    rationale_parts: list[str] = [
        f"category={params.category.value} → base={base:+.2f}."
    ]

    # Positive modifiers
    if params.reversible:
        delta += _MOD_REVERSIBLE
        modifiers.append("reversible")
    if params.monitorable:
        delta += _MOD_MONITORABLE
        modifiers.append("monitorable")
    if params.comparable_to_control:
        delta += _MOD_COMPARABLE_TO_CONTROL
        modifiers.append("comparable_to_control")

    # Negative modifiers
    if (
        params.discontinuation_rate is not None
        and params.discontinuation_rate > _HIGH_DISCONTINUATION_RATE_THRESHOLD
    ):
        delta += _MOD_HIGH_DISCONTINUATION
        modifiers.append("high_discontinuation_rate")
        rationale_parts.append(
            f"Discontinuation rate {params.discontinuation_rate:.0%} > {_HIGH_DISCONTINUATION_RATE_THRESHOLD:.0%} threshold."
        )

    if params.treatment_related_deaths > 0:
        delta += _MOD_TREATMENT_RELATED_DEATH
        modifiers.append("treatment_related_death_signal")
        rationale_parts.append(
            f"Treatment-related deaths={params.treatment_related_deaths} → hard regulatory flag."
        )

    if params.organ_toxicity_signal:
        delta += _MOD_ORGAN_TOXICITY
        modifiers.append("organ_toxicity_signal")
        rationale_parts.append("Organ toxicity signal present.")

    if params.class_known_risk:
        delta += _MOD_CLASS_KNOWN_RISK
        modifiers.append("class_known_risk")
        rationale_parts.append("Class-level mechanism-linked risk; structurally difficult to mitigate.")

    # Cap
    raw_total = base + delta
    capped_total = max(_CAP_MIN, min(_CAP_MAX, raw_total))
    capped = capped_total != raw_total

    if modifiers:
        rationale_parts.append(
            f"Modifiers: [{', '.join(modifiers)}] → delta={delta:+.2f}."
        )
    if capped:
        rationale_parts.append(
            f"Raw total={raw_total:+.2f} capped to {capped_total:+.2f}."
        )

    return SafetyScoringResult(
        adjustment=capped_total,
        base_adjustment=base,
        modifier_delta=delta,
        modifiers_applied=modifiers,
        capped=capped,
        rationale=" ".join(rationale_parts),
    )
