"""Recompute the five reported figures after V2 reconciliation.

V1 numbers are recomputed from V1 artifacts and reported unchanged alongside V2, never
replaced by them. Strict M8 recall keeps its permanent n=224 denominator.
"""
import json, pathlib, collections

V1 = pathlib.Path("/home/djmann/staging/pdcd1_adjudication_v1")
MEM = json.load(open("/home/djmann/staging/pdcd1_baseline/diag/b6_denominator_members.json"))["member"]
ident, reach = set(MEM["identified_asset"]), set(MEM["as_of_eligible"])

roles = {json.loads(l)["benchmark_id"]: json.loads(l) for l in open(V1 / "gold_entry_roles.jsonl")}
v2 = {json.loads(l)["benchmark_id"]: json.loads(l) for l in open("v2_annotation_layer.jsonl")}

N_M8 = len(roles)
assert N_M8 == 224

v1_conf = {b for b, r in roles.items()
           if r["entity_role"] == "ASSET" and r["target_relevance"] == "PDCD1_MATCH"}
v2_new = {b for b, r in v2.items() if r["target_relevance_v2"] == "PDCD1_MATCH"}
v2_conf = v1_conf | v2_new
still_unc = {b for b, r in v2.items() if r["target_relevance_v2"] == "UNCERTAIN_V2"}


def rec(s):
    return len(s & ident), len(s), (len(s & ident) / len(s) if s else float("nan"))


rows = [
    ("strict M8 recall (permanent n=224)", (len(ident), N_M8, len(ident) / N_M8)),
    ("V1 confirmed PDCD1 asset recall", rec(v1_conf)),
    ("V2 confirmed PDCD1 asset recall", rec(v2_conf)),
    ("reachable V2 confirmed PDCD1 asset recall", rec(v2_conf & reach)),
]
print(f"{'figure':45} {'ident':>6} {'denom':>6} {'recall':>8}")
for name, (i, d, r) in rows:
    print(f"{name:45} {i:>6} {d:>6} {r:>8.1%}")

# Residual interval: best case every still-uncertain asset turns out not to be PDCD1;
# worst case every one of them is.
best_i, best_d, best = rec(v2_conf)
worst_i, worst_d, worst = rec(v2_conf | still_unc)
print(f"\nresidual uncertainty interval  [{worst:.1%}, {best:.1%}]"
      f"   (worst {worst_i}/{worst_d}, best {best_i}/{best_d})")
print(f"still UNCERTAIN_V2 after V2: {len(still_unc)}  (was 48 before V2)")

by = collections.Counter((r["track"], r["target_relevance_v2"]) for r in v2.values())
print(f"\n{'track':6} {'verdict':16} n")
for (t, v), n in sorted(by.items()):
    print(f"{t:6} {v:16} {n}")

ranks = collections.Counter(r["source_rank"] for r in v2.values() if r["source_rank"])
print(f"\nsource rank used (resolved entries only): {dict(sorted(ranks.items()))}")
ctg = [r for r in v2.values() if r.get("ctgov_only") and not r["unresolved"]]
print(f"resolved solely by CT.gov rank 5: {len(ctg)}")
for r in ctg:
    print(f"  {r['target_relevance_v2']:12} {r['entry']}")

json.dump({"figures": {n: {"identified": i, "denominator": d, "recall": r} for n, (i, d, r) in rows},
           "residual_interval": [worst, best],
           "still_uncertain": sorted(still_unc),
           "v2_new_pdcd1": sorted(v2_new),
           "ctgov_only_resolutions": [r["benchmark_id"] for r in ctg]},
          open("v2_denominators.json", "w"), indent=1)
