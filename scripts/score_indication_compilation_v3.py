"""Sealed compilation-only acceptance; no acquisition, product replay or gate changes."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import date
from pathlib import Path
import subprocess

from bve.se.gates.engine import _requirement
from bve.se.gates.evaluator import evaluate_indication, evaluate_requirement
from bve.se.intent.compiler import compile_intent, intent_to_trial_query, residual_indications
from bve.se.intent.indication_compilation import indication_spans
from bve.se.intent.intent import SpanKind
from bve.se.intent.parser import parse_query
from bve.se.ontology.indications import B_CELL_LYMPHOMA, is_indication_concept
from bve.se.ontology.targets import resolve_target
from bve.se.schemas.contracts import BuyerIdentity, NormalizedFact, RequirementOperator

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/se_indication_compilation_v3"
AMB_WARNING = "ambiguous terms left unresolved (escalate rather than guess): "


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def parser_isolation(before: dict, after: dict, operator: bool) -> bool:
    before, after = json.loads(json.dumps(before)), json.loads(json.dumps(after))
    if not operator:
        return before == after
    match = re.search(r"(?<![\w-])not(?![\w-])", before["original_query"], re.I)
    start, end = match.span()
    before["spans"] = [s for s in before["spans"] if not (s["start"] < end and start < s["end"])]
    after["spans"] = [s for s in after["spans"] if s["kind"] != "GRAMMATICAL_OPERATOR"]
    remaining = [term for term in before["ambiguous_terms"] if term.casefold() != "not"]
    before["ambiguous_terms"] = remaining
    before["warnings"] = [
        (AMB_WARNING + ", ".join(remaining) if remaining else None)
        if warning.startswith(AMB_WARNING) else warning for warning in before["warnings"]
    ]
    before["warnings"] = [warning for warning in before["warnings"] if warning is not None]
    return before == after


def score() -> dict:
    manifest = json.loads((OUT / "manifest.json").read_text())
    sealed = all(digest(ROOT / name) == sha for name, sha in manifest.items())
    pop = json.loads((OUT / "population.json").read_text())
    records = []
    for case in pop["cases"]:
        intent = parse_query(case["query"])
        spans = indication_spans(intent)
        after = residual_indications(intent)
        parsed = intent.model_dump(mode="json")
        operators = [s for s in intent.spans if s.kind is SpanKind.GRAMMATICAL_OPERATOR]
        operator_ok = not operators
        if case["operator"]:
            match = re.search(r"(?<![\w-])not(?![\w-])", case["query"], re.I)
            operator_ok = (
                len(operators) == 1 and operators[0].start == match.start()
                and operators[0].end == match.end() and operators[0].resolved_to == "NOT"
                and operators[0].rule == "grammatical_clinical_negation"
                and not any(s.kind in {SpanKind.TARGET, SpanKind.AMBIGUOUS_TARGET}
                            and s.start < match.end() and match.start() < s.end
                            for s in intent.spans)
                and len(spans) == 1 and spans[0].normalization == "UNRESOLVED"
                and spans[0].requirement == case["expected"][0]
            )
        problem_unchanged = intent.is_compilable == case["baseline_compilable"]
        if intent.is_compilable and case["baseline_problem"] is not None:
            before = json.loads(json.dumps(case["baseline_problem"]))
            problem = compile_intent(
                intent, buyer=BuyerIdentity.model_validate(before["buyer"]),
                therapeutic_areas=before["strategic_gap"]["therapeutic_areas"],
            ).model_dump(mode="json")
            before["strategic_gap"].pop("indications")
            problem["strategic_gap"].pop("indications")
            before.pop("version")
            problem.pop("version")
            problem_unchanged = problem_unchanged and problem == before
        retrieval = intent_to_trial_query(intent, as_of_date=date(2026, 10, 11)).model_dump(mode="json")
        records.append({
            "id": case["id"], "group": case["group"], "operator_expected": case["operator"],
            "query": case["query"], "expected": case["expected"], "after": after,
            "before": (case["baseline_problem"] or {}).get("strategic_gap", {}).get("indications"),
            "exact": after == case["expected"], "spans": [asdict(s) for s in spans],
            "operator_ok": operator_ok, "operators": [s.model_dump(mode="json") for s in operators],
            "targets": parsed["targets"], "baseline_targets": case["baseline_intent"]["targets"],
            "offsets": all(s.text == case["query"][s.start:s.end] for s in spans),
            "parser_unchanged": parsed == case["baseline_intent"],
            "parser_isolation": parser_isolation(case["baseline_intent"], parsed, case["operator"]),
            "problem_isolation": problem_unchanged,
            "retrieval_unchanged": retrieval == case["baseline_retrieval"],
            "refusal_preserved": not intent.is_compilable
                and intent.blockers(indication_supplied=True) == case["baseline_blockers"],
        })
    by_id = {row["id"]: row for row in records}
    alias_results = {}
    for alias in pop["aliases"]:
        resolved = resolve_target(alias)
        alias_results[alias] = {
            "status": resolved.status.value, "rule": resolved.rule,
            "entity": resolved.entity.canonical_id if resolved.entity else None,
            "candidates": [candidate.canonical_id for candidate in resolved.candidates],
        }
    gates = all(decide(c["requested"], c["observed"]) == c["baseline_decision"]
                for c in pop["gate_controls"])
    jcar = decide(B_CELL_LYMPHOMA, pop["JCAR014"]["conditions"][0], jcar=True)
    protected = all(digest(ROOT / path) == sha for path, sha in pop["protected_source"].items())
    v2_preserved = all(digest(ROOT / path) == sha for path, sha in pop["preserved_v2"].items())
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", pop["baseline_head"], "--", "src/"], cwd=ROOT, text=True,
    ).splitlines()
    scoped = set(changed).issubset(pop["allowed_production_changes"])
    criteria = {
        "C3.1": all(row["operator_ok"] and row["exact"] and row["targets"] == row["baseline_targets"]
                     for row in records if row["operator_expected"]),
        "C3.2": alias_results == pop["aliases"] and all(
            row["parser_unchanged"] and row["operator_ok"] and row["retrieval_unchanged"]
            for row in records if row["group"] == "entity"),
        "C3.3": all(row["exact"] for row in records if row["group"] == "v2"),
        "C3.4": all(row["exact"] and row["offsets"] for row in records)
            and all(row["refusal_preserved"] and row["parser_unchanged"]
                    for row in records if row["group"] == "ambiguous"),
        "C3.5": all(not row["after"] for row in records if not row["expected"]),
        "C3.6": all(by_id[key]["exact"] and by_id[key]["parser_unchanged"]
                     and by_id[key]["problem_isolation"] and by_id[key]["retrieval_unchanged"]
                     for key in ["TAC01", "mint5"])
            and gates and jcar == pop["JCAR014"]["baseline_decision"],
        "C3.7": sealed and protected and v2_preserved and scoped and gates and all(
            row["parser_isolation"] and row["problem_isolation"] and row["retrieval_unchanged"]
            for row in records),
    }
    return {"criteria": criteria, "total": len(records),
            "exact_count": sum(row["exact"] for row in records),
            "sealed": sealed, "protected_source": protected, "v2_preserved": v2_preserved,
            "source_diff_scoped": scoped, "production_changes": changed,
            "alias_results": alias_results, "gate_controls_unchanged": gates,
            "JCAR014": jcar, "records": records}


if __name__ == "__main__":
    result = score()
    (OUT / "score.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, sort_keys=True))
    raise SystemExit(0 if all(result["criteria"].values()) else 1)
