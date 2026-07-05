"""Tests for the AI source-drafting workflow + the hard human approval line.

Pins the contract "AI drafts -> human approves -> model scores":
  * a reviewer_candidate (AI) draft is never promotable;
  * an approved draft with an unverified source is never promotable;
  * only approved + source-verified + complete drafts become eligible atoms;
  * rejected drafts are dropped;
  * the reviewer packet is stamped AI-drafted and omits the outcome;
  * a promoted atom is calibration-eligible and moves the posterior;
  * nothing here touches live POS.
"""
from __future__ import annotations

import csv
from pathlib import Path

from bve.analysis.claim_calibration_corpus import ClaimCalibrationRecord, load_corpus
from bve.analysis.claim_evidence_atoms import build_atoms_for_corpus
from bve.analysis.claim_review_packet import (
    is_calibration_eligible,
    predicted_posterior_from_atoms,
)
from bve.analysis.claim_source_drafting import (
    DRAFT_APPROVED,
    DRAFT_CANDIDATE,
    DRAFT_REJECTED,
    SOURCE_DRAFT_COLUMNS,
    VERIFY_TRUE,
    VERIFY_UNVERIFIED,
    SourceDraft,
    build_source_drafts,
    draft_from_row,
    draft_status,
    is_draft_promotable,
    load_source_drafts,
    promote_drafts_to_atoms,
    render_reviewer_packet_markdown,
    validate_source_drafts,
    write_source_drafts,
)
from bve.intelligence.claim_ledger import ClaimType

REPO = Path(__file__).resolve().parents[1]
LIVE_CORPUS = REPO / "research" / "data" / "claim_calibration_corpus.csv"


def _draft(**kw) -> SourceDraft:
    base = dict(
        atom_id="d:ther:0",
        program_id="d",
        claim_type=ClaimType.THERAPEUTIC_WINDOW.value,
        claim_question="Is an efficacious dose achievable below the toxicity ceiling?",
        evidence_span="dose-limiting thrombocytopenia at efficacious exposure",
        proposed_direction="refuting",
        search_targets="FDA review; label",
        primary_source_link="https://www.accessdata.fda.gov/.../review.pdf",
        supporting_quote="Grade 3-4 thrombocytopenia required dose reductions in 40% of patients.",
        page_ref="Medical Review p.52",
        source_type="fda_review",
        drafted_tier="high",
        drafted_direction="refuting",
        drafted_likelihood_ratio="0.25",
        drafted_observed_vs_inferred="observed",
        drafted_limitations="single-arm",
        provenance_confidence="medium",
        drafter="ai:opus-4.8",
        draft_date="2026-07-05",
        source_verified=VERIFY_TRUE,
        review_status=DRAFT_APPROVED,
        reviewer="Chris",
        review_date="2026-07-06",
    )
    base.update(kw)
    return SourceDraft(**base)


