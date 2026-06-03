"""Tests for Sprint 23 Task 5 — forward paper log new fields.

Verifies:
1. _load_ece_gate_passes() returns False when report is absent.
2. _load_ece_gate_passes() returns False when report has gate=False.
3. _load_ece_gate_passes() returns True when report has gate=True.
4. _extract_ma_snapshot_fields() returns empty dict when no row found.
5. _extract_ma_snapshot_fields() returns watchlist_type, calibrated_score,
   transaction_driver_count from a row.
6. _extract_ma_snapshot_fields() extracts gate_reason_codes from candidates JSON.
7. _extract_ma_snapshot_fields() extracts top5_acquirers (max 5 names).
8. calibrated_score_label is "rank_score" when ECE gate does not pass.
9. calibrated_score_label is "probability_estimate" when ECE gate passes.
10. write_paper_tracking_entry() persists new fields to DB and they round-trip.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import date
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# _load_ece_gate_passes
# ---------------------------------------------------------------------------

from bve.cli.paper_tracking import _load_ece_gate_passes, _extract_ma_snapshot_fields


class TestLoadEceGatePasses:
    def test_missing_file_returns_false(self, tmp_path):
        assert _load_ece_gate_passes(tmp_path / "nonexistent.json") is False

    def test_gate_false_in_report(self, tmp_path):
        p = tmp_path / "report.json"
        p.write_text(json.dumps({"calibration_gate_passes": False}))
        assert _load_ece_gate_passes(p) is False

    def test_gate_true_in_report(self, tmp_path):
        p = tmp_path / "report.json"
        p.write_text(json.dumps({"calibration_gate_passes": True}))
        assert _load_ece_gate_passes(p) is True

    def test_malformed_json_returns_false(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("NOT JSON {{{")
        assert _load_ece_gate_passes(p) is False

    def test_missing_key_returns_false(self, tmp_path):
        p = tmp_path / "report.json"
        p.write_text(json.dumps({"some_other_key": True}))
        assert _load_ece_gate_passes(p) is False


# ---------------------------------------------------------------------------
# _extract_ma_snapshot_fields
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ma_probability_snapshots (
    snapshot_date TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    ticker TEXT,
    probability REAL NOT NULL DEFAULT 0.5,
    rank INTEGER NOT NULL DEFAULT 1,
    best_acquirer_id TEXT NOT NULL DEFAULT '',
    above_alert_threshold INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT '2025-01-01T00:00:00Z',
    watchlist_type TEXT,
    p_takeout_calibrated REAL,
    transaction_driver_count INTEGER,
    acquirer_candidates_json TEXT,
    PRIMARY KEY(snapshot_date, asset_id)
)
"""


