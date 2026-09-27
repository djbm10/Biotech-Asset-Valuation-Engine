"""Score shortlist ranking v1 against ``docs/se_policies/ranking_lexicographic_v1.md``.

Usage::

    PYTHONPATH=src python3 scripts/se_ranking_v1_compare.py <run_dir> [<run_dir> ...]

Rebuilds each run's shortlist offline from ``result.json`` and checks R1–R3 against an
order re-derived here, independently of the shortlist code's key. Prints each top 20 for the
preregistered manual judgement (K1/K2), plus the positions of the reference records.
R4 is a unit test, not a run property.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from bve.se.pipeline import SESearchResult
from bve.se.schemas.contracts import TargetAssertionStatus

UNLIMITED = 10**9
TOP = 20
REFERENCE = {
    "tac01": (
        "Axicabtagene Ciloleucel", "Tisagenlecleucel", "Lisocabtagene Maraleucel",
        "Brexucabtagene Autoleucel", "TAC01",
    ),
    "mint5": (
        "GC012F", "AZD0120", "CNCT19", "Inaticabtagene autoleucel", "CABA-201", "RD06",
        "FKC289", "ICG318", "KN5501", "QT-019C", "BH2024", "IM19", "CM336", "HBI0101",
    ),
}
_TARGET_ORDER = {status.value: i for i, status in enumerate(TargetAssertionStatus)}
_DECISION_ORDER = {"PASS": 0, "UNKNOWN": 1}


def _independent_order(raw: dict, human_poc_required: bool) -> list[str]:
    hidden = set(raw["excluded_asset_ids"]) | set(raw["low_support_asset_ids"] or ())
    eligible = set(raw["eligible_asset_ids"])
    decisions = {
        e["subject_id"]: {d["requirement_id"]: d["status"] for d in e["decisions"]}
        for e in raw["gate_evaluations"]
    }
    poc_fact: set[str] = set()
    stage: dict[str, int] = {}
    for fact in raw["facts"]:
        if fact["contradicting_claim_ids"]:
            continue
        if fact["fact_type"] == "human_poc_present" and fact["value"] is True:
            poc_fact.add(fact["subject_id"])
        elif fact["fact_type"] == "development_stage_order":
            stage[fact["subject_id"]] = max(stage.get(fact["subject_id"], -1), int(fact["value"]))

    keys = []
    for asset in raw["candidates"]:
        subject = asset["asset_id"]
        if subject in hidden:
            continue
        d = decisions.get(subject, {})
        poc = d.get("evidence.human_poc") == "PASS" if human_poc_required else subject in poc_fact
        assertions = asset["target_assertions"]
        keys.append((
            0 if subject in eligible else 1,
            0 if poc else 1,
            -stage.get(subject, -1),
            _DECISION_ORDER.get(d.get("target.expression"), 2),
            _TARGET_ORDER[assertions[0]["status"]] if assertions else len(_TARGET_ORDER),
            -sum(1 for status in d.values() if status == "PASS"),
            asset["canonical_name"].casefold(),
            subject,
        ))
    return [key[-1] for key in sorted(keys)]


def _verdict(name: str, ok: bool, detail: str) -> bool:
    print(f"  {name:3} {'PASS' if ok else 'FAIL'}  {detail}")
    return ok


def score(run_dir: Path) -> bool:
    from bve.se.reporting.shortlist import build_shortlist

    raw = json.loads((run_dir / "result.json").read_text())
    problem = yaml.safe_load((run_dir / "problem.yaml").read_text())
    required = bool(((problem["strategic_gap"].get("evidence_floor") or {}).get("human_poc_required")))
    result = SESearchResult.model_validate(raw)
    first = build_shortlist(result, limit=UNLIMITED)
    second = build_shortlist(result, limit=UNLIMITED)
    names = {c["asset_id"]: c["canonical_name"] for c in raw["candidates"]}
    print(f"\n=== {run_dir.name}  (human_poc_required={required}, basis {first.ordering_basis})")

    ok = True
    built = [entry.asset_id for entry in first.entries]
    expected = _independent_order(raw, required)
    first_diff = next((i for i, (a, b) in enumerate(zip(built, expected)) if a != b), None)
    ok &= _verdict(
        "R1", built == expected,
        f"{len(built)} ranked; first divergence at {first_diff}"
        + (f" ({names.get(built[first_diff])} vs {names.get(expected[first_diff])})"
           if first_diff is not None else ""),
    )

    excluded = set(raw["excluded_asset_ids"])
    low = set(raw["low_support_asset_ids"] or ())
    visible = {c["asset_id"] for c in raw["candidates"]} - excluded - low
    band = getattr(first, "excluded", ())
    unnamed = [e.name for e in band if not e.review_reasons]
    ok &= _verdict(
        "R2", set(built) == visible
        and {e.asset_id for e in first.deferred} == low - excluded
        and {e.asset_id for e in band} == excluded and not unnamed,
        f"ranked==visible {set(built) == visible}; deferred==low-support "
        f"{ {e.asset_id for e in first.deferred} == low - excluded}; excluded band "
        f"{len(band)}/{len(excluded)}; excluded entries naming no FAIL {len(unnamed)}",
    )
    ok &= _verdict("R3", first.model_dump_json() == second.model_dump_json(), "two builds identical")

    print(f"  -- top {TOP} for manual judgement (K1/K2)")
    for entry in first.entries[:TOP]:
        print(f"     {entry.position:3} | {entry.name} | {entry.target_status}")
    arm = "tac01" if "tac01" in run_dir.name else "mint5"
    position = {names[a].casefold(): i for i, a in enumerate(built, start=1)}
    print("  -- reference positions (reported)")
    for record in REFERENCE[arm]:
        print(f"     {record:28} {position.get(record.casefold(), 'not ranked')}")
    print(f"  VERDICT R1-R3 {'PASS' if ok else 'FAILED'} (K1/K2 are judged by hand)")
    return ok


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    return 0 if all([score(Path(arg)) for arg in argv]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
