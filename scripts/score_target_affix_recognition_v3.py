"""Score TARGET_AFFIX_RECOGNITION v3 (AV1-AV5) against the frozen v3 population."""
import json
from bve.se.intent.parser import parse_query

WRAP = {"directed": "{}-directed", "targeting": "{}-targeting", "blocking": "{}-blocking", "anti": "anti-{}"}
EXTRA_NEG = ["anti-inflammatory", "anti-tumor", "anti-cancer", "tumor-directed", "cancer-targeting", "cell-directed",
             "T-cell-directed", "antibody-directed", "drug-binding", "disease-specific", "patient-specific",
             "B-cell-directed", "anti-drug", "liver-targeted"]
V1_FRAMES = {"bare": "Find clinical-stage {} therapies for cancer.", "directed": "Find clinical-stage {}-directed therapies for cancer.",
             "targeting": "Find clinical-stage {}-targeting therapies for cancer.", "blocking": "Find clinical-stage {}-blocking antibodies for cancer.",
             "anti": "Find clinical-stage anti-{} antibodies for cancer.", "inhibitors": "Find clinical-stage {} inhibitors for cancer."}


def parse(q):
    i = parse_query(q)
    return {"targets": sorted(t.canonical_id for t in i.targets),
            "ambiguous": sorted(",".join(sorted(s.candidates)) for s in i.spans if s.kind.name == "AMBIGUOUS_TARGET")}


pop = json.load(open("research/se_heldout/affix_population_v3.json"))
bad = []
n = 0
for name in pop["names"]:
    for w, tmpl in WRAP.items():
        n += 1
        got = parse(f"Find clinical-stage {tmpl.format(name)} therapies for cancer.")
        if got != pop["bare"][name]:
            bad.append((name, w, pop["bare"][name], got))
print(f"AV1 parity: {not bad} ({n - len(bad)}/{n}) mismatches={len(bad)}")
for b in bad[:20]:
    print("   ", b)
v1 = json.load(open("research/se_heldout/target_population_v1.json"))
neg = [(r["name"], r["frame"]) for r in v1["neg"]]
fp = [(nm, f) for nm, f in neg if parse(V1_FRAMES[f].format(nm))["targets"]]
fp += [(nm, "extra") for nm in EXTRA_NEG if parse(f"Find clinical-stage {nm} therapies for cancer.")["targets"]]
print(f"AV2 negative controls with a target: {len(fp)} of {len(neg) + len(EXTRA_NEG)} {fp}")
before = json.load(open("research/se_heldout/affix_controls_before_v1.json"))
after = json.load(open("research/se_heldout/affix_controls_after_v3.json"))
t = lambda d, k: [x["canonical_id"] for x in d[k]["targets"]]  # noqa: E731
print(f"AV3 H1={t(after, 'H1')} H3={t(after, 'H3')} H5 refused={t(after, 'H5') == []} H2 unchanged={before['H2'] == after['H2']}")
print("AV4 identical:", {k: before[k] == after[k] for k in ("TAC01", "mint5", "H2", "H4")})
amb = {k: (t(after, k), [s["candidates"] for s in after[k]["spans"] if s["kind"] == "AMBIGUOUS_TARGET"]) for k in ("AMB1", "AMB2")}
print(f"AV5 ambiguous stay ambiguous: {all(not v[0] and v[1] for v in amb.values())} {amb}")
