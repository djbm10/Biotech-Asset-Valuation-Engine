"""
Replay-store historical price backfiller.

Downloads missing replay-store price history from yfinance for a replay
universe plus the XBI benchmark, extending coverage backward to a target
start date without duplicating existing rows.

Two tables are maintained:
- `historical_prices`: replay return series used by the replay engine
- `market_prices`: volume-aware history used for replay-safe ADV filters

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

from bve.connectors.market_prices import MarketPriceRecord
from bve.ops.historical_replay import REPLAY_STORE_PATH, ReplayStore, load_replay_universe


logger = logging.getLogger(__name__)

PriceSeriesFetcher = Callable[[str, date, date], Mapping[date, float]]
MarketPriceSeriesFetcher = Callable[[str, date, date], list[MarketPriceRecord]]
_REQUIRED_PRICE_COLUMNS = {"ticker", "price_date", "close_usd"}


@dataclass(frozen=True)
class PriceBackfillResult:
    ticker: str
    inserted_days: int = 0
    market_inserted_days: int = 0
    first_new: Optional[date] = None
    last_new: Optional[date] = None
    coverage_start: Optional[date] = None
    market_coverage_start: Optional[date] = None
    already_complete: bool = False
    skipped: bool = False


@dataclass(frozen=True)
class PriceBackfillSummary:
    start_date: date
    end_date: date
    tickers_processed: int
    tickers_backfilled: int
    market_rows_backfilled: int
    tickers_already_complete: int
    tickers_skipped: int
    benchmark_ticker: str
    benchmark_backfilled_days: int
    benchmark_market_backfilled_days: int
    new_coverage_start: Optional[date]
    new_market_coverage_start: Optional[date]
    ticker_results: list[PriceBackfillResult]
    benchmark_result: PriceBackfillResult


def _download_yfinance_prices(
    ticker: str,
    start_date: date,
    end_date: date,
) -> dict[date, float]:
    return {
        record.price_date: record.close_usd
        for record in _download_yfinance_market_prices(ticker, start_date, end_date)
    }


def _download_yfinance_market_prices(
    ticker: str,
    start_date: date,
    end_date: date,
) -> list[MarketPriceRecord]:
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
        return []

    history.columns = [col[0] if isinstance(col, tuple) else col for col in history.columns]
    if "Close" not in history.columns:
        return []

    price_ticker = yf.Ticker(ticker)
    fast_info = getattr(price_ticker, "fast_info", None)
    shares = getattr(fast_info, "shares", None) if fast_info else None

    records: list[MarketPriceRecord] = []
    for idx, row in history.iterrows():
        price_date = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
        close = float(row.get("Close", 0) or 0)
        volume = int(row.get("Volume", 0) or 0)
        mc_millions = round(float(shares) * close / 1e6, 2) if shares and close else None
        records.append(
            MarketPriceRecord(
                ticker=ticker,
                price_date=price_date,
                close_usd=round(close, 4),
                adj_close_usd=round(close, 4),
                volume=volume,
                market_cap_millions=mc_millions,
            )
        )
    return records


def _format_date(value: Optional[date]) -> str:
    return value.isoformat() if value else "-"


def render_backfill_summary(summary: PriceBackfillSummary) -> str:
    lines = [
        "Backfill complete:",
        f"  Tickers processed: {summary.tickers_processed}",
        f"  Tickers backfilled: {summary.tickers_backfilled}",
        f"  Tickers already complete: {summary.tickers_already_complete}",
    ]
    if summary.market_rows_backfilled or summary.benchmark_market_backfilled_days:
        lines.append(f"  Market rows backfilled: {summary.market_rows_backfilled}")
    if summary.tickers_skipped:
        lines.append(f"  Tickers skipped: {summary.tickers_skipped}")
    lines.extend([
        f"  {summary.benchmark_ticker} backfilled: {summary.benchmark_backfilled_days} days",
        (
            f"  {summary.benchmark_ticker} market rows backfilled: "
            f"{summary.benchmark_market_backfilled_days}"
        ),
        f"  New coverage start: {_format_date(summary.new_coverage_start)}",
    ])
    if summary.new_market_coverage_start is not None:
        lines.append(f"  New market coverage start: {_format_date(summary.new_market_coverage_start)}")
    return "\n".join(lines)


class PriceBackfiller:
    def __init__(
        self,
        *,
        replay_db_path: str = str(REPLAY_STORE_PATH),
        price_fetcher: Optional[PriceSeriesFetcher] = None,
        market_price_fetcher: Optional[MarketPriceSeriesFetcher] = None,
        reporter: Optional[Callable[[str], None]] = print,
        benchmark_ticker: str = "XBI",
    ) -> None:
        self.replay_db_path = replay_db_path
        self.price_fetcher = price_fetcher or _download_yfinance_prices
        if market_price_fetcher is not None:
            self.market_price_fetcher = market_price_fetcher
        elif price_fetcher is None:
            self.market_price_fetcher = _download_yfinance_market_prices
        else:
            self.market_price_fetcher = None
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
    def _ensure_market_price_schema(store: ReplayStore) -> None:
        store._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_prices (
                ticker TEXT NOT NULL,
                price_date TEXT NOT NULL,
                close_usd REAL,
                adj_close_usd REAL,
                volume INTEGER,
                market_cap_millions REAL,
                is_adjusted INTEGER NOT NULL DEFAULT 1,
                source TEXT NOT NULL DEFAULT 'yfinance',
                ingested_at TEXT NOT NULL,
                PRIMARY KEY (ticker, price_date)
            )
            """
        )
        store._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_market_prices_ticker_date "
            "ON market_prices(ticker, price_date)"
        )
        store._conn.commit()

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
    def _earliest_market_price_date(store: ReplayStore, ticker: str) -> Optional[date]:
        row = store._conn.execute(
            "SELECT MIN(price_date) AS earliest_price_date "
            "FROM market_prices WHERE ticker = ?",
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
    def _existing_market_dates(
        store: ReplayStore,
        ticker: str,
        first_date: date,
        last_date: date,
    ) -> set[date]:
        rows = store._conn.execute(
            "SELECT price_date FROM market_prices "
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
    def _market_coverage_start(store: ReplayStore, tickers: list[str]) -> Optional[date]:
        if not tickers:
            return None
        placeholders = ",".join("?" for _ in tickers)
        row = store._conn.execute(
            f"SELECT MIN(price_date) AS first_price_date "
            f"FROM market_prices WHERE ticker IN ({placeholders})",
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

    @staticmethod
    def _insert_market_rows(
        store: ReplayStore,
        rows: list[MarketPriceRecord],
    ) -> int:
        if not rows:
            return 0
        before_changes = store._conn.total_changes
        store._conn.executemany(
            """
            INSERT OR REPLACE INTO market_prices(
                ticker, price_date, close_usd, adj_close_usd, volume,
                market_cap_millions, is_adjusted, source, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.ticker,
                    record.price_date.isoformat(),
                    record.close_usd,
                    record.adj_close_usd,
                    record.volume,
                    record.market_cap_millions,
                    1 if record.is_adjusted else 0,
                    record.source,
                    record.ingested_at.isoformat(),
                )
                for record in rows
            ],
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

    def _fetch_market_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[MarketPriceRecord]:
        if self.market_price_fetcher is None:
            return []
        try:
            return list(self.market_price_fetcher(ticker, start_date, end_date))
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s: failed to download market price history: %s", ticker, exc)
            return []

    def _backfill_ticker(
        self,
        store: ReplayStore,
        ticker: str,
        *,
        start_date: date,
        end_date: date,
    ) -> PriceBackfillResult:
        earliest_existing = self._earliest_price_date(store, ticker)
        earliest_market_existing = (
            self._earliest_market_price_date(store, ticker)
            if self.market_price_fetcher is not None
            else None
        )
        historical_complete = earliest_existing is not None and earliest_existing <= start_date
        market_complete = (
            self.market_price_fetcher is None
            or (
                earliest_market_existing is not None
                and earliest_market_existing <= start_date
            )
        )
        if historical_complete and market_complete:
            result = PriceBackfillResult(
                ticker=ticker,
                coverage_start=earliest_existing,
                market_coverage_start=earliest_market_existing,
                already_complete=True,
            )
            self._emit(f"{ticker}: already complete")
            return result

        fetch_bounds: list[date] = []
        if not historical_complete:
            fetch_bounds.append(earliest_existing or (end_date + timedelta(days=1)))
        if not market_complete:
            fetch_bounds.append(earliest_market_existing or (end_date + timedelta(days=1)))
        fetch_end = max(fetch_bounds) if fetch_bounds else (end_date + timedelta(days=1))
        upper_bound = end_date if fetch_end > end_date else fetch_end

        candidate_market_records: list[MarketPriceRecord] = []
        if self.market_price_fetcher is not None:
            fetched_market_records = self._fetch_market_prices(ticker, start_date, fetch_end)
            deduped_market_records: dict[date, MarketPriceRecord] = {}
            for record in fetched_market_records:
                if start_date <= record.price_date <= upper_bound:
                    deduped_market_records[record.price_date] = record
            candidate_market_records = [
                deduped_market_records[d] for d in sorted(deduped_market_records)
            ]
            candidate_rows = [
                (record.price_date, float(record.close_usd))
                for record in candidate_market_records
            ]
        else:
            fetched_prices = self._fetch_prices(ticker, start_date, fetch_end)
            candidate_rows = sorted(
                (price_date, float(close_usd))
                for price_date, close_usd in fetched_prices.items()
                if start_date <= price_date <= upper_bound
            )

        if not candidate_rows and not candidate_market_records:
            logger.warning("%s: no price data returned from yfinance; skipping", ticker)
            return PriceBackfillResult(
                ticker=ticker,
                coverage_start=earliest_existing,
                market_coverage_start=earliest_market_existing,
                skipped=True,
            )

        first_candidate_date = candidate_rows[0][0] if candidate_rows else candidate_market_records[0].price_date
        last_candidate_date = candidate_rows[-1][0] if candidate_rows else candidate_market_records[-1].price_date
        existing_dates = self._existing_dates(store, ticker, first_candidate_date, last_candidate_date)
        new_rows = [
            (price_date, close_usd)
            for price_date, close_usd in candidate_rows
            if price_date not in existing_dates
        ]
        inserted = self._insert_price_rows(store, ticker, new_rows)

        market_inserted = 0
        if candidate_market_records:
            existing_market_dates = self._existing_market_dates(
                store,
                ticker,
                candidate_market_records[0].price_date,
                candidate_market_records[-1].price_date,
            )
            new_market_rows = [
                record for record in candidate_market_records
                if record.price_date not in existing_market_dates
            ]
            market_inserted = self._insert_market_rows(store, new_market_rows)
        if not inserted and not market_inserted:
            logger.warning("%s: no new replay-store rows inserted; skipping", ticker)
            coverage_start = self._earliest_price_date(store, ticker)
            market_coverage_start = (
                self._earliest_market_price_date(store, ticker)
                if self.market_price_fetcher is not None
                else None
            )
            return PriceBackfillResult(
                ticker=ticker,
                coverage_start=coverage_start,
                market_coverage_start=market_coverage_start,
                skipped=True,
            )

        first_new = new_rows[0][0] if new_rows else None
        last_new = new_rows[-1][0] if new_rows else None
        coverage_start = self._earliest_price_date(store, ticker)
        market_coverage_start = (
            self._earliest_market_price_date(store, ticker)
            if self.market_price_fetcher is not None
            else None
        )
        if inserted and first_new and last_new:
            self._emit(
                f"{ticker}: backfilled {inserted} days "
                f"({_format_date(first_new)} -> {_format_date(last_new)})"
            )
        if market_inserted:
            first_market_new = candidate_market_records[0].price_date
            last_market_new = candidate_market_records[-1].price_date
            self._emit(
                f"{ticker}: backfilled {market_inserted} market rows "
                f"({_format_date(first_market_new)} -> {_format_date(last_market_new)})"
            )
        return PriceBackfillResult(
            ticker=ticker,
            inserted_days=inserted,
            market_inserted_days=market_inserted,
            first_new=first_new,
            last_new=last_new,
            coverage_start=coverage_start,
            market_coverage_start=market_coverage_start,
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
            if self.market_price_fetcher is not None:
                self._ensure_market_price_schema(store)
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
            market_coverage_start = (
                self._market_coverage_start(store, tickers + [self.benchmark_ticker])
                if self.market_price_fetcher is not None
                else None
            )
        finally:
            store.close()

        return PriceBackfillSummary(
            start_date=start_date,
            end_date=end_date,
            tickers_processed=len(tickers),
            tickers_backfilled=sum(
                (result.inserted_days > 0) or (result.market_inserted_days > 0)
                for result in ticker_results
            ),
            market_rows_backfilled=sum(result.market_inserted_days for result in ticker_results),
            tickers_already_complete=sum(result.already_complete for result in ticker_results),
            tickers_skipped=sum(result.skipped for result in ticker_results),
            benchmark_ticker=self.benchmark_ticker,
            benchmark_backfilled_days=benchmark_result.inserted_days,
            benchmark_market_backfilled_days=benchmark_result.market_inserted_days,
            new_coverage_start=coverage_start,
            new_market_coverage_start=market_coverage_start,
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
