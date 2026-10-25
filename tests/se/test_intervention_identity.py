"""intervention_identity_v1: code spelling, composite labels, seed-mention nomination.

Declared in ``docs/se_policies/intervention_identity_v1.md`` before the change. The
ontology here is synthetic. Every test pins a general rule, never a product.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from bve.se.discovery.adapters import ClinicalTrialsGovAdapter
from bve.se.discovery.seeding import SeedProvenance
from bve.se.ontology.records import AliasType, EntityType, SourceAlias, SourceEntityRecord
from bve.se.ontology.snapshot import OntologySnapshot, SourceProvenance
from bve.se.ontology.targets import reset_resolver_cache
from bve.se.schemas.contracts import CompiledQuery, IdentityRelationship
from bve.se.universe.ctgov import ClinicalTrialsGovProvider

AS_OF = date(2026, 10, 25)


def _target(source_id: str, symbol: str, *synonyms: str) -> SourceEntityRecord:
    return SourceEntityRecord(
        source="open_targets", source_id=source_id, entity_type=EntityType.TARGET,
        canonical_symbol=symbol, label=symbol,
        aliases=[SourceAlias(value=v, alias_type=AliasType.SYNONYM) for v in synonyms],
        xrefs={"uniprot": [f"P{source_id[-5:]}"]},
    )


def _drug(chembl: str, name: str, *codes: str, synonyms: tuple[str, ...] = ()) -> SourceEntityRecord:
    return SourceEntityRecord(
        source="chembl", source_id=chembl, entity_type=EntityType.DRUG,
        canonical_symbol=name.upper(), label=name.upper(),
        aliases=[SourceAlias(value=name.upper(), alias_type=AliasType.APPROVED_NAME),
                 *(SourceAlias(value=c, alias_type=AliasType.DEVELOPMENT_CODE) for c in codes),
                 *(SourceAlias(value=s, alias_type=AliasType.SYNONYM) for s in synonyms)],
        xrefs={"chembl": [chembl]},
    )


@pytest.fixture
def ontology(tmp_path_factory, monkeypatch):
    snapshot = OntologySnapshot(
        sources=[SourceProvenance(source="chembl", release="37", retrieved_at=date(2026, 8, 15),
                                  locator="test"),
                 SourceProvenance(source="open_targets", release="26.06",
                                  retrieved_at=date(2026, 8, 15), locator="test")],
        records=[
            _target("ENSG00000149554", "CHEK1", "CHK1"),
            _drug("CHEMBL9001", "Kinasertib", "XL-844"),
            _drug("CHEMBL9002", "Otherinib", "LY-2603618", "IC-83"),
            _drug("CHEMBL9003", "Partnermab", "LY3023414"),
            # Two drugs sharing one separated code: the compact form must stay unresolved.
            _drug("CHEMBL9004", "Ambiguone", "QQ-12"),
            _drug("CHEMBL9005", "Ambiguzine", "QQ-12"),
        ],
    )
    path = tmp_path_factory.mktemp("identity_ontology") / "snapshot"
    snapshot.write(path)
    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(path))
    reset_resolver_cache()
    from bve.se.discovery.adapters import QueryVocabulary

    QueryVocabulary.for_ontology.cache_clear()
    yield snapshot
    reset_resolver_cache()
    QueryVocabulary.for_ontology.cache_clear()


def _authority():
    from bve.se.resolution.target_attribution import attribution_for

    return attribution_for(["CHEK1"])


class TestN1CodeSpelling:
    @pytest.mark.parametrize(("compact", "separated"), [("XL844", "XL-844"), ("IC83", "IC-83")])
    def test_compact_code_resolves_like_its_separated_form(self, ontology, compact, separated) -> None:
        a = _authority()
        assert a.resolve_drug(separated) is not None
        assert a.resolve_drug(compact) == a.resolve_drug(separated)
        assert a.identifies_drug(compact) == a.identifies_drug(separated)
        assert a.resolve_asset(compact, []) == a.resolve_drug(separated)

    @pytest.mark.parametrize("name", ["XL845", "QQ12", "KINASERTIBX1"])
    def test_unknown_or_ambiguous_compact_codes_stay_unresolved(self, ontology, name) -> None:
        assert _authority().resolve_drug(name) is None

    def test_targets_are_not_respelled(self, ontology) -> None:
        # "CHK1" is a target alias; the drug fallback must not reach into target space.
        assert _authority().resolve_drug("CHK1") is None


def _protocol(nct: str, *interventions: dict, title: str = "A study") -> dict:
    return {
        "identificationModule": {"nctId": nct, "briefTitle": title},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Bio"}},
        "statusModule": {"lastUpdatePostDateStruct": {"date": "2026-05-01"}},
        "designModule": {"phases": ["PHASE1"]},
        "armsInterventionsModule": {
            "interventions": list(interventions),
            "armGroups": [{"type": "EXPERIMENTAL", "label": "Arm A",
                           "interventionNames": [f"Drug: {i['name']}" for i in interventions]}],
        },
    }


def _iv(name: str, *, kind: str = "DRUG", other=None, description: str = "") -> dict:
    return {"type": kind, "name": name, "otherNames": other or [], "description": description}


def _seeded(*names: str) -> CompiledQuery:
    return CompiledQuery(
        query_id=f"query:{names[0]}", query="(" + " OR ".join(f'"{n}"' for n in names) + ")",
        target_ids=["CHEK1"], modality_ids=[], aliases=list(names),
        seed_provenance=SeedProvenance.AUTHORITY_SEEDED_ASSET, seed_drug_id="DRUG:X",
    )


def _hits(query: CompiledQuery, *protocols: dict):
    adapter = ClinicalTrialsGovAdapter(
        provider=ClinicalTrialsGovProvider(search_fn=lambda **_: list(protocols)))
    return adapter.search(query, as_of_date=AS_OF).hits


class TestN2SeededCodeSpelling:
    def test_seeded_hyphenated_code_nominates_the_compact_spelling(self, ontology) -> None:
        hits = _hits(_seeded("KINASERTIB", "XL-844"), _protocol("NCT1", _iv("XL844")))
        assert [(h.trial_id, h.asset_name) for h in hits] == [("NCT1", "XL844")]

    def test_a_different_code_is_not_matched(self, ontology) -> None:
        assert _hits(_seeded("XL-844"), _protocol("NCT2", _iv("XL845"))) == []


class TestN3Composites:
    def test_enumerated_label_yields_constituents_not_a_combined_identity(self, ontology) -> None:
        protocol = _protocol("NCT3", _iv("Drug 1: LY3023414; Drug 2: Kinasertib",
                                         kind="COMBINATION_PRODUCT"))
        names = {h.asset_name for h in _hits(_seeded("Kinasertib", "XL-844"), protocol)}
        assert names == {"Kinasertib"}  # the partner has no evidence of its own here
        assert not any("Drug 1:" in n for n in names)

    def test_original_composite_string_is_kept_as_a_related_name(self, ontology) -> None:
        protocol = _protocol("NCT3", _iv("Drug 1: LY3023414; Drug 2: Kinasertib",
                                         kind="COMBINATION_PRODUCT"))
        [hit] = _hits(_seeded("Kinasertib"), protocol)
        assert "Drug 1: LY3023414; Drug 2: Kinasertib" in hit.aliases

    def _registry_for(self, *hits):
        from bve.se.resolution.registry import AssetRegistry

        authority = _authority()
        registry = AssetRegistry(authority, identity_authority=authority)
        for hit in hits:
            registry.ingest_hit(hit)
        return registry

    def test_slash_pair_of_one_drug_becomes_one_identity(self, ontology) -> None:
        [hit] = _hits(_seeded("Otherinib", "IC-83", "LY-2603618"),
                      _protocol("NCT4", _iv("IC83/LY2603618")))
        registry = self._registry_for(hit)
        [asset] = registry.assets.values()
        names = {asset.canonical_name, *asset.aliases}
        assert {"IC83", "LY2603618"} <= names

    def test_slash_pair_of_two_drugs_is_never_merged(self, ontology) -> None:
        hits = _hits(_seeded("Otherinib", "LY-2603618"),
                     _protocol("NCT5", _iv("LY2603618/LY3023414")))
        registry = self._registry_for(*hits)
        edges = [e for a in registry.assets.values() for e in registry.edges_for(a.asset_id)] \
            if hasattr(registry, "edges_for") else list(getattr(registry, "identity_edges", []))
        assert all(
            not (e.related_name == "LY3023414" and e.merged) for e in edges
        )
        assert any(
            e.related_name == "LY3023414"
            and e.relationship is IdentityRelationship.COMBINATION_PARTNER
            for e in edges
        )

    def test_parenthetical_pair_offers_the_inner_name(self, ontology) -> None:
        [hit] = _hits(_seeded("Kinasertib", "XL-844"), _protocol("NCT6", _iv("Kinasertib (XL844)")))
        assert hit.asset_name == "Kinasertib"
        assert "XL844" in hit.aliases


class TestN4SeedMention:
    def test_placebo_described_as_matching_the_seed_is_not_nominated(self, ontology) -> None:
        protocol = _protocol("NCT7", _iv("Placebo", description="Placebo matching Kinasertib"))
        assert _hits(_seeded("Kinasertib"), protocol) == []

    def test_descriptor_mentioning_the_seed_in_its_description_is_not_nominated(self, ontology) -> None:
        protocol = _protocol("NCT8", _iv("Responder cohort", kind="OTHER",
                                         description="Participants who completed Kinasertib dosing"))
        assert _hits(_seeded("Kinasertib"), protocol) == []

    def test_seed_in_other_names_still_nominates(self, ontology) -> None:
        protocol = _protocol("NCT9", _iv("ACR-999", other=["Kinasertib"]))
        assert [h.asset_name for h in _hits(_seeded("Kinasertib"), protocol)] == ["ACR-999"]


class TestI5Provenance:
    def test_snapshot_keeps_the_original_composite_record(self, ontology, tmp_path) -> None:
        import json

        protocol = _protocol("NCT10", _iv("Drug 1: LY3023414; Drug 2: Kinasertib",
                                          kind="COMBINATION_PRODUCT"))
        adapter = ClinicalTrialsGovAdapter(
            provider=ClinicalTrialsGovProvider(search_fn=lambda **_: [protocol]),
            snapshot_root=tmp_path)
        result = adapter.search(_seeded("Kinasertib"), as_of_date=AS_OF)
        [m] = [m for m in result.materializations if m.record_id == "NCT10"]
        with open(m.snapshot_path) as handle:
            saved = json.load(handle)
        names = [i["name"] for i in saved["armsInterventionsModule"]["interventions"]]
        assert names == ["Drug 1: LY3023414; Drug 2: Kinasertib"]
        assert {h.trial_id for h in result.hits} == {"NCT10"}
        _ = datetime.now(UTC)
