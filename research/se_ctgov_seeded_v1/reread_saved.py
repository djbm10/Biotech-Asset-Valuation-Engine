"""DEVELOPMENT: re-read the records a live_seeded.py run saved, per query, with current code.

    python research/se_ctgov_seeded_v1/reread_saved.py LIVE.json SNAPSHOT_DIR OUT.json

No network: each query is served exactly the NCT ids the live run recorded for it, from the
snapshot files it wrote. Only nomination (the adapter's extraction) is re-run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from bve.se.discovery.adapters import ClinicalTrialsGovAdapter
from bve.se.discovery.query import compile_problem_queries
from bve.se.schemas.contracts import BuyerProblemV2
from bve.se.universe.ctgov import ClinicalTrialsGovProvider


def main() -> None:
    live = json.loads(Path(sys.argv[1]).read_text())
    snapdir = Path(sys.argv[2])
    by_nct: dict[str, dict] = {}
    for path in snapdir.rglob("*.json"):
        payload = json.loads(path.read_text())
        protocol = payload.get("protocolSection", payload)
        nct = (protocol.get("identificationModule") or {}).get("nctId")
        if nct:
            by_nct[nct] = payload
    out = {"grade": "DEVELOPMENT", "runs": []}
    for run in live["runs"]:
        problem = BuyerProblemV2.model_validate(yaml.safe_load(Path(run["problem"]).read_text()))
        compiled = {q.query: q for q in compile_problem_queries(problem)}
        rows = []
        for row in run["queries"]:
            served = [by_nct[n] for n in row["records"] if n in by_nct]
            adapter = ClinicalTrialsGovAdapter(
                provider=ClinicalTrialsGovProvider(search_fn=lambda _s=served, **_: list(_s)))
            result = adapter.search(compiled[row["query"]], as_of_date=problem.buyer.as_of_date)
            rows.append({"query": row["query"], "kind": row["kind"], "records": len(row["records"]),
                         "served": len(served), "nominated_before": row["nominated"],
                         "nominated_after": sorted({h.asset_name for h in result.hits if h.asset_name}),
                         "trials_with_hits_after": sorted({h.trial_id for h in result.hits})})
        out["runs"].append({"problem": run["problem"], "queries": rows})
    Path(sys.argv[3]).write_text(json.dumps(out, indent=1) + "\n")
    for run in out["runs"]:
        print(run["problem"])
        for r in run["queries"]:
            print(f"  rec={r['records']:3} served={r['served']:3} trials_hit={len(r['trials_with_hits_after']):3} "
                  f"{r['query'][:38]:38} after={r['nominated_after'][:6]}")


if __name__ == "__main__":
    main()
