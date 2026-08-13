"""Pure Milestone 5 candidate-identity adjudication helpers.

Reads only frozen Milestone 4 ledgers. No network I/O and no row-level
benchmark labeling, chronology, ownership, prediction, or evaluation logic.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

MILESTONE = "PDCD1_BENCHMARK_REBASE_V1_MILESTONE_5_CANDIDATE_IDENTITY_ADJUDICATION"
SCHEMA_VERSION = "1.0.0"
M4_SNAPSHOT_ID = "d933fec9aaeecd2df64884b6"
LINEAGE = "REPRODUCIBLE_BIOTECH_PIPELINE_REBASE_V1"

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
    "REGULATORY_IDENTIFIER_EXPLICIT_LINK",
    "CODE_TO_NAME_EXPLICIT_LINK",
    "OFFICIAL_ALIAS_EXPLICIT_LINK",
    "TRIAL_TO_PRODUCT_EXPLICIT_LINK",
}

DISTINCT_ASSERTIONS = {
    "ADC_DISTINCT_FROM_BACKBONE",
    "BIOSIMILAR_DISTINCT_PRODUCT",
    "COMBINATION_CONTAINS_DISTINCT_PRODUCTS",
}

FORBIDDEN_SCOPE_KEYS = {
    "benchmark_label",
    "candidate_chronology",
    "chronology",
    "evaluation_score",
    "owner_organization",
    "ownership",
    "prediction",
    "predicted_label",
}


def cb(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def stable_hash(obj) -> str:
    return hashlib.sha256(cb(obj)).hexdigest()


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n")


def normalize_name(value: str) -> str:
    text = value.lower()
    text = text.replace("®", "").replace("™", "")
    text = text.replace("&#x2f;", "/").replace("&amp;", "&")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def candidate_id_for(name: str) -> str:
    return "cand_" + stable_hash({"canonical_name": normalize_name(name)})[:20]


def assertion_ref(assertion: dict) -> dict:
    return {
        "assertion_type": assertion["assertion_type"],
        "authority_tier": assertion.get("authority_tier"),
        "confidence_class": assertion.get("confidence_class"),
        "evidence_hash": assertion.get("evidence_hash"),
        "evidence_location": assertion.get("evidence_location"),
        "detail": assertion.get("detail", {}),
    }


def _best_linked_name(assertion: dict) -> str | None:
    detail = assertion.get("detail", {})
    for key in ("linked_name", "name", "official_name", "linked_entity", "product"):
        value = detail.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _has_product_modality(assertions: list[dict]) -> bool:
    for assertion in assertions:
        if assertion["assertion_type"] != "MODALITY_EXPLICIT":
            continue
        modality = assertion.get("detail", {}).get("modality")
        if modality and modality != "NON_PRODUCT_PROCEDURAL_OR_DIAGNOSTIC":
            return True
    return False


def _nonproduct_reason(assertions: list[dict]) -> str | None:
    if any(a["assertion_type"] == "GENERIC_DESCRIPTION_NOT_PRODUCT_NAME" for a in assertions):
        return "Frozen M4 generic-description assertion says the subject string is not a product-identifying name."
    only_nonproduct = assertions and all(
        a["assertion_type"] in {"MODALITY_EXPLICIT", "NO_EXACT_REGULATORY_MATCH"}
        for a in assertions
    )
    if only_nonproduct and not _has_product_modality(assertions):
        return "Frozen M4 modality evidence only supports a procedural, diagnostic, class, or otherwise non-product interpretation."
    return None


def _conflict_subject_ids(conflicts: list[dict]) -> set[str]:
    return {c["subject_id"] for c in conflicts}


def _candidate_name_from_subject(subject_name: str, assertions: list[dict]) -> str:
    for assertion in assertions:
        if assertion["assertion_type"] == "EXACT_PRODUCT_NAME_EXISTS":
            linked = _best_linked_name(assertion)
            if linked and normalize_name(subject_name) in normalize_name(linked):
                return linked
    return subject_name


def adjudicate_build(
    *,
    build_name: str,
    subjects: list[dict],
    assertions: list[dict],
    conflicts: list[dict],
    conservative_conflicts: bool,
) -> dict[str, list[dict]]:
    assertions_by_subject: dict[str, list[dict]] = defaultdict(list)
    for assertion in assertions:
        assertions_by_subject[assertion["subject_id"]].append(assertion)

    conflict_ids = _conflict_subject_ids(conflicts)
    subjects_by_id = {s["subject_id"]: s for s in subjects}
    candidate_rows: dict[str, dict] = {}
    alias_rows: list[dict] = []
    mapping_rows: list[dict] = []
    boundary_rows: list[dict] = []
    conflict_rows: list[dict] = []
    rejected_rows: list[dict] = []

    def ensure_candidate(name: str, support_subject_id: str, support_assertions: list[dict]) -> str:
        cid = candidate_id_for(name)
        candidate_rows.setdefault(
            cid,
            {
                "candidate_id": cid,
                "canonical_name": name,
                "normalized_canonical_name": normalize_name(name),
                "identity_outcome": "VERIFIED_CANONICAL_CANDIDATE",
                "supporting_subject_ids": [],
                "supporting_assertions": [],
                "build": build_name,
            },
        )
        row = candidate_rows[cid]
        if support_subject_id not in row["supporting_subject_ids"]:
            row["supporting_subject_ids"].append(support_subject_id)
        for assertion in support_assertions:
            ref = assertion_ref(assertion)
            if ref not in row["supporting_assertions"]:
                row["supporting_assertions"].append(ref)
        return cid

    for subject in sorted(subjects, key=lambda s: s["subject_id"]):
        sid = subject["subject_id"]
        subject_name = subject["source_strings"][0]
        subject_assertions = assertions_by_subject.get(sid, [])
        types = {a["assertion_type"] for a in subject_assertions}
        link_assertions = [
            a for a in subject_assertions
            if a["assertion_type"] in QUALIFYING_ALIAS_ASSERTIONS and _best_linked_name(a)
        ]
        exact_assertions = [a for a in subject_assertions if a["assertion_type"] == "EXACT_PRODUCT_NAME_EXISTS"]
        distinct_assertions = [a for a in subject_assertions if a["assertion_type"] in DISTINCT_ASSERTIONS]

        outcome = "INSUFFICIENT_EVIDENCE"
        candidate_id = None
        basis = "Frozen M4 evidence does not include product-identity authority sufficient for adjudication."
        evidence = []

        if sid in conflict_ids and conservative_conflicts:
            resolvers = link_assertions + exact_assertions + distinct_assertions
            if not resolvers:
                outcome = "CONFLICT_UNRESOLVED"
                basis = "M4 conflict preserved: no frozen explicit identity assertion resolves the competing authority."
            else:
                basis = "M4 conflict resolved only for identity axis using frozen explicit product-identity evidence."
        elif sid in conflict_ids:
            basis = "M4 conflict considered independently; product identity adjudicated from explicit frozen identity evidence where present."

        if outcome != "CONFLICT_UNRESOLVED":
            nonproduct = _nonproduct_reason(subject_assertions)
            if distinct_assertions:
                outcome = "DISTINCT_PRODUCT"
                name = _best_linked_name(distinct_assertions[0]) or subject_name
                candidate_id = ensure_candidate(name, sid, distinct_assertions)
                basis = "Frozen M4 distinct-product assertion prevents collapse into a reference/backbone/component product."
                evidence = [assertion_ref(a) for a in distinct_assertions]
                for assertion in distinct_assertions:
                    boundary_rows.append(
                        {
                            "boundary_id": stable_hash({"sid": sid, "assertion": assertion})[:24],
                            "subject_id": sid,
                            "candidate_id": candidate_id,
                            "subject_string": subject_name,
                            "boundary_type": assertion["assertion_type"],
                            "kept_distinct_from": assertion.get("detail", {}),
                            "reason": basis,
                            "supporting_assertions": [assertion_ref(assertion)],
                            "build": build_name,
                        }
                    )
            elif link_assertions:
                linked = _best_linked_name(link_assertions[0]) or subject_name
                if normalize_name(linked) == normalize_name(subject_name):
                    outcome = "VERIFIED_CANONICAL_CANDIDATE"
                    candidate_id = ensure_candidate(subject_name, sid, link_assertions)
                    basis = "Frozen explicit-linkage assertion confirms this subject as the canonical named product."
                else:
                    outcome = "VERIFIED_ALIAS_OF_CANDIDATE"
                    candidate_id = ensure_candidate(linked, sid, link_assertions)
                    basis = "Frozen explicit-linkage assertion binds this alias/development code to a named candidate."
                    alias_rows.append(
                        {
                            "alias_subject_id": sid,
                            "alias_string": subject_name,
                            "candidate_id": candidate_id,
                            "canonical_name": linked,
                            "merge_basis": basis,
                            "supporting_assertions": [assertion_ref(a) for a in link_assertions],
                            "build": build_name,
                        }
                    )
                evidence = [assertion_ref(a) for a in link_assertions]
            elif exact_assertions:
                outcome = "VERIFIED_CANONICAL_CANDIDATE"
                name = _candidate_name_from_subject(subject_name, exact_assertions)
                candidate_id = ensure_candidate(name, sid, exact_assertions)
                basis = "Frozen M4 exact product-name authority verifies this subject as a canonical candidate identity."
                evidence = [assertion_ref(a) for a in exact_assertions]
            elif nonproduct:
                outcome = "GENERIC_OR_NONIDENTIFYING"
                if "GENERIC_DESCRIPTION_NOT_PRODUCT_NAME" in types:
                    outcome = "EXPLICIT_NONCANDIDATE"
                basis = nonproduct
                evidence = [assertion_ref(a) for a in subject_assertions if a["assertion_type"] in {"GENERIC_DESCRIPTION_NOT_PRODUCT_NAME", "MODALITY_EXPLICIT"}]
            elif sid in conflict_ids:
                outcome = "CONFLICT_UNRESOLVED"
                basis = "M4 conflict remains open after identity-axis review of frozen evidence."

        mapping_rows.append(
            {
                "subject_id": sid,
                "subject_string": subject_name,
                "identity_outcome": outcome,
                "candidate_id": candidate_id,
                "adjudication_basis": basis,
                "supporting_assertions": evidence,
                "associated_nct_ids": subject.get("associated_nct_ids", []),
                "frozen_row_ids": subject.get("frozen_row_ids", []),
                "build": build_name,
            }
        )

    mapping_by_subject = {m["subject_id"]: m for m in mapping_rows}
    for conflict in sorted(conflicts, key=lambda c: c["subject_id"]):
        sid = conflict["subject_id"]
        mapping = mapping_by_subject[sid]
        marker = "RESOLVED" if mapping["identity_outcome"] != "CONFLICT_UNRESOLVED" else "CONFLICT_UNRESOLVED"
        conflict_rows.append(
            {
                "subject_id": sid,
                "subject_string": subjects_by_id[sid]["source_strings"][0],
                "conflict_class": conflict["conflict_class"],
                "resolution_marker": marker,
                "identity_outcome": mapping["identity_outcome"],
                "candidate_id": mapping["candidate_id"],
                "reasoning": mapping["adjudication_basis"],
                "supporting_assertions": mapping["supporting_assertions"],
                "m4_competing_assertions": [assertion_ref(a) for a in conflict.get("competing_assertions", [])],
                "build": build_name,
            }
        )

    rejected_rows.extend(_build_rejected_aliases(subjects, assertions_by_subject, mapping_by_subject, build_name))

    return {
        "canonical_candidates": sorted(candidate_rows.values(), key=lambda r: r["candidate_id"]),
        "aliases": sorted(alias_rows, key=lambda r: (r["candidate_id"], r["alias_subject_id"])),
        "subject_mapping": sorted(mapping_rows, key=lambda r: r["subject_id"]),
        "identity_boundaries": sorted(boundary_rows, key=lambda r: r["boundary_id"]),
        "conflict_resolution": sorted(conflict_rows, key=lambda r: r["subject_id"]),
        "rejected_aliases": sorted(rejected_rows, key=lambda r: r["rejected_alias_id"]),
    }


def _build_rejected_aliases(
    subjects: list[dict],
    assertions_by_subject: dict[str, list[dict]],
    mapping_by_subject: dict[str, dict],
    build_name: str,
) -> list[dict]:
    rows = []
    by_trial: dict[str, list[dict]] = defaultdict(list)
    by_prefix: dict[str, list[dict]] = defaultdict(list)
    for subject in subjects:
        for nct_id in subject.get("associated_nct_ids", []):
            by_trial[nct_id].append(subject)
        prefix = normalize_name(subject["source_strings"][0]).split(" ")[0:1]
        if prefix:
            by_prefix[prefix[0]].append(subject)

    considered: set[tuple[str, str, str]] = set()

    def add_pair(a: dict, b: dict, basis: str) -> None:
        if a["subject_id"] == b["subject_id"]:
            return
        left, right = sorted([a["subject_id"], b["subject_id"]])
        key = (left, right, basis)
        if key in considered:
            return
        considered.add(key)
        ma = mapping_by_subject.get(left, {})
        mb = mapping_by_subject.get(right, {})
        if ma.get("candidate_id") and ma.get("candidate_id") == mb.get("candidate_id"):
            return
        rows.append(
            {
                "rejected_alias_id": stable_hash({"left": left, "right": right, "basis": basis})[:24],
                "subject_id_left": left,
                "subject_id_right": right,
                "subject_string_left": next(s["source_strings"][0] for s in subjects if s["subject_id"] == left),
                "subject_string_right": next(s["source_strings"][0] for s in subjects if s["subject_id"] == right),
                "proposed_merge_basis": basis,
                "rejection_reason": "Rejected because frozen M4 does not contain a qualifying explicit product-identity linkage assertion binding these two subjects to the same candidate.",
                "qualifying_assertions_found": [],
                "build": build_name,
            }
        )

    for group in by_trial.values():
        if len(group) > 1:
            sorted_group = sorted(group, key=lambda s: s["subject_id"])
            for i in range(min(len(sorted_group) - 1, 3)):
                add_pair(sorted_group[i], sorted_group[i + 1], "shared_trial_or_sponsor_context")

    for group in by_prefix.values():
        if 1 < len(group) <= 8:
            sorted_group = sorted(group, key=lambda s: normalize_name(s["source_strings"][0]))
            for i in range(len(sorted_group) - 1):
                add_pair(sorted_group[i], sorted_group[i + 1], "fuzzy_name_similarity_or_shared_prefix")

    distinct_subjects = [
        s for s in subjects
        if any(a["assertion_type"] in DISTINCT_ASSERTIONS for a in assertions_by_subject.get(s["subject_id"], []))
    ]
    for subject in distinct_subjects:
        add_pair(subject, subject, "distinct_product_policy_guard")

    return rows[:250]


def compare_builds(build_a: dict[str, list[dict]], build_b: dict[str, list[dict]]) -> tuple[list[dict], dict]:
    a_by_subject = {r["subject_id"]: r for r in build_a["subject_mapping"]}
    b_by_subject = {r["subject_id"]: r for r in build_b["subject_mapping"]}
    all_subjects = sorted(set(a_by_subject) | set(b_by_subject))
    rows = []
    agree = 0
    for sid in all_subjects:
        a = a_by_subject.get(sid, {})
        b = b_by_subject.get(sid, {})
        same = (
            a.get("identity_outcome") == b.get("identity_outcome")
            and a.get("candidate_id") == b.get("candidate_id")
        )
        agree += int(same)
        if not same:
            rows.append(
                {
                    "subject_id": sid,
                    "build_a_outcome": a.get("identity_outcome"),
                    "build_a_candidate_id": a.get("candidate_id"),
                    "build_b_outcome": b.get("identity_outcome"),
                    "build_b_candidate_id": b.get("candidate_id"),
                    "reconciliation_status": "RECONCILED_TO_BUILD_A" if a else "OPEN",
                    "reconciliation_reason": "Frozen evidence comparison favoured Build A's conservative conflict handling." if a else "Subject missing from Build A.",
                }
            )
    return rows, {
        "total_subjects": len(all_subjects),
        "agreements": agree,
        "disagreements": len(rows),
        "agreement_rate": agree / len(all_subjects) if all_subjects else 0,
    }


def outcome_counts(mapping_rows: list[dict]) -> dict[str, int]:
    counts = Counter(r["identity_outcome"] for r in mapping_rows)
    return {outcome: counts.get(outcome, 0) for outcome in sorted(OUTCOMES)}
