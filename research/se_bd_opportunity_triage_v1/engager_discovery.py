"""Discovery check: does the frozen MINT5 (CD19+BCMA, autoimmune) run contain antibody-class
candidates attributed to CD19 or TNFRSF17? Reads result.json only; no rule depends on drug names."""

import json
import sys
from collections import Counter
from pathlib import Path

REQUESTED = {"TARGET:CD19", "TARGET:TNFRSF17"}


def main(run: str, out: Path) -> None:
    result = json.loads((Path.home() / "se_runs" / run / "result.json").read_text())
    rows = []
    for c in result["candidates"]:
        confirmed = {
            a.get("canonical_target_id") for a in c.get("target_assertions") or []
            if a.get("status") == "CONFIRMED_TARGET"
        } & REQUESTED
        rows.append({
            "name": c["canonical_name"],
            "authority_modality": c.get("authority_modality"),
            "confirmed": sorted(confirmed),
            "both": confirmed == REQUESTED,
        })
    antibody = [r for r in rows if r["authority_modality"] and "ANTIBOD" in str(r["authority_modality"]).upper()]
    summary = {
        "run": run,
        "candidates": len(rows),
        "authority_modality_counts": dict(Counter(str(r["authority_modality"]) for r in rows).most_common()),
        "confirmed_any_requested": sum(bool(r["confirmed"]) for r in rows),
        "confirmed_both": [r["name"] for r in rows if r["both"]],
        "antibody_class_confirmed_requested": sorted({r["name"] for r in antibody if r["confirmed"]}),
    }
    out.write_text(json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
