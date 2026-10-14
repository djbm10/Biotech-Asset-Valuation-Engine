"""v2 acceptance audit (prereg 42b94f7). Verdict derived by `decide`; no constant."""

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research/se_target_alias_authority_source_v2"
sys.path.insert(0, str(STUDY))
import universe as U  # noqa: E402

from bve.se.discovery.query import compile_problem_queries  # noqa: E402
from bve.se.intent.compiler import compile_intent  # noqa: E402
from bve.se.intent.parser import parse_query  # noqa: E402
from bve.se.ontology.records import AliasType, EntityType  # noqa: E402
from bve.se.schemas.contracts import BuyerIdentity  # noqa: E402

POLICIES = {"A": {"A"}, "B": {"B-current"}, "B-hist (diagnostic)": {"B-hist"}}
H20 = "Find clinical-stage factor XI inhibitors for prevention of thrombosis."
BUYER = BuyerIdentity(buyer_id="audit", name="audit", as_of_date=date(2026, 10, 14))


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@contextmanager
def injected(r, pairs):
    saved = copy.deepcopy(r._lookup)
    try:
        for text, cid in pairs:
            r._lookup[(EntityType.TARGET, U.key(text))].append((AliasType.SYNONYM, cid))
        yield
    finally:
        r._lookup.clear()
        r._lookup.update(saved)


def chain(query):
    intent = parse_query(query)
    try:
        problem = compile_intent(intent, buyer=BUYER)
        plans = compile_problem_queries(problem)
        dumped = json.dumps(problem.model_dump(mode="json"))
        return {
            "compiled": True,
            "plans": len(plans),
            "target_ids": sorted({x.split('"')[0] for x in dumped.split("TARGET:")[1:]}),
        }
    except Exception as e:  # noqa: BLE001 - refusal is a measured outcome
        return {"compiled": False, "error": type(e).__name__}


def evaluate(policy_classes, rows, sample, labels, regress, h20):
    adm = [r for r in rows if r["admitted"] and r["class"] in policy_classes]
    negatives = {r["key"] for r in rows if r["n_drug"] or r["n_ncit"]}
    s1 = sorted({r["key"] for r in adm if r["n_drug"] or r["n_ncit"]})
    in_sample = [r for r in adm if r["entity"] in sample]
    lab = {(x["name"], x["target_symbol"]): x["label"] for x in labels}
    unsafe = sorted(
        {
            r["text"]
            for r in in_sample
            if lab.get((r["text"], r["entity"].split(":", 1)[-1])) != "SAFE_TARGET_NAME"
        }
    )
    safe_entities = {
        r["entity"]
        for r in in_sample
        if lab.get((r["text"], r["entity"].split(":", 1)[-1])) == "SAFE_TARGET_NAME"
    }
    ec = [r["text"] for r in adm if U.EC.match(r["text"].strip())]
    regress_admitted = sorted({r["key"] for r in adm if r["key"] in regress})
    gates = {
        "S1_independent_negatives": not s1,
        "S2_reviewer_safe": not unsafe,
        "S3_no_ec": not ec,
        "S4_regression": not regress_admitted,
        "S5_h20_chain": h20,
        "S6_overlap": len(negatives) >= 20,
        "S7_deterministic": True,
    }
    coverage = len(safe_entities) / len(sample)
    if all(gates.values()):
        verdict = "JUSTIFIED" if coverage >= 0.10 else "LIMITED"
    else:
        verdict = "STOP"
    return {
        "gates": gates,
        "coverage": coverage,
        "verdict": verdict,
        "admitted_universe": len(adm),
        "negative_collisions": s1[:40],
        "negative_collision_count": len(s1),
        "unsafe_in_sample": unsafe,
        "safe_entities": len(safe_entities),
        "ec_admitted": ec[:10],
        "regression_admitted": regress_admitted,
    }


def decide(per_policy):
    order = {"JUSTIFIED": 2, "LIMITED": 1, "STOP": 0}
    best = max(
        (v["verdict"] for k, v in per_policy.items() if "diagnostic" not in k), key=order.get
    )
    return best


