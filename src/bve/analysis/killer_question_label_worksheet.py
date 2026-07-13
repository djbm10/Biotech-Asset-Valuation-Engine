"""Seed-labeling worksheet generator for the killer-question ground truth.

Step 2 of the Idea 20 path needs the labeled corpus to grow (more archetypes
actually decisive, esp. DOSE_ADEQUACY / DELIVERY_EXPOSURE, plus non-dominant
cases for M3). Producing *clean* labels is domain-review research and cannot be
automated. What this module does is **accelerate** that research: it pulls
resolved programs from `phase_transitions.csv`, pre-fills the mechanically
derivable fields, and proposes a decisive archetype + competitors from a
transparent heuristic over the existing signal columns.

Every proposal is a **seed for review, never a clean label**. The worksheet is
written to its own staging file with `label_status="seed_review"` — a status the
backtest scorer does not count (only `clean` enters the M1 headline) and the
ground-truth loader does not accept — so seeds can never pollute a metric until a
human promotes a reviewed row into `killer_question_ground_truth.csv`.

The heuristic is intentionally simple and auditable; the `_seed_rationale` column
records exactly which signals fired so review is fast.
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

DEFAULT_POOL_CSV = Path("research/data/phase_transitions.csv")
DEFAULT_GROUND_TRUTH_CSV = Path("research/data/killer_question_ground_truth.csv")
DEFAULT_WORKSHEET_CSV = Path("research/data/killer_question_label_worksheet.csv")

# Status marker for un-reviewed seed rows. Deliberately NOT one of the
# loader's accepted values ("clean"/"subjective"/"excluded"), so a seed row
# cannot be loaded as ground truth by accident.
SEED_STATUS = "seed_review"

# Ground-truth schema columns, in order, so a reviewed row promotes by copy.
GROUND_TRUTH_COLUMNS = (
    "program_id",
    "decision_date",
    "outcome",
    "decisive_archetype",
    "label_status",
    "decisive_confidence",
    "why_this_archetype_decided",
    "label_source",
    "label_date",
    "pivotal_evidence_event",
    "pivotal_evidence_date",
    "single_question_dominant",
    "competing_archetypes",
)
# Extra helper columns (``_``-prefixed) carry the review aids; drop them on promote.
HELPER_COLUMNS = ("_seed_rationale", "_pool_signals")


# ---------------------------------------------------------------------------
# Heuristic: signal columns -> archetype evidence points
# ---------------------------------------------------------------------------

# Each rule adds points to an archetype. Highest total is the proposed decisive
# question; archetypes within ONE point of the top become competitors. These are
# starting points for human review, not calibrated weights.
_SAFETY_POINTS = {"serious": 3, "concerning": 2, "manageable": 1}
_COMPETITION_POINTS = {"high": 3, "moderate": 1}
_MOA_POINTS = {"novel": 2, "partial": 1}

_NOTE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("DOSE_ADEQUACY", r"exposure|pharmacokinet|\bpk\b|dose[- ]limiting|limits dosing|dose intensity|dose reduction|narrow therapeutic|underdos|target engagement"),
    ("DELIVERY_EXPOSURE", r"penetrat|delivery|biodistribut|blood[- ]brain|\bbbb\b|tissue"),
    ("TOLERABILITY_CEILING", r"toxic|death|mortalit|safety|adverse|colitis|effusion|pneumonitis"),
    ("DIFFERENTIATION", r"differentiat|versus|crowded|superiority|me[- ]too|failed to beat|no benefit over"),
    ("TARGET_VALIDITY", r"unselected|antigen|target|validation|biology|futility"),
)
_NOTE_POINTS = 2
_NOTE_POINTS_STRONG = 3  # DOSE / DELIVERY keywords are explicit and rare — weight them up

# Deterministic tie-break: on equal points the archetype earliest here wins,
# matching the picker's own candidate build order so seeds are reproducible.
_TIE_ORDER = (
    "TARGET_VALIDITY",
    "DELIVERY_EXPOSURE",
    "DOSE_ADEQUACY",
    "DIFFERENTIATION",
    "TOLERABILITY_CEILING",
    "NOVEL_OR_UNMODELED_RISK",
)


@dataclass(frozen=True)
class ArchetypeProposal:
    """A reviewable seed proposal for one program."""

    decisive: str
    competing: tuple[str, ...]
    single_dominant: bool
    confidence: str  # "high" | "medium" | "low"
    rationale: str
    scores: dict[str, int] = field(default_factory=dict)


def _score_signals(row: dict[str, str]) -> tuple[dict[str, int], list[str]]:
    """Accumulate archetype evidence points from one pool row's signals."""
    scores: dict[str, int] = {}
    fired: list[str] = []

    def add(arch: str, pts: int, why: str) -> None:
        if pts <= 0:
            return
        scores[arch] = scores.get(arch, 0) + pts
        fired.append(f"{why}(+{pts}->{arch})")

    safety = row.get("safety_profile", "").strip().lower()
    add("TOLERABILITY_CEILING", _SAFETY_POINTS.get(safety, 0), f"safety={safety}")

    comp = row.get("competitive_pressure", "").strip().lower()
    add("DIFFERENTIATION", _COMPETITION_POINTS.get(comp, 0), f"competition={comp}")

    moa = row.get("moa_precedent", "").strip().lower()
    add("TARGET_VALIDITY", _MOA_POINTS.get(moa, 0), f"moa={moa}")

    if row.get("biomarker_enriched", "").strip().lower() == "false":
        add("TARGET_VALIDITY", 1, "unselected(biomarker_enriched=false)")
    if row.get("endpoint_type", "").strip().lower() == "biomarker_only":
        add("TARGET_VALIDITY", 1, "endpoint=biomarker_only")

    notes = row.get("notes", "").lower()
    for arch, pattern in _NOTE_PATTERNS:
        if re.search(pattern, notes):
            pts = _NOTE_POINTS_STRONG if arch in ("DOSE_ADEQUACY", "DELIVERY_EXPOSURE") else _NOTE_POINTS
            add(arch, pts, f"notes~{arch.lower()}")

    return scores, fired


