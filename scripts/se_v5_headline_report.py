"""Score a paired live run against the class-terms v5 bar.

Usage::

    PYTHONPATH=src BVE_SE_ONTOLOGY_SNAPSHOT=data/se/ontology/current \
      python3 scripts/se_v5_headline_report.py <off_dir> <on_dir>

Reads only the run artifacts, so it can be re-run without touching the network. The seven
criteria are the ones frozen in ``docs/se_policies/class_terms_v5.md`` §5; the eighth section
is the break-out that Amendment B1.2 requires, kept separate precisely because the policy
declined to rule on it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bve.se.discovery.class_terms import individuating_residue, is_class_term
from bve.se.ontology.targets import normalize_target

#: Names that must keep their standing. `TAC01-CD19` is here because it is the single most
#: informative positive control for v5: it is a CAR-T against CD19 whose only individuating
#: token is a sponsor stem, so a rule that over-reaches takes it first.
FROZEN_POSITIVES = (
    "SYNCAR-001",
    "HB2198",
    "AMG 420",
    "ALLO-715",
    "ABBV-383",
    "gemcitabine",
    "pomalidomide",
    "teclistamab",
    "pembrolizumab",
    "belantamab mafodotin",
    "TAC01-CD19",
    "Descartes-08",
)

#: v4's twelve, which must stay off the default path, plus the two v5 exists to remove.
FROZEN_NEGATIVES = (
    "Placebo",
    "choice",
    "paper",
    "frontline",
    "bsAbs",
    "POD24",
    "equal",
    "nature",
    "roche",
    "saline",
    "search",
    "success",
    "CAR19",
    "CART19",
)

#: The targets this query is *about*. A resolved symbol in a name that is not one of these is
#: describing the construct rather than what it binds, which is B1.2's disputed subset. Taken
#: from the query rather than from the corpus, so it cannot be tuned by what the run returned.
QUERY_TARGETS = ("CD19", "BCMA", "TNFRSF17")


def _load(directory: str) -> dict:
    return json.loads((Path(directory) / "result.json").read_text())


def _view(result: dict) -> dict:
    low = set(result["low_support_asset_ids"])
    poc = {
        fact["subject_id"]
        for fact in result["facts"]
        if fact.get("fact_type") == "human_poc_present"
    }
    by_name: dict[str, dict] = {}
    for candidate in result["candidates"]:
        name = candidate.get("canonical_name") or ""
        by_name[name] = {
            "asset_id": candidate["asset_id"],
            "default": candidate["asset_id"] not in low,
            "reason": candidate.get("qualification_reason"),
            "poc": candidate["asset_id"] in poc,
            "trials": len(candidate.get("trial_ids") or []),
            "candidate": candidate,
        }
    return {
        "by_name": by_name,
        "default": [n for n, v in by_name.items() if v["default"]],
        "poc_names": sorted(n for n, v in by_name.items() if v["poc"]),
    }


def _disputed(name: str) -> bool:
    """Whether a class term individuates via a symbol that is not a query target."""

    query = {t.upper() for t in QUERY_TARGETS}
    query |= {normalize_target(t) or t.upper() for t in QUERY_TARGETS}
    for token in name.replace("/", " ").replace("-", " ").replace(".", " ").split():
        resolved = normalize_target(token)
        if resolved is None:
            continue
        if resolved.upper() not in query and token.upper() not in query:
            return True
    return False


def main(off_dir: str, on_dir: str) -> int:
    off, on = _view(_load(off_dir)), _view(_load(on_dir))
    failures: list[str] = []

    print(f"default path  off={len(off['default'])}  on={len(on['default'])}")
    print(f"human_poc     off={len(off['poc_names'])}  on={len(on['poc_names'])}")

    print("\n1/2. CAR19, CART19 and the v4 negatives: no default path, no PASS")
    for name in FROZEN_NEGATIVES:
        o, n = off["by_name"].get(name), on["by_name"].get(name)

        def fmt(v: dict | None) -> str:
            if v is None:
                return "absent"
            return f"{'default' if v['default'] else 'review'}/{v['reason'] or '-'}" + (
                " POC" if v["poc"] else ""
            )

        print(f"  {name:16} off: {fmt(o):46} on: {fmt(n)}")
        if n is not None and (n["default"] or n["poc"]):
            failures.append(f"§5.1/5.2 {name} is still default-path or holds a PASS")

    print("\n3. frozen positives must survive with an unchanged reason")
    for name in FROZEN_POSITIVES:
        o, n = off["by_name"].get(name), on["by_name"].get(name)
        if o is None and n is None:
            print(f"  {name:22} absent from both runs (not exercised)")
            continue
        o_reason = o["reason"] if o else None
        n_reason = n["reason"] if n else None
        ok = n is not None and n["default"] and o_reason == n_reason
        print(f"  {name:22} off: {o_reason}  on: {n_reason}  {'ok' if ok else 'CHANGED'}")
        if o is not None and o["default"] and not ok:
            failures.append(f"§5.3 {name} lost standing or changed reason")

    print("\n4. every demotion must be a class term (zero residue-bearing losses)")
    lost = sorted(set(off["default"]) - set(on["default"]))
    gained = sorted(set(on["default"]) - set(off["default"]))
    print(f"  lost {len(lost)}  gained {len(gained)}")
    wrongly = [n for n in lost if not is_class_term(n)]
    for name in wrongly:
        print(f"  NOT A CLASS TERM: {name!r} residue={individuating_residue(name)}")
        failures.append(f"§5.4 {name} was demoted but carries individuating residue")
    if gained:
        print("  unexpected gains:", gained)

    print("\n5. human_poc falls by exactly the class terms that held one")
    lost_poc = sorted(set(off["poc_names"]) - set(on["poc_names"]))
    gained_poc = sorted(set(on["poc_names"]) - set(off["poc_names"]))
    print(f"  withdrawn: {lost_poc}")
    print(f"  added:     {gained_poc}")
    for name in lost_poc:
        if not is_class_term(name):
            failures.append(f"§5.5 real asset {name} lost its human_poc PASS")
    print("\n  remaining PASSes:")
    for name in on["poc_names"]:
        flag = "  <-- CLASS TERM" if is_class_term(name) else ""
        print(f"    {name}{flag}")
        if is_class_term(name):
            failures.append(f"§5.2 class term {name} still holds a PASS")

    print("\n6. every default-path asset carries a reason")
    anonymous = [n for n in on["default"] if not on["by_name"][n]["reason"]]
    print(f"  anonymous admissions: {len(anonymous)}")
    if anonymous:
        failures.append(f"§5.6 {len(anonymous)} anonymous admissions")
    counts: dict[str, int] = {}
    for name in on["default"]:
        reason = on["by_name"][name]["reason"] or "NONE"
        counts[reason] = counts.get(reason, 0) + 1
    for reason, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"    {reason:34} {count}")

    print("\n7. B1.2 disputed subset -- armored / non-target-symbol constructs")
    disputed = [n for n in lost if is_class_term(n) and _disputed(n)]
    plain = [n for n in lost if is_class_term(n) and not _disputed(n)]
    print(f"  plain class descriptors demoted: {len(plain)}")
    print(f"  disputed (operator must rule):   {len(disputed)}")
    for name in sorted(disputed):
        print(f"    {name}  (trials {off['by_name'][name]['trials']})")

    print("\n" + ("FAIL" if failures else "PASS"))
    for failure in failures:
        print("  -", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
