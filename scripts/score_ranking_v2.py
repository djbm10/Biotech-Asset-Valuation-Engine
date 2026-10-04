"""Offline scorer for ``docs/se_policies/ranking_lexicographic_v2.md`` (G1, G3, G7 + top 20).

    PYTHONPATH=src python scripts/score_ranking_v2.py ~/se_runs > research/se_ranking_v2/score_v2.txt
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bve.se.reporting.shortlist as sl
from bve.se.pipeline import SESearchResult


def build(result, declared: bool):
    original = sl._declares_target
    sl._declares_target = lambda _result: declared
    try:
        return sl.build_shortlist(result, limit=10_000)
    finally:
        sl._declares_target = original


def main(root: Path) -> None:
    for bench in ("tac01", "mint5"):
        raw = json.loads((root / f"{bench}_qual_v7" / "result.json").read_text())
        result = SESearchResult.model_validate(raw)
        v1, v2, v2b = build(result, False), build(result, True), build(result, True)
        ids = lambda s: [e.asset_id for e in s.entries]  # noqa: E731
        deferred = lambda s: sorted(e.asset_id for e in s.deferred)  # noqa: E731
        print(f"===== {bench}")
        print(f"G1 visible set equal: {sorted(ids(v1)) == sorted(ids(v2))}; "
              f"deferred equal: {deferred(v1) == deferred(v2)}; counts {len(ids(v1))}")
        print(f"G7 deterministic: {ids(v2) == ids(v2b)}")
        status = {e.asset_id: (e.target_status, e.name) for e in v2.entries}
        gates = {}
        for evaluation in result.gate_evaluations:
            for d in evaluation.decisions:
                if d.requirement_id == sl._TARGET_REQUIREMENT_ID:
                    gates[evaluation.subject_id] = d.status.value
        p1 = {a: i for i, a in enumerate(ids(v1))}
        p2 = {a: i for i, a in enumerate(ids(v2))}
        violations = 0
        order = ids(v1)
        for i, a in enumerate(order):
            for b in order[i + 1:]:
                if gates.get(a) == gates.get(b) and p2[a] > p2[b]:
                    violations += 1
        print(f"G3 same-decision pairs reordered: {violations}")
        print("top 20 v1 | v2 (target decision)")
        for i in range(20):
            a, b = ids(v1)[i], ids(v2)[i]
            print(f"  {i + 1:2} {status[a][1][:38]:38} {gates.get(a)!s:8}| "
                  f"{status[b][1][:38]:38} {gates.get(b)}")
        _ = p1


if __name__ == "__main__":
    main(Path(sys.argv[1]))
