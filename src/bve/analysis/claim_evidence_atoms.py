"""Evidence-atom extraction scaffold (POS Claim-Ledger Build Plan, extraction-QA phase).

Calibration needs a *pair* per program: the model's predicted claim posterior versus
the reviewed outcome. The corpus (:mod:`bve.analysis.claim_calibration_corpus`) supplies
the outcome; this module supplies the other half of the pair by turning each row's
``evidence_available`` prose into structured, reviewable :class:`ClaimEvidenceAtom`
inputs that the claim ledger can then score.

The build plan is explicit that a bad evidence base makes a well-engineered model
confidently wrong. So the scaffold is deliberately timid:

  * **Conservative by construction.** Every freshly extracted atom is LOW-tier,
    ``inferred`` rather than observed, ``review_status=draft``, ``extraction_review_status
    =extracted``, and carries a placeholder ``likelihood_ratio=1.0`` (no movement). Each
    of those four alone is enough to zero the materiality gate — so a raw extraction can
    never move a posterior. The reviewer promotes tier, sets the real LR, marks
    observed, and approves; only then can an atom become material.
  * **Extraction reads evidence only.** :func:`extract_atoms_from_row` reads
    ``evidence_available`` (plus ``program_id`` / ``claim_type`` for linkage) and nothing
    else. The outcome columns (``claim_held``, ``program_outcome``,
    ``failure_success_reason``) are never inspected — extraction cannot peek at the label
    it will later be scored against. This is pinned by tests.
  * **Unreviewed atoms cannot yield approved predictions.** :func:`to_claim_atom` forces
    ``review_status`` down to DRAFT whenever the extraction itself is not approved, so an
    atom cannot smuggle an ``approved`` provenance past an unreviewed extraction.

Strictly shadow: nothing here imports or writes the live POS path.
"""
from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from bve.analysis.claim_calibration_corpus import (
    ClaimCalibrationRecord,
    load_corpus,
)
from bve.intelligence.claim_ledger import (
    ClaimEvidenceAtom,
    ClaimType,
    EvidenceTier,
    MatchStatus,
    ObservationBasis,
    ReviewStatus,
    ScienceClaim,
    make_claim_atom,
)

DEFAULT_ATOMS_CSV = Path("research/data/claim_evidence_atoms.csv")

# Atom worksheet schema, in order. One row = one candidate evidence atom awaiting review.
ATOM_COLUMNS = (
    "atom_id",
    "program_id",             # foreign key back to the corpus row
    "claim_type",
    "evidence_span",          # the prose snippet this atom was extracted from
    "proposed_direction",     # advisory hint only (confirming|refuting|neutral)
    "likelihood_ratio",       # PLACEHOLDER 1.0 until a reviewer sets it
    "tier",                   # default low (non-material until promoted)
    "source_type",
    "source_id",
    "observed_vs_inferred",   # default inferred (non-material until confirmed observed)
    "population_match",
    "rationale",
    "extraction_review_status",  # extracted|reviewed|approved
    "review_status",          # draft|reviewed|approved (provenance review)
    "extraction_source",
    "extraction_date",
)

# Extraction review states, ascending trust. Only an approved extraction may carry an
# approved provenance through :func:`to_claim_atom`.
EXTRACTION_EXTRACTED = "extracted"
EXTRACTION_REVIEWED = "reviewed"
EXTRACTION_APPROVED = "approved"
ALLOWED_EXTRACTION_STATUSES = frozenset(
    {EXTRACTION_EXTRACTED, EXTRACTION_REVIEWED, EXTRACTION_APPROVED}
)

# Outcome columns the extractor must never read (guards against label leakage).
FORBIDDEN_EVIDENCE_FIELDS = frozenset(
    {"claim_held", "program_outcome", "failure_success_reason"}
)

# Advisory direction hints. These NEVER set the likelihood ratio (which stays a neutral
# placeholder); they only pre-fill the reviewer's "proposed_direction" column.
_REFUTING_HINT = re.compile(
    r"fail|did not|no (?:significant |meaningful )?benefit|lack|toxic|dose[- ]limit|"
    r"discontinu|halt|terminat|narrow therapeutic|insufficient|underdos|could not|"
    r"unable|effusion|thrombocyto|neutropen|hepatotox|pneumonitis|colitis|"
    r"poor (?:exposure|penetrat)|below (?:the )?efficac",
    re.IGNORECASE,
)
_CONFIRMING_HINT = re.compile(
    r"achiev|demonstrat|adequate exposure|well[- ]tolerated|sustained|robust|"
    r"favorable|met (?:the )?(?:primary )?endpoint|significant improvement|"
    r"acceptable safety|wide therapeutic|target engagement confirmed",
    re.IGNORECASE,
)

