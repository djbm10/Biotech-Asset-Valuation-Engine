"""Block 11 — Sprint 52A: Management Receptivity Gate.

Answers: "Would this management team engage with, or block, a transaction?"

Distinct from ManagementGate (which is a downstream structural gate on deal
form) — ManagementReceptivity is a sell-side willingness signal that modifies
acquisition probability caps and partner-realism scores before Layer 5
calibration.

Design rules
------------
- UNKNOWN → no cap, no boost; confidence note only. Never penalise UNKNOWN.
- ENTRENCHED + no activist + no strategic review → cap acquisition probability.
- OPEN + prior partnership history → partner realism boost.
- RESISTANT/ENTRENCHED always sets founder_entrenchment flag when
  founder_on_board is True.
- Caps are advisory: they feed into Layer 3 process_closing as an additional
  cap; they do NOT hard-zero the score.
- Boosts are additive and capped at +0.15 total.
- No double-counting with ManagementGate: receptivity is about willingness to
  transact; ManagementGate is about structural fit and diligence routing.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ManagementReceptivity(str, Enum):
    """Sell-side willingness to engage with an M&A or partnership process."""
    OPEN       = "open"
    NEUTRAL    = "neutral"
    RESISTANT  = "resistant"
    ENTRENCHED = "entrenched"
    UNKNOWN    = "unknown"


# ---------------------------------------------------------------------------
# Cap / boost constants
# ---------------------------------------------------------------------------

# Acquisition probability caps by receptivity tier
_ACQUISITION_CAPS: dict[ManagementReceptivity, Optional[float]] = {
    ManagementReceptivity.OPEN:       None,   # no cap
    ManagementReceptivity.NEUTRAL:    None,   # no cap
    ManagementReceptivity.RESISTANT:  0.50,
    ManagementReceptivity.ENTRENCHED: 0.25,
    ManagementReceptivity.UNKNOWN:    None,   # no cap (uncertainty ≠ obstruction)
}

# When ENTRENCHED but activist or strategic review present, relax cap
_ENTRENCHED_WITH_CATALYST_CAP: float = 0.55

# Partner realism boost for OPEN + prior partnership history
_OPEN_PARTNERSHIP_BOOST: float = 0.10

# NEUTRAL + prior partnership history
_NEUTRAL_PARTNERSHIP_BOOST: float = 0.05


# ---------------------------------------------------------------------------
# Input / output containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReceptivityContext:
    """Inputs that determine a receptivity gate result.

    Parameters
    ----------
    receptivity:
        Analyst-assessed receptivity tier.
    has_activist_pressure:
        True if a known activist investor holds ≥ 3 % of shares or has
        publicly demanded strategic alternatives.
    has_strategic_review:
        True if the board has publicly announced a strategic review /
        sale process.
    has_prior_partnership_history:
        True if the company has previously signed a co-development,
        licensing, or option-to-acquire agreement with any large acquirer.
    founder_on_board:
        True if the original founder(s) remain on the board or hold
        C-suite positions (amplifies RESISTANT/ENTRENCHED flags).
    data_confidence:
        0.0–1.0 confidence in the receptivity assessment.
        UNKNOWN receptivity always caps this at 0.40.
    """
    receptivity: ManagementReceptivity = ManagementReceptivity.UNKNOWN
    has_activist_pressure: bool = False
    has_strategic_review: bool = False
    has_prior_partnership_history: bool = False
    founder_on_board: bool = False
    data_confidence: float = 0.60


@dataclass(frozen=True)
class ReceptivityGateResult:
    """Output of the receptivity gate computation.

    Parameters
    ----------
    receptivity:
        Pass-through of the input receptivity tier.
    acquisition_probability_cap:
        Advisory cap on acquisition probability (None = no cap).
        Fed into Layer 3 process_closing.
    partner_realism_boost:
        Additive boost to partner/license realism score.
        0.0 = no boost.
    rationale:
        Plain-English explanation of the gate outcome.
    flags:
        Named value-destruction or value-preservation flags that should
        propagate into BuyerTargetThesis and DecisionReport.
        e.g. ["founder_entrenchment", "value_preserving_management"]
    confidence:
        Confidence in this gate result (degrades for UNKNOWN receptivity).
    cap_catalyst_present:
        True when ENTRENCHED but activist/strategic-review relaxes the cap.
    """
    receptivity: ManagementReceptivity
    acquisition_probability_cap: Optional[float]
    partner_realism_boost: float
    rationale: str
    flags: list[str]
    confidence: float
    cap_catalyst_present: bool = False


# ---------------------------------------------------------------------------
# Gate computation
# ---------------------------------------------------------------------------

def apply_receptivity_gate(ctx: ReceptivityContext) -> ReceptivityGateResult:
    """Compute the receptivity gate from a ReceptivityContext.

    Rules (in priority order)
    --------------------------
    1. UNKNOWN → no cap, no boost; confidence capped at 0.40.
    2. ENTRENCHED:
       a. No activist + no strategic review → cap = 0.25, founder_entrenchment
          flag if founder_on_board.
       b. Activist OR strategic review present → cap = 0.55 (relaxed),
          cap_catalyst_present = True.
    3. RESISTANT:
       a. cap = 0.50.
       b. founder_entrenchment flag if founder_on_board.
    4. OPEN + prior partnership history → partner_realism_boost = +0.10.
       value_preserving_management flag added.
    5. NEUTRAL + prior partnership history → partner_realism_boost = +0.05.
    6. OPEN without partnership history → no cap, no boost; no flag.
    7. NEUTRAL without partnership history → no cap, no boost.

    Returns
    -------
    ReceptivityGateResult
    """
    receptivity = ctx.receptivity
    flags: list[str] = []
    cap: Optional[float] = None
    boost: float = 0.0
    cap_catalyst_present = False
    confidence = max(0.0, min(1.0, float(ctx.data_confidence)))

    if receptivity == ManagementReceptivity.UNKNOWN:
        confidence = min(confidence, 0.40)
        rationale = (
            "Management receptivity unknown — insufficient public data. "
            "No cap or boost applied; treat all transaction scenarios with "
            "equal uncertainty."
        )
        return ReceptivityGateResult(
            receptivity=receptivity,
            acquisition_probability_cap=None,
            partner_realism_boost=0.0,
            rationale=rationale,
            flags=[],
            confidence=confidence,
            cap_catalyst_present=False,
        )

    if receptivity == ManagementReceptivity.ENTRENCHED:
        has_catalyst = ctx.has_activist_pressure or ctx.has_strategic_review
        if has_catalyst:
            cap = _ENTRENCHED_WITH_CATALYST_CAP
            cap_catalyst_present = True
            rationale = (
                "Management is ENTRENCHED but activist pressure or a strategic "
                "review is present — cap relaxed to 0.55. Deal remains difficult "
                "but external catalyst materially increases probability."
            )
        else:
            cap = _ACQUISITION_CAPS[ManagementReceptivity.ENTRENCHED]
            rationale = (
                "Management is ENTRENCHED with no activist pressure or strategic "
                "review. Full acquisition probability capped at 0.25. A partnership "
                "or licensing structure may be feasible; full acquisition is unlikely "
                "without an external catalyst."
            )
            if ctx.founder_on_board:
                flags.append("founder_entrenchment")

    elif receptivity == ManagementReceptivity.RESISTANT:
        cap = _ACQUISITION_CAPS[ManagementReceptivity.RESISTANT]
        rationale = (
            "Management is RESISTANT to M&A. Acquisition probability capped at 0.50. "
            "Partnership or licensing approaches may be more viable."
        )
        if ctx.founder_on_board:
            flags.append("founder_entrenchment")

    elif receptivity == ManagementReceptivity.OPEN:
        if ctx.has_prior_partnership_history:
            boost = _OPEN_PARTNERSHIP_BOOST
            flags.append("value_preserving_management")
            rationale = (
                "Management is OPEN to transactions and has prior partnership history. "
                f"Partner/license realism boosted by +{boost:.0%}."
            )
        else:
            rationale = (
                "Management is OPEN to transactions. No prior partnership history "
                "on record; no boost applied."
            )

    else:  # NEUTRAL
        if ctx.has_prior_partnership_history:
            boost = _NEUTRAL_PARTNERSHIP_BOOST
            rationale = (
                "Management is NEUTRAL on transactions but has prior partnership "
                f"history. Partner/license realism boosted by +{boost:.0%}."
            )
        else:
            rationale = (
                "Management is NEUTRAL on transactions. No prior partnership history; "
                "no cap or boost applied."
            )

    return ReceptivityGateResult(
        receptivity=receptivity,
        acquisition_probability_cap=cap,
        partner_realism_boost=boost,
        rationale=rationale,
        flags=flags,
        confidence=confidence,
        cap_catalyst_present=cap_catalyst_present,
    )


# ---------------------------------------------------------------------------
# Layer 3 integration helper
# ---------------------------------------------------------------------------

def receptivity_to_process_closing_cap(
    gate: ReceptivityGateResult,
) -> Optional[float]:
    """Return the acquisition probability cap as a Layer 3 process_closing cap.

    Returns None when no cap applies (OPEN, NEUTRAL, UNKNOWN).
    This is the value to pass as an additional cap into Layer 3's
    process_closing component or directly into Layer 5 calibration.
    """
    return gate.acquisition_probability_cap
