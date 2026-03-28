"""
Seed replay-store historical acquisition events from the M&A deal universe.

Usage
-----
    python src/bve/ops/deal_event_backfiller.py \
        --universe-file examples/research/universe_expanded_mna.yaml
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from bve.ops.historical_replay import REPLAY_STORE_PATH, ReplayStore, load_replay_universe
from bve.ops.replay_universe_builder import (
    DEFAULT_DEAL_UNIVERSE_PATH,
    DEFAULT_OUTPUT_PATH,
)


@dataclass(frozen=True)
class DealEventBackfillSummary:
    deal_file: Path
    universe_file: Path
    deals_considered: int
    public_deals_seen: int
    in_universe_public_deals: int
    inserted_events: int
    skipped_missing_ticker: int
    skipped_not_in_universe: int


def render_summary(summary: DealEventBackfillSummary) -> str:
    return "\n".join(
        [
            "Deal event backfill complete:",
            f"  Deals considered: {summary.deals_considered}",
            f"  Public deals seen: {summary.public_deals_seen}",
            f"  Public deals in universe: {summary.in_universe_public_deals}",
            f"  Events inserted: {summary.inserted_events}",
            f"  Skipped missing ticker: {summary.skipped_missing_ticker}",
            f"  Skipped not in universe: {summary.skipped_not_in_universe}",
        ]
    )


class DealEventBackfiller:
    """Upsert acquisition announcement events from the local M&A deal universe."""

    def __init__(self, *, replay_db_path: str = str(REPLAY_STORE_PATH)) -> None:
        self.replay_db_path = replay_db_path

    def backfill(
        self,
        *,
        universe_file: Path | str = DEFAULT_OUTPUT_PATH,
        deal_file: Path | str = DEFAULT_DEAL_UNIVERSE_PATH,
    ) -> DealEventBackfillSummary:
        universe = load_replay_universe(str(universe_file))
        universe_by_ticker = {
            str(entry["ticker"]).upper(): str(entry["asset_id"])
            for entry in universe
        }

        payload = yaml.safe_load(Path(deal_file).read_text(encoding="utf-8")) or {}
        deals = payload.get("deals", []) if isinstance(payload, dict) else payload
        if not isinstance(deals, list):
            raise ValueError("Deal universe YAML must be a list or contain a 'deals' list")

        public_deals_seen = 0
        in_universe_public_deals = 0
        inserted_events = 0
        skipped_missing_ticker = 0
        skipped_not_in_universe = 0

        store = ReplayStore(self.replay_db_path)
        try:
            for deal in deals:
                if not isinstance(deal, dict):
                    continue

                ticker_raw = deal.get("target_ticker")
                if not ticker_raw:
                    skipped_missing_ticker += 1
                    continue

                public_deals_seen += 1
                ticker = str(ticker_raw).upper()
                asset_id = universe_by_ticker.get(ticker)
                if asset_id is None:
                    skipped_not_in_universe += 1
                    continue

                announcement_date = str(deal.get("announcement_date") or "").strip()
                if not announcement_date:
                    continue

                announced_at = date.fromisoformat(announcement_date[:10])
                acquirer = str(deal.get("acquirer") or "Strategic buyer").strip()
                target_name = str(deal.get("target_name") or ticker).strip()
                headline_value = deal.get("headline_value_millions")
                lead_asset = str(deal.get("lead_asset") or "").strip()
                value_text = ""
                if headline_value not in (None, ""):
                    value_text = f" for approximately ${float(headline_value):,.0f}M"
                asset_text = f"; lead asset {lead_asset}" if lead_asset else ""
                headline = f"{acquirer} announced acquisition of {target_name}{value_text}{asset_text}"

                event_id = f"mna:{ticker}:{announced_at.isoformat()}"
                store._conn.execute(
                    """
                    INSERT OR REPLACE INTO historical_events
                        (event_id, asset_id, ticker, event_type, announced_at,
                         effective_date, outcome_label, headline)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        asset_id,
                        ticker,
                        "acquisition",
                        announced_at.isoformat(),
                        announced_at.isoformat(),
                        "positive",
                        headline,
                    ),
                )
                inserted_events += 1
                in_universe_public_deals += 1

            store._conn.commit()
        finally:
            store.close()

        return DealEventBackfillSummary(
            deal_file=Path(deal_file),
            universe_file=Path(universe_file),
            deals_considered=len(deals),
            public_deals_seen=public_deals_seen,
            in_universe_public_deals=in_universe_public_deals,
            inserted_events=inserted_events,
            skipped_missing_ticker=skipped_missing_ticker,
            skipped_not_in_universe=skipped_not_in_universe,
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill acquisition announcement events")
    parser.add_argument("--universe-file", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--deal-file", default=str(DEFAULT_DEAL_UNIVERSE_PATH))
    parser.add_argument("--db", default=str(REPLAY_STORE_PATH))
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    summary = DealEventBackfiller(replay_db_path=args.db).backfill(
        universe_file=args.universe_file,
        deal_file=args.deal_file,
    )
    print(render_summary(summary))


if __name__ == "__main__":
    main()
