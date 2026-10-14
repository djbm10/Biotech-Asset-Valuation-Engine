"""Execute the frozen v3 design (b12ee79 + 7dd05ae). Verdict derived by `criteria`; no constant."""

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

from bve.se.evidence.modality_scope import ScopeSource, scoped_modality_assertions

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research/se_product_vs_component_modality_semantics_v3"
V2 = ROOT / "research/se_product_vs_component_modality_semantics_v2"
HA = ROOT / "research/se_modality_scope_head_attachment_v1"
RUNS = {
    r: Path.home() / "se_runs" / r / "result.json" for r in ("tac01_protoid_v1", "mint5_protoid_v1")
}
ORDER = ("R1", "R2", "R3", "R4")


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def fixture(text, names, rid):
    src = ScopeSource(
        artifact="fixture",
        artifact_sha256=hashlib.sha256(text.encode()).hexdigest(),
        record_id=rid,
        field="text",
        product_names=tuple(names),
        product_locator="fixture",
    )
    return scoped_modality_assertions(f"fixture:{rid}", text, src)


def measure_controls():
    """Per control: list of (start, end, modality, scope) plus its frozen focus/expectation."""
    out = []
    for c in json.loads((V2 / "additional_controls.json").read_text()):
        start = c["text"].casefold().index(c["focus"].casefold())
        rows = fixture(c["text"], ["Novel Product"], c["id"])
        focus = sorted(
            {
                r.scope
                for r in rows
                if (r.mention.start, r.mention.end) == (start, start + len(c["focus"]))
            }
        )
        out.append(
            {"suite": "v2", "id": c["id"], "expected": c["expected_scope"], "focus_scopes": focus}
        )
    for c in json.loads((HA / "controls.json").read_text()):
        rows = fixture(c["text"], c["product_names"], c["id"])
        have = sorted([r.mention.start, r.mention.end, r.modality, r.scope, r.rule] for r in rows)
        want = sorted(
            [m["start"], m["end"], m["modality"], m["scope"], m["rule"]] for m in c["mentions"]
        )
        out.append({"suite": "head_attachment", "id": c["id"], "conforms": have == want})
    for c in json.loads((STUDY / "uncovered_controls.json").read_text()):
        rows = fixture(c["text"], c["product_names"], c["id"])
        product = sorted({r.modality for r in rows if r.scope == "PRODUCT_LEVEL"})
        focus = []
        if c["focus"]:
            start = c["text"].index(c["focus"])
            focus = sorted(
                {r.scope for r in rows if r.mention.start == start and r.modality == c["modality"]}
            )
        out.append(
            {
                "suite": "uncovered",
                "id": c["id"],
                "truth": c["truth"],
                "modality": c["modality"],
                "focus_scopes": focus,
                "product_level_modalities": product,
            }
        )
    return out


def _route_input(claim, candidate):
    if claim["extraction_method"] == "clinicaltrials_structured":
        try:
            row = json.loads(claim["supporting_passage"])
        except (TypeError, json.JSONDecodeError):
            return None
        names = [row.get("name")] + list(row.get("otherNames") or [])
        text, field = row.get("description"), "interventions/description"
    else:
        names, text, field = (
            list(candidate.get("aliases") or []),
            claim["supporting_passage"],
            "passage",
        )
    names = tuple(sorted({n for n in names if n}))
    return (text, names, field) if text and names else None


