"""
Sprint 24 — Per-Asset Concentration Cap
Tests for ReplayPolicyConfig.max_decisions_per_asset and
ReplayPolicy.select() concentration gate.
"""
from __future__ import annotations

from dataclasses import field
from datetime import date, timedelta
from typing import Optional
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_opportunity(asset_id: str, ticker: str, score: float = 0.70):
    """Build a minimal ScoredCandidate-like mock."""
    opp = MagicMock()
    opp.asset_id = asset_id
    opp.ticker = ticker
    opp.composite_score = score
    opp.recommended_action = "buy"
    opp.recommended_size_pct = 0.05
    opp.critic_severity = None
    opp.one_line_summary = "test"
    return opp


def _make_report(opportunities, week: str = "2022-06-01"):
    report = MagicMock()
    report.opportunities = opportunities
    report.week_ending = date.fromisoformat(week)
    return report


# ---------------------------------------------------------------------------
# ReplayPolicyConfig — field exists and defaults correctly
# ---------------------------------------------------------------------------

class TestPolicyConfigField:
    def test_max_decisions_per_asset_default_is_zero(self):
        from bve.intelligence.replay_policy import ReplayPolicyConfig
        cfg = ReplayPolicyConfig()
        assert cfg.max_decisions_per_asset == 0

    def test_max_decisions_per_asset_set(self):
        from bve.intelligence.replay_policy import ReplayPolicyConfig
        cfg = ReplayPolicyConfig(max_decisions_per_asset=15)
        assert cfg.max_decisions_per_asset == 15

    def test_mna_profile_has_no_cap_by_default(self):
        from bve.intelligence.replay_policy import ReplayPolicyConfig
        cfg = ReplayPolicyConfig.mna_profile()
        assert cfg.max_decisions_per_asset == 0


# ---------------------------------------------------------------------------
# ReplayPolicy — reset_run_state initialises counter
# ---------------------------------------------------------------------------

class TestRunStateReset:
    def test_per_asset_decisions_initialised_empty(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(max_decisions_per_asset=5))
        assert policy._per_asset_decisions == {}

    def test_reset_clears_counter(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(max_decisions_per_asset=5))
        # Manually populate
        policy._per_asset_decisions["a-alny"] = 3
        policy.reset_run_state()
        assert policy._per_asset_decisions == {}


# ---------------------------------------------------------------------------
# ReplayPolicy.select() — concentration cap gating
# ---------------------------------------------------------------------------