_MIN_SPAN_CHARS = 15
_MAX_ATOMS_PER_ROW = 6
_SPAN_SPLIT = re.compile(r"(?<=[.;])\s+|\n+")
# Seed/placeholder markers stripped from prose before extraction.
_SEED_MARKER = re.compile(r"\[(?:SEED|EXTRACTED)[^\]]*\]|REVIEW REQUIRED", re.IGNORECASE)


@dataclass(frozen=True)
class ExtractedAtom:
    """One candidate evidence atom, awaiting human review. All fields are strings on disk."""

    atom_id: str
    program_id: str
    claim_type: str
    evidence_span: str
    proposed_direction: str
    likelihood_ratio: str
    tier: str
    source_type: str
    source_id: str
    observed_vs_inferred: str
    population_match: str
    rationale: str
    extraction_review_status: str
    review_status: str
    extraction_source: str
    extraction_date: str

    @property
    def is_extraction_approved(self) -> bool:
        return self.extraction_review_status.strip().lower() == EXTRACTION_APPROVED

    def as_row(self) -> dict[str, str]:
        return {col: getattr(self, col) for col in ATOM_COLUMNS}


# ---------------------------------------------------------------------------
# Extraction — prose -> candidate atoms (reads evidence_available ONLY)
# ---------------------------------------------------------------------------


def _proposed_direction(span: str) -> str:
    """Advisory direction hint from keywords. Never sets the likelihood ratio."""
    if _REFUTING_HINT.search(span):
        return "refuting"
    if _CONFIRMING_HINT.search(span):
        return "confirming"
    return "neutral"


def _candidate_spans(prose: str) -> list[str]:
    cleaned = _SEED_MARKER.sub("", prose or "").strip()
    spans: list[str] = []
    for raw in _SPAN_SPLIT.split(cleaned):
        span = raw.strip(" \t-–—•")
        if len(span) >= _MIN_SPAN_CHARS:
            spans.append(span)
    return spans[:_MAX_ATOMS_PER_ROW]


def extract_atoms_from_row(
    row: dict[str, str] | ClaimCalibrationRecord,
    *,
    extraction_date: str | None = None,
) -> list[ExtractedAtom]:
    """Extract conservative candidate atoms from ONE corpus row's evidence prose.

    Reads ``program_id``, ``claim_type`` and ``evidence_available`` only. The outcome
    columns are never consulted — extraction cannot see the label it will be scored
    against. Every atom is emitted LOW-tier / inferred / draft / LR=1.0, i.e. inert.
    """
    if isinstance(row, ClaimCalibrationRecord):
        program_id = row.program_id
        claim_type = row.claim_type
        evidence = row.evidence_available
    else:
        program_id = (row.get("program_id", "") or "").strip()
        claim_type = (row.get("claim_type", "") or "").strip()
        evidence = row.get("evidence_available", "") or ""

    when = extraction_date or date.today().isoformat()
    short = claim_type.split("_")[0][:4] or "clm"
    atoms: list[ExtractedAtom] = []
    for i, span in enumerate(_candidate_spans(evidence)):
        atoms.append(
            ExtractedAtom(
                atom_id=f"{program_id}:{short}:{i}",
                program_id=program_id,
                claim_type=claim_type,
                evidence_span=span,
                proposed_direction=_proposed_direction(span),
                likelihood_ratio="1.0",  # placeholder: no movement until a reviewer sets it
                tier=EvidenceTier.LOW.value,  # non-material until promoted
                source_type="",
                source_id=f"{program_id}:evidence",
                observed_vs_inferred=ObservationBasis.INFERRED.value,  # non-material until confirmed
                population_match=MatchStatus.UNKNOWN.value,
                rationale=f"[EXTRACTED — REVIEW] {span}",
                extraction_review_status=EXTRACTION_EXTRACTED,
                review_status=ReviewStatus.DRAFT.value,
                extraction_source="claim_evidence_atoms.extract_atoms_from_row heuristic",
                extraction_date=when,
            )
        )
    return atoms


