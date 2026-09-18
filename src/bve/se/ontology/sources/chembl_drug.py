"""Parse ChEMBL ``molecule`` rows into source-fidelity records.

ChEMBL is the identifier authority for drugs (``molecule_chembl_id``) in the
same way Open Targets is for targets. Only identity is parsed here: who a
molecule *is*. What a molecule is documented to *act on* is a separate edge table, kept apart on purpose.
Conflating the two is what let a query target be stamped onto every candidate
it happened to co-occur with.

A molecule with no mechanism row is not evidence of anything. The absence is carried
through as silence, never as a negative.
"""

from __future__ import annotations

from typing import Any, Mapping

from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
)

SOURCE_NAME = "chembl"

#: ChEMBL ``syn_type`` values mapped onto the alias vocabulary. INN, USAN and BAN are the
#: nonproprietary names; RESEARCH_CODE is where development codes like ABBV-181 live,
#: which is exactly the spelling a trial registry is most likely to use.
_SYN_TYPE_TO_ALIAS_TYPE = {
    "INN": AliasType.APPROVED_NAME,
    "USAN": AliasType.APPROVED_NAME,
    "USP": AliasType.APPROVED_NAME,
    "BAN": AliasType.APPROVED_NAME,
    "JAN": AliasType.APPROVED_NAME,
    "TRADE_NAME": AliasType.TRADE_NAME,
    "BRAND_NAME": AliasType.TRADE_NAME,
    "RESEARCH_CODE": AliasType.DEVELOPMENT_CODE,
    "ATC": AliasType.XREF,
    "FDA": AliasType.SYNONYM,
    "MERCK_INDEX": AliasType.SYNONYM,
    "OTHER": AliasType.SYNONYM,
}


def parse_chembl_molecule(record: Mapping[str, Any]) -> SourceEntityRecord | None:
    """Convert one ChEMBL molecule row; ``None`` when it carries no usable identity.

    A molecule with no preferred name is skipped: ChEMBL holds ~2.9M structures, of which
    only ~49k are named compounds. The unnamed remainder cannot be matched to anything a
    trial registry or company document would call an asset, so indexing them adds 60x the
    volume and no reachable identity.
    """

    chembl_id = record.get("molecule_chembl_id")
    if not isinstance(chembl_id, str) or not chembl_id.strip():
        return None
    pref_name = record.get("pref_name")
    if not isinstance(pref_name, str) or not pref_name.strip():
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

    add(pref_name, AliasType.APPROVED_NAME)
    for synonym in record.get("molecule_synonyms") or []:
        if not isinstance(synonym, Mapping):
            continue
        alias_type = _SYN_TYPE_TO_ALIAS_TYPE.get(
            str(synonym.get("syn_type") or "").upper(), AliasType.SYNONYM
        )
        add(synonym.get("molecule_synonym"), alias_type)

    xrefs: dict[str, list[str]] = {"chembl": [chembl_id]}
    structures = record.get("molecule_structures")
    if isinstance(structures, Mapping):
        inchikey = structures.get("standard_inchi_key")
        if isinstance(inchikey, str) and inchikey.strip():
            # An InChIKey identifies a small molecule across sources. Antibodies have no
            # structure record, so they join on the ChEMBL id alone.
            xrefs["inchikey"] = [inchikey]

    return SourceEntityRecord(
        source=SOURCE_NAME,
        source_id=chembl_id,
        entity_type=EntityType.DRUG,
        canonical_symbol=pref_name,
        label=pref_name,
        aliases=aliases,
        xrefs=xrefs,
    )
