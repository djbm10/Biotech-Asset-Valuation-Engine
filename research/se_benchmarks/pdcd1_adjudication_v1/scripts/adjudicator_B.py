"""Adjudicator B -- registry-evidence-first.

Starts from how the string behaves in the frozen CT.gov corpus: something registered as an
intervention is an asset regardless of whether an authority curated it, and something that
appears only in prose is not. Target relevance is re-derived from the raw binding records
rather than read off the precomputed verdict, so a mistake in the verdict computation does
not propagate into both adjudications. Sees no pipeline outcome.
"""
import json, re
from collections import Counter

DISEASE = re.compile(
    r"\b(tumou?rs?|carcinoma|cancer|melanoma|lymphoma|leukemia|myeloma|sarcoma|"
    r"mutant|amplified|neoplasms?)\b", re.I)
VAGUE = re.compile(
    r"\b(investigational|computationally[- ]designed|targeted antibody[- ]drug conjugate|"
    r"anti[- ]tumor tablet|tumou?r[- ]associated antigen|autologous|personalized)\b", re.I)
GENERIC_CLASS = re.compile(
    r"^(pd-1|pd-l1)?[\s/x]*(bispecific|trispecific|monoclonal)?\s*(antibody|virus|vaccine|"
    r"agonist|therapy|inhibitor|decoction)\b", re.I)
COMBI_WORDS = re.compile(r"coformulat|co-formulat|\bplus\b|\bconjugated to\b|\bwith\b.*\badjuvant\b", re.I)


def adjudicate(rec):
    entry, a = rec["gold_entry"], rec["authority"]
    ev, reasons = [], []

    # --- registry behaviour first ---
    as_intervention, as_other_name, only_title = [], [], []
    for term, exhibits in rec["ctgov_exhibits"].items():
        for h in exhibits:
            if h["field"] == "interventions":
                as_intervention.append(h)
            elif h["field"] == "other_names":
                as_other_name.append(h)
            else:
                only_title.append(h)
    for h in (as_intervention + as_other_name)[:6]:
        ev.append(f"{h['nct']}:{h['field']}={h['evidence']!r}")

    combi = bool(COMBI_WORDS.search(entry)) or "COFORMULATION_OR_COMBINATION_STRING" in a["flags"]

    if combi:
        role, conf = "COMBINATION_REGIMEN", 0.85
        reasons.append("combination/coformulation language")
    elif as_intervention:
        role, conf = "ASSET", 0.9
        reasons.append(f"registered as a trial intervention in {len(as_intervention)} record(s)")
    elif as_other_name:
        role, conf = "ASSET", 0.75
        reasons.append("appears as an intervention other_name (registry alias)")
    elif DISEASE.search(entry) and not re.search(r"[a-z]{4,}(mab|nib|parib)\b", entry, re.I):
        role, conf = "INDICATION", 0.75
        reasons.append("disease/population string with no agent token")
    elif VAGUE.search(entry) or GENERIC_CLASS.match(entry.strip()):
        role, conf = "PLACEHOLDER_DESCRIPTION", 0.65
        reasons.append("descriptive, not a named product")
    elif a["bindings"]:
        role, conf = "ASSET", 0.7
        reasons.append("absent from corpus but curated as a molecule")
    else:
        role, conf = "UNCERTAIN", 0.3
        reasons.append("no registry evidence and no authority record")

    # --- target relevance re-derived from raw bindings ---
    if a["agreement"] == "UNCERTAIN_A33":
        target, tconf = "UNCERTAIN", 0.9
        reasons.append("A3.3 withheld; not recovered from context")
    else:
        syms = Counter(b["target_symbol"] for b in a["bindings"] if b["target_symbol"])
        if "PDCD1" in syms:
            target, tconf = "PDCD1_MATCH", 0.95
            mech = next((b["mechanism"] for b in a["bindings"] if b["target_symbol"] == "PDCD1"), None)
            ev.append(f"binding: PDCD1 -- {mech}")
        elif syms:
            target, tconf = "NON_PDCD1", 0.9
            ev.append(f"binding targets: {sorted(syms)[:4]}")
        elif a["bindings"]:
            target, tconf = "NON_PDCD1", 0.6
            reasons.append("curated molecule with no PDCD1 binding recorded")
        else:
            target, tconf = "UNCERTAIN", 0.4
            reasons.append("no binding record")

    if as_intervention:
        trial_role = "INTERVENTION"
    elif as_other_name:
        trial_role = "INTERVENTION_ALIAS"
    elif only_title:
        trial_role = "MENTIONED_ONLY"
    else:
        trial_role = "ABSENT_FROM_CORPUS"

    return {
        "benchmark_id": rec["benchmark_id"], "gold_entry": entry,
        "entity_role": role, "target_relevance": target, "trial_role": trial_role,
        "confidence": round(min(conf, tconf), 2),
        "evidence": ev[:8], "reason": "; ".join(reasons), "adjudicator": "B",
    }


rows = [json.loads(l) for l in open("blinded_evidence.jsonl")]
with open("adjudication_B.jsonl", "w") as fh:
    for r in rows:
        fh.write(json.dumps(adjudicate(r), sort_keys=True) + "\n")
out = [json.loads(l) for l in open("adjudication_B.jsonl")]
print("B entity_role:", dict(Counter(r["entity_role"] for r in out)))
print("B target:", dict(Counter(r["target_relevance"] for r in out)))
print("B trial_role:", dict(Counter(r["trial_role"] for r in out)))
