"""Structural safety of an inert provenance record; no human-PoC policy changes."""

import json
import runpy
from pathlib import Path

import pytest
from pydantic import ValidationError

from bve.se.schemas.treatment_cohort import TreatmentCohortAttribution

ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / "research/se_treatment_cohort_attribution_representation_v1"
MATERIALIZE = runpy.run_path(str(PACKET / "materialize.py"))["materialize"]
ROWS = json.loads((PACKET / "expected_representation.json").read_text())


@pytest.mark.parametrize("row", ROWS, ids=lambda row: row["witness_id"])
def test_frozen_grounding_round_trip(row):
    record = MATERIALIZE(row)
    assert record.relationship.value == row["expected_relation"]
    assert record.receipt_status.value == row["receipt_status"]
    assert record.cohort_membership_status.value == row["cohort_membership_status"]
    assert record.result_ownership_status.value == row["result_ownership_status"]
    assert record.canonical_json() == MATERIALIZE(row).canonical_json()
    restored = TreatmentCohortAttribution.model_validate_json(record.canonical_json())
    assert restored.canonical_json() == record.canonical_json()
    if row["population"] == "negative_65" or row["previous_unresolved_14"]:
        assert record.ownership_certificate is None
        assert record.result_ownership_status.value == "UNKNOWN"


def sample(relationship):
    return MATERIALIZE(next(r for r in ROWS if r["expected_relation"] == relationship))


@pytest.mark.parametrize("relationship", ["RECEIPT", "REGIMEN_RECEIPT", "UNRESOLVED"])
@pytest.mark.parametrize("mutation", [
    {"relationship": "RESULT_OWNERSHIP"},
    {"result_ownership_status": "CERTIFIED"},
    {"relationship": "RESULT_OWNERSHIP", "result_ownership_status": "CERTIFIED"},
])
def test_receipt_never_silently_upgrades(relationship, mutation):
    data = sample(relationship).model_dump(mode="json")
    data.update(mutation)
    with pytest.raises(ValidationError):
        TreatmentCohortAttribution.model_validate(data)


@pytest.mark.parametrize("scope", ["REGIMEN_COMPONENT", "POOLED_REGIMEN", "NONCLINICAL"])
def test_certificate_cannot_override_component_or_nonclinical_scope(scope):
    data = sample("RESULT_OWNERSHIP").model_dump(mode="json")
    data["scope"] = scope
    with pytest.raises(ValidationError):
        TreatmentCohortAttribution.model_validate(data)


@pytest.mark.parametrize("field", ["receipt_status", "cohort_membership_status"])
def test_ownership_requires_actual_treatment_and_cohort(field):
    data = sample("RESULT_OWNERSHIP").model_dump(mode="json")
    data[field] = "UNKNOWN"
    with pytest.raises(ValidationError):
        TreatmentCohortAttribution.model_validate(data)


@pytest.mark.parametrize("mutation", [
    {"qualifiers": []}, {"qualifiers": ["monotherapy effect"]},
    {"basis": "D_REGIMEN"}, {"ownership_certificate": None},
])
def test_ownership_preserves_qualifiers_and_independent_certificate(mutation):
    data = sample("RESULT_OWNERSHIP").model_dump(mode="json")
    data.update(mutation)
    with pytest.raises(ValidationError):
        TreatmentCohortAttribution.model_validate(data)


@pytest.mark.parametrize("field", ["path", "sha256", "json_pointer"])
def test_missing_provenance_is_not_admissible(field):
    data = sample("RECEIPT").model_dump(mode="json")
    del data["passage"]["reference"][field]
    with pytest.raises(ValidationError):
        TreatmentCohortAttribution.model_validate(data)


def test_offsets_cannot_discard_evidence():
    data = sample("RECEIPT").model_dump(mode="json")
    data["passage"]["end"] -= 1
    with pytest.raises(ValidationError):
        TreatmentCohortAttribution.model_validate(data)


def test_records_and_nested_provenance_are_immutable():
    record = sample("RECEIPT")
    with pytest.raises(ValidationError):
        record.result_ownership_status = "CERTIFIED"
    with pytest.raises(ValidationError):
        record.passage.reference.path = "another document"
    assert isinstance(record.qualifiers, tuple)
    assert isinstance(record.regimen_components, tuple)


def test_trial_arm_presence_is_context_not_result_ownership():
    data = sample("REGIMEN_RECEIPT").model_dump(mode="json")
    source = next(MATERIALIZE(r).source for r in ROWS if r["source"] is not None)
    data["trial_context_ids"] = ["NCT-example"]
    data["arm"] = {
        "trial_id": "NCT-example", "arm_label": "Arm A",
        "source": source.model_dump(mode="json"), "evidence": data["grounding_reference"],
    }
    record = TreatmentCohortAttribution.model_validate(data)
    assert record.result_group is None
    assert record.result_ownership_status.value == "UNKNOWN"
    del data["arm"]["source"]
    with pytest.raises(ValidationError):
        TreatmentCohortAttribution.model_validate(data)


def test_c056_is_nonowning_without_repairing_the_reader():
    from bve.se.evidence.human_poc import efficacy_statements

    row = next(r for r in ROWS if r["witness_id"] == "negative:C056")
    record = MATERIALIZE(row)
    assert record.relationship.value == "REGIMEN_RECEIPT"
    assert record.ownership_certificate is None
    assert efficacy_statements(row["text"], asset_names=row["candidate_names"])