def build_atoms_for_corpus(
    records: list[ClaimCalibrationRecord],
    *,
    extraction_date: str | None = None,
) -> list[ExtractedAtom]:
    """Extract candidate atoms for every corpus row (all draft, all inert)."""
    atoms: list[ExtractedAtom] = []
    for r in records:
        atoms.extend(extract_atoms_from_row(r, extraction_date=extraction_date))
    return atoms


# ---------------------------------------------------------------------------
# Atom worksheet loader / writer
# ---------------------------------------------------------------------------


def atom_from_row(row: dict[str, str]) -> ExtractedAtom:
    """Build a typed atom from one schema-shaped dict row."""
    return ExtractedAtom(**{col: (row.get(col, "") or "").strip() for col in ATOM_COLUMNS})


def load_atoms(path: Path = DEFAULT_ATOMS_CSV) -> list[ExtractedAtom]:
    """Load all atom rows (any review status). Missing file => empty list."""
    p = Path(path)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as handle:
        return [atom_from_row(r) for r in csv.DictReader(handle)]


def write_atoms(atoms: list[ExtractedAtom], out_csv: Path = DEFAULT_ATOMS_CSV) -> Path:
    """Write atom rows to CSV in schema order."""
    out = Path(out_csv)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ATOM_COLUMNS))
        writer.writeheader()
        writer.writerows(a.as_row() for a in atoms)
    return out


def validate_atoms(atoms: list[ExtractedAtom]) -> list[str]:
    """Return human-readable validation problems (empty => clean)."""
    problems: list[str] = []
    valid_claims = {c.value for c in ClaimType}
    valid_tiers = {t.value for t in EvidenceTier}
    valid_review = {s.value for s in ReviewStatus}
    valid_obs = {o.value for o in ObservationBasis}
    for i, a in enumerate(atoms):
        where = f"atom {i} ({a.atom_id or '?'})"
        if not a.program_id:
            problems.append(f"{where}: missing program_id")
        if not a.evidence_span:
            problems.append(f"{where}: empty evidence_span")
        if a.claim_type and a.claim_type not in valid_claims:
            problems.append(f"{where}: unknown claim_type '{a.claim_type}'")
        if a.tier and a.tier not in valid_tiers:
            problems.append(f"{where}: invalid tier '{a.tier}'")
        if a.review_status and a.review_status not in valid_review:
            problems.append(f"{where}: invalid review_status '{a.review_status}'")
        if a.extraction_review_status.lower() not in ALLOWED_EXTRACTION_STATUSES:
            problems.append(
                f"{where}: invalid extraction_review_status '{a.extraction_review_status}'"
            )
        if a.observed_vs_inferred and a.observed_vs_inferred not in valid_obs:
            problems.append(f"{where}: invalid observed_vs_inferred '{a.observed_vs_inferred}'")
        try:
            lr = float(a.likelihood_ratio)
            if lr <= 0.0:
                problems.append(f"{where}: likelihood_ratio must be > 0")
        except (TypeError, ValueError):
            problems.append(f"{where}: non-numeric likelihood_ratio '{a.likelihood_ratio}'")
    return problems


# ---------------------------------------------------------------------------
# Bridge to the claim ledger — atom row -> ClaimEvidenceAtom (materiality-safe)
# ---------------------------------------------------------------------------


def _enum_or(value: str, enum_cls, default):
    try:
        return enum_cls(value.strip().lower())
    except (ValueError, AttributeError):
        return default


def to_claim_atom(atom: ExtractedAtom) -> ClaimEvidenceAtom:
    """Convert a worksheet atom into a ledger :class:`ClaimEvidenceAtom`.

    Safety rail: if the *extraction* is not approved, the provenance ``review_status`` is
    forced to DRAFT regardless of what the row claims — an unreviewed extraction can never
    produce a material (POS-moving) atom, even if someone typed ``approved`` in the
    review_status column.
    """
    review = _enum_or(atom.review_status, ReviewStatus, ReviewStatus.DRAFT)
    if not atom.is_extraction_approved:
        review = ReviewStatus.DRAFT

    try:
        lr = float(atom.likelihood_ratio)
    except (TypeError, ValueError):
        lr = 1.0

    return make_claim_atom(
        _enum_or(atom.claim_type, ClaimType, ClaimType.THERAPEUTIC_WINDOW),
        likelihood_ratio=lr,
        tier=_enum_or(atom.tier, EvidenceTier, EvidenceTier.LOW),
        rationale=atom.rationale,
        source_id=atom.source_id or f"{atom.program_id}:evidence",
        review_status=review,
        observed_vs_inferred=_enum_or(
            atom.observed_vs_inferred, ObservationBasis, ObservationBasis.INFERRED
        ),
        population_match=_enum_or(atom.population_match, MatchStatus, MatchStatus.UNKNOWN),
        source_type=atom.source_type,
    )


