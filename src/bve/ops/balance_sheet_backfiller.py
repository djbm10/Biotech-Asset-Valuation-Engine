"""
Replay-store balance-sheet provenance backfiller for top-universe watchlists.

Loads a watchlist YAML, backfills dated SEC-derived balance-sheet snapshots into
the replay store, and writes a simple coverage report so company-level SOTP can
be rerun on populated point-in-time inputs.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Optional

import yaml

from bve.ops.historical_replay import REPLAY_STORE_PATH, ReplayStore
from bve.ops.signal_backfiller import SignalBackfiller
from bve.pipeline.watchlist_runner import WatchlistAsset, load_watchlist_config


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "outputs" / "analysis"


@dataclass(frozen=True)
class BalanceSheetCoverageRow:
    ticker: str
    asset_ids: tuple[str, ...]
    snapshot_count: int
    latest_snapshot_date: Optional[date]
    latest_period_end_date: Optional[date]
    latest_form_type: Optional[str]
    latest_source_type: Optional[str]
    latest_source_ref: Optional[str]


@dataclass(frozen=True)
class BalanceSheetBackfillSummary:
    watchlist_path: str
    replay_db_path: str
    n_watchlist_assets: int
    n_unique_tickers: int
    n_capital_rows_inserted: int
    n_balance_sheet_rows_added: int
    n_tickers_with_balance_sheet: int
    coverage_rows: list[BalanceSheetCoverageRow]
    coverage_csv_path: Path


class BalanceSheetBackfiller:
    def __init__(
        self,
        *,
        replay_db_path: str | Path = REPLAY_STORE_PATH,
        output_dir: str | Path = _DEFAULT_OUTPUT_DIR,
        reporter: Optional[Callable[[str], None]] = print,
    ) -> None:
        self.replay_db_path = Path(replay_db_path)
        self.output_dir = Path(output_dir)
        self.reporter = reporter

    def _emit(self, message: str) -> None:
        if self.reporter is not None:
            self.reporter(message)

    def backfill_watchlist(self, watchlist_path: str | Path) -> BalanceSheetBackfillSummary:
        resolved_watchlist = _resolve_watchlist_path(watchlist_path)
        watchlist_cfg = load_watchlist_config(resolved_watchlist)
        universe = _watchlist_to_universe(watchlist_cfg.watchlist, resolved_watchlist)

        store = ReplayStore(str(self.replay_db_path))
        try:
            before_rows = _count_rows(store, "balance_sheet_snapshots")
            inserted = SignalBackfiller(store).backfill_capital_risk(universe)
            after_rows = _count_rows(store, "balance_sheet_snapshots")
            coverage_rows = _load_coverage_rows(store, universe)
        finally:
            store.close()

        coverage_csv_path = self._write_coverage_csv(
            coverage_rows,
            snapshot_label=date.today().isoformat(),
        )
        summary = BalanceSheetBackfillSummary(
            watchlist_path=str(resolved_watchlist),
            replay_db_path=str(self.replay_db_path),
            n_watchlist_assets=len(watchlist_cfg.watchlist),
            n_unique_tickers=len({row.ticker for row in coverage_rows}),
            n_capital_rows_inserted=inserted,
            n_balance_sheet_rows_added=max(after_rows - before_rows, 0),
            n_tickers_with_balance_sheet=sum(1 for row in coverage_rows if row.snapshot_count > 0),
            coverage_rows=coverage_rows,
            coverage_csv_path=coverage_csv_path,
        )
        self._emit(render_summary(summary))
        self._emit(f"Coverage CSV -> {coverage_csv_path}")
        return summary

    def _write_coverage_csv(
        self,
        rows: list[BalanceSheetCoverageRow],
        *,
        snapshot_label: str,
    ) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.output_dir / f"balance_sheet_coverage_{snapshot_label}.csv"
        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "ticker",
                    "asset_ids",
                    "snapshot_count",
                    "latest_snapshot_date",
                    "latest_period_end_date",
                    "latest_form_type",
                    "latest_source_type",
                    "latest_source_ref",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "ticker": row.ticker,
                        "asset_ids": "|".join(row.asset_ids),
                        "snapshot_count": row.snapshot_count,
                        "latest_snapshot_date": (
                            row.latest_snapshot_date.isoformat()
                            if row.latest_snapshot_date is not None
                            else ""
                        ),
                        "latest_period_end_date": (
                            row.latest_period_end_date.isoformat()
                            if row.latest_period_end_date is not None
                            else ""
                        ),
                        "latest_form_type": row.latest_form_type or "",
                        "latest_source_type": row.latest_source_type or "",
                        "latest_source_ref": row.latest_source_ref or "",
                    }
                )
        return out_path


def render_summary(summary: BalanceSheetBackfillSummary) -> str:
    return "\n".join(
        [
            "Balance-sheet backfill complete:",
            f"  Watchlist assets: {summary.n_watchlist_assets}",
            f"  Unique tickers: {summary.n_unique_tickers}",
            f"  Capital rows inserted: {summary.n_capital_rows_inserted}",
            f"  Balance-sheet rows added: {summary.n_balance_sheet_rows_added}",
            f"  Tickers with dated balance sheet: {summary.n_tickers_with_balance_sheet}",
        ]
    )


def _resolve_watchlist_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.exists():
        return candidate.resolve()
    repo_candidate = (_REPO_ROOT / candidate).resolve()
    if repo_candidate.exists():
        return repo_candidate
    raise FileNotFoundError(f"Watchlist not found: {path}")


def _watchlist_to_universe(
    watchlist: list[WatchlistAsset],
    watchlist_path: Path,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for asset in watchlist:
        ticker = str(asset.ticker or "").upper()
        asset_id = str(asset.asset_id or "")
        if not ticker or not asset_id:
            continue
        company_name = _company_name_from_config(asset, watchlist_path)
        row = {"ticker": ticker, "asset_id": asset_id}
        if company_name:
            row["company_name"] = company_name
        rows.append(row)
    return rows


def _company_name_from_config(asset: WatchlistAsset, watchlist_path: Path) -> Optional[str]:
    raw_config = getattr(asset, "valuation_config", None)
    if not raw_config:
        return None
    config_path = Path(raw_config).expanduser()
    if not config_path.is_absolute():
        repo_candidate = (_REPO_ROOT / config_path).resolve()
        config_path = repo_candidate if repo_candidate.exists() else (watchlist_path.parent / config_path).resolve()
    if not config_path.exists():
        return None
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return None
    company_name = raw.get("company", {}).get("name")
    if company_name:
        return str(company_name)
    return None


def _count_rows(store: ReplayStore, table: str) -> int:
    return int(store._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _load_coverage_rows(
    store: ReplayStore,
    universe: list[dict[str, str]],
) -> list[BalanceSheetCoverageRow]:
    assets_by_ticker: dict[str, list[str]] = {}
    for row in universe:
        assets_by_ticker.setdefault(row["ticker"], []).append(row["asset_id"])

    coverage_rows: list[BalanceSheetCoverageRow] = []
    for ticker in sorted(assets_by_ticker):
        row = store._conn.execute(
            """
            SELECT COUNT(*) AS snapshot_count,
                   MAX(snapshot_date) AS latest_snapshot_date
            FROM balance_sheet_snapshots
            WHERE ticker = ?
            """,
            (ticker,),
        ).fetchone()
        latest = store._conn.execute(
            """
            SELECT snapshot_date,
                   period_end_date,
                   form_type,
                   source_type,
                   source_ref
            FROM balance_sheet_snapshots
            WHERE ticker = ?
            ORDER BY snapshot_date DESC, created_at DESC
            LIMIT 1
            """,
            (ticker,),
        ).fetchone()
        coverage_rows.append(
            BalanceSheetCoverageRow(
                ticker=ticker,
                asset_ids=tuple(sorted(assets_by_ticker[ticker])),
                snapshot_count=int(row["snapshot_count"]) if row is not None else 0,
                latest_snapshot_date=(
                    date.fromisoformat(str(latest["snapshot_date"]))
                    if latest is not None and latest["snapshot_date"]
                    else None
                ),
                latest_period_end_date=(
                    date.fromisoformat(str(latest["period_end_date"]))
                    if latest is not None and latest["period_end_date"]
                    else None
                ),
                latest_form_type=str(latest["form_type"]) if latest is not None and latest["form_type"] else None,
                latest_source_type=(
                    str(latest["source_type"]) if latest is not None and latest["source_type"] else None
                ),
                latest_source_ref=(
                    str(latest["source_ref"]) if latest is not None and latest["source_ref"] else None
                ),
            )
        )
    return coverage_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill dated balance-sheet provenance for a watchlist")
    parser.add_argument("--watchlist", required=True, help="Watchlist YAML path")
    parser.add_argument("--replay-db", default=str(REPLAY_STORE_PATH), help="Replay store SQLite path")
    parser.add_argument("--output-dir", default=str(_DEFAULT_OUTPUT_DIR), help="Coverage CSV output directory")
    args = parser.parse_args()

    BalanceSheetBackfiller(
        replay_db_path=args.replay_db,
        output_dir=args.output_dir,
    ).backfill_watchlist(args.watchlist)


if __name__ == "__main__":
    main()
