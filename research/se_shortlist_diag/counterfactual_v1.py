"""Read-only measurements for SHORTLIST_NONPRODUCT_OFFTARGET_DIAGNOSIS v1 (no behaviour change).

M1  How D/A rows relate to the drug authority (resolved with edges / resolved without / unresolved).
M2  Excluded assets whose ONLY failing requirement is strategy.indication, split by target gate,
    and how many of those carry an indication condition containing every content word of the
    query's disease phrase (a crude, reported-only plausibility check, not a proposed rule).
M3  Rows whose target gate is PASS but which rank below a target-UNKNOWN row (ranking key order).
"""

import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = {"H2": "v1", "H4": "v1", "H11": "v3", "H12": "v3", "H13": "v3", "H14": "v3"}
DISEASE_WORDS = {  # content words of each frozen query's disease phrase (read from the query text)
    "H2": ["lung"], "H4": ["ulcerative", "colitis"], "H11": ["lung"],
    "H12": ["paroxysmal", "hemoglobinuria"], "H13": ["hidradenitis"], "H14": ["myeloma"],
}


def norm(t):
    return " ".join(re.sub(r"[^0-9a-z]+", " ", t.casefold()).split())


def main():
    rows = json.loads((HERE / "classified_v1.json").read_text())
    out = {}
    for q, ver in RUNS.items():
        run = Path.home() / f"se_runs/heldout_{q.lower()}_{ver}"
        raw = json.loads((run / "result.json").read_text())
        problem_ind = [l.strip("- ").strip() for l in (run / "problem.yaml").read_text().split("indications:")[1].split("target_expression")[0].splitlines() if l.strip().startswith("-")]
        m1 = Counter()
        for r in rows[q]["rows"]:
            if r["class"] in ("A", "D"):
                m1[(r["class"], "resolved+edges" if r["auth"] else "resolved_no_edges" if r["drug"] else "unresolved")] += 1
        exc = set(raw["excluded_asset_ids"])
        gates = {g["subject_id"]: g for g in raw["gate_evaluations"]}
        conds = {}
        for f in raw["facts"]:
            if f["fact_type"] == "indication":
                vals = f["value"] if isinstance(f["value"], list) else [f["value"]]
                conds.setdefault(f["subject_id"], []).extend(str(v) for v in vals)
        only_ind = Counter(); plausible = Counter()
        for aid in exc:
            g = gates.get(aid)
            if not g:
                continue
            fails = {d["requirement_id"] for d in g["decisions"] if d["status"] == "FAIL"}
            if fails == {"strategy.indication"}:
                t = next((d["status"] for d in g["decisions"] if d["requirement_id"] == "target.expression"), None)
                only_ind[t] += 1
                if any(all(w in norm(c).split() for w in DISEASE_WORDS[q]) for c in conds.get(aid, [])):
                    plausible[t] += 1
        all_ind_fail = sum(1 for aid in exc if gates.get(aid) and any(d["requirement_id"] == "strategy.indication" and d["status"] == "FAIL" for d in gates[aid]["decisions"]))
        # M3
        seen_unknown = False; displaced = []
        for r in rows[q]["rows"]:
            if r["T"] == "PASS" and seen_unknown:
                displaced.append((r["pos"], r["name"], r["modality_match"]))
            if r["T"] != "PASS":
                seen_unknown = True
        out[q] = {"indication_requirement": problem_ind, "M1_A_D_vs_authority": {f"{k[0]}:{k[1]}": v for k, v in m1.items()},
                  "excluded_total": len(exc), "excluded_with_indication_FAIL": all_ind_fail,
                  "excluded_ONLY_indication_by_target_gate": dict(only_ind),
                  "of_which_condition_contains_query_disease_words": dict(plausible),
                  "M3_target_PASS_ranked_below_UNKNOWN": displaced}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
