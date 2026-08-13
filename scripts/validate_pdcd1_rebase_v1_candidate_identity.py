"""Independent Milestone 5 candidate-identity validator.

Fails closed. Imports no build/adjudication module and rechecks the finalized
M5 snapshot against frozen M4 ledgers and M5's declared artifact contracts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

OUTCOMES = {
    "VERIFIED_CANONICAL_CANDIDATE",
    "VERIFIED_ALIAS_OF_CANDIDATE",
    "DISTINCT_PRODUCT",
    "GENERIC_OR_NONIDENTIFYING",
    "EXPLICIT_NONCANDIDATE",
    "CONFLICT_UNRESOLVED",
    "INSUFFICIENT_EVIDENCE",
}
QUALIFYING_ALIAS_ASSERTIONS = {
    "CODE_TO_NAME_EXPLICIT_LINK",
    "OFFICIAL_ALIAS_EXPLICIT_LINK",
    "TRIAL_TO_PRODUCT_EXPLICIT_LINK",
    "REGULATORY_IDENTIFIER_EXPLICIT_LINK",
}
CANONICAL_SUPPORT_ASSERTIONS = {
    "EXACT_PRODUCT_NAME_EXISTS",
    "CODE_TO_NAME_EXPLICIT_LINK",
    "OFFICIAL_ALIAS_EXPLICIT_LINK",
    "TRIAL_TO_PRODUCT_EXPLICIT_LINK",
    "REGULATORY_IDENTIFIER_EXPLICIT_LINK",
}
DISTINCT_TYPES = {
    "ADC_DISTINCT_FROM_BACKBONE",
    "BIOSIMILAR_DISTINCT_PRODUCT",
    "COMBINATION_CONTAINS_DISTINCT_PRODUCTS",
}
FORBIDDEN_KEYS = {
    "benchmark_label",
    "candidate_chronology",
    "chronology",
    "evaluation_score",
    "owner_organization",
    "ownership",
    "prediction",
    "predicted_label",
}


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def validate(snapshot_dir: Path, m4_snapshot_dir: Path) -> dict:
    checks: dict[str, dict] = {}

    def record(name: str, passed: bool, detail=None) -> None:
        checks[name] = {"pass": bool(passed), "detail": detail}

    try:
        manifest = json.loads((snapshot_dir / "manifest.json").read_text())
    except Exception as exc:
        record("manifest_readable", False, str(exc))
        return {"overall_pass": False, "failed_checks": list(checks), "checks": checks}
    record("manifest_readable", True)

    mapping = load_jsonl(snapshot_dir / "subjects" / "subject_candidate_mapping_ledger.jsonl")
    candidates = load_jsonl(snapshot_dir / "candidates" / "canonical_candidate_ledger.jsonl")
    aliases = load_jsonl(snapshot_dir / "aliases" / "alias_development_code_ledger.jsonl")
    boundaries = load_jsonl(snapshot_dir / "boundaries" / "identity_boundary_ledger.jsonl")
    conflict_resolution = load_jsonl(snapshot_dir / "conflicts" / "conflict_resolution_ledger.jsonl")
    rejected_aliases = load_jsonl(snapshot_dir / "aliases" / "rejected_alias_ledger.jsonl")
    reconciliation = load_jsonl(snapshot_dir / "reproducibility" / "reconciliation_ledger.jsonl")

    m4_subjects = load_jsonl(m4_snapshot_dir / "subjects" / "authority_research_subject_ledger.jsonl")
    m4_assertions = load_jsonl(m4_snapshot_dir / "assertions" / "normalized_assertion_ledger.jsonl")
    m4_conflicts = load_jsonl(m4_snapshot_dir / "conflicts" / "authority_conflict_ledger.jsonl")
    m4_subject_ids = {s["subject_id"] for s in m4_subjects}
    mapping_subject_ids = [m["subject_id"] for m in mapping]

    record("all_554_m4_subjects_mapped_once", Counter(mapping_subject_ids) == Counter(m4_subject_ids), len(mapping_subject_ids))
    bad_outcomes = [m for m in mapping if m.get("identity_outcome") not in OUTCOMES]
    record("only_closed_set_identity_outcomes_used", not bad_outcomes, bad_outcomes[:5])
    out_of_scope = [m for m in mapping if m.get("identity_outcome") and "benchmark_label" in m]
    record("no_row_level_benchmark_labels_created", not out_of_scope, len(out_of_scope))

    expected_flags = {
        "canonical_candidates_created": True,
        "aliases_adjudicated": True,
        "benchmark_labels_created": False,
        "candidate_chronology_created": False,
        "predictions_generated": False,
        "evaluation_performed": False,
        "ownership_claims_created": False,
    }
    flag_mismatches = {k: manifest.get(k) for k, v in expected_flags.items() if manifest.get(k) != v}
    record("manifest_scope_flags_correct", not flag_mismatches, flag_mismatches)

    m4_evidence_hashes = {a.get("evidence_hash") for a in m4_assertions if a.get("evidence_hash")}
    m5_refs = []
    for rows in (mapping, candidates, aliases, boundaries, conflict_resolution):
        for row in rows:
            m5_refs.extend(row.get("supporting_assertions", []))
    bad_refs = [
        r for r in m5_refs
        if not r.get("evidence_hash") or r.get("evidence_hash") not in m4_evidence_hashes
    ]
    record("all_m5_evidence_bindings_resolve_to_frozen_m4_assertions", not bad_refs, len(bad_refs))

    candidate_ids = [c["candidate_id"] for c in candidates]
    record("canonical_candidate_ids_unique", len(candidate_ids) == len(set(candidate_ids)), len(candidate_ids))
    candidate_without_support = [
        c for c in candidates
        if not c.get("supporting_assertions")
        or not any(a.get("assertion_type") in CANONICAL_SUPPORT_ASSERTIONS | DISTINCT_TYPES for a in c["supporting_assertions"])
    ]
    record("canonical_candidates_have_supporting_identity_assertions", not candidate_without_support, len(candidate_without_support))

    alias_bad = []
    for alias in aliases:
        if alias.get("candidate_id") not in set(candidate_ids):
            alias_bad.append(alias)
            continue
        refs = alias.get("supporting_assertions", [])
        if not refs or not any(r.get("assertion_type") in QUALIFYING_ALIAS_ASSERTIONS for r in refs):
            alias_bad.append(alias)
    record("aliases_have_citable_qualifying_assertions", not alias_bad, len(alias_bad))

    mapping_candidate_bad = [
        m for m in mapping
        if m.get("identity_outcome") in {"VERIFIED_CANONICAL_CANDIDATE", "VERIFIED_ALIAS_OF_CANDIDATE", "DISTINCT_PRODUCT"}
        and not m.get("candidate_id")
    ]
    record("candidate_outcomes_have_candidate_id", not mapping_candidate_bad, len(mapping_candidate_bad))

    fuzzy_or_context_merges = [
        m for m in mapping
        if m.get("identity_outcome") == "VERIFIED_ALIAS_OF_CANDIDATE"
        and not any(r.get("assertion_type") in QUALIFYING_ALIAS_ASSERTIONS for r in m.get("supporting_assertions", []))
    ]
    record("no_fuzzy_same_sponsor_or_same_target_merges", not fuzzy_or_context_merges, len(fuzzy_or_context_merges))

    boundary_bad = [
        b for b in boundaries
        if b.get("boundary_type") in DISTINCT_TYPES
        and any(k in json.dumps(b.get("kept_distinct_from", {})).lower() for k in ("same_as", "merged_with", "equivalent_to"))
    ]
    record("no_adc_or_biosimilar_or_combination_collapse", not boundary_bad, len(boundary_bad))

    m4_conflict_ids = {c["subject_id"] for c in m4_conflicts}
    conflict_ids = [c["subject_id"] for c in conflict_resolution]
    record("all_76_m4_conflicts_covered_once", Counter(conflict_ids) == Counter(m4_conflict_ids), len(conflict_ids))
    bad_conflict_markers = [
        c for c in conflict_resolution
        if c.get("resolution_marker") not in {"RESOLVED", "CONFLICT_UNRESOLVED"}
        or not c.get("reasoning")
    ]
    record("conflicts_have_real_resolution_or_unresolved_marker", not bad_conflict_markers, len(bad_conflict_markers))

    record("rejected_alias_ledger_populated", bool(rejected_aliases), len(rejected_aliases))
    bad_rejected = [r for r in rejected_aliases if r.get("qualifying_assertions_found")]
    record("rejected_aliases_do_not_contain_qualifying_merge_evidence", not bad_rejected, len(bad_rejected))
    record("reconciliation_ledger_present", reconciliation is not None, len(reconciliation))

    forbidden_hits = []

    def walk(obj, relpath):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in FORBIDDEN_KEYS:
                    forbidden_hits.append((relpath, key))
                walk(value, relpath)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, relpath)

    for path in sorted(snapshot_dir.rglob("*.json")):
        if path.name == "STORAGE_STATUS.json":
            continue
        try:
            walk(json.loads(path.read_text()), str(path.relative_to(snapshot_dir)))
        except Exception:
            pass
    for path in sorted(snapshot_dir.rglob("*.jsonl")):
        for row in load_jsonl(path):
            walk(row, str(path.relative_to(snapshot_dir)))
    record("no_out_of_scope_fields_present_anywhere_in_snapshot", not forbidden_hits, forbidden_hits[:10])

    try:
        receipt = json.loads((snapshot_dir / "receipt.json").read_text())
        mismatches = []
        for relpath, meta in receipt.get("artifacts", {}).items():
            path = snapshot_dir / relpath
            data = path.read_bytes()
            if len(data) != meta.get("byte_length") or hashlib.sha256(data).hexdigest() != meta.get("sha256"):
                mismatches.append(relpath)
        record("receipt_bound_artifact_hashes_match", not mismatches, mismatches[:10])
    except Exception as exc:
        record("receipt_bound_artifact_hashes_match", False, str(exc))

    failed = [name for name, result in checks.items() if not result["pass"]]
    return {"overall_pass": not failed, "failed_checks": failed, "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("m4_snapshot_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.snapshot_dir, args.m4_snapshot_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
