"""
Tests for SeedRecordLoader (Phase 5D) and related Phase 5 evidence infrastructure.

Covers:
  - SeedRecordLoader.load() against the real seed_records.yaml
  - EvidenceRecord Phase 5 optional fields round-trip
  - LedgerValidator S3/S4/S5 rules
  - check_pair_evidence_coverage() via an in-memory ledger
"""
from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

import pytest
import yaml

from bve.ingestion.evidence_ledger import (
    EvidenceLedger,
    EvidenceRecord,
    SeedRecordLoader,
    VALID_ENTITY_TYPES,
    VALID_SIGNAL_TYPES,
)
from bve.ingestion.ledger_validator import (
    LedgerValidator,
    PairEvidenceReport,
    check_pair_evidence_coverage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEED_PATH = Path("research/evidence/seed_records.yaml")


def _make_minimal_record(**overrides) -> EvidenceRecord:
    defaults = dict(
        ticker="RVMD",
        event_date="2025-06-01",
        event_type="manual",
        direction="positive",
        phase_detected=None,
        source_type="press_release",
        source_url="https://example.com",
        raw_text="Example summary",
        confidence=0.80,
        match_reasons=["seed_record"],
        score_deltas={},
        published_date="2025-06-01",
        event_hash="abc123def456ab12",
    )
    defaults.update(overrides)
    return EvidenceRecord(**defaults)


# ---------------------------------------------------------------------------
# SeedRecordLoader — unit tests
# ---------------------------------------------------------------------------


def test_seed_records_yaml_exists():
    assert _SEED_PATH.exists(), "research/evidence/seed_records.yaml must exist"


def test_seed_record_loader_returns_list():
    records = SeedRecordLoader.load(_SEED_PATH)
    assert isinstance(records, list)
    assert len(records) >= 10  # we have 26+ records


def test_seed_records_all_have_required_fields():
    records = SeedRecordLoader.load(_SEED_PATH)
    for rec in records:
        assert rec.ticker, f"ticker missing on {rec}"
        assert rec.event_date, f"event_date missing on {rec}"
        assert rec.event_hash, f"event_hash missing on {rec}"
        assert rec.event_type == "manual"
        assert rec.score_deltas == {}


def test_seed_records_entity_types_valid():
    records = SeedRecordLoader.load(_SEED_PATH)
    for rec in records:
        if rec.entity_type is not None:
            assert rec.entity_type in VALID_ENTITY_TYPES, (
                f"{rec.ticker}: entity_type '{rec.entity_type}' not in VALID_ENTITY_TYPES"
            )


def test_seed_records_signal_types_valid():
    records = SeedRecordLoader.load(_SEED_PATH)
    for rec in records:
        if rec.signal_type is not None:
            assert rec.signal_type in VALID_SIGNAL_TYPES, (
                f"{rec.ticker}: signal_type '{rec.signal_type}' not in VALID_SIGNAL_TYPES"
            )


def test_seed_records_pair_records_have_pair_entity():
    records = SeedRecordLoader.load(_SEED_PATH)
    pair_records = [r for r in records if r.entity_type == "pair"]
    assert len(pair_records) >= 1, "Expected at least one pair record in seed_records.yaml"
    for rec in pair_records:
        assert rec.pair_entity, (
            f"pair record for {rec.ticker} is missing pair_entity"
        )


def test_seed_records_acquirer_records_present():
    records = SeedRecordLoader.load(_SEED_PATH)
    vrtx = [r for r in records if r.ticker == "VRTX" and r.entity_type == "acquirer"]
    regn = [r for r in records if r.ticker == "REGN" and r.entity_type == "acquirer"]
    assert len(vrtx) >= 2, "Need ≥2 VRTX acquirer records"
    assert len(regn) >= 2, "Need ≥2 REGN acquirer records"


def test_seed_records_confidence_converted_from_string():
    records = SeedRecordLoader.load(_SEED_PATH)
    for rec in records:
        assert 0.0 <= rec.confidence <= 1.0, (
            f"{rec.ticker}: confidence {rec.confidence} out of range"
        )


def test_seed_records_strength_in_range():
    records = SeedRecordLoader.load(_SEED_PATH)
    for rec in records:
        if rec.strength is not None:
            assert 0.0 <= rec.strength <= 1.0, (
                f"{rec.ticker}: strength {rec.strength} out of range"
            )


def test_seed_record_loader_deduplicates_on_append(tmp_path):
    """append_if_not_duplicate must skip identical hashes."""
    ledger = EvidenceLedger(path=tmp_path / "ledger.jsonl")
    records = SeedRecordLoader.load(_SEED_PATH)
    appended_first = sum(1 for r in records if ledger.append_if_not_duplicate(r))
    appended_second = sum(1 for r in records if ledger.append_if_not_duplicate(r))
    assert appended_first == len(records)
    assert appended_second == 0


# ---------------------------------------------------------------------------
# EvidenceRecord Phase 5 fields — round-trip serialisation
# ---------------------------------------------------------------------------


def test_evidence_record_phase5_fields_serialise():
    rec = _make_minimal_record(
        entity_type="target",
        signal_type="target_positive_trial_data",
        strength=0.75,
        summary="Phase 3 met primary endpoint.",
        pair_entity=None,
    )
    jsonl = rec.to_jsonl()
    loaded = EvidenceRecord.from_jsonl(jsonl)
    assert loaded.entity_type == "target"
    assert loaded.signal_type == "target_positive_trial_data"
    assert loaded.strength == pytest.approx(0.75)
    assert loaded.summary == "Phase 3 met primary endpoint."
    assert loaded.pair_entity is None


def test_evidence_record_pair_fields_serialise():
    rec = _make_minimal_record(
        ticker="VRTX",
        entity_type="pair",
        signal_type="pair_specific_synergy",
        strength=0.80,
        summary="VRTX renal franchise strongly complements TVTX povetacicept.",
        pair_entity="TVTX",
    )
    loaded = EvidenceRecord.from_jsonl(rec.to_jsonl())
    assert loaded.entity_type == "pair"
    assert loaded.pair_entity == "TVTX"


def test_evidence_record_phase5_fields_default_to_none():
    rec = _make_minimal_record()
    assert rec.entity_type is None
    assert rec.signal_type is None
    assert rec.strength is None
    assert rec.summary is None
    assert rec.pair_entity is None


# ---------------------------------------------------------------------------
# LedgerValidator S3/S4/S5 rules
# ---------------------------------------------------------------------------


def _write_jsonl(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "ledger.jsonl"
    with p.open("w") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    return p


def _base_record(**overrides) -> dict:
    base = {
        "ticker": "RVMD",
        "event_date": "2025-06-01",
        "event_type": "manual",
        "direction": "positive",
        "phase_detected": None,
        "source_type": "press_release",
        "source_url": "https://example.com",
        "raw_text": "Example",
        "confidence": 0.8,
        "match_reasons": [],
        "score_deltas": {},
        "event_hash": "abc123def456ab12",
        "ledger_version": "1",
    }
    base.update(overrides)
    return base


def test_validator_s3_warns_unknown_signal_type(tmp_path):
    path = _write_jsonl(tmp_path, [_base_record(signal_type="bogus_signal")])
    result = LedgerValidator(path).validate()
    assert result.is_valid  # S3 is a warning, not an error
    assert any("S3" in w for w in result.warnings)


def test_validator_s3_accepts_known_signal_types(tmp_path):
    for st in ["target_positive_trial_data", "acquirer_bd_appetite", "pair_specific_synergy"]:
        path = _write_jsonl(tmp_path, [_base_record(signal_type=st)])
        result = LedgerValidator(path).validate()
        s3_warns = [w for w in result.warnings if "S3" in w]
        assert len(s3_warns) == 0, f"Unexpected S3 warning for valid signal_type={st}"


def test_validator_s4_errors_unknown_entity_type(tmp_path):
    path = _write_jsonl(tmp_path, [_base_record(entity_type="unknown_side")])
    result = LedgerValidator(path).validate()
    assert not result.is_valid
    assert any("S4" in e for e in result.errors)


def test_validator_s4_accepts_known_entity_types(tmp_path):
    for et in ["target", "acquirer", "pair"]:
        path = _write_jsonl(
            tmp_path,
            [_base_record(entity_type=et, pair_entity="TVTX" if et == "pair" else None)],
        )
        result = LedgerValidator(path).validate()
        s4_errs = [e for e in result.errors if "S4" in e]
        assert len(s4_errs) == 0, f"Unexpected S4 error for entity_type={et}"


def test_validator_s5_errors_pair_without_pair_entity(tmp_path):
    path = _write_jsonl(tmp_path, [_base_record(entity_type="pair")])  # missing pair_entity
    result = LedgerValidator(path).validate()
    assert not result.is_valid
    assert any("S5" in e for e in result.errors)


def test_validator_s5_no_error_when_pair_entity_present(tmp_path):
    path = _write_jsonl(tmp_path, [_base_record(entity_type="pair", pair_entity="TVTX")])
    result = LedgerValidator(path).validate()
    s5_errs = [e for e in result.errors if "S5" in e]
    assert len(s5_errs) == 0


# ---------------------------------------------------------------------------
# check_pair_evidence_coverage — Phase 5C
# ---------------------------------------------------------------------------


def _seed_ledger(tmp_path: Path, records: list[EvidenceRecord]) -> EvidenceLedger:
    ledger = EvidenceLedger(path=tmp_path / "ledger.jsonl")
    for rec in records:
        ledger.append(rec)
    return ledger


def test_pair_coverage_defensible(tmp_path):
    recs = [
        # 2 acquirer records for VRTX
        _make_minimal_record(ticker="VRTX", event_hash="h1", entity_type="acquirer"),
        _make_minimal_record(ticker="VRTX", event_hash="h2", entity_type="acquirer"),
        # 3 target records for TVTX
        _make_minimal_record(ticker="TVTX", event_hash="h3", entity_type="target"),
        _make_minimal_record(ticker="TVTX", event_hash="h4", entity_type="target"),
        _make_minimal_record(ticker="TVTX", event_hash="h5", entity_type="target"),
        # 1 pair record
        _make_minimal_record(
            ticker="VRTX", event_hash="h6",
            entity_type="pair", pair_entity="TVTX",
        ),
    ]
    ledger = _seed_ledger(tmp_path, recs)
    report = check_pair_evidence_coverage(ledger, "VRTX", "TVTX")
    assert report.is_defensible
    assert report.gap_summary == "all thresholds met"
    assert report.acquirer_count >= 2
    assert report.target_count >= 3
    assert report.pair_count >= 1


def test_pair_coverage_not_defensible_missing_pair(tmp_path):
    recs = [
        _make_minimal_record(ticker="VRTX", event_hash="h1", entity_type="acquirer"),
        _make_minimal_record(ticker="VRTX", event_hash="h2", entity_type="acquirer"),
        _make_minimal_record(ticker="TVTX", event_hash="h3", entity_type="target"),
        _make_minimal_record(ticker="TVTX", event_hash="h4", entity_type="target"),
        _make_minimal_record(ticker="TVTX", event_hash="h5", entity_type="target"),
        # intentionally NO pair record
    ]
    ledger = _seed_ledger(tmp_path, recs)
    report = check_pair_evidence_coverage(ledger, "VRTX", "TVTX")
    assert not report.is_defensible
    assert "pair=" in report.gap_summary


def test_pair_coverage_not_defensible_missing_acquirer(tmp_path):
    # Only 1 acquirer record (need ≥2). No pair record so pair count also fails.
    # Note: get_records filters by ticker, so all VRTX-tickered records count toward
    # acquirer_count. We intentionally omit the pair record here to isolate the deficit.
    recs = [
        _make_minimal_record(ticker="VRTX", event_hash="h1", entity_type="acquirer"),
        _make_minimal_record(ticker="TVTX", event_hash="h3", entity_type="target"),
        _make_minimal_record(ticker="TVTX", event_hash="h4", entity_type="target"),
        _make_minimal_record(ticker="TVTX", event_hash="h5", entity_type="target"),
    ]
    ledger = _seed_ledger(tmp_path, recs)
    report = check_pair_evidence_coverage(ledger, "VRTX", "TVTX")
    assert not report.is_defensible
    assert "acquirer" in report.gap_summary


def test_pair_coverage_not_defensible_missing_target(tmp_path):
    recs = [
        _make_minimal_record(ticker="VRTX", event_hash="h1", entity_type="acquirer"),
        _make_minimal_record(ticker="VRTX", event_hash="h2", entity_type="acquirer"),
        # only 2 target records (need ≥3)
        _make_minimal_record(ticker="TVTX", event_hash="h3", entity_type="target"),
        _make_minimal_record(ticker="TVTX", event_hash="h4", entity_type="target"),
        _make_minimal_record(
            ticker="VRTX", event_hash="h6",
            entity_type="pair", pair_entity="TVTX",
        ),
    ]
    ledger = _seed_ledger(tmp_path, recs)
    report = check_pair_evidence_coverage(ledger, "VRTX", "TVTX")
    assert not report.is_defensible
    assert "target" in report.gap_summary


def test_pair_coverage_with_seed_records(tmp_path):
    """End-to-end: load seed_records.yaml and check a known defensible pair."""
    ledger = EvidenceLedger(path=tmp_path / "ledger.jsonl")
    for rec in SeedRecordLoader.load(_SEED_PATH):
        ledger.append_if_not_duplicate(rec)

    report = check_pair_evidence_coverage(ledger, "VRTX", "TVTX")
    # seed_records.yaml has ≥2 VRTX acquirer, ≥3 TVTX target, ≥1 VRTX-TVTX pair
    assert report.is_defensible, f"VRTX-TVTX not defensible: {report.gap_summary}"


def test_pair_coverage_report_fields():
    report = PairEvidenceReport(
        acquirer_ticker="VRTX",
        target_ticker="TVTX",
        acquirer_count=3,
        target_count=4,
        pair_count=1,
        is_defensible=True,
        gap_summary="all thresholds met",
    )
    assert report.acquirer_ticker == "VRTX"
    assert report.target_ticker == "TVTX"
    assert report.is_defensible is True
