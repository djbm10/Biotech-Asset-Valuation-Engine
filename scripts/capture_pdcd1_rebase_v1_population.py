#!/usr/bin/env python3
"""Milestone 1 stage runner for the REPRODUCIBLE_BIOTECH_PIPELINE_REBASE_V1 lineage.

Captures the PDCD1 population by invoking the existing, unmodified
scripts/capture_v4_fourth_target_population.py (its selection algorithm is not
touched) while additionally recording full retrieval metadata (HTTP status,
final URL, timestamps, page count) that the original script discards. Writes
an immutable, resumable, exportable snapshot under
artifacts/pipeline/pdcd1_rebase_v1/stages/01_population_capture/<snapshot_id>/.

Scope: population capture only. This stage performs no candidate
adjudication, no prediction generation, and no benchmark/evaluation scoring.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINEAGE = "REPRODUCIBLE_BIOTECH_PIPELINE_REBASE_V1"
MILESTONE = "PDCD1_BENCHMARK_REBASE_V1_MILESTONE_1_POPULATION_CAPTURE"
STAGE_NAME = "01_population_capture"
STAGE_ROOT = ROOT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages" / STAGE_NAME
UNDERLYING_SCRIPT = ROOT / "scripts" / "capture_v4_fourth_target_population.py"
CANONICAL_TARGET = "PDCD1"
QUERY_INTR = "PD-1 OR PDCD1"
API_VERSION = "clinicaltrials.gov API v2"


def cb(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_hash(value: object) -> str:
    return hashlib.sha256(cb(value)).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".staged")
    tmp.write_bytes(data)
    tmp.replace(path)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_underlying_module():
    spec = importlib.util.spec_from_file_location("capture_v4_fourth_target_population", UNDERLYING_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def validate_snapshot(snapshot_dir: Path) -> dict:
    """Re-check every artifact binding in receipt.json against the files on disk."""
    receipt_path = snapshot_dir / "receipt.json"
    manifest_path = snapshot_dir / "manifest.json"
    if not receipt_path.is_file() or not manifest_path.is_file():
        raise ValueError("MISSING_RECEIPT_OR_MANIFEST")
    receipt = json.loads(receipt_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    if receipt.get("status") != "FINALIZED" or manifest.get("stage_status") != "FINALIZED":
        raise ValueError("STAGE_NOT_FINALIZED")
    for rel, binding in receipt["artifacts"].items():
        path = snapshot_dir / rel
        if not path.is_file():
            raise ValueError(f"MISSING_ARTIFACT:{rel}")
        if path.stat().st_size != binding["byte_length"] or sha(path) != binding["sha256"]:
            raise ValueError(f"ARTIFACT_HASH_MISMATCH:{rel}")
    if (manifest.get("adjudication_performed") is not False
            or manifest.get("predictions_generated") is not False
            or manifest.get("evaluation_performed") is not False):
        raise ValueError("MILESTONE_SCOPE_VIOLATION")
    return {"manifest": manifest, "receipt": receipt}


def find_resumable_snapshot(today: str) -> Path | None:
    """Look for an already-finalized snapshot for this target/query/date, purely from local state."""
    if not STAGE_ROOT.exists():
        return None
    for candidate in sorted(STAGE_ROOT.iterdir()):
        if not candidate.is_dir():
            continue
        manifest_path = candidate / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if (manifest.get("canonical_target") == CANONICAL_TARGET
                and manifest.get("query_intr") == QUERY_INTR
                and manifest.get("source_retrieval_date") == today
                and manifest.get("stage_status") == "FINALIZED"):
            return candidate
    return None


def run_capture(work_source_dir: Path) -> dict:
    """Invoke the unmodified underlying script's main(), instrumenting the one HTTP call it makes."""
    module = load_underlying_module()
    http_events: list[dict] = []
    real_urlopen = urllib.request.urlopen

    def instrumented_urlopen(request, *args, **kwargs):
        t0 = utcnow()
        response = real_urlopen(request, *args, **kwargs)
        event = {
            "requested_url": getattr(request, "full_url", str(request)),
            "final_url": response.geturl(),
            "http_status": response.status,
            "timestamp": t0,
            "response_headers": dict(response.headers.items()),
        }
        http_events.append(event)
        return response

    urllib.request.urlopen = instrumented_urlopen
    old_argv = sys.argv
    sys.argv = ["capture_v4_fourth_target_population.py", "--output", str(work_source_dir)]
    start = time.monotonic()
    exit_status = 0
    stdout_text = ""
    error_text = None
    try:
        import io
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            module.main()
        stdout_text = buf.getvalue()
    except Exception as exc:  # noqa: BLE001 - must record failure, not swallow it
        exit_status = 1
        error_text = f"{type(exc).__name__}: {exc}"
    finally:
        urllib.request.urlopen = real_urlopen
        sys.argv = old_argv
    duration_ms = int((time.monotonic() - start) * 1000)
    return {
        "exit_status": exit_status,
        "error": error_text,
        "stdout": stdout_text,
        "duration_ms": duration_ms,
        "http_events": http_events,
    }


