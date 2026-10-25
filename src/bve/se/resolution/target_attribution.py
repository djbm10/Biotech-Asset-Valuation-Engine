"""Attribute targets to a candidate on the candidate's own evidence.

This is the replacement for query-target inheritance. A discovery run scoped to PDCD1
used to let every asset it returned carry PDCD1, which records what was searched for as
though it were what the asset does. Chemotherapy co-administered in a PDCD1 trial is a
legitimate discovery result; a PDCD1 attribution on that chemotherapy is the error.

What this deliberately does not have access to: the query, the trial, the sponsor, or the
document a candidate was found in. It sees an asset's names and nothing else, so there is
no path by which the context of discovery can influence the attribution.
"""

from __future__ import annotations

import re
from typing import Iterable

from bve.se.ontology.mechanisms import DrugTargetAuthority
from bve.se.ontology.records import EntityType
from bve.se.ontology.resolver import BiomedicalEntityResolver, ResolutionStatus
from bve.se.schemas.contracts import CandidateTargetAssertion, TargetAssertionStatus

#: intervention_identity_v1 N1: exactly a compact development code -- 1-6 letters
#: immediately followed by 2-8 digits, optionally one trailing letter. Nothing else is
#: respelled: no fuzzy matching, no other spelling axis, never a target.
_COMPACT_CODE = re.compile(r"^([A-Za-z]{1,6})(\d{2,8}[A-Za-z]?)$")


def separated_code(name: str) -> str | None:
    """``"XL844"`` -> ``"XL 844"``; ``None`` for anything that is not a compact code."""

    match = _COMPACT_CODE.match(name.strip())
    return f"{match.group(1)} {match.group(2)}" if match else None


class OntologyTargetAttribution:
    """Answer, for each target of interest, what the ontology says about one asset.

    ``requested_target_ids`` are canonical TARGET ids: the targets a run wants an answer
    about. They decide only *which questions are asked*, never what the answers are.
    """

    def __init__(
        self,
        resolver: BiomedicalEntityResolver,
        authority: DrugTargetAuthority,
        requested_target_ids: list[str],
    ) -> None:
        self._resolver = resolver
        self._authority = authority
        self._requested = list(dict.fromkeys(requested_target_ids))

    def _resolve_one(self, name: str) -> str | None:
        result = self._resolver.resolve(name, entity_type=EntityType.DRUG)
        if result.status is ResolutionStatus.RESOLVED:
            return result.canonical_id
        # intervention_identity_v1 N1: a compact development code ("XL844") is retried with
        # one separator ("XL 844"), which the lookup key already equates with "XL-844".
        separated = separated_code(name)
        if separated is None:
            return None
        retry = self._resolver.resolve(separated, entity_type=EntityType.DRUG)
        return retry.canonical_id if retry.status is ResolutionStatus.RESOLVED else None

    def resolve_asset(self, asset_name: str, aliases: list[str]) -> str | None:
        """Find the canonical drug, by exact identifier or alias match only.

        An ambiguous name resolves to nothing. Two molecules sharing a spelling is a
        reason to say nothing about either, not to pick one.
        """

        for candidate in [asset_name, *aliases]:
            if not candidate:
                continue
            resolved = self._resolve_one(candidate)
            if resolved:
                return resolved
        return None

    def resolve_drug(self, name: str) -> str | None:
        """The canonical drug one single name denotes, or ``None``.

        Unlike :meth:`resolve_asset` this asks about one string in isolation, which is what
        deciding whether two names denote the same molecule requires: folding a list of
        names into one answer is exactly how a combination partner's identity gets read as
        the primary's.
        """

        if not name or not name.strip():
            return None
        return self._resolve_one(name)

    def authority_names(self, asset_name: str, aliases: list[str]) -> tuple[str, ...]:
        """The authority's own queryable names for the drug this asset resolves to.

        ``registry_target_lookup_v1.md`` L2: what the registry is asked for comes from the
        authority, never from ``otherNames`` or corpus co-occurrence. Class labels are
        dropped for the reason :meth:`identifies_drug` drops them.
        """

        from bve.se.discovery.class_terms import is_class_term

        canonical_drug = self.resolve_asset(asset_name, aliases)
        if canonical_drug is None:
            return ()
        return tuple(
            name
            for name in self._resolver.aliases_for(canonical_drug, EntityType.DRUG)
            if not is_class_term(name)
        )

    def identifies_drug(self, name: str) -> str | None:
        """The canonical drug *name* identifies strongly enough to merge two assets on.

        Narrower than :meth:`resolve_drug`, which is enough to classify one source's
        ``otherNames``. Merging two separately registered assets needs the authority's own
        identifier names, and a class label is never one: ``CART19`` is filed as a
        tisagenlecleucel development code, but it denotes every CD19 CAR-T.
        """

        # Imported here: discovery sits above resolution, and this is the one question
        # identity needs from it.
        from bve.se.discovery.class_terms import is_class_term

        if not name or not name.strip() or is_class_term(name):
            return None
        found = self._resolver.resolve_identifier(name, entity_type=EntityType.DRUG)
        separated = None if found else separated_code(name)
        return found or (
            self._resolver.resolve_identifier(separated, entity_type=EntityType.DRUG)
            if separated
            else None
        )

    def describes_target_or_class(self, name: str) -> bool:
        """Whether a name denotes a target or mechanism class rather than a drug.

        ``anti-PD-1``, ``PD-L1 inhibitor`` and bare gene symbols appear in ``otherNames``
        as descriptions of what the intervention is, not as other names for it.
        """

        if not name or not name.strip():
            return False
        return (
            self._resolver.resolve(name, entity_type=EntityType.TARGET).status
            is ResolutionStatus.RESOLVED
        )

    def assert_targets(
        self, asset_name: str, aliases: list[str]
    ) -> list[CandidateTargetAssertion]:
        """One assertion per requested target.

        An asset whose identity does not resolve yields ``UNRESOLVED`` for every
        requested target rather than no assertion at all: recording the question as
        unanswered is what keeps it distinguishable from an answered negative.
        """

        if not self._requested:
            return []
        canonical_drug = self.resolve_asset(asset_name, aliases)
        if canonical_drug is None:
            return [
                CandidateTargetAssertion(
                    canonical_target_id=target_id,
                    status=TargetAssertionStatus.UNRESOLVED,
                )
                for target_id in self._requested
            ]
        return [
            self._authority.assert_target(canonical_drug, target_id)
            for target_id in self._requested
        ]


def attribution_for(declared_targets: "Iterable[str]") -> OntologyTargetAttribution | None:
    """Build attribution for the targets a problem declares, or ``None`` without a snapshot.

    Declared targets decide only which questions get asked. A declared target the
    ontology cannot resolve is dropped rather than passed through as a literal: an
    unresolvable target id could never match a canonical edge, so asking about it would
    return ``UNRESOLVED`` for every asset and read as though the authority were silent.
    """

    from bve.se.ontology.targets import get_authority, get_resolver

    resolver = get_resolver()
    authority = get_authority()
    if resolver is None or authority is None:
        return None
    requested = []
    for declared in declared_targets:
        result = resolver.resolve(declared, entity_type=EntityType.TARGET)
        if result.status is ResolutionStatus.RESOLVED:
            requested.append(result.canonical_id)
    if not requested:
        return None
    return OntologyTargetAttribution(resolver, authority, requested)
