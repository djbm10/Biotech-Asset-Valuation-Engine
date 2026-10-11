"""Sealed, offline compilation-only acceptance scorer. No source acquisition."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from bve.se.gates.engine import _requirement
from bve.se.gates.evaluator import evaluate_indication, evaluate_requirement
from bve.se.intent.compiler import compile_intent, intent_to_trial_query, residual_indications
from bve.se.intent.indication_compilation import indication_spans
from bve.se.intent.intent import SearchIntent
from bve.se.ontology.indications import B_CELL_LYMPHOMA, is_indication_concept
from bve.se.schemas.contracts import BuyerIdentity, NormalizedFact, RequirementOperator

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/se_indication_compilation_v2"


def decide(requested: str, observed: str, *, jcar: bool = False) -> dict:
    fact = NormalizedFact(
        fact_id="jcar" if jcar else "f", subject_id="JCAR014" if jcar else "a",
        fact_type="indication", value=observed, confidence=.9,
        supporting_claim_ids=["jcar_claim" if jcar else "c"],
    )
    evaluator = evaluate_indication if is_indication_concept(requested) else evaluate_requirement
    return evaluator(
        _requirement("strategy.indication", "indication", RequirementOperator.IN, [requested]),
        subject_id=fact.subject_id, facts=[fact], gate_id="strategic_sandbox",
    ).model_dump(mode="json")


def score() -> dict:
    manifest = json.loads((OUT / "manifest.json").read_text())
    sealed = all(hashlib.sha256((OUT / name).read_bytes()).hexdigest() == sha
                 for name, sha in manifest.items())
    pop = json.loads((OUT / "population.json").read_text())
    records = []
    for case in pop["cases"]:
        intent = SearchIntent.model_validate(case["intent"])
        spans = indication_spans(intent)
        after = residual_indications(intent)
        problem = compile_intent(
            intent, buyer=BuyerIdentity.model_validate(case["baseline_problem"]["buyer"]),
            therapeutic_areas=case["baseline_problem"]["strategic_gap"]["therapeutic_areas"],
        ).model_dump(mode="json")
        before = json.loads(json.dumps(case["baseline_problem"]))
        before["strategic_gap"].pop("indications")
        problem["strategic_gap"].pop("indications")
        before.pop("version")
        problem.pop("version")
        retrieval = intent_to_trial_query(intent, as_of_date=date(2026, 10, 11)).model_dump(mode="json")
        records.append({
            "id": case["id"], "query": case["query"], "before": case["baseline_requirements"],
            "after": after, "expected": case["expected"], "exact": after == case["expected"],
            "spans": [asdict(s) for s in spans],
            "offsets": all(s.text == intent.original_query[s.start:s.end] for s in spans),
            "isolation": problem == before and retrieval == case["baseline_retrieval"]
                and intent.model_dump(mode="json") == case["intent"],
        })
    by_id = {r["id"]: r for r in records}
    gate_unchanged = all(decide(c["requested"], c["observed"]) == c["baseline_decision"]
                         for c in pop["gate_controls"])
    jcar = decide(B_CELL_LYMPHOMA, pop["JCAR014"]["conditions"][0], jcar=True)
    protected = all(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha
                    for path, sha in pop["source_hashes"].items())
    uncertainty = {"H13", "general_unknown", "general_syndrome", "general_negated",
                   "general_nos", "general_coordination", "general_qualified",
                   "v1_unrecognized_request", "v1_unknown_request"}
    # IDs present in the frozen population determine the applicable uncertainty controls.
    uncertain = [r for r in records if r["id"] in uncertainty]
    criteria = {
        "C1": all(r["exact"] for r in records if r["expected"]),
        "C2": all(by_id[q]["exact"] and len(by_id[q]["after"]) == 1
                  for q in ["H2", "H4", "H11", "H12", "H13", "H14"]),
        "C3": all(r["exact"] for r in records if not r["expected"]),
        "C4": all(r["exact"] and r["offsets"] for r in records)
            and all(len(r["spans"]) == 1 and r["spans"][0]["normalization"] == "UNRESOLVED"
                    for r in uncertain),
        "C5": by_id["TAC01"]["exact"] and jcar == pop["JCAR014"]["baseline_decision"],
        "C6": by_id["mint5"]["exact"] and by_id["mint5"]["isolation"],
        "C7": sealed and protected and gate_unchanged and all(r["isolation"] for r in records),
    }
    return {"criteria": criteria, "sealed": sealed, "protected_source": protected,
            "gate_controls_unchanged": gate_unchanged, "JCAR014": jcar,
            "positive_count": sum(bool(r["expected"]) for r in records),
            "records": records}


if __name__ == "__main__":
    result = score()
    (OUT / "score.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "records"}, sort_keys=True))
    raise SystemExit(0 if all(result["criteria"].values()) else 1)
