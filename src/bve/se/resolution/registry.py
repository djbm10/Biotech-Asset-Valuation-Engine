"""In-memory canonical asset registry with provenance-preserving reversible merges."""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Callable, Protocol

from bve.se.schemas.contracts import (
    IDENTITY_BEARING_EVIDENCE,
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
    #
    # Bounded to short runs, because unbounded it also welded ordinary words to ordinary
    # numbers. Punctuation above is replaced by a space rather than treated as a boundary,
    # so "Plitidepsin 1.5 mg/day" first became "plitidepsin 1 5 mg day" and the join then
    # produced "plitidepsin1 5mg day" -- destroying the molecule name, and with it any
    # chance for a later layer to strip the dose. A code prefix is short (CLN, BW, MK, R);
    # a molecule or an English word is not, so length separates the two without needing a
    # list of either.
    normalized = re.sub(r"\b([a-z]{1,4}) (?=\d)", r"\1", normalized)
    normalized = re.sub(r"(?<=\d) (?=[a-z]{1,4}\b)", "", normalized)
    return normalized or None


#: A trailing arm/dose qualifier from a closed grammar (``arm_variant_identity_v1`` V1).
_ARM_QUALIFIER = re.compile(
    r"""(?ix)
    (?:^|[\s\-\u2013:,(]+)
    (?:
      (?:dose|dosage)(?:\s*level)?\s*[0-9]{1,2}[a-z]? |
      dl\s*[0-9]{1,2} |
      (?:iv\s+)?(?:high|low|middle|mid|medium|intermediate)[\s-]+dose |
      (?:cohort|arm|group|part)\s+(?:[0-9]{1,2}|[a-h])
    )\s*\)?\s*$"""
)


def arm_variant_base(name: str) -> str | None:
    """The product name before a trailing arm/dose qualifier, or ``None``."""

    match = _ARM_QUALIFIER.search(name)
    if not match:
        return None
    base = name[: match.start()].strip(" -\u2013:,(")
    return base or None


#: A modality token and an antigen designator, nothing else (``ncit_product_identity_v1``
#: P3). No leading zero, so zero-padded sponsor serials (``CAR039``) are not designators.
_GENERIC_DESIGNATOR = re.compile(r"^CAR(?:[\s-]?T)?[\s-]?[1-9]\d{0,2}$", re.IGNORECASE)


def is_generic_designator(name: str) -> bool:
    """Whether a name is a generic construct label such as ``CART19``, not a product."""

    return bool(_GENERIC_DESIGNATOR.match(name.strip()))


def _id(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha256(value.encode()).hexdigest()[:20]}"


class TargetAttribution(Protocol):
    """The narrow slice of the ontology the registry is allowed to ask about.

    A protocol rather than an import so the registry cannot reach past this question
    into resolution, queries or trial context.
    """

    def assert_targets(self, asset_name: str, aliases: list[str]) -> list[CandidateTargetAssertion]:
        ...


class IdentityAuthority(Protocol):
    """The only questions the registry may ask when deciding whether two names match.

    Deliberately not "are these related?" -- a source already asserted relatedness, and
    believing it is the defect. These ask what each name denotes on its own.
    """

    def resolve_drug(self, name: str) -> str | None:
        ...

    def describes_target_or_class(self, name: str) -> bool:
        ...

    def identifies_drug(self, name: str) -> str | None:
        ...


#: Source-declared structure meaning the product co-formulates more than one molecule.
#: Consulted only after synonymy has been ruled out: CT.gov applies this type loosely
#: enough that ("Pembrolizumab", otherNames ["Keytruda"]) carries it, so on its own it
#: says nothing about whether two names denote one molecule.
_COFORMULATED_TYPES = frozenset({"COMBINATION_PRODUCT"})
#: Structured intervention types that state the named thing is a drug. Exact and narrow on
#: purpose: ``COMBINATION_PRODUCT`` is deliberately absent, because it is the type sponsors
#: also give single agents, and ``BIOLOGICAL`` names a class of product, not a molecule.
#: gucy2c_pilot_remediation_v1 C11: CT.gov types cell, gene and vaccine products
#: BIOLOGICAL. Every veto that precedes the structured route (class term, comparator, v6)
#: still applies, which is what keeps "CAR-T cells" out while "LCAR-G08" qualifies.
_STRUCTURED_DRUG_TYPES = frozenset({"DRUG", "BIOLOGICAL"})


class AssetRegistry:
    """Resolve deterministic identities first and preserve every source mention.

    Probabilistic merges are proposals only. Applying any merge records a complete snapshot of the
    source records so reversal restores the exact prior state.

    ``target_attribution`` is optional and, when absent, the registry records no target
    assertions at all rather than falling back to the targets a hit was found under.
    Falling back is precisely the bug this separation exists to prevent: it would make an
    asset's documented target depend on which query returned it.
    """

    def __init__(
        self,
        target_attribution: "TargetAttribution | None" = None,
        identity_authority: "IdentityAuthority | None" = None,
    ) -> None:
        self._target_attribution = target_attribution
        #: Without an authority there is no positive evidence available, so no related
        #: name can be corroborated and none is merged. Fail-closed is the whole point:
        #: the alternative is believing the source, which is what produced B8's false
        #: assertions.
        self._identity_authority = identity_authority
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
        # The same keys the index runs on, published on the record itself. This is the
        # only write path, so an asset cannot reach a caller carrying keys that disagree
        # with the names it was indexed under.
        record.identity_keys = sorted(keys)
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
        # Only corroborated names take part in identity. An uncorroborated related name is
        # still recorded as an edge below, so nothing is lost -- it simply does not get to
        # decide which asset this hit belongs to.
        classifications = self._classify_related_names(hit)
        merged_aliases = [
            related for related, _, merged, _ in classifications if merged
        ]
        alias_keys = {
            normalized
            for normalized in (
                normalize_identity_name(value)
                for value in [hit.asset_name, *merged_aliases]
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
        aliases = [value for value in [hit.asset_name, *merged_aliases] if value]
        # The source's own structured classification of what this intervention is. Only an
        # explicit DRUG or BIOLOGICAL counts: ``COMBINATION_PRODUCT``, ``BEHAVIORAL``, ``OTHER`` and the
        # rest say nothing about whether the string names a molecule. It is recorded, not
        # acted on -- nomination routing reads it, identity does not.
        typed_drug = (hit.intervention_type or "").upper() in _STRUCTURED_DRUG_TYPES
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
                structurally_typed_drug=typed_drug,
                comparator_observations=int(
                    hit.arm_relationship in {"comparator", "specific_comparator"}
                ),
                specific_comparator_observations=int(
                    hit.arm_relationship == "specific_comparator"
                ),
                therapeutic_observations=int(hit.arm_relationship == "therapeutic"),
                unknown_observations=int(hit.arm_relationship == "unknown"),
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
                    # Monotonic: a later untyped observation is weaker evidence, not a
                    # retraction of the typing already seen.
                    "structurally_typed_drug": existing.structurally_typed_drug or typed_drug,
                    # Conjunctive where typing is disjunctive: the flag survives only
                    # while every observation has been a control-arm one.
                    # Additive, not conjunctive. v2 merged one boolean with ``and`` and an
                    # observation that declared nothing thereby retracted 34 that declared a
                    # placebo arm. Counting keeps every observation and defers the verdict.
                    "comparator_observations": existing.comparator_observations
                    + int(hit.arm_relationship in {"comparator", "specific_comparator"}),
                    "specific_comparator_observations": (
                        existing.specific_comparator_observations
                        + int(hit.arm_relationship == "specific_comparator")
                    ),
                    "therapeutic_observations": existing.therapeutic_observations
                    + int(hit.arm_relationship == "therapeutic"),
                    "unknown_observations": existing.unknown_observations
                    + int(hit.arm_relationship == "unknown"),
                }
            )
        existing = self._attribute_targets(existing)
        self._index_asset(existing)
        self._record_identity_edges(hit, existing, classifications)
        return existing

    def _classify_related_names(
        self, hit: CandidateHit
    ) -> list[tuple[str, IdentityRelationship, bool, str]]:
        """Decide what each source-offered name is, and whether it may bear identity.

        ``(related name, relationship, merged, basis)`` per offered name, in source order.

        Identity requires positive evidence that two names denote one molecule, and only
        the ontology can supply it. The asymmetry that matters: a name resolving to a
        *different* drug is a hard veto on molecular synonymy, while a name resolving to
        *nothing* is merely insufficient evidence -- never an approval. Without that second
        half the rule would just move the false merges onto ontology-unknown codes.
        """

        primary = hit.asset_name or hit.provisional_identity_key
        authority = self._identity_authority
        # A new source family may expand discovery; it may not bypass the evidence
        # contract. Claims that are not identity claims are refused before corroboration
        # is even considered, so a pipeline page or press release cannot mint an alias by
        # wording a discovery mention persuasively. Ordered first deliberately: this is a
        # gate on eligibility, not a tie-breaker among rules.
        if hit.alias_evidence_type not in IDENTITY_BEARING_EVIDENCE:
            return [
                (
                    related,
                    IdentityRelationship.UNCERTAIN_RELATIONSHIP,
                    False,
                    f"{hit.alias_evidence_type.value} is not identity evidence, so this"
                    " name is not eligible to become an alias",
                )
                for related in hit.aliases
                if related and related.strip()
            ]
        primary_drug = authority.resolve_drug(primary) if authority else None
        coformulated = (hit.intervention_type or "").upper() in _COFORMULATED_TYPES

        classified: list[tuple[str, IdentityRelationship, bool, str]] = []
        for related in hit.aliases:
            if not related or not related.strip():
                continue
            if authority is None:
                classified.append(
                    (
                        related,
                        IdentityRelationship.UNCERTAIN_RELATIONSHIP,
                        False,
                        "no identity authority available, so no corroboration is possible",
                    )
                )
                continue
            related_drug = authority.resolve_drug(related)
            if primary_drug and related_drug and primary_drug == related_drug:
                classified.append(
                    (
                        related,
                        IdentityRelationship.IDENTITY_ALIAS,
                        True,
                        f"both names resolve to the same canonical drug {primary_drug}",
                    )
                )
            elif primary_drug and related_drug:
                # Checked only here: the declared product structure can say two molecules
                # share a product, but it can never make them one molecule, so the
                # canonical ids stay distinct either way and this only chooses the label.
                relationship = (
                    IdentityRelationship.COFORMULATED_COMPONENT
                    if coformulated
                    else IdentityRelationship.COMBINATION_PARTNER
                )
                classified.append(
                    (
                        related,
                        relationship,
                        False,
                        f"resolves to {related_drug}, a different drug from {primary_drug}"
                        + (
                            "; source declares a co-formulated product, so the relationship"
                            " is product-level and not molecular synonymy"
                            if coformulated
                            else ""
                        ),
                    )
                )
            elif authority.describes_target_or_class(related):
                classified.append(
                    (
                        related,
                        IdentityRelationship.UNCERTAIN_RELATIONSHIP,
                        False,
                        "names a target or mechanism class, which describes an"
                        " intervention rather than naming it",
                    )
                )
            elif related_drug and not primary_drug:
                classified.append(
                    (
                        related,
                        IdentityRelationship.UNCERTAIN_RELATIONSHIP,
                        False,
                        f"resolves to {related_drug} while the intervention name does not"
                        " resolve, so there is no evidence they are the same molecule",
                    )
                )
            else:
                classified.append(
                    (
                        related,
                        IdentityRelationship.UNCERTAIN_RELATIONSHIP,
                        False,
                        "does not resolve to any known drug; absence of a contradicting"
                        " authority is not positive identity evidence",
                    )
                )
        return classified

    def _record_identity_edges(
        self,
        hit: CandidateHit,
        asset: CanonicalAsset,
        classifications: list[tuple[str, IdentityRelationship, bool, str]],
    ) -> None:
        """Record every offered name and its disposition, acted on or not.

        Edges are emitted for rejected names too. That is what makes a removed merge
        auditable: the original evidence field, trial and intervention survive alongside
        the new classification instead of the merge simply disappearing.
        """

        primary = hit.asset_name or hit.provisional_identity_key
        for related, relationship, merged, basis in classifications:
            self.identity_edges.append(
                IdentityEdge(
                    edge_id=_id("edge", f"{hit.hit_id}|{primary}|{related}"),
                    asset_id=asset.asset_id,
                    primary_name=primary,
                    related_name=related,
                    relationship=relationship,
                    merged=merged,
                    evidence_field=f"{hit.source}.intervention.otherNames",
                    basis=basis,
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
            structurally_typed_drug=any(
                record.structurally_typed_drug for record in records
            ),
            comparator_observations=sum(record.comparator_observations for record in records),
            specific_comparator_observations=sum(
                record.specific_comparator_observations for record in records
            ),
            therapeutic_observations=sum(record.therapeutic_observations for record in records),
            unknown_observations=sum(record.unknown_observations for record in records),
        )
        for asset_id in merge.source_asset_ids:
            self._deindex_asset(asset_id)
        self._index_asset(merged)
        self.merges[merge_id] = merge.model_copy(
            update={"status": MergeStatus.APPLIED, "applied_at": datetime.now(timezone.utc)}
        )
        return merged

    def consolidate_by_authority(self) -> dict[str, str]:
        """Merge separately registered assets whose names identify one drug.

        Ingest only ever unites names a source offered together. Two assets that never
        co-occur -- ``KTE-C19`` in one trial, ``axicabtagene ciloleucel`` in another --
        stay apart although the authority files one as the other's development code. This
        pass unites them, on the authority's identifier names alone
        (``authority_identity_merge_v1.md``), through the ordinary reversible merge.

        Returns ``{absorbed asset id: surviving asset id}`` so callers holding asset ids
        can follow the merge.
        """

        authority = self._identity_authority
        if authority is None:
            return {}
        by_drug: dict[str, list[str]] = {}
        approved: dict[str, str] = {}
        for asset_id, asset in sorted(self.assets.items()):
            drugs = {
                drug
                for drug in (
                    authority.identifies_drug(name)
                    for name in [asset.canonical_name, *asset.aliases]
                )
                if drug
            }
            # An asset that identifies two drugs is itself a conflict; merging it would
            # choose between them.
            if len(drugs) != 1:
                continue
            drug = next(iter(drugs))
            by_drug.setdefault(drug, []).append(asset_id)
            if normalize_identity_name(asset.canonical_name) == normalize_identity_name(
                drug.split(":", 1)[-1]
            ):
                approved.setdefault(drug, asset_id)
        redirects: dict[str, str] = {}
        for drug, members in sorted(by_drug.items()):
            if len(members) < 2:
                continue
            survivor = approved.get(drug, members[0])
            ordered = [survivor, *(member for member in members if member != survivor)]
            proposal = self.propose_merge(
                ordered,
                target_asset_id=survivor,
                confidence=1.0,
                deterministic_basis=f"authority_drug:{drug}",
            )
            self.apply_merge(proposal.merge_id)
            for member in ordered[1:]:
                redirects[member] = survivor
        return redirects

    def consolidate_arm_variants(self) -> dict[str, str]:
        """Merge dose, arm and cohort variants of one product (``arm_variant_identity_v1``).

        "X Dose 1" and "X Dose 2" are one product only when one registry record lists both:
        a shared trial id is required, never textual similarity alone, and targets are not
        consulted. Every member's name stays as an alias of the merged asset.
        """

        groups: dict[str, list[str]] = {}
        for asset_id, asset in sorted(self.assets.items()):
            base = arm_variant_base(asset.canonical_name)
            if base:
                groups.setdefault(base.casefold(), []).append(asset_id)
        redirects: dict[str, str] = {}
        for base, members in sorted(groups.items()):
            if len(members) < 2:
                continue
            shared = set.intersection(*(set(self.assets[m].trial_ids) for m in members))
            if not shared:
                continue
            ordered = sorted(
                members, key=lambda m: (self.assets[m].canonical_name.casefold(), m)
            )
            survivor = ordered[0]
            proposal = self.propose_merge(
                ordered,
                target_asset_id=survivor,
                confidence=1.0,
                deterministic_basis=f"arm_variant:{base}:{','.join(sorted(shared))}",
            )
            self.apply_merge(proposal.merge_id)
            for member in ordered[1:]:
                redirects[member] = survivor
        return redirects

    def consolidate_by_ncit_product(
        self, ncit_code_of: Callable[[CanonicalAsset], str | None]
    ) -> dict[str, str]:
        """Merge assets unambiguously linked to one NCIt product concept.

        ``ncit_product_identity_v1.md``. ``ncit_code_of`` is the adopted unambiguous link;
        an asset whose own names are all generic designators (``CART19``) takes no part,
        because NCIt filing a construct label under one product does not make every
        registry entry so named that product. It keeps its link and its own trials.
        """

        groups: dict[str, list[str]] = {}
        for asset_id, asset in sorted(self.assets.items()):
            names = [asset.canonical_name, *asset.aliases]
            if all(is_generic_designator(name) for name in names if name):
                continue
            code = ncit_code_of(asset)
            if code:
                groups.setdefault(code, []).append(asset_id)
        redirects: dict[str, str] = {}
        for code, members in sorted(groups.items()):
            if len(members) < 2:
                continue
            ordered = sorted(
                members, key=lambda m: (self.assets[m].canonical_name.casefold(), m)
            )
            survivor = ordered[0]
            proposal = self.propose_merge(
                ordered,
                target_asset_id=survivor,
                confidence=1.0,
                deterministic_basis=f"ncit_product:{code}",
            )
            self.apply_merge(proposal.merge_id)
            for member in ordered[1:]:
                redirects[member] = survivor
        return redirects

    def reattribute_trial(self, trial_id: str, from_asset_id: str, to_asset_id: str) -> None:
        """Move one trial between two assets (``protocol_id_trial_attribution_v1``).

        Neither asset is merged, created or deleted; a source left with no trials stays.
        One trial can sit on several source assets (an intervention name and a title-minted
        name), so a destination that already received it from another source keeps one copy.
        """

        source, destination = self.assets[from_asset_id], self.assets[to_asset_id]
        if trial_id not in source.trial_ids or from_asset_id == to_asset_id:
            raise ValueError(f"cannot move {trial_id} from {from_asset_id} to {to_asset_id}")
        self._index_asset(
            source.model_copy(update={"trial_ids": [t for t in source.trial_ids if t != trial_id]})
        )
        if trial_id not in destination.trial_ids:
            self._index_asset(
                destination.model_copy(update={"trial_ids": [*destination.trial_ids, trial_id]})
            )

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
