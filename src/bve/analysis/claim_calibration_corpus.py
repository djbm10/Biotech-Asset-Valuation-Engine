"""Claim calibration corpus — schema, strict loader, worksheet generator (Phase 8).

Phase 8 of the POS Claim-Ledger Build Plan is the hard, net-new *data* work: a corpus
of 30-50 historical programs, each with the evidence available at a decision point, the
later outcome, and a **human-reviewed** claim label. Producing clean labels is domain
research and cannot be automated — the plan is explicit that a bad evidence base makes a
well-engineered model confidently wrong, so the corpus sets the pace, not the calendar.

What this module does, mirroring the killer-question label-worksheet convention already
in the repo:

  * defines the corpus **schema** (:data:`CORPUS_COLUMNS`) and a typed row;
  * ships a strict **loader** whose calibrated view accepts ONLY ``review_status ==
    approved`` rows — draft/reviewed seeds can never enter a calibration metric by
    accident (the mirror of the ground-truth loader's ``clean``-only rule);
  * **accelerates** the human work with a worksheet generator that seeds the exposure/
    toxicity oncology wedge from ``phase_transitions.csv``, pre-fills the mechanically
    derivable fields, proposes a claim family from transparent keyword heuristics, and
    marks every row ``draft`` with source links left as REVIEW-REQUIRED;
  * provides an **inert-until-approved** calibration report (Phase 9A shape) that returns
    ``n=0`` / ``uncalibrated`` while no approved rows exist — so the NO LIVE POS GATE is
    never silently crossed.

Strictly shadow: nothing here imports or writes the live POS path.
"""
from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from bve.intelligence.claim_ledger import ClaimType

DEFAULT_POOL_CSV = Path("research/data/phase_transitions.csv")
DEFAULT_CORPUS_CSV = Path("research/data/claim_calibration_corpus.csv")

# Corpus schema, in order (Phase 8 field list). A reviewed row is edited in place;
# promotion to "approved" is a human action, never automated here.
CORPUS_COLUMNS = (
    "program_id",
    "target",
    "indication",
    "modality",
    "phase",
    "decision_date",           # date the evidence below was available
    "claim_type",              # which ClaimType this row labels
    "claim_question",
    "evidence_available",      # what was known at decision_date
    "predicted_posterior",     # optional model prediction for calibration (blank = none)
    "claim_held",              # ground truth for the claim: true|false|unknown
    "program_outcome",         # later program outcome: approved|failed|ongoing
    "failure_success_reason",
    "source_links",
    "review_status",           # draft|reviewed|approved (only approved calibrates)
    "label_source",
    "label_date",
)

# Review statuses, in ascending trust. Only APPROVED may enter a calibration metric.
REVIEW_DRAFT = "draft"
REVIEW_REVIEWED = "reviewed"
REVIEW_APPROVED = "approved"
ALLOWED_REVIEW_STATUSES = frozenset({REVIEW_DRAFT, REVIEW_REVIEWED, REVIEW_APPROVED})
ALLOWED_CLAIM_HELD = frozenset({"true", "false", "unknown"})

# The Phase 1 wedge: this corpus slice only labels exposure/therapeutic-window claims.
_WEDGE_CLAIM_TYPES = frozenset({ClaimType.EXPOSURE_DELIVERY, ClaimType.THERAPEUTIC_WINDOW})


# ---------------------------------------------------------------------------
# Typed row + loader
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClaimCalibrationRecord:
    """One reviewable corpus row. ``predicted_posterior`` / ``claim_held`` may be blank."""

    program_id: str
    target: str
    indication: str
    modality: str
    phase: str
    decision_date: str
    claim_type: str
    claim_question: str
    evidence_available: str
    predicted_posterior: Optional[float]
    claim_held: str
    program_outcome: str
    failure_success_reason: str
    source_links: str
    review_status: str
    label_source: str
    label_date: str

    @property
    def is_approved(self) -> bool:
        return self.review_status.strip().lower() == REVIEW_APPROVED

    @property
    def has_calibration_pair(self) -> bool:
        """Approved, with both a prediction and a resolved binary claim outcome."""
        return (
            self.is_approved
            and self.predicted_posterior is not None
            and self.claim_held.strip().lower() in {"true", "false"}
        )


