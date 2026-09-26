"""Score the indication-gate fix against ``docs/se_policies/indication_gate_semantics.md``.

Usage::

    PYTHONPATH=src python3 scripts/se_indication_gate_compare.py <baseline_run_dir> <replay_run_dir> tac01
    PYTHONPATH=src python3 scripts/se_indication_gate_compare.py <baseline_run_dir> <replay_run_dir> mint5

Reads two ``result.json`` (and ``problem.yaml``) files and re-derives no gate. The lexicon
below is a verbatim copy of the declaration's, kept independent of the engine code so the
scorer cannot drift with the implementation. ``tac01`` scores B1–B4; ``mint5`` scores B5.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

IND = "strategy.indication"
B1_RECORDS = (
    "Axicabtagene Ciloleucel",
    "Tisagenlecleucel",
    "Lisocabtagene Maraleucel",
    "Brexucabtagene Autoleucel",
    "TAC01",
)
MATCH = (
    "b cell lymphoma", "lymphoma b cell", "b cell non hodgkin", "b cell nhl", "b nhl",
    "large b cell", "dlbcl", "lbcl", "follicular lymphoma", "lymphoma follicular",
    "mantle cell lymphoma", "lymphoma mantle cell", "marginal zone lymphoma",
    "lymphoma marginal zone", "malt lymphoma", "burkitt", "primary mediastinal", "pmbcl",
    "small lymphocytic lymphoma", "high grade b cell", "hgbl", "transformed follicular",
)
BROADER = (
    "lymphoma", "non hodgkin", "nhl", "lymphoproliferative", "hematologic malignan",
    "hematological malignan", "haematolog", "b cell malignan", "b cell neoplasm",
)


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^0-9a-z]+", " ", text.casefold()).split())


def _has(text: str, term: str) -> bool:
    # Terms ending in a stem ("malignan", "haematolog") match a word prefix.
    tail = r"" if term.endswith(("malignan", "haematolog")) else r"\b"
    return re.search(rf"\b{re.escape(term)}{tail}", _norm(text)) is not None


def _load(directory: Path) -> dict:
    return json.loads((directory / "result.json").read_text())


def _indications(directory: Path) -> list[str]:
    problem = yaml.safe_load((directory / "problem.yaml").read_text())
    return list(problem["strategic_gap"].get("indications") or [])


def _decisions(raw: dict) -> dict[str, dict[str, str]]:
    return {
        e["subject_id"]: {d["requirement_id"]: d["status"] for d in e["decisions"]}
        for e in raw["gate_evaluations"]
    }


def _dispositions(raw: dict) -> dict[str, str]:
    return {e["subject_id"]: e["disposition"] for e in raw["gate_evaluations"]}


def _facts(raw: dict) -> set[tuple]:
    return {
        (f["fact_id"], f["subject_id"], f["fact_type"], json.dumps(f["value"], sort_keys=True))
        for f in raw["facts"]
    }


def _condition_strings(raw: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for fact in raw["facts"]:
        if fact["fact_type"] == "indication":
            out.setdefault(fact["subject_id"], []).append(str(fact["value"]))
    return out


def _attempts(raw: dict) -> list[tuple]:
    return sorted((a["source"], a["query"], a.get("pass_number")) for a in raw["search_attempts"])


def _visible(raw: dict) -> set[str]:
    hidden = set(raw["excluded_asset_ids"]) | set(raw["low_support_asset_ids"] or ())
    return {c["asset_id"] for c in raw["candidates"]} - hidden


def _verdict(name: str, ok: bool, detail: str) -> bool:
    print(f"  {name:3} {'PASS' if ok else 'FAIL'}  {detail}")
    return ok


def _isolation(frozen: dict, replay: dict, before, after) -> tuple[bool, set[str]]:
    frozen_ids = {c["asset_id"] for c in frozen["candidates"]}
    replay_ids = {c["asset_id"] for c in replay["candidates"]}
    same_pop = frozen_ids == replay_ids and set(frozen["low_support_asset_ids"] or ()) == set(
        replay["low_support_asset_ids"] or ()
    )
    same_facts = _facts(frozen) == _facts(replay)
    same_attempts = _attempts(frozen) == _attempts(replay)
    moved = Counter()
    for subject in frozen_ids & replay_ids:
        b, a = before.get(subject, {}), after.get(subject, {})
        for requirement in (set(b) | set(a)) - {IND}:
            if b.get(requirement) != a.get(requirement):
                moved[requirement] += 1
    ok = _verdict(
        "B3", same_pop and same_facts and same_attempts and not moved,
        f"same candidate+low-support {same_pop}; same facts {same_facts}; "
        f"same search attempts {same_attempts}; non-indication decisions changed {dict(moved)}",
    )
    return ok, frozen_ids & replay_ids


def compare_tac01(frozen_dir: Path, replay_dir: Path) -> bool:
    frozen, replay = _load(frozen_dir), _load(replay_dir)
    before, after = _decisions(frozen), _decisions(replay)
    disp_b, disp_a = _dispositions(frozen), _dispositions(replay)
    names = {c["asset_id"]: c["canonical_name"] for c in replay["candidates"]}
    low_a = set(replay["low_support_asset_ids"] or ())
    print(f"\n=== {frozen_dir.name} -> {replay_dir.name}  (TAC01)")
    print(f"  indications {_indications(frozen_dir)} -> {_indications(replay_dir)}")
    for label, raw in (("before", before), ("after", after)):
        counts = Counter(d.get(IND, "absent") for d in raw.values())
        print(f"  {IND} {label:6} {dict(sorted(counts.items()))}")

    ok = True
    # B1: recovery for the right reason.
    by_name: dict[str, list[str]] = {}
    for subject, name in names.items():
        by_name.setdefault(name.casefold(), []).append(subject)
    b1_rows = []
    for record in B1_RECORDS:
        subjects = by_name.get(record.casefold(), [])
        good = bool(subjects) and all(
            disp_a.get(s) != "EXCLUDED"
            and s not in low_a
            and after.get(s, {}).get(IND) == "PASS"
            and {k: v for k, v in before.get(s, {}).items() if k != IND}
            == {k: v for k, v in after.get(s, {}).items() if k != IND}
            for s in subjects
        )
        b1_rows.append(good)
        detail = [(disp_a.get(s), after.get(s, {}).get(IND)) for s in subjects] or "MISSING"
        print(f"       {record:28} {'ok ' if good else 'BAD'} {detail}")
    ok &= _verdict("B1", all(b1_rows), f"{sum(b1_rows)}/{len(B1_RECORDS)} reference records recovered")

    # B2: no leak, mechanical + listed review.
    conditions = _condition_strings(replay)
    loosened = [
        s for s in after
        if before.get(s, {}).get(IND) == "FAIL" and after[s].get(IND) in ("PASS", "UNKNOWN")
    ]
    unexplained = [
        names.get(s, s) for s in loosened
        if not any(_has(c, t) for c in conditions.get(s, []) for t in (*MATCH, *BROADER))
    ]
    ok &= _verdict(
        "B2", not unexplained,
        f"FAIL->PASS/UNKNOWN {len(loosened)}; without a lexicon term {len(unexplained)} "
        f"{unexplained[:10]}",
    )
    match_strings = sorted({
        c for s, a in after.items() if a.get(IND) == "PASS"
        for c in conditions.get(s, []) if any(_has(c, t) for t in MATCH)
    })
    print(f"  B2 review list: {len(match_strings)} distinct MATCH condition strings")
    for c in match_strings:
        print(f"       | {c}")

    iso_ok, shared = _isolation(frozen, replay, before, after)
    ok &= iso_ok

    # B4: every disposition change coincides with an indication status change.
    changed = [s for s in shared if disp_b.get(s) != disp_a.get(s)]
    stray = [names.get(s, s) for s in changed if before.get(s, {}).get(IND) == after.get(s, {}).get(IND)]
    ok &= _verdict("B4", not stray, f"disposition changes {len(changed)}; without an indication change {len(stray)} {stray[:5]}")

    print("  -- predictions (reported, not criteria)")
    print(f"  disposition transitions {dict(Counter((disp_b.get(s), disp_a.get(s)) for s in changed))}")
    vis_b, vis_a = _visible(frozen), _visible(replay)
    trial = {s for s, c in conditions.items() if c}
    print(f"  visible {len(vis_b)} -> {len(vis_a)}; visible with an indication fact "
          f"{len(vis_b & trial)} -> {len(vis_a & trial)}")
    released = sorted(names.get(s, s) for s in changed if disp_b.get(s) == "EXCLUDED")
    print(f"  released from EXCLUDED ({len(released)}): {released[:60]}")
    still = Counter(
        r for s in shared if disp_a.get(s) == "EXCLUDED"
        for r, status in after.get(s, {}).items() if status == "FAIL"
    )
    print(f"  FAILs among still-EXCLUDED {dict(still.most_common())}")
    print(f"  VERDICT {'ALL CRITERIA PASS' if ok else 'CRITERIA FAILED'}")
    return ok


def compare_mint5(frozen_dir: Path, replay_dir: Path) -> bool:
    frozen, replay = _load(frozen_dir), _load(replay_dir)
    before, after = _decisions(frozen), _decisions(replay)
    print(f"\n=== {frozen_dir.name} -> {replay_dir.name}  (mint5)")
    ind_b, ind_a = _indications(frozen_dir), _indications(replay_dir)
    same_decisions = before == after
    same_disp = _dispositions(frozen) == _dispositions(replay)
    ok = _verdict(
        "B5", ind_b == [] and ind_a == [] and same_decisions and same_disp,
        f"indications {ind_b} -> {ind_a}; identical decisions {same_decisions}; "
        f"identical dispositions {same_disp}",
    )
    iso_ok, _ = _isolation(frozen, replay, before, after)
    ok &= iso_ok
    print(f"  VERDICT {'ALL CRITERIA PASS' if ok else 'CRITERIA FAILED'}")
    return ok


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[2] not in ("tac01", "mint5"):
        print(__doc__)
        return 2
    compare = compare_tac01 if argv[2] == "tac01" else compare_mint5
    return 0 if compare(Path(argv[0]), Path(argv[1])) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
