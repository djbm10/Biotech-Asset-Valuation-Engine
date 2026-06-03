from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from bve.connectors.market_prices import MarketPriceRecord
from bve.ops.historical_replay import ReplayStore
from bve.ops.price_backfiller import PriceBackfiller, render_backfill_summary


def _write_universe_file(path: Path, payload: list[dict[str, str]]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _make_price_fetcher(
    price_map: dict[str, dict[date, float]],
    calls: list[tuple[str, date, date]],
):
    def _fetch(ticker: str, start_date: date, end_date: date) -> dict[date, float]:
        calls.append((ticker, start_date, end_date))
        return price_map.get(ticker, {})

    return _fetch


def _make_market_price_fetcher(
    price_map: dict[str, list[MarketPriceRecord]],
    calls: list[tuple[str, date, date]],
):
    def _fetch(ticker: str, start_date: date, end_date: date) -> list[MarketPriceRecord]:
        calls.append((ticker, start_date, end_date))
        return price_map.get(ticker, [])

    return _fetch


def _price_rows(db_path: Path, ticker: str) -> list[tuple[str, float]]:
    store = ReplayStore(str(db_path))
    try:
        rows = store._conn.execute(
            "SELECT price_date, close_usd FROM historical_prices "
            "WHERE ticker = ? ORDER BY price_date",
            (ticker,),
        ).fetchall()
        return [(str(row["price_date"]), float(row["close_usd"])) for row in rows]
    finally:
        store.close()


def _market_rows(db_path: Path, ticker: str) -> list[tuple[str, float, int]]:
    store = ReplayStore(str(db_path))
    try:
        rows = store._conn.execute(
            "SELECT price_date, close_usd, volume FROM market_prices "
            "WHERE ticker = ? ORDER BY price_date",
            (ticker,),
        ).fetchall()
        return [(str(row["price_date"]), float(row["close_usd"]), int(row["volume"] or 0)) for row in rows]
    finally:
        store.close()


def test_backfiller_inserts_new_price_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    store = ReplayStore(str(db_path))
    store.insert_prices("ALNY", [(date(2023, 1, 5), 105.0)])
    store.close()

    universe_path = _write_universe_file(
        tmp_path / "universe.json",
        [{"ticker": "ALNY", "asset_id": "a-alny"}],
    )
    calls: list[tuple[str, date, date]] = []
    messages: list[str] = []
    fetcher = _make_price_fetcher(
        {
            "ALNY": {
                date(2023, 1, 3): 103.0,
                date(2023, 1, 4): 104.0,
                date(2023, 1, 5): 105.0,
            },
            "XBI": {
                date(2023, 1, 3): 80.0,
                date(2023, 1, 4): 81.0,
            },
        },
        calls,
    )

    summary = PriceBackfiller(
        replay_db_path=str(db_path),
        price_fetcher=fetcher,
        reporter=messages.append,
    ).backfill(
        universe_path,
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 10),
    )

    assert summary.tickers_backfilled == 1
    assert summary.benchmark_backfilled_days == 2
    assert summary.new_coverage_start == date(2023, 1, 3)
    assert ("ALNY", date(2023, 1, 3), date(2023, 1, 5)) in calls
    assert "ALNY: backfilled 2 days (2023-01-03 -> 2023-01-04)" in messages
    assert _price_rows(db_path, "ALNY") == [
        ("2023-01-03", 103.0),
        ("2023-01-04", 104.0),
        ("2023-01-05", 105.0),
    ]