def _record(**kw) -> ClaimCalibrationRecord:
    base = dict(
        program_id="d",
        target="BCL-xL",
        indication="MPN",
        modality="small_molecule",
        phase="phase_3",
        decision_date="2021-01-01",
        claim_type=ClaimType.THERAPEUTIC_WINDOW.value,
        claim_question="Q?",
        evidence_available="Dose-limiting thrombocytopenia.",
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


# --- the approval line ---------------------------------------------------------


def test_candidate_draft_is_never_promotable():
    assert is_draft_promotable(_draft(review_status=DRAFT_CANDIDATE)) is False


def test_approved_but_unverified_is_never_promotable():
    assert is_draft_promotable(_draft(source_verified=VERIFY_UNVERIFIED)) is False


def test_rejected_draft_is_dropped():
    assert is_draft_promotable(_draft(review_status=DRAFT_REJECTED)) is False


def test_missing_link_or_quote_blocks_promotion():
    assert is_draft_promotable(_draft(primary_source_link="")) is False
    assert is_draft_promotable(_draft(supporting_quote="")) is False


def test_missing_lr_or_low_tier_blocks_promotion():
    assert is_draft_promotable(_draft(drafted_likelihood_ratio="")) is False
    assert is_draft_promotable(_draft(drafted_tier="low")) is False


def test_fully_approved_verified_draft_is_promotable():
    assert is_draft_promotable(_draft()) is True


# --- promotion produces an eligible, posterior-moving atom ---------------------


def test_promotion_yields_only_approved_verified_atoms():
    drafts = [
        _draft(atom_id="a", review_status=DRAFT_CANDIDATE),        # AI draft
        _draft(atom_id="b", source_verified=VERIFY_UNVERIFIED),    # approved, unverified
        _draft(atom_id="c", review_status=DRAFT_REJECTED),         # rejected
        _draft(atom_id="d"),                                       # approved + verified
    ]
    atoms = promote_drafts_to_atoms(drafts)
    assert [a.atom_id for a in atoms] == ["d"]
    atom = atoms[0]
    # The promoted atom is calibration-eligible and carries the quote + source.
    assert is_calibration_eligible(atom) is True
    assert "thrombocytopenia" in atom.rationale
    assert atom.source_id.startswith("https://")


def test_promoted_atom_moves_the_posterior():
    atoms = promote_drafts_to_atoms([_draft(program_id="d")])
    pred = predicted_posterior_from_atoms("d", ClaimType.THERAPEUTIC_WINDOW, atoms)
    assert pred is not None
    assert pred < 0.5  # refuting evidence pushes the window claim down


# --- skeleton generation -------------------------------------------------------


def test_build_drafts_are_all_candidate_and_unverified():
    records = load_corpus(LIVE_CORPUS)
    atoms = build_atoms_for_corpus(records)
    drafts = build_source_drafts(records, atoms)
    assert len(drafts) == len(atoms)
    assert all(d.review_status == DRAFT_CANDIDATE for d in drafts)
    assert all(d.source_verified == VERIFY_UNVERIFIED for d in drafts)
    # Evidence fields blank (no fabrication); context + search targets present.
    assert all(d.primary_source_link == "" and d.supporting_quote == "" for d in drafts)
    assert all(d.search_targets for d in drafts)


def test_drafts_round_trip_through_csv(tmp_path):
    records = [_record(program_id="d")]
    atoms = build_atoms_for_corpus(records)
    drafts = build_source_drafts(records, atoms)
    out = write_source_drafts(drafts, tmp_path / "drafts.csv")
    with out.open(newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert header == list(SOURCE_DRAFT_COLUMNS)
    loaded = load_source_drafts(out)
    assert [d.as_row() for d in loaded] == [d.as_row() for d in drafts]


def test_draft_from_row_preserves_columns():
    d = _draft()
    assert draft_from_row(d.as_row()) == d


# --- validation ----------------------------------------------------------------


def test_validation_requires_verified_source_for_approval():
    bad = [
        _draft(source_verified=VERIFY_UNVERIFIED),  # approved but unverified
        _draft(primary_source_link=""),             # approved, no link
        _draft(supporting_quote=""),                # approved, no quote
        _draft(review_status="bogus"),
    ]
    problems = validate_source_drafts(bad)
    assert any("source_verified != true" in p for p in problems)
    assert any("no primary_source_link" in p for p in problems)
    assert any("no supporting_quote" in p for p in problems)
    assert any("invalid review_status" in p for p in problems)


def test_candidate_drafts_validate_clean():
    records = [_record(program_id="d")]
    drafts = build_source_drafts(records, build_atoms_for_corpus(records))
    assert validate_source_drafts(drafts) == []


# --- reviewer packet -----------------------------------------------------------


def test_reviewer_packet_is_stamped_and_blind():
    records = [_record(program_id="d")]
    drafts = build_source_drafts(records, build_atoms_for_corpus(records))
    md = render_reviewer_packet_markdown("d", records, drafts)
    assert "AI DRAFT — UNVERIFIED" in md
    assert "review_status = approved" in md
    # Outcome must not leak into a blind reviewer packet.
    assert "failed" not in md
    assert "claim_held" not in md


# --- status + live-POS guard ---------------------------------------------------


def test_status_reports_nothing_promotable_for_skeletons():
    records = load_corpus(LIVE_CORPUS)
    drafts = build_source_drafts(records, build_atoms_for_corpus(records))
    s = draft_status(drafts)
    assert s.n_candidate == s.n_drafts
    assert s.n_approved == 0
    assert s.n_promotable == 0
    assert s.affects_live_pos is False


def test_module_has_no_live_pos_path():
    import bve.analysis.claim_source_drafting as mod

    text = Path(mod.__file__).read_text(encoding="utf-8")
    assert "compute_science_modifier" not in text
