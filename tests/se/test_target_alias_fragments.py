"""A token split off a longer target alias is not a target name: ``target_alias_fragment_v1.md``."""

from __future__ import annotations

from datetime import date

from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
    SourceProvenance,
)
from bve.se.ontology.resolver import BiomedicalEntityResolver, ResolutionStatus
from bve.se.ontology.snapshot import OntologySnapshot


def _target(source_id: str, symbol: str, *aliases: str) -> SourceEntityRecord:
    return SourceEntityRecord(
        source="open_targets",
        source_id=source_id,
        entity_type=EntityType.TARGET,
        canonical_symbol=symbol,
        label=symbol,
        aliases=[
            SourceAlias(value=symbol, alias_type=AliasType.SYMBOL),
            *(SourceAlias(value=alias, alias_type=AliasType.SYMBOL) for alias in aliases),
        ],
    )


def _resolver(*records: SourceEntityRecord) -> BiomedicalEntityResolver:
    return BiomedicalEntityResolver(
        OntologySnapshot(
            sources=[
                SourceProvenance(
                    source="open_targets",
                    release="26.06",
                    retrieved_at=date(2026, 9, 7),
                    locator="test",
                    digest="d",
                    record_count=len(records),
                )
            ],
            records=list(records),
        )
    )


def _status(resolver: BiomedicalEntityResolver, value: str) -> ResolutionStatus:
    return resolver.resolve(value, EntityType.TARGET).status


def test_a_split_off_short_token_does_not_resolve() -> None:
    resolver = _resolver(_target("E1", "ST6GALNAC4", "ST6GalNAc IV", "ST6GalNAc", "IV"))
    assert _status(resolver, "IV") is ResolutionStatus.UNRESOLVED
    # The whole alias and the approved symbol still identify the target.
    assert _status(resolver, "ST6GalNAc IV") is ResolutionStatus.RESOLVED
    assert _status(resolver, "ST6GALNAC4") is ResolutionStatus.RESOLVED


def test_a_short_alias_that_is_not_a_split_piece_still_resolves() -> None:
    # "antigen" is not an alias, so "CD19 antigen" is not the split signature.
    resolver = _resolver(_target("E1", "CD19", "CD19 antigen", "B4"))
    assert _status(resolver, "B4") is ResolutionStatus.RESOLVED


def test_the_approved_symbol_is_never_a_fragment() -> None:
    resolver = _resolver(_target("E1", "KIT", "KIT receptor", "receptor"))
    assert _status(resolver, "KIT") is ResolutionStatus.RESOLVED


def test_a_longer_split_piece_is_kept() -> None:
    resolver = _resolver(_target("E1", "NFE2", "p45 NF-E2", "p45", "NF-E2"))
    assert _status(resolver, "NF-E2") is ResolutionStatus.RESOLVED
    assert _status(resolver, "p45") is ResolutionStatus.UNRESOLVED


def test_another_entity_keeps_its_own_claim_on_the_string() -> None:
    resolver = _resolver(
        _target("E1", "ST6GALNAC4", "ST6GalNAc IV", "ST6GalNAc", "IV"),
        _target("E2", "FAKE4", "IV"),
    )
    result = resolver.resolve("IV", EntityType.TARGET)
    assert result.status is ResolutionStatus.RESOLVED
    assert result.canonical_id != "TARGET:ST6GALNAC4"
