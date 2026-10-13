"""Read-only H19 artifact audit. No pipeline runs or source acquisition."""

import gzip
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

from bve.se.discovery import asset_qualification as q
from bve.se.discovery.adapters import QueryVocabulary, _arm_relationships
from bve.se.discovery.drug_name_shape import (
    is_identity_bearing_drug_name,
    is_corroborative_drug_name,
)
from bve.se.ontology.ncit_entity_types import ncit_entity_types

ROOT = Path("/home/djmann/projects/bve-b8")
STUDY = ROOT / "research/se_h19_candidate_qualification_diagnosis_v1"
RUN = Path("/home/djmann/se_runs/heldout_h19_v4")
OUT = Path("/tmp/h19_qualification_results")
OUT.mkdir(exist_ok=False)
manifest = json.loads((STUDY / "inputs.json").read_text())
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == v for p, v in manifest.items())
pop = json.loads((STUDY / "population.json").read_text())
r = json.loads((RUN / "result.json").read_text())
assets = {a["asset_id"]: a for a in r["candidates"]}
docs = {d["document_id"]: d for d in r["source_documents"]}
claims = {c["claim_id"]: c for c in r["claims"]}
facts = defaultdict(list)
for f in r["facts"]:
    facts[f["subject_id"]].append(f)
gates = {g["subject_id"]: g for g in r["gate_evaluations"]}
mentions = {m["mention_id"]: m for m in r["identity_mentions"]}


def fold(s):
    return re.sub("[^a-z0-9]", "", s.casefold())


def leaves(v, path=()):
    if isinstance(v, dict):
        for k, x in v.items():
            yield from leaves(x, path + (k,))
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from leaves(x, path + (i,))
    elif isinstance(v, str):
        yield list(path), v


source_scan = {"ESG401": [], "BL-M02D1": []}
raw_records = {}
for d in docs.values():
    if not d.get("snapshot_path"):
        continue
    raw = json.loads(Path(d["snapshot_path"]).read_text())
    raw_records[d["document_id"]] = raw
    for path, value in leaves(raw):
        for name in source_scan:
            if fold(name) in fold(value):
                source_scan[name].append({"document": d, "field_path": path, "raw_value": value})
name_scan = {
    name: {
        "candidates": [
            a
            for a in assets.values()
            if any(fold(name) in fold(n) for n in [a["canonical_name"], *a["aliases"]])
        ],
        "identity_mentions": [
            m for m in mentions.values() if fold(name) in fold(m["raw_asset_name"] or "")
        ],
    }
    for name in source_scan
}


