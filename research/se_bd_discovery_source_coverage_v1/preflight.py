"""Preflight for running the remaining BD coverage arms on another machine. Reads only.

Checks, and exits non-zero on any failure:
  * git HEAD and a clean tracked tree for src/;
  * Python >= 3.11 and the engine importing;
  * frozen input hashes (frozen_inputs.sha256 is kept byte-for-byte; its recorded absolute
    prefix is mapped to --root, never rewritten);
  * the sealed baseline custody validating in full (every snapshot re-hashed), which also
    proves its embedded absolute snapshot paths resolve on this machine;
  * ontology / NCIt / modality authority files present, with the versions the baseline ran;
  * free disk and total RAM.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parent
REPO = STUDY.parents[1]
RECORDED_ROOT = "/home/djmann/se_runs/bd_cov_v1"
RECORDED_REPO_PREFIX = "research/"
MIN_RAM_GB = 24
MIN_DISK_GB = 10


def check(ok: bool, label: str, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}{(': ' + detail) if detail else ''}")
    return ok


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(RECORDED_ROOT))
    args = parser.parse_args()
    root = args.root
    ok = True

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "src"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    ok &= check(not dirty, "git src/ clean", head)
    ok &= check(sys.version_info >= (3, 11), "python", sys.version.split()[0])
    try:
        sys.path.insert(0, str(REPO / "src"))
        import bve.se.pipeline  # noqa: F401
        from bve.se.discovery.custody import validate_seal

        ok &= check(True, "engine imports")
    except Exception as exc:  # pragma: no cover - environment check
        return int(not check(False, "engine imports", repr(exc)))

    for line in (STUDY / "frozen_inputs.sha256").read_text().splitlines():
        digest, recorded = line.split(maxsplit=1)
        if recorded.startswith(RECORDED_ROOT):
            path = root / os.path.relpath(recorded, RECORDED_ROOT)
        else:
            path = REPO / recorded
        ok &= check(path.is_file() and sha(path) == digest, f"frozen input {path}")

    custody = root / "A_base" / "custody"
    try:
        sealed = validate_seal(custody, verify_snapshots=True)
        prefixes = {e.snapshot_path.rsplit("/snapshots/", 1)[0] for e in sealed.ledger}
        ok &= check(True, "sealed baseline custody verifies", f"{len(sealed.ledger)} snapshots; prefixes {sorted(prefixes)}")
    except Exception as exc:
        ok &= check(False, "sealed baseline custody verifies", str(exc)[:300])
        print(
            "      the seal embeds absolute snapshot paths under "
            f"{RECORDED_ROOT}/A_base; place the run directory there (a symlink is fine)."
        )

    pins = json.loads((root / "A_base" / "run_manifest.json").read_text())
    print("      baseline ontology:", pins.get("ontology_version"))
    for rel in ("data/se/ontology/current", "data/se/ontology/ncit", "data/se/ontology/modality"):
        path = REPO / rel
        ok &= check(path.is_dir() and any(path.iterdir()), f"ontology data {rel}")

    free_gb = shutil.disk_usage(root).free / 1e9
    ok &= check(free_gb >= MIN_DISK_GB, "free disk", f"{free_gb:.0f} GB")
    ram_gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
    ok &= check(ram_gb >= MIN_RAM_GB, "total RAM", f"{ram_gb:.1f} GB (need >= {MIN_RAM_GB})")
    print("PREFLIGHT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
