"""Tests for the claim-atom reviewer packet + promotion gates.

Pins the review contract:
  * only approved (extraction + provenance) atoms can produce a predicted_posterior;
  * rejected atoms are ignored;
  * a missing likelihood ratio blocks materiality;
  * no approved source => no calibration row;
  * the reviewer packet includes every draft atom (nothing dropped);
  * nothing here touches live POS.
"""
from __future__ import annotations

import csv
from pathlib import Path

from bve.analysis.claim_calibration_corpus import ClaimCalibrationRecord, load_corpus
from bve.analysis.claim_evidence_atoms import (
    EXTRACTION_APPROVED,
    EXTRACTION_EXTRACTED,
    ExtractedAtom,
    build_atoms_for_corpus,
    extract_atoms_from_row,
)
from bve.analysis.claim_review_packet import (
    PACKET_COLUMNS,
    build_review_packet,
    is_calibration_eligible,
    packet_status,
    predicted_posterior_from_atoms,
    render_program_markdown,
    write_review_packet,
    writeback_predictions,
)
from bve.intelligence.claim_ledger import (
    ClaimType,
    EvidenceTier,
    ObservationBasis,
    ReviewStatus,
)

REPO = Path(__file__).resolve().parents[1]
LIVE_CORPUS = REPO / "research" / "data" / "claim_calibration_corpus.csv"


def _atom(**kw) -> ExtractedAtom:
    base = dict(
        atom_id="d:ther:0",
        program_id="d",
        claim_type=ClaimType.THERAPEUTIC_WINDOW.value,
        evidence_span="dose-limiting toxicity below efficacious exposure",
        proposed_direction="refuting",
        likelihood_ratio="0.2",
        tier=EvidenceTier.HIGH.value,
        source_type="fda_review",
        source_id="d:fda",
        observed_vs_inferred=ObservationBasis.OBSERVED.value,
        population_match="match",
        rationale="tox ceiling",
        extraction_review_status=EXTRACTION_APPROVED,
        review_status=ReviewStatus.APPROVED.value,
        extraction_source="test",
        extraction_date="2026-07-05",
    )
    base.update(kw)
    return ExtractedAtom(**base)


def _record(**kw) -> ClaimCalibrationRecord:
    base = dict(
        program_id="d",
        target="",
        indication="MPN",
        modality="small_molecule",
        phase="phase_3",
        decision_date="2021-01-01",
        claim_type=ClaimType.THERAPEUTIC_WINDOW.value,
        claim_question="Is an efficacious dose achievable below the toxicity ceiling?",
        evidence_available="Dose-limiting thrombocytopenia at efficacious exposure.",
        predicted_posterior=None,
        claim_held="false",
        program_outcome="failed",
        failure_success_reason="tox",
        source_links="wikipedia",
        review_status="draft",
        label_source="test",
        label_date="2026-07-05",
    )
    base.update(kw)
    return ClaimCalibrationRecord(**base)


# --- eligibility gate ----------------------------------------------------------


def test_fully_approved_atom_is_eligible():
    assert is_calibration_eligible(_atom()) is True


def test_only_approved_extraction_is_eligible():
    # provenance approved but extraction only "extracted" => ineligible
    assert is_calibration_eligible(_atom(extraction_review_status=EXTRACTION_EXTRACTED)) is False


def test_rejected_atoms_ignored():
    assert is_calibration_eligible(_atom(review_status="rejected")) is False


def test_missing_lr_blocks_materiality():
    assert is_calibration_eligible(_atom(likelihood_ratio="")) is False
    assert is_calibration_eligible(_atom(likelihood_ratio="n/a")) is False
    assert is_calibration_eligible(_atom(likelihood_ratio="0")) is False


def test_no_approved_source_no_calibration_row():
    assert is_calibration_eligible(_atom(source_type="")) is False


def test_low_tier_is_not_material():
    assert is_calibration_eligible(_atom(tier=EvidenceTier.LOW.value)) is False


# --- prediction gate -----------------------------------------------------------


