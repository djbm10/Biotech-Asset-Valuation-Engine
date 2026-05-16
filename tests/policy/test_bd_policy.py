"""Tests for BD screening decision policy."""

import pytest

from bve.policy.decision_policy import BDPolicy, DecisionPolicy, PolicyAction
from bve.policy.policy_engine import DecisionPolicyEngine, ModelScores


def make_engine() -> DecisionPolicyEngine:
    return DecisionPolicyEngine()


def make_scores(**kwargs) -> ModelScores:
    defaults = dict(
        composite_score=0.80,
        asset_quality_score=0.70,
        strategic_fit_score=0.75,
        seller_willingness_score=0.50,
        expected_return=0.30,
        downside_floor_exists=True,
        liquidity_usd=10_000_000,
        catalyst_days_away=60,
        biology_score=0.70,
        capital_to_poc_usd=80_000_000,
        exit_buyer_count=5,
    )
    defaults.update(kwargs)
    return ModelScores(**defaults)


class TestBDPolicy:
    def test_active_pursuit_when_all_thresholds_met(self):
        engine = make_engine()
        scores = make_scores()
        rec = engine.evaluate_bd(scores, BDPolicy())
        assert rec.allowed_action == PolicyAction.ACTIVE_PURSUIT

    def test_monitor_when_composite_below_threshold(self):
        engine = make_engine()
        scores = make_scores(composite_score=0.40)
        rec = engine.evaluate_bd(scores, BDPolicy())
        assert rec.allowed_action == PolicyAction.MONITOR

    def test_blocked_when_asset_quality_too_low(self):
        engine = make_engine()
        scores = make_scores(asset_quality_score=0.30)
        rec = engine.evaluate_bd(scores, BDPolicy())
        assert PolicyAction.MONITOR == rec.allowed_action
        assert any("asset quality" in r for r in rec.blocked_reasons)

    def test_blocked_when_strategic_fit_too_low(self):
        engine = make_engine()
        scores = make_scores(strategic_fit_score=0.20)
        rec = engine.evaluate_bd(scores, BDPolicy())
        assert any("strategic fit" in r for r in rec.blocked_reasons)

    def test_blocked_when_seller_willingness_too_low(self):
        engine = make_engine()
        scores = make_scores(seller_willingness_score=0.10)
        rec = engine.evaluate_bd(scores, BDPolicy())
        assert any("seller willingness" in r for r in rec.blocked_reasons)

    def test_relationship_build_at_mid_score(self):
        engine = make_engine()
        scores = make_scores(composite_score=0.60)
        rec = engine.evaluate_bd(scores, BDPolicy())
        assert rec.allowed_action == PolicyAction.RELATIONSHIP_BUILD

    def test_recommendation_has_next_steps_for_active_pursuit(self):
        engine = make_engine()
        scores = make_scores()
        rec = engine.evaluate_bd(scores, BDPolicy())
        assert len(rec.required_next_steps) > 0

    def test_describe_returns_string(self):
        engine = make_engine()
        scores = make_scores()
        rec = engine.evaluate_bd(scores, BDPolicy())
        desc = rec.describe()
        assert "Policy:" in desc
        assert "Action:" in desc

    def test_is_actionable_false_for_monitor(self):
        engine = make_engine()
        scores = make_scores(composite_score=0.40)
        rec = engine.evaluate_bd(scores, BDPolicy())
        assert not rec.is_actionable
