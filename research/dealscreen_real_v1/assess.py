"""Compare a DealScreen workspace on the real landscape with the manual reference.

INTERNAL DEVELOPMENT: the reference was prepared by the same AI environment (committed
before screening). Usage: python research/dealscreen_real_v1/assess.py WORKSPACE OUT.json
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

from bve.dealscreen.workspace import Workspace

ROOT = Path(__file__).resolve().parents[2]
CATEGORY = {
    ("IN", "ELIGIBLE"): "correct: eligible",
    ("IN", "UNRESOLVED"): "in scope but left for review (missed)",
    ("IN", "EXCLUDED"): "WRONG: in-scope program excluded",
    ("OUT", "EXCLUDED"): "correct: excluded",
    ("OUT", "UNRESOLVED"): "out of scope but left for review (noise)",
    ("OUT", "ELIGIBLE"): "WRONG: out-of-scope program eligible",
}


def assess(workspace: Path) -> dict:
    ws = Workspace(workspace)
    reference = {r["program_id"]: r for r in csv.DictReader(
        (ROOT / "examples/dealscreen_real/reference_manual_assessment.csv").open())}
    assets = {a.asset_id: a for a in ws.assets()}
    flags = {f.flag_id: f for f in ws.flags()}
    rows = []
    for s in ws.screening()["screens"]:
        asset = assets[s["asset_id"]]
        ref = reference[asset.external_id]
        not_pass = {d["requirement_id"]: d["analyst_override"] or d["status"]
                    for d in s["decisions"] if (d["analyst_override"] or d["status"]) != "PASS"}
        rows.append({
            "program_id": asset.external_id, "program": asset.program_name,
            "reference": ref["reference_scope"], "engine": s["disposition"],
            "category": CATEGORY.get((ref["reference_scope"], s["disposition"]), "reference UNKNOWN"),
            "gates_not_passed": not_pass,
            "unreadable_source_values": [f"{u['field']}={u['value']!r}" for u in s["unreadable_claims"]],
            "us_rights": s["commercial"]["display"],
            "identity_flags": [f"{flags[f].kind}:{flags[f].shared_value}" for f in s["identity_flag_ids"]],
            "reference_identity_note": ref["identity_note"],
            "rank": s["rank"],
        })
    rows.sort(key=lambda r: r["program_id"])
    return {"label": "INTERNAL DEVELOPMENT: same AI environment prepared landscape, reference and review",
            "categories": dict(Counter(r["category"] for r in rows)),
            "funnel": ws.screening()["funnel"], "rows": rows}


if __name__ == "__main__":
    result = assess(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["categories"], indent=1))
    for r in result["rows"]:
        print(f"{r['program_id']} {r['program'][:30]:30} ref={r['reference']:7} engine={r['engine']:10} "
              f"{r['category'][:38]:38} {r['gates_not_passed']} {r['identity_flags']}")
