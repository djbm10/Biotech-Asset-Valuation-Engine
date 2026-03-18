from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from bve.cli.rank import _resolve_watchlist_path, main as rank_main
from bve.connectors.market_prices import MarketPriceRecord
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace, StoredValuationDiff
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType


def _signal(*, asset_id: str, company_id: str, event_id: str, signal_date: date, confidence: float):
    return StructuredSignal(
        id=str(uuid.uuid4()),
        event_id=event_id,
        asset_id=asset_id,
        company_id=company_id,
        event_type=EventType.TRIAL_READOUT,
        signal_date=signal_date,
        extraction_confidence=confidence,
        created_at=datetime.combine(signal_date, datetime.min.time(), tzinfo=timezone.utc),
    )


def _diff(*, asset_id: str, event_id: str, before_npv: float, delta_npv: float):
    return StoredValuationDiff(
        run_id=str(uuid.uuid4()),
        event_id=event_id,
        asset_id=asset_id,
        valuation_before={"rnpv_millions": before_npv},
        valuation_after={"rnpv_millions": before_npv + delta_npv},
        delta_npv=delta_npv,
        created_at=datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc),
    )


def test_resolve_watchlist_path_supports_example_basename():
    resolved = _resolve_watchlist_path("watchlist_stage1.yaml")
    assert resolved.name == "watchlist_stage1.yaml"
    assert resolved.exists()


def test_rank_cli_prints_top_ranked_asset(tmp_path: Path, monkeypatch, capsys):
    db_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(str(db_path))
    try:
        recent_signal = _signal(
            asset_id="asset-recent",
            company_id="co-1",
            event_id="evt-recent",
            signal_date=date(2024, 6, 14),
            confidence=0.9,
        )
        stale_signal = _signal(
            asset_id="asset-stale",
            company_id="co-2",
            event_id="evt-stale",
            signal_date=date(2024, 5, 20),
            confidence=0.4,
        )
        store.add_structured_signal(
            recent_signal,
            SourceTrace(source_type="test", source_ref="rank-cli"),
            extraction_result_id="extract-recent",
        )
        store.add_structured_signal(
            stale_signal,
            SourceTrace(source_type="test", source_ref="rank-cli"),
            extraction_result_id="extract-stale",
        )
        store.add_valuation_diff(
            _diff(asset_id="asset-recent", event_id="evt-recent", before_npv=100.0, delta_npv=50.0),
            company_id="co-1",
            source_trace=SourceTrace(source_type="test", source_ref="rank-cli"),
        )
        store.add_valuation_diff(
            _diff(asset_id="asset-stale", event_id="evt-stale", before_npv=100.0, delta_npv=50.0),
            company_id="co-2",
            source_trace=SourceTrace(source_type="test", source_ref="rank-cli"),
        )
        store.upsert_market_price(
            MarketPriceRecord(
                ticker="RANK1",
                price_date=date(2024, 6, 14),
                close_usd=10.0,
                adj_close_usd=10.0,
                volume=10_000,
                market_cap_millions=100.0,
            )
        )
        store.upsert_market_price(
            MarketPriceRecord(
                ticker="RANK2",
                price_date=date(2024, 5, 20),
                close_usd=10.0,
                adj_close_usd=10.0,
                volume=10_000,
                market_cap_millions=100.0,
            )
        )
    finally:
        store.close()

    watchlist_path = tmp_path / "watchlist_rank.yaml"
    watchlist_path.write_text(
        yaml.safe_dump(
            {
                "knowledge_db_path": str(db_path),
                "watchlist": [
                    {"company_id": "co-1", "asset_id": "asset-recent", "ticker": "RANK1"},
                    {"company_id": "co-2", "asset_id": "asset-stale", "ticker": "RANK2"},
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-rank",
            "--watchlist",
            str(watchlist_path),
            "--top",
            "1",
        ],
    )
    rank_main()
    out = capsys.readouterr().out
    assert "asset-recent" in out
    assert "evt-recent" in out
    assert "asset-stale" not in out
