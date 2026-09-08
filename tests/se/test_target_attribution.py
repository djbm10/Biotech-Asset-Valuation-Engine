"""Per-asset target attribution, and the query inheritance it replaces."""

from __future__ import annotations

from datetime import date, datetime, timezone

from bve.se.ontology.mechanisms import (
    DrugTargetAuthority,
    DrugTargetEdge,
    EdgeStatus,
    TargetRelationship,
)
from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
    SourceProvenance,
)
from bve.se.ontology.resolver import BiomedicalEntityResolver
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.resolution.registry import AssetRegistry
from bve.se.resolution.target_attribution import OntologyTargetAttribution
from bve.se.schemas.contracts import CandidateHit, TargetAssertionStatus


def _drug(source_id: str, name: str, *aliases: str) -> SourceEntityRecord:
    return SourceEntityRecord(
        source="chembl",
        source_id=source_id,
        entity_type=EntityType.DRUG,
        canonical_symbol=name,
        label=name,
        aliases=[
            SourceAlias(value=value, alias_type=AliasType.SYNONYM) for value in (name, *aliases)
        ],
        xrefs={"chembl": [source_id]},
    )


def _snapshot() -> OntologySnapshot:
    return OntologySnapshot(
        sources=[
            SourceProvenance(
                source="chembl",
                release="ChEMBL_37",
                retrieved_at=date(2026, 9, 7),
                locator="test",
                digest="d",
                record_count=3,
            )
        ],
        records=[
            _drug("CHEMBL3137343", "PEMBROLIZUMAB", "MK-3475"),
            _drug("CHEMBL2109331", "DURVALUMAB"),
            _drug("CHEMBL288441", "CARBOPLATIN"),
        ],
    )


def _edge(drug: str, target: str) -> DrugTargetEdge:
    return DrugTargetEdge(
        canonical_drug_id=drug,
        canonical_target_id=target,
        relationship_type=TargetRelationship.DIRECT_TARGET,
        source="chembl",
        source_release="ChEMBL_37",
        source_record_id="1",
        evidence_hash=f"{drug}:{target}",
        status=EdgeStatus.USABLE,
    )


def _attribution(edges_by_name: dict[str, str]) -> OntologyTargetAttribution:
    resolver = BiomedicalEntityResolver(_snapshot())
    edges = [
        _edge(resolver.resolve(name, entity_type=EntityType.DRUG).canonical_id, target)
        for name, target in edges_by_name.items()
    ]
    return OntologyTargetAttribution(resolver, DrugTargetAuthority(edges), ["TARGET:PDCD1"])


def _hit(asset_name: str, *, target_terms: list[str]) -> CandidateHit:
    return CandidateHit(
        hit_id=f"hit:{asset_name}",
        source="ctgov",
        source_document_id="doc:1",
        query="PDCD1",
        asset_name=asset_name,
        trial_id="NCT00000001",
        target_terms=target_terms,
        snippet="",
        provisional_identity_key=f"ctgov:{asset_name.casefold()}",
        retrieved_at=datetime.now(timezone.utc),
        applicable_as_of_date=date(2026, 9, 7),
    )


class TestAttribution:
    def test_a_documented_target_is_confirmed(self) -> None:
        attribution = _attribution({"PEMBROLIZUMAB": "TARGET:PDCD1"})
        assertion = attribution.assert_targets("Pembrolizumab", [])[0]
        assert assertion.status is TargetAssertionStatus.CONFIRMED_TARGET
        assert assertion.documented_targets == ["TARGET:PDCD1"]
        assert [ref.evidence_hash for ref in assertion.evidence]

    def test_a_pd_l1_asset_is_confirmed_other_target_not_pdcd1(self) -> None:
        attribution = _attribution({"DURVALUMAB": "TARGET:CD274"})
        assertion = attribution.assert_targets("Durvalumab", [])[0]
        assert assertion.status is TargetAssertionStatus.CONFIRMED_OTHER_TARGET
        assert assertion.documented_targets == ["TARGET:CD274"]

    def test_an_asset_with_no_mechanism_is_unresolved_not_excluded(self) -> None:
        attribution = _attribution({"PEMBROLIZUMAB": "TARGET:PDCD1"})
        assertion = attribution.assert_targets("Carboplatin", [])[0]
        assert assertion.status is TargetAssertionStatus.UNRESOLVED

    def test_an_unknown_asset_records_the_question_as_unanswered(self) -> None:
        attribution = _attribution({"PEMBROLIZUMAB": "TARGET:PDCD1"})
        assertions = attribution.assert_targets("SMT112", [])
        assert [assertion.status for assertion in assertions] == [
            TargetAssertionStatus.UNRESOLVED
        ]

    def test_an_alias_resolves_to_the_same_assertion(self) -> None:
        attribution = _attribution({"PEMBROLIZUMAB": "TARGET:PDCD1"})
        assertion = attribution.assert_targets("MK-3475", [])[0]
        assert assertion.status is TargetAssertionStatus.CONFIRMED_TARGET


class TestRegistryNoLongerInheritsTheQueryTarget:
    def test_a_co_administered_drug_does_not_acquire_the_searched_target(self) -> None:
        # The whole point: carboplatin appearing in a PDCD1 trial is discovery evidence,
        # and a PDCD1 attribution on carboplatin is the error.
        registry = AssetRegistry(_attribution({"PEMBROLIZUMAB": "TARGET:PDCD1"}))
        asset = registry.ingest_hit(_hit("Carboplatin", target_terms=["PDCD1"]))
        assert asset.target_ids == []
        assert asset.discovery_target_context == ["PDCD1"]
        assert [a.status for a in asset.target_assertions] == [TargetAssertionStatus.UNRESOLVED]

    def test_a_confirmed_asset_gets_the_target_from_its_own_evidence(self) -> None:
        registry = AssetRegistry(_attribution({"PEMBROLIZUMAB": "TARGET:PDCD1"}))
        asset = registry.ingest_hit(_hit("Pembrolizumab", target_terms=["PDCD1"]))
        assert asset.target_ids == ["TARGET:PDCD1"]

    def test_without_an_authority_no_target_is_attributed_at_all(self) -> None:
        # Falling back to the hit's context would restore the inheritance bug silently.
        registry = AssetRegistry()
        asset = registry.ingest_hit(_hit("Pembrolizumab", target_terms=["PDCD1"]))
        assert asset.target_ids == []
        assert asset.discovery_target_context == ["PDCD1"]
