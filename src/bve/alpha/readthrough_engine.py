"""Assess the readthrough from a competitor event to a focal asset."""
from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field


class CompetitorEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    competitor_name: str
    competitor_asset: str
    event_type: str     # "phase3_success" / "phase3_failure" / "fda_approval" / "crl" /
                        # "discontinuation" / "safety_hold" / "partnership" / "label_expansion"
    event_date: date
    indication: str
    description: str
    magnitude: str = "moderate"    # "large" / "moderate" / "small"


class ReadthroughAssessment(BaseModel):
    focal_asset_id: str
    focal_ticker: str
    competitor_event: CompetitorEvent
    # Direction and magnitude
    readthrough_direction: str          # "positive" / "negative" / "ambiguous" / "class_expanding"
    readthrough_strength: str           # "strong" / "moderate" / "weak" / "negligible"
    # Quantified deltas (fractions)
    pos_delta: float = 0.0             # change to PoS estimate
    peak_sales_delta_pct: float = 0.0  # % change to peak sales estimate
    market_expansion_factor: float = 1.0  # >1 = market grew due to competitor success
    strategic_value_delta: str = "neutral"  # "increased" / "decreased" / "neutral"
    # Investment implication
    investment_implication: str         # one sentence
    urgency: str = "low"               # "high" / "medium" / "low" — triggers recompute
    # Rationale
    rationale: str
    key_analogies: list[str] = Field(default_factory=list)


# Readthrough rules: (event_type, direction_logic)
_READTHROUGH_RULES: dict[str, tuple[str, float, float]] = {
    # event_type: (direction, pos_delta, peak_sales_delta_pct)
    "phase3_success":    ("positive",        +0.05, +0.05),
    "fda_approval":      ("positive",        +0.05, +0.10),
    "label_expansion":   ("class_expanding", +0.03, +0.15),
    "partnership":       ("positive",        +0.03, +0.05),
    "phase3_failure":    ("negative",        -0.08, -0.10),
    "crl":               ("negative",        -0.05, -0.05),
    "discontinuation":   ("positive",        +0.05, +0.10),  # one less competitor
    "safety_hold":       ("negative",        -0.10, -0.05),  # class safety signal
}


class ReadthroughEngine:
    """
    Assess readthrough from competitor events to a focal asset.

    Rules:
    - Competitor success in same indication → positive readthrough (validates class)
    - Competitor failure → negative (questions class viability)
    - Competitor discontinuation → positive (removes competitive pressure)
    - Class safety signal → negative class-wide PoS penalty
    - Label expansion → class-expanding (grows TAM)
    - Magnitude multipliers: large=1.5×, moderate=1.0×, small=0.5×
    """

    def assess(
        self,
        focal_asset_id: str,
        focal_ticker: str,
        event: CompetitorEvent,
        *,
        same_mechanism: bool = True,
        same_indication: bool = True,
    ) -> ReadthroughAssessment:
        direction, pos_d, sales_d = _READTHROUGH_RULES.get(
            event.event_type, ("ambiguous", 0.0, 0.0)
        )
        magnitude_mult = {"large": 1.5, "moderate": 1.0, "small": 0.5}.get(event.magnitude, 1.0)
        # Scale down if not same mechanism
        mech_mult = 1.0 if same_mechanism else 0.4
        ind_mult = 1.0 if same_indication else 0.3

        pos_delta = round(pos_d * magnitude_mult * mech_mult * ind_mult, 4)
        sales_delta = round(sales_d * magnitude_mult * ind_mult, 4)
        mkt_exp = 1.0 + max(0.0, sales_delta) if direction == "class_expanding" else 1.0

        strength = "negligible"
        if abs(pos_delta) >= 0.08:
            strength = "strong"
        elif abs(pos_delta) >= 0.04:
            strength = "moderate"
        elif abs(pos_delta) >= 0.01:
            strength = "weak"

        urgency = "high" if strength in ("strong", "moderate") else "low"

        strat = "increased" if pos_delta > 0 else "decreased" if pos_delta < 0 else "neutral"

        implications = {
            "positive": f"Competitor success validates mechanism; {focal_ticker} PoS should increase.",
            "negative": f"Competitor failure questions class viability; review {focal_ticker} thesis.",
            "class_expanding": f"Label expansion grows TAM; {focal_ticker} peak sales estimate may increase.",
            "ambiguous": f"Readthrough unclear; monitor {focal_ticker} for market reaction.",
        }

        return ReadthroughAssessment(
            focal_asset_id=focal_asset_id, focal_ticker=focal_ticker,
            competitor_event=event,
            readthrough_direction=direction, readthrough_strength=strength,
            pos_delta=pos_delta, peak_sales_delta_pct=sales_delta,
            market_expansion_factor=round(mkt_exp, 3),
            strategic_value_delta=strat,
            investment_implication=implications.get(direction, "Monitor closely."),
            urgency=urgency,
            rationale=(f"{event.event_type.replace('_', ' ').title()} by {event.competitor_name} "
                       f"({event.magnitude} magnitude). Same mechanism: {same_mechanism}. "
                       f"PoS delta: {pos_delta:+.1%}. Peak sales delta: {sales_delta:+.1%}."),
            key_analogies=[],
        )
