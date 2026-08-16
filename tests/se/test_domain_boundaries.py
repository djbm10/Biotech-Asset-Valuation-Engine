"""Internal storage keys must never escape into scientific comparison interfaces.

Two identifier domains meet in the ontology layer and are easy to confuse:

* the **storage** domain — ``target:CD19``, ``drug:chembl:CHEMBL25``,
  ``disease:efo:EFO_0000311`` — internal registry keys whose only job is to be unique
* the **scientific** domain — ``CD19``, ``TNFRSF17`` — what a query names, what a source
  document says, and what a downstream comparison is entitled to compare

``known_targets()`` shipped keyed by the storage domain, so ontology-wide labelling
produced ``target:CD19`` and could never match a compiled query asking for ``CD19``. That
is a class of bug, not an incident: the same mistake is available for drugs and diseases.
These tests therefore assert the *invariant* over every entity type rather than the one
symbol that happened to break.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
    SourceProvenance,
)
from bve.se.ontology.resolver import BiomedicalEntityResolver
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.ontology.targets import known_targets, normalize_target, target_aliases

#: A storage key is ``<entity type>:...``. No scientific identifier is spelled this way.
_STORAGE_KEY = re.compile(
    rf"^(?:{'|'.join(entity.value for entity in EntityType)}):", re.IGNORECASE
)


def _record(
    entity_type: EntityType,
    source_id: str,
    symbol: str,
    *,
    namespace: str,
    accession: str,
    synonym: str | None = None,
) -> SourceEntityRecord:
    return SourceEntityRecord(
        source="open_targets",
        source_id=source_id,
        entity_type=entity_type,
        canonical_symbol=symbol,
        label=symbol,
        aliases=(
            [SourceAlias(value=synonym, alias_type=AliasType.SYNONYM)] if synonym else []
        ),
        xrefs={namespace: [accession]},
    )


@pytest.fixture
def resolver() -> BiomedicalEntityResolver:
    """One entity of every type, so the invariant is checked across all three domains."""

    return BiomedicalEntityResolver(
        OntologySnapshot(
            sources=[
                SourceProvenance(
                    source="open_targets",
                    release="26.06",
                    retrieved_at=date(2026, 8, 15),
                    locator="ftp://example.invalid/open_targets/26.06",
                )
            ],
            records=[
                _record(
                    EntityType.TARGET,
                    "ENSG00000188389",
                    "PDCD1",
                    namespace="uniprot",
                    accession="Q15116",
                    synonym="PD-1",
                ),
                _record(
                    EntityType.DRUG,
                    "CHEMBL25",
                    "ASPIRIN",
                    namespace="chembl",
                    accession="CHEMBL25",
                ),
                _record(
                    EntityType.DISEASE,
                    "EFO_0000311",
                    "CANCER",
                    namespace="efo",
                    accession="EFO_0000311",
                ),
            ],
        )
    )


def test_storage_keys_stay_inside_the_registry(resolver: BiomedicalEntityResolver) -> None:
    """Canonical ids are storage keys; symbols and aliases are the scientific domain."""

    for entity_type in EntityType:
        for entity in resolver.entities_of_type(entity_type):
            assert _STORAGE_KEY.match(entity.canonical_id), (
                "canonical_id is the storage key and is expected to be namespaced"
            )
            assert not _STORAGE_KEY.match(entity.canonical_symbol or "")
            for alias in entity.queryable_aliases():
                assert not _STORAGE_KEY.match(alias), (
                    f"{entity.canonical_id} would emit the storage key {alias!r} as a "
                    "searchable term"
                )


def test_resolution_answers_in_the_scientific_domain(
    resolver: BiomedicalEntityResolver,
) -> None:
    for entity_type in EntityType:
        for entity in resolver.entities_of_type(entity_type):
            result = resolver.resolve(entity.canonical_id, entity_type)
            assert not _STORAGE_KEY.match(result.canonical_symbol or "")


def test_public_target_api_never_emits_storage_keys(se_ontology_snapshot) -> None:
    """The seam discovery actually calls. A storage key here is un-matchable downstream.

    ``known_targets`` feeds whole-ontology labelling, which is compared against the target
    ids a compiled query carries. Those are symbols, so anything else silently labels
    nothing rather than failing loudly.
    """

    symbols = {symbol for symbol, _ in known_targets()}
    assert symbols == {"CD19", "TNFRSF17"}
    assert not any(_STORAGE_KEY.match(symbol) for symbol in symbols)

    for symbol in symbols:
        assert not any(_STORAGE_KEY.match(alias) for alias in target_aliases(symbol))

    # A synonym resolves to the approved symbol, never to the key it is stored under.
    assert normalize_target("BCMA") == "TNFRSF17"
