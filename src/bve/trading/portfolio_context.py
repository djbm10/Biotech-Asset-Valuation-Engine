"""Portfolio context for position sizing and concentration checks."""
from __future__ import annotations

from pydantic import BaseModel, model_validator


class PositionRecord(BaseModel, frozen=True):
    asset_id: str
    ticker: str
    weight: float          # current portfolio weight 0.0-1.0
    cost_basis_return: float  # return since entry (e.g. -0.10 = down 10%)
    phase: str             # "Phase 1", "Phase 2", "Phase 3", "Approved"
    therapeutic_area: str  # e.g. "oncology", "rare_disease"
    days_held: int


class PortfolioContext(BaseModel, frozen=True):
    positions: list[PositionRecord]
    total_nav: float        # total portfolio NAV in USD
    cash_pct: float         # cash as fraction of NAV (0.0-1.0)
    max_single_position: float = 0.10   # hard cap per position (default 10%)
    max_ta_concentration: float = 0.35  # max weight per therapeutic area (default 35%)
    max_phase_concentration: float = 0.40  # max weight per phase bucket (default 40%)

    # Derived (auto-computed):
    total_invested_pct: float = 0.0        # 1 - cash_pct
    ta_weights: dict[str, float] = {}      # TA -> total weight
    phase_weights: dict[str, float] = {}   # phase -> total weight
    n_positions: int = 0

    @model_validator(mode="before")
    @classmethod
    def compute_derived(cls, data: dict) -> dict:
        positions = data.get("positions", [])
        cash_pct = data.get("cash_pct", 0.0)

        # Compute TA weights
        ta_weights: dict[str, float] = {}
        phase_weights: dict[str, float] = {}

        for pos in positions:
            if isinstance(pos, dict):
                ta = pos.get("therapeutic_area", "")
                phase = pos.get("phase", "")
                weight = pos.get("weight", 0.0)
            else:
                ta = pos.therapeutic_area
                phase = pos.phase
                weight = pos.weight

            ta_weights[ta] = ta_weights.get(ta, 0.0) + weight
            phase_weights[phase] = phase_weights.get(phase, 0.0) + weight

        data["total_invested_pct"] = 1.0 - cash_pct
        data["ta_weights"] = ta_weights
        data["phase_weights"] = phase_weights
        data["n_positions"] = len(positions)
        return data


def available_capacity(
    context: PortfolioContext,
    asset_id: str,
    therapeutic_area: str,
    phase: str,
) -> float:
    """
    Returns the maximum additional weight that can be allocated to this asset
    given position, TA, and phase concentration limits.

    Takes the minimum of:
    - (max_single_position - current position weight for this asset_id, or max_single_position if not held)
    - (max_ta_concentration - current TA weight)
    - (max_phase_concentration - current phase weight)
    - cash_pct (can't invest more than available cash)
    Floored at 0.0.
    """
    # Find existing position weight for this asset_id
    current_weight = 0.0
    for pos in context.positions:
        if pos.asset_id == asset_id:
            current_weight = pos.weight
            break

    # Single position headroom
    single_headroom = context.max_single_position - current_weight

    # TA headroom (subtract existing TA weight)
    current_ta_weight = context.ta_weights.get(therapeutic_area, 0.0)
    # If asset is already in this TA, don't double-count its weight
    if current_weight > 0:
        for pos in context.positions:
            if pos.asset_id == asset_id and pos.therapeutic_area == therapeutic_area:
                # The asset's weight is already included in ta_weights; capacity is
                # how much more we can add on top of what's already there
                break
    ta_headroom = context.max_ta_concentration - current_ta_weight

    # Phase headroom
    current_phase_weight = context.phase_weights.get(phase, 0.0)
    phase_headroom = context.max_phase_concentration - current_phase_weight

    # Cash constraint
    cash_headroom = context.cash_pct

    capacity = min(single_headroom, ta_headroom, phase_headroom, cash_headroom)
    return max(0.0, capacity)


def concentration_penalty(
    context: PortfolioContext,
    therapeutic_area: str,
    phase: str,
) -> float:
    """
    Returns a penalty multiplier [0.5, 1.0] applied to position size:
    - 1.0 if TA weight < 0.20 and phase weight < 0.25
    - 0.75 if TA weight >= 0.25 or phase weight >= 0.30
    - 0.50 if TA weight >= 0.30 or phase weight >= 0.35
    """
    ta_weight = context.ta_weights.get(therapeutic_area, 0.0)
    phase_weight = context.phase_weights.get(phase, 0.0)

    # Check highest penalty tier first
    if ta_weight >= 0.30 or phase_weight >= 0.35:
        return 0.50

    if ta_weight >= 0.25 or phase_weight >= 0.30:
        return 0.75

    return 1.0
