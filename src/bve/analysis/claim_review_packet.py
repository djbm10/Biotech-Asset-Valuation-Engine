"""Reviewer packet + promotion gates for the claim-atom review pass.

The extraction scaffold (:mod:`bve.analysis.claim_evidence_atoms`) produced 97 inert
candidate atoms. The bottleneck is now human review, not code. This module builds the
worksheet a reviewer works from, and — critically — the *gates* that decide which reviewed
atoms are allowed to reach a calibration row.

Two deliverables:

  * **Reviewer packet** (:func:`build_review_packet` -> ``research/review/
    claim_atom_review_packet.csv``, plus optional per-program Markdown). Each row joins a
    candidate atom to its corpus context (claim question, full evidence, current source
    links) and lists the *needed primary sources* alongside blank columns the reviewer
    fills: source_type, primary_source_link, observed_vs_inferred, evidence_tier,
    direction, likelihood_ratio, limitations, extraction_review_status=reviewed,
    review_status=approved|rejected.
  * **Promotion gates** (:func:`is_calibration_eligible`, :func:`predicted_posterior_from_atoms`,
    :func:`writeback_predictions`). These add *no* new model logic — they reuse the existing
    claim-ledger posterior engine — but they enforce the calibration contract:
      - only an atom whose *extraction* is approved AND whose *provenance* is approved counts;
      - a rejected atom is ignored;
      - an atom with a missing/invalid likelihood ratio cannot be material;
      - an atom with no approved primary source cannot form a calibration row;
      - a program with no eligible material atoms produces no ``predicted_posterior``.

Strictly shadow: no import of, or write into, the live POS path. A ``predicted_posterior``
is a diagnostic against a reviewed outcome, never a live-POS authorization.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from bve.analysis.claim_calibration_corpus import (
    CORPUS_COLUMNS,
    ClaimCalibrationRecord,
    load_corpus,
)
from bve.analysis.claim_evidence_atoms import (
    ExtractedAtom,
    build_atoms_for_corpus,
    build_science_claim,
    load_atoms,
)
from bve.intelligence.claim_ledger import ClaimType, compute_claim_posterior

DEFAULT_PACKET_CSV = Path("research/review/claim_atom_review_packet.csv")
DEFAULT_MARKDOWN_DIR = Path("research/review/programs")

# Packet schema: read-only context first, then the columns the reviewer fills.
PACKET_COLUMNS = (
    # --- context (DO NOT EDIT) ---
    "program_id",
    "claim_type",
    "claim_question",
    "atom_id",
    "evidence_span",
    "proposed_direction",
    "evidence_available",       # full corpus evidence prose for context
    "current_source_links",     # what the corpus row currently cites (often secondary)
    "needed_primary_sources",   # what a reviewer should go find
    # --- reviewer fills these ---
    "source_type",
    "primary_source_link",
    "observed_vs_inferred",
    "evidence_tier",
    "direction",
    "likelihood_ratio",
    "limitations",
    "extraction_review_status",  # reviewer sets -> reviewed / approved
    "review_status",             # reviewer sets -> approved / rejected
    "reviewer",
    "review_date",
)

# Suggested primary sources by claim family (guidance text, not a link).
_NEEDED_SOURCES: dict[str, str] = {
    ClaimType.THERAPEUTIC_WINDOW.value: (
        "FDA label (Adverse Reactions + Dosage/Administration); FDA medical/clinical "
        "review; ODAC briefing doc; EPAR; pivotal trial paper (DLTs, dose reductions); "
        "ClinicalTrials.gov results (SAEs, discontinuations)"
    ),
    ClaimType.EXPOSURE_DELIVERY.value: (
        "FDA clinical pharmacology review; label PK/Clinical Pharmacology section; "
        "pivotal PK/PD paper (exposure-response, target coverage); ClinicalTrials.gov "
        "PK arm"
    ),
}
_NEEDED_SOURCES_DEFAULT = (
    "FDA review/label; pivotal trial publication; ClinicalTrials.gov; ODAC/EPAR where available"
)

# --- calibration-eligibility gate ------------------------------------------------

_MATERIAL_TIERS = frozenset({"high", "medium"})
_APPROVED = "approved"


def is_calibration_eligible(atom: ExtractedAtom) -> bool:
    """Whether a reviewed atom may contribute to a calibration prediction.

    Every clause is a separable failure of the review contract. All must pass:
      * the *extraction* is approved (``extraction_review_status == approved``);
      * the *provenance* is approved (``review_status == approved``) — a rejected or draft
        atom is ignored;
      * an approved primary source is named (``source_type`` non-empty) — no source, no row;
      * the likelihood ratio parses to a positive float — a missing LR blocks materiality;
      * the tier is material-capable (high/medium) — low-tier evidence only raises a question.
    """
    if not atom.is_extraction_approved:
        return False
    if atom.review_status.strip().lower() != _APPROVED:
        return False
    if not atom.source_type.strip():
        return False
    try:
        lr = float(atom.likelihood_ratio)
    except (TypeError, ValueError):
        return False
    if lr <= 0.0:
        return False
    if atom.tier.strip().lower() not in _MATERIAL_TIERS:
        return False
    return True


def predicted_posterior_from_atoms(
    program_id: str,
    claim_type: ClaimType,
    atoms: list[ExtractedAtom],
    *,
    prior: float = 0.5,
) -> Optional[float]:
    """Per-program claim posterior from calibration-eligible atoms only.

    Returns ``None`` (no calibration row) when the program has no eligible, material atoms.
    Reuses the existing ledger posterior engine — no new model logic.
    """
    eligible = [
        a
        for a in atoms
        if a.program_id == program_id
        and a.claim_type == claim_type.value
        and is_calibration_eligible(a)
    ]
    if not eligible:
        return None
    claim = build_science_claim(program_id, claim_type, eligible, prior=prior)
    posterior = compute_claim_posterior(claim)
    if posterior.n_material_atoms == 0:
        return None
    return posterior.posterior


# --- reviewer packet -------------------------------------------------------------


def _needed_sources(claim_type: str) -> str:
    return _NEEDED_SOURCES.get(claim_type, _NEEDED_SOURCES_DEFAULT)


def build_review_packet(
    records: list[ClaimCalibrationRecord],
    atoms: list[ExtractedAtom],
) -> list[dict[str, str]]:
    """Join every candidate atom to its corpus context into a reviewer worksheet row.

    All draft atoms are included (nothing is silently dropped); reviewer columns are blank.
    """
    by_program: dict[str, ClaimCalibrationRecord] = {r.program_id: r for r in records}
    rows: list[dict[str, str]] = []
    for atom in atoms:
        rec = by_program.get(atom.program_id)
        rows.append(
            {
                "program_id": atom.program_id,
                "claim_type": atom.claim_type,
                "claim_question": rec.claim_question if rec else "",
                "atom_id": atom.atom_id,
                "evidence_span": atom.evidence_span,
                "proposed_direction": atom.proposed_direction,
                "evidence_available": rec.evidence_available if rec else "",
                "current_source_links": rec.source_links if rec else "",
                "needed_primary_sources": _needed_sources(atom.claim_type),
                # reviewer fills these
                "source_type": "",
                "primary_source_link": "",
                "observed_vs_inferred": "",
                "evidence_tier": "",
                "direction": "",
                "likelihood_ratio": "",
                "limitations": "",
                "extraction_review_status": "",
                "review_status": "",
                "reviewer": "",
                "review_date": "",
            }
        )
    return rows


def write_review_packet(
    rows: list[dict[str, str]], out_csv: Path = DEFAULT_PACKET_CSV
) -> Path:
    """Write the packet to CSV in schema order (creates parent dir)."""
    out = Path(out_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(PACKET_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    return out


def render_program_markdown(
    program_id: str,
    records: list[ClaimCalibrationRecord],
    atoms: list[ExtractedAtom],
) -> str:
    """Render a per-program Markdown review sheet (context + a checklist per atom)."""
    rec = next((r for r in records if r.program_id == program_id), None)
    program_atoms = [a for a in atoms if a.program_id == program_id]
    lines: list[str] = [f"# Review: {program_id}", ""]
    if rec:
        lines += [
            f"- **Claim family:** {rec.claim_type}",
            f"- **Question:** {rec.claim_question}",
            f"- **Indication / modality:** {rec.indication} / {rec.modality}",
            f"- **Decision date:** {rec.decision_date}",
            f"- **Current sources (verify/replace):** {rec.source_links or '—'}",
            f"- **Needed primary sources:** {_needed_sources(rec.claim_type)}",
            "",
            "> Outcome columns are intentionally omitted — review the evidence blind to the label.",
            "",
            "## Evidence available at decision",
            "",
            rec.evidence_available or "_(none recorded)_",
            "",
        ]
    lines += ["## Candidate atoms to review", ""]
    for a in program_atoms:
        lines += [
            f"### {a.atom_id}",
            f"- **Span:** {a.evidence_span}",
            f"- **Proposed direction (hint):** {a.proposed_direction}",
            "- [ ] source_type + primary_source_link",
            "- [ ] observed_vs_inferred",
            "- [ ] evidence_tier",
            "- [ ] direction + likelihood_ratio",
            "- [ ] limitations",
            "- [ ] extraction_review_status = reviewed",
            "- [ ] review_status = approved | rejected",
            "",
        ]
    return "\n".join(lines)


def write_program_markdowns(
    records: list[ClaimCalibrationRecord],
    atoms: list[ExtractedAtom],
    out_dir: Path = DEFAULT_MARKDOWN_DIR,
) -> list[Path]:
    """Write one Markdown review sheet per program that has candidate atoms."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for program_id in sorted({a.program_id for a in atoms if a.program_id}):
        path = out_dir / f"{program_id}.md"
        path.write_text(
            render_program_markdown(program_id, records, atoms), encoding="utf-8"
        )
        written.append(path)
    return written


