"""The identity graph must be visible before it can be corrected.

B8 showed that `otherNames` is a mixed semantic field: on NCT03544723 the intervention
"Ad-p53" carries otherNames ['anti-PD-1/anti-PD-L1', 'nivolumab', 'pembrolizumab',
'atezolizumab', 'durvalumab'] -- four combination partners and a class descriptor, none
of them synonyms. Merging them made Ad-p53 answer to the name Durvalumab and carry a
confirmed PDCD1 assertion, which is 7 of the run's false target assertions.

Edge emission came first and recorded that behaviour exactly, frozen as
B8_IDENTITY_GRAPH_BASELINE_V1. These tests cover emission itself; the evidence model that
decides what each name is lives in ``test_identity_evidence_model.py``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from bve.se.resolution.registry import AssetRegistry
from bve.se.schemas.contracts import CandidateHit, IdentityRelationship


def _hit(
    name: str,
    aliases: list[str],
    *,
    hit_id: str = "hit:1",
    trial: str = "NCT1",
    intervention_type: str | None = None,
) -> CandidateHit:
    return CandidateHit(
        intervention_type=intervention_type,
        hit_id=hit_id,
        source="clinicaltrials_gov",
        source_document_id="doc:1",
        query="q",
        asset_name=name,
        trial_id=trial,
        aliases=aliases,
        provisional_identity_key=f"|{name}|{trial}",
        retrieved_at=datetime.now(timezone.utc),
        applicable_as_of_date=date(2026, 8, 24),
    )


class TestEveryOfferedNameBecomesAnEdge:
    def test_each_related_name_is_recorded_with_its_evidence(self):
        registry = AssetRegistry()
        registry.ingest_hit(_hit("Ad-p53", ["nivolumab", "durvalumab"]))

        edges = registry.identity_edges
        assert [edge.related_name for edge in edges] == ["nivolumab", "durvalumab"]
        assert {edge.primary_name for edge in edges} == {"Ad-p53"}
        assert all(edge.evidence_field.endswith("otherNames") for edge in edges)
        assert all(edge.hit_id == "hit:1" and edge.trial_id == "NCT1" for edge in edges)

    def test_edge_ids_are_stable_and_distinct_per_related_name(self):
        registry = AssetRegistry()
        registry.ingest_hit(_hit("Ad-p53", ["nivolumab", "durvalumab"]))
        again = AssetRegistry()
        again.ingest_hit(_hit("Ad-p53", ["nivolumab", "durvalumab"]))

        ids = [edge.edge_id for edge in registry.identity_edges]
        assert len(set(ids)) == 2
        assert ids == [edge.edge_id for edge in again.identity_edges]

    def test_an_asset_with_no_offered_names_produces_no_edges(self):
        registry = AssetRegistry()
        registry.ingest_hit(_hit("Durvalumab", []))
        assert registry.identity_edges == []

    def test_blank_related_names_are_not_edges(self):
        registry = AssetRegistry()
        registry.ingest_hit(_hit("Durvalumab", ["", "   "]))
        assert registry.identity_edges == []


class TestWithoutAnAuthorityNothingIsMerged:
    """Fail-closed. No ontology means no positive evidence, so no name bears identity."""

    def test_offered_names_are_held_as_uncertain_rather_than_believed(self):
        registry = AssetRegistry()
        registry.ingest_hit(_hit("Ad-p53", ["nivolumab", "anti-PD-1/anti-PD-L1"]))

        assert all(
            edge.relationship is IdentityRelationship.UNCERTAIN_RELATIONSHIP
            and not edge.merged
            for edge in registry.identity_edges
        )

    def test_the_b8_defect_no_longer_reproduces(self):
        """The two hits stayed one asset in B8 only because the partner was an alias."""

        registry = AssetRegistry()
        registry.ingest_hit(_hit("Ad-p53", ["durvalumab"], hit_id="hit:1", trial="NCT1"))
        registry.ingest_hit(_hit("Durvalumab", [], hit_id="hit:2", trial="NCT2"))

        assert len(registry.assets) == 2
        assert {asset.canonical_name for asset in registry.assets.values()} == {
            "Ad-p53",
            "Durvalumab",
        }
        assert all(
            "durvalumab" not in [alias.casefold() for alias in asset.aliases]
            for asset in registry.assets.values()
            if asset.canonical_name == "Ad-p53"
        )
