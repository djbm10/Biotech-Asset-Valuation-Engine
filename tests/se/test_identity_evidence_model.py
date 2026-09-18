"""Identity requires positive evidence.

Co-occurrence is not identity, ``otherNames`` is not identity, and lack of contradictory
authority is not identity. These tests pin the asymmetry that carries the whole rule: a
name resolving to a *different* drug is a hard veto on molecular synonymy, while a name
resolving to *nothing* is insufficient evidence rather than approval. Without the second
half the rule would only move B8's false merges onto ontology-unknown development codes.

Split deliberately into regression guards -- behaviour that must hold now -- and
improvement targets, which are xfail because they describe identification B8 did not
achieve and this change is not claimed to deliver.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from bve.se.resolution.registry import AssetRegistry
from bve.se.schemas.contracts import (
    CandidateHit,
    IdentityRelationship,
    SourceEvidenceType,
)


class FakeAuthority:
    """An ontology stub that answers only the two questions the registry may ask.

    ``drugs`` maps a spelling to a canonical drug id; anything absent is unresolved, which
    is the ontology saying nothing rather than saying no.
    """

    def __init__(self, drugs: dict[str, str], targets: set[str] | None = None) -> None:
        self._drugs = {name.casefold(): value for name, value in drugs.items()}
        self._targets = {name.casefold() for name in (targets or set())}

    def resolve_drug(self, name: str) -> str | None:
        return self._drugs.get((name or "").strip().casefold())

    def describes_target_or_class(self, name: str) -> bool:
        return (name or "").strip().casefold() in self._targets


#: The names B8 actually saw, with the canonical ids the published ontology gives them.
ONTOLOGY = FakeAuthority(
    drugs={
        "pembrolizumab": "DRUG:PEMBROLIZUMAB",
        "keytruda": "DRUG:PEMBROLIZUMAB",
        "mk-3475": "DRUG:PEMBROLIZUMAB",
        "durvalumab": "DRUG:DURVALUMAB",
        "imfinzi": "DRUG:DURVALUMAB",
        "atezolizumab": "DRUG:ATEZOLIZUMAB",
        "nivolumab": "DRUG:NIVOLUMAB",
        "carboplatin": "DRUG:CARBOPLATIN",
        "berahyaluronidase alfa": "DRUG:BERAHYALURONIDASE_ALFA",
    },
    targets={"anti-pd-1/anti-pd-l1", "pd-1", "pd-l1", "pd-1 monoclonal antibody"},
)


def _hit(
    name: str,
    aliases: list[str],
    *,
    hit_id: str = "hit:1",
    trial: str = "NCT1",
    intervention_type: str | None = None,
) -> CandidateHit:
    return CandidateHit(
        hit_id=hit_id,
        source="clinicaltrials_gov",
        source_document_id="doc:1",
        query="q",
        asset_name=name,
        trial_id=trial,
        aliases=aliases,
        intervention_type=intervention_type,
        # These fixtures stand in for CT.gov's ``otherNames``, which is an identity claim.
        # Declaring it is what keeps these tests exercising corroboration and veto rather
        # than stopping at the M12 eligibility gate.
        alias_evidence_type=SourceEvidenceType.IDENTITY_EVIDENCE,
        provisional_identity_key=f"|{name}|{trial}",
        retrieved_at=datetime.now(timezone.utc),
        applicable_as_of_date=date(2026, 8, 24),
    )


def _registry() -> AssetRegistry:
    return AssetRegistry(identity_authority=ONTOLOGY)


def _edge(registry: AssetRegistry, related: str):
    return next(
        edge
        for edge in registry.identity_edges
        if edge.related_name.casefold() == related.casefold()
    )


class TestPositiveEvidenceMerges:
    def test_two_spellings_of_one_molecule_are_an_identity_alias(self):
        registry = _registry()
        registry.ingest_hit(_hit("Pembrolizumab", ["KEYTRUDA", "MK-3475"]))

        assert all(
            edge.relationship is IdentityRelationship.IDENTITY_ALIAS and edge.merged
            for edge in registry.identity_edges
        )
        asset = next(iter(registry.assets.values()))
        assert {alias.casefold() for alias in asset.aliases} == {
            "pembrolizumab",
            "keytruda",
            "mk-3475",
        }

    def test_a_true_synonym_is_not_split_by_punctuation_in_the_name(self):
        """``MK-3475`` merges on what it resolves to; the hyphen is not evidence."""

        registry = _registry()
        registry.ingest_hit(_hit("MK-3475", ["Keytruda"]))

        assert _edge(registry, "Keytruda").merged

    def test_a_declared_combination_product_still_merges_a_real_synonym(self):
        """CT.gov types ('Pembrolizumab', ['Keytruda']) as COMBINATION_PRODUCT.

        Structure may label a vetoed pair; it may never override what the names resolve to.
        """

        registry = _registry()
        registry.ingest_hit(
            _hit("Pembrolizumab", ["Keytruda"], intervention_type="COMBINATION_PRODUCT")
        )

        edge = _edge(registry, "Keytruda")
        assert edge.relationship is IdentityRelationship.IDENTITY_ALIAS
        assert edge.merged


class TestRegressionGuards:
    """The B8 failures, each pinned so it cannot return."""

    def test_durvalumab_cannot_contaminate_a_pdcd1_asset(self):
        registry = _registry()
        registry.ingest_hit(
            _hit(
                "Ad-p53",
                ["anti-PD-1/anti-PD-L1", "nivolumab", "pembrolizumab", "atezolizumab", "durvalumab"],
                trial="NCT03544723",
            )
        )

        asset = next(iter(registry.assets.values()))
        assert asset.canonical_name == "Ad-p53"
        assert [alias.casefold() for alias in asset.aliases] == ["ad-p53"]
        assert not any(edge.merged for edge in registry.identity_edges)

    def test_atezolizumab_stays_its_own_asset(self):
        registry = _registry()
        registry.ingest_hit(_hit("Ad-p53", ["atezolizumab"], hit_id="h1", trial="NCT1"))
        registry.ingest_hit(_hit("Atezolizumab", [], hit_id="h2", trial="NCT2"))

        assert len(registry.assets) == 2

    def test_a_co_administered_backbone_does_not_become_an_alias(self):
        registry = _registry()
        registry.ingest_hit(_hit("Pembrolizumab", ["Carboplatin"]))

        edge = _edge(registry, "Carboplatin")
        assert edge.relationship is IdentityRelationship.COMBINATION_PARTNER
        assert not edge.merged

    def test_a_class_descriptor_is_uncertain_not_an_alias(self):
        registry = _registry()
        registry.ingest_hit(_hit("Ad-p53", ["anti-PD-1/anti-PD-L1"]))

        edge = _edge(registry, "anti-PD-1/anti-PD-L1")
        assert edge.relationship is IdentityRelationship.UNCERTAIN_RELATIONSHIP
        assert not edge.merged
        assert "target or mechanism class" in edge.basis

    def test_an_unknown_code_is_not_merged_merely_because_it_failed_to_resolve(self):
        """The rule must not launder the same false merges through unknown strings."""

        registry = _registry()
        registry.ingest_hit(_hit("Ad-p53", ["XYZ-999"]))

        edge = _edge(registry, "XYZ-999")
        assert edge.relationship is IdentityRelationship.UNCERTAIN_RELATIONSHIP
        assert not edge.merged
        assert "not positive identity evidence" in edge.basis

    def test_a_known_drug_offered_by_an_unknown_primary_is_not_identity(self):
        registry = _registry()
        registry.ingest_hit(_hit("Ad-p53", ["durvalumab"]))

        edge = _edge(registry, "durvalumab")
        assert edge.relationship is IdentityRelationship.UNCERTAIN_RELATIONSHIP
        assert not edge.merged


class TestEveryChangedMergeStaysTraceable:
    def test_a_rejected_name_keeps_its_original_evidence(self):
        """A removed merge must be explainable, not merely absent."""

        registry = _registry()
        registry.ingest_hit(
            _hit("Ad-p53", ["durvalumab"], hit_id="hit:9", trial="NCT03544723")
        )

        edge = _edge(registry, "durvalumab")
        assert edge.evidence_field == "clinicaltrials_gov.intervention.otherNames"
        assert edge.trial_id == "NCT03544723"
        assert edge.hit_id == "hit:9"
        assert edge.primary_name == "Ad-p53"
        assert edge.basis


class TestCoformulatedProductsAreRepresentable:
    def test_two_molecules_in_one_product_are_named_without_being_merged(self):
        registry = _registry()
        registry.ingest_hit(
            _hit(
                "Pembrolizumab",
                ["berahyaluronidase alfa"],
                intervention_type="COMBINATION_PRODUCT",
            )
        )

        edge = _edge(registry, "berahyaluronidase alfa")
        assert edge.relationship is IdentityRelationship.COFORMULATED_COMPONENT
        assert not edge.merged, "product-level relationship is not molecular synonymy"
        asset = next(iter(registry.assets.values()))
        assert [alias.casefold() for alias in asset.aliases] == ["pembrolizumab"]


class TestImprovementTargets:
    """B8 identification misses. Not delivered by this change; recorded as open.

    Each needs an authority this run does not have -- a development-code mapping, or a
    product registration linking a subcutaneous co-formulation to its parent molecule.
    Merging them on the evidence available would mean merging unresolved strings, which is
    the defect the guards above forbid.
    """

    @pytest.mark.xfail(reason="no development-code authority for SMT112/AK112", strict=True)
    def test_smt112_and_ak112_resolve_to_one_asset(self):
        registry = _registry()
        registry.ingest_hit(_hit("SMT112", ["AK112"], hit_id="h1", trial="NCT1"))
        registry.ingest_hit(_hit("AK112", [], hit_id="h2", trial="NCT2"))

        assert len(registry.assets) == 1

    @pytest.mark.xfail(reason="no development-code authority for ABBV-181", strict=True)
    def test_budigalimab_and_abbv_181_resolve_to_one_asset(self):
        registry = _registry()
        registry.ingest_hit(_hit("ABBV-181", ["Budigalimab"], hit_id="h1", trial="NCT1"))
        registry.ingest_hit(_hit("Budigalimab", [], hit_id="h2", trial="NCT2"))

        assert len(registry.assets) == 1
