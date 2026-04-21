"""Final trade signal output combining all upstream signals."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel

from bve.trading.asymmetry_score import AsymmetryResult
from bve.trading.kelly_sizer import SizingResult


class TradeAction(str, Enum):
    STRONG_BUY = "strong_buy"   # asymmetry_score >= 0.70, thesis actionable
    BUY = "buy"                  # asymmetry_score >= 0.50
    WATCH = "watch"              # asymmetry_score >= 0.35, not yet actionable
    HOLD = "hold"                # existing position, no new entry signal
    REDUCE = "reduce"            # bear thesis, reduce existing
    EXIT = "exit"                # kill criterion triggered OR strong_bear
    NO_ACTION = "no_action"      # score < 0.35, neutral


class TradeSignal(BaseModel, frozen=True):
    signal_id: str               # UUID
    asset_id: str
    ticker: str
    action: TradeAction
    asymmetry_score: float
    recommended_instrument: str  # from AsymmetryResult.recommended_instrument
    suggested_weight: float      # from SizingResult.final_weight (0 if no action)
    pos_delta: float
    thesis_strength: str         # from VariantView.thesis_strength.value
    kill_triggered: bool
    rationale: str
    generated_at: datetime       # UTC


def generate_signal(
    asset_id: str,
    ticker: str,
    asymmetry: AsymmetryResult,
    sizing: SizingResult,
    kill_triggered: bool,
    thesis_strength: str,
) -> TradeSignal:
    """
    Action logic:
    - EXIT if kill_triggered
    - EXIT if thesis_strength in ("strong_bear",) AND asymmetry.pos_delta < -0.15
    - REDUCE if thesis_strength == "bear"
    - STRONG_BUY if asymmetry_score >= 0.70 AND NOT kill_triggered
    - BUY if asymmetry_score >= 0.50
    - WATCH if asymmetry_score >= 0.35
    - NO_ACTION otherwise
    """
    asymmetry_score = asymmetry.asymmetry_score

    # Determine action
    if kill_triggered:
        action = TradeAction.EXIT
        rationale = (
            f"Kill criterion triggered for {asset_id}; exiting position regardless of score."
        )
    elif thesis_strength in ("strong_bear",) and asymmetry.pos_delta < -0.15:
        action = TradeAction.EXIT
        rationale = (
            f"Strong bear thesis (strength={thesis_strength!r}) with pos_delta={asymmetry.pos_delta:+.3f} "
            f"< -0.15; exiting position."
        )
    elif thesis_strength == "bear":
        action = TradeAction.REDUCE
        rationale = (
            f"Bear thesis (strength={thesis_strength!r}); reducing position. "
            f"asymmetry_score={asymmetry_score:.3f}."
        )
    elif asymmetry_score >= 0.70:
        action = TradeAction.STRONG_BUY
        rationale = (
            f"Strong buy: asymmetry_score={asymmetry_score:.3f} >= 0.70, "
            f"thesis={thesis_strength!r}, kill_triggered=False."
        )
    elif asymmetry_score >= 0.50:
        action = TradeAction.BUY
        rationale = (
            f"Buy: asymmetry_score={asymmetry_score:.3f} >= 0.50, "
            f"thesis={thesis_strength!r}."
        )
    elif asymmetry_score >= 0.35:
        action = TradeAction.WATCH
        rationale = (
            f"Watch: asymmetry_score={asymmetry_score:.3f} >= 0.35; "
            "monitoring but not yet actionable."
        )
    else:
        action = TradeAction.NO_ACTION
        rationale = (
            f"No action: asymmetry_score={asymmetry_score:.3f} < 0.35; "
            "insufficient edge."
        )

    # Suggested weight is 0 for non-buy actions
    suggested_weight = sizing.final_weight if action in (
        TradeAction.STRONG_BUY, TradeAction.BUY
    ) else 0.0

    return TradeSignal(
        signal_id=str(uuid.uuid4()),
        asset_id=asset_id,
        ticker=ticker,
        action=action,
        asymmetry_score=asymmetry_score,
        recommended_instrument=asymmetry.recommended_instrument.value,
        suggested_weight=suggested_weight,
        pos_delta=asymmetry.pos_delta,
        thesis_strength=thesis_strength,
        kill_triggered=kill_triggered,
        rationale=rationale,
        generated_at=datetime.now(timezone.utc),
    )
