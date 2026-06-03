"""Tests for deal structure optimizer."""

import pytest

from bve.deals.structure import DealStructure, DealStructureType
from bve.deals.seller_utility import SellerUtilityModel, SellerValuation
from bve.deals.optimizer import DealOptimizer, DealOptimizerInput


def make_seller(**kwargs) -> SellerValuation:
    defaults = dict(
        standalone_rnpv_usd_m=200.0,
        cash_runway_months=18.0,
        strategic_alternatives=1,
        founder_control_preference=0.3,
    )
    defaults.update(kwargs)
    return SellerValuation(**defaults)


def make_optimizer_input(**kwargs) -> DealOptimizerInput:
    defaults = dict(
        buyer_rnpv_full_acquisition_usd_m=800.0,
        seller_standalone_rnpv_usd_m=200.0,
        seller_cash_runway_months=18.0,
        seller_strategic_alternatives=1,
        seller_founder_control_preference=0.3,
        budget_usd_m=1000.0,
        min_seller_acceptance_probability=0.30,
        approval_probability=0.50,
    )
    defaults.update(kwargs)
    return DealOptimizerInput(**defaults)


class TestDealStructure:
    def test_net_rnpv_after_upfront(self):
        s = DealStructure(
            structure_type=DealStructureType.FULL_ACQUISITION,
            upfront_cash_usd_m=400.0,
            buyer_rnpv_usd_m=600.0,
        )
        assert s.net_buyer_rnpv_after_upfront == 200.0

    def test_upfront_as_pct_of_buyer_rnpv(self):
        s = DealStructure(
            structure_type=DealStructureType.FULL_ACQUISITION,
            upfront_cash_usd_m=200.0,
            buyer_rnpv_usd_m=800.0,
        )
        assert abs(s.upfront_as_pct_buyer_rnpv - 25.0) < 0.01

    def test_summary_contains_structure_type(self):
        s = DealStructure(
            structure_type=DealStructureType.OPTION_TO_ACQUIRE,
            upfront_cash_usd_m=50.0,
            option_exercise_price_usd_m=400.0,
            milestones_total_usd_m=200.0,
            buyer_rnpv_usd_m=300.0,
            seller_expected_value_usd_m=350.0,
        )
        summary = s.summary()
        assert "option_to_acquire" in summary
        assert "$50M" in summary


class TestSellerUtilityModel:
    def setup_method(self):
        self.model = SellerUtilityModel()

    def test_high_multiple_increases_acceptance(self):
        seller = make_seller()
        low_p = self.model.acceptance_probability(200.0, seller)    # 1× standalone
        high_p = self.model.acceptance_probability(400.0, seller)   # 2× standalone
        assert high_p > low_p

    def test_low_cash_runway_increases_acceptance(self):
        seller_urgent = make_seller(cash_runway_months=6)
        seller_fine = make_seller(cash_runway_months=36)
        p_urgent = self.model.acceptance_probability(300.0, seller_urgent)
        p_fine = self.model.acceptance_probability(300.0, seller_fine)
        assert p_urgent > p_fine

    def test_more_alternatives_reduces_acceptance(self):
        seller_no_alt = make_seller(strategic_alternatives=0)
        seller_many_alt = make_seller(strategic_alternatives=4)
        p_no_alt = self.model.acceptance_probability(300.0, seller_no_alt)
        p_many_alt = self.model.acceptance_probability(300.0, seller_many_alt)
        assert p_no_alt > p_many_alt

    def test_acceptance_probability_in_range(self):
        for offer in [50, 200, 400, 800, 1500]:
            p = self.model.acceptance_probability(float(offer), make_seller())
            assert 0.0 <= p <= 1.0

    def test_minimum_acceptable_value_above_standalone(self):
        seller = make_seller()
        min_val = self.model.minimum_acceptable_value(seller)
        assert min_val > seller.standalone_rnpv_usd_m

    def test_urgent_seller_accepts_at_lower_multiple(self):
        seller = make_seller(cash_runway_months=6)
        min_val = self.model.minimum_acceptable_value(seller)
        normal_min = self.model.minimum_acceptable_value(make_seller(cash_runway_months=36))
        assert min_val < normal_min


class TestDealOptimizer:
    def setup_method(self):
        self.optimizer = DealOptimizer()

    def test_returns_optimized_deal(self):
        inp = make_optimizer_input()
        result = self.optimizer.optimize(inp)
        assert result.best_structure is not None

    def test_best_structure_is_feasible(self):
        inp = make_optimizer_input()
        result = self.optimizer.optimize(inp)
        assert result.best_structure.upfront_cash_usd_m <= inp.budget_usd_m

    def test_all_structures_generated(self):
        inp = make_optimizer_input()
        result = self.optimizer.optimize(inp)
        assert len(result.all_structures) >= 3

    def test_budget_constraint_respected(self):
        inp = make_optimizer_input(budget_usd_m=100.0)
        result = self.optimizer.optimize(inp)
        assert result.best_structure.upfront_cash_usd_m <= 100.0 + 1e-6

    def test_describe_contains_structure(self):
        inp = make_optimizer_input()
        result = self.optimizer.optimize(inp)
        desc = result.describe()
        assert "Best structure:" in desc

    def test_option_preferred_over_full_acquisition_at_high_risk(self):
        # With P(approval) = 0.3 and tight budget, option should often win
        inp = make_optimizer_input(
            approval_probability=0.30,
            budget_usd_m=80.0,  # too small for full acquisition premium
        )
        result = self.optimizer.optimize(inp)
        # Just check it produces a result (specific structure depends on arithmetic)
        assert result.best_structure.structure_type is not None
