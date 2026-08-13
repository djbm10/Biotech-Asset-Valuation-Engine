"""Pure Milestone 6 frozen-row identity mapping helpers.

Reads only finalized M1-M5 artifacts. No network I/O, chronology, ownership,
benchmark labeling, prediction, or evaluation logic.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

MILESTONE = "PDCD1_BENCHMARK_REBASE_V1_MILESTONE_6_FROZEN_ROW_IDENTITY_MAPPING"
SCHEMA_VERSION = "1.0.0"
LINEAGE = "REPRODUCIBLE_BIOTECH_PIPELINE_REBASE_V1"

M1_SNAPSHOT_ID = "47e9e791f48bb7aacc467e28"
M2_SNAPSHOT_ID = "62914ac00fa635d38755e25b"
M3_SNAPSHOT_ID = "f5dd19d08deb59a75232d3bc"
M4_SNAPSHOT_ID = "d933fec9aaeecd2df64884b6"
M5_SNAPSHOT_ID = "f26fd47e34ab97badde4e2ae"

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


def canonical_bytes(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def stable_hash(obj: object) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def assertion_types(mapping: dict) -> list[str]:
    return sorted({a.get("assertion_type") for a in mapping.get("supporting_assertions", []) if a.get("assertion_type")})


def build_indexes(inputs: dict[str, list[dict]]) -> dict[str, object]:
    occurrence_to_unique_key = {}
    unique_rows_by_key = {}
    for row in inputs["unique_strings"]:
        key = row["unique_string_key"]
        unique_rows_by_key[key] = row
        for occurrence_id in row.get("occurrence_ids", []):
            occurrence_to_unique_key[occurrence_id] = key

    subject_by_source_string = {}
    subject_by_id = {}
    for subject in inputs["subjects"]:
        subject_by_id[subject["subject_id"]] = subject
        for source_string in subject.get("source_strings", []):
            subject_by_source_string[source_string] = subject

    mapping_by_subject = {row["subject_id"]: row for row in inputs["subject_mapping"]}
    component_rows_by_key = defaultdict(list)
    for row in inputs["parsed_components"]:
        component_rows_by_key[row["unique_string_key"]].append(row)

    aliases_by_subject_candidate = {
        (row["alias_subject_id"], row["candidate_id"]): row
        for row in inputs["aliases"]
    }

    conflicts_by_subject = {
        row["subject_id"]: row
        for row in inputs["conflict_resolution"]
        if row.get("identity_outcome") == "CONFLICT_UNRESOLVED"
    }

    insufficient_subjects = {
        row["subject_id"]
        for row in inputs["subject_mapping"]
        if row.get("identity_outcome") == "INSUFFICIENT_EVIDENCE"
    }

    return {
        "aliases_by_subject_candidate": aliases_by_subject_candidate,
        "component_rows_by_key": component_rows_by_key,
        "conflicts_by_subject": conflicts_by_subject,
        "insufficient_subjects": insufficient_subjects,
        "mapping_by_subject": mapping_by_subject,
        "occurrence_to_unique_key": occurrence_to_unique_key,
        "subject_by_id": subject_by_id,
        "subject_by_source_string": subject_by_source_string,
        "unique_rows_by_key": unique_rows_by_key,
    }


def _binding_entry(
    *,
    occurrence_id: str | None,
    unique_key: str,
    subject: dict | None,
    mapping: dict | None,
    aliases_by_subject_candidate: dict[tuple[str, str], dict],
) -> dict:
    if subject is None or mapping is None:
        return {
            "alias_ledger_binding": None,
            "assertion_types": [],
            "canonical_candidate_id": None,
            "evidence_occurrence_id": occurrence_id,
            "m4_subject_id": None,
            "m5_identity_outcome": "INSUFFICIENT_EVIDENCE",
            "unique_string_key": unique_key,
        }

    candidate_id = mapping.get("candidate_id")
    alias_binding = None
    if mapping.get("identity_outcome") == "VERIFIED_ALIAS_OF_CANDIDATE" and candidate_id:
        alias = aliases_by_subject_candidate.get((subject["subject_id"], candidate_id))
        if alias:
            alias_binding = {
                "alias_string": alias["alias_string"],
                "alias_subject_id": alias["alias_subject_id"],
                "candidate_id": alias["candidate_id"],
            }

    return {
        "alias_ledger_binding": alias_binding,
        "assertion_types": assertion_types(mapping),
        "canonical_candidate_id": candidate_id,
        "evidence_occurrence_id": occurrence_id,
        "m4_subject_id": subject["subject_id"],
        "m5_identity_outcome": mapping["identity_outcome"],
        "unique_string_key": unique_key,
    }


def _resolution_for_mapping(mapping: dict | None) -> str:
    if not mapping:
        return "UNRESOLVED"
    outcome = mapping.get("identity_outcome")
    if outcome in CANDIDATE_M5_OUTCOMES:
        return "CANDIDATE"
    if outcome in {"EXPLICIT_NONCANDIDATE", "GENERIC_OR_NONIDENTIFYING"}:
        return "GENERIC_DISCARDED"
    return "UNRESOLVED"


def _component_candidate_ids(
    unique_keys: list[str],
    component_rows_by_key: dict[str, list[dict]],
    subject_by_source_string: dict[str, dict],
    mapping_by_subject: dict[str, dict],
) -> set[str]:
    candidate_ids = set()
    for unique_key in unique_keys:
        for component in component_rows_by_key.get(unique_key, []):
            subject = subject_by_source_string.get(component["text"])
            if not subject:
                continue
            mapping = mapping_by_subject.get(subject["subject_id"])
            if mapping and mapping.get("identity_outcome") in CANDIDATE_M5_OUTCOMES and mapping.get("candidate_id"):
                candidate_ids.add(mapping["candidate_id"])
    return candidate_ids


def _note_for_outcome(outcome: str, candidate_count: int, subject_count: int) -> str:
    if outcome == "CANDIDATE_LINKED":
        if subject_count > 1:
            return "Frozen row evidence resolves to one M5 canonical candidate; noncandidate/generic components, if any, are discarded in the component ledger."
        return "Frozen row evidence resolves to one M5 canonical candidate."
    if outcome == "CONFLICTING_MULTI_PRODUCT":
        return f"Frozen row evidence maps to {candidate_count} distinct M5 canonical candidates."
    if outcome == "IDENTITY_CONFLICT_UNRESOLVED":
        return "At least one bound M5 subject remains CONFLICT_UNRESOLVED; M6 did not re-adjudicate it."
    if outcome == "INSUFFICIENT_EVIDENCE":
        return "At least one bound subject lacks sufficient frozen M5 identity evidence, or no M4 subject binding exists."
    return f"All bound M5 subjects resolve to {outcome}."


def map_rows(build_name: str, inputs: dict[str, list[dict]]) -> dict[str, list[dict] | dict]:
    indexes = build_indexes(inputs)
    occurrence_to_unique_key = indexes["occurrence_to_unique_key"]
    subject_by_source_string = indexes["subject_by_source_string"]
    mapping_by_subject = indexes["mapping_by_subject"]
    aliases_by_subject_candidate = indexes["aliases_by_subject_candidate"]
    component_rows_by_key = indexes["component_rows_by_key"]
    conflicts_by_subject = indexes["conflicts_by_subject"]
    insufficient_subjects = indexes["insufficient_subjects"]

    frozen_rows = sorted(inputs["frozen_rows"], key=lambda row: row["frozen_row_id"])
    if build_name == "build_b":
        frozen_rows = list(reversed(frozen_rows))

    row_outcomes = []
    row_candidate_mappings = []
    combination_components = []
    unresolved_rows = []
    evidence_bindings = []
    boundary_rows = []

    for frozen in frozen_rows:
        row_id = frozen["frozen_row_id"]
        occurrence_ids = sorted(frozen.get("evidence_occurrence_ids", []))
        unique_keys = sorted({occurrence_to_unique_key.get(occ) for occ in occurrence_ids if occurrence_to_unique_key.get(occ)})

        subject_ids = []
        m5_outcomes = []
        binding_path = []
        candidates_by_id = {}
        conflict_subject_ids = []
        insufficient_subject_ids = []
        for unique_key in unique_keys:
            subject = subject_by_source_string.get(unique_key)
            mapping = mapping_by_subject.get(subject["subject_id"]) if subject else None
            matching_occurrences = [occ for occ in occurrence_ids if occurrence_to_unique_key.get(occ) == unique_key]
            for occurrence_id in matching_occurrences or [None]:
                binding_path.append(
                    _binding_entry(
                        occurrence_id=occurrence_id,
                        unique_key=unique_key,
                        subject=subject,
                        mapping=mapping,
                        aliases_by_subject_candidate=aliases_by_subject_candidate,
                    )
                )
            if subject:
                subject_ids.append(subject["subject_id"])
            if mapping:
                m5_outcomes.append(mapping["identity_outcome"])
                if mapping.get("identity_outcome") in CANDIDATE_M5_OUTCOMES and mapping.get("candidate_id"):
                    candidates_by_id[mapping["candidate_id"]] = mapping
                if mapping.get("identity_outcome") == "CONFLICT_UNRESOLVED":
                    conflict_subject_ids.append(mapping["subject_id"])
                if mapping.get("identity_outcome") == "INSUFFICIENT_EVIDENCE":
                    insufficient_subject_ids.append(mapping["subject_id"])
            else:
                insufficient_subject_ids.append(f"NO_SUBJECT::{unique_key}")

            for component in component_rows_by_key.get(unique_key, []):
                component_subject = subject_by_source_string.get(component["text"])
                component_mapping = (
                    mapping_by_subject.get(component_subject["subject_id"]) if component_subject else None
                )
                if (
                    component_subject
                    and component_mapping
                    and component_mapping.get("identity_outcome") in CANDIDATE_M5_OUTCOMES
                    and component_mapping.get("candidate_id")
                ):
                    binding_path.append(
                        _binding_entry(
                            occurrence_id=None,
                            unique_key=f"{unique_key}::component::{component['component_index']}::{component['text']}",
                            subject=component_subject,
                            mapping=component_mapping,
                            aliases_by_subject_candidate=aliases_by_subject_candidate,
                        )
                    )
        candidates_by_id.update(
            {
                candidate_id: {"candidate_id": candidate_id}
                for candidate_id in _component_candidate_ids(
                    unique_keys,
                    component_rows_by_key,
                    subject_by_source_string,
                    mapping_by_subject,
                )
            }
        )
        candidate_ids = sorted(candidates_by_id)
        if conflict_subject_ids:
            outcome = "IDENTITY_CONFLICT_UNRESOLVED"
        elif insufficient_subject_ids or not unique_keys:
            outcome = "INSUFFICIENT_EVIDENCE"
        elif len(candidate_ids) > 1:
            outcome = "CONFLICTING_MULTI_PRODUCT"
        elif len(candidate_ids) == 1:
            outcome = "CANDIDATE_LINKED"
        elif m5_outcomes and all(o == "EXPLICIT_NONCANDIDATE" for o in m5_outcomes):
            outcome = "EXPLICIT_NONCANDIDATE"
        elif m5_outcomes and all(o == "GENERIC_OR_NONIDENTIFYING" for o in m5_outcomes):
            outcome = "GENERIC_OR_NONIDENTIFYING"
        elif "EXPLICIT_NONCANDIDATE" in m5_outcomes:
            outcome = "EXPLICIT_NONCANDIDATE"
        elif "GENERIC_OR_NONIDENTIFYING" in m5_outcomes:
            outcome = "GENERIC_OR_NONIDENTIFYING"
        else:
            outcome = "INSUFFICIENT_EVIDENCE"

        row_outcomes.append(
            {
                "canonical_candidate_id": candidate_ids[0] if outcome == "CANDIDATE_LINKED" else None,
                "frozen_row_id": row_id,
                "intervention_index": frozen["intervention_index"],
                "nct_id": frozen["nct_id"],
                "notes": _note_for_outcome(outcome, len(candidate_ids), len(set(subject_ids))),
                "outcome": outcome,
            }
        )

        evidence_bindings.append(
            {
                "evidence_occurrence_ids": occurrence_ids,
                "frozen_row_id": row_id,
                "m5_outcomes": sorted(set(m5_outcomes)) if m5_outcomes else ["INSUFFICIENT_EVIDENCE"],
                "subject_ids": sorted(set(subject_ids)),
                "unique_string_keys": unique_keys,
            }
        )

        if outcome in {"CANDIDATE_LINKED", "CONFLICTING_MULTI_PRODUCT"}:
            row_candidate_mappings.append(
                {
                    "binding_path": sorted(binding_path, key=lambda x: (x["unique_string_key"], x["evidence_occurrence_id"] or "")),
                    "canonical_candidate_id": candidate_ids[0] if outcome == "CANDIDATE_LINKED" else None,
                    "canonical_candidate_ids": candidate_ids,
                    "frozen_row_id": row_id,
                }
            )

        if outcome in {"CONFLICTING_MULTI_PRODUCT", "IDENTITY_CONFLICT_UNRESOLVED", "INSUFFICIENT_EVIDENCE"}:
            reason = _note_for_outcome(outcome, len(candidate_ids), len(set(subject_ids)))
            pointer = None
            if conflict_subject_ids:
                pointer = {
                    "m5_conflict_subject_ids": sorted(set(conflict_subject_ids)),
                    "m5_conflict_resolution_entries": [
                        conflicts_by_subject[sid] for sid in sorted(set(conflict_subject_ids)) if sid in conflicts_by_subject
                    ],
                }
            elif insufficient_subject_ids:
                pointer = {"m5_insufficient_subject_ids": sorted(set(insufficient_subject_ids))}
            unresolved_rows.append(
                {
                    "frozen_row_id": row_id,
                    "outcome": outcome,
                    "reason": reason,
                    "underlying_m5_pointer": pointer,
                }
            )

        has_generic_discard = any(
            mapping_by_subject.get(subject_by_source_string[key]["subject_id"], {}).get("identity_outcome")
            in {"EXPLICIT_NONCANDIDATE", "GENERIC_OR_NONIDENTIFYING"}
            for key in unique_keys
            if key in subject_by_source_string
        )
        is_combination = any(component_rows_by_key.get(key) for key in unique_keys) or outcome == "CONFLICTING_MULTI_PRODUCT" or (
            outcome == "CANDIDATE_LINKED" and has_generic_discard
        )
        if is_combination:
            components = []
            for unique_key in unique_keys:
                parsed = component_rows_by_key.get(unique_key)
                if parsed:
                    for component in sorted(parsed, key=lambda x: x["component_index"]):
                        component_subject = subject_by_source_string.get(component["text"])
                        component_mapping = (
                            mapping_by_subject.get(component_subject["subject_id"]) if component_subject else None
                        )
                        source_mapping = mapping_by_subject.get(subject_by_source_string[unique_key]["subject_id"]) if unique_key in subject_by_source_string else None
                        mapping_for_component = component_mapping or source_mapping
                        components.append(
                            {
                                "canonical_candidate_id": mapping_for_component.get("candidate_id") if mapping_for_component else None,
                                "component_text": component["text"],
                                "resolution": _resolution_for_mapping(mapping_for_component),
                            }
                        )
                else:
                    subject = subject_by_source_string.get(unique_key)
                    mapping = mapping_by_subject.get(subject["subject_id"]) if subject else None
                    components.append(
                        {
                            "canonical_candidate_id": mapping.get("candidate_id") if mapping else None,
                            "component_text": unique_key,
                            "resolution": _resolution_for_mapping(mapping),
                        }
                    )
            combination_components.append(
                {
                    "components": components,
                    "frozen_row_id": row_id,
                    "raw_string_or_component_source": " | ".join(unique_keys),
                }
            )

        if conflict_subject_ids:
            boundary_rows.append(
                {
                    "escape_hatch_applied": False,
                    "frozen_row_id": row_id,
                    "reason": "Bound subject is M5 CONFLICT_UNRESOLVED; row kept unresolved under M6 constraint 5.",
                    "subject_ids": sorted(set(conflict_subject_ids)),
                }
            )
        if insufficient_subject_ids:
            real_insufficient = [sid for sid in insufficient_subject_ids if sid in insufficient_subjects]
            if real_insufficient:
                boundary_rows.append(
                    {
                        "escape_hatch_applied": False,
                        "frozen_row_id": row_id,
                        "reason": "Bound subject is M5 INSUFFICIENT_EVIDENCE; row kept insufficient under M6 constraint 5.",
                        "subject_ids": sorted(set(real_insufficient)),
                    }
                )

    for rows in (row_outcomes, row_candidate_mappings, combination_components, unresolved_rows, evidence_bindings, boundary_rows):
        rows.sort(key=lambda row: row["frozen_row_id"])

    comparison_basis = {
        "row_outcome": row_outcomes,
        "row_candidate_mapping": row_candidate_mappings,
        "combination_component": combination_components,
        "unresolved_row": unresolved_rows,
        "row_evidence_binding": evidence_bindings,
        "row_identity_boundary": boundary_rows,
    }
    return {
        **comparison_basis,
        "summary": {
            "build": build_name,
            "combination_row_count": len(combination_components),
            "escape_hatch_count": sum(1 for row in boundary_rows if row.get("escape_hatch_applied")),
            "outcome_counts": dict(sorted(Counter(row["outcome"] for row in row_outcomes).items())),
            "total_rows": len(row_outcomes),
        },
    }


def compare_builds(build_a: dict, build_b: dict) -> tuple[list[dict], dict]:
    a_by_row = {row["frozen_row_id"]: row for row in build_a["row_outcome"]}
    b_by_row = {row["frozen_row_id"]: row for row in build_b["row_outcome"]}
    all_rows = sorted(set(a_by_row) | set(b_by_row))
    reconciliation = []
    agreements = 0
    for row_id in all_rows:
        a = a_by_row.get(row_id)
        b = b_by_row.get(row_id)
        same = (
            a is not None
            and b is not None
            and a.get("outcome") == b.get("outcome")
            and a.get("canonical_candidate_id") == b.get("canonical_candidate_id")
        )
        if same:
            agreements += 1
        else:
            reconciliation.append(
                {
                    "build_a": a,
                    "build_b": b,
                    "frozen_row_id": row_id,
                    "reason": "Build A and Build B row outcome and/or canonical candidate differed.",
                }
            )
    total = len(all_rows)
    return reconciliation, {
        "agreement_rate": agreements / total if total else 0.0,
        "agreements": agreements,
        "disagreements": total - agreements,
        "total_rows": total,
    }