def row(a, label, position=None):
    fs = facts[a["asset_id"]]
    cids = sorted(
        set(a.get("supporting_claim_ids", []))
        | {cid for f in fs for cid in f["supporting_claim_ids"]}
    )
    cs = [claims[c] for c in cids if c in claims]
    ms = [mentions[mid] for mid in a["mention_ids"] if mid in mentions]
    ds = sorted({c["source_document_id"] for c in cs} | {m["source_document_id"] for m in ms})
    ev = q.AssetEvidence(
        name=a["canonical_name"],
        structurally_typed_drug=a["structurally_typed_drug"],
        comparator_observations=a["comparator_observations"],
        specific_comparator_observations=a["specific_comparator_observations"],
        therapeutic_observations=a["therapeutic_observations"],
        unknown_observations=a["unknown_observations"],
        entity_specific_link=bool(a["trial_ids"] or a["company_ids"]),
    )
    reason = q.qualification_reason(ev)
    types = ncit_entity_types()
    authority = {
        "identity_bearing_name": is_identity_bearing_drug_name(a["canonical_name"]),
        "corroborative_name": is_corroborative_drug_name(a["canonical_name"]),
        "ncit_non_product_concepts": types.non_product_concepts(a["canonical_name"])
        if types
        else [],
        "qualification_veto": q.qualification_veto(a["canonical_name"]),
        "authority_modality": a["authority_modality"],
        "authority_modality_basis": a["authority_modality_basis"],
    }
    if label == "NON_ASSET":
        bucket = "A_NON_ASSET_ADMISSION"
        boundary = "STRUCTURED_INTERVENTION_ROLE_TO_THERAPEUTIC_QUALIFICATION"
        cause = "Experimental-arm membership is promoted to therapeutic product role; generic category and diagnostic use are not represented."
    elif label == "DUPLICATE":
        bucket = "E_IDENTITY"
        boundary = "IDENTITY_CONSOLIDATION_SEPARATE_MILESTONE"
        cause = "Frozen duplicate; candidate qualification itself is not the failure."
    elif label == "WRONG_TARGET":
        bucket = "F_OTHER"
        boundary = "TARGET_EVIDENCE_UNKNOWN_REVIEW_INCLUSION_OUT_OF_SCOPE"
        cause = "Real product; qualification is valid, query-target relevance is not established. No qualification repair assigned."
    elif label == "REFERENCE_MISS":
        bucket = "B_FALSE_PRODUCT_TYPE_EXCLUSION"
        boundary = "MODALITY_EXTRACTION_PRODUCT_COMPONENT_SCOPE"
        cause = "Qualified ADC receives PEPTIDE modality fact from a tetrapeptide linker description; downstream modality gate excludes."
    else:
        bucket = "NONE"
        boundary = "NONE_FOR_CANDIDATE_QUALIFICATION"
        cause = "Frozen relevant row; human-PoC defect, if any, remains separately stopped."
    return {
        "position": position,
        "expected_entity": a["canonical_name"],
        "frozen_label": label,
        "emitted": position is not None,
        "candidate": a,
        "extracted_names": ms,
        "authority_facts": authority,
        "recorded_qualification_route": a["qualification_reason"],
        "current_decisive_route_probe": reason.value if reason else None,
        "probe_limit": "Uses persisted decisive evidence only, not a replay of corpus prose corroboration.",
        "final_qualification": "QUALIFIED" if a["qualification_reason"] else "NO_RECORDED_REASON",
        "candidate_sets": [
            k
            for k in [
                "eligible_asset_ids",
                "excluded_asset_ids",
                "unresolved_asset_ids",
                "low_support_asset_ids",
            ]
            if a["asset_id"] in r[k]
        ],
        "gate": gates.get(a["asset_id"]),
        "structured_type_facts": fs,
        "claims": cs,
        "source_records": [docs[d] for d in ds],
        "first_failure_boundary": boundary,
        "bucket": bucket,
        "root_cause": cause,
    }


rows = [
    row(assets[label["asset_id"]], label["label"], label["position"]) for label in pop["emitted"]
]
dato = next(
    a for a in assets.values() if a["canonical_name"].casefold() == "datopotamab deruxtecan"
)
rows.append(row(dato, "REFERENCE_MISS"))
for name, bucket, boundary in [
    ("ESG401", "C_NAME_EXTRACTION_CANDIDATE_NOMINATION", "ARM_DESCRIPTION_NAME_NOT_NOMINATED"),
    ("BL-M02D1", "D_SOURCE_COVERAGE_DISCOVERY", "ABSENT_FROM_CAPTURED_CORPUS"),
]:
    rows.append(
        {
            "position": None,
            "expected_entity": name,
            "frozen_label": "REFERENCE_MISS",
            "emitted": False,
            "candidate": None,
            "extracted_names": name_scan[name],
            "source_records": source_scan[name],
            "authority_facts": None,
            "structured_type_facts": [],
            "recorded_qualification_route": None,
            "final_qualification": "NOT_REACHED",
            "first_failure_boundary": boundary,
            "bucket": bucket,
            "root_cause": "No named candidate reaches qualification; do not repair through qualification.",
        }
    )
non_assets = []
for entry in rows:
    if entry["frozen_label"] != "NON_ASSET":
        continue
    a = entry["candidate"]
    observations = []
    for d in docs.values():
        raw = raw_records.get(d["document_id"], {})
        if raw.get("identificationModule", {}).get("nctId") not in a["trial_ids"]:
            continue
        module = raw.get("armsInterventionsModule", {})
        for i, intervention in enumerate(module.get("interventions", [])):
            if fold(intervention.get("name", "")) not in {
                fold(n) for n in [a["canonical_name"], *a["aliases"]]
            }:
                continue
            observations.append(
                {
                    "document": d,
                    "raw_intervention": intervention,
                    "field_path": ["armsInterventionsModule", "interventions", i],
                    "all_arm_groups": module.get("armGroups", []),
                    "design": raw.get("designModule", {}),
                    "description": raw.get("descriptionModule", {}),
                    "current_arm_relationships": {
                        k: v.value for k, v in _arm_relationships(raw).items()
                    },
                }
            )
    non_assets.append(
        {
            "name": a["canonical_name"],
            "authority_route_probes": entry["authority_facts"],
            "recorded_route": a["qualification_reason"],
            "observations": observations,
        }
    )