def test_only_approved_atoms_produce_predicted_posterior():
    draft = extract_atoms_from_row(
        {
            "program_id": "d",
            "claim_type": ClaimType.THERAPEUTIC_WINDOW.value,
            "evidence_available": "Dose-limiting toxicity capped the efficacious dose.",
        }
    )
    assert predicted_posterior_from_atoms("d", ClaimType.THERAPEUTIC_WINDOW, draft) is None
    approved = [_atom()]
    pred = predicted_posterior_from_atoms("d", ClaimType.THERAPEUTIC_WINDOW, approved)
    assert pred is not None
    assert pred < 0.5  # refuting evidence pushed the window claim down


def test_rejected_and_unsourced_atoms_produce_no_row():
    atoms = [_atom(review_status="rejected"), _atom(source_type="")]
    assert predicted_posterior_from_atoms("d", ClaimType.THERAPEUTIC_WINDOW, atoms) is None


def test_prediction_scoped_to_program_and_family():
    atoms = [_atom(program_id="other")]
    assert predicted_posterior_from_atoms("d", ClaimType.THERAPEUTIC_WINDOW, atoms) is None


# --- writeback -----------------------------------------------------------------


def test_writeback_fills_only_predictable_rows():
    records = [_record(program_id="d"), _record(program_id="empty")]
    atoms = [_atom(program_id="d")]
    rows = writeback_predictions(records, atoms)
    by_id = {r["program_id"]: r for r in rows}
    assert by_id["d"]["predicted_posterior"] != ""
    assert by_id["empty"]["predicted_posterior"] == ""


# --- packet build --------------------------------------------------------------


def test_packet_includes_all_draft_atoms():
    records = load_corpus(LIVE_CORPUS)
    atoms = build_atoms_for_corpus(records)
    rows = build_review_packet(records, atoms)
    assert len(rows) == len(atoms)
    assert {r["atom_id"] for r in rows} == {a.atom_id for a in atoms}
    # Reviewer columns start blank; context columns are populated.
    for r in rows:
        assert r["review_status"] == ""
        assert r["likelihood_ratio"] == ""
        assert r["needed_primary_sources"]  # guidance present


def test_packet_joins_corpus_context():
    records = [_record(program_id="d", claim_question="Q?", source_links="wikipedia")]
    atoms = extract_atoms_from_row(
        {
            "program_id": "d",
            "claim_type": ClaimType.THERAPEUTIC_WINDOW.value,
            "evidence_available": "Dose-limiting toxicity.",
        }
    )
    rows = build_review_packet(records, atoms)
    assert rows[0]["claim_question"] == "Q?"
    assert rows[0]["current_source_links"] == "wikipedia"


def test_packet_round_trips_through_csv(tmp_path):
    records = [_record(program_id="d")]
    atoms = extract_atoms_from_row(
        {
            "program_id": "d",
            "claim_type": ClaimType.THERAPEUTIC_WINDOW.value,
            "evidence_available": "Dose-limiting toxicity; adequate exposure in responders.",
        }
    )
    out = write_review_packet(build_review_packet(records, atoms), tmp_path / "pkt.csv")
    with out.open(newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert header == list(PACKET_COLUMNS)


def test_markdown_omits_outcome_and_lists_atoms():
    records = [_record(program_id="d")]
    atoms = extract_atoms_from_row(
        {
            "program_id": "d",
            "claim_type": ClaimType.THERAPEUTIC_WINDOW.value,
            "evidence_available": "Dose-limiting toxicity capped dosing.",
        }
    )
    md = render_program_markdown("d", records, atoms)
    assert "# Review: d" in md
    # Outcome must not leak into the blind review sheet.
    assert "failed" not in md
    assert "claim_held" not in md
    assert "review_status = approved | rejected" in md


# --- status + live-POS guard ---------------------------------------------------


def test_status_reports_gate_closed_for_fresh_extraction():
    records = load_corpus(LIVE_CORPUS)
    atoms = build_atoms_for_corpus(records)
    s = packet_status(records, atoms)
    assert s.n_eligible == 0
    assert s.n_programs_predictable == 0
    assert s.affects_live_pos is False
    assert s.n_atoms == len(atoms)


def test_module_has_no_live_pos_path():
    import bve.analysis.claim_review_packet as mod

    text = Path(mod.__file__).read_text(encoding="utf-8")
    assert "compute_science_modifier" not in text
