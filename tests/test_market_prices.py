"""
Tests for MarketPriceRecord upsert/query methods on KnowledgeStore (Wave 1A).

Does NOT use yfinance — all records are constructed directly.
Covers: upsert idempotency, get_latest_price, get_price_on_or_before,
get_20day_avg_volume, and bulk upsert_market_prices.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from bve.connectors.market_prices import MarketPriceRecord
from bve.intelligence.knowledge_layer import KnowledgeStore


@pytest.fixture
def knowledge(tmp_path):
    ks = KnowledgeStore(str(tmp_path / "prices_test.db"))
    yield ks
    ks.close()


def _rec(
    ticker: str = "TEST",
    price_date: date = date(2024, 1, 2),
    close: float = 20.0,
    adj_close: float = 20.0,
    volume: int = 500_000,
    market_cap: float = 500.0,
) -> MarketPriceRecord:
    return MarketPriceRecord(
        ticker=ticker,
        price_date=price_date,
        close_usd=close,
        adj_close_usd=adj_close,
        volume=volume,
        market_cap_millions=market_cap,
        ingested_at=datetime.now(timezone.utc),
    )


class TestUpsertMarketPrice:
    def test_single_upsert_roundtrip(self, knowledge):
        r = _rec()
        knowledge.upsert_market_price(r)
        fetched = knowledge.get_latest_price("TEST")
        assert fetched is not None
        assert fetched.close_usd == 20.0
        assert fetched.ticker == "TEST"

    def test_upsert_idempotent(self, knowledge):
        r = _rec()
        knowledge.upsert_market_price(r)
        knowledge.upsert_market_price(r)  # second upsert should not error or duplicate
        count = knowledge._conn.execute(
            "SELECT COUNT(*) FROM market_prices WHERE ticker = 'TEST'"
        ).fetchone()[0]
        assert count == 1

    def test_upsert_replaces_on_same_date(self, knowledge):
        d = date(2024, 1, 2)
        knowledge.upsert_market_price(_rec(price_date=d, close=20.0))
        knowledge.upsert_market_price(_rec(price_date=d, close=25.0))
        fetched = knowledge.get_latest_price("TEST")
        assert fetched.close_usd == 25.0


class TestGetLatestPrice:
    def test_returns_most_recent(self, knowledge):
        knowledge.upsert_market_price(_rec(price_date=date(2024, 1, 1), close=10.0))
        knowledge.upsert_market_price(_rec(price_date=date(2024, 1, 5), close=15.0))
        fetched = knowledge.get_latest_price("TEST")
        assert fetched.price_date == date(2024, 1, 5)
        assert fetched.close_usd == 15.0

    def test_returns_none_for_unknown_ticker(self, knowledge):
        assert knowledge.get_latest_price("UNKNOWN") is None

    def test_ticker_isolation(self, knowledge):
        knowledge.upsert_market_price(_rec(ticker="AAA", price_date=date(2024, 1, 5), close=50.0))
        knowledge.upsert_market_price(_rec(ticker="BBB", price_date=date(2024, 1, 5), close=99.0))
        assert knowledge.get_latest_price("AAA").close_usd == 50.0
        assert knowledge.get_latest_price("BBB").close_usd == 99.0


class TestGetPriceOnOrBefore:
    def test_exact_date_match(self, knowledge):
        knowledge.upsert_market_price(_rec(price_date=date(2024, 1, 3), close=30.0))
        fetched = knowledge.get_price_on_or_before("TEST", date(2024, 1, 3))
        assert fetched is not None
        assert fetched.close_usd == 30.0

    def test_returns_most_recent_before_date(self, knowledge):
        knowledge.upsert_market_price(_rec(price_date=date(2024, 1, 2), close=20.0))
        knowledge.upsert_market_price(_rec(price_date=date(2024, 1, 4), close=40.0))
        # Ask for 2024-01-03; should return the Jan 2 row
        fetched = knowledge.get_price_on_or_before("TEST", date(2024, 1, 3))
        assert fetched is not None
        assert fetched.price_date == date(2024, 1, 2)

    def test_returns_none_when_all_after(self, knowledge):
        knowledge.upsert_market_price(_rec(price_date=date(2024, 1, 10), close=10.0))
        fetched = knowledge.get_price_on_or_before("TEST", date(2024, 1, 5))
        assert fetched is None


class TestGet20DayAvgVolume:
    def test_returns_avg_over_available_days(self, knowledge):
        # Insert 10 days of 1M volume
        for i in range(10):
            d = date(2024, 1, 2 + i)
            knowledge.upsert_market_price(_rec(price_date=d, volume=1_000_000))
        avg = knowledge.get_20day_avg_volume("TEST", date(2024, 1, 15))
        assert avg is not None
        assert abs(avg - 1_000_000) < 1

    def test_returns_none_for_no_data(self, knowledge):
        avg = knowledge.get_20day_avg_volume("UNKNOWN", date(2024, 1, 15))
        assert avg is None

    def test_excludes_dates_after_as_of(self, knowledge):
        # 5 days before as_of at 1M, 5 days after at 10M
        as_of = date(2024, 1, 15)
        for i in range(1, 6):
            knowledge.upsert_market_price(
                _rec(price_date=date(2024, 1, 10 + i), volume=1_000_000)
            )
        for i in range(1, 6):
            knowledge.upsert_market_price(
                _rec(price_date=date(2024, 1, 20 + i), volume=10_000_000)
            )
        avg = knowledge.get_20day_avg_volume("TEST", as_of)
        assert avg is not None
        # Only the pre-as_of rows should be averaged
        assert avg < 5_000_000


class TestUpsertMarketPrices:
    def test_bulk_insert_returns_count(self, knowledge):
        records = [
            _rec(price_date=date(2024, 1, i + 2), close=float(10 + i))
            for i in range(5)
        ]
        n = knowledge.upsert_market_prices(records)
        assert n == 5

    def test_bulk_empty_list(self, knowledge):
        n = knowledge.upsert_market_prices([])
        assert n == 0

    def test_bulk_all_retrievable(self, knowledge):
        records = [
            _rec(price_date=date(2024, 1, 2 + i))
            for i in range(3)
        ]
        knowledge.upsert_market_prices(records)
        latest = knowledge.get_latest_price("TEST")
        assert latest.price_date == date(2024, 1, 4)
