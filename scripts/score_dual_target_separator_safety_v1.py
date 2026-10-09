"""Score DUAL_TARGET_SEPARATOR_SAFETY v1 (SS1-SS5) against the frozen cases."""
import json
from collections import Counter
from bve.se.intent.parser import parse_query


def parse(q):
    i = parse_query(q)
    return {"targets": sorted(t.canonical_id for t in i.targets), "operator": i.target_operator.value,
            "ambiguous": sorted(",".join(sorted(s.candidates)) for s in i.spans if s.kind.name == "AMBIGUOUS_TARGET")}


frozen = json.load(open("research/se_separator/cases_v1.json"))
pop = json.load(open("research/se_heldout/affix_population_v2.json"))
ss1 = []
ss3 = []
ss5 = []
after_kind = Counter()
for c in frozen["cases"]:
    got = parse(f"Find clinical-stage {c['wrapper'].format(c['name'])} therapies for cancer.")
    if not set(got["targets"]) <= set(c["bare"]["targets"]):
        ss1.append((c["name"], c["wrapper"], c["bare"]["targets"], got["targets"]))
    if c["kind"] == "equal" and {"targets": got["targets"], "ambiguous": got["ambiguous"]} != c["affixed_before"]:
        ss3.append((c["name"], c["wrapper"]))
    if not set(got["ambiguous"]) <= set(c["affixed_before"]["ambiguous"]):
        ss5.append((c["name"], c["wrapper"], got["ambiguous"]))
    b = c["bare"]
    gc = {"targets": got["targets"], "ambiguous": got["ambiguous"]}
    after_kind["equal" if gc == b else "lost" if b["targets"] and not got["targets"] else "gained" if got["targets"] and not b["targets"]
               else "different" if got["targets"] != b["targets"] else "ambiguity_changed"] += 1
print(f"SS1 affixed targets subset of bare: {not ss1} violations={len(ss1)} {ss1[:5]}")
print("   classes after fix:", dict(after_kind))
reg = [n for n in pop["names"] if {k: v for k, v in parse(f"Find clinical-stage {n} therapies for cancer.").items() if k != "operator"} != pop["bare"][n]]
print(f"SS2 bare parses unchanged: {not reg} ({len(pop['names']) - len(reg)}/{len(pop['names'])}) {reg[:5]}")
print(f"SS3 previously-equal cases unchanged: {not ss3} changed={len(ss3)} {ss3[:5]}")
ctl = {q: parse(q) == v for q, v in frozen["controls"].items()}
before = json.load(open("research/se_heldout/affix_controls_before_v1.json"))
from bve.se.intent.parser import parse_query as pq  # noqa: E402
import sys  # noqa: E402
sys.path.insert(0, "research/se_heldout")
QUERIES = {
    "TAC01": "Find clinical-stage CD19 cell therapies for relapsed or refractory B-cell lymphoma.",
    "mint5": "Find clinical-stage dual CD19/BCMA therapies for autoimmune disease with human efficacy.",
    "H1": "Find clinical-stage GPRC5D-directed therapies for relapsed or refractory multiple myeloma.",
    "H2": "Find clinical-stage KRAS G12C inhibitors for non-small cell lung cancer.",
    "H3": "Find clinical-stage FcRn-blocking antibodies for generalized myasthenia gravis.",
    "H4": "Find clinical-stage TL1A antibodies for ulcerative colitis.",
    "H5": "Find clinical-stage Claudin 18.2-directed therapies for gastric cancer.",
}
full = {k: json.loads(pq(q).model_dump_json()) == before[k] for k, q in QUERIES.items()}
print(f"SS4 controls identical: {all(ctl.values())} {[q for q, ok in ctl.items() if not ok]} | full-intent identical: {full}")
print(f"SS5 ambiguous sets never gain a member: {not ss5} {ss5[:5]}")
