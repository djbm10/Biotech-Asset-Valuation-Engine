"""Read-only integrity preflight for the sealed holdout package.

This validates the designated detached worktree and package hashes. It never invokes the evaluator.
Run it as the custodian before handing the package to a fresh evaluator.
"""

from __future__ import annotations

import argparse
import hashlib
import re
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

    expected_hashes = {
        "holdout_data.jsonl": re.search(r"Holdout data.*?([0-9a-f]{64})", manifest, re.S),
        "holdout_labels_private.csv": re.search(r"Private labels.*?([0-9a-f]{64})", manifest, re.S),
    }
    for name, match in expected_hashes.items():
        if not match:
            raise SystemExit(f"manifest missing hash for {name}")
        path = args.holdout_dir / name
        if not path.is_file():
            raise SystemExit(f"missing artifact: {path}")
        if sha256(path) != match.group(1):
            raise SystemExit(f"hash mismatch: {path}")

    command = "bve.cli.se_holdout_evaluate"
    if command not in manifest or "--holdout-data" not in manifest:
        raise SystemExit("manifest does not specify the case-level evaluator command")
    print("HOLDOUT_PREFLIGHT_PASS: hashes and worktree verified; lock labels before execution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
