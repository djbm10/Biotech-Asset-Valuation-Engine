"""Stage T scorer for ``docs/se_policies/protocol_id_trial_attribution_v1.md``.

Identity/facts/gates vs raw ``*_ncitid_v1``; ranking with both sides rebuilt under ranking v2
at HEAD. Merge timestamps (``created_at``, ``applied_at``) are excluded, as preregistered.
"""

from __future__ import annotations

import json
import re
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


def facts(raw, subjects=None):
    return sorted(json.dumps([f["subject_id"], f["fact_type"], f["value"]], sort_keys=True) for f in raw["facts"] if subjects is None or f["subject_id"] in subjects)


def gates(raw):
    return {e["subject_id"]: {d["requirement_id"]: d["status"] for d in e["decisions"]} for e in raw["gate_evaluations"]}


def top(raw, n=50):
    s = build_shortlist(SESearchResult.model_validate(raw), limit=n)
    return [(e.asset_id, e.name) for e in s.entries]


def main(runs: Path) -> None:
    pop = json.loads((ROOT / "research/se_protocol_id/population_v1.json").read_text())
    a, b = load(runs / "tac01_protoid_v1"), load(runs / "tac01_protoid_v1_det")
    print("T7 determinism:", merges(a) == merges(b) and facts(a) == facts(b) and gates(a) == gates(b) and top(a) == top(b) and a["trial_reattributions"] == b["trial_reattributions"])
    for bench in ("tac01", "mint5"):
        base, new = load(runs / f"{bench}_ncitid_v1"), load(runs / f"{bench}_protoid_v1")
        bc = {x["asset_id"]: x for x in base["candidates"]}
        nc = {x["asset_id"]: x for x in new["candidates"]}
        want = {(p["trial_id"], p["from_asset"], p["to"][0]) for p in pop if p["benchmark"] == bench}
        got = {(m["trial_id"], m["from_asset_id"], m["to_asset_id"]) for m in new["trial_reattributions"]}
        print(f"===== {bench}")
        print(f"T1 moves == frozen: {got == want} ({len(got)} vs {len(want)}) extra={sorted(got - want)} missing={sorted(want - got)}")
        print(f"T2 merges unchanged: {merges(base) == merges(new)}")
        touched = {s for _, s, _ in want} | {d for _, _, d in want}
        audit_ok = all(set(m) >= {"trial_id", "from_asset_id", "to_asset_id", "protocol_id", "prefix", "basis"} for m in new["trial_reattributions"])
        placed = all(t in nc[d]["trial_ids"] and t not in nc[s]["trial_ids"] for t, s, d in want)
        expected_trials = {k: set(v["trial_ids"]) for k, v in bc.items()}
        for t, s, d in want:
            expected_trials[s].discard(t)
            expected_trials[d].add(t)
        others_ok = all(set(nc[k]["trial_ids"]) == expected_trials[k] for k in bc if k in nc)
        print(f"T3 audit complete={audit_ok} placed={placed} all trial sets as expected={others_ok} deleted={sorted(set(bc) - set(nc))}")
        outside = set(bc) - touched
        changed = [k for k in outside if any(bc[k][f] != nc[k][f] for f in ("canonical_name", "aliases", "trial_ids", "authority_modality", "modality_match", "qualification_reason"))]
        gb, gn = gates(base), gates(new)
        print(f"T4 outside changed={len(changed)} gates changed={sum(gb.get(k) != gn.get(k) for k in outside)} facts same={facts(base, outside) == facts(new, outside)}")
        for k in sorted(touched):
            fb, fn = set(facts(base, {k})), set(facts(new, {k}))
            if fb != fn or gb.get(k) != gn.get(k) or bc[k]["qualification_reason"] != nc[k]["qualification_reason"]:
                print(f"   touched {nc[k]['canonical_name'][:45]!r}: -facts {len(fb - fn)} +facts {len(fn - fb)} gate_changed={gb.get(k) != gn.get(k)} qual {bc[k]['qualification_reason']} -> {nc[k]['qualification_reason']}")
        hp = lambda r: {f["subject_id"]: f["value"] for f in r["facts"] if f["fact_type"] == "human_poc_present"}  # noqa: E731
        hb, hn = hp(base), hp(new)
        hp_changed = {k for k in set(hb) | set(hn) if hb.get(k) != hn.get(k)}
        dests = {d for _, _, d in want}
        moved_trials = {t for t, _, _ in want}
        docs = {d["document_id"]: d.get("source_url") or "" for d in new["source_documents"]}
        claims = {c["claim_id"]: c for c in new["claims"]}
        support_ok = True
        for k in hp_changed & dests:
            f = next(f for f in new["facts"] if f["fact_type"] == "human_poc_present" and f["subject_id"] == k)
            urls = {docs.get(claims[c]["source_document_id"], "") for c in f["supporting_claim_ids"] if c in claims}
            support_ok &= any(re.search(r"NCT\d{8}", u) and re.search(r"NCT\d{8}", u).group(0) in moved_trials for u in urls)
        print(f"T5 human-PoC changes={sorted(nc[k]['canonical_name'] for k in hp_changed)} only on destinations={hp_changed <= dests} supported by moved trials={support_ok}")
        tb, tn = top(base), top(new)
        ib, inew = [x for x, _ in tb], [x for x, _ in tn]
        print(f"T6 identical={tb == tn} left={[(n, i + 1, x in touched) for i, (x, n) in enumerate(tb) if x not in inew]} entered={[(n, i + 1, x in touched) for i, (x, n) in enumerate(tn) if x not in ib]}")
        kept = [x for x in inew if x in ib and x not in touched]
        print(f"   retained untouched relative order preserved: {kept == [x for x in ib if x in kept]}")
        print("   top20:", [n[:28] for _, n in tn[:20]])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