def _make_conn(*, asset_id=None, snapshot_date=None, row_kwargs=None) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    if asset_id and snapshot_date:
        defaults = {
            "watchlist_type": None,
            "p_takeout_calibrated": None,
            "transaction_driver_count": None,
            "acquirer_candidates_json": None,
        }
        if row_kwargs:
            defaults.update(row_kwargs)
        conn.execute(
            """INSERT INTO ma_probability_snapshots(
                snapshot_date, asset_id, watchlist_type, p_takeout_calibrated,
                transaction_driver_count, acquirer_candidates_json
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                snapshot_date,
                asset_id,
                defaults["watchlist_type"],
                defaults["p_takeout_calibrated"],
                defaults["transaction_driver_count"],
                defaults["acquirer_candidates_json"],
            ),
        )
        conn.commit()
    return conn


class TestExtractMaSnapshotFields:
    def test_no_row_returns_empty(self):
        conn = _make_conn()
        result = _extract_ma_snapshot_fields(conn, date(2025, 6, 1), "ALVX_asset")
        assert result == {}

    def test_returns_watchlist_type(self):
        conn = _make_conn(
            asset_id="alvx",
            snapshot_date="2025-05-01",
            row_kwargs={"watchlist_type": "strategic_watch"},
        )
        result = _extract_ma_snapshot_fields(conn, date(2025, 6, 1), "alvx")
        assert result["watchlist_type"] == "strategic_watch"

    def test_returns_calibrated_score(self):
        conn = _make_conn(
            asset_id="alvx",
            snapshot_date="2025-05-01",
            row_kwargs={"p_takeout_calibrated": 0.42},
        )
        result = _extract_ma_snapshot_fields(conn, date(2025, 6, 1), "alvx")
        assert result["calibrated_score"] == pytest.approx(0.42, abs=1e-6)

    def test_returns_transaction_driver_count(self):
        conn = _make_conn(
            asset_id="alvx",
            snapshot_date="2025-05-01",
            row_kwargs={"transaction_driver_count": 2},
        )
        result = _extract_ma_snapshot_fields(conn, date(2025, 6, 1), "alvx")
        assert result["transaction_driver_count"] == 2

    def test_extracts_gate_reason_codes_from_best_candidate(self):
        candidates = [
            {
                "acquirer_id": "pfizer",
                "acquirer_name": "Pfizer",
                "mna_probability_score": 0.55,
                "p_acquisition": 0.55,
                "strategic_fit_score": 0.70,
                "passes_hard_filters": True,
                "transaction_gate_reason_codes": ["missing_trigger:second"],
            }
        ]
        conn = _make_conn(
            asset_id="alvx",
            snapshot_date="2025-05-01",
            row_kwargs={"acquirer_candidates_json": json.dumps(candidates)},
        )
        result = _extract_ma_snapshot_fields(conn, date(2025, 6, 1), "alvx")
        assert result["gate_reason_codes"] == ["missing_trigger:second"]

    def test_extracts_top5_acquirers(self):
        candidates = [
            {"acquirer_id": f"acq{i}", "acquirer_name": f"Acq{i}",
             "mna_probability_score": 0.5, "p_acquisition": 0.5,
             "strategic_fit_score": 0.5, "passes_hard_filters": True,
             "transaction_gate_reason_codes": []}
            for i in range(7)
        ]
        conn = _make_conn(
            asset_id="alvx",
            snapshot_date="2025-05-01",
            row_kwargs={"acquirer_candidates_json": json.dumps(candidates)},
        )
        result = _extract_ma_snapshot_fields(conn, date(2025, 6, 1), "alvx")
        assert len(result["top5_acquirers"]) == 5
        assert result["top5_acquirers"][0] == "Acq0"

    def test_no_prior_snapshot_returns_empty(self):
        """Snapshot date after snap_date → no row returned."""
        conn = _make_conn(
            asset_id="alvx",
            snapshot_date="2025-07-01",  # future
            row_kwargs={"watchlist_type": "near_term_transaction"},
        )
        result = _extract_ma_snapshot_fields(conn, date(2025, 6, 1), "alvx")
        assert result == {}

    def test_picks_most_recent_prior_snapshot(self):
        """When multiple snapshots exist, picks the most recent <= snap_date."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        for snap_date, wt in [("2025-03-01", "strategic_watch"), ("2025-05-01", "near_term_transaction")]:
            conn.execute(
                """INSERT INTO ma_probability_snapshots(
                    snapshot_date, asset_id, watchlist_type
                ) VALUES (?, ?, ?)""",
                (snap_date, "alvx", wt),
            )
        conn.commit()
        result = _extract_ma_snapshot_fields(conn, date(2025, 6, 1), "alvx")
        assert result["watchlist_type"] == "near_term_transaction"


# ---------------------------------------------------------------------------
# DB round-trip: write_paper_tracking_entry with new fields
# ---------------------------------------------------------------------------

class TestPaperTrackingEntryRoundtrip:
    def _make_store_conn(self):
        """Return a KnowledgeStore backed by an in-memory SQLite."""
        from unittest.mock import MagicMock
        import sqlite3
        from bve.intelligence.knowledge_layer import KnowledgeStore

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        store = KnowledgeStore(db_path)
        return store, db_path

    def test_new_fields_persist_and_round_trip(self):
        store, db_path = self._make_store_conn()
        try:
            store.write_paper_tracking_entry(
                entry_id="test-001",
                snapshot_date=date(2025, 6, 1),
                asset_id="alvx",
                recommendation="add",
                ticker="ALVX",
                composite_score=0.72,
                watchlist_type="near_term_transaction",
                calibrated_score=0.38,
                calibrated_score_label="rank_score",
                transaction_driver_count=2,
                gate_reason_codes=["missing_trigger:second"],
                top5_acquirers=["Pfizer", "Roche", "Amgen"],
            )
            entries = store.get_paper_tracking_entries(since=date(2025, 1, 1))
        finally:
            store.close()
            Path(db_path).unlink(missing_ok=True)

        assert len(entries) == 1
        row = entries[0]
        assert row["watchlist_type"] == "near_term_transaction"
        assert row["calibrated_score"] == pytest.approx(0.38, abs=1e-6)
        assert row["calibrated_score_label"] == "rank_score"
        assert row["transaction_driver_count"] == 2
        codes = json.loads(row["gate_reason_codes"])
        assert codes == ["missing_trigger:second"]
        top5 = json.loads(row["top5_acquirers"])
        assert top5 == ["Pfizer", "Roche", "Amgen"]

    def test_null_new_fields_persist(self):
        store, db_path = self._make_store_conn()
        try:
            store.write_paper_tracking_entry(
                entry_id="test-002",
                snapshot_date=date(2025, 6, 1),
                asset_id="alvx",
                recommendation="watch",
            )
            entries = store.get_paper_tracking_entries(since=date(2025, 1, 1))
        finally:
            store.close()
            Path(db_path).unlink(missing_ok=True)

        assert len(entries) == 1
        row = entries[0]
        assert row.get("watchlist_type") is None
        assert row.get("calibrated_score") is None
        assert row.get("transaction_driver_count") is None

    def test_calibrated_score_label_probability_when_ece_passes(self, tmp_path):
        """When the holdout report shows ECE gate passes, label is probability_estimate."""
        report = tmp_path / "holdout.json"
        report.write_text(json.dumps({"calibration_gate_passes": True}))
        assert _load_ece_gate_passes(report) is True
        # The label the snapshot_main would use:
        label = "probability_estimate" if _load_ece_gate_passes(report) else "rank_score"
        assert label == "probability_estimate"

    def test_calibrated_score_label_rank_score_when_ece_fails(self, tmp_path):
        report = tmp_path / "holdout.json"
        report.write_text(json.dumps({"calibration_gate_passes": False}))
        label = "probability_estimate" if _load_ece_gate_passes(report) else "rank_score"
        assert label == "rank_score"
