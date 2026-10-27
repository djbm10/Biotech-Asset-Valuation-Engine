"""Measure a demo run against the SYNTHETIC ground truth (never an application input).

Reports what happened. It is never used to tune criteria or fixtures, and synthetic
accuracy says nothing about real-world precision.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from bve.dealscreen.commercial import AVAILABLE, AVAILABLE_CONFIRMED
from bve.dealscreen.workspace import Workspace


def evaluate(
    ws: Workspace, ground_truth: str | Path, *, stage: str, after_research: bool = False
) -> dict[str, Any]:
    """``after_research`` scores against the truth once the public evidence has been confirmed."""
    truth = json.loads(Path(ground_truth).read_text(encoding="utf-8"))
    programs = truth["programs"]
    screens = ws.screening()["screens"]
    assets = {a.asset_id: a for a in ws.assets()}
    confusion: Counter[str] = Counter()
    false_exclusions, false_eligible, conservative = [], [], []
    for s in screens:
        ext = assets[s["asset_id"]].external_id
        key = "expected_after_confirmed_research" if after_research else "expected_disposition"
        expected = programs[ext][key]
        actual = s["disposition"]
        confusion[f"{expected}->{actual}"] += 1
        if actual == "EXCLUDED" and expected != "EXCLUDED":
            false_exclusions.append({"external_id": ext, "expected": expected, "archetype": programs[ext]["archetype"]})
        if actual == "ELIGIBLE" and expected != "ELIGIBLE":
            false_eligible.append({"external_id": ext, "expected": expected, "archetype": programs[ext]["archetype"]})
        if actual == "UNRESOLVED" and expected != "UNRESOLVED":
            conservative.append({"external_id": ext, "expected": expected, "archetype": programs[ext]["archetype"]})
    by_ext = {a.external_id: a.asset_id for a in assets.values()}
    merge_errors = [pair for pair in truth["must_not_merge"]
                    if len({by_ext.get(e) for e in pair}) < len(pair)]
    rights_violations = []
    for s in screens:
        status = s["commercial"]["us_rights_status"]
        if status in {AVAILABLE, AVAILABLE_CONFIRMED}:
            texts = [c.value_as_written for c in assets[s["asset_id"]].claims_for("us_rights")]
            if not any("available" in t.casefold() or "seeking" in t.casefold() for t in texts):
                rights_violations.append(s["asset_id"])
    matched = sum(v for k, v in confusion.items() if k.split("->")[0] == k.split("->")[1])
    log = ws.decision_log()
    return {
        "stage": stage,
        "label": "SYNTHETIC evaluation; not evidence of real-world accuracy",
        "programs_scored": len(screens),
        "disposition_agreement": f"{matched}/{len(screens)}",
        "confusion_expected_to_actual": dict(sorted(confusion.items())),
        "false_exclusions": false_exclusions,
        "false_eligible": false_eligible,
        "conservative_unresolved": conservative,
        "identity_merge_errors": merge_errors,
        "rights_available_without_explicit_statement": rights_violations,
        "manual_review_actions": dict(Counter(r["action"] for r in log.records)),
        "review_actions_by_reviewer_kind": dict(Counter(r["reviewer_kind"] for r in log.records)),
    }
