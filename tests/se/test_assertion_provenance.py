import json
from pathlib import Path

import pytest

from bve.se.ontology.assertion_provenance import capture_assertions, link_assertions, replay
from bve.se.ontology.sources.chembl import parse_chembl_target
from bve.se.ontology.sources.open_targets import parse_open_targets_target

FROZEN = json.loads(
    Path("research/se_authority_assertion_provenance_sidecar_v1/synthetics.json").read_text()
)


def capture(source, raw):
    return capture_assertions(source, "test-release", "a" * 64, "targets/input", 0, raw)


@pytest.mark.parametrize("source,prefix", [("open_targets", "ot"), ("chembl", "chembl")])
def test_frozen_raw_components_and_real_transforms(source, prefix):
    rows = capture(source, FROZEN[source])
    assert [r["raw_component"] for r in rows] == FROZEN[f"expected_{prefix}_raw_components"]
    assert [r["normalized_key"] for r in rows] == FROZEN[f"expected_{prefix}_keys"]
    for row in rows:
        start, end = row["component_interval"]
        assert row["raw_scalar"][start:end] == row["raw_component"]
        assert replay(row["raw_scalar"], row["transforms"]) == row["normalized_key"]


def test_duplicates_have_independent_identity_and_shared_link():
    raw = FROZEN["open_targets"]
    rows = capture("open_targets", raw)
    assert len({r["assertion_id"] for r in rows}) == len(rows)
    links = link_assertions(rows, parse_open_targets_target(raw), parse_open_targets_target(raw))
    assert all(link["assertion_ids"] for link in links)
    assert max(len(link["assertion_ids"]) for link in links) == 3
    assert rows == capture("open_targets", raw)


def test_chembl_component_ownership_and_first_symbol():
    raw = FROZEN["chembl"]
    rows = capture("chembl", raw)
    same = [r for r in rows if r["normalized_key"] == "xα"]
    assert {r["upstream_component"]["index"] for r in same} == {0, 1}
    links = link_assertions(rows, parse_chembl_target(raw), parse_chembl_target(raw))
    symbol = next(link for link in links if link["field"] == "canonical_symbol")
    assert symbol["assertion_ids"] == [rows[4]["assertion_id"]]


def test_changed_snapshot_fails_closed():
    raw = FROZEN["open_targets"]
    parsed = parse_open_targets_target(raw)
    changed = parsed.model_copy(update={"label": "different"})
    with pytest.raises(ValueError, match="snapshot"):
        link_assertions(capture("open_targets", raw), parsed, changed)


def test_missing_source_is_explicit_not_original_text():
    record = parse_chembl_target(FROZEN["chembl"])
    links = link_assertions([], None, record)
    assert all(r["status"] == "UNRECOVERABLE" and not r["assertion_ids"] for r in links)
    assert all("raw_component" not in r for r in links)


def test_unknown_adapter_fails():
    with pytest.raises(ValueError):
        capture("unrecognized", {})
