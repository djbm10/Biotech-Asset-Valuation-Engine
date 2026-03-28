from __future__ import annotations

from pathlib import Path

import yaml

from bve.ops.deal_event_backfiller import DealEventBackfiller
from bve.ops.historical_replay import ReplayStore


def test_backfiller_inserts_public_deal_events_idempotently(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    ReplayStore(str(db_path)).close()

    universe_path = tmp_path / "universe.yaml"
    universe_path.write_text(
        yaml.safe_dump(
            {
                "universe": [
                    {"ticker": "ABC", "asset_id": "a-abc"},
                    {"ticker": "XYZ", "asset_id": "a-xyz"},
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    deal_file = tmp_path / "deals.yaml"
    deal_file.write_text(
        yaml.safe_dump(
            {
                "deals": [
                    {
                        "target_name": "ABC Corp",
                        "target_ticker": "ABC",
                        "acquirer": "Big Pharma",
                        "announcement_date": "2025-02-01",
                        "headline_value_millions": 2200,
                        "lead_asset": "ABC-101",
                    },
                    {
                        "target_name": "PrivateCo",
                        "acquirer": "Big Pharma",
                        "announcement_date": "2025-03-01",
                    },
                    {
                        "target_name": "OFFU Corp",
                        "target_ticker": "OFFU",
                        "acquirer": "Big Pharma",
                        "announcement_date": "2025-04-01",
                    },
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    backfiller = DealEventBackfiller(replay_db_path=str(db_path))
    first = backfiller.backfill(universe_file=universe_path, deal_file=deal_file)
    second = backfiller.backfill(universe_file=universe_path, deal_file=deal_file)

    assert first.deals_considered == 3
    assert first.public_deals_seen == 2
    assert first.in_universe_public_deals == 1
    assert first.inserted_events == 1
    assert first.skipped_missing_ticker == 1
    assert first.skipped_not_in_universe == 1
    assert second.inserted_events == 1

    store = ReplayStore(str(db_path))
    try:
        rows = store._conn.execute(
            "SELECT event_id, asset_id, ticker, event_type, announced_at, outcome_label, headline "
            "FROM historical_events ORDER BY announced_at"
        ).fetchall()
    finally:
        store.close()

    assert len(rows) == 1
    row = rows[0]
    assert row["event_id"] == "mna:ABC:2025-02-01"
    assert row["asset_id"] == "a-abc"
    assert row["ticker"] == "ABC"
    assert row["event_type"] == "acquisition"
    assert row["announced_at"] == "2025-02-01"
    assert row["outcome_label"] == "positive"
    assert "Big Pharma announced acquisition of ABC Corp" in row["headline"]
