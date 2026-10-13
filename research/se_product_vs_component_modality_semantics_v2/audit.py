"""Execute the frozen v2 design; do not change the adopted scope implementation."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from bve.se.evidence.modality_scope import ScopeSource, scoped_modality_assertions

ROOT = Path("/home/djmann/projects/bve-b8")
STUDY = ROOT / "research/se_product_vs_component_modality_semantics_v2"
OLD = ROOT / "research/se_modality_assertion_scope_representation_v1"


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build(out):
    for p, h in json.loads((STUDY / "inputs.json").read_text()).items():
        assert digest(Path(p)) == h, p
    controlpath = STUDY / "additional_controls.json"
    controls = json.loads(controlpath.read_text())
    scored = []
    for i, c in enumerate(controls):
        source = ScopeSource(
            artifact=str(controlpath),
            artifact_sha256=digest(controlpath),
            record_id=c["id"],
            field=f"/{i}/text",
            product_names=("Novel Product",),
            product_locator="fixture subject Novel Product",
        )
        rows = scoped_modality_assertions("fixture:Novel Product", c["text"], source)
        start = c["text"].casefold().index(c["focus"].casefold())
        end = start + len(c["focus"])
        focus = [r for r in rows if r.mention.start == start and r.mention.end == end]
        assert focus
        statuses = {r.scope for r in focus}
        adequate = (
            not bool(statuses & {"PRODUCT_LEVEL"})
            if c["expected_scope"] == "NON_PRODUCT"
            else statuses == {c["expected_scope"]}
        )
        for r in rows:
            assert c["text"][r.mention.start : r.mention.end] == r.mention.text
        scored.append(
            {
                **c,
                "actual_focus_scopes": sorted(statuses),
                "scope_sufficient_for_proposed_consumer": adequate,
                "assertions": [r.model_dump(mode="json") for r in rows],
                "semantic_permission": "CONFLICT_FAIL_CLOSED"
                if c["id"].startswith("CONFLICT")
                else "NOT_IMPLEMENTED",
            }
        )
    runpath = Path("/home/djmann/se_runs/heldout_h19_v4/result.json")
    run = json.loads(runpath.read_text())
    facts = [f for f in run["facts"] if f["fact_type"] == "modality_id"]
    claims = {c["claim_id"]: c for c in run["claims"]}
    assets = {a["asset_id"]: a for a in run["candidates"]}
    docs = {d["document_id"]: d for d in run["source_documents"]}
    scoped = json.loads((OLD / "results/h19_assertions.json").read_text())
    entailment = run["entailment_results"]
    registers = []
    for f in facts:
        supporting = [claims[i] for i in f["supporting_claim_ids"]]
        ss = [a for a in scoped if f["fact_id"] in a["legacy_fact_ids"]]
        matches = [a for a in ss if a["modality"] == f["value"]]
        scopes = {a["scope"] for a in matches}
        category = (
            "A_PRODUCT_SUPPORTED"
            if "PRODUCT_LEVEL" in scopes
            else (
                "B_COMPONENT_ONLY"
                if scopes == {"COMPONENT_LEVEL"}
                else "C_RELATIONAL"
                if scopes == {"RELATIONAL_COMPOSITE"}
                else "D_AMBIGUOUS_OR_MISSING"
            )
        )
        gates = [
            d
            for g in run["gate_evaluations"]
            if g["subject_id"] == f["subject_id"]
            for d in g["decisions"]
            if d["requirement_id"] == "modality.required"
        ]
        registers.append(
            {
                "candidate": assets[f["subject_id"]],
                "legacy_fact": f,
                "claims": supporting,
                "sources": [docs[c["source_document_id"]] for c in supporting],
                "entailment_results": [
                    e for e in entailment if e.get("claim_id") in f["supporting_claim_ids"]
                ],
                "scoped_assertions": ss,
                "legacy_value_assertion_scopes": sorted(scopes),
                "category": category,
                "current_gate": gates,
                "proposed_semantic_disposition": {
                    "A_PRODUCT_SUPPORTED": "PRODUCT_LEVEL_CANDIDATE_SUPPORT",
                    "B_COMPONENT_ONLY": "COMPONENT_ONLY_CANNOT_INDEPENDENTLY_SUPPORT_WHOLE_PRODUCT",
                    "C_RELATIONAL": "REQUIRES_SEPARATE_COMPOSITE_POLICY",
                    "D_AMBIGUOUS_OR_MISSING": "NON_DECISIVE",
                }[category],
                "potential_replacement_assertions": [
                    a["assertion_id"] for a in ss if a["scope"] == "PRODUCT_LEVEL"
                ],
                "authorized_action": "NONE_BLOCKED_SCOPE_CERTIFICATION",
                "current_fact_action": "RETAIN_LEGACY_PENDING_SAFE_CONSUMER",
                "production_delta": False,
            }
        )
    # Stop rule from population_freeze.md: any NON_PRODUCT control receiving PRODUCT_LEVEL.
    unsafe = [
        c["id"]
        for c in scored
        if c["expected_scope"] == "NON_PRODUCT" and "PRODUCT_LEVEL" in c["actual_focus_scopes"]
    ]
    summary = {
        "design_status": "STOP_UNSAFE_PRODUCT_LEVEL_CERTIFICATION" if unsafe else "NO_STOP_TRIGGERED",
        "stop_triggering_controls": unsafe,
        "additional_controls": len(scored),
        "adequate_controls": sum(c["scope_sufficient_for_proposed_consumer"] for c in scored),
        "inadequate_controls": [
            c["id"] for c in scored if not c["scope_sufficient_for_proposed_consumer"]
        ],
        "legacy_modality_facts": len(facts),
        "fact_categories": dict(Counter(r["category"] for r in registers)),
        "emitter_counts": dict(
            Counter(
                c["extraction_method"]
                for f in facts
                for c in [claims[i] for i in f["supporting_claim_ids"]]
            )
        ),
        "stored_candidates": len(run["candidates"]),
        "source_documents": len(run["source_documents"]),
        "production_changes": 0,
        "semantic_implementation": "NOT_STARTED",
        "scope_representation": "PRESERVED_UNCHANGED",
        "implementation_ready_delta": "NOT_AUTHORIZED",
    }
    out.mkdir(parents=True, exist_ok=False)
    for name, value in {
        "control_results.json": scored,
        "proposed_action_register.json": registers,
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
