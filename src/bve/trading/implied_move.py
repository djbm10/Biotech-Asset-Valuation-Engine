"""IV-based implied move estimation — no live market data calls."""
from __future__ import annotations

import math

from pydantic import BaseModel

# Analog table: historical median implied moves by event type and therapeutic area
ANALOG_IMPLIED_MOVES: dict[str, dict[str, float]] = {
    "phase2_readout": {"oncology": 0.35, "rare_disease": 0.45, "other": 0.28},
    "phase3_readout": {"oncology": 0.45, "rare_disease": 0.55, "other": 0.38},
    "pdufa_date":     {"oncology": 0.30, "rare_disease": 0.40, "other": 0.25},
    "adcom":          {"oncology": 0.20, "rare_disease": 0.25, "other": 0.18},
    "partnership":    {"oncology": 0.15, "rare_disease": 0.18, "other": 0.12},
    "interim_data":   {"oncology": 0.25, "rare_disease": 0.30, "other": 0.20},
}

_FALLBACK_EVENT_TYPE = "phase3_readout"
_FALLBACK_AREA = "other"
_CLAMP_MIN = 0.05
_CLAMP_MAX = 2.00


class ImpliedMoveEstimate(BaseModel, frozen=True):
    asset_id: str
    event_type: str
    therapeutic_area: str
    implied_move_pct: float        # e.g. 0.35 = ±35%
    source: str                    # "iv_derived" or "analog_table"
    iv_input: float | None         # annualized IV if provided (e.g. 1.20 = 120%)
    days_to_event: int | None      # used for IV-to-move conversion
    analog_used: str | None        # which analog table entry was used


def estimate_from_iv(
    asset_id: str,
    annualized_iv: float,
    days_to_event: int,
    event_type: str = "phase3_readout",
    therapeutic_area: str = "other",
) -> ImpliedMoveEstimate:
    """
    Convert annualized IV to expected move:
    implied_move = annualized_iv × sqrt(days_to_event / 252)
    Clamp output to [0.05, 2.00].
    """
    raw_move = annualized_iv * math.sqrt(days_to_event / 252.0)
    implied_move = max(_CLAMP_MIN, min(_CLAMP_MAX, raw_move))
    return ImpliedMoveEstimate(
        asset_id=asset_id,
        event_type=event_type,
        therapeutic_area=therapeutic_area,
        implied_move_pct=implied_move,
        source="iv_derived",
        iv_input=annualized_iv,
        days_to_event=days_to_event,
        analog_used=None,
    )


def estimate_from_analog(
    asset_id: str,
    event_type: str,
    therapeutic_area: str = "other",
) -> ImpliedMoveEstimate:
    """
    Look up analog table. Falls back to 'other' if therapeutic_area not found.
    Falls back to 'phase3_readout'/'other' if event_type not found.
    """
    event_entry = ANALOG_IMPLIED_MOVES.get(event_type)
    if event_entry is None:
        # Unknown event type — fall back to phase3_readout/other
        implied_move = ANALOG_IMPLIED_MOVES[_FALLBACK_EVENT_TYPE][_FALLBACK_AREA]
        analog_used = f"{_FALLBACK_EVENT_TYPE}/{_FALLBACK_AREA}"
        resolved_event = _FALLBACK_EVENT_TYPE
        resolved_area = _FALLBACK_AREA
    else:
        resolved_event = event_type
        area_value = event_entry.get(therapeutic_area)
        if area_value is None:
            # Unknown therapeutic area — fall back to 'other'
            implied_move = event_entry[_FALLBACK_AREA]
            analog_used = f"{event_type}/{_FALLBACK_AREA}"
            resolved_area = _FALLBACK_AREA
        else:
            implied_move = area_value
            analog_used = f"{event_type}/{therapeutic_area}"
            resolved_area = therapeutic_area

    return ImpliedMoveEstimate(
        asset_id=asset_id,
        event_type=resolved_event,
        therapeutic_area=resolved_area,
        implied_move_pct=implied_move,
        source="analog_table",
        iv_input=None,
        days_to_event=None,
        analog_used=analog_used,
    )