def propose_archetypes(row: dict[str, str]) -> ArchetypeProposal:
    """Propose a decisive archetype + competitors from a pool row's signals.

    Deterministic: on a points tie the archetype earliest in ``_TIE_ORDER`` wins,
    matching the picker's own build order so seeds are reproducible.
    """
    scores, fired = _score_signals(row)
    if not scores:
        return ArchetypeProposal(
            decisive="TARGET_VALIDITY",
            competing=(),
            single_dominant=False,
            confidence="low",
            rationale="no signals fired; defaulted to TARGET_VALIDITY — REVIEW",
            scores={},
        )

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], _TIE_ORDER.index(kv[0])))
    decisive, top = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    competing = tuple(a for a, s in ranked[1:] if s >= top - 1 and s > 0)[:2]
    single_dominant = (top - second) >= 2
    if top >= 3 and single_dominant:
        confidence = "high"
    elif top >= 2:
        confidence = "medium"
    else:
        confidence = "low"
    rationale = "; ".join(fired) + f" | top={decisive}({top}) second={second} dominant={single_dominant}"
    return ArchetypeProposal(
        decisive=decisive,
        competing=competing,
        single_dominant=single_dominant,
        confidence=confidence,
        rationale=rationale,
        scores=scores,
    )


# ---------------------------------------------------------------------------
# Worksheet build
# ---------------------------------------------------------------------------

def _existing_program_ids(ground_truth_csv: Path) -> set[str]:
    if not Path(ground_truth_csv).exists():
        return set()
    with Path(ground_truth_csv).open(newline="", encoding="utf-8") as handle:
        return {row["program_id"].strip().lower() for row in csv.DictReader(handle)}


