"""Parse Open Targets ``drug_molecule`` and ``drug_mechanism_of_action`` rows.

Open Targets is a second authority over the same question ChEMBL answers, not a
replacement for it. Both are kept as source-fidelity records so that agreement and
disagreement are both visible.

Two safeguards are enforced here rather than downstream:

* **ChEMBL-sourced strings only.** Open Targets labels each synonym and trade name with
  where it came from, and some come from AACT — free text scraped from trial registrations.
  Those are exactly the strings this layer must not treat as identity evidence, since
  binding them would let a registry's own phrasing decide what an asset is.
* **No component inheritance.** ``childChemblIds`` is recorded as a cross-reference for
  provenance, never expanded into aliases or edges: a coformulation must not acquire its
  components' names or targets.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

from pydantic import Field

from bve.se.ontology.mechanisms import MechanismRow
from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
)
from bve.se.schemas.contracts import StrictModel

SOURCE_NAME = "open_targets"

#: The only synonym provenance this parser will bind. Open Targets also carries AACT
#: labels, which are trial free text, not an identity assertion.
_TRUSTED_LABEL_SOURCES = frozenset({"chembl"})


def _trusted_labels(raw: Any) -> Iterable[str]:
    """Yield labels an authority asserted, dropping registry free text."""

    if not isinstance(raw, list):
        return
    for item in raw:
        if not isinstance(item, Mapping):
            # A bare string carries no provenance, so it cannot be shown to be
            # authority-sourced and is not bound.
            continue
        label = item.get("label")
        source = str(item.get("source") or "").strip().casefold()
        if isinstance(label, str) and source in _TRUSTED_LABEL_SOURCES:
            yield label


def parse_open_targets_drug(record: Mapping[str, Any]) -> SourceEntityRecord | None:
    """Convert one Open Targets drug row; ``None`` when it carries no usable identity."""

    chembl_id = record.get("id")
    if not isinstance(chembl_id, str) or not chembl_id.strip():
        return None
    name = record.get("name")
    if not isinstance(name, str) or not name.strip():
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

    add(name, AliasType.APPROVED_NAME)
    for label in _trusted_labels(record.get("synonyms")):
        add(label, AliasType.SYNONYM)
    for label in _trusted_labels(record.get("tradeNames")):
        add(label, AliasType.TRADE_NAME)

    xrefs: dict[str, list[str]] = {"chembl": [chembl_id]}
    inchikey = record.get("inchiKey")
    if isinstance(inchikey, str) and inchikey.strip():
        xrefs["inchikey"] = [inchikey]
    # Recorded for provenance only. These are never join keys and never aliases: a
    # coformulation joined to its children would inherit their identity and their targets.
    children = [child for child in (record.get("childChemblIds") or []) if isinstance(child, str)]
    if children:
        xrefs["chembl_child"] = children

    return SourceEntityRecord(
        source=SOURCE_NAME,
        source_id=chembl_id,
        entity_type=EntityType.DRUG,
        canonical_symbol=name,
        label=name,
        aliases=aliases,
        xrefs=xrefs,
    )


class OpenTargetsMoaRow(StrictModel):
    """One Open Targets mechanism-of-action row, before it is expanded into edges.

    The dataset publishes no stable row identifier, so the evidence hash doubles as one.
    """

    drug_source_ids: list[str] = Field(default_factory=list)
    target_source_ids: list[str] = Field(default_factory=list)
    action_type: str | None = None
    mechanism_of_action: str | None = None
    target_type: str | None = None
    evidence_hash: str = Field(min_length=1)

    @property
    def is_single_protein(self) -> bool:
        """Whether the row names one protein rather than a complex or a family.

        A complex or family row lists every member gene. Treating each member as a
        directly bound target would assert something the row does not say -- the same
        inheritance mistake as giving a coformulation its components' targets.
        """

        return (self.target_type or "").strip().casefold() == "single protein"


def parse_open_targets_moa(record: Mapping[str, Any]) -> OpenTargetsMoaRow | None:
    """Convert one Open Targets mechanism row; ``None`` when it links nothing."""

    drugs = [value for value in (record.get("chemblIds") or []) if isinstance(value, str)]
    targets = [value for value in (record.get("targets") or []) if isinstance(value, str)]
    if not drugs or not targets:
        return None

    payload = {
        "chemblIds": sorted(drugs),
        "targets": sorted(targets),
        "actionType": record.get("actionType"),
        "mechanismOfAction": record.get("mechanismOfAction"),
        "targetType": record.get("targetType"),
    }
    return OpenTargetsMoaRow(
        drug_source_ids=drugs,
        target_source_ids=targets,
        action_type=record.get("actionType") or None,
        mechanism_of_action=record.get("mechanismOfAction") or None,
        target_type=record.get("targetType") or None,
        evidence_hash=hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )


def expand_open_targets_moa(rows: Iterable[OpenTargetsMoaRow]) -> list[MechanismRow]:
    """Flatten mechanism rows into one row per drug/target pair.

    Open Targets states a mechanism once for a set of drugs and a set of targets. Every
    pair inherits the same evidence hash, which is what lets an edge be traced back to
    the single upstream row it came from.
    """

    expanded: list[MechanismRow] = []
    for row in rows:
        for drug_id in row.drug_source_ids:
            for target_id in row.target_source_ids:
                expanded.append(
                    MechanismRow(
                        source=SOURCE_NAME,
                        source_record_id=row.evidence_hash,
                        drug_source_id=drug_id,
                        target_source_id=target_id,
                        action_type=row.action_type,
                        mechanism_of_action=row.mechanism_of_action,
                        direct_interaction=row.is_single_protein,
                        evidence_hash=row.evidence_hash,
                    )
                )
    return expanded
