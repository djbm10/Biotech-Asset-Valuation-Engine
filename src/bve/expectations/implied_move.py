"""Estimate options-implied expected move for a catalyst event."""
from __future__ import annotations

import math
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class ImpliedMoveEstimate(BaseModel):
    asset_id: str
    ticker: str
    event_date: date
    days_to_event: int
    implied_volatility_annual: Optional[float] = None   # e.g. 1.20 for 120% IV
    implied_move_pct: Optional[float] = None            # ±% expected move (unsigned)
    method: str = "iv_approximation"                    # "iv_approximation" / "straddle_price" / "historical_analog"
    # Historical analog inputs (when IV not available)
    phase: Optional[str] = None
    modality: Optional[str] = None
    therapeutic_area: Optional[str] = None
    historical_analog_move_pct: Optional[float] = None
    # Scenario-weighted move
    upside_move_pct: Optional[float] = None
    downside_move_pct: Optional[float] = None
    prob_success: Optional[float] = None                # used to weight scenario move
    expected_move_pct: Optional[float] = None           # prob * upside + (1-prob) * downside (signed)
    iv_richness: Optional[str] = None                   # "cheap" / "fair" / "rich" / "unknown"
    notes: list[str] = Field(default_factory=list)


# Historical analog move table by phase and TA
_ANALOG_MOVES: dict[tuple[str, str], tuple[float, float]] = {
    # (phase, ta): (upside_pct, downside_pct)
    ("3", "oncology"):      (0.30, -0.40),
    ("3", "rare_disease"):  (0.50, -0.55),
    ("3", "immunology"):    (0.25, -0.35),
    ("3", "cns"):           (0.20, -0.35),
    ("2", "oncology"):      (0.25, -0.35),
    ("2", "rare_disease"):  (0.40, -0.45),
    ("2", "immunology"):    (0.20, -0.30),
    ("2", "cns"):           (0.15, -0.30),
    ("1", "oncology"):      (0.15, -0.20),
}
_DEFAULT_ANALOG = (0.25, -0.35)


def estimate_implied_move(
    *,
    asset_id: str,
    ticker: str,
    event_date: date,
    days_to_event: int,
    implied_volatility_annual: Optional[float] = None,
    phase: Optional[str] = None,
    therapeutic_area: Optional[str] = None,
    prob_success: Optional[float] = None,
    upside_move_pct: Optional[float] = None,
    downside_move_pct: Optional[float] = None,
) -> ImpliedMoveEstimate:
    """
    Estimate expected move from IV or historical analogs.

    IV method: implied_move ≈ IV × sqrt(days/365)  (1-std-dev expected move)
    Analog method: look up (phase, ta) in _ANALOG_MOVES table.
    Expected move = prob_success * upside + (1 - prob_success) * downside
    IV richness: compare IV to historical analog; > 1.3× → rich, < 0.7× → cheap
    """
    implied_move = None
    method = "historical_analog"
    iv_richness = "unknown"

    if implied_volatility_annual is not None and implied_volatility_annual > 0:
        implied_move = implied_volatility_annual * math.sqrt(days_to_event / 365.0)
        method = "iv_approximation"

    ta_key = (therapeutic_area or "").lower()
    ph_key = str(phase or "")
    lookup_key = (ph_key, ta_key)
    up_analog, dn_analog = _ANALOG_MOVES.get(lookup_key, _DEFAULT_ANALOG)

    if upside_move_pct is None:
        upside_move_pct = up_analog
    if downside_move_pct is None:
        downside_move_pct = dn_analog

    # Analog move = average unsigned magnitude
    analog_implied = (abs(upside_move_pct) + abs(downside_move_pct)) / 2

    if implied_move is not None and analog_implied > 0:
        ratio = implied_move / analog_implied
        if ratio > 1.3:
            iv_richness = "rich"
        elif ratio < 0.7:
            iv_richness = "cheap"
        else:
            iv_richness = "fair"

    final_implied = implied_move if implied_move is not None else analog_implied

    expected_move = None
    if prob_success is not None:
        expected_move = prob_success * upside_move_pct + (1 - prob_success) * downside_move_pct

    return ImpliedMoveEstimate(
        asset_id=asset_id, ticker=ticker, event_date=event_date,
        days_to_event=days_to_event,
        implied_volatility_annual=implied_volatility_annual,
        implied_move_pct=round(final_implied, 4),
        method=method, phase=phase, therapeutic_area=therapeutic_area,
        historical_analog_move_pct=round(analog_implied, 4),
        upside_move_pct=upside_move_pct, downside_move_pct=downside_move_pct,
        prob_success=prob_success, expected_move_pct=expected_move,
        iv_richness=iv_richness,
    )
