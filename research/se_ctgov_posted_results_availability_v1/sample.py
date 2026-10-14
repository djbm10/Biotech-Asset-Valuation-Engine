"""Phase 2 tabulation + Phase 3 frozen sampling rule and full-record retrieval (prereg eefd8a2)."""

import hashlib
import json
import time
import urllib.request
from pathlib import Path

STUDY = Path(__file__).resolve().parent
ROOT = STUDY.parents[1]
RAW = Path.home() / "se_runs/ctgov_posted_results_availability_v1"
AS_OF = "2026-09-24"
PER_STRATUM, NEGATIVES = 8, 4


def stratum(phases):
    p = set(phases or [])
    if p & {"PHASE3", "PHASE4"}:
        return "LATE"
    if "PHASE2" in p:
        return "PHASE2"
    if p & {"PHASE1", "EARLY_PHASE1"}:
        return "EARLY"
    return "OTHER_NA"


def census_rows():
    manifest = json.loads((STUDY / "census_manifest.json").read_text())
    rows = {}
    for req in manifest["requests"]:
        if req["status"] != 200:
            continue
        body = (RAW / "census" / req["file"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == req["sha256"], req["file"]
        for s in json.loads(body)["studies"]:
            ps = s.get("protocolSection", {})
            st = ps.get("statusModule", {})
            nct = ps["identificationModule"]["nctId"]
            rows[nct] = {
                "nct": nct,
                "phases": ps.get("designModule", {}).get("phases") or [],
                "status": st.get("overallStatus"),
                "primary_completion": (st.get("primaryCompletionDateStruct") or {}).get("date"),
                "has_results": bool(s.get("hasResults")),
                "results_first_posted": (st.get("resultsFirstPostDateStruct") or {}).get("date"),
                "last_update_posted": (st.get("lastUpdatePostDateStruct") or {}).get("date"),
            }
    return rows


def frozen_sample(rows):
    key = lambda n: hashlib.sha256(n.encode()).hexdigest()  # noqa: E731
    withr = [r for r in rows.values() if r["has_results"]]
    picks = []
    for st in ("EARLY", "PHASE2", "LATE", "OTHER_NA"):
        group = sorted((r["nct"] for r in withr if stratum(r["phases"]) == st), key=key)
        picks += [(n, st) for n in group[:PER_STRATUM]]
    neg = sorted((r["nct"] for r in rows.values() if not r["has_results"]), key=key)[:NEGATIVES]
    return picks + [(n, "NEGATIVE_CONTROL") for n in neg]


def fetch(sample):
    out = RAW / "full"
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for nct, st in sample:
        req = urllib.request.Request(
            f"https://clinicaltrials.gov/api/v2/studies/{nct}",
            headers={"User-Agent": "bve-research-survey/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            (out / f"{nct}.json").write_bytes(body)
            manifest.append(
                {
                    "nct": nct,
                    "stratum": st,
                    "status": 200,
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            )
        except Exception as e:  # noqa: BLE001
            manifest.append({"nct": nct, "stratum": st, "status": "ERROR", "error": str(e)})
        time.sleep(1.0)
    return manifest


if __name__ == "__main__":
    rows = census_rows()
    sample = frozen_sample(rows)
    (STUDY / "census_rows.json").write_text(json.dumps(rows, indent=0, sort_keys=True) + "\n")
    (STUDY / "full_manifest.json").write_text(json.dumps(fetch(sample), indent=1) + "\n")
    print(len(rows), len(sample))
