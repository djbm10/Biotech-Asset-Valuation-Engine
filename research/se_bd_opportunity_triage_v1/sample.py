"""Freeze the BD triage reference sample (mechanical rule, applied before any triage logic).

Rule: for each demo run, the first 15 reviewable shortlist entries plus the first 10 deferred
(low-support) entries, in the shortlist's own declared order. No name-based selection.
"""

import json
import sys
from pathlib import Path

RUNS = {"cd19_cell_therapy_bcl": "tac01_protoid_v1", "cd19_bcma_dual_autoimmune": "mint5_protoid_v1"}


def main(out: Path) -> None:
    rows = []
    for demo, run in RUNS.items():
        sl = json.loads((Path.home() / "se_runs" / run / "shortlist.json").read_text())
        for section, entries in (("shown", sl["entries"][:15]), ("deferred", sl["deferred"][:10])):
            for e in entries:
                facts = {f["label"]: f for f in e["facts"]}
                rows.append({
                    "sample_id": f"{demo}:{section}:{e['position']}",
                    "demo": demo,
                    "run": run,
                    "section": section,
                    "asset_id": e["asset_id"],
                    "name": e["name"],
                    "target_status": e["target_status"],
                    "authority_modality_note": facts.get("Authority modality", {}).get("note"),
                    "sponsors": facts.get("Company", {}).get("value"),
                    "stage": facts.get("Phase", {}).get("value"),
                    "trials": sorted({c["native_id"] for c in facts.get("Phase", {}).get("citations", []) if c.get("native_id")})[:5],
                })
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    print(len(rows))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
