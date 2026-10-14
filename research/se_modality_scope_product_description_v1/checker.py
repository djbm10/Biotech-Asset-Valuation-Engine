"""Acceptance checker for MODALITY_SCOPE_PRODUCT_DESCRIPTION v1. Verdict derived, never constant."""

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research/se_modality_scope_product_description_v1"
HA = ROOT / "research/se_modality_scope_head_attachment_v1"
V3 = ROOT / "research/se_product_vs_component_modality_semantics_v3"
sys.path.insert(0, str(HA))
import freeze as ha_freeze  # noqa: E402

NEW_RULES = {"A": "explicit_product_appositive", "B": "explicit_product_predicate_premodified"}
FALSE_FACTS = (
    "fact:207184bd1b371d31ada1",
    "fact:e11600a1b72953fb2aff",
    "fact:f9cbd50c0e32a72a8d3f",
    "fact:02b6dda9819bfac2cd8f",
    "fact:3121baea1a1ef891b4bb",
)


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run_unit(unit):
    from bve.se.evidence.modality_scope import ScopeSource, scoped_modality_assertions

    src = ScopeSource(
        artifact=unit["artifact"],
        artifact_sha256=unit["artifact_sha256"],
        record_id=unit["record_id"],
        field=unit["field"],
        product_names=tuple(unit["product_names"]),
        product_locator="source",
    )
    off = unit["sentence_offset"]
    end = off + len(unit["sentence"])
    rows = scoped_modality_assertions(f"unit:{unit['unit_id']}", unit["text"], src)
    return [
        {
            "start": r.mention.start - off,
            "end": r.mention.end - off,
            "text": r.mention.text,
            "modality": r.modality,
            "scope": r.scope,
            "rule": r.rule,
            "provenance": bool(r.product_span and r.relation_span and r.rule and r.source),
        }
        for r in rows
        if off <= r.mention.start < end
    ]


def score_units(measured, labels):
    unsafe, by_rule, missing_provenance = [], {"A": [0, 0], "B": [0, 0]}, []
    for lab in labels:
        rows = measured[lab["unit_id"]]
        spans = {
            tuple(s)
            for s in lab["required_any"] + [a for a in lab["allowed"] if not isinstance(a, str)]
        }
        igg_ok = "IgG" in lab["allowed"]
        for r in rows:
            if r["scope"] != "PRODUCT_LEVEL":
                continue
            if not r["provenance"]:
                missing_provenance.append(lab["unit_id"])
            ok = (r["start"], r["end"]) in spans or (igg_ok and r["text"].casefold() == "igg")
            if not ok:
                unsafe.append([lab["unit_id"], r["text"], r["modality"], r["rule"]])
        if lab["structure"] in by_rule:
            hit = any(
                r["scope"] == "PRODUCT_LEVEL" and [r["start"], r["end"]] in lab["required_any"]
                for r in rows
            )
            by_rule[lab["structure"]][0] += hit
            by_rule[lab["structure"]][1] += 1
    unsafe_by_rule = {k: [u for u in unsafe if u[3] == v] for k, v in NEW_RULES.items()}
    return unsafe, unsafe_by_rule, by_rule, missing_provenance


def ha_conformance(measured_ha, controls):
    bad = []
    for c in controls:
        want = sorted(
            [m["start"], m["end"], m["modality"], m["scope"], m["rule"]] for m in c["mentions"]
        )
        if sorted(measured_ha[c["id"]]) != want:
            bad.append(c["id"])
    return bad


def criteria(m):
    unsafe, unsafe_by_rule, by_rule, missing = score_units(m["units"], m["labels"])
    recall = {k: (v[0] / v[1] if v[1] else 0.0) for k, v in by_rule.items()}
    per_rule = {
        k: not unsafe_by_rule[k] and recall[k] >= 0.8 and by_rule[k][1] >= 5 for k in NEW_RULES
    }
    gates = {
        "G1_independent_safety": not unsafe,
        "G2_per_rule_recall": all(recall[k] >= 0.8 for k in NEW_RULES),
        "G3_frozen_controls": not m["ha_bad"] and not m["v1v2_bad"],
        "G4_false_facts_unsupported": not m["false_fact_products"],
        "G5_population_identical": m["population_identical"],
        "G6_provenance": not missing,
        "G7_no_consumer": m["consumers"] == ["src/bve/se/evidence/modality_scope.py"],
    }
    failing = [k for k, v in gates.items() if not v]
    return {
        "gates": gates,
        "first_failing": failing[0] if failing else None,
        "verdict": "ADOPT" if not failing else "FAIL",
        "per_rule_pass": per_rule,
        "recall": recall,
        "recall_counts": by_rule,
        "unsafe": unsafe,
    }


