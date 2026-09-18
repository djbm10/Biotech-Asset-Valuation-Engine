"""Parse Open Targets bulk ``target`` records into source-fidelity rows.

Open Targets is the symbol authority for targets: ``approvedSymbol`` is the HGNC
approved symbol. The parser accepts both the modern ``synonyms: [{label, source}]``
shape and the older split ``symbolSynonyms`` / ``nameSynonyms`` lists, because the
two coexist across releases and we pin releases rather than chasing the newest.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
)

SOURCE_NAME = "open_targets"


def _synonym_labels(raw: Any) -> Iterable[str]:
    """Yield labels from either ``["PD-1"]`` or ``[{"label": "PD-1", ...}]``."""

    if not isinstance(raw, list):
        return
    for item in raw:
        if isinstance(item, str):
            yield item
        elif isinstance(item, Mapping):
            label = item.get("label") or item.get("name")
            if isinstance(label, str):
                yield label


def _protein_accessions(record: Mapping[str, Any]) -> list[str]:
    accessions: list[str] = []
    for item in record.get("proteinIds") or []:
        if isinstance(item, Mapping):
            # Only UniProt-family sources are valid join keys; Ensembl protein IDs
            # would create false joins against ChEMBL accessions.
            source = str(item.get("source") or "")
            identifier = item.get("id")
            if isinstance(identifier, str) and source.startswith("uniprot"):
                accessions.append(identifier)
        elif isinstance(item, str):
            accessions.append(item)
    for key in ("uniprotIds", "uniprot_ids"):
        for value in record.get(key) or []:
            if isinstance(value, str):
                accessions.append(value)
    return accessions


def parse_open_targets_target(record: Mapping[str, Any]) -> SourceEntityRecord | None:
    """Convert one Open Targets target row; ``None`` when it carries no usable ID."""

    ensembl_id = record.get("id") or record.get("ensemblId")
    if not isinstance(ensembl_id, str) or not ensembl_id.strip():
        return None

    aliases: list[SourceAlias] = []
    seen: set[tuple[str, AliasType]] = set()

    def add(value: Any, alias_type: AliasType) -> None:
        if not isinstance(value, str) or not value.strip():
            return
        alias = SourceAlias(value=value, alias_type=alias_type)
        key = (alias.normalized, alias_type)
        if key not in seen:
            seen.add(key)
            aliases.append(alias)

    for label in _synonym_labels(record.get("synonyms")):
        add(label, AliasType.SYNONYM)
    for label in _synonym_labels(record.get("symbolSynonyms")):
        add(label, AliasType.SYMBOL)
    for label in _synonym_labels(record.get("nameSynonyms")):
        add(label, AliasType.SYNONYM)
    for label in _synonym_labels(record.get("obsoleteSymbols")):
        add(label, AliasType.SYNONYM)

    accessions = _protein_accessions(record)
    xrefs: dict[str, list[str]] = {"ensembl": [ensembl_id]}
    if accessions:
        xrefs["uniprot"] = accessions
    hgnc = record.get("hgncId")
    if isinstance(hgnc, str) and hgnc.strip():
        xrefs["hgnc"] = [hgnc]

    symbol = record.get("approvedSymbol")
    name = record.get("approvedName")
    return SourceEntityRecord(
        source=SOURCE_NAME,
        source_id=ensembl_id,
        entity_type=EntityType.TARGET,
        canonical_symbol=symbol if isinstance(symbol, str) and symbol.strip() else None,
        label=name if isinstance(name, str) and name.strip() else None,
        aliases=aliases,
        xrefs=xrefs,
    )
