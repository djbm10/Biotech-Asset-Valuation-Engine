"""Red-first semantic probes: expected to fail on unmodified baseline."""

import json
from pathlib import Path
import pytest
from bve.se.discovery.asset_qualification import AssetEvidence, qualifies_as_asset

ROOT = Path("/home/djmann/projects/bve-b8")
DIAG = ROOT / "research/se_h19_candidate_qualification_diagnosis_v1"
STUDY = ROOT / "research/se_therapeutic_product_role_qualification_contract_v1"


@pytest.mark.parametrize("name", ["[68Ga]Ga-TTP", "Rescue Medications", "Rescue Medication"])
def test_frozen_nonasset_requires_more_than_context(name):
    result = json.loads(Path("/home/djmann/se_runs/heldout_h19_v4/result.json").read_text())
    a = next(a for a in result["candidates"] if a["canonical_name"] == name)
    evidence = AssetEvidence(
        name=name,
        structurally_typed_drug=a["structurally_typed_drug"],
        therapeutic_observations=a["therapeutic_observations"],
        entity_specific_link=bool(a["trial_ids"] or a["company_ids"]),
    )
    assert not qualifies_as_asset(evidence)


def test_diagnostic_structural_control_requires_product_evidence():
    cases = json.loads((STUDY / "structural_gap_controls.json").read_text())["controls"]
    assert not qualifies_as_asset(AssetEvidence(**cases[1]["qualification_input"]))


def test_positive_structural_control_is_protected():
    cases = json.loads((STUDY / "structural_gap_controls.json").read_text())["controls"]
    assert qualifies_as_asset(AssetEvidence(**cases[0]["qualification_input"]))


@pytest.mark.parametrize("name", ["benzhexol", "ibritumomab", "lestaurinib"])
def test_existing_therapeutic_controls_are_protected(name):
    controls = json.loads((DIAG / "population.json").read_text())["controls"]
    control = next(c for c in controls if c["id"] == "P_" + name)
    assert qualifies_as_asset(AssetEvidence(**control["evidence"]))
