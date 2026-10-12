"""A recognized entity must survive a homonymous display symbol."""
from datetime import date

import pytest

from bve.se.discovery.query import compile_problem_queries
from bve.se.gates.evaluator import _target_key
from bve.se.intent import build_buyer_identity, compile_intent, parse_query
from bve.se.ontology.records import (
    AliasType, EntityType, SourceAlias, SourceEntityRecord, SourceProvenance,
)
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.ontology.targets import reset_resolver_cache, resolve_target


@pytest.fixture()
def authority(tmp_path, monkeypatch):
    records = [
        SourceEntityRecord(
            source="open_targets", source_id="gene-a", entity_type=EntityType.TARGET,
            canonical_symbol="GAX1", xrefs={"uniprot": ["Q00001"]},
            aliases=[SourceAlias(value=a, alias_type=AliasType.SYNONYM)
                     for a in ["AXONE", "AXTWO"]],
        ),
        SourceEntityRecord(
            source="open_targets", source_id="gene-b", entity_type=EntityType.TARGET,
            canonical_symbol="GAX2", xrefs={"uniprot": ["Q00002"]},
            aliases=[SourceAlias(value="GAX1", alias_type=AliasType.SYMBOL)],
        ),
    ]
    path = tmp_path / "snapshot"
    OntologySnapshot(
        sources=[SourceProvenance(source="open_targets", release="fixture-v1",
                                  retrieved_at=date(2026, 10, 12), locator="fixture:authority")],
        records=records,
    ).write(path)
    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(path))
    reset_resolver_cache()
    yield
    reset_resolver_cache()


def test_unique_alias_survives_compilation(authority):
    intent = parse_query("Find clinical-stage AXONE antibodies.")
    assert [(t.canonical_id, t.label) for t in intent.targets] == [("TARGET:GAX1", "GAX1")]
    problem = compile_intent(intent, buyer=build_buyer_identity(
        "Offline identity test", as_of_date=date(2026, 10, 12)))
    assert problem.strategic_gap.target_expression.targets[0].canonical_id == "TARGET:GAX1"
    queries = compile_problem_queries(problem)
    assert queries
    assert all(q.target_ids == ["TARGET:GAX1"] for q in queries)
    assert all('"TARGET:' not in q.query for q in queries)
    assert _target_key("TARGET:GAX1") == _target_key("GAX1") == "GAX1"


def test_bare_homonym_is_still_ambiguous(authority):
    assert resolve_target("GAX1").status.value == "AMBIGUOUS"
    intent = parse_query("Find GAX1 antibodies.")
    assert intent.targets == []
    assert intent.ambiguous_terms == ["GAX1"]


@pytest.mark.parametrize("frame", ["{}", "anti-{}", "{}-directed", "{}-targeted",
                                  "{}-targeting", "{}-blocking", "{}-binding", "{}-specific"])
def test_affixes_preserve_resolved_entity(authority, frame):
    intent = parse_query(f"Find {frame.format('AXONE')} antibodies.")
    assert [t.canonical_id for t in intent.targets] == ["TARGET:GAX1"]


def test_equivalent_mentions_deduplicate(authority):
    intent = parse_query("Find AXONE or AXTWO antibodies.")
    assert [t.canonical_id for t in intent.targets] == ["TARGET:GAX1"]


@pytest.mark.parametrize("join", ["/", "×"])
def test_separators_keep_distinct_entities(authority, join):
    intent = parse_query(f"Find AXONE{join}GAX2 antibodies.")
    assert {t.canonical_id for t in intent.targets} == {"TARGET:GAX1", "GAX2"}
    assert intent.target_operator.value == "ALL"


def test_repeated_outputs_are_equal(authority):
    query = "Find clinical-stage AXONE antibodies."
    assert parse_query(query).model_dump_json() == parse_query(query).model_dump_json()