def measure_population():
    rows = []
    for run, path in RUNS.items():
        d = json.loads(path.read_text())
        claims = {c["claim_id"]: c for c in d["claims"]}
        docs = {x["document_id"]: x for x in d["source_documents"]}
        cands = {c["asset_id"]: c for c in d["candidates"]}
        admitted = {
            i
            for g in d["gate_evaluations"]
            for x in g["decisions"]
            if x["requirement_id"] == "modality.required"
            for i in x.get("observed_fact_ids") or []
        }
        for f in (x for x in d["facts"] if x["fact_type"] == "modality_id"):
            evidence = []
            for cid in f["supporting_claim_ids"]:
                c = claims[cid]
                doc = docs[c["source_document_id"]]
                routed = _route_input(c, cands[f["subject_id"]])
                if routed is None:
                    evidence.append(
                        {"claim_id": cid, "route": c["extraction_method"], "scoped": None}
                    )
                    continue
                text, names, field = routed
                src = ScopeSource(
                    artifact=doc.get("snapshot_path") or doc["source_url"],
                    artifact_sha256=doc.get("content_hash") or "",
                    record_id=cid,
                    field=field,
                    product_names=names,
                    product_locator=c["extraction_method"],
                )
                scoped = scoped_modality_assertions(
                    f["subject_id"], text, src, legacy_fact_ids=(f["fact_id"],)
                )
                evidence.append(
                    {
                        "claim_id": cid,
                        "route": c["extraction_method"],
                        "source_url": doc["source_url"],
                        "scoped": [[r.mention.text, r.modality, r.scope, r.rule] for r in scoped],
                    }
                )
            rows.append(
                {
                    "run": run,
                    "fact_id": f["fact_id"],
                    "subject_id": f["subject_id"],
                    "value": f["value"],
                    "admitted": f["fact_id"] in admitted,
                    "evidence": evidence,
                }
            )
    return rows


def categorize(row):
    same = [s for e in row["evidence"] if e["scoped"] for s in e["scoped"] if s[1] == row["value"]]
    other_product = {
        s[1]
        for e in row["evidence"]
        if e["scoped"]
        for s in e["scoped"]
        if s[2] == "PRODUCT_LEVEL" and s[1] not in (None, row["value"])
    }
    scopes = {s[2] for s in same}
    if all(e["scoped"] is None for e in row["evidence"]) or not same:
        cat = "E_NO_SCOPED_EVIDENCE"
    elif "PRODUCT_LEVEL" in scopes:
        cat = "A_PRODUCT"
    elif scopes == {"COMPONENT_LEVEL"}:
        cat = "B_COMPONENT_ONLY"
    elif scopes == {"RELATIONAL_COMPOSITE"}:
        cat = "C_RELATIONAL"
    else:
        cat = "D_AMBIGUOUS"
    conflict = bool(other_product)
    retain = cat == "A_PRODUCT" and not conflict
    return {
        **row,
        "category": cat,
        "conflict": conflict,
        "conflicting_product_modalities": sorted(other_product),
        "proposed": "RETAIN" if retain else "WITHDRAW_TO_UNKNOWN",
    }


def criteria(controls, register, labels):
    unsafe = [
        c["id"]
        for c in controls
        if (
            c["suite"] == "v2"
            and (
                c["expected"] == "NON_PRODUCT"
                and "PRODUCT_LEVEL" in c["focus_scopes"]
                or c["expected"] != "NON_PRODUCT"
                and c["focus_scopes"] != [c["expected"]]
            )
        )
        or (c["suite"] == "head_attachment" and not c["conforms"])
        or (
            c["suite"] == "uncovered"
            and c["truth"] == "NON_PRODUCT"
            and "PRODUCT_LEVEL" in c["focus_scopes"]
        )
    ]
    accounted = all(r.get("category") and r["evidence"] for r in register)
    true_lost = [
        r["fact_id"]
        for r in register
        if r["admitted"] and labels.get(r["fact_id"], {}).get("truth") and r["proposed"] != "RETAIN"
    ]
    selected = [r["fact_id"] for r in register if r["conflict"] and r["proposed"] == "RETAIN"]
    result = {
        "R1": not unsafe,
        "R2": accounted
        and len(register) == 293
        and sum(r["admitted"] for r in register) == 13
        and set(labels) - {"_basis"} <= {r["fact_id"] for r in register},
        "R3": not true_lost,
        "R4": not selected,
    }
    failing = [k for k in ORDER if not result[k]]
    return {
        "requirements": result,
        "first_failing": failing[0] if failing else None,
        "verdict": "IMPLEMENTATION_READY" if not failing else "STOP_NOT_IMPLEMENTATION_READY",
        "unsafe_controls": unsafe,
        "admitted_true_withdrawn": true_lost,
        "conflicts_selected": selected,
    }


