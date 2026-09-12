"""In-memory canonical asset registry with provenance-preserving reversible merges."""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Protocol

from bve.se.schemas.contracts import (
    CandidateHit,
    CandidateTargetAssertion,
    CanonicalAsset,
    CompanyRecord,
    IdentityEdge,
    IdentityMention,
    IdentityMerge,
    IdentityRelationship,
    MergeStatus,
    OwnershipRight,
    TargetAssertionStatus,
)

_PUNCTUATION = re.compile(r"[^a-z0-9]+")


def normalize_identity_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _PUNCTUATION.sub(" ", value.casefold()).strip()
    normalized = " ".join(normalized.split())
    # Development codes are commonly rendered as CLN-978, CLN 978, or CLN978.
    # Separator-only differences are deterministic aliases, not distinct assets.
    normalized = re.sub(r"(?<=[a-z]) (?=\d)|(?<=\d) (?=[a-z])", "", normalized)
    return normalized or None


def _id(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha256(value.encode()).hexdigest()[:20]}"


class TargetAttribution(Protocol):
    """The narrow slice of the ontology the registry is allowed to ask about.

    A protocol rather than an import so the registry cannot reach past this question
    into resolution, queries or trial context.
    """

    def assert_targets(self, asset_name: str, aliases: list[str]) -> list[CandidateTargetAssertion]:
        ...


