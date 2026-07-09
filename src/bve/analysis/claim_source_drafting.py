"""AI source-drafting workflow with a hard human approval line.

The review packet asks a human to do everything: find sources, pull quotes, set tiers and
weights. That is the bottleneck. AI can *draft* most of it — search primary sources, fill a
link, pull the supporting quote, propose tier/direction/weight — as long as the drafts can
never score themselves. This module enforces that line:

    AI drafts (reviewer_candidate) -> human verifies + approves -> model scores -> calibration

The load-bearing primitive is a distinct **``reviewer_candidate``** state that AI drafting
lands in. A candidate draft is structurally inert: it lives in its own file, and the only
path from a draft into the calibration-eligible atom store (:mod:`claim_evidence_atoms`)
runs through :func:`promote_drafts_to_atoms`, which lifts a draft **only** when a human has
set ``review_status=approved`` *and* ``source_verified=true``. A candidate — however
complete — is never promotable, and an ``approved`` draft with an unverified source is never
promotable. So an AI draft cannot move a posterior; a human check is a required edge in the
graph, not a norm.

Deliberate non-goal: this module does not fabricate sources or quotes. It builds the draft
skeleton (context + search targets + blank, human/fetch-filled evidence fields) and the
reviewer packet for Chris/Harvey. The ``primary_source_link`` and ``supporting_quote``
columns are filled by a real fetch pass with verifiable citations, never from model memory.

Strictly shadow: no import of, or write into, the live POS path.

Fetch-path hierarchy (the AI drafter's real-fetch pass should try these, in order, before
resorting to ``quote_status=needs_primary_pdf_confirmation``):

1. **PMC free full text** (``pmc.ncbi.nlm.nih.gov/articles/PMC<id>/``) for pivotal trial
   publications. Reliably fetchable, and often the primary clinical source underlying a
   label anyway. Find the PMCID via a PubMed search when the DOI/journal link is paywalled
   (``ascopubs.org`` and similar publisher sites frequently 403).
2. **DailyMed with an explicit ``version=`` parameter** for FDA label content on currently
   marketed drugs. The default DailyMed page serves the *current* (most-revised) label,
   which is wrong for a historical approval-basis claim — use
   ``GET /dailymed/services/v2/spls/<setid>/history.json`` to list every SPL version with
   its publish date, then fetch
   ``/dailymed/fda/fdaDrugXsl.cfm?setid=<setid>&type=display&version=<N>`` for the version
   published at/near the decision date. This gives a verbatim, dated, point-in-time label
   snapshot — not a lookahead-contaminated current one.
3. ``*.fda.gov`` (including ``accessdata.fda.gov`` PDFs) is domain-wide blocked to the
   fetcher (404s on every path tried, including non-PDF HTML pages) — do not keep retrying
   it. For a drug withdrawn from the market, DailyMed drops the label entirely; fall back to
   its PMC pivotal-trial publication instead (which usually has the same underlying safety
   data as the label anyway).
4. Only when none of the above resolves: reconstruct the quote from secondary reporting and
   mark ``quote_status=needs_primary_pdf_confirmation``, ``provenance_confidence=medium`` at
   best — never ``high``.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from bve.analysis.claim_calibration_corpus import ClaimCalibrationRecord, load_corpus
from bve.analysis.claim_evidence_atoms import (
    ATOM_COLUMNS,
    ExtractedAtom,
    build_atoms_for_corpus,
    load_atoms,
)
from bve.intelligence.claim_ledger import ClaimType

DEFAULT_DRAFTS_CSV = Path("research/review/claim_source_drafts.csv")
DEFAULT_PACKET_DIR = Path("research/review/reviewer_packets")

# Draft review states. AI drafting lands in reviewer_candidate; only a human moves a draft
# to approved (and must verify the source to do so) or rejected.
DRAFT_CANDIDATE = "reviewer_candidate"
DRAFT_APPROVED = "approved"
DRAFT_REJECTED = "rejected"
ALLOWED_DRAFT_STATUSES = frozenset({DRAFT_CANDIDATE, DRAFT_APPROVED, DRAFT_REJECTED})

# Source verification is a human act — AI cannot self-verify a quote against a source.
VERIFY_UNVERIFIED = "unverified"
VERIFY_TRUE = "true"
VERIFY_FALSE = "false"
ALLOWED_VERIFY = frozenset({VERIFY_UNVERIFIED, VERIFY_TRUE, VERIFY_FALSE})

# Quote fidelity. AI quotes reconstructed from a source we could not open verbatim (e.g. an
# FDA PDF blocked to the fetcher) are marked needs_primary_pdf_confirmation — acceptable for
# a reviewer_candidate, but the reviewer must confirm the exact wording before approval.
QUOTE_VERBATIM = "verbatim_confirmed"
QUOTE_NEEDS_PDF = "needs_primary_pdf_confirmation"
ALLOWED_QUOTE_STATUS = frozenset({"", QUOTE_VERBATIM, QUOTE_NEEDS_PDF})

_MATERIAL_TIERS = frozenset({"high", "medium"})

# Draft worksheet schema. Context first, then AI-drafted evidence fields, then the human
# approval columns (review_status / source_verified / reviewer / review_date).
SOURCE_DRAFT_COLUMNS = (
    # --- context (DO NOT EDIT) ---
    "atom_id",
    "program_id",
    "claim_type",
    "claim_question",
    "evidence_span",
    "proposed_direction",       # extraction hint
    "search_targets",           # where AI should look
    # --- AI drafts these (from a real fetch, not memory) ---
    "primary_source_link",
    "supporting_quote",
    "page_ref",
    "source_type",
    "drafted_tier",
    "drafted_direction",
    "drafted_likelihood_ratio",
    "drafted_observed_vs_inferred",
    "drafted_limitations",
    "provenance_confidence",    # AI self-rating (advisory only)
    "quote_status",             # verbatim_confirmed | needs_primary_pdf_confirmation
    "drafter",                  # e.g. ai:opus-4.8
    "draft_date",
    # --- human approval line (AI never sets these to approved/true) ---
    "source_verified",          # human confirms quote matches source -> true
    "review_status",            # human -> approved | rejected (else reviewer_candidate)
    "reviewer",
    "review_date",
)

_SEARCH_TARGETS: dict[str, str] = {
    ClaimType.THERAPEUTIC_WINDOW.value: (
        "FDA label (Adverse Reactions, Dosage/Administration, Warnings); FDA medical review; "
        "ODAC briefing; EPAR; pivotal paper (DLTs, dose reductions, discontinuations); "
        "ClinicalTrials.gov results (SAEs)"
    ),
    ClaimType.EXPOSURE_DELIVERY.value: (
        "FDA clinical pharmacology review; label Clinical Pharmacology/PK section; "
        "pivotal PK/PD paper (exposure-response, target coverage); ClinicalTrials.gov PK arm"
    ),
}
_SEARCH_TARGETS_DEFAULT = (
    "FDA review/label; pivotal publication; ClinicalTrials.gov; ODAC/EPAR where available"
)


@dataclass(frozen=True)
class SourceDraft:
    """One AI source-draft row awaiting human verification + approval."""

    atom_id: str
    program_id: str
    claim_type: str
    claim_question: str
    evidence_span: str
    proposed_direction: str
    search_targets: str
    primary_source_link: str
    supporting_quote: str
    page_ref: str
    source_type: str
    drafted_tier: str
    drafted_direction: str
    drafted_likelihood_ratio: str
    drafted_observed_vs_inferred: str
    drafted_limitations: str
    provenance_confidence: str
    drafter: str
    draft_date: str
    source_verified: str
    review_status: str
    reviewer: str
    review_date: str
    quote_status: str = ""

    def as_row(self) -> dict[str, str]:
        return {col: getattr(self, col) for col in SOURCE_DRAFT_COLUMNS}

    @property
    def is_human_approved(self) -> bool:
        return self.review_status.strip().lower() == DRAFT_APPROVED

    @property
    def is_source_verified(self) -> bool:
        return self.source_verified.strip().lower() == VERIFY_TRUE


# --- skeleton generation --------------------------------------------------------


def _search_targets(claim_type: str, rec: ClaimCalibrationRecord | None) -> str:
    base = _SEARCH_TARGETS.get(claim_type, _SEARCH_TARGETS_DEFAULT)
    if rec and (rec.target or rec.indication):
        return f"{base}  [query: {rec.target} {rec.indication} {rec.modality}]".strip()
    return base


def build_source_drafts(
    records: list[ClaimCalibrationRecord],
    atoms: list[ExtractedAtom],
    *,
    drafter: str = "ai:pending",
    draft_date: str = "",
) -> list[SourceDraft]:
    """Build one reviewer-candidate draft skeleton per candidate atom.

    Context and search targets are filled; the evidence fields are left blank for a real
    fetch pass. Every draft is ``reviewer_candidate`` + ``unverified`` — inert by state.
    """
    by_program = {r.program_id: r for r in records}
    drafts: list[SourceDraft] = []
    for atom in atoms:
        rec = by_program.get(atom.program_id)
        drafts.append(
            SourceDraft(
                atom_id=atom.atom_id,
                program_id=atom.program_id,
                claim_type=atom.claim_type,
                claim_question=rec.claim_question if rec else "",
                evidence_span=atom.evidence_span,
                proposed_direction=atom.proposed_direction,
                search_targets=_search_targets(atom.claim_type, rec),
                primary_source_link="",
                supporting_quote="",
                page_ref="",
                source_type="",
                drafted_tier="",
                drafted_direction="",
                drafted_likelihood_ratio="",
                drafted_observed_vs_inferred="",
                drafted_limitations="",
                provenance_confidence="",
                quote_status="",
                drafter=drafter,
                draft_date=draft_date,
                source_verified=VERIFY_UNVERIFIED,
                review_status=DRAFT_CANDIDATE,
                reviewer="",
                review_date="",
            )
        )
    return drafts


# --- loader / writer / validation ----------------------------------------------


def draft_from_row(row: dict[str, str]) -> SourceDraft:
    return SourceDraft(**{c: (row.get(c, "") or "").strip() for c in SOURCE_DRAFT_COLUMNS})


def load_source_drafts(path: Path = DEFAULT_DRAFTS_CSV) -> list[SourceDraft]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as handle:
        return [draft_from_row(r) for r in csv.DictReader(handle)]


def write_source_drafts(
    drafts: list[SourceDraft], out_csv: Path = DEFAULT_DRAFTS_CSV
) -> Path:
    out = Path(out_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(SOURCE_DRAFT_COLUMNS))
        writer.writeheader()
        writer.writerows(d.as_row() for d in drafts)
    return out


def validate_source_drafts(drafts: list[SourceDraft]) -> list[str]:
    """Human-readable validation problems (empty => clean)."""
    problems: list[str] = []
    for i, d in enumerate(drafts):
        where = f"draft {i} ({d.atom_id or '?'})"
        if not d.program_id:
            problems.append(f"{where}: missing program_id")
        if d.review_status.strip().lower() not in ALLOWED_DRAFT_STATUSES:
            problems.append(f"{where}: invalid review_status '{d.review_status}'")
        if d.source_verified.strip().lower() not in ALLOWED_VERIFY:
            problems.append(f"{where}: invalid source_verified '{d.source_verified}'")
        if d.quote_status.strip().lower() not in ALLOWED_QUOTE_STATUS:
            problems.append(f"{where}: invalid quote_status '{d.quote_status}'")
        # An approved draft must carry a verified primary source + quote — no exceptions.
        if d.is_human_approved:
            if not d.is_source_verified:
                problems.append(f"{where}: approved but source_verified != true")
            if not d.primary_source_link.strip():
                problems.append(f"{where}: approved but no primary_source_link")
            if not d.supporting_quote.strip():
                problems.append(f"{where}: approved but no supporting_quote")
    return problems


# --- the approval line: draft -> calibration-eligible atom ----------------------


def is_draft_promotable(draft: SourceDraft) -> bool:
    """Whether a draft may become a calibration-eligible atom.

    Requires a human-approved review status AND a verified source AND a real link + quote
    AND a material tier AND a valid positive likelihood ratio. A ``reviewer_candidate`` (AI
    draft) always fails here — the human approval + verification edge is mandatory.
    """
    if not draft.is_human_approved:
        return False
    if not draft.is_source_verified:
        return False
    if not draft.primary_source_link.strip() or not draft.supporting_quote.strip():
        return False
    if draft.source_type.strip() == "":
        return False
    if draft.drafted_tier.strip().lower() not in _MATERIAL_TIERS:
        return False
    try:
        lr = float(draft.drafted_likelihood_ratio)
    except (TypeError, ValueError):
        return False
    return lr > 0.0


def _draft_to_atom(draft: SourceDraft) -> ExtractedAtom:
    quote = draft.supporting_quote.strip()
    page = f" [{draft.page_ref.strip()}]" if draft.page_ref.strip() else ""
    return ExtractedAtom(
        atom_id=draft.atom_id,
        program_id=draft.program_id,
        claim_type=draft.claim_type,
        evidence_span=draft.evidence_span,
        proposed_direction=draft.drafted_direction or draft.proposed_direction,
        likelihood_ratio=draft.drafted_likelihood_ratio.strip(),
        tier=draft.drafted_tier.strip().lower(),
        source_type=draft.source_type.strip(),
        source_id=draft.primary_source_link.strip(),
        observed_vs_inferred=draft.drafted_observed_vs_inferred.strip().lower() or "observed",
        population_match="unknown",
        rationale=f"{quote}{page} ({draft.primary_source_link.strip()})",
        # Promotion is the moment the extraction is treated as human-approved.
        extraction_review_status="approved",
        review_status="approved",
        extraction_source=f"human-approved source draft by {draft.reviewer or 'reviewer'}",
        extraction_date=draft.review_date or draft.draft_date,
    )


def promote_drafts_to_atoms(drafts: list[SourceDraft]) -> list[ExtractedAtom]:
    """Convert only human-approved, source-verified drafts into eligible atoms.

    Candidate and rejected drafts (and approved-but-unverified drafts) are dropped.
    """
    return [_draft_to_atom(d) for d in drafts if is_draft_promotable(d)]


# --- reviewer packet for Chris/Harvey ------------------------------------------


def render_reviewer_packet_markdown(
    program_id: str,
    records: list[ClaimCalibrationRecord],
    drafts: list[SourceDraft],
) -> str:
    """Render a per-program reviewer packet, clearly stamped AI-drafted / unverified."""
    rec = next((r for r in records if r.program_id == program_id), None)
    program_drafts = [d for d in drafts if d.program_id == program_id]
    lines: list[str] = [
        f"# Reviewer packet: {program_id}",
        "",
        "> **AI DRAFT — UNVERIFIED.** Every quote below must be confirmed against the linked "
        "primary source before approval. Nothing here scores until you set "
        "`source_verified=true` and `review_status=approved`.",
        "",
    ]
    if rec:
        lines += [
            f"- **Claim family:** {rec.claim_type}",
            f"- **Question:** {rec.claim_question}",
            f"- **Indication / modality:** {rec.indication} / {rec.modality}",
            f"- **Decision date:** {rec.decision_date}",
            "",
            "> Outcome is intentionally omitted — approve on the evidence, blind to the label.",
            "",
        ]
    for d in program_drafts:
        lines += [
            f"## {d.atom_id}",
            f"- **Evidence span:** {d.evidence_span}",
            f"- **Search targets:** {d.search_targets}",
            f"- **Primary source (AI draft):** {d.primary_source_link or '_(to fill)_'}",
            f"- **Supporting quote (AI draft, verify):** {d.supporting_quote or '_(to fill)_'}",
            f"- **Quote status:** {d.quote_status or '_(to fill)_'}",
            f"- **Page ref:** {d.page_ref or '_(to fill)_'}",
            f"- **Drafted source_type / tier / direction / LR:** "
            f"{d.source_type or '?'} / {d.drafted_tier or '?'} / "
            f"{d.drafted_direction or '?'} / {d.drafted_likelihood_ratio or '?'}",
            f"- **AI confidence (advisory):** {d.provenance_confidence or '?'}",
            "",
            "**Reviewer decision:**",
            "- [ ] quote confirmed against source → `source_verified=true`",
            "- [ ] tier / direction / likelihood_ratio correct (edit if not)",
            "- [ ] `review_status = approved`  — or  `review_status = rejected`",
            "",
        ]
    return "\n".join(lines)


def write_reviewer_packets(
    records: list[ClaimCalibrationRecord],
    drafts: list[SourceDraft],
    out_dir: Path = DEFAULT_PACKET_DIR,
) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for program_id in sorted({d.program_id for d in drafts if d.program_id}):
        path = out_dir / f"{program_id}.md"
        path.write_text(
            render_reviewer_packet_markdown(program_id, records, drafts), encoding="utf-8"
        )
        written.append(path)
    return written


# --- diagnostic -----------------------------------------------------------------


@dataclass(frozen=True)
class DraftStatus:
    n_drafts: int
    n_candidate: int
    n_approved: int
    n_promotable: int
    affects_live_pos: bool = False


def draft_status(drafts: list[SourceDraft]) -> DraftStatus:
    return DraftStatus(
        n_drafts=len(drafts),
        n_candidate=sum(1 for d in drafts if d.review_status.strip().lower() == DRAFT_CANDIDATE),
        n_approved=sum(1 for d in drafts if d.is_human_approved),
        n_promotable=sum(1 for d in drafts if is_draft_promotable(d)),
    )


# --- CLI ------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "AI source-drafting workflow with a hard human approval line. 'draft' builds "
            "reviewer-candidate skeletons + Chris/Harvey packets; 'promote' lifts only "
            "human-approved + source-verified drafts into eligible atoms; 'status' reports "
            "the pipeline. AI drafts are inert until a human verifies + approves."
        )
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    dr = sub.add_parser("draft", help="build candidate drafts + reviewer packets")
    dr.add_argument("--corpus", default=None)
    dr.add_argument("--atoms", default=None)
    dr.add_argument("--out", default=str(DEFAULT_DRAFTS_CSV))
    dr.add_argument("--packets", action="store_true", help="also write per-program packets")

    pr = sub.add_parser("promote", help="promote approved+verified drafts to atoms CSV")
    pr.add_argument("--drafts", default=str(DEFAULT_DRAFTS_CSV))
    pr.add_argument("--out", default="research/data/claim_evidence_atoms_approved.csv")

    st = sub.add_parser("status", help="report draft pipeline status")
    st.add_argument("--drafts", default=str(DEFAULT_DRAFTS_CSV))

    args = parser.parse_args()

    if args.cmd == "draft":
        records = load_corpus(Path(args.corpus)) if args.corpus else load_corpus()
        atoms = load_atoms(Path(args.atoms)) if args.atoms else load_atoms()
        if not atoms:
            atoms = build_atoms_for_corpus(records)
        drafts = build_source_drafts(records, atoms)
        out = write_source_drafts(drafts, Path(args.out))
        print(f"Wrote {len(drafts)} reviewer-candidate drafts -> {out}")
        print("  ALL drafts: review_status=reviewer_candidate, source_verified=unverified (inert).")
        print("  Fill primary_source_link + supporting_quote from a REAL fetch (not memory).")
        if args.packets:
            paths = write_reviewer_packets(records, drafts)
            print(f"  Wrote {len(paths)} reviewer packets -> {DEFAULT_PACKET_DIR}/")
    elif args.cmd == "promote":
        drafts = load_source_drafts(Path(args.drafts))
        problems = validate_source_drafts(drafts)
        if problems:
            print(f"VALIDATION ({len(problems)} problems) — fix before promoting:")
            for p in problems[:20]:
                print(f"  - {p}")
            return
        atoms = promote_drafts_to_atoms(drafts)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(ATOM_COLUMNS))
            writer.writeheader()
            writer.writerows(a.as_row() for a in atoms)
        print(f"Promoted {len(atoms)}/{len(drafts)} drafts (approved + verified) -> {out}")
    elif args.cmd == "status":
        s = draft_status(load_source_drafts(Path(args.drafts)))
        print(
            f"drafts={s.n_drafts} candidate={s.n_candidate} approved={s.n_approved} "
            f"promotable={s.n_promotable} affects_live_pos={s.affects_live_pos}"
        )
        if s.n_promotable == 0:
            print("  note: nothing promotable — AI drafts inert until human verifies + approves")


if __name__ == "__main__":
    main()
