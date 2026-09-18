"""Turn authoritative target->drug edges into things to search for.

Discovery historically searched one vocabulary: the target's own names. That silently
assumes **the target is named in the documents describing its assets**. The assumption
holds for immuno-oncology, where a PD-1 trial says "PD-1", and fails for established
pharmacology: atomoxetine has 223 registered trials and three of them name ``SLC6A2``.
Under a target-only search such an asset is unreachable no matter how good extraction,
identity resolution and gating are.

So discovery gains a second direction. Alongside ``target -> documents -> assets`` it
now also walks ``target -> known assets -> documents``, using the ``DIRECT_TARGET``
edges already present in the pinned snapshot.

**A seed is a place to look, not a finding.** Nothing in this module asserts that a
seeded drug binds the target. It nominates a name to search; the documents that come
back go through acquisition, extraction, identity resolution, target assertion and the
normal gates unchanged. Short-circuiting that -- letting the authority's edge stand in
for the evidence -- would mean the engine reports back the contents of its own reference
data, which is not a discovery result and is not evidence of anything.

That distinction also has to survive into the score, because for any benchmark whose
gold set was cut from these same edges, recovering them proves only that the index can
be read backwards. :class:`SeedProvenance` is what lets a report separate assets found
by independent search from assets the authority handed over.
"""

from __future__ import annotations

from bve.se.ontology.resolver import EntityType
from bve.se.ontology.targets import get_authority, get_resolver

#: How many seeded assets one target may contribute. Seeding multiplies the query plan by
#: the number of known binders, and a well-studied target has hundreds, so an uncapped
#: expansion turns a bounded run into an unbounded one. Truncation is reported rather than
#: silent -- a run that looked at 150 of 400 known binders has a different blind spot from
#: one that looked at all of them.
DEFAULT_MAX_SEEDED_ASSETS = 150


class SeedProvenance:
    """How a query earned its place in the plan.

    Kept as plain string constants on the :class:`CompiledQuery` rather than as an
    inferred property, because after the run there is no way to reconstruct whether a
    document was reached by searching the target or by searching a name the authority
    supplied -- and that is precisely the distinction a generalization claim rests on.
    """

    #: Built from the target's own alias vocabulary. Independent of the drug->target
    #: reference data, so a hit here corroborates that data rather than echoing it.
    TARGET_VOCABULARY = "TARGET_VOCABULARY"
    #: Built from a drug name the drug->target authority associated with the target.
    AUTHORITY_SEEDED_ASSET = "AUTHORITY_SEEDED_ASSET"


def _queryable_drug_names(canonical_drug_id: str) -> list[str]:
    """Searchable spellings for one drug, ambiguous ones removed.

    Uses the same sole-claimant rule as target alias expansion. Drug vocabularies carry
    the same hazard: a development code or a salt-form fragment shared by two molecules
    retrieves both, and afterwards neither the corpus nor the score can say which.
    """

    resolver = get_resolver()
    if resolver is None:
        return []
    entity = resolver.get(canonical_drug_id, EntityType.DRUG)
    if entity is None:
        return []
    names = [
        *( [entity.canonical_symbol] if entity.canonical_symbol else [] ),
        *( [entity.label] if entity.label else [] ),
        *resolver.unambiguous_aliases_for(canonical_drug_id, EntityType.DRUG),
    ]
    # Single characters and bare numbers are alias noise that would match everything.
    return list(dict.fromkeys(name for name in names if name and len(name.strip()) > 2))


def seeded_assets_for_target(
    canonical_target_id: str, *, limit: int = DEFAULT_MAX_SEEDED_ASSETS
) -> tuple[list[tuple[str, list[str]]], int]:
    """``([(canonical_drug_id, searchable_names)], n_known)`` for one target.

    ``n_known`` is the number of binders the authority knows, before the cap, so a caller
    can report how much of the seed set it actually searched.

    Ordered by canonical drug id -- stable across runs, and independent of anything the
    engine observed -- so the cap cannot become a place where a good-looking subset gets
    chosen after the fact.
    """

    authority = get_authority()
    resolver = get_resolver()
    if authority is None or resolver is None:
        return [], 0
    # Edges are keyed by the resolver's canonical id ("TARGET:SLC6A2"), while a buyer
    # problem may legitimately declare the bare approved symbol. Resolving first means a
    # correctly-declared target cannot silently seed nothing.
    entity = resolver.get(canonical_target_id, EntityType.TARGET)
    drug_ids = authority.drugs_for(entity.canonical_id if entity else canonical_target_id)
    seeds: list[tuple[str, list[str]]] = []
    for drug_id in drug_ids:
        names = _queryable_drug_names(drug_id)
        if names:
            seeds.append((drug_id, names))
    return seeds[:limit], len(drug_ids)