def compute_checks(work_source_dir: Path) -> dict:
    source_manifest = json.loads((work_source_dir / "source_manifest.json").read_text())
    population = json.loads((work_source_dir / "benchmark_population.json").read_text())
    raw_page = json.loads((work_source_dir / "current_page_1.json").read_text())

    page_studies = raw_page.get("studies", [])
    page_nct_ids = [s["protocolSection"]["identificationModule"]["nctId"] for s in page_studies]
    page_duplicates = len(page_nct_ids) - len(set(page_nct_ids))

    selected_ids = source_manifest["benchmark_trial_ids"]
    selected_duplicates = len(selected_ids) - len(set(selected_ids))

    intervention_ids: list[str] = []
    for study in population["studies"]:
        nct = study["protocolSection"]["identificationModule"]["nctId"]
        interventions = study["protocolSection"].get("armsInterventionsModule", {}).get("interventions", [])
        for idx in range(len(interventions)):
            intervention_ids.append(f"{nct}:intervention:{idx}")
    intervention_duplicates = len(intervention_ids) - len(set(intervention_ids))

    return {
        "total_universe_studies": source_manifest.get("source_study_count"),
        "captured_page_studies": len(page_studies),
        "captured_page_duplicate_nct_ids": page_duplicates,
        "selected_benchmark_studies": len(selected_ids),
        "selected_benchmark_duplicate_nct_ids": selected_duplicates,
        "selected_benchmark_intervention_rows": len(intervention_ids),
        "selected_benchmark_duplicate_intervention_rows": intervention_duplicates,
        "additional_pages_beyond_captured_page": source_manifest.get("source_study_count", 0) > len(page_studies),
    }


def build_export(snapshot_dir: Path, export_dir: Path) -> dict:
    export_dir.mkdir(parents=True, exist_ok=True)
    tar_path = export_dir / "snapshot.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        for path in sorted(snapshot_dir.rglob("*")):
            if path.is_file() and export_dir not in path.parents and path != tar_path:
                tar.add(path, arcname=str(path.relative_to(snapshot_dir)))
    tar_sha256 = sha(tar_path)
    (export_dir / "snapshot.tar.gz.sha256").write_text(f"{tar_sha256}  snapshot.tar.gz\n")
    return {"tar_path": str(tar_path), "tar_sha256": tar_sha256, "tar_byte_length": tar_path.stat().st_size}


