"""Milestone 3: PDCD1_BENCHMARK_REBASE_V1_MILESTONE_3_CANDIDATE_BEARING_EVIDENCE_EXTRACTION_AND_TRIAGE.

Extracts and triages candidate-bearing registry evidence (intervention
names, official other-names) from the frozen Milestone 1 population (81
studies / 300 intervention rows) and the complete Milestone 2 registry
history capture. This stage performs evidence triage only: it does not
create canonical candidates, aliases, ownership claims, candidate
chronology, benchmark labels, predictions, or evaluation metrics.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdcd1_evidence_triage_lib as lib  # noqa: E402

LINEAGE = "REPRODUCIBLE_BIOTECH_PIPELINE_REBASE_V1"
MILESTONE = "PDCD1_BENCHMARK_REBASE_V1_MILESTONE_3_CANDIDATE_BEARING_EVIDENCE_EXTRACTION_AND_TRIAGE"
STAGE = "03_candidate_bearing_evidence_triage"
CANONICAL_TARGET = "PDCD1"

MILESTONE1_SNAPSHOT_ID = "47e9e791f48bb7aacc467e28"
MILESTONE1_ARCHIVE_SHA256 = "7a6b509d42de915a0e0e8e5dfc054c23ffab4e6a3cfa5409acda1a45fae00923"
MILESTONE1_RELEASE_TAG = f"pdcd1-rebase-v1-population-{MILESTONE1_SNAPSHOT_ID}"
MILESTONE1_REPO = "djbm10/Biotech-Asset-Valuation-Engine"

MILESTONE2_SNAPSHOT_ID = "62914ac00fa635d38755e25b"
MILESTONE2_ARCHIVE_SHA256 = "e48ea84d623788957b2cd37a9737b2b3a0c201bce9fd3902faf7a34223c639ae"
MILESTONE2_RELEASE_TAG = f"pdcd1-rebase-v1-history-{MILESTONE2_SNAPSHOT_ID}"
MILESTONE2_REPO = "djbm10/Biotech-Asset-Valuation-Engine"

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE_ROOT = REPO_ROOT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages" / STAGE
STAGING_ROOT = STAGE_ROOT / "_staging"

SCOPE_FLAGS = {
    "canonical_candidates_created": False,
    "aliases_adjudicated": False,
    "ownership_claims_created": False,
    "candidate_chronology_created": False,
    "benchmark_labels_created": False,
    "predictions_generated": False,
    "evaluation_performed": False,
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def atomic_write_json(path: Path, obj) -> None:
    atomic_write(path, (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode())


def atomic_write_jsonl(path: Path, rows) -> None:
    buf = "\n".join(json.dumps(r, sort_keys=True, separators=(",", ":")) for r in rows)
    if rows:
        buf += "\n"
    atomic_write(path, buf.encode())


# ---------------------------------------------------------------------------
# Prerequisite loading + validation
# ---------------------------------------------------------------------------

def load_prerequisite_m1(m1_dir: Path) -> dict:
    manifest = json.loads((m1_dir / "manifest.json").read_text())
    receipt = json.loads((m1_dir / "receipt.json").read_text())
    if receipt.get("snapshot_id") != MILESTONE1_SNAPSHOT_ID:
        raise ValueError(
            f"PREREQUISITE_SNAPSHOT_ID_MISMATCH: m1 receipt snapshot_id "
            f"{receipt.get('snapshot_id')!r} != expected {MILESTONE1_SNAPSHOT_ID!r}"
        )
    if receipt.get("status") != "FINALIZED":
        raise ValueError("PREREQUISITE_NOT_FINALIZED: m1 receipt.status != FINALIZED")

    population_path = m1_dir / "source" / "benchmark_population.json"
    raw_bytes = population_path.read_bytes()
    raw_sha = lib.sha_bytes(raw_bytes)
    bindings = receipt.get("artifacts", {})
    expected_sha = None
    for key, meta in bindings.items():
        if key.endswith("benchmark_population.json"):
            expected_sha = meta.get("sha256")
    if expected_sha and expected_sha != raw_sha:
        raise ValueError("PREREQUISITE_ARTIFACT_HASH_MISMATCH: benchmark_population.json")

    population = json.loads(raw_bytes)
    studies = population["studies"]
    nct_ids = []
    frozen_rows = []
    for study_index, study in enumerate(studies):
        nct_id = study["protocolSection"]["identificationModule"]["nctId"]
        nct_ids.append(nct_id)
        interventions = (
            study["protocolSection"].get("armsInterventionsModule", {}).get("interventions", [])
        )
        for intervention_index, intervention in enumerate(interventions):
            frozen_rows.append(
                {
                    "frozen_row_id": f"row_{len(frozen_rows):03d}_{nct_id}_{intervention_index}",
                    "study_index": study_index,
                    "nct_id": nct_id,
                    "intervention_index": intervention_index,
                    "intervention": intervention,
                }
            )
    expected_studies = manifest["checks"]["selected_benchmark_studies"]
    expected_rows = manifest["checks"]["selected_benchmark_intervention_rows"]
    if len(nct_ids) != expected_studies:
        raise ValueError("PREREQUISITE_STUDY_COUNT_MISMATCH")
    if len(frozen_rows) != expected_rows:
        raise ValueError("PREREQUISITE_ROW_COUNT_MISMATCH")

    return {
        "manifest": manifest,
        "receipt": receipt,
        "raw_sha256": raw_sha,
        "nct_ids": nct_ids,
        "frozen_rows": frozen_rows,
    }


def load_prerequisite_m2(m2_dir: Path, expected_nct_ids: set[str]) -> dict:
    manifest = json.loads((m2_dir / "manifest.json").read_text())
    receipt = json.loads((m2_dir / "receipt.json").read_text())
    if receipt.get("snapshot_id") != MILESTONE2_SNAPSHOT_ID:
        raise ValueError(
            f"PREREQUISITE_SNAPSHOT_ID_MISMATCH: m2 receipt snapshot_id "
            f"{receipt.get('snapshot_id')!r} != expected {MILESTONE2_SNAPSHOT_ID!r}"
        )
    if receipt.get("status") != "FINALIZED":
        raise ValueError("PREREQUISITE_NOT_FINALIZED: m2 receipt.status != FINALIZED")

    version_ledger_path = m2_dir / "normalized" / "version_ledger.jsonl"
    version_rows = [
        json.loads(line) for line in version_ledger_path.read_text().splitlines() if line.strip()
    ]
    captured = [r for r in version_rows if r["status"] == "CAPTURED"]
    nct_ids_seen = {r["nct_id"] for r in captured}
    if nct_ids_seen != expected_nct_ids:
        raise ValueError("PREREQUISITE_NCT_ID_SET_MISMATCH: m1/m2 frozen study sets differ")

    by_nct: dict[str, list[dict]] = {}
    for row in captured:
        by_nct.setdefault(row["nct_id"], []).append(row)
    for rows in by_nct.values():
        rows.sort(key=lambda r: r["version"])

    return {"manifest": manifest, "receipt": receipt, "versions_by_nct": by_nct, "root": m2_dir}


# ---------------------------------------------------------------------------
# Occurrence extraction
# ---------------------------------------------------------------------------

def _intervention_occurrences(
    interventions: list[dict],
    base_pointer: str,
    nct_id: str,
    version_flag: str,
    version: int | None,
    version_date: str | None,
    frozen_row_id: str | None,
) -> list[dict]:
    occ = []
    for i, iv in enumerate(interventions):
        name = iv.get("name")
        if isinstance(name, str):
            pointer = f"{base_pointer}/{i}/name"
            occ.append(
                _make_occurrence(
                    nct_id, version_flag, version, version_date, i, "name", None,
                    pointer, name, frozen_row_id,
                )
            )
        other_names = iv.get("otherNames")
        if isinstance(other_names, list):
            for j, on in enumerate(other_names):
                if isinstance(on, str):
                    pointer = f"{base_pointer}/{i}/otherNames/{j}"
                    occ.append(
                        _make_occurrence(
                            nct_id, version_flag, version, version_date, i,
                            "official_other_name", j, pointer, on, frozen_row_id,
                        )
                    )
    return occ


def _make_occurrence(
    nct_id, version_flag, version, version_date, intervention_index, field_class,
    sub_index, pointer, raw_string, frozen_row_id,
) -> dict:
    raw_sha = lib.sha_str(raw_string)
    key = {
        "nct_id": nct_id,
        "version_flag": version_flag,
        "version": version,
        "intervention_index": intervention_index,
        "field_class": field_class,
        "sub_index": sub_index,
        "pointer": pointer,
        "raw_sha256": raw_sha,
    }
    occurrence_id = lib.stable_hash(key)[:24]
    return {
        "occurrence_id": occurrence_id,
        "nct_id": nct_id,
        "version_flag": version_flag,
        "version": version,
        "version_date": version_date,
        "intervention_index": intervention_index,
        "field_class": field_class,
        "sub_index": sub_index,
        "json_pointer": pointer,
        "raw_string": raw_string,
        "raw_string_nfc": lib.normalize_nfc(raw_string),
        "raw_sha256": raw_sha,
        "frozen_row_id": frozen_row_id,
    }


def extract_occurrences(m1: dict, m2: dict) -> list[dict]:
    occurrences: list[dict] = []

    for row in m1["frozen_rows"]:
        base_pointer = (
            f"/studies/{row['study_index']}/protocolSection/armsInterventionsModule/interventions"
        )
        iv = row["intervention"]
        i = row["intervention_index"]
        name = iv.get("name")
        if isinstance(name, str):
            pointer = f"{base_pointer}/{i}/name"
            occurrences.append(
                _make_occurrence(
                    row["nct_id"], "FROZEN_CURRENT", None, None, i, "name", None,
                    pointer, name, row["frozen_row_id"],
                )
            )
        other_names = iv.get("otherNames")
        if isinstance(other_names, list):
            for j, on in enumerate(other_names):
                if isinstance(on, str):
                    pointer = f"{base_pointer}/{i}/otherNames/{j}"
                    occurrences.append(
                        _make_occurrence(
                            row["nct_id"], "FROZEN_CURRENT", None, None, i,
                            "official_other_name", j, pointer, on, row["frozen_row_id"],
                        )
                    )

    m2_root = m2["root"]
    for nct_id in sorted(m2["versions_by_nct"]):
        for vrow in m2["versions_by_nct"][nct_id]:
            version = vrow["version"]
            path = m2_root / vrow["path"]
            raw_bytes = path.read_bytes()
            if lib.sha_bytes(raw_bytes) != vrow["sha256"]:
                raise ValueError(f"VERSION_ARTIFACT_HASH_MISMATCH: {vrow['path']}")
            body = json.loads(raw_bytes)
            interventions = (
                body.get("study", {})
                .get("protocolSection", {})
                .get("armsInterventionsModule", {})
                .get("interventions", [])
            )
            version_flag = "ORIGINAL_VERSION" if version == 0 else "HISTORICAL_VERSION"
            base_pointer = "/study/protocolSection/armsInterventionsModule/interventions"
            occurrences.extend(
                _intervention_occurrences(
                    interventions, base_pointer, nct_id, version_flag, version,
                    vrow.get("version_date"), None,
                )
            )

    occurrences.sort(key=lambda o: o["occurrence_id"])
    return occurrences


# ---------------------------------------------------------------------------
# Ledger construction
# ---------------------------------------------------------------------------

def build_unique_exact_string_ledger(occurrences: list[dict]) -> dict[str, dict]:
    by_key: dict[str, dict] = {}
    for occ in occurrences:
        key = occ["raw_string_nfc"]
        entry = by_key.setdefault(
            key,
            {
                "unique_string_key": key,
                "occurrence_ids": [],
                "distinct_raw_spellings": set(),
                "field_classes": set(),
            },
        )
        entry["occurrence_ids"].append(occ["occurrence_id"])
        entry["distinct_raw_spellings"].add(occ["raw_string"])
        entry["field_classes"].add(occ["field_class"])
    for entry in by_key.values():
        entry["occurrence_ids"] = sorted(entry["occurrence_ids"])
        entry["distinct_raw_spellings"] = sorted(entry["distinct_raw_spellings"])
        entry["field_classes"] = sorted(entry["field_classes"])
    return by_key


def build_presentation_variant_ledger(unique_strings: dict[str, dict]) -> dict[str, dict]:
    groups: dict[str, dict] = {}
    for key in sorted(unique_strings):
        pkey = lib.presentation_key(key)
        group = groups.setdefault(pkey, {"presentation_key": pkey, "members": []})
        group["members"].append(key)
    for g in groups.values():
        g["members"] = sorted(g["members"])
        g["member_count"] = len(g["members"])
    return groups


def build_official_other_name_edges(occurrences: list[dict]) -> list[dict]:
    by_context: dict[tuple, dict] = {}
    for occ in occurrences:
        ctx = (occ["nct_id"], occ["version_flag"], occ["version"], occ["intervention_index"])
        by_context.setdefault(ctx, {"name": None, "other_names": []})
        if occ["field_class"] == "name":
            by_context[ctx]["name"] = occ
        elif occ["field_class"] == "official_other_name":
            by_context[ctx]["other_names"].append(occ)

    edges = []
    for ctx, bundle in by_context.items():
        name_occ = bundle["name"]
        if name_occ is None:
            continue
        for on_occ in bundle["other_names"]:
            edge_key = {
                "nct_id": ctx[0],
                "version_flag": ctx[1],
                "version": ctx[2],
                "intervention_index": ctx[3],
                "name_occurrence_id": name_occ["occurrence_id"],
                "other_name_occurrence_id": on_occ["occurrence_id"],
            }
            edges.append(
                {
                    "edge_id": lib.stable_hash(edge_key)[:24],
                    "nct_id": ctx[0],
                    "version_flag": ctx[1],
                    "version": ctx[2],
                    "intervention_index": ctx[3],
                    "name_string": name_occ["raw_string"],
                    "other_name_string": on_occ["raw_string"],
                    "name_occurrence_id": name_occ["occurrence_id"],
                    "other_name_occurrence_id": on_occ["occurrence_id"],
                }
            )
    edges.sort(key=lambda e: e["edge_id"])
    return edges


def classify_unique_strings(unique_strings: dict[str, dict]) -> dict[str, dict]:
    classified = {}
    for key, entry in unique_strings.items():
        field_classes = set(entry["field_classes"])
        is_otherName_only = field_classes == {"official_other_name"}
        category, flags = lib.classify(key, sorted(field_classes)[0] if len(field_classes) == 1 else "mixed", is_otherName_only)
        components = lib.parse_components(key) if category == "MULTI_PRODUCT_OR_COMBINATION_STRING" else []
        classified[key] = {
            "unique_string_key": key,
            "triage_category": category,
            "flags": flags,
            "components": components,
            "occurrence_ids": entry["occurrence_ids"],
            "distinct_raw_spellings": entry["distinct_raw_spellings"],
        }
    return classified


def build_historical_appearance_ledger(occurrences: list[dict]) -> dict[str, dict]:
    facts: dict[str, dict] = {}
    for occ in occurrences:
        key = occ["raw_string_nfc"]
        entry = facts.setdefault(
            key,
            {
                "unique_string_key": key,
                "appears_in_frozen_current": False,
                "appears_in_original_version": False,
                "first_registry_string_appearance_version": None,
                "first_registry_string_appearance_version_date": None,
                "observed_nct_ids": set(),
            },
        )
        entry["observed_nct_ids"].add(occ["nct_id"])
        if occ["version_flag"] == "FROZEN_CURRENT":
            entry["appears_in_frozen_current"] = True
            continue
        if occ["version_flag"] == "ORIGINAL_VERSION":
            entry["appears_in_original_version"] = True
        v = occ["version"]
        if entry["first_registry_string_appearance_version"] is None or v < entry["first_registry_string_appearance_version"]:
            entry["first_registry_string_appearance_version"] = v
            entry["first_registry_string_appearance_version_date"] = occ["version_date"]
    for entry in facts.values():
        entry["observed_nct_ids"] = sorted(entry["observed_nct_ids"])
    return facts


def build_frozen_row_bindings(m1: dict, occurrences: list[dict]) -> list[dict]:
    by_row: dict[str, list[dict]] = {}
    for occ in occurrences:
        if occ["version_flag"] != "FROZEN_CURRENT":
            continue
        by_row.setdefault(occ["frozen_row_id"], []).append(occ["occurrence_id"])
    bindings = []
    for row in m1["frozen_rows"]:
        bindings.append(
            {
                "frozen_row_id": row["frozen_row_id"],
                "nct_id": row["nct_id"],
                "intervention_index": row["intervention_index"],
                "evidence_occurrence_ids": sorted(by_row.get(row["frozen_row_id"], [])),
            }
        )
    bindings.sort(key=lambda b: b["frozen_row_id"])
    return bindings


def build_review_queues(classified: dict[str, dict], presentation_groups: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    group_size_by_key = {}
    for g in presentation_groups.values():
        for member in g["members"]:
            group_size_by_key[member] = g["member_count"]

    targeted, forensic = [], []
    for key in sorted(classified):
        row = dict(classified[key])
        row["presentation_group_size"] = group_size_by_key.get(key, 1)
        routes = lib.review_routing(row)
        for route in routes:
            entry = {
                "unique_string_key": key,
                "triage_category": row["triage_category"],
                "reason": route["reason"],
                "occurrence_ids": row["occurrence_ids"],
            }
            if route["queue"] == "TARGETED":
                targeted.append(entry)
            else:
                forensic.append(entry)
    targeted.sort(key=lambda e: e["unique_string_key"])
    forensic.sort(key=lambda e: e["unique_string_key"])
    return targeted, forensic


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def compute_staging_key(m1: dict, m2: dict) -> str:
    return lib.stable_hash(
        {
            "milestone1_snapshot_id": MILESTONE1_SNAPSHOT_ID,
            "milestone2_snapshot_id": MILESTONE2_SNAPSHOT_ID,
            "frozen_row_ids": sorted(r["frozen_row_id"] for r in m1["frozen_rows"]),
            "nct_ids": sorted(m1["nct_ids"]),
            "extractor_schema_version": lib.EXTRACTOR_SCHEMA_VERSION,
            "extraction_rules_hash": lib.EXTRACTION_RULES_HASH,
        }
    )


def find_finalized_snapshot_by_staging_key(staging_key: str) -> Path | None:
    if not STAGE_ROOT.is_dir():
        return None
    for p in STAGE_ROOT.iterdir():
        if not p.is_dir() or p.name == "_staging":
            continue
        manifest_path = p / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if manifest.get("staging_key") == staging_key and manifest.get("stage_status") == "FINALIZED":
            return p
    return None


def run_extraction(m1_dir: Path, m2_dir: Path) -> dict:
    m1 = load_prerequisite_m1(m1_dir)
    m2 = load_prerequisite_m2(m2_dir, set(m1["nct_ids"]))
    staging_key = compute_staging_key(m1, m2)

    existing = find_finalized_snapshot_by_staging_key(staging_key)
    if existing is not None:
        return {
            "status": "ALREADY_FINALIZED",
            "snapshot_dir": existing,
            "staging_key": staging_key,
            "counters": {
                "api_calls": 0, "downloads": 0, "source_extraction_operations": 0,
                "adjudications": 0, "predictions": 0, "scoring_operations": 0, "writes": 0,
            },
        }

    occurrences = extract_occurrences(m1, m2)
    unique_strings = build_unique_exact_string_ledger(occurrences)
    presentation_groups = build_presentation_variant_ledger(unique_strings)
    edges = build_official_other_name_edges(occurrences)
    classified = classify_unique_strings(unique_strings)
    historical_appearance = build_historical_appearance_ledger(occurrences)
    frozen_bindings = build_frozen_row_bindings(m1, occurrences)
    targeted_queue, forensic_queue = build_review_queues(classified, presentation_groups)

    derived_evidence_manifest_hash = lib.stable_hash(
        {
            "occurrence_count": len(occurrences),
            "occurrence_ids": sorted(o["occurrence_id"] for o in occurrences),
            "unique_string_keys": sorted(unique_strings.keys()),
            "edge_ids": sorted(e["edge_id"] for e in edges),
            "triage_categories": {k: v["triage_category"] for k, v in sorted(classified.items())},
        }
    )
    triage_snapshot_id = lib.stable_hash(
        {"staging_key": staging_key, "derived_evidence_manifest_hash": derived_evidence_manifest_hash}
    )[:24]

    final_dir = STAGE_ROOT / triage_snapshot_id
    staging_dir = STAGING_ROOT / triage_snapshot_id

    write_snapshot(
        staging_dir, m1, m2, occurrences, unique_strings, presentation_groups, edges,
        classified, historical_appearance, frozen_bindings, targeted_queue, forensic_queue,
        staging_key, triage_snapshot_id, derived_evidence_manifest_hash,
    )

    final_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir.replace(final_dir)

    return {
        "status": "FINALIZED",
        "snapshot_dir": final_dir,
        "staging_key": staging_key,
        "triage_snapshot_id": triage_snapshot_id,
        "counters": {
            "occurrences": len(occurrences),
            "unique_strings": len(unique_strings),
            "presentation_groups": len(presentation_groups),
            "edges": len(edges),
            "frozen_rows": len(frozen_bindings),
            "targeted_queue": len(targeted_queue),
            "forensic_queue": len(forensic_queue),
        },
    }


def write_snapshot(
    staging_dir, m1, m2, occurrences, unique_strings, presentation_groups, edges,
    classified, historical_appearance, frozen_bindings, targeted_queue, forensic_queue,
    staging_key, triage_snapshot_id, derived_evidence_manifest_hash,
) -> None:
    if staging_dir.exists():
        import shutil
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    input_dir = staging_dir / "input"
    extracted_dir = staging_dir / "extracted"
    normalized_dir = staging_dir / "normalized"
    triage_dir = staging_dir / "triage"
    validation_dir = staging_dir / "validation"
    logs_dir = staging_dir / "logs"
    for d in (input_dir, extracted_dir, normalized_dir, triage_dir, validation_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)

    atomic_write_json(
        input_dir / "prerequisite_bindings.json",
        {
            "milestone1": {
                "repository": MILESTONE1_REPO,
                "release_tag": MILESTONE1_RELEASE_TAG,
                "snapshot_id": MILESTONE1_SNAPSHOT_ID,
                "archive_sha256": MILESTONE1_ARCHIVE_SHA256,
                "manifest_sha256": lib.sha_str(json.dumps(m1["manifest"], sort_keys=True)),
                "receipt_sha256": lib.sha_str(json.dumps(m1["receipt"], sort_keys=True)),
                "nct_ids_count": len(m1["nct_ids"]),
                "frozen_rows_count": len(m1["frozen_rows"]),
            },
            "milestone2": {
                "repository": MILESTONE2_REPO,
                "release_tag": MILESTONE2_RELEASE_TAG,
                "snapshot_id": MILESTONE2_SNAPSHOT_ID,
                "archive_sha256": MILESTONE2_ARCHIVE_SHA256,
                "manifest_sha256": lib.sha_str(json.dumps(m2["manifest"], sort_keys=True)),
                "receipt_sha256": lib.sha_str(json.dumps(m2["receipt"], sort_keys=True)),
            },
        },
    )

    atomic_write_jsonl(extracted_dir / "frozen_row_evidence_bindings.jsonl", frozen_bindings)

    atomic_write_jsonl(
        normalized_dir / "candidate_bearing_occurrence_ledger.jsonl", occurrences
    )
    atomic_write_jsonl(
        normalized_dir / "unique_exact_string_ledger.jsonl",
        [classified[k] for k in sorted(classified)],
    )
    atomic_write_jsonl(
        normalized_dir / "presentation_variant_ledger.jsonl",
        [presentation_groups[k] for k in sorted(presentation_groups)],
    )
    atomic_write_jsonl(normalized_dir / "official_other_name_edge_ledger.jsonl", edges)
    atomic_write_jsonl(
        normalized_dir / "historical_appearance_ledger.jsonl",
        [historical_appearance[k] for k in sorted(historical_appearance)],
    )

    atomic_write_jsonl(triage_dir / "targeted_review_queue.jsonl", targeted_queue)
    atomic_write_jsonl(triage_dir / "forensic_review_queue.jsonl", forensic_queue)

    category_counts: dict[str, int] = {}
    for row in classified.values():
        category_counts[row["triage_category"]] = category_counts.get(row["triage_category"], 0) + 1
    atomic_write_json(
        validation_dir / "triage_category_summary.json",
        {"category_counts": category_counts, "total_unique_strings": len(classified)},
    )

    manifest = {
        "lineage": LINEAGE,
        "milestone": MILESTONE,
        "canonical_target": CANONICAL_TARGET,
        "stage_status": "FINALIZED",
        "staging_key": staging_key,
        "triage_snapshot_id": triage_snapshot_id,
        "derived_evidence_manifest_hash": derived_evidence_manifest_hash,
        "extractor_schema_version": lib.EXTRACTOR_SCHEMA_VERSION,
        "extraction_rules_hash": lib.EXTRACTION_RULES_HASH,
        "milestone1_prerequisite": {
            "snapshot_id": MILESTONE1_SNAPSHOT_ID,
            "archive_sha256": MILESTONE1_ARCHIVE_SHA256,
            "nct_ids_count": len(m1["nct_ids"]),
        },
        "milestone2_prerequisite": {
            "snapshot_id": MILESTONE2_SNAPSHOT_ID,
            "archive_sha256": MILESTONE2_ARCHIVE_SHA256,
        },
        "checks": {
            "occurrence_count": len(occurrences),
            "unique_string_count": len(unique_strings),
            "presentation_group_count": len(presentation_groups),
            "official_other_name_edge_count": len(edges),
            "frozen_row_binding_count": len(frozen_bindings),
            "targeted_review_queue_count": len(targeted_queue),
            "forensic_review_queue_count": len(forensic_queue),
        },
        **SCOPE_FLAGS,
    }
    atomic_write_json(staging_dir / "manifest.json", manifest)

    artifacts = {}
    for path in sorted(staging_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            rel = path.relative_to(staging_dir).as_posix()
            data = path.read_bytes()
            artifacts[rel] = {"sha256": lib.sha_bytes(data), "byte_length": len(data)}
    manifest_bytes = (staging_dir / "manifest.json").read_bytes()
    artifacts["manifest.json"] = {
        "sha256": lib.sha_bytes(manifest_bytes),
        "byte_length": len(manifest_bytes),
    }

    receipt = {
        "lineage": LINEAGE,
        "milestone": MILESTONE,
        "snapshot_id": triage_snapshot_id,
        "status": "FINALIZED",
        "generated_at": utcnow(),
        "artifacts": artifacts,
        **SCOPE_FLAGS,
    }
    atomic_write_json(staging_dir / "receipt.json", receipt)

    commands = [
        {"timestamp": utcnow(), "command": "extract_pdcd1_rebase_v1_evidence_triage.run_extraction"},
    ]
    atomic_write(
        logs_dir / "extraction.jsonl",
        ("\n".join(json.dumps(c, sort_keys=True) for c in commands) + "\n").encode(),
    )
    atomic_write(
        staging_dir / "commands.jsonl",
        ("\n".join(json.dumps(c, sort_keys=True) for c in commands) + "\n").encode(),
    )


def validate_snapshot(snapshot_dir: Path) -> dict:
    receipt = json.loads((snapshot_dir / "receipt.json").read_text())
    mismatches = []
    for rel, meta in receipt["artifacts"].items():
        path = snapshot_dir / rel
        if not path.is_file():
            mismatches.append({"path": rel, "issue": "MISSING"})
            continue
        data = path.read_bytes()
        actual_sha = lib.sha_bytes(data)
        if actual_sha != meta["sha256"]:
            mismatches.append({"path": rel, "issue": "ARTIFACT_HASH_MISMATCH"})
    if mismatches:
        raise ValueError(f"ARTIFACT_HASH_MISMATCH: {mismatches}")
    return {"receipt": receipt, "mismatches": mismatches}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--m1-dir", required=True, type=Path)
    parser.add_argument("--m2-dir", required=True, type=Path)
    args = parser.parse_args()

    result = run_extraction(args.m1_dir, args.m2_dir)
    print(json.dumps({k: (str(v) if isinstance(v, Path) else v) for k, v in result.items()}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
