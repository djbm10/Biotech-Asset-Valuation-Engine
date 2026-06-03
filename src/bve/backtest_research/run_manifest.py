"""
run_manifest — generate run_manifest.json for every backtest output.

The manifest records everything needed to reproduce a backtest run:
  - git commit (HEAD SHA)
  - model_config_hash  (SHA256 of config.yaml)
  - feature_schema_hash (SHA256 of FeatureRow field names)
  - scoring_engine_hash (SHA256 of AcquirerPairScorer source file)
  - pair_scorer_hash    (SHA256 of WEIGHTS + INTERCEPT constants)
  - seed_file_hash      (SHA256 of deal_seed_vrtx_regn.csv)
  - python_version
  - package_version     (bve package version from importlib.metadata)
  - run_timestamp       (UTC ISO)
  - cli_args            (raw argv)
  - include_unverified_deals
  - score_mode
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _sha256_file(path: "str | Path") -> Optional[str]:
    """Return hex SHA256 of a file, or None if file not found."""
    p = Path(path)
    if not p.exists():
        return None
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _git_dirty() -> bool:
    """Return True if working tree has uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def _package_version() -> str:
    try:
        from importlib.metadata import version
        return version("bve")
    except Exception:
        return "unknown"


def _feature_schema_hash() -> str:
    """Hash the field names of FeatureRow to detect schema changes."""
    try:
        from bve.backtest_research.feature_store import FeatureRow
        import dataclasses
        field_names = "|".join(f.name for f in dataclasses.fields(FeatureRow))
        return _sha256_str(field_names)
    except Exception:
        return "unknown"


def _scoring_engine_hash() -> str:
    """Hash the AcquirerPairScorer source file."""
    try:
        import bve.intelligence.acquirer_pair_scorer as _mod
        src_path = Path(_mod.__file__)
        return _sha256_file(src_path) or "unknown"
    except Exception:
        return "unknown"


def _pair_scorer_weights_hash() -> str:
    """Hash the WEIGHTS dict + INTERCEPT to detect any weight changes."""
    try:
        from bve.intelligence.acquirer_pair_scorer import WEIGHTS, INTERCEPT
        payload = json.dumps({"intercept": INTERCEPT, "weights": WEIGHTS}, sort_keys=True)
        return _sha256_str(payload)
    except Exception:
        return "unknown"


def build_manifest(
    config_path: Optional["str | Path"],
    seed_csv_path: Optional["str | Path"],
    cli_args: Optional[list[str]],
    include_unverified_deals: bool,
    score_mode: str,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Build the run manifest dict.  Does not write to disk.
    """
    commit = _git_commit()
    dirty = _git_dirty()

    manifest: dict[str, Any] = {
        "git_commit": commit,
        "git_dirty": dirty,
        "git_commit_note": (
            "WARNING: working tree has uncommitted changes — run may not be reproducible"
            if dirty else "clean"
        ),
        "model_config_hash": _sha256_file(config_path) if config_path else None,
        "feature_schema_hash": _feature_schema_hash(),
        "scoring_engine_hash": _scoring_engine_hash(),
        "pair_scorer_hash": _pair_scorer_weights_hash(),
        "seed_file_hash": _sha256_file(seed_csv_path) if seed_csv_path else None,
        "python_version": sys.version,
        "package_version": _package_version(),
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "cli_args": cli_args or [],
        "include_unverified_deals": include_unverified_deals,
        "score_mode": score_mode,
    }
    if extra:
        manifest.update(extra)
    return manifest


def write_manifest(
    output_dir: "str | Path",
    config_path: Optional["str | Path"],
    seed_csv_path: Optional["str | Path"],
    cli_args: Optional[list[str]],
    include_unverified_deals: bool,
    score_mode: str,
    extra: Optional[dict[str, Any]] = None,
) -> Path:
    """Write run_manifest.json to output_dir and return the path."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(
        config_path=config_path,
        seed_csv_path=seed_csv_path,
        cli_args=cli_args,
        include_unverified_deals=include_unverified_deals,
        score_mode=score_mode,
        extra=extra,
    )
    manifest_path = output_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path
