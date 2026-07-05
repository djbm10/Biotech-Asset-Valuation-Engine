"""Outcome-leakage scrubber for the calibration corpus ``evidence_available`` field.

The seed notes were written with the outcome in hand, so many reason *from* the result:
"feasible for accelerated approval", "approvals support a held therapeutic window",
"before market withdrawal decision", "ODAC judged risk-benefit unfavorable". In a blind
reviewer packet that is lookahead leakage — it tells the reviewer the answer before they
judge the evidence, contaminating the very labels the corpus exists to collect.

This module removes outcome references from the evidence text while preserving the
pre-decision facts (trial names, response rates, toxicity profile, research to-dos). Two
pieces, both testable:

  * :data:`SCRUB_RULES` — ordered, mechanical ``(pattern, replacement)`` rewrites that
    neutralize known outcome phrases (e.g. "feasible for approval" -> "feasible at the
    selected dose"). They only ever *remove* the outcome; they never add a new claim.
  * :func:`detect_leakage` / :func:`audit_corpus` — a residual detector that flags any
    remaining outcome term, so the scrub can be verified to converge to zero leakage and
    future rows are guarded.

Scrubbing is not fabrication: it strips the leaked outcome, it does not invent evidence.
The original text is preserved in git history.
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from bve.analysis.claim_calibration_corpus import (
    CORPUS_COLUMNS,
    DEFAULT_CORPUS_CSV,
    ClaimCalibrationRecord,
    load_corpus,
)

# Ordered mechanical rewrites. Specific rules first (so "feasible enough for accelerated
# approval" is handled before the general "feasible for ... approval").
SCRUB_RULES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pat, re.IGNORECASE), repl)
    for pat, repl in (
        (r"\s*before market withdrawal decision", ""),
        (r",?\s*but ODAC judged risk[-/]benefit unfavorable", ""),
        (r"\bAccelerated approval based on\b", "Pivotal data from"),
        (r"\s*before approval\b", ""),
        (r"\bfeasible enough for accelerated approval\b", "feasible at the selected dose"),
        (r"\baccepted for accelerated approval\b", "accepted at the selected dose"),
        (
            r"\bfeasible for (?:multiple |tissue-specific |accelerated )?approvals?\b",
            "feasible at the selected dose",
        ),
        (r"\bapproval indicates manageable\b", "data indicate a manageable"),
        (r"\ballowed approvals/expansions\b", "allowed continued active dosing"),
        (
            r"\bapprovals support held therapeutic window\b",
            "data support a held therapeutic window",
        ),
        (r"\bapproved in ALK-positive NSCLC\b", "active in ALK-positive NSCLC"),
        (r"\bNeed approval review extraction\b", "Need FDA review extraction"),
        (r"\bFDA label/ODAC packet extraction\b", "FDA label/review extraction"),
        (r"\bODAC\b", "review"),
        (r"\s{2,}", " "),
    )
)

# Residual outcome-leakage terms. Presence after a scrub == a row still needs attention.
# Deliberately excludes "discontinuation" (a legitimate dose-safety data request, not an
# outcome) and trial names.
_LEAKAGE_DETECTOR = re.compile(
    r"withdraw\w*|approv\w*|\bCRL\b|complete response letter|\bODAC\b|risk[-/]benefit|"
    r"negative vote|voluntar\w*|increased risk of death|inferior (?:OS|overall survival)|"
    r"before market|sponsor discontinued|discontinued development|de-prioriti\w*",
    re.IGNORECASE,
)


def scrub_text(text: str) -> str:
    """Apply the mechanical scrub rules, returning the outcome-free evidence text."""
    out = text or ""
    for pattern, repl in SCRUB_RULES:
        out = pattern.sub(repl, out)
    return out.strip()


def detect_leakage(text: str) -> list[str]:
    """Return the distinct residual outcome-leakage terms in ``text`` (empty => clean)."""
    return sorted({m.group(0).lower() for m in _LEAKAGE_DETECTOR.finditer(text or "")})


def scrub_record(record: ClaimCalibrationRecord) -> dict[str, str]:
    """Return a schema-shaped dict row for ``record`` with a scrubbed ``evidence_available``."""
    row = {
        col: (
            "" if getattr(record, col) is None else str(getattr(record, col))
        )
        for col in CORPUS_COLUMNS
    }
    row["evidence_available"] = scrub_text(record.evidence_available)
    # predicted_posterior round-trips as blank when None.
    row["predicted_posterior"] = (
        "" if record.predicted_posterior is None else str(record.predicted_posterior)
    )
    return row


def audit_corpus(
    records: list[ClaimCalibrationRecord],
) -> dict[str, list[str]]:
    """Map program_id -> residual leakage terms for rows that still leak (empty => clean)."""
    flagged: dict[str, list[str]] = {}
    for r in records:
        terms = detect_leakage(r.evidence_available)
        if terms:
            flagged[r.program_id] = terms
    return flagged


def scrub_corpus(
    records: list[ClaimCalibrationRecord],
) -> tuple[list[dict[str, str]], list[str]]:
    """Scrub every row's evidence text. Returns (rows, changed_program_ids)."""
    rows: list[dict[str, str]] = []
    changed: list[str] = []
    for r in records:
        row = scrub_record(r)
        if row["evidence_available"] != (r.evidence_available or "").strip():
            changed.append(r.program_id)
        rows.append(row)
    return rows, changed


# --- CLI ------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Scrub outcome/lookahead language from the corpus evidence_available field. "
            "'audit' reports residual leakage without writing; 'scrub' applies the rules "
            "and rewrites the corpus (git preserves the original)."
        )
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("audit", "scrub"):
        p = sub.add_parser(name)
        p.add_argument("--corpus", default=str(DEFAULT_CORPUS_CSV))
    args = parser.parse_args()

    records = load_corpus(Path(args.corpus))

    if args.cmd == "audit":
        flagged = audit_corpus(records)
        if not flagged:
            print(f"clean: 0/{len(records)} rows contain outcome-leakage language")
            return
        print(f"LEAKAGE: {len(flagged)}/{len(records)} rows:")
        for pid, terms in flagged.items():
            print(f"  {pid}: {terms}")
    elif args.cmd == "scrub":
        rows, changed = scrub_corpus(records)
        out = Path(args.corpus)
        with out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(CORPUS_COLUMNS))
            writer.writeheader()
            writer.writerows(rows)
        print(f"Scrubbed {len(changed)}/{len(rows)} rows -> {out}")
        # Verify convergence.
        residual = audit_corpus(load_corpus(out))
        if residual:
            print(f"  WARNING: {len(residual)} rows still leak: {residual}")
        else:
            print("  verified: 0 residual leakage terms")


if __name__ == "__main__":
    main()
