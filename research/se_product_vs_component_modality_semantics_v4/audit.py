"""Execute the frozen v4 design (8ca2a76 + R3 policy 78c3694). Verdict derived by `criteria`."""

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research/se_product_vs_component_modality_semantics_v4"
V3 = ROOT / "research/se_product_vs_component_modality_semantics_v3"
ADJ = ROOT / "research/se_modality_product_description_coverage_v1/adjudication.json"
sys.path.insert(0, str(V3))
import audit as v3  # noqa: E402  (reuse v3 routing/categorization unchanged)

ADOPTED = {"APPOSITIVE"}
R3_POLICY = STUDY / "r3_policy.md"


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dispose(row):
    if row["conflict"]:
        return "UNKNOWN_CONFLICT"
    if row["category"] == "A_PRODUCT":
        return "RETAIN"
    return "UNKNOWN_REVIEW"


def measure():
    rows = [v3.categorize(r) for r in v3.measure_population()]
    for r in rows:
        r["disposition"] = dispose(r)
        r["key"] = f"{r['run']}|{r['fact_id']}"
    return rows


def criteria(rows, adjudication, policy_ok):
    adj = {k: v for k, v in adjudication.items() if not k.startswith("_")}
    tac = {r["fact_id"]: r for r in rows if r["run"] == "tac01_protoid_v1"}
    distinct = {r["fact_id"] for r in rows}
    keys = {r["key"] for r in rows}
    false_retained = [
        k for k, v in adj.items() if not v["whole_product"] and tac[k]["disposition"] == "RETAIN"
    ]
    supported_true_lost = [
        k
        for k, v in adj.items()
        if v["whole_product"] and v["support_type"] in ADOPTED and tac[k]["disposition"] != "RETAIN"
    ]
    true_to_unknown = [
        k for k, v in adj.items() if v["whole_product"] and tac[k]["disposition"] != "RETAIN"
    ]
    conflict_chosen = [
        r["key"] for r in rows if r["conflict"] and r["disposition"] != "UNKNOWN_CONFLICT"
    ]
    pop_ok = len(rows) == 293 and len(keys) == 293 and len(distinct) == 172 and set(adj) <= set(tac)
    req = {
        "R0_population_frozen": pop_ok,
        "R1_no_false_retained": not false_retained,
        "R2_no_supported_true_lost": not supported_true_lost,
        "R3_policy_valid_and_no_true_to_unknown": policy_ok and not true_to_unknown,
        "R4_conflicts_unknown": not conflict_chosen,
    }
    failing = [k for k, v in req.items() if not v]
    return {
        "requirements": req,
        "first_failing": failing[0] if failing else None,
        "verdict": "DESIGN_READY" if not failing else "STOP",
        "false_retained": false_retained,
        "supported_true_lost": supported_true_lost,
        "true_to_unknown": true_to_unknown,
        "conflict_chosen": conflict_chosen,
    }


def selftest(rows, adjudication):
    adj = {k: v for k, v in adjudication.items() if not k.startswith("_")}
    good = copy.deepcopy(rows)
    for r in good:
        if r["run"] == "tac01_protoid_v1" and r["fact_id"] in adj:
            r["disposition"] = "RETAIN" if adj[r["fact_id"]]["whole_product"] else "UNKNOWN_REVIEW"
    out = {"valid": criteria(good, adjudication, True)["verdict"]}

    def mutate(fid, value):
        x = copy.deepcopy(good)
        next(r for r in x if r["run"] == "tac01_protoid_v1" and r["fact_id"] == fid)[
            "disposition"
        ] = value
        return x

    out["false_retained"] = criteria(
        mutate("fact:e11600a1b72953fb2aff", "RETAIN"), adjudication, True
    )["first_failing"]
    out["supported_true_withdrawn"] = criteria(
        mutate("fact:a21e40454f36ee328210", "UNKNOWN_REVIEW"), adjudication, True
    )["first_failing"]
    out["invalid_r3_policy"] = criteria(good, adjudication, False)["first_failing"]
    chosen = copy.deepcopy(good)
    c = next(r for r in chosen if r["conflict"])
    c["disposition"] = "RETAIN"
    out["conflict_chosen"] = criteria(chosen, adjudication, True)["first_failing"]
    out["altered_population"] = criteria(good[:-1], adjudication, True)["first_failing"]
    assert out == {
        "valid": "DESIGN_READY",
        "false_retained": "R1_no_false_retained",
        "supported_true_withdrawn": "R2_no_supported_true_lost",
        "invalid_r3_policy": "R3_policy_valid_and_no_true_to_unknown",
        "conflict_chosen": "R4_conflicts_unknown",
        "altered_population": "R0_population_frozen",
    }, out
    return out


def build(out):
    for line in (V3 / "freeze_hashes.txt").read_text().splitlines():
        sha, path = line.split(maxsplit=1)
        if "se_runs" in path:
            assert digest(path) == sha, path
    adjudication = json.loads(ADJ.read_text())
    policy_ok = R3_POLICY.is_file() and "UNKNOWN_REVIEW" in R3_POLICY.read_text()
    rows = measure()
    crit = criteria(rows, adjudication, policy_ok)
    adj = {k: v for k, v in adjudication.items() if not k.startswith("_")}
    tac = {r["fact_id"]: r for r in rows if r["run"] == "tac01_protoid_v1"}
    first = {}
    for r in rows:
        first.setdefault(r["fact_id"], r)
    true_ret = sum(
        1 for k, v in adj.items() if v["whole_product"] and tac[k]["disposition"] == "RETAIN"
    )
    false_ret = len(crit["false_retained"])
    n_true = sum(v["whole_product"] for v in adj.values())
    summary = {
        **crit,
        "selftest": selftest(rows, adjudication),
        "rows": len(rows),
        "distinct_facts": len(first),
        "disposition_distinct": dict(
            sorted(Counter(r["disposition"] for r in first.values()).items())
        ),
        "disposition_rows": dict(sorted(Counter(r["disposition"] for r in rows).items())),
        "category_distinct": dict(sorted(Counter(r["category"] for r in first.values()).items())),
        "adjudicated_admitted": {
            "true_retained": true_ret,
            "true_to_unknown": len(crit["true_to_unknown"]),
            "false_retained": false_ret,
            "false_withdrawn": sum(not v["whole_product"] for v in adj.values()) - false_ret,
            "precision_of_retained": (true_ret / (true_ret + false_ret))
            if true_ret + false_ret
            else None,
            "recall_of_true": true_ret / n_true,
            "legacy_gate_precision": n_true / len(adj),
            "scope": "13 adjudicated admitted facts only; not population-wide performance",
        },
        "per_fact": {
            k: {
                "truth": v["whole_product"],
                "support_type": v["support_type"],
                "category": tac[k]["category"],
                "disposition": tac[k]["disposition"],
            }
            for k, v in sorted(adj.items())
        },
        "conflicts": [r["key"] for r in rows if r["conflict"]],
        "production_changes": 0,
    }
    out.mkdir(parents=True, exist_ok=False)
    for name, value in {"register.json": rows, "summary.json": summary}.items():
        (out / name).write_text(canonical(value) + "\n")
    (out / "hashes.json").write_text(
        canonical({p.name: digest(p) for p in sorted(out.iterdir())}) + "\n"
    )
    print(canonical(summary))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)
