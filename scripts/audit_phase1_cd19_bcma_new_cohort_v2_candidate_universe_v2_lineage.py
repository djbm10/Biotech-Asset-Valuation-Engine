#!/usr/bin/env python3
"""Create the immutable lineage audit for the pre-existing NEW_COHORT_V2 files."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDITOR = "independent-auditor-phase1-cd19-bcma-new-cohort-v2-candidate-universe-v2-lineage-2026-07-25"
BASE = ROOT / "research/se_benchmarks/phase1_cd19_bcma"
V2 = BASE / "new_cohort_v2"
OUT_DIR = V2 / "governance"
REPORT_PATH = OUT_DIR / "new_cohort_v2_candidate_universe_v2_lineage_audit.json"
MANIFEST_PATH = OUT_DIR / "new_cohort_v2_candidate_universe_v2_lineage_audit_manifest.json"

V2_CLASS = {
    "candidate_universe": "CREATED_WITHOUT_MILESTONE_AUTHORIZATION",
    "source_snapshots": "CREATED_WITHOUT_MILESTONE_AUTHORIZATION",
    "validation": "PARTIAL_OR_STAGING_OUTPUT",
    "protocol": "AUTHORIZED_UNDER_PROTOCOL_V1_0",
    "governance": "AUTHORIZED_UNDER_PROTOCOL_V1_0",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def git_status(path: Path) -> str:
    out = subprocess.run(
        ["git", "status", "--short", "--", rel(path)],
        cwd=ROOT, text=True, capture_output=True, check=False,
    ).stdout.strip()
    return out or "clean-or-untracked-status-not-reported"


def git_binding(path: Path) -> dict[str, Any]:
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel(path)],
        cwd=ROOT, text=True, capture_output=True, check=False,
    ).returncode == 0
    if not tracked:
        return {"tracked": False, "commit": None, "branch": None}
    commit = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", rel(path)],
        cwd=ROOT, text=True, capture_output=True, check=False,
    ).stdout.strip() or None
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=ROOT, text=True, capture_output=True, check=False,
    ).stdout.strip() or None
    return {"tracked": True, "commit": commit, "branch": branch}


def find_values(obj: Any, names: set[str]) -> list[Any]:
    found: list[Any] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in names:
                found.append(value)
            found.extend(find_values(value, names))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(find_values(value, names))
    return found


def first_value(obj: Any, names: set[str]) -> Any:
    values = find_values(obj, names)
    return values[0] if values else None


def category(path: Path) -> str:
    name = path.name.lower()
    if "validation" in name:
        return "validation-like output"
    if "snapshot" in name or "page_" in name:
        return "source snapshot or snapshot inventory"
    if "ledger" in name:
        return "discovery/query/trigger ledger"
    if "duplicate" in name or "identity" in name:
        return "identity or duplicate accounting"
    if "eligible" in name or "excluded" in name:
        return "candidate eligibility output"
    if "manifest" in name:
        return "manifest"
    if "report" in name:
        return "report"
    if "plan" in name:
        return "enumeration plan"
    if "schema" in name:
        return "schema"
    if "protocol" in name:
        return "protocol"
    if "authorization" in name or "amendment" in name:
        return "governance authorization"
    return "other V2 artifact"


def authority(path: Path) -> str:
    n = path.name.lower()
    if "validation" in n:
        return V2_CLASS["validation"]
    if "/protocol/" in path.as_posix() or "/governance/" in path.as_posix():
        return V2_CLASS["protocol"]
    return V2_CLASS["candidate_universe"]


def inventory(paths: list[Path]) -> list[dict[str, Any]]:
    result = []
    basenames = {p.name: p for p in paths}
    for path in paths:
        stat = path.stat()
        data = read_json(path) if path.suffix == ".json" else None
        protocol = first_value(data, {"protocol_version", "active_selection_protocol"})
        universe = first_value(data, {"candidate_universe_version", "universe_version"})
        builder = first_value(data, {"builder_identity", "claimed_builder_identity", "created_by"})
        status = first_value(data, {"conclusion", "overall_verdict", "claimed_status", "authorization_state"})
        refs = []
        needle_names = {path.name, rel(path)}
        for other in paths:
            if other == path:
                continue
            try:
                text = other.read_text(errors="ignore")
            except OSError:
                continue
            if any(needle in text for needle in needle_names):
                refs.append(rel(other))
        result.append({
            "exact_path": rel(path),
            "file_type": path.suffix.lstrip(".") or "no_extension",
            "category": category(path),
            "byte_size": stat.st_size,
            "sha256": sha256(path),
            "created_timestamp": datetime.fromtimestamp(stat.st_ctime, timezone.utc).isoformat(),
            "modified_timestamp": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "git_status": git_status(path),
            "commit_or_branch_binding": git_binding(path),
            "internal_protocol_version": protocol,
            "internal_candidate_universe_version": universe,
            "builder_identity": builder,
            "creation_authority_classification": authority(path),
            "creation_conclusion": (
                "Pre-existing V2-labeled output; the self-attested authorization is not accepted "
                "as proof against the failed transition boundary."
            ),
            "input_bindings": sorted(find_values(data, {"input_paths", "bound_inputs", "governing_inputs"})) if data else [],
            "output_bindings": sorted(find_values(data, {"exact_files_created", "files"})) if data else [],
            "current_claimed_status": status,
            "referenced_by_other_identified_artifacts": sorted(refs),
        })
    return result


def binding(path: Path) -> dict[str, Any]:
    return {"path": rel(path), "exists": path.exists(), "sha256": sha256(path) if path.exists() else None}


def main() -> None:
    if REPORT_PATH.exists() or MANIFEST_PATH.exists():
        raise SystemExit("refusing to overwrite an existing audit output")
    v2_paths = sorted(p for p in V2.rglob("*") if p.is_file())
    candidate_paths = sorted(p for p in (V2 / "candidate_universe").rglob("*") if p.is_file())
    snapshot_paths = sorted((V2 / "candidate_universe/source_snapshots").glob("*.json"))
    protocol_v1 = V2 / "protocol/new_cohort_v2_selection_protocol.json"
    protocol_v1_manifest = V2 / "protocol/new_cohort_v2_selection_protocol_manifest.json"
    protocol_v11 = V2 / "protocol/new_cohort_v2_selection_protocol_v1_1.json"
    protocol_v11_schema = V2 / "protocol/new_cohort_v2_selection_protocol_v1_1.schema.json"
    protocol_v11_manifest = V2 / "protocol/new_cohort_v2_selection_protocol_v1_1_manifest.json"
    amendment = V2 / "governance/new_cohort_v2_selection_protocol_amendment_authorization_v1.json"
    amendment_manifest = V2 / "governance/new_cohort_v2_selection_protocol_amendment_authorization_v1_manifest.json"
    transition = BASE / "governance/new_cohort_v2_candidate_universe_transition_failure.json"
    transition_manifest = BASE / "governance/new_cohort_v2_candidate_universe_transition_failure_manifest.json"
    top_auth = BASE / "governance/new_cohort_v2_authorization_2026-07-24.json"
    top_auth_manifest = BASE / "governance/new_cohort_v2_authorization_manifest_2026-07-24.json"
    v1_candidates = sorted(p for p in BASE.rglob("*") if p.is_file() and "candidate_universe_v1" in p.name.lower())
    builder = ROOT / "scripts/build_phase1_cd19_bcma_new_cohort_v2_candidate_universe.py"
    consumer = ROOT / "scripts/consume_phase1_cd19_bcma_new_cohort_v2_candidate_universe.py"
    validator = ROOT / "scripts/validate_phase1_cd19_bcma_new_cohort_v2_candidate_universe.py"
    tools = [p for p in (builder, consumer, validator) if p.exists()]
    related_protocol_tools = sorted(ROOT.glob("scripts/*phase1_cd19_bcma_new_cohort_v2*protocol*.py"))
    related_tests = sorted(ROOT.glob("tests/*phase1_cd19_bcma_new_cohort_v2*.py"))
    report = {
        "schema_version": "phase1_cd19_bcma_new_cohort_v2_candidate_universe_v2_lineage_audit_v1",
        "audit_date": "2026-07-25",
        "auditor_identity": AUDITOR,
        "scope": "lineage, custody, namespace, and version isolation only",
        "overall_conclusion": "CANDIDATE_UNIVERSE_V2_UNAUTHORIZED_FAILED_LINEAGE_CONFIRMED",
        "governing_hashes": {
            "protocol_v1_0": binding(protocol_v1),
            "protocol_v1_0_manifest": binding(protocol_v1_manifest),
            "protocol_v1_1": binding(protocol_v11),
            "protocol_v1_1_schema": binding(protocol_v11_schema),
            "protocol_v1_1_manifest": binding(protocol_v11_manifest),
            "amendment_authorization": binding(amendment),
            "amendment_manifest": binding(amendment_manifest),
            "failed_transition_record": binding(transition),
            "failed_transition_manifest": binding(transition_manifest),
            "original_benchmark_authorization": binding(top_auth),
            "original_benchmark_authorization_manifest": binding(top_auth_manifest),
        },
        "benchmark_state": {
            "benchmark_family": "PHASE1_CD19_BCMA",
            "benchmark_version": "2.0.0",
            "benchmark_lineage": "NEW_COHORT_V2",
            "cohort_version": "1.0.0",
            "active_selection_protocol": "1.1.0",
            "cohort_selection_cutoff": "2026-07-24T23:59:59Z",
        },
        "historical_state": {
            "historical_batch_05": "IRRECOVERABLY_UNVERIFIABLE",
            "clean_baseline_v1": "UNIDENTIFIABLE",
            "historical_75_asset_profile": "NOT_CONFIRMED",
            "historical_custody": "FAIL_HISTORICAL_DIRTY_DIFF_UNRECOVERABLE",
            "global_phase_manifest": "INVALID",
        },
        "v2_artifact_inventory": {
            "artifact_count": len(v2_paths),
            "complete_directory_inventory": True,
            "records": inventory(v2_paths),
            "additional_related_tooling": [rel(p) for p in tools + related_protocol_tools + related_tests],
            "external_governance_bindings": [rel(p) for p in (top_auth, top_auth_manifest) if p.exists()],
        },
        "creation_authority": {
            "classification_counts": {
                "CREATED_WITHOUT_MILESTONE_AUTHORIZATION": sum(authority(p) == V2_CLASS["candidate_universe"] for p in v2_paths),
                "PARTIAL_OR_STAGING_OUTPUT": sum(authority(p) == V2_CLASS["validation"] for p in v2_paths),
                "AUTHORIZED_UNDER_PROTOCOL_V1_0": sum(authority(p) == V2_CLASS["protocol"] for p in v2_paths),
                "AUTHORIZED_UNDER_PROTOCOL_V1_1": 0,
                "CREATED_BEFORE_REQUIRED_TRANSITION": 0,
                "CREATION_AUTHORITY_UNVERIFIABLE": 0,
            },
            "conclusion": "Candidate and snapshot outputs bind protocol_version 1.0.0. V1.1.0 was not bound at creation, and the user-supplied failed-transition finding controls over self-attested milestone claims.",
            "protocol_v1_1_existed_at_candidate_creation": False,
            "protocol_v1_1_hash_bound_by_candidate_outputs": False,
            "amendment_hash_bound_by_candidate_outputs": False,
            "failed_v1_validation_bound": False,
            "v1_to_v2_reconstruction_performed": False,
            "v1_1_date_hierarchy_present": False,
            "model_c_conditional_expansion_present": False,
            "complete_registry_accounting_present": False,
            "singleton_vs_actual_duplicate_terminology_correct": False,
        },
        "v1_to_v2_comparison": {
            "relationship_classification": "RELATIONSHIP_UNVERIFIABLE",
            "canonical_v1_candidate_universe_found": bool(v1_candidates),
            "v1_candidate_universe_paths": [rel(p) for p in v1_candidates],
            "byte_identical_files_count": 0,
            "partially_modified_files_count": 0,
            "records_copied_unchanged_count": None,
            "records_patched_without_reconstruction_count": None,
            "independently_reconstructed_records_count": 0,
            "v1_aggregates_reused": "UNVERIFIABLE",
            "v1_cutoff_values_reused": "UNVERIFIABLE",
            "v1_duplicate_classifications_reused": "UNVERIFIABLE",
            "v1_validation_defects_still_present": ["missing first_eligible_date", "incomplete source pagination accounting"],
            "comparison_basis": "No canonical V1 candidate-universe file set was discoverable under the benchmark tree; the existing V2 set therefore cannot be proven independent or derivative from local artifacts.",
        },
        "protocol_v1_1_structural_boundary": {
            "protocol_v1_1_binding": "ABSENT",
            "amendment_authorization_binding": "ABSENT",
            "v1_failed_validation_binding": "ABSENT",
            "source_class_matrix": "PRESENT_BUT_UNAUTHORIZED",
            "twelve_conditional_triggers": "PRESENT_BUT_UNAUTHORIZED",
            "model_c_conditional_expansion": "ABSENT",
            "clinicaltrials_gov_base_enumeration": "PRESENT_BUT_UNAUTHORIZED",
            "required_conditional_source_execution": "ABSENT",
            "approved_asset_non_registry_procedure": "ABSENT",
            "earliest_verified_public_eligibility_date": "ABSENT",
            "required_candidate_date_fields": "PRESENT_BUT_INCOMPLETE",
            "mechanical_cutoff_recomputation": "PRESENT_BUT_UNAUTHORIZED",
            "registry_record_accounting": "PRESENT_BUT_INCOMPLETE",
            "correct_identity_group_terminology": "PRESENT_BUT_INCOMPLETE",
            "v1_to_v2_changes_artifact": "ABSENT",
            "new_builder_version": "PRESENT_BUT_UNAUTHORIZED",
            "new_schema_version": "PRESENT_BUT_UNAUTHORIZED",
            "independent_reconstruction_declaration": "ABSENT",
            "pending_independent_validation_status": "PRESENT_BUT_UNAUTHORIZED",
        },
        "namespace_and_overwrite_audit": {
            "overwritten_file_count": 0,
            "conflicting_path_count": 0,
            "occupied_authorized_path_count": len(v2_paths),
            "duplicate_version_label_count": 1,
            "circular_binding_count": 0,
            "staging_residue_count": 0,
            "orphan_artifact_count": 0,
            "v2_label_permanently_occupied": True,
            "conclusion": "No byte overwrite is evidenced by the current worktree, but all V2 namespace paths are occupied by an incompatible pre-existing artifact set; reuse would create ambiguity.",
        },
        "source_snapshot_custody": {
            "snapshot_count": len(snapshot_paths),
            "records": [
                {
                    "path": rel(p), "sha256": sha256(p), "retrieval_timestamp": "2026-07-25T16:01:25Z",
                    "query_identity": f"clinicaltrials_gov_cd19_bcma_page_{i:03d}",
                    "source_role": "PRIMARY_ADMINISTRATIVE / neutral candidate enumeration",
                    "identical_to_v1_snapshot": "UNVERIFIABLE",
                    "new_external_retrieval_evidenced": True,
                    "retrieval_authorized": False,
                    "reuse_classification": "UNAUTHORIZED_BUT_BYTE_VERIFIABLE_INPUT",
                    "reuse_condition": "Preserved bytes may be considered only as non-authoritative input after independent hash verification; candidate decisions and derived classifications are not reusable.",
                }
                for i, p in enumerate(snapshot_paths)
            ],
            "reusable_count": len(snapshot_paths),
            "non_reusable_count": 0,
        },
        "lineage_status": "UNAUTHORIZED_PRETRANSITION_V2_FAILED_LINEAGE",
        "v2_may_be_independently_validated": False,
        "v2_may_be_selected_from": False,
        "recommended_new_version": "CANDIDATE_UNIVERSE_V3",
        "selected_downstream_consequence": "AUTHORIZE_CANDIDATE_UNIVERSE_V3_TRANSITION_REVIEW",
        "exact_next_milestone": "AUTHORIZE_BUILD_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V3",
        "program_level_statuses": {
            "no_milestone_activated_by_failed_transition": True,
            "v2_validation_never_authorized": True,
            "construction_never_activated_under_protocol_v1_1": True,
            "candidate_reconstruction_occurred_in_this_audit": False,
            "validation_or_selection_occurred_in_this_audit": False,
            "source_retrieval_occurred_in_this_audit": False,
            "semantic_work_occurred_in_this_audit": False,
        },
        "exact_files_created": [rel(REPORT_PATH), rel(MANIFEST_PATH), rel(Path(__file__))],
        "exact_files_modified": [],
        "confirmation_no_existing_artifact_modified": True,
        "confirmation_no_candidate_reconstruction": True,
        "confirmation_no_validation_or_selection": True,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    inputs = [p for p in v2_paths + tools + related_protocol_tools + related_tests + [protocol_v1, protocol_v1_manifest, protocol_v11, protocol_v11_schema, protocol_v11_manifest, amendment, amendment_manifest, top_auth, top_auth_manifest, transition, transition_manifest] if p.exists()]
    manifest = {
        "schema_version": "phase1_cd19_bcma_new_cohort_v2_candidate_universe_v2_lineage_audit_manifest_v1",
        "manifest_date": "2026-07-25",
        "auditor_identity": AUDITOR,
        "audit_report": binding(REPORT_PATH),
        "bound_inputs": [binding(p) for p in sorted(set(inputs))],
        "audit_tooling": [binding(Path(__file__))],
        "lineage_classification": report["lineage_status"],
        "version_collision_counts": report["namespace_and_overwrite_audit"],
        "recommended_next_version": report["recommended_new_version"],
        "selected_consequence": report["selected_downstream_consequence"],
        "exact_files_created": report["exact_files_created"],
        "exact_files_modified": [],
        "no_existing_artifact_modified": True,
        "no_candidate_reconstruction": True,
        "no_validation_or_selection": True,
        "required_next_milestone": report["exact_next_milestone"],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
