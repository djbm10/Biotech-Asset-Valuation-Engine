"""DEVELOPMENT: check gi_area_evidence_v1 acceptance criteria B2-B7 between two replays.

    python research/se_gucy2c_dev_v2/check_acceptance.py BEFORE/result.json AFTER/result.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROUTES = [("eligible_asset_ids", "ELIGIBLE"), ("unresolved_asset_ids", "REVIEW"),
          ("excluded_asset_ids", "EXCLUDED"), ("low_support_asset_ids", "LOW_SUPPORT")]
AGONISTS = ("linaclotide", "plecanatide", "dolcanatide")
#: The 12 named reference assets recovered in the v1 development replay, by the candidate
#: name they carry there (already disclosed in research/se_gucy2c_dev_v1/REPORT.md).
RECOVERED = ("TAK-264", "TAK-164", "PF-07062119", "Ad5-hGCC-PADRE", "Ad5.F35-hGUCY2C-PADRE",
             "Lm-GUCY2C", "LYL273", "IM96", "LCAR-G08", "XKDCT080", "WD-01",
             "EB-DUO-CAR-NK-CEA/GCC")


def load(path):
    r = json.loads(Path(path).read_text())
    route = {i: lab for key, lab in ROUTES for i in r[key]}
    cands = {c["canonical_name"]: c for c in r["candidates"]}
    gates = {g["subject_id"]: g["decisions"] for g in r["gate_evaluations"]}
    facts = {}
    for f in r["facts"]:
        facts.setdefault(f["subject_id"], []).append(f)
    entailed = {e["claim_id"]: e.get("entailed") for e in r["entailment_results"]}
    return r, route, cands, gates, facts, entailed


def main() -> None:
    (ra, rta, ca, _ga, fa, _), (rb, rtb, cb, gb, fb, eb) = load(sys.argv[1]), load(sys.argv[2])
    out = {}
    out["B1_recovered_not_visible"] = [
        n for n in RECOVERED
        if n not in cb or rtb.get(cb[n]["asset_id"]) not in ("ELIGIBLE", "REVIEW")]
    out["B6_total_candidates"] = (len(ca), len(cb))
    out["B6_engine_merges"] = (len(ra["identity_merges"]), len(rb["identity_merges"]))
    left = [n for n in ca if rta.get(ca[n]["asset_id"]) in ("ELIGIBLE", "REVIEW")
            and rtb.get(cb[n]["asset_id"]) not in ("ELIGIBLE", "REVIEW")]
    rows = []
    for n in left:
        aid = cb[n]["asset_id"]
        ta = next(d for d in gb[aid] if d["requirement_id"] == "strategy.therapeutic_area")
        areas = sorted({f["value"] for f in fb[aid] if f["fact_type"] == "therapeutic_area"})
        claims = [c for f in fb[aid] if f["fact_type"] == "therapeutic_area"
                  for c in f["supporting_claim_ids"]]
        rows.append({"name": n, "route": rtb[aid], "ta_gate": ta["status"], "areas": areas,
                     "all_claims_entailed": all(eb.get(c) for c in claims)})
    out["B3_left_view"] = rows
    out["B3_ok"] = all(r["route"] == "EXCLUDED" and r["ta_gate"] == "FAIL" and
                       "ONCOLOGY" not in r["areas"] and r["all_claims_entailed"] for r in rows)
    out["B4_oncology_evidence_excluded"] = [
        n for n in cb if rtb.get(cb[n]["asset_id"]) == "EXCLUDED"
        and rta.get(ca[n]["asset_id"]) != "EXCLUDED"
        and any(f["fact_type"] == "therapeutic_area" and f["value"] == "ONCOLOGY"
                for f in fb.get(cb[n]["asset_id"], []))]
    out["route_changes"] = sorted(
        (n, rta.get(ca[n]["asset_id"]), rtb.get(cb[n]["asset_id"])) for n in ca
        if rta.get(ca[n]["asset_id"]) != rtb.get(cb[n]["asset_id"]))
    out["B2_agonists"] = {}
    for n, c in cb.items():
        if n.casefold() in AGONISTS:
            reasons = [d["requirement_id"] for d in gb.get(c["asset_id"], []) if d["status"] == "FAIL"]
            out["B2_agonists"][n] = (rtb.get(c["asset_id"]), reasons)
    out["B5_target_or_modality_changes"] = [
        n for n in ca if (ca[n]["target_ids"], ca[n]["modality_id"]) != (cb[n]["target_ids"], cb[n]["modality_id"])]
    hp = lambda f: sum(1 for x in f.values() for y in x if y["fact_type"] == "human_poc_present")
    out["B7_eligible"] = (len(ra["eligible_asset_ids"]), len(rb["eligible_asset_ids"]))
    out["B7_eligible_names"] = [c["canonical_name"] for c in rb["candidates"] if c["asset_id"] in rb["eligible_asset_ids"]]
    out["B7_human_poc_present_facts"] = (hp(fa), hp(fb))
    print(json.dumps(out, indent=1))
    if out["B1_recovered_not_visible"]:
        raise SystemExit(f"B1 FAIL: {out['B1_recovered_not_visible']}")


if __name__ == "__main__":
    main()