def test_insert_or_ignore_does_not_duplicate_existing_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    store = ReplayStore(str(db_path))
    store.insert_prices(
        "ALNY",
        [
            (date(2023, 1, 4), 104.0),
            (date(2023, 1, 5), 105.0),
        ],
    )
    store.close()

    universe_path = _write_universe_file(
        tmp_path / "universe.json",
        [{"ticker": "ALNY", "asset_id": "a-alny"}],
    )
    calls: list[tuple[str, date, date]] = []
    fetcher = _make_price_fetcher(
        {
            "ALNY": {
                date(2023, 1, 3): 103.0,
                date(2023, 1, 4): 104.0,
            },
            "XBI": {
                date(2023, 1, 3): 80.0,
            },
        },
        calls,
    )

    summary = PriceBackfiller(
        replay_db_path=str(db_path),
        price_fetcher=fetcher,
        reporter=None,
    ).backfill(
        universe_path,
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 10),
    )

    assert summary.ticker_results[0].inserted_days == 1
    assert ("ALNY", date(2023, 1, 3), date(2023, 1, 4)) in calls
    assert _price_rows(db_path, "ALNY") == [
        ("2023-01-03", 103.0),
        ("2023-01-04", 104.0),
        ("2023-01-05", 105.0),
    ]


def test_xbi_backfilled_alongside_universe_tickers(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    store = ReplayStore(str(db_path))
    store.insert_prices("ALNY", [(date(2023, 1, 3), 103.0)])
    store.close()

    universe_path = _write_universe_file(
        tmp_path / "universe.json",
        [{"ticker": "ALNY", "asset_id": "a-alny"}],
    )
    fetcher = _make_price_fetcher(
        {
            "XBI": {
                date(2023, 1, 3): 80.0,
                date(2023, 1, 4): 81.0,
            },
        },
        [],
    )

    summary = PriceBackfiller(
        replay_db_path=str(db_path),
        price_fetcher=fetcher,
        reporter=None,
    ).backfill(
        universe_path,
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 10),
    )

    assert summary.tickers_already_complete == 1
    assert summary.benchmark_result.ticker == "XBI"
    assert summary.benchmark_backfilled_days == 2
    assert _price_rows(db_path, "XBI") == [
        ("2023-01-03", 80.0),
        ("2023-01-04", 81.0),
    ]


def test_missing_or_delisted_ticker_handled_gracefully(tmp_path: Path, caplog) -> None:
    db_path = tmp_path / "replay.sqlite"
    ReplayStore(str(db_path)).close()

    universe_path = _write_universe_file(
        tmp_path / "universe.json",
        [{"ticker": "MISS", "asset_id": "a-miss"}],
    )
    fetcher = _make_price_fetcher(
        {
            "XBI": {
                date(2023, 1, 3): 80.0,
            },
        },
        [],
    )

    with caplog.at_level(logging.WARNING):
        summary = PriceBackfiller(
            replay_db_path=str(db_path),
            price_fetcher=fetcher,
            reporter=None,
        ).backfill(
            universe_path,
            start_date=date(2023, 1, 3),
            end_date=date(2023, 1, 10),
        )

    assert summary.tickers_skipped == 1
    assert "MISS: no price data returned from yfinance; skipping" in caplog.text
    assert _price_rows(db_path, "MISS") == []


def test_summary_counts_are_correct(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    store = ReplayStore(str(db_path))
    store.insert_prices("ALNY", [(date(2023, 1, 5), 105.0)])
    store.insert_prices("CRSP", [(date(2023, 1, 3), 50.0)])
    store.close()

    universe_path = _write_universe_file(
        tmp_path / "universe.json",
        [
            {"ticker": "ALNY", "asset_id": "a-alny"},
            {"ticker": "CRSP", "asset_id": "a-crsp"},
            {"ticker": "MISS", "asset_id": "a-miss"},
        ],
    )
    fetcher = _make_price_fetcher(
        {
            "ALNY": {
                date(2023, 1, 3): 103.0,
                date(2023, 1, 4): 104.0,
                date(2023, 1, 5): 105.0,
            },
            "XBI": {
                date(2023, 1, 3): 80.0,
                date(2023, 1, 4): 81.0,
            },
        },
        [],
    )

    summary = PriceBackfiller(
        replay_db_path=str(db_path),
        price_fetcher=fetcher,
        reporter=None,
    ).backfill(
        universe_path,
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 10),
    )
    rendered = render_backfill_summary(summary)

    assert summary.tickers_processed == 3
    assert summary.tickers_backfilled == 1
    assert summary.tickers_already_complete == 1
    assert summary.tickers_skipped == 1
    assert summary.benchmark_backfilled_days == 2
    assert summary.new_coverage_start == date(2023, 1, 3)
    assert "Tickers processed: 3" in rendered
    assert "Tickers backfilled: 1" in rendered
    assert "Tickers already complete: 1" in rendered
    assert "Tickers skipped: 1" in rendered
    assert "XBI backfilled: 2 days" in rendered


