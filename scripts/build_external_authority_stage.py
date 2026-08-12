"""Builds the canonical Milestone 4 (external product authority capture)
stage output directory, per Section 18-20 of the governing spec.

Reads the already-computed, deterministic _m4_scratch/* ledgers (built by
build_authority_research_universe.py, run_tier_a_regulatory_adapter.py,
run_ctgov_modality_adapter.py, run_tier_bc_capture.py, and
merge_authority_evidence.py -- all pure/checkpointed transforms of
finalized Milestone 3 evidence plus resumable source captures) and packages
them into the canonical stage-output layout:

  artifacts/pipeline/pdcd1_rebase_v1/stages/04_external_product_authority/<snapshot_id>/
    manifest.json  receipt.json  commands.jsonl  logs/  input/
    subjects/  source/  assertions/  conflicts/  validation/  export/

Also verifies, before writing anything:
  * the freshly-downloaded+checksummed Milestone 3 prerequisite snapshot
    (prerequisite_validation/m3/) is the one all subjects are bound to;
  * every subject_id in the research universe originates from that M3
    snapshot's targeted/forensic review queues (no unapproved subject
    introduced);
  * every subject has reached a valid terminal completion state.

Does not create canonical candidates, adjudicate aliases, decide
ownership, build candidate chronology, assign benchmark labels, or invoke
any prediction/evaluation logic.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdcd1_external_authority_lib as lib  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "_m4_scratch"
STAGE_ROOT = ROOT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages" / "04_external_product_authority"
M3_PREREQ_DIR = STAGE_ROOT / "prerequisite_validation" / "m3"
MILESTONE = "PDCD1_BENCHMARK_REBASE_V1_MILESTONE_4_EXTERNAL_PRODUCT_AUTHORITY_CAPTURE"
MILESTONE3_SNAPSHOT_ID = "f5dd19d08deb59a75232d3bc"
M3_ARCHIVE_SHA256 = "889f18f8cda547ed12e484535116ed2cac710a08d617e958272b61bea58a89e8"


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def find_m3_extracted_root() -> Path:
    candidates = list((M3_PREREQ_DIR / "extracted").glob(f"{MILESTONE3_SNAPSHOT_ID}"))
    if not candidates:
        raise SystemExit("M3 prerequisite not extracted; run prerequisite validation first")
    return candidates[0]


def verify_prerequisite(m3_root: Path) -> dict:
    receipt = json.loads((m3_root / "receipt.json").read_text())
    mismatches = []
    for relpath, meta in receipt["artifacts"].items():
        p = m3_root / relpath
        data = p.read_bytes()
        import hashlib
        ok = len(data) == meta["byte_length"] and hashlib.sha256(data).hexdigest() == meta["sha256"]
        if not ok:
            mismatches.append(relpath)
    if mismatches:
        raise SystemExit(f"M3 receipt binding mismatches: {mismatches}")
    manifest = json.loads((m3_root / "manifest.json").read_text())
    if manifest.get("stage_status") != "FINALIZED":
        raise SystemExit("M3 prerequisite is not FINALIZED")
    return {"receipt_artifacts_verified": len(receipt["artifacts"]), "manifest": manifest}


def verify_subject_universe_subset(m3_root: Path, subjects: list[dict]) -> None:
    approved_keys = set()
    for fname in ("targeted_review_queue.jsonl", "forensic_review_queue.jsonl"):
        for row in load_jsonl(m3_root / "triage" / fname):
            approved_keys.add(row["unique_string_key"])
    unapproved = [s["subject_id"] for s in subjects if s["source_strings"][0] not in approved_keys]
    if unapproved:
        raise SystemExit(f"unapproved research subjects introduced: {unapproved[:5]} (+{len(unapproved)-5} more)" if len(unapproved) > 5 else f"unapproved research subjects introduced: {unapproved}")
    for s in subjects:
        if s["milestone3_evidence_bindings"]["milestone3_snapshot_id"] != MILESTONE3_SNAPSHOT_ID:
            raise SystemExit(f"subject {s['subject_id']} bound to wrong M3 snapshot")


def main() -> None:
    m3_root = find_m3_extracted_root()
    prereq_check = verify_prerequisite(m3_root)

    subjects = load_jsonl(SCRATCH / "authority_research_subject_ledger.jsonl")
    verify_subject_universe_subset(m3_root, subjects)

    questions = load_jsonl(SCRATCH / "research_question_ledger.jsonl")
    source_attempts = load_jsonl(SCRATCH / "source_attempt_ledger.jsonl")
    source_evidence = load_jsonl(SCRATCH / "source_evidence_ledger.jsonl")
    assertions = load_jsonl(SCRATCH / "normalized_assertion_ledger.jsonl")
    conflicts = load_jsonl(SCRATCH / "authority_conflict_ledger.jsonl")
    completion_states = load_jsonl(SCRATCH / "research_completion_state_ledger.jsonl")

    from collections import Counter
    state_counts = Counter(c["state"] for c in completion_states)
    non_terminal = {"RETRYABLE"}
    stuck = [c for c in completion_states if c["state"] in non_terminal]
    if stuck:
        raise SystemExit(f"{len(stuck)} subjects not in a terminal completion state")

    sorted_subject_ids = sorted(s["subject_id"] for s in subjects)
    assertion_schema_hash = lib.stable_hash(sorted(lib.ASSERTION_TYPES))
    canonical_evidence_manifest_hash = lib.stable_hash({
        "assertions": sorted(json.dumps(a, sort_keys=True) for a in assertions),
        "source_evidence": sorted(json.dumps(e, sort_keys=True) for e in source_evidence),
        "conflicts": sorted(json.dumps(c, sort_keys=True) for c in conflicts),
        "completion_states": sorted(json.dumps(c, sort_keys=True) for c in completion_states),
    })
    snapshot_id = lib.stable_hash({
        "milestone3_snapshot_id": MILESTONE3_SNAPSHOT_ID,
        "sorted_subject_ids": sorted_subject_ids,
        "research_schema_version": lib.RESEARCH_SCHEMA_VERSION,
        "source_authority_policy_hash": lib.SOURCE_AUTHORITY_POLICY_HASH,
        "assertion_schema_hash": assertion_schema_hash,
        "canonical_evidence_manifest_hash": canonical_evidence_manifest_hash,
    })[:24]

    out_dir = STAGE_ROOT / snapshot_id
    if out_dir.is_dir():
        shutil.rmtree(out_dir)
    for sub in ("logs", "input", "subjects", "source", "assertions", "conflicts", "validation", "export"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)

    def write_jsonl(path: Path, rows: list[dict]) -> None:
        with path.open("w") as f:
            for r in rows:
                f.write(json.dumps(r, sort_keys=True) + "\n")

    write_jsonl(out_dir / "subjects" / "authority_research_subject_ledger.jsonl", subjects)
    write_jsonl(out_dir / "subjects" / "research_question_ledger.jsonl", questions)
    write_jsonl(out_dir / "source" / "source_attempt_ledger.jsonl", source_attempts)
    write_jsonl(out_dir / "source" / "source_evidence_ledger.jsonl", source_evidence)
    write_jsonl(out_dir / "assertions" / "normalized_assertion_ledger.jsonl", assertions)
    write_jsonl(out_dir / "conflicts" / "authority_conflict_ledger.jsonl", conflicts)
    write_jsonl(out_dir / "validation" / "research_completion_state_ledger.jsonl", completion_states)

    (out_dir / "validation" / "completion_state_summary.json").write_text(
        json.dumps({"counts": dict(sorted(state_counts.items())), "total_subjects": len(subjects)}, sort_keys=True, indent=2)
    )

    (out_dir / "input" / "prerequisite_bindings.json").write_text(json.dumps({
        "milestone3_snapshot_id": MILESTONE3_SNAPSHOT_ID,
        "milestone3_archive_sha256": M3_ARCHIVE_SHA256,
        "milestone3_receipt_artifacts_verified": prereq_check["receipt_artifacts_verified"],
    }, sort_keys=True, indent=2))

    (out_dir / "logs" / "build.jsonl").write_text(
        json.dumps({
            "event": "external_authority_stage_build",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "subjects_processed": len(subjects),
        }, sort_keys=True) + "\n"
    )

    (out_dir / "commands.jsonl").write_text(
        json.dumps({"command": "build_external_authority_stage.main", "timestamp": datetime.now(timezone.utc).isoformat()}, sort_keys=True) + "\n"
    )

    manifest = {
        "milestone": MILESTONE,
        "lineage": "REPRODUCIBLE_BIOTECH_PIPELINE_REBASE_V1",
        "canonical_target": "PDCD1",
        "stage_status": "FINALIZED",
        "snapshot_id": snapshot_id,
        "milestone3_prerequisite": {
            "snapshot_id": MILESTONE3_SNAPSHOT_ID,
            "archive_sha256": M3_ARCHIVE_SHA256,
        },
        "research_schema_version": lib.RESEARCH_SCHEMA_VERSION,
        "assertion_schema_version": lib.ASSERTION_SCHEMA_VERSION,
        "source_authority_policy_hash": lib.SOURCE_AUTHORITY_POLICY_HASH,
        "assertion_schema_hash": assertion_schema_hash,
        "canonical_evidence_manifest_hash": canonical_evidence_manifest_hash,
        "checks": {
            "subject_count": len(subjects),
            "research_question_count": len(questions),
            "source_attempt_count": len(source_attempts),
            "source_evidence_count": len(source_evidence),
            "assertion_count": len(assertions),
            "conflict_count": len(conflicts),
            "completion_state_counts": dict(sorted(state_counts.items())),
        },
        "external_authority_capture_performed": True,
        "canonical_candidates_created": False,
        "aliases_adjudicated": False,
        "ownership_claims_created": False,
        "candidate_chronology_created": False,
        "benchmark_labels_created": False,
        "predictions_generated": False,
        "evaluation_performed": False,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2))

    import hashlib
    artifact_hashes = {}
    for p in sorted(out_dir.rglob("*")):
        if p.is_file() and p.name not in ("receipt.json",) and "logs" not in p.relative_to(out_dir).parts[:0]:
            rel = str(p.relative_to(out_dir))
            data = p.read_bytes()
            artifact_hashes[rel] = {"byte_length": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    receipt = {
        "milestone": MILESTONE,
        "lineage": "REPRODUCIBLE_BIOTECH_PIPELINE_REBASE_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": snapshot_id,
        "artifacts": artifact_hashes,
        "external_authority_capture_performed": True,
        "canonical_candidates_created": False,
        "aliases_adjudicated": False,
        "ownership_claims_created": False,
        "candidate_chronology_created": False,
        "benchmark_labels_created": False,
        "predictions_generated": False,
        "evaluation_performed": False,
    }
    (out_dir / "receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2))

    print(f"snapshot_id: {snapshot_id}")
    print(f"out_dir: {out_dir}")
    print("completion states:", dict(sorted(state_counts.items())))
    print("subjects:", len(subjects), "assertions:", len(assertions), "conflicts:", len(conflicts))


if __name__ == "__main__":
    main()
