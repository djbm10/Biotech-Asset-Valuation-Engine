"""Score the therapeutic-area gate fix against ``docs/se_policies/ta_gate_semantics.md``.

Usage::

    PYTHONPATH=src python3 scripts/se_ta_gate_compare.py <frozen_run_dir> <replay_run_dir> <AREA>

Reads two ``result.json`` files and re-derives no gate. ``AREA`` is the canonical area the arm
requested (``ONCOLOGY`` for ``tac01_control_a1``, ``AUTOIMMUNE`` for ``mint5_on``). Prints
the declared criteria A1–A5 (A1 and A2 are the single "requested-area assets never FAIL"
check, applied per arm) and the declared predictions.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

TA = "strategy.therapeutic_area"
FROZEN_ONCOLOGY = "oncology"


def _load(directory: Path) -> dict:
    return json.loads((directory / "result.json").read_text())


def _decisions(raw: dict) -> dict[str, dict[str, str]]:
    return {
        e["subject_id"]: {d["requirement_id"]: d["status"] for d in e["decisions"]}
        for e in raw["gate_evaluations"]
    }


def _dispositions(raw: dict) -> dict[str, str]:
    return {e["subject_id"]: e["disposition"] for e in raw["gate_evaluations"]}


def _areas(raw: dict) -> dict[str, set[str]]:
    areas: dict[str, set[str]] = {}
    for fact in raw["facts"]:
        if fact["fact_type"] != "therapeutic_area":
            continue
        values = fact["value"] if isinstance(fact["value"], list) else [fact["value"]]
        areas.setdefault(fact["subject_id"], set()).update(values)
    return areas


def _visible(raw: dict) -> set[str]:
    hidden = set(raw["excluded_asset_ids"]) | set(raw["low_support_asset_ids"] or ())
    return {c["asset_id"] for c in raw["candidates"]} - hidden


def _poc_pass(raw: dict) -> set[str]:
    return {
        subject for subject, d in _decisions(raw).items() if d.get("evidence.human_poc") == "PASS"
    }


def _verdict(name: str, ok: bool, detail: str) -> bool:
    print(f"  {name:4} {'PASS' if ok else 'FAIL'}  {detail}")
    return ok


def compare(frozen_dir: Path, replay_dir: Path, area: str) -> bool:
    frozen, replay = _load(frozen_dir), _load(replay_dir)
    before, after = _decisions(frozen), _decisions(replay)
    names = {c["asset_id"]: c["canonical_name"] for c in replay["candidates"]}
    print(f"\n=== {frozen_dir.name} -> {replay_dir.name}  (requested {area})")

    frozen_ids = {c["asset_id"] for c in frozen["candidates"]}
    replay_ids = {c["asset_id"] for c in replay["candidates"]}
    frozen_low = set(frozen["low_support_asset_ids"] or ())
    replay_low = set(replay["low_support_asset_ids"] or ())
    print(f"  candidates {len(frozen_ids)} -> {len(replay_ids)}"
          f"  (only frozen {len(frozen_ids - replay_ids)}, only replay {len(replay_ids - frozen_ids)})")
    print(f"  low support {len(frozen_low)} -> {len(replay_low)}"
          f"  (symmetric difference {len(frozen_low ^ replay_low)})")

    for label, raw in (("before", before), ("after", after)):
        counts = Counter(d.get(TA, "absent") for d in raw.values())
        print(f"  TA {label:6} {dict(sorted(counts.items()))}")

    ok = True
    # A1 / A2: an asset whose evidence supports the requested area never FAILs.
    areas_after = _areas(replay)
    supported = {s for s, a in areas_after.items() if area in a}
    wrong = sorted(names.get(s, s) for s in supported if after.get(s, {}).get(TA) == "FAIL")
    passes = sum(1 for d in after.values() if d.get(TA) == "PASS")
    ok &= _verdict(
        "A1/2", not wrong and passes > 0,
        f"{len(supported)} assets support {area}; FAIL among them {len(wrong)} {wrong[:5]}; "
        f"TA PASS {passes}",
    )

    # A3: isolation. Every non-TA decision unchanged on the shared population.
    shared = frozen_ids & replay_ids
    moved = Counter()
    for subject in shared:
        b, a = before.get(subject, {}), after.get(subject, {})
        for requirement in (set(b) | set(a)) - {TA}:
            if b.get(requirement) != a.get(requirement):
                moved[requirement] += 1
    same_population = frozen_ids == replay_ids and frozen_low == replay_low
    ok &= _verdict(
        "A3", not moved and same_population,
        f"non-TA decisions changed {dict(moved)}; identical candidate+low-support sets "
        f"{same_population}",
    )

    # A4: oncology conservation.
    areas_before = _areas(frozen)
    onc_before = {s for s, a in areas_before.items() if FROZEN_ONCOLOGY in a}
    onc_after = {s for s, a in areas_after.items() if "ONCOLOGY" in a}
    lost = sorted(names.get(s, s) for s in (onc_before - onc_after) & shared)
    added = sorted(names.get(s, s) for s in onc_after - onc_before)
    ok &= _verdict(
        "A4", not lost,
        f"ONCOLOGY assets {len(onc_before)} -> {len(onc_after)}; lost {len(lost)} {lost[:5]}; "
        f"added {len(added)} {added[:10]}",
    )

    # A5: no disposition change without a TA decision change.
    disp_b, disp_a = _dispositions(frozen), _dispositions(replay)
    changed = [s for s in shared if disp_b.get(s) != disp_a.get(s)]
    unexplained = [
        names.get(s, s) for s in changed
        if before.get(s, {}).get(TA) == after.get(s, {}).get(TA)
    ]
    ok &= _verdict(
        "A5", not unexplained,
        f"disposition changes {len(changed)}; without a TA change {len(unexplained)} {unexplained[:5]}",
    )

    print("  -- predictions (reported, not criteria)")
    transitions = Counter((disp_b.get(s), disp_a.get(s)) for s in changed)
    print(f"  disposition transitions {dict(transitions)}")
    vis_b, vis_a = _visible(frozen), _visible(replay)
    print(f"  visible {len(vis_b)} -> {len(vis_a)}")
    poc_b, poc_a = _poc_pass(frozen) & vis_b, _poc_pass(replay) & vis_a
    print(f"  human-PoC PASS on the visible path {len(poc_b)} -> {len(poc_a)}"
          f"  new {sorted(names.get(s, s) for s in poc_a - poc_b)}")
    released = sorted(
        names.get(s, s) for s in changed
        if disp_b.get(s) == "EXCLUDED" and disp_a.get(s) != "EXCLUDED"
    )
    print(f"  left EXCLUDED ({len(released)}): {released[:40]}")
    still = Counter(
        requirement
        for s in shared
        if disp_a.get(s) == "EXCLUDED"
        for requirement, status in after.get(s, {}).items()
        if status == "FAIL"
    )
    print(f"  FAILs among still-EXCLUDED {dict(still.most_common())}")
    print(f"  VERDICT {'ALL CRITERIA PASS' if ok else 'CRITERIA FAILED'}")
    return ok


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    return 0 if compare(Path(argv[0]), Path(argv[1]), argv[2]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
