"""Reconcile A and B into the frozen role annotation.

Reconciliation may only apply rules already frozen. It may not recover a verdict that A3.3
withheld, and it may not resolve an entity_role disagreement by consulting anything the
adjudicators were not allowed to see. Anything the frozen rules do not settle is UNCERTAIN.
"""
import json
from collections import Counter

A = {r["benchmark_id"]: r for r in map(json.loads, open("adjudication_A.jsonl"))}
B = {r["benchmark_id"]: r for r in map(json.loads, open("adjudication_B.jsonl"))}
ev = {json.loads(l)["benchmark_id"]: json.loads(l) for l in open("blinded_evidence.jsonl")}

# Frozen precedence for entity_role. A registered intervention outranks a string-shape
# guess, because registration is direct evidence and string shape is inference. Nothing
# outranks a combination finding, which is what A3.3 protects.
PRECEDENCE = ["COMBINATION_REGIMEN", "ASSET", "INDICATION", "PLACEHOLDER_DESCRIPTION",
              "MODALITY_CLASS", "UNCERTAIN"]

ledger, final = [], []
for bid in A:
    a, b, e = A[bid], B[bid], ev[bid]
    entry = a["gold_entry"]

    # entity_role
    if a["entity_role"] == b["entity_role"]:
        role, basis = a["entity_role"], "AGREE"
    else:
        pair = {a["entity_role"], b["entity_role"]}
        if "COMBINATION_REGIMEN" in pair:
            role, basis = "COMBINATION_REGIMEN", "RECONCILED: combination finding is protective (A3.3)"
        elif pair == {"ASSET", "UNCERTAIN"}:
            # Resolve only on registry evidence, which both were permitted to see.
            registered = any(h["field"] in ("interventions", "other_names")
                             for hits in e["ctgov_exhibits"].values() for h in hits)
            role = "ASSET" if registered else "UNCERTAIN"
            basis = f"RECONCILED: registered_as_intervention={registered}"
        elif pair <= {"ASSET", "MODALITY_CLASS", "PLACEHOLDER_DESCRIPTION", "INDICATION"}:
            registered = any(h["field"] == "interventions"
                             for hits in e["ctgov_exhibits"].values() for h in hits)
            if registered:
                role, basis = "ASSET", "RECONCILED: registered as a trial intervention"
            else:
                role, basis = "UNCERTAIN", "UNRESOLVED: descriptive vs asset, no registration"
        else:
            role, basis = "UNCERTAIN", "UNRESOLVED: no frozen rule settles this pair"

    # target_relevance -- must never be recovered from context
    if a["target_relevance"] == b["target_relevance"]:
        target, tbasis = a["target_relevance"], "AGREE"
    else:
        target, tbasis = "UNCERTAIN", "UNRESOLVED: adjudicators differ; A3.4 sends this to UNCERTAIN"

    trial = a["trial_role"] if a["trial_role"] == b["trial_role"] else \
        ("INTERVENTION" if "INTERVENTION" in (a["trial_role"], b["trial_role"]) else b["trial_role"])

    if basis != "AGREE" or tbasis != "AGREE":
        ledger.append({"benchmark_id": bid, "gold_entry": entry,
                       "A": [a["entity_role"], a["target_relevance"]],
                       "B": [b["entity_role"], b["target_relevance"]],
                       "resolution": [role, target], "basis": basis, "target_basis": tbasis})

    final.append({"benchmark_id": bid, "gold_entry": entry, "entity_role": role,
                  "target_relevance": target, "trial_role": trial,
                  "confidence": round(min(a["confidence"], b["confidence"]), 2),
                  "reason_A": a["reason"], "reason_B": b["reason"],
                  "reconciliation_basis": basis, "target_basis": tbasis,
                  "evidence": (a["evidence"] + b["evidence"])[:8]})

for name, rows in (("gold_entry_roles.jsonl", final), ("reconciliation_ledger.jsonl", ledger)):
    with open(name, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")

print("entity_role disagreements:", len(ledger))
print("final entity_role:", dict(Counter(r["entity_role"] for r in final)))
print("final target:", dict(Counter(r["target_relevance"] for r in final)))
print("final trial_role:", dict(Counter(r["trial_role"] for r in final)))
print()
print("PDCD1 asset denominator (ASSET + PDCD1_MATCH):",
      sum(1 for r in final if r["entity_role"] == "ASSET" and r["target_relevance"] == "PDCD1_MATCH"))
print("UNCERTAIN entity_role:", sum(1 for r in final if r["entity_role"] == "UNCERTAIN"))
print("UNCERTAIN target:", sum(1 for r in final if r["target_relevance"] == "UNCERTAIN"))
