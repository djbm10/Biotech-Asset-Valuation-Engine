"""Two registered names, one drug: ``authority_identity_merge_v1.md``.

Merging separately registered assets needs the authority's own identifier names -- an
approved name or a development code. Trade names, bare synonyms, class labels and
biosimilar product codes still resolve, but none of them may unite two assets.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

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
from bve.se.schemas.contracts import CandidateHit, MergeStatus


def _drug(source_id: str, name: str, **aliases: list[str]) -> SourceEntityRecord:
    return SourceEntityRecord(
        source="chembl",
        source_id=source_id,
        entity_type=EntityType.DRUG,
        canonical_symbol=name,
        label=name,
        aliases=[
            SourceAlias(value=name, alias_type=AliasType.APPROVED_NAME),
            *(
                SourceAlias(value=value, alias_type=AliasType(alias_type))
                for alias_type, values in aliases.items()
                for value in values
            ),
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
                record_count=4,
            )
        ],
        records=[
            _drug(
                "CHEMBL1",
                "AXICABTAGENE CILOLEUCEL",
                DEVELOPMENT_CODE=["KTE-C19"],
                TRADE_NAME=["Yescarta"],
            ),
            _drug("CHEMBL2", "TISAGENLECLEUCEL", DEVELOPMENT_CODE=["CART19", "CTL019"]),
            _drug(
                "CHEMBL3",
                "TRASTUZUMAB",
                DEVELOPMENT_CODE=["EG12014"],
                SYNONYM=["Eg12014 trastuzumab biosimilar", "Herceptin biosim"],
            ),
            _drug("CHEMBL4", "ACYCLOVIR", TRADE_NAME=["avert"], SYNONYM=["aciclovir"]),
        ],
    )


def _authority() -> OntologyTargetAttribution:
    # Attribution with no requested targets: only the identity questions are asked here.
    return OntologyTargetAttribution(BiomedicalEntityResolver(_snapshot()), None, [])  # type: ignore[arg-type]


def _hit(name: str, hit_id: str) -> CandidateHit:
    return CandidateHit(
        hit_id=hit_id,
        source="clinicaltrials_gov",
        source_document_id=f"doc:{hit_id}",
        query="q",
        asset_name=name,
        trial_id=f"NCT{hit_id}",
        provisional_identity_key=f"|{name}|{hit_id}",
        retrieved_at=datetime.now(timezone.utc),
        applicable_as_of_date=date(2026, 9, 7),
    )


def _consolidated(*names: str) -> tuple[AssetRegistry, dict[str, str]]:
    authority = _authority()
    registry = AssetRegistry(identity_authority=authority)
    for index, name in enumerate(names):
        registry.ingest_hit(_hit(name, str(index)))
    return registry, registry.consolidate_by_authority()


def _names(registry: AssetRegistry) -> list[list[str]]:
    return sorted(sorted(asset.aliases) for asset in registry.assets.values())


class TestIdentifierResolution:
    def test_development_code_and_approved_name_identify(self) -> None:
        authority = _authority()
        assert authority.identifies_drug("KTE-C19") == "DRUG:AXICABTAGENE CILOLEUCEL"
        assert authority.identifies_drug("axicabtagene ciloleucel") == (
            "DRUG:AXICABTAGENE CILOLEUCEL"
        )

    def test_trade_names_and_synonyms_resolve_but_do_not_identify(self) -> None:
        authority = _authority()
        assert authority.resolve_drug("Yescarta") == "DRUG:AXICABTAGENE CILOLEUCEL"
        assert authority.identifies_drug("Yescarta") is None
        assert authority.identifies_drug("avert") is None
        assert authority.identifies_drug("aciclovir") is None

    def test_a_class_label_filed_as_a_code_does_not_identify(self) -> None:
        authority = _authority()
        assert authority.resolve_drug("CART19") == "DRUG:TISAGENLECLEUCEL"
        assert authority.identifies_drug("CART19") is None
        assert authority.identifies_drug("CTL019") == "DRUG:TISAGENLECLEUCEL"

    def test_a_code_the_entity_files_as_a_biosimilar_does_not_identify(self) -> None:
        authority = _authority()
        assert authority.resolve_drug("EG12014") == "DRUG:TRASTUZUMAB"
        assert authority.identifies_drug("EG12014") is None
        assert authority.identifies_drug("trastuzumab") == "DRUG:TRASTUZUMAB"


class TestConsolidation:
    def test_a_development_code_merges_into_the_approved_name(self) -> None:
        registry, redirects = _consolidated("KTE-C19", "Axicabtagene Ciloleucel")
        assert len(registry.assets) == 1
        survivor = next(iter(registry.assets.values()))
        assert survivor.canonical_name == "Axicabtagene Ciloleucel"
        assert sorted(survivor.aliases) == ["Axicabtagene Ciloleucel", "KTE-C19"]
        assert list(redirects.values()) == [survivor.asset_id]
        merge = next(iter(registry.merges.values()))
        assert merge.status is MergeStatus.APPLIED
        assert merge.deterministic_basis == "authority_drug:DRUG:AXICABTAGENE CILOLEUCEL"

    def test_the_merge_is_reversible(self) -> None:
        registry, _ = _consolidated("KTE-C19", "Axicabtagene Ciloleucel")
        registry.reverse_merge(next(iter(registry.merges)))
        assert _names(registry) == [["Axicabtagene Ciloleucel"], ["KTE-C19"]]

    def test_trade_name_class_term_biosimilar_and_word_never_absorb(self) -> None:
        registry, redirects = _consolidated(
            "Yescarta",
            "axicabtagene ciloleucel",
            "CART19",
            "tisagenlecleucel",
            "EG12014",
            "trastuzumab",
            "avert",
            "acyclovir",
        )
        assert redirects == {}
        assert len(registry.assets) == 8

    def test_unresolved_names_stay_apart(self) -> None:
        registry, redirects = _consolidated("GC012F", "AZD0120")
        assert redirects == {}
        assert len(registry.assets) == 2

    def test_an_asset_identifying_two_drugs_merges_with_neither(self) -> None:
        authority = _authority()
        registry = AssetRegistry(identity_authority=authority)
        conflicted = registry.ingest_hit(_hit("KTE-C19", "0"))
        registry._index_asset(
            conflicted.model_copy(update={"aliases": ["KTE-C19", "CTL019"]})
        )
        registry.ingest_hit(_hit("axicabtagene ciloleucel", "1"))
        registry.ingest_hit(_hit("tisagenlecleucel", "2"))
        assert registry.consolidate_by_authority() == {}
        assert len(registry.assets) == 3

    def test_without_an_authority_nothing_merges(self) -> None:
        registry = AssetRegistry()
        registry.ingest_hit(_hit("KTE-C19", "0"))
        registry.ingest_hit(_hit("axicabtagene ciloleucel", "1"))
        assert registry.consolidate_by_authority() == {}
