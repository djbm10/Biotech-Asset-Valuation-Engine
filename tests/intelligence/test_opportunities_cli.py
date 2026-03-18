from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from bve.cli.opportunities import main as opportunities_main
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace
from bve.intelligence.opportunity_snapshot import OpportunitySnapshotStore
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType


def _signal(*, asset_id: str, event_id: str, signal_date: date, confidence: float) -> StructuredSignal:
    return StructuredSignal(
        id=str(uuid.uuid4()),
        event_id=event_id,
        asset_id=asset_id,
        company_id=f"co-{asset_id}",
        event_type=EventType.TRIAL_READOUT,
        signal_date=signal_date,
        extraction_confidence=confidence,
        created_at=datetime.combine(signal_date, datetime.min.time(), tzinfo=timezone.utc),
    )


def test_opportunities_cli_prints_latest_snapshot(tmp_path: Path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(str(db_path))
    try:
        signal_a = _signal(
            asset_id="asset-a",
            event_id="evt-a",
            signal_date=date(2026, 3, 9),
            confidence=0.78,
        )
        signal_b = _signal(
            asset_id="asset-b",
            event_id="evt-b",
            signal_date=date(2026, 3, 8),
            confidence=0.74,
        )
        store.add_structured_signal(
            signal_a,
            SourceTrace(source_type="test", source_ref="opportunities-cli"),
            extraction_result_id="extract-a",
        )
        store.add_structured_signal(
            signal_b,
            SourceTrace(source_type="test", source_ref="opportunities-cli"),
            extraction_result_id="extract-b",
        )
        snapshot_store = OpportunitySnapshotStore(store)
        snapshot_store.write_snapshots(
            [
                type(
                    "SnapshotOpp",
                    (),
                    {
                        "rank": 1,
                        "asset_id": "asset-a",
                        "company_id": "co-a",
                        "event_id": "evt-a",
                        "ticker": "AAA",
                        "score": 0.16,
                        "composite_score": 0.16,
                        "valuation_component": 0.16,
                        "confidence_component": 0.78,
                        "recency_component": 1.0,
                        "event_type_component": 0.8,
                        "mispricing": 0.42,
                        "mispricing_score": 0.42,
                        "confidence": 0.78,
                        "extraction_confidence": 0.78,
                        "days_since_event": 2,
                        "event_priority": 0.8,
                        "delta_npv_millions": 20.0,
                        "signal_event_type": "trial_readout",
                    },
                )(),
                type(
                    "SnapshotOpp",
                    (),
                    {
                        "rank": 2,
                        "asset_id": "asset-b",
                        "company_id": "co-b",
                        "event_id": "evt-b",
                        "ticker": "BBB",
                        "score": 0.13,
                        "composite_score": 0.13,
                        "valuation_component": 0.13,
                        "confidence_component": 0.74,
                        "recency_component": 1.0,
                        "event_type_component": 0.8,
                        "mispricing": 0.31,
                        "mispricing_score": 0.31,
                        "confidence": 0.74,
                        "extraction_confidence": 0.74,
                        "days_since_event": 3,
                        "event_priority": 0.8,
                        "delta_npv_millions": 20.0,
                        "signal_event_type": "fda_decision",
                    },
                )(),
            ],
            snapshot_date=date(2026, 3, 10),
            run_id="run-1",
        )
    finally:
        store.close()

    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-opportunities",
            "--db",
            str(db_path),
            "--top",
            "1",
        ],
    )
    opportunities_main()
    out = capsys.readouterr().out
    assert "Snapshot date: 2026-03-10" in out
    assert "asset-a" in out
    assert "0.16" in out
    assert "trial_readout" in out
    assert "asset-b" not in out
