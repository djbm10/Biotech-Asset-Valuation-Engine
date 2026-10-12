"""Decision-neutral target mention representation, independent of benchmark identities."""

from datetime import date

import pytest

from bve.se.intent import parse_query
from bve.se.intent.target_mentions import MentionRole, analyze_target_mentions
from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
    SourceProvenance,
)
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.ontology.targets import reset_resolver_cache


@pytest.fixture
def authority(tmp_path, monkeypatch):
    records = []
    for i, (symbol, aliases) in enumerate(
        [
            ("ZXA1", ["Kappa enzyme", "Kappa enzyme receptor subunit"]),
            ("ZXB2", ["enzyme receptor", "shared mention"]),
            ("ZXC3", ["shared mention", "(R)-laboratory protein"]),
        ]
    ):
        records.append(
            SourceEntityRecord(
                source="open_targets",
                source_id=f"ENSG0099999999{i}",
                entity_type=EntityType.TARGET,
                canonical_symbol=symbol,
                aliases=[SourceAlias(value=a, alias_type=AliasType.SYNONYM) for a in aliases],
                xrefs={"uniprot": [f"Q9999{i}"], "ensembl": [f"ENSG0099999999{i}"]},
            )
        )
    snapshot = OntologySnapshot(
        sources=[
            SourceProvenance(
                source="open_targets",
                release="fixture",
                retrieved_at=date(2026, 10, 12),
                locator="fixture://target-mentions",
            )
        ],
        records=records,
    )
    snapshot.write(tmp_path / "snapshot")
    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "snapshot"))
    reset_resolver_cache()
    yield
    reset_resolver_cache()


def test_overlapping_mentions_preserve_production_selection(authority):
    intent = parse_query("Find Kappa enzyme receptor subunit therapies.")
    before = intent.model_dump_json()
    analysis = analyze_target_mentions(intent)
    assert intent.model_dump_json() == before
    by_text = {m.surface: m for m in analysis.mentions}
    assert {"Kappa enzyme receptor subunit", "Kappa enzyme", "enzyme receptor"} <= by_text.keys()
    assert by_text["enzyme receptor"].role is MentionRole.EMBEDDED_BIOLOGICAL_MENTION
    assert by_text["enzyme receptor"].canonical_id == "TARGET:ZXB2"
    assert by_text["Kappa enzyme receptor subunit"].canonical_id == "TARGET:ZXA1"
    assert all(m.ownership == "UNADJUDICATED" for m in analysis.mentions)
    assert any(r.kind == "OVERLAPPING" for r in analysis.relations)
    assert all(m.role is not MentionRole.TARGET_ROLE_CONFIRMED for m in analysis.mentions)
    assert all(m.decision_bindings for m in analysis.mentions if m.currently_decision_bearing)


def test_exact_scientific_punctuation_and_affixes(authority):
    for query, surface in [
        ("Find (R)-laboratory protein therapies.", "(R)-laboratory protein"),
        ("Find anti-ZXA1 therapies.", "ZXA1"),
        ("Find ZXA1-directed therapies.", "ZXA1"),
    ]:
        result = analyze_target_mentions(parse_query(query))
        matches = [m for m in result.mentions if m.surface == surface]
        assert matches
        assert all(query[m.start : m.end] == surface for m in matches)
        assert all(m.authority_evidence for m in matches)


def test_ambiguity_keeps_all_source_claimants(authority):
    result = analyze_target_mentions(parse_query("Find shared mention therapies."))
    mention = next(m for m in result.mentions if m.surface == "shared mention")
    assert mention.status == "AMBIGUOUS"
    assert mention.canonical_id is None
    assert mention.claimant_ids == ["TARGET:ZXB2", "TARGET:ZXC3"]
    assert not mention.currently_decision_bearing
    assert len(mention.authority_evidence) == 2
    assert all(e.matching_aliases for e in mention.authority_evidence)


def test_repetition_does_not_mutate_intent_or_change_records(authority):
    intent = parse_query("Find ZXA1 therapies for ZXA1 expression.")
    before = intent.model_dump_json()
    first = analyze_target_mentions(intent)
    assert first.model_dump_json() == analyze_target_mentions(intent).model_dump_json()
    assert before == intent.model_dump_json()
    occurrences = [m for m in first.mentions if m.surface == "ZXA1"]
    assert len(occurrences) == 2
    assert len({m.mention_id for m in occurrences}) == 2
    assert any(r.kind == "INDEPENDENT" for r in first.relations)


def test_stale_intent_rejected_without_mutation(authority):
    intent = parse_query("Find ZXA1 therapies.").model_copy(update={"ontology_version": "stale"})
    before = intent.model_dump_json()
    with pytest.raises(ValueError, match="snapshot"):
        analyze_target_mentions(intent)
    assert before == intent.model_dump_json()


def test_no_snapshot_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "absent"))
    reset_resolver_cache()
    intent = parse_query("Find ZXA1 therapies.")
    result = analyze_target_mentions(intent)
    assert result.source_status == "UNAVAILABLE"
    assert result.mentions == []
    reset_resolver_cache()


def test_role_states_are_distinct():
    assert len(MentionRole) == 6
