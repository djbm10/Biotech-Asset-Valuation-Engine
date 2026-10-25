"""DEVELOPMENT: per-candidate attribution audit between two GUCY2C dev replays.

    python research/se_gucy2c_dev_v3/attribution_audit.py BEFORE/result.json AFTER/result.json OUT.json

For every candidate visible in either run, and every candidate whose target or modality
changed, records: route, area-gate status, asset-specific and document-context areas,
modality (candidate and authority), and targets, before and after.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROUTES = [("eligible_asset_ids", "ELIGIBLE"), ("unresolved_asset_ids", "REVIEW"),
          ("excluded_asset_ids", "EXCLUDED"), ("low_support_asset_ids", "LOW_SUPPORT")]


def view(path: str) -> dict[str, dict]:
    r = json.loads(Path(path).read_text())
    route = {i: lab for key, lab in ROUTES for i in r[key]}
    gates = {g["subject_id"]: g["decisions"] for g in r["gate_evaluations"]}
    facts: dict[str, list] = {}
    for f in r["facts"]:
        facts.setdefault(f["subject_id"], []).append(f)
    out = {}
    for c in r["candidates"]:
        a = c["asset_id"]
        fs = facts.get(a, [])
        ta = next((d["status"] for d in gates.get(a, []) if d["requirement_id"] == "strategy.therapeutic_area"), None)
        out[c["canonical_name"]] = {
            "route": route.get(a), "ta_gate": ta, "targets": c["target_ids"],
            "modality": c["modality_id"], "authority_modality": c["authority_modality"],
            "asset_areas": sorted({f["value"] for f in fs if f["fact_type"] == "therapeutic_area"}),
            "context_areas": sorted({f["value"] for f in fs if f["fact_type"] == "document_therapeutic_area"}),
            "trials": len(c["trial_ids"]),
        }
    return out


def main() -> None:
    before, after = view(sys.argv[1]), view(sys.argv[2])
    visible = {"ELIGIBLE", "REVIEW"}
    names = sorted(n for n in after if after[n]["route"] in visible or before.get(n, {}).get("route") in visible)
    rows = {n: {"before": before.get(n), "after": after[n]} for n in names}
    target_changes = [n for n in after if n in before and before[n]["targets"] != after[n]["targets"]]
    modality_changes = {n: (before[n]["modality"], after[n]["modality"]) for n in after
                        if n in before and before[n]["modality"] != after[n]["modality"]}
    summary = {
        "visible_before": sum(before[n]["route"] in visible for n in before),
        "visible_after": sum(after[n]["route"] in visible for n in after),
        "target_changes": target_changes,
        "modality_changes_count": len(modality_changes),
        "modality_changes_to_none": sum(1 for b, a in modality_changes.values() if a is None),
        "modality_changes_other": {n: v for n, v in modality_changes.items() if v[1] is not None},
        "visible_modality_changes": {n: modality_changes[n] for n in names if n in modality_changes},
    }
    Path(sys.argv[3]).write_text(json.dumps({"summary": summary, "visible": rows}, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    for n in names:
        b, a = before.get(n) or {}, after[n]
        print(f"{n[:30]:30} {b.get('route')!s:9}->{a['route']:9} ta {b.get('ta_gate')}->{a['ta_gate']} "
              f"asset{a['asset_areas']} ctx{a['context_areas']} mod {b.get('modality')}->{a['modality']}")


if __name__ == "__main__":
    main()
