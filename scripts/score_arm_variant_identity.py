"""Stage I scorer for ``docs/se_policies/arm_variant_identity_v1.md``.

    PYTHONPATH=src python scripts/score_arm_variant_identity.py ~/se_runs > research/se_arm_identity/stage_i_v1.txt

I1-I4 compare against the raw ``*_qual_v7`` result; I5 compares top-50 orders where BOTH
sides are built with the adopted ranking-v2 key at HEAD, so no v2 movement is attributed here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bve.se.pipeline import SESearchResult
from bve.se.reporting.shortlist import build_shortlist

ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path) -> dict:
    return json.loads((path / "result.json").read_text())


def _gates(raw: dict) -> dict[str, dict[str, str]]:
    return {
        e["subject_id"]: {d["requirement_id"]: d["status"] for d in e["decisions"]}
        for e in raw["gate_evaluations"]
    }


def _facts(raw: dict, fact_type: str) -> dict[str, list]:
    out: dict[str, list] = {}
    for fact in raw["facts"]:
        if fact["fact_type"] == fact_type:
            out.setdefault(fact["subject_id"], []).append(json.dumps(fact["value"], sort_keys=True))
    return {k: sorted(v) for k, v in out.items()}


def _top(raw: dict, n: int = 50) -> list[tuple[str, str]]:
    shortlist = build_shortlist(SESearchResult.model_validate(raw), limit=n)
    return [(e.asset_id, e.name) for e in shortlist.entries]


def main(runs: Path) -> None:
    population = json.loads((ROOT / "research/se_arm_identity/population_v1.json").read_text())
    det_a, det_b = _load(runs / "tac01_armid_v1"), _load(runs / "tac01_armid_v1_det")
    same = (
        det_a["identity_merges"] == det_b["identity_merges"]
        and _facts(det_a, "construct_target_set") == _facts(det_b, "construct_target_set")
        and _gates(det_a) == _gates(det_b)
        and _top(det_a) == _top(det_b)
    )
    print(f"I6 determinism: {'PASS' if same else 'FAIL'}")
    for bench in ("tac01", "mint5"):
        base, new = _load(runs / f"{bench}_qual_v7"), _load(runs / f"{bench}_armid_v1")
        print(f"===== {bench}")
        arm = [m for m in new["identity_merges"] if str(m.get("deterministic_basis", "")).startswith("arm_variant:")]
        by_id = {a["asset_id"]: a for a in new["candidates"]}
        groups = sorted(sorted(a for a in by_id[m["target_asset_id"]]["aliases"]) for m in arm)
        frozen = [g for g in population if g["benchmark"] == bench]
        ok_i1 = len(arm) == len(frozen)
        ok_i3 = True
        for group in frozen:
            hit = [m for m in arm if set(group["members"]) <= set(by_id[m["target_asset_id"]]["aliases"])]
            if len(hit) != 1:
                ok_i1 = False
                continue
            merged = by_id[hit[0]["target_asset_id"]]
            if not set(group["shared_trials"]) <= set(merged["trial_ids"]):
                ok_i3 = False
        print(f"I1 arm merges {len(arm)} vs frozen {len(frozen)}: {'PASS' if ok_i1 else 'FAIL'}")
        print(f"I3 aliases+trials preserved: {'PASS' if ok_i3 else 'FAIL'}  groups={groups}")
        absorbed = {s for m in arm for s in m["source_asset_ids"]}
        survivors = {m["target_asset_id"] for m in arm}
        bq = {a["asset_id"]: a["qualification_reason"] for a in base["candidates"]}
        nq = {a["asset_id"]: a["qualification_reason"] for a in new["candidates"]}
        others = [k for k in bq if k not in absorbed]
        q_changed = [k for k in others if k in nq and bq[k] != nq[k]]
        missing = [k for k in others if k not in nq]
        gb, gn = _gates(base), _gates(new)
        g_changed = [k for k in others if k in gb and gb.get(k) != gn.get(k)]
        cb, cn = _facts(base, "construct_target_set"), _facts(new, "construct_target_set")
        c_changed = [k for k in others if cb.get(k) != cn.get(k)]
        print(f"I4 non-merged assets: missing={len(missing)} qual_changed={len(q_changed)} "
              f"gate_changed={len(g_changed)} construct_changed={len(c_changed)}")
        for k in survivors:
            members = [s for m in arm if m["target_asset_id"] == k for s in m["source_asset_ids"]]
            member_gates = [gb.get(s) for s in members if s in gb]
            agreed = member_gates and all(g == member_gates[0] for g in member_gates)
            print(f"   survivor {by_id[k]['canonical_name'][:40]}: members agreed={bool(agreed)} "
                  f"equal={agreed and gn.get(k) == member_gates[0]}")
        tb, tn = _top(base), _top(new)
        ids_b, ids_n = [a for a, _ in tb], [a for a, _ in tn]
        left = [(name, i + 1, a in absorbed) for i, (a, name) in enumerate(tb) if a not in ids_n]
        kept = [a for a in ids_b if a in ids_n]
        order = [a for a in ids_n if a in set(kept)]
        print(f"I5 (both sides ranking v2) left={left} entered="
              f"{[(n, i + 1) for i, (a, n) in enumerate(tn) if a not in ids_b]} "
              f"retained order preserved={kept == order}")
        print("   top20:", [n[:30] for _, n in tn[:20]])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