# --- writeback: reviewed atoms -> corpus predicted_posterior ---------------------


def writeback_predictions(
    records: list[ClaimCalibrationRecord],
    atoms: list[ExtractedAtom],
    *,
    prior: float = 0.5,
) -> list[dict[str, str]]:
    """Return corpus rows with ``predicted_posterior`` filled where a prediction exists.

    A row is filled only when its program has calibration-eligible atoms for its claim
    family; otherwise ``predicted_posterior`` is left blank. Non-destructive: returns new
    schema-shaped dict rows, does not mutate the records.
    """
    rows: list[dict[str, str]] = []
    for rec in records:
        try:
            claim_type = ClaimType(rec.claim_type)
            pred = predicted_posterior_from_atoms(
                rec.program_id, claim_type, atoms, prior=prior
            )
        except ValueError:
            pred = None
        row = {col: str(getattr(rec, col, "") or "") for col in CORPUS_COLUMNS}
        row["predicted_posterior"] = "" if pred is None else f"{pred:.4f}"
        rows.append(row)
    return rows


# --- diagnostic ------------------------------------------------------------------


@dataclass(frozen=True)
class PacketStatus:
    n_atoms: int
    n_programs: int
    n_eligible: int
    n_programs_predictable: int
    affects_live_pos: bool = False


