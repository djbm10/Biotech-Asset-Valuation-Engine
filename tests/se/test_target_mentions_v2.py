import gzip
import hashlib
import json

import pytest

from bve.se.intent import parse_query
from bve.se.intent.target_mentions import analyze_target_mentions, MentionRole
from bve.se.ontology.assertion_sidecar_lookup import SidecarLookup, build_index


def make_index(tmp_path):
    path = tmp_path / "assertions.jsonl.gz"
    rows = []
    for i, component in enumerate(("component1", "component2", "component2")):
        rows.append(
            {
                "assertion_id": str(i) * 64,
                "normalized_key": "example",
                "source_record_key": f"fixture:record{i}",
                "assertion_type": "SYNONYM",
                "snapshot_records_sha256": "f" * 64,
                "resolver_components": [
                    {"canonical_id": "TARGET:EXAMPLE", "component_id": component}
                ],
            }
        )
    with gzip.open(path, "wt") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    index = tmp_path / "index.sqlite"
    build_index(path, index, assertions_sha256=digest, snapshot_sha256="f" * 64)
    return index, digest


def test_exact_assertion_identity_and_components_survive(tmp_path):
    index, digest = make_index(tmp_path)
    with SidecarLookup(index, assertions_sha256=digest, snapshot_sha256="f" * 64) as lookup:
        rows = lookup.matches("EXAMPLE")
        assert len(rows) == 3
        assert {r["component_id"] for r in rows} == {"component1", "component2"}
        assert len({r["assertion_id"] for r in rows}) == 3
        assert rows == lookup.matches("example")
        assert lookup.matches("example extra") == []
        assert lookup.matches("TARGET:EXAMPLE") == []


def test_stale_index_fails_closed(tmp_path):
    index, digest = make_index(tmp_path)
    with pytest.raises(ValueError):
        SidecarLookup(index, assertions_sha256=digest, snapshot_sha256="e" * 64)


def test_missing_sidecar_never_reconstructs_authority():
    intent = parse_query("Find anti-CD19 therapies")
    before = intent.model_dump(mode="json")
    analysis = analyze_target_mentions(intent)
    assert analysis.provenance_status == "UNAVAILABLE"
    assert analysis.mentions
    assert all(not m.authority_evidence for m in analysis.mentions)
    assert all(m.role == MentionRole.AMBIGUOUS_ROLE for m in analysis.mentions)
    assert before == intent.model_dump(mode="json")


def test_index_has_no_target_promotion(tmp_path):
    index, digest = make_index(tmp_path)
    with SidecarLookup(index, assertions_sha256=digest, snapshot_sha256="f" * 64) as lookup:
        intent = parse_query("Find anti-CD19 therapies")
        before = intent.model_dump(mode="json")
        analysis = analyze_target_mentions(intent, provenance=lookup)
        assert before == intent.model_dump(mode="json")
        assert all(not m.authority_evidence for m in analysis.mentions)
        assert all(m.role == MentionRole.AMBIGUOUS_ROLE for m in analysis.mentions)
