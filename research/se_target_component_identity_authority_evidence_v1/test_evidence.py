"""Focused source-lineage controls; never exercise target-role semantics."""

from evidence import assertions_for, canonical, pointer_value


def test_raw_alias_components_and_source_identity_survive():
    raw = {"names": [" IL-4Rα ", "IL-4 receptor alpha", "CD124"], "members": [7, 9]}
    source = {
        "source": "test_authority",
        "release": "frozen",
        "artifact_sha256": "a" * 64,
        "locator": {"row": 4},
        "entity_key": "shared-canonical-label",
    }
    one = assertions_for(source, raw)
    two = assertions_for(dict(source, locator={"row": 5}), raw)
    assert len({r["assertion_id"] for r in one + two}) == 10
    assert [r["raw_value"] for r in one if r["field_path"][0] == "names"] == raw["names"]
    assert all(pointer_value(raw, r["field_path"]) == r["raw_value"] for r in one)
    assert canonical(assertions_for(source, raw)) == canonical(one)


def test_structural_membership_and_empty_or_null_fields_are_not_lost():
    raw = {
        "type": "CHIMERIC PROTEIN",
        "components": [{"id": 2}, {"id": 3}],
        "relations": [],
        "taxon": None,
    }
    source = {
        "source": "test_authority",
        "release": "frozen",
        "artifact_sha256": "b" * 64,
        "locator": {"tid": 8},
        "entity_key": "target:8",
    }
    rows = assertions_for(source, raw)
    values = {tuple(r["field_path"]): r["raw_value"] for r in rows}
    assert values[("components", 0, "id")] == 2
    assert values[("components", 1, "id")] == 3
    assert values[("relations",)] == []
    assert values[("taxon",)] is None
    assert values[("type",)] == "CHIMERIC PROTEIN"
