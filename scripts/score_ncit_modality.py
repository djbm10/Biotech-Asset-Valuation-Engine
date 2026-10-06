"""Stage N scorer for ``docs/se_policies/ncit_modality_v1.md``.

Facts/identity/gates vs raw ``*_armid_v1``; ranking with both sides rebuilt under ranking v2
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


def load(path: Path) -> dict:
    return json.loads((path / "result.json").read_text())


def merges(raw):
    return sorted(json.dumps({k: v for k, v in m.items() if k not in VOLATILE}, sort_keys=True) for m in raw["identity_merges"])


def facts(raw):
    return sorted(json.dumps([f["subject_id"], f["fact_type"], f["value"]], sort_keys=True) for f in raw["facts"])


def gates(raw):
    return {e["subject_id"]: {d["requirement_id"]: d["status"] for d in e["decisions"]} for e in raw["gate_evaluations"]}


def top(raw, n=50):
    s = build_shortlist(SESearchResult.model_validate(raw), limit=n)
    return [(e.asset_id, e.name) for e in s.entries]


def main(runs: Path) -> None:
    pop = json.loads((ROOT / "research/se_ncit_modality/population_v1.json").read_text())
    a, b = load(runs / "tac01_ncitmod_v1"), load(runs / "tac01_ncitmod_v1_det")
    mod = lambda r: sorted((x["asset_id"], x["authority_modality"], x["modality_match"]) for x in r["candidates"])  # noqa: E731
    print("N6 determinism:", merges(a) == merges(b) and facts(a) == facts(b) and gates(a) == gates(b) and mod(a) == mod(b) and top(a) == top(b))
    for bench in ("tac01", "mint5"):
        base, new = load(runs / f"{bench}_armid_v1"), load(runs / f"{bench}_ncitmod_v1")
        bc = {x["asset_id"]: x for x in base["candidates"]}
        nc = {x["asset_id"]: x for x in new["candidates"]}
        frozen = {p["asset_id"] for p in pop if p["benchmark"] == bench}
        filled = {k for k in nc if bc.get(k, {}).get("authority_modality") is None and nc[k]["authority_modality"] == "CELL_THERAPY"}
        other_mod = [k for k in nc if k not in frozen and (bc[k]["authority_modality"], bc[k]["authority_modality_basis"]) != (nc[k]["authority_modality"], nc[k]["authority_modality_basis"])]
        match_changed = {k for k in nc if bc[k]["modality_match"] != nc[k]["modality_match"]}
        print(f"===== {bench}")
        print(f"N1 filled == frozen: {filled == frozen} ({len(filled)} vs {len(frozen)}) extra={len(filled - frozen)} missing={len(frozen - filled)}")
        print(f"N2 non-population modality changes: {len(other_mod)}")
        print(f"N3 candidates same: {set(bc) == set(nc)} facts same: {facts(base) == facts(new)} gates same: {gates(base) == gates(new)} merges same: {merges(base) == merges(new)} qual same: {all(bc[k]['qualification_reason'] == nc[k]['qualification_reason'] for k in nc)}")
        trans = {}
        for k in match_changed:
            trans[(bc[k]["modality_match"], nc[k]["modality_match"])] = trans.get((bc[k]["modality_match"], nc[k]["modality_match"]), 0) + 1
        print(f"N4 match changes only in population: {match_changed <= frozen}; transitions={trans}")
        tb, tn = top(base), top(new)
        ib, inew = [x for x, _ in tb], [x for x, _ in tn]
        print(f"N5 identical={tb == tn} left={[(n, i + 1, x in frozen) for i, (x, n) in enumerate(tb) if x not in inew]} entered={[(n, i + 1, x in frozen) for i, (x, n) in enumerate(tn) if x not in ib]}")
        moved = [(n[:34], ib.index(x) + 1, i + 1, x in frozen) for i, (x, n) in enumerate(tn) if x in ib and ib.index(x) != i]
        print(f"   moved (name, before, after, in population): {moved}")
        print("   top20:", [n[:28] for _, n in tn[:20]])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
