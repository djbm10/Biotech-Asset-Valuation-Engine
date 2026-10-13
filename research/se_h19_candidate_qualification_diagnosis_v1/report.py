"""Freeze row boundary table and verify diagnosis custody, without scoring."""

import gzip
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path("/home/djmann/projects/bve-b8")
OUT = Path("/tmp/h19_qualification_results")
STUDY = ROOT / "research/se_h19_candidate_qualification_diagnosis_v1"
rows = json.loads(gzip.open(OUT / "row_audit.json.gz").read())
pop = json.loads((STUDY / "population.json").read_text())
r = json.loads(Path("/home/djmann/se_runs/heldout_h19_v4/result.json").read_text())
assert [(x["position"], x["candidate"]["asset_id"], x["frozen_label"]) for x in rows[:20]] == [
    (x["position"], x["asset_id"], x["label"]) for x in pop["emitted"]
]
assert {x["expected_entity"] for x in rows[20:]} == {"Datopotamab deruxtecan", "ESG401", "BL-M02D1"}
assert len(json.loads((OUT / "reference_coverage.json").read_text())) == 5
assert len(rows) == 23
ids = {d["document_id"] for d in r["source_documents"]}
claimids = {c["claim_id"] for c in r["claims"]}
for row in rows:
    assert all(
        c["claim_id"] in claimids and c["source_document_id"] in ids for c in row.get("claims", [])
    )
manifest = json.loads((STUDY / "inputs.json").read_text())
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in manifest.items())
types = json.loads((ROOT / "data/se/ontology/modality/chembl_37_molecule_type.json").read_text())
claim = next(c for c in r["claims"] if c["claim_id"] == "claim:2022030306a59db4acec")
doc = next(d for d in r["source_documents"] if d["document_id"] == claim["source_document_id"])
raw = json.loads(Path(doc["snapshot_path"]).read_text())
intervention = json.loads(claim["supporting_passage"])
index = raw["armsInterventionsModule"]["interventions"].index(intervention)
lineage = {
    "claim_id": claim["claim_id"],
    "exact_field_path": ["armsInterventionsModule", "interventions", index, "description"],
    "document": doc,
    "raw_description": intervention["description"],
    "semantic_subject": "LINKER_COMPONENT",
    "not_an_ontology_peptide_assertion": True,
    "canonical_ontology_identity": "DRUG:DATOPOTAMAB DERUXTECAN",
    "chembl_identity": "CHEMBL4297939",
    "authority_product_type": types["molecule_types"]["CHEMBL4297939"],
    "authority_release": types["release"],
    "authority_source_sha256": types["source_sha256"],
    "authority_field_path": ["molecule_types", "CHEMBL4297939"],
    "fact_id": "fact:71c28d48f9461eb004d3",
    "qualified_route": "DIRECT_APPROVED_NAME",
    "first_failure": "Lexical modality assignment confuses component description with product type, before modality.required exclusion.",
}
(OUT / "datopotamab_exact_field.json").write_text(
    json.dumps(lineage, sort_keys=True, indent=2) + "\n"
)
lines = [
    "# Frozen H19 first-boundary register",
    "",
    "All 20 emitted rows plus the three missing references. The other two references are rows 1 and 2. Full fields, sources, claims, facts and gates are in `row_audit.json.gz`. NONE means no candidate-qualification failure; it does not assert that every other claim is correct.",
    "",
    "| Position | Entity | Frozen label | Qualification route | First boundary | Bucket |",
    "|---|---|---|---|---|---|",
]
for row in rows:
    lines.append(
        "| "
        + " | ".join(
            str(v).replace("|", "/")
            for v in [
                row["position"] or "Not emitted",
                row["expected_entity"],
                row["frozen_label"],
                row["recorded_qualification_route"] or "NOT_REACHED",
                row["first_failure_boundary"],
                row["bucket"],
            ]
        )
        + " |"
    )
(OUT / "row_table.md").write_text("\n".join(lines) + "\n")
for f, t in [("/tmp/h19_qualification_tests.log", "qualification_tests.log")]:
    shutil.copy2(f, OUT / t)
log = Path("/tmp/h19_qualification_tests.log").read_text()
passed = sum(line.split("[")[0].count(".") for line in log.splitlines())
validation = {
    "rows": 23,
    "emitted": 20,
    "references": 5,
    "buckets": dict(Counter(x["bucket"] for x in rows)),
    "all_frozen_inputs_unchanged": True,
    "claim_and_document_links_valid": True,
    "existing_qualification_tests_passed": passed,
    "live_replays_or_acquisition": False,
    "production_changes": False,
    "full_tests_se": "Not required: diagnosis only.",
}
(OUT / "validation.json").write_text(json.dumps(validation, sort_keys=True, indent=2) + "\n")
(OUT / "artifact_hashes.json").write_text(
    json.dumps(
        {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(OUT.iterdir())
            if p.name != "artifact_hashes.json"
        },
        sort_keys=True,
        indent=2,
    )
    + "\n"
)
print(json.dumps(validation))
