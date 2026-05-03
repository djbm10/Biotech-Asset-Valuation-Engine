"""Regression tests for Sprint 22 in-place rescore of ma_probability_snapshots.

Verifies:
1. After rescore, strategic_fit_score cap rate (>= 0.95) < 10%
2. After rescore, mna_screening_score (probability) cap rate < 10%
3. transaction_gate_reason_codes are populated on capped candidates

Uses an in-memory SQLite DB with synthetic rows that have uncapped scores
(mimicking pre-Sprint-22 state).
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from bve.intelligence.ma_probability import _STRATEGIC_FIT_HARD_CAP
from bve.intelligence.ma_scoring import SATURATION_THRESHOLD


# ---------------------------------------------------------------------------
# Helpers to build synthetic snapshot DB
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ma_probability_snapshots (
    snapshot_date TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    ticker TEXT,
    stage TEXT,
    therapeutic_area TEXT,
    probability REAL NOT NULL,
    rank INTEGER NOT NULL,
    best_acquirer_id TEXT NOT NULL,
    best_acquirer_name TEXT,
    acquirer_candidates_json TEXT,
    above_alert_threshold INTEGER NOT NULL,
    strategic_fit_score REAL,
    valuation_discount_score REAL,
    de_risking_stage_score REAL,
    capital_vulnerability_score REAL,
    scarcity_score REAL,
    scarcity_peer_count INTEGER,
    scarcity_bucket TEXT,
    enterprise_value_millions REAL,
    acquisition_discount REAL,
    days_to_catalyst INTEGER,
    estimated_deal_value_low_millions REAL,
    estimated_deal_value_high_millions REAL,
    run_id TEXT,
    created_at TEXT NOT NULL,
    p_takeout_calibrated REAL,
    PRIMARY KEY(snapshot_date, asset_id)
)
"""

