"""
Replay-store historical price backfiller.

Downloads missing replay-store price history from yfinance for a replay
universe plus the XBI benchmark, extending coverage backward to a target
start date without duplicating existing rows.

Usage
-----
    python -m bve.ops.price_backfiller \
        --universe-file examples/research/universe_expanded_mna.yaml \
        --start 2021-01-01 \
        --end 2026-03-22
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Mapping, Optional

from bve.ops.historical_replay import REPLAY_STORE_PATH, ReplayStore, load_replay_universe


logger = logging.getLogger(__name__)

PriceSeriesFetcher = Callable[[str, date, date], Mapping[date, float]]
_REQUIRED_PRICE_COLUMNS = {"ticker", "price_date", "close_usd"}


@dataclass(frozen=True)
class PriceBackfillResult:
    ticker: str
    inserted_days: int = 0
    first_new: Optional[date] = None
    last_new: Optional[date] = None
    coverage_start: Optional[date] = None
    already_complete: bool = False
    skipped: bool = False


@dataclass(frozen=True)
class PriceBackfillSummary:
    start_date: date
    end_date: date
    tickers_processed: int
    tickers_backfilled: int
    tickers_already_complete: int
    tickers_skipped: int
    benchmark_ticker: str
    benchmark_backfilled_days: int
    new_coverage_start: Optional[date]
    ticker_results: list[PriceBackfillResult]
    benchmark_result: PriceBackfillResult


def _download_yfinance_prices(
    ticker: str,
    start_date: date,
    end_date: date,
) -> dict[date, float]:
    import yfinance as yf  # type: ignore[import-untyped]

    cache_dir = Path("/tmp") / "yfinance_tz_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        yf.set_tz_cache_location(str(cache_dir))
    except Exception:
        pass

    history = yf.Ticker(ticker).history(
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        auto_adjust=True,
    )
    if history is None or history.empty:
        return {}

    history.columns = [col[0] if isinstance(col, tuple) else col for col in history.columns]
    if "Close" not in history.columns:
        return {}

    close = history["Close"]
    if getattr(close, "ndim", 1) > 1:
        close = close.iloc[:, 0]
    close = close.dropna()
    return {
        idx.date(): float(value)
        for idx, value in close.items()
    }


def _format_date(value: Optional[date]) -> str:
    return value.isoformat() if value else "-"


def render_backfill_summary(summary: PriceBackfillSummary) -> str:
    lines = [
        "Backfill complete:",
        f"  Tickers processed: {summary.tickers_processed}",
        f"  Tickers backfilled: {summary.tickers_backfilled}",
        f"  Tickers already complete: {summary.tickers_already_complete}",
    ]
    if summary.tickers_skipped:
        lines.append(f"  Tickers skipped: {summary.tickers_skipped}")
    lines.extend([
        f"  {summary.benchmark_ticker} backfilled: {summary.benchmark_backfilled_days} days",
        f"  New coverage start: {_format_date(summary.new_coverage_start)}",
    ])
    return "\n".join(lines)


class PriceBackfiller:
    def __init__(
        self,
        *,
        replay_db_path: str = str(REPLAY_STORE_PATH),
        price_fetcher: Optional[PriceSeriesFetcher] = None,
        reporter: Optional[Callable[[str], None]] = print,
        benchmark_ticker: str = "XBI",
    ) -> None:
        self.replay_db_path = replay_db_path
        self.price_fetcher = price_fetcher or _download_yfinance_prices
        self.reporter = reporter
        self.benchmark_ticker = benchmark_ticker.upper()

    def _emit(self, message: str) -> None:
        if self.reporter is not None:
            self.reporter(message)

    @staticmethod
    def _ensure_price_schema(store: ReplayStore) -> None:
        rows = store._conn.execute("PRAGMA table_info(historical_prices)").fetchall()
        columns = {str(row["name"]) for row in rows}
        missing = _REQUIRED_PRICE_COLUMNS - columns
        if missing:
            missing_csv = ", ".join(sorted(missing))
            raise RuntimeError(
                "historical_prices schema mismatch; missing required columns: "
                f"{missing_csv}"
            )

    @staticmethod
    def _earliest_price_date(store: ReplayStore, ticker: str) -> Optional[date]:
        row = store._conn.execute(
            "SELECT MIN(price_date) AS earliest_price_date "
            "FROM historical_prices WHERE ticker = ?",
            (ticker,),
        ).fetchone()
        raw = row["earliest_price_date"] if row is not None else None
        if raw is None:
            return None
        return date.fromisoformat(str(raw)[:10])

    @staticmethod
    def _existing_dates(
        store: ReplayStore,
        ticker: str,
        first_date: date,
        last_date: date,
    ) -> set[date]:
        rows = store._conn.execute(
            "SELECT price_date FROM historical_prices "
            "WHERE ticker = ? AND price_date >= ? AND price_date <= ?",
            (ticker, first_date.isoformat(), last_date.isoformat()),
        ).fetchall()
        return {date.fromisoformat(str(row["price_date"])[:10]) for row in rows}

    @staticmethod
    def _coverage_start(store: ReplayStore, tickers: list[str]) -> Optional[date]:
        if not tickers:
            return None
        placeholders = ",".join("?" for _ in tickers)
        row = store._conn.execute(
            f"SELECT MIN(price_date) AS first_price_date "
            f"FROM historical_prices WHERE ticker IN ({placeholders})",
            tuple(tickers),
        ).fetchone()
        raw = row["first_price_date"] if row is not None else None
        if raw is None:
            return None
        return date.fromisoformat(str(raw)[:10])

    @staticmethod
    def _insert_price_rows(
        store: ReplayStore,
        ticker: str,
        rows: list[tuple[date, float]],
    ) -> int:
        if not rows:
            return 0
        before_changes = store._conn.total_changes
        store._conn.executemany(
            "INSERT OR IGNORE INTO historical_prices (ticker, price_date, close_usd) "
            "VALUES (?, ?, ?)",
            [(ticker, price_date.isoformat(), close_usd) for price_date, close_usd in rows],
        )
        store._conn.commit()
        return store._conn.total_changes - before_changes

    def _fetch_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> dict[date, float]:
        try:
            return dict(self.price_fetcher(ticker, start_date, end_date))
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s: failed to download price history: %s", ticker, exc)
            return {}

    def _backfill_ticker(
        self,
        store: ReplayStore,
        ticker: str,
        *,
        start_date: date,
        end_date: date,
    ) -> PriceBackfillResult:
        earliest_existing = self._earliest_price_date(store, ticker)
        if earliest_existing is not None and earliest_existing <= start_date:
            result = PriceBackfillResult(
                ticker=ticker,
                coverage_start=earliest_existing,
                already_complete=True,
            )
            self._emit(f"{ticker}: already complete")
            return result

        fetch_end = earliest_existing or (end_date + timedelta(days=1))
        fetched_prices = self._fetch_prices(ticker, start_date, fetch_end)
        upper_bound = end_date if earliest_existing is None else earliest_existing
        candidate_rows = sorted(
            (price_date, float(close_usd))
            for price_date, close_usd in fetched_prices.items()
            if start_date <= price_date <= upper_bound
        )
        if not candidate_rows:
            logger.warning("%s: no price data returned from yfinance; skipping", ticker)
            return PriceBackfillResult(
                ticker=ticker,
                coverage_start=earliest_existing,
                skipped=True,
            )

        existing_dates = self._existing_dates(
            store,
            ticker,
            candidate_rows[0][0],
            candidate_rows[-1][0],
        )
        new_rows = [
            (price_date, close_usd)
            for price_date, close_usd in candidate_rows
            if price_date not in existing_dates
        ]

        inserted = self._insert_price_rows(store, ticker, candidate_rows)
        if not inserted or not new_rows:
            logger.warning("%s: no new replay-store rows inserted; skipping", ticker)
            coverage_start = self._earliest_price_date(store, ticker)
            return PriceBackfillResult(
                ticker=ticker,
                coverage_start=coverage_start,
                skipped=True,
            )

        first_new = new_rows[0][0]
        last_new = new_rows[-1][0]
        coverage_start = self._earliest_price_date(store, ticker)
        self._emit(
            f"{ticker}: backfilled {inserted} days "
            f"({_format_date(first_new)} -> {_format_date(last_new)})"
        )
        return PriceBackfillResult(
            ticker=ticker,
            inserted_days=inserted,
            first_new=first_new,
            last_new=last_new,
            coverage_start=coverage_start,
        )

    def backfill(
        self,
        universe_file: str | Path,
        *,
        start_date: date,
        end_date: date,
    ) -> PriceBackfillSummary:
        if start_date > end_date:
            raise ValueError("start_date must be on or before end_date")

        universe = load_replay_universe(str(universe_file))
        seen: set[str] = set()
        tickers: list[str] = []
        for entry in universe:
            ticker = str(entry.get("ticker") or "").upper()
            if not ticker or ticker == self.benchmark_ticker or ticker in seen:
                continue
            seen.add(ticker)
            tickers.append(ticker)

        store = ReplayStore(self.replay_db_path)
        try:
            self._ensure_price_schema(store)
            ticker_results = [
                self._backfill_ticker(
                    store,
                    ticker,
                    start_date=start_date,
                    end_date=end_date,
                )
                for ticker in tickers
            ]
            benchmark_result = self._backfill_ticker(
                store,
                self.benchmark_ticker,
                start_date=start_date,
                end_date=end_date,
            )
            coverage_start = self._coverage_start(
                store,
                tickers + [self.benchmark_ticker],
            )
        finally:
            store.close()

        return PriceBackfillSummary(
            start_date=start_date,
            end_date=end_date,
            tickers_processed=len(tickers),
            tickers_backfilled=sum(result.inserted_days > 0 for result in ticker_results),
            tickers_already_complete=sum(result.already_complete for result in ticker_results),
            tickers_skipped=sum(result.skipped for result in ticker_results),
            benchmark_ticker=self.benchmark_ticker,
            benchmark_backfilled_days=benchmark_result.inserted_days,
            new_coverage_start=coverage_start,
            ticker_results=ticker_results,
            benchmark_result=benchmark_result,
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill replay-store historical prices")
    parser.add_argument("--universe-file", required=True, help="Replay universe JSON or YAML file")
    parser.add_argument("--start", required=True, help="Backfill start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="Backfill end date (YYYY-MM-DD)")
    parser.add_argument("--db", default=str(REPLAY_STORE_PATH), help="Replay SQLite store path")
    parser.add_argument("--benchmark", default="XBI", help="Benchmark ticker to backfill")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(message)s")
    parser = _build_parser()
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)
    if start_date > end_date:
        parser.error("--start must be on or before --end")

    summary = PriceBackfiller(
        replay_db_path=args.db,
        benchmark_ticker=args.benchmark,
    ).backfill(
        args.universe_file,
        start_date=start_date,
        end_date=end_date,
    )
    print(render_backfill_summary(summary))


if __name__ == "__main__":
    main()
