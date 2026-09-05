"""Fix the V2 subject set from V1 output alone, before any entry is researched.

The set is exactly the V1 ASSET + UNCERTAIN entries; membership is derived, never chosen.
"""
import csv, json, pathlib

V1 = pathlib.Path("/home/djmann/staging/pdcd1_adjudication_v1")
M8 = pathlib.Path("/home/djmann/staging/pdcd1_baseline/pdcd1_reference_universe_m8v2.csv")

roles = {json.loads(l)["benchmark_id"]: json.loads(l) for l in open(V1 / "gold_entry_roles.jsonl")}
subtype = {json.loads(l)["benchmark_id"]: json.loads(l) for l in open(V1 / "asset_uncertain_subtypes.jsonl")}
gold = {r["benchmark_id"]: r for r in csv.DictReader(open(M8))}

TRACK_B = {"CELL_THERAPY_VACCINE_OR_CONSTRUCT", "BIOSIMILAR_CANDIDATE",
           "NON_SMALL_MOLECULE_TRADITIONAL_MEDICINE"}

rows = []
for bid, r in roles.items():
    if r["entity_role"] != "ASSET" or r["target_relevance"] != "UNCERTAIN":
        continue
    st = subtype[bid]["uncertainty_subtype"]
    rows.append({
        "benchmark_id": bid,
        "gold_entry": gold[bid]["canonical_asset"],
        "aliases": [a for a in (gold[bid]["aliases"] or "").split("|") if a],
        "v1_entity_role": r["entity_role"],
        "v1_target_relevance": r["target_relevance"],
        "v1_subtype": st,
        "track": "B" if st in TRACK_B else "A",
    })

rows.sort(key=lambda x: (x["track"], x["v1_subtype"], x["gold_entry"].casefold()))
with open("v2_subject_set.jsonl", "w") as fh:
    for r in rows:
        fh.write(json.dumps(r) + "\n")

by = {}
for r in rows:
    by.setdefault((r["track"], r["v1_subtype"]), []).append(r)
for (t, s), v in sorted(by.items()):
    print(f"{t}  {s:41} {len(v):>3}")
print(f"{'':3} {'TOTAL':41} {len(rows):>3}")
