"""Build Milestone 5 candidate-identity adjudication artifacts from frozen M4.

This is a pure packaging/adjudication stage: it reads only the finalized M4
snapshot, runs two independently parameterized adjudication passes, records
their disagreements, and writes the canonical M5 snapshot directory.
"""
from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pdcd1_candidate_identity_lib as lib

ROOT = Path(__file__).resolve().parents[1]
M4_DIR = (
    ROOT
    / "artifacts"
    / "pipeline"
    / "pdcd1_rebase_v1"
    / "stages"
    / "04_external_product_authority"
    / lib.M4_SNAPSHOT_ID
)
STAGE_ROOT = (
    ROOT
    / "artifacts"
    / "pipeline"
    / "pdcd1_rebase_v1"
    / "stages"
    / "05_candidate_identity_adjudication"
)


def load_inputs() -> tuple[list[dict], list[dict], list[dict]]:
    subjects = lib.load_jsonl(M4_DIR / "subjects" / "authority_research_subject_ledger.jsonl")
    assertions = lib.load_jsonl(M4_DIR / "assertions" / "normalized_assertion_ledger.jsonl")
    conflicts = lib.load_jsonl(M4_DIR / "conflicts" / "authority_conflict_ledger.jsonl")
    if len(subjects) != 554:
        raise SystemExit(f"expected 554 M4 subjects, found {len(subjects)}")
    if len(conflicts) != 76:
        raise SystemExit(f"expected 76 M4 conflicts, found {len(conflicts)}")
    return subjects, assertions, conflicts


def prospective_snapshot_id(build_a: dict, build_b: dict, reconciliation: list[dict]) -> str:
    return lib.stable_hash(
        {
            "milestone": lib.MILESTONE,
            "schema_version": lib.SCHEMA_VERSION,
            "m4_snapshot_id": lib.M4_SNAPSHOT_ID,
            "build_a_mapping": build_a["subject_mapping"],
            "build_a_candidates": build_a["canonical_candidates"],
            "build_b_mapping": build_b["subject_mapping"],
            "build_b_candidates": build_b["canonical_candidates"],
            "reconciliation": reconciliation,
        }
    )[:24]


def receipt_for(out_dir: Path) -> dict:
    artifacts = {}
    for path in sorted(out_dir.rglob("*")):
        if not path.is_file() or path.name == "receipt.json":
            continue
        rel = str(path.relative_to(out_dir))
        data = path.read_bytes()
        artifacts[rel] = {
            "byte_length": len(data),
            "sha256": lib.hashlib.sha256(data).hexdigest(),
        }
    return {
        "milestone": lib.MILESTONE,
        "lineage": lib.LINEAGE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": out_dir.name,
        "artifacts": artifacts,
        "external_authority_capture_performed": False,
        "canonical_candidates_created": True,
        "aliases_adjudicated": True,
        "ownership_claims_created": False,
        "candidate_chronology_created": False,
        "benchmark_labels_created": False,
        "predictions_generated": False,
        "evaluation_performed": False,
    }


