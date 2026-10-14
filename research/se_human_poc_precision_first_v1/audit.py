"""Human-PoC precision-first design audit (prereg 729c500). Verdict derived by `decide`."""

import argparse
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

from bve.se.schemas.contracts import VerificationStatus

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research/se_human_poc_precision_first_v1"
ADJ = ROOT / "research/se_human_efficacy_context_safety_v1/witness_adjudications.json"
RUNS = {
    r: Path.home() / "se_runs" / r / "result.json"
    for r in (
        "tac01_protoid_v1",
        "mint5_protoid_v1",
        "aacr_safety",
        "heldout_h16_v4",
        "heldout_h18_v4_rerun1",
        "heldout_h19_v4",
    )
}
DEV = {"tac01_protoid_v1", "mint5_protoid_v1", "aacr_safety"}
PROSE = {"reported_efficacy_sentence"}


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def route(claim):
    m = claim["extraction_method"]
    if m == "structured_clinical_result":
        return "STRUCTURED_COMPLETE"
    if m in PROSE or "sentence" in m:
        return "PROSE"
    return "OTHER"


def emitter_capability():
    """Static read: which ClinicalResult(...) calls exist and whether any can be complete."""
    calls = []
    for p in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(p.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "ClinicalResult":
                kw = {k.arg: ast.unparse(k.value) for k in node.keywords}
                calls.append(
                    {
                        "file": str(p.relative_to(ROOT)),
                        "line": node.lineno,
                        "incomplete_reporting": kw.get("incomplete_reporting", "False(default)"),
                        "effect_size": kw.get("effect_size", "None(default)"),
                    }
                )
    can_complete = any(
        c["incomplete_reporting"] != "True" and c["effect_size"] != "None(default)" for c in calls
    )
    return {"calls": calls, "any_can_be_complete": can_complete}


def measure(adj):
    truth = {w["passage"]: w["expected_pass"] for w in adj}
    rows, results_seen = [], Counter()
    for run, path in RUNS.items():
        d = json.loads(path.read_text())
        claims = {c["claim_id"]: c for c in d["claims"]}
        cands = {c["asset_id"]: c for c in d["candidates"]}
        results_seen[run] = {
            "clinical_results": len(d.get("clinical_results") or []),
            "complete": sum(
                1
                for r in d.get("clinical_results") or []
                if not r.get("incomplete_reporting") and r.get("effect_size") is not None
            ),
        }
        gates = {}
        for g in d.get("gate_evaluations") or []:
            for x in g["decisions"]:
                if x["requirement_id"] == "evidence.human_poc":
                    gates[g["subject_id"]] = x["status"]
        for f in d["facts"]:
            if f["fact_type"] != "human_poc_present" or f["value"] is not True:
                continue
            sup = [claims[i] for i in f["supporting_claim_ids"] if i in claims]
            routes = sorted({route(c) for c in sup})
            passages = sorted({c["supporting_passage"] for c in sup})
            labels = sorted({str(truth.get(p, "UNADJUDICATED")) for p in passages})
            name = (
                cands.get(f["subject_id"], {}).get("canonical_name") or f["subject_id"]
            ).casefold()
            rows.append(
                {
                    "run": run,
                    "dev": run in DEV,
                    "fact_id": f["fact_id"],
                    "subject": name,
                    "routes": routes,
                    "passages": passages,
                    "labels": labels,
                    "gate": gates.get(f["subject_id"]),
                    "proposed": "CONFIRMED"
                    if "STRUCTURED_COMPLETE" in routes
                    else ("UNVERIFIED_PROSE" if "PROSE" in routes else "UNKNOWN"),
                }
            )
    return rows, dict(results_seen)


def decide(rows, schema_statuses, capability):
    distinct = {}
    for r in rows:
        for p in r["passages"]:
            distinct.setdefault((r["subject"], p), r)
    conf = [k for k, r in distinct.items() if r["proposed"] == "CONFIRMED"]
    false_conf = [
        k for k, r in distinct.items() if r["proposed"] == "CONFIRMED" and "False" in r["labels"]
    ]
    bad_struct = [k for k, r in distinct.items() if r["proposed"] == "CONFIRMED" and not capability]
    true_keys = [k for k, r in distinct.items() if r["labels"] == ["True"]]
    true_kept = [k for k in true_keys if distinct[k]["proposed"] == "CONFIRMED"]
    dev_conf = [k for k in conf if distinct[k]["dev"]]
    frac = len(true_kept) / len(true_keys) if true_keys else 0.0
    req = {
        "R1_no_false_confirmed": not false_conf,
        "R2_structured_support_verified": not bad_struct,
        "R3_meaningful_capability": len(dev_conf) >= 1 and frac >= 0.25,
        "R4_unverified_status_representable": any("UNVERIFIED" in s for s in schema_statuses),
    }
    failing = [k for k, v in req.items() if not v]
    return {
        "requirements": req,
        "first_failing": failing[0] if failing else None,
        "verdict": "IMPLEMENTATION_READY" if not failing else "DESIGN_STOP",
        "confirmed_distinct": len(conf),
        "true_distinct": len(true_keys),
        "true_kept": len(true_kept),
        "false_confirmed": len(false_conf),
        "confirmed_fraction_of_true": frac,
    }


def selftest(rows, statuses):
    def mk(proposed, labels, dev=True, subject="x", passage="p"):
        return {
            "run": "r",
            "dev": dev,
            "fact_id": "f",
            "subject": subject,
            "routes": [],
            "passages": [passage],
            "labels": labels,
            "gate": None,
            "proposed": proposed,
        }

    valid = [mk("CONFIRMED", ["True"], passage=f"p{i}") for i in range(4)] + [
        mk("UNVERIFIED_PROSE", ["False"], passage="q")
    ]
    ok = statuses + ["UNVERIFIED_PROSE"]
    out = {"valid": decide(valid, ok, True)["verdict"]}
    out["false_admitted"] = decide(valid + [mk("CONFIRMED", ["False"], passage="z")], ok, True)[
        "first_failing"
    ]
    out["unsupported_structured"] = decide(valid, ok, False)["first_failing"]
    withdrawn = [mk("UNVERIFIED_PROSE", ["True"], passage=f"p{i}") for i in range(4)] + [
        mk("CONFIRMED", ["True"], passage="a")
    ]
    out["protected_withdrawn"] = decide(withdrawn, ok, True)["first_failing"]
    zero = [mk("UNVERIFIED_PROSE", ["True"], passage=f"p{i}") for i in range(4)]
    out["zero_positive_not_ready"] = decide(zero, ok, True)["verdict"]
    out["no_status"] = decide(valid, statuses, True)["first_failing"]
    assert out == {
        "valid": "IMPLEMENTATION_READY",
        "false_admitted": "R1_no_false_confirmed",
        "unsupported_structured": "R2_structured_support_verified",
        "protected_withdrawn": "R3_meaningful_capability",
        "zero_positive_not_ready": "DESIGN_STOP",
        "no_status": "R4_unverified_status_representable",
    }, out
    return out


def build(out):
    for line in (STUDY / "freeze_hashes.txt").read_text().splitlines():
        sha, path = line.split(maxsplit=1)
        assert digest(path) == sha, path
    adj = json.loads(ADJ.read_text())
    rows, results_seen = measure(adj)
    statuses = [s.value for s in VerificationStatus]
    cap = emitter_capability()
    dec = decide(rows, statuses, cap["any_can_be_complete"])
    distinct = {}
    for r in rows:
        for p in r["passages"]:
            distinct.setdefault((r["subject"], p), r)
    exposed = [
        {
            "run": r["run"],
            "subject": r["subject"],
            "labels": r["labels"],
            "routes": r["routes"],
            "proposed": r["proposed"],
            "gate": r["gate"],
        }
        for r in rows
        if not r["dev"]
    ]
    summary = {
        **dec,
        "selftest": selftest(rows, statuses),
        "verification_status_values": statuses,
        "clinical_result_emitters": cap,
        "clinical_results_in_runs": results_seen,
        "fact_observations": len(rows),
        "distinct_fact_passages": len(distinct),
        "distinct_subjects": len({r["subject"] for r in rows}),
        "routes_observations": dict(Counter("+".join(r["routes"]) for r in rows)),
        "routes_distinct": dict(Counter("+".join(r["routes"]) for r in distinct.values())),
        "labels_distinct": dict(Counter("|".join(r["labels"]) for r in distinct.values())),
        "baseline_vs_proposed_distinct": {
            "baseline_true_facts": len(distinct),
            "proposed": dict(Counter(r["proposed"] for r in distinct.values())),
        },
        "gate_status_observations": dict(Counter(str(r["gate"]) for r in rows)),
        "exposed_controls": exposed,
        "production_changes": 0,
    }
    out.mkdir(parents=True, exist_ok=False)
    for name, value in {"rows.json": rows, "summary.json": summary}.items():
        (out / name).write_text(canonical(value) + "\n")
    (out / "hashes.json").write_text(
        canonical({p.name: digest(p) for p in sorted(out.iterdir())}) + "\n"
    )
    print(
        canonical(
            {
                k: summary[k]
                for k in (
                    "verdict",
                    "first_failing",
                    "confirmed_distinct",
                    "true_distinct",
                    "true_kept",
                    "false_confirmed",
                )
            }
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)