def selftest(controls, register, labels):
    good_controls = [
        {
            **c,
            "focus_scopes": [c["expected"]]
            if c["suite"] == "v2" and c["expected"] != "NON_PRODUCT"
            else [],
            "conforms": True,
        }
        for c in controls
    ]
    good_register = [
        {
            **r,
            "proposed": "RETAIN" if labels.get(r["fact_id"], {}).get("truth") else r["proposed"],
            "conflict": False,
        }
        for r in register
    ]
    out = {"valid": criteria(good_controls, good_register, labels)["verdict"]}
    bad = copy.deepcopy(good_controls)
    next(c for c in bad if c["id"] == "MODIFIER_PEPTIDE")["focus_scopes"] = ["PRODUCT_LEVEL"]
    out["unsupported_product_promotion"] = criteria(bad, good_register, labels)["first_failing"]
    lost = copy.deepcopy(good_register)
    next(r for r in lost if r["fact_id"] == "fact:a21e40454f36ee328210")["proposed"] = (
        "WITHDRAW_TO_UNKNOWN"
    )
    out["true_fact_withdrawn"] = criteria(good_controls, lost, labels)["first_failing"]
    out["unregistered_population_change"] = criteria(good_controls, good_register[:-1], labels)[
        "first_failing"
    ]
    sel = copy.deepcopy(good_register)
    sel[0]["conflict"] = True
    out["conflict_selected"] = criteria(good_controls, sel, labels)["first_failing"]
    assert out == {
        "valid": "IMPLEMENTATION_READY",
        "unsupported_product_promotion": "R1",
        "true_fact_withdrawn": "R3",
        "unregistered_population_change": "R2",
        "conflict_selected": "R4",
    }, out
    return out


def build(out):
    for line in (STUDY / "freeze_hashes.txt").read_text().splitlines():
        sha, path = line.split(maxsplit=1)
        assert digest(path) == sha, path
    labels = json.loads((STUDY / "labels.json").read_text())
    controls = measure_controls()
    register = [categorize(r) for r in measure_population()]
    crit = criteria(controls, register, labels)
    adm = [r for r in register if r["admitted"]]
    summary = {
        **crit,
        "selftest": selftest(controls, register, labels),
        "facts": len(register),
        "admitted": len(adm),
        "categories_all": dict(sorted(Counter(r["category"] for r in register).items())),
        "categories_admitted": dict(sorted(Counter(r["category"] for r in adm).items())),
        "proposed_all": dict(sorted(Counter(r["proposed"] for r in register).items())),
        "admitted_truth_vs_proposed": dict(
            sorted(
                Counter(
                    f"{'TRUE' if labels[r['fact_id']]['truth'] else 'FALSE'}->{r['proposed']}"
                    for r in adm
                ).items()
            )
        ),
        "conflicts": sum(r["conflict"] for r in register),
        "missing_provenance_claims": sum(
            e["scoped"] is None for r in register for e in r["evidence"]
        ),
        "routes": dict(
            sorted(Counter(e["route"] for r in register for e in r["evidence"]).items())
        ),
        "uncovered_product_coverage": {
            c["id"]: c["focus_scopes"] for c in controls if c["suite"] == "uncovered"
        },
        "production_changes": 0,
    }
    out.mkdir(parents=True, exist_ok=False)
    for name, value in {
        "controls.json": controls,
        "register.json": register,
        "summary.json": summary,
    }.items():
        (out / name).write_text(canonical(value) + "\n")
    (out / "hashes.json").write_text(
        canonical({p.name: digest(p) for p in sorted(out.iterdir())}) + "\n"
    )
    print(canonical(summary))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)
