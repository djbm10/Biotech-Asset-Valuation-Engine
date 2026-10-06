"""Stage P scorer for ``docs/se_policies/ncit_product_identity_v1.md``.

Identity/facts/gates vs raw ``*_ncitmod_v1``; ranking with both sides rebuilt under ranking v2
at HEAD. Merge timestamps (``created_at``, ``applied_at``) are excluded, as preregistered.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bve.se.pipeline import SESearchResult
from bve.se.reporting.shortlist import build_shortlist

ROOT = Path(__file__).resolve().parents[1]
VOLATILE = {"created_at", "applied_at"}
BASIS = "ncit_product:"


def load(path: Path) -> dict:
    return json.loads((path / "result.json").read_text())


def merges(raw):
    return sorted(json.dumps({k: v for k, v in m.items() if k not in VOLATILE}, sort_keys=True) for m in raw["identity_merges"])


def facts(raw, keep=None):
    return sorted(json.dumps([f["subject_id"], f["fact_type"], f["value"]], sort_keys=True) for f in raw["facts"] if keep is None or f["subject_id"] in keep)


def gates(raw):
    return {e["subject_id"]: {d["requirement_id"]: d["status"] for d in e["decisions"]} for e in raw["gate_evaluations"]}


def top(raw, n=50):
    s = build_shortlist(SESearchResult.model_validate(raw), limit=n)
    return [(e.asset_id, e.name) for e in s.entries]


def main(runs: Path) -> None:
    pop = json.loads((ROOT / "research/se_ncit_identity/population_v2.json").read_text())
    a, b = load(runs / "tac01_ncitid_v1"), load(runs / "tac01_ncitid_v1_det")
    print("P-6 determinism:", merges(a) == merges(b) and facts(a) == facts(b) and gates(a) == gates(b) and top(a) == top(b))
    for bench in ("tac01", "mint5"):
        base, new = load(runs / f"{bench}_ncitmod_v1"), load(runs / f"{bench}_ncitid_v1")
        bc = {x["asset_id"]: x for x in base["candidates"]}
        nc = {x["asset_id"]: x for x in new["candidates"]}
        groups = [g for g in pop if g["benchmark"] == bench]
        expected = {frozenset(g["expected_merged"]) for g in groups if g["expected"] == "MERGE"}
        got = {frozenset(m["source_asset_ids"]) for m in new["identity_merges"] if (m.get("deterministic_basis") or "").startswith(BASIS)}
        print(f"===== {bench}")
        print(f"P-1 merged groups == frozen: {got == expected} ({len(got)} vs {len(expected)}) extra={[sorted(x) for x in got - expected]} missing={[sorted(x) for x in expected - got]}")
        separate = {i for g in groups for i in g["expected_separate"]}
        print(f"P-2 guarded assets still present: {separate <= set(nc)}")
        merged_ids = set().union(*expected) if expected else set()
        bad_prov = []
        for g in expected:
            survivor = next(i for i in g if i in nc)
            names = {n for i in g for n in [bc[i]["canonical_name"], *bc[i]["aliases"]]}
            trials = {t for i in g for t in bc[i]["trial_ids"]}
            if not names <= set(nc[survivor]["aliases"]) or set(nc[survivor]["trial_ids"]) != trials:
                bad_prov.append(survivor)
        sep_ok = all(nc[i]["trial_ids"] == bc[i]["trial_ids"] for i in separate)
        print(f"P-3 provenance bad={bad_prov} guarded trials unchanged={sep_ok}")
        outside = set(bc) - merged_ids
        changed = [k for k in outside if k in nc and any(bc[k][f] != nc[k][f] for f in ("canonical_name", "aliases", "trial_ids", "authority_modality", "modality_match", "qualification_reason"))]
        gb, gn = gates(base), gates(new)
        print(f"P-4 outside missing={len(outside - set(nc))} changed={len(changed)} gates changed={sum(gb.get(k) != gn.get(k) for k in outside)} facts same={facts(base, outside) == facts(new, outside)}")
        for g in expected:
            survivor = next(i for i in g if i in nc)
            member_gates = [gb.get(i) for i in g]
            if all(x == member_gates[0] for x in member_gates) and gn.get(survivor) != member_gates[0]:
                print(f"   P-4 survivor gate differs from agreeing members: {nc[survivor]['canonical_name']}")
        tb, tn = top(base), top(new)
        ib, inew = [x for x, _ in tb], [x for x, _ in tn]
        print(f"P-5 identical={tb == tn} left={[(n, i + 1, x in merged_ids) for i, (x, n) in enumerate(tb) if x not in inew]} entered={[(n, i + 1) for i, (x, n) in enumerate(tn) if x not in ib]}")
        kept = [x for x in inew if x in ib and x not in merged_ids]
        print(f"   retained non-merged relative order preserved: {kept == [x for x in ib if x in kept]}")
        print("   top20:", [n[:28] for _, n in tn[:20]])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
