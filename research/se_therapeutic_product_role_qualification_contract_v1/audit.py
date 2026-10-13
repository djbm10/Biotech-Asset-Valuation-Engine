"""Existing design contract audit; no new decision rule or production behavior."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from bve.se.discovery.asset_qualification import AssetEvidence, qualification_reason

ROOT = Path("/home/djmann/projects/bve-b8")
STUDY = ROOT / "research/se_therapeutic_product_role_qualification_contract_v1"
DIAG = ROOT / "research/se_h19_candidate_qualification_diagnosis_v1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build(output):
    pinned = json.loads((STUDY / "inputs.json").read_text())
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha for p, sha in pinned.items())
    rows = json.loads(gzip.open(DIAG / "results/row_audit.json.gz").read())
    controls = json.loads((DIAG / "population.json").read_text())["controls"]
    observations = json.loads((DIAG / "results/non_asset_routes.json").read_text())
    by_name = {x["name"]: x["observations"] for x in observations}
    audit = []
    for row in rows:
        name = row["expected_entity"]
        asset = row.get("candidate")
        nonasset = row["frozen_label"] == "NON_ASSET"
        scope = "PRODUCT" if asset else "NOT_NOMINATED"
        obs = by_name.get(name, [])
        audit.append(
            {
                "id": "H19:" + str(row["position"] or name),
                "entity": name,
                "source_fields": [
                    {
                        "document": o["document"],
                        "path": o["field_path"],
                        "raw_intervention": o["raw_intervention"],
                        "design": o["design"],
                    }
                    for o in obs
                ]
                or [
                    {
                        "frozen_artifact": "row_audit.json.gz",
                        "entity": name,
                        "document_ids": [
                            d["document_id"]
                            for d in row.get("source_records", [])
                            if "document_id" in d
                        ],
                    }
                ],
                "claim_subject": asset["asset_id"] if asset else None,
                "identity_level": scope,
                "intrinsic_kind": (
                    "DIAGNOSTIC_SUBSTANCE_PER_EXPLICIT_SOURCE"
                    if name == "[68Ga]Ga-TTP"
                    else "GENERIC_SUPPORTIVE_CATEGORY_PER_EXPLICIT_SOURCE"
                )
                if nonasset
                else "THERAPEUTIC_PER_FROZEN_LABEL_NOT_A_NEW_MACHINE_ASSERTION"
                if asset
                else "NOT_REACHED",
                "observation_role": (
                    "DIAGNOSTIC_IMAGING" if name == "[68Ga]Ga-TTP" else "SUPPORTIVE_PREMEDICATION"
                )
                if nonasset
                else "NOT_ADJUDICATED_OUTSIDE_QUALIFICATION_DEFECT",
                "positive_negative_ambiguous_evidence": {
                    "recorded_candidate_qualification": row["recorded_qualification_route"],
                    "frozen_label": row["frozen_label"],
                    "authority_facts": row.get("authority_facts"),
                    "context_is_not_product_identity": nonasset,
                },
                "current_route": row["recorded_qualification_route"],
                "proposed_qualification_outcome": "WITHHOLD_CONTEXT_ONLY_QUALIFICATION_PENDING_SCOPED_EVIDENCE"
                if nonasset
                else "PRESERVE_EXISTING_QUALIFICATION"
                if asset
                else "NOT_REACHED_OUT_OF_SCOPE",
                "rule_implemented": False,
                "unresolved_boundary": "Role/kind source claims are absent from AssetEvidence; no frozen operational replacement rule."
                if nonasset
                else "No change within this milestone.",
                "evidence_origin": "Frozen diagnosis and original source fields; not a new biological authority.",
            }
        )
    for control in controls:
        observed = None
        if "evidence" in control:
            found = qualification_reason(AssetEvidence(**control["evidence"]))
            observed = found.value if found else None
        audit.append(
            {
                "id": control["id"],
                "entity": control.get("evidence", {}).get(
                    "name", control.get("name", control.get("kind"))
                ),
                "source_fields": [
                    {
                        "frozen_artifact": "population.json",
                        "control_id": control["id"],
                        "raw_control": control,
                    }
                ],
                "claim_subject": control["id"],
                "identity_level": "STIPULATED_CONTROL_NOT_AUTHORITY_IDENTITY",
                "intrinsic_kind": control["kind"],
                "observation_role": control.get("description", "NOT_SPECIFIED"),
                "positive_negative_ambiguous_evidence": control,
                "current_route": observed,
                "proposed_qualification_outcome": (
                    "PROTECT_STIPULATED_THERAPEUTIC"
                    if control["stipulated_product_identity"]
                    else "DO_NOT_INFER_THERAPEUTIC_FROM_CONTEXT"
                )
                if "stipulated_product_identity" in control
                else "PRESERVE_EXISTING_CONTROL_OR_ISOLATE_PRECEDENCE",
                "rule_implemented": False,
                "unresolved_boundary": "Synthetic semantic descriptions lack a source-to-qualification binding rule."
                if control.get("synthetic")
                else "Existing regression expectation, not independent product-level authority evidence.",
            }
        )
    gaps = json.loads((STUDY / "structural_gap_controls.json").read_text())["controls"]
    serialized = []
    for c in gaps:
        e = AssetEvidence(**c["qualification_input"])
        reason = qualification_reason(e)
        serialized.append(e.model_dump())
        audit.append(
            {
                "id": c["id"],
                "entity": e.name,
                "source_fields": c["source"],
                "claim_subject": "synthetic-intervention",
                "identity_level": "SINGLE_PRODUCT_OR_SUBSTANCE",
                "intrinsic_kind": c["semantic_expectation"],
                "observation_role": "EXPERIMENTAL_ARM_MEMBER",
                "current_route": reason.value if reason else None,
                "qualification_input": e.model_dump(),
                "proposed_qualification_outcome": c["semantic_expectation"],
                "unresolved_boundary": "Identical qualification inputs despite distinct source semantics.",
                "rule_implemented": False,
            }
        )
    assert serialized[0] == serialized[1]
    run = json.loads(Path("/home/djmann/se_runs/heldout_h19_v4/result.json").read_text())
    baseline = [
        {
            "asset_id": a["asset_id"],
            "name": a["canonical_name"],
            "qualification_reason": a["qualification_reason"],
        }
        for a in run["candidates"]
    ]
    summary = {
        "design_rows": len(audit),
        "original_diagnosis_rows": len(rows),
        "original_controls": len(controls),
        "additional_frozen_controls": len(gaps),
        "pinned_inputs_unchanged": True,
        "model_fields": sorted(AssetEvidence.model_fields),
        "identical_input_distinct_semantics": True,
        "implementation_ready": False,
        "boundary": "ROLE_AND_PRODUCT_KIND_NOT_REPRESENTED_IN_QUALIFICATION_INPUT",
        "baseline_candidate_decisions": len(baseline),
        "changed_decisions": 0,
        "true_therapeutic_controls_losing_qualification": 0,
        "implementation": "NOT_STARTED",
        "before_after": "UNCHANGED_BASELINE_NOT_AN_IMPLEMENTATION_RESULT",
        "contract": "d22f6b8 unchanged; D8 documented architecture boundary",
    }
    output.mkdir(parents=True, exist_ok=False)
    for name, data in [
        ("subject_scope_audit.json", audit),
        ("baseline_candidate_decisions.json", baseline),
        ("summary.json", summary),
    ]:
        (output / name).write_text(canonical(data) + "\n")
    lines = [
        "# Frozen subject/scope audit",
        "",
        "| Case | Entity | Kind/scope | Current route | Proposed design outcome (not implemented) |",
        "|---|---|---|---|---|",
    ]
    for a in audit:
        lines.append(
            "| "
            + " | ".join(
                str(a.get(k)).replace("|", "/")
                for k in [
                    "id",
                    "entity",
                    "intrinsic_kind",
                    "current_route",
                    "proposed_qualification_outcome",
                ]
            )
            + " |"
        )
    (output / "subject_scope_table.md").write_text("\n".join(lines) + "\n")
    (output / "hashes.json").write_text(
        canonical(
            {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())}
        )
        + "\n"
    )
    print(canonical(summary))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)
