"""ESG401 nomination diagnosis. Verdict derived by `decide`; no constant. Diagnosis only."""

import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from bve.se.discovery.adapters import extract_observed_asset_names
from bve.se.schemas.contracts import IdentityRelationship

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research/se_esg401_candidate_nomination_diagnosis_v1"


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def norm(s):
    return re.sub(r"[^0-9a-z]+", "", s.casefold())


def trial_names(protocol):
    out = []
    for iv in (protocol.get("armsInterventionsModule") or {}).get("interventions") or []:
        out += [iv.get("name") or "", *(iv.get("otherNames") or [])]
    return [norm(x) for x in out if x]


def covered(name, names):
    k = norm(name)
    return bool(k) and any(k in x or (x and x in k) for x in names)


def measure_unit(unit):
    assert digest(unit["artifact"]) == unit["artifact_sha256"], unit["artifact"]
    protocol = json.loads(Path(unit["artifact"]).read_text())
    names = trial_names(protocol)
    probe = extract_observed_asset_names(unit["description"])
    return {"covered_names": names, "probe": probe}


def evaluate(units, labels, measured):
    rows = []
    for u, lab in zip(units, labels, strict=True):
        m = measured[u["unit_id"]]
        products = [e for e in lab["entities"] if e["kind"] == "THERAPEUTIC_PRODUCT"]
        ents = []
        for e in lab["entities"]:
            ents.append(
                {
                    **e,
                    "covered": covered(e["name"], m["covered_names"]),
                    "probed": any(
                        norm(p) == norm(e["name"]) or norm(e["name"]) in norm(p) for p in m["probe"]
                    ),
                }
            )
        spurious = [
            p
            for p in m["probe"]
            if not any(norm(e["name"]) in norm(p) or norm(p) in norm(e["name"]) for e in products)
        ]
        rows.append(
            {
                "unit_id": u["unit_id"],
                "nct": u["nct"],
                "arm_index": u["arm_index"],
                "dev": bool(u.get("development_reference")),
                "relation": lab["relation"],
                "entities": ents,
                "probe": m["probe"],
                "spurious": spurious,
            }
        )
    return rows


def decide(rows, relationship_values):
    indep = [r for r in rows if not r["dev"]]
    uncovered = [
        (r["nct"], e["name"])
        for r in indep
        for e in r["entities"]
        if e["kind"] == "THERAPEUTIC_PRODUCT" and e["role"] == "ADMINISTERED" and not e["covered"]
    ]
    j1 = len(uncovered) >= 5 and len({n for n, _ in uncovered}) >= 3
    spurious = [(r["unit_id"], s) for r in indep for s in r["spurious"]]
    j2 = not spurious
    j3 = any("ALTERNATIVE" in v for v in relationship_values)
    first = "J1_failure_class" if not j1 else "J2_probe_safety" if not j2 else None
    return {
        "J1_failure_class": j1,
        "J2_probe_safety": j2,
        "J3_alternative_relation_exists": j3,
        "first_failing": first,
        "verdict": "JUSTIFIED" if first is None else "STOP",
        "uncovered_administered": uncovered,
        "spurious": spurious,
    }


def selftest(rows):
    rel = [v.value for v in IdentityRelationship]
    good = copy.deepcopy(rows)
    k = 0
    for r in good:
        r["spurious"] = []
        if not r["dev"] and k < 5:
            r["entities"].append(
                {
                    "name": f"X{k}",
                    "kind": "THERAPEUTIC_PRODUCT",
                    "role": "ADMINISTERED",
                    "covered": False,
                    "probed": True,
                }
            )
            r["nct"] = f"NCT_FAKE_{k}"
            k += 1
    out = {"valid": decide(good, rel)["verdict"]}
    few = copy.deepcopy(good)
    for r in few:
        r["entities"] = [e for e in r["entities"] if not e["name"].startswith("X")]
    out["no_failure_class"] = decide(few, rel)["first_failing"]
    noisy = copy.deepcopy(good)
    next(r for r in noisy if not r["dev"])["spurious"] = ["Dose"]
    out["spurious_probe"] = decide(noisy, rel)["first_failing"]
    dev_only = copy.deepcopy(few)
    next(r for r in dev_only if r["dev"])["entities"] += [
        {
            "name": f"Y{i}",
            "kind": "THERAPEUTIC_PRODUCT",
            "role": "ADMINISTERED",
            "covered": False,
            "probed": True,
        }
        for i in range(6)
    ]
    out["dev_reference_not_counted"] = decide(dev_only, rel)["first_failing"]
    out["alternative_relation_detected"] = decide(good, rel + ["ARM_ALTERNATIVE"])[
        "J3_alternative_relation_exists"
    ]
    assert out == {
        "valid": "JUSTIFIED",
        "no_failure_class": "J1_failure_class",
        "spurious_probe": "J2_probe_safety",
        "dev_reference_not_counted": "J1_failure_class",
        "alternative_relation_detected": True,
    }, out
    return out


