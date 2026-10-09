"""Freeze DUAL_TARGET_SEPARATOR_SAFETY v3 labels from INDEPENDENT authority resolution.

For every case (one separator-bearing token T inside the fixed frame), the expected target set
E is derived without the parser:
  1. whole: resolve_target(_clean(T)) is RESOLVED -> E = {that target}          [label WHOLE]
  2. dual : else every separator piece of T resolves (RESOLVED or AMBIGUOUS)
            -> E = the RESOLVED pieces' targets                                  [label DUAL]
  3. none : else E = {}                                                          [label NONE]
Cases: every bare population name containing a separator, every frozen v1 affixed case, and the
frozen v1 controls. The current (pre-fix) parse is stored and classified against E.
"""
import json, hashlib, re
from collections import Counter
from bve.se.ontology.targets import resolve_target
from bve.se.intent.parser import parse_query, _TARGET_JOIN, _tokenize, _clean, _STOPWORDS
from bve.se.ontology.resolver import ResolutionStatus

def sym(r): return r.entity.canonical_symbol

def expected(token):
    whole = resolve_target(_clean(token))
    if whole is not None and whole.status is ResolutionStatus.RESOLVED:
        return "WHOLE", [sym(whole)]
    pieces = [_clean(p) for p, _, _ in _tokenize(token)]
    rs = [resolve_target(p) if p else None for p in pieces]
    valid = lambda p: len(p) >= 2 and p.casefold() not in _STOPWORDS  # noqa: E731  (v3: a lone character or stopword is not a component)
    if rs and all(r is not None and valid(p) and r.status in (ResolutionStatus.RESOLVED, ResolutionStatus.AMBIGUOUS) for p, r in zip(pieces, rs)):
        return "DUAL", sorted({sym(r) for r in rs if r.status is ResolutionStatus.RESOLVED})
    return "NONE", []

def parse(q):
    i = parse_query(q)
    return {"targets": sorted(t.canonical_id for t in i.targets),
            "ambiguous": sorted(",".join(sorted(s.candidates)) for s in i.spans if s.kind.name == "AMBIGUOUS_TARGET")}

FRAME = "Find clinical-stage {} therapies for cancer."
pop = json.load(open("research/se_heldout/affix_population_v2.json"))
v1 = json.load(open("research/se_separator/cases_v1.json"))
cases = []
for n in pop["names"]:
    if _TARGET_JOIN.search(n):
        lab, e = expected(n)
        cases.append({"kind": "bare", "token": n, "label": lab, "expected": e, "before": pop["bare"][n]})
for c in v1["cases"]:
    tok = c["wrapper"].format(c["name"])
    lab, e = expected(tok)
    cases.append({"kind": "affixed", "token": tok, "label": lab, "expected": e, "before": c["affixed_before"]})
def cls(c):
    got = set(c["before"]["targets"]); E = set(c["expected"])
    return "wrong" if got - E else "correct" if got == E else "missing"
for c in cases: c["before_class"] = cls(c)
out = {"cases": cases, "controls": v1["controls"]}
blob = json.dumps(out, sort_keys=True)
open("research/se_separator/labels_v3.json", "w").write(blob)
print(len(cases), "cases | sha256", hashlib.sha256(blob.encode()).hexdigest())
print(Counter((c["kind"], c["label"], c["before_class"]) for c in cases))
