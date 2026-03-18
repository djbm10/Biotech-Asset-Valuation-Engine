"""
Tests for AssetRankingEngine.

All tests use pre-loaded data via rank_assets() unless a DB-specific code path
needs to be exercised.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from bve.connectors.market_prices import MarketPriceRecord
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace, StoredValuationDiff
from bve.intelligence.ranking import (
    AssetRankingEngine,
    RankingConfig,
    _recency_score,
    _sigmoid,
)
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType
from bve.pipeline.watchlist_runner import WatchlistAsset

_NOW = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _asset(
    asset_id: str = "asset-001",
    company_id: str = "co-001",
    ticker: str | None = None,
    market_cap: float | None = None,
) -> WatchlistAsset:
    return WatchlistAsset(
        asset_id=asset_id,
        company_id=company_id,
        ticker=ticker,
        market_cap_millions=market_cap,
    )


def _diff(
    asset_id: str = "asset-001",
    *,
    event_id: str = "evt-001",
    delta_npv: float = 50.0,
    before_npv: float = 200.0,
    created_at: datetime = _NOW,
    market_cap_snapshot_millions: float | None = None,
) -> StoredValuationDiff:
    return StoredValuationDiff(
        run_id=str(uuid.uuid4()),
        event_id=event_id,
        asset_id=asset_id,
        valuation_before={"rnpv_millions": before_npv},
        valuation_after={"rnpv_millions": before_npv + delta_npv},
        delta_npv=delta_npv,
        created_at=created_at,
        market_cap_snapshot_millions=market_cap_snapshot_millions,
    )


def _signal(
    *,
    asset_id: str = "asset-001",
    company_id: str = "co-001",
    event_id: str = "evt-001",
    event_type: EventType = EventType.TRIAL_READOUT,
    signal_date: date = date(2024, 6, 15),
    extraction_confidence: float = 0.8,
) -> StructuredSignal:
    return StructuredSignal(
        id=str(uuid.uuid4()),
        event_id=event_id,
        asset_id=asset_id,
        company_id=company_id,
        event_type=event_type,
        signal_date=signal_date,
        extraction_confidence=extraction_confidence,
        created_at=datetime.combine(signal_date, datetime.min.time(), tzinfo=timezone.utc),
    )


def _engine(config: RankingConfig | None = None) -> AssetRankingEngine:
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
        assert _recency_score(_NOW, _NOW, half_life_days=14.0) == pytest.approx(1.0)

    def test_at_half_life(self):
        past = _NOW - timedelta(days=14)
        assert _recency_score(past, _NOW, half_life_days=14.0) == pytest.approx(0.5, abs=1e-9)

    def test_future_diff_clamped_to_one(self):
        future = _NOW + timedelta(days=5)
        assert _recency_score(future, _NOW, half_life_days=14.0) == pytest.approx(1.0)


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
        assert cfg.resolved_event_score("fda_approval") == 1.0

    def test_missing_calibration_file_falls_back_to_defaults(self):
        cfg = RankingConfig(calibration_path="/tmp/definitely-missing-calibration.yaml")
        assert cfg.resolved_event_score("trial_readout") == 0.8
        assert cfg.resolved_confidence_scaling_factor() == 1.0

    def test_calibration_file_merges_with_defaults(self, tmp_path: Path):
        calibration_path = tmp_path / "ranking_calibration.yaml"
        calibration_path.write_text(
            yaml.safe_dump(
                {
                    "confidence_scaling_factor": 1.25,
                    "event_type_weights": {"trial_readout": 0.61},
                }
            ),
            encoding="utf-8",
        )
        cfg = RankingConfig(calibration_path=str(calibration_path))
        assert cfg.resolved_event_score("trial_readout") == 0.61
        assert cfg.resolved_event_score("fda_approval") == 1.0
        assert cfg.resolved_confidence_scaling_factor() == pytest.approx(1.25)


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

    def test_score_matches_sprint5_formula(self):
        engine = _engine()
        signal = _signal(
            event_type=EventType.FDA_APPROVAL,
            signal_date=date(2024, 6, 10),
            extraction_confidence=0.8,
        )
        diff = _diff(before_npv=100.0, delta_npv=50.0, event_id=signal.event_id)
        result = engine.rank_assets(
            [_asset()],
            diffs_by_asset={"co-001::asset-001": [diff]},
            market_caps={"co-001::asset-001": 100.0},
            signals_by_asset={"co-001::asset-001": signal},
            ranked_at=_NOW,
        )

        opp = result.opportunities[0]
        expected_recency = 0.5 ** (5.0 / 14.0)
        expected_score = (
            0.5 * 0.50
            + 0.8 * 0.25
            + expected_recency * 0.15
            + 1.0 * 0.10
        )

        assert opp.event_id == signal.event_id
        assert opp.mispricing == pytest.approx(0.5, abs=1e-6)
        assert opp.confidence == pytest.approx(0.8, abs=1e-6)
        assert opp.days_since_event == 5
        assert opp.event_priority == pytest.approx(1.0, abs=1e-6)
        assert opp.score == pytest.approx(expected_score, abs=1e-6)
        assert opp.composite_score == pytest.approx(expected_score, abs=1e-6)

    def test_recent_high_confidence_event_ranks_higher(self):
        engine = _engine()
        assets = [_asset("recent"), _asset("stale")]
        recent_signal = _signal(
            asset_id="recent",
            event_id="evt-recent",
            signal_date=date(2024, 6, 14),
            extraction_confidence=0.9,
        )
        stale_signal = _signal(
            asset_id="stale",
            event_id="evt-stale",
            signal_date=date(2024, 5, 25),
            extraction_confidence=0.4,
        )
        diffs = {
            "co-001::recent": [_diff("recent", event_id="evt-recent", before_npv=100.0, delta_npv=50.0)],
            "co-001::stale": [_diff("stale", event_id="evt-stale", before_npv=100.0, delta_npv=50.0)],
        }
        result = engine.rank_assets(
            assets,
            diffs_by_asset=diffs,
            signals_by_asset={
                "co-001::recent": recent_signal,
                "co-001::stale": stale_signal,
            },
            market_caps={
                "co-001::recent": 100.0,
                "co-001::stale": 100.0,
            },
            ranked_at=_NOW,
        )
        assert result.opportunities[0].asset_id == "recent"
        assert result.opportunities[0].score > result.opportunities[1].score

    def test_higher_delta_ranks_higher_in_delta_mode(self):
        engine = _engine(RankingConfig(use_market_cap_normalization=False))
        assets = [_asset("a1"), _asset("a2")]
        diffs = {
            "co-001::a1": [_diff("a1", delta_npv=100.0)],
            "co-001::a2": [_diff("a2", delta_npv=10.0)],
        }
        result = engine.rank_assets(assets, diffs_by_asset=diffs, ranked_at=_NOW)
        assert result.opportunities[0].asset_id == "a1"


class TestRankingEngineBasicBehavior:
    def test_no_diffs_empty_result(self):
        engine = _engine()
        result = engine.rank_assets([_asset()], diffs_by_asset={}, ranked_at=_NOW)
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


class TestMispricingMode:
    def test_mispricing_score_computed_when_market_cap_available(self):
        engine = _engine()
        diff = _diff(before_npv=200.0, delta_npv=50.0)
        result = engine.rank_assets(
            [_asset(market_cap=300.0)],
            diffs_by_asset={"co-001::asset-001": [diff]},
            market_caps={"co-001::asset-001": 300.0},
            ranked_at=_NOW,
        )
        opp = result.opportunities[0]
        assert opp.mispricing_score == pytest.approx(-0.1667, abs=0.001)
        assert opp.mispricing == pytest.approx(-0.166667, abs=0.001)
        assert opp.market_cap_millions == 300.0

    def test_mispricing_none_when_no_market_cap(self):
        engine = _engine()
        result = engine.rank_assets(
            [_asset()],
            diffs_by_asset={"co-001::asset-001": [_diff()]},
            ranked_at=_NOW,
        )
        opp = result.opportunities[0]
        assert opp.mispricing_score is None
        assert opp.mispricing is None

    def test_large_cap_scores_lower_than_small_cap_same_delta(self):
        engine = _engine(
            RankingConfig(
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
        result = engine.rank_assets(
            assets,
            diffs_by_asset=diffs,
            market_caps={
                "co-001::small": 100.0,
                "co-001::large": 1000.0,
            },
            ranked_at=_NOW,
        )
        assert result.opportunities[0].asset_id == "small"

    def test_use_market_cap_false_ignores_market_cap(self):
        engine = _engine(RankingConfig(use_market_cap_normalization=False))
        result = engine.rank_assets(
            [_asset(market_cap=300.0)],
            diffs_by_asset={"co-001::asset-001": [_diff()]},
            market_caps={"co-001::asset-001": 300.0},
            ranked_at=_NOW,
        )
        assert result.opportunities[0].mispricing_score is None

    def test_rank_from_watchlist_uses_market_prices(self):
        store = KnowledgeStore(":memory:")
        try:
            signal = _signal(
                asset_id="asset-001",
                company_id="co-001",
                event_id="evt-market-price",
                signal_date=date(2024, 6, 14),
                extraction_confidence=0.7,
            )
            store.add_structured_signal(
                signal,
                SourceTrace(source_type="test", source_ref="ranking-test"),
                extraction_result_id="extract-1",
            )
            store.add_valuation_diff(
                StoredValuationDiff(
                    run_id=str(uuid.uuid4()),
                    event_id=signal.event_id,
                    asset_id="asset-001",
                    valuation_before={"rnpv_millions": 100.0, "approval_probability": 0.30},
                    valuation_after={"rnpv_millions": 150.0, "approval_probability": 0.40},
                    delta_npv=50.0,
                    created_at=_NOW,
                ),
                company_id="co-001",
                source_trace=SourceTrace(source_type="test", source_ref="ranking-test"),
            )
            store.upsert_market_price(
                MarketPriceRecord(
                    ticker="TST",
                    price_date=date(2024, 6, 14),
                    close_usd=10.0,
                    adj_close_usd=10.0,
                    volume=1000,
                    market_cap_millions=120.0,
                )
            )
            watchlist = type(
                "WatchlistConfig",
                (),
                {
                    "watchlist": [
                        _asset(
                            asset_id="asset-001",
                            company_id="co-001",
                            ticker="TST",
                            market_cap=999.0,
                        )
                    ]
                },
            )()

            result = AssetRankingEngine(knowledge_store=store).rank_from_watchlist_config(
                watchlist,
                ranked_at=_NOW,
            )

            opp = result.opportunities[0]
            assert opp.market_cap_millions == pytest.approx(120.0)
            assert opp.mispricing == pytest.approx(0.25, abs=1e-6)
            assert opp.model_pos == pytest.approx(0.40, abs=1e-6)
            assert opp.implied_pos == pytest.approx(0.32, abs=1e-4)
            assert opp.pos_gap == pytest.approx(-0.08, abs=1e-4)
        finally:
            store.close()


class TestPerAssetOverrides:
    def test_per_asset_weight_override_applied(self):
        cfg = RankingConfig(
            valuation_weight=0.0,
            confidence_weight=0.0,
            recency_weight=0.0,
            event_type_weight=1.0,
        )
        engine = _engine(cfg)
        a_override = WatchlistAsset(
            asset_id="a-override",
            company_id="co-001",
            ranking_overrides={"event_type_weight": 0.0},
        )
        result = engine.rank_assets(
            [a_override, _asset("a-normal")],
            diffs_by_asset={
                "co-001::a-override": [_diff("a-override")],
                "co-001::a-normal": [_diff("a-normal")],
            },
            ranked_at=_NOW,
        )
        override_opp = next(o for o in result.opportunities if o.asset_id == "a-override")
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
