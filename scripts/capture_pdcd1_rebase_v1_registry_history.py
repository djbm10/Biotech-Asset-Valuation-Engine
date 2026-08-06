#!/usr/bin/env python3
"""Milestone 2: capture complete ClinicalTrials.gov registry history for the
81 studies frozen by Milestone 1 (PDCD1_BENCHMARK_REBASE_V1_MILESTONE_1_POPULATION_CAPTURE).

This stage performs capture and validation only. It does not adjudicate
candidate identities, derive aliases, build chronology, create benchmark
labels, run predictions, or compute evaluation metrics.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import random
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LINEAGE = "REPRODUCIBLE_BIOTECH_PIPELINE_REBASE_V1"
MILESTONE = "PDCD1_BENCHMARK_REBASE_V1_MILESTONE_2_COMPLETE_REGISTRY_HISTORY_CAPTURE"
STAGE = "02_registry_history_capture"
CANONICAL_TARGET = "PDCD1"
API_VERSION_LABEL = "clinicaltrials_gov_api_int_v1+api_v2_current"

HISTORY_INDEX_URL = "https://clinicaltrials.gov/api/int/studies/{nct}/history"
HISTORY_VERSION_URL = "https://clinicaltrials.gov/api/int/studies/{nct}/history/{version}"
CURRENT_URL = "https://clinicaltrials.gov/api/v2/studies/{nct}"

RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}
ACCESS_BLOCKED_HTTP_CODES = {401, 403}
MAX_ATTEMPTS = 10
MIN_REQUEST_INTERVAL_SECONDS = 0.12
MAX_WORKERS = 6

ROOT = Path(__file__).resolve().parents[1]
STAGE_ROOT = ROOT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages" / STAGE
STAGING_ROOT = STAGE_ROOT / "_staging"

MILESTONE1_RELEASE_TAG = "pdcd1-rebase-v1-population-47e9e791f48bb7aacc467e28"
MILESTONE1_REPO = "djbm10/Biotech-Asset-Valuation-Engine"
MILESTONE1_ARCHIVE_SHA256 = "7a6b509d42de915a0e0e8e5dfc054c23ffab4e6a3cfa5409acda1a45fae00923"
MILESTONE1_SNAPSHOT_ID = "47e9e791f48bb7aacc467e28"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cb(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def stable_hash(obj) -> str:
    return sha(cb(obj))


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def atomic_write_json(path: Path, obj) -> None:
    atomic_write(path, cb(obj))


class RateLimiter:
    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self.lock = threading.Lock()
        self.last = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delta = now - self.last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
            self.last = time.monotonic()


class FetchResult:
    __slots__ = ("status", "http_status", "attempts", "data", "final_url", "error")

    def __init__(self, status, http_status, attempts, data, final_url, error):
        self.status = status
        self.http_status = http_status
        self.attempts = attempts
        self.data = data
        self.final_url = final_url
        self.error = error


def fetch(url: str, limiter: RateLimiter) -> FetchResult:
    last_error = None
    for i in range(MAX_ATTEMPTS):
        limiter.wait()
        req = urllib.request.Request(
            url, headers={"User-Agent": "pdcd1-rebase-v1-history-capture/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = resp.read()
                final_url = resp.geturl()
                http_status = resp.status
            try:
                json.loads(data)
            except json.JSONDecodeError as exc:
                return FetchResult(
                    "TERMINAL_FAILURE", http_status, i + 1, None, final_url, f"invalid_json:{exc}"
                )
            return FetchResult("CAPTURED", http_status, i + 1, data, final_url, None)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return FetchResult("NOT_AVAILABLE", exc.code, i + 1, None, url, "http_404")
            if exc.code in ACCESS_BLOCKED_HTTP_CODES:
                return FetchResult(
                    "ACCESS_BLOCKED", exc.code, i + 1, None, url, f"http_{exc.code}"
                )
            if exc.code not in RETRYABLE_HTTP_CODES:
                return FetchResult(
                    "TERMINAL_FAILURE", exc.code, i + 1, None, url, f"http_{exc.code}"
                )
            last_error = f"http_{exc.code}"
            if i == MAX_ATTEMPTS - 1:
                return FetchResult(
                    "RETRYABLE_FAILURE", exc.code, i + 1, None, url,
                    f"exhausted_retries:{last_error}",
                )
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else min(60.0, 2 ** i)
            time.sleep(delay + random.random())
        except OSError as exc:
            last_error = str(exc)
            if i == MAX_ATTEMPTS - 1:
                return FetchResult(
                    "RETRYABLE_FAILURE", None, i + 1, None, url,
                    f"exhausted_retries:{last_error}",
                )
            time.sleep(min(60.0, 2 ** i) + random.random())
    return FetchResult(
        "RETRYABLE_FAILURE", None, MAX_ATTEMPTS, None, url, f"exhausted_retries:{last_error}"
    )


def load_status(status_path: Path):
    if not status_path.is_file():
        return None
    try:
        return json.loads(status_path.read_text())
    except json.JSONDecodeError:
        return None


def fetch_with_checkpoint(url: str, raw_path: Path, status_path: Path, limiter: RateLimiter) -> dict:
    existing = load_status(status_path)
    if existing is not None and existing.get("status") != "RETRYABLE_FAILURE":
        if existing.get("status") == "CAPTURED":
            if raw_path.is_file() and sha(raw_path.read_bytes()) == existing.get("sha256"):
                return existing
        else:
            return existing

    result = fetch(url, limiter)
    record = {
        "url": url,
        "final_url": result.final_url,
        "status": result.status,
        "http_status": result.http_status,
        "attempts": result.attempts,
        "error": result.error,
        "timestamp": utcnow(),
    }
    if result.status == "CAPTURED":
        atomic_write(raw_path, result.data)
        record["path"] = str(raw_path.name)
        record["sha256"] = sha(result.data)
        record["byte_length"] = len(result.data)
    atomic_write_json(status_path, record)
    return record


def process_study(nct: str, staging_dir: Path, limiter: RateLimiter) -> dict:
    study_dir = staging_dir / "source" / nct
    versions_dir = study_dir / "versions"

    index_record = fetch_with_checkpoint(
        HISTORY_INDEX_URL.format(nct=nct),
        study_dir / "history_index.json",
        study_dir / "history_index.status.json",
        limiter,
    )
    current_record = fetch_with_checkpoint(
        CURRENT_URL.format(nct=nct),
        study_dir / "current.json",
        study_dir / "current.status.json",
        limiter,
    )

    version_records: list[dict] = []
    changes: list[dict] = []
    if index_record.get("status") == "CAPTURED":
        raw = (study_dir / "history_index.json").read_bytes()
        parsed = json.loads(raw)
        changes = parsed.get("changes", [])
        for change in changes:
            version = int(change["version"])
            version_date = change.get("date")
            record = fetch_with_checkpoint(
                HISTORY_VERSION_URL.format(nct=nct, version=version),
                versions_dir / f"{version}.json",
                versions_dir / f"{version}.status.json",
                limiter,
            )
            record = dict(record)
            record["version"] = version
            record["version_date"] = version_date
            version_records.append(record)

    return {
        "nct_id": nct,
        "index": index_record,
        "current": current_record,
        "versions": version_records,
        "changes_declared_count": len(changes),
    }


def compute_staging_key(milestone1_snapshot_id: str, nct_ids: list[str], retrieval_date: str) -> str:
    return stable_hash(
        {
            "milestone1_snapshot_id": milestone1_snapshot_id,
            "nct_ids": sorted(nct_ids),
            "api_version_label": API_VERSION_LABEL,
            "retrieval_date": retrieval_date,
        }
    )[:24]


def find_finalized_snapshot_by_staging_key(staging_key: str) -> Path | None:
    if not STAGE_ROOT.is_dir():
        return None
    for candidate in STAGE_ROOT.iterdir():
        if not candidate.is_dir() or candidate.name == "_staging":
            continue
        manifest_path = candidate / "manifest.json"
        receipt_path = candidate / "receipt.json"
        if not (manifest_path.is_file() and receipt_path.is_file()):
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            continue
        if manifest.get("staging_key") == staging_key and manifest.get("stage_status") == "FINALIZED":
            return candidate
    return None


def validate_snapshot(snapshot_dir: Path) -> dict:
    receipt = json.loads((snapshot_dir / "receipt.json").read_text())
    mismatches = []
    for rel_path, meta in receipt["artifacts"].items():
        full = snapshot_dir / rel_path
        if not full.is_file():
            raise ValueError(f"MISSING_ARTIFACT:{rel_path}")
        data = full.read_bytes()
        if len(data) != meta["byte_length"] or sha(data) != meta["sha256"]:
            mismatches.append(rel_path)
    if mismatches:
        raise ValueError(f"ARTIFACT_HASH_MISMATCH:{mismatches}")
    return {"receipt": receipt, "mismatches": mismatches}


def build_normalized_ledgers(staging_dir: Path, study_results: list[dict]) -> dict:
    index_rows = []
    version_rows = []
    current_rows = []
    for result in sorted(study_results, key=lambda r: r["nct_id"]):
        nct = result["nct_id"]
        idx = result["index"]
        versions = sorted(result["versions"], key=lambda r: r["version"])
        version_numbers = [v["version"] for v in versions if v.get("status") == "CAPTURED"]
        dates = [v["version_date"] for v in versions if v.get("version_date")]
        index_rows.append(
            {
                "nct_id": nct,
                "status": idx.get("status"),
                "http_status": idx.get("http_status"),
                "attempts": idx.get("attempts"),
                "sha256": idx.get("sha256"),
                "byte_length": idx.get("byte_length"),
                "changes_declared_count": result["changes_declared_count"],
                "versions_captured_count": len(version_numbers),
                "min_version": min(version_numbers) if version_numbers else None,
                "max_version": max(version_numbers) if version_numbers else None,
                "earliest_version_date": min(dates) if dates else None,
                "latest_version_date": max(dates) if dates else None,
            }
        )
        for v in versions:
            version_rows.append(
                {
                    "nct_id": nct,
                    "version": v["version"],
                    "version_date": v.get("version_date"),
                    "status": v.get("status"),
                    "http_status": v.get("http_status"),
                    "attempts": v.get("attempts"),
                    "sha256": v.get("sha256"),
                    "byte_length": v.get("byte_length"),
                    "path": (f"source/{nct}/versions/{v['path']}" if v.get("path") else None),
                }
            )
        current_rows.append(
            {
                "nct_id": nct,
                "status": result["current"].get("status"),
                "http_status": result["current"].get("http_status"),
                "attempts": result["current"].get("attempts"),
                "sha256": result["current"].get("sha256"),
                "byte_length": result["current"].get("byte_length"),
            }
        )

    index_ledger = staging_dir / "normalized" / "history_index_ledger.jsonl"
    version_ledger = staging_dir / "normalized" / "version_ledger.jsonl"
    current_ledger = staging_dir / "normalized" / "current_ledger.jsonl"
    atomic_write(
        index_ledger,
        ("".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in index_rows)).encode(),
    )
    atomic_write(
        version_ledger,
        ("".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in version_rows)).encode(),
    )
    atomic_write(
        current_ledger,
        ("".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in current_rows)).encode(),
    )
    return {"index_rows": index_rows, "version_rows": version_rows, "current_rows": current_rows}


def build_export(snapshot_dir: Path) -> Path:
    export_dir = snapshot_dir / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"pdcd1-rebase-v1-history-{snapshot_dir.name}.tar.gz"
    tar_path = export_dir / archive_name
    with tarfile.open(tar_path, "w:gz") as tar:
        for path in sorted(snapshot_dir.rglob("*")):
            if path.is_file() and "export" not in path.relative_to(snapshot_dir).parts:
                tar.add(path, arcname=str(path.relative_to(snapshot_dir)))
    checksum_path = tar_path.with_suffix(tar_path.suffix + ".sha256")
    digest = sha(tar_path.read_bytes())
    checksum_path.write_text(f"{digest}  {archive_name}\n")
    return tar_path


def revalidate_export(tar_path: Path, receipt: dict) -> dict:
    mismatches = []
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(tmp)
        for rel_path, meta in receipt["artifacts"].items():
            full = Path(tmp) / rel_path
            if not full.is_file():
                mismatches.append(f"MISSING:{rel_path}")
                continue
            data = full.read_bytes()
            if len(data) != meta["byte_length"] or sha(data) != meta["sha256"]:
                mismatches.append(f"HASH_MISMATCH:{rel_path}")
    return {"revalidated": True, "mismatches": mismatches}


def repo_git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def load_prerequisite(prereq_extracted_dir: Path) -> dict:
    manifest = json.loads((prereq_extracted_dir / "manifest.json").read_text())
    receipt = json.loads((prereq_extracted_dir / "receipt.json").read_text())
    population = json.loads((prereq_extracted_dir / "source" / "benchmark_population.json").read_text())
    if receipt.get("status") != "FINALIZED" or manifest.get("stage_status") != "FINALIZED":
        raise ValueError("PREREQUISITE_NOT_FINALIZED")
    if receipt.get("snapshot_id") != MILESTONE1_SNAPSHOT_ID:
        raise ValueError("PREREQUISITE_SNAPSHOT_ID_MISMATCH")
    nct_ids = sorted(
        {study["protocolSection"]["identificationModule"]["nctId"] for study in population["studies"]}
    )
    if len(nct_ids) != manifest["checks"]["selected_benchmark_studies"]:
        raise ValueError("PREREQUISITE_STUDY_COUNT_MISMATCH")
    return {"manifest": manifest, "receipt": receipt, "nct_ids": nct_ids}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prerequisite-dir",
        type=Path,
        required=True,
        help="Path to the independently-verified, extracted Milestone 1 snapshot",
    )
    parser.add_argument("--retrieval-date", default=datetime.now(timezone.utc).date().isoformat())
    args = parser.parse_args()

    prereq = load_prerequisite(args.prerequisite_dir)
    nct_ids = prereq["nct_ids"]

    staging_key = compute_staging_key(MILESTONE1_SNAPSHOT_ID, nct_ids, args.retrieval_date)

    finalized = find_finalized_snapshot_by_staging_key(staging_key)
    if finalized is not None:
        result = validate_snapshot(finalized)
        print(
            json.dumps(
                {
                    "status": "ALREADY_FINALIZED",
                    "snapshot_id": finalized.name,
                    "staging_key": staging_key,
                    "receipt_status": result["receipt"]["status"],
                    "api_calls_made": 0,
                    "writes_made": 0,
                },
                sort_keys=True,
            )
        )
        return

    staging_dir = STAGING_ROOT / staging_key
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "input").mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        staging_dir / "input" / "staging_manifest.json",
        {
            "staging_key": staging_key,
            "milestone1_snapshot_id": MILESTONE1_SNAPSHOT_ID,
            "milestone1_release_tag": MILESTONE1_RELEASE_TAG,
            "milestone1_repo": MILESTONE1_REPO,
            "milestone1_archive_sha256": MILESTONE1_ARCHIVE_SHA256,
            "nct_ids": nct_ids,
            "nct_ids_count": len(nct_ids),
            "api_version_label": API_VERSION_LABEL,
            "retrieval_date": args.retrieval_date,
        },
    )

    limiter = RateLimiter(MIN_REQUEST_INTERVAL_SECONDS)
    commands_log = []
    start_time = utcnow()
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        study_results = list(
            executor.map(lambda nct: process_study(nct, staging_dir, limiter), nct_ids)
        )
    end_time = utcnow()
    commands_log.append(
        {
            "command": "capture_registry_history",
            "started_at": start_time,
            "finished_at": end_time,
            "study_count": len(nct_ids),
        }
    )

    ledgers = build_normalized_ledgers(staging_dir, study_results)

    def count_status(rows, key="status"):
        counts = {}
        for r in rows:
            counts[r[key]] = counts.get(r[key], 0) + 1
        return counts

    index_status_counts = count_status(ledgers["index_rows"])
    version_status_counts = count_status(ledgers["version_rows"])
    current_status_counts = count_status(ledgers["current_rows"])

    per_study_version_counts = sorted(r["versions_captured_count"] for r in ledgers["index_rows"])
    all_dates = [r["earliest_version_date"] for r in ledgers["index_rows"] if r["earliest_version_date"]]
    all_dates += [r["latest_version_date"] for r in ledgers["index_rows"] if r["latest_version_date"]]

    total_raw_bytes = 0
    for r in ledgers["index_rows"]:
        total_raw_bytes += r.get("byte_length") or 0
    for r in ledgers["version_rows"]:
        total_raw_bytes += r.get("byte_length") or 0
    for r in ledgers["current_rows"]:
        total_raw_bytes += r.get("byte_length") or 0

    any_retryable = (
        index_status_counts.get("RETRYABLE_FAILURE", 0) > 0
        or version_status_counts.get("RETRYABLE_FAILURE", 0) > 0
        or current_status_counts.get("RETRYABLE_FAILURE", 0) > 0
    )
    stage_status = "PARTIAL" if any_retryable else "FINALIZED"

    versions_expected = sum(r["changes_declared_count"] for r in ledgers["index_rows"])
    versions_captured = sum(1 for r in ledgers["version_rows"] if r["status"] == "CAPTURED")

    checks = {
        "studies_total": len(nct_ids),
        "indexes_captured": index_status_counts.get("CAPTURED", 0),
        "indexes_not_available": index_status_counts.get("NOT_AVAILABLE", 0),
        "indexes_access_blocked": index_status_counts.get("ACCESS_BLOCKED", 0),
        "indexes_retryable_failure": index_status_counts.get("RETRYABLE_FAILURE", 0),
        "indexes_terminal_failure": index_status_counts.get("TERMINAL_FAILURE", 0),
        "current_captured": current_status_counts.get("CAPTURED", 0),
        "current_not_available": current_status_counts.get("NOT_AVAILABLE", 0),
        "current_access_blocked": current_status_counts.get("ACCESS_BLOCKED", 0),
        "current_retryable_failure": current_status_counts.get("RETRYABLE_FAILURE", 0),
        "current_terminal_failure": current_status_counts.get("TERMINAL_FAILURE", 0),
        "versions_expected_from_index": versions_expected,
        "versions_captured": versions_captured,
        "versions_not_available": version_status_counts.get("NOT_AVAILABLE", 0),
        "versions_access_blocked": version_status_counts.get("ACCESS_BLOCKED", 0),
        "versions_retryable_failure": version_status_counts.get("RETRYABLE_FAILURE", 0),
        "versions_terminal_failure": version_status_counts.get("TERMINAL_FAILURE", 0),
        "versions_expected_vs_captured_delta": versions_expected - versions_captured,
        "min_versions_per_study": min(per_study_version_counts) if per_study_version_counts else 0,
        "median_versions_per_study": (
            per_study_version_counts[len(per_study_version_counts) // 2] if per_study_version_counts else 0
        ),
        "max_versions_per_study": max(per_study_version_counts) if per_study_version_counts else 0,
        "earliest_version_date": min(all_dates) if all_dates else None,
        "latest_version_date": max(all_dates) if all_dates else None,
        "total_raw_bytes": total_raw_bytes,
        "duplicate_nct_ids_in_frozen_set": len(nct_ids) - len(set(nct_ids)),
    }

    source_manifest_hash = stable_hash(
        {
            "index_rows": ledgers["index_rows"],
            "version_rows": ledgers["version_rows"],
            "current_rows": ledgers["current_rows"],
        }
    )
    final_id = stable_hash({"staging_key": staging_key, "source_manifest_hash": source_manifest_hash})[:24]

    final_dir = STAGE_ROOT / final_id
    if final_dir.exists():
        raise ValueError(f"SNAPSHOT_ID_COLLISION_WITHOUT_FINALIZATION:{final_id}")
    staging_dir.rename(final_dir)

    atomic_write(
        final_dir / "commands.jsonl",
        ("".join(json.dumps(c, sort_keys=True, separators=(",", ":")) + "\n" for c in commands_log)).encode(),
    )

    manifest = {
        "lineage": LINEAGE,
        "milestone": MILESTONE,
        "canonical_target": CANONICAL_TARGET,
        "stage": STAGE,
        "snapshot_id": final_id,
        "staging_key": staging_key,
        "source_manifest_hash": source_manifest_hash,
        "api_version_label": API_VERSION_LABEL,
        "source_retrieval_date": args.retrieval_date,
        "repo_git_commit": repo_git_commit(),
        "underlying_script_path": "scripts/capture_pdcd1_rebase_v1_registry_history.py",
        "underlying_script_sha256": sha(Path(__file__).read_bytes()),
        "milestone1_prerequisite": {
            "snapshot_id": MILESTONE1_SNAPSHOT_ID,
            "release_tag": MILESTONE1_RELEASE_TAG,
            "github_repository": MILESTONE1_REPO,
            "archive_sha256": MILESTONE1_ARCHIVE_SHA256,
            "nct_ids_count": len(nct_ids),
        },
        "checks": checks,
        "adjudication_performed": False,
        "candidate_identities_derived": False,
        "aliases_derived": False,
        "benchmark_labels_created": False,
        "predictions_generated": False,
        "evaluation_performed": False,
        "stage_status": stage_status,
    }
    atomic_write_json(final_dir / "manifest.json", manifest)

    log_dir = final_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(log_dir / "capture.jsonl", (json.dumps({"started_at": start_time, "finished_at": end_time}, sort_keys=True) + "\n").encode())

    validation_dir = final_dir / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        validation_dir / "completeness_report.json",
        {"checks": checks, "stage_status": stage_status},
    )

    artifacts = {}
    for path in sorted(final_dir.rglob("*")):
        if path.is_file() and path.name not in ("receipt.json",) and "export" not in path.relative_to(final_dir).parts:
            data = path.read_bytes()
            artifacts[str(path.relative_to(final_dir))] = {"sha256": sha(data), "byte_length": len(data)}

    receipt = {
        "lineage": LINEAGE,
        "milestone": MILESTONE,
        "stage": STAGE,
        "snapshot_id": final_id,
        "status": "FINALIZED" if stage_status == "FINALIZED" else "PARTIAL",
        "finalized_at": utcnow(),
        "artifacts": artifacts,
    }
    atomic_write_json(final_dir / "receipt.json", receipt)

    tar_path = build_export(final_dir)
    revalidation = revalidate_export(tar_path, json.loads((final_dir / "receipt.json").read_text()))

    print(
        json.dumps(
            {
                "status": stage_status,
                "snapshot_id": final_id,
                "staging_key": staging_key,
                "checks": checks,
                "export_revalidation": revalidation,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
