"""
Phase 3 — Point-in-time replay engine and evaluation tracks.

Tests cover:
  3B — SnapshotReplayEngine
       1. run() returns empty list when no snapshots exist
       2. run() returns one view per company with a qualifying snapshot
       3. No-lookahead: snapshot with as_of_date > replay_date is excluded
       4. Companies with no snapshot before replay_date are skipped
       5. Views ranked by sotp_discount descending (rank 1 = best opportunity)
       6. Action "buy" when approved + sotp_discount > 0.20
       7. Action "watch" when sotp_discount > 0.05 (not approved)
       8. Action "no_action" when discount low and not approved
       9. Capital-candidate gate: DRAFT snapshot never gets "buy" action
      10. ReplayDecisionView.is_undervalued matches sotp_discount > 0
      11. ReplayDecisionView.discount_pct_str formats correctly
      12. snapshot_id in view matches the snapshot actually used
      13. snapshot_as_of is the snapshot's as_of_date (may lag replay date)
      14. run_range returns dict keyed by date
      15. run_range uses correct point-in-time data per date

  3C — RankingEvaluator
      16. precision_at_k = 1.0 when all top-k have positive outcomes
      17. precision_at_k = 0.0 when all top-k have negative outcomes
      18. precision_at_k = 0.0 when no decisions in top-k
      19. hit_rate_by_decile returns list of length 10
      20. hit_rate_by_decile: decile 1 uses top-ranked decisions
      21. evaluate() returns RankingResult with all fields
      22. hit_rate_overall matches fraction of positive outcomes

  3C — CalibrationEvaluator
      23. brier_score = 0.0 for perfect predictions
      24. brier_score = 1.0 for maximally wrong predictions
      25. brier_score between 0 and 1 for typical predictions
      26. reliability_buckets returns list of 10 CalibrationBucket
      27. empty bucket has n=0
      28. brier_skill_score > 0 when model outperforms climatology
      29. brier_skill_score ≤ 0 when model is no better than mean
      30. mean_calibration_error is non-negative
      31. evaluate() with empty pairs returns nan scores

  3C — PortfolioEvaluator
      32. evaluate() with all "buy" + positive returns: hit_rate_buy = 1.0
      33. evaluate() with mixed buy returns: hit_rate_buy between 0 and 1
      34. mean_return_buy is mean of buy returns
      35. turnover = n_buy / n_total
      36. no_action decisions do not affect buy metrics
      37. max_drawdown = 0 when all returns positive
      38. max_drawdown > 0 when there are losses
      39. simple_returns filters by action
      40. evaluate() with empty decisions returns zero counts
"""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Optional

import pytest