_SCREEN_SNAPSHOTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS screen_snapshots (
    snapshot_date TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    PRIMARY KEY(snapshot_date, asset_id)
)
"""


def _make_candidate(
    strategic_fit_score: float = 1.0,
    mna_probability_score: float = 0.98,
    capital_vulnerability_score: float = 0.05,
    valuation_discount_score: float = 0.20,
    de_risking_stage_score: float = 0.62,
) -> dict:
    return {
        "acquirer_id": "test_acquirer",
        "acquirer_name": "TestCo",
        "mna_probability_score": mna_probability_score,
        "p_acquisition": mna_probability_score,
        "raw_probability": mna_probability_score,
        "strategic_fit_score": strategic_fit_score,
        "valuation_discount_score": valuation_discount_score,
        "de_risking_stage_score": de_risking_stage_score,
        "capital_vulnerability_score": capital_vulnerability_score,
        "scarcity_score": 0.40,
        "scarcity_peer_count": 3,
        "scarcity_bucket": "moderate",
        "fit_score": 0.80,
        "passes_hard_filters": True,
        "hard_fail_reasons": [],
        "matched_therapeutic_gap": None,
        "matched_modality": None,
        "matched_priorities": [],
        "explanation": "test",
        # Pre-Sprint-22: no transaction_gate_reason_codes key
    }


def _build_synthetic_db(n_rows: int = 50) -> tuple[str, Path]:
    """Create a temp SQLite DB with n_rows of uncapped snapshot rows.

    Returns (db_path, watchlist_yaml_path).
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tmp.name
    tmp.close()

    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.executescript(_SCREEN_SNAPSHOTS_SCHEMA)

    # Insert synthetic rows with high (uncapped) strategic_fit_score
    for i in range(n_rows):
        asset_id = f"asset_{i:03d}"
        cand = _make_candidate(
            strategic_fit_score=0.98,      # pre-Sprint-22: above hard cap
            mna_probability_score=0.97,    # pre-Sprint-22: above saturation threshold
        )
        conn.execute(
            """
            INSERT INTO ma_probability_snapshots(
                snapshot_date, asset_id, ticker, stage, therapeutic_area,
                probability, rank, best_acquirer_id, best_acquirer_name,
                acquirer_candidates_json, above_alert_threshold,
                strategic_fit_score, valuation_discount_score,
                de_risking_stage_score, capital_vulnerability_score,
                scarcity_score, scarcity_peer_count, scarcity_bucket,
                run_id, created_at, p_takeout_calibrated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2025-01-01", asset_id, f"TKR{i}", "phase 3", "oncology",
                0.97,           # stale probability
                i + 1,
                "test_acquirer", "TestCo",
                json.dumps([cand]),
                1,
                0.98,           # stale strategic_fit_score (above hard cap)
                0.20,           # valuation_discount_score
                0.62,           # de_risking_stage_score
                0.05,           # capital_vulnerability_score (low → gate fires)
                0.40,           # scarcity_score
                3, "moderate",
                "old_run", "2025-01-01T00:00:00", None,
            ),
        )
    conn.commit()
    conn.close()

    # Create a minimal watchlist YAML
    wl_tmp = tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False)
    wl_tmp.write("watchlist: []\n")
    wl_tmp.close()

    return db_path, Path(wl_tmp.name)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSprint22Rescore:
    def test_strategic_fit_cap_rate_below_10pct(self, tmp_path):
        """After rescore, strategic_fit_score cap rate (>= 0.95) must be < 10%."""
        from bve.ops.ma_probability_backfiller import rescore_ma_probability_snapshots

        db_path, wl_path = _build_synthetic_db(n_rows=50)
        summary = rescore_ma_probability_snapshots(
            knowledge_db_path=db_path,
            watchlist_path=wl_path,
            score_version="v1.4",
        )

        assert summary.strategic_fit_cap_rate < 0.10, (
            f"strategic_fit_score cap rate {summary.strategic_fit_cap_rate:.1%} "
            f"exceeds 10% after rescore — Sprint 22 hard cap not applied"
        )

    def test_mna_screening_cap_rate_below_10pct(self, tmp_path):
        """After rescore, mna_screening_score (probability) cap rate (>= 0.95) must be < 10%."""
        from bve.ops.ma_probability_backfiller import rescore_ma_probability_snapshots

        db_path, wl_path = _build_synthetic_db(n_rows=50)
        summary = rescore_ma_probability_snapshots(
            knowledge_db_path=db_path,
            watchlist_path=wl_path,
            score_version="v1.4",
        )

        assert summary.mna_screening_cap_rate < 0.10, (
            f"mna_screening_score cap rate {summary.mna_screening_cap_rate:.1%} "
            f"exceeds 10% after rescore — gate logic not applied"
        )

    def test_strategic_fit_score_hard_capped_in_db(self, tmp_path):
        """strategic_fit_score in DB must not exceed _STRATEGIC_FIT_HARD_CAP after rescore."""
        from bve.ops.ma_probability_backfiller import rescore_ma_probability_snapshots

        db_path, wl_path = _build_synthetic_db(n_rows=20)
        rescore_ma_probability_snapshots(
            knowledge_db_path=db_path,
            watchlist_path=wl_path,
            score_version="v1.4",
        )

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT strategic_fit_score FROM ma_probability_snapshots WHERE strategic_fit_score IS NOT NULL"
        ).fetchall()
        conn.close()

        assert rows, "No rows found after rescore"
        max_sf = max(r[0] for r in rows)
        assert max_sf <= _STRATEGIC_FIT_HARD_CAP + 1e-9, (
            f"Max strategic_fit_score {max_sf:.4f} exceeds hard cap {_STRATEGIC_FIT_HARD_CAP} "
            f"after rescore"
        )

    def test_transaction_gate_reason_codes_populated(self, tmp_path):
        """After rescore, candidates with capped scores must have transaction_gate_reason_codes."""
        from bve.ops.ma_probability_backfiller import rescore_ma_probability_snapshots

        db_path, wl_path = _build_synthetic_db(n_rows=10)
        rescore_ma_probability_snapshots(
            knowledge_db_path=db_path,
            watchlist_path=wl_path,
            score_version="v1.4",
        )

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT acquirer_candidates_json FROM ma_probability_snapshots"
        ).fetchall()
        conn.close()

        n_with_codes = 0
        for (json_str,) in rows:
            candidates = json.loads(json_str or "[]")
            for cand in candidates:
                codes = cand.get("transaction_gate_reason_codes")
                if codes:
                    n_with_codes += 1

        assert n_with_codes > 0, (
            "No acquirer candidates have transaction_gate_reason_codes after rescore"
        )

    def test_rescore_rows_count_matches(self, tmp_path):
        """rows_rescored must equal total rows in DB."""
        from bve.ops.ma_probability_backfiller import rescore_ma_probability_snapshots

        n = 30
        db_path, wl_path = _build_synthetic_db(n_rows=n)
        summary = rescore_ma_probability_snapshots(
            knowledge_db_path=db_path,
            watchlist_path=wl_path,
            score_version="v1.4",
        )

        assert summary.rows_rescored == n, (
            f"Expected {n} rows rescored, got {summary.rows_rescored}"
        )

    def test_probability_does_not_exceed_dual_gate_cap(self, tmp_path):
        """With cv=0.05 (low pressure) and no external activity, the dual gate
        must cap probability at _MNA_PROB_DUAL_GATE_CAP (0.55)."""
        from bve.ops.ma_probability_backfiller import rescore_ma_probability_snapshots
        from bve.intelligence.ma_probability import _MNA_PROB_DUAL_GATE_CAP

        db_path, wl_path = _build_synthetic_db(n_rows=10)
        rescore_ma_probability_snapshots(
            knowledge_db_path=db_path,
            watchlist_path=wl_path,
            score_version="v1.4",
        )

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT probability, capital_vulnerability_score FROM ma_probability_snapshots"
        ).fetchall()
        conn.close()

        # All rows have cv=0.05 (low pressure) and external_deal_activity=0 (default)
        # → dual gate fires → probability must be <= _MNA_PROB_DUAL_GATE_CAP
        for prob, cv in rows:
            if cv is not None and float(cv) < 0.25:
                assert float(prob) <= _MNA_PROB_DUAL_GATE_CAP + 1e-9, (
                    f"probability {prob:.4f} exceeds dual gate cap {_MNA_PROB_DUAL_GATE_CAP} "
                    f"with low financing pressure cv={cv}"
                )
