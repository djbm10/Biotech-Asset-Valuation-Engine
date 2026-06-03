"""
Tests for LedgerValidator (Block 2I).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from bve.ingestion.ledger_validator import LedgerValidator, LedgerValidationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TODAY = date.today().isoformat()
_YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
_FUTURE = (date.today() + timedelta(days=5)).isoformat()


def _good_rec(
    *,
    ticker: str = "RVMD",
    event_date: str = _YESTERDAY,
    event_type: str = "clinical_positive_ph3",
    direction: str = "positive",
    source_type: str = "sec_filing",
    source_url: str = "https://example.com",
    raw_text: str = "trial met primary endpoint",
    confidence: float = 0.85,
    score_deltas: dict | None = None,
    event_hash: str = "abc0000000000001",
    published_date: str | None = None,
    ledger_version: str = "1",
) -> dict:
    return {
        "ticker": ticker,
        "event_date": event_date,
        "event_type": event_type,
        "direction": direction,
        "phase_detected": "Phase 3",
        "source_type": source_type,
        "source_url": source_url,
        "raw_text": raw_text,
        "confidence": confidence,
        "match_reasons": ["test"],
        "score_deltas": score_deltas if score_deltas is not None else {"asset_quality": 0.10},
        "created_at": "2026-06-01T00:00:00+00:00",
        "ledger_version": ledger_version,
        "published_date": published_date or event_date,
        "event_hash": event_hash,
    }


def _write_ledger(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def _validate(path: Path, **kwargs) -> LedgerValidationResult:
    return LedgerValidator(path=path, **kwargs).validate()


# ---------------------------------------------------------------------------
# F1 — File-level
# ---------------------------------------------------------------------------

class TestFileLevelRules:
    def test_missing_file_returns_error(self, tmp_path):
        result = _validate(tmp_path / "nonexistent.jsonl")
        assert not result.is_valid
        assert any("F1" in e for e in result.errors)

    def test_empty_file_returns_warning_not_error(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        p.write_text("")
        result = _validate(p)
        assert result.is_valid
        assert any("F1" in w for w in result.warnings)

    def test_valid_file_passes(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec()])
        result = _validate(p)
        assert result.is_valid
        assert result.valid_records == 1

    def test_blank_lines_trigger_warning(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        with p.open("w") as f:
            f.write(json.dumps(_good_rec()) + "\n")
            f.write("\n")
            f.write(json.dumps(_good_rec(event_hash="abc0000000000002")) + "\n")
        result = _validate(p)
        assert any("F3" in w for w in result.warnings)

    def test_invalid_json_triggers_error(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        with p.open("w") as f:
            f.write("not json at all\n")
        result = _validate(p)
        assert not result.is_valid
        assert any("F2" in e for e in result.errors)


# ---------------------------------------------------------------------------
# R — Record-level
# ---------------------------------------------------------------------------

class TestRecordRules:
    def test_missing_required_field_ticker(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        rec = _good_rec()
        del rec["ticker"]
        _write_ledger(p, [rec])
        result = _validate(p)
        assert not result.is_valid
        assert any("R1" in e for e in result.errors)

    def test_missing_event_hash_is_error(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        rec = _good_rec()
        del rec["event_hash"]
        _write_ledger(p, [rec])
        result = _validate(p)
        assert not result.is_valid

    def test_empty_ticker_is_error(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec(ticker="")])
        result = _validate(p)
        assert not result.is_valid
        assert any("R2" in e for e in result.errors)

    def test_invalid_direction_is_error(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec(direction="bullish")])
        result = _validate(p)
        assert not result.is_valid
        assert any("R3" in e for e in result.errors)

    def test_valid_directions_all_pass(self, tmp_path):
        for idx, d in enumerate(["positive", "negative", "mixed", "neutral", "unknown"]):
            p = tmp_path / f"ledger_{d}.jsonl"
            _write_ledger(p, [_good_rec(direction=d, event_hash=f"hash{idx:013d}")])
            result = _validate(p)
            assert result.is_valid, f"direction '{d}' should be valid"

    def test_confidence_out_of_range_is_error(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec(confidence=1.5)])
        result = _validate(p)
        assert not result.is_valid
        assert any("R4" in e for e in result.errors)

    def test_confidence_zero_valid(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec(confidence=0.0)])
        result = _validate(p)
        assert result.is_valid

    def test_bad_event_date_format_is_error(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec(event_date="06/01/2026")])
        result = _validate(p)
        assert not result.is_valid
        assert any("R5" in e for e in result.errors)

    def test_bad_published_date_format_is_error(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        rec = _good_rec()
        rec["published_date"] = "not-a-date"
        _write_ledger(p, [rec])
        result = _validate(p)
        assert not result.is_valid
        assert any("R6" in e for e in result.errors)


# ---------------------------------------------------------------------------
# T — Temporal rules
# ---------------------------------------------------------------------------

class TestTemporalRules:
    def test_future_event_date_fails_with_as_of(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec(event_date=_FUTURE, published_date=_FUTURE)])
        result = _validate(p, as_of_date=_TODAY)
        assert not result.is_valid
        assert any("T1" in e for e in result.errors)

    def test_future_published_date_fails_with_as_of(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        rec = _good_rec()
        rec["published_date"] = _FUTURE
        _write_ledger(p, [rec])
        result = _validate(p, as_of_date=_TODAY)
        assert not result.is_valid
        assert any("T2" in e for e in result.errors)

    def test_past_dates_pass_with_as_of(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec(event_date=_YESTERDAY, published_date=_YESTERDAY)])
        result = _validate(p, as_of_date=_TODAY)
        assert result.is_valid

    def test_no_as_of_skips_temporal_checks(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec(event_date=_FUTURE, published_date=_FUTURE)])
        result = _validate(p, as_of_date=None)
        assert result.is_valid


# ---------------------------------------------------------------------------
# S — Score delta rules
# ---------------------------------------------------------------------------

class TestScoreDeltaRules:
    def test_delta_exceeds_cap_is_error(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        # asset_quality cap is 0.25; 0.30 exceeds it
        _write_ledger(p, [_good_rec(score_deltas={"asset_quality": 0.30})])
        result = _validate(p)
        assert not result.is_valid
        assert any("S2" in e for e in result.errors)

    def test_delta_at_cap_passes(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec(score_deltas={"asset_quality": 0.25})])
        result = _validate(p)
        assert result.is_valid

    def test_unknown_delta_key_is_warning(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec(score_deltas={"mystery_feature": 0.05})])
        result = _validate(p)
        assert result.is_valid  # only a warning, not an error
        assert any("S1" in w for w in result.warnings)

    def test_empty_deltas_dict_passes(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec(score_deltas={})])
        result = _validate(p)
        assert result.is_valid

    def test_negative_delta_within_cap_passes(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec(score_deltas={"seller_willingness": -0.20})])
        result = _validate(p)
        assert result.is_valid


# ---------------------------------------------------------------------------
# I — Integrity rules
# ---------------------------------------------------------------------------

class TestIntegrityRules:
    def test_empty_event_hash_is_error(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec(event_hash="")])
        result = _validate(p)
        assert not result.is_valid
        assert any("I1" in e for e in result.errors)

    def test_duplicate_hashes_flagged(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        rec = _good_rec()
        _write_ledger(p, [rec, rec])  # same hash twice
        result = _validate(p)
        assert not result.is_valid
        assert any("I2" in e for e in result.errors)

    def test_unique_hashes_pass(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [
            _good_rec(event_hash="hash000000000001"),
            _good_rec(event_hash="hash000000000002"),
        ])
        result = _validate(p)
        assert result.is_valid


# ---------------------------------------------------------------------------
# U — Universe rules
# ---------------------------------------------------------------------------

class TestUniverseRules:
    def test_unknown_ticker_is_warning(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec(ticker="UNKN")])
        result = _validate(p, known_tickers={"RVMD", "BEAM"})
        assert result.is_valid  # warning only
        assert any("U1" in w for w in result.warnings)

    def test_known_ticker_passes(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec(ticker="RVMD")])
        result = _validate(p, known_tickers={"RVMD", "BEAM"})
        assert result.is_valid
        assert not any("U1" in w for w in result.warnings)

    def test_no_known_tickers_skips_check(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [_good_rec(ticker="ANYTHING")])
        result = _validate(p, known_tickers=None)
        assert result.is_valid


# ---------------------------------------------------------------------------
# Multi-record / counts
# ---------------------------------------------------------------------------

class TestMultiRecord:
    def test_valid_records_count_correct(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [
            _good_rec(event_hash="h1"),
            _good_rec(event_hash="h2"),
            _good_rec(event_hash="h3"),
        ])
        result = _validate(p)
        assert result.valid_records == 3

    def test_mixed_valid_invalid_counts(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [
            _good_rec(event_hash="h1"),
            _good_rec(direction="WRONG", event_hash="h2"),  # error
            _good_rec(event_hash="h3"),
        ])
        result = _validate(p)
        assert not result.is_valid
        assert result.valid_records == 2  # two good records

    def test_total_lines_includes_all_lines(self, tmp_path):
        p = tmp_path / "ledger.jsonl"
        _write_ledger(p, [
            _good_rec(event_hash="h1"),
            _good_rec(event_hash="h2"),
        ])
        result = _validate(p)
        assert result.total_lines == 2
