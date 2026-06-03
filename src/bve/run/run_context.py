"""
Run context capture (Block 2J).

Captures the full reproducibility envelope for a pipeline run:
  - Git commit hash of the code
  - Pipeline model version strings (ALL_VERSIONS)
  - SHA-256 hashes of key input files (targets, acquirers, overrides, ledger)
  - Run parameters (as_of_date, score_mode, lookback_days, ingest_live)
  - Timestamps (started_at, completed_at)
  - Python version

The RunContext is written as ``run_context.json`` inside every output directory
so that any downstream user can determine exactly what was run and whether they
can reproduce the result.

Usage::

    from bve.run.run_context import capture_run_context, RunContext

    ctx = capture_run_context(
        as_of_date="2026-06-02",
        score_mode="provisional",
        lookback_days=3,
        ingest_live=True,
        input_files={
            "targets": "research/universe/targets.yaml",
            "acquirers": "research/universe/acquirers.yaml",
            "ledger": "outputs/intelligence/evidence_ledger.jsonl",
        },
    )
    ctx.save("outputs/daily/2026-06-02/run_context.json")
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class RunContext:
    """Immutable snapshot of a pipeline run's reproducibility envelope."""

    # Timestamps
    started_at: str          # ISO datetime (UTC)
    completed_at: Optional[str] = None

    # Code provenance
    git_commit: str = "unknown"
    git_dirty: bool = False  # True if there were uncommitted changes

    # Model versions
    pipeline_versions: dict[str, str] = field(default_factory=dict)

    # Run parameters
    as_of_date: str = ""
    score_mode: str = "provisional"
    lookback_days: int = 3
    ingest_live: bool = False

    # Input file hashes (filename → sha256[:16])
    input_hashes: dict[str, str] = field(default_factory=dict)

    # Python runtime
    python_version: str = ""

    # Schema version for this file
    run_context_version: str = "1"

    # ------------------------------------------------------------------

    def mark_completed(self) -> "RunContext":
        """Return a new RunContext with completed_at stamped to now."""
        import dataclasses
        return dataclasses.replace(self, completed_at=datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "RunContext":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)


def capture_run_context(
    as_of_date: str,
    score_mode: str = "provisional",
    lookback_days: int = 3,
    ingest_live: bool = False,
    input_files: Optional[dict[str, str | Path]] = None,
) -> RunContext:
    """
    Build a RunContext, hashing input files and reading git state.

    Parameters
    ----------
    input_files:
        Mapping of logical name → path (e.g. ``{"targets": "research/universe/targets.yaml"}``).
        Missing files are recorded as ``"missing"``.
    """
    from bve.ingestion.model_versions import ALL_VERSIONS

    git_commit, git_dirty = _get_git_state()

    input_hashes: dict[str, str] = {}
    for name, file_path in (input_files or {}).items():
        input_hashes[name] = _file_hash_short(file_path)

    return RunContext(
        started_at=datetime.now(timezone.utc).isoformat(),
        git_commit=git_commit,
        git_dirty=git_dirty,
        pipeline_versions=dict(ALL_VERSIONS),
        as_of_date=as_of_date,
        score_mode=score_mode,
        lookback_days=lookback_days,
        ingest_live=ingest_live,
        input_hashes=input_hashes,
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _get_git_state() -> tuple[str, bool]:
    """Return (commit_hash, is_dirty). Returns ("unknown", False) if git unavailable."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        dirty_output = subprocess.check_output(
            ["git", "status", "--porcelain"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return commit, bool(dirty_output)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown", False


def _file_hash_short(path: str | Path) -> str:
    """First 16 hex chars of SHA-256, or 'missing' if file not found."""
    p = Path(path)
    if not p.exists():
        return "missing"
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    except OSError:
        return "error"


def compare_contexts(ctx_a: RunContext, ctx_b: RunContext) -> dict[str, list]:
    """
    Compare two RunContexts and return a dict of differences.

    Returns
    -------
    {"changed": [...], "same": [...]}
    """
    changed: list[str] = []
    same: list[str] = []

    checks = [
        ("git_commit", ctx_a.git_commit, ctx_b.git_commit),
        ("as_of_date", ctx_a.as_of_date, ctx_b.as_of_date),
        ("score_mode", ctx_a.score_mode, ctx_b.score_mode),
        ("lookback_days", ctx_a.lookback_days, ctx_b.lookback_days),
        ("ingest_live", ctx_a.ingest_live, ctx_b.ingest_live),
    ]
    for name, a, b in checks:
        (changed if a != b else same).append(name)

    # Pipeline versions
    for k in set(ctx_a.pipeline_versions) | set(ctx_b.pipeline_versions):
        a_ver = ctx_a.pipeline_versions.get(k, "missing")
        b_ver = ctx_b.pipeline_versions.get(k, "missing")
        label = f"pipeline_versions.{k}"
        (changed if a_ver != b_ver else same).append(label)

    # Input hashes
    for k in set(ctx_a.input_hashes) | set(ctx_b.input_hashes):
        a_h = ctx_a.input_hashes.get(k, "missing")
        b_h = ctx_b.input_hashes.get(k, "missing")
        label = f"input_hashes.{k}"
        (changed if a_h != b_h else same).append(label)

    return {"changed": changed, "same": same}
