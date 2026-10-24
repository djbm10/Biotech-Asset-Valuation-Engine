"""Reporting-only follow-up: evidence custody and orthogonal commercial context."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "research/se_lead_verification_v1"
spec = importlib.util.spec_from_file_location("lead_handoff", ROOT / "handoff.py")
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def data():
    return json.loads((ROOT / "leads.json").read_text())


def test_final_handoff_is_deterministic_and_keeps_commercial_unknowns():
    value = data()
    rendered = module.render(value)
    assert rendered == module.render(copy.deepcopy(value))
    assert rendered == (ROOT / "BRIEF.md").read_text()
    assert "ACQUIRED_PROGRAM" in rendered
    assert "PRECLINICAL_RESEARCH_LEAD" in rendered
    for lead in value["leads"]:
        assert lead["facts"]["territorial_rights"]["status"] == "UNKNOWN"
        assert lead["facts"]["availability"]["status"] == "UNKNOWN"
    assert "independent BD review **OUTSTANDING**" in rendered


@pytest.mark.parametrize("field", ["identity", "company_relationship", "target_format"])
def test_supported_claim_without_citation_rejected(field):
    lead = data()["leads"][1]
    lead["facts"][field]["sources"] = []
    with pytest.raises(ValueError, match="primary source links"):
        module.Lead.model_validate(lead)


def test_acquired_context_requires_company_evidence_not_sponsor_inference():
    lead = data()["leads"][1]
    lead["facts"]["company_relationship"]["status"] = "UNKNOWN"
    with pytest.raises(ValueError, match="company evidence"):
        module.Lead.model_validate(lead)


def test_inadequate_identity_cannot_be_promoted_by_display():
    lead = data()["leads"][0]
    lead["facts"]["identity"]["status"] = "UNKNOWN"
    with pytest.raises(ValueError, match="source-backed identity"):
        module.Lead.model_validate(lead)
    lead["research_category"] = "INSUFFICIENTLY_IDENTIFIED"
    assert module.Lead.model_validate(lead).research_category == "INSUFFICIENTLY_IDENTIFIED"


def test_evidence_hash_and_bounds_are_checked(tmp_path):
    path = tmp_path / "source.txt"
    path.write_text("named molecule")
    entry = {
        "path": "source.txt",
        "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "start": 0,
        "end": 5,
        "selection_sha256": hashlib.sha256(b"named").hexdigest(),
    }
    module.verify_pointers(tmp_path, {"evidence": [entry]})
    entry["end"] = 200
    with pytest.raises(ValueError, match="offsets"):
        module.verify_pointers(tmp_path, {"evidence": [entry]})
    entry["end"] = 5
    path.write_text("changed source")
    with pytest.raises(ValueError, match="file changed"):
        module.verify_pointers(tmp_path, {"evidence": [entry]})


def test_all_fact_links_match_ledger_urls():
    ledger = json.loads((ROOT / "evidence.json").read_text())
    sources = {e["id"]: e["url"] for e in ledger["evidence"]}
    for lead in data()["leads"]:
        for fact in lead["facts"].values():
            for source in fact["sources"]:
                assert sources[source["label"]] == source["url"]


def test_comparator_and_development_labels_require_their_own_evidence():
    lead = data()["leads"][0]
    lead["research_category"] = "APPROVED_COMPARATOR"
    with pytest.raises(ValueError, match="approval evidence"):
        module.Lead.model_validate(lead)
    lead["research_category"] = "CLINICAL_INVESTIGATIONAL"
    lead["facts"]["development"]["status"] = "UNKNOWN"
    with pytest.raises(ValueError, match="development evidence"):
        module.Lead.model_validate(lead)