def packet_status(
    records: list[ClaimCalibrationRecord], atoms: list[ExtractedAtom]
) -> PacketStatus:
    n_eligible = sum(1 for a in atoms if is_calibration_eligible(a))
    predictable = 0
    for rec in records:
        try:
            if (
                predicted_posterior_from_atoms(rec.program_id, ClaimType(rec.claim_type), atoms)
                is not None
            ):
                predictable += 1
        except ValueError:
            continue
    return PacketStatus(
        n_atoms=len(atoms),
        n_programs=len({a.program_id for a in atoms if a.program_id}),
        n_eligible=n_eligible,
        n_programs_predictable=predictable,
    )


# --- CLI -------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Claim-atom review packet + promotion gates. 'packet' builds the reviewer "
            "worksheet (CSV + per-program Markdown). 'status' reports how many atoms are "
            "calibration-eligible. No approved atoms => nothing predictable (gate closed)."
        )
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    pk = sub.add_parser("packet", help="build reviewer packet from corpus + atom worksheet")
    pk.add_argument("--corpus", default=None)
    pk.add_argument("--atoms", default=None, help="atom worksheet CSV (default: repo)")
    pk.add_argument("--out", default=str(DEFAULT_PACKET_CSV))
    pk.add_argument("--markdown", action="store_true", help="also write per-program Markdown")

    st = sub.add_parser("status", help="report calibration-eligibility over the atom worksheet")
    st.add_argument("--corpus", default=None)
    st.add_argument("--atoms", default=None)

    args = parser.parse_args()
    records = load_corpus(Path(args.corpus)) if args.corpus else load_corpus()
    atoms = load_atoms(Path(args.atoms)) if args.atoms else load_atoms()
    if not atoms:
        # Fall back to a fresh extraction so the packet is never silently empty.
        atoms = build_atoms_for_corpus(records)

    if args.cmd == "packet":
        rows = build_review_packet(records, atoms)
        out = write_review_packet(rows, Path(args.out))
        print(f"Wrote {len(rows)} review rows ({len(atoms)} atoms) -> {out}")
        if args.markdown:
            paths = write_program_markdowns(records, atoms)
            print(f"Wrote {len(paths)} per-program Markdown sheets -> {DEFAULT_MARKDOWN_DIR}/")
        print(f"Set {date.today().isoformat()} review_date as you go. Fill reviewer columns,")
        print("promote atoms to approved (with primary sources), then re-run status.")
    elif args.cmd == "status":
        s = packet_status(records, atoms)
        print(
            f"atoms={s.n_atoms} programs={s.n_programs} eligible={s.n_eligible} "
            f"predictable_programs={s.n_programs_predictable} affects_live_pos={s.affects_live_pos}"
        )
        if s.n_eligible == 0:
            print("  note: no calibration-eligible atoms yet — review gate closed, nothing scored")


if __name__ == "__main__":
    main()
