"""Score coverage arms against the frozen reference (prereg f74e020)."""

import json
import re
import sys
from collections import Counter
from pathlib import Path

STUDY = Path(__file__).resolve().parent


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def load_arm(run_dir: Path) -> dict:
    r = json.loads((run_dir / "result.json").read_text())
    gates = {g["subject_id"]: g["disposition"] for g in r["gate_evaluations"]}
    low = set(r.get("low_support_asset_ids") or [])
    cands = {}
    for c in r["candidates"]:
        keys = {norm(c["canonical_name"])} | {norm(a) for a in c.get("aliases") or []}
        cands[c["asset_id"]] = {
            "name": c["canonical_name"],
            "keys": {k for k in keys if len(k) >= 3},
            "disposition": gates.get(c["asset_id"], "NONE"),
            "low_support": c["asset_id"] in low,
            "confirmed": sorted(
                a.get("canonical_target_id") for a in c.get("target_assertions") or []
                if a.get("status") == "CONFIRMED_TARGET"
            ),
        }
    docs = Counter(d.get("publisher") for d in r["source_documents"])
    return {"candidates": cands, "documents": dict(docs), "n_docs": len(r["source_documents"]),
            "mentions": len(r.get("identity_mentions") or [])}


def match(entry: dict, cands: dict) -> list[dict]:
    names = {norm(n) for n in [entry["name"], *entry.get("aliases", [])]}
    names = {n for n in names if len(n) >= 3}
    return [c for c in cands.values() if c["keys"] & names]


def main(out: Path, *arms: str) -> None:
    ref = json.loads((STUDY / "reference_frozen.json").read_text())["entries"]
    report = {}
    for spec in arms:
        label, path = spec.split("=", 1)
        arm = load_arm(Path(path))
        rows = []
        for e in ref:
            hits = match(e, arm["candidates"])
            rows.append({
                "ref_id": e["ref_id"], "name": e["name"], "label": e["label"],
                "fully_verified": e["fully_verified"],
                "found": bool(hits),
                "dispositions": sorted({h["disposition"] for h in hits}),
                "low_support": any(h["low_support"] for h in hits),
                "engine_names": sorted({h["name"] for h in hits})[:4],
            })
        report[label] = {
            "documents": arm["n_docs"], "documents_by_publisher": arm["documents"],
            "mentions": arm["mentions"], "candidates": len(arm["candidates"]),
            "fully_verified_relevant_found": [r["name"] for r in rows if r["fully_verified"] and r["found"]],
            "any_relevant_found": [r["name"] for r in rows if r["label"] == "RELEVANT_INVESTIGATIONAL" and r["found"]],
            "comparators_found": [r["name"] for r in rows if r["label"] == "APPROVED_COMPARATOR" and r["found"]],
            "comparators_eligible": [r["name"] for r in rows if r["label"] == "APPROVED_COMPARATOR" and "ELIGIBLE" in r["dispositions"]],
            "wrong_target_or_modality_not_excluded": [
                r["name"] for r in rows
                if r["label"] == "WRONG_TARGET_OR_MODALITY" and r["found"] and r["dispositions"] != ["EXCLUDED"]
            ],
            "eligible_total": sum(1 for c in arm["candidates"].values() if c["disposition"] == "ELIGIBLE"),
            "rows": rows,
        }
    names = list(report)
    if len(names) >= 2:
        a, b = report[names[0]], report[names[1]]
        report["delta"] = {
            "documents": b["documents"] - a["documents"],
            "mentions": b["mentions"] - a["mentions"],
            "candidates": b["candidates"] - a["candidates"],
            "new_fully_verified_relevant": sorted(set(b["fully_verified_relevant_found"]) - set(a["fully_verified_relevant_found"])),
            "lost_fully_verified_relevant": sorted(set(a["fully_verified_relevant_found"]) - set(b["fully_verified_relevant_found"])),
        }
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    for k, v in report.items():
        print(k, json.dumps({x: v[x] for x in v if x != "rows" and x != "documents_by_publisher"}, ensure_ascii=False))


if __name__ == "__main__":
    main(Path(sys.argv[1]), *sys.argv[2:])