def test_backfiller_populates_market_prices_with_volume_history(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    ReplayStore(str(db_path)).close()

    universe_path = _write_universe_file(
        tmp_path / "universe.json",
        [{"ticker": "ALNY", "asset_id": "a-alny"}],
    )
    calls: list[tuple[str, date, date]] = []
    fetcher = _make_market_price_fetcher(
        {
            "ALNY": [
                MarketPriceRecord(
                    ticker="ALNY",
                    price_date=date(2023, 1, 3),
                    close_usd=103.0,
                    adj_close_usd=103.0,
                    volume=1_000_000,
                    market_cap_millions=12_000.0,
                ),
                MarketPriceRecord(
                    ticker="ALNY",
                    price_date=date(2023, 1, 4),
                    close_usd=104.0,
                    adj_close_usd=104.0,
                    volume=1_200_000,
                    market_cap_millions=12_100.0,
                ),
            ],
            "XBI": [
                MarketPriceRecord(
                    ticker="XBI",
                    price_date=date(2023, 1, 3),
                    close_usd=80.0,
                    adj_close_usd=80.0,
                    volume=2_000_000,
                    market_cap_millions=None,
                ),
            ],
        },
        calls,
    )

    summary = PriceBackfiller(
        replay_db_path=str(db_path),
        market_price_fetcher=fetcher,
        reporter=None,
    ).backfill(
        universe_path,
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 10),
    )

    assert summary.tickers_backfilled == 1
    assert summary.market_rows_backfilled == 2
    assert summary.benchmark_market_backfilled_days == 1
    assert ("ALNY", date(2023, 1, 3), date(2023, 1, 11)) in calls
    assert _price_rows(db_path, "ALNY") == [
        ("2023-01-03", 103.0),
        ("2023-01-04", 104.0),
    ]
    assert _market_rows(db_path, "ALNY") == [
        ("2023-01-03", 103.0, 1_000_000),
        ("2023-01-04", 104.0, 1_200_000),
    ]


def test_backfiller_fills_market_only_gap_when_historical_prices_already_complete(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "replay.sqlite"
    store = ReplayStore(str(db_path))
    store.insert_prices(
        "ALNY",
        [
            (date(2023, 1, 3), 103.0),
            (date(2023, 1, 4), 104.0),
        ],
    )
    store.close()

    universe_path = _write_universe_file(
        tmp_path / "universe.json",
        [{"ticker": "ALNY", "asset_id": "a-alny"}],
    )
    messages: list[str] = []
    fetcher = _make_market_price_fetcher(
        {
            "ALNY": [
                MarketPriceRecord(
                    ticker="ALNY",
                    price_date=date(2023, 1, 3),
                    close_usd=103.0,
                    adj_close_usd=103.0,
                    volume=900_000,
                    market_cap_millions=11_900.0,
                ),
                MarketPriceRecord(
                    ticker="ALNY",
                    price_date=date(2023, 1, 4),
                    close_usd=104.0,
                    adj_close_usd=104.0,
                    volume=950_000,
                    market_cap_millions=12_000.0,
                ),
            ],
            "XBI": [],
        },
        [],
    )

    summary = PriceBackfiller(
        replay_db_path=str(db_path),
        market_price_fetcher=fetcher,
        reporter=messages.append,
    ).backfill(
        universe_path,
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 10),
    )

    assert summary.tickers_backfilled == 1
    assert summary.tickers_already_complete == 0
    assert summary.ticker_results[0].inserted_days == 0
    assert summary.ticker_results[0].market_inserted_days == 2
    assert _market_rows(db_path, "ALNY") == [
        ("2023-01-03", 103.0, 900_000),
        ("2023-01-04", 104.0, 950_000),
    ]
    assert "ALNY: backfilled 2 market rows (2023-01-03 -> 2023-01-04)" in messages
