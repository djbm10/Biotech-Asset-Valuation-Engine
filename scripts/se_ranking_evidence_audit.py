"""Audit what a run's records can actually support as a shortlist ordering.

Usage::

    PYTHONPATH=src BVE_SE_ONTOLOGY_SNAPSHOT=data/se/ontology/current \
      python3 scripts/se_ranking_evidence_audit.py <run_dir> [<run_dir> ...]

Read-only, and deliberately rule-free: every number comes from a record the pipeline wrote
(``gate_evaluations``, ``facts``, ``candidates``, ``low_support_asset_ids``, the manifest).
Nothing here re-derives a gate, a class term or a support decision, because hand-rolled
probes of implemented rules produced wrong numbers twice in the identity arc. The population
reported is the one a BD user sees first: the default path (not excluded, not low support).
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from bve.se.pipeline import SESearchResult
from bve.se.reporting.shortlist import build_shortlist


def _pct(n: int, d: int) -> str:
    return f"{n:>5} / {d:<5} ({100 * n / d:5.1f}%)" if d else f"{n:>5} / 0"


def audit(directory: Path) -> None:
    raw = json.loads((directory / "result.json").read_text())
    excluded = set(raw["excluded_asset_ids"])
    low = set(raw["low_support_asset_ids"] or ())
    candidates = raw["candidates"]
    default = [c for c in candidates if c["asset_id"] not in excluded | low]
    ids = {c["asset_id"] for c in default}
    n = len(default)

    print(f"\n=== {directory.name}")
    manifest = raw["run_manifest"]
    print(f"status {manifest['status']}   candidates {len(candidates)}   default path {n}"
          f"   excluded {len(excluded)}   low support {len(low)}")
    print(f"eligible {len(raw['eligible_asset_ids'])}   unresolved {len(raw['unresolved_asset_ids'])}"
          f"   ranking.ranked {len(raw['ranking']['ranked'])}"
          f"   clinical_results {len(raw['clinical_results'])}"
          f"   cohort_assignments {len(raw['cohort_assignments'])}"
          f"   clinical_meaningfulness {len(raw['clinical_meaningfulness'])}")

    print("\n-- gate status on the default path (every asset has one decision per requirement)")
    by_gate: dict[str, Counter] = defaultdict(Counter)
    for evaluation in raw["gate_evaluations"]:
        if evaluation["subject_id"] not in ids:
            continue
        for decision in evaluation["decisions"]:
            by_gate[f"{decision['gate_id']}/{decision['requirement_id']}"][decision["status"]] += 1
    for gate, counts in sorted(by_gate.items()):
        print(f"  {gate:55} PASS {counts['PASS']:>5}  FAIL {counts['FAIL']:>5}"
              f"  UNKNOWN {counts['UNKNOWN']:>5}")

    print("\n-- facts present per default-path asset (at least one fact of the type)")
    have: dict[str, set] = defaultdict(set)
    for fact in raw["facts"]:
        if fact.get("subject_id") in ids:
            have[fact["fact_type"]].add(fact["subject_id"])
    for fact_type, subjects in sorted(have.items(), key=lambda kv: -len(kv[1])):
        print(f"  {fact_type:28} {_pct(len(subjects), n)}")

    print("\n-- candidate fields populated on the default path")
    for field in ("development_stage", "development_status", "company_ids", "modality_id",
                  "indication_ids", "trial_ids", "target_ids", "target_assertions"):
        filled = sum(1 for c in default if c.get(field))
        print(f"  {field:28} {_pct(filled, n)}")
    stages = Counter(c.get("development_stage") for c in default)
    print(f"  development_stage values   {dict(stages.most_common(8))}")
    assertions = Counter(
        (c["target_assertions"][0]["status"] if c.get("target_assertions") else "none")
        for c in default
    )
    print(f"  first target assertion     {dict(assertions)}")
    reasons = Counter(c.get("qualification_reason") for c in default)
    print(f"  qualification_reason       {dict(reasons.most_common(8))}")

    print("\n-- how much of the current declared order is decided by evidence vs tiebreak")
    shortlist = build_shortlist(SESearchResult.model_validate(raw), limit=n or 1)
    print(f"  ordering_basis {shortlist.ordering_basis}")
    top = shortlist.entries[:20]
    for entry in top:
        print(f"  {entry.position:>3}. {entry.name[:40]:40}"
              f" citations={len(entry.citations):>3}  target={entry.target_status}")

    print("\n-- source coverage (families the ordering would silently not see)")
    for family, status in sorted(manifest.get("source_status", {}).items()):
        print(f"  {family:28} {status}")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for arg in argv:
        audit(Path(arg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