def measure():
    sample = json.loads((STUDY / "sample.json").read_text())["units"]
    labels = json.loads((STUDY / "labels.json").read_text())["labels"]
    units = {u["unit_id"]: run_unit(u) for u in sample}
    controls = json.loads((HA / "controls.json").read_text())
    from bve.se.evidence.modality_scope import ScopeSource, scoped_modality_assertions

    ha = {}
    for c in controls:
        src = ScopeSource(
            artifact="fixture",
            artifact_sha256="fixture",
            record_id=c["id"],
            field="text",
            product_names=tuple(c["product_names"]),
            product_locator="fixture",
        )
        ha[c["id"]] = [
            [r.mention.start, r.mention.end, r.modality, r.scope, r.rule]
            for r in scoped_modality_assertions("candidate", c["text"], src)
        ]
    baseline = json.loads((HA / "baseline_records.json").read_text())
    ha_delta = json.loads((HA / "expected_delta.json").read_text())
    sys.path.insert(0, str(HA))
    import checker as ha_checker  # noqa: PLC0415

    predicted = ha_checker.apply_delta(baseline, ha_delta)
    actual = {
        f"{pop}:{cid}": ha_freeze.records(t, cand, src, leg)
        for pop, cid, cand, t, src, leg in ha_freeze.population()
    }
    v1v2_bad = [k for k in predicted if actual.get(k) != predicted[k]]
    register = json.loads((V3 / "results/register.json").read_text())
    false_products = []
    for row in register:
        if row["run"] == "tac01_protoid_v1" and row["fact_id"] in FALSE_FACTS:
            false_products += [
                row["fact_id"]
                for e in row["evidence"]
                if e["scoped"]
                for s in e["scoped"]
                if s[1] == row["value"] and s[2] == "PRODUCT_LEVEL"
            ]
    consumers = sorted(
        str(p.relative_to(ROOT))
        for p in (ROOT / "src").rglob("*.py")
        if "modality_scope" in p.read_text()
    )
    return {
        "units": units,
        "labels": labels,
        "ha_bad": ha_conformance(ha, controls),
        "v1v2_bad": v1v2_bad,
        "false_fact_products": false_products,
        "population_identical": not v1v2_bad,
        "consumers": consumers,
    }


def selftest(m):
    good = copy.deepcopy(m)
    for lab in good["labels"]:
        rows = []
        for s in lab["required_any"][:1]:
            rows.append(
                {
                    "start": s[0],
                    "end": s[1],
                    "text": "x",
                    "modality": "M",
                    "scope": "PRODUCT_LEVEL",
                    "rule": NEW_RULES.get(lab["structure"], "x"),
                    "provenance": True,
                }
            )
        good["units"][lab["unit_id"]] = rows
    good.update(
        ha_bad=[],
        v1v2_bad=[],
        false_fact_products=[],
        population_identical=True,
        consumers=["src/bve/se/evidence/modality_scope.py"],
    )
    out = {"valid": criteria(good)["verdict"]}
    neg = next(lab for lab in good["labels"] if lab["note"].startswith("class-label subject"))
    bad = copy.deepcopy(good)
    bad["units"][neg["unit_id"]] = [
        {
            "start": 0,
            "end": 3,
            "text": "x",
            "modality": "M",
            "scope": "PRODUCT_LEVEL",
            "rule": NEW_RULES["B"],
            "provenance": True,
        }
    ]
    out["unsupported_promotion"] = criteria(bad)["first_failing"]
    miss = copy.deepcopy(good)
    for lab in miss["labels"]:
        if lab["structure"] == "A":
            miss["units"][lab["unit_id"]] = []
    out["recall_loss"] = criteria(miss)["first_failing"]
    unreg = copy.deepcopy(good)
    unreg["v1v2_bad"] = ["v1_controls:S01"]
    out["unregistered_delta"] = criteria(unreg)["first_failing"]
    ffact = copy.deepcopy(good)
    ffact["false_fact_products"] = [FALSE_FACTS[0]]
    out["false_fact_certified"] = criteria(ffact)["first_failing"]
    assert out == {
        "valid": "ADOPT",
        "unsupported_promotion": "G1_independent_safety",
        "recall_loss": "G2_per_rule_recall",
        "unregistered_delta": "G3_frozen_controls",
        "false_fact_certified": "G4_false_facts_unsupported",
    }, out
    return out


def build(out):
    m = measure()
    crit = criteria(m)
    summary = {
        **crit,
        "selftest": selftest(m),
        "units": len(m["units"]),
        "ha_bad": m["ha_bad"],
        "v1v2_bad": m["v1v2_bad"],
        "false_fact_products": m["false_fact_products"],
        "consumers": m["consumers"],
    }
    out.mkdir(parents=True, exist_ok=False)
    (out / "measured_units.json").write_text(canonical(m["units"]) + "\n")
    (out / "summary.json").write_text(canonical(summary) + "\n")
    (out / "hashes.json").write_text(
        canonical({p.name: digest(p) for p in sorted(out.iterdir())}) + "\n"
    )
    print(canonical(summary))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)
