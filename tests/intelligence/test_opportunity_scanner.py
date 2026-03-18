from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from bve.connectors.market_prices import MarketPriceRecord
from bve.entities.trial import TrialPhase
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace, StoredValuationDiff
from bve.intelligence.opportunity_scanner import OpportunityScanner, OpportunityScannerConfig
from bve.intelligence.ranking import RankingConfig
from bve.intelligence.schemas.signals import Event, StructuredSignal
from bve.intelligence.taxonomy import EventType
from bve.models.catalyst_model import CatalystModel
from bve.pipeline.watchlist_runner import WatchlistAsset


def _seed(store: KnowledgeStore, *, created_at: datetime) -> None:
    event = Event(
        id="evt-1",
        event_type=EventType.TRIAL_READOUT,
        asset_id="asset-1",
        company_id="company-1",
        observed_at=created_at,
        ingested_at=created_at,
        source_type="press_release",
        headline="Positive trial readout",
        confidence=0.95,
    )
    signal = StructuredSignal(
        id="sig-1",
        event_id="evt-1",
        asset_id="asset-1",
        company_id="company-1",
        event_type=EventType.TRIAL_READOUT,
        signal_date=date(2026, 3, 9),
        trial_phase=TrialPhase.PHASE_2,
        primary_endpoint_met=True,
        extraction_model="unit-test",
        extraction_confidence=0.9,
        created_at=created_at,
    )
    diff = StoredValuationDiff(
        run_id="run-diff-1",
        event_id="evt-1",
        asset_id="asset-1",
        valuation_before={"rnpv_millions": 100.0},
        valuation_after={"rnpv_millions": 160.0},
        delta_npv=60.0,
        created_at=created_at,
        valuation_delta={"delta_npv": 60.0},
    )
    trace = SourceTrace(source_type="test", source_ref="seed")
    store.add_event(event, trace, signal_id=signal.id)
    store.add_structured_signal(signal, trace, extraction_result_id="extract-1")
    store.add_valuation_diff(diff, company_id="company-1", source_trace=trace)
    store.upsert_market_price(
        MarketPriceRecord(
            ticker="TEST",
            price_date=signal.signal_date,
            close_usd=10.0,
            adj_close_usd=10.0,
            volume=100_000,
            market_cap_millions=100.0,
        )
    )


def _watchlist_config() -> SimpleNamespace:
    return SimpleNamespace(
        watchlist=[
            WatchlistAsset(
                company_id="company-1",
                asset_id="asset-1",
                ticker="TEST",
                market_cap_millions=100.0,
            )
        ],
        ranking=RankingConfig(use_market_cap_normalization=True, top_n=10),
    )


def test_opportunity_scanner_idempotent_alerts_same_window():
    store = KnowledgeStore(":memory:")
    scanned_at = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    _seed(store, created_at=scanned_at)

    scanner = OpportunityScanner(
        knowledge_store=store,
        config=OpportunityScannerConfig(
            min_composite_score=0.0,
            min_abs_mispricing_pct=1.0,
            alert_window_hours=24,
        ),
    )
    cfg = _watchlist_config()
    first = scanner.scan_from_watchlist_config(cfg, run_id="run-1", scanned_at=scanned_at)
    second = scanner.scan_from_watchlist_config(cfg, run_id="run-2", scanned_at=scanned_at)

    assert len(first.opportunities) == 1
    assert len(first.alerts_emitted) == 1
    assert first.snapshots_written == 1
    assert first.monitor_alerts_emitted == []
    assert len(second.opportunities) == 1
    assert len(second.alerts_emitted) == 0
    assert second.alerts_suppressed_as_duplicate == 1
    assert first.alerts_emitted[0].payload_json["confidence"] == 0.9
    store.close()


def test_opportunity_scanner_deterministic_output():
    scanned_at = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    store_a = KnowledgeStore(":memory:")
    store_b = KnowledgeStore(":memory:")
    _seed(store_a, created_at=scanned_at)
    _seed(store_b, created_at=scanned_at)
    scanner_a = OpportunityScanner(
        knowledge_store=store_a,
        config=OpportunityScannerConfig(
            min_composite_score=0.0,
            min_abs_mispricing_pct=1.0,
            alert_window_hours=24,
        ),
    )
    scanner_b = OpportunityScanner(
        knowledge_store=store_b,
        config=OpportunityScannerConfig(
            min_composite_score=0.0,
            min_abs_mispricing_pct=1.0,
            alert_window_hours=24,
        ),
    )
    cfg = _watchlist_config()

    a = scanner_a.scan_from_watchlist_config(cfg, run_id="run-a", scanned_at=scanned_at)
    b = scanner_b.scan_from_watchlist_config(cfg, run_id="run-b", scanned_at=scanned_at)

    assert [o.model_dump(mode="json") for o in a.opportunities] == [
        o.model_dump(mode="json") for o in b.opportunities
    ]
    assert a.alerts_emitted[0].window == b.alerts_emitted[0].window
    store_a.close()
    store_b.close()


