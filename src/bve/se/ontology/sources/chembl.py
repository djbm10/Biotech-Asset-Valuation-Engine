"""Parse ChEMBL ``target`` records into source-fidelity rows.

ChEMBL contributes UniProt accessions (the join key against Open Targets) and a rich
synonym set drawn from UniProt. Two real-data quirks are handled here:

* UniProt-derived synonyms arrive with a field prefix, e.g. ``CD_antigen=CD279`` and
  ``Synonyms=PD1``. Taking the raw string would bury ``CD279`` behind a prefix that
  no search engine will ever match, so the prefix is stripped and the remainder split.
* Only ``SINGLE PROTEIN`` targets carry a clean one-accession identity. Protein
  complexes and families list several accessions, which would union unrelated targets
  into one entity; their accessions are recorded but not used as join keys.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
)

SOURCE_NAME = "chembl"

#: ChEMBL ``target_type`` values whose accessions identify exactly one protein.
_SINGLE_IDENTITY_TARGET_TYPES = frozenset({"SINGLE PROTEIN"})

_SYN_TYPE_TO_ALIAS_TYPE = {
    "GENE_SYMBOL": AliasType.SYMBOL,
    "GENE_SYMBOL_OTHER": AliasType.SYNONYM,
    "UNIPROT": AliasType.SYNONYM,
    "EC_NUMBER": AliasType.XREF,
}


def _clean_synonyms(raw: str) -> Iterable[str]:
    """Strip UniProt field prefixes and split multi-valued synonym strings.

    ``"CD_antigen=CD279"`` yields ``"CD279"``; ``"Synonyms=PD1; PD-1"`` yields both.

    Only ``;`` separates values. Commas are part of UniProt recommended names --
    splitting on them turns "4-aminobutyrate aminotransferase, mitochondrial" into a
    bogus "mitochondrial" alias that then collides with every other mitochondrial
    protein in the snapshot.
    """

    payload = raw.split("=", 1)[1] if "=" in raw else raw
    for part in payload.split(";"):
        candidate = part.strip()
        if candidate:
            yield candidate


def parse_chembl_target(record: Mapping[str, Any]) -> SourceEntityRecord | None:
    """Convert one ChEMBL target row; ``None`` when it carries no usable ID."""

    chembl_id = record.get("target_chembl_id")
    if not isinstance(chembl_id, str) or not chembl_id.strip():
        return None

    target_type = str(record.get("target_type") or "")
    single_identity = target_type.upper() in _SINGLE_IDENTITY_TARGET_TYPES

    aliases: list[SourceAlias] = []
    seen: set[tuple[str, AliasType]] = set()
    symbol: str | None = None
    accessions: list[str] = []

    def add(value: str, alias_type: AliasType) -> None:
        if not value.strip():
            return
        alias = SourceAlias(value=value, alias_type=alias_type)
        key = (alias.normalized, alias_type)
        if key not in seen:
            seen.add(key)
            aliases.append(alias)

    for component in record.get("target_components") or []:
        if not isinstance(component, Mapping):
            continue
        accession = component.get("accession")
        if isinstance(accession, str) and accession.strip():
            accessions.append(accession)
        for synonym in component.get("target_component_synonyms") or []:
            if not isinstance(synonym, Mapping):
                continue
            raw = synonym.get("component_synonym")
            if not isinstance(raw, str):
                continue
            alias_type = _SYN_TYPE_TO_ALIAS_TYPE.get(str(synonym.get("syn_type") or ""), AliasType.SYNONYM)
            for value in _clean_synonyms(raw):
                if alias_type is AliasType.SYMBOL and symbol is None:
                    symbol = value
                add(value, alias_type)

    xrefs: dict[str, list[str]] = {"chembl": [chembl_id]}
    if accessions:
        # Non-single-protein targets keep their accessions for inspection but are not
        # joined on, so a complex never absorbs its member proteins.
        xrefs["uniprot" if single_identity else "uniprot_unjoinable"] = accessions

    pref_name = record.get("pref_name")
    return SourceEntityRecord(
        source=SOURCE_NAME,
        source_id=chembl_id,
        entity_type=EntityType.TARGET,
        canonical_symbol=symbol,
        label=pref_name if isinstance(pref_name, str) and pref_name.strip() else None,
        aliases=aliases,
        xrefs=xrefs,
    )