def _parse_float(raw: str) -> Optional[float]:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def load_corpus(path: Path = DEFAULT_CORPUS_CSV) -> list[ClaimCalibrationRecord]:
    """Load all corpus rows (any review status). Missing file => empty corpus."""
    p = Path(path)
    if not p.exists():
        return []
    records: list[ClaimCalibrationRecord] = []
    with p.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            records.append(
                ClaimCalibrationRecord(
                    program_id=row.get("program_id", "").strip(),
                    target=row.get("target", "").strip(),
                    indication=row.get("indication", "").strip(),
                    modality=row.get("modality", "").strip(),
                    phase=row.get("phase", "").strip(),
                    decision_date=row.get("decision_date", "").strip(),
                    claim_type=row.get("claim_type", "").strip(),
                    claim_question=row.get("claim_question", "").strip(),
                    evidence_available=row.get("evidence_available", "").strip(),
                    predicted_posterior=_parse_float(row.get("predicted_posterior", "")),
                    claim_held=row.get("claim_held", "").strip(),
                    program_outcome=row.get("program_outcome", "").strip(),
                    failure_success_reason=row.get("failure_success_reason", "").strip(),
                    source_links=row.get("source_links", "").strip(),
                    review_status=row.get("review_status", "").strip(),
                    label_source=row.get("label_source", "").strip(),
                    label_date=row.get("label_date", "").strip(),
                )
            )
    return records


def approved_records(records: list[ClaimCalibrationRecord]) -> list[ClaimCalibrationRecord]:
    """The only rows allowed to feed a calibration metric."""
    return [r for r in records if r.is_approved]


def validate_corpus(records: list[ClaimCalibrationRecord]) -> list[str]:
    """Return a list of human-readable validation problems (empty => clean)."""
    problems: list[str] = []
    valid_claim_types = {c.value for c in ClaimType}
    for i, r in enumerate(records):
        where = f"row {i} ({r.program_id or '?'})"
        if not r.program_id:
            problems.append(f"{where}: missing program_id")
        if r.review_status.lower() not in ALLOWED_REVIEW_STATUSES:
            problems.append(f"{where}: invalid review_status '{r.review_status}'")
        if r.claim_type and r.claim_type not in valid_claim_types:
            problems.append(f"{where}: unknown claim_type '{r.claim_type}'")
        if r.claim_held and r.claim_held.lower() not in ALLOWED_CLAIM_HELD:
            problems.append(f"{where}: invalid claim_held '{r.claim_held}'")
        if r.predicted_posterior is not None and not 0.0 <= r.predicted_posterior <= 1.0:
            problems.append(f"{where}: predicted_posterior out of [0,1]")
        # Approved rows must actually be evidence-backed.
        if r.is_approved and not r.source_links:
            problems.append(f"{where}: approved row has no source_links")
    return problems


# ---------------------------------------------------------------------------
# Claim-family proposal (transparent heuristic; a seed for review, never a label)
# ---------------------------------------------------------------------------