def test_opportunity_scanner_applies_catalyst_weight_for_near_term_event():
    store = KnowledgeStore(":memory:")
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    _seed(store, created_at=now)
    # Add future catalyst event in 10 days.
    future_evt = Event(
        id="evt-future",
        event_type=EventType.TRIAL_READOUT,
        asset_id="asset-1",
        company_id="company-1",
        observed_at=datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc),
        ingested_at=now,
        source_type="manual",
        headline="Expected topline readout window",
        confidence=0.7,
    )
    store.add_event(future_evt, SourceTrace(source_type="test", source_ref="future"))

    scanner = OpportunityScanner(
        knowledge_store=store,
        config=OpportunityScannerConfig(
            min_composite_score=0.0,
            min_abs_mispricing_pct=1.0,
            alert_window_hours=24,
        ),
    )
    cfg = _watchlist_config()
    result = scanner.scan_from_watchlist_config(cfg, run_id="run-catalyst", scanned_at=now)
    opp = result.opportunities[0]
    assert opp.catalyst_type == "trial_readout"
    assert opp.days_to_catalyst == 10
    assert opp.catalyst_importance is not None
    # Score should be catalyst-weighted and remain bounded.
    assert 0.0 <= opp.composite_score <= 1.0
    assert result.alerts_emitted[0].payload_json["days_to_catalyst"] == 10
    store.close()


def test_opportunity_scanner_with_catalyst_model_attaches_valuation_and_snapshot():
    store = KnowledgeStore(":memory:")
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    _seed(store, created_at=now)
    catalyst_model = CatalystModel(store=store)

    scanner = OpportunityScanner(
        knowledge_store=store,
        config=OpportunityScannerConfig(
            min_composite_score=0.0,
            min_abs_mispricing_pct=1.0,
            alert_window_hours=24,
        ),
        catalyst_model=catalyst_model,
    )
    cfg = _watchlist_config()
    result = scanner.scan_from_watchlist_config(cfg, run_id="run-catalyst-model", scanned_at=now)

    assert len(result.opportunities) == 1
    opp = result.opportunities[0]
    assert opp.catalyst_valuation is not None
    assert opp.catalyst_valuation.event_type == "trial_readout"
    assert 0.0 <= opp.catalyst_valuation.p_positive_outcome <= 1.0
    assert opp.base_rank_score is not None
    assert opp.final_rank_score is not None
    assert opp.catalyst_score is not None

    snapshots = store.get_backtest_snapshots(asset_id="asset-1")
    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap.rank_at_signal == opp.rank
    assert snap.composite_score == opp.composite_score
    assert snap.extraction_confidence == opp.extraction_confidence
    assert snap.signal_id == opp.signal_id
    assert snap.signal_timestamp == opp.last_diff_at
    assert snap.catalyst_score == opp.catalyst_score
    store.close()


def test_opportunity_scanner_does_not_write_snapshot_for_non_firing_opportunity():
    store = KnowledgeStore(":memory:")
    scanned_at = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    _seed(store, created_at=scanned_at)

    scanner = OpportunityScanner(
        knowledge_store=store,
        config=OpportunityScannerConfig(
            min_composite_score=0.99,
            min_abs_mispricing_pct=99.0,
            alert_window_hours=24,
        ),
    )
    cfg = _watchlist_config()
    result = scanner.scan_from_watchlist_config(cfg, run_id="run-no-fire", scanned_at=scanned_at)

    assert len(result.alerts_emitted) == 0
    assert result.snapshots_written == 1
    assert store.get_backtest_snapshots(asset_id="asset-1") == []
    store.close()


def test_opportunity_scanner_emits_monitor_alerts_from_prior_snapshot():
    store = KnowledgeStore(":memory:")
    previous = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
    current = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    _seed(store, created_at=previous)
    _seed(store, created_at=current)

    scanner = OpportunityScanner(
        knowledge_store=store,
        config=OpportunityScannerConfig(
            min_composite_score=0.0,
            min_abs_mispricing_pct=1.0,
            alert_window_hours=24,
        ),
    )
    cfg = _watchlist_config()
    first = scanner.scan_from_watchlist_config(cfg, run_id="run-prev", scanned_at=previous)
    second = scanner.scan_from_watchlist_config(cfg, run_id="run-current", scanned_at=current)

    assert first.monitor_alerts_emitted == []
    assert second.monitor_alerts_emitted == []
    assert second.snapshots_written == 1
    store.close()
