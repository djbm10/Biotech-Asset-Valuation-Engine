"""Build Milestone 6 frozen-row identity mapping artifacts from frozen M1-M5 inputs."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pdcd1_row_identity_mapping_lib as lib

ROOT = Path(__file__).resolve().parents[1]
STAGE_ROOT = ROOT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages" / "06_frozen_row_identity_mapping"
M1_DIR = ROOT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages" / "01_population_capture" / lib.M1_SNAPSHOT_ID
M2_DIR = ROOT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages" / "02_registry_history_capture" / lib.M2_SNAPSHOT_ID
M3_DIR = ROOT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages" / "03_candidate_bearing_evidence_triage" / lib.M3_SNAPSHOT_ID
M4_DIR = ROOT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages" / "04_external_product_authority" / lib.M4_SNAPSHOT_ID
M5_DIR = ROOT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages" / "05_candidate_identity_adjudication" / lib.M5_SNAPSHOT_ID


def load_inputs() -> dict[str, list[dict]]:
    inputs = {
        "aliases": lib.load_jsonl(M5_DIR / "aliases" / "alias_development_code_ledger.jsonl"),
        "canonical_candidates": lib.load_jsonl(M5_DIR / "candidates" / "canonical_candidate_ledger.jsonl"),
        "conflict_resolution": lib.load_jsonl(M5_DIR / "conflicts" / "conflict_resolution_ledger.jsonl"),
        "frozen_rows": lib.load_jsonl(M3_DIR / "extracted" / "frozen_row_evidence_bindings.jsonl"),
        "parsed_components": lib.load_jsonl(M3_DIR / "normalized" / "parsed_component_ledger.jsonl"),
        "presentation_variants": lib.load_jsonl(M3_DIR / "normalized" / "presentation_variant_ledger.jsonl"),
        "rejected_aliases": lib.load_jsonl(M5_DIR / "aliases" / "rejected_alias_ledger.jsonl"),
        "subject_mapping": lib.load_jsonl(M5_DIR / "subjects" / "subject_candidate_mapping_ledger.jsonl"),
        "subjects": lib.load_jsonl(M4_DIR / "subjects" / "authority_research_subject_ledger.jsonl"),
        "unique_strings": lib.load_jsonl(M3_DIR / "normalized" / "unique_exact_string_ledger.jsonl"),
    }
    if len(inputs["frozen_rows"]) != 300:
        raise SystemExit(f"expected 300 frozen rows, found {len(inputs['frozen_rows'])}")
    if len(inputs["canonical_candidates"]) != 224:
        raise SystemExit(f"expected 224 M5 canonical candidates, found {len(inputs['canonical_candidates'])}")
    if len(inputs["subject_mapping"]) != 554:
        raise SystemExit(f"expected 554 M5 subject mappings, found {len(inputs['subject_mapping'])}")
    return inputs


def prospective_snapshot_id(build_a: dict, build_b: dict, reconciliation: list[dict]) -> str:
    return lib.stable_hash(
        {
            "build_a_row_outcome": build_a["row_outcome"],
            "build_b_row_outcome": build_b["row_outcome"],
            "m3_snapshot_id": lib.M3_SNAPSHOT_ID,
            "m4_snapshot_id": lib.M4_SNAPSHOT_ID,
            "m5_snapshot_id": lib.M5_SNAPSHOT_ID,
            "milestone": lib.MILESTONE,
            "reconciliation": reconciliation,
            "schema_version": lib.SCHEMA_VERSION,
        }
    )[:24]


def receipt_for(out_dir: Path) -> dict:
    artifacts = {}
    for path in sorted(out_dir.rglob("*")):
        if not path.is_file() or path.name == "receipt.json":
            continue
        rel = str(path.relative_to(out_dir))
        data = path.read_bytes()
        artifacts[rel] = {"byte_length": len(data), "sha256": lib.hashlib.sha256(data).hexdigest()}
    return {
        "artifacts": artifacts,
        "benchmark_labels_created": False,
        "candidate_chronology_created": False,
        "canonical_candidates_created": False,
        "evaluation_performed": False,
        "external_authority_capture_performed": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lineage": lib.LINEAGE,
        "milestone": lib.MILESTONE,
        "ownership_claims_created": False,
        "predictions_generated": False,
        "row_identity_mapping_performed": True,
        "snapshot_id": out_dir.name,
    }


def write_ledgers(base: Path, build: dict) -> None:
    lib.write_jsonl(base / "rows" / "row_outcome_ledger.jsonl", build["row_outcome"])
    lib.write_jsonl(base / "rows" / "row_candidate_mapping_ledger.jsonl", build["row_candidate_mapping"])
    lib.write_jsonl(base / "rows" / "combination_component_ledger.jsonl", build["combination_component"])
    lib.write_jsonl(base / "rows" / "unresolved_row_ledger.jsonl", build["unresolved_row"])
    lib.write_jsonl(base / "rows" / "row_evidence_binding_ledger.jsonl", build["row_evidence_binding"])
    lib.write_jsonl(base / "boundaries" / "row_identity_boundary_ledger.jsonl", build["row_identity_boundary"])


def main() -> None:
    inputs = load_inputs()
    build_a = lib.map_rows("build_a", inputs)
    build_b_inputs = {key: list(reversed(value)) for key, value in inputs.items()}
    build_b = lib.map_rows("build_b", build_b_inputs)
    reconciliation, agreement = lib.compare_builds(build_a, build_b)
    snapshot_id = prospective_snapshot_id(build_a, build_b, reconciliation)
    out_dir = STAGE_ROOT / snapshot_id
    if out_dir.is_dir():
        shutil.rmtree(out_dir)
    for subdir in ("input", "rows", "boundaries", "validation", "reproducibility", "logs", "export"):
        (out_dir / subdir).mkdir(parents=True, exist_ok=True)
    for subdir in ("rows", "boundaries", "validation"):
        (out_dir / "reproducibility" / "build_b" / subdir).mkdir(parents=True, exist_ok=True)

    prereq = {
        "frozen_input_only": True,
        "milestone1": {"manifest_sha256": lib.file_sha(M1_DIR / "manifest.json"), "snapshot_id": lib.M1_SNAPSHOT_ID},
        "milestone2": {"manifest_sha256": lib.file_sha(M2_DIR / "manifest.json"), "snapshot_id": lib.M2_SNAPSHOT_ID},
        "milestone3": {"manifest_sha256": lib.file_sha(M3_DIR / "manifest.json"), "snapshot_id": lib.M3_SNAPSHOT_ID},
        "milestone4": {"manifest_sha256": lib.file_sha(M4_DIR / "manifest.json"), "snapshot_id": lib.M4_SNAPSHOT_ID},
        "milestone5": {"manifest_sha256": lib.file_sha(M5_DIR / "manifest.json"), "snapshot_id": lib.M5_SNAPSHOT_ID},
        "new_external_research_performed": False,
    }
    lib.write_json(out_dir / "input" / "prerequisite_bindings.json", prereq)

    write_ledgers(out_dir, build_a)
    write_ledgers(out_dir / "reproducibility" / "build_b", build_b)
    lib.write_jsonl(out_dir / "reproducibility" / "reconciliation_ledger.jsonl", reconciliation)

    comparison = [
        "# Milestone 6 - Build A vs Build B Frozen Row Identity Mapping Comparison",
        "",
        f"Build A rows: `{len(build_a['row_outcome'])}`",
        f"Build B rows: `{len(build_b['row_outcome'])}`",
        f"Row outcome agreement: `{agreement['agreements']}/{agreement['total_rows']}` ({agreement['agreement_rate']:.1%}).",
        f"Disagreements: `{agreement['disagreements']}`, enumerated in `reconciliation_ledger.jsonl`.",
        "",
        "Both builds read the same frozen M1-M5 inputs. Build B reverses input ordering and writes its own complete ledger set; Build A remains the published row mapping.",
    ]
    (out_dir / "reproducibility" / "BUILD_A_VS_BUILD_B_COMPARISON.md").write_text("\n".join(comparison) + "\n")

    summary = {
        "build_a_vs_build_b_agreement": agreement,
        "combination_row_count": build_a["summary"]["combination_row_count"],
        "escape_hatch_count": build_a["summary"]["escape_hatch_count"],
        "outcome_counts": build_a["summary"]["outcome_counts"],
        "schema_version": lib.SCHEMA_VERSION,
        "total_rows": build_a["summary"]["total_rows"],
    }
    lib.write_json(out_dir / "validation" / "row_identity_mapping_summary.json", summary)
    manifest = {
        "benchmark_labels_created": False,
        "candidate_chronology_created": False,
        "canonical_candidates_created": False,
        "canonical_target": "PDCD1",
        "checks": summary,
        "evaluation_performed": False,
        "external_authority_capture_performed": False,
        "lineage": lib.LINEAGE,
        "milestone": lib.MILESTONE,
        "milestone_prerequisites": {
            "milestone1_snapshot_id": lib.M1_SNAPSHOT_ID,
            "milestone2_snapshot_id": lib.M2_SNAPSHOT_ID,
            "milestone3_snapshot_id": lib.M3_SNAPSHOT_ID,
            "milestone4_snapshot_id": lib.M4_SNAPSHOT_ID,
            "milestone5_snapshot_id": lib.M5_SNAPSHOT_ID,
        },
        "ownership_claims_created": False,
        "predictions_generated": False,
        "row_identity_mapping_performed": True,
        "row_identity_mapping_schema_version": lib.SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "stage_status": "FINALIZED",
    }
    lib.write_json(out_dir / "manifest.json", manifest)
    (out_dir / "commands.jsonl").write_text(
        json.dumps(
            {
                "command": "build_row_identity_mapping_stage.main",
                "input_m3_snapshot_id": lib.M3_SNAPSHOT_ID,
                "input_m4_snapshot_id": lib.M4_SNAPSHOT_ID,
                "input_m5_snapshot_id": lib.M5_SNAPSHOT_ID,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            sort_keys=True,
        )
        + "\n"
    )
    (out_dir / "logs" / "build.jsonl").write_text(
        json.dumps(
            {
                "event": "row_identity_mapping_stage_build",
                "frozen_rows_processed": len(build_a["row_outcome"]),
                "snapshot_id": snapshot_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            sort_keys=True,
        )
        + "\n"
    )
    lib.write_json(out_dir / "receipt.json", receipt_for(out_dir))
    print(json.dumps({"snapshot_id": snapshot_id, "status": "COMPLETED", "summary": summary}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
