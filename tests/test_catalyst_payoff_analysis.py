"""Tests for catalyst_payoff analysis module."""

from __future__ import annotations

from datetime import date

import pytest

from bve.analysis.catalyst_payoff import (
    Catalyst,
    CatalystEVResult,
    CatalystPayoffTree,
    CatalystScenario,
)


# ---------------------------------------------------------------------------
# CatalystScenario
# ---------------------------------------------------------------------------

def test_catalyst_scenario_basic():
    sc = CatalystScenario(
        scenario_id="SC1",
        label="clear_win",
        probability=0.40,
        expected_price_move_pct=80.0,
        post_event_financing_state="no_need",
        post_event_thesis_state="confirmed",
    )
    assert sc.label == "clear_win"
    assert sc.next_catalyst is None
    assert sc.post_event_ev_millions is None


def test_catalyst_scenario_probability_bounds():
    with pytest.raises(Exception):
        CatalystScenario(
            scenario_id="SC1",
            label="bad",
            probability=1.5,
            expected_price_move_pct=0.0,
            post_event_financing_state="no_need",
            post_event_thesis_state="confirmed",
        )


# ---------------------------------------------------------------------------
# CatalystPayoffTree
# ---------------------------------------------------------------------------

def _make_tree() -> CatalystPayoffTree:
    sc_win = CatalystScenario(
        scenario_id="SC1",
        label="clear_win",
        probability=0.40,
        expected_price_move_pct=80.0,
        post_event_financing_state="no_need",
        post_event_thesis_state="confirmed",
    )
    sc_miss = CatalystScenario(
        scenario_id="SC2",
        label="miss",
        probability=0.60,
        expected_price_move_pct=-50.0,
        post_event_financing_state="distressed",
        post_event_thesis_state="broken",
    )
    return CatalystPayoffTree(
        catalyst_id="CAT1",
        asset_id="A1",
        catalyst_label="Phase 3 readout",
        catalyst_date=date(2026, 3, 1),
        catalyst_type="readout",
        scenarios=[sc_win, sc_miss],
        expected_return_pct=0.40 * 80.0 + 0.60 * (-50.0),
        downside_severity_pct=50.0,
        skew_ratio=80.0 / 50.0,
        setup_score=0.65,
        pre_event_recommendation="half-size add",
        post_event_action_map={"confirmed": "full-size add", "broken": "exit"},
    )


def test_catalyst_payoff_tree_basic():
    tree = _make_tree()
    assert len(tree.scenarios) == 2
    assert tree.setup_score == 0.65
    assert "confirmed" in tree.post_event_action_map


def test_catalyst_payoff_tree_expected_return():
    tree = _make_tree()
    # 0.40 * 80 + 0.60 * (-50) = 32 - 30 = 2
    assert abs(tree.expected_return_pct - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# CatalystEVResult
# ---------------------------------------------------------------------------

def test_catalyst_ev_result_basic():
    tree = _make_tree()
    result = CatalystEVResult(
        asset_id="A1",
        ticker="TICK",
        trees=[tree],
        composite_expected_return_pct=2.0,
        max_downside_pct=50.0,
        best_risk_reward_catalyst_id="CAT1",
    )
    assert result.best_risk_reward_catalyst_id == "CAT1"
    assert len(result.trees) == 1


# ---------------------------------------------------------------------------
# Catalyst
# ---------------------------------------------------------------------------

def test_catalyst_basic():
    cat = Catalyst(
        catalyst_id="CAT1",
        asset_id="A1",
        label="Phase 3 readout",
        expected_date=date(2026, 3, 1),
        catalyst_type="readout",
        importance="primary",
        source="company guidance",
    )
    assert cat.importance == "primary"


def test_catalyst_secondary():
    cat = Catalyst(
        catalyst_id="CAT2",
        asset_id="A1",
        label="ASCO presentation",
        expected_date=date(2026, 6, 1),
        catalyst_type="conference",
        importance="secondary",
        source="ASCO abstract",
    )
    assert cat.catalyst_type == "conference"
