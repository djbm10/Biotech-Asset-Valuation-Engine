"""DEVELOPMENT: bounded live check of CT.gov asset-seeded retrieval (ctgov_seeded_retrieval_v1).

    python research/se_ctgov_seeded_v1/live_seeded.py --out OUT.json --snapshots DIR PROBLEM.yaml...

For each problem: the target-vocabulary query plus every authority-seeded query the engine
compiles, run once against the live CT.gov v2 API through the production provider. Records
every HTTP URL, records returned, nominated assets and the overlap with the target-query
record set. Reads no reference and computes no score.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests
import yaml

from bve.se.discovery.adapters import ClinicalTrialsGovAdapter
from bve.se.discovery.query import compile_problem_queries
from bve.se.discovery.seeding import SeedProvenance
from bve.se.schemas.contracts import BuyerProblemV2
from bve.se.universe.factory import build_trial_provider

URLS: list[str] = []
_send = requests.Session.send


def _logging_send(self, request, **kwargs):
    URLS.append(request.url)
    return _send(self, request, **kwargs)


requests.Session.send = _logging_send  # type: ignore[method-assign]


def run(problem_path: Path, snapshots: Path) -> dict:
    problem = BuyerProblemV2.model_validate(yaml.safe_load(problem_path.read_text()))
    queries = [q for q in compile_problem_queries(problem)
               if q.seed_provenance == SeedProvenance.AUTHORITY_SEEDED_ASSET
               or (q.seed_provenance == SeedProvenance.TARGET_VOCABULARY and not q.modality_ids)]
    adapter = ClinicalTrialsGovAdapter(
        provider=build_trial_provider("rest", snapshot_root=snapshots / problem_path.stem),
        snapshot_root=snapshots / problem_path.stem)
    rows, target_set = [], set()
    for q in queries:
        start = len(URLS)
        t0 = time.monotonic()
        result = adapter.search(q, as_of_date=problem.buyer.as_of_date)
        records = sorted({m.record_id for m in result.materializations})
        row = {"kind": q.seed_provenance, "seed_drug_id": q.seed_drug_id, "query": q.query,
               "outcome": result.outcome.value, "error": result.error,
               "http_urls": URLS[start:], "records": records,
               "nominated": sorted({h.asset_name for h in result.hits if h.asset_name}),
               "elapsed_s": round(time.monotonic() - t0, 2)}
        if q.seed_provenance == SeedProvenance.TARGET_VOCABULARY:
            target_set = set(records)
        rows.append(row)
    for row in rows:
        row["records_not_in_target_set"] = sorted(set(row["records"]) - target_set)
    seeded = [r for r in rows if r["kind"] == SeedProvenance.AUTHORITY_SEEDED_ASSET]
    return {"problem": str(problem_path), "as_of": str(problem.buyer.as_of_date),
            "target_set_size": len(target_set),
            "seeded_queries": len(seeded),
            "seeded_requests_distinct_from_target": sum(
                r["http_urls"] != rows[0]["http_urls"] for r in seeded),
            "seeded_record_sets_distinct_from_target": sum(set(r["records"]) != target_set for r in seeded),
            "union_records_seeded_only": len({x for r in seeded for x in r["records_not_in_target_set"]}),
            "queries": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--snapshots", required=True)
    ap.add_argument("problems", nargs="+")
    args = ap.parse_args()
    t0 = time.monotonic()
    out = {"grade": "DEVELOPMENT", "runs": [run(Path(p), Path(args.snapshots)) for p in args.problems]}
    out["http_requests_total"] = len(URLS)
    out["elapsed_s"] = round(time.monotonic() - t0, 1)
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n")
    for r in out["runs"]:
        print(r["problem"], {k: v for k, v in r.items() if k not in ("queries", "problem")})
        for q in r["queries"]:
            print(f"  {q['kind'][:9]:9} {q['outcome']:17} records={len(q['records']):3} new={len(q['records_not_in_target_set']):3} "
                  f"urls={len(q['http_urls'])} {q['query'][:60]}")
    print("http_requests_total", out["http_requests_total"], "elapsed_s", out["elapsed_s"])


if __name__ == "__main__":
    main()