# Keyword -> claim family. Therapeutic-window = efficacy dose capped by toxicity;
# exposure-delivery = drug can't reach/sustain target exposure. Explicitly the two
# families of the Phase 1 wedge.
_WINDOW_PATTERN = re.compile(
    r"toxic|dose[- ]limit|limits dosing|thrombocyto|effusion|colitis|pneumonitis|"
    r"neutropen|hepatotox|narrow therapeutic|dose reduction|dlts?\b|adverse",
    re.IGNORECASE,
)
_EXPOSURE_PATTERN = re.compile(
    r"penetrat|delivery|biodistribut|blood[- ]brain|\bbbb\b|exposure|pharmacokinet|"
    r"\bpk\b|half[- ]life|target engagement|underdos",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClaimTypeProposal:
    claim_type: Optional[ClaimType]
    confidence: str  # high | medium | low
    rationale: str


def propose_claim_type(pool_row: dict[str, str]) -> ClaimTypeProposal:
    """Propose an exposure/window claim family from a pool row's notes + safety."""
    notes = pool_row.get("notes", "") or ""
    safety = (pool_row.get("safety_profile", "") or "").strip().lower()
    window_hit = bool(_WINDOW_PATTERN.search(notes)) or safety in {"serious", "concerning"}
    exposure_hit = bool(_EXPOSURE_PATTERN.search(notes))

    if exposure_hit and not window_hit:
        return ClaimTypeProposal(
            ClaimType.EXPOSURE_DELIVERY, "medium", f"exposure/delivery keyword in notes: {notes!r}"
        )
    if window_hit:
        conf = "high" if _WINDOW_PATTERN.search(notes) and safety in {"serious", "concerning"} else "medium"
        return ClaimTypeProposal(
            ClaimType.THERAPEUTIC_WINDOW,
            conf,
            f"toxicity/dose-limiting signal (safety={safety}) in notes: {notes!r}",
        )
    return ClaimTypeProposal(None, "low", "no exposure/window signal — not in this wedge")


# ---------------------------------------------------------------------------
# Worksheet generator — seed the corpus from the pool (all rows draft)
# ---------------------------------------------------------------------------


def build_seed_rows(
    pool_csv: Path = DEFAULT_POOL_CSV,
    *,
    outcomes: tuple[str, ...] = ("failed",),
) -> list[dict[str, str]]:
    """Seed draft corpus rows for exposure/window failures in the pool.

    Only programs whose ``outcome`` is in ``outcomes`` and whose notes/safety show an
    exposure- or toxicity-driven signal are seeded. Every row is ``review_status=draft``
    with ``source_links`` and ``claim_held`` left for a human — these are research
    starting points, not labels.
    """
    label_date = date.today().isoformat()
    rows: list[dict[str, str]] = []
    with Path(pool_csv).open(newline="", encoding="utf-8") as handle:
        for pool in csv.DictReader(handle):
            if (pool.get("outcome", "").strip().lower()) not in outcomes:
                continue
            proposal = propose_claim_type(pool)
            if proposal.claim_type is None:
                continue  # outside the exposure/window wedge
            drug = pool.get("drug", "").strip()
            year = pool.get("year", "").strip()
            rows.append(
                {
                    "program_id": drug,
                    "target": "[REVIEW]",  # not mechanically derivable from the pool
                    "indication": pool.get("indication", "").strip(),
                    "modality": "[REVIEW]",
                    "phase": pool.get("phase_start", "").strip() or "phase_3",
                    "decision_date": f"{year}-01-01" if year else "",
                    "claim_type": proposal.claim_type.value,
                    "claim_question": _claim_question(proposal.claim_type),
                    "evidence_available": f"[SEED — REVIEW] {pool.get('notes', '').strip()}",
                    "predicted_posterior": "",
                    "claim_held": "unknown",
                    "program_outcome": pool.get("outcome", "").strip(),
                    "failure_success_reason": pool.get("notes", "").strip(),
                    "source_links": "REVIEW REQUIRED",
                    "review_status": REVIEW_DRAFT,
                    "label_source": f"phase_transitions.csv heuristic seed ({proposal.confidence} conf) — REVIEW",
                    "label_date": label_date,
                }
            )
    return rows


def _claim_question(claim_type: ClaimType) -> str:
    return {
        ClaimType.EXPOSURE_DELIVERY: "Did the drug reach and sustain adequate target exposure?",
        ClaimType.THERAPEUTIC_WINDOW: "Was the efficacious dose achievable below the toxicity ceiling?",
    }.get(claim_type, claim_type.value)


def write_corpus(rows: list[dict[str, str]], out_csv: Path = DEFAULT_CORPUS_CSV) -> Path:
    """Write corpus rows to CSV in schema order."""
    out = Path(out_csv)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CORPUS_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    return out


# ---------------------------------------------------------------------------
# Calibration report (Phase 9A shape) — inert until approved rows exist
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClaimCalibrationReport:
    """Diagnostic calibration over approved corpus rows. Inert while n_pairs == 0."""

    status: str  # "uncalibrated" | "diagnostic"
    n_approved: int
    n_pairs: int  # approved rows with both a prediction and a binary outcome
    brier: Optional[float]
    base_rate: Optional[float]
    mean_prediction: Optional[float]
    #: Restates the gate: a diagnostic report never authorizes a live-POS change.
    affects_live_pos: bool = False
    notes: list[str] = field(default_factory=list)


def calibration_report(
    records: list[ClaimCalibrationRecord],
    *,
    predictor: Optional[Callable[[ClaimCalibrationRecord], float]] = None,
) -> ClaimCalibrationReport:
    """Compute a diagnostic calibration report over approved corpus rows.

    A prediction comes from the row's ``predicted_posterior`` or, if given, from
    ``predictor`` (e.g. a claim-ledger posterior). With no approved calibration pairs
    the report is ``uncalibrated`` (n=0) — the honest state until the corpus is built
    and reviewed.
    """
    approved = approved_records(records)
    pairs: list[tuple[float, int]] = []
    for r in approved:
        held = r.claim_held.strip().lower()
        if held not in {"true", "false"}:
            continue
        pred = r.predicted_posterior if predictor is None else predictor(r)
        if pred is None:
            continue
        pairs.append((float(pred), 1 if held == "true" else 0))

    if not pairs:
        return ClaimCalibrationReport(
            status="uncalibrated",
            n_approved=len(approved),
            n_pairs=0,
            brier=None,
            base_rate=None,
            mean_prediction=None,
            notes=[
                "no approved calibration pairs yet — corpus not built/reviewed; "
                "NO LIVE POS GATE remains closed"
            ],
        )

    brier = sum((p - y) ** 2 for p, y in pairs) / len(pairs)
    base_rate = sum(y for _, y in pairs) / len(pairs)
    mean_pred = sum(p for p, _ in pairs) / len(pairs)
    return ClaimCalibrationReport(
        status="diagnostic",
        n_approved=len(approved),
        n_pairs=len(pairs),
        brier=round(brier, 4),
        base_rate=round(base_rate, 4),
        mean_prediction=round(mean_pred, 4),
        notes=["diagnostic only — shadow calibration, not a live-POS authorization"],
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Claim calibration corpus tools. 'seed' generates a draft worksheet for the "
            "exposure/therapeutic-window oncology wedge from phase_transitions.csv; "
            "'report' prints a diagnostic calibration report (inert until rows are approved)."
        )
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    seed = sub.add_parser("seed", help="generate a draft corpus worksheet")
    seed.add_argument("--pool", default=str(DEFAULT_POOL_CSV))
    seed.add_argument("--out", default=str(DEFAULT_CORPUS_CSV))
    seed.add_argument("--outcomes", default="failed")

    rep = sub.add_parser("report", help="diagnostic calibration report over the corpus")
    rep.add_argument("--corpus", default=str(DEFAULT_CORPUS_CSV))

    args = parser.parse_args()

    if args.cmd == "seed":
        outcomes = tuple(o.strip().lower() for o in args.outcomes.split(",") if o.strip())
        rows = build_seed_rows(Path(args.pool), outcomes=outcomes)
        out = write_corpus(rows, Path(args.out))
        from collections import Counter

        by_type = Counter(r["claim_type"] for r in rows)
        print(f"Wrote {len(rows)} draft corpus rows -> {out}")
        print(f"  proposed claim family: {dict(by_type)}")
        print("  ALL rows are review_status=draft with source_links=REVIEW REQUIRED.")
        print("  Fill target/modality/source_links/claim_held, then set review_status=approved.")
    elif args.cmd == "report":
        records = load_corpus(Path(args.corpus))
        problems = validate_corpus(records)
        if problems:
            print(f"VALIDATION ({len(problems)} problems):")
            for p in problems[:20]:
                print(f"  - {p}")
        report = calibration_report(records)
        print(
            f"status={report.status} n_approved={report.n_approved} n_pairs={report.n_pairs} "
            f"brier={report.brier} base_rate={report.base_rate} affects_live_pos={report.affects_live_pos}"
        )
        for note in report.notes:
            print(f"  note: {note}")


if __name__ == "__main__":
    main()