def revalidate_export(tar_path: Path, expected_receipt: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(tmp_path)
        mismatches = []
        for rel, binding in expected_receipt["artifacts"].items():
            p = tmp_path / rel
            if not p.is_file():
                mismatches.append(f"MISSING:{rel}")
                continue
            if p.stat().st_size != binding["byte_length"] or sha(p) != binding["sha256"]:
                mismatches.append(f"MISMATCH:{rel}")
        return {"revalidated": len(mismatches) == 0, "mismatches": mismatches}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-new", action="store_true",
                         help="Skip resumability short-circuit and force a fresh capture attempt.")
    args = parser.parse_args()

    today = datetime.now(timezone.utc).date().isoformat()

    if not args.force_new:
        existing = find_resumable_snapshot(today)
        if existing is not None:
            try:
                validate_snapshot(existing)
            except ValueError as exc:
                print(json.dumps({"status": "RESUME_VALIDATION_FAILED", "snapshot": str(existing),
                                   "error": str(exc)}, sort_keys=True))
                sys.exit(1)
            print(json.dumps({"status": "ALREADY_FINALIZED", "snapshot_id": existing.name,
                               "path": str(existing), "api_calls": 0, "writes": 0}, sort_keys=True))
            return

    script_sha256 = sha(UNDERLYING_SCRIPT)
    git_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                                 check=True).stdout.strip()

    with tempfile.TemporaryDirectory() as tmp:
        work_source_dir = Path(tmp) / "source"
        capture_result = run_capture(work_source_dir)
        logs_blob = cb({
            "underlying_script": "scripts/capture_v4_fourth_target_population.py",
            "argv": ["--output", "<snapshot>/source"],
            "exit_status": capture_result["exit_status"],
            "error": capture_result["error"],
            "stdout": capture_result["stdout"],
            "duration_ms": capture_result["duration_ms"],
            "http_events": capture_result["http_events"],
        })

        if capture_result["exit_status"] != 0:
            failure_dir = STAGE_ROOT / f"FAILED_{today}_{stable_hash(logs_blob)[:16]}"
            failure_dir.mkdir(parents=True, exist_ok=True)
            atomic_write(failure_dir / "logs" / "capture.jsonl", logs_blob)
            print(json.dumps({"status": "PARTIALLY_COMPLETE", "reason": capture_result["error"],
                               "logs": str(failure_dir / "logs" / "capture.jsonl")}, sort_keys=True))
            sys.exit(1)

        checks = compute_checks(work_source_dir)
        source_manifest_bytes = (work_source_dir / "source_manifest.json").read_bytes()
        raw_response_sha256 = json.loads(source_manifest_bytes)["raw_source"]["sha256"]

        snapshot_id_seed = {
            "canonical_target": CANONICAL_TARGET,
            "query_intr": QUERY_INTR,
            "api_version": API_VERSION,
            "retrieval_date": today,
            "raw_response_sha256": raw_response_sha256,
        }
        snapshot_id = stable_hash(snapshot_id_seed)[:24]
        snapshot_dir = STAGE_ROOT / snapshot_id

        if snapshot_dir.exists():
            try:
                validate_snapshot(snapshot_dir)
            except ValueError as exc:
                print(json.dumps({"status": "PARTIALLY_COMPLETE",
                                   "reason": f"EXISTING_SNAPSHOT_DIR_INVALID:{exc}",
                                   "snapshot_id": snapshot_id}, sort_keys=True))
                sys.exit(1)
            print(json.dumps({"status": "ALREADY_FINALIZED", "snapshot_id": snapshot_id,
                               "path": str(snapshot_dir), "api_calls": 0, "writes": 0}, sort_keys=True))
            return

        final_source_dir = snapshot_dir / "source"
        final_source_dir.mkdir(parents=True, exist_ok=True)
        for item in work_source_dir.iterdir():
            atomic_write(final_source_dir / item.name, item.read_bytes())

        atomic_write(snapshot_dir / "logs" / "capture.jsonl", logs_blob)
        atomic_write(snapshot_dir / "commands.jsonl", cb({
            "timestamp": utcnow(),
            "command": "python3 scripts/capture_v4_fourth_target_population.py --output <snapshot>/source",
            "invoked_via": "importlib in-process module load (scripts/capture_pdcd1_rebase_v1_population.py)",
            "exit_status": 0,
            "duration_ms": capture_result["duration_ms"],
        }))

        manifest = {
            "lineage": LINEAGE,
            "milestone": MILESTONE,
            "stage": STAGE_NAME,
            "stage_status": "FINALIZED",
            "snapshot_id": snapshot_id,
            "canonical_target": CANONICAL_TARGET,
            "query_intr": QUERY_INTR,
            "api_version": API_VERSION,
            "source_retrieval_date": today,
            "adjudication_performed": False,
            "predictions_generated": False,
            "evaluation_performed": False,
            "underlying_script_path": "scripts/capture_v4_fourth_target_population.py",
            "underlying_script_sha256": script_sha256,
            "underlying_script_git_status": "untracked_no_commit_history",
            "repo_git_commit": git_commit,
            "http_events": capture_result["http_events"],
            "checks": checks,
        }
        manifest_bytes = cb(manifest)
        atomic_write(snapshot_dir / "manifest.json", manifest_bytes)

        artifact_bindings = {}
        for path in sorted(snapshot_dir.rglob("*")):
            if path.is_file() and path.name not in {"receipt.json"} and "export" not in path.parts:
                rel = str(path.relative_to(snapshot_dir))
                artifact_bindings[rel] = {"sha256": sha(path), "byte_length": path.stat().st_size}

        receipt = {
            "lineage": LINEAGE,
            "milestone": MILESTONE,
            "stage": STAGE_NAME,
            "status": "FINALIZED",
            "snapshot_id": snapshot_id,
            "finalized_at": utcnow(),
            "artifacts": artifact_bindings,
        }
        atomic_write(snapshot_dir / "receipt.json", cb(receipt))

        export_info = build_export(snapshot_dir, snapshot_dir / "export")
        revalidation = revalidate_export(Path(export_info["tar_path"]), receipt)

        print(json.dumps({
            "status": "FINALIZED",
            "snapshot_id": snapshot_id,
            "path": str(snapshot_dir),
            "checks": checks,
            "export": export_info,
            "revalidation": revalidation,
        }, sort_keys=True))


if __name__ == "__main__":
    main()
