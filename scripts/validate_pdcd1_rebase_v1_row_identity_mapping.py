"""Independent Milestone 6 frozen-row identity mapping validator. Fails closed."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROW_OUTCOMES = {
    "CANDIDATE_LINKED",
    "EXPLICIT_NONCANDIDATE",
    "GENERIC_OR_NONIDENTIFYING",
    "CONFLICTING_MULTI_PRODUCT",
    "IDENTITY_CONFLICT_UNRESOLVED",
    "INSUFFICIENT_EVIDENCE",
}
CANDIDATE_M5_OUTCOMES = {
    "VERIFIED_CANONICAL_CANDIDATE",
    "VERIFIED_ALIAS_OF_CANDIDATE",
    "DISTINCT_PRODUCT",
}
IDENTITY_BEARING_ASSERTION_TYPES = {
    "EXACT_PRODUCT_NAME_EXISTS",
    "PRODUCT_CODE_EXISTS",
    "CODE_TO_NAME_EXPLICIT_LINK",
    "OFFICIAL_ALIAS_EXPLICIT_LINK",
    "TRIAL_TO_PRODUCT_EXPLICIT_LINK",
    "REGULATORY_IDENTIFIER_EXPLICIT_LINK",
    "ADC_DISTINCT_FROM_BACKBONE",
    "BIOSIMILAR_DISTINCT_PRODUCT",
    "COMBINATION_CONTAINS_DISTINCT_PRODUCTS",
}
CONTEXT_ONLY_ASSERTION_TYPES = {
    "GENERIC_DESCRIPTION_NOT_PRODUCT_NAME",
    "MODALITY_EXPLICIT",
    "NO_EXACT_REGULATORY_MATCH",
    "TARGET_ONLY",
    "SPONSOR_ONLY",
    "ORGANIZATION_ONLY",
    "FUZZY_NAME_SIMILARITY",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(checks: dict, name: str, passed: bool, detail: object = None) -> None:
    checks[name] = {"detail": detail, "pass": bool(passed)}


def _row_candidate_ids(mapping_row: dict) -> list[str]:
    ids = list(mapping_row.get("canonical_candidate_ids") or [])
    if mapping_row.get("canonical_candidate_id"):
        ids.append(mapping_row["canonical_candidate_id"])
    return sorted(set(ids))


def _candidate_binding_entries(mapping_row: dict) -> list[dict]:
    return [
        entry
        for entry in mapping_row.get("binding_path", [])
        if entry.get("canonical_candidate_id") and entry.get("m5_identity_outcome") in CANDIDATE_M5_OUTCOMES
    ]


def validate(snapshot_dir: Path, m3_dir: Path, m5_dir: Path) -> dict:
    checks = {}
    try:
        manifest = load_json(snapshot_dir / "manifest.json")
        receipt = load_json(snapshot_dir / "receipt.json")
        frozen_rows = load_jsonl(m3_dir / "extracted" / "frozen_row_evidence_bindings.jsonl")
        candidates = load_jsonl(m5_dir / "candidates" / "canonical_candidate_ledger.jsonl")
        aliases = load_jsonl(m5_dir / "aliases" / "alias_development_code_ledger.jsonl")
        rejected_aliases = load_jsonl(m5_dir / "aliases" / "rejected_alias_ledger.jsonl")
        m5_mapping = load_jsonl(m5_dir / "subjects" / "subject_candidate_mapping_ledger.jsonl")
        row_outcomes = load_jsonl(snapshot_dir / "rows" / "row_outcome_ledger.jsonl")
        row_mappings = load_jsonl(snapshot_dir / "rows" / "row_candidate_mapping_ledger.jsonl")
        components = load_jsonl(snapshot_dir / "rows" / "combination_component_ledger.jsonl")
        unresolved = load_jsonl(snapshot_dir / "rows" / "unresolved_row_ledger.jsonl")
        evidence = load_jsonl(snapshot_dir / "rows" / "row_evidence_binding_ledger.jsonl")
        boundaries = load_jsonl(snapshot_dir / "boundaries" / "row_identity_boundary_ledger.jsonl")
    except Exception as exc:
        return {"checks": {"load_required_artifacts": {"detail": repr(exc), "pass": False}}, "failed_checks": ["load_required_artifacts"], "overall_pass": False}

    frozen_ids = [row["frozen_row_id"] for row in frozen_rows]
    outcome_ids = [row.get("frozen_row_id") for row in row_outcomes]
    _record(checks, "all_300_frozen_rows_present_exactly_once", len(outcome_ids) == 300 and Counter(outcome_ids) == Counter(frozen_ids), {"missing": sorted(set(frozen_ids) - set(outcome_ids))[:20], "extra": sorted(set(outcome_ids) - set(frozen_ids))[:20], "duplicates": [row_id for row_id, n in Counter(outcome_ids).items() if n > 1][:20]})
    _record(checks, "row_outcomes_are_schema_defined", all(row.get("outcome") in ROW_OUTCOMES for row in row_outcomes), sorted({row.get("outcome") for row in row_outcomes} - ROW_OUTCOMES))

    candidate_ids = {row["candidate_id"] for row in candidates}
    bad_linked = [row for row in row_outcomes if row.get("outcome") == "CANDIDATE_LINKED" and row.get("canonical_candidate_id") not in candidate_ids]
    bad_nonlinked = [row for row in row_outcomes if row.get("outcome") != "CANDIDATE_LINKED" and row.get("canonical_candidate_id") is not None]
    _record(checks, "linked_rows_have_valid_single_candidate_id", not bad_linked and not bad_nonlinked, {"bad_linked": bad_linked[:5], "bad_nonlinked": bad_nonlinked[:5]})

    row_outcome_by_id = {row["frozen_row_id"]: row for row in row_outcomes}
    mapping_by_row = {row["frozen_row_id"]: row for row in row_mappings}
    mapping_bad = []
    for row in row_outcomes:
        has_mapping = row["frozen_row_id"] in mapping_by_row
        should_have = row["outcome"] in {"CANDIDATE_LINKED", "CONFLICTING_MULTI_PRODUCT"}
        if has_mapping != should_have:
            mapping_bad.append(row)
    _record(checks, "candidate_and_multiproduct_rows_have_only_expected_mapping_rows", not mapping_bad, mapping_bad[:10])

    invalid_mapping_candidates = [
        row for row in row_mappings for cid in _row_candidate_ids(row) if cid not in candidate_ids
    ]
    _record(checks, "every_mapped_candidate_id_exists_in_m5_canonical_candidates", not invalid_mapping_candidates, invalid_mapping_candidates[:5])

    alias_tuples = {(row["alias_subject_id"], row["candidate_id"], row["alias_string"]) for row in aliases}
    rejected_subject_pairs = {
        tuple(sorted((row["subject_id_left"], row["subject_id_right"]))) for row in rejected_aliases
    }
    bad_alias = []
    for row in row_mappings:
        for entry in row.get("binding_path", []):
            if entry.get("m5_identity_outcome") != "VERIFIED_ALIAS_OF_CANDIDATE":
                continue
            binding = entry.get("alias_ledger_binding")
            if not binding:
                bad_alias.append(row)
                continue
            if (binding.get("alias_subject_id"), binding.get("candidate_id"), binding.get("alias_string")) not in alias_tuples:
                bad_alias.append(row)
            if tuple(sorted((entry.get("m4_subject_id"), binding.get("alias_subject_id")))) in rejected_subject_pairs:
                bad_alias.append(row)
    _record(checks, "every_alias_bypass_mapping_exists_in_m5_alias_ledger_and_not_rejected", not bad_alias, bad_alias[:5])

    unsupported_candidate_rows = []
    context_only_rows = []
    for row in row_mappings:
        if row_outcome_by_id.get(row["frozen_row_id"], {}).get("outcome") not in {"CANDIDATE_LINKED", "CONFLICTING_MULTI_PRODUCT"}:
            continue
        candidate_entries = _candidate_binding_entries(row)
        if not candidate_entries:
            unsupported_candidate_rows.append(row)
            continue
        for entry in candidate_entries:
            types = set(entry.get("assertion_types", []))
            if not (types & IDENTITY_BEARING_ASSERTION_TYPES):
                unsupported_candidate_rows.append(row)
            if types and types <= CONTEXT_ONLY_ASSERTION_TYPES:
                context_only_rows.append(row)
    _record(checks, "candidate_rows_include_real_identity_bearing_m4_assertion_types", not unsupported_candidate_rows, unsupported_candidate_rows[:5])
    _record(checks, "no_candidate_row_derives_only_from_context_assertion_types", not context_only_rows, context_only_rows[:5])

    m5_outcome_by_subject = {row["subject_id"]: row["identity_outcome"] for row in m5_mapping}
    boundary_escape_rows = {row["frozen_row_id"] for row in boundaries if row.get("escape_hatch_applied")}
    evidence_by_row = {row["frozen_row_id"]: row for row in evidence}
    forced_closed = []
    insufficient_forced = []
    for row_id, binding in evidence_by_row.items():
        subject_outcomes = {m5_outcome_by_subject.get(sid) for sid in binding.get("subject_ids", [])}
        outcome = row_outcome_by_id.get(row_id, {}).get("outcome")
        if "CONFLICT_UNRESOLVED" in subject_outcomes and outcome != "IDENTITY_CONFLICT_UNRESOLVED" and row_id not in boundary_escape_rows:
            forced_closed.append(row_id)
        if "INSUFFICIENT_EVIDENCE" in subject_outcomes and outcome != "INSUFFICIENT_EVIDENCE" and row_id not in boundary_escape_rows:
            insufficient_forced.append(row_id)
    _record(checks, "conflict_unresolved_subject_rows_remain_unresolved_without_escape_hatch", not forced_closed, forced_closed[:20])
    _record(checks, "insufficient_evidence_subject_rows_remain_insufficient_without_escape_hatch", not insufficient_forced, insufficient_forced[:20])

    unresolved_ids = {row["frozen_row_id"] for row in unresolved}
    expected_unresolved_ids = {
        row["frozen_row_id"]
        for row in row_outcomes
        if row["outcome"] in {"CONFLICTING_MULTI_PRODUCT", "IDENTITY_CONFLICT_UNRESOLVED", "INSUFFICIENT_EVIDENCE"}
    }
    _record(checks, "unresolved_row_ledger_covers_all_unresolved_outcomes_once", unresolved_ids == expected_unresolved_ids and len(unresolved_ids) == len(unresolved), {"missing": sorted(expected_unresolved_ids - unresolved_ids)[:20], "extra": sorted(unresolved_ids - expected_unresolved_ids)[:20]})

    component_bad_ids = []
    component_rows_by_id = {row["frozen_row_id"]: row for row in components}
    for row_id, component_row in component_rows_by_id.items():
        component_candidate_ids = sorted({
            c.get("canonical_candidate_id")
            for c in component_row.get("components", [])
            if c.get("resolution") == "CANDIDATE" and c.get("canonical_candidate_id")
        })
        if any(cid not in candidate_ids for cid in component_candidate_ids):
            component_bad_ids.append(row_id)
        if len(set(component_candidate_ids)) > 1 and row_outcome_by_id.get(row_id, {}).get("outcome") in {"CANDIDATE_LINKED", "CONFLICTING_MULTI_PRODUCT"}:
            outcome = row_outcome_by_id.get(row_id, {}).get("outcome")
            mapping_ids = _row_candidate_ids(mapping_by_row.get(row_id, {}))
            if outcome != "CONFLICTING_MULTI_PRODUCT" or not set(component_candidate_ids) <= set(mapping_ids):
                component_bad_ids.append(row_id)
    _record(checks, "combination_rows_preserve_all_distinct_candidate_components", not component_bad_ids, component_bad_ids[:20])

    multiproduct_bad = []
    for row in row_outcomes:
        mapping_ids = _row_candidate_ids(mapping_by_row.get(row["frozen_row_id"], {}))
        if row["outcome"] == "CONFLICTING_MULTI_PRODUCT" and len(mapping_ids) < 2:
            multiproduct_bad.append(row)
        if row["outcome"] == "CANDIDATE_LINKED" and len(mapping_ids) > 1:
            multiproduct_bad.append(row)
    _record(checks, "multi_candidate_rows_are_not_collapsed_to_single_candidate", not multiproduct_bad, multiproduct_bad[:10])

    receipt_bad = []
    for rel, expected in receipt.get("artifacts", {}).items():
        path = snapshot_dir / rel
        if not path.is_file() or file_sha(path) != expected.get("sha256") or path.stat().st_size != expected.get("byte_length"):
            receipt_bad.append(rel)
    _record(checks, "receipt_bound_artifact_hashes_match", not receipt_bad, receipt_bad[:20])

    expected_flags = {
        "benchmark_labels_created": False,
        "candidate_chronology_created": False,
        "evaluation_performed": False,
        "external_authority_capture_performed": False,
        "predictions_generated": False,
        "row_identity_mapping_performed": True,
        "stage_status": "FINALIZED",
    }
    flag_bad = {key: manifest.get(key) for key, value in expected_flags.items() if manifest.get(key) != value}
    _record(checks, "manifest_scope_flags_are_correct", not flag_bad, flag_bad)

    failed = [name for name, result in checks.items() if not result["pass"]]
    return {"checks": checks, "failed_checks": failed, "overall_pass": not failed}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("m3_snapshot_dir", type=Path)
    parser.add_argument("m5_snapshot_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.snapshot_dir, args.m3_snapshot_dir, args.m5_snapshot_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
