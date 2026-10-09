"""Score DUAL_TARGET_SEPARATOR_SAFETY v2 (DV1-DV6) against the frozen authority labels."""
import json
from collections import Counter
from bve.se.intent.parser import parse_query, _TARGET_JOIN

FRAME = "Find clinical-stage {} therapies for cancer."


def parse(q):
    i = parse_query(q)
    return {"targets": sorted(t.canonical_id for t in i.targets), "operator": i.target_operator.value,
            "ambiguous": sorted(",".join(sorted(s.candidates)) for s in i.spans if s.kind.name == "AMBIGUOUS_TARGET")}


lab = json.load(open("research/se_separator/labels_v2.json"))
dv1, dv2, dv3, dv5 = [], [], [], []
after = Counter()
for c in lab["cases"]:
    got = parse(FRAME.format(c["token"]))
    g, e = set(got["targets"]), set(c["expected"])
    if not g <= e:
        dv1.append((c["kind"], c["token"], sorted(e), sorted(g)))
    if c["label"] == "WHOLE" and g != e:
        dv2.append((c["token"], sorted(e), sorted(g)))
    if c["label"] == "DUAL" and g != e:
        dv3.append((c["token"], sorted(e), sorted(g)))
    if not set(got["ambiguous"]) <= set(c["before"]["ambiguous"]):
        dv5.append((c["token"], got["ambiguous"]))
    after[(c["kind"], c["label"], "wrong" if g - e else "correct" if g == e else "missing")] += 1
print(f"DV1 zero wrong targets: {not dv1} violations={len(dv1)} {dv1[:6]}")
print(f"DV2 WHOLE kept: {not dv2} violations={len(dv2)} {dv2[:6]}")
print(f"DV3 DUAL exact: {not dv3} {dv3[:6]}")
print("   classes after:", dict(after))
ctl = [q for q, v in lab["controls"].items() if parse(q) != v]
before = json.load(open("research/se_heldout/affix_controls_before_v1.json"))
Q = {"TAC01": "Find clinical-stage CD19 cell therapies for relapsed or refractory B-cell lymphoma.",
     "mint5": "Find clinical-stage dual CD19/BCMA therapies for autoimmune disease with human efficacy.",
     "H1": "Find clinical-stage GPRC5D-directed therapies for relapsed or refractory multiple myeloma.",
     "H2": "Find clinical-stage KRAS G12C inhibitors for non-small cell lung cancer.",
     "H3": "Find clinical-stage FcRn-blocking antibodies for generalized myasthenia gravis.",
     "H4": "Find clinical-stage TL1A antibodies for ulcerative colitis.",
     "H5": "Find clinical-stage Claudin 18.2-directed therapies for gastric cancer."}
full = [k for k, q in Q.items() if json.loads(parse_query(q).model_dump_json()) != before[k]]
print(f"DV4 controls identical: {not ctl and not full} control diffs={ctl} full-intent diffs={full}")
print(f"DV5 ambiguous never gains: {not dv5} {dv5[:5]}")
pop = json.load(open("research/se_heldout/affix_population_v2.json"))
reg = [n for n in pop["names"] if not _TARGET_JOIN.search(n)
       and {k: v for k, v in parse(FRAME.format(n)).items() if k != "operator"} != pop["bare"][n]]
print(f"DV6 non-separator names unchanged: {not reg} changed={len(reg)} {reg[:5]}")