def selftest():
    sample = {"T:X", "T:Y"}
    base = [
        {
            "entity": "T:X",
            "text": "Good",
            "key": "good",
            "class": "A",
            "admitted": True,
            "n_drug": False,
            "n_ncit": False,
        }
    ] + [
        {
            "entity": "T:Z",
            "text": f"n{i}",
            "key": f"n{i}",
            "class": "A",
            "admitted": False,
            "n_drug": True,
            "n_ncit": False,
        }
        for i in range(25)
    ]
    labels = [{"name": "Good", "target_symbol": "X", "label": "SAFE_TARGET_NAME"}]
    ok = evaluate({"A"}, base, sample, labels, set(), True)
    out = {"valid": ok["verdict"]}
    neg = copy.deepcopy(base)
    neg[1]["admitted"] = True
    out["negative_admitted"] = evaluate({"A"}, neg, sample, labels, set(), True)["verdict"]
    out["reviewer_unsafe"] = evaluate(
        {"A"}, base, sample, [{**labels[0], "label": "UNSAFE"}], set(), True
    )["verdict"]
    ec = copy.deepcopy(base) + [
        {
            "entity": "T:Q",
            "text": "EC 1.1.1.1",
            "key": "ec 1.1.1.1",
            "class": "A",
            "admitted": True,
            "n_drug": False,
            "n_ncit": False,
        }
    ]
    out["ec_admitted"] = evaluate({"A"}, ec, sample, labels, set(), True)["verdict"]
    out["statin_regression"] = evaluate({"A"}, base, sample, labels, {"good"}, True)["verdict"]
    out["h20_identity_loss"] = evaluate({"A"}, base, sample, labels, set(), False)["verdict"]
    out["too_easy"] = evaluate({"A"}, base[:2], sample, labels, set(), True)["verdict"]
    big = {f"T:{i}" for i in range(100)}
    out["safe_but_small"] = evaluate({"A"}, base, big, labels, set(), True)["verdict"]
    assert out == {
        "valid": "JUSTIFIED",
        "negative_admitted": "STOP",
        "reviewer_unsafe": "STOP",
        "ec_admitted": "STOP",
        "statin_regression": "STOP",
        "h20_identity_loss": "STOP",
        "too_easy": "STOP",
        "safe_but_small": "LIMITED",
    }, out
    return out


def build(out):
    for line in (STUDY / "freeze_hashes.txt").read_text().splitlines():
        sha, path = line.split(maxsplit=1)
        assert digest(path) == sha, path
    s = U.load()
    rows = U.universe(s)
    assert canonical(rows) == canonical(json.loads((STUDY / "universe.json").read_text())), (
        "universe drift"
    )
    sample = set(json.loads((STUDY / "sample_ids.json").read_text())["sample"])
    labels = json.loads((STUDY / "review_labels.json").read_text())["labels"]
    v1 = json.loads((U.V1 / "results/candidates.json").read_text())
    regress = {U.key("statin"), U.key("statin-like")} | {
        U.key(c["text"]) for c in v1 if U.EC.match(c["text"])
    }
    f11 = [r for r in rows if r["entity"] == "TARGET:F11" and r["key"] == U.key("factor XI")]
    r = s["r"]
    with injected(r, [("factor XI", "TARGET:F11")]):
        h20_chain = chain(H20)
    bare_f11 = sorted(r.claimants_of("F11", EntityType.TARGET))
    per = {}
    for name, classes in POLICIES.items():
        h20_ok = (
            any(x["admitted"] and x["class"] in classes for x in f11)
            and h20_chain.get("target_ids") == ["F11"]
            and len(bare_f11) > 1
        )
        per[name] = evaluate(classes, rows, sample, labels, regress, h20_ok)
    summary = {
        "verdict": decide(per),
        "policies": per,
        "selftest": selftest(),
        "universe_candidates": len(rows),
        "universe_by_class": dict(Counter(x["class"] for x in rows)),
        "admitted_by_class": dict(Counter(x["class"] for x in rows if x["admitted"])),
        "rejection_reasons": dict(Counter(rr for x in rows for rr in x["reasons"])),
        "independent_negative_keys": len({x["key"] for x in rows if x["n_drug"] or x["n_ncit"]}),
        "h20": {"factor_xi_rows": f11, "injected_chain": h20_chain, "bare_f11_claimants": bare_f11},
        "h17": "known refusal; no authority spelling (v1); not attempted",
        "sample_size": len(sample),
        "reviewed": len(labels),
        "production_changes": 0,
    }
    out.mkdir(parents=True, exist_ok=False)
    (out / "summary.json").write_text(canonical(summary) + "\n")
    (out / "hashes.json").write_text(
        canonical({"summary.json": digest(out / "summary.json")}) + "\n"
    )
    print(
        canonical(
            {
                "verdict": summary["verdict"],
                **{k: (v["verdict"], v["gates"], round(v["coverage"], 4)) for k, v in per.items()},
            }
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)
