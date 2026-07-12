"""
Tests for the point-in-time equity-to-enterprise-value bridge and the
explicit-boundary-status implied-PoS solve built on top of it.

Covers the accounting fix at the center of the valuation-bridge audit:
market cap != enterprise value, and enterprise value != the value
attributable to a single lead asset once other-asset/platform/overhead
terms are (even trivially) accounted for.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bve.analysis.valuation_bridge import (
    SolverStatus,
    compute_valuation_bridge,
    solve_bridged_implied_pos,
)

XYZ_CONFIG = Path(__file__).resolve().parents[1] / "examples" / "configs" / "xyz101.yaml"
CEMP_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "configs"
    / "pit"
    / "cemp_solithromycin_pit_2016-11-03.yaml"
)


def test_bridge_nets_cash_and_debt_not_just_market_cap() -> None:
    bridge = compute_valuation_bridge(
        price=10.0,
        shares_outstanding_millions=100.0,
        cash_millions=450.0,
        debt_millions=50.0,
    )

    assert bridge.market_cap_millions == pytest.approx(1000.0)
    assert bridge.net_cash_millions == pytest.approx(400.0)
    assert bridge.enterprise_value_millions == pytest.approx(600.0)
    # No other-asset/platform/overhead terms supplied -> residual == EV.
    assert bridge.residual_asset_value_millions == pytest.approx(600.0)
    assert bridge.market_cap_millions != bridge.enterprise_value_millions


def test_bridge_residual_nets_other_asset_platform_and_overhead() -> None:
    bridge = compute_valuation_bridge(
        price=10.0,
        shares_outstanding_millions=100.0,
        cash_millions=450.0,
        debt_millions=50.0,
        other_asset_value_millions=200.0,
        platform_value_millions=50.0,
        corporate_overhead_pv_millions=30.0,
    )

    assert bridge.enterprise_value_millions == pytest.approx(600.0)
    # residual = EV - other_asset - platform + overhead
    assert bridge.residual_asset_value_millions == pytest.approx(600.0 - 200.0 - 50.0 + 30.0)


def test_bridge_notes_flag_zero_defaults_as_simplification_not_fact() -> None:
    bridge = compute_valuation_bridge(
        price=10.0, shares_outstanding_millions=100.0, cash_millions=0.0
    )
    joined = " ".join(bridge.notes)
    assert "other_asset_value_millions=0.0" in joined
    assert "not a claim" in joined


def test_solve_bridged_implied_pos_returns_solvable_within_normal_range() -> None:
    bridge = compute_valuation_bridge(
        price=1.0,
        shares_outstanding_millions=1.0,
        cash_millions=0.0,
        debt_millions=0.0,
    )
    # Override residual directly via a fresh bridge constructed to equal a
    # known reachable target: use the model's own mid-range value.
    from bve.analysis.implied_pos import ImpliedPoSSolver

    solver = ImpliedPoSSolver(mc_simulations=1, random_seed=42)
    context = solver._build_context(XYZ_CONFIG)
    assert context is not None
    _, target_rnpv = solver._value_at_target_pos(context, 0.30)

    bridge = compute_valuation_bridge(
        price=target_rnpv, shares_outstanding_millions=1.0, cash_millions=0.0
    )
    result = solve_bridged_implied_pos(XYZ_CONFIG, bridge)

    assert result.status == SolverStatus.SOLVABLE
    assert result.implied_pos == pytest.approx(0.30, abs=0.01)
    assert result.model_value_at_pos_1_millions is None


def test_solve_bridged_implied_pos_required_pos_above_one_has_diagnostics() -> None:
    from bve.analysis.implied_pos import ImpliedPoSSolver

    solver = ImpliedPoSSolver(mc_simulations=1, random_seed=42)
    context = solver._build_context(XYZ_CONFIG)
    assert context is not None
    _, max_rnpv = solver._value_at_target_pos(context, 1.0 - 1e-9)

    bridge = compute_valuation_bridge(
        price=max_rnpv + 500.0, shares_outstanding_millions=1.0, cash_millions=0.0
    )
    result = solve_bridged_implied_pos(XYZ_CONFIG, bridge)

    assert result.status == SolverStatus.REQUIRED_POS_ABOVE_ONE
    assert result.implied_pos is None
    assert result.model_value_at_pos_1_millions is not None
    assert result.remaining_gap_millions == pytest.approx(
        bridge.residual_asset_value_millions - result.model_value_at_pos_1_millions, abs=1.0
    )
    assert result.required_peak_sales_at_pos_1_millions is not None
    assert result.required_peak_sales_multiple is not None
    assert result.required_peak_sales_multiple > 1.0


def test_solve_bridged_implied_pos_market_value_below_zero_pos_value() -> None:
    # market_cap (10) - net_cash (500) => residual = -490M, well below the
    # model's value at min_pos (~ -89M per xyz101.yaml's trial cost PV).
    bridge = compute_valuation_bridge(
        price=10.0, shares_outstanding_millions=1.0, cash_millions=500.0
    )
    result = solve_bridged_implied_pos(XYZ_CONFIG, bridge)

    assert result.status == SolverStatus.MARKET_VALUE_BELOW_ZERO_POS_VALUE
    assert result.implied_pos is None


def test_solve_bridged_implied_pos_insufficient_inputs_for_bad_config_path() -> None:
    bridge = compute_valuation_bridge(
        price=10.0, shares_outstanding_millions=1.0, cash_millions=0.0
    )
    result = solve_bridged_implied_pos("does/not/exist.yaml", bridge)

    assert result.status == SolverStatus.INSUFFICIENT_INPUTS
    assert result.implied_pos is None


def test_cemp_pilot_moves_off_ceiling_ambiguity_with_quantified_gap() -> None:
    """Regression guard for the specific accounting bug this audit fixes:
    CEMP's raw market cap ($395.5M) was previously passed directly to the
    solver as if it were EV. The corrected bridge nets $248.9M of cash,
    leaving a $146.6M residual -- still above the model's ceiling value,
    but now with a quantified, small (~9.5x) required-peak-sales multiple
    instead of an unquantified 0.99 clamp.
    """
    bridge = compute_valuation_bridge(
        price=7.55, shares_outstanding_millions=52.38, cash_millions=248.9, debt_millions=0.0
    )
    assert bridge.market_cap_millions == pytest.approx(395.469, abs=0.01)
    assert bridge.residual_asset_value_millions == pytest.approx(146.569, abs=0.01)
    assert bridge.residual_asset_value_millions < bridge.market_cap_millions

    result = solve_bridged_implied_pos(CEMP_CONFIG, bridge)
    assert result.status == SolverStatus.REQUIRED_POS_ABOVE_ONE
    assert result.required_peak_sales_multiple == pytest.approx(9.5, abs=0.5)
