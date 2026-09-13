"""Decide whether a *shared* alias is safe to use as a search term for one target.

An alias that two genes both claim is not thereby useless. ``PD-1`` is shared with
``RPL17`` and is still the name almost every PDCD1 document uses; ``NET`` is shared with
``ELK3`` and ``EPHB1`` and, in the trial registry, overwhelmingly means *neutrophil
extracellular trap*. Refusing both costs PDCD1 its dominant vocabulary. Admitting both
replaces the SLC6A2 corpus with someone else's literature. The snapshot cannot tell them
apart -- both are ``SYNONYM`` from the same sources for every claimant -- so the
distinction has to be measured rather than declared.

This module measures it, under a policy frozen before any probe was executed
(``m14_alias_admission_policy_v1.json``, sha256 ``9a8572d5...``).

Three boundaries define what this is:

* It is a **retrieval** decision, not an ontology or identity one. No alias is removed
  from any entity. ``PD-1`` remains a synonym of both PDCD1 and RPL17 for recognition,
  normalization and display. The only question here is what goes into a search box.
* It is **claimant-relative**. The question is never "does this alias co-occur with my
  target?" -- that admits any alias whose target merely appears somewhere. It is "among
  every entity claiming this string, which one does the retrieved corpus support?"
* It **never asserts biology**. Like the D2 seeds, admission licenses looking; whether a
  resulting asset actually binds the target is still decided downstream by
  ``CandidateTargetAssertion`` on its own evidence.

It fails closed. A probe that errors, returns nothing, or cannot run leaves the alias
out of the search, because a measurement that did not happen is not evidence of
dominance.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from functools import lru_cache

from bve.se.discovery.seeding import seeded_assets_for_target
from bve.se.ontology.resolver import EntityType
from bve.se.ontology.targets import get_resolver, unambiguous_target_aliases

POLICY_ID = "retrieval_alias_admission_v1"

#: Frozen 2026-09-13 before any probe ran, and before any calibration set existed. See
#: the policy artifact for the asymmetry argument: wrongly refusing an alias narrows
#: recall visibly, wrongly admitting one yields a corpus about a different gene that
#: looks like a normal result.
MIN_SUPPORTED_DOCS = 5
MIN_TARGET_SHARE = 0.80
MIN_RATIO_OVER_NEXT_BEST = 4.0
MAX_PROBE_DOCUMENTS = 200


class Decision:
    ACTIVE_SOLE_CLAIMANT = "ACTIVE_SOLE_CLAIMANT"
    ACTIVE_PROBE_ADMITTED = "ACTIVE_PROBE_ADMITTED"
    RETRIEVAL_AMBIGUOUS = "RETRIEVAL_AMBIGUOUS"
    PROBE_UNAVAILABLE = "PROBE_UNAVAILABLE"


@dataclass
class ProbeRecord:
    """Everything needed to re-derive one admission decision.

    The search plan is now adaptive -- which terms it issues depends on what a probe
    measured -- so the plan is reproducible only if the measurement is stored with it.
    """

    alias: str
    target_id: str
    all_claimants: list[str]
    probe_query: str
    as_of_date: str
    source: str
    source_release: str | None
    document_hashes: list[str]
    anchor_sets: dict[str, list[str]]
    support_counts: dict[str, int]
    documents_supporting_any_claimant: int
    decision: str
    reason: str
    policy_id: str = POLICY_ID
    thresholds: dict = field(
        default_factory=lambda: {
            "min_claimant_supported_docs_for_target": MIN_SUPPORTED_DOCS,
            "min_target_share_of_claimant_supported_docs": MIN_TARGET_SHARE,
            "min_ratio_over_next_best_claimant": MIN_RATIO_OVER_NEXT_BEST,
        }
    )

    @property
    def admitted(self) -> bool:
        return self.decision in {Decision.ACTIVE_SOLE_CLAIMANT, Decision.ACTIVE_PROBE_ADMITTED}


class AdmissionRegistry:
    """Per-run record of which shared aliases were admitted for which target.

    A probe is a live measurement, so it is made once per (alias, target) per run and
    reused. Without this the vocabulary layer -- which is consulted for every query and
    every document label -- would re-probe continuously, and worse, could reach different
    conclusions within a single run and make the plan unreproducible.

    Defaults to refusing shared aliases. A run that never installs a probe therefore
    behaves exactly like the sole-claimant rule, which is the intended fail-closed state
    rather than a degraded one.
    """

    def __init__(self) -> None:
        self._decisions: dict[tuple[str, str], ProbeRecord] = {}

    def record(self, probe: ProbeRecord) -> None:
        self._decisions[(probe.alias.casefold(), probe.target_id)] = probe

    def admitted_aliases(self, canonical_id: str) -> tuple[str, ...]:
        return tuple(
            probe.alias
            for (_alias, target), probe in sorted(self._decisions.items())
            if target == canonical_id and probe.admitted
        )

    def probes(self) -> list[ProbeRecord]:
        return [probe for _key, probe in sorted(self._decisions.items())]


#: The registry consulted by the retrieval vocabulary. Module-level because the
#: vocabulary layer is reached through call paths that do not thread a run context, and a
#: retrieval-admission decision is a property of the run rather than of any one query.
_ACTIVE = AdmissionRegistry()


def active_registry() -> AdmissionRegistry:
    return _ACTIVE


def install_registry(registry: AdmissionRegistry) -> AdmissionRegistry:
    """Replace the active registry, returning the previous one so callers can restore it."""

    global _ACTIVE
    previous, _ACTIVE = _ACTIVE, registry
    return previous


def admitted_shared_aliases(canonical_id: str) -> tuple[str, ...]:
    """Shared aliases a probe has admitted for this target in the current run; ``()`` if none."""

    return _ACTIVE.admitted_aliases(canonical_id)


def searchable_target_aliases(canonical_id: str) -> tuple[str, ...]:
    """The vocabulary this target may actually be searched with.

    Every alias no other entity claims, plus every shared alias a probe admitted under
    the frozen policy. This is the single seam retrieval should use; ``target_aliases``
    remains the right answer for *recognising* a name in text, where a shared alias is
    informative and the surrounding evidence disambiguates it.
    """

    resolver = get_resolver()
    entity = resolver.get(canonical_id, EntityType.TARGET) if resolver else None
    resolved = entity.canonical_id if entity else canonical_id
    return tuple(
        dict.fromkeys(
            [*unambiguous_target_aliases(canonical_id), *admitted_shared_aliases(resolved)]
        )
    )


def probe_and_admit(
    canonical_ids: list[str],
    fetcher,
    *,
    as_of_date: str,
    source: str,
    source_release: str | None = None,
    registry: AdmissionRegistry | None = None,
) -> AdmissionRegistry:
    """Probe every shared alias of every declared target, once, before a run begins.

    ``fetcher(alias)`` returns ``[(record_id, text)]`` or ``None``. Kept as a parameter so
    this is testable offline and reusable for whichever source a deployment probes
    against; the policy fixes the *rule*, not the transport.

    Only shared aliases are probed -- a sole-claimant alias is already active and costs
    nothing to confirm.
    """

    resolver = get_resolver()
    registry = registry if registry is not None else AdmissionRegistry()
    if resolver is None:
        return registry
    for canonical_id in canonical_ids:
        entity = resolver.get(canonical_id, EntityType.TARGET)
        if entity is None:
            continue
        for alias in entity.queryable_aliases():
            if len(resolver.claimants_of(alias, EntityType.TARGET)) <= 1:
                continue
            registry.record(
                evaluate(
                    alias,
                    canonical_id,
                    documents=fetcher(alias),
                    as_of_date=as_of_date,
                    source=source,
                    source_release=source_release,
                )
            )
    return registry


def anchors_for(canonical_id: str, *, competing_aliases: set[str]) -> list[str]:
    """Terms that identify one claimant *without* relying on any contested string.

    Built from the claimant's canonical symbol, its sole-claimant aliases, and the drug
    names the DIRECT_TARGET authority associates with it. The probed alias is excluded,
    and so is any alias a competing claimant also owns -- an ambiguous anchor cannot
    adjudicate ambiguity, it just launders it.
    """

    resolver = get_resolver()
    if resolver is None:
        return []
    entity = resolver.get(canonical_id, EntityType.TARGET)
    if entity is None:
        return []
    terms: list[str] = []
    if entity.canonical_symbol:
        terms.append(entity.canonical_symbol)
    terms.extend(unambiguous_target_aliases(canonical_id))
    seeds, _ = seeded_assets_for_target(canonical_id)
    for _drug_id, names in seeds:
        terms.extend(names)
    contested = {value.casefold() for value in competing_aliases}
    deduped: dict[str, None] = {}
    for term in terms:
        folded = term.casefold()
        if folded in contested or len(folded.strip()) < MIN_ANCHOR_LENGTH:
            continue
        deduped.setdefault(term, None)
    return list(deduped)


#: Anchors shorter than this are dropped. A three-character drug code carries almost no
#: evidence on its own and is disproportionately likely to collide with an ordinary word
#: or an unrelated acronym, so the support it contributes is mostly noise.
MIN_ANCHOR_LENGTH = 4


@lru_cache(maxsize=4096)
def _anchor_pattern(anchor: str) -> re.Pattern[str]:
    return re.compile(r"(?<![0-9a-z])" + re.escape(anchor.casefold()) + r"(?![0-9a-z])")


def _support(text: str, anchors: list[str]) -> bool:
    """Does this document mention any of the claimant's anchors *as a term*?

    Word-bounded, not substring. Plain ``in`` matching made the probe unusable: the drug
    anchor ``Ganda`` matched "Uganda" and ``DMI`` matched "admission", which between them
    manufactured 41 of 41 supporting documents for SLC6A2 in a sample that was actually
    about cytomegalovirus and HIV. An instrument that finds support in unrelated text
    cannot adjudicate anything.

    The boundary is alphanumeric rather than ``\\b`` so that codes ending in punctuation
    -- ``PD-1``, ``CL 67,772`` -- still anchor on their own terms.
    """

    lowered = text.casefold()
    return any(_anchor_pattern(anchor).search(lowered) for anchor in anchors)


def evaluate(
    alias: str,
    target_id: str,
    *,
    documents: list[tuple[str, str]] | None,
    as_of_date: str,
    source: str,
    source_release: str | None = None,
) -> ProbeRecord:
    """Admit or refuse ``alias`` as a search term for ``target_id``.

    ``documents`` is ``[(record_id, text)]`` retrieved by searching the bare alias, or
    ``None`` when the probe could not be run. Retrieval is the caller's job so this stays
    testable without a network and reusable across sources.
    """

    resolver = get_resolver()
    claimants = list(resolver.claimants_of(alias, EntityType.TARGET)) if resolver else []
    entity = resolver.get(target_id, EntityType.TARGET) if resolver else None
    resolved_target = entity.canonical_id if entity else target_id

    def record(decision: str, reason: str, **kwargs) -> ProbeRecord:
        base = dict(
            alias=alias,
            target_id=resolved_target,
            all_claimants=claimants,
            probe_query=alias,
            as_of_date=as_of_date,
            source=source,
            source_release=source_release,
            document_hashes=[],
            anchor_sets={},
            support_counts={},
            documents_supporting_any_claimant=0,
            decision=decision,
            reason=reason,
        )
        base.update(kwargs)
        return ProbeRecord(**base)

    if len(claimants) <= 1:
        return record(
            Decision.ACTIVE_SOLE_CLAIMANT,
            "no competing claimant in this snapshot, so the string cannot redirect the search",
        )
    if documents is None:
        return record(
            Decision.PROBE_UNAVAILABLE,
            "probe did not run; failing closed to sole-claimant behaviour",
        )

    sample = documents[:MAX_PROBE_DOCUMENTS]
    anchor_sets: dict[str, list[str]] = {}
    for claimant in claimants:
        others: set[str] = set()
        for other in claimants:
            if other == claimant:
                continue
            other_entity = resolver.get(other, EntityType.TARGET) if resolver else None
            if other_entity:
                others.update(a.value for a in other_entity.aliases)
        anchor_sets[claimant] = anchors_for(claimant, competing_aliases={alias, *others})

    support = {claimant: 0 for claimant in claimants}
    supported_any = 0
    hashes: list[str] = []
    for record_id, text in sample:
        hashes.append(hashlib.sha256(f"{record_id}\x1f{text}".encode()).hexdigest()[:16])
        hit = False
        for claimant, anchors in anchor_sets.items():
            if anchors and _support(text, anchors):
                support[claimant] += 1
                hit = True
        if hit:
            supported_any += 1

    mine = support.get(resolved_target, 0)
    rivals = [count for claimant, count in support.items() if claimant != resolved_target]
    next_best = max(rivals) if rivals else 0
    share = (mine / supported_any) if supported_any else 0.0
    ratio = (mine / next_best) if next_best else float("inf")

    common = dict(
        document_hashes=hashes,
        anchor_sets={k: v[:50] for k, v in anchor_sets.items()},
        support_counts=support,
        documents_supporting_any_claimant=supported_any,
    )

    if mine < MIN_SUPPORTED_DOCS:
        return record(
            Decision.RETRIEVAL_AMBIGUOUS,
            f"only {mine} probe documents support {resolved_target} "
            f"(policy requires {MIN_SUPPORTED_DOCS})",
            **common,
        )
    if share < MIN_TARGET_SHARE:
        return record(
            Decision.RETRIEVAL_AMBIGUOUS,
            f"{resolved_target} holds {share:.0%} of claimant-supported documents "
            f"(policy requires {MIN_TARGET_SHARE:.0%})",
            **common,
        )
    if ratio < MIN_RATIO_OVER_NEXT_BEST:
        return record(
            Decision.RETRIEVAL_AMBIGUOUS,
            f"{resolved_target} leads the next claimant by {ratio:.1f}x "
            f"(policy requires {MIN_RATIO_OVER_NEXT_BEST}x)",
            **common,
        )
    return record(
        Decision.ACTIVE_PROBE_ADMITTED,
        f"{resolved_target} holds {share:.0%} of claimant-supported documents "
        f"and leads the next claimant by {ratio:.1f}x",
        **common,
    )
