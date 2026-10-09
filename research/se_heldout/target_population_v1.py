"""TARGET_RECOGNITION_GENERALIZATION_DIAGNOSIS v1 offline population study (no behaviour change).

Frozen sample: every 40th target (sorted by canonical id) of the pinned snapshot's known_targets(),
using its canonical symbol and its first non-symbol alias. Each name is put in fixed query frames
and parsed with the current parser. Negative controls use the same frames.
"""
import json, sys, hashlib
from collections import Counter
from bve.se.ontology.targets import known_targets, ontology_version
from bve.se.intent.parser import parse_query

FRAMES = {
    "bare": "Find clinical-stage {} therapies for cancer.",
    "directed": "Find clinical-stage {}-directed therapies for cancer.",
    "targeting": "Find clinical-stage {}-targeting therapies for cancer.",
    "blocking": "Find clinical-stage {}-blocking antibodies for cancer.",
    "anti": "Find clinical-stage anti-{} antibodies for cancer.",
    "inhibitors": "Find clinical-stage {} inhibitors for cancer.",
}
NEGATIVES = ["patient", "therapy", "survival", "antibody", "bispecific", "CAR-T", "small molecule",
             "lung cancer", "lupus", "myeloma", "inflammation", "placebo", "dose", "biomarker",
             "chemotherapy", "remission", "cytokine", "receptor", "kinase", "protein"]

def recognized(q):
    i = parse_query(q)
    return sorted(t.canonical_id for t in i.targets)

def main():
    kt = sorted(known_targets())
    sample = kt[::40]
    rows = []
    for cid, aliases in sample:
        sym = cid.split(":", 1)[-1]
        alt = next((a for a in aliases if a.casefold() != sym.casefold() and len(a) <= 12 and " " not in a), None)
        for label, name in (("symbol", sym), ("alias", alt)):
            if not name: continue
            for f, tmpl in FRAMES.items():
                got = recognized(tmpl.format(name))
                rows.append({"target": sym, "form": label, "name": name, "frame": f, "got": got, "hit": sym in got})
    neg = []
    for n in NEGATIVES:
        for f, tmpl in FRAMES.items():
            got = recognized(tmpl.format(n))
            neg.append({"name": n, "frame": f, "got": got})
    by = Counter(); tot = Counter()
    for r in rows:
        tot[(r["form"], r["frame"])] += 1; by[(r["form"], r["frame"])] += r["hit"]
    print("ontology", ontology_version(), "| sample targets", len(sample))
    for k in sorted(tot): print(f"  {k[0]:6} {k[1]:10} recognized {by[k]}/{tot[k]} = {by[k]/tot[k]:.2f}")
    fp = [n for n in neg if n["got"]]
    print("negative controls producing a target:", len(fp), "of", len(neg))
    for n in fp: print("   ", n)
    blob = json.dumps({"rows": rows, "neg": neg}, sort_keys=True)
    open("research/se_heldout/target_population_v1.json", "w").write(blob)
    print("sha256", hashlib.sha256(blob.encode()).hexdigest())

if __name__ == "__main__":
    main()
