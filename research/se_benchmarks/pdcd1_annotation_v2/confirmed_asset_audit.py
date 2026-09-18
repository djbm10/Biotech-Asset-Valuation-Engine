"""Per-asset failure-boundary accounting over the 40 V2-confirmed PDCD1 assets.

Each asset is walked through the pipeline's own stage boundaries and attributed to the
FIRST boundary it failed at, so a downstream symptom is never reported as the cause.
"""
import csv, json, pathlib, re, collections

B = pathlib.Path("/home/djmann/staging/pdcd1_baseline")
V1 = pathlib.Path("/home/djmann/staging/pdcd1_adjudication_v1")

MEM = json.load(open(B / "diag/b6_denominator_members.json"))["member"]
LEVEL = {k: set(v) for k, v in MEM.items()}
led = {r["nct"]: r for r in json.load(open(B / "diag/b6_attrition_ledger.json"))}
run = json.load(open(B / "result_B6_pdcd1.json"))
mentions = {m["normalized_asset_name"] for m in run["identity_mentions"] if m.get("normalized_asset_name")}
gold = {r["benchmark_id"]: r for r in csv.DictReader(open(B / "pdcd1_reference_universe_m8v2.csv"))}
ev = {json.loads(l)["benchmark_id"]: json.loads(l) for l in open(V1 / "blinded_evidence.jsonl")}

roles = {json.loads(l)["benchmark_id"]: json.loads(l) for l in open(V1 / "gold_entry_roles.jsonl")}
v2 = {json.loads(l)["benchmark_id"]: json.loads(l) for l in open("v2_annotation_layer.jsonl")}
confirmed = ({b for b, r in roles.items()
              if r["entity_role"] == "ASSET" and r["target_relevance"] == "PDCD1_MATCH"}
             | {b for b, r in v2.items() if r["target_relevance_v2"] == "PDCD1_MATCH"})

rows = []
for b in sorted(confirmed, key=lambda x: gold[x]["canonical_asset"].casefold()):
    g = gold[b]
    names = [g["canonical_asset"]] + [a for a in (g["aliases"] or "").split("|") if a]
    hits = ev.get(b, {}).get("ctgov_exhibits", {})
    ncts = {h["nct"] for v in hits.values() for h in v}

    # LEVEL maps each stage to the set of BENCHMARK IDS that survive it, not to NCT ids.
    reachable = b in LEVEL["as_of_eligible"]
    retrieved = bool(ncts)
    survived_policy = b in LEVEL["policy_filtered"]
    extracted = b in LEVEL["extracted"]
    identified = b in LEVEL["identified_asset"]
    # Identity resolution is separable from extraction: did the run emit ANY mention that
    # normalises to one of this entry's names?
    resolved = any(n.casefold() in mentions for n in names)

    if not reachable:
        bound, why = "ACQUISITION", "no as-of-eligible CT.gov record mentions the entry"
    elif not survived_policy:
        bound, why = "POLICY_FILTER", "all matching trials removed by run policy before extraction"
    elif not extracted:
        drops = collections.Counter(led[n]["primary"] for n in ncts if n in led)
        bound, why = "EXTRACTION", f"trials survived policy but no asset name extracted: {dict(drops)}"
    elif not identified:
        bound = "IDENTITY_BINDING" if resolved else "IDENTITY_RESOLUTION"
        why = ("molecule extracted and a mention emitted, but no mention binds to this entry's "
               "exact alias set" if resolved else "extracted, but no emitted mention matches any alias")
    else:
        bound, why = "NONE", "identified"

    rows.append({"benchmark_id": b, "gold_entry": g["canonical_asset"],
                 "source": "V1" if b in roles and roles[b]["target_relevance"] == "PDCD1_MATCH" else "V2",
                 "reachable": reachable, "retrieved": retrieved,
                 "survived_policy": survived_policy, "asset_name_extracted": extracted,
                 "identity_resolved": resolved, "final_identified": identified,
                 "first_failure_boundary": bound, "reason": why,
                 "n_ctgov_records": len(ncts)})

with open("confirmed_asset_audit.jsonl", "w") as fh:
    for r in rows:
        fh.write(json.dumps(r) + "\n")

ok = [r for r in rows if r["final_identified"]]
bad = [r for r in rows if not r["final_identified"]]
print(f"confirmed PDCD1 assets: {len(rows)}   identified: {len(ok)}   missed: {len(bad)}\n")
print(f"{'gold_entry':58} {'src':4} {'rch':4}{'ret':4}{'pol':4}{'ext':4}{'res':4} boundary")
for r in rows:
    f = lambda x: " Y  " if x else " .  "
    print(f"{r['gold_entry'][:57]:58} {r['source']:4} {f(r['reachable'])}{f(r['retrieved'])}"
          f"{f(r['survived_policy'])}{f(r['asset_name_extracted'])}{f(r['identity_resolved'])} "
          f"{r['first_failure_boundary']}")
print("\n=== the misses ===")
for r in bad:
    print(f"\n{r['gold_entry']}  [{r['source']}]  boundary={r['first_failure_boundary']}")
    print(f"  ctgov records: {r['n_ctgov_records']}   {r['reason']}")
print("\nboundary counts:", dict(collections.Counter(r["first_failure_boundary"] for r in rows)))
