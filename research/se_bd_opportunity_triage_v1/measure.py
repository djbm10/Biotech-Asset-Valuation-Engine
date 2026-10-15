"""Score BD triage against the frozen independent adjudication (prereg db04327)."""

import json
import sys
from collections import Counter
from pathlib import Path

import yaml

from bve.se.reporting.bd_brief import build_bd_brief, load_run
from bve.se.reporting.bd_triage import ApprovalStatus, LabelSnapshot, TriageCategory

STUDY = Path(__file__).resolve().parent
ROOT = STUDY.parents[1]
RUNS = {"cd19_cell_therapy_bcl": "tac01_protoid_v1", "cd19_bcma_dual_autoimmune": "mint5_protoid_v1"}


def system_rows(labels):
    out = {}
    for demo, run in RUNS.items():
        ctx = yaml.safe_load((ROOT / "examples/se_bd" / f"{demo}.yaml").read_text())
        brief = build_bd_brief(load_run(Path.home() / "se_runs" / run), context=ctx, labels=labels)
        for section, cards in (("shown", brief.candidates), ("deferred", brief.held_back_cards)):
            for c in cards:
                out[f"{demo}:{section}:{c.position}"] = c
    return out


def main(out: Path) -> None:
    labels = LabelSnapshot.load(STUDY / "fda_label_snapshot.json")
    sample = {r["sample_id"]: r for r in json.loads((STUDY / "sample.json").read_text())}
    ref = {x["sample_id"]: x for x in json.loads((STUDY / "adjudication.json").read_text())["labels"]}
    sys_rows = system_rows(labels)
    assert set(sample) == set(ref) <= set(sys_rows), "sample/system mismatch"
    rows, confusion = [], Counter()
    for sid in sample:
        c, r = sys_rows[sid], ref[sid]
        got, want = c.triage.category.value, r["expected_category"]
        confusion[(want, got)] += 1
        rows.append({
            "sample_id": sid, "name": c.name, "system": got, "reference": want,
            "match": got == want, "worth": r["worth_external_research"],
            "system_us_label": c.triage.approval.value, "reference_us_approval": r["us_approval"],
        })
    named = TriageCategory.NAMED_INVESTIGATIONAL.value
    metrics = {
        "n": len(rows),
        "category_accuracy": sum(r["match"] for r in rows),
        "per_reference_category": {
            k: {"n": v, "correct": sum(1 for r in rows if r["reference"] == k and r["match"])}
            for k, v in sorted(Counter(r["reference"] for r in rows).items())
        },
        "unsupported_approval_claims": [
            r["sample_id"] for r in rows
            if r["system_us_label"] == ApprovalStatus.US_LABEL_FOUND.value and r["reference_us_approval"] != "APPROVED"
        ],
        "us_approvals_missed": [
            r["sample_id"] for r in rows
            if r["reference_us_approval"] == "APPROVED" and r["system_us_label"] != ApprovalStatus.US_LABEL_FOUND.value
        ],
        "ownership_claims": 0,
        "genuine_named_opportunities": {
            "reference": sum(1 for r in rows if r["reference"] == named and r["worth"] == "YES"),
            "surfaced_in_category_1": sum(1 for r in rows if r["reference"] == named and r["worth"] == "YES" and r["system"] == named),
        },
        "wrong_products_promoted_to_category_1": [r["sample_id"] for r in rows if r["system"] == named and r["reference"] != named],
        "academic_called_commercial_product": [
            r["sample_id"] for r in rows
            if r["reference"] == "ACADEMIC_CONSTRUCT" and r["system"] in (named, "APPROVED_REFERENCE")
        ],
        "confusion": {f"{w} -> {g}": n for (w, g), n in sorted(confusion.items())},
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "rows.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    (out / "metrics.json").write_text(json.dumps(metrics, indent=1, sort_keys=True) + "\n")
    print(json.dumps(metrics, indent=1, sort_keys=True))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
