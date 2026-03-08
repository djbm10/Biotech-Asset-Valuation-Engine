"""
Tests for AssetRankingEngine.

All tests use pre-loaded data via rank_assets() — no knowledge store required.
Covers score component math, determinism, mispricing mode, config-driven event
scores, per-asset overrides, top_n, --since filter, and explanation generation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from bve.intelligence.ranking import (
    AssetRankingEngine,
    RankingConfig,
    RankedOpportunity,
    RankingResult,
    _recency_score,
    _sigmoid,
    DEFAULT_EVENT_TYPE_SCORES,
)
from bve.intelligence.knowledge_layer import StoredValuationDiff
from bve.pipeline.watchlist_runner import WatchlistAsset

_NOW = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _asset(asset_id="asset-001", company_id="co-001", ticker=None, market_cap=None):
    return WatchlistAsset(
        asset_id=asset_id,
        company_id=company_id,
        ticker=ticker,
        market_cap_millions=market_cap,
    )


def _diff(
    asset_id="asset-001",
    delta_npv: float = 50.0,
    before_npv: float = 200.0,
    created_at: datetime = _NOW,
) -> StoredValuationDiff:
    return StoredValuationDiff(
        run_id=str(uuid.uuid4()),
        event_id="evt-001",
        asset_id=asset_id,
        valuation_before={"rnpv_millions": before_npv},
        valuation_after={"rnpv_millions": before_npv + delta_npv},
        delta_npv=delta_npv,
        created_at=created_at,
    )


def _engine(config: RankingConfig = None) -> AssetRankingEngine:
    return AssetRankingEngine(config or RankingConfig())


class TestSigmoid:
    def test_zero_input(self):
        assert _sigmoid(0.0) == pytest.approx(0.0, abs=1e-9)

    def test_large_input_approaches_one(self):
        assert _sigmoid(100.0) > 0.99

    def test_monotone(self):
        assert _sigmoid(1.0) < _sigmoid(2.0) < _sigmoid(5.0)


class TestRecencyScore:
    def test_at_zero_days(self):
        score = _recency_score(_NOW, _NOW, half_life_days=14.0)
        assert score == pytest.approx(1.0)

    def test_at_half_life(self):
        past = _NOW - timedelta(days=14)
        score = _recency_score(past, _NOW, half_life_days=14.0)
        assert score == pytest.approx(0.5, abs=1e-9)

    def test_at_double_half_life(self):
        past = _NOW - timedelta(days=28)
        score = _recency_score(past, _NOW, half_life_days=14.0)
        assert score == pytest.approx(0.25, abs=1e-9)

    def test_monotone_decays(self):
        s1 = _recency_score(_NOW - timedelta(days=1), _NOW, 14.0)
        s2 = _recency_score(_NOW - timedelta(days=7), _NOW, 14.0)
        s3 = _recency_score(_NOW - timedelta(days=14), _NOW, 14.0)
        assert s1 > s2 > s3

    def test_future_diff_clamped_to_one(self):
        future = _NOW + timedelta(days=5)
        score = _recency_score(future, _NOW, half_life_days=14.0)
        assert score == pytest.approx(1.0)


class TestEventTypeScores:
    def test_known_type_returns_score(self):
        cfg = RankingConfig()
        assert cfg.resolved_event_score("fda_approval") == 1.0
        assert cfg.resolved_event_score("safety_signal") == 1.0
        assert cfg.resolved_event_score("financing") == 0.15

    def test_unknown_type_returns_default(self):
        cfg = RankingConfig()
        assert cfg.resolved_event_score("totally_made_up_event") == 0.3
        assert cfg.resolved_event_score(None) == 0.3

    def test_config_override_replaces_default(self):
        cfg = RankingConfig(event_type_scores={"trial_readout": 0.5})
        assert cfg.resolved_event_score("trial_readout") == 0.5
        # Others unchanged
        assert cfg.resolved_event_score("fda_approval") == 1.0

    def test_config_override_adds_new_type(self):
        cfg = RankingConfig(event_type_scores={"custom_event": 0.99})
        assert cfg.resolved_event_score("custom_event") == 0.99


class TestRankingEngineDeterminism:
    def test_identical_inputs_identical_output(self):
        engine = _engine()
        assets = [_asset("a1"), _asset("a2")]
        diffs = {
            "co-001::a1": [_diff("a1", delta_npv=60.0)],
            "co-001::a2": [_diff("a2", delta_npv=30.0)],
        }
        r1 = engine.rank_assets(assets, diffs_by_asset=diffs, ranked_at=_NOW)
        r2 = engine.rank_assets(assets, diffs_by_asset=diffs, ranked_at=_NOW)
        assert r1.opportunities[0].composite_score == r2.opportunities[0].composite_score
        assert r1.opportunities[0].asset_id == r2.opportunities[0].asset_id

    def test_higher_delta_ranks_higher_in_delta_mode(self):
        engine = _engine(RankingConfig(use_market_cap_normalization=False))
        assets = [_asset("a1"), _asset("a2")]
        diffs = {
            "co-001::a1": [_diff("a1", delta_npv=100.0)],
            "co-001::a2": [_diff("a2", delta_npv=10.0)],
        }
        result = engine.rank_assets(assets, diffs_by_asset=diffs, ranked_at=_NOW)
        assert result.opportunities[0].asset_id == "a1"

    def test_ordering_is_stable_same_score(self):
        engine = _engine()
        assets = [_asset("a1"), _asset("a2")]
        # Same diff → same score → order preserved by insertion
        same_diff = _diff(delta_npv=50.0)
        diffs = {
            "co-001::a1": [same_diff],
            "co-001::a2": [same_diff],
        }
        r = engine.rank_assets(assets, diffs_by_asset=diffs, ranked_at=_NOW)
        # Must not raise; ranks assigned 1 and 2
        assert {o.rank for o in r.opportunities} == {1, 2}


class TestRankingEngineBasicBehavior:
    def test_no_diffs_empty_result(self):
        engine = _engine()
        result = engine.rank_assets(
            [_asset()], diffs_by_asset={}, ranked_at=_NOW
        )
        assert result.opportunities == []
        assert result.assets_skipped_no_diffs == 1
        assert result.assets_with_diffs == 0

    def test_single_asset_gets_rank_1(self):
        engine = _engine()
        result = engine.rank_assets(
            [_asset()],
            diffs_by_asset={"co-001::asset-001": [_diff()]},
            ranked_at=_NOW,
        )
        assert len(result.opportunities) == 1
        assert result.opportunities[0].rank == 1

    def test_top_n_respected(self):
        engine = _engine(RankingConfig(top_n=2))
        assets = [_asset(f"a{i}") for i in range(5)]
        diffs = {f"co-001::a{i}": [_diff(f"a{i}", delta_npv=float(i * 10 + 10))] for i in range(5)}
        result = engine.rank_assets(assets, diffs_by_asset=diffs, ranked_at=_NOW)
        assert len(result.opportunities) == 2

    def test_assets_evaluated_count(self):
        engine = _engine()
        assets = [_asset("a1"), _asset("a2"), _asset("a3")]
        diffs = {"co-001::a1": [_diff("a1")]}  # only a1 has diffs
        result = engine.rank_assets(assets, diffs_by_asset=diffs, ranked_at=_NOW)
        assert result.assets_evaluated == 3
        assert result.assets_with_diffs == 1
        assert result.assets_skipped_no_diffs == 2


class TestMispricingMode:
    def test_mispricing_score_computed_when_market_cap_available(self):
        engine = _engine(RankingConfig(use_market_cap_normalization=True))
        asset = _asset(market_cap=300.0)  # market cap $300M
        diff = _diff(before_npv=200.0, delta_npv=50.0)  # after_rnpv=$250M
        result = engine.rank_assets(
            [asset],
            diffs_by_asset={"co-001::asset-001": [diff]},
            market_caps={"co-001::asset-001": 300.0},
            ranked_at=_NOW,
        )
        opp = result.opportunities[0]
        assert opp.mispricing_score is not None
        assert opp.market_cap_millions == 300.0
        # after_rnpv=$250M, market_cap=$300M → mispricing=(250-300)/300=-0.167 (overvalued)
        assert opp.mispricing_score == pytest.approx(-0.1667, abs=0.001)

    def test_mispricing_none_when_no_market_cap(self):
        engine = _engine(RankingConfig(use_market_cap_normalization=True))
        asset = _asset()  # no market cap
        result = engine.rank_assets(
            [asset],
            diffs_by_asset={"co-001::asset-001": [_diff()]},
            ranked_at=_NOW,
        )
        opp = result.opportunities[0]
        assert opp.mispricing_score is None

    def test_large_cap_scores_lower_than_small_cap_same_delta(self):
        """A $50M delta means more for a $100M rNPV company than a $1000M one."""
        engine = _engine(
            RankingConfig(
                use_market_cap_normalization=True,
                confidence_weight=0.0,
                recency_weight=0.0,
                event_type_weight=0.0,
            )
        )
        assets = [_asset("small"), _asset("large")]
        diffs = {
            "co-001::small": [_diff("small", delta_npv=50.0, before_npv=80.0)],
            "co-001::large": [_diff("large", delta_npv=50.0, before_npv=900.0)],
        }
        market_caps = {
            "co-001::small": 100.0,   # after_rnpv=$130M → mispricing=+30%
            "co-001::large": 1000.0,  # after_rnpv=$950M → mispricing=-5%
        }
        result = engine.rank_assets(
            assets, diffs_by_asset=diffs, market_caps=market_caps, ranked_at=_NOW
        )
        # Small cap undervalued → higher opportunity score
        assert result.opportunities[0].asset_id == "small"

    def test_use_market_cap_false_ignores_market_cap(self):
        engine = _engine(RankingConfig(use_market_cap_normalization=False))
        asset = _asset(market_cap=300.0)
        result = engine.rank_assets(
            [asset],
            diffs_by_asset={"co-001::asset-001": [_diff()]},
            market_caps={"co-001::asset-001": 300.0},
            ranked_at=_NOW,
        )
        opp = result.opportunities[0]
        # mispricing_score should be None when normalization disabled
        assert opp.mispricing_score is None


class TestPerAssetOverrides:
    def test_per_asset_weight_override_applied(self):
        """Asset with event_type_weight=0 should score the same regardless of event type."""
        cfg = RankingConfig(
            valuation_weight=0.0,
            confidence_weight=0.0,
            recency_weight=0.0,
            event_type_weight=1.0,
        )
        engine = _engine(cfg)
        # Asset with override: event_type_weight=0
        a_override = WatchlistAsset(
            asset_id="a-override",
            company_id="co-001",
            ranking_overrides={"event_type_weight": 0.0},
        )
        a_normal = _asset("a-normal")
        diffs = {
            "co-001::a-override": [_diff("a-override")],
            "co-001::a-normal": [_diff("a-normal")],
        }
        result = engine.rank_assets([a_override, a_normal], diffs_by_asset=diffs, ranked_at=_NOW)
        override_opp = next(o for o in result.opportunities if o.asset_id == "a-override")
        # With event_type_weight=0 and all others=0, score should be 0
        assert override_opp.composite_score == pytest.approx(0.0, abs=1e-9)


class TestRankingExplanation:
    def test_explanation_nonempty(self):
        engine = _engine()
        result = engine.rank_assets(
            [_asset()],
            diffs_by_asset={"co-001::asset-001": [_diff()]},
            ranked_at=_NOW,
        )
        assert result.opportunities[0].explanation
        assert len(result.opportunities[0].explanation) > 10

    def test_explanation_contains_asset_id(self):
        engine = _engine()
        result = engine.rank_assets(
            [_asset("my-special-asset")],
            diffs_by_asset={"co-001::my-special-asset": [_diff("my-special-asset")]},
            ranked_at=_NOW,
        )
        assert "my-special-asset" in result.opportunities[0].explanation


class TestRankingResultModel:
    def test_ranked_at_set(self):
        engine = _engine()
        result = engine.rank_assets(
            [_asset()],
            diffs_by_asset={"co-001::asset-001": [_diff()]},
            ranked_at=_NOW,
        )
        assert result.ranked_at == _NOW

    def test_since_filter_preserved(self):
        since = _NOW - timedelta(days=7)
        engine = _engine()
        result = engine.rank_assets(
            [_asset()],
            diffs_by_asset={"co-001::asset-001": [_diff()]},
            ranked_at=_NOW,
            since=since,
        )
        assert result.since_filter == since

    def test_json_serializable(self):
        import json
        engine = _engine()
        result = engine.rank_assets(
            [_asset()],
            diffs_by_asset={"co-001::asset-001": [_diff()]},
            ranked_at=_NOW,
        )
        data = json.loads(result.model_dump_json())
        assert "opportunities" in data
        assert "ranked_at" in data
