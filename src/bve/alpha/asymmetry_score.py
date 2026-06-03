"""Composite asymmetry score formula combining model-vs-market gap, catalyst magnitude, confidence, urgency, liquidity, and crowding."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AsymmetryScoreInput(BaseModel):
    asset_id: str
    ticker: str
    # Core inputs
    model_ev_millions: float
    market_ev_millions: float       # current EV
    enterprise_value_millions: float  # same as market_ev usually; used as denominator
    # Catalyst
    expected_catalyst_return_pct: float   # probability-weighted expected return (signed)
    catalytic_magnitude: float = Field(ge=0.0, le=1.0, default=0.5)  # how large/binary is the event
    # Model confidence
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    # Time
    days_to_catalyst: Optional[int] = None
    time_urgency: float = Field(ge=0.0, le=1.0, default=0.5)   # 1 = imminent, 0 = distant
    # Execution
    liquidity_adjustment: float = Field(ge=0.0, le=1.0, default=1.0)  # 1 = liquid, 0 = illiquid
    crowding_risk: float = Field(ge=0.0, le=1.0, default=0.0)         # 0 = uncrowded, 1 = max crowded


class AsymmetryScoreResult(BaseModel):
    asset_id: str
    ticker: str
    # Sub-components
    ev_gap_pct: float                   # (model_ev - market_ev) / enterprise_value
    normalized_ev_gap: float            # clipped to [-1, 1]
    composite_score: float              # final asymmetry score (can be negative)
    # Alpha source classification
    alpha_source: str                   # "science_edge" / "regulatory_edge" / "financing_edge" /
                                        # "readthrough_edge" / "expectation_mismatch" / "mixed"
    # Confidence tier
    confidence_tier: str                # "high" / "medium" / "low"
    # Recommended instrument
    recommended_instrument: str         # "equity" / "call" / "debit_spread" / "straddle" / "put" / "none"
    # Breakdown
    ev_gap_contribution: float
    catalyst_contribution: float
    confidence_adjustment: float
    urgency_adjustment: float
    liquidity_adjustment: float
    crowding_penalty: float


def compute_asymmetry_score(inputs: AsymmetryScoreInput) -> AsymmetryScoreResult:
    """
    Asymmetry Score =
      ((model_ev - market_ev) / enterprise_value)   [ev_gap, clipped ±1]
      × catalytic_magnitude
      × confidence
      × time_urgency
      × liquidity_adjustment
      ÷ max(0.1, 1 + crowding_risk)  [crowding penalty]

    Then add expected_catalyst_return_pct × 0.3 as a catalyst contribution.

    Alpha source: largest contributing gap type.
    Confidence tier: confidence >= 0.70 → high, >= 0.50 → medium, else low.
    Instrument: composite > 0.30 → call; > 0.15 → equity; > 0 → equity;
                < -0.15 → put; else → none.
                If |composite| > 0.40 and time_urgency > 0.7 → straddle.
    """
    ev_gap = (inputs.model_ev_millions - inputs.market_ev_millions) / max(1.0, inputs.enterprise_value_millions)
    clipped_gap = max(-1.0, min(1.0, ev_gap))

    crowding_divisor = max(0.1, 1.0 + inputs.crowding_risk)

    base = (clipped_gap
            * inputs.catalytic_magnitude
            * inputs.confidence
            * inputs.time_urgency
            * inputs.liquidity_adjustment
            / crowding_divisor)

    catalyst_contribution = inputs.expected_catalyst_return_pct * 0.3
    composite = base + catalyst_contribution

    # Confidence tier
    if inputs.confidence >= 0.70:
        conf_tier = "high"
    elif inputs.confidence >= 0.50:
        conf_tier = "medium"
    else:
        conf_tier = "low"

    # Instrument
    if abs(composite) > 0.40 and inputs.time_urgency > 0.7:
        instrument = "straddle"
    elif composite > 0.30:
        instrument = "call"
    elif composite > 0.05:
        instrument = "equity"
    elif composite < -0.15:
        instrument = "put"
    else:
        instrument = "none"

    # Alpha source (simplified heuristic)
    abs_gap = abs(clipped_gap)
    if abs_gap > 0.20:
        source = "expectation_mismatch"
    elif inputs.catalytic_magnitude > 0.70:
        source = "regulatory_edge"
    elif inputs.confidence > 0.70:
        source = "science_edge"
    else:
        source = "mixed"

    return AsymmetryScoreResult(
        asset_id=inputs.asset_id, ticker=inputs.ticker,
        ev_gap_pct=round(ev_gap, 4), normalized_ev_gap=round(clipped_gap, 4),
        composite_score=round(composite, 4),
        alpha_source=source, confidence_tier=conf_tier,
        recommended_instrument=instrument,
        ev_gap_contribution=round(clipped_gap, 4),
        catalyst_contribution=round(catalyst_contribution, 4),
        confidence_adjustment=round(inputs.confidence, 4),
        urgency_adjustment=round(inputs.time_urgency, 4),
        liquidity_adjustment=round(inputs.liquidity_adjustment, 4),
        crowding_penalty=round(1.0 / crowding_divisor, 4),
    )
