"""Tests for portfolio allocator and position sizing."""

import pytest

from bve.portfolio.allocator import AllocationResult, PortfolioAllocator, PortfolioState
from bve.portfolio.constraints import PortfolioConstraints
from bve.portfolio.risk_model import PositionInput, RiskModel


def make_input(**kwargs) -> PositionInput:
    defaults = dict(
        ticker="VKTX",
        expected_return=0.35,
        downside_case=-0.40,
        liquidity_usd=20_000_000,
        nav_usd=500_000_000,
        event_date_days=60,
        correlation_cluster="oncology_io",
        confidence_score=0.75,
        max_loss_pct_nav=1.0,
        phase="phase_2",
        modality="small_molecule",
        catalyst_month="2024-06",
    )
    defaults.update(kwargs)
    return PositionInput(**defaults)


class TestRiskModel:
    def test_base_size_increases_with_expected_return(self):
        rm = RiskModel()
        low = make_input(expected_return=0.20)
        high = make_input(expected_return=0.40)
        assert rm.base_size_pct_nav(high) > rm.base_size_pct_nav(low)

    def test_base_size_decreases_with_larger_downside(self):
        rm = RiskModel()
        small_down = make_input(downside_case=-0.20)
        big_down = make_input(downside_case=-0.60)
        assert rm.base_size_pct_nav(small_down) > rm.base_size_pct_nav(big_down)

    def test_base_size_zero_for_nonneg_downside(self):
        rm = RiskModel()
        inp = make_input(downside_case=0.05)
        assert rm.base_size_pct_nav(inp) == 0.0

    def test_confidence_multiplier_max_at_one(self):
        rm = RiskModel()
        assert rm.confidence_multiplier(1.0) == 1.0

    def test_confidence_multiplier_floor_at_025(self):
        rm = RiskModel()
        assert rm.confidence_multiplier(0.0) == 0.25

    def test_liquidity_multiplier_high_liquidity(self):
        rm = RiskModel()
        mult = rm.liquidity_multiplier(100_000_000, 500_000_000)
        assert mult >= 0.5

    def test_raw_size_positive_for_good_input(self):
        rm = RiskModel()
        inp = make_input()
        assert rm.compute_raw_size_pct(inp) > 0


class TestPortfolioConstraints:
    def test_default_constraints_reasonable(self):
        c = PortfolioConstraints()
        assert 0 < c.max_single_name_pct_nav <= 10
        assert c.max_preclinical_pct_nav == 0.0

    def test_conservative_constraints_tighter(self):
        default = PortfolioConstraints()
        conservative = PortfolioConstraints.conservative()
        assert conservative.max_single_name_pct_nav < default.max_single_name_pct_nav

    def test_aggressive_constraints_looser(self):
        default = PortfolioConstraints()
        aggressive = PortfolioConstraints.aggressive()
        assert aggressive.max_single_name_pct_nav > default.max_single_name_pct_nav


class TestPortfolioAllocator:
    def test_buy_action_for_valid_input(self):
        alloc = PortfolioAllocator()
        inp = make_input()
        result = alloc.allocate(inp)
        assert result.action == "buy"
        assert result.suggested_size_pct_nav > 0

    def test_no_action_for_preclinical_with_zero_limit(self):
        alloc = PortfolioAllocator()
        inp = make_input(phase="preclinical")
        result = alloc.allocate(inp)
        assert result.action == "no_action"
        assert result.blocked_reason is not None

    def test_no_action_for_nonneg_return(self):
        alloc = PortfolioAllocator()
        inp = make_input(expected_return=-0.05)
        result = alloc.allocate(inp)
        assert result.action == "no_action"

    def test_no_action_for_nonneg_downside(self):
        alloc = PortfolioAllocator()
        inp = make_input(downside_case=0.10)
        result = alloc.allocate(inp)
        assert result.action == "no_action"

    def test_size_capped_at_single_name_limit(self):
        alloc = PortfolioAllocator(constraints=PortfolioConstraints(max_single_name_pct_nav=2.0))
        inp = make_input(expected_return=2.0, downside_case=-0.01)  # enormous raw size
        result = alloc.allocate(inp)
        assert result.suggested_size_pct_nav <= 2.0
        assert result.cap_reason is not None

    def test_phase2_cluster_cap_enforced(self):
        alloc = PortfolioAllocator()
        state = PortfolioState(phase2_total_pct=7.5)  # nearly at limit (8%)
        inp = make_input(phase="phase_2", expected_return=2.0, downside_case=-0.01)
        result = alloc.allocate(inp, portfolio=state)
        assert result.suggested_size_pct_nav <= 0.5 + 1e-9
        assert result.cap_reason is not None

    def test_catalyst_month_cap_enforced(self):
        alloc = PortfolioAllocator()
        state = PortfolioState(catalyst_month_exposure={"2024-06": 9.5})  # near 10% limit
        inp = make_input(catalyst_month="2024-06", expected_return=2.0, downside_case=-0.01)
        result = alloc.allocate(inp, portfolio=state)
        assert result.suggested_size_pct_nav <= 0.5 + 1e-9

    def test_describe_contains_action(self):
        alloc = PortfolioAllocator()
        inp = make_input()
        result = alloc.allocate(inp)
        desc = result.describe()
        assert "Action:" in desc
        assert "Suggested size:" in desc

    def test_max_loss_contribution_computed(self):
        alloc = PortfolioAllocator()
        inp = make_input()
        result = alloc.allocate(inp)
        assert result.max_loss_contribution_pct_nav >= 0
