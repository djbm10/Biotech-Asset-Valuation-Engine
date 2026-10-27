"""Conservative, reviewable identity questions over an imported landscape.

Nothing here merges anything. Assets are already keyed by (source system, external ID) in
the importer; this module only raises flags for an analyst:

- SHARED_CODE: two distinct records use the same name or code (in S&E's normalized name
  space, so ``MB-102`` and ``MB102`` collide). This is the IL3RA MB-102 failure class: one
  code, two companies' molecules. The relationship is UNCERTAIN and stays unmerged.
- PROPOSED_MERGE: an identity authority resolves names from both records to the same drug
  AND the records name the same company. Still only a proposal: an analyst merge decision
  is required, and a shared code with an authority match but different companies stays a
  SHARED_CODE question, because that is exactly how the MB-102 merge happened.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from itertools import combinations

from bve.dealscreen.models import IdentityFlag, LandscapeAsset
from bve.se.resolution.registry import normalize_identity_name
from bve.se.schemas.contracts import IdentityRelationship

#: name -> authority drug id, or None when the authority cannot resolve it unambiguously.
DrugAuthority = Callable[[str], str | None]


def _company_key(value: str | None) -> str:
    return normalize_identity_name(value) or ""


def _flag_id(kind: str, ids: list[str], value: str) -> str:
    digest = hashlib.sha256(f"{kind}|{'|'.join(sorted(ids))}|{value}".encode()).hexdigest()[:12]
    return f"idflag:{digest}"


def identity_flags(
    assets: list[LandscapeAsset], *, authority: DrugAuthority | None = None
) -> list[IdentityFlag]:
    by_name: dict[str, list[str]] = {}
    names_of: dict[str, list[str]] = {}
    by_id = {asset.asset_id: asset for asset in assets}
    for asset in assets:
        names = [asset.program_name, *asset.aliases]
        names_of[asset.asset_id] = names
        for key in {normalize_identity_name(name) for name in names} - {None}:
            assert key is not None
            by_name.setdefault(key, []).append(asset.asset_id)

    flags: dict[str, IdentityFlag] = {}
    for key, ids in sorted(by_name.items()):
        if len(ids) < 2:
            continue
        flag_id = _flag_id("SHARED_CODE", ids, key)
        flags[flag_id] = IdentityFlag(
            flag_id=flag_id,
            kind="SHARED_CODE",
            asset_ids=sorted(ids),
            shared_value=key,
            relationship=IdentityRelationship.UNCERTAIN_RELATIONSHIP.value,
            basis=(
                f"{len(ids)} distinct source records share the name/code {key!r}. A shared "
                "code is not identity evidence; the records stay separate until an analyst "
                "decides."
            ),
        )

    if authority is not None:
        resolved: dict[str, set[str]] = {
            asset_id: {drug for name in names if (drug := authority(name))}
            for asset_id, names in names_of.items()
        }
        for left, right in combinations(sorted(resolved), 2):
            common = resolved[left] & resolved[right]
            if not common:
                continue
            a, b = by_id[left], by_id[right]
            if not a.company or _company_key(a.company) != _company_key(b.company):
                continue  # MB-102 rule: an authority match across companies is not proposed
            drug = min(common)
            flag_id = _flag_id("PROPOSED_MERGE", [left, right], drug)
            flags[flag_id] = IdentityFlag(
                flag_id=flag_id,
                kind="PROPOSED_MERGE",
                asset_ids=[left, right],
                shared_value=drug,
                relationship=IdentityRelationship.IDENTITY_ALIAS.value,
                basis=(
                    f"The identity authority resolves names of both records to {drug} and "
                    "both name the same company. Proposed only: an analyst must apply it."
                ),
            )
    return list(flags.values())
