"""
Sprint 25 — Thesis strength in screen snapshots + bve-claim-resolve CLI.

Tests cover:
  - ScreenRow.thesis_strength field (default None, round-trip)
  - screen_snapshots schema migration (thesis_strength column added to existing DB)
  - write_screen_snapshots() persists thesis_strength
  - get_screen_snapshots() returns thesis_strength
  - bve-claim-resolve list / resolve / expire-overdue
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_screen_row(ticker: str = "VKTX", thesis_strength=None):
    from bve.analysis.implied_pos_batch import ScreenRow
    return ScreenRow(
        ticker=ticker,
        program_label="VK2735 obesity",
        stage="Phase 2",
        ta="metabolic",
        model_pos=0.45,
        implied_pos=0.30,
        spread_pp=15.0,
        rnpv_millions=3200.0,
        ev_millions=2100.0,
        acquisition_discount_pct=-34.3,
        next_catalyst="Ph2 readout",
        catalyst_date=None,
        days_to_catalyst=None,
        single_asset=True,
        approximation_warning=None,
        data_date=date(2026, 3, 29),
        thesis_strength=thesis_strength,
    )


def _make_store(tmp_path: Path):
    from bve.intelligence.knowledge_layer import KnowledgeStore
    return KnowledgeStore(str(tmp_path / "test.db"))


def _make_tracker(store):
    from bve.intelligence.thesis_tracker import ThesisTracker
    return ThesisTracker(store)


def _make_claim(store, asset_id: str = "a-vktx"):
    from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
    tt = ThesisTracker(store)
    return tt.add_claim(
        asset_id=asset_id,
        company_id="c-vktx",
        claim_type=ClaimType.ENDPOINT_MET,
        assertion="VK2735 meets primary weight loss endpoint",
        resolution_date=date(2026, 6, 1),
    )


# ===========================================================================
# 1. ScreenRow.thesis_strength
# ===========================================================================

class TestScreenRowThesisStrength:
    def test_default_is_none(self):
        row = _make_screen_row()
        assert row.thesis_strength is None

    def test_float_value_accepted(self):
        row = _make_screen_row(thesis_strength=0.75)
        assert row.thesis_strength == pytest.approx(0.75)

    def test_zero_accepted(self):
        row = _make_screen_row(thesis_strength=0.0)
        assert row.thesis_strength == 0.0

    def test_one_accepted(self):
        row = _make_screen_row(thesis_strength=1.0)
        assert row.thesis_strength == 1.0


# ===========================================================================
# 2. screen_snapshots schema migration
# ===========================================================================

class TestScreenSnapshotSchema:
    def test_thesis_strength_column_created_fresh_db(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(str(tmp_path / "test.db"))
        cols = {
            row[1]
            for row in store._conn.execute("PRAGMA table_info(screen_snapshots)")
        }
        assert "thesis_strength" in cols
        assert "asset_id" in cols
        store.close()

    def test_migration_on_existing_db_without_column(self, tmp_path):
        """DB without thesis_strength gets the column via _ensure_column migration."""
        db_path = str(tmp_path / "legacy.db")
        # Create a DB with screen_snapshots but no thesis_strength
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE screen_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(ticker, snapshot_date)
            )
        """)
        conn.commit()
        conn.close()

        # Opening via KnowledgeStore should add the column
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(db_path)
        cols = {
            row[1]
            for row in store._conn.execute("PRAGMA table_info(screen_snapshots)")
        }
        assert "thesis_strength" in cols
        assert "asset_id" in cols
        store.close()


# ===========================================================================
# 3. write_screen_snapshots + get_screen_snapshots round-trip
# ===========================================================================

class TestWriteReadThesisStrength:
    def test_write_none_thesis_strength(self, tmp_path):
        store = _make_store(tmp_path)
        row = _make_screen_row(thesis_strength=None)
        n = store.write_screen_snapshots([row])
        assert n == 1
        rows = store.get_screen_snapshots()
        assert len(rows) == 1
        assert rows[0]["thesis_strength"] is None
        store.close()

    def test_write_numeric_thesis_strength(self, tmp_path):
        store = _make_store(tmp_path)
        row = _make_screen_row(thesis_strength=0.80)
        store.write_screen_snapshots([row])
        rows = store.get_screen_snapshots()
        assert rows[0]["thesis_strength"] == pytest.approx(0.80)
        store.close()

    def test_write_zero_thesis_strength(self, tmp_path):
        store = _make_store(tmp_path)
        row = _make_screen_row(thesis_strength=0.0)
        store.write_screen_snapshots([row])
        rows = store.get_screen_snapshots()
        assert rows[0]["thesis_strength"] == pytest.approx(0.0)
        store.close()

    def test_multiple_tickers_different_thesis(self, tmp_path):
        store = _make_store(tmp_path)
        rows = [
            _make_screen_row("VKTX", thesis_strength=0.90),
            _make_screen_row("ALNY", thesis_strength=0.50),
            _make_screen_row("MDGL", thesis_strength=None),
        ]
        store.write_screen_snapshots(rows)
        result = store.get_screen_snapshots()
        by_ticker = {r["ticker"]: r["thesis_strength"] for r in result}
        assert by_ticker["VKTX"] == pytest.approx(0.90)
        assert by_ticker["ALNY"] == pytest.approx(0.50)
        assert by_ticker["MDGL"] is None
        store.close()

    def test_upsert_updates_thesis_strength(self, tmp_path):
        store = _make_store(tmp_path)
        row_v1 = _make_screen_row(thesis_strength=0.60)
        store.write_screen_snapshots([row_v1])

        # Write again with updated thesis_strength — UPSERT should overwrite
        row_v2 = _make_screen_row(thesis_strength=0.80)
        store.write_screen_snapshots([row_v2])

        rows = store.get_screen_snapshots()
        assert rows[0]["thesis_strength"] == pytest.approx(0.80)
        store.close()


