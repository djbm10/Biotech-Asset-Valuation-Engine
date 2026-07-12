"""
Point-in-time equity-to-enterprise-value bridge.

Fixes the accounting error identified in the three-pilot diagnostic: a raw
``price x shares_outstanding`` figure is market capitalization (equity
value), not enterprise value. Enterprise value nets out cash and debt.
Beyond that two-line fix, this module makes explicit the fuller identity so
future callers cannot silently re-introduce the same conflation:

    equity value (market cap)
        = net cash
        + sum of asset values (lead asset + any other modeled assets)
        + platform / other operating value
        - corporate overhead and other liabilities (PV, not yet captured
          in any per-asset rNPV)

Given ``market cap`` (observed) and every term except the lead asset's
value, the residual attributable to the lead asset is:

    residual_asset_value = enterprise_value
                            - other_asset_value
                            - platform_value
                            + corporate_overhead_pv

This residual, not raw market cap and not the two-term
``market_cap - net_cash`` enterprise value, is what should be compared to
a single-asset rNPV model's output.

For the single-asset lean-biotech configs this module was built for,
``other_asset_value_millions``, ``platform_value_millions`` are 0.0 by
construction (no other assets exist to value) and
``corporate_overhead_pv_millions`` defaults to 0.0 because none of the
three pilot configs (or the diagnostic controls) carry a standalone
corporate-G&A burn estimate independent of the asset-level SG&A already
inside the revenue model. That default is a documented simplification,
not a silent assumption -- ``ValuationBridgeResult.notes`` says so
explicitly whenever a component defaults to zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from bve.analysis.implied_pos import ImpliedPoSSolver


@dataclass(frozen=True)
class ValuationBridgeResult:
    market_cap_millions: float
    cash_millions: float
    debt_millions: float
    net_cash_millions: float
    other_asset_value_millions: float
    platform_value_millions: float
    corporate_overhead_pv_millions: float
    enterprise_value_millions: float
    """market_cap - net_cash. The 'simplified market EV' -- what the market
    is pricing operations + all pipeline assets + platform value at, net of
    the cash/debt balance sheet position."""
    residual_asset_value_millions: float
    """enterprise_value - other_asset_value - platform_value +
    corporate_overhead_pv. The value attributable to the single lead asset
    being valued, after backing out every other component of the identity.
    This -- not market cap, not enterprise_value_millions -- is the
    quantity that belongs on the other side of a single-asset rNPV
    comparison."""
    notes: list[str] = field(default_factory=list)


def compute_valuation_bridge(
    *,
    price: float,
    shares_outstanding_millions: float,
    cash_millions: float,
    debt_millions: float = 0.0,
    other_asset_value_millions: float = 0.0,
    platform_value_millions: float = 0.0,
    corporate_overhead_pv_millions: float = 0.0,
) -> ValuationBridgeResult:
    """Compute the point-in-time equity-to-enterprise-value bridge.

    No arbitrary cash floor and no hidden clamping -- every intermediate
    term is returned so a caller (or reviewer) can see exactly how
    ``residual_asset_value_millions`` was derived from the observed market
    cap.
    """
    market_cap = float(price) * float(shares_outstanding_millions)
    net_cash = float(cash_millions) - float(debt_millions)
    enterprise_value = market_cap - net_cash
    residual_asset_value = (
        enterprise_value
        - float(other_asset_value_millions)
        - float(platform_value_millions)
        + float(corporate_overhead_pv_millions)
    )

    notes: list[str] = []
    if other_asset_value_millions == 0.0:
        notes.append(
            "other_asset_value_millions=0.0: single-asset config simplification, "
            "not a claim the company has no other pipeline assets."
        )
    if platform_value_millions == 0.0:
        notes.append(
            "platform_value_millions=0.0: no standalone platform/technology value "
            "estimated separately from the lead asset."
        )
    if corporate_overhead_pv_millions == 0.0:
        notes.append(
            "corporate_overhead_pv_millions=0.0: no corporate G&A burn PV modeled "
            "independent of the asset-level SG&A already inside the revenue model. "
            "This is a documented simplification, not evidence overhead is zero."
        )

    return ValuationBridgeResult(
        market_cap_millions=round(market_cap, 6),
        cash_millions=round(float(cash_millions), 6),
        debt_millions=round(float(debt_millions), 6),
        net_cash_millions=round(net_cash, 6),
        other_asset_value_millions=round(float(other_asset_value_millions), 6),
        platform_value_millions=round(float(platform_value_millions), 6),
        corporate_overhead_pv_millions=round(float(corporate_overhead_pv_millions), 6),
        enterprise_value_millions=round(enterprise_value, 6),
        residual_asset_value_millions=round(residual_asset_value, 6),
        notes=notes,
    )


class SolverStatus(str, Enum):
    """Explicit boundary status for the bridged implied-PoS solve.

    Replaces the legacy `ImpliedPoSSolver` pattern of silently clamping an
    infeasible implied probability to `max_pos` (0.99) and setting a bare
    `market_exceeds_model` boolean. That pattern is left untouched on
    `bve.analysis.implied_pos.ImpliedPoSSolver` itself -- it is the shared
    class used by the live intelligence/screening pipeline
    (`mispricing_screener.py`, `ma_calibration.py`, `knowledge_layer.py`'s
    ops.db schema) and changing its public result shape there is a much
    larger blast-radius change than this narrow bridge audit calls for.
    This status lives only on the new `BridgedImpliedPoSResult` used by the
    six-name valuation-bridge diagnostic.
    """

    SOLVABLE = "solvable"
    REQUIRED_POS_ABOVE_ONE = "required_pos_above_one"
    MARKET_VALUE_BELOW_ZERO_POS_VALUE = "market_value_below_zero_pos_value"
    INSUFFICIENT_INPUTS = "insufficient_inputs"
    NON_MONOTONIC = "non_monotonic"


@dataclass(frozen=True)
class BridgedImpliedPoSResult:
    asset_id: str
    ticker: str
    bridge: ValuationBridgeResult
    status: SolverStatus
    model_pos: float
    model_rnpv_millions: float
    implied_pos: Optional[float] = None
    """Only populated when status == SOLVABLE. A pos value is never
    reported for any other status -- infeasible solves do not get a
    clamped-to-0.99 number presented as if it were a probability."""
    pos_spread: Optional[float] = None
    iterations: int = 0

    # Populated only when status == REQUIRED_POS_ABOVE_ONE.
    model_value_at_pos_1_millions: Optional[float] = None
    remaining_gap_millions: Optional[float] = None
    required_peak_sales_at_pos_1_millions: Optional[float] = None
    required_peak_sales_multiple: Optional[float] = None

    notes: list[str] = field(default_factory=list)


def solve_bridged_implied_pos(
    config_path: str | Path,
    bridge: ValuationBridgeResult,
    *,
    tolerance_millions: float = 1.0,
    tolerance_pct: float = 0.005,
    max_iterations: int = 50,
) -> BridgedImpliedPoSResult:
    """Solve implied PoS against `bridge.residual_asset_value_millions`
    (NOT raw market cap, NOT the two-term enterprise value) with explicit
    boundary-status reporting.

    `ImpliedPoSSolver`'s trial-probability-scaling mechanism clamps each
    phase probability to `[1e-6, 1 - 1e-6]` internally, so a compound PoS of
    exactly 1.0 is unreachable -- ``max_pos=1.0 - 1e-9`` here is a
    deliberate near-1.0 approximation used only to evaluate "model value at
    PoS = 1.0", not a claim that PoS can literally equal 1.0.
    """
    target_value = bridge.residual_asset_value_millions
    solver = ImpliedPoSSolver(
        min_pos=0.001,
        max_pos=1.0 - 1e-9,
        tolerance_millions=tolerance_millions,
        tolerance_pct=tolerance_pct,
        max_iterations=max_iterations,
    )

    config_path = Path(config_path)
    context = solver._build_context(config_path)
    if context is None:
        return BridgedImpliedPoSResult(
            asset_id="",
            ticker="",
            bridge=bridge,
            status=SolverStatus.INSUFFICIENT_INPUTS,
            model_pos=0.0,
            model_rnpv_millions=0.0,
            notes=["Config could not be loaded/validated, or has no remaining trials context."],
        )

    base_output = context.base_output
    asset_id = base_output.asset.id
    ticker = base_output.company.ticker or asset_id.upper()
    model_pos = float(base_output.rnpv.cumulative_success_probability)
    model_rnpv = float(base_output.rnpv.rnpv_millions)

    if not context.base_trials:
        # Already-approved / no-remaining-trials asset: pos is not solvable
        # in the usual sense. Treat as insufficient inputs for this
        # diagnostic rather than silently reusing the gross-revenue-scaling
        # shortcut, since none of BIND/GNCA/CEMP or the diagnostic controls
        # are in this state.
        return BridgedImpliedPoSResult(
            asset_id=asset_id,
            ticker=ticker,
            bridge=bridge,
            status=SolverStatus.INSUFFICIENT_INPUTS,
            model_pos=model_pos,
            model_rnpv_millions=model_rnpv,
            notes=["Config has no remaining trials; PoS is not a meaningful solve target."],
        )

    lo_actual_pos, lo_rnpv = solver._value_at_target_pos(context, solver.min_pos)
    hi_actual_pos, hi_rnpv = solver._value_at_target_pos(context, solver.max_pos)

    if hi_rnpv < lo_rnpv:
        return BridgedImpliedPoSResult(
            asset_id=asset_id,
            ticker=ticker,
            bridge=bridge,
            status=SolverStatus.NON_MONOTONIC,
            model_pos=model_pos,
            model_rnpv_millions=model_rnpv,
            notes=[
                f"Model value at min_pos ({lo_rnpv:.1f}M) exceeds value at max_pos "
                f"({hi_rnpv:.1f}M); rNPV is not monotonic in PoS for this config."
            ],
        )

    tolerance = solver._tolerance_for_ev(target_value) if target_value else tolerance_millions

    if target_value < lo_rnpv - tolerance:
        return BridgedImpliedPoSResult(
            asset_id=asset_id,
            ticker=ticker,
            bridge=bridge,
            status=SolverStatus.MARKET_VALUE_BELOW_ZERO_POS_VALUE,
            model_pos=model_pos,
            model_rnpv_millions=model_rnpv,
            notes=[
                f"Residual asset value ({target_value:.1f}M) is below the model's value "
                f"even at pos={solver.min_pos:.3f} ({lo_rnpv:.1f}M): the market is pricing "
                "this asset below what the model assigns to near-certain failure."
            ],
        )

    if target_value > hi_rnpv + tolerance:
        hi_output = _rerun_at_pos(solver, context, solver.max_pos)
        gross_pv_at_1 = float(hi_output.rnpv.gross_revenue_pv_millions)
        peak_sales_at_1 = float(hi_output.rnpv.peak_sales_millions)

        other_costs_net_at_1 = gross_pv_at_1 - hi_rnpv
        required_gross_pv = target_value + other_costs_net_at_1
        required_multiple = required_gross_pv / gross_pv_at_1 if gross_pv_at_1 > 0 else float("inf")
        required_peak_sales = peak_sales_at_1 * required_multiple

        return BridgedImpliedPoSResult(
            asset_id=asset_id,
            ticker=ticker,
            bridge=bridge,
            status=SolverStatus.REQUIRED_POS_ABOVE_ONE,
            model_pos=model_pos,
            model_rnpv_millions=model_rnpv,
            model_value_at_pos_1_millions=round(hi_rnpv, 6),
            remaining_gap_millions=round(target_value - hi_rnpv, 6),
            required_peak_sales_at_pos_1_millions=round(required_peak_sales, 6),
            required_peak_sales_multiple=round(required_multiple, 6),
            notes=[
                f"Residual asset value ({target_value:.1f}M) exceeds the model's value "
                f"at pos~1.0 ({hi_rnpv:.1f}M) by {target_value - hi_rnpv:.1f}M. Holding "
                f"success probability at ~1.0, peak sales would need to be "
                f"{required_multiple:.2f}x the config's assumed peak sales "
                f"({peak_sales_at_1:.0f}M -> {required_peak_sales:.0f}M) to justify this "
                "residual value from the lead asset alone."
            ],
        )

    solved = solver.solve(str(config_path), target_value)
    if solved is None:
        return BridgedImpliedPoSResult(
            asset_id=asset_id,
            ticker=ticker,
            bridge=bridge,
            status=SolverStatus.INSUFFICIENT_INPUTS,
            model_pos=model_pos,
            model_rnpv_millions=model_rnpv,
            notes=["Legacy solver returned None (target_value <= 0 or config load failure)."],
        )

    return BridgedImpliedPoSResult(
        asset_id=asset_id,
        ticker=ticker,
        bridge=bridge,
        status=SolverStatus.SOLVABLE,
        model_pos=model_pos,
        model_rnpv_millions=model_rnpv,
        implied_pos=solved.implied_pos,
        pos_spread=solved.pos_spread,
        iterations=solved.iterations,
    )


def _rerun_at_pos(solver: ImpliedPoSSolver, context, target_pos: float):
    """Return the full ValuationOutput at `target_pos`, not just the
    (actual_pos, rnpv) tuple `_value_at_target_pos` returns -- needed to
    read `gross_revenue_pv_millions` / `peak_sales_millions` for the
    required-peak-sales-at-PoS=1 diagnostic.
    """
    import warnings

    scaled_trials = solver._scale_trials_to_target_pos(context.base_trials, target_pos)
    context.engine.trials = scaled_trials
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return context.engine.run()
