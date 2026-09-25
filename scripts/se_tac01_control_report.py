"""Score the TAC01-CD19 over-reach positive control.

Usage::

    PYTHONPATH=src BVE_SE_ONTOLOGY_SNAPSHOT=data/se/ontology/current \
      python3 scripts/se_tac01_control_report.py <run_dir>

Single arm by design -- see ``docs/se_policies/tac01_overreach_positive_control.md`` §3: the v5 veto
is monotone in the removing direction, so retention with the rule on settles over-reach without a
fix-off control. The criteria below are §4/§5 as frozen, including the *inconclusive* outcome, which
matters as much as the pass: if no class term is demoted anywhere in this run then the veto never
fired and TAC01-CD19's survival would prove nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bve.se.discovery.class_terms import individuating_residue, is_class_term

CANARY = "TAC01-CD19"

#: v4's twelve plus v5's two. None may reach the default path.
FROZEN_NEGATIVES = (
    "Placebo",
    "choice",
    "paper",
    "frontline",
    "bsAbs",
    "POD24",
    "equal",
    "nature",
    "roche",
    "saline",
    "search",
    "success",
    "CAR19",
    "CART19",
)


def _view(directory: str) -> dict:
    result = json.loads((Path(directory) / "result.json").read_text())
    low = set(result["low_support_asset_ids"])
    poc = {
        fact["subject_id"]
        for fact in result["facts"]
        if fact.get("fact_type") == "human_poc_present"
    }
    by_name: dict[str, dict] = {}
    for candidate in result["candidates"]:
        by_name[candidate.get("canonical_name") or ""] = {
            "default": candidate["asset_id"] not in low,
            "reason": candidate.get("qualification_reason"),
            "poc": candidate["asset_id"] in poc,
            "trials": len(candidate.get("trial_ids") or []),
        }
    return by_name


def main(directory: str) -> int:
    by_name = _view(directory)
    default = [n for n, v in by_name.items() if v["default"]]
    failures: list[str] = []
    inconclusive: list[str] = []

    print(f"candidates {len(by_name)}   default path {len(default)}")

    print(f"\n1. the canary: {CANARY}")
    canary = by_name.get(CANARY)
    if canary is None:
        print(f"  ABSENT from the run -- residue={individuating_residue(CANARY)}")
        print("  Per §5 this means the QUERY failed to reach it, not that v5 passed.")
        inconclusive.append(f"{CANARY} absent: the query did not reach it")
    else:
        state = "default" if canary["default"] else "review"
        print(
            f"  {state} / {canary['reason'] or '-'} / trials={canary['trials']} /"
            f" poc={canary['poc']}"
        )
        print(f"  residue={individuating_residue(CANARY)}  is_class_term={is_class_term(CANARY)}")
        if not canary["default"]:
            failures.append(
                f"§5 {CANARY} was demoted to review -- a named asset lost standing, which is the "
                "one outcome the operator said reopens identity"
            )
        elif not canary["reason"]:
            failures.append(f"§4.1 {CANARY} is on the default path with no named reason")

    print("\n2. the veto must be firing in this corpus (else the canary proves nothing)")
    demoted = sorted(n for n, v in by_name.items() if not v["default"] and is_class_term(n))
    print(f"  class terms held in review: {len(demoted)}")
    for name in demoted[:15]:
        print(f"    {name}  (trials {by_name[name]['trials']})")
    if len(demoted) > 15:
        print(f"    … and {len(demoted) - 15} more")
    if not demoted:
        inconclusive.append("no class term was demoted, so the veto did not fire on this corpus")

    print("\n3. no frozen negative on the default path")
    for name in FROZEN_NEGATIVES:
        entry = by_name.get(name)
        if entry is None:
            continue
        state = "default" if entry["default"] else "review"
        marker = "  <-- FAIL" if entry["default"] else ""
        print(f"  {name:12} {state}{' POC' if entry['poc'] else ''}{marker}")
        if entry["default"]:
            failures.append(f"§4.3 frozen negative {name} reached the default path")

    print("\n4. any class term still on the default path is an invariant breach")
    leaked = sorted(n for n in default if is_class_term(n))
    print(f"  leaked: {len(leaked)}")
    for name in leaked:
        print(f"    {name}")
        failures.append(f"class term {name} is on the default path")

    if failures:
        verdict = "FAIL"
    elif inconclusive:
        verdict = "INCONCLUSIVE"
    else:
        verdict = "PASS"
    print(f"\n{verdict}")
    for note in failures or inconclusive:
        print(f"  - {note}")
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
