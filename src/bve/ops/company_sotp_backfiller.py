"""
Historical company-SOTP backfiller.

Uses persisted ``screen_snapshots`` dates as the replay-safe calendar, reruns the
company-level SOTP layer for each date, and stores the resulting rows in
``company_sotp_snapshots`` so downstream ranking and validation can use a dated
company-level dataset instead of one-off current snapshots.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from bve.analysis.company_sotp import CompanySOTPBuilder
from bve.ops.historical_replay import REPLAY_STORE_PATH
from bve.pipeline.watchlist_runner import load_watchlist_config
from bve.intelligence.knowledge_layer import KnowledgeStore


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "outputs" / "analysis"


@dataclass(frozen=True)
class CompanySOTPBackfillDateSummary:
    snapshot_date: date
    n_companies: int
    n_pass_recency_gate: int
    n_buy: int
    n_watch: int
    n_avoid: int
    n_needs_manual_review: int
    csv_path: Path


@dataclass(frozen=True)
class CompanySOTPBackfillSummary:
    watchlist_path: str
    knowledge_db_path: str
    replay_db_path: str
    n_watchlist_assets: int
    n_snapshot_dates: int
    snapshot_start: Optional[date]
    snapshot_end: Optional[date]
    total_company_rows: int
    total_pass_recency_gate: int
    total_buy: int
    total_watch: int
    total_avoid: int
    total_needs_manual_review: int
    date_summaries: list[CompanySOTPBackfillDateSummary]
    summary_csv_path: Path


class CompanySOTPBackfiller:
    def __init__(
        self,
        *,
        knowledge_db_path: str | Path,
        replay_db_path: str | Path = REPLAY_STORE_PATH,
        output_dir: str | Path = _DEFAULT_OUTPUT_DIR,
        reporter: Optional[Callable[[str], None]] = print,
    ) -> None:
        self.knowledge_db_path = Path(knowledge_db_path)
        self.replay_db_path = Path(replay_db_path)
        self.output_dir = Path(output_dir)
        self.reporter = reporter

    def _emit(self, message: str) -> None:
        if self.reporter is not None:
            self.reporter(message)

    def backfill_watchlist(
        self,
        watchlist_path: str | Path,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        active_screen_only: bool = True,
    ) -> CompanySOTPBackfillSummary:
        resolved_watchlist = _resolve_watchlist_path(watchlist_path)
        watchlist_cfg = load_watchlist_config(resolved_watchlist)
        snapshot_dates = self._resolve_dates(start_date=start_date, end_date=end_date)
        if not snapshot_dates:
            raise ValueError("No screen snapshot dates found for the requested range")

        date_summaries: list[CompanySOTPBackfillDateSummary] = []
        total_company_rows = 0
        total_pass_recency_gate = 0
        total_buy = 0
        total_watch = 0
        total_avoid = 0
        total_needs_manual_review = 0
        shared_asset_rnpv_cache: dict[str, float] = {}

        for snapshot_date in snapshot_dates:
            include_tickers = (
                self._active_screen_tickers(snapshot_date)
                if active_screen_only
                else None
            )
            builder = CompanySOTPBuilder(
                as_of_date=snapshot_date,
                output_dir=self.output_dir,
                knowledge_db_path=self.knowledge_db_path,
                replay_store_path=self.replay_db_path,
                persist_company_snapshots=True,
                asset_rnpv_cache=shared_asset_rnpv_cache,
            )
            rows = builder.build(
                str(resolved_watchlist),
                price_source="replay_store",
                include_tickers=include_tickers,
            )
            n_companies = len(rows)
            n_pass_recency_gate = sum(
                1 for row in rows if row.balance_sheet_passes_recency_gate
            )
            n_buy = sum(1 for row in rows if row.action_policy == "buy")
            n_watch = sum(1 for row in rows if row.action_policy == "watch")
            n_avoid = sum(1 for row in rows if row.action_policy == "avoid")
            n_needs_manual_review = sum(
                1 for row in rows if row.action_policy == "needs_manual_review"
            )
            csv_path = builder.last_csv_path or (
                self.output_dir / f"company_sotp_{snapshot_date.isoformat()}.csv"
            )
            date_summaries.append(
                CompanySOTPBackfillDateSummary(
                    snapshot_date=snapshot_date,
                    n_companies=n_companies,
                    n_pass_recency_gate=n_pass_recency_gate,
                    n_buy=n_buy,
                    n_watch=n_watch,
                    n_avoid=n_avoid,
                    n_needs_manual_review=n_needs_manual_review,
                    csv_path=csv_path,
                )
            )
            total_company_rows += n_companies
            total_pass_recency_gate += n_pass_recency_gate
            total_buy += n_buy
            total_watch += n_watch
            total_avoid += n_avoid
            total_needs_manual_review += n_needs_manual_review

        summary_csv_path = self._write_summary_csv(date_summaries)
        summary = CompanySOTPBackfillSummary(
            watchlist_path=str(resolved_watchlist),
            knowledge_db_path=str(self.knowledge_db_path),
            replay_db_path=str(self.replay_db_path),
            n_watchlist_assets=len(watchlist_cfg.watchlist),
            n_snapshot_dates=len(snapshot_dates),
            snapshot_start=snapshot_dates[0],
            snapshot_end=snapshot_dates[-1],
            total_company_rows=total_company_rows,
            total_pass_recency_gate=total_pass_recency_gate,
            total_buy=total_buy,
            total_watch=total_watch,
            total_avoid=total_avoid,
            total_needs_manual_review=total_needs_manual_review,
            date_summaries=date_summaries,
            summary_csv_path=summary_csv_path,
        )
        self._emit(render_summary(summary))
        self._emit(f"Date summary CSV -> {summary.summary_csv_path}")
        return summary

    def _resolve_dates(
        self,
        *,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> list[date]:
        store = KnowledgeStore(self.knowledge_db_path)
        try:
            dates = store.list_screen_snapshot_dates()
        finally:
            store.close()
        if start_date is not None:
            dates = [item for item in dates if item >= start_date]
        if end_date is not None:
            dates = [item for item in dates if item <= end_date]
        return sorted(dates)

    def _active_screen_tickers(self, snapshot_date: date) -> set[str]:
        store = KnowledgeStore(self.knowledge_db_path)
        try:
            rows = store.get_screen_snapshots(snapshot_date=snapshot_date, limit=10000)
        finally:
            store.close()
        return {
            str(row.get("ticker") or "").upper()
            for row in rows
            if row.get("ticker")
        }

    def _write_summary_csv(
        self,
        rows: list[CompanySOTPBackfillDateSummary],
    ) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        token = _summary_range_token(rows)
        out_path = self.output_dir / f"company_sotp_backfill_summary_{token}.csv"
        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "snapshot_date",
                    "n_companies",
                    "n_pass_recency_gate",
                    "n_buy",
                    "n_watch",
                    "n_avoid",
                    "n_needs_manual_review",
                    "csv_path",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "snapshot_date": row.snapshot_date.isoformat(),
                        "n_companies": row.n_companies,
                        "n_pass_recency_gate": row.n_pass_recency_gate,
                        "n_buy": row.n_buy,
                        "n_watch": row.n_watch,
                        "n_avoid": row.n_avoid,
                        "n_needs_manual_review": row.n_needs_manual_review,
                        "csv_path": str(row.csv_path),
                    }
                )
        return out_path


def render_summary(summary: CompanySOTPBackfillSummary) -> str:
    return "\n".join(
        [
            "Company SOTP historical backfill complete:",
            f"  Watchlist assets: {summary.n_watchlist_assets}",
            f"  Snapshot dates: {summary.n_snapshot_dates}",
            f"  Date range: {summary.snapshot_start} -> {summary.snapshot_end}",
            f"  Company rows persisted: {summary.total_company_rows}",
            f"  Pass recency gate: {summary.total_pass_recency_gate}",
            f"  Action policy totals: buy={summary.total_buy}, watch={summary.total_watch}, "
            f"avoid={summary.total_avoid}, needs_manual_review={summary.total_needs_manual_review}",
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


def _summary_range_token(rows: list[CompanySOTPBackfillDateSummary]) -> str:
    if not rows:
        return "empty"
    return f"{rows[0].snapshot_date.isoformat()}_{rows[-1].snapshot_date.isoformat()}"


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical company-level SOTP snapshots")
    parser.add_argument("--watchlist", required=True, help="Path to watchlist YAML")
    parser.add_argument("--db", required=True, help="KnowledgeStore SQLite path")
    parser.add_argument("--replay-db", default=str(REPLAY_STORE_PATH), help="Replay store SQLite path")
    parser.add_argument("--start", default=None, help="Optional YYYY-MM-DD start date")
    parser.add_argument("--end", default=None, help="Optional YYYY-MM-DD end date")
    parser.add_argument("--output-dir", default=str(_DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--full-watchlist",
        action="store_true",
        help="Backfill the full watchlist on every date instead of only the active stored screen cohort",
    )
    args = parser.parse_args()

    summary = CompanySOTPBackfiller(
        knowledge_db_path=args.db,
        replay_db_path=args.replay_db,
        output_dir=args.output_dir,
        reporter=None,
    ).backfill_watchlist(
        args.watchlist,
        start_date=_parse_date(args.start) if args.start else None,
        end_date=_parse_date(args.end) if args.end else None,
        active_screen_only=not args.full_watchlist,
    )
    print(render_summary(summary))


if __name__ == "__main__":
    main()
