"""
Coverage audit for replay-universe expansion.

Evaluates replay-store price/event/signal coverage for a research universe and
checks whether missing price history appears to be backfillable from yfinance.

Usage
-----
    python -m bve.analysis.coverage_audit --universe-file <path>
        [--start 2023-01-01] [--end 2026-03-21]
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Mapping, Optional

from bve.analysis.alpha_validation import OUTPUT_DIR, _download_yfinance_prices
from bve.ops.historical_replay import REPLAY_STORE_PATH, ReplayStore, load_replay_universe


PriceSeriesFetcher = Callable[[str, date, date], Mapping[date, float]]


@dataclass(frozen=True)
class CoverageAuditRow:
    ticker: str
    asset_id: str
    price_first_date: Optional[date]
    price_last_date: Optional[date]
    price_trading_days: int
    price_gaps_gt_5: int
    yfinance_first_date: Optional[date]
    yfinance_last_date: Optional[date]
    yfinance_trading_days: int
    replay_price_full_coverage: bool
    yfinance_price_full_coverage: bool
    n_events: int
    first_event_date: Optional[date]
    last_event_date: Optional[date]
    event_types: str
    catalyst_rows: int
    enrollment_rows: int
    signal_rows: int
    capital_rows: int


@dataclass(frozen=True)
class CoverageAuditReport:
    universe_file: Path
    start_date: date
    end_date: date
    rows: list[CoverageAuditRow]
    full_price_coverage_count: int
    event_coverage_count: int
    ready_for_replay_count: int
    needing_price_backfill_count: int
    needing_event_seeding_count: int
    csv_path: Path


def _format_date(value: Optional[date], *, no_data: bool = False) -> str:
    if value is None:
        return "(no data)" if no_data else "-"
    return value.isoformat()


def _filtered_dates(prices: Mapping[date, float], start_date: date, end_date: date) -> list[date]:
    return sorted(d for d in prices if start_date <= d <= end_date)


def _gap_count(dates: list[date]) -> int:
    if len(dates) < 2:
        return 0
    return sum(1 for left, right in zip(dates, dates[1:]) if (right - left).days > 5)


def _has_full_coverage(dates: list[date], start_date: date, end_date: date) -> bool:
    if not dates:
        return False
    return (
        dates[0] <= start_date + timedelta(days=5)
        and dates[-1] >= end_date - timedelta(days=5)
        and _gap_count(dates) == 0
    )


def _coverage_from_prices(
    prices: Mapping[date, float],
    start_date: date,
    end_date: date,
) -> tuple[Optional[date], Optional[date], int, int, bool]:
    dates = _filtered_dates(prices, start_date, end_date)
    if not dates:
        return None, None, 0, 0, False
    gaps = _gap_count(dates)
    return dates[0], dates[-1], len(dates), gaps, _has_full_coverage(dates, start_date, end_date)


def _load_store_prices(
    store: ReplayStore,
    ticker: str,
    start_date: date,
    end_date: date,
) -> dict[date, float]:
    rows = store._conn.execute(
        "SELECT price_date, close_usd FROM historical_prices "
        "WHERE ticker = ? AND price_date >= ? AND price_date <= ? "
        "ORDER BY price_date",
        (ticker, start_date.isoformat(), end_date.isoformat()),
    ).fetchall()
    return {
        date.fromisoformat(str(row["price_date"])[:10]): float(row["close_usd"])
        for row in rows
    }


def _event_coverage(
    store: ReplayStore,
    asset_id: str,
    start_date: date,
    end_date: date,
) -> tuple[int, Optional[date], Optional[date], str]:
    rows = store._conn.execute(
        "SELECT announced_at, event_type FROM historical_events "
        "WHERE asset_id = ? AND announced_at >= ? AND announced_at <= ? "
        "ORDER BY announced_at",
        (asset_id, start_date.isoformat(), end_date.isoformat()),
    ).fetchall()
    if not rows:
        return 0, None, None, "-"
    dates = [date.fromisoformat(str(row["announced_at"])[:10]) for row in rows]
    types = ",".join(sorted({str(row["event_type"]) for row in rows}))
    return len(rows), dates[0], dates[-1], types


def _signal_count(
    store: ReplayStore,
    table: str,
    asset_id: str,
    date_column_sql: str,
    start_date: date,
    end_date: date,
) -> int:
    row = store._conn.execute(
        f"SELECT COUNT(*) AS n FROM {table} "
        "WHERE asset_id = ? "
        f"AND {date_column_sql} >= ? AND {date_column_sql} <= ?",
        (asset_id, start_date.isoformat(), end_date.isoformat()),
    ).fetchone()
    return int(row["n"]) if row is not None else 0


def _csv_path(output_dir: Path) -> Path:
    return output_dir / "coverage_audit.csv"


def render_coverage_audit_report(report: CoverageAuditReport) -> str:
    sep = "=" * 60
    lines = [
        sep,
        "COVERAGE AUDIT",
        f"Universe: {report.universe_file} ({len(report.rows)} tickers)",
        f"Target period: {report.start_date.isoformat()} -> {report.end_date.isoformat()}",
        sep,
        "",
        "PRICE COVERAGE",
        "Ticker   First Date   Last Date    Trading Days   Gaps",
    ]
    for row in report.rows:
        lines.append(
            f"{row.ticker:<8} "
            f"{_format_date(row.price_first_date, no_data=True):<12} "
            f"{_format_date(row.price_last_date, no_data=True):<12} "
            f"{row.price_trading_days:>12}   "
            f"{'-' if row.price_trading_days == 0 else row.price_gaps_gt_5}"
        )
    lines.extend([
        "",
        (
            f"Summary: {report.full_price_coverage_count}/{len(report.rows)} tickers "
            "have full price coverage for target period"
        ),
        "",
        "EVENT COVERAGE",
        "Asset       Events  First       Last        Types",
    ])
    for row in report.rows:
        lines.append(
            f"{row.asset_id:<11} {row.n_events:>6}  "
            f"{_format_date(row.first_event_date):<10}  "
            f"{_format_date(row.last_event_date):<10}  "
            f"{row.event_types}"
        )
    lines.extend([
        "",
        (
            f"Summary: {report.event_coverage_count}/{len(report.rows)} assets "
            "have >=1 event in target period"
        ),
        "",
        "SIGNAL COVERAGE",
        "Asset       Catalysts  Enrollment  Signals  Capital",
    ])
    for row in report.rows:
        lines.append(
            f"{row.asset_id:<11} {row.catalyst_rows:>9}  "
            f"{row.enrollment_rows:>10}  "
            f"{row.signal_rows:>7}  "
            f"{row.capital_rows:>7}"
        )
    lines.extend([
        "",
        "RECOMMENDATION",
        f"  Tickers ready for replay (price + events): {report.ready_for_replay_count}",
        f"  Tickers needing price backfill: {report.needing_price_backfill_count}",
        f"  Tickers needing event seeding: {report.needing_event_seeding_count}",
        sep,
    ])
    return "\n".join(lines)


class CoverageAuditor:
    def __init__(
        self,
        *,
        replay_db_path: str = str(REPLAY_STORE_PATH),
        output_dir: Path = OUTPUT_DIR,
        price_fetcher: Optional[PriceSeriesFetcher] = None,
    ) -> None:
        self.replay_db_path = replay_db_path
        self.output_dir = output_dir
        self.price_fetcher = price_fetcher or _download_yfinance_prices

    def _fetch_yfinance_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> dict[date, float]:
        try:
            return dict(self.price_fetcher(ticker, start_date, end_date))
        except Exception:
            return {}

    def _export_csv(self, rows: list[CoverageAuditRow]) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = _csv_path(self.output_dir)
        fieldnames = [
            "ticker",
            "asset_id",
            "price_first_date",
            "price_last_date",
            "price_trading_days",
            "price_gaps_gt_5",
            "yfinance_first_date",
            "yfinance_last_date",
            "yfinance_trading_days",
            "replay_price_full_coverage",
            "yfinance_price_full_coverage",
            "n_events",
            "first_event_date",
            "last_event_date",
            "event_types",
            "catalyst_rows",
            "enrollment_rows",
            "signal_rows",
            "capital_rows",
        ]
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "ticker": row.ticker,
                    "asset_id": row.asset_id,
                    "price_first_date": row.price_first_date.isoformat() if row.price_first_date else "",
                    "price_last_date": row.price_last_date.isoformat() if row.price_last_date else "",
                    "price_trading_days": row.price_trading_days,
                    "price_gaps_gt_5": row.price_gaps_gt_5,
                    "yfinance_first_date": row.yfinance_first_date.isoformat() if row.yfinance_first_date else "",
                    "yfinance_last_date": row.yfinance_last_date.isoformat() if row.yfinance_last_date else "",
                    "yfinance_trading_days": row.yfinance_trading_days,
                    "replay_price_full_coverage": row.replay_price_full_coverage,
                    "yfinance_price_full_coverage": row.yfinance_price_full_coverage,
                    "n_events": row.n_events,
                    "first_event_date": row.first_event_date.isoformat() if row.first_event_date else "",
                    "last_event_date": row.last_event_date.isoformat() if row.last_event_date else "",
                    "event_types": row.event_types,
                    "catalyst_rows": row.catalyst_rows,
                    "enrollment_rows": row.enrollment_rows,
                    "signal_rows": row.signal_rows,
                    "capital_rows": row.capital_rows,
                })
        return path

    def audit(
        self,
        universe_file: str | Path,
        *,
        start_date: date,
        end_date: date,
    ) -> CoverageAuditReport:
        universe = load_replay_universe(str(universe_file))
        store = ReplayStore(self.replay_db_path)
        try:
            rows: list[CoverageAuditRow] = []
            for entry in universe:
                ticker = str(entry["ticker"])
                asset_id = str(entry["asset_id"])

                replay_prices = _load_store_prices(store, ticker, start_date, end_date)
                yfinance_prices = self._fetch_yfinance_prices(ticker, start_date, end_date)

                price_first, price_last, trading_days, gaps, replay_full = _coverage_from_prices(
                    replay_prices,
                    start_date,
                    end_date,
                )
                yf_first, yf_last, yf_days, _yf_gaps, yf_full = _coverage_from_prices(
                    yfinance_prices,
                    start_date,
                    end_date,
                )
                n_events, first_event, last_event, event_types = _event_coverage(
                    store,
                    asset_id,
                    start_date,
                    end_date,
                )
                catalyst_rows = _signal_count(
                    store,
                    "catalyst_events",
                    asset_id,
                    "COALESCE(snapshot_date, event_date)",
                    start_date,
                    end_date,
                )
                enrollment_rows = _signal_count(
                    store,
                    "enrollment_snapshots",
                    asset_id,
                    "snapshot_date",
                    start_date,
                    end_date,
                )
                signal_rows = _signal_count(
                    store,
                    "structured_signals",
                    asset_id,
                    "signal_date",
                    start_date,
                    end_date,
                )
                capital_rows = _signal_count(
                    store,
                    "capital_snapshots",
                    asset_id,
                    "snapshot_date",
                    start_date,
                    end_date,
                )

                rows.append(CoverageAuditRow(
                    ticker=ticker,
                    asset_id=asset_id,
                    price_first_date=price_first,
                    price_last_date=price_last,
                    price_trading_days=trading_days,
                    price_gaps_gt_5=gaps,
                    yfinance_first_date=yf_first,
                    yfinance_last_date=yf_last,
                    yfinance_trading_days=yf_days,
                    replay_price_full_coverage=replay_full,
                    yfinance_price_full_coverage=yf_full,
                    n_events=n_events,
                    first_event_date=first_event,
                    last_event_date=last_event,
                    event_types=event_types,
                    catalyst_rows=catalyst_rows,
                    enrollment_rows=enrollment_rows,
                    signal_rows=signal_rows,
                    capital_rows=capital_rows,
                ))
        finally:
            store.close()

        csv_path = self._export_csv(rows)
        return CoverageAuditReport(
            universe_file=Path(universe_file),
            start_date=start_date,
            end_date=end_date,
            rows=rows,
            full_price_coverage_count=sum(row.replay_price_full_coverage for row in rows),
            event_coverage_count=sum(row.n_events > 0 for row in rows),
            ready_for_replay_count=sum(
                row.replay_price_full_coverage and row.n_events > 0 for row in rows
            ),
            needing_price_backfill_count=sum(not row.replay_price_full_coverage for row in rows),
            needing_event_seeding_count=sum(row.n_events == 0 for row in rows),
            csv_path=csv_path,
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit replay-universe coverage")
    parser.add_argument("--universe-file", required=True, help="Replay universe JSON or YAML file")
    parser.add_argument("--start", default="2023-01-01", help="Coverage period start date")
    parser.add_argument("--end", default=date.today().isoformat(), help="Coverage period end date")
    parser.add_argument("--db", default=str(REPLAY_STORE_PATH), help="Replay SQLite store path")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    auditor = CoverageAuditor(replay_db_path=args.db)
    report = auditor.audit(
        args.universe_file,
        start_date=date.fromisoformat(args.start),
        end_date=date.fromisoformat(args.end),
    )
    print(render_coverage_audit_report(report))


if __name__ == "__main__":
    main()