def build_worksheet_rows(
    pool_csv: Path = DEFAULT_POOL_CSV,
    ground_truth_csv: Path = DEFAULT_GROUND_TRUTH_CSV,
    *,
    outcomes: tuple[str, ...] = ("failed",),
) -> list[dict[str, str]]:
    """Build seed worksheet rows for pool programs not already labeled.

    Only programs whose ``outcome`` is in ``outcomes`` (default: failures, where
    a decisive-failure archetype is most defensible) and that are absent from the
    ground truth are included.
    """
    already = _existing_program_ids(ground_truth_csv)
    label_date = date.today().isoformat()
    rows: list[dict[str, str]] = []
    with Path(pool_csv).open(newline="", encoding="utf-8") as handle:
        for pool in csv.DictReader(handle):
            drug = pool["drug"].strip()
            if not drug or drug.lower() in already:
                continue
            if pool["outcome"].strip().lower() not in outcomes:
                continue
            year = pool["year"].strip()
            phase = pool["phase_start"].strip() or "phase_3"
            proposal = propose_archetypes(pool)
            rows.append(
                {
                    "program_id": drug,
                    "decision_date": f"{year}-01-01",
                    "outcome": pool["outcome"].strip(),
                    "decisive_archetype": proposal.decisive,
                    "label_status": SEED_STATUS,
                    "decisive_confidence": proposal.confidence,
                    "why_this_archetype_decided": f"[SEED — REVIEW] {pool.get('notes', '').strip()}",
                    "label_source": "phase_transitions.csv heuristic seed (REVIEW REQUIRED)",
                    "label_date": label_date,
                    "pivotal_evidence_event": f"{phase} readout ({pool.get('indication', '').strip()})",
                    "pivotal_evidence_date": f"{year}-12-31",
                    "single_question_dominant": "true" if proposal.single_dominant else "false",
                    "competing_archetypes": ",".join(proposal.competing),
                    "_seed_rationale": proposal.rationale,
                    "_pool_signals": (
                        f"phase={phase};moa={pool.get('moa_precedent','').strip()};"
                        f"biomarker={pool.get('biomarker_enriched','').strip()};"
                        f"safety={pool.get('safety_profile','').strip()};"
                        f"competition={pool.get('competitive_pressure','').strip()};"
                        f"endpoint={pool.get('endpoint_type','').strip()}"
                    ),
                }
            )
    return rows


def write_worksheet(
    rows: list[dict[str, str]],
    out_csv: Path = DEFAULT_WORKSHEET_CSV,
) -> Path:
    """Write worksheet rows to a staging CSV (ground-truth columns + helpers)."""
    out = Path(out_csv)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*GROUND_TRUTH_COLUMNS, *HELPER_COLUMNS])
        writer.writeheader()
        writer.writerows(rows)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a seed-labeling worksheet from phase_transitions.csv for "
            "killer-question ground-truth expansion. Seeds are proposals for "
            "human/domain review — never clean labels."
        )
    )
    parser.add_argument("--pool", default=str(DEFAULT_POOL_CSV))
    parser.add_argument("--ground-truth", default=str(DEFAULT_GROUND_TRUTH_CSV))
    parser.add_argument("--out", default=str(DEFAULT_WORKSHEET_CSV))
    parser.add_argument(
        "--outcomes",
        default="failed",
        help="Comma-separated pool outcomes to include (default: failed).",
    )
    args = parser.parse_args()
    outcomes = tuple(o.strip().lower() for o in args.outcomes.split(",") if o.strip())
    rows = build_worksheet_rows(
        Path(args.pool), Path(args.ground_truth), outcomes=outcomes
    )
    out = write_worksheet(rows, Path(args.out))

    from collections import Counter

    by_arch = Counter(r["decisive_archetype"] for r in rows)
    by_conf = Counter(r["decisive_confidence"] for r in rows)
    n_nondominant = sum(1 for r in rows if r["single_question_dominant"] == "false")
    print(f"Wrote {len(rows)} seed rows -> {out}")
    print(f"  proposed decisive archetype: {dict(by_arch)}")
    print(f"  confidence mix: {dict(by_conf)}")
    print(f"  non-dominant (M3 candidate) seeds: {n_nondominant}")
    print("  ALL rows are label_status=seed_review — review before promoting to ground truth.")


if __name__ == "__main__":
    main()
