"""Tests for the claim calibration corpus (Phase 8 infrastructure).

Pins the invariants: only approved rows calibrate, the calibration report is inert
until approved pairs exist, validation catches bad rows, and the seed worksheet is
always draft (never a label).
"""
from __future__ import annotations

import csv
from pathlib import Path

from bve.analysis.claim_calibration_corpus import (
    CORPUS_COLUMNS,
    REVIEW_APPROVED,
    REVIEW_DRAFT,
    ClaimCalibrationRecord,
    approved_records,
    build_seed_rows,
    calibration_report,
    load_corpus,
    propose_claim_type,
    validate_corpus,
    write_corpus,
)
from bve.intelligence.claim_ledger import ClaimType

REPO = Path(__file__).resolve().parents[1]
POOL = REPO / "research" / "data" / "phase_transitions.csv"
LIVE_CORPUS = REPO / "research" / "data" / "claim_calibration_corpus.csv"


def _record(**kw) -> ClaimCalibrationRecord:
    base = dict(
        program_id="drugX",
        target="BCL-XL",
        indication="MPN",
        modality="small_molecule",
        phase="phase_3",
        decision_date="2021-01-01",
        claim_type=ClaimType.THERAPEUTIC_WINDOW.value,
        claim_question="q",
        evidence_available="e",
        predicted_posterior=None,
        claim_held="unknown",
        program_outcome="failed",
        failure_success_reason="tox",
        source_links="",
        review_status=REVIEW_DRAFT,
        label_source="test",
        label_date="2026-07-04",
    )
    base.update(kw)
    return ClaimCalibrationRecord(**base)


# --- schema / seed generator ---------------------------------------------------


def test_seed_rows_are_all_draft_and_review_required():
    rows = build_seed_rows(POOL, outcomes=("failed",))
    assert rows, "expected some exposure/window failures in the pool"
    assert all(r["review_status"] == REVIEW_DRAFT for r in rows)
    assert all(r["source_links"] == "REVIEW REQUIRED" for r in rows)
    assert all(r["claim_type"] in {c.value for c in ClaimType} for r in rows)
    # Wedge only: exposure/window families.
    assert all(
        r["claim_type"]
        in {ClaimType.EXPOSURE_DELIVERY.value, ClaimType.THERAPEUTIC_WINDOW.value}
        for r in rows
    )


def test_seed_roundtrips_through_csv(tmp_path):
    rows = build_seed_rows(POOL, outcomes=("failed",))
    out = write_corpus(rows, tmp_path / "corpus.csv")
    with out.open(newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert header == list(CORPUS_COLUMNS)
    loaded = load_corpus(out)
    assert len(loaded) == len(rows)


def test_propose_claim_type_wedge_and_out_of_wedge():
    window = propose_claim_type({"notes": "thrombocytopenia limits dosing", "safety_profile": "concerning"})
    assert window.claim_type is ClaimType.THERAPEUTIC_WINDOW
    exposure = propose_claim_type({"notes": "poor CNS penetration, low exposure", "safety_profile": "manageable"})
    assert exposure.claim_type is ClaimType.EXPOSURE_DELIVERY
    none = propose_claim_type({"notes": "failed to beat standard of care", "safety_profile": "manageable"})
    assert none.claim_type is None


# --- loader / review gate ------------------------------------------------------


def test_only_approved_rows_are_calibration_eligible():
    records = [
        _record(review_status=REVIEW_DRAFT),
        _record(review_status="reviewed"),
        _record(review_status=REVIEW_APPROVED, source_links="pmid:123"),
    ]
    assert len(approved_records(records)) == 1


def test_missing_corpus_file_is_empty(tmp_path):
    assert load_corpus(tmp_path / "nope.csv") == []


# --- validation ----------------------------------------------------------------


def test_validation_flags_bad_rows():
    bad = [
        _record(program_id="", review_status="bogus"),
        _record(claim_type="not_a_claim"),
        _record(claim_held="maybe"),
        _record(predicted_posterior=1.5),
        _record(review_status=REVIEW_APPROVED, source_links=""),  # approved, no source
    ]
    problems = validate_corpus(bad)
    assert any("missing program_id" in p for p in problems)
    assert any("invalid review_status" in p for p in problems)
    assert any("unknown claim_type" in p for p in problems)
    assert any("invalid claim_held" in p for p in problems)
    assert any("out of [0,1]" in p for p in problems)
    assert any("no source_links" in p for p in problems)


def test_clean_corpus_validates():
    good = [_record(review_status=REVIEW_APPROVED, source_links="pmid:1", claim_held="false")]
    assert validate_corpus(good) == []


# --- calibration report: inert until approved pairs ----------------------------


def test_report_inert_without_approved_pairs():
    records = [_record(review_status=REVIEW_DRAFT, predicted_posterior=0.3, claim_held="false")]
    report = calibration_report(records)
    assert report.status == "uncalibrated"
    assert report.n_pairs == 0
    assert report.brier is None
    assert report.affects_live_pos is False


def test_report_diagnostic_with_approved_pairs():
    records = [
        _record(review_status=REVIEW_APPROVED, source_links="s", predicted_posterior=0.2, claim_held="false"),
        _record(review_status=REVIEW_APPROVED, source_links="s", predicted_posterior=0.8, claim_held="true"),
    ]
    report = calibration_report(records)
    assert report.status == "diagnostic"
    assert report.n_pairs == 2
    assert report.brier is not None
    assert report.base_rate == 0.5
    assert report.affects_live_pos is False


def test_report_predictor_callable_overrides_column():
    records = [
        _record(review_status=REVIEW_APPROVED, source_links="s", predicted_posterior=None, claim_held="true"),
    ]
    report = calibration_report(records, predictor=lambda r: 0.9)
    assert report.n_pairs == 1
    assert report.mean_prediction == 0.9


# --- shadow-only guarantee -----------------------------------------------------


def test_module_has_no_live_pos_path():
    import bve.analysis.claim_calibration_corpus as mod

    text = Path(mod.__file__).read_text(encoding="utf-8")
    assert "compute_science_modifier" not in text


# --- live seeded corpus is a valid draft worksheet -----------------------------


def test_live_corpus_is_valid_and_all_draft_or_reviewed():
    records = load_corpus(LIVE_CORPUS)
    assert records, "seeded corpus should exist"
    assert validate_corpus(records) == []
    # Nothing is approved yet => calibration stays inert (gate closed).
    assert approved_records(records) == []
    assert calibration_report(records).status == "uncalibrated"