# ===========================================================================
# 4. bve-claim-resolve: list command
# ===========================================================================

class TestClaimResolveList:
    def test_list_empty(self, tmp_path, capsys):
        store = _make_store(tmp_path)
        store.close()
        from bve.cli.claim_resolve import cmd_list
        args = MagicMock()
        args.db = tmp_path / "test.db"
        args.asset = None
        args.all = False
        cmd_list(args)
        out = capsys.readouterr().out
        assert "No open claims" in out

    def test_list_shows_open_claim(self, tmp_path, capsys):
        store = _make_store(tmp_path)
        _make_claim(store)
        store.close()
        from bve.cli.claim_resolve import cmd_list
        args = MagicMock()
        args.db = tmp_path / "test.db"
        args.asset = None
        args.all = False
        cmd_list(args)
        out = capsys.readouterr().out
        assert "OPEN" in out
        assert "a-vktx" in out

    def test_list_asset_filter(self, tmp_path, capsys):
        store = _make_store(tmp_path)
        _make_claim(store, asset_id="a-vktx")
        _make_claim(store, asset_id="a-alny")
        store.close()
        from bve.cli.claim_resolve import cmd_list
        args = MagicMock()
        args.db = tmp_path / "test.db"
        args.asset = "a-alny"
        args.all = False
        cmd_list(args)
        out = capsys.readouterr().out
        assert "a-alny" in out
        assert "a-vktx" not in out

    def test_list_all_shows_resolved(self, tmp_path, capsys):
        store = _make_store(tmp_path)
        claim = _make_claim(store)
        tt = _make_tracker(store)
        tt.resolve_claim(claim.claim_id, "confirmed", evidence="met endpoint")
        store.close()
        from bve.cli.claim_resolve import cmd_list
        args = MagicMock()
        args.db = tmp_path / "test.db"
        args.asset = None
        args.all = True
        cmd_list(args)
        out = capsys.readouterr().out
        assert "CONFIRMED" in out


# ===========================================================================
# 5. bve-claim-resolve: resolve command
# ===========================================================================

class TestClaimResolveResolve:
    def test_resolve_confirmed(self, tmp_path, capsys):
        store = _make_store(tmp_path)
        claim = _make_claim(store)
        store.close()
        from bve.cli.claim_resolve import cmd_resolve
        args = MagicMock()
        args.db = tmp_path / "test.db"
        args.claim_id = claim.claim_id
        args.status = "confirmed"
        args.evidence = "Phase 2 readout positive"
        cmd_resolve(args)
        out = capsys.readouterr().out
        assert "confirmed" in out.lower()

        # Verify in DB
        store2 = _make_store(tmp_path)
        tt = _make_tracker(store2)
        updated = tt.get_claim(claim.claim_id)
        assert updated.status == "confirmed"
        assert updated.resolution_evidence == "Phase 2 readout positive"
        store2.close()

    def test_resolve_refuted(self, tmp_path, capsys):
        store = _make_store(tmp_path)
        claim = _make_claim(store)
        store.close()
        from bve.cli.claim_resolve import cmd_resolve
        args = MagicMock()
        args.db = tmp_path / "test.db"
        args.claim_id = claim.claim_id
        args.status = "refuted"
        args.evidence = "Trial missed primary endpoint"
        cmd_resolve(args)
        store2 = _make_store(tmp_path)
        tt = _make_tracker(store2)
        updated = tt.get_claim(claim.claim_id)
        assert updated.status == "refuted"
        store2.close()

    def test_resolve_already_resolved_exits(self, tmp_path, capsys):
        store = _make_store(tmp_path)
        claim = _make_claim(store)
        tt = _make_tracker(store)
        tt.resolve_claim(claim.claim_id, "confirmed", evidence="already done")
        store.close()
        from bve.cli.claim_resolve import cmd_resolve
        args = MagicMock()
        args.db = tmp_path / "test.db"
        args.claim_id = claim.claim_id
        args.status = "refuted"
        args.evidence = "attempt to re-resolve"
        with pytest.raises(SystemExit):
            cmd_resolve(args)

    def test_resolve_nonexistent_claim_exits(self, tmp_path):
        store = _make_store(tmp_path)
        store.close()
        from bve.cli.claim_resolve import cmd_resolve
        args = MagicMock()
        args.db = tmp_path / "test.db"
        args.claim_id = "00000000-0000-0000-0000-000000000000"
        args.status = "confirmed"
        args.evidence = "test"
        with pytest.raises(SystemExit):
            cmd_resolve(args)


