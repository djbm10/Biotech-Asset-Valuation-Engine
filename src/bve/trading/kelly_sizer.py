"""Kelly-inspired position sizer with hard caps and concentration adjustments."""
from __future__ import annotations

from pydantic import BaseModel

from bve.trading.portfolio_context import (
    PortfolioContext,
    available_capacity,
    concentration_penalty,
)
from bve.trading.asymmetry_score import AsymmetryResult


class SizingResult(BaseModel, frozen=True):
    asset_id: str
    raw_kelly: float           # uncapped Kelly fraction
    kelly_half: float          # half-Kelly (raw_kelly / 2)
    capacity_cap: float        # from available_capacity()
    concentration_mult: float  # from concentration_penalty()
    final_weight: float        # min(kelly_half, capacity_cap) × concentration_mult, floored 0
    position_size_usd: float   # final_weight × total_nav
    rationale: str


def compute_kelly(
    win_prob: float,      # P(positive outcome) — from pos_delta + base PoS
    win_return: float,    # expected return if positive
    loss_return: float,   # expected return if negative (negative number, e.g. -0.40)
) -> float:
    """
    Kelly fraction = (win_prob × win_return - (1 - win_prob) × abs(loss_return)) / win_return
    Clamped to [0.0, 0.25] (never bet more than 25% on a single name).
    Returns 0.0 if win_return <= 0 or result is negative.
    """
    if win_return <= 0:
        return 0.0

    lose_prob = 1.0 - win_prob
    abs_loss = abs(loss_return)

    kelly = (win_prob * win_return - lose_prob * abs_loss) / win_return

    if kelly < 0.0:
        return 0.0

    return min(0.25, kelly)


def size_position(
    asymmetry: AsymmetryResult,
    context: PortfolioContext,
    therapeutic_area: str,
    phase: str,
    base_pos: float,      # base PoS (e.g. 0.35)
) -> SizingResult:
    """
    1. win_prob = base_pos + max(0, asymmetry.pos_delta × 0.5)  — shift PoS by half the variant delta
    2. win_return = asymmetry.expected_return if > 0, else 0.10 (floor for sizing)
    3. loss_return = -asymmetry.implied_move_pct (use implied move as downside proxy)
    4. raw_kelly = compute_kelly(win_prob, win_return, loss_return)
    5. kelly_half = raw_kelly / 2
    6. capacity_cap = available_capacity(context, asymmetry.asset_id, therapeutic_area, phase)
    7. concentration_mult = concentration_penalty(context, therapeutic_area, phase)
    8. final_weight = min(kelly_half, capacity_cap) × concentration_mult
    9. position_size_usd = final_weight × context.total_nav
    """
    # Step 1: win probability
    win_prob = base_pos + max(0.0, asymmetry.pos_delta * 0.5)
    win_prob = min(1.0, max(0.0, win_prob))

    # Step 2: win return (floor at 0.10)
    win_return = asymmetry.expected_return if asymmetry.expected_return > 0 else 0.10

    # Step 3: loss return (downside proxy from implied move)
    loss_return = -asymmetry.implied_move_pct

    # Step 4: raw Kelly
    raw_kelly = compute_kelly(win_prob, win_return, loss_return)

    # Step 5: half Kelly
    kelly_half = raw_kelly / 2.0

    # Step 6: capacity cap
    capacity_cap = available_capacity(context, asymmetry.asset_id, therapeutic_area, phase)

    # Step 7: concentration multiplier
    concentration_mult = concentration_penalty(context, therapeutic_area, phase)

    # Step 8: final weight
    final_weight = min(kelly_half, capacity_cap) * concentration_mult
    final_weight = max(0.0, final_weight)

    # Step 9: position size in USD
    position_size_usd = final_weight * context.total_nav

    rationale = (
        f"win_prob={win_prob:.3f}, win_return={win_return:.3f}, "
        f"loss_return={loss_return:.3f}, raw_kelly={raw_kelly:.4f}, "
        f"kelly_half={kelly_half:.4f}, capacity_cap={capacity_cap:.4f}, "
        f"concentration_mult={concentration_mult:.2f}, final_weight={final_weight:.4f}"
    )

    return SizingResult(
        asset_id=asymmetry.asset_id,
        raw_kelly=raw_kelly,
        kelly_half=kelly_half,
        capacity_cap=capacity_cap,
        concentration_mult=concentration_mult,
        final_weight=final_weight,
        position_size_usd=position_size_usd,
        rationale=rationale,
    )
