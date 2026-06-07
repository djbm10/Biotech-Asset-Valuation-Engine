"""Tests for Sprint 23 Task 3 — Strategic vs Near-Term Transaction watchlist separation.

Verifies:
1. WatchlistType constants are defined.
2. classify_watchlist_type() logic: driver_count < 2 → strategic_watch.
3. classify_watchlist_type() logic: both financing_not_pressured + no_buyer_urgency → strategic_watch.
4. classify_watchlist_type() logic: ≥ 2 drivers → near_term_transaction.
5. MAProbabilityRow carries watchlist_type from classify_watchlist_type.
6. watchlist_type persists to and reads from SQLite.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from unittest.mock import MagicMock

import pytest

from bve.intelligence.ma_scoring import (
    FINANCING_REASON_NOT_PRESSURED,
    FINANCING_REASON_NO_BUYER_URGENCY,
    WatchlistType,
    classify_watchlist_type,
    _GATE_CODE_DUAL_LOW_PRESSURE,
    _GATE_CODE_MISSING_ALL,
)


# ---------------------------------------------------------------------------
# classify_watchlist_type unit tests
# ---------------------------------------------------------------------------

class TestClassifyWatchlistType:
    def test_zero_drivers_is_strategic(self):
        result = classify_watchlist_type(
            transaction_driver_count=0,
            gate_reason_codes=[],
        )
        assert result == WatchlistType.STRATEGIC_WATCH

    def test_one_driver_is_strategic(self):
        result = classify_watchlist_type(
            transaction_driver_count=1,
            gate_reason_codes=[],
        )
        assert result == WatchlistType.STRATEGIC_WATCH

    def test_two_drivers_is_near_term(self):
        result = classify_watchlist_type(
            transaction_driver_count=2,
            gate_reason_codes=[],
        )
        assert result == WatchlistType.NEAR_TERM_TRANSACTION

    def test_three_drivers_is_near_term(self):
        result = classify_watchlist_type(
            transaction_driver_count=3,
            gate_reason_codes=["driver:financing", "driver:catalyst", "driver:activist"],
        )
        assert result == WatchlistType.NEAR_TERM_TRANSACTION

    def test_none_driver_count_dual_gate_code_is_strategic(self):
        """Rescore path: driver_count=None but dual gate code present → strategic."""
        result = classify_watchlist_type(
            transaction_driver_count=None,
            gate_reason_codes=[_GATE_CODE_DUAL_LOW_PRESSURE],
        )
        assert result == WatchlistType.STRATEGIC_WATCH

    def test_none_driver_count_missing_all_code_is_strategic(self):
        """missing_trigger:all gate code → strategic_watch even with None driver count."""
        result = classify_watchlist_type(
            transaction_driver_count=None,
            gate_reason_codes=[_GATE_CODE_MISSING_ALL],
        )
        assert result == WatchlistType.STRATEGIC_WATCH

    def test_none_driver_count_missing_second_only_is_near_term(self):
        """missing_trigger:second (1 driver) with None count → near_term (one driver fired)."""
        result = classify_watchlist_type(
            transaction_driver_count=None,
            gate_reason_codes=["missing_trigger:second"],
        )
        # Only "missing_trigger:second" — one driver fired, but not the dual-low-pressure case
        assert result == WatchlistType.NEAR_TERM_TRANSACTION

    def test_none_driver_count_no_codes_is_near_term(self):
        result = classify_watchlist_type(
            transaction_driver_count=None,
            gate_reason_codes=[],
        )
        assert result == WatchlistType.NEAR_TERM_TRANSACTION

    def test_driver_count_two_no_low_pressure_codes_is_near_term(self):
        """driver_count=2 with no dual-gate codes → near_term."""
        result = classify_watchlist_type(
            transaction_driver_count=2,
            gate_reason_codes=["missing_trigger:second"],
        )
        assert result == WatchlistType.NEAR_TERM_TRANSACTION

    def test_watchlist_type_constants(self):
        assert WatchlistType.STRATEGIC_WATCH == "strategic_watch"
        assert WatchlistType.NEAR_TERM_TRANSACTION == "near_term_transaction"


# ---------------------------------------------------------------------------
# Integration: MAProbabilityRow carries watchlist_type
# ---------------------------------------------------------------------------

class TestRowWatchlistType:
    def _make_candidate_and_row(
        self,
        transaction_driver_count: int,
        gate_codes: list[str] | None = None,
    ):
        from bve.intelligence.ma_probability import MAAcquirerCandidate, MAProbabilityRow
        from bve.intelligence.ma_scoring import classify_watchlist_type

        gate_codes = gate_codes or []
        cand = MAAcquirerCandidate(
            acquirer_id="acq",
            acquirer_name="A",
            mna_targetability_score=0.45,
            p_acquisition=0.45,
            raw_probability=0.45,
            strategic_fit_score=0.60,
            valuation_discount_score=0.20,
            de_risking_stage_score=0.62,
            capital_vulnerability_score=0.40,
            scarcity_score=0.40,
            scarcity_peer_count=2,
            scarcity_bucket="moderate",
            fit_score=0.60,
            passes_hard_filters=True,
            explanation="x",
            transaction_driver_count=transaction_driver_count,
            transaction_gate_reason_codes=gate_codes,
        )
        row = MAProbabilityRow(
            asset_id="asset_a",
            mna_targetability_score=cand.mna_targetability_score,
            p_acquisition=cand.p_acquisition,
            raw_probability=cand.raw_probability,
            above_alert_threshold=False,
            score_version="v1.4",
            best_acquirer_id=cand.acquirer_id,
            best_acquirer_name=cand.acquirer_name,
            best_acquirer_fit_score=cand.fit_score,
            valuation_discount_score=cand.valuation_discount_score,
            strategic_fit_score=cand.strategic_fit_score,
            de_risking_stage_score=cand.de_risking_stage_score,
            capital_vulnerability_score=cand.capital_vulnerability_score,
            scarcity_score=cand.scarcity_score,
            scarcity_peer_count=cand.scarcity_peer_count,
            scarcity_bucket=cand.scarcity_bucket,
            vulnerability_score=0.40,
            explanation="x",
            acquirer_candidates=[cand],
            transaction_driver_count=cand.transaction_driver_count,
            gap_urgency=cand.gap_urgency,
            watchlist_type=classify_watchlist_type(
                transaction_driver_count=cand.transaction_driver_count,
                gate_reason_codes=list(cand.transaction_gate_reason_codes),
            ),
        )
        return row

    def test_low_driver_count_row_is_strategic(self):
        row = self._make_candidate_and_row(transaction_driver_count=1)
        assert row.watchlist_type == WatchlistType.STRATEGIC_WATCH

    def test_high_driver_count_row_is_near_term(self):
        row = self._make_candidate_and_row(transaction_driver_count=2)
        assert row.watchlist_type == WatchlistType.NEAR_TERM_TRANSACTION

    def test_watchlist_type_defaults_none(self):
        from bve.intelligence.ma_probability import MAProbabilityRow
        row = MAProbabilityRow(
            asset_id="x",
            mna_targetability_score=0.3,
            p_acquisition=0.3,
            raw_probability=0.3,
            above_alert_threshold=False,
            score_version="v1.4",
            best_acquirer_id="a",
            best_acquirer_name="A",
            best_acquirer_fit_score=0.5,
            valuation_discount_score=0.1,
            strategic_fit_score=0.5,
            de_risking_stage_score=0.5,
            capital_vulnerability_score=0.3,
            scarcity_score=0.3,
            scarcity_peer_count=2,
            scarcity_bucket="moderate",
            vulnerability_score=0.3,
            explanation="x",
        )
        assert row.watchlist_type is None


# ---------------------------------------------------------------------------
# Integration: DB round-trip for watchlist_type
# ---------------------------------------------------------------------------

class TestWatchlistTypeSnapshotRoundtrip:
    def _build_store(self):
        import sqlite3
        from bve.intelligence.ma_probability import MAProbabilitySnapshotStore
        from unittest.mock import MagicMock

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        knowledge = MagicMock()
        knowledge._conn = conn

        def _ensure_column(table, col, coltype):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
                conn.commit()
            except Exception:
                pass

        def _coerce_datetime(val):
            from datetime import datetime
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(str(val))

        knowledge._ensure_column = _ensure_column
        knowledge._coerce_datetime = _coerce_datetime
        return MAProbabilitySnapshotStore(knowledge), conn

    def _make_row(self, watchlist_type: str) -> "MAProbabilityRow":
        from bve.intelligence.ma_probability import MAAcquirerCandidate, MAProbabilityRow
        cand = MAAcquirerCandidate(
            acquirer_id="acq",
            acquirer_name="A",
            mna_targetability_score=0.50,
            p_acquisition=0.50,
            raw_probability=0.50,
            strategic_fit_score=0.60,
            valuation_discount_score=0.20,
            de_risking_stage_score=0.60,
            capital_vulnerability_score=0.35,
            scarcity_score=0.40,
            scarcity_peer_count=3,
            scarcity_bucket="moderate",
            fit_score=0.65,
            passes_hard_filters=True,
            explanation="x",
        )
        return MAProbabilityRow(
            asset_id="asset_wt",
            mna_targetability_score=0.50,
            p_acquisition=0.50,
            raw_probability=0.50,
            above_alert_threshold=False,
            score_version="v1.4",
            best_acquirer_id="acq",
            best_acquirer_name="A",
            best_acquirer_fit_score=0.65,
            valuation_discount_score=0.20,
            strategic_fit_score=0.60,
            de_risking_stage_score=0.60,
            capital_vulnerability_score=0.35,
            scarcity_score=0.40,
            scarcity_peer_count=3,
            scarcity_bucket="moderate",
            vulnerability_score=0.35,
            explanation="x",
            acquirer_candidates=[cand],
            watchlist_type=watchlist_type,
        )

    def test_strategic_watch_persists(self):
        store, conn = self._build_store()
        row = self._make_row(WatchlistType.STRATEGIC_WATCH)
        store.write_snapshots([row], snapshot_date=date(2025, 1, 1))
        result = store.get_snapshot_map(snapshot_date=date(2025, 1, 1))
        assert result["asset_wt"].watchlist_type == WatchlistType.STRATEGIC_WATCH

    def test_near_term_persists(self):
        store, conn = self._build_store()
        row = self._make_row(WatchlistType.NEAR_TERM_TRANSACTION)
        store.write_snapshots([row], snapshot_date=date(2025, 1, 1))
        result = store.list_snapshots(start_date=date(2025, 1, 1), end_date=date(2025, 1, 1))
        assert len(result) == 1
        assert result[0].watchlist_type == WatchlistType.NEAR_TERM_TRANSACTION

    def test_null_watchlist_type_persists_as_none(self):
        store, conn = self._build_store()
        row = self._make_row(None)
        store.write_snapshots([row], snapshot_date=date(2025, 1, 1))
        result = store.get_snapshot_map(snapshot_date=date(2025, 1, 1))
        assert result["asset_wt"].watchlist_type is None
