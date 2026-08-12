"""Section 21 resumable run driver for Milestone 4 external authority
capture.

Orchestrates the existing resumable/checkpointed steps in order:
  1. build_authority_research_universe.py  (pure, deterministic)
  2. run_ctgov_modality_adapter.py         (pure, reads M2/M3 registry data)
  3. run_tier_a_regulatory_adapter.py      (network, per-subject checkpoint)
  4. run_tier_bc_capture.py                (network, per-(subject,source) checkpoint)
  5. merge_authority_evidence.py           (pure, deterministic)
  6. build_external_authority_stage.py     (pure, deterministic; computes
     the Section 19 snapshot_id and writes the canonical Section 18 tree)

Each unit-producing step (3, 4) is bound as: subject ID, source target,
query/input, retrieval result, response hash, normalized assertions, and a
unit receipt -- via each adapter's own per-unit checkpoint file, which is
reused unchanged on resume (no re-fetch of a valid immutable capture).

Before doing any work, computes what the Section 19 snapshot_id *would be*
given the current state of the _m4_scratch ledgers and checks whether a
stage-output directory already exists for that exact snapshot_id with
stage_status "FINALIZED". If so, this run is a no-op and returns
ALREADY_FINALIZED with all-zero counts, per Section 21.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdcd1_external_authority_lib as lib  # noqa: E402
import build_external_authority_stage as stage_builder  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
STAGE_ROOT = ROOT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages" / "04_external_product_authority"

ZERO_COUNTS = {
    "prerequisite_downloads": 0,
    "external_source_requests": 0,
    "extraction": 0,
    "assertions_generated": 0,
    "adjudications": 0,
    "predictions": 0,
    "scoring": 0,
    "writes": 0,
}


def compute_prospective_snapshot_id() -> str | None:
    """Recomputes what build_external_authority_stage.py would produce as
    snapshot_id from the *current* _m4_scratch ledgers, without writing
    anything. Returns None if the scratch ledgers are not yet complete
    enough to compute it (e.g. first-ever run)."""
    scratch = ROOT / "_m4_scratch"
    subjects_path = scratch / "authority_research_subject_ledger.jsonl"
    if not subjects_path.is_file():
        return None
    subjects = stage_builder.load_jsonl(subjects_path)
    assertions = stage_builder.load_jsonl(scratch / "normalized_assertion_ledger.jsonl")
    source_evidence = stage_builder.load_jsonl(scratch / "source_evidence_ledger.jsonl")
    conflicts = stage_builder.load_jsonl(scratch / "authority_conflict_ledger.jsonl")
    completion_states = stage_builder.load_jsonl(scratch / "research_completion_state_ledger.jsonl")
    if not (subjects and assertions and completion_states):
        return None

    sorted_subject_ids = sorted(s["subject_id"] for s in subjects)
    assertion_schema_hash = lib.stable_hash(sorted(lib.ASSERTION_TYPES))
    canonical_evidence_manifest_hash = lib.stable_hash({
        "assertions": sorted(json.dumps(a, sort_keys=True) for a in assertions),
        "source_evidence": sorted(json.dumps(e, sort_keys=True) for e in source_evidence),
        "conflicts": sorted(json.dumps(c, sort_keys=True) for c in conflicts),
        "completion_states": sorted(json.dumps(c, sort_keys=True) for c in completion_states),
    })
    return lib.stable_hash({
        "milestone3_snapshot_id": stage_builder.MILESTONE3_SNAPSHOT_ID,
        "sorted_subject_ids": sorted_subject_ids,
        "research_schema_version": lib.RESEARCH_SCHEMA_VERSION,
        "source_authority_policy_hash": lib.SOURCE_AUTHORITY_POLICY_HASH,
        "assertion_schema_hash": assertion_schema_hash,
        "canonical_evidence_manifest_hash": canonical_evidence_manifest_hash,
    })[:24]


def already_finalized(snapshot_id: str) -> bool:
    manifest_path = STAGE_ROOT / snapshot_id / "manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError:
        return False
    return manifest.get("stage_status") == "FINALIZED" and manifest.get("snapshot_id") == snapshot_id


def run_step(argv: list[str]) -> None:
    print(f"$ {' '.join(argv)}", file=sys.stderr)
    subprocess.run(argv, cwd=ROOT, check=True)


def main() -> None:
    prospective = compute_prospective_snapshot_id()
    if prospective and already_finalized(prospective):
        result = {
            "status": "ALREADY_FINALIZED",
            "snapshot_id": prospective,
            "counts": ZERO_COUNTS,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    py = sys.executable
    run_step([py, str(SCRIPTS / "build_authority_research_universe.py")])
    run_step([py, str(SCRIPTS / "run_ctgov_modality_adapter.py")])
    run_step([py, str(SCRIPTS / "run_tier_a_regulatory_adapter.py")])
    run_step([py, str(SCRIPTS / "run_tier_bc_capture.py")])
    run_step([py, str(SCRIPTS / "merge_authority_evidence.py")])
    run_step([py, str(SCRIPTS / "build_external_authority_stage.py")])

    final_snapshot_id = compute_prospective_snapshot_id()
    result = {
        "status": "COMPLETED",
        "snapshot_id": final_snapshot_id,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
