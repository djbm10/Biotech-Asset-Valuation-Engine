from __future__ import annotations

from datetime import date, datetime, timezone

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.opportunity_snapshot import (
    OpportunitySnapshotRecord,
    OpportunitySnapshotStore,
)
from bve.intelligence.ranking import RankedOpportunity


def _opp(
    *,
    asset_id: str,
    rank: int,
    score: float,
    mispricing: float | None,
    confidence: float,
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
        days_since_event=3,
        event_priority=0.8,
        delta_npv_millions=50.0,
        signal_event_type=event_type,
        explanation=f"{asset_id} snapshot",
    )


def test_opportunity_snapshot_store_round_trip() -> None:
    store = KnowledgeStore(":memory:")
    snapshot_store = OpportunitySnapshotStore(store)
    snapshot = OpportunitySnapshotRecord(
        snapshot_date=date(2026, 3, 9),
        asset_id="asset-1",
        score=0.72,
        mispricing=0.34,
        confidence=0.91,
        event_type="trial_readout",
        rank=2,
        run_id="run-1",
        created_at=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )

    snapshot_store.write_snapshot(snapshot)
    rows = snapshot_store.get_snapshots(snapshot_date=date(2026, 3, 9))

    assert len(rows) == 1
    assert rows[0].asset_id == "asset-1"
    assert rows[0].score == 0.72
    assert rows[0].mispricing == 0.34
    assert rows[0].rank == 2
    store.close()


def test_opportunity_snapshot_store_writes_ranked_opportunities() -> None:
    store = KnowledgeStore(":memory:")
    snapshot_store = OpportunitySnapshotStore(store)
    written = snapshot_store.write_snapshots(
        [
            _opp(asset_id="asset-1", rank=1, score=0.80, mispricing=0.50, confidence=0.92),
            _opp(asset_id="asset-2", rank=2, score=0.65, mispricing=0.20, confidence=0.88),
        ],
        snapshot_date=date(2026, 3, 9),
        run_id="run-snapshots",
    )

    rows = snapshot_store.get_snapshots(snapshot_date=date(2026, 3, 9), top_n=1)

    assert written == 2
    assert len(rows) == 1
    assert rows[0].asset_id == "asset-1"
    assert snapshot_store.latest_snapshot_date_before(date(2026, 3, 10)) == date(2026, 3, 9)
    store.close()
