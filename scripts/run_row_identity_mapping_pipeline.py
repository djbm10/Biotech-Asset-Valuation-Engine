"""Idempotent Milestone 6 frozen-row identity mapping driver."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import build_row_identity_mapping_stage as builder

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
STAGE_ROOT = builder.STAGE_ROOT
ZERO_COUNTS = {
    "adjudications": 0,
    "assertions_generated": 0,
    "external_source_requests": 0,
    "extraction": 0,
    "predictions": 0,
    "prerequisite_downloads": 0,
    "scoring": 0,
    "writes": 0,
}


def compute_prospective_snapshot_id() -> str | None:
    try:
        inputs = builder.load_inputs()
        build_a = builder.lib.map_rows("build_a", inputs)
        build_b_inputs = {key: list(reversed(value)) for key, value in inputs.items()}
        build_b = builder.lib.map_rows("build_b", build_b_inputs)
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
                {"counts": ZERO_COUNTS, "snapshot_id": prospective, "status": "ALREADY_FINALIZED"},
                indent=2,
                sort_keys=True,
            )
        )
        return
    subprocess.run([sys.executable, str(SCRIPTS / "build_row_identity_mapping_stage.py")], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
