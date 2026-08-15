"""Source-fidelity records for the biomedical entity layer.

These records are deliberately *not* merged. Each one states what a single upstream
source said about a single entity, together with the provenance needed to re-derive
it. The normalized view built by :mod:`bve.se.ontology.resolver` sits on top of these
records and never replaces them, so a disagreement between Open Targets and ChEMBL
stays visible instead of being silently resolved in favour of one source.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import ConfigDict, Field, field_validator

from bve.se.schemas.contracts import StrictModel


class EntityType(str, Enum):
    """The kinds of biomedical entity the resolver can normalize."""

    TARGET = "TARGET"
    DRUG = "DRUG"
    DISEASE = "DISEASE"


class AliasType(str, Enum):
    """Why a string is attached to an entity.

    The type matters for query expansion: a ``SYMBOL`` is safe to search verbatim,
    whereas a ``DESCRIPTION`` is usually too generic to use as a search term.
    """

    SYMBOL = "SYMBOL"
    APPROVED_NAME = "APPROVED_NAME"
    SYNONYM = "SYNONYM"
    TRADE_NAME = "TRADE_NAME"
    DEVELOPMENT_CODE = "DEVELOPMENT_CODE"
    XREF = "XREF"
    DESCRIPTION = "DESCRIPTION"


#: Alias types that are specific enough to expand into a literal search query.
QUERYABLE_ALIAS_TYPES = frozenset(
    {
        AliasType.SYMBOL,
        AliasType.APPROVED_NAME,
        AliasType.SYNONYM,
        AliasType.TRADE_NAME,
        AliasType.DEVELOPMENT_CODE,
    }
)


class SourceProvenance(StrictModel):
    """Which upstream release a set of records was derived from."""

    source: str = Field(min_length=1)
    release: str = Field(min_length=1)
    retrieved_at: date
    locator: str = Field(min_length=1)
    digest: str | None = None
    record_count: int = Field(default=0, ge=0)

    @property
    def version_token(self) -> str:
        """The fragment this source contributes to an ``ontology_version`` string."""

        return f"{self.source}_{self.release}"


class SourceAlias(StrictModel):
    """One string an upstream source associated with one entity."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True, frozen=True)

    value: str = Field(min_length=1)
    alias_type: AliasType

    @field_validator("value")
    @classmethod
    def strip_value(cls, value: str) -> str:
        collapsed = " ".join(value.split())
        if not collapsed:
            raise ValueError("alias value cannot be blank")
        return collapsed

    @property
    def normalized(self) -> str:
        """The casefolded form used for lookup, with common separators unified."""

        return normalize_lookup_key(self.value)

    @property
    def is_queryable(self) -> bool:
        return self.alias_type in QUERYABLE_ALIAS_TYPES


def normalize_lookup_key(value: str) -> str:
    """Fold a user-supplied string into the resolver's lookup key space.

    Hyphens and underscores are treated as insignificant so that ``PD-1``, ``PD_1``
    and ``PD 1`` collapse together, which is the dominant alias-spelling axis in
    target nomenclature. Digits are never separated from letters, so ``CD19`` and
    ``CD 19`` also collapse, but ``CD19`` and ``CD199`` stay distinct.
    """

    lowered = value.casefold()
    unified = lowered.replace("-", " ").replace("_", " ").replace("/", " ")
    return " ".join(unified.split())


class SourceEntityRecord(StrictModel):
    """What one source says about one entity, before any cross-source merge."""

    source: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    entity_type: EntityType
    canonical_symbol: str | None = None
    label: str | None = None
    aliases: list[SourceAlias] = Field(default_factory=list)
    #: Cross-source join keys, e.g. ``{"uniprot": ["P16410"], "ensembl": ["ENSG..."]}``.
    xrefs: dict[str, list[str]] = Field(default_factory=dict)

    @property
    def record_key(self) -> str:
        return f"{self.source}:{self.source_id}"

    def join_keys(self, namespace: str) -> tuple[str, ...]:
        """Normalized cross-reference values for one namespace."""

        return tuple(sorted({value.strip().upper() for value in self.xrefs.get(namespace, []) if value.strip()}))

    def all_aliases(self) -> tuple[SourceAlias, ...]:
        """Aliases plus the symbol and label, de-duplicated by normalized value."""

        collected: list[SourceAlias] = []
        if self.canonical_symbol:
            collected.append(SourceAlias(value=self.canonical_symbol, alias_type=AliasType.SYMBOL))
        if self.label:
            collected.append(SourceAlias(value=self.label, alias_type=AliasType.APPROVED_NAME))
        collected.extend(self.aliases)

        seen: dict[tuple[str, AliasType], SourceAlias] = {}
        for alias in collected:
            seen.setdefault((alias.normalized, alias.alias_type), alias)
        return tuple(seen.values())