class TestConcentrationCap:
    def test_cap_zero_allows_unlimited(self):
        """max_decisions_per_asset=0 means no cap — same asset selected every step."""
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(max_decisions_per_asset=0, max_positions=1))
        opp = _make_opportunity("a-alny", "ALNY", score=0.80)
        # Call select 30 times for same asset
        total = 0
        for i in range(30):
            week = (date(2022, 1, 1) + timedelta(weeks=i)).isoformat()
            report = _make_report([opp], week=week)
            decisions = policy.select(report)
            total += len(decisions)
        assert total == 30

    def test_cap_one_allows_only_first_decision(self):
        """max_decisions_per_asset=1 → asset blocked after first selection."""
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(max_decisions_per_asset=1, max_positions=1))
        # Two different weeks
        opp = _make_opportunity("a-alny", "ALNY", score=0.80)
        r1 = _make_report([opp], week="2022-01-01")
        r2 = _make_report([opp], week="2022-02-01")
        d1 = policy.select(r1)
        d2 = policy.select(r2)
        assert len(d1) == 1
        assert len(d2) == 0

    def test_cap_blocks_asset_after_n_decisions(self):
        """Asset blocked after exactly max_decisions_per_asset decisions."""
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        cap = 3
        policy = ReplayPolicy(ReplayPolicyConfig(max_decisions_per_asset=cap, max_positions=1))
        opp = _make_opportunity("a-alny", "ALNY", score=0.80)
        counts = []
        for i in range(5):
            week = (date(2022, 1, 1) + timedelta(weeks=i)).isoformat()
            report = _make_report([opp], week=week)
            d = policy.select(report)
            counts.append(len(d))
        # First 3 selected, last 2 blocked
        assert counts == [1, 1, 1, 0, 0]

    def test_cap_counts_per_asset_independently(self):
        """Cap applies per asset — different assets have independent counters."""
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(max_decisions_per_asset=2, max_positions=2))
        alny = _make_opportunity("a-alny", "ALNY", score=0.80)
        vktx = _make_opportunity("a-vktx", "VKTX", score=0.75)
        # 3 rounds: both assets selected (up to their cap)
        decisions_alny = 0
        decisions_vktx = 0
        for i in range(4):
            week = (date(2022, 1, 1) + timedelta(weeks=i)).isoformat()
            report = _make_report([alny, vktx], week=week)
            decisions = policy.select(report)
            for d in decisions:
                if d.asset_id == "a-alny":
                    decisions_alny += 1
                elif d.asset_id == "a-vktx":
                    decisions_vktx += 1
        assert decisions_alny == 2
        assert decisions_vktx == 2

    def test_cap_counter_increments_correctly(self):
        """_per_asset_decisions tracks selected assets accurately."""
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(max_decisions_per_asset=10, max_positions=1))
        opp = _make_opportunity("a-alny", "ALNY", score=0.80)
        for i in range(4):
            week = (date(2022, 1, 1) + timedelta(weeks=i)).isoformat()
            report = _make_report([opp], week=week)
            policy.select(report)
        assert policy._per_asset_decisions["a-alny"] == 4

    def test_fallback_to_second_choice_when_cap_hit(self):
        """When top asset is capped, second-best asset should be selected."""
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(max_decisions_per_asset=1, max_positions=1))
        alny = _make_opportunity("a-alny", "ALNY", score=0.80)
        vktx = _make_opportunity("a-vktx", "VKTX", score=0.75)
        # Week 1: ALNY selected (higher score)
        r1 = _make_report([alny, vktx], week="2022-01-01")
        d1 = policy.select(r1)
        assert d1[0].ticker == "ALNY"
        # Week 2: ALNY capped, VKTX selected
        r2 = _make_report([alny, vktx], week="2022-02-01")
        d2 = policy.select(r2)
        assert len(d2) == 1
        assert d2[0].ticker == "VKTX"

    def test_reset_clears_cap_state(self):
        """After reset_run_state(), previously-capped asset is selectable again."""
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(max_decisions_per_asset=1, max_positions=1))
        opp = _make_opportunity("a-alny", "ALNY", score=0.80)
        # Select once (cap hit)
        d1 = policy.select(_make_report([opp], week="2022-01-01"))
        d2 = policy.select(_make_report([opp], week="2022-02-01"))
        assert len(d1) == 1 and len(d2) == 0
        # Reset and retry
        policy.reset_run_state()
        d3 = policy.select(_make_report([opp], week="2022-03-01"))
        assert len(d3) == 1


# ---------------------------------------------------------------------------
# Graduation run metrics validation
# ---------------------------------------------------------------------------

class TestGraduationMetrics:
    """Verify the concentration-capped run achieves graduation N criterion."""

    def test_cap_run_returns_n_above_threshold(self):
        """Integration: run a mini-replay with cap; verify N ≥ 3 decisions."""
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(max_decisions_per_asset=2, max_positions=2))
        candidates = [
            _make_opportunity("a-alny", "ALNY", score=0.80),
            _make_opportunity("a-vktx", "VKTX", score=0.78),
            _make_opportunity("a-kymr", "KYMR", score=0.75),
        ]
        total_decisions = 0
        for i in range(10):
            week = (date(2022, 1, 1) + timedelta(weeks=i)).isoformat()
            report = _make_report(candidates, week=week)
            decisions = policy.select(report)
            total_decisions += len(decisions)
        assert total_decisions >= 3

    def test_concentration_below_cap_threshold(self):
        """With cap=2 and 3 assets, no asset exceeds 2 decisions."""
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(max_decisions_per_asset=2, max_positions=3))
        candidates = [
            _make_opportunity("a-alny", "ALNY", score=0.80),
            _make_opportunity("a-vktx", "VKTX", score=0.78),
            _make_opportunity("a-kymr", "KYMR", score=0.75),
        ]
        for i in range(10):
            week = (date(2022, 1, 1) + timedelta(weeks=i)).isoformat()
            policy.select(_make_report(candidates, week=week))
        assert max(policy._per_asset_decisions.values(), default=0) <= 2