from bve.entities.company_snapshot import (
    CompanySnapshot,
    ConfidenceMetadata,
    ProvenanceMetadata,
    ReviewerState,
    ValueBucket,
)
from bve.persistence.snapshot_store import SnapshotStore
from bve.persistence.snapshot_replay import (
    BUY_THRESHOLD,
    WATCH_THRESHOLD,
    ReplayDecisionView,
    SnapshotReplayEngine,
)
from bve.analysis.replay_evaluator import (
    CalibrationEvaluator,
    PortfolioEvaluator,
    RankingEvaluator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_snapshot(
    company_id: str,
    ticker: str,
    *,
    as_of: date,
    market_cap: float = 1_000.0,
    sotp_value: float = 1_200.0,    # SOTP > market_cap → undervalued
    cash: float = 200.0,
    reviewer_state: ReviewerState = ReviewerState.DRAFT,
    pack_version: int = 0,
) -> CompanySnapshot:
    """Create a minimal snapshot with known SOTP discount."""
    # net_cash = cash (no debt), modeled_asset = 0 by default
    # sotp = net_cash + modeled_assets + ... = cash + (sotp_value - cash)
    # We achieve target sotp by adding a modeled_asset bucket.
    bucket_value = sotp_value - cash  # net_cash + bucket = sotp_value
    bucket = ValueBucket(
        bucket_id=f"{company_id}_asset",
        bucket_type="modeled_asset",
        label="Main asset",
        value_millions=max(0.0, bucket_value),
        methodology="rnpv",
        source_type="modeled",
        source_ref=f"bve:{company_id}",
        as_of_date=as_of,
        confidence=0.70,
    )
    prov = ProvenanceMetadata(
        pack_version=pack_version,
        created_by="system",
    )
    if reviewer_state == ReviewerState.APPROVED and pack_version < 1:
        prov = ProvenanceMetadata(pack_version=1, created_by="system")

    return CompanySnapshot(
        company_id=company_id,
        company_name=company_id.upper(),
        ticker=ticker,
        as_of_date=as_of,
        market_cap_millions=market_cap,
        cash_millions=cash,
        modeled_assets=[bucket] if bucket_value > 0 else [],
        confidence=ConfidenceMetadata(overall_confidence=0.70),
        provenance=prov,
        reviewer_state=reviewer_state,
    )


@pytest.fixture
def store(tmp_path: Path) -> SnapshotStore:
    return SnapshotStore(tmp_path / "test.db")


@pytest.fixture
def engine(store: SnapshotStore) -> SnapshotReplayEngine:
    return SnapshotReplayEngine(store)


# ---------------------------------------------------------------------------
# 3B — SnapshotReplayEngine
# ---------------------------------------------------------------------------

class TestReplayEngineEmpty:
    """Test 1: empty store returns empty list."""

    def test_empty_store(self, engine):
        decisions = engine.run(["co-a", "co-b"], as_of_date=date(2026, 1, 1))
        assert decisions == []

    def test_unknown_company_skipped(self, store, engine):
        store.insert_snapshot(_make_snapshot("co-a", "CA", as_of=date(2026, 1, 1)))
        decisions = engine.run(["co-a", "no-such-co"], as_of_date=date(2026, 1, 1))
        assert len(decisions) == 1
        assert decisions[0].company_id == "co-a"


class TestReplayEngineNoLookahead:
    """Tests 3–4: point-in-time guarantee."""

    def test_future_snapshot_excluded(self, store, engine):
        # Snapshot dated 2026-06-01, replay on 2026-01-01 → excluded
        store.insert_snapshot(_make_snapshot("co-a", "CA", as_of=date(2026, 6, 1)))
        decisions = engine.run(["co-a"], as_of_date=date(2026, 1, 1))
        assert decisions == []

    def test_snapshot_on_replay_date_included(self, store, engine):
        store.insert_snapshot(_make_snapshot("co-a", "CA", as_of=date(2026, 1, 1)))
        decisions = engine.run(["co-a"], as_of_date=date(2026, 1, 1))
        assert len(decisions) == 1

    def test_earlier_snapshot_used_when_later_exists(self, store, engine):
        snap_jan = _make_snapshot("co-a", "CA", as_of=date(2026, 1, 1), sotp_value=1_200.0)
        snap_apr = _make_snapshot("co-a", "CA", as_of=date(2026, 4, 1), sotp_value=2_000.0)
        store.insert_snapshot(snap_jan)
        store.insert_snapshot(snap_apr)

        # Replay on 2026-02-01 → must use Jan snapshot, not April
        decisions = engine.run(["co-a"], as_of_date=date(2026, 2, 1))
        assert len(decisions) == 1
        assert decisions[0].snapshot_id == snap_jan.snapshot_id
        assert decisions[0].snapshot_as_of == date(2026, 1, 1)


class TestReplayEngineRanking:
    """Test 5: ranking by sotp_discount."""

    def test_ranked_by_discount_descending(self, store, engine):
        # co-a: discount = (1_300 - 1_000)/1_000 = 30%
        # co-b: discount = (1_100 - 1_000)/1_000 = 10%
        # co-c: discount = (800 - 1_000)/1_000 = -20% (overvalued)
        store.insert_snapshot(_make_snapshot("co-a", "CA", as_of=date(2026, 1, 1),
                                            market_cap=1_000.0, sotp_value=1_300.0))
        store.insert_snapshot(_make_snapshot("co-b", "CB", as_of=date(2026, 1, 1),
                                            market_cap=1_000.0, sotp_value=1_100.0))
        store.insert_snapshot(_make_snapshot("co-c", "CC", as_of=date(2026, 1, 1),
                                            market_cap=1_000.0, sotp_value=800.0))
        decisions = engine.run(["co-a", "co-b", "co-c"], as_of_date=date(2026, 1, 1))

        assert len(decisions) == 3
        assert decisions[0].company_id == "co-a"  # rank 1 — highest discount
        assert decisions[1].company_id == "co-b"
        assert decisions[2].company_id == "co-c"  # rank 3 — overvalued
        assert [d.rank for d in decisions] == [1, 2, 3]


class TestReplayEngineActions:
    """Tests 6–9: action assignment."""

    def test_buy_when_approved_and_high_discount(self, store, engine):
        # sotp_discount ≈ 30% (> BUY_THRESHOLD), APPROVED
        snap = _make_snapshot("co-a", "CA", as_of=date(2026, 1, 1),
                              market_cap=1_000.0, sotp_value=1_300.0,
                              reviewer_state=ReviewerState.APPROVED, pack_version=1)
        store.insert_snapshot(snap)
        decisions = engine.run(["co-a"], as_of_date=date(2026, 1, 1))
        assert decisions[0].action == "buy"

    def test_watch_when_not_approved_but_discount_above_watch(self, store, engine):
        # sotp_discount ≈ 10% (> WATCH_THRESHOLD), DRAFT
        snap = _make_snapshot("co-a", "CA", as_of=date(2026, 1, 1),
                              market_cap=1_000.0, sotp_value=1_100.0,
                              reviewer_state=ReviewerState.DRAFT)
        store.insert_snapshot(snap)
        decisions = engine.run(["co-a"], as_of_date=date(2026, 1, 1))
        assert decisions[0].action == "watch"

    def test_no_action_when_discount_too_low(self, store, engine):
        # sotp_discount ≈ 2% (< WATCH_THRESHOLD)
        snap = _make_snapshot("co-a", "CA", as_of=date(2026, 1, 1),
                              market_cap=1_000.0, sotp_value=1_020.0)
        store.insert_snapshot(snap)
        decisions = engine.run(["co-a"], as_of_date=date(2026, 1, 1))
        assert decisions[0].action == "no_action"

    def test_draft_never_gets_buy_even_with_high_discount(self, store, engine):
        # DRAFT + 30% discount → watch (not buy)
        snap = _make_snapshot("co-a", "CA", as_of=date(2026, 1, 1),
                              market_cap=1_000.0, sotp_value=1_300.0,
                              reviewer_state=ReviewerState.DRAFT)
        store.insert_snapshot(snap)
        decisions = engine.run(["co-a"], as_of_date=date(2026, 1, 1))
        assert decisions[0].action == "watch"
        assert not decisions[0].is_capital_candidate

    def test_approved_watch_when_discount_between_thresholds(self, store, engine):
        # Approved but discount = 12% (> WATCH but < BUY) → watch
        snap = _make_snapshot("co-a", "CA", as_of=date(2026, 1, 1),
                              market_cap=1_000.0, sotp_value=1_120.0,
                              reviewer_state=ReviewerState.APPROVED, pack_version=1)
        store.insert_snapshot(snap)
        decisions = engine.run(["co-a"], as_of_date=date(2026, 1, 1))
        assert decisions[0].action == "watch"


class TestReplayDecisionViewProperties:
    """Tests 10–13: view properties."""

    @pytest.fixture(autouse=True)
    def _insert(self, store, engine):
        snap = _make_snapshot("co-a", "CA", as_of=date(2026, 1, 1),
                              market_cap=1_000.0, sotp_value=1_200.0)
        store.insert_snapshot(snap)
        self._decisions = engine.run(["co-a"], as_of_date=date(2026, 1, 1))
        self._snap = snap

    def test_is_undervalued_true_when_discount_positive(self):
        d = self._decisions[0]
        assert d.sotp_discount > 0
        assert d.is_undervalued

    def test_discount_pct_str_format(self):
        d = self._decisions[0]
        assert d.discount_pct_str.startswith("+") or d.discount_pct_str.startswith("-")
        assert "%" in d.discount_pct_str

    def test_snapshot_id_matches(self):
        d = self._decisions[0]
        assert d.snapshot_id == self._snap.snapshot_id

    def test_snapshot_as_of_matches(self):
        d = self._decisions[0]
        assert d.snapshot_as_of == date(2026, 1, 1)


class TestRunRange:
    """Tests 14–15: run_range."""

    def test_run_range_returns_dict(self, store, engine):
        store.insert_snapshot(_make_snapshot("co-a", "CA", as_of=date(2026, 1, 1)))
        dates = [date(2026, 1, 1), date(2026, 4, 1)]
        result = engine.run_range(["co-a"], dates)
        assert isinstance(result, dict)
        assert set(result.keys()) == {date(2026, 1, 1), date(2026, 4, 1)}

    def test_run_range_point_in_time(self, store, engine):
        snap_jan = _make_snapshot("co-a", "CA", as_of=date(2026, 1, 1), sotp_value=1_200.0)
        snap_apr = _make_snapshot("co-a", "CA", as_of=date(2026, 4, 1), sotp_value=2_000.0)
        store.insert_snapshot(snap_jan)
        store.insert_snapshot(snap_apr)

        result = engine.run_range(["co-a"], [date(2026, 1, 1), date(2026, 6, 1)])
        # Jan replay uses Jan snapshot; June replay uses Apr snapshot (latest by then)
        jan_snap_id = result[date(2026, 1, 1)][0].snapshot_id
        jun_snap_id = result[date(2026, 6, 1)][0].snapshot_id
        assert jan_snap_id == snap_jan.snapshot_id
        assert jun_snap_id == snap_apr.snapshot_id


# ---------------------------------------------------------------------------
# 3C — RankingEvaluator
# ---------------------------------------------------------------------------

class TestRankingEvaluator:
    """Tests 16–22."""

    def test_precision_at_k_all_positive(self):
        pairs = [(1, 0.10), (2, 0.05), (3, -0.10)]
        assert RankingEvaluator.precision_at_k(pairs, k=2) == 1.0

    def test_precision_at_k_all_negative(self):
        pairs = [(1, -0.10), (2, -0.05)]
        assert RankingEvaluator.precision_at_k(pairs, k=2) == 0.0

    def test_precision_at_k_empty_top_k(self):
        # All ranks > k
        pairs = [(5, 0.10), (6, 0.20)]
        assert RankingEvaluator.precision_at_k(pairs, k=2) == 0.0

    def test_hit_rate_by_decile_length(self):
        pairs = [(i, 0.10 if i % 2 == 0 else -0.10) for i in range(1, 21)]
        rates = RankingEvaluator.hit_rate_by_decile(pairs, n_deciles=10)
        assert len(rates) == 10

    def test_hit_rate_by_decile_uses_top_ranks(self):
        # Top 2 (rank 1, 2) both positive; bottom 2 (rank 3, 4) negative
        pairs = [(1, 0.10), (2, 0.15), (3, -0.10), (4, -0.05)]
        rates = RankingEvaluator.hit_rate_by_decile(pairs, n_deciles=4)
        # decile 1 = rank 1 → hit_rate 1.0
        assert rates[0] == pytest.approx(1.0)
        # decile 4 = rank 4 → hit_rate 0.0
        assert rates[3] == pytest.approx(0.0)

    def test_evaluate_returns_ranking_result(self):
        pairs = [(1, 0.10), (2, -0.05), (3, 0.08)]
        result = RankingEvaluator.evaluate(pairs, k=2)
        assert result.k == 2
        assert 0.0 <= result.precision_at_k <= 1.0
        assert result.n_evaluated == 3

    def test_hit_rate_overall_correct(self):
        pairs = [(1, 0.10), (2, -0.05), (3, 0.08), (4, -0.02)]
        result = RankingEvaluator.evaluate(pairs, k=2)
        # 2 out of 4 positive → 0.5
        assert result.hit_rate_overall == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 3C — CalibrationEvaluator
# ---------------------------------------------------------------------------

class TestCalibrationEvaluator:
    """Tests 23–31."""

    def test_brier_perfect(self):
        # Perfect: predict 1.0 for outcome=1, 0.0 for outcome=0
        pairs = [(1.0, 1), (0.0, 0), (1.0, 1)]
        assert CalibrationEvaluator.brier_score(pairs) == pytest.approx(0.0)

    def test_brier_worst(self):
        # Worst: predict 1.0 for outcome=0, 0.0 for outcome=1
        pairs = [(1.0, 0), (0.0, 1)]
        assert CalibrationEvaluator.brier_score(pairs) == pytest.approx(1.0)

    def test_brier_typical(self):
        pairs = [(0.7, 1), (0.3, 0), (0.6, 1), (0.4, 0)]
        bs = CalibrationEvaluator.brier_score(pairs)
        assert 0.0 < bs < 1.0

    def test_reliability_buckets_length(self):
        pairs = [(i / 10, 1 if i > 5 else 0) for i in range(10)]
        buckets = CalibrationEvaluator.reliability_buckets(pairs, n_bins=10)
        assert len(buckets) == 10

    def test_empty_bucket_has_n_zero(self):
        # Only prediction near 0.95 → all other bins are empty
        pairs = [(0.95, 1), (0.95, 0)]
        buckets = CalibrationEvaluator.reliability_buckets(pairs, n_bins=10)
        empty = [b for b in buckets if b.n == 0]
        assert len(empty) > 0

    def test_skill_score_positive_when_better_than_climatology(self):
        # Perfect prediction → skill > 0
        pairs = [(1.0, 1), (0.0, 0), (1.0, 1), (0.0, 0)]
        result = CalibrationEvaluator.evaluate(pairs)
        assert result.brier_skill_score is not None
        assert result.brier_skill_score > 0

    def test_skill_score_zero_when_always_predict_mean(self):
        # Always predict mean outcome = 0.5 → skill = 0
        pairs = [(0.5, 1), (0.5, 0), (0.5, 1), (0.5, 0)]
        result = CalibrationEvaluator.evaluate(pairs)
        assert result.brier_skill_score is not None
        assert result.brier_skill_score == pytest.approx(0.0, abs=1e-9)

    def test_mce_non_negative(self):
        pairs = [(0.7, 1), (0.3, 0), (0.6, 1)]
        result = CalibrationEvaluator.evaluate(pairs)
        assert result.mean_calibration_error >= 0.0

    def test_evaluate_empty_returns_nan_scores(self):
        result = CalibrationEvaluator.evaluate([])
        assert math.isnan(result.brier_score)
        assert result.brier_skill_score is None
        assert result.n_pairs == 0


# ---------------------------------------------------------------------------
# 3C — PortfolioEvaluator
# ---------------------------------------------------------------------------

class TestPortfolioEvaluator:
    """Tests 32–40."""

    def test_hit_rate_buy_all_positive(self):
        decisions = [("buy", 0.10), ("buy", 0.05), ("buy", 0.20)]
        result = PortfolioEvaluator.evaluate(decisions)
        assert result.hit_rate_buy == pytest.approx(1.0)

    def test_hit_rate_buy_mixed(self):
        decisions = [("buy", 0.10), ("buy", -0.05), ("buy", 0.15), ("buy", -0.03)]
        result = PortfolioEvaluator.evaluate(decisions)
        assert result.hit_rate_buy == pytest.approx(0.5)

    def test_mean_return_buy(self):
        decisions = [("buy", 0.10), ("buy", 0.20)]
        result = PortfolioEvaluator.evaluate(decisions)
        assert result.mean_return_buy == pytest.approx(0.15)

    def test_turnover(self):
        decisions = [("buy", 0.10), ("watch", 0.05), ("no_action", 0.0), ("buy", 0.08)]
        result = PortfolioEvaluator.evaluate(decisions)
        assert result.n_buy == 2
        assert result.n_decisions == 4
        assert result.turnover == pytest.approx(0.5)

    def test_no_action_excluded_from_buy_metrics(self):
        decisions = [("no_action", -0.50), ("no_action", -0.50), ("buy", 0.10)]
        result = PortfolioEvaluator.evaluate(decisions)
        assert result.n_buy == 1
        assert result.mean_return_buy == pytest.approx(0.10)

    def test_max_drawdown_zero_when_all_positive(self):
        decisions = [("buy", 0.10), ("buy", 0.05), ("buy", 0.20)]
        result = PortfolioEvaluator.evaluate(decisions)
        assert result.max_drawdown == pytest.approx(0.0)

    def test_max_drawdown_positive_when_losses(self):
        # Drawdown sequence: up, down, up
        decisions = [("buy", 0.10), ("buy", -0.20), ("buy", 0.15)]
        result = PortfolioEvaluator.evaluate(decisions)
        assert result.max_drawdown is not None
        assert result.max_drawdown > 0.0

    def test_simple_returns_filter_by_action(self):
        decisions = [("buy", 0.10), ("watch", 0.05), ("buy", -0.03)]
        buy_rets = PortfolioEvaluator.simple_returns(decisions, action_filter="buy")
        assert buy_rets == pytest.approx([0.10, -0.03])

    def test_evaluate_empty_decisions(self):
        result = PortfolioEvaluator.evaluate([])
        assert result.n_decisions == 0
        assert result.n_buy == 0
        assert result.mean_return_buy is None
        assert result.turnover == pytest.approx(0.0)
