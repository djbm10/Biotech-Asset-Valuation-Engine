"""Freeze availability gate inputs and native-CT.gov structural controls."""

import hashlib
import json
from pathlib import Path

ROOT = Path("/home/djmann/projects/bve-b8")
OUT = Path(__file__).parent
RUN = Path("/home/djmann/se_runs/heldout_h19_v4/result.json")
r = json.loads(RUN.read_text())
files = [
    RUN,
    ROOT / "docs/se_policies/therapeutic_product_role_qualification_contract_v1.md",
    ROOT
    / "research/se_therapeutic_product_role_qualification_contract_v1/structural_gap_controls.json",
    ROOT
    / "research/se_therapeutic_product_role_qualification_contract_v1/results/baseline_candidate_decisions.json",
    ROOT / "research/se_h19_candidate_qualification_diagnosis_v1/population.json",
    ROOT / "research/se_h19_candidate_qualification_diagnosis_v1/results/non_asset_routes.json",
]
files += [Path(d["snapshot_path"]) for d in r["source_documents"] if d.get("snapshot_path")]
files += list((ROOT / "tests/se").glob("test_*qualification*.py"))
files += [
    ROOT / "src/bve/se/discovery/asset_qualification.py",
    ROOT / "src/bve/se/discovery/adapters.py",
    ROOT / "src/bve/se/resolution/registry.py",
    ROOT / "src/bve/se/schemas/contracts.py",
    ROOT / "src/bve/se/pipeline.py",
    ROOT / "src/bve/se/ontology/ncit_cell_products.py",
    ROOT / "src/bve/se/ontology/ncit_entity_types.py",
]
files += list((ROOT / "data/se/ontology/ncit").glob("*.json"))
files += [ROOT / "data/se/ontology/modality/chembl_37_molecule_type.json"]
(OUT / "inputs.json").write_text(
    json.dumps(
        {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))},
        sort_keys=True,
        indent=2,
    )
    + "\n"
)
(OUT / "population.json").write_text(
    json.dumps(
        [
            {
                "asset_id": a["asset_id"],
                "name": a["canonical_name"],
                "qualification_reason": a["qualification_reason"],
            }
            for a in r["candidates"]
        ],
        sort_keys=True,
        indent=2,
    )
    + "\n"
)
cases = []
for category, arm_type, purpose, description in [
    (
        "therapeutic",
        "EXPERIMENTAL",
        "TREATMENT",
        "A therapeutic medicinal product under evaluation.",
    ),
    ("diagnostic_imaging", "EXPERIMENTAL", "DIAGNOSTIC", "A substance used only for PET imaging."),
    (
        "supportive",
        "EXPERIMENTAL",
        "TREATMENT",
        "Background supportive medication before the study product.",
    ),
    (
        "conditioning",
        "EXPERIMENTAL",
        "TREATMENT",
        "A preparative conditioning treatment before the study product.",
    ),
    ("comparator", "ACTIVE_COMPARATOR", "TREATMENT", ""),
    ("placebo_control", "PLACEBO_COMPARATOR", "TREATMENT", ""),
    (
        "combination_constituent",
        "EXPERIMENTAL",
        "TREATMENT",
        "One component administered with another intervention.",
    ),
    (
        "drug_nontherapeutic_study",
        "EXPERIMENTAL",
        "BASIC_SCIENCE",
        "An established medicinal product used to measure a physiological response.",
    ),
]:
    interventions = [
        {
            "name": "Intervention X",
            "type": "DRUG",
            "description": description,
            "armGroupLabels": ["Arm A"],
        }
    ]
    names = ["Drug: Intervention X"]
    if category == "combination_constituent":
        interventions.append(
            {"name": "Intervention Y", "type": "DRUG", "armGroupLabels": ["Arm A"]}
        )
        names.append("Drug: Intervention Y")
    cases.append(
        {
            "id": category,
            "synthetic": True,
            "selection_reason": "Native structured context versus product/use semantic level; no new authority fields.",
            "source": {
                "designModule": {"designInfo": {"primaryPurpose": purpose}},
                "armsInterventionsModule": {
                    "interventions": interventions,
                    "armGroups": [{"label": "Arm A", "type": arm_type, "interventionNames": names}],
                },
            },
            "expected_entity_type": "DRUG",
            "expected_arm_type": arm_type,
            "expected_study_purpose": purpose,
            "expected_product_kind": "UNKNOWN",
            "expected_intervention_use": "UNKNOWN",
            "rationale": "Structured fields express entity type, arm membership and study purpose. Description remains unparsed prose; no product/use assertion is invented.",
        }
    )
(OUT / "structural_controls.json").write_text(json.dumps(cases, sort_keys=True, indent=2) + "\n")
print(
    "Frozen",
    len(r["candidates"]),
    "decisions;",
    len(set(files)),
    "inputs;",
    len(cases),
    "additional native-field controls.",
)