# ===========================================================================
# 6. bve-claim-resolve: expire-overdue command
# ===========================================================================

class TestClaimResolveExpireOverdue:
    def test_expire_overdue_no_overdue(self, tmp_path, capsys):
        store = _make_store(tmp_path)
        store.close()
        from bve.cli.claim_resolve import cmd_expire_overdue
        args = MagicMock()
        args.db = tmp_path / "test.db"
        args.as_of = None
        cmd_expire_overdue(args)
        out = capsys.readouterr().out
        assert "No overdue" in out

    def test_expire_overdue_expires_past_claim(self, tmp_path, capsys):
        from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
        store = _make_store(tmp_path)
        tt = ThesisTracker(store)
        tt.add_claim(
            asset_id="a-vktx",
            company_id="c-vktx",
            claim_type=ClaimType.ENDPOINT_MET,
            assertion="Past due claim",
            resolution_date=date(2020, 1, 1),  # well in the past
        )
        store.close()
        from bve.cli.claim_resolve import cmd_expire_overdue
        args = MagicMock()
        args.db = tmp_path / "test.db"
        args.as_of = None  # today → 2020-01-01 is overdue
        cmd_expire_overdue(args)
        out = capsys.readouterr().out
        assert "Expired 1" in out

        # Verify in DB
        store2 = _make_store(tmp_path)
        tt2 = ThesisTracker(store2)
        snap = tt2.snapshot("a-vktx")
        assert snap.n_expired == 1
        store2.close()

    def test_expire_overdue_as_of_future(self, tmp_path, capsys):
        """as_of in far future expires claim due 2026-06-01."""
        from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
        store = _make_store(tmp_path)
        tt = ThesisTracker(store)
        tt.add_claim(
            asset_id="a-alny",
            company_id="c-alny",
            claim_type=ClaimType.ENDPOINT_MET,
            assertion="Zilebesiran meets endpoint",
            resolution_date=date(2026, 6, 1),
        )
        store.close()
        from bve.cli.claim_resolve import cmd_expire_overdue
        args = MagicMock()
        args.db = tmp_path / "test.db"
        args.as_of = "2027-01-01"  # after resolution_date
        cmd_expire_overdue(args)
        out = capsys.readouterr().out
        assert "Expired 1" in out


# ===========================================================================
# 7. Thesis strength updates composite snapshot
# ===========================================================================

class TestThesisStrengthInSnapshot:
    def test_thesis_strength_none_when_no_resolved_claims(self, tmp_path):
        store = _make_store(tmp_path)
        _make_claim(store)  # open claim only
        tt = _make_tracker(store)
        snap = tt.snapshot("a-vktx")
        assert snap.thesis_strength is None
        store.close()

    def test_thesis_strength_computed_after_confirmation(self, tmp_path):
        store = _make_store(tmp_path)
        claim = _make_claim(store)
        tt = _make_tracker(store)
        tt.resolve_claim(claim.claim_id, "confirmed", evidence="positive")
        snap = tt.snapshot("a-vktx")
        assert snap.thesis_strength == pytest.approx(1.0)
        store.close()

    def test_thesis_strength_partial_resolution(self, tmp_path):
        store = _make_store(tmp_path)
        from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
        tt = ThesisTracker(store)
        c1 = tt.add_claim("a-vktx", "c-vktx", ClaimType.ENDPOINT_MET, "claim 1")
        c2 = tt.add_claim("a-vktx", "c-vktx", ClaimType.ENDPOINT_MET, "claim 2")
        tt.resolve_claim(c1.claim_id, "confirmed", evidence="yes")
        tt.resolve_claim(c2.claim_id, "refuted", evidence="no")
        snap = tt.snapshot("a-vktx")
        # 1 confirmed / 2 resolved = 0.5
        assert snap.thesis_strength == pytest.approx(0.5)
        store.close()

    def test_screen_snapshot_thesis_strength_roundtrip_with_resolved_claim(self, tmp_path):
        store = _make_store(tmp_path)
        claim = _make_claim(store)
        tt = _make_tracker(store)
        tt.resolve_claim(claim.claim_id, "confirmed", evidence="met")
        snap = tt.snapshot("a-vktx")

        row = _make_screen_row("VKTX", thesis_strength=snap.thesis_strength)
        store.write_screen_snapshots([row])
        result = store.get_screen_snapshots()
        assert result[0]["thesis_strength"] == pytest.approx(1.0)
        store.close()