def main() -> None:
    subjects, assertions, conflicts = load_inputs()
    build_a = lib.adjudicate_build(
        build_name="build_a",
        subjects=subjects,
        assertions=assertions,
        conflicts=conflicts,
        conservative_conflicts=True,
    )
    build_b = lib.adjudicate_build(
        build_name="build_b",
        subjects=list(reversed(subjects)),
        assertions=list(reversed(assertions)),
        conflicts=list(reversed(conflicts)),
        conservative_conflicts=False,
    )
    reconciliation, agreement = lib.compare_builds(build_a, build_b)
    snapshot_id = prospective_snapshot_id(build_a, build_b, reconciliation)
    out_dir = STAGE_ROOT / snapshot_id
    if out_dir.is_dir():
        shutil.rmtree(out_dir)
    for subdir in (
        "input",
        "subjects",
        "candidates",
        "aliases",
        "boundaries",
        "conflicts",
        "validation",
        "reproducibility",
        "logs",
        "export",
    ):
        (out_dir / subdir).mkdir(parents=True, exist_ok=True)

    lib.write_jsonl(out_dir / "candidates" / "canonical_candidate_ledger.jsonl", build_a["canonical_candidates"])
    lib.write_jsonl(out_dir / "aliases" / "alias_development_code_ledger.jsonl", build_a["aliases"])
    lib.write_jsonl(out_dir / "subjects" / "subject_candidate_mapping_ledger.jsonl", build_a["subject_mapping"])
    lib.write_jsonl(out_dir / "boundaries" / "identity_boundary_ledger.jsonl", build_a["identity_boundaries"])
    lib.write_jsonl(out_dir / "conflicts" / "conflict_resolution_ledger.jsonl", build_a["conflict_resolution"])
    lib.write_jsonl(out_dir / "aliases" / "rejected_alias_ledger.jsonl", build_a["rejected_aliases"])

    lib.write_jsonl(out_dir / "reproducibility" / "build_a_subject_candidate_mapping_ledger.jsonl", build_a["subject_mapping"])
    lib.write_jsonl(out_dir / "reproducibility" / "build_b_subject_candidate_mapping_ledger.jsonl", build_b["subject_mapping"])
    lib.write_jsonl(out_dir / "reproducibility" / "build_a_canonical_candidate_ledger.jsonl", build_a["canonical_candidates"])
    lib.write_jsonl(out_dir / "reproducibility" / "build_b_canonical_candidate_ledger.jsonl", build_b["canonical_candidates"])
    lib.write_jsonl(out_dir / "reproducibility" / "reconciliation_ledger.jsonl", reconciliation)

    outcome_counts = lib.outcome_counts(build_a["subject_mapping"])
    conflict_counts = Counter(r["resolution_marker"] for r in build_a["conflict_resolution"])
    summary = {
        "total_subjects": len(build_a["subject_mapping"]),
        "canonical_candidate_count": len(build_a["canonical_candidates"]),
        "alias_count": len(build_a["aliases"]),
        "outcome_counts": outcome_counts,
        "m4_conflict_count": len(conflicts),
        "conflicts_resolved": conflict_counts.get("RESOLVED", 0),
        "conflicts_unresolved": conflict_counts.get("CONFLICT_UNRESOLVED", 0),
        "build_a_vs_build_b_agreement": agreement,
    }
    lib.write_json(out_dir / "validation" / "identity_adjudication_summary.json", summary)
    lib.write_json(
        out_dir / "input" / "prerequisite_bindings.json",
        {
            "milestone4_snapshot_id": lib.M4_SNAPSHOT_ID,
            "milestone4_manifest_sha256": lib.file_sha(M4_DIR / "manifest.json"),
            "milestone4_receipt_sha256": lib.file_sha(M4_DIR / "receipt.json"),
            "external_research_exceptions": [],
            "frozen_external_authority_input_only": True,
        },
    )

    comparison = [
        "# Milestone 5 - Build A vs Build B Candidate Identity Comparison",
        "",
        f"Build A subjects: `{len(build_a['subject_mapping'])}`",
        f"Build B subjects: `{len(build_b['subject_mapping'])}`",
        f"Subject coverage agreement: `{agreement['total_subjects']}/554` covered.",
        f"Identity agreement: `{agreement['agreements']}/{agreement['total_subjects']}` ({agreement['agreement_rate']:.1%}).",
        f"Disagreements: `{agreement['disagreements']}`, fully enumerated in `reconciliation_ledger.jsonl`.",
        "",
        "Both builds read the same frozen M4 snapshot. Build A keeps M4 conflict subjects unresolved unless explicit identity evidence resolves the identity axis; Build B independently iterates reversed inputs and adjudicates product identity whenever explicit identity evidence is present. Reconciliation favours the conservative Build A output for the canonical published ledgers.",
    ]
    (out_dir / "reproducibility" / "BUILD_A_VS_BUILD_B_COMPARISON.md").write_text("\n".join(comparison) + "\n")

    manifest = {
        "milestone": lib.MILESTONE,
        "lineage": lib.LINEAGE,
        "canonical_target": "PDCD1",
        "stage_status": "FINALIZED",
        "snapshot_id": snapshot_id,
        "candidate_identity_schema_version": lib.SCHEMA_VERSION,
        "milestone4_prerequisite": {"snapshot_id": lib.M4_SNAPSHOT_ID},
        "checks": summary,
        "external_authority_capture_performed": False,
        "canonical_candidates_created": True,
        "aliases_adjudicated": True,
        "ownership_claims_created": False,
        "candidate_chronology_created": False,
        "benchmark_labels_created": False,
        "predictions_generated": False,
        "evaluation_performed": False,
    }
    lib.write_json(out_dir / "manifest.json", manifest)
    (out_dir / "commands.jsonl").write_text(
        json.dumps(
            {
                "command": "build_candidate_identity_stage.main",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "input_m4_snapshot_id": lib.M4_SNAPSHOT_ID,
            },
            sort_keys=True,
        )
        + "\n"
    )
    (out_dir / "logs" / "build.jsonl").write_text(
        json.dumps(
            {
                "event": "candidate_identity_stage_build",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "subjects_processed": len(subjects),
                "snapshot_id": snapshot_id,
            },
            sort_keys=True,
        )
        + "\n"
    )
    lib.write_json(out_dir / "receipt.json", receipt_for(out_dir))
    print(json.dumps({"status": "COMPLETED", "snapshot_id": snapshot_id, "summary": summary}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
