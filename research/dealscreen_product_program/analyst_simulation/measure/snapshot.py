"""Per-asset snapshot of a DealScreen workspace for before/after comparison.

Usage: python snapshot.py <workspace> <out.json>
"""
import csv
import json
import sys
from pathlib import Path

ws, out = Path(sys.argv[1]), Path(sys.argv[2])
s = json.loads((ws / "screening.json").read_text())
ext = {a["asset_id"]: a["external_id"] for a in json.loads((ws / "import.json").read_text())["assets"]}
rows = {}
for x in s["screens"]:
    gates = {d["requirement_id"]: d["status"] for d in x["decisions"]}
    rows[ext.get(x["asset_id"], x["asset_id"])] = {
        "program": x["program_name"], "disposition": x["disposition"], "rank": x["rank"],
        "activity": x["activity"], "indication_gate": gates.get("strategy.indication"),
        "gates": gates,
    }
json.dump({"funnel": s["funnel"], "assets": dict(sorted(rows.items()))}, out.open("w"), indent=1, sort_keys=True)
print(s["funnel"]["eligible"], s["funnel"]["unresolved"], s["funnel"]["excluded"], len(rows), "ext-ids:", len(ext))
