"""Tests for VC underwriting decision policy."""

import pytest

from bve.policy.decision_policy import PolicyAction, VCPolicy
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


class TestVCPolicy:
    def test_diligence_required_when_all_gates_pass(self):
        engine = make_engine()
        scores = make_scores()
        rec = engine.evaluate_vc(scores, VCPolicy())
        assert rec.allowed_action == PolicyAction.DILIGENCE_REQUIRED

    def test_pass_when_biology_score_too_low(self):
        engine = make_engine()
        scores = make_scores(biology_score=0.40)
        rec = engine.evaluate_vc(scores, VCPolicy())
        assert rec.allowed_action == PolicyAction.PASS
        assert any("biology" in r for r in rec.blocked_reasons)

    def test_pass_when_capital_requirement_too_high(self):
        engine = make_engine()
        scores = make_scores(capital_to_poc_usd=200_000_000)
        rec = engine.evaluate_vc(scores, VCPolicy())
        assert rec.allowed_action == PolicyAction.PASS
        assert any("capital to PoC" in r for r in rec.blocked_reasons)

    def test_pass_when_buyer_universe_too_small(self):
        engine = make_engine()
        scores = make_scores(exit_buyer_count=1)
        rec = engine.evaluate_vc(scores, VCPolicy())
        assert rec.allowed_action == PolicyAction.PASS
        assert any("exit buyer" in r for r in rec.blocked_reasons)

    def test_platform_optionality_gate_when_required(self):
        engine = make_engine()
        policy = VCPolicy(require_platform_optionality=True)
        scores = make_scores(has_platform_optionality=False)
        rec = engine.evaluate_vc(scores, policy)
        assert rec.allowed_action == PolicyAction.PASS
        assert any("platform" in r for r in rec.blocked_reasons)

    def test_platform_gate_passes_when_optionality_present(self):
        engine = make_engine()
        policy = VCPolicy(require_platform_optionality=True)
        scores = make_scores(has_platform_optionality=True)
        rec = engine.evaluate_vc(scores, policy)
        assert rec.allowed_action == PolicyAction.DILIGENCE_REQUIRED

    def test_evaluate_all_returns_three_policies(self):
        from bve.policy.decision_policy import DecisionPolicy
        engine = make_engine()
        scores = make_scores()
        results = engine.evaluate_all(scores, DecisionPolicy())
        assert set(results.keys()) == {"bd", "hedge_fund", "vc"}
