"""
Tests for PriceReactionTracker (Wave 1B — price reaction tracking).

Uses an in-memory KnowledgeStore; does not touch yfinance.
Covers: record() idempotency, volume spike detection, resolve_pending()
incremental window resolution, fully_resolved flag, and no-ticker path.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from bve.connectors.market_prices import MarketPriceRecord
from bve.intelligence.knowledge_layer import KnowledgeStore, StoredValuationDiff
from bve.intelligence.market_expectations import MarketExpectation
from bve.intelligence.price_reaction import EventOutcome, PriceReactionTracker
from bve.intelligence.schemas.signals import EventType, StructuredSignal
from bve.utils.trading_calendar import trading_days_after


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def knowledge(tmp_path):
    ks = KnowledgeStore(str(tmp_path / "test.db"))
    yield ks
    ks.close()


@pytest.fixture
def tracker(knowledge):
    return PriceReactionTracker(knowledge)


_SIGNAL_DATE = date(2024, 1, 2)   # Tuesday


def _signal(
    event_type: EventType = EventType.TRIAL_READOUT,
    signal_date: date = _SIGNAL_DATE,
    confidence: float = 0.85,
) -> StructuredSignal:
    eid = str(uuid.uuid4())
    return StructuredSignal(
        id=str(uuid.uuid4()),
        event_id=eid,
        event_type=event_type,
        signal_date=signal_date,
        extraction_confidence=confidence,
        asset_id="test-asset",
        company_id="test-co",
        created_at=datetime.now(timezone.utc),
    )


def _diff(
    event_id: str = "evt-001",
    asset_id: str = "test-asset",
    delta_npv: float = 80.0,
    before_npv: float = 400.0,
) -> StoredValuationDiff:
    return StoredValuationDiff(
        run_id=str(uuid.uuid4()),
        event_id=event_id,
        asset_id=asset_id,
        valuation_before={"rnpv_millions": before_npv},
        valuation_after={"rnpv_millions": before_npv + delta_npv},
        delta_npv=delta_npv,
        created_at=datetime.now(timezone.utc),
    )


def _price_record(
    ticker: str = "TEST",
    price_date: date = _SIGNAL_DATE,
    close: float = 20.0,
    volume: int = 500_000,
) -> MarketPriceRecord:
    return MarketPriceRecord(
        ticker=ticker,
        price_date=price_date,
        close_usd=close,
        adj_close_usd=close,
        volume=volume,
        market_cap_millions=500.0,
        ingested_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Tests: record()
# ---------------------------------------------------------------------------

class TestRecord:
    def test_creates_outcome_row(self, tracker, knowledge):
        sig = _signal()
        diff = _diff(event_id=sig.event_id)
        outcome = tracker.record(diff, sig, ticker=None)
        assert outcome is not None
        assert outcome.event_id == sig.event_id
        assert outcome.asset_id == "test-asset"

    def test_idempotent_on_same_event_id(self, tracker, knowledge):
        sig = _signal()
        diff = _diff(event_id=sig.event_id)
        first = tracker.record(diff, sig, ticker=None)
        second = tracker.record(diff, sig, ticker=None)
        assert first is not None
        assert second is None  # skipped as duplicate

    def test_model_delta_pct_computed(self, tracker):
        sig = _signal()
        diff = _diff(event_id=sig.event_id, delta_npv=40.0, before_npv=200.0)
        outcome = tracker.record(diff, sig, ticker=None)
        assert outcome.model_delta_pct == pytest.approx(20.0, abs=0.01)

    def test_model_delta_pct_none_when_before_zero(self, tracker):
        sig = _signal()
        diff = _diff(event_id=sig.event_id, delta_npv=40.0, before_npv=0.0)
        outcome = tracker.record(diff, sig, ticker=None)
        assert outcome.model_delta_pct is None

    def test_no_ticker_no_price(self, tracker):
        sig = _signal()
        diff = _diff(event_id=sig.event_id)
        outcome = tracker.record(diff, sig, ticker=None)
        assert outcome.price_before is None
        assert outcome.volume_spike_at_signal is False

    def test_price_before_loaded_from_knowledge(self, tracker, knowledge):
        knowledge.upsert_market_price(_price_record(close=25.0))
        sig = _signal()
        diff = _diff(event_id=sig.event_id)
        outcome = tracker.record(diff, sig, ticker="TEST")
        assert outcome.price_before == 25.0

    def test_no_volume_spike_when_volume_normal(self, tracker, knowledge):
        # Insert 20 days of history at 500K volume, then signal day also 500K
        base_date = date(2023, 12, 1)
        for i in range(20):
            d = date(2023, 12, 1 + i % 28)
            knowledge.upsert_market_price(_price_record(price_date=d, volume=500_000))
        knowledge.upsert_market_price(_price_record(price_date=_SIGNAL_DATE, volume=500_000))
        sig = _signal()
        diff = _diff(event_id=sig.event_id)
        outcome = tracker.record(diff, sig, ticker="TEST")
        assert outcome.volume_spike_at_signal is False

    def test_volume_spike_detected(self, tracker, knowledge):
        # 20-day avg volume = 100K; signal-day volume = 300K → spike (> 2×)
        for i in range(20):
            d = date(2023, 12, 1 + i % 28)
            knowledge.upsert_market_price(_price_record(price_date=d, volume=100_000))
        knowledge.upsert_market_price(_price_record(price_date=_SIGNAL_DATE, volume=300_000))
        sig = _signal()
        diff = _diff(event_id=sig.event_id)
        outcome = tracker.record(diff, sig, ticker="TEST")
        assert outcome.volume_spike_at_signal is True


# ---------------------------------------------------------------------------
# Tests: resolve_pending()
# ---------------------------------------------------------------------------

class TestResolvePending:
    def _seed(self, tracker, knowledge, signal_date=_SIGNAL_DATE):
        knowledge.upsert_market_price(_price_record(price_date=signal_date, close=20.0))
        sig = _signal(signal_date=signal_date)
        sig = sig.model_copy(update={"event_id": str(uuid.uuid4())})
        diff = _diff(event_id=sig.event_id)
        tracker.record(diff, sig, ticker="TEST")
        return sig.event_id

    def test_no_resolutions_before_window_elapsed(self, tracker, knowledge):
        self._seed(tracker, knowledge)
        # as_of = signal_date itself → T+1 not yet elapsed
        n = tracker.resolve_pending(as_of=_SIGNAL_DATE)
        assert n == 0

    def test_resolves_t1_when_price_available(self, tracker, knowledge):
        self._seed(tracker, knowledge)
        t1_date = trading_days_after(_SIGNAL_DATE, 1)
        knowledge.upsert_market_price(_price_record(price_date=t1_date, close=22.0))
        n = tracker.resolve_pending(as_of=t1_date)
        assert n >= 1

    def test_market_return_computed_correctly(self, tracker, knowledge):
        self._seed(tracker, knowledge)
        t1_date = trading_days_after(_SIGNAL_DATE, 1)
        knowledge.upsert_market_price(_price_record(price_date=t1_date, close=22.0))
        tracker.resolve_pending(as_of=t1_date)

        # Read return from DB
        row = knowledge._conn.execute(
            "SELECT market_return_t1, resolved_t1 FROM event_outcomes LIMIT 1"
        ).fetchone()
        # (22 - 20) / 20 = 0.1
        assert row["resolved_t1"] == 1
        assert abs(row["market_return_t1"] - 0.1) < 1e-5

    def test_fully_resolved_only_when_all_windows_done(self, tracker, knowledge):
        self._seed(tracker, knowledge)
        # Only provide T+1 price; T+5/30/90/180 not yet available
        t1_date = trading_days_after(_SIGNAL_DATE, 1)
        knowledge.upsert_market_price(_price_record(price_date=t1_date, close=22.0))
        tracker.resolve_pending(as_of=t1_date)

        row = knowledge._conn.execute(
            "SELECT fully_resolved FROM event_outcomes LIMIT 1"
        ).fetchone()
        assert row["fully_resolved"] == 0

    def test_idempotent_resolution(self, tracker, knowledge):
        self._seed(tracker, knowledge)
        t1_date = trading_days_after(_SIGNAL_DATE, 1)
        knowledge.upsert_market_price(_price_record(price_date=t1_date, close=22.0))
        n1 = tracker.resolve_pending(as_of=t1_date)
        n2 = tracker.resolve_pending(as_of=t1_date)
        # Second call resolves 0 new windows (already resolved)
        assert n2 == 0

    def test_no_ticker_skipped(self, tracker, knowledge):
        sig = _signal()
        diff = _diff(event_id=sig.event_id)
        tracker.record(diff, sig, ticker=None)
        n = tracker.resolve_pending(as_of=date(2030, 1, 1))
        assert n == 0
