"""Freeze the TARGET_AFFIX_RECOGNITION v2 population and its bare-frame baseline (before any code).

Population = (a) a NEW sample: every 40th target starting at offset 20 (disjoint from v1's
offset 0), symbol + first short alias; (b) every name in the v1 sample (regression);
(c) every snapshot alias (<=24 chars) containing a dual-target separator or a parenthesis,
the two classes v1 broke on. Baseline = the parse of the bare frame at the pre-v2 commit.
"""
import json, hashlib, re
from bve.se.ontology.targets import known_targets, ontology_version
from bve.se.intent.parser import parse_query, _TARGET_JOIN

def parse(q):
    i = parse_query(q)
    return {"targets": sorted(t.canonical_id for t in i.targets),
            "ambiguous": sorted(",".join(sorted(s.candidates)) for s in i.spans if s.kind.name == "AMBIGUOUS_TARGET")}

BARE = "Find clinical-stage {} therapies for cancer."
kt = sorted(known_targets())
names = set()
for cid, aliases in kt[20::40]:
    sym = cid.split(":", 1)[-1]; names.add(sym)
    alt = next((a for a in aliases if a.casefold() != sym.casefold() and len(a) <= 12 and " " not in a), None)
    if alt: names.add(alt)
v1 = json.load(open("research/se_heldout/target_population_v1.json"))
names |= {r["name"] for r in v1["rows"]}
for cid, aliases in kt:
    for a in aliases:
        if len(a) <= 24 and " " not in a and (_TARGET_JOIN.search(a) or "(" in a or ")" in a):
            names.add(a)
names = sorted(names)
pop = {"ontology": ontology_version(), "names": names, "bare": {n: parse(BARE.format(n)) for n in names}}
blob = json.dumps(pop, sort_keys=True)
open("research/se_heldout/affix_population_v2.json", "w").write(blob)
print(len(names), "names | sha256", hashlib.sha256(blob.encode()).hexdigest())
print("separator names", sum(1 for n in names if _TARGET_JOIN.search(n)), "| paren names", sum(1 for n in names if "(" in n or ")" in n))
