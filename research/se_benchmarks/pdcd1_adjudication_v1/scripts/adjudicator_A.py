"""Adjudicator A -- authority-first.

Starts from the frozen drug-target authority: an entry that resolves to a curated molecule
is an asset, and its target relevance is whatever the authority says. Registry evidence is
consulted only to place the entry's role within a trial. Sees no pipeline outcome.
"""
import json, re

ENTRY = "entity_role"

INDICATION = re.compile(
    r"\b(solid tumou?rs?|carcinoma|cancer|melanoma|lymphoma|leukemia|myeloma|sarcoma|"
    r"mutant|amplified|[-\s]positive|advanced|metastatic|refractory|relapsed)\b", re.I)
PLACEHOLDER = re.compile(
    r"\b(investigational|targeted antibody[- ]drug conjugate|anti[- ]tumor tablet|"
    r"computationally[- ]designed|tumou?r[- ]associated antigen)\b", re.I)
CLASS_ONLY = re.compile(
    r"\b(bispecific antibody|trispecific antibody|oncolytic virus|cancer vaccine|"
    r"monoclonal antibody|cell therapy|tumor[- ]infiltrating lymphocytes?|"
    r"agonist|adjuvant|chemotherapy)\b", re.I)
# A bare "/" is not a combination marker: M8 uses it inside parentheses to list aliases
# ("Toripalimab (JS001 / LOQTORZI)"). Only explicit combination language counts, plus the
# authority's own coformulation flag.
COMBINATION = re.compile(
    r"coformulat|co-formulat|\bplus\b|conjugated to|\band\b[^()]*\bchemotherapy\b|"
    r"[a-z]{4,}mab\s+and\s+[a-z]{4,}mab|[a-z]{4,}mab\s*/\s*[a-z]{4,}mab", re.I)
NAMED = re.compile(r"\b([a-z]{4,}(?:limab|zumab|ximab|umab|tinib|ciclib|parib|degib))\b", re.I)


def adjudicate(rec):
    a = rec["authority"]
    entry = rec["gold_entry"]
    flags = set(a["flags"])
    ev, reasons = [], []

    resolved = bool(a["bindings"])
    if resolved:
        ev.append(f"authority: {len(a['bindings'])} binding record(s), agreement={a['agreement']}")

    # entity_role
    if "COFORMULATION_OR_COMBINATION_STRING" in flags or COMBINATION.search(entry):
        role, conf = "COMBINATION_REGIMEN", 0.8
        reasons.append("string denotes a combination or coformulation")
    elif resolved:
        role, conf = "ASSET", 0.9
        reasons.append("resolves to a curated molecule in the authority")
    elif INDICATION.search(entry) and not NAMED.search(entry):
        role, conf = "INDICATION", 0.7
        reasons.append("disease/population language, no drug name")
    elif PLACEHOLDER.search(entry):
        role, conf = "PLACEHOLDER_DESCRIPTION", 0.7
        reasons.append("descriptive placeholder, not a named product")
    elif CLASS_ONLY.search(entry) and not NAMED.search(entry):
        role, conf = "MODALITY_CLASS", 0.6
        reasons.append("names a modality class, not a specific agent")
    elif NAMED.search(entry):
        role, conf = "ASSET", 0.55
        reasons.append("INN-stem drug name present but unresolved in authority")
    else:
        role, conf = "UNCERTAIN", 0.3
        reasons.append("unresolved and no decisive string signal")

    # target_relevance -- authority only; A3.3 withholding is honoured, not worked around
    if a["agreement"] == "UNCERTAIN_A33":
        target, tconf = "UNCERTAIN", 0.9
        reasons.append("A3.3: component-derived verdict withheld")
    elif a["open_targets_verdict"] == "PDCD1_MATCH" or a["chembl_verdict"] == "PDCD1_MATCH":
        target, tconf = "PDCD1_MATCH", 0.95
        ev.append("authority target_symbol=PDCD1")
    elif a["open_targets_verdict"] == "NON_PDCD1" or a["chembl_verdict"] == "NON_PDCD1":
        target, tconf = "NON_PDCD1", 0.9
        syms = sorted({b["target_symbol"] for b in a["bindings"] if b["target_symbol"]})
        ev.append(f"authority targets={syms[:4]}")
    else:
        target, tconf = "UNCERTAIN", 0.4
        reasons.append("no authority target record")

    # trial_role -- descriptive only; never allowed to change target_relevance
    types, hits = set(), 0
    for term, exhibits in rec["ctgov_exhibits"].items():
        for h in exhibits:
            hits += 1
            if h["intervention_type"]:
                types.add(h["intervention_type"])
            if len(ev) < 8 and h["field"] != "title":
                ev.append(f"{h['nct']}:{h['field']}={h['evidence']!r}")
    if not hits:
        trial_role = "ABSENT_FROM_CORPUS"
    elif types & {"DRUG", "BIOLOGICAL"}:
        trial_role = "INTERVENTION"
    else:
        trial_role = "MENTIONED_ONLY"

    return {
        "benchmark_id": rec["benchmark_id"], "gold_entry": entry,
        "entity_role": role, "target_relevance": target, "trial_role": trial_role,
        "confidence": round(min(conf, tconf), 2),
        "evidence": ev[:8], "reason": "; ".join(reasons),
        "adjudicator": "A",
    }


rows = [json.loads(l) for l in open("blinded_evidence.jsonl")]
with open("adjudication_A.jsonl", "w") as fh:
    for r in rows:
        fh.write(json.dumps(adjudicate(r), sort_keys=True) + "\n")
from collections import Counter
out = [json.loads(l) for l in open("adjudication_A.jsonl")]
print("A entity_role:", dict(Counter(r["entity_role"] for r in out)))
print("A target:", dict(Counter(r["target_relevance"] for r in out)))
print("A trial_role:", dict(Counter(r["trial_role"] for r in out)))
