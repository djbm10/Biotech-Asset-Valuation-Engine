"""Idempotent Milestone 5 candidate-identity adjudication driver."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import build_candidate_identity_stage as builder

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
STAGE_ROOT = builder.STAGE_ROOT

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
    try:
        subjects, assertions, conflicts = builder.load_inputs()
        build_a = builder.lib.adjudicate_build(
            build_name="build_a",
            subjects=subjects,
            assertions=assertions,
            conflicts=conflicts,
            conservative_conflicts=True,
        )
        build_b = builder.lib.adjudicate_build(
            build_name="build_b",
            subjects=list(reversed(subjects)),
            assertions=list(reversed(assertions)),
            conflicts=list(reversed(conflicts)),
            conservative_conflicts=False,
        )
        reconciliation, _ = builder.lib.compare_builds(build_a, build_b)
        return builder.prospective_snapshot_id(build_a, build_b, reconciliation)
    except Exception:
        return None


def already_finalized(snapshot_id: str) -> bool:
    manifest_path = STAGE_ROOT / snapshot_id / "manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError:
        return False
    return manifest.get("stage_status") == "FINALIZED" and manifest.get("snapshot_id") == snapshot_id


def main() -> None:
    prospective = compute_prospective_snapshot_id()
    if prospective and already_finalized(prospective):
        print(
            json.dumps(
                {
                    "status": "ALREADY_FINALIZED",
                    "snapshot_id": prospective,
                    "counts": ZERO_COUNTS,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    subprocess.run([sys.executable, str(SCRIPTS / "build_candidate_identity_stage.py")], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
