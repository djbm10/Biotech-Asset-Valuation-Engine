"""bve-sync-data — sync GitHub Actions data-branch artifacts locally."""
from __future__ import annotations

import argparse
import subprocess
import tarfile
import tempfile
from pathlib import Path


DEFAULT_PATHS = [
    "outputs/intelligence/evidence_ledger.jsonl",
    "outputs/intelligence/ledger_manifest.json",
]


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _repo_root() -> Path:
    result = _run(["git", "rev-parse", "--show-toplevel"], cwd=Path.cwd())
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "not inside a git repository")
    return Path(result.stdout.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-sync-data",
        description=(
            "Fetch the GitHub Actions data branch and extract ledger files into "
            "the local workspace without switching branches."
        ),
    )
    parser.add_argument("--remote", default="origin", help="Git remote name")
    parser.add_argument("--branch", default="data", help="Remote data branch")
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        help="Path to extract from the data branch. May be repeated.",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Use the existing remote ref without running git fetch.",
    )
    args = parser.parse_args(argv)

    try:
        root = _repo_root()
        ref = f"{args.remote}/{args.branch}"
        paths = args.paths or DEFAULT_PATHS

        if not args.skip_fetch:
            fetch = _run(["git", "fetch", args.remote, args.branch], cwd=root)
            if fetch.returncode != 0:
                print(fetch.stderr.strip() or "git fetch failed")
                return fetch.returncode

        with tempfile.TemporaryDirectory(prefix="bve-sync-data-") as tmp:
            tmp_path = Path(tmp)
            archive_cmd = ["git", "archive", ref, *paths]
            archive = subprocess.Popen(
                archive_cmd,
                cwd=str(root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert archive.stdout is not None
            try:
                with tarfile.open(fileobj=archive.stdout, mode="r|") as tf:
                    tf.extractall(tmp_path)
            except tarfile.TarError as exc:
                _out, err = archive.communicate()
                print(err.decode().strip() or f"git archive failed: {exc}")
                return archive.returncode or 1

            _out, err = archive.communicate()
            if archive.returncode != 0:
                print(err.decode().strip() or "git archive failed")
                return archive.returncode

            copied = 0
            for rel in paths:
                src = tmp_path / rel
                dst = root / rel
                if not src.exists():
                    print(f"missing in {ref}: {rel}")
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())
                copied += 1
                print(f"synced {rel}")

        print(f"bve-sync-data: synced {copied}/{len(paths)} file(s) from {ref}")
        return 0
    except Exception as exc:
        print(f"bve-sync-data: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
