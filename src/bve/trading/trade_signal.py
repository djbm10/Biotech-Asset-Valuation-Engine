"""Combine instrument selection and position sizing into a unified trade signal."""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from bve.trading.instrument_selector import InstrumentSelectionResult
from bve.trading.position_sizer import PositionSizeResult


class TradeSignal(BaseModel):
    asset_id: str
    ticker: Optional[str] = None
    signal_date: date
    action: str  # "initiate" | "add" | "trim" | "exit" | "no_trade"
    instrument: str  # from InstrumentSelector
    target_position_pct: float
    incremental_pct: float
    asymmetry_score: float
    rationale: str
    risk_flags: list[str] = Field(default_factory=list)


class TradeSignalBuilder:
    """
    Combines InstrumentSelectionResult + PositionSizeResult → TradeSignal.

    Action mapping:
        incremental_pct > 0.01 and current == 0  → "initiate"
        incremental_pct > 0.005                  → "add"
        incremental_pct < -0.005                 → "trim"
        target == 0 and current > 0              → "exit"
        else                                     → "no_trade"

    risk_flags collected from:
        - PositionSizeResult.risk_adjustments
        - InstrumentSelectionResult.notes
    """

    def build(
        self,
        instrument_result: InstrumentSelectionResult,
        size_result: PositionSizeResult,
        signal_date: date,
        ticker: Optional[str] = None,
        current_position_pct: float = 0.0,
        asymmetry_score: float = 0.0,
    ) -> TradeSignal:
        """Build a TradeSignal from instrument selection and position sizing results."""
        incremental_pct = size_result.incremental_position_pct
        target_pct = size_result.target_position_pct

        # Determine action (exit checked before trim to distinguish full liquidation)
        if target_pct == 0.0 and current_position_pct > 0.0:
            action = "exit"
        elif incremental_pct > 0.01 and current_position_pct == 0.0:
            action = "initiate"
        elif incremental_pct > 0.005:
            action = "add"
        elif incremental_pct < -0.005:
            action = "trim"
        else:
            action = "no_trade"

        # Aggregate risk flags from both results
        risk_flags: list[str] = []
        risk_flags.extend(size_result.risk_adjustments)
        risk_flags.extend(instrument_result.notes)

        # Compose rationale
        rationale = f"[{instrument_result.instrument.value}] {instrument_result.rationale} | Size: {size_result.sizing_rationale}"

        return TradeSignal(
            asset_id=size_result.asset_id,
            ticker=ticker,
            signal_date=signal_date,
            action=action,
            instrument=instrument_result.instrument.value,
            target_position_pct=target_pct,
            incremental_pct=incremental_pct,
            asymmetry_score=asymmetry_score,
            rationale=rationale,
            risk_flags=risk_flags,
        )
