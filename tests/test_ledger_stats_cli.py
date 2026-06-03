"""
Tests for bve-ledger-stats CLI (Block 2H).
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from bve.cli.ledger_stats_cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_ledger(path: Path, n: int = 5, ticker: str = "RVMD",
                 source_type: str = "sec_filing",
                 event_type: str = "clinical_positive_ph3") -> None:
    """Write n minimal EvidenceRecord JSONL lines to path."""
    import json
    from datetime import date as _date

    path.parent.mkdir(parents=True, exist_ok=True)
    today = _date.today().isoformat()
    with path.open("w", encoding="utf-8") as f:
        for i in range(n):
            rec = {
                "ticker": ticker,
                "event_date": today,
                "event_type": event_type,
                "direction": "positive",
                "phase_detected": "Phase 3",
                "source_type": source_type,
                "source_url": f"https://example.com/{i}",
                "raw_text": f"test event {i}",
                "confidence": 0.85,
                "match_reasons": ["test"],
                "score_deltas": {"asset_quality": 0.10},
                "created_at": "2026-06-01T00:00:00+00:00",
                "ledger_version": "1",
                "published_date": today,
                "event_hash": f"abc{i:013d}",
            }
            f.write(json.dumps(rec) + "\n")


# ---------------------------------------------------------------------------
# 1. Empty / missing ledger
# ---------------------------------------------------------------------------

class TestEmptyLedger:
    def test_missing_file_returns_0(self, tmp_path, capsys):
        rc = main(["--ledger", str(tmp_path / "nonexistent.jsonl")])
        assert rc == 0

    def test_empty_file_returns_0(self, tmp_path, capsys):
        p = tmp_path / "ledger.jsonl"
        p.write_text("")
        rc = main(["--ledger", str(p)])
        assert rc == 0

    def test_empty_prints_total_zero(self, tmp_path, capsys):
        p = tmp_path / "ledger.jsonl"
        p.write_text("")
        main(["--ledger", str(p)])
        out = capsys.readouterr().out
        assert "0" in out


# ---------------------------------------------------------------------------
# 2. Basic counts
# ---------------------------------------------------------------------------

class TestBasicCounts:
    def test_total_records_correct(self, tmp_path, capsys):
        p = tmp_path / "ledger.jsonl"
        _seed_ledger(p, n=7)
        main(["--ledger", str(p)])
        out = capsys.readouterr().out
        assert "7" in out

    def test_unique_tickers_reported(self, tmp_path, capsys):
        import json
        from datetime import date as _d

        p = tmp_path / "ledger.jsonl"
        today = _d.today().isoformat()
        with p.open("w") as f:
            for i, ticker in enumerate(["RVMD", "BEAM", "NTLA"]):
                rec = {
                    "ticker": ticker,
                    "event_date": today,
                    "event_type": "trial_start",
                    "direction": "positive",
                    "phase_detected": None,
                    "source_type": "clinicaltrials_gov",
                    "source_url": "https://x.com",
                    "raw_text": "test",
                    "confidence": 0.80,
                    "match_reasons": [],
                    "score_deltas": {},
                    "created_at": "2026-06-01T00:00:00+00:00",
                    "ledger_version": "1",
                    "published_date": today,
                    "event_hash": f"hash{i:013d}",
                }
                f.write(json.dumps(rec) + "\n")

        main(["--ledger", str(p)])
        out = capsys.readouterr().out
        assert "unique_tickers" in out
        assert "3" in out

    def test_returns_0_on_populated_ledger(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _seed_ledger(p, n=5)
        rc = main(["--ledger", str(p)])
        assert rc == 0


# ---------------------------------------------------------------------------
# 3. Lookback windows
# ---------------------------------------------------------------------------

class TestLookbackWindows:
    def test_records_last_7d_shown(self, tmp_path, capsys):
        p = tmp_path / "ledger.jsonl"
        _seed_ledger(p, n=3)
        main(["--ledger", str(p)])
        out = capsys.readouterr().out
        assert "records_last_7d" in out

    def test_records_last_30d_shown(self, tmp_path, capsys):
        p = tmp_path / "ledger.jsonl"
        _seed_ledger(p, n=3)
        main(["--ledger", str(p)])
        out = capsys.readouterr().out
        assert "records_last_30d" in out

    def test_old_records_excluded_from_7d(self, tmp_path, capsys):
        import json

        p = tmp_path / "ledger.jsonl"
        old_date = (date.today() - timedelta(days=60)).isoformat()
        rec = {
            "ticker": "RVMD",
            "event_date": old_date,
            "event_type": "trial_start",
            "direction": "positive",
            "phase_detected": None,
            "source_type": "sec_filing",
            "source_url": "",
            "raw_text": "old event",
            "confidence": 0.80,
            "match_reasons": [],
            "score_deltas": {"asset_quality": 0.05},
            "created_at": "2025-01-01T00:00:00+00:00",
            "ledger_version": "1",
            "published_date": old_date,
            "event_hash": "old0000000000000",
        }
        with p.open("w") as f:
            f.write(json.dumps(rec) + "\n")

        main(["--ledger", str(p), "--as-of", date.today().isoformat()])
        out = capsys.readouterr().out
        # records_last_7d should be 0
        lines = {ln.strip() for ln in out.splitlines()}
        seven_day_lines = [l for l in lines if "records_last_7d" in l]
        assert any("0" in l for l in seven_day_lines)


# ---------------------------------------------------------------------------
# 4. Source + event type breakdown
# ---------------------------------------------------------------------------

class TestBreakdowns:
    def test_sources_section_present(self, tmp_path, capsys):
        p = tmp_path / "ledger.jsonl"
        _seed_ledger(p, n=4, source_type="fda_website")
        main(["--ledger", str(p)])
        out = capsys.readouterr().out
        assert "Sources" in out
        assert "fda_website" in out

    def test_event_types_section_present(self, tmp_path, capsys):
        p = tmp_path / "ledger.jsonl"
        _seed_ledger(p, n=4, event_type="btd")
        main(["--ledger", str(p)])
        out = capsys.readouterr().out
        assert "Event types" in out
        assert "btd" in out

    def test_multiple_sources_all_listed(self, tmp_path, capsys):
        import json

        p = tmp_path / "ledger.jsonl"
        today = date.today().isoformat()
        with p.open("w") as f:
            for i, src in enumerate(["sec_filing", "clinicaltrials_gov", "fda_website"]):
                rec = {
                    "ticker": "RVMD",
                    "event_date": today,
                    "event_type": "trial_start",
                    "direction": "positive",
                    "phase_detected": None,
                    "source_type": src,
                    "source_url": "",
                    "raw_text": "test",
                    "confidence": 0.80,
                    "match_reasons": [],
                    "score_deltas": {},
                    "created_at": "2026-06-01T00:00:00+00:00",
                    "ledger_version": "1",
                    "published_date": today,
                    "event_hash": f"src{i:013d}",
                }
                f.write(json.dumps(rec) + "\n")

        main(["--ledger", str(p)])
        out = capsys.readouterr().out
        assert "sec_filing" in out
        assert "clinicaltrials_gov" in out
        assert "fda_website" in out


# ---------------------------------------------------------------------------
# 5. Integrity check
# ---------------------------------------------------------------------------

class TestIntegrity:
    def test_no_duplicates_reports_ok(self, tmp_path, capsys):
        p = tmp_path / "ledger.jsonl"
        _seed_ledger(p, n=5)
        main(["--ledger", str(p)])
        out = capsys.readouterr().out
        assert "Integrity" in out
        assert "ok" in out

    def test_duplicate_hashes_flagged(self, tmp_path, capsys):
        import json

        p = tmp_path / "ledger.jsonl"
        today = date.today().isoformat()
        rec = {
            "ticker": "RVMD",
            "event_date": today,
            "event_type": "trial_start",
            "direction": "positive",
            "phase_detected": None,
            "source_type": "sec_filing",
            "source_url": "",
            "raw_text": "dup event",
            "confidence": 0.80,
            "match_reasons": [],
            "score_deltas": {},
            "created_at": "2026-06-01T00:00:00+00:00",
            "ledger_version": "1",
            "published_date": today,
            "event_hash": "duphash0000001",  # same hash written twice
        }
        with p.open("w") as f:
            f.write(json.dumps(rec) + "\n")
            f.write(json.dumps(rec) + "\n")

        main(["--ledger", str(p)])
        out = capsys.readouterr().out
        assert "WARNING" in out or "1" in out

    def test_empty_deltas_counted(self, tmp_path, capsys):
        p = tmp_path / "ledger.jsonl"
        _seed_ledger(p, n=3)  # all have score_deltas
        main(["--ledger", str(p)])
        out = capsys.readouterr().out
        assert "records_with_empty_deltas" in out


# ---------------------------------------------------------------------------
# 6. Date + file metadata
# ---------------------------------------------------------------------------

class TestMetadata:
    def test_oldest_and_newest_shown(self, tmp_path, capsys):
        p = tmp_path / "ledger.jsonl"
        _seed_ledger(p, n=3)
        main(["--ledger", str(p)])
        out = capsys.readouterr().out
        assert "oldest_record" in out
        assert "newest_record" in out

    def test_file_size_shown(self, tmp_path, capsys):
        p = tmp_path / "ledger.jsonl"
        _seed_ledger(p, n=3)
        main(["--ledger", str(p)])
        out = capsys.readouterr().out
        assert "KB" in out

    def test_tickers_listed(self, tmp_path, capsys):
        p = tmp_path / "ledger.jsonl"
        _seed_ledger(p, n=3, ticker="BEAM")
        main(["--ledger", str(p)])
        out = capsys.readouterr().out
        assert "BEAM" in out

    def test_as_of_date_honoured(self, tmp_path, capsys):
        p = tmp_path / "ledger.jsonl"
        _seed_ledger(p, n=3)
        main(["--ledger", str(p), "--as-of", "2026-01-01"])
        out = capsys.readouterr().out
        assert "2026-01-01" in out
