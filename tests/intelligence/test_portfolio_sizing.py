"""Tests for Wave P — Portfolio Sizing Framework."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pytest

from bve.intelligence.portfolio_sizing import (
    PortfolioAllocation,
    PortfolioSizingEngine,
    PositionAllocation,
    PositionSizeRules,
    compute_portfolio_allocation,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@dataclass
class _Opp:
    """Minimal RankedOpportunity stand-in."""
    asset_id: str
    composite_score: float
    company_id: str = "co-1"
    ticker: Optional[str] = None
    rank: int = 1
    mispricing_score: Optional[float] = None
    indication: Optional[str] = None


def _make_opps(n: int, *, composite_score: float = 0.6, mispricing: Optional[float] = None) -> list[_Opp]:
    return [
        _Opp(
            asset_id=f"asset-{i}",
            company_id=f"co-{i}",
            rank=i + 1,
            composite_score=composite_score - i * 0.05,
            mispricing_score=mispricing,
            indication=f"ind-{i}",
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# PositionSizeRules
# ---------------------------------------------------------------------------

def test_rules_defaults() -> None:
    r = PositionSizeRules()
    assert r.kelly_fraction == 0.5
    assert r.max_position_pct == 0.20
    assert r.min_position_pct == 0.01
    assert r.max_n_positions == 20
    assert r.cash_buffer_pct == 0.05


def test_rules_frozen() -> None:
    r = PositionSizeRules()
    with pytest.raises(Exception):
        r.max_position_pct = 0.5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Empty / trivial inputs
# ---------------------------------------------------------------------------

def test_empty_opportunities() -> None:
    result = compute_portfolio_allocation([])
    assert result.n_positions == 0
    assert result.total_weight == 0.0
    assert result.cash_weight == 1.0
    assert result.positions == []


def test_single_opportunity_no_mispricing() -> None:
    opps = [_Opp("a-1", composite_score=0.8, company_id="co-a", indication="ind-x")]
    result = compute_portfolio_allocation(opps)
    assert result.n_positions == 1
    assert len(result.positions) == 1
    pos = result.positions[0]
    assert pos.weight <= 0.20
    assert pos.weight >= 0.01


# ---------------------------------------------------------------------------
# Half-Kelly sizing
# ---------------------------------------------------------------------------

def test_half_kelly_weight_proportional_to_mispricing() -> None:
    """Half-Kelly position = 0.5 × mispricing_score."""
    opps = [
        _Opp("a-1", composite_score=0.8, mispricing_score=0.30, company_id="co-1", indication="ind-1"),
        _Opp("a-2", composite_score=0.7, mispricing_score=0.10, company_id="co-2", indication="ind-2"),
    ]
    rules = PositionSizeRules(kelly_fraction=0.5, max_position_pct=0.5)
    result = PortfolioSizingEngine(rules).size(opps)
    pos_a1 = next(p for p in result.positions if p.asset_id == "a-1")
    pos_a2 = next(p for p in result.positions if p.asset_id == "a-2")
    # a-1 should have higher weight
    assert pos_a1.weight > pos_a2.weight
    assert pos_a1.sizing_method == "half_kelly"
    assert pos_a2.sizing_method == "half_kelly"
    # raw Kelly weight = 0.5 * 0.30 = 0.15 for a-1
    assert abs(pos_a1.raw_kelly_weight - 0.15) < 1e-6


def test_kelly_zero_falls_back_to_proportional() -> None:
    rules = PositionSizeRules(kelly_fraction=0.0)
    opps = [_Opp("a-1", composite_score=0.8, mispricing_score=0.30)]
    result = PortfolioSizingEngine(rules).size(opps)
    assert result.positions[0].sizing_method in ("proportional", "equal_weight")


def test_negative_mispricing_falls_back() -> None:
    """Negative mispricing (overvalued) → raw half-Kelly = 0, falls back."""
    opps = [_Opp("a-1", composite_score=0.7, mispricing_score=-0.20, indication="ind-1")]
    rules = PositionSizeRules(kelly_fraction=0.5)
    result = PortfolioSizingEngine(rules).size(opps)
    assert result.positions[0].sizing_method in ("proportional", "equal_weight")


# ---------------------------------------------------------------------------
# Position clipping
# ---------------------------------------------------------------------------

def test_weight_clipped_to_max_position_pct() -> None:
    opps = [_Opp("a-1", composite_score=0.9, mispricing_score=0.80, indication="ind-1")]
    rules = PositionSizeRules(max_position_pct=0.15, kelly_fraction=1.0)
    result = PortfolioSizingEngine(rules).size(opps)
    assert result.positions[0].weight <= 0.15 + 1e-9


def test_weight_clipped_to_min_position_pct() -> None:
    opps = [_Opp("a-1", composite_score=0.1, mispricing_score=0.001, indication="ind-1")]
    rules = PositionSizeRules(min_position_pct=0.03, kelly_fraction=0.5)
    result = PortfolioSizingEngine(rules).size(opps)
    assert result.positions[0].weight >= 0.03 - 1e-9


# ---------------------------------------------------------------------------
# Concentration guardrails
# ---------------------------------------------------------------------------

def test_concentration_same_indication() -> None:
    """Multiple assets in same indication should not exceed max_concentration_pct."""
    opps = [
        _Opp(f"a-{i}", composite_score=0.8, company_id=f"co-{i}", indication="oncology")
        for i in range(5)
    ]
    rules = PositionSizeRules(max_concentration_pct=0.30, max_position_pct=0.20)
    result = PortfolioSizingEngine(rules).size(opps)
    total_oncology = sum(p.weight for p in result.positions)
    assert total_oncology <= 0.30 + 1e-9


def test_concentration_same_company() -> None:
    """Multiple assets in same company should not exceed max_concentration_pct."""
    opps = [
        _Opp(f"a-{i}", composite_score=0.8, company_id="mega-co", indication=f"ind-{i}")
        for i in range(5)
    ]
    rules = PositionSizeRules(max_concentration_pct=0.25, max_position_pct=0.20)
    result = PortfolioSizingEngine(rules).size(opps)
    total_co = sum(p.weight for p in result.positions)
    assert total_co <= 0.25 + 1e-9


# ---------------------------------------------------------------------------
# max_n_positions
# ---------------------------------------------------------------------------

def test_max_n_positions_respected() -> None:
    opps = _make_opps(10)
    rules = PositionSizeRules(max_n_positions=3)
    result = PortfolioSizingEngine(rules).size(opps)
    assert result.n_positions <= 3


# ---------------------------------------------------------------------------
# Score filter
# ---------------------------------------------------------------------------

def test_min_composite_score_filter() -> None:
    opps = [
        _Opp("a-1", composite_score=0.8, indication="ind-1"),
        _Opp("a-2", composite_score=0.3, indication="ind-2"),
        _Opp("a-3", composite_score=0.1, indication="ind-3"),
    ]
    rules = PositionSizeRules(min_composite_score=0.5)
    result = PortfolioSizingEngine(rules).size(opps)
    assert result.n_excluded_score == 2
    assert result.n_positions == 1
    assert result.positions[0].asset_id == "a-1"


# ---------------------------------------------------------------------------
# Cash buffer
# ---------------------------------------------------------------------------

def test_cash_buffer_respected() -> None:
    opps = _make_opps(20, mispricing=0.5)
    rules = PositionSizeRules(cash_buffer_pct=0.10, max_n_positions=20)
    result = PortfolioSizingEngine(rules).size(opps)
    assert result.total_weight <= 0.90 + 1e-9
    assert result.cash_weight >= 0.10 - 1e-9


def test_total_weight_plus_cash_weight_equals_one() -> None:
    opps = _make_opps(5, mispricing=0.3)
    result = compute_portfolio_allocation(opps)
    assert abs(result.total_weight + result.cash_weight - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# Dollar amounts
# ---------------------------------------------------------------------------

def test_dollar_amounts_populated_when_aum_given() -> None:
    opps = [_Opp("a-1", composite_score=0.8, mispricing_score=0.25, indication="ind-1")]
    result = compute_portfolio_allocation(opps, portfolio_aum_millions=100.0)
    pos = result.positions[0]
    assert pos.dollar_amount_millions is not None
    assert abs(pos.dollar_amount_millions - pos.weight * 100.0) < 0.01


def test_dollar_amounts_none_when_no_aum() -> None:
    opps = [_Opp("a-1", composite_score=0.8, indication="ind-1")]
    result = compute_portfolio_allocation(opps, portfolio_aum_millions=None)
    assert result.positions[0].dollar_amount_millions is None


# ---------------------------------------------------------------------------
# PortfolioAllocation metadata
# ---------------------------------------------------------------------------

def test_allocation_n_positions_matches_len() -> None:
    opps = _make_opps(4)
    result = compute_portfolio_allocation(opps)
    assert result.n_positions == len(result.positions)


def test_allocation_rules_preserved() -> None:
    rules = PositionSizeRules(max_n_positions=7)
    result = compute_portfolio_allocation(_make_opps(3), rules=rules)
    assert result.rules.max_n_positions == 7
