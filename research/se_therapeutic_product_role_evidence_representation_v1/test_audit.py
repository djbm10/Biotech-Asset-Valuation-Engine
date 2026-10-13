"""Source gate checks; no qualification rule or prose classifier."""

import gzip
import json
from pathlib import Path

import audit

RESULTS = Path("/tmp/product_role_rep_seed0")


def test_native_context_does_not_manufacture_product_role():
    controls = json.loads((audit.STUDY / "structural_controls.json").read_text())
    for control in controls:
        raw = control["source"]
        records = audit.native_fields(raw, "fixture", "frozen", control["id"])
        assert records
        assert all(not r["therapeutic_product_assertion"] for r in records)
        assert all(not r["intervention_use_assertion"] for r in records)
        for record in records:
            value = raw
            for part in record["source"]["field_path"]:
                value = value[part]
            assert value == record["raw_value"] == record["normalized_value"]


def test_independent_builds_are_identical():
    other = Path("/tmp/product_role_rep_seed42")
    for name in json.loads((RESULTS / "hashes.json").read_text()):
        assert (RESULTS / name).read_bytes() == (other / name).read_bytes()


def test_all_frozen_decisions_and_provenance_links_preserved():
    rows = json.loads(gzip.decompress((RESULTS / "availability.json.gz").read_bytes()))
    fields = json.loads(gzip.decompress((RESULTS / "source_field_ledger.json.gz").read_bytes()))
    ids = {f["assertion_id"] for f in fields}
    assert len(ids) == len(fields)
    baseline = json.loads((audit.STUDY / "population.json").read_text())
    assert len(rows) == len(baseline) == 1181
    for row, expected in zip(rows, baseline, strict=True):
        assert row["asset_id"] == expected["asset_id"]
        assert row["qualification_reason_before"] == row["qualification_reason_after"]
        assert row["qualification_reason_after"] == expected["qualification_reason"]
        assert set(row["native_assertion_ids"]).issubset(ids)
        assert set(row["authority_annotation_ids"]).issubset(ids)


def test_h19_native_evidence_is_visible_without_prose_classification():
    rows = json.loads(gzip.decompress((RESULTS / "availability.json.gz").read_bytes()))
    names = {"[68Ga]Ga-TTP", "Rescue Medications", "Rescue Medication"}
    selected = [r for r in rows if r["name"] in names]
    assert len(selected) == 3
    for row in selected:
        assert row["entity_type_declarations"] == ["DRUG"]
        assert row["arm_type_declarations"] == ["EXPERIMENTAL"]
        assert row["intervention_links"]
        assert row["availability"]["free_text_present_not_classified"]
        assert row["product_kind"] == row["intervention_use"] == "UNKNOWN"
        assert row["qualification_reason_after"] == "STRUCTURED_THERAPEUTIC"
