"""DEVELOPMENT: check evidence_attribution_v1 acceptance criteria E1-E7 between two replays.

    python research/se_gucy2c_dev_v3/check_acceptance.py BEFORE/result.json AFTER/result.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from bve.se.evidence.attribution import attributed_areas

ROUTES = [("eligible_asset_ids", "ELIGIBLE"), ("unresolved_asset_ids", "REVIEW"),
          ("excluded_asset_ids", "EXCLUDED"), ("low_support_asset_ids", "LOW_SUPPORT")]
RECOVERED = ("TAK-264", "TAK-164", "PF-07062119", "Ad5-hGCC-PADRE", "Ad5.F35-hGUCY2C-PADRE",
             "Lm-GUCY2C", "LYL273", "IM96", "LCAR-G08", "XKDCT080", "WD-01",
             "EB-DUO-CAR-NK-CEA/GCC")
AGONISTS = ("linaclotide", "plecanatide", "dolcanatide")
EXAMPLES = ("dextran", "aniline", "ether")


def load(path):
    r = json.loads(Path(path).read_text())
    route = {i: lab for key, lab in ROUTES for i in r[key]}
    cands = {c["canonical_name"]: c for c in r["candidates"]}
    gates = {g["subject_id"]: g["decisions"] for g in r["gate_evaluations"]}
    facts: dict[str, list] = {}
    for f in r["facts"]:
        facts.setdefault(f["subject_id"], []).append(f)
    claims = {c["claim_id"]: c for c in r["claims"]}
    docs = {d["document_id"]: d for d in r["source_documents"]}
    return r, route, cands, gates, facts, claims, docs


def fails(gates, aid):
    return {d["requirement_id"] for d in gates.get(aid, []) if d["status"] == "FAIL"}


def main() -> None:
    _, ra, ca, ga, _, _, _ = load(sys.argv[1])
    rb, rtb, cb, gb, fb, clb, db = load(sys.argv[2])
    out: dict = {}
    out["E1_recovered_not_visible"] = [n for n in RECOVERED
                                       if rtb.get(cb[n]["asset_id"]) not in ("ELIGIBLE", "REVIEW")]
    out["E2_agonists"] = {n: (rtb.get(c["asset_id"]), sorted(fails(gb, c["asset_id"])))
                          for n, c in cb.items() if n.casefold() in AGONISTS}
    out["E3_examples"] = {n: {"asset_areas": sorted({f["value"] for f in fb.get(cb[n]["asset_id"], [])
                                                     if f["fact_type"] == "therapeutic_area"}),
                              "modality": cb[n]["modality_id"]} for n in EXAMPLES}
    bad = []
    free_text = 0
    for aid, fs in fb.items():
        name = next((c["canonical_name"] for c in rb["candidates"] if c["asset_id"] == aid), "")
        for f in fs:
            if f["fact_type"] != "therapeutic_area":
                continue
            for cid in f["supporting_claim_ids"]:
                claim = clb.get(cid)
                doc = db.get(claim["source_document_id"]) if claim else None
                if not claim or not doc or doc["publisher"] == "ClinicalTrials.gov":
                    continue
                free_text += 1
                names = {name, *[c for c in [claim.get("subject_id")] if False]}
                ok = any(area == f["value"] for n in names
                         for area, _ in attributed_areas(claim["supporting_passage"], n))
                if not ok:
                    # the hit's raw name may differ from the canonical name: accept any alias
                    cand = next(c for c in rb["candidates"] if c["asset_id"] == aid)
                    ok = any(area == f["value"] for n in cand["aliases"]
                             for area, _ in attributed_areas(claim["supporting_passage"], n))
                if not ok:
                    bad.append((name, f["value"], claim["supporting_passage"][:160]))
    out["E4_free_text_area_claims"] = free_text
    out["E4_unattributed"] = bad
    out["E5_new_fail_or_excluded"] = sorted(
        (n, sorted(fails(gb, c["asset_id"]) - fails(ga, ca[n]["asset_id"])), rtb.get(c["asset_id"]))
        for n, c in cb.items() if n in ca and (
            (rtb.get(c["asset_id"]) == "EXCLUDED" and ra.get(ca[n]["asset_id"]) != "EXCLUDED")
            or fails(gb, c["asset_id"]) - fails(ga, ca[n]["asset_id"])))
    out["E5_identity"] = {"candidates": len(cb), "merges": len(rb["identity_merges"]),
                          "target_changes": [n for n in cb if n in ca and cb[n]["target_ids"] != ca[n]["target_ids"]]}
    eligible = [c["canonical_name"] for c in rb["candidates"] if c["asset_id"] in rb["eligible_asset_ids"]]
    out["E6_eligible"] = {n: sorted({f["value"] for f in fb[cb[n]["asset_id"]] if f["fact_type"] == "therapeutic_area"})
                          for n in eligible}

    def ctgov_areas(facts, claims, docs, aid):
        rows = set()
        for f in facts.get(aid, []):
            if f["fact_type"] != "therapeutic_area":
                continue
            for cid in f["supporting_claim_ids"]:
                cl = claims.get(cid)
                if cl and docs.get(cl["source_document_id"], {}).get("publisher") == "ClinicalTrials.gov":
                    rows.add((cl["source_document_id"], f["value"]))
        return rows
    _, _, _, _, fa2, cla, da = load(sys.argv[1])
    out["E7_ctgov_area_changes"] = [
        n for n in RECOVERED
        if ctgov_areas(fa2, cla, da, ca[n]["asset_id"]) != ctgov_areas(fb, clb, db, cb[n]["asset_id"])]
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
