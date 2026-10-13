"""Freeze diagnosis inputs/controls before proposing any qualification rule."""

import hashlib
import json
from pathlib import Path

ROOT = Path("/home/djmann/projects/bve-b8")
RUN = Path("/home/djmann/se_runs/heldout_h19_v4")
OUT = Path(__file__).parent
result = json.loads((RUN / "result.json").read_text())
labels = json.loads((ROOT / "research/se_heldout/v4_primary_validation/labels.json").read_text())[
    "queries"
]["H19"]["rows"]
references = [
    ["sacituzumab govitecan", "Trodelvy", "IMMU-132"],
    ["datopotamab deruxtecan", "Datroway", "Dato-DXd", "DS-1062"],
    ["sacituzumab tirumotecan", "sac-TMT", "MK-2870", "SKB264"],
    ["ESG401"],
    ["BL-M02D1"],
]
structural = [
    ("antibody", "A monoclonal antibody therapeutic administered to treat disease.", True),
    ("ADC", "An antibody-drug conjugate with a peptide linker and cytotoxic payload.", True),
    ("peptide", "A peptide therapeutic administered to treat disease.", True),
    ("protein", "A recombinant protein therapeutic administered to treat disease.", True),
    (
        "diagnostic",
        "A diagnostic substance used to identify disease, without therapeutic intent.",
        False,
    ),
    ("imaging", "A radiotracer used only for PET imaging; no anticancer treatment.", False),
    (
        "supportive",
        "Unspecified rescue medications: antihistamines, acetaminophen, and steroids.",
        False,
    ),
    ("regimen", "A list of two independently named drugs, not one fixed-dose product.", False),
    ("procedure", "A diagnostic imaging procedure, not a substance or therapeutic product.", False),
    ("biomarker", "A measured biomarker expression level, not an administered product.", False),
    ("reagent", "A laboratory assay reagent used only ex vivo.", False),
    (
        "supportive_real_product",
        "One named therapeutic drug used as supportive care in this trial.",
        True,
    ),
]
controls = [
    {
        "id": f"S{i:02}",
        "kind": k,
        "description": t,
        "stipulated_product_identity": v,
        "synthetic": True,
        "note": "Semantic structural control, not a claim about a real product or frozen pass rule.",
    }
    for i, (k, t, v) in enumerate(structural, 1)
]
controls += [
    {
        "id": "P_" + name,
        "kind": "existing_positive",
        "evidence": {
            "name": name,
            "support": 1,
            "pharmacologic_context": True,
            "pharmacologic_documents": 2,
            "entity_specific_link": True,
        },
        "expected_current_qualifies": True,
    }
    for name in ["benzhexol", "ibritumomab", "lestaurinib"]
]
controls += [
    {
        "id": "N_" + name,
        "kind": "existing_negative",
        "evidence": {"name": name, "support": 100},
        "expected_current_qualifies": False,
    }
    for name in ["although", "before", "baseline", "Euroflow", "IQR"]
]
controls += [
    {
        "id": "PRECEDENCE",
        "kind": "synthetic_route_probe",
        "name": "synthetic authority molecule",
        "direct_name_authority": True,
        "explicit_non_product_veto": True,
        "expected_current_route": "DIRECT_APPROVED_NAME",
        "note": "Controlled route-order observation only; does not decide future conflict policy.",
    }
]
files = [
    RUN / "result.json",
    RUN / "run_manifest.json",
    ROOT / "research/se_heldout/v4_primary_validation/labels.json",
    ROOT / "research/se_heldout/v4_primary_validation/report.md",
    ROOT / "docs/se_policies/primary_validation_failure_diagnosis_v1.md",
]
files += [Path(d["snapshot_path"]) for d in result["source_documents"] if d.get("snapshot_path")]
files += list((ROOT / "src/bve/se/discovery").glob("*.py"))
files += [
    ROOT / p
    for p in [
        "src/bve/se/resolution/registry.py",
        "src/bve/se/gates/engine.py",
        "src/bve/se/pipeline.py",
        "src/bve/se/ontology/ncit_entity_types.py",
        "src/bve/se/ontology/drug_modality.py",
        "src/bve/se/ontology/sources/chembl_drug.py",
    ]
]
files += list((ROOT / "tests/se").glob("test_*qualification*.py"))
files += list((ROOT / "data/se/ontology/ncit").glob("*.json"))
files += [ROOT / "data/se/ontology/modality/chembl_37_molecule_type.json"]
manifest = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}
for name, value in [
    ("population.json", {"emitted": labels, "references": references, "controls": controls}),
    ("inputs.json", manifest),
]:
    (OUT / name).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
print(len(labels), len(references), len(controls), len(manifest))
