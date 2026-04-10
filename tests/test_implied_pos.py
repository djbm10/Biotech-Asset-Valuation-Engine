from __future__ import annotations

from pathlib import Path

import pytest

from bve.analysis.implied_pos import ImpliedPoSSolver

CONFIG_PATH = Path(__file__).resolve().parents[1] / "examples" / "configs" / "xyz101.yaml"


@pytest.fixture
def solver() -> ImpliedPoSSolver:
    return ImpliedPoSSolver(max_iterations=50, mc_simulations=1, random_seed=42)


@pytest.fixture
def context(solver: ImpliedPoSSolver):
    ctx = solver._build_context(CONFIG_PATH)
    assert ctx is not None
    return ctx


def _ev_at_target_pos(
    solver: ImpliedPoSSolver,
    context,
    target_pos: float,
) -> float:
    _, rnpv = solver._value_at_target_pos(context, target_pos)
    return rnpv


def test_known_config_with_known_ev_solves_expected_implied_pos(
    solver: ImpliedPoSSolver,
    context,
) -> None:
    target_pos = 0.24
    current_ev = _ev_at_target_pos(solver, context, target_pos)

    result = solver.solve(str(CONFIG_PATH), current_ev)

    assert result is not None
    assert result.implied_pos == pytest.approx(target_pos, abs=0.01)


def test_binary_search_converges_within_50_iterations(
    solver: ImpliedPoSSolver,
    context,
) -> None:
    target_pos = 0.30
    current_ev = _ev_at_target_pos(solver, context, target_pos)

    result = solver.solve(str(CONFIG_PATH), current_ev)

    assert result is not None
    assert result.iterations <= 50


def test_edge_case_ev_exceeds_max_rnpv_returns_upper_bound(
    solver: ImpliedPoSSolver,
    context,
) -> None:
    _, max_rnpv = solver._value_at_target_pos(context, solver.max_pos)

    result = solver.solve(str(CONFIG_PATH), max_rnpv + 25.0)

    assert result is not None
    assert result.market_exceeds_model is True
    assert result.implied_pos == pytest.approx(0.99, abs=1e-6)


def test_edge_case_zero_ev_returns_none(solver: ImpliedPoSSolver) -> None:
    assert solver.solve(str(CONFIG_PATH), 0.0) is None


def test_pos_spread_is_positive_when_model_pos_exceeds_implied_pos(
    solver: ImpliedPoSSolver,
    context,
) -> None:
    target_pos = 0.19
    current_ev = _ev_at_target_pos(solver, context, target_pos)

    result = solver.solve(str(CONFIG_PATH), current_ev)

    assert result is not None
    assert result.model_pos > result.implied_pos
    assert result.pos_spread > 0


def test_round_trip_rnpv_at_implied_pos_matches_current_ev(
    solver: ImpliedPoSSolver,
    context,
) -> None:
    target_pos = 0.27
    current_ev = _ev_at_target_pos(solver, context, target_pos)

    result = solver.solve(str(CONFIG_PATH), current_ev)

    assert result is not None
    tolerance = solver._tolerance_for_ev(current_ev)
    assert abs(result.implied_rnpv_millions - current_ev) <= tolerance
