"""Composite asymmetry score combining variant view, catalyst payoff, and implied move."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from bve.intelligence.variant_view import VariantView, thesis_is_actionable
from bve.valuation.scenario_tree import CatalystPayoffTree
from bve.trading.implied_move import ImpliedMoveEstimate


class InstrumentType(str, Enum):
    EQUITY = "equity"
    CALL_OPTION = "call_option"
    PUT_OPTION = "put_option"
    STRADDLE = "straddle"
    NO_TRADE = "no_trade"


class AsymmetryResult(BaseModel, frozen=True):
    asset_id: str
    asymmetry_score: float        # 0.0-1.0 composite
    recommended_instrument: InstrumentType
    pos_delta: float              # from variant view
    skew_ratio: float             # from catalyst tree
    implied_move_pct: float       # from implied move estimate
    expected_return: float        # from catalyst tree
    rationale: str


def _select_instrument(
    asymmetry_score: float,
    pos_delta: float,
    skew_ratio: float,
    implied_move_pct: float,
    view: VariantView,
) -> tuple[InstrumentType, str]:
    """Determine recommended instrument and rationale string."""
    if asymmetry_score < 0.30 or not thesis_is_actionable(view):
        if asymmetry_score < 0.30:
            rationale = (
                f"Asymmetry score {asymmetry_score:.3f} below 0.30 threshold; "
                "insufficient edge to trade."
            )
        else:
            rationale = (
                "Thesis is not actionable: requires at least one kill criterion "
                "and |pos_delta| >= 0.05."
            )
        return InstrumentType.NO_TRADE, rationale

    if implied_move_pct >= 0.35 and skew_ratio < 1.5:
        return (
            InstrumentType.STRADDLE,
            f"High implied move ({implied_move_pct:.0%}) with low directional skew "
            f"({skew_ratio:.2f}); straddle captures binary outcome.",
        )

    if pos_delta >= 0.10 and skew_ratio >= 1.5:
        return (
            InstrumentType.CALL_OPTION,
            f"Bullish pos_delta ({pos_delta:+.3f}) with favorable skew ({skew_ratio:.2f}); "
            "call option preferred.",
        )

    if pos_delta <= -0.10 and skew_ratio >= 1.5:
        return (
            InstrumentType.PUT_OPTION,
            f"Bearish pos_delta ({pos_delta:+.3f}) with favorable skew ({skew_ratio:.2f}); "
            "put option preferred.",
        )

    if 0.05 <= abs(pos_delta) < 0.10:
        return (
            InstrumentType.EQUITY,
            f"Moderate pos_delta ({pos_delta:+.3f}); equity provides directional exposure "
            "at lower cost.",
        )

    return (
        InstrumentType.NO_TRADE,
        f"No instrument rule matched for pos_delta={pos_delta:+.3f}, "
        f"skew_ratio={skew_ratio:.2f}, implied_move={implied_move_pct:.0%}.",
    )


def compute_asymmetry(
    asset_id: str,
    view: VariantView,
    tree: CatalystPayoffTree,
    implied_move: ImpliedMoveEstimate,
) -> AsymmetryResult:
    """
    Composite formula:
    - pos_component = min(1.0, abs(view.pos_delta) / 0.20)
    - skew_component = min(1.0, tree.skew_ratio / 3.0)
    - return_component = min(1.0, max(0.0, (tree.expected_return + 0.20) / 0.60))
    - asymmetry_score = 0.40 × pos_component + 0.35 × skew_component + 0.25 × return_component
    """
    pos_component = min(1.0, abs(view.pos_delta) / 0.20)
    skew_component = min(1.0, tree.skew_ratio / 3.0)
    return_component = min(1.0, max(0.0, (tree.expected_return + 0.20) / 0.60))

    asymmetry_score = (
        0.40 * pos_component
        + 0.35 * skew_component
        + 0.25 * return_component
    )
    asymmetry_score = round(min(1.0, max(0.0, asymmetry_score)), 6)

    instrument, rationale = _select_instrument(
        asymmetry_score=asymmetry_score,
        pos_delta=view.pos_delta,
        skew_ratio=tree.skew_ratio,
        implied_move_pct=implied_move.implied_move_pct,
        view=view,
    )

    return AsymmetryResult(
        asset_id=asset_id,
        asymmetry_score=asymmetry_score,
        recommended_instrument=instrument,
        pos_delta=view.pos_delta,
        skew_ratio=tree.skew_ratio,
        implied_move_pct=implied_move.implied_move_pct,
        expected_return=tree.expected_return,
        rationale=rationale,
    )
