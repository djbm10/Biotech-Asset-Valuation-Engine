"""Phase 2 census: metadata-only batched retrieval for the frozen cohort (prereg eefd8a2)."""

import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STUDY = Path(__file__).resolve().parent
RAW = Path.home() / "se_runs/ctgov_posted_results_availability_v1/census"
FIELDS = "NCTId,Phase,OverallStatus,PrimaryCompletionDate,HasResults,ResultsFirstPostDate,LastUpdatePostDate"
BATCH = 100


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "bve-research-survey/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read()


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    cohort = json.loads((STUDY / "cohort.json").read_text())["cohort"]
    _, ver = get("https://clinicaltrials.gov/api/v2/version")
    (RAW / "version.json").write_bytes(ver)
    manifest = {"version": json.loads(ver), "requests": []}
    for i in range(0, len(cohort), BATCH):
        ids = cohort[i : i + BATCH]
        q = urllib.parse.urlencode(
            {"filter.ids": ",".join(ids), "fields": FIELDS, "pageSize": 1000}
        )
        url = f"https://clinicaltrials.gov/api/v2/studies?{q}"
        stamp = datetime.now(timezone.utc).isoformat()
        try:
            status, body = get(url)
            name = f"batch_{i // BATCH:03d}.json"
            (RAW / name).write_bytes(body)
            manifest["requests"].append(
                {
                    "batch": i // BATCH,
                    "ids": len(ids),
                    "status": status,
                    "file": name,
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "retrieved_at": stamp,
                }
            )
        except Exception as e:  # noqa: BLE001 - API error is recorded, distinct from absence
            manifest["requests"].append(
                {
                    "batch": i // BATCH,
                    "ids": len(ids),
                    "status": "ERROR",
                    "error": f"{type(e).__name__}: {e}",
                    "retrieved_at": stamp,
                }
            )
        time.sleep(1.0)
    (STUDY / "census_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(sum(r["status"] == 200 for r in manifest["requests"]), len(manifest["requests"]))


if __name__ == "__main__":
    main()
