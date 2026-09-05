"""Benchmark denominator under the run's own as-of policy.

Recall against the raw live universe conflates four different things. This states each
level separately, in benchmark terms: of the 224 canonical candidates, how many are even
reachable in the CT.gov corpus once each policy has been applied.
"""
import csv, json, pathlib, re, sys
sys.path.insert(0, "/home/djmann/projects/biotech-asset-valuation-engine/src")
from bve.se.discovery.adapters import _protocol_text

S = pathlib.Path("/home/djmann/staging/pdcd1_baseline")
ROOT = pathlib.Path("/home/djmann/projects/biotech-asset-valuation-engine/outputs/se/snapshots/clinicaltrials_gov")
d = json.load(open(S / "result_B6_pdcd1.json"))
led = {r["nct"]: r for r in json.load(open(S / "diag/b6_attrition_ledger.json"))}

nct2text = {}
for att in d["search_attempts"]:
    if att["source"] != "clinicaltrials_gov":
        continue
    for sid in att.get("snapshot_ids") or []:
        p = ROOT / (sid.split(":", 1)[1] + ".json")
        if not p.exists():
            continue
        j = json.loads(p.read_text())
        n = (j.get("identificationModule") or {}).get("nctId")
        if n and n not in nct2text:
            nct2text[n] = _protocol_text(j).casefold()

gold = list(csv.DictReader(open(S / "pdcd1_reference_universe_m8v2.csv")))
LEVELS = ["as_of_eligible", "policy_filtered", "extracted"]
sets = {
    "as_of_eligible": set(nct2text),
    "policy_filtered": {n for n, r in led.items() if r["primary"] in ("SURVIVED", "NO_ASSET_NAME_EXTRACTED")},
    "extracted": {n for n, r in led.items() if r["primary"] == "SURVIVED"},
}
mentioned = {m["normalized_asset_name"] for m in d["identity_mentions"] if m.get("normalized_asset_name")}

hit = {k: 0 for k in LEVELS}
hit["identified_asset"] = 0
unreachable = []
member = {}
for row in gold:
    names = [row["canonical_asset"]] + [a for a in (row["aliases"] or "").split("|") if a]
    pats = [re.compile(r"\b" + re.escape(n.casefold()) + r"\b") for n in names if n.strip()]
    found = {lvl: False for lvl in LEVELS}
    for n, txt in nct2text.items():
        if any(p.search(txt) for p in pats):
            for lvl in LEVELS:
                if n in sets[lvl]:
                    found[lvl] = True
    for lvl in LEVELS:
        hit[lvl] += found[lvl]
        if found[lvl]: member.setdefault(lvl, []).append(row["benchmark_id"])
    if any(nm.casefold() in mentioned for nm in names):
        hit["identified_asset"] += 1
        member.setdefault("identified_asset", []).append(row["benchmark_id"])
    if not found["as_of_eligible"]:
        unreachable.append(row["canonical_asset"])

print(f"gold candidates: {len(gold)}\n")
print(f"{'universe level':24} {'NCTs':>6}   {'gold reachable':>14}  {'ceiling recall':>14}")
print(f"{'live (no as-of)':24} {2913:>6}   {'-':>14}  {'-':>14}")
for lvl in LEVELS:
    print(f"{lvl:24} {len(sets[lvl]):>6}   {hit[lvl]:>14}  {hit[lvl]/len(gold):>13.1%}")
print(f"{'identified as asset':24} {'-':>6}   {hit['identified_asset']:>14}  {hit['identified_asset']/len(gold):>13.1%}")
print(f"\ngold candidates absent from the as-of CT.gov corpus entirely: {len(unreachable)}")
print("  e.g.", ", ".join(unreachable[:10]))
json.dump({"levels": {k: sorted(v) for k, v in sets.items()}, "gold_reachable": hit, "member": member,
           "unreachable": unreachable}, open(S / "diag/b6_denominator_members.json", "w"), indent=1)
