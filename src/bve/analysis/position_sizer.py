"""
Position sizing engine for biotech equity investments.

Converts conviction, edge, downside, and portfolio context into a
recommended gross position size (% of portfolio). Uses a Kelly-inspired
formula with guard rails and explicit portfolio constraints.

Architecture
------------
PositionSizerInput  →  size_position()  →  PositionSizerOutput

The formula
-----------
Kelly fraction = (edge * conviction_weight) / (downside_severity)

Where:
  edge             = (model_pos - market_implied_pos)  [0..1 gap]
  conviction_weight = tier weight [0.4, 0.6, 0.8, 1.0]
  downside_severity = estimated max loss as fraction of investment

Final size is then discounted by:
  - financing_risk_discount  (reduces size for runway-challenged companies)
  - catalyst_proximity_boost (increases size near binary events)
  - portfolio_concentration  (hard cap at max_single_position_pct)

Usage
-----
from bve.analysis.position_sizer import PositionSizerInput, size_position, ConvictionTier

result = size_position(PositionSizerInput(
    model_pos=0.45,
    market_implied_pos=0.25,
    downside_pct=0.60,
    conviction=ConvictionTier.HIGH,
    catalyst_months_out=3,
    financing_runway_months=18,
))
print(result.recommended_size_pct)   # e.g. 3.8
print(result.rationale)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ConvictionTier(str, Enum):
    SPECULATIVE = "speculative"   # 0.40 weight — very early / uncertain
    LOW = "low"                   # 0.55 weight
    MEDIUM = "medium"             # 0.70 weight
    HIGH = "high"                 # 0.85 weight
    VERY_HIGH = "very_high"       # 1.00 weight — fully underwritten thesis


_CONVICTION_WEIGHTS: dict[ConvictionTier, float] = {
    ConvictionTier.SPECULATIVE: 0.40,
    ConvictionTier.LOW:         0.55,
    ConvictionTier.MEDIUM:      0.70,
    ConvictionTier.HIGH:        0.85,
    ConvictionTier.VERY_HIGH:   1.00,
}

# Portfolio constraint defaults
_DEFAULT_MAX_SINGLE_PCT = 8.0    # hard cap on any single position
_DEFAULT_MAX_SPEC_PCT   = 2.0    # cap for SPECULATIVE conviction
_DEFAULT_KELLY_FRACTION = 0.25   # fractional Kelly (25%) to limit over-sizing


# ---------------------------------------------------------------------------
# Input / Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PositionSizerInput:
    """
    Inputs required to compute a recommended position size.

    All probabilities in [0.0, 1.0]; percentages as fractions (0.60 = 60%).
    """
    model_pos: float                          # model probability of success
    market_implied_pos: float                 # back-solved market PoS
    downside_pct: float                       # estimated max loss vs current price (0.0–1.0)
    conviction: ConvictionTier = ConvictionTier.MEDIUM

    catalyst_months_out: Optional[float] = None   # months to next binary catalyst
    financing_runway_months: Optional[float] = None  # months of cash at current burn
    portfolio_current_pct: float = 0.0        # current position size (for adds)
    max_single_position_pct: float = _DEFAULT_MAX_SINGLE_PCT
    kelly_fraction: float = _DEFAULT_KELLY_FRACTION


@dataclass(frozen=True)
class PositionSizerOutput:
    """
    Recommended position size with full decomposition.

    All sizes are % of gross portfolio.
    """
    recommended_size_pct: float      # suggested new / total size
    max_size_pct: float              # hard upper bound
    add_size_pct: float              # incremental add vs current position
    raw_kelly_pct: float             # uncapped Kelly estimate (diagnostic)
    pos_edge: float                  # model_pos - market_implied_pos
    conviction_weight: float
    financing_discount: float        # [0.0, 1.0] — 1.0 = no discount
    catalyst_boost: float            # [1.0, 1.3] — 1.0 = no boost
    rationale: str
    constraints_hit: list[str]       # which caps / limits were applied


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def size_position(inputs: PositionSizerInput) -> PositionSizerOutput:
    """
    Compute a recommended gross position size.

    Parameters
    ----------
    inputs:
        PositionSizerInput with model POS, market POS, downside, conviction, etc.

    Returns
    -------
    PositionSizerOutput with recommended_size_pct and full decomposition.

    Raises
    ------
    ValueError if model_pos or market_implied_pos are outside [0.0, 1.0],
    or if downside_pct is outside (0.0, 1.0].
    """
    _validate(inputs)

    constraints_hit: list[str] = []
    rationale_parts: list[str] = []

    # ── Edge ──────────────────────────────────────────────────────────────
    pos_edge = inputs.model_pos - inputs.market_implied_pos
    rationale_parts.append(
        f"Edge: model_pos={inputs.model_pos:.2f} − implied={inputs.market_implied_pos:.2f} "
        f"= {pos_edge:+.2f}"
    )

    # ── Kelly fraction ────────────────────────────────────────────────────
    conviction_weight = _CONVICTION_WEIGHTS[inputs.conviction]
    effective_downside = max(inputs.downside_pct, 0.05)  # floor at 5%

    # Kelly = (edge × conviction) / downside_severity
    # We use a fractional Kelly (default 25%) to avoid over-sizing
    if pos_edge <= 0.0:
        # No edge or negative edge → zero position (or reduce)
        raw_kelly_pct = 0.0
        constraints_hit.append("No positive edge: model_pos <= market_implied_pos")
    else:
        raw_kelly_pct = (
            (pos_edge * conviction_weight) / effective_downside
            * inputs.kelly_fraction
            * 100.0  # convert to percentage
        )

    rationale_parts.append(
        f"Kelly ({inputs.kelly_fraction:.0%} fraction): "
        f"({pos_edge:.2f} × {conviction_weight:.2f}) / {effective_downside:.2f} "
        f"× {inputs.kelly_fraction:.0%} = {raw_kelly_pct:.1f}%"
    )

    # ── Financing risk discount ───────────────────────────────────────────
    financing_discount = _financing_discount(
        inputs.financing_runway_months, constraints_hit
    )
    if financing_discount < 1.0:
        runway_str = (
            f"{inputs.financing_runway_months:.0f}mo"
            if inputs.financing_runway_months is not None
            else "unknown"
        )
        rationale_parts.append(
            f"Financing discount: {financing_discount:.2f}× (runway={runway_str})"
        )

    # ── Catalyst proximity boost ──────────────────────────────────────────
    catalyst_boost = _catalyst_boost(inputs.catalyst_months_out, rationale_parts)

    # ── Assemble recommended size ─────────────────────────────────────────
    size = raw_kelly_pct * financing_discount * catalyst_boost

    # Conviction-based cap for speculative positions
    if inputs.conviction == ConvictionTier.SPECULATIVE:
        if size > _DEFAULT_MAX_SPEC_PCT:
            constraints_hit.append(
                f"Speculative conviction: capped at {_DEFAULT_MAX_SPEC_PCT:.1f}%"
            )
        size = min(size, _DEFAULT_MAX_SPEC_PCT)

    # Hard portfolio cap
    max_size = inputs.max_single_position_pct
    if size > max_size:
        constraints_hit.append(
            f"Max single-position cap: {max_size:.1f}%"
        )
    size = min(size, max_size)
    size = max(size, 0.0)

    # Incremental add vs current holding
    add_size = max(0.0, size - inputs.portfolio_current_pct)

    rationale = " | ".join(rationale_parts)
    if constraints_hit:
        rationale += f" | Constraints applied: {'; '.join(constraints_hit)}"

    return PositionSizerOutput(
        recommended_size_pct=round(size, 2),
        max_size_pct=round(max_size, 2),
        add_size_pct=round(add_size, 2),
        raw_kelly_pct=round(raw_kelly_pct, 2),
        pos_edge=round(pos_edge, 4),
        conviction_weight=conviction_weight,
        financing_discount=round(financing_discount, 4),
        catalyst_boost=round(catalyst_boost, 4),
        rationale=rationale,
        constraints_hit=constraints_hit,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate(inputs: PositionSizerInput) -> None:
    if not 0.0 <= inputs.model_pos <= 1.0:
        raise ValueError(f"model_pos must be in [0, 1], got {inputs.model_pos}")
    if not 0.0 <= inputs.market_implied_pos <= 1.0:
        raise ValueError(
            f"market_implied_pos must be in [0, 1], got {inputs.market_implied_pos}"
        )
    if not 0.0 < inputs.downside_pct <= 1.0:
        raise ValueError(
            f"downside_pct must be in (0, 1], got {inputs.downside_pct}"
        )
    if not 0.0 < inputs.kelly_fraction <= 1.0:
        raise ValueError(
            f"kelly_fraction must be in (0, 1], got {inputs.kelly_fraction}"
        )


def _financing_discount(
    runway_months: Optional[float],
    constraints_hit: list[str],
) -> float:
    """
    Discount multiplier based on financing runway.

    Runway (months)   Discount
    ≥ 24              1.00  (no discount)
    18–23             0.90
    12–17             0.75
    6–11              0.55
    < 6               0.30  (distress risk)
    None/unknown      0.90  (slight haircut for uncertainty)
    """
    if runway_months is None:
        return 0.90
    if runway_months >= 24:
        return 1.00
    if runway_months >= 18:
        return 0.90
    if runway_months >= 12:
        constraints_hit.append(f"Runway {runway_months:.0f}mo: financing risk discount applied")
        return 0.75
    if runway_months >= 6:
        constraints_hit.append(f"Runway {runway_months:.0f}mo: HIGH financing risk")
        return 0.55
    constraints_hit.append(f"Runway {runway_months:.0f}mo: DISTRESS — severe financing discount")
    return 0.30


def _catalyst_boost(
    months_out: Optional[float],
    rationale_parts: list[str],
) -> float:
    """
    Boost multiplier when a binary catalyst is approaching.

    Months to catalyst   Boost
    ≤ 3                  1.25
    4–6                  1.15
    7–12                 1.05
    > 12 or unknown      1.00
    """
    if months_out is None:
        return 1.00
    if months_out <= 3:
        rationale_parts.append(f"Catalyst boost ×1.25 ({months_out:.0f}mo out)")
        return 1.25
    if months_out <= 6:
        rationale_parts.append(f"Catalyst boost ×1.15 ({months_out:.0f}mo out)")
        return 1.15
    if months_out <= 12:
        rationale_parts.append(f"Catalyst boost ×1.05 ({months_out:.0f}mo out)")
        return 1.05
    return 1.00
