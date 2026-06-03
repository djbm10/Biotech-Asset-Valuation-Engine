"""
Sprint 28 — Open-claim entry gate (leading indicator).

Tests for:
1. ScoredCandidate.n_open_claims field
2. ActionableOpportunity.n_open_claims passthrough
3. ReplayPolicyConfig.require_open_claim field + defaults
4. ReplayPolicy.select() open-claim gate behaviour
5. Gate interaction with min_thesis_score and concentration cap
6. historical_replay n_open_claims wired from ThesisTracker.snapshot()
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_opportunity(
    asset_id: str,
    ticker: str,
    score: float = 0.70,
    thesis_strength=None,
    n_open_claims: int = 0,
):
    opp = MagicMock()
    opp.asset_id = asset_id
    opp.ticker = ticker
    opp.composite_score = score
    opp.recommended_action = "buy"
    opp.recommended_size_pct = 0.05
    opp.critic_severity = None
    opp.one_line_summary = "test"
    opp.thesis_strength = thesis_strength
    opp.n_open_claims = n_open_claims
    return opp


def _make_report(opportunities, week: str = "2022-06-01"):
    report = MagicMock()
    report.opportunities = opportunities
    report.week_ending = date.fromisoformat(week)
    return report


# ===========================================================================
# 1. ScoredCandidate.n_open_claims field
# ===========================================================================

class TestScoredCandidateNOpenClaims:
    def test_default_is_zero(self):
        from bve.intelligence.actionable_output import ScoredCandidate
        cand = ScoredCandidate(asset_id="a-test", ticker="TEST", ranking_score=0.5)
        assert cand.n_open_claims == 0

    def test_explicit_value_stored(self):
        from bve.intelligence.actionable_output import ScoredCandidate
        cand = ScoredCandidate(asset_id="a-test", ticker="TEST", ranking_score=0.5, n_open_claims=3)
        assert cand.n_open_claims == 3


# ===========================================================================
# 2. ActionableOpportunity.n_open_claims passthrough
# ===========================================================================

class TestActionableOpportunityPassthrough:
    def test_n_open_claims_passed_through(self):
        from bve.intelligence.actionable_output import ActionableGenerator, ScoredCandidate
        gen = ActionableGenerator()
        cand = ScoredCandidate(
            asset_id="a-alny", ticker="ALNY",
            ranking_score=0.8, opportunity_score=0.7,
            n_open_claims=2,
        )
        report = gen.generate([cand], top_n=5, week_ending=date(2022, 6, 1))
        assert len(report.opportunities) == 1
        assert report.opportunities[0].n_open_claims == 2

    def test_n_open_claims_zero_when_not_set(self):
        from bve.intelligence.actionable_output import ActionableGenerator, ScoredCandidate
        gen = ActionableGenerator()
        cand = ScoredCandidate(
            asset_id="a-alny", ticker="ALNY",
            ranking_score=0.8, opportunity_score=0.7,
        )
        report = gen.generate([cand], top_n=5, week_ending=date(2022, 6, 1))
        assert report.opportunities[0].n_open_claims == 0

    def test_n_open_claims_propagated_for_multiple_candidates(self):
        from bve.intelligence.actionable_output import ActionableGenerator, ScoredCandidate
        gen = ActionableGenerator()
        candidates = [
            ScoredCandidate("a-alny", "ALNY", 0.9, n_open_claims=1),
            ScoredCandidate("a-vktx", "VKTX", 0.7, n_open_claims=0),
        ]
        report = gen.generate(candidates, top_n=5, week_ending=date(2022, 6, 1))
        by_ticker = {opp.ticker: opp.n_open_claims for opp in report.opportunities}
        assert by_ticker["ALNY"] == 1
        assert by_ticker["VKTX"] == 0


# ===========================================================================
# 3. ReplayPolicyConfig — require_open_claim defaults and config
# ===========================================================================

class TestPolicyConfigRequireOpenClaim:
    def test_default_is_false(self):
        from bve.intelligence.replay_policy import ReplayPolicyConfig
        cfg = ReplayPolicyConfig()
        assert cfg.require_open_claim is False

    def test_explicit_true_accepted(self):
        from bve.intelligence.replay_policy import ReplayPolicyConfig
        cfg = ReplayPolicyConfig(require_open_claim=True)
        assert cfg.require_open_claim is True

    def test_mna_profile_has_gate_disabled(self):
        from bve.intelligence.replay_policy import ReplayPolicyConfig
        cfg = ReplayPolicyConfig.mna_profile()
        assert cfg.require_open_claim is False


# ===========================================================================
# 4. Gate disabled — all n_open_claims values pass
# ===========================================================================

class TestOpenClaimGateDisabled:
    def test_allows_zero_open_when_disabled(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(require_open_claim=False, max_positions=1))
        opp = _make_opportunity("a-alny", "ALNY", n_open_claims=0)
        assert len(policy.select(_make_report([opp]))) == 1

    def test_allows_positive_open_when_disabled(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(require_open_claim=False, max_positions=1))
        opp = _make_opportunity("a-alny", "ALNY", n_open_claims=3)
        assert len(policy.select(_make_report([opp]))) == 1


# ===========================================================================
# 5. Gate enabled — blocks zero open claims, allows ≥ 1
# ===========================================================================

class TestOpenClaimGateEnabled:
    def test_blocks_zero_open_claims(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(require_open_claim=True, max_positions=1))
        opp = _make_opportunity("a-alny", "ALNY", n_open_claims=0)
        assert len(policy.select(_make_report([opp]))) == 0

    def test_allows_one_open_claim(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(require_open_claim=True, max_positions=1))
        opp = _make_opportunity("a-alny", "ALNY", n_open_claims=1)
        assert len(policy.select(_make_report([opp]))) == 1

    def test_allows_multiple_open_claims(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(require_open_claim=True, max_positions=1))
        opp = _make_opportunity("a-alny", "ALNY", n_open_claims=4)
        assert len(policy.select(_make_report([opp]))) == 1

    def test_fallback_to_second_when_first_blocked(self):
        """Top candidate (0 open claims) blocked; second (1 open claim) selected."""
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(require_open_claim=True, max_positions=1))
        alny = _make_opportunity("a-alny", "ALNY", score=0.90, n_open_claims=0)
        vktx = _make_opportunity("a-vktx", "VKTX", score=0.80, n_open_claims=1)
        decisions = policy.select(_make_report([alny, vktx]))
        assert len(decisions) == 1
        assert decisions[0].ticker == "VKTX"

    def test_all_zero_open_returns_empty(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(require_open_claim=True, max_positions=2))
        opp1 = _make_opportunity("a-alny", "ALNY", score=0.90, n_open_claims=0)
        opp2 = _make_opportunity("a-vktx", "VKTX", score=0.85, n_open_claims=0)
        assert len(policy.select(_make_report([opp1, opp2]))) == 0

    def test_missing_n_open_claims_attr_treated_as_zero(self):
        """opp with no n_open_claims attr → getattr returns 0 → blocked."""
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(require_open_claim=True, max_positions=1))
        opp = MagicMock(spec=[])
        opp.asset_id = "a-alny"
        opp.ticker = "ALNY"
        opp.composite_score = 0.90
        opp.recommended_action = "buy"
        opp.recommended_size_pct = 0.05
        opp.critic_severity = None
        opp.one_line_summary = "test"
        # n_open_claims not set on spec-restricted mock → getattr returns 0 → blocked
        assert len(policy.select(_make_report([opp]))) == 0


# ===========================================================================
# 6. Gate interaction with min_thesis_score
# ===========================================================================

class TestOpenClaimWithMinThesis:
    def test_both_gates_must_pass(self):
        """require_open_claim=True AND min_thesis_score=0.5: both must pass."""
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(
            require_open_claim=True,
            min_thesis_score=0.5,
            max_positions=1,
        ))
        # Has open claim but low thesis → blocked by thesis gate
        opp_low_thesis = _make_opportunity("a-alny", "ALNY", thesis_strength=0.3, n_open_claims=1)
        assert len(policy.select(_make_report([opp_low_thesis]))) == 0

        # Has good thesis but zero open claims → blocked by open-claim gate
        opp_no_open = _make_opportunity("a-vktx", "VKTX", thesis_strength=0.8, n_open_claims=0)
        assert len(policy.select(_make_report([opp_no_open]))) == 0

    def test_both_gates_pass(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(
            require_open_claim=True,
            min_thesis_score=0.5,
            max_positions=1,
        ))
        opp = _make_opportunity("a-alny", "ALNY", thesis_strength=0.8, n_open_claims=2)
        assert len(policy.select(_make_report([opp]))) == 1


# ===========================================================================
# 7. Gate interaction with concentration cap
# ===========================================================================

class TestOpenClaimWithConcentrationCap:
    def test_blocked_entries_do_not_count_against_cap(self):
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
        policy = ReplayPolicy(ReplayPolicyConfig(
            require_open_claim=True,
            max_decisions_per_asset=2,
            max_positions=1,
        ))
        # Week 1: zero open claims → blocked; cap should not increment
        opp = _make_opportunity("a-alny", "ALNY", n_open_claims=0)
        d1 = policy.select(_make_report([opp], week="2022-01-01"))
        assert len(d1) == 0
        assert policy._per_asset_decisions.get("a-alny", 0) == 0

        # Week 2: now has open claim → allowed
        opp2 = _make_opportunity("a-alny", "ALNY", n_open_claims=1)
        d2 = policy.select(_make_report([opp2], week="2022-02-01"))
        assert len(d2) == 1
        assert policy._per_asset_decisions.get("a-alny", 0) == 1


# ===========================================================================
# 8. Integration: n_open_claims wired from ThesisTracker in replay
# ===========================================================================

class TestNOpenClaimsInReplay:
    def test_n_open_claims_from_snapshot(self, tmp_path):
        """
        ScoredCandidate gets n_open_claims=snap.n_open from ThesisTracker.
        Verify that an asset with 1 open claim gets n_open_claims=1 in the report.
        """
        from bve.intelligence.knowledge_layer import KnowledgeStore
        from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
        from bve.intelligence.actionable_output import ActionableGenerator, ScoredCandidate
        from datetime import timezone

        db = str(tmp_path / "test.db")
        store = KnowledgeStore(db)
        tt = ThesisTracker(store)

        # Add one open claim (no resolution)
        tt.add_claim(
            asset_id="a-alny",
            company_id="co-alny",
            claim_type=ClaimType.ENDPOINT_MET,
            assertion="Phase 3 endpoint will be met",
            created_at=date(2022, 1, 1),
        )

        snap = tt.snapshot("a-alny", as_of_date=date(2022, 6, 1))
        assert snap.n_open == 1

        cand = ScoredCandidate(
            asset_id="a-alny",
            ticker="ALNY",
            ranking_score=0.8,
            n_open_claims=snap.n_open,
        )
        gen = ActionableGenerator()
        report = gen.generate([cand], top_n=5, week_ending=date(2022, 6, 1))
        assert report.opportunities[0].n_open_claims == 1
        store.close()

    def test_open_claim_gate_fires_correctly_with_real_snapshot(self, tmp_path):
        """End-to-end: asset with 1 open claim passes gate; asset with 0 open claims blocked."""
        from bve.intelligence.knowledge_layer import KnowledgeStore
        from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
        from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig

        db = str(tmp_path / "test.db")
        store = KnowledgeStore(db)
        tt = ThesisTracker(store)

        tt.add_claim(
            asset_id="a-alny",
            company_id="co-alny",
            claim_type=ClaimType.ENDPOINT_MET,
            assertion="ALNY Phase 3 claim",
            created_at=date(2022, 1, 1),
        )

        snap_alny = tt.snapshot("a-alny", as_of_date=date(2022, 6, 1))
        snap_vktx = tt.snapshot("a-vktx", as_of_date=date(2022, 6, 1))  # no claims

        policy = ReplayPolicy(ReplayPolicyConfig(require_open_claim=True, max_positions=2))
        opp_alny = _make_opportunity("a-alny", "ALNY", score=0.90, n_open_claims=snap_alny.n_open)
        opp_vktx = _make_opportunity("a-vktx", "VKTX", score=0.85, n_open_claims=snap_vktx.n_open)

        decisions = policy.select(_make_report([opp_alny, opp_vktx]))
        tickers = {d.ticker for d in decisions}
        assert "ALNY" in tickers
        assert "VKTX" not in tickers
        store.close()