def pool_prevalence():
    """Unadjudicated upper bound over every arm in the frozen development pool."""
    runs = Path.home() / "se_runs"
    seen, arms, hits, names = set(), 0, [], Counter()
    for run in ("tac01_protoid_v1", "mint5_protoid_v1"):
        for p in sorted((runs / run / "snapshots").rglob("*.json")):
            if "clinicaltrials" not in str(p):
                continue
            d = json.loads(p.read_text())
            nct = d["identificationModule"]["nctId"]
            if nct in seen:
                continue
            seen.add(nct)
            tn = trial_names(d)
            for i, arm in enumerate(
                (d.get("armsInterventionsModule") or {}).get("armGroups") or []
            ):
                desc = arm.get("description") or ""
                if not desc.strip():
                    continue
                arms += 1
                miss = [x for x in extract_observed_asset_names(desc) if not covered(x, tn)]
                if miss:
                    hits.append([nct, i, miss])
                    names.update(norm(x) for x in miss)
    return {
        "arms": arms,
        "arms_with_uncovered_probe_names": len(hits),
        "trials_with_uncovered_probe_names": len({h[0] for h in hits}),
        "distinct_uncovered_probe_names": len(names),
        "examples": hits[:40],
    }


def esg401_trace(dev_unit, measured):
    protocol = json.loads(Path(dev_unit["artifact"]).read_text())
    ivs = protocol["armsInterventionsModule"]["interventions"]
    linked = [iv["name"] for iv in ivs if dev_unit["label"] in (iv.get("armGroupLabels") or [])]
    h19 = json.loads((Path.home() / "se_runs/heldout_h19_v4/result.json").read_text())
    cand_hit = [
        c["asset_id"]
        for c in h19["candidates"]
        if any(
            "esg401" in norm(a) for a in [c.get("preferred_name") or "", *(c.get("aliases") or [])]
        )
    ]
    return [
        {
            "stage": "raw_field",
            "present": "ESG401" in dev_unit["description"],
            "artifact_sha256": dev_unit["artifact_sha256"],
            "field": dev_unit["field"],
            "phrase": dev_unit["description"],
        },
        {
            "stage": "arm_intervention_linkage",
            "arm_label": dev_unit["label"],
            "interventionNames": dev_unit["interventionNames"],
            "linked_intervention_names": linked,
        },
        {
            "stage": "nomination_inputs (interventions[].name/otherNames)",
            "esg401_reachable": covered("ESG401", measured[dev_unit["unit_id"]]["covered_names"]),
        },
        {
            "stage": "arm_description_route",
            "exists_in_code": False,
            "note": "_candidate_interventions iterates interventions only; armGroups[].description is read nowhere for names",
        },
        {
            "stage": "probe_over_description (hypothetical route)",
            "names": measured[dev_unit["unit_id"]]["probe"],
        },
        {"stage": "candidate_population (frozen H19 result)", "esg401_candidates": cand_hit},
        {
            "stage": "alternative_relation_in_schema",
            "available": [v.value for v in IdentityRelationship],
        },
    ]


def build(out):
    sample = json.loads((STUDY / "sample.json").read_text())
    labels = json.loads((STUDY / "labels.json").read_text())["labels"]
    units = sample["units"]
    measured = {u["unit_id"]: measure_unit(u) for u in units}
    rows = evaluate(units, labels, measured)
    rel = [v.value for v in IdentityRelationship]
    decision = decide(rows, rel)
    indep = [r for r in rows if not r["dev"]]
    ents = [e for r in indep for e in r["entities"]]
    products = [e for e in ents if e["kind"] == "THERAPEUTIC_PRODUCT"]
    summary = {
        **decision,
        "selftest": selftest(rows),
        "independent_units": len(indep),
        "mentions": len(ents),
        "product_mentions": len(products),
        "distinct_product_names": len({norm(e["name"]) for e in products}),
        "product_mentions_covered": sum(e["covered"] for e in products),
        "uncovered_product_mentions_by_role": dict(
            Counter(e["role"] for e in products if not e["covered"])
        ),
        "relations": dict(sorted(Counter(r["relation"] for r in indep).items())),
        "probe_recall_on_products": sum(e["probed"] for e in products) / len(products),
        "probe_spurious": decision["spurious"],
        "generic_class_mentions": sum(e["kind"] == "GENERIC_CLASS" for e in ents),
        "esg401_trace": esg401_trace(
            next(u for u in units if u.get("development_reference")), measured
        ),
        "dev_reference_row": next(r for r in rows if r["dev"]),
        "pool_prevalence_unadjudicated": pool_prevalence(),
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
                    "J1_failure_class",
                    "J2_probe_safety",
                    "J3_alternative_relation_exists",
                )
            }
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)
