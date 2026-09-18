"""Precision control: how often does a PDCD1-scoped run surface a confirmed non-PDCD1 asset?

The run is target-scoped, so every asset it identifies is implicitly offered as PDCD1-relevant.
Identifying a confirmed NON_PDCD1 entry is therefore a candidate false positive -- an upper
bound, because a PD-1 combination trial legitimately contains backbone and comparator drugs.
"""
import csv, json, pathlib, collections

B = pathlib.Path("/home/djmann/staging/pdcd1_baseline")
V1 = pathlib.Path("/home/djmann/staging/pdcd1_adjudication_v1")
ident = set(json.load(open(B / "diag/b6_denominator_members.json"))["member"]["identified_asset"])
gold = {r["benchmark_id"]: r["canonical_asset"] for r in csv.DictReader(open(B / "pdcd1_reference_universe_m8v2.csv"))}
roles = {json.loads(l)["benchmark_id"]: json.loads(l) for l in open(V1 / "gold_entry_roles.jsonl")}
v2 = {json.loads(l)["benchmark_id"]: json.loads(l) for l in open("v2_annotation_layer.jsonl")}

neg = {b for b, r in roles.items()
       if r["entity_role"] == "ASSET" and r["target_relevance"] == "NON_PDCD1"}
neg |= {b for b, r in v2.items() if r["target_relevance_v2"] == "NON_PDCD1"}
pos = ({b for b, r in roles.items()
        if r["entity_role"] == "ASSET" and r["target_relevance"] == "PDCD1_MATCH"}
       | {b for b, r in v2.items() if r["target_relevance_v2"] == "PDCD1_MATCH"})

fp = sorted(neg & ident, key=lambda b: gold[b].casefold())
tp = pos & ident
print(f"confirmed NON_PDCD1 assets (V1 106 + V2 27): {len(neg)}")
print(f"  surfaced by the PDCD1-scoped run: {len(fp)}  ({len(fp)/len(neg):.1%})")
print(f"confirmed PDCD1 assets: {len(pos)}   identified: {len(tp)}  ({len(tp)/len(pos):.1%})")
print(f"\nupper-bound precision on confirmed entries: {len(tp)}/{len(tp)+len(fp)} = "
      f"{len(tp)/(len(tp)+len(fp)):.1%}")

# PD-L1 drugs are the sharpest trap: same pathway, different gene.
PDL1 = ("durvalumab", "atezolizumab", "avelumab", "adebrelimab", "sugemalimab", "imfinzi",
        "tecentriq", "bavencio", "pumitamig", "bnt327", "socazolimab", "envafolimab")
traps = [b for b in fp if any(k in gold[b].casefold() for k in PDL1)]
print(f"\nof which PD-L1 / pathway-adjacent traps: {len(traps)}")
for b in traps:
    print(f"  {gold[b]}")
print(f"\nall {len(fp)} surfaced confirmed negatives:")
for b in fp:
    print(f"  {gold[b]}")
json.dump({"n_confirmed_negatives": len(neg), "surfaced": [gold[b] for b in fp],
           "n_surfaced": len(fp), "pdl1_traps": [gold[b] for b in traps],
           "upper_bound_precision": len(tp) / (len(tp) + len(fp))},
          open("v2_precision_negatives.json", "w"), indent=1)
