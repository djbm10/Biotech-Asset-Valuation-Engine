"""Mechanical scoring of workflow calls against the frozen reference (cycle C1). INTERNAL DEVELOPMENT.

Usage: python score.py [run_dir ...]  (default: runs/A_spreadsheet runs/B_general runs/C_dealscreen)
Writes scores.json next to this file. The critic's evidence-based review is separate.
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ref = {r["program_id"]: r for r in csv.DictReader((HERE / "reference/reference_calls.csv").open())}
TOP = {k for k, r in ref.items() if r["transaction_attractiveness"] in ("HIGH", "MEDIUM")}


def groups(rows: dict, key: str) -> dict:
    g = defaultdict(set)
    for pid, r in rows.items():
        if (r.get(key) or "").strip():
            g[r[key].strip().casefold()].add(pid)
    return {k: v for k, v in g.items() if len(v) > 1}


def score(run: Path, call_col: str = "scientific_call") -> dict:
    calls = {r["program_id"]: r for r in csv.DictReader((run / "calls.csv").open())}
    tool_words = {"ELIGIBLE": "IN", "EXCLUDED": "OUT"}  # the tool's labels (critic fix)

    def c(p):  # noqa: E306
        value = (calls.get(p, {}).get(call_col) or "").strip().upper()
        return tool_words.get(value, value)
    ref_in = [p for p, r in ref.items() if r["scientific_call"] == "IN"]
    ref_out = [p for p, r in ref.items() if r["scientific_call"] == "OUT"]
    short = {p: int(r["shortlist_rank"]) for p, r in calls.items() if (r.get("shortlist_rank") or "").strip().isdigit()}
    ref_groups = groups(ref, "identity_group")
    run_groups = groups(calls, "identity_group")
    split = [sorted(g) for g in ref_groups.values()
             if not any(g <= rg for rg in run_groups.values())]
    contradictory = [sorted(g) for g in ref_groups.values() if len({c(p) for p in g}) > 1]
    wrong_merge = [sorted(rg) for rg in run_groups.values()
                   if not any(rg <= g for g in ref_groups.values())]
    unsupported_avail = [p for p, r in calls.items() if (r.get("availability") or "").upper().startswith("EVIDENCED_AVAILABLE")]
    def held(p):  # noqa: E306
        return ref[p]["availability"].startswith("HELD_BY_LARGE_PHARMA")
    short_crit = {p: [w for w, bad in (("reference OUT", ref[p]["scientific_call"] == "OUT"),
                                       ("rights held by large pharma", held(p)),
                                       ("marketed", ref[p]["marketing_status"].upper().startswith("US")))
                      if bad] for p in short}
    seen, dupes = set(), []
    for p in sorted(short, key=short.get):
        grp = ref[p]["identity_group"].strip().casefold()
        if grp and grp in seen:
            dupes.append(p)
        seen.add(grp)
    return {
        "reference_IN_found": sum(c(p) == "IN" for p in ref_in), "reference_IN_total": len(ref_in),
        "wrong_exclusions": sorted(p for p in ref_in if c(p) == "OUT"),
        "reference_IN_unresolved": sorted(p for p in ref_in if c(p) not in ("IN", "OUT")),
        "wrong_inclusions": sorted(p for p in ref_out if c(p) == "IN"),
        "identity_groups_split": split, "identity_contradictory_calls": contradictory,
        "identity_wrong_merges": wrong_merge,
        "availability_asserted": unsupported_avail,
        "shortlist": [p for p in sorted(short, key=short.get)],
        "shortlist_critical": {p: v for p, v in short_crit.items() if v},
        "shortlist_same_molecule_twice": dupes,
        "shortlist_overlap_reference_top": sorted(set(short) & TOP), "reference_top_size": len(TOP),
    }


runs = sys.argv[1:] or ["runs/A_spreadsheet", "runs/B_general", "runs/C_dealscreen"]
out = {r: score(HERE / r) for r in runs}
if (HERE / "runs/C_dealscreen/calls.csv").exists() and "runs/C_dealscreen" in runs:
    out["runs/C_dealscreen [tool, with analyst target map]"] = score(HERE / "runs/C_dealscreen", "tool_disposition")
    out["runs/C_dealscreen [tool, as installed]"] = score(HERE / "runs/C_dealscreen",
                                                           "tool_disposition_without_target_map")
(HERE / "scores.json").write_text(json.dumps(out, indent=1))
for k, v in out.items():
    crit = (len(v["wrong_exclusions"]) + len(v["shortlist_critical"]) + len(v["availability_asserted"])
            + len(v["shortlist_same_molecule_twice"]))
    print(f"{k}: IN {v['reference_IN_found']}/{v['reference_IN_total']}, wrong-excl {len(v['wrong_exclusions'])}, "
          f"unres {len(v['reference_IN_unresolved'])}, wrong-incl {len(v['wrong_inclusions'])}, id-split "
          f"{len(v['identity_groups_split'])}, id-contradict {len(v['identity_contradictory_calls'])}, "
          f"short-crit {len(v['shortlist_critical'])}, avail-asserted {len(v['availability_asserted'])}, "
          f"top-overlap {len(v['shortlist_overlap_reference_top'])}/{v['reference_top_size']}, critical(screen+short) {crit}")
