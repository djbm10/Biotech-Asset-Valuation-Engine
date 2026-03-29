"""
Sprint 26B — Thesis-strength entry gate in ReplayPolicy.

Tests for ReplayPolicyConfig.min_thesis_score and ReplayPolicy.select() gate.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_opportunity(asset_id: str, ticker: str, score: float = 0.70, thesis_strength=None):
    opp = MagicMock()
    opp.asset_id = asset_id
    opp.ticker = ticker
    opp.composite_score = score
    opp.recommended_action = "buy"
    opp.recommended_size_pct = 0.05
    opp.critic_severity = None
    opp.one_line_summary = "test"
    opp.thesis_strength = thesis_strength
    return opp


def _make_report(opportunities, week: str = "2022-06-01"):
    report = MagicMock()
    report.opportunities = opportunities
    report.week_ending = date.fromisoformat(week)
    return report


# ===========================================================================
# 1. ReplayPolicyConfig — field exists and defaults
# ===========================================================================

class TestPolicyConfigMinThesisScore:
    def test_default_is_zero(self):
        from bve.intelligence.replay_policy import ReplayPolicyConfig
        cfg = ReplayPolicyConfig()
        assert cfg.min_thesis_score == 0.0

    def test_explicit_value_accepted(self):
        from bve.intelligence.replay_policy import ReplayPolicyConfig
        cfg = ReplayPolicyConfig(min_thesis_score=0.5)
        assert cfg.min_thesis_score == pytest.approx(0.5)

    def test_mna_profile_has_no_gate(self):
        from bve.intelligence.replay_policy import ReplayPolicyConfig
        cfg = ReplayPolicyConfig.mna_profile()
        assert cfg.min_thesis_score == 0.0


# ===========================================================================
# 2. Gate disabled (min_thesis_score = 0) — all thesis values allowed
# ===========================================================================

class TestGateDisabled:
    def test_allows_none_thesis_when_disabled(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(min_thesis_score=0.0, max_positions=1))
        opp = _make_opportunity("a-alny", "ALNY", thesis_strength=None)
        decisions = policy.select(_make_report([opp]))
        assert len(decisions) == 1

    def test_allows_low_thesis_when_disabled(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(min_thesis_score=0.0, max_positions=1))
        opp = _make_opportunity("a-alny", "ALNY", thesis_strength=0.1)
        decisions = policy.select(_make_report([opp]))
        assert len(decisions) == 1

    def test_allows_zero_thesis_when_disabled(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(min_thesis_score=0.0, max_positions=1))
        opp = _make_opportunity("a-alny", "ALNY", thesis_strength=0.0)
        decisions = policy.select(_make_report([opp]))
        assert len(decisions) == 1


# ===========================================================================
# 3. Gate enabled — blocks None and below-threshold thesis
# ===========================================================================

class TestGateEnabled:
    def test_blocks_none_thesis(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(min_thesis_score=0.5, max_positions=1))
        opp = _make_opportunity("a-alny", "ALNY", thesis_strength=None)
        decisions = policy.select(_make_report([opp]))
        assert len(decisions) == 0

    def test_blocks_below_threshold(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(min_thesis_score=0.5, max_positions=1))
        opp = _make_opportunity("a-alny", "ALNY", thesis_strength=0.4)
        decisions = policy.select(_make_report([opp]))
        assert len(decisions) == 0

    def test_allows_exactly_threshold(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(min_thesis_score=0.5, max_positions=1))
        opp = _make_opportunity("a-alny", "ALNY", thesis_strength=0.5)
        decisions = policy.select(_make_report([opp]))
        assert len(decisions) == 1

    def test_allows_above_threshold(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(min_thesis_score=0.5, max_positions=1))
        opp = _make_opportunity("a-alny", "ALNY", thesis_strength=1.0)
        decisions = policy.select(_make_report([opp]))
        assert len(decisions) == 1

    def test_fallback_to_second_when_first_blocked_by_thesis(self):
        """If top candidate fails thesis gate, second should be selected."""
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(min_thesis_score=0.5, max_positions=1))
        alny = _make_opportunity("a-alny", "ALNY", score=0.90, thesis_strength=None)
        vktx = _make_opportunity("a-vktx", "VKTX", score=0.80, thesis_strength=0.80)
        decisions = policy.select(_make_report([alny, vktx]))
        assert len(decisions) == 1
        assert decisions[0].ticker == "VKTX"

    def test_all_below_threshold_returns_empty(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(min_thesis_score=0.8, max_positions=2))
        opp1 = _make_opportunity("a-alny", "ALNY", score=0.90, thesis_strength=0.5)
        opp2 = _make_opportunity("a-vktx", "VKTX", score=0.85, thesis_strength=None)
        decisions = policy.select(_make_report([opp1, opp2]))
        assert len(decisions) == 0

    def test_partial_pass_returns_only_passing(self):
        """Two candidates, only one passes the gate."""
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(min_thesis_score=0.6, max_positions=2))
        alny = _make_opportunity("a-alny", "ALNY", score=0.90, thesis_strength=0.80)
        vktx = _make_opportunity("a-vktx", "VKTX", score=0.85, thesis_strength=0.40)
        decisions = policy.select(_make_report([alny, vktx]))
        assert len(decisions) == 1
        assert decisions[0].ticker == "ALNY"


# ===========================================================================
# 4. Gate interacts correctly with concentration cap
# ===========================================================================

class TestGateWithConcentrationCap:
    def test_thesis_gate_applied_before_cap_increment(self):
        """Assets blocked by thesis gate don't count against concentration cap."""
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(
            min_thesis_score=0.5,
            max_decisions_per_asset=2,
            max_positions=1,
        ))
        # Week 1: ALNY has thesis=None → blocked; no cap increment
        alny = _make_opportunity("a-alny", "ALNY", score=0.90, thesis_strength=None)
        d1 = policy.select(_make_report([alny], week="2022-01-01"))
        assert len(d1) == 0

        # Week 2: ALNY now has good thesis → should be allowed (cap is still 0)
        alny2 = _make_opportunity("a-alny", "ALNY", score=0.90, thesis_strength=1.0)
        d2 = policy.select(_make_report([alny2], week="2022-02-01"))
        assert len(d2) == 1
        assert policy._per_asset_decisions.get("a-alny", 0) == 1


# ===========================================================================
# 5. MagicMock missing thesis_strength attribute is safe
# ===========================================================================

class TestGateSafety:
    def test_missing_thesis_strength_attr_handled(self):
        """ScoredCandidate missing thesis_strength attr defaults to None → blocked."""
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(min_thesis_score=0.5, max_positions=1))
        opp = MagicMock(spec=[])  # no attributes
        opp.asset_id = "a-alny"
        opp.ticker = "ALNY"
        opp.composite_score = 0.90
        opp.recommended_action = "buy"
        opp.recommended_size_pct = 0.05
        opp.critic_severity = None
        opp.one_line_summary = "test"
        # thesis_strength not set → getattr returns None → blocked
        decisions = policy.select(_make_report([opp]))
        assert len(decisions) == 0
