#!/usr/bin/env python3
"""Standalone, fail-closed consumer for Selection Protocol V1.1.0.

It deliberately does not import the builder or any candidate-universe code.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

NS = "research/se_benchmarks/phase1_cd19_bcma/new_cohort_v2/"
CUTOFF = "2026-07-24T23:59:59Z"
CONCLUSION = "NEW_COHORT_V2_SELECTION_PROTOCOL_V1_1_CREATED"
DATE_FIELDS = ["first_eligible_date", "first_eligible_date_concept", "first_eligible_date_type", "controlling_event", "controlling_source_class", "controlling_source_role", "controlling_source_snapshot_id", "controlling_source_record_id", "controlling_date_field", "controlling_date_raw_value", "controlling_date_normalized_value", "date_precision", "date_authority_level", "date_confidence", "identity_continuity_verified", "conflicting_dates", "conflict_resolution_rule", "cohort_selection_cutoff", "cutoff_comparison", "cohort_cutoff_eligible"]
TRIGGERS = {"IDENTITY_AMBIGUITY", "STABLE_IDENTIFIER_MISSING", "FIRST_ELIGIBLE_DATE_MISSING", "FIRST_ELIGIBLE_DATE_CONFLICT", "SPONSOR_TRANSFER_AMBIGUITY", "RENAME_AMBIGUITY", "REGISTRY_VERSION_AMBIGUITY", "LINEAGE_AMBIGUITY", "COMBINATION_AMBIGUITY", "QUALIFYING_APPROVED_ASSET_WITHOUT_REGISTRY_COVERAGE", "REGULATORY_IDENTITY_CONFLICT", "SOURCE_VERSION_UNVERIFIABLE"}
STATUSES = {"MANDATORY_ENUMERATION_SOURCE", "CONDITIONAL_MANDATORY_SOURCE", "OPTIONAL_SUPPLEMENTAL_ENUMERATION_SOURCE", "IDENTITY_CORROBORATION_ONLY", "DATE_CORROBORATION_ONLY"}
GROUP_TYPES = {"SINGLETON_IDENTITY_GROUP", "EXACT_DUPLICATE_GROUP", "ALIAS_DUPLICATE_GROUP", "SPONSOR_TRANSFER_GROUP", "RENAMED_PROGRAM_GROUP", "TRIAL_LEVEL_CONSOLIDATION_GROUP", "COMBINATION_RELATIONSHIP_GROUP", "POSSIBLE_DUPLICATE_UNRESOLVED", "OTHER_PROTOCOL_DEFINED_GROUP"}

def read(p: Path): return json.loads(p.read_text(encoding="utf-8"))
def sha(p: Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def fail(message: str): raise ValueError(message)

def consume(protocol_path: Path, protocol_schema_path: Path, candidate_schema_path: Path, manifest_path: Path, amendment_report_path: Path, amendment_manifest_path: Path, protocol_v1_path: Path, universe_v1_report_path: Path, universe_v1_validation_path: Path) -> dict:
    p, ps, cs, m, ar, am, old, uv1, val = map(read, (protocol_path, protocol_schema_path, candidate_schema_path, manifest_path, amendment_report_path, amendment_manifest_path, protocol_v1_path, universe_v1_report_path, universe_v1_validation_path))
    if p.get("protocol_version") != "1.1.0" or p.get("protocol_id") != "PHASE1_CD19_BCMA_NEW_COHORT_V2_SELECTION_PROTOCOL": fail("protocol identity/version mismatch")
    for k, v in {"benchmark_family":"PHASE1_CD19_BCMA", "benchmark_version":"2.0.0", "benchmark_lineage":"NEW_COHORT_V2", "cohort_version":"1.0.0", "namespace":NS}.items():
        if p.get(k) != v: fail(f"benchmark invariant failed: {k}")
    if m.get("protocol_sha256") != sha(protocol_path) or m.get("protocol_schema_sha256") != sha(protocol_schema_path) or m.get("candidate_universe_v2_schema_sha256") != sha(candidate_schema_path): fail("manifest mismatch")
    if m.get("governing_bindings", {}).get("amendment_report", {}).get("sha256") != sha(amendment_report_path): fail("amendment binding mismatch")
    if am.get("authorization_report", {}).get("sha256") != sha(amendment_report_path) or ar.get("overall_conclusion") != "NEW_COHORT_V2_SELECTION_PROTOCOL_AMENDMENT_AUTHORIZED": fail("governance amendment mismatch")
    if old.get("protocol_version") != "1.0.0" or m.get("supersedes_protocol_version") != "1.0.0": fail("V1 fallback/version isolation failed")
    if p.get("supersession", {}).get("protocol_v1_0_status") != "SEALED_SUPERSEDED_FOR_FUTURE_UNIVERSE_WORK": fail("missing V1 supersession status")
    if p.get("supersession", {}).get("candidate_universe_v1_status") != "INDEPENDENTLY_FAILED_INVALID_DOWNSTREAM_INPUT": fail("V1 universe is not invalidated")
    if uv1.get("selected") is not False or val.get("overall_verdict") != "FAIL_MULTIPLE_BLOCKING_DEFECTS": fail("V1 universe boundary failed")
    if m.get("candidate_universe_v2_exists") is not False or p.get("boundary_controls", {}).get("candidate_universe_v2_exists") is not False: fail("V2 incorrectly represented as existing")
    if p.get("next_permitted_milestone") != "BUILD_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V2" or p.get("milestone_state", {}).get("separate_transition_required") is not True: fail("wrong next milestone")
    auth = p.get("authorization", {})
    if any(auth.get(k) is not False for k in ("candidate_universe_v2_construction_authorized", "candidate_universe_v2_validation_authorized", "cohort_selection_authorized", "selection_seed_execution_authorized", "reviewer_id_generation_authorized", "evidence_acquisition_authorized", "semantic_review_authorized", "release_authorized")): fail("premature activation")
    ep = p.get("eligibility_date_policy", {})
    if ep.get("first_eligible_date_concept") != "EARLIEST_VERIFIED_PUBLIC_ELIGIBILITY_DATE" or len(ep.get("controlling_date_hierarchy", [])) != 3: fail("eligibility-date hierarchy missing")
    if ep.get("partial_date_rule", {}).get("MONTH") != "Normalize to final calendar day of month." or ep.get("partial_date_rule", {}).get("YEAR") != "Normalize to December 31 of year.": fail("partial date rules failed")
    if ep.get("partial_date_rule", {}).get("cutoff_rule") is None or ep.get("conflict_rule", {}).get("evaluation_order") != ["source authorization", "public availability", "unique asset identification", "identity continuity", "source authority", "date precision", "reproducibility", "version-specific content"]: fail("conflict rule failed")
    if ep.get("required_candidate_fields") != DATE_FIELDS: fail("required date fields failed")
    matrix = p.get("source_class_requirement_matrix", [])
    if len(matrix) != 7 or {x.get("status") for x in matrix} != STATUSES: fail("source matrix/status failed")
    clinical = next(x for x in matrix if x.get("source_class") == "clinical_trial_registries")
    if clinical.get("status") != "MANDATORY_ENUMERATION_SOURCE" or p.get("enumeration_completeness", {}).get("clinicaltrials_gov_alone_sufficient") is not False: fail("ClinicalTrials.gov sufficiency failed")
    if set(p.get("conditional_source_trigger_ledger", {}).get("required_trigger_types", [])) != TRIGGERS: fail("conditional trigger ledger failed")
    if p.get("enumeration_completeness", {}).get("enumeration_completeness_model") != "MODEL_C_CONDITIONAL_SOURCE_EXPANSION": fail("Model C failed")
    required_roles = {"source_class", "source_role", "authorization_status", "trigger_id", "identity_authority", "date_authority", "eligibility_authority", "enumeration_authority", "candidate_discovery_authorized", "first_eligible_date_authorized", "provenance_references"}
    if not required_roles.issubset(set(p.get("source_role_enforcement", {}).get("required_source_reference_fields", []))): fail("source-role requirements missing")
    if not p.get("registry_accounting", {}).get("exactly_one_accounting_record_per_registry_record") or p.get("registry_accounting", {}).get("unexplained_difference_must_equal") != 0: fail("registry accounting failed")
    ig = p.get("identity_groups", {})
    if "SINGLETON_IDENTITY_GROUP" not in ig.get("controlled_types", []) or ig.get("singleton_is_duplicate_prohibited") is not True: fail("identity-group terminology failed")
    req = p.get("candidate_universe_v2_schema_requirements", {})
    if req.get("required_date_fields") != DATE_FIELDS or req.get("fixed_fields") != {"historical_semantic_inputs_used": False, "reviewer_id_generated": False, "selected": False}: fail("candidate schema requirements failed")
    if p.get("source_role_enforcement", {}).get("selection_metadata_label") != "SELECTION_METADATA_NOT_BENCHMARK_TRUTH": fail("selection metadata label missing")
    if p.get("boundary_controls", {}).get("candidate_identities_embedded") is not False or p.get("boundary_controls", {}).get("semantic_review_occurred") is not False: fail("semantic/candidate boundary failed")
    return {"conclusion": CONCLUSION, "protocol_version": p["protocol_version"], "eligibility_date_concept": ep["first_eligible_date_concept"], "source_classes": len(matrix), "conditional_trigger_types": sorted(TRIGGERS), "enumeration_completeness_model": "MODEL_C_CONDITIONAL_SOURCE_EXPANSION", "clinicaltrials_gov_alone_sufficient": False, "candidate_universe_v1_status": p["supersession"]["candidate_universe_v1_status"], "candidate_universe_v2_exists": False, "next_milestone": p["next_permitted_milestone"]}

def main(argv=None):
    ap=argparse.ArgumentParser();
    for arg in ("protocol", "protocol-schema", "candidate-schema", "manifest", "amendment-report", "amendment-manifest", "protocol-v1", "universe-v1-report", "universe-v1-validation"): ap.add_argument("--"+arg, required=True, type=Path)
    a=ap.parse_args(argv)
    try: print(json.dumps(consume(a.protocol,a.protocol_schema,a.candidate_schema,a.manifest,a.amendment_report,a.amendment_manifest,a.protocol_v1,a.universe_v1_report,a.universe_v1_validation), indent=2, sort_keys=True)); return 0
    except Exception as exc: print(f"CONSUMER_ERROR: {exc}", file=sys.stderr); return 1
if __name__ == "__main__": raise SystemExit(main())
