from __future__ import annotations

from datetime import date, datetime, timezone

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.opportunity_monitor import OpportunityMonitor, OpportunityMonitorConfig
from bve.intelligence.opportunity_snapshot import OpportunitySnapshotStore
from bve.intelligence.ranking import RankedOpportunity


def _opp(
    *,
    asset_id: str,
    rank: int,
    score: float,
    mispricing: float | None,
    confidence: float = 0.9,
    event_type: str = "trial_readout",
) -> RankedOpportunity:
    return RankedOpportunity(
        rank=rank,
        asset_id=asset_id,
        company_id="company-1",
        event_id=f"evt-{asset_id}",
        ticker="TEST",
        score=score,
        composite_score=score,
        valuation_component=score,
        confidence_component=confidence,
        recency_component=1.0,
        event_type_component=0.8,
        mispricing=mispricing,
        mispricing_score=mispricing,
        confidence=confidence,
        extraction_confidence=confidence,
        days_since_event=2,
        event_priority=0.8,
        delta_npv_millions=50.0,
        signal_event_type=event_type,
        explanation=f"{asset_id} monitor",
    )


def test_opportunity_monitor_emits_expected_change_alerts() -> None:
    store = KnowledgeStore(":memory:")
    snapshot_store = OpportunitySnapshotStore(store)
    snapshot_store.write_snapshots(
        [
            _opp(asset_id="asset-1", rank=12, score=0.40, mispricing=0.10),
            _opp(asset_id="asset-2", rank=4, score=0.50, mispricing=0.10),
        ],
        snapshot_date=date(2026, 3, 8),
        run_id="run-prev",
    )

    monitor = OpportunityMonitor(
        knowledge_store=store,
        config=OpportunityMonitorConfig(
            top_n=10,
            score_change_threshold_pct=30.0,
            mispricing_threshold_pct=25.0,
        ),
        snapshot_store=snapshot_store,
    )
    result = monitor.evaluate(
        [
            _opp(asset_id="asset-1", rank=5, score=0.60, mispricing=0.30),
            _opp(asset_id="asset-2", rank=4, score=0.55, mispricing=0.30),
        ],
        monitored_at=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
        run_id="run-current",
    )

    emitted_types = {record.event_type for record in result.alerts_emitted}
    assert emitted_types == {
        "opportunity_top10_entry",
        "opportunity_score_change",
        "opportunity_mispricing_cross",
    }
    assert len(store.get_opportunity_alerts(limit=10)) == 4
    store.close()


def test_opportunity_monitor_dedupes_same_day_alerts() -> None:
    store = KnowledgeStore(":memory:")
    snapshot_store = OpportunitySnapshotStore(store)
    snapshot_store.write_snapshots(
        [_opp(asset_id="asset-1", rank=12, score=0.40, mispricing=0.10)],
        snapshot_date=date(2026, 3, 8),
        run_id="run-prev",
    )

    monitor = OpportunityMonitor(
        knowledge_store=store,
        config=OpportunityMonitorConfig(top_n=10),
        snapshot_store=snapshot_store,
    )
    monitored_at = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    current = [_opp(asset_id="asset-1", rank=5, score=0.60, mispricing=0.30)]

    first = monitor.evaluate(current, monitored_at=monitored_at, run_id="run-1")
    second = monitor.evaluate(current, monitored_at=monitored_at, run_id="run-2")

    assert len(first.alerts_emitted) == 3
    assert len(second.alerts_emitted) == 0
    assert second.alerts_suppressed_as_duplicate == 3
    store.close()
