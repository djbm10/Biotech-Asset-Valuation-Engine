"""A token split off a longer target alias is not a target name: ``target_alias_fragment_v1_amendment_1.md``."""

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


def test_a_fragment_claimant_still_makes_a_shared_string_ambiguous() -> None:
    # The DPP case: v1 dropped the fragment claim and handed the string to the other entity.
    resolver = _resolver(
        _target("E1", "DPP7", "DPP II", "DPP", "II"),
        _target("E2", "DSPP", "DPP"),
    )
    assert _status(resolver, "DPP") is ResolutionStatus.AMBIGUOUS
    assert resolver.claimants_of("DPP", EntityType.TARGET) == ("TARGET:DPP7", "TARGET:DSPP")


def test_a_fragment_that_wins_on_precedence_is_refused_not_replaced() -> None:
    fragment_holder = _target("E1", "ST6GALNAC4", "ST6GalNAc IV", "ST6GalNAc", "IV")
    other = SourceEntityRecord(
        source="open_targets",
        source_id="E2",
        entity_type=EntityType.TARGET,
        canonical_symbol="FAKE4",
        label="FAKE4",
        aliases=[
            SourceAlias(value="FAKE4", alias_type=AliasType.SYMBOL),
            SourceAlias(value="IV", alias_type=AliasType.SYNONYM),
        ],
    )
    result = _resolver(fragment_holder, other).resolve("IV", EntityType.TARGET)
    assert result.status is ResolutionStatus.UNRESOLVED
    assert result.rule == "fragment_alias_only"


def test_the_rule_only_removes_resolutions() -> None:
    records = (
        _target("E1", "ST6GALNAC4", "ST6GalNAc IV", "ST6GalNAc", "IV"),
        _target("E2", "DPP7", "DPP II", "DPP", "II"),
        _target("E3", "DSPP", "DPP"),
        _target("E4", "NFE2", "p45 NF-E2", "p45", "NF-E2"),
        _target("E5", "CD19", "CD19 antigen", "B4"),
    )
    resolver = _resolver(*records)
    strings = {alias.value for record in records for alias in record.aliases}
    for value in strings:
        result = resolver.resolve(value, EntityType.TARGET)
        if result.status is ResolutionStatus.RESOLVED:
            # No split fragment is ever the resolving claim.
            assert value not in {"IV", "II", "p45"}
    for value in ("CD19", "B4", "NF-E2", "DSPP", "DPP7", "ST6GALNAC4"):
        assert _status(resolver, value) is ResolutionStatus.RESOLVED
    assert _status(resolver, "DPP") is ResolutionStatus.AMBIGUOUS
