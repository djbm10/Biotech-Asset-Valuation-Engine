"""
Tests for LedgerManifest (Block 2I).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from bve.ingestion.ledger_manifest import (
    LedgerManifest,
    generate_manifest,
    verify_manifest,
)

_TODAY = date.today().isoformat()


def _write_ledger(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def _make_rec(
    ticker: str = "RVMD",
    source_type: str = "sec_filing",
    event_date: str = _TODAY,
    event_hash: str = "abc0000000000001",
) -> dict:
    return {
        "ticker": ticker,
        "event_date": event_date,
        "event_type": "clinical_positive_ph3",
        "direction": "positive",
        "phase_detected": "Phase 3",
        "source_type": source_type,
        "source_url": "https://example.com",
        "raw_text": "test",
        "confidence": 0.85,
        "match_reasons": [],
        "score_deltas": {"asset_quality": 0.10},
        "created_at": "2026-06-01T00:00:00+00:00",
        "ledger_version": "1",
        "published_date": event_date,
        "event_hash": event_hash,
    }


# ---------------------------------------------------------------------------
# 1. Empty / missing
# ---------------------------------------------------------------------------

class TestEmptyLedger:
    def test_missing_ledger_returns_zero_records(self, tmp_path):
        m = generate_manifest(tmp_path / "nonexistent.jsonl", run_id="r1", as_of_date=_TODAY)
        assert m.total_records == 0

    def test_empty_ledger_returns_zero_records(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        p.write_text("")
        m = generate_manifest(p, run_id="r1", as_of_date=_TODAY)
        assert m.total_records == 0

    def test_empty_has_sha256(self, tmp_path):
        m = generate_manifest(tmp_path / "nonexistent.jsonl", run_id="r1", as_of_date=_TODAY)
        assert len(m.sha256) == 64  # hex SHA-256 is always 64 chars

    def test_empty_file_size_zero(self, tmp_path):
        m = generate_manifest(tmp_path / "nonexistent.jsonl", run_id="r1", as_of_date=_TODAY)
        assert m.file_size_bytes == 0


# ---------------------------------------------------------------------------
# 2. Record counts
# ---------------------------------------------------------------------------

class TestRecordCounts:
    def test_total_records_correct(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        recs = [_make_rec(event_hash=f"h{i:013d}") for i in range(7)]
        _write_ledger(p, recs)
        m = generate_manifest(p, run_id="r1", as_of_date=_TODAY)
        assert m.total_records == 7

    def test_records_by_source_correct(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        recs = [
            _make_rec(source_type="sec_filing", event_hash="h1"),
            _make_rec(source_type="sec_filing", event_hash="h2"),
            _make_rec(source_type="fda_website", event_hash="h3"),
        ]
        _write_ledger(p, recs)
        m = generate_manifest(p, run_id="r1", as_of_date=_TODAY)
        assert m.records_by_source["sec_filing"] == 2
        assert m.records_by_source["fda_website"] == 1

    def test_records_by_ticker_correct(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        recs = [
            _make_rec(ticker="RVMD", event_hash="h1"),
            _make_rec(ticker="RVMD", event_hash="h2"),
            _make_rec(ticker="BEAM", event_hash="h3"),
        ]
        _write_ledger(p, recs)
        m = generate_manifest(p, run_id="r1", as_of_date=_TODAY)
        assert m.records_by_ticker["RVMD"] == 2
        assert m.records_by_ticker["BEAM"] == 1


# ---------------------------------------------------------------------------
# 3. Date range
# ---------------------------------------------------------------------------

class TestDateRange:
    def test_oldest_and_newest_correct(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        recs = [
            _make_rec(event_date="2025-01-01", event_hash="h1"),
            _make_rec(event_date="2026-06-01", event_hash="h2"),
            _make_rec(event_date="2025-06-15", event_hash="h3"),
        ]
        _write_ledger(p, recs)
        m = generate_manifest(p, run_id="r1", as_of_date=_TODAY)
        assert m.oldest_record == "2025-01-01"
        assert m.newest_record == "2026-06-01"

    def test_single_record_oldest_equals_newest(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_make_rec(event_date="2026-05-01")])
        m = generate_manifest(p, run_id="r1", as_of_date=_TODAY)
        assert m.oldest_record == "2026-05-01"
        assert m.newest_record == "2026-05-01"

    def test_no_records_oldest_newest_none(self, tmp_path):
        m = generate_manifest(tmp_path / "none.jsonl", run_id="r1", as_of_date=_TODAY)
        assert m.oldest_record is None
        assert m.newest_record is None


# ---------------------------------------------------------------------------
# 4. Checksum
# ---------------------------------------------------------------------------

class TestChecksum:
    def test_sha256_matches_file(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_make_rec()])
        m = generate_manifest(p, run_id="r1", as_of_date=_TODAY)
        expected = hashlib.sha256(p.read_bytes()).hexdigest()
        assert m.sha256 == expected

    def test_different_files_different_sha256(self, tmp_path):
        p1 = tmp_path / "l1.jsonl"
        p2 = tmp_path / "l2.jsonl"
        _write_ledger(p1, [_make_rec(event_hash="h1")])
        _write_ledger(p2, [_make_rec(event_hash="h2")])
        m1 = generate_manifest(p1, run_id="r1", as_of_date=_TODAY)
        m2 = generate_manifest(p2, run_id="r2", as_of_date=_TODAY)
        assert m1.sha256 != m2.sha256


# ---------------------------------------------------------------------------
# 5. Save / load round-trip
# ---------------------------------------------------------------------------

class TestSaveLoad:
    def test_save_creates_file(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_make_rec()])
        m = generate_manifest(p, run_id="r1", as_of_date=_TODAY)
        out = tmp_path / "manifest.json"
        m.save(out)
        assert out.exists()

    def test_round_trip_preserves_sha256(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_make_rec()])
        m = generate_manifest(p, run_id="r1", as_of_date=_TODAY)
        out = tmp_path / "manifest.json"
        m.save(out)
        loaded = LedgerManifest.load(out)
        assert loaded.sha256 == m.sha256

    def test_round_trip_preserves_total_records(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_make_rec(event_hash=f"h{i}") for i in range(4)])
        m = generate_manifest(p, run_id="r1", as_of_date=_TODAY)
        out = tmp_path / "manifest.json"
        m.save(out)
        loaded = LedgerManifest.load(out)
        assert loaded.total_records == 4


# ---------------------------------------------------------------------------
# 6. Verify
# ---------------------------------------------------------------------------

class TestVerify:
    def test_verify_ok_when_file_unchanged(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_make_rec()])
        m = generate_manifest(p, run_id="r1", as_of_date=_TODAY)
        manifest_path = tmp_path / "manifest.json"
        m.save(manifest_path)
        ok, msg = verify_manifest(p, manifest_path)
        assert ok
        assert "ok" in msg.lower()

    def test_verify_fails_when_file_modified(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_make_rec()])
        m = generate_manifest(p, run_id="r1", as_of_date=_TODAY)
        manifest_path = tmp_path / "manifest.json"
        m.save(manifest_path)
        # Tamper with ledger
        with p.open("a") as f:
            f.write(json.dumps(_make_rec(event_hash="tampered")) + "\n")
        ok, msg = verify_manifest(p, manifest_path)
        assert not ok
        assert "MISMATCH" in msg

    def test_verify_run_id_preserved(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_make_rec()])
        m = generate_manifest(p, run_id="daily-2026-06-02", as_of_date=_TODAY)
        out = tmp_path / "manifest.json"
        m.save(out)
        loaded = LedgerManifest.load(out)
        assert loaded.run_id == "daily-2026-06-02"
