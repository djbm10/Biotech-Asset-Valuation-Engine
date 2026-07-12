"""
Locks in the CURRENT (pre-bridge-fix) equation `ImpliedPoSSolver` solves,
before any refactor. Per the valuation-bridge audit: `ImpliedPoSSolver`
performs ZERO cash/debt netting internally. It treats whatever
`current_ev_millions` value the caller passes in as directly comparable to
`model_rnpv_millions` (an asset-only quantity -- P(approval) x PV(FCF) -
PV(costs) + milestones, per `RNPVModel`). Correctness of the EV/market-cap
distinction is entirely the caller's responsibility; the solver's parameter
name is aspirational, not enforced.

This is exactly the gap that let the three-pilot script pass raw
`price x shares_outstanding` (market cap) in as `current_ev_millions`
without netting cash/debt, understating the implied PoS ceiling problem
(see docs/historical_valuation_configs/three_pilot_report_2026-07-12.md
and the valuation-bridge audit that followed it). These tests exist to
freeze that legacy behavior with an explicit test, per the instruction to
"add a unit test that locks the current equation before refactoring it" --
NOT to endorse the behavior as correct.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bve.analysis.implied_pos import ImpliedPoSSolver

CONFIG_PATH = Path(__file__).resolve().parents[1] / "examples" / "configs" / "xyz101.yaml"

# From examples/configs/xyz101.yaml `company:` block.
CASH_MILLIONS = 450.0
DEBT_MILLIONS = 50.0
NET_CASH_MILLIONS = CASH_MILLIONS - DEBT_MILLIONS  # 400.0


@pytest.fixture
def solver() -> ImpliedPoSSolver:
    return ImpliedPoSSolver(max_iterations=50, mc_simulations=1, random_seed=42)


@pytest.fixture
def context(solver: ImpliedPoSSolver):
    ctx = solver._build_context(CONFIG_PATH)
    assert ctx is not None
    return ctx


def test_solver_equates_current_ev_millions_directly_to_asset_only_rnpv(
    solver: ImpliedPoSSolver,
    context,
) -> None:
    """The solver's equation is: find pos such that
    model_rnpv_millions(pos) == current_ev_millions, with no adjustment for
    cash, debt, or any other balance-sheet term. Feeding it the asset's own
    rnpv at a known pos must round-trip back to that same pos exactly --
    proving current_ev_millions is compared against rnpv_millions with
    nothing subtracted or added in between.
    """
    target_pos = 0.25
    _, rnpv_at_target = solver._value_at_target_pos(context, target_pos)

    result = solver.solve(str(CONFIG_PATH), rnpv_at_target)

    assert result is not None
    assert result.implied_pos == pytest.approx(target_pos, abs=0.01)
    assert result.implied_rnpv_millions == pytest.approx(rnpv_at_target, abs=1.0)


def test_solver_does_not_net_cash_or_debt_from_current_ev_millions(
    solver: ImpliedPoSSolver,
    context,
) -> None:
    """If the solver netted cash/debt internally, feeding it
    `rnpv_at_target_pos + net_cash` (the value a market-cap-based caller
    would mistakenly pass in, having forgotten to subtract net cash first)
    would still solve back to `target_pos` once the solver's own netting
    cancelled the added net_cash back out. It does not: the solver has no
    netting step, so adding net_cash shifts the solved-for pos higher
    (since a larger `current_ev_millions` requires a larger pos to match
    the asset's rNPV) -- reproducing the market-cap/EV conflation bug at
    the unit level.
    """
    target_pos = 0.25
    _, rnpv_at_target = solver._value_at_target_pos(context, target_pos)

    market_cap_style_ev = rnpv_at_target + NET_CASH_MILLIONS
    result = solver.solve(str(CONFIG_PATH), market_cap_style_ev)

    assert result is not None
    assert result.implied_pos > target_pos + 0.01
    assert result.implied_rnpv_millions == pytest.approx(market_cap_style_ev, abs=5.0)


def test_solver_has_no_cash_or_debt_aware_parameters(solver: ImpliedPoSSolver) -> None:
    """Documents, at the API-surface level, that no cash/debt/net_cash
    keyword exists anywhere on `solve()` -- confirming the netting
    responsibility is 100% the caller's, matching the finding in
    `historical_implied_pos_validation.py` (which nets cash/debt itself,
    correctly, before calling `solve()`) vs. the three-pilot script (which
    did not).
    """
    import inspect

    solve_params = set(inspect.signature(ImpliedPoSSolver.solve).parameters)
    assert not solve_params & {"cash_millions", "debt_millions", "net_cash_millions"}
