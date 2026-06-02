"""
Tests for review_apply.py (Block 2L).
"""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pytest

from bve.ingestion.review_apply import (
    apply_decisions_to_gate,
    build_pending_events_rows,
    load_review_decisions_yaml,
    write_pending_events_csv,
)
from bve.ingestion.review_gate import ReviewDecision, ReviewGate, ReviewStatus

_TODAY = date.today().isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_decisions_yaml(path: Path, items: list[dict]) -> None:
    import yaml  # type: ignore[import-untyped]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump({"decisions": items}), encoding="utf-8")


def _write_ledger(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def _make_rec(
    ticker: str = "RVMD",
    event_hash: str = "abc0000000000001",
    event_date: str = _TODAY,
    raw_text: str = "Phase 3 met primary endpoint",
) -> dict:
    return {
        "ticker": ticker,
        "event_date": event_date,
        "event_type": "clinical_positive_ph3",
        "direction": "positive",
        "phase_detected": "Phase 3",
        "source_type": "sec_filing",
        "source_url": "https://example.com",
        "raw_text": raw_text,
        "confidence": 0.85,
        "match_reasons": ["test"],
        "score_deltas": {"asset_quality": 0.10},
        "created_at": "2026-06-01T00:00:00+00:00",
        "ledger_version": "1",
        "published_date": event_date,
        "event_hash": event_hash,
    }


# ---------------------------------------------------------------------------
# 1. load_review_decisions_yaml
# ---------------------------------------------------------------------------

class TestLoadReviewDecisionsYaml:
    def test_missing_file_returns_empty(self, tmp_path):
        result = load_review_decisions_yaml(tmp_path / "nonexistent.yaml")
        assert result == []

    def test_loads_approved_decision(self, tmp_path):
        p = tmp_path / "decisions.yaml"
        _write_decisions_yaml(p, [{"event_hash": "abc001", "status": "approved"}])
        decisions = load_review_decisions_yaml(p)
        assert len(decisions) == 1
        assert decisions[0].status == ReviewStatus.APPROVED
        assert decisions[0].event_hash == "abc001"

    def test_loads_rejected_decision(self, tmp_path):
        p = tmp_path / "decisions.yaml"
        _write_decisions_yaml(p, [{"event_hash": "abc002", "status": "rejected"}])
        decisions = load_review_decisions_yaml(p)
        assert decisions[0].status == ReviewStatus.REJECTED

    def test_loads_downgraded_decision(self, tmp_path):
        p = tmp_path / "decisions.yaml"
        _write_decisions_yaml(p, [
            {"event_hash": "abc003", "status": "downgraded", "downgrade_factor": 0.5}
        ])
        decisions = load_review_decisions_yaml(p)
        assert decisions[0].status == ReviewStatus.DOWNGRADED
        assert decisions[0].downgrade_factor == 0.5

    def test_loads_reviewer_id_and_notes(self, tmp_path):
        p = tmp_path / "decisions.yaml"
        _write_decisions_yaml(p, [
            {"event_hash": "abc004", "status": "approved",
             "reviewer_id": "djmann", "notes": "Confirmed"}
        ])
        decisions = load_review_decisions_yaml(p)
        assert decisions[0].reviewer_id == "djmann"
        assert decisions[0].notes == "Confirmed"

    def test_loads_multiple_decisions(self, tmp_path):
        p = tmp_path / "decisions.yaml"
        _write_decisions_yaml(p, [
            {"event_hash": "h1", "status": "approved"},
            {"event_hash": "h2", "status": "rejected"},
            {"event_hash": "h3", "status": "downgraded", "downgrade_factor": 0.7},
        ])
        decisions = load_review_decisions_yaml(p)
        assert len(decisions) == 3

    def test_skips_missing_event_hash(self, tmp_path):
        p = tmp_path / "decisions.yaml"
        _write_decisions_yaml(p, [
            {"event_hash": "", "status": "approved"},
            {"event_hash": "valid001", "status": "approved"},
        ])
        decisions = load_review_decisions_yaml(p)
        assert len(decisions) == 1
        assert decisions[0].event_hash == "valid001"

    def test_skips_invalid_status(self, tmp_path):
        p = tmp_path / "decisions.yaml"
        _write_decisions_yaml(p, [
            {"event_hash": "h1", "status": "INVALID_STATUS"},
            {"event_hash": "h2", "status": "approved"},
        ])
        decisions = load_review_decisions_yaml(p)
        assert len(decisions) == 1

    def test_empty_file_returns_empty(self, tmp_path):
        p = tmp_path / "decisions.yaml"
        p.write_text("")
        decisions = load_review_decisions_yaml(p)
        assert decisions == []

    def test_no_decisions_key_returns_empty(self, tmp_path):
        import yaml  # type: ignore[import-untyped]

        p = tmp_path / "decisions.yaml"
        p.write_text(yaml.dump({"other_key": []}))
        decisions = load_review_decisions_yaml(p)
        assert decisions == []


# ---------------------------------------------------------------------------
# 2. apply_decisions_to_gate
# ---------------------------------------------------------------------------

class TestApplyDecisionsToGate:
    def test_applies_decisions_to_gate(self):
        gate = ReviewGate()
        decisions = [
            ReviewDecision(event_hash="h1", status=ReviewStatus.APPROVED),
            ReviewDecision(event_hash="h2", status=ReviewStatus.REJECTED),
        ]
        n = apply_decisions_to_gate(decisions, gate)
        assert n == 2
        assert gate.get_status("h1") == ReviewStatus.APPROVED
        assert gate.get_status("h2") == ReviewStatus.REJECTED

    def test_returns_count_of_applied(self):
        gate = ReviewGate()
        decisions = [ReviewDecision(event_hash=f"h{i}", status=ReviewStatus.APPROVED) for i in range(5)]
        n = apply_decisions_to_gate(decisions, gate)
        assert n == 5

    def test_empty_decisions_returns_zero(self):
        gate = ReviewGate()
        n = apply_decisions_to_gate([], gate)
        assert n == 0

    def test_pending_events_not_in_gate_stay_pending(self):
        gate = ReviewGate()
        apply_decisions_to_gate([
            ReviewDecision(event_hash="known", status=ReviewStatus.APPROVED)
        ], gate)
        assert gate.get_status("unknown_hash") == ReviewStatus.PENDING


# ---------------------------------------------------------------------------
# 3. build_pending_events_rows
# ---------------------------------------------------------------------------

class TestBuildPendingEventsRows:
    def test_pending_records_appear(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_make_rec()])
        from bve.ingestion.evidence_ledger import EvidenceLedger

        ledger = EvidenceLedger(path=p)
        gate = ReviewGate()
        rows = build_pending_events_rows(ledger, gate)
        assert len(rows) == 1
        assert rows[0]["event_hash"] == "abc0000000000001"

    def test_approved_records_excluded_from_pending(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_make_rec()])
        from bve.ingestion.evidence_ledger import EvidenceLedger

        ledger = EvidenceLedger(path=p)
        gate = ReviewGate()
        gate.record_decision(ReviewDecision(
            event_hash="abc0000000000001", status=ReviewStatus.APPROVED
        ))
        rows = build_pending_events_rows(ledger, gate, pending_only=True)
        assert len(rows) == 0

    def test_all_mode_includes_approved(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_make_rec()])
        from bve.ingestion.evidence_ledger import EvidenceLedger

        ledger = EvidenceLedger(path=p)
        gate = ReviewGate()
        gate.record_decision(ReviewDecision(
            event_hash="abc0000000000001", status=ReviewStatus.APPROVED
        ))
        rows = build_pending_events_rows(ledger, gate, pending_only=False)
        assert len(rows) == 1

    def test_as_of_filters_future_events(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        future_date = "2099-01-01"
        _write_ledger(p, [_make_rec(event_date=future_date)])
        from bve.ingestion.evidence_ledger import EvidenceLedger

        ledger = EvidenceLedger(path=p)
        gate = ReviewGate()
        rows = build_pending_events_rows(ledger, gate, as_of_date=_TODAY)
        assert len(rows) == 0

    def test_rows_sorted_by_ticker_then_date(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [
            _make_rec(ticker="RVMD", event_date="2026-01-01", event_hash="h1"),
            _make_rec(ticker="BEAM", event_date="2026-02-01", event_hash="h2"),
            _make_rec(ticker="RVMD", event_date="2026-03-01", event_hash="h3"),
        ])
        from bve.ingestion.evidence_ledger import EvidenceLedger

        ledger = EvidenceLedger(path=p)
        gate = ReviewGate()
        rows = build_pending_events_rows(ledger, gate)
        tickers = [r["ticker"] for r in rows]
        assert tickers == sorted(tickers)

    def test_raw_text_preview_truncated(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        long_text = "x" * 300
        _write_ledger(p, [_make_rec(raw_text=long_text)])
        from bve.ingestion.evidence_ledger import EvidenceLedger

        ledger = EvidenceLedger(path=p)
        gate = ReviewGate()
        rows = build_pending_events_rows(ledger, gate)
        assert len(rows[0]["raw_text_preview"]) <= 121  # 120 + ellipsis char
        assert rows[0]["raw_text_preview"].endswith("…")

    def test_row_has_required_fields(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_make_rec()])
        from bve.ingestion.evidence_ledger import EvidenceLedger

        ledger = EvidenceLedger(path=p)
        gate = ReviewGate()
        rows = build_pending_events_rows(ledger, gate)
        row = rows[0]
        for field in ["event_hash", "ticker", "event_date", "event_type",
                      "direction", "confidence", "source_type", "review_status"]:
            assert field in row


# ---------------------------------------------------------------------------
# 4. write_pending_events_csv
# ---------------------------------------------------------------------------

class TestWritePendingEventsCsv:
    def test_creates_csv_file(self, tmp_path):
        out = tmp_path / "pending.csv"
        write_pending_events_csv([], out)
        assert out.exists()

    def test_csv_has_header(self, tmp_path):
        out = tmp_path / "pending.csv"
        write_pending_events_csv([], out)
        content = out.read_text()
        assert "event_hash" in content
        assert "ticker" in content

    def test_csv_rows_match_input(self, tmp_path):
        out = tmp_path / "pending.csv"
        rows = [
            {
                "event_hash": "h1",
                "ticker": "RVMD",
                "event_date": _TODAY,
                "event_type": "clinical_positive_ph3",
                "direction": "positive",
                "confidence": "0.85",
                "source_type": "sec_filing",
                "source_url": "https://example.com",
                "raw_text_preview": "test event",
                "review_status": "pending",
            }
        ]
        write_pending_events_csv(rows, out)
        with out.open(newline="") as f:
            reader = csv.DictReader(f)
            written = list(reader)
        assert len(written) == 1
        assert written[0]["ticker"] == "RVMD"
        assert written[0]["event_hash"] == "h1"

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "nested" / "deep" / "pending.csv"
        write_pending_events_csv([], out)
        assert out.exists()
