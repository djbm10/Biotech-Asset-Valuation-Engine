"""Tests for the evidence-atom extraction scaffold.

Pins the four load-bearing invariants:
  * draft/extracted atoms are inert — they cannot move a claim posterior;
  * an unreviewed *extraction* cannot yield an ``approved`` (material) atom;
  * atoms preserve source / provenance through the round trip;
  * extraction reads evidence prose only — outcome fields are never used as evidence.
"""
from __future__ import annotations

import csv
from pathlib import Path

from bve.analysis.claim_calibration_corpus import ClaimCalibrationRecord, load_corpus
from bve.analysis.claim_evidence_atoms import (
    ATOM_COLUMNS,
    EXTRACTION_APPROVED,
    EXTRACTION_EXTRACTED,
    FORBIDDEN_EVIDENCE_FIELDS,
    ExtractedAtom,
    atom_from_row,
    build_atoms_for_corpus,
    build_science_claim,
    extract_atoms_from_row,
    load_atoms,
    summarize_atoms,
    to_claim_atom,
    validate_atoms,
    write_atoms,
)
from bve.intelligence.claim_ledger import (
    ClaimType,
    EvidenceTier,
    ObservationBasis,
    ReviewStatus,
    ScienceClaim,
    compute_claim_posterior,
)

REPO = Path(__file__).resolve().parents[1]
LIVE_CORPUS = REPO / "research" / "data" / "claim_calibration_corpus.csv"


def _corpus_row(**kw) -> dict[str, str]:
    base = {
        "program_id": "drugX",
        "claim_type": ClaimType.THERAPEUTIC_WINDOW.value,
        "evidence_available": (
            "Phase 2 showed dose-limiting thrombocytopenia at efficacious doses. "
            "Exposure was adequate in responders. Trial continued to registration."
        ),
        "claim_held": "false",
        "program_outcome": "failed",
        "failure_success_reason": "tox ceiling below efficacy",
    }
    base.update(kw)
    return base


# --- extraction basics ---------------------------------------------------------


def test_extraction_produces_conservative_draft_atoms():
    atoms = extract_atoms_from_row(_corpus_row())
    assert atoms, "expected candidate spans"
    for a in atoms:
        assert a.tier == EvidenceTier.LOW.value
        assert a.observed_vs_inferred == ObservationBasis.INFERRED.value
        assert a.review_status == ReviewStatus.DRAFT.value
        assert a.extraction_review_status == EXTRACTION_EXTRACTED
        assert a.likelihood_ratio == "1.0"
        assert a.program_id == "drugX"
        assert a.claim_type == ClaimType.THERAPEUTIC_WINDOW.value


def test_direction_hint_is_advisory_only():
    atoms = extract_atoms_from_row(_corpus_row())
    # A refuting-keyword span is hinted refuting, but LR stays a neutral placeholder.
    refuting = [a for a in atoms if a.proposed_direction == "refuting"]
    assert refuting, "expected a refuting hint on the thrombocytopenia span"
    assert all(a.likelihood_ratio == "1.0" for a in refuting)


# --- invariant 1: draft atoms cannot move POS ----------------------------------


def test_draft_atoms_are_inert_on_the_posterior():
    atoms = extract_atoms_from_row(_corpus_row())
    claim = build_science_claim(
        "drugX", ClaimType.THERAPEUTIC_WINDOW, atoms, prior=0.5
    )
    posterior = compute_claim_posterior(claim)
    # No material atoms => posterior stays at prior, openness stays fully open.
    assert posterior.posterior == 0.5
    assert posterior.n_material_atoms == 0
    assert posterior.openness == 1.0
    assert posterior.n_raised_questions == len(claim.atoms)


# --- invariant 2: unreviewed extraction cannot yield an approved atom -----------


def test_unreviewed_extraction_cannot_produce_material_atom():
    # A row that LIES: it claims HIGH tier / observed / approved provenance, but the
    # extraction itself is only "extracted". The safety rail must force it non-material.
    lying = ExtractedAtom(
        atom_id="d:ther:0",
        program_id="d",
        claim_type=ClaimType.THERAPEUTIC_WINDOW.value,
        evidence_span="dose-limiting toxicity capped efficacy",
        proposed_direction="refuting",
        likelihood_ratio="0.2",
        tier=EvidenceTier.HIGH.value,
        source_type="fda_review",
        source_id="d:fda",
        observed_vs_inferred=ObservationBasis.OBSERVED.value,
        population_match="match",
        rationale="tox ceiling",
        extraction_review_status=EXTRACTION_EXTRACTED,  # NOT approved
        review_status=ReviewStatus.APPROVED.value,      # claims approved
        extraction_source="test",
        extraction_date="2026-07-05",
    )
    claim_atom = to_claim_atom(lying)
    # review_status forced to DRAFT => gate returns zero weight.
    assert claim_atom.provenance.review_status is ReviewStatus.DRAFT
    assert claim_atom.provenance.materiality_weight() == 0.0
    assert not claim_atom.provenance.is_material()


