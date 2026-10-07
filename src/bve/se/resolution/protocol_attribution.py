"""Trial-level attribution by a trial's own sponsor protocol id (``protocol_id_trial_attribution_v1``).

A trial can sit on a descriptor asset ("CD19-targeted CAR T Cells") while its own protocol id
(``JWCAR029-005``) names a product that is already an asset. This plans moves of such trials
to that product. It never merges, creates or deletes an asset, and never consults sponsor.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from bve.se.schemas.contracts import CanonicalAsset

#: R1: the leading code token of a sponsor protocol id.
_PREFIX = re.compile(r"^([A-Za-z]{2,8}[- ]?\d{2,5}[A-Za-z]?)(?=$|[-_ .])")
#: R3: antigen or construct designators are not product codes.
_ANTIGENISH = re.compile(r"^(cd\d{1,3}[a-z]?|bcma\d*|car-?t?\d{1,3}|cart\d{1,3})$")
#: R6: a product-code-shaped token in a source asset's own name.
_CODE_TOKEN = re.compile(r"[a-z]{1,8}-?\d{2,5}[a-z]?", re.IGNORECASE)

#: Frozen vocabulary of ``generic_descriptor_split_diagnosis_v1`` §1 (R4).
_GENERIC_WORDS = frozenset(
    """car cart car-t cars t tcr nk cell cells lymphocyte lymphocytes injection infusion
    therapy therapies treatment targeted targeting target dual bispecific tandem anti autologous
    allogeneic allogenic universal u chimeric antigen receptor receptors engineered redirected
    modified expressing product products and or plus with of the for directed specific gene
    cord blood umbilical derived ucb in vivo nanobody based cord-blood donor donor-derived
    cytotoxic gamma delta γδt γδ αβ natural killer infusions group arm""".split()
)
_GENERIC_ANTIGEN = re.compile(r"^(cd\d{1,3}[a-z]?|bcma|tnfrsf17|\d{1,3}|car-?t?[1-9]\d{0,2})$")


def _tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[\s/,+()\-–_.:;\[\]]+", name.casefold()) if t]


def is_generic_descriptor(name: str) -> bool:
    """Every token is a modality/format word or an antigen designator, with a CAR/TCR/NK word."""

    tokens = _tokens(name)
    return (
        bool(tokens)
        and any(t in ("car", "cart", "tcr", "nk") or t.startswith("car") for t in tokens)
        and all(t in _GENERIC_WORDS or _GENERIC_ANTIGEN.match(t) for t in tokens)
    )


def link_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def protocol_prefix(protocol_id: str | None) -> str | None:
    match = _PREFIX.match((protocol_id or "").strip())
    return match.group(1) if match else None


def intervention_keys(record: Mapping) -> set[str]:
    """Link keys of a CT.gov record's intervention names, ``otherNames``, and their tokens."""

    interventions = (record.get("armsInterventionsModule") or {}).get("interventions") or []
    names = [
        value
        for intervention in interventions
        for value in [intervention.get("name") or "", *(intervention.get("otherNames") or [])]
    ]
    keys = {link_key(name) for name in names}
    keys |= {link_key(token) for name in names for token in re.split(r"[,;()]\s*|\s+", name)}
    return keys


def sponsor_protocol_id(record: Mapping) -> str | None:
    return ((record.get("identificationModule") or {}).get("orgStudyIdInfo") or {}).get("id")


@dataclass(frozen=True)
class TrialMove:
    trial_id: str
    from_asset_id: str
    to_asset_id: str
    protocol_id: str
    prefix: str

    @property
    def basis(self) -> str:
        return f"protocol_id:{self.prefix}"

    def as_record(self) -> dict:
        return {
            "trial_id": self.trial_id,
            "from_asset_id": self.from_asset_id,
            "to_asset_id": self.to_asset_id,
            "protocol_id": self.protocol_id,
            "prefix": self.prefix,
            "basis": self.basis,
        }


def _names(asset: CanonicalAsset) -> list[str]:
    return [asset.canonical_name, *asset.aliases]


def plan_protocol_moves(
    assets: Iterable[CanonicalAsset],
    records: Mapping[str, Mapping],
    has_drug_authority: Callable[[list[str]], bool],
) -> list[TrialMove]:
    """R1-R7 over every (asset, CT.gov trial) pair. ``records`` maps trial id -> sealed record."""

    by_id = {asset.asset_id: asset for asset in assets}
    by_key: dict[str, set[str]] = {}
    for asset in by_id.values():
        for name in _names(asset):
            by_key.setdefault(link_key(name), set()).add(asset.asset_id)
    moves: list[TrialMove] = []
    for source in sorted(by_id.values(), key=lambda a: a.asset_id):
        source_specific: bool | None = None
        for trial_id in source.trial_ids:
            record = records.get(trial_id)
            if record is None:
                continue
            protocol_id = sponsor_protocol_id(record) or ""
            prefix = protocol_prefix(protocol_id)
            if prefix is None:
                continue
            key = link_key(prefix)
            holders = by_key.get(key, set())
            owners = holders - {source.asset_id}
            if not owners or source.asset_id in holders:  # R2
                continue
            if source_specific is None:  # R6, computed once per source
                source_specific = has_drug_authority(_names(source)) or any(
                    not _ANTIGENISH.match(link_key(token)) and _CODE_TOKEN.fullmatch(token)
                    for name in _names(source)
                    for token in re.split(r"[\s/,+()\[\]]+", name)
                    if token
                )
            if source_specific or _ANTIGENISH.match(key) or len(owners) != 1:  # R6, R3, R2
                continue
            destination = by_id[next(iter(owners))]
            if trial_id in destination.trial_ids:  # R7
                continue
            if all(is_generic_descriptor(name) for name in _names(destination)):  # R4
                continue
            if not any(  # R5
                key in intervention_keys(records[other])
                for other in destination.trial_ids
                if other in records
            ):
                continue
            moves.append(
                TrialMove(trial_id, source.asset_id, destination.asset_id, protocol_id, prefix)
            )
    return moves
