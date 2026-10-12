"""Formal offline representation checks on frozen annotations, never engine replay."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from materialize import materialize, serialize

from bve.se.evidence.human_poc import efficacy_statements
from bve.se.schemas.treatment_cohort import TreatmentCohortAttribution


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load(path: Path):
    return json.loads(path.read_text())


def check_reference(root: Path, reference: dict):
    path = root / reference["path"]
    assert digest(path) == reference["sha256"], str(path)
    value = load(path)
    for component in reference["json_pointer"].split("/")[1:]:
        component = component.replace("~1", "/").replace("~0", "~")
        value = value[int(component)] if isinstance(value, list) else value[component]
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--quality", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    packet = root / "research/se_treatment_cohort_attribution_representation_v1"
    args.output.mkdir(parents=True, exist_ok=True)
    # Refuse to overwrite an acceptance score, including a failed one.
    assert not (args.output / "score.json").exists()
    rows = load(packet / "expected_representation.json")
    records = [materialize(r) for r in rows]
    checks = {}

    def check(name, operation):
        try:
            detail = operation()
            checks[name] = {"pass": True, "detail": detail}
        except Exception as error:  # Preserve failures as results, never amend expectations.
            checks[name] = {"pass": False, "error": str(error)}

    def fidelity():
        freeze = load(packet / "freeze.json")
        for name, expected in freeze["files"].items():
            assert digest(packet / name) == expected, name
        assert len(rows) == len(records) == 98
        assert len({r.attribution_id for r in records}) == 98
        for row, record in zip(rows, records):
            assert record.relationship.value == row["expected_relation"]
            for field in ("asset_id", "witness_id", "receipt_status", "cohort_membership_status",
                          "result_ownership_status", "scope", "basis", "reason"):
                assert getattr(record, field) == row[field], (row["witness_id"], field)
            assert list(record.candidate_names) == row["candidate_names"]
            assert list(record.regimen_components) == row["regimen_components"]
            assert list(record.qualifiers) == row["qualifiers"]
            original = check_reference(root, row["annotation_reference"])
            if row["population"] == "contract_33":
                assert record.receipt_status == original["receipt_status"]
                assert record.result_ownership_status == original["efficacy_owner_status"]
        review = load(packet / "scientific_grounding_review.json")
        unsupported = review["unsupported_receipt_annotations"]
        assert not unsupported, (
            "98/98 match their frozen labels, but independent grounding review found "
            f"{len(unsupported)} unsupported receipt labels: "
            + ", ".join(r["witness_id"] for r in unsupported)
        )
        return {"matched": 98, "kind": "Frozen manual grounding represented, not text inference"}

    def separation():
        nonowning = [r for r in records if r.relationship.value != "RESULT_OWNERSHIP"]
        assert len(nonowning) == 83
        for record in nonowning:
            serialized = json.loads(record.canonical_json())
            assert serialized["result_ownership_status"] == "UNKNOWN"
            assert serialized["ownership_certificate"] is None
        return {"nonowning_records": len(nonowning)}

    def negatives():
        negative = [record for row, record in zip(rows, records)
                    if row["population"] == "negative_65"]
        assert len(negative) == 65
        assert all(r.result_ownership_status == "UNKNOWN" for r in negative)
        c056 = next(r for r in negative if r.witness_id == "negative:C056")
        assert c056.relationship.value == "REGIMEN_RECEIPT"
        return {"nonowning": 65, "C056": "REGIMEN_RECEIPT; old reader defect preserved"}

    def provenance():
        snapshots = set()
        for row, record in zip(rows, records):
            annotation = check_reference(root, row["annotation_reference"])
            original = check_reference(root, row["text_reference"])
            for field in row["text_field"].split("."):
                original = original[field]
            assert original == record.passage.text
            assert record.passage.start == 0 and record.passage.end == len(original)
            if record.source is not None:
                snapshot = Path(record.source.snapshot_path)
                assert digest(snapshot) == record.source.snapshot_sha256
                snapshots.add(str(snapshot))
            if record.ownership_certificate is not None:
                assert annotation["efficacy_owner_status"] == "CERTIFIED"
                assert annotation["receipt_status"] == "CERTIFIED"
                assert annotation["proposed_edge_basis"] == record.basis
            assert record.arm is None and record.result_group is None
        return {"traceable": 98, "unique_verified_snapshots": len(snapshots),
                "invented_result_arm_links": 0}

    def regimen():
        component = [r for r in records if r.scope.value in
                     {"REGIMEN_COMPONENT", "POOLED_REGIMEN"}]
        assert all(r.result_ownership_status == "UNKNOWN" for r in component)
        unresolved14 = [record for row, record in zip(rows, records)
                        if row["previous_unresolved_14"]]
        assert len(unresolved14) == 14
        counts = Counter(r.relationship.value for r in unresolved14)
        assert counts == {"REGIMEN_RECEIPT": 9, "UNRESOLVED": 5}
        return {"component_records_nonowning": len(component), "previous_14": dict(counts)}

    def deterministic():
        first, second = serialize(rows), serialize(rows)
        assert first == second
        assert first == "\n".join(TreatmentCohortAttribution.model_validate_json(
            line).canonical_json() for line in first.splitlines()) + "\n"
        (args.output / "records.jsonl").write_text(first)
        return {"records": 98, "canonical_sha256": hashlib.sha256(first.encode()).hexdigest()}

    def neutrality():
        probes = load(packet / "reader_baseline.json")
        for probe in probes:
            actual = [s.model_dump(mode="json") for s in efficacy_statements(
                probe["text"], asset_names=probe["asset_names"],
                document_id=probe["document_id"])]
            assert actual == probe["outputs"], probe["id"]
        runs = load(packet / "run_baseline.json")
        for name, run in runs.items():
            assert digest(Path(run["path"])) == run["sha256"], name
        protected = load(packet / "protected_files.json")
        for path, expected in protected.items():
            assert digest(root / path) == expected, path
        c056 = next(p for p in probes if p["id"] == "negative:C056")
        assert c056["outputs"]
        return {"reader_outputs_unchanged": len(probes), "original_results_byte_unchanged": len(runs),
                "protected_files_byte_unchanged": len(protected),
                "human_poc_present_gates_shortlist_ranking": "UNCHANGED; inert sidecar only",
                "C056_reader_pass_preserved": True, "replays": 0}

    def isolation():
        protected = load(packet / "protected_files.json")
        new = sorted(str(p.relative_to(root)) for folder in ("src", "tests", "scripts")
                     for p in (root / folder).rglob("*.py")
                     if str(p.relative_to(root)) not in protected)
        assert new == ["src/bve/se/schemas/treatment_cohort.py",
                       "tests/se/test_treatment_cohort_representation.py"], new
        for path in protected:
            if path.startswith("src/") and path.endswith(".py"):
                assert "schemas.treatment_cohort" not in (root / path).read_text(), path
        implementation = load(packet / "implementation_manifest.json")
        for path, expected in implementation["files"].items():
            assert digest(root / path) == expected, path
        return {"new_production_modules": 1, "existing_production_consumers": 0}

    def quality():
        report = load(args.quality)
        assert report["pytest_exit_code"] == report["ruff_exit_code"] == 0
        assert report["failed"] == report["errors"] == 0
        assert report["passed"] == 1824 and report["xfail"] == 3
        for path, expected in report["evidence_sha256"].items():
            assert digest(Path(path)) == expected, path
        return report

    for name, operation in (
        ("R1", fidelity), ("R2", separation), ("R3", negatives), ("R4", provenance),
        ("R5", regimen), ("R6", deterministic), ("R7", neutrality),
        ("R8", isolation), ("R9", quality),
    ):
        check(name, operation)
    passed = all(r["pass"] for r in checks.values())
    score = {
        "milestone": "TREATMENT_COHORT_ATTRIBUTION_REPRESENTATION v1",
        "decision": "ADOPT_REPRESENTATION_ONLY" if passed else "FAIL_REVERT_IMPLEMENTATION",
        "evaluation_kind": "Grounded annotation representation, not extraction/generalization",
        "checks": checks, "counts": dict(Counter(r.relationship.value for r in records)),
        "counts_by_population": {
            pop: dict(Counter(record.relationship.value for row, record in zip(rows, records)
                              if row["population"] == pop))
            for pop in ("contract_33", "negative_65")
        },
        "previously_unresolved_14": [{
            "id": row["witness_id"], "candidate": row["candidate_asset"],
            "relationship": record.relationship.value, "reason": record.reason,
        } for row, record in zip(rows, records) if row["previous_unresolved_14"]],
        "new_result_ownership_edges_for_14": 0,
        "human_poc_implementation_ready": False,
        "recommendation": "STOP recovery of these 14 until stronger sources or structured result attribution exist.",
    }
    (args.output / "score.json").write_text(json.dumps(score, indent=2) + "\n")
    print(json.dumps({"decision": score["decision"], "counts": score["counts"], "checks": checks},
                     indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