def test_approved_extraction_and_provenance_becomes_material():
    approved = ExtractedAtom(
        atom_id="d:ther:0",
        program_id="d",
        claim_type=ClaimType.THERAPEUTIC_WINDOW.value,
        evidence_span="dose-limiting toxicity capped efficacy",
        proposed_direction="refuting",
        likelihood_ratio="0.2",
        tier=EvidenceTier.HIGH.value,
        source_type="fda_review",
        source_id="d:fda",
        observed_vs_inferred=ObservationBasis.OBSERVED.value,
        population_match="match",
        rationale="tox ceiling below efficacious exposure",
        extraction_review_status=EXTRACTION_APPROVED,  # extraction approved
        review_status=ReviewStatus.APPROVED.value,     # provenance approved
        extraction_source="test",
        extraction_date="2026-07-05",
    )
    claim_atom = to_claim_atom(approved)
    assert claim_atom.provenance.review_status is ReviewStatus.APPROVED
    assert claim_atom.provenance.is_material()
    # And it moves the posterior down (refuting LR < 1).
    claim = ScienceClaim(
        claim_type=ClaimType.THERAPEUTIC_WINDOW,
        question="window",
        prior=0.5,
        atoms=[claim_atom],
    )
    posterior = compute_claim_posterior(claim)
    assert posterior.posterior < 0.5
    assert posterior.n_material_atoms == 1


# --- invariant 3: provenance/source preserved through round trip ---------------


def test_atoms_round_trip_through_csv(tmp_path):
    atoms = extract_atoms_from_row(_corpus_row())
    out = write_atoms(atoms, tmp_path / "atoms.csv")
    with out.open(newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert header == list(ATOM_COLUMNS)
    loaded = load_atoms(out)
    assert [a.as_row() for a in loaded] == [a.as_row() for a in atoms]
    # Source linkage survives.
    assert all(a.source_id == "drugX:evidence" for a in loaded)
    assert all(a.program_id == "drugX" for a in loaded)


def test_atom_from_row_preserves_all_columns():
    atoms = extract_atoms_from_row(_corpus_row())
    row = atoms[0].as_row()
    assert atom_from_row(row) == atoms[0]
    assert list(row.keys()) == list(ATOM_COLUMNS)


# --- invariant 4: extraction never reads the outcome fields --------------------


def test_extraction_ignores_outcome_fields():
    held = extract_atoms_from_row(_corpus_row(claim_held="true", program_outcome="approved"))
    failed = extract_atoms_from_row(
        _corpus_row(claim_held="false", program_outcome="failed", failure_success_reason="tox")
    )
    # Identical evidence + differing outcome columns => byte-identical atoms.
    assert [a.as_row() for a in held] == [a.as_row() for a in failed]


def test_forbidden_fields_are_named_outcome_columns():
    assert FORBIDDEN_EVIDENCE_FIELDS == {
        "claim_held",
        "program_outcome",
        "failure_success_reason",
    }


def test_module_has_no_live_pos_path():
    import bve.analysis.claim_evidence_atoms as mod

    text = Path(mod.__file__).read_text(encoding="utf-8")
    assert "compute_science_modifier" not in text


# --- validation + summary ------------------------------------------------------


def test_validation_flags_bad_atoms():
    bad = [
        ExtractedAtom(
            atom_id="x",
            program_id="",
            claim_type="not_a_claim",
            evidence_span="",
            proposed_direction="neutral",
            likelihood_ratio="notnum",
            tier="platinum",
            source_type="",
            source_id="",
            observed_vs_inferred="guessed",
            population_match="unknown",
            rationale="",
            extraction_review_status="bogus",
            review_status="approved",
            extraction_source="test",
            extraction_date="2026-07-05",
        )
    ]
    problems = validate_atoms(bad)
    assert any("missing program_id" in p for p in problems)
    assert any("empty evidence_span" in p for p in problems)
    assert any("unknown claim_type" in p for p in problems)
    assert any("invalid tier" in p for p in problems)
    assert any("non-numeric likelihood_ratio" in p for p in problems)
    assert any("invalid extraction_review_status" in p for p in problems)
    assert any("invalid observed_vs_inferred" in p for p in problems)


def test_summary_reports_no_material_atoms_for_fresh_extraction():
    atoms = extract_atoms_from_row(_corpus_row())
    s = summarize_atoms(atoms)
    assert s.n_material_capable == 0
    assert s.n_extraction_approved == 0
    assert s.affects_live_pos is False
    assert any("inert" in n or "material" in n for n in s.notes)


# --- against the live corpus ---------------------------------------------------


def test_build_atoms_for_live_corpus_is_all_draft_and_valid():
    records = load_corpus(LIVE_CORPUS)
    atoms = build_atoms_for_corpus(records)
    assert atoms, "live corpus should yield candidate atoms"
    assert validate_atoms(atoms) == []
    # Every extracted atom is inert: draft + extracted.
    assert all(a.review_status == ReviewStatus.DRAFT.value for a in atoms)
    assert all(a.extraction_review_status == EXTRACTION_EXTRACTED for a in atoms)
    # And none is material when bridged into the ledger.
    for a in atoms:
        assert not to_claim_atom(a).provenance.is_material()


def test_record_input_matches_dict_input():
    row = _corpus_row()
    rec = ClaimCalibrationRecord(
        program_id=row["program_id"],
        target="",
        indication="",
        modality="",
        phase="",
        decision_date="",
        claim_type=row["claim_type"],
        claim_question="",
        evidence_available=row["evidence_available"],
        predicted_posterior=None,
        claim_held=row["claim_held"],
        program_outcome=row["program_outcome"],
        failure_success_reason=row["failure_success_reason"],
        source_links="",
        review_status="draft",
        label_source="",
        label_date="",
    )
    from_dict = [a.as_row() for a in extract_atoms_from_row(row)]
    from_rec = [a.as_row() for a in extract_atoms_from_row(rec)]
    assert from_dict == from_rec
