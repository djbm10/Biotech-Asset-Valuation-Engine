"""Independent per-build prerequisite verification for Milestone 3B.

Run once per build root. Recomputes every receipt-bound hash/byte length
from the freshly downloaded+extracted bytes and checks the frozen study
set, row count, history-index count, and version count. Writes a
noncanonical telemetry record (timestamps, asset ids) alongside a
canonical validation result (no local paths, no timestamps) that the
extraction stage can bind to.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_m1(m1_dir: Path) -> dict:
    manifest = json.loads((m1_dir / "manifest.json").read_text())
    receipt = json.loads((m1_dir / "receipt.json").read_text())
    assert receipt["snapshot_id"] == "47e9e791f48bb7aacc467e28", "M1 snapshot id mismatch"
    assert receipt["status"] == "FINALIZED", "M1 not finalized"

    mismatches = []
    for rel, meta in receipt["artifacts"].items():
        path = m1_dir / rel
        if not path.is_file():
            mismatches.append({"path": rel, "issue": "MISSING"})
            continue
        data = path.read_bytes()
        if sha_bytes(data) != meta["sha256"] or len(data) != meta["byte_length"]:
            mismatches.append({"path": rel, "issue": "HASH_OR_LENGTH_MISMATCH"})

    population = json.loads((m1_dir / "source" / "benchmark_population.json").read_text())
    studies = population["studies"]
    row_count = sum(
        len(s["protocolSection"].get("armsInterventionsModule", {}).get("interventions", []))
        for s in studies
    )
    nct_ids = sorted(s["protocolSection"]["identificationModule"]["nctId"] for s in studies)

    return {
        "manifest_schema_valid": "checks" in manifest and "lineage" in manifest,
        "receipt_schema_valid": "artifacts" in receipt and "snapshot_id" in receipt,
        "artifact_mismatches": mismatches,
        "study_count": len(studies),
        "row_count": row_count,
        "nct_ids": nct_ids,
    }


def verify_m2(m2_dir: Path, expected_nct_ids: list[str]) -> dict:
    manifest = json.loads((m2_dir / "manifest.json").read_text())
    receipt = json.loads((m2_dir / "receipt.json").read_text())
    assert receipt["snapshot_id"] == "62914ac00fa635d38755e25b", "M2 snapshot id mismatch"
    assert receipt["status"] == "FINALIZED", "M2 not finalized"

    mismatches = []
    for rel, meta in receipt["artifacts"].items():
        path = m2_dir / rel
        if not path.is_file():
            mismatches.append({"path": rel, "issue": "MISSING"})
            continue
        data = path.read_bytes()
        if sha_bytes(data) != meta["sha256"] or len(data) != meta["byte_length"]:
            mismatches.append({"path": rel, "issue": "HASH_OR_LENGTH_MISMATCH"})

    history_index_rows = [
        json.loads(l) for l in (m2_dir / "normalized" / "history_index_ledger.jsonl").read_text().splitlines() if l.strip()
    ]
    current_rows = [
        json.loads(l) for l in (m2_dir / "normalized" / "current_ledger.jsonl").read_text().splitlines() if l.strip()
    ]
    version_rows = [
        json.loads(l) for l in (m2_dir / "normalized" / "version_ledger.jsonl").read_text().splitlines() if l.strip()
    ]
    captured_versions = [r for r in version_rows if r["status"] == "CAPTURED"]
    nct_ids_seen = sorted({r["nct_id"] for r in captured_versions})

    version_hash_mismatches = []
    for row in captured_versions:
        path = m2_dir / row["path"]
        data = path.read_bytes()
        if sha_bytes(data) != row["sha256"] or len(data) != row["byte_length"]:
            version_hash_mismatches.append(row["path"])

    return {
        "manifest_schema_valid": "checks" in manifest and "lineage" in manifest,
        "receipt_schema_valid": "artifacts" in receipt and "snapshot_id" in receipt,
        "artifact_mismatches": mismatches,
        "history_index_count": len(history_index_rows),
        "current_record_count": len(current_rows),
        "historical_version_count": len(captured_versions),
        "version_hash_mismatches": version_hash_mismatches,
        "nct_id_set_matches_m1": nct_ids_seen == sorted(expected_nct_ids),
    }


def main() -> int:
    prereq_root = Path(sys.argv[1])
    m1_dir = prereq_root / "m1" / "extracted"
    m2_dir = prereq_root / "m2" / "extracted"

    m1_result = verify_m1(m1_dir)
    m2_result = verify_m2(m2_dir, m1_result["nct_ids"])

    ok = (
        not m1_result["artifact_mismatches"]
        and not m2_result["artifact_mismatches"]
        and m1_result["study_count"] == 81
        and m1_result["row_count"] == 300
        and m2_result["history_index_count"] == 81
        and m2_result["current_record_count"] == 81
        and m2_result["historical_version_count"] == 4029
        and not m2_result["version_hash_mismatches"]
        and m2_result["nct_id_set_matches_m1"]
    )

    canonical_result = {
        "m1": {k: v for k, v in m1_result.items() if k != "nct_ids"},
        "m1_nct_ids": m1_result["nct_ids"],
        "m2": m2_result,
        "overall_pass": ok,
    }
    telemetry = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "prerequisite_root": str(prereq_root),
    }

    out_dir = prereq_root
    (out_dir / "validation_result.json").write_text(json.dumps(canonical_result, indent=2, sort_keys=True) + "\n")
    (out_dir / "download_telemetry.json").write_text(json.dumps(telemetry, indent=2, sort_keys=True) + "\n")

    print(json.dumps(canonical_result, indent=2, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