claim = claims["claim:2022030306a59db4acec"]
intervention = json.loads(claim["supporting_passage"])
context = " ".join(
    [intervention["name"], intervention.get("description", ""), *intervention.get("otherNames", [])]
)
vocab = QueryVocabulary.for_ontology()
modality_probe = {
    "selected": vocab.modality_in(context),
    "context": context,
    "matches": [
        {"modality": m, "terms": [t for t in terms if t in context.casefold()]}
        for m, terms in vocab.modalities
        if any(t in context.casefold() for t in terms)
    ],
}
dato_audit = {
    "claim": claim,
    "document": docs[claim["source_document_id"]],
    "raw_protocol": raw_records[claim["source_document_id"]],
    "probe": modality_probe,
    "candidate": dato,
    "facts": facts[dato["asset_id"]],
    "gate": gates[dato["asset_id"]],
    "identity_events": [
        e
        for k in ["identity_merges", "identity_edges"]
        for e in r[k]
        if dato["asset_id"] in json.dumps(e) or claim["subject_id"] in json.dumps(e)
    ],
    "conclusion": "PEPTIDE is lexical modality output from a linker component, not an ontology parent, target, or erroneous identity merge. The ADC qualifies; modality.required is the exclusion boundary.",
}
control_results = []
for c in pop["controls"]:
    if "evidence" in c:
        observed = q.qualifies_as_asset(q.AssetEvidence(**c["evidence"]))
        control_results.append(
            c
            | {
                "observed": observed,
                "matches_existing_expectation": observed == c["expected_current_qualifies"],
            }
        )
    elif c["id"] == "PRECEDENCE":
        with (
            patch.object(q.drug_name_shape, "is_identity_bearing_drug_name", return_value=True),
            patch.object(q.class_terms, "is_class_term", return_value=False),
            patch.object(
                q, "qualification_veto", return_value=("SYNTHETIC_NON_PRODUCT_TYPE", ["synthetic"])
            ),
        ):
            route = q.qualification_reason(q.AssetEvidence(name=c["name"]))
        control_results.append(
            c
            | {
                "observed_route": route.value,
                "matches_existing_expectation": route.value == c["expected_current_route"],
            }
        )
    else:
        control_results.append(c | {"evaluation": "SEMANTIC_DESIGN_CONTROL_ONLY_NO_NEW_RULE"})
reference_coverage = []
for aliases in pop["references"]:
    matches = [
        a["asset_id"]
        for a in assets.values()
        if any(
            fold(alias) == fold(n)
            for alias in aliases
            for n in [a["canonical_name"], *a["aliases"]]
        )
    ]
    reference_coverage.append(
        {
            "reference": aliases[0],
            "aliases": aliases,
            "candidate_ids": matches,
            "row_names": [
                x["expected_entity"]
                for x in rows
                if x.get("candidate") and x["candidate"]["asset_id"] in matches
            ],
        }
    )
outputs = {
    "row_audit.json.gz": rows,
    "non_asset_routes.json": non_assets,
    "datopotamab_type_lineage.json": dato_audit,
    "source_scan.json": source_scan,
    "candidate_name_scan.json": name_scan,
    "controls.json": control_results,
    "reference_coverage.json": reference_coverage,
}
for name, data in outputs.items():
    raw = (json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    (OUT / name).write_bytes(gzip.compress(raw, mtime=0) if name.endswith(".gz") else raw)
summary = {
    "rows": len(rows),
    "emitted_rows": 20,
    "references": len(reference_coverage),
    "snapshots_scanned": len(raw_records),
    "non_snapshot_source_documents": len(docs) - len(raw_records),
    "esg401_field_hits": len(source_scan["ESG401"]),
    "bl_m02d1_field_hits": len(source_scan["BL-M02D1"]),
    "esg401_candidates": len(name_scan["ESG401"]["candidates"]),
    "esg401_mentions": len(name_scan["ESG401"]["identity_mentions"]),
    "datopotamab_qualification": dato["qualification_reason"],
    "datopotamab_modality_probe": modality_probe["selected"],
    "controls_pass": all(c.get("matches_existing_expectation", True) for c in control_results),
    "inputs_unchanged": True,
}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary))