class AssetRegistry:
    """Resolve deterministic identities first and preserve every source mention.

    Probabilistic merges are proposals only. Applying any merge records a complete snapshot of the
    source records so reversal restores the exact prior state.

    ``target_attribution`` is optional and, when absent, the registry records no target
    assertions at all rather than falling back to the targets a hit was found under.
    Falling back is precisely the bug this separation exists to prevent: it would make an
    asset's documented target depend on which query returned it.
    """

    def __init__(self, target_attribution: "TargetAttribution | None" = None) -> None:
        self._target_attribution = target_attribution
        self.assets: dict[str, CanonicalAsset] = {}
        #: normalized alias key -> asset ids holding it. Finding the assets that share a
        #: spelling with an incoming hit used to mean scanning every registered asset and
        #: re-normalizing all of its aliases, once per hit. That is quadratic with string
        #: work in the inner loop: invisible on a few hundred records, ~95 minutes of CPU
        #: on a 2,908-trial corpus. The index answers the same question by lookup.
        self._assets_by_alias_key: dict[str, set[str]] = {}
        #: the keys each asset contributed, so it can be withdrawn exactly on merge/unmerge.
        self._alias_keys_by_asset: dict[str, frozenset[str]] = {}
        self.mentions: dict[str, IdentityMention] = {}
        self.merges: dict[str, IdentityMerge] = {}
        #: Every related name a source offered, classified and recorded whether or not it
        #: was acted on. Ingest-time attachment -- not :meth:`apply_merge` -- is where this
        #: registry actually forms identity, so it is the only place the graph is visible.
        self.identity_edges: list[IdentityEdge] = []
        self.companies: dict[str, CompanyRecord] = {}
        self.rights: dict[str, OwnershipRight] = {}
        self._merge_snapshots: dict[str, dict[str, CanonicalAsset]] = {}

    @staticmethod
    def _alias_keys(record: CanonicalAsset) -> frozenset[str]:
        return frozenset(
            normalized
            for normalized in (
                normalize_identity_name(value)
                for value in [record.canonical_name, *record.aliases]
            )
            if normalized
        )

    def _index_asset(self, record: CanonicalAsset) -> None:
        """Write an asset and keep the alias index in step with it."""

        self._deindex_asset(record.asset_id)
        self.assets[record.asset_id] = record
        keys = self._alias_keys(record)
        self._alias_keys_by_asset[record.asset_id] = keys
        for key in keys:
            self._assets_by_alias_key.setdefault(key, set()).add(record.asset_id)

    def _deindex_asset(self, asset_id: str) -> None:
        """Forget an asset entirely, leaving no key pointing at a gone id."""

        self.assets.pop(asset_id, None)
        for key in self._alias_keys_by_asset.pop(asset_id, frozenset()):
            holders = self._assets_by_alias_key.get(key)
            if holders is None:
                continue
            holders.discard(asset_id)
            if not holders:
                del self._assets_by_alias_key[key]

    def ingest_hit(self, hit: CandidateHit) -> CanonicalAsset:
        normalized_asset = normalize_identity_name(hit.asset_name)
        normalized_company = normalize_identity_name(hit.company_name)
        mention_id = _id("mention", hit.hit_id)
        mention = IdentityMention(
            mention_id=mention_id,
            hit_id=hit.hit_id,
            raw_asset_name=hit.asset_name,
            raw_company_name=hit.company_name,
            raw_trial_id=hit.trial_id,
            normalized_asset_name=normalized_asset,
            normalized_company_name=normalized_company,
            source_document_id=hit.source_document_id,
            observed_at=hit.retrieved_at,
        )
        self.mentions[mention_id] = mention
        company_id: str | None = None
        if normalized_company:
            company_id = _id("company", normalized_company)
            self.companies.setdefault(
                company_id,
                CompanyRecord(
                    company_id=company_id,
                    canonical_name=hit.company_name or normalized_company,
                    aliases=[hit.company_name] if hit.company_name else [],
                ),
            )

        # A source-observed named asset remains the same asset across trials, sponsors, licensors,
        # and owners. Company identity is provenance/rights context, not part of a drug's identity.
        # Exact normalized aliases are deterministic; ambiguous fuzzy merges remain review-only.
        deterministic_key = (
            f"asset:{normalized_asset}"
            if normalized_asset
            else f"trial:{(hit.trial_id or '').upper()}:{hit.provisional_identity_key}"
        )
        alias_keys = {
            normalized
            for normalized in (
                normalize_identity_name(value)
                for value in [hit.asset_name, *hit.aliases]
            )
            if normalized
        }
        # Same set as scanning every asset for a shared normalized spelling: an asset
        # matches exactly when it holds at least one of these keys.
        matching_ids = {
            asset_id
            for key in alias_keys
            for asset_id in self._assets_by_alias_key.get(key, ())
        }
        asset_id = (
            next(iter(matching_ids))
            if len(matching_ids) == 1
            else _id("asset", deterministic_key)
        )
        existing = self.assets.get(asset_id)
        aliases = [value for value in [hit.asset_name, *hit.aliases] if value]
        if existing is None:
            existing = CanonicalAsset(
                asset_id=asset_id,
                canonical_name=hit.asset_name or hit.provisional_identity_key,
                aliases=list(dict.fromkeys(aliases)),
                company_ids=[company_id] if company_id else [],
                trial_ids=[hit.trial_id] if hit.trial_id else [],
                # ``hit.target_terms`` are the targets the *context* named, so they are
                # discovery evidence only. ``target_ids`` is filled from mechanism
                # assertions below, or left empty.
                discovery_target_context=list(dict.fromkeys(hit.target_terms)),
                modality_id=hit.modality_terms[0] if len(hit.modality_terms) == 1 else None,
                mention_ids=[mention_id],
                provisional=not bool(hit.trial_id),
            )
        else:
            existing = existing.model_copy(
                update={
                    "aliases": list(dict.fromkeys([*existing.aliases, *aliases])),
                    "company_ids": list(
                        dict.fromkeys([*existing.company_ids, *([company_id] if company_id else [])])
                    ),
                    "trial_ids": list(
                        dict.fromkeys([*existing.trial_ids, *([hit.trial_id] if hit.trial_id else [])])
                    ),
                    "discovery_target_context": list(
                        dict.fromkeys([*existing.discovery_target_context, *hit.target_terms])
                    ),
                    "modality_id": (
                        existing.modality_id
                        if not hit.modality_terms
                        else hit.modality_terms[0]
                        if existing.modality_id in {None, hit.modality_terms[0]}
                        else None
                    ),
                    "mention_ids": list(dict.fromkeys([*existing.mention_ids, mention_id])),
                    "provisional": existing.provisional and not bool(hit.trial_id),
                }
            )
        existing = self._attribute_targets(existing)
        self._index_asset(existing)
        self._record_identity_edges(hit, existing)
        return existing

    def _record_identity_edges(self, hit: CandidateHit, asset: CanonicalAsset) -> None:
        """Describe, without changing, the relationship this run treated each alias as.

        Shadow-only. Current behaviour merges every related name a source offers, so every
        edge is recorded as ``IDENTITY_ALIAS`` with ``merged=True``: that is the claim the
        run is making, and stating it is what lets a stricter rule be diffed against it.
        """

        primary = hit.asset_name or hit.provisional_identity_key
        for related in hit.aliases:
            if not related or not related.strip():
                continue
            self.identity_edges.append(
                IdentityEdge(
                    edge_id=_id("edge", f"{hit.hit_id}|{primary}|{related}"),
                    asset_id=asset.asset_id,
                    primary_name=primary,
                    related_name=related,
                    relationship=IdentityRelationship.IDENTITY_ALIAS,
                    merged=True,
                    evidence_field=f"{hit.source}.intervention.otherNames",
                    basis="source-offered related name, merged unconditionally",
                    hit_id=hit.hit_id,
                    source_document_id=hit.source_document_id,
                    trial_id=hit.trial_id,
                )
            )

    def _attribute_targets(self, asset: CanonicalAsset) -> CanonicalAsset:
        """Attach mechanism assertions, and derive ``target_ids`` from them alone."""

        if self._target_attribution is None:
            return asset
        assertions = self._target_attribution.assert_targets(
            asset.canonical_name, list(asset.aliases)
        )
        if not assertions:
            return asset
        confirmed = [
            assertion.canonical_target_id
            for assertion in assertions
            if assertion.status is TargetAssertionStatus.CONFIRMED_TARGET
        ]
        return asset.model_copy(
            update={
                "target_assertions": assertions,
                "target_ids": list(dict.fromkeys([*asset.target_ids, *confirmed])),
            }
        )

    def add_right(self, right: OwnershipRight) -> OwnershipRight:
        if right.asset_id not in self.assets:
            raise KeyError(f"unknown asset {right.asset_id!r}")
        if right.company_id not in self.companies:
            raise KeyError(f"unknown company {right.company_id!r}")
        existing = self.rights.get(right.right_id)
        if existing and existing != right:
            raise ValueError("ownership rights are immutable")
        self.rights[right.right_id] = right
        return right

    def rights_as_of(
        self,
        asset_id: str,
        *,
        as_of_date,
        geography: str = "GLOBAL",
        indication: str | None = None,
    ) -> list[OwnershipRight]:
        return [
            right
            for right in self.rights.values()
            if right.asset_id == asset_id
            and right.geography in {"GLOBAL", geography}
            and right.effective_from <= as_of_date
            and (right.effective_to is None or as_of_date <= right.effective_to)
            and (indication is None or right.indication in {None, indication})
        ]

    def propose_merge(
        self,
        source_asset_ids: list[str],
        *,
        target_asset_id: str,
        confidence: float,
        deterministic_basis: str | None = None,
        evidence_claim_ids: list[str] | None = None,
    ) -> IdentityMerge:
        unique_sources = list(dict.fromkeys(source_asset_ids))
        if len(unique_sources) < 2:
            raise ValueError("a merge proposal requires at least two distinct assets")
        missing = [asset_id for asset_id in unique_sources if asset_id not in self.assets]
        if missing:
            raise KeyError(f"unknown source assets: {missing}")
        merge_id = _id("merge", "|".join([*sorted(unique_sources), target_asset_id]))
        proposal = IdentityMerge(
            merge_id=merge_id,
            source_asset_ids=unique_sources,
            target_asset_id=target_asset_id,
            confidence=confidence,
            deterministic_basis=deterministic_basis,
            evidence_claim_ids=evidence_claim_ids or [],
            analyst_review_required=not bool(deterministic_basis),
            created_at=datetime.now(timezone.utc),
        )
        self.merges[merge_id] = proposal
        return proposal

    def apply_merge(self, merge_id: str, *, analyst_approved: bool = False) -> CanonicalAsset:
        merge = self.merges[merge_id]
        if merge.status != MergeStatus.PROPOSED:
            raise ValueError(f"merge {merge_id} is not proposed")
        if merge.analyst_review_required and not analyst_approved:
            raise PermissionError("probabilistic merges require analyst approval")

        snapshot = {asset_id: deepcopy(self.assets[asset_id]) for asset_id in merge.source_asset_ids}
        self._merge_snapshots[merge_id] = snapshot
        records = list(snapshot.values())
        merged = CanonicalAsset(
            asset_id=merge.target_asset_id,
            canonical_name=records[0].canonical_name,
            aliases=list(dict.fromkeys(value for record in records for value in record.aliases)),
            company_ids=list(
                dict.fromkeys(value for record in records for value in record.company_ids)
            ),
            trial_ids=list(dict.fromkeys(value for record in records for value in record.trial_ids)),
            target_ids=list(dict.fromkeys(value for record in records for value in record.target_ids)),
            discovery_target_context=list(
                dict.fromkeys(
                    value for record in records for value in record.discovery_target_context
                )
            ),
            target_assertions=list(
                {
                    (assertion.canonical_target_id, assertion.status): assertion
                    for record in records
                    for assertion in record.target_assertions
                }.values()
            ),
            modality_id=next((record.modality_id for record in records if record.modality_id), None),
            indication_ids=list(
                dict.fromkeys(value for record in records for value in record.indication_ids)
            ),
            development_stage=next(
                (record.development_stage for record in records if record.development_stage), None
            ),
            development_status=next(
                (record.development_status for record in records if record.development_status), None
            ),
            last_confirmed_active_date=max(
                (record.last_confirmed_active_date for record in records if record.last_confirmed_active_date),
                default=None,
            ),
            mention_ids=list(dict.fromkeys(value for record in records for value in record.mention_ids)),
            supporting_claim_ids=list(
                dict.fromkeys(value for record in records for value in record.supporting_claim_ids)
            ),
            provisional=all(record.provisional for record in records),
        )
        for asset_id in merge.source_asset_ids:
            self._deindex_asset(asset_id)
        self._index_asset(merged)
        self.merges[merge_id] = merge.model_copy(
            update={"status": MergeStatus.APPLIED, "applied_at": datetime.now(timezone.utc)}
        )
        return merged

    def reverse_merge(self, merge_id: str) -> None:
        merge = self.merges[merge_id]
        if merge.status != MergeStatus.APPLIED:
            raise ValueError(f"merge {merge_id} is not applied")
        self._deindex_asset(merge.target_asset_id)
        for record in deepcopy(self._merge_snapshots[merge_id]).values():
            self._index_asset(record)
        self.merges[merge_id] = merge.model_copy(
            update={"status": MergeStatus.REVERSED, "reversed_at": datetime.now(timezone.utc)}
        )
