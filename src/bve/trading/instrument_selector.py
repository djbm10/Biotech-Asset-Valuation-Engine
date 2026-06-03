"""Select the best trading instrument given asymmetry score and catalyst context."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Instrument(str, Enum):
    EQUITY = "equity"
    CALL = "call"
    PUT = "put"
    STRADDLE = "straddle"
    STRANGLE = "strangle"
    NO_TRADE = "no_trade"


class InstrumentSelectionInput(BaseModel):
    asset_id: str
    asymmetry_score: float  # composite from alpha/asymmetry_score.py (-1 to +1)
    ev_gap_direction: str  # "underpriced" | "overpriced" | "fairly_priced"
    days_to_catalyst: Optional[int] = None
    implied_move_pct: Optional[float] = None  # from implied_move.py
    model_expected_move_pct: Optional[float] = None  # from scenario_tree EV
    iv_richness: Optional[str] = None  # "rich" | "fair" | "cheap"
    financing_risk_tier: Optional[str] = None  # "low" | "medium" | "high" | "distress"


class InstrumentSelectionResult(BaseModel):
    asset_id: str
    instrument: Instrument
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class InstrumentSelector:
    """
    Rule-based instrument selector. No external dependencies.

    Selection rules (apply in priority order):
    1. financing_risk_tier == "distress" → NO_TRADE (financing overhang kills options)
    2. ev_gap_direction == "fairly_priced" and abs(asymmetry_score) < 0.10 → NO_TRADE
    3. days_to_catalyst is not None and days_to_catalyst <= 30:
       - iv_richness == "rich" → avoid buying options (EQUITY if bullish, PUT if bearish)
       - iv_richness == "cheap" or None:
         - abs(asymmetry_score) >= 0.40 → STRADDLE (high uncertainty both sides)
         - asymmetry_score > 0.20 → CALL
         - asymmetry_score < -0.20 → PUT
         - else → EQUITY
    4. No near-term catalyst:
       - asymmetry_score > 0.15 → EQUITY (cheap to own, hold through)
       - asymmetry_score < -0.15 → PUT (long-dated hedge)
       - else → NO_TRADE
    5. model_expected_move_pct vs implied_move_pct:
       - if model > implied * 1.3 and bullish → CALL (model thinks move is bigger than priced)
       - if model > implied * 1.3 and bearish → PUT
    Note: These rules are checked sequentially; first match wins.
    """

    def select(self, inp: InstrumentSelectionInput) -> InstrumentSelectionResult:
        """Select the best instrument for a given asset and catalyst context."""
        notes: list[str] = []

        # Rule 1: distress financing risk → no trade
        if inp.financing_risk_tier == "distress":
            return InstrumentSelectionResult(
                asset_id=inp.asset_id,
                instrument=Instrument.NO_TRADE,
                rationale="Financing overhang (distress tier) makes options too risky; no trade recommended.",
                confidence=0.90,
                notes=["financing_risk_tier=distress overrides all other signals"],
            )

        # Rule 2: fairly priced and low asymmetry → no trade
        if inp.ev_gap_direction == "fairly_priced" and abs(inp.asymmetry_score) < 0.10:
            return InstrumentSelectionResult(
                asset_id=inp.asset_id,
                instrument=Instrument.NO_TRADE,
                rationale="Asset is fairly priced with negligible asymmetry score; insufficient edge to trade.",
                confidence=0.80,
                notes=["ev_gap=fairly_priced and |asymmetry_score| < 0.10"],
            )

        # Rule 3: near-term catalyst (≤30 days)
        if inp.days_to_catalyst is not None and inp.days_to_catalyst <= 30:
            if inp.iv_richness == "rich":
                # Avoid buying options into rich IV
                if inp.asymmetry_score > 0:
                    notes.append("IV is rich; using equity to avoid overpaying for options premium")
                    return InstrumentSelectionResult(
                        asset_id=inp.asset_id,
                        instrument=Instrument.EQUITY,
                        rationale="Near-term catalyst bullish with rich IV; equity preferred over options.",
                        confidence=0.75,
                        notes=notes,
                    )
                else:
                    notes.append("IV is rich; using put to hedge despite premium cost")
                    return InstrumentSelectionResult(
                        asset_id=inp.asset_id,
                        instrument=Instrument.PUT,
                        rationale="Near-term catalyst bearish with rich IV; put for directional hedge.",
                        confidence=0.70,
                        notes=notes,
                    )
            else:
                # iv_richness is "cheap" or None — options are not overpriced
                abs_score = abs(inp.asymmetry_score)
                if abs_score >= 0.40:
                    notes.append("High |asymmetry_score| with near-term catalyst; straddle captures binary outcome")
                    return InstrumentSelectionResult(
                        asset_id=inp.asset_id,
                        instrument=Instrument.STRADDLE,
                        rationale="High uncertainty near catalyst; straddle captures binary move in either direction.",
                        confidence=0.80,
                        notes=notes,
                    )
                elif inp.asymmetry_score > 0.20:
                    notes.append("Bullish asymmetry with affordable options near catalyst")
                    return InstrumentSelectionResult(
                        asset_id=inp.asset_id,
                        instrument=Instrument.CALL,
                        rationale="Bullish asymmetry with near-term catalyst and cheap/fair IV; call preferred.",
                        confidence=0.78,
                        notes=notes,
                    )
                elif inp.asymmetry_score < -0.20:
                    notes.append("Bearish asymmetry with affordable options near catalyst")
                    return InstrumentSelectionResult(
                        asset_id=inp.asset_id,
                        instrument=Instrument.PUT,
                        rationale="Bearish asymmetry with near-term catalyst and cheap/fair IV; put preferred.",
                        confidence=0.78,
                        notes=notes,
                    )
                else:
                    notes.append("Near-term catalyst but weak directional signal; equity for modest exposure")
                    return InstrumentSelectionResult(
                        asset_id=inp.asset_id,
                        instrument=Instrument.EQUITY,
                        rationale="Near-term catalyst with moderate asymmetry and non-rich IV; equity for participation.",
                        confidence=0.60,
                        notes=notes,
                    )

        # Rule 4: No near-term catalyst
        if inp.days_to_catalyst is None or inp.days_to_catalyst > 30:
            # Check model vs implied move before directional rules (Rule 5 integrated here for no-catalyst case)
            if (
                inp.model_expected_move_pct is not None
                and inp.implied_move_pct is not None
                and inp.implied_move_pct > 0
                and inp.model_expected_move_pct > inp.implied_move_pct * 1.3
            ):
                if inp.asymmetry_score >= 0:
                    notes.append("Model expects larger move than implied; call to capture upside mispricing")
                    return InstrumentSelectionResult(
                        asset_id=inp.asset_id,
                        instrument=Instrument.CALL,
                        rationale="Model expected move exceeds implied move by >30%; call offers levered upside.",
                        confidence=0.72,
                        notes=notes,
                    )
                else:
                    notes.append("Model expects larger move than implied; put to capture downside mispricing")
                    return InstrumentSelectionResult(
                        asset_id=inp.asset_id,
                        instrument=Instrument.PUT,
                        rationale="Model expected move exceeds implied move by >30%; put offers levered downside.",
                        confidence=0.72,
                        notes=notes,
                    )

            if inp.asymmetry_score > 0.15:
                notes.append("No near-term catalyst; equity is cheapest way to hold bullish conviction")
                return InstrumentSelectionResult(
                    asset_id=inp.asset_id,
                    instrument=Instrument.EQUITY,
                    rationale="Bullish asymmetry without near-term catalyst; equity cheapest to own through.",
                    confidence=0.65,
                    notes=notes,
                )
            elif inp.asymmetry_score < -0.15:
                notes.append("No near-term catalyst; long-dated put for bearish hedge")
                return InstrumentSelectionResult(
                    asset_id=inp.asset_id,
                    instrument=Instrument.PUT,
                    rationale="Bearish asymmetry without near-term catalyst; long-dated put for hedge.",
                    confidence=0.65,
                    notes=notes,
                )
            else:
                return InstrumentSelectionResult(
                    asset_id=inp.asset_id,
                    instrument=Instrument.NO_TRADE,
                    rationale="No near-term catalyst and weak asymmetry signal; insufficient edge.",
                    confidence=0.70,
                    notes=["asymmetry_score in [-0.15, 0.15] with no near-term catalyst"],
                )

        # Fallback — should not be reached given the rules above
        return InstrumentSelectionResult(
            asset_id=inp.asset_id,
            instrument=Instrument.NO_TRADE,
            rationale="No matching rule; defaulting to no trade.",
            confidence=0.50,
            notes=["fallback: no rule matched"],
        )
