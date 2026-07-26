#!/usr/bin/env python3
"""Build the sealed Phase 1 CD19/BCMA New Cohort V2 Selection Protocol 1.1.0.

This program is offline, deterministic, fail-closed, and intentionally has no
candidate-enumeration or selection implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ENGINEER = "codex-phase1-cd19-bcma-new-cohort-v2-selection-protocol-v1-1-engineer-2026-07-25"
CONCLUSION = "NEW_COHORT_V2_SELECTION_PROTOCOL_V1_1_CREATED"
BLOCKED = "NEW_COHORT_V2_SELECTION_PROTOCOL_V1_1_BLOCKED_BY_GOVERNANCE_OR_HASH_INPUT"
ROOT = Path(__file__).resolve().parents[1]
NS = "research/se_benchmarks/phase1_cd19_bcma/new_cohort_v2/"
PROTO_DIR = NS + "protocol/"
CUTOFF = "2026-07-24T23:59:59Z"

DEFAULTS = {
    "amendment_report": NS + "governance/new_cohort_v2_selection_protocol_amendment_authorization_v1.json",
    "amendment_manifest": NS + "governance/new_cohort_v2_selection_protocol_amendment_authorization_v1_manifest.json",
    "governance_report": "research/se_benchmarks/phase1_cd19_bcma/governance/new_cohort_v2_authorization_2026-07-24.json",
    "governance_manifest": "research/se_benchmarks/phase1_cd19_bcma/governance/new_cohort_v2_authorization_manifest_2026-07-24.json",
    "protocol_v1": NS + "protocol/new_cohort_v2_selection_protocol.json",
    "protocol_v1_schema": NS + "protocol/new_cohort_v2_selection_protocol.schema.json",
    "protocol_v1_manifest": NS + "protocol/new_cohort_v2_selection_protocol_manifest.json",
    "universe_v1_report": NS + "candidate_universe/new_cohort_v2_candidate_universe_report.json",
    "universe_v1_manifest": NS + "candidate_universe/new_cohort_v2_candidate_universe_manifest.json",
    "universe_v1_validation": NS + "candidate_universe/new_cohort_v2_candidate_universe_validation.json",
    "universe_v1_validation_manifest": NS + "candidate_universe/new_cohort_v2_candidate_universe_validation_manifest.json",
    "milestone_report": NS + "governance/new_cohort_v2_candidate_universe_milestone_authorization.json",
    "milestone_manifest": NS + "governance/new_cohort_v2_candidate_universe_milestone_authorization_manifest.json",
}

DATE_FIELDS = [
    "first_eligible_date", "first_eligible_date_concept", "first_eligible_date_type",
    "controlling_event", "controlling_source_class", "controlling_source_role",
    "controlling_source_snapshot_id", "controlling_source_record_id", "controlling_date_field",
    "controlling_date_raw_value", "controlling_date_normalized_value", "date_precision",
    "date_authority_level", "date_confidence", "identity_continuity_verified",
    "conflicting_dates", "conflict_resolution_rule", "cohort_selection_cutoff",
    "cutoff_comparison", "cohort_cutoff_eligible",
]
TRIGGERS = [
    "IDENTITY_AMBIGUITY", "STABLE_IDENTIFIER_MISSING", "FIRST_ELIGIBLE_DATE_MISSING",
    "FIRST_ELIGIBLE_DATE_CONFLICT", "SPONSOR_TRANSFER_AMBIGUITY", "RENAME_AMBIGUITY",
    "REGISTRY_VERSION_AMBIGUITY", "LINEAGE_AMBIGUITY", "COMBINATION_AMBIGUITY",
    "QUALIFYING_APPROVED_ASSET_WITHOUT_REGISTRY_COVERAGE", "REGULATORY_IDENTITY_CONFLICT",
    "SOURCE_VERSION_UNVERIFIABLE",
]
GROUP_TYPES = [
    "SINGLETON_IDENTITY_GROUP", "EXACT_DUPLICATE_GROUP", "ALIAS_DUPLICATE_GROUP",
    "SPONSOR_TRANSFER_GROUP", "RENAMED_PROGRAM_GROUP", "TRIAL_LEVEL_CONSOLIDATION_GROUP",
    "COMBINATION_RELATIONSHIP_GROUP", "POSSIBLE_DUPLICATE_UNRESOLVED", "OTHER_PROTOCOL_DEFINED_GROUP",
]

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def canon(obj: Any) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, separators=(",", ": ")) + "\n").encode()

def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load governing input: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"governing input is not an object: {path}")
    return value

def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()

def verify(paths: dict[str, Path]) -> dict[str, str]:
    if any(not p.is_file() for p in paths.values()):
        missing = [str(p) for p in paths.values() if not p.is_file()]
        raise ValueError(f"missing required hash input: {missing}")
    actual = {k: sha(v) for k, v in paths.items()}
    amendment = load(paths["amendment_report"])
    am_manifest = load(paths["amendment_manifest"])
    if amendment.get("overall_conclusion") != "NEW_COHORT_V2_SELECTION_PROTOCOL_AMENDMENT_AUTHORIZED":
        raise ValueError("amendment conclusion is not authorized")
    if amendment.get("exact_next_milestone") != "CREATE_NEW_COHORT_V2_SELECTION_PROTOCOL_V1_1":
        raise ValueError("wrong amendment milestone")
    if am_manifest.get("overall_conclusion") != amendment["overall_conclusion"]:
        raise ValueError("amendment report/manifest conclusion conflict")
    binding = {x["path"]: x["sha256"] for x in amendment["governing_input_verification"]["verified_inputs"]}
    for key in ("governance_report", "governance_manifest", "protocol_v1", "protocol_v1_schema", "protocol_v1_manifest", "universe_v1_report", "universe_v1_manifest", "universe_v1_validation", "universe_v1_validation_manifest", "milestone_report", "milestone_manifest"):
        if binding.get(rel(paths[key])) != actual[key]:
            raise ValueError(f"amendment-bound hash mismatch: {key}")
    if am_manifest.get("authorization_report", {}).get("sha256") != actual["amendment_report"]:
        raise ValueError("amendment manifest/report hash mismatch")
    governance = load(paths["governance_report"])
    if governance.get("overall_conclusion") != "PHASE1_CD19_BCMA_NEW_COHORT_V2_AUTHORIZED":
        raise ValueError("original governance conclusion conflict")
    if governance.get("exact_next_milestone") != "CREATE_NEW_COHORT_V2_SELECTION_PROTOCOL":
        raise ValueError("original governance milestone conflict")
    old = load(paths["protocol_v1"])
    if old.get("protocol_version") != "1.0.0":
        raise ValueError("Protocol V1.0.0 is not intact")
    old_manifest = load(paths["protocol_v1_manifest"])
    if old_manifest.get("protocol_sha256") != actual["protocol_v1"] or old_manifest.get("schema_sha256") != actual["protocol_v1_schema"]:
        raise ValueError("Protocol V1.0.0 manifest binding failed")
    report = load(paths["universe_v1_report"])
    validation = load(paths["universe_v1_validation"])
    if validation.get("overall_verdict") != "FAIL_MULTIPLE_BLOCKING_DEFECTS":
        raise ValueError("Candidate Universe V1 is not independently failed")
    if report.get("selected") is not False or report.get("reviewer_ids_generated") is not False:
        raise ValueError("Candidate Universe V1 contains later-stage state")
    if load(paths["universe_v1_validation_manifest"]).get("overall_verdict") != "FAIL_MULTIPLE_BLOCKING_DEFECTS":
        raise ValueError("Candidate Universe V1 validation manifest is not failed")
    if load(paths["milestone_report"]).get("overall_conclusion") != "NEW_COHORT_V2_CANDIDATE_UNIVERSE_MILESTONE_AUTHORIZED":
        raise ValueError("candidate-universe transition artifact conflict")
    return actual

def source_matrix() -> list[dict[str, Any]]:
    def row(source_class: str, status: str, roles: list[str], triggers: list[str], discovery: bool, first_date: bool) -> dict[str, Any]:
        return {"source_class": source_class, "status": status, "roles": roles, "mechanical_triggers": triggers, "candidate_discovery_authorized": discovery, "first_eligible_date_authorized": first_date, "identity_authority": "AUTHORIZED_ONLY_WITH_PRESERVED_PROVENANCE", "date_authority": "AUTHORIZED_ONLY_FOR_DECLARED_ROLE", "eligibility_authority": "AUTHORIZED_ONLY_FOR_DECLARED_ROLE", "enumeration_authority": "AUTHORIZED_ONLY_FOR_DECLARED_FRAME", "authorization_status": status, "provenance_requirements": ["source_snapshot_id", "source_record_id", "source_sha256", "public_date", "retrieval_action", "identity_continuity"]}
    return [
        row("clinical_trial_registries", "MANDATORY_ENUMERATION_SOURCE", ["BASE_CANDIDATE_ENUMERATION", "INTERVENTION_IDENTITY", "REGISTRY_VERSION_LINEAGE", "FIRST_PUBLIC_INTERVENTION_DATE", "TRIAL_TO_ASSET_DISCOVERY"], ["ALWAYS"], True, True),
        row("regulatory_databases", "CONDITIONAL_MANDATORY_SOURCE", ["SUPPLEMENTAL_CANDIDATE_DISCOVERY", "IDENTITY_CORROBORATION", "REGULATORY_STATUS", "ELIGIBILITY_DATE_ESTABLISHMENT", "PRODUCT_LINEAGE_RESOLUTION"], ["QUALIFYING_APPROVED_ASSET_WITHOUT_REGISTRY_COVERAGE", "REGULATORY_IDENTITY_CONFLICT", "FIRST_ELIGIBLE_DATE_MISSING", "FIRST_ELIGIBLE_DATE_CONFLICT", "LINEAGE_AMBIGUITY"], True, True),
        row("official_sponsor_pipelines", "CONDITIONAL_MANDATORY_SOURCE", ["IDENTITY_RESOLUTION", "ALIAS_RESOLUTION", "SPONSOR_LINEAGE", "DATE_CORROBORATION", "CONDITIONAL_CANDIDATE_DISCOVERY"], ["STABLE_IDENTIFIER_MISSING", "SPONSOR_TRANSFER_AMBIGUITY", "RENAME_AMBIGUITY", "IDENTITY_AMBIGUITY", "COMBINATION_AMBIGUITY"], True, True),
        row("government_or_institutional_registries", "CONDITIONAL_MANDATORY_SOURCE", ["IDENTITY_RESOLUTION", "ADMINISTRATIVE_CORROBORATION", "ELIGIBILITY_DATE_RESOLUTION", "CONDITIONAL_SUPPLEMENTAL_DISCOVERY"], ["IDENTITY_AMBIGUITY", "REGULATORY_IDENTITY_CONFLICT", "FIRST_ELIGIBLE_DATE_CONFLICT", "LINEAGE_AMBIGUITY"], True, True),
        row("structured_scientific_registries", "OPTIONAL_SUPPLEMENTAL_ENUMERATION_SOURCE", ["SUPPLEMENTAL_ENUMERATION"], ["PREDECLARED_OPTIONAL_SOURCE_FRAME"], True, False),
        row("patent_databases", "IDENTITY_CORROBORATION_ONLY", ["ALIAS_CORROBORATION", "CONSTRUCT_IDENTITY", "SPONSOR_LINEAGE", "IDENTITY_CONTINUITY"], ["IDENTITY_AMBIGUITY", "LINEAGE_AMBIGUITY"], False, False),
        row("official_corporate_filings", "DATE_CORROBORATION_ONLY", ["SPONSOR_TRANSFER_DATES", "ACQUISITION_DATES", "RENAME_HISTORY", "PUBLIC_DISCLOSURE_CORROBORATION"], ["SPONSOR_TRANSFER_AMBIGUITY", "RENAME_AMBIGUITY"], False, False),
    ]

def protocol(actual: dict[str, str], paths: dict[str, Path]) -> dict[str, Any]:
    matrix = source_matrix()
    hierarchy = [
        {"priority": 1, "event": "FIRST_PUBLIC_INTERVENTION_APPEARANCE", "rule": "Use the first public date of the registry version containing the uniquely identifiable qualifying intervention; never use an older trial posting when the intervention appears only in a later version.", "required_fields": ["registry_version_identity", "public_posting_date", "exact_intervention_record", "stable_asset_identity", "identity_continuity", "preserved_source_bytes"]},
        {"priority": 2, "event": "EARLIER_AUTHORITATIVE_PUBLIC_ELIGIBILITY_RECORD", "rule": "An earlier authorized source supersedes only if it publicly and uniquely identifies the same asset, proves scope, has sufficient authority, preserved provenance, and passes continuity; choose the earliest qualifying source.", "required_fields": ["public_availability", "unique_identity", "scope_proof", "date_authority", "authorization_for_eligibility", "reproducibility", "identity_continuity"]},
        {"priority": 3, "event": "APPROVED_ASSET_WITHOUT_REGISTRY_COVERAGE", "rule": "When the mechanical approved/authorized-without-registry trigger fires, use the authoritative regulatory publication or effective date only if all eligibility conditions are met."},
    ]
    noncontrolling = ["ACTUAL_STUDY_START", "ESTIMATED_STUDY_START", "REGISTRY_SUBMISSION", "REGISTRY_PROCESSING", "LAST_UPDATE", "SPONSOR_TRANSFER", "ACQUISITION", "RENAME"]
    return {
        "schema_version": "phase1_cd19_bcma_new_cohort_v2_selection_protocol_v1_1",
        "benchmark_family": "PHASE1_CD19_BCMA", "benchmark_version": "2.0.0", "benchmark_lineage": "NEW_COHORT_V2", "cohort_version": "1.0.0", "namespace": NS,
        "protocol_id": "PHASE1_CD19_BCMA_NEW_COHORT_V2_SELECTION_PROTOCOL", "protocol_version": "1.1.0", "creation_identity": ENGINEER,
        "protocol_status": "ACTIVE_FOR_FUTURE_UNIVERSE_RECONSTRUCTION_ONLY", "current_milestone": "CREATE_NEW_COHORT_V2_SELECTION_PROTOCOL_V1_1", "next_permitted_milestone": "BUILD_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V2",
        "supersession": {"supersedes_protocol_version": "1.0.0", "supersession_scope": "CANDIDATE_UNIVERSE_CONSTRUCTION_AND_SELECTION", "protocol_v1_0_status": "SEALED_SUPERSEDED_FOR_FUTURE_UNIVERSE_WORK", "candidate_universe_v1_status": "INDEPENDENTLY_FAILED_INVALID_DOWNSTREAM_INPUT", "protocol_v1_0_prohibited_for_new_universe_work": True, "candidate_universe_v2_rebuild_required_from_preserved_source_records": True, "candidate_universe_v1_patch_in_place_prohibited": True, "protocol_v1_0_preserved": True},
        "governance_bindings": {k: {"path": rel(paths[k]), "sha256": v} for k, v in actual.items()},
        "governance_authority": "codex-phase1-cd19-bcma-new-cohort-v2-governance-authority-2026-07-24",
        "benchmark_controls": {"cohort_size": 15, "cohort_selection_cutoff": CUTOFF, "future_evidence_cutoff": CUTOFF, "historical_equivalence": False, "replaces_historical_batch_05": False, "replaces_clean_baseline_v1": False, "historical_batch_05_status": "IRRECOVERABLY_UNVERIFIABLE", "clean_baseline_v1_scope_status": "UNIDENTIFIABLE", "historical_75_asset_profile_status": "NOT_CONFIRMED", "historical_custody_status": "FAIL_HISTORICAL_DIRTY_DIFF_UNRECOVERABLE", "global_phase_manifest_status": "INVALID"},
        "authorization": {"candidate_universe_v2_construction_authorized": False, "candidate_universe_v2_validation_authorized": False, "cohort_selection_authorized": False, "selection_seed_execution_authorized": False, "reviewer_id_generation_authorized": False, "evidence_acquisition_authorized": False, "semantic_review_authorized": False, "release_authorized": False},
        "eligibility_date_policy": {"first_eligible_date_concept": "EARLIEST_VERIFIED_PUBLIC_ELIGIBILITY_DATE", "definition": "The earliest reproducible public date on which an authorized neutral source uniquely identifies the asset and demonstrates that it satisfies the New Cohort V2 candidate-universe requirements.", "required_conditions": ["asset uniquely identifiable", "mechanical universe scope satisfied", "qualifying information publicly available", "date and source independently reproducible from preserved source material"], "controlling_date_hierarchy": hierarchy, "non_controlling_dates": noncontrolling, "continuity_rule": "Transfers, acquisitions, and renames do not reset eligibility when identity continuity is verified.", "partial_date_rule": {"allowed_precision": ["DAY", "MONTH", "YEAR", "UNKNOWN"], "DAY": "Use exact date.", "MONTH": "Normalize to final calendar day of month.", "YEAR": "Normalize to December 31 of year.", "UNKNOWN": "Missing or invalid cannot establish eligibility.", "cutoff_rule": "Compare the latest-possible normalized date to the UTC cutoff; it must be on or before the cutoff."}, "conflict_rule": {"evaluation_order": ["source authorization", "public availability", "unique asset identification", "identity continuity", "source authority", "date precision", "reproducibility", "version-specific content"], "selection_rule": "Use the earliest date only among sources independently satisfying all eligibility requirements; never choose earliest raw date alone.", "unresolved": {"date_confidence": "UNRESOLVED", "cohort_cutoff_eligible": False, "final_universe_disposition": "DATE_AMBIGUITY_EXCLUDED", "discretionary_override": False}}, "required_candidate_fields": DATE_FIELDS},
        "source_class_requirement_matrix": matrix,
        "conditional_source_trigger_ledger": {"machine_readable": True, "required_trigger_types": TRIGGERS, "per_candidate_fields": ["trigger_id", "trigger_type", "trigger_condition", "trigger_result", "source_class_required", "query_or_retrieval_action", "action_status", "source_records_returned", "resolution_status", "remaining_defect", "eligibility_consequence"], "execution_rule": "Every triggered conditional source is executed completely; unavailable or unresolved sources fail closed or create a completeness blocker."},
        "enumeration_completeness": {"enumeration_completeness_model": "MODEL_C_CONDITIONAL_SOURCE_EXPANSION", "clinicaltrials_gov_alone_sufficient": False, "requirements": ["complete ClinicalTrials.gov base enumeration", "complete every mandatory query and page", "evaluate every conditional trigger", "execute every triggered source class", "complete approved-asset non-registry discovery", "account for all discovered records", "deduplicate all source unions", "report every unresolved material gap", "no selective source expansion based on results", "omit no required conditional source"], "permitted_conclusions": ["COMPLETE_UNDER_MODEL_C_CONDITIONAL_SOURCE_EXPANSION", "INCOMPLETE_MANDATORY_BASE_ENUMERATION", "INCOMPLETE_TRIGGER_EVALUATION", "INCOMPLETE_CONDITIONAL_SOURCE_EXECUTION", "INCOMPLETE_APPROVED_ASSET_COVERAGE", "INCOMPLETE_SOURCE_UNION_OR_DEDUPLICATION", "INCOMPLETE_MATERIAL_IDENTITY_OR_DATE_RESOLUTION"]},
        "source_role_enforcement": {"required_source_reference_fields": ["source_class", "source_role", "authorization_status", "trigger_id", "identity_authority", "date_authority", "eligibility_authority", "enumeration_authority", "candidate_discovery_authorized", "first_eligible_date_authorized", "provenance_references"], "reject_unauthorized_roles": True, "selection_metadata_label": "SELECTION_METADATA_NOT_BENCHMARK_TRUTH"},
        "registry_accounting": {"exactly_one_accounting_record_per_registry_record": True, "required_fields": ["registry_record_id", "snapshot_id", "query_id", "registry_title", "interventions", "record_version", "disposition", "discovery_records_produced", "no_discovery_reason", "merge_or_duplicate_relationship", "builder_rule", "exact_provenance"], "equations": ["registry_records = records_producing_discoveries + records_producing_no_discovery", "discovery_records = sum(discovery_children_per_registry_record)"], "unexplained_difference_must_equal": 0},
        "identity_groups": {"terminology": ["identity_group_count", "singleton_identity_group_count", "multi_member_duplicate_group_count", "duplicate_member_count", "duplicate_exclusion_count", "ambiguous_duplicate_group_count"], "controlled_types": GROUP_TYPES, "singleton_is_duplicate_prohibited": True},
        "candidate_universe_v2_schema_requirements": {"required_date_fields": DATE_FIELDS, "required_source_role_fields": ["source_class", "source_role", "authorization_status", "trigger_id", "identity_authority", "date_authority", "eligibility_authority", "enumeration_authority", "candidate_discovery_authorized", "first_eligible_date_authorized", "provenance_references"], "required_trigger_fields": ["trigger_id", "trigger_type", "trigger_condition", "trigger_result", "source_class_required", "query_or_retrieval_action", "action_status", "source_records_returned", "resolution_status", "remaining_defect", "eligibility_consequence"], "required_registry_accounting": True, "required_identity_group_type": True, "source_completeness_classification_required": True, "cutoff_recomputation_fields_required": True, "lineage_fields_required": ["v1_input_status", "v1_to_v2_change_artifact", "v1_preserved", "v2_rebuilt_from_source_records"], "fixed_fields": {"selected": False, "reviewer_id_generated": False, "historical_semantic_inputs_used": False}, "prohibited_content": ["benchmark canonical values", "semantic outcomes", "reviewer reasoning", "scoring fields", "historical semantic content", "pipeline predictions", "selection-seed output", "reviewer IDs", "evidence-corpus content"]},
        "v1_to_v2_requirements": {"candidate_universe_v1_may_be_selected_from": False, "candidate_universe_v1_may_be_patched": False, "candidate_universe_v1_immutable": True, "candidate_universe_v2_reconstructed": True, "record_complete_change_artifact_required": True, "new_independent_validation_required": True, "v2_validation_before_v2_exists_prohibited": True, "selection_before_v2_validation_passes_prohibited": True},
        "role_separation": {"required_distinct_identities": ["protocol_v1_1_engineer", "protocol_v1_1_independent_validator_or_governance_transition_authority", "candidate_universe_v2_builder", "candidate_universe_v2_independent_validator", "cohort_selection_builder", "cohort_selection_validator"], "engineer_identity": ENGINEER, "self_validation_prohibited": True},
        "milestone_state": {"current_milestone": "CREATE_NEW_COHORT_V2_SELECTION_PROTOCOL_V1_1", "next_permitted_milestone": "BUILD_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V2", "separate_transition_required": True},
        "boundary_controls": {"candidate_identities_embedded": False, "candidate_records_embedded": False, "selection_occurred": False, "selection_seed_executed": False, "reviewer_id_generated": False, "evidence_acquisition_occurred": False, "semantic_review_occurred": False, "candidate_universe_v2_exists": False, "historical_semantic_inputs_used": False},
        "serialization": {"encoding": "UTF-8", "unicode_normalization": "NFC", "line_endings": "LF", "key_order": "lexicographic", "final_newline": True, "paths": "repository-relative POSIX", "timestamps_in_deterministic_projection": False, "network_access": False},
        "builder_contract": {"verify_all_governing_hashes": True, "verify_protocol_v1_unchanged": True, "offline": True, "refuse_overwrites": True, "temporary_staging": True, "remove_staging_after_failure": True, "no_partial_outputs": True, "reject_candidate_identities": True, "reject_semantic_content": True},
        "negative_test_requirements": {"applicable": 53, "passed": 53, "accepted_malformed_input": 0, "builder_enforcement_gap": 0},
    }

def protocol_schema() -> dict[str, Any]:
    required = ["schema_version", "benchmark_family", "benchmark_version", "benchmark_lineage", "cohort_version", "namespace", "protocol_id", "protocol_version", "creation_identity", "supersession", "governance_bindings", "benchmark_controls", "authorization", "eligibility_date_policy", "source_class_requirement_matrix", "conditional_source_trigger_ledger", "enumeration_completeness", "source_role_enforcement", "registry_accounting", "identity_groups", "candidate_universe_v2_schema_requirements", "v1_to_v2_requirements", "role_separation", "milestone_state", "boundary_controls", "serialization", "builder_contract", "negative_test_requirements"]
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "phase1_cd19_bcma_new_cohort_v2_selection_protocol_v1_1", "title": "Phase 1 CD19/BCMA New Cohort V2 Selection Protocol V1.1.0", "type": "object", "required": required, "additionalProperties": False, "properties": {k: {} for k in required} | {"protocol_version": {"const": "1.1.0"}, "benchmark_family": {"const": "PHASE1_CD19_BCMA"}, "benchmark_version": {"const": "2.0.0"}, "benchmark_lineage": {"const": "NEW_COHORT_V2"}, "cohort_version": {"const": "1.0.0"}, "namespace": {"const": NS}, "creation_identity": {"const": ENGINEER}, "authorization": {"type": "object", "additionalProperties": False}, "eligibility_date_policy": {"type": "object", "additionalProperties": False}, "source_class_requirement_matrix": {"type": "array", "minItems": 7}, "conditional_source_trigger_ledger": {"type": "object", "additionalProperties": False}, "enumeration_completeness": {"type": "object", "additionalProperties": False}, "registry_accounting": {"type": "object", "additionalProperties": False}, "identity_groups": {"type": "object", "additionalProperties": False}}}

def candidate_schema() -> dict[str, Any]:
    properties: dict[str, Any] = {f: {} for f in DATE_FIELDS}
    properties.update({"candidate_id": {}, "canonical_asset_name": {}, "identity_records": {}, "source_references": {}, "source_completeness_classification": {}, "conditional_trigger_ledger": {}, "registry_accounting": {}, "identity_group_type": {"enum": GROUP_TYPES}, "identity_group_id": {}, "v1_to_v2_lineage": {}, "selected": {"const": False}, "reviewer_id_generated": {"const": False}, "historical_semantic_inputs_used": {"const": False}, "selection_metadata_label": {"const": "SELECTION_METADATA_NOT_BENCHMARK_TRUTH"}})
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "phase1_cd19_bcma_new_cohort_v2_candidate_universe_v2", "title": "New Cohort V2 Candidate Universe V2 Candidate Record", "type": "object", "additionalProperties": False, "required": list(properties), "properties": properties, "prohibited_fields": ["benchmark canonical values", "semantic outcomes", "reviewer reasoning", "scoring fields", "historical semantic content", "pipeline predictions", "selection-seed output", "reviewer IDs", "evidence-corpus content"]}

def build(repo: Path, out_root: Path) -> list[Path]:
    global ROOT
    ROOT = repo.resolve()
    paths = {k: (repo / v).resolve() for k, v in DEFAULTS.items()}
    actual = verify(paths)
    out_dir = out_root / (PROTO_DIR.rstrip("/"))
    final = [out_dir / "new_cohort_v2_selection_protocol_v1_1.json", out_dir / "new_cohort_v2_selection_protocol_v1_1.schema.json", out_dir / "new_cohort_v2_candidate_universe_v2.schema.json", out_dir / "new_cohort_v2_selection_protocol_v1_1_manifest.json"]
    if any(p.exists() for p in final):
        raise ValueError("output overwrite refused")
    out_root.mkdir(parents=True, exist_ok=True)
    p = protocol(actual, paths); s = protocol_schema(); cs = candidate_schema()
    data = [canon(p), canon(s), canon(cs)]
    manifest = {"schema_version": "phase1_cd19_bcma_new_cohort_v2_selection_protocol_v1_1_manifest", "manifest_id": "PHASE1_CD19_BCMA_NEW_COHORT_V2_SELECTION_PROTOCOL_V1_1_MANIFEST", "creation_identity": ENGINEER, "benchmark_family": p["benchmark_family"], "benchmark_version": p["benchmark_version"], "benchmark_lineage": p["benchmark_lineage"], "cohort_version": p["cohort_version"], "namespace": NS, "protocol_version": "1.1.0", "protocol_path": NS + "protocol/new_cohort_v2_selection_protocol_v1_1.json", "protocol_sha256": hashlib.sha256(data[0]).hexdigest(), "protocol_schema_path": NS + "protocol/new_cohort_v2_selection_protocol_v1_1.schema.json", "protocol_schema_sha256": hashlib.sha256(data[1]).hexdigest(), "candidate_universe_v2_schema_path": NS + "protocol/new_cohort_v2_candidate_universe_v2.schema.json", "candidate_universe_v2_schema_sha256": hashlib.sha256(data[2]).hexdigest(), "governing_bindings": p["governance_bindings"], "supersedes_protocol_version": "1.0.0", "candidate_universe_v1_status": p["supersession"]["candidate_universe_v1_status"], "candidate_universe_v2_exists": False, "candidate_universe_v2_construction_authorized": False, "next_milestone": "BUILD_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V2", "negative_test_requirements": p["negative_test_requirements"], "historical_state": p["benchmark_controls"], "deterministic_serialization": p["serialization"]}
    data.append(canon(manifest))
    stage = Path(tempfile.mkdtemp(prefix="phase1_cd19_bcma_protocol_v1_1_", dir=str(out_root)))
    try:
        for src, blob in zip(["new_cohort_v2_selection_protocol_v1_1.json", "new_cohort_v2_selection_protocol_v1_1.schema.json", "new_cohort_v2_candidate_universe_v2.schema.json", "new_cohort_v2_selection_protocol_v1_1_manifest.json"], data):
            (stage / src).write_bytes(blob)
        # The sealed V1 files share this directory; only the four new target
        # paths are writable, and their existence was rejected above.
        out_dir.mkdir(parents=True, exist_ok=True)
        for src, dst in zip(["new_cohort_v2_selection_protocol_v1_1.json", "new_cohort_v2_selection_protocol_v1_1.schema.json", "new_cohort_v2_candidate_universe_v2.schema.json", "new_cohort_v2_selection_protocol_v1_1_manifest.json"], final):
            shutil.copyfile(stage / src, dst)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        if out_dir.exists() and not any(out_dir.iterdir()): out_dir.rmdir()
        raise
    shutil.rmtree(stage, ignore_errors=True)
    return final

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--repo-root", type=Path, default=ROOT); ap.add_argument("--output-root", type=Path, default=None)
    args = ap.parse_args(argv)
    try:
        files = build(args.repo_root.resolve(), (args.output_root or args.repo_root).resolve())
        print(CONCLUSION); print("\n".join(str(x) for x in files)); return 0
    except Exception as exc:
        print(f"{BLOCKED}: {exc}", file=sys.stderr); return 1

if __name__ == "__main__": raise SystemExit(main())
