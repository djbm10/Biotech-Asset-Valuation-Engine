"""Tests for hedge fund event-driven decision policy."""

import pytest

from bve.policy.decision_policy import HedgeFundPolicy, PolicyAction
from bve.policy.policy_engine import DecisionPolicyEngine, ModelScores


def make_engine():
    return DecisionPolicyEngine()


def make_scores(**kwargs) -> ModelScores:
    defaults = dict(
        composite_score=0.75,
        asset_quality_score=0.70,
        strategic_fit_score=0.70,
        seller_willingness_score=0.50,
        expected_return=0.35,
        downside_floor_exists=True,
        liquidity_usd=10_000_000,
        catalyst_days_away=60,
        biology_score=0.70,
        capital_to_poc_usd=80_000_000,
        exit_buyer_count=4,
    )
    defaults.update(kwargs)
    return ModelScores(**defaults)


class TestHFPolicy:
    def test_initiate_when_all_gates_pass(self):
        engine = make_engine()
        scores = make_scores()
        rec = engine.evaluate_hf(scores, HedgeFundPolicy())
        assert rec.allowed_action in (PolicyAction.INITIATE_POSITION, PolicyAction.ADD_TO_POSITION)

    def test_no_trade_when_expected_return_too_low(self):
        engine = make_engine()
        scores = make_scores(expected_return=0.05)
        rec = engine.evaluate_hf(scores, HedgeFundPolicy())
        assert rec.allowed_action == PolicyAction.NO_TRADE
        assert any("expected return" in r for r in rec.blocked_reasons)

    def test_no_trade_when_liquidity_insufficient(self):
        engine = make_engine()
        scores = make_scores(liquidity_usd=1_000)
        rec = engine.evaluate_hf(scores, HedgeFundPolicy())
        assert rec.allowed_action == PolicyAction.NO_TRADE
        assert any("liquidity" in r for r in rec.blocked_reasons)

    def test_no_trade_when_no_downside_floor(self):
        engine = make_engine()
        scores = make_scores(downside_floor_exists=False)
        rec = engine.evaluate_hf(scores, HedgeFundPolicy())
        assert rec.allowed_action == PolicyAction.NO_TRADE
        assert any("downside floor" in r for r in rec.blocked_reasons)

    def test_no_trade_when_catalyst_too_far(self):
        engine = make_engine()
        scores = make_scores(catalyst_days_away=365)
        rec = engine.evaluate_hf(scores, HedgeFundPolicy())
        assert rec.allowed_action == PolicyAction.NO_TRADE
        assert any("catalyst" in r for r in rec.blocked_reasons)

    def test_add_when_return_is_very_high(self):
        engine = make_engine()
        # 35% return >= 20% * 1.5 = 30% → add_to_position
        scores = make_scores(expected_return=0.35)
        rec = engine.evaluate_hf(scores, HedgeFundPolicy())
        assert rec.allowed_action == PolicyAction.ADD_TO_POSITION

    def test_no_trade_is_not_actionable(self):
        engine = make_engine()
        scores = make_scores(expected_return=0.01)
        rec = engine.evaluate_hf(scores, HedgeFundPolicy())
        assert not rec.is_actionable
