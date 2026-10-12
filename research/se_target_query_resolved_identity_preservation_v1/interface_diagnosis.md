# Resolved target identity: failed candidate and interface boundary

Candidate 612c088, preregistration 533c699. This diagnosis does not amend acceptance.

The current `TargetTerm.canonical_id` has two responsibilities: semantic identity
and biological surface form. Most parser outputs serialize approved symbols, even
when those symbols are ambiguous resolver aliases. The resolver itself already
supports exact namespace-qualified identities.

The attempted minimal preservation path is insufficient. It fixes the alias →
display-symbol → ambiguity round-trip but changes a frozen external serialization
and sends internal identifier syntax to other consumers that expect biological
words. A stubbed FDA connector call (no network and no records) demonstrates the
change from `description:"GAX1"` to `description:"TARGET:GAX1"` despite available
biological aliases. This is an I6 isolation failure, independently of the I8 test
failure for `AK/ATPase` returning TARGET:AK6 instead of legacy AK6.

## Consumer inventory from current source

- intent/parser.py: resolved entity -> span reference -> TargetTerm; loses exact
  identity if only a homonymous symbol is serialized.
- intent/compiler.py: copies canonical_id, expands aliases from that string;
  intent_to_trial_query additionally inserts it literally into retrieval terms.
- discovery/query.py: re-resolves that field, builds both literals and target-ID
  metadata; authority seeding also receives the field.
- acquisition/runner.py: passes it unchanged into TargetQuery.
- acquisition/connectors.py: TargetQuery.or_group and multiple connectors use it
  literally; FDA ignores supplied aliases in its target description predicate.
- acquisition/policy.py: compares the raw uppercased field against supported_targets.
- pipeline.py: uses it to build asset-target attribution context.
- gates/evaluator.py: normalizes it before comparisons, already accepts full IDs.
- schemas/contracts.py: deduplicates target expressions by this field.

A discovery-plan-only success cannot establish live-source compatibility.

## Minimum general design to investigate next

Keep biological retrieval/display vocabulary separate from a pinned ontology entity
reference. Existing consumers need an explicit migration inventory, not implicit
reinterpretation of `canonical_id`. A candidate interface should retain legacy
serialized symbols for compatibility and separately carry exact entity identity,
snapshot/version and query-resolution provenance; authority operations must use
that identity, while text searches use only admitted biological aliases. A pair of
unrelated symbol/entity values must fail validation, never silently override one
another. Legacy inputs without a certificate retain their current ambiguity rules.

Preregister a separate interface migration only after enumerating serialization,
source-policy, acquisition, seeding and gate consumers and freezing end-to-end
stubbed source requests. Include ambiguous aliases, mixed equivalent mentions,
wrong identity pairs, missing/mismatched snapshots, legacy round-trips and source
query literals. This is not permission to change the failed candidate or its rules.

No source acquisition, live replay, heldout execution or human-PoC recovery was
performed. Parent target alias milestone stays open; new authority aliases have
not been implemented. H21–H25 and H6–H10 remain unrun.

## Next diagnostic checks (not implementation preregistration)

1. Inventory all consumers of both TargetTerm and TargetQuery, including source
   policy validation and direct trial-query compilation.
2. Freeze stubbed end-to-end requests for existing unambiguous terms and for
   unique aliases whose display symbols collide. No network requests.
3. Compare a separate exact ontology-reference field with a versioned migration of
   canonical_id. Favor additive compatibility if it prevents raw-ID search leakage
   and does not introduce two competing identities.
4. Specify validation of a conflicting display symbol/reference pair and snapshot
   mismatch. Do not use the new reference to override an unresolved bare query.
5. Freeze expectations before any next implementation. The prior candidate stays
   failed; this is a cross-consumer interface investigation, not a score amendment.
