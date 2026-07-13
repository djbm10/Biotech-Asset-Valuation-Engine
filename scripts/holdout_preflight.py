"""Read-only integrity preflight for the sealed holdout package.

This validates the designated detached worktree and package hashes. It never invokes the evaluator.
Run it as the custodian before handing the package to a fresh evaluator.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--holdout-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = args.manifest.read_text()
    commit_match = re.search(r"Frozen commit: `([0-9a-f]{40})`", manifest)
    if not commit_match:
        raise SystemExit("manifest missing full frozen commit")
    observed_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=args.worktree, check=True, capture_output=True, text=True
    ).stdout.strip()
    if observed_commit != commit_match.group(1):
        raise SystemExit(f"commit mismatch: {observed_commit} != {commit_match.group(1)}")
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=args.worktree, check=True, capture_output=True, text=True
    ).stdout
    if status:
        raise SystemExit(f"worktree is dirty:\n{status}")

    data_match = re.search(r"Holdout data.*?([0-9a-f]{64})", manifest, re.S)
    label_match = re.search(r"Private labels.*?([0-9a-f]{64})", manifest, re.S)
    if not data_match or not label_match:
        raise SystemExit("manifest is missing a holdout hash")
    data_path = args.holdout_dir / "holdout_data.jsonl"
    if not data_path.is_file() or sha256(data_path) != data_match.group(1):
        raise SystemExit("holdout data hash mismatch")

    # The label file must remain unreadable to the frozen process. The custodian preflight may
    # temporarily unlock it to perform direct digest verification, then always re-seals mode 000
    # before returning. The frozen evaluator is never started by this script.
    label_path = args.holdout_dir / "holdout_labels_private.csv"
    sidecar = args.holdout_dir / "holdout_labels_private.csv.sha256"
    if not label_path.is_file() or not sidecar.is_file():
        raise SystemExit("missing sealed label artifact or digest sidecar")
    if sidecar.read_text().split()[0] != label_match.group(1):
        raise SystemExit("sealed label digest mismatch")
    try:
        os.chmod(label_path, 0o600)
        if sha256(label_path) != label_match.group(1):
            raise SystemExit("direct private-label hash mismatch")
    finally:
        os.chmod(label_path, 0)
    if stat.S_IMODE(label_path.stat().st_mode) != 0:
        raise SystemExit("private labels could not be re-sealed mode 000")

    bundle_match = re.search(
        r"Final sealed bundle: `([^`]+)`.*?SHA-256: `([0-9a-f]{64})`", manifest, re.S
    )
    if not bundle_match:
        raise SystemExit("manifest missing final bundle path or hash")
    bundle_path = Path(bundle_match.group(1))
    if not bundle_path.is_file() or sha256(bundle_path) != bundle_match.group(2):
        raise SystemExit("final bundle hash mismatch")

    command = "bve.cli.se_holdout_evaluate"
    required_command_parts = (command, "--problem", "--holdout-data", "--output")
    if any(part not in manifest for part in required_command_parts):
        raise SystemExit("manifest does not specify the case-level evaluator command")
    print("HOLDOUT_PREFLIGHT_PASS: sealed hashes, mode 000 labels, command, and worktree verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
