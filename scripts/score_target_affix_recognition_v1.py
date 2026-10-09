"""Score TARGET_AFFIX_RECOGNITION v1 (AR1-AR5) offline."""
import json
from bve.se.intent.parser import parse_query

EXTRA_NEG = ["anti-inflammatory", "anti-tumor", "anti-cancer", "tumor-directed", "cancer-targeting", "cell-directed",
             "T-cell-directed", "antibody-directed", "drug-binding", "disease-specific", "patient-specific",
             "B-cell-directed", "anti-drug", "liver-targeted"]
FRAMES = {"bare": "Find clinical-stage {} therapies for cancer.", "directed": "Find clinical-stage {}-directed therapies for cancer.",
          "targeting": "Find clinical-stage {}-targeting therapies for cancer.", "blocking": "Find clinical-stage {}-blocking antibodies for cancer.",
          "anti": "Find clinical-stage anti-{} antibodies for cancer.", "inhibitors": "Find clinical-stage {} inhibitors for cancer."}
tg = lambda q: sorted(t.canonical_id for t in parse_query(q).targets)  # noqa: E731

base = json.load(open("research/se_heldout/target_population_v1.json"))
pairs = {(r["target"], r["form"], r["name"]) for r in base["rows"]}
bad = []
n = 0
for target, form, name in sorted(pairs):
    bare = tg(FRAMES["bare"].format(name))
    for f in ("directed", "targeting", "blocking", "anti"):
        n += 1
        got = tg(FRAMES[f].format(name))
        if got != bare:
            bad.append((name, f, bare, got))
print(f"AR1 affixed == bare: {not bad} ({n - len(bad)}/{n}); mismatches={len(bad)}")
for b in bad[:15]:
    print("   ", b)
neg = [(r["name"], r["frame"]) for r in base["neg"]]
fp = [(nm, f, tg(FRAMES[f].format(nm))) for nm, f in neg if tg(FRAMES[f].format(nm))]
fp += [(nm, "extra", tg(f"Find clinical-stage {nm} therapies for cancer.")) for nm in EXTRA_NEG if tg(f"Find clinical-stage {nm} therapies for cancer.")]
print(f"AR2 negative controls producing a target: {len(fp)} of {len(neg) + len(EXTRA_NEG)} {fp}")
before = json.load(open("research/se_heldout/affix_controls_before_v1.json"))
after = json.load(open("research/se_heldout/affix_controls_after_v1.json"))
t = lambda d, k: [x["canonical_id"] for x in d[k]["targets"]]  # noqa: E731
print(f"AR3 H1={t(after,'H1')} H3={t(after,'H3')} H5 refused={t(after,'H5') == []}")
print(f"AR4 identical parse for controls: " + str({k: before[k] == after[k] for k in ('TAC01', 'mint5', 'H2', 'H4')}))
amb = {k: (t(after, k), [s["candidates"] for s in after[k]["spans"] if s["kind"] == "AMBIGUOUS_TARGET"]) for k in ("AMB1", "AMB2")}
print(f"AR5 ambiguous affixed forms fail closed: {all(not v[0] and v[1] for v in amb.values())} {amb}")
