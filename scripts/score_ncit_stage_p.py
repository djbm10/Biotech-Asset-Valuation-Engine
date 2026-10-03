"""Stage P scorer for ``docs/se_policies/ncit_target_sidecar_v1.md`` (P0-P5 mechanics).

    python scripts/score_ncit_stage_p.py ~/se_runs > research/se_ncit/stage_p_v1.txt
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load(run: Path) -> dict:
    return json.loads((run / "result.json").read_text())


def construct(result: dict) -> dict[str, list]:
    out: dict[str, list] = {}
    for fact in result["facts"]:
        if fact["fact_type"] == "construct_target_set":
            out.setdefault(fact["subject_id"], []).append(sorted(fact["value"]))
    return {k: sorted(v) for k, v in out.items()}


def names(result: dict) -> dict[str, str]:
    return {a["asset_id"]: a["canonical_name"] for a in result["candidates"]}


def ranked(result: dict) -> list[str]:
    return [e["asset_id"] for e in result["ranking"]["ranked"]]


def target_gate(result: dict) -> dict[str, str]:
    out = {}
    for evaluation in result["gate_evaluations"]:
        for decision in evaluation["decisions"]:
            if decision["gate_id"] == "target_logic":
                out[evaluation["subject_id"]] = decision["status"]
    return out


def main(root: Path) -> None:
    det_a, det_b = load(root / "tac01_ncit_v1"), load(root / "tac01_ncit_v1_det")
    p0 = (
        construct(det_a) == construct(det_b)
        and det_a["ncit_target_dispositions"] == det_b["ncit_target_dispositions"]
        and ranked(det_a) == ranked(det_b)
    )
    print(f"P0 determinism (construct facts, dispositions, ranking): {'PASS' if p0 else 'FAIL'}")

    for bench in ("tac01", "mint5"):
        base, new = load(root / f"{bench}_fragment_a1"), load(root / f"{bench}_ncit_v1")
        nb, nn = names(base), names(new)
        cb, cn = construct(base), construct(new)
        changed_existing = [a for a in cb if cn.get(a) != cb[a]]
        print(f"\n===== {bench}")
        print(f"P2 baseline construct facts changed/removed: {len(changed_existing)}")
        for a in changed_existing:
            print(f"   {nb.get(a, a)} base={cb[a]} new={cn.get(a)}")
        rb, rn = ranked(base), ranked(new)
        top50 = set(rn[:50]) | set(rb[:50])
        new_facts = {a: cn[a] for a in cn if a not in cb}
        print(f"new construct facts: {len(new_facts)} total, {len(set(new_facts) & top50)} in a top 50")
        disp = {d["asset_id"]: d for d in new["ncit_target_dispositions"]}
        for a in sorted(new_facts, key=lambda a: (a not in top50, nn.get(a, a))):
            d = disp.get(a, {})
            pos = rn.index(a) + 1 if a in rn else None
            print(
                f"   {'TOP50 ' if a in top50 else '      '}#{pos} {nn.get(a, a)} -> {new_facts[a]}"
                f" | NCIt {d.get('ncit_code')} via {d.get('matched_name')!r}"
            )
        gb, gn = target_gate(base), target_gate(new)
        print("target-gate changes:")
        for a in sorted(set(gb) | set(gn)):
            if gb.get(a) != gn.get(a):
                print(f"   {nn.get(a, nb.get(a, a))}: {gb.get(a)} -> {gn.get(a)}")
        print("top-20 base -> new:")
        for i in range(20):
            x = nb.get(rb[i], rb[i]) if i < len(rb) else "-"
            y = nn.get(rn[i], rn[i]) if i < len(rn) else "-"
            print(f"   {i + 1:2} {x[:40]:40} | {y[:40]}")
        print("dispositions by reason/action:")
        tally: dict[tuple, int] = {}
        for d in new["ncit_target_dispositions"]:
            tally[(d["reason"], d["action"])] = tally.get((d["reason"], d["action"]), 0) + 1
        for k, v in sorted(tally.items()):
            print(f"   {k}: {v}")
        for d in new["ncit_target_dispositions"]:
            if d["action"] == "kept_existing_conflict" or d["reason"] != "emit":
                print(f"   [{d['reason']}/{d['action']}] {d['canonical_name']} {d['ncit_code']} "
                      f"ncit={d['ncit_targets']} class={d['class_set']} mech={d['mechanism_set']}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