def build_science_claim(
    program_id: str,
    claim_type: ClaimType,
    atoms: list[ExtractedAtom],
    *,
    prior: float = 0.5,
    question: str = "",
    baseline_openness: float = 1.0,
) -> ScienceClaim:
    """Assemble a :class:`ScienceClaim` for one program+claim family from its atoms.

    Only the atoms matching ``program_id`` and ``claim_type`` are included; each is passed
    through :func:`to_claim_atom` (which enforces the extraction-approval safety rail).
    """
    selected = [
        to_claim_atom(a)
        for a in atoms
        if a.program_id == program_id and a.claim_type == claim_type.value
    ]
    return ScienceClaim(
        claim_type=claim_type,
        question=question or claim_type.value,
        prior=prior,
        atoms=selected,
        baseline_openness=baseline_openness,
    )


# ---------------------------------------------------------------------------
# Extraction coverage summary (diagnostic)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractionSummary:
    """Diagnostic counts over an atom worksheet. Never a calibration authorization."""

    n_atoms: int
    n_programs: int
    n_extraction_approved: int
    n_material_capable: int  # extraction-approved AND provenance-approved
    affects_live_pos: bool = False
    notes: list[str] = field(default_factory=list)


def summarize_atoms(atoms: list[ExtractedAtom]) -> ExtractionSummary:
    """Summarize an atom worksheet: how many are extracted vs review-approved."""
    programs = {a.program_id for a in atoms if a.program_id}
    n_extr_appr = sum(1 for a in atoms if a.is_extraction_approved)
    n_material = sum(
        1
        for a in atoms
        if a.is_extraction_approved and a.review_status.strip().lower() == ReviewStatus.APPROVED.value
    )
    notes = [
        "extraction is a review scaffold — draft atoms are inert and never move POS",
    ]
    if n_material == 0:
        notes.append("no extraction-approved + review-approved atoms yet; nothing is material")
    return ExtractionSummary(
        n_atoms=len(atoms),
        n_programs=len(programs),
        n_extraction_approved=n_extr_appr,
        n_material_capable=n_material,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evidence-atom extraction scaffold. 'extract' turns corpus evidence prose into "
            "conservative draft atoms for review; 'summary' reports extraction/review "
            "coverage. Extracted atoms are inert (LOW/inferred/draft/LR=1.0) until reviewed."
        )
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    ext = sub.add_parser("extract", help="extract draft atoms from the calibration corpus")
    ext.add_argument("--corpus", default=None, help="corpus CSV (default: repo corpus)")
    ext.add_argument("--out", default=str(DEFAULT_ATOMS_CSV))

    summ = sub.add_parser("summary", help="extraction/review coverage over an atom worksheet")
    summ.add_argument("--atoms", default=str(DEFAULT_ATOMS_CSV))

    args = parser.parse_args()

    if args.cmd == "extract":
        records = load_corpus(Path(args.corpus)) if args.corpus else load_corpus()
        atoms = build_atoms_for_corpus(records)
        problems = validate_atoms(atoms)
        out = write_atoms(atoms, Path(args.out))
        print(f"Extracted {len(atoms)} draft atoms from {len(records)} corpus rows -> {out}")
        print("  ALL atoms: tier=low, inferred, review_status=draft, LR=1.0 (inert).")
        print("  Reviewer sets tier/LR/observed + extraction_review_status=approved to make material.")
        if problems:
            print(f"  VALIDATION: {len(problems)} problem(s):")
            for p in problems[:20]:
                print(f"    - {p}")
        else:
            print("  validation: clean")
    elif args.cmd == "summary":
        atoms = load_atoms(Path(args.atoms))
        s = summarize_atoms(atoms)
        print(
            f"atoms={s.n_atoms} programs={s.n_programs} "
            f"extraction_approved={s.n_extraction_approved} "
            f"material_capable={s.n_material_capable} affects_live_pos={s.affects_live_pos}"
        )
        for note in s.notes:
            print(f"  note: {note}")


if __name__ == "__main__":
    main()
