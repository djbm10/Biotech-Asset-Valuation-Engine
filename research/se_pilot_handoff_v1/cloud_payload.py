"""Copy only replay inputs; stream hashes, dereference ontology, never copy credentials."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = Path("/home/djmann/se_runs/bd_cov_v1")
RUN_INPUTS = (
    "A_base",
    "corpus_A",
    "source_index_baseline.yaml",
    "source_index_full.yaml",
    "acquire_report.json",
)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(root: Path) -> dict:
    return {
        str(p.relative_to(root)): {"sha256": sha(p), "bytes": p.stat().st_size}
        for p in sorted(root.rglob("*"))
        if p.is_file() and p != root / "manifest.json"
    }


def verify(root: Path) -> None:
    manifest = json.loads((root / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        path = root / name
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError(f"unsafe manifest path: {name}")
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"escaping symlink: {name}")
        if not path.is_file() or path.stat().st_size != expected["bytes"]:
            raise ValueError(f"missing/size mismatch: {name}")
        if sha(path) != expected["sha256"]:
            raise ValueError(f"checksum mismatch: {name}")
    actual = set(inventory(root))
    if actual != set(manifest["files"]):
        raise ValueError("unexpected files in payload")
    print(f"Verified {len(actual)} files; source HEAD {manifest['code_head']}")


def environment(root: Path) -> None:
    """Fail closed on a different code revision, interpreter or installed dependency."""
    manifest = json.loads((root / "manifest.json").read_text())
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    if head != manifest["code_head"] or platform.python_version() != manifest["python"]:
        raise ValueError("code HEAD or Python does not match the migration manifest")
    for line in (root / "requirements.txt").read_text().splitlines():
        name, expected = line.split("==", 1)
        if importlib.metadata.version(name) != expected:
            raise ValueError(f"dependency mismatch: {name}")
    print("Code, Python and installed dependency versions match")


def prepare(destination: Path) -> None:
    dirty = subprocess.check_output(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            "src",
            "pyproject.toml",
            "research/se_bd_discovery_source_coverage_v1",
            "research/se_pilot_handoff_v1",
        ],
        cwd=REPO,
        text=True,
    ).strip()
    if dirty:
        raise ValueError("commit the engine and handoff files before preparing a pinned payload")
    # mkdir without exist_ok prevents accidentally overwriting an old migration.
    destination.mkdir(parents=True)
    for name in RUN_INPUTS:
        source, target = ROOT / name, destination / "runs" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, symlinks=False)
        else:
            shutil.copy2(source, target)
    shutil.copytree(REPO / "data/se/ontology", destination / "ontology", symlinks=False)
    pins = sorted(
        {
            f"{d.metadata['Name']}=={d.version}"
            for d in importlib.metadata.distributions()
            if d.metadata["Name"].lower() != "bve"
        }
    )
    (destination / "requirements.txt").write_text("\n".join(pins) + "\n")
    seal(destination)
    verify(destination)


def seal(destination: Path) -> None:
    """Write a transport manifest without modifying existing data or custody files."""
    if (destination / "manifest.json").exists():
        raise FileExistsError(destination / "manifest.json")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    manifest = {
        "code_head": head,
        "python": platform.python_version(),
        "original_root": str(ROOT),
        "files": inventory(destination),
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "verify", "seal", "environment"])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    {"prepare": prepare, "verify": verify, "seal": seal, "environment": environment}[args.action](
        args.directory
    )
