"""Score the sealed evidence-only milestone without running the search engine."""

import ast
from collections import Counter
from datetime import date
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from bve.se.evidence import human_poc as hp
from bve.se.gates.engine import GateEngine
from bve.se.schemas.contracts import BuyerProblemV2, ClinicalResult

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "research/se_human_efficacy_context_safety_v1"
OUT = Path("/tmp/human_efficacy_context_safety_v1_result")


def load(name):
    return json.loads((PACKET / name).read_text())


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def function_bytes(source, name):
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return "\n".join(source.splitlines()[node.lineno - 1 : node.end_lineno])


def main():
    OUT.mkdir(exist_ok=True)
    frozen = load("preregistration_manifest.json")
    for name, digest in frozen["files"].items():
        assert sha(PACKET / name) == digest, name
    isolation = load("isolation_manifest.json")
    preserved_files = all(sha(ROOT / p) == h for p, h in isolation["protected_files"].items())
    for run in load("input_manifest.json").values():
        assert sha(Path(run["path"])) == run["sha256"]

    semantic = []
    for c in load("semantic_controls.json"):
        statements = hp.efficacy_statements(
            c["text"], asset_names=c["asset_names"], document_id="control"
        )
        semantic.append(
            {
                **c,
                "actual_pass": bool(statements),
                "statements": [s.model_dump() for s in statements],
            }
        )
    structured = [
        {
            **c,
            "actual_pass": hp.result_supports_human_poc(ClinicalResult.model_validate(c["result"])),
        }
        for c in load("structured_controls.json")
    ]
    existing = []
    for c in load("existing_test_population.json"):
        value = (
            bool(hp.efficacy_statements(**c["inputs"]))
            if c["route"] == "prose"
            else hp.result_supports_human_poc(ClinicalResult.model_validate(c["inputs"]))
        )
        existing.append(
            {
                "id": c["id"],
                "route": c["route"],
                "expected": bool(c["baseline_outputs"]),
                "actual": value,
            }
        )

    judgments = {w["passage"]: w for w in load("witness_adjudications.json")}
    witnesses = []
    facts = []
    for asset in load("benchmark_population.json"):
        old_survives = False
        expected_survives = False
        new_survives = False
        for w in asset["witnesses"]:
            if not w["baseline_accepted"]:
                continue
            passage = w["claim"]["supporting_passage"]
            expected = judgments[passage]["expected_pass"]
            statements = hp.efficacy_statements(
                passage,
                asset_names=asset["asset_names"],
                document_id=w["claim"]["source_document_id"],
            )
            old_survives = True
            expected_survives |= expected
            new_survives |= bool(statements)
            witnesses.append(
                {
                    "run": asset["run"],
                    "name": asset["name"],
                    "asset_id": asset["asset_id"],
                    "claim_id": w["claim"]["claim_id"],
                    "survey_id": judgments[passage]["id"],
                    "expected_pass": expected,
                    "actual_pass": bool(statements),
                    "reason": judgments[passage]["reason"],
                }
            )
        facts.append(
            {
                "run": asset["run"],
                "name": asset["name"],
                "asset_id": asset["asset_id"],
                "baseline_reader_pass": old_survives,
                "expected_pass": expected_survives,
                "actual_pass": new_survives,
            }
        )

    problem = BuyerProblemV2.model_validate(
        {
            "problem_id": "context-control",
            "version": "1",
            "buyer": {"buyer_id": "control", "name": "Control", "as_of_date": "2026-10-11"},
            "strategic_gap": {
                "therapeutic_areas": ["UNSPECIFIED"],
                "evidence_floor": {"human_poc_required": True},
            },
        }
    )
    empty = hp.human_poc_evidence(
        "asset:control", results=[], statements=[], as_of_date=date(2026, 10, 11)
    )
    decision = next(
        d
        for d in GateEngine().evaluate(problem, subject_id="asset:control", facts=[]).decisions
        if d.requirement_id == "evidence.human_poc"
    )
    original = (PACKET / "original_human_poc.py").read_text()
    candidate = inspect.getsource(hp)
    attribution_same = all(
        function_bytes(original, n) == function_bytes(candidate, n)
        for n in ["_reports_a_regimen", "_is_regimen_list_item"]
    )
    changed = subprocess.check_output(
        ["git", "diff", isolation["base_commit"], "--name-only", "--", "src"], cwd=ROOT, text=True
    ).splitlines()
    isolated = changed == ["src/bve/se/evidence/human_poc.py"]
    benchmark_runs = {"TAC01", "mint5", "AACR_accepted", "TAC01_regimen_accepted"}
    primary_false = [
        w
        for w in witnesses
        if w["claim_id"] in {"claim:9954996062248331a551", "claim:6c5b35e2a5871015f940"}
    ]

    quality_path = OUT / "quality.json"
    quality = json.loads(quality_path.read_text()) if quality_path.exists() else {}
    junit_path = OUT / "tests.xml"
    junit = ET.parse(junit_path).getroot() if junit_path.exists() else None
    suites = (
        list(junit)
        if junit is not None and junit.tag == "testsuites"
        else [junit]
        if junit is not None
        else []
    )
    tests_ok = bool(suites) and all(
        int(s.get("failures", 0)) == int(s.get("errors", 0)) == 0 for s in suites
    )
    skips = sum(int(s.get("skipped", 0)) for s in suites)
    criteria = {
        "E1": len(primary_false) == 2 and all(not w["actual_pass"] for w in primary_false),
        "E2": all(
            c["actual_pass"] == c["expected_pass"]
            for c in semantic
            if c["category"]
            in {
                "laboratory",
                "material_cohort",
                "ambiguous_cohort",
                "clinical_cohort",
                "clinical_response",
            }
        )
        and all(c["actual_pass"] == c["expected_pass"] for c in structured),
        "E3": all(c["actual_pass"] == c["expected_pass"] for c in semantic),
        "E4": all(not c["actual"] for c in existing if not c["expected"]),
        "E5": attribution_same and all(c["actual"] == c["expected"] for c in existing),
        "E6": all(w["actual_pass"] == w["expected_pass"] for w in witnesses)
        and all(c["actual"] for c in existing if c["expected"]),
        "E7": empty is None and decision.status.value == "UNKNOWN",
        "E8": isolated and preserved_files,
        "E9": all(
            f["actual_pass"] == f["expected_pass"] for f in facts if f["run"] in benchmark_runs
        ),
        "E10": tests_ok
        and skips == 3
        and quality.get("ruff_exit_code") == 0
        and quality.get("pytest_exit_code") == 0,
    }
    result = {
        "milestone": "HUMAN_EFFICACY_CONTEXT_SAFETY v1",
        "criteria": criteria,
        "decision": "ADOPT" if all(criteria.values()) else "FAILED_ACCEPTANCE",
        "semantic_controls": semantic,
        "structured_controls": structured,
        "existing_controls": existing,
        "witnesses": witnesses,
        "facts": facts,
        "primary_false_removals": primary_false,
        "counts": dict(
            Counter(
                ("preserved_true" if w["expected_pass"] else "rejected_false")
                for w in witnesses
                if w["actual_pass"] == w["expected_pass"]
            )
        ),
        "semantic_failures": [c for c in semantic if c["actual_pass"] != c["expected_pass"]],
        "structured_failures": [c for c in structured if c["actual_pass"] != c["expected_pass"]],
        "witness_failures": [w for w in witnesses if w["actual_pass"] != w["expected_pass"]],
        "facts_removed": [f for f in facts if f["baseline_reader_pass"] and not f["actual_pass"]],
        "production_changes": changed,
        "quality": quality,
    }
    (OUT / "score.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "criteria": criteria,
                "decision": result["decision"],
                "semantic_failures": [
                    (c["id"], c["category"]) for c in result["semantic_failures"]
                ],
                "witness_failures": [
                    (w["run"], w["name"], w["survey_id"]) for w in result["witness_failures"]
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
