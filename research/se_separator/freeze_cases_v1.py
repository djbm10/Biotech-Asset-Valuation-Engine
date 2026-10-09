"""Freeze DUAL_TARGET_SEPARATOR_SAFETY v1 cases at the pre-fix parser (no behaviour change).

Cases: every (separator name, affix wrapper) of the frozen affix v2 population, with the bare
parse and the current affixed parse, classified lost / different / gained / ambiguity_changed /
equal. Also the parse of every affix-population name in the bare frame (no-regression set) and
of a frozen dual-target control set.
"""
import json, hashlib
from bve.se.intent.parser import parse_query, _TARGET_JOIN

def parse(q):
    i = parse_query(q)
    return {"targets": sorted(t.canonical_id for t in i.targets), "operator": i.target_operator.value,
            "ambiguous": sorted(",".join(sorted(s.candidates)) for s in i.spans if s.kind.name == "AMBIGUOUS_TARGET")}

WRAP = ["{}-directed", "{}-targeting", "{}-blocking", "anti-{}"]
CONTROLS = [
    "Find clinical-stage dual CD19/BCMA therapies for autoimmune disease with human efficacy.",
    "Find clinical-stage CD19/BCMA CAR-T therapies for lupus.",
    "Find clinical-stage CD19xBCMA bispecifics for myeloma.",
    "Find clinical-stage CD19×CD22 CAR-T cells for leukemia.",
    "Find clinical-stage CD3/CD20 bispecific antibodies for lymphoma.",
    "Find clinical-stage CD19/CD22/CD20 CAR-T for lymphoma.",
    "Find clinical-stage CD19 or BCMA CAR-T for lupus.",
    "Find clinical-stage CD19 cell therapies for relapsed or refractory B-cell lymphoma.",
    "Find clinical-stage KRAS G12C inhibitors for non-small cell lung cancer.",
    "Find clinical-stage TL1A antibodies for ulcerative colitis.",
    "Find clinical-stage CD19/CAR therapies for lymphoma.",
]
pop = json.load(open("research/se_heldout/affix_population_v2.json"))
cases = []
for name in pop["names"]:
    if not _TARGET_JOIN.search(name):
        continue
    b = pop["bare"][name]
    for w in WRAP:
        got = parse(f"Find clinical-stage {w.format(name)} therapies for cancer.")
        got_c = {"targets": got["targets"], "ambiguous": got["ambiguous"]}
        kind = ("equal" if got_c == b else "lost" if b["targets"] and not got["targets"] else
                "gained" if got["targets"] and not b["targets"] else
                "different" if got["targets"] != b["targets"] else "ambiguity_changed")
        cases.append({"name": name, "wrapper": w, "bare": b, "affixed_before": got_c, "kind": kind})
out = {"cases": cases, "controls": {q: parse(q) for q in CONTROLS}}
blob = json.dumps(out, sort_keys=True)
open("research/se_separator/cases_v1.json", "w").write(blob)
from collections import Counter
print(Counter(c["kind"] for c in cases), "| sha256", hashlib.sha256(blob.encode()).hexdigest())
for q, v in out["controls"].items(): print(v["targets"], v["operator"], v["ambiguous"], "|", q)
