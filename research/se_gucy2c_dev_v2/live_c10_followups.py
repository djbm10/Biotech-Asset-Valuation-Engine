"""DEVELOPMENT: bounded live diagnostic of C10 and follow-up acquisition (GUCY2C dev problem).

Free public endpoints only (ClinicalTrials.gov v2, NCBI E-utilities). Does not touch the
frozen pilot or its custody. Runs at most 8 searches:

1. the main target-vocabulary query the current code compiles (C10 applied);
2. the same query with the refused shared alias "STAR" restored (the pre-C10 string);
3. depth-1 follow-ups for PF-07062119 and XKDCT080, if the main CT.gov query yields them;

each on CT.gov and PubMed. Records query strings, records returned, emitted asset names,
follow-ups proposed, failures, elapsed time and peak RSS.

    python research/se_gucy2c_dev_v2/live_c10_followups.py --out OUT.json --snapshots DIR
"""

from __future__ import annotations

import argparse
import json
import resource
import time
import traceback
from datetime import date
from pathlib import Path

import yaml

from bve.se.discovery.adapters import ClinicalTrialsGovAdapter, PubMedDiscoveryAdapter
from bve.se.discovery.query import compile_problem_queries
from bve.se.discovery.seeding import SeedProvenance
from bve.se.schemas.contracts import BuyerProblemV2, CompiledQuery
from bve.se.universe.factory import build_trial_provider

PROBLEM = Path(__file__).resolve().parents[1] / "se_gucy2c_dev_v1/engine_problem_dev.yaml"
LEADS = ("PF-07062119", "XKDCT080")


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _run(adapter, query: CompiledQuery, as_of: date) -> dict:
    started = time.monotonic()
    row = {"source": adapter.source_name, "query": query.query, "depth": query.expansion_depth}
    try:
        result = adapter.search(query, as_of_date=as_of)
    except Exception as exc:  # noqa: BLE001 -- a live failure is recorded, not hidden
        row |= {"outcome": "EXCEPTION", "error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc(limit=3)}
    else:
        docs = {d.source_url for d in result.source_documents}
        row |= {
            "outcome": result.outcome.value, "error": result.error,
            "records": len(docs),
            "hits": len(result.hits),
            "assets_emitted": sorted({h.asset_name for h in result.hits if h.asset_name}),
            "follow_up_queries": result.follow_up_queries,
        }
    row["elapsed_s"] = round(time.monotonic() - started, 1)
    row["peak_rss_mb"] = round(_rss_mb(), 1)
    print(json.dumps({k: v for k, v in row.items() if k not in ("assets_emitted", "follow_up_queries", "trace")}))
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--snapshots", required=True)
    args = ap.parse_args()
    snap = Path(args.snapshots)
    problem = BuyerProblemV2.model_validate(yaml.safe_load(PROBLEM.read_text()))
    as_of = problem.buyer.as_of_date
    [main_q] = [q for q in compile_problem_queries(problem)
                if q.seed_provenance == SeedProvenance.TARGET_VOCABULARY and not q.modality_ids]
    old_q = main_q.model_copy(update={
        "query_id": "query:pre_c10",
        "query": main_q.query.replace('"GCC" OR ', '"GCC" OR "STAR" OR ', 1),
    })
    # Built exactly as `bve-se-search` builds its live adapter (default `rest` backend).
    ctgov = ClinicalTrialsGovAdapter(
        provider=build_trial_provider("rest", snapshot_root=snap / "ctgov"),
        snapshot_root=snap / "ctgov",
    )
    pubmed = PubMedDiscoveryAdapter(snapshot_root=snap / "pubmed")
    report = {"problem": str(PROBLEM), "as_of": str(as_of),
              "c10_main_query": main_q.query, "pre_c10_query": old_q.query,
              "star_in_main_query": '"STAR"' in main_q.query, "runs": []}
    for q in (main_q, old_q):
        for adapter in (ctgov, pubmed):
            report["runs"].append(_run(adapter, q, as_of))
    proposed = set(report["runs"][0].get("follow_up_queries", []))
    report["leads_proposed_by_main_ctgov"] = {lead: lead in proposed for lead in LEADS}
    for lead in LEADS:
        follow = CompiledQuery(query_id=f"query:{lead}", query=lead, target_ids=main_q.target_ids,
                               modality_ids=main_q.modality_ids, aliases=[lead], expansion_depth=1)
        for adapter in (ctgov, pubmed):
            report["runs"].append(_run(adapter, follow, as_of))
    Path(args.out).write_text(json.dumps(report, indent=1, default=str) + "\n")


if __name__ == "__main__":
    main()
