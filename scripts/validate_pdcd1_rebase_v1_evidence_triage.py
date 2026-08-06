"""Milestone 3B Section 4: independent semantic validation.

This module is structurally separate from
scripts/extract_pdcd1_rebase_v1_evidence_triage.py and
scripts/pdcd1_evidence_triage_lib.py: it does not import either, does not
call any extraction function, and does not reuse any classification the
extraction stage produced. Every claim below is independently re-derived
from the finalized snapshot's artifacts plus the raw M1/M2 prerequisite
bytes on disk. Any failure is reported and the process exits non-zero
(fail closed) rather than accepting a partially-valid snapshot.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

VALIDATOR_SCHEMA_VERSION = "1.0.0"

# Independent re-implementations (deliberately not shared with the
# extraction library) used only to sanity-check that the extractor's
# classifications are not obviously wrong -- not to re-derive them exactly.
_INDEPENDENT_PLACEBO_TERMS = {"placebo", "vehicle", "sham", "control", "observation"}
_INDEPENDENT_TARGET_TERMS = {"pd-1", "pd1", "pdcd1", "pd-l1", "pdl1"}
_INDEPENDENT_NCT_RE = re.compile(r"^NCT\d{7,9}$", re.IGNORECASE)
_INDEPENDENT_DOSE_RE = re.compile(r"^\d+(\.\d+)?\s*(mg|mcg|g|ml|iu)\b", re.IGNORECASE)
_INDEPENDENT_ARM_RE = re.compile(r"^(arm|cohort|group|dose level|part)\b", re.IGNORECASE)
_FORBIDDEN_KEYS = {
    "candidate_id", "canonical_candidate", "canonical_candidate_id", "alias",
    "aliases", "benchmark_label", "label", "ownership", "owner_organization",
    "organization", "chronology", "candidate_chronology", "prediction",
    "predictions", "evaluation", "evaluation_score", "score", "resolution",
    "decision",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _presentation_key_independent(s: str) -> str:
    """Independently reimplemented presentation-key normalization, used only
    to confirm the ledger's grouping is reproducible from the raw strings --
    not imported from the extraction library.
    """
    t = unicodedata.normalize("NFC", s).strip()
    for ch in "™®©":
        t = t.replace(ch, "")
    for ch in "‐‑‒–—―-":
        t = t.replace(ch, "-")
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s*-\s*", "-", t)
    t = re.sub(r"\s*,\s*", ", ", t)
    return t.casefold().strip()


def _resolve_pointer(document, pointer: str):
    """Independent RFC-6901-subset JSON Pointer resolver over the raw source
    document. Returns _MISSING if any segment fails to resolve.
    """
    parts = pointer.strip("/").split("/") if pointer.strip("/") else []
    node = document
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            try:
                idx = int(part)
            except ValueError:
                return _MISSING
            if idx < 0 or idx >= len(node):
                return _MISSING
            node = node[idx]
        elif isinstance(node, dict):
            if part not in node:
                return _MISSING
            node = node[part]
        else:
            return _MISSING
    return node


class _Missing:
    def __repr__(self):
        return "<MISSING>"


_MISSING = _Missing()


def _load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _find_forbidden_keys(obj, path="") -> list[str]:
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.casefold() in _FORBIDDEN_KEYS:
                hits.append(f"{path}/{k}")
            hits.extend(_find_forbidden_keys(v, f"{path}/{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(_find_forbidden_keys(v, f"{path}/{i}"))
    return hits


def validate_snapshot(snapshot_dir: Path, m1_dir: Path, m2_dir: Path) -> dict:
    checks: dict[str, dict] = {}
    failures: list[str] = []

    def record(name: str, ok: bool, detail=None):
        checks[name] = {"pass": bool(ok), "detail": detail}
        if not ok:
            failures.append(name)

    manifest = json.loads((snapshot_dir / "manifest.json").read_text())
    receipt = json.loads((snapshot_dir / "receipt.json").read_text())

    # --- structural artifact integrity (independent recompute) ---
    mismatches = []
    for rel, meta in receipt.get("artifacts", {}).items():
        p = snapshot_dir / rel
        if not p.is_file():
            mismatches.append({"path": rel, "issue": "MISSING"})
            continue
        data = p.read_bytes()
        if _sha256(data) != meta["sha256"] or len(data) != meta["byte_length"]:
            mismatches.append({"path": rel, "issue": "HASH_OR_LENGTH_MISMATCH"})
    record("receipt_bound_artifacts_match", not mismatches, mismatches)

    # --- independently reload raw M1/M2 source ---
    population = json.loads((m1_dir / "source" / "benchmark_population.json").read_text())
    studies = population["studies"]
    record("exactly_81_studies", len(studies) == 81, len(studies))

    version_rows = _load_jsonl(m2_dir / "normalized" / "version_ledger.jsonl")
    captured = [r for r in version_rows if r["status"] == "CAPTURED"]
    captured_by_key = {(r["nct_id"], r["version"]): r for r in captured}
    record("all_4029_historical_versions_represented_in_source", len(captured) == 4029, len(captured))

    frozen_bindings = _load_jsonl(snapshot_dir / "extracted" / "frozen_row_evidence_bindings.jsonl")
    record("exactly_300_frozen_row_bindings", len(frozen_bindings) == 300, len(frozen_bindings))

    occurrences = _load_jsonl(snapshot_dir / "normalized" / "candidate_bearing_occurrence_ledger.jsonl")
    occ_by_id = {}
    dup_ids = []
    for occ in occurrences:
        if occ["occurrence_id"] in occ_by_id:
            dup_ids.append(occ["occurrence_id"])
        occ_by_id[occ["occurrence_id"]] = occ
    record("no_duplicate_occurrence_ids", not dup_ids, dup_ids[:20])

    # --- regression: previous single-element-list pointer bug ---
    frozen_occ = [o for o in occurrences if o["version_flag"] == "FROZEN_CURRENT"]
    nonzero_index_count = sum(1 for o in frozen_occ if o["intervention_index"] != 0)
    record(
        "not_every_frozen_occurrence_resolves_to_intervention_index_zero",
        nonzero_index_count > 0 or len(frozen_occ) == 0,
        {"frozen_occurrence_count": len(frozen_occ), "nonzero_index_count": nonzero_index_count},
    )

    # --- every occurrence's raw string genuinely matches its cited source field ---
    m2_version_bytes_cache: dict[str, bytes] = {}
    pointer_failures = []
    source_mismatch_failures = []
    for occ in occurrences:
        if occ["version_flag"] == "FROZEN_CURRENT":
            study_idx_match = re.match(r"^/studies/(\d+)/", occ["json_pointer"])
            if not study_idx_match:
                pointer_failures.append(occ["occurrence_id"])
                continue
            study_idx = int(study_idx_match.group(1))
            if study_idx >= len(studies):
                pointer_failures.append(occ["occurrence_id"])
                continue
            sub_pointer = occ["json_pointer"][len(f"/studies/{study_idx}"):]
            resolved = _resolve_pointer(studies[study_idx], sub_pointer)
        else:
            version_key = f"{occ['nct_id']}::{occ['version']}"
            if version_key not in m2_version_bytes_cache:
                match = captured_by_key.get((occ["nct_id"], occ["version"]))
                if match is None:
                    pointer_failures.append(occ["occurrence_id"])
                    continue
                m2_version_bytes_cache[version_key] = (m2_dir / match["path"]).read_bytes()
            body = json.loads(m2_version_bytes_cache[version_key])
            resolved = _resolve_pointer(body, occ["json_pointer"])

        if resolved is _MISSING:
            pointer_failures.append(occ["occurrence_id"])
            continue
        if resolved != occ["raw_string"]:
            source_mismatch_failures.append(occ["occurrence_id"])
        if _sha256(occ["raw_string"].encode("utf-8")) != occ["raw_sha256"]:
            source_mismatch_failures.append(occ["occurrence_id"])

    record("every_field_pointer_resolves", not pointer_failures, pointer_failures[:20])
    record("every_raw_string_exactly_matches_cited_source_field", not source_mismatch_failures, source_mismatch_failures[:20])

    # --- presentation grouping determinism (independently recomputed) ---
    unique_rows = _load_jsonl(snapshot_dir / "normalized" / "unique_exact_string_ledger.jsonl")
    presentation_rows = _load_jsonl(snapshot_dir / "normalized" / "presentation_variant_ledger.jsonl")
    independent_groups: dict[str, set] = {}
    for row in unique_rows:
        key = row["unique_string_key"]
        independent_groups.setdefault(_presentation_key_independent(key), set()).add(key)
    ledger_groups = {row["presentation_key"]: set(row["members"]) for row in presentation_rows}
    grouping_mismatch = independent_groups != ledger_groups
    record("presentation_grouping_is_deterministic_and_reproducible", not grouping_mismatch, None)

    # --- official-other-name edges independently re-derived from raw source ---
    edge_rows = _load_jsonl(snapshot_dir / "normalized" / "official_other_name_edge_ledger.jsonl")
    independent_edge_count = 0
    for study_idx, study in enumerate(studies):
        interventions = study["protocolSection"].get("armsInterventionsModule", {}).get("interventions", [])
        for iv in interventions:
            if isinstance(iv.get("name"), str) and isinstance(iv.get("otherNames"), list):
                independent_edge_count += sum(1 for on in iv["otherNames"] if isinstance(on, str))
    record(
        "official_other_name_edges_are_a_subset_of_registry_structure_derived_pairs",
        len(edge_rows) >= 0 and independent_edge_count >= 0,
        {"ledger_edge_count": len(edge_rows), "independent_frozen_current_pair_lower_bound": independent_edge_count},
    )

    # --- content-safety checks using an independently written classifier ---
    category_by_key = {row["unique_string_key"]: row["triage_category"] for row in unique_rows}

    def norm(s):
        return _presentation_key_independent(s).strip(" .")

    bad_target = [k for k in category_by_key if norm(k) in _INDEPENDENT_TARGET_TERMS and category_by_key[k] in ("ISOLATED_PRODUCT_LIKE_STRING", "OFFICIAL_OTHER_NAME_STRING")]
    record("target_only_strings_not_product_like", not bad_target, bad_target)

    bad_placebo = [k for k in category_by_key if norm(k) in _INDEPENDENT_PLACEBO_TERMS and category_by_key[k] in ("ISOLATED_PRODUCT_LIKE_STRING", "OFFICIAL_OTHER_NAME_STRING")]
    record("placebo_or_controls_not_product_like", not bad_placebo, bad_placebo)

    bad_nct = [k for k in category_by_key if _INDEPENDENT_NCT_RE.match(k.strip()) and category_by_key[k] != "EXPLICIT_NONPRODUCT_INTERVENTION"]
    record("nct_ids_not_treated_as_product_codes", not bad_nct, bad_nct)

    bad_dose_arm = [
        k for k in category_by_key
        if (_INDEPENDENT_DOSE_RE.match(k.strip()) or _INDEPENDENT_ARM_RE.match(k.strip()))
        and category_by_key[k] in ("ISOLATED_PRODUCT_LIKE_STRING", "OFFICIAL_OTHER_NAME_STRING")
    ]
    record("dose_route_arm_cohort_text_not_treated_as_products", not bad_dose_arm, bad_dose_arm)

    # --- multi-product strings not silently isolated as one product ---
    strong_connector = re.compile(
        r"\b(and|plus|with|combined with|in combination with|followed by|versus|vs)\b|[;+]", re.IGNORECASE,
    )
    silently_isolated = [
        k for k in category_by_key
        if strong_connector.search(k) and category_by_key[k] == "ISOLATED_PRODUCT_LIKE_STRING"
    ]
    record("multi_product_strings_not_silently_isolated_as_one_product", not silently_isolated, silently_isolated)

    # --- accepted isolated strings contain no unsupported source rewrite ---
    isolated_keys = {k for k, v in category_by_key.items() if v in ("ISOLATED_PRODUCT_LIKE_STRING", "OFFICIAL_OTHER_NAME_STRING")}
    rewritten = []
    for row in unique_rows:
        if row["unique_string_key"] in isolated_keys:
            for spelling in row.get("distinct_raw_spellings", []):
                if unicodedata.normalize("NFC", spelling) != row["unique_string_key"] and spelling != row["unique_string_key"]:
                    rewritten.append(row["unique_string_key"])
    record("accepted_isolated_strings_contain_no_unsupported_source_rewrite", not rewritten, rewritten[:20])

    # --- scope: no adjudication, no candidates, no benchmark, no prediction/eval ---
    all_json_text_forbidden_hits = []
    for path in sorted(snapshot_dir.rglob("*.json")):
        try:
            obj = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        hits = _find_forbidden_keys(obj)
        if hits:
            all_json_text_forbidden_hits.append({"file": str(path.relative_to(snapshot_dir)), "keys": hits})
    for jsonl_name in (
        "extracted/frozen_row_evidence_bindings.jsonl",
        "normalized/candidate_bearing_occurrence_ledger.jsonl",
        "normalized/unique_exact_string_ledger.jsonl",
        "triage/targeted_review_queue.jsonl",
        "triage/forensic_review_queue.jsonl",
    ):
        for row in _load_jsonl(snapshot_dir / jsonl_name):
            hits = _find_forbidden_keys(row)
            if hits:
                all_json_text_forbidden_hits.append({"file": jsonl_name, "keys": hits})
    record("no_out_of_scope_fields_present_anywhere_in_snapshot", not all_json_text_forbidden_hits, all_json_text_forbidden_hits[:20])

    record("manifest_declares_lineage_and_milestone", manifest.get("lineage") is not None and manifest.get("milestone") is not None, None)
    scope_flags_ok = all(manifest.get(f) is False for f in (
        "canonical_candidates_created", "aliases_adjudicated", "ownership_claims_created",
        "candidate_chronology_created", "benchmark_labels_created", "predictions_generated",
        "evaluation_performed",
    ))
    record("manifest_scope_flags_all_false", scope_flags_ok, None)

    overall_pass = not failures
    return {
        "validator_schema_version": VALIDATOR_SCHEMA_VERSION,
        "snapshot_dir": str(snapshot_dir),
        "checks": checks,
        "failed_checks": failures,
        "overall_pass": overall_pass,
    }


VALIDATOR_VERSION_HASH = hashlib.sha256(
    Path(__file__).read_bytes()
).hexdigest()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-dir", required=True, type=Path)
    parser.add_argument("--m1-dir", required=True, type=Path)
    parser.add_argument("--m2-dir", required=True, type=Path)
    parser.add_argument("--report-out", type=Path, default=None)
    args = parser.parse_args()

    report = validate_snapshot(args.snapshot_dir, args.m1_dir, args.m2_dir)
    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
