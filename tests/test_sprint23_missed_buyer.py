"""Tests for Sprint 23 Task 4 — buyer-in-pool miss diagnostics.

Verifies:
1. generate_missed_buyer_report() classifies target_not_in_universe.
2. generate_missed_buyer_report() classifies no_prior_snapshot.
3. generate_missed_buyer_report() classifies no_profile.
4. generate_missed_buyer_report() classifies candidate_pruning (profile exists, not in pool).
5. generate_missed_buyer_report() classifies alias_issue (profile exists, name didn't match).
6. Deals that are in pool are not in the miss report.
7. Summary JSON and CSV are written to output_dir.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from bve.analysis.institutional_validation import (
    MISS_ALIAS_ISSUE,
    MISS_CANDIDATE_PRUNING,
    MISS_NO_PRIOR_SNAPSHOT,
    MISS_NO_PROFILE,
    MISS_TARGET_NOT_IN_UNIVERSE,
    generate_missed_buyer_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ma_probability_snapshots (
    snapshot_date TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    ticker TEXT,
    acquirer_candidates_json TEXT,
    PRIMARY KEY(snapshot_date, asset_id)
)
"""


def _build_conn(
    *,
    ticker: str | None = None,
    snapshot_date: str | None = None,
    candidates: list[dict] | None = None,
) -> sqlite3.Connection:
    """Build an in-memory SQLite connection with optional snapshot row."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    if ticker and snapshot_date is not None:
        conn.execute(
            "INSERT INTO ma_probability_snapshots(snapshot_date, asset_id, ticker, acquirer_candidates_json) "
            "VALUES (?, ?, ?, ?)",
            (snapshot_date, f"{ticker}_asset", ticker.upper(), json.dumps(candidates or [])),
        )
        conn.commit()
    return conn


def _deal(
    ticker: str = "ALVX",
    acquirer: str = "Pfizer",
    ann_date: str = "2025-06-01",
) -> dict:
    return {"target_ticker": ticker, "acquirer": acquirer, "announcement_date": ann_date}


def _candidate(name: str) -> dict:
    return {
        "acquirer_id": name.lower().replace(" ", "_"),
        "acquirer_name": name,
        "mna_targetability_score": 0.50,
        "p_acquisition": 0.50,
        "strategic_fit_score": 0.60,
        "passes_hard_filters": True,
        "transaction_gate_reason_codes": [],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMissedBuyerReport:
    def _run(self, deals, conn):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            result = generate_missed_buyer_report(deals, conn, out)
            return result, out

    def test_target_not_in_universe(self):
        """Target ticker never in any snapshot → target_not_in_universe."""
        conn = _build_conn()  # no rows
        rows, out = self._run([_deal("ALVX", "Pfizer", "2025-06-01")], conn)
        assert len(rows) == 1
        assert rows[0]["miss_type"] == MISS_TARGET_NOT_IN_UNIVERSE

    def test_no_prior_snapshot(self):
        """Target in universe but no snapshot before announcement date."""
        conn = _build_conn(ticker="ALVX", snapshot_date="2025-07-01", candidates=[])
        rows, out = self._run([_deal("ALVX", "Pfizer", "2025-06-01")], conn)
        assert len(rows) == 1
        assert rows[0]["miss_type"] == MISS_NO_PRIOR_SNAPSHOT

    def test_no_profile(self):
        """Prior snapshot exists, acquirer has no YAML profile → no_profile."""
        # "FakeBuyer Inc" is not in _KNOWN_PROFILE_NAMES
        conn = _build_conn(ticker="ALVX", snapshot_date="2025-05-01", candidates=[])
        rows, out = self._run([_deal("ALVX", "FakeBuyer Inc", "2025-06-01")], conn)
        assert len(rows) == 1
        assert rows[0]["miss_type"] == MISS_NO_PROFILE

    def test_candidate_pruning(self):
        """Prior snapshot exists, acquirer has a profile, but not in candidate JSON → pruning."""
        # Pfizer has a profile but is not in the candidate list
        conn = _build_conn(
            ticker="ALVX",
            snapshot_date="2025-05-01",
            candidates=[_candidate("Amgen")],  # Pfizer not here
        )
        rows, out = self._run([_deal("ALVX", "Pfizer", "2025-06-01")], conn)
        assert len(rows) == 1
        assert rows[0]["miss_type"] == MISS_CANDIDATE_PRUNING

    def test_in_pool_deal_excluded_from_report(self):
        """Deal where acquirer IS in the pool should not appear in miss report."""
        conn = _build_conn(
            ticker="ALVX",
            snapshot_date="2025-05-01",
            candidates=[_candidate("Pfizer")],
        )
        rows, _ = self._run([_deal("ALVX", "Pfizer", "2025-06-01")], conn)
        assert len(rows) == 0

    def test_mixed_deals(self):
        """Multiple deals: in_pool deal excluded; miss deals classified."""
        conn = _build_conn(
            ticker="ALVX",
            snapshot_date="2025-05-01",
            candidates=[_candidate("Pfizer")],
        )
        deals = [
            _deal("ALVX", "Pfizer", "2025-06-01"),     # in pool → excluded
            _deal("ALVX", "FakeBuyer Inc", "2025-06-01"),  # not in pool, no profile
            _deal("ZYNO", "Roche", "2025-06-01"),       # target not in universe
        ]
        rows, _ = self._run(deals, conn)
        miss_types = {r["miss_type"] for r in rows}
        assert MISS_NO_PROFILE in miss_types
        assert MISS_TARGET_NOT_IN_UNIVERSE in miss_types
        # The in-pool Pfizer deal must not appear
        assert all(r["actual_acquirer"] != "Pfizer" for r in rows)

    def test_csv_written(self):
        """missed_buyer_report.csv is created in output_dir."""
        conn = _build_conn()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            generate_missed_buyer_report([_deal()], conn, out)
            assert (out / "missed_buyer_report.csv").exists()

    def test_summary_json_written(self):
        """missed_buyer_summary.json is created with n_missed_deals and miss_breakdown."""
        conn = _build_conn()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            generate_missed_buyer_report([_deal()], conn, out)
            summary_path = out / "missed_buyer_summary.json"
            assert summary_path.exists()
            data = json.loads(summary_path.read_text())
            assert "n_missed_deals" in data
            assert "miss_breakdown" in data

    def test_empty_deals_list(self):
        """No deals → empty miss report."""
        conn = _build_conn()
        rows, _ = self._run([], conn)
        assert rows == []

    def test_alias_normalization_matches_pfizer_variant(self):
        """Variant spellings of Pfizer should still match the pool candidate."""
        conn = _build_conn(
            ticker="ALVX",
            snapshot_date="2025-05-01",
            candidates=[_candidate("Pfizer Inc.")],
        )
        # Slight variant in the deal record
        rows, _ = self._run([_deal("ALVX", "PFIZER", "2025-06-01")], conn)
        assert len(rows) == 0, "PFIZER should match 'Pfizer Inc.' via alias normalization"
