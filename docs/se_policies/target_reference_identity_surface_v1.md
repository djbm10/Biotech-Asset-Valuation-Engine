# TARGET_REFERENCE_IDENTITY_SURFACE v1

Status: PREREGISTERED before production changes. This is a new cross-consumer
interface design, not an amendment or retry-score of failed candidate 612c088.
That candidate remains failed and reverted. Baseline production is 50c9227 /
dea4fdb (identical src/tests/scripts to 533c699).

## Diagnosis and general hypothesis

Frozen synthetic controls demonstrate two separate roles. A unique alias can lose
its entity when the parser stores only a homonymous approved symbol. Replacing
that symbol with an ontology ID repairs lookup but leaks the ID into all six
source connectors and fails source-policy validation. Correct interfaces must
carry exact identity separately from biological retrieval text.

## Deterministic representation and rules

1. Add `TargetReference` with `entity_id` (exact TARGET namespace canonical ID) and
   `ontology_version` (the installed target resolver's exact version token).
   Add optional `target_reference` to TargetTerm and IntentSpan. Omit it from
   serialized legacy objects when absent, using the existing Pydantic-v2 serializer
   interface rather than raising the package's minimum dependency version.
2. A successfully resolved target span receives its actual resolver entity ID and
   version, without changing `resolved_to`, span text, offsets, explanation, rule,
   legacy canonical symbol or label. Non-target/ambiguous/residual spans have no
   reference. Separator demotion clears references. TargetTerm carries the same
   reference. Equivalent mentions deduplicate by certified identity; TargetExpression
   rejects duplicate certified IDs. Existing affix/separator grammar is unchanged.
3. Before a provided reference is used, require an available snapshot, exact version
   match, an exact existing TARGET entity ID, and agreement between the legacy
   canonical_id and that entity's approved symbol or exact qualified ID (casefold
   and surrounding whitespace only). A claimed alias of another entity cannot
   establish this agreement. Invalid/mismatched references fail closed with an
   explicit error; never fall back to re-resolving their display text.
4. Inputs without a reference retain existing ambiguity and unresolved-name
   semantics. Bare homonyms remain ambiguous. No canonical-symbol-precedence rule
   is added to the resolver. Existing explicit qualified IDs may resolve exactly;
   an unknown qualified ID must not be sent as biological query text.
5. Central helpers distinguish ontology lookup ID from biological search surface.
   Alias expansion, authority seeding, pipeline target-attribution context and gate
   normalization use the validated reference when present. Display and source-query
   text use biological symbols/aliases. A known qualified ID in a surface position
   is rendered through its actual entity, never by blindly deleting a prefix.
   A qualified ID for another/unknown entity in that target's retrieval terms is
   rejected. This does not change the biological alias-admission policy.
6. Source-policy validation uses the coherent biological canonical scope already
   declared by the policy. TargetQuery remains a retrieval object: the adapter
   supplies biological text; its boundary rejects internal TARGET IDs in literal
   terms. Individual connector search algorithms, acquisition limits, discovery
   routing, source sets and external calls are unchanged.
7. Existing CompiledQuery target metadata stays compatible; the BuyerProblem retains
   the exact pinned reference. This metadata must not become a literal source term.
   A reference is not evidence that any asset targets it. Existing asset-specific
   authority/prose attribution and all negative target controls remain in force.
8. Bump intent compiler version to `intent_v1__target_reference_v1`. No target aliases,
   ontology records, indication ontology, human-PoC extraction, identity, modality,
   qualification or ranking changes. No live searches/replays or holdout probes.

## Historical certification versus current compatibility

Do not edit any frozen population, expected label, old source hash, acceptance
receipt or historical scorer. The existing indication-v3 tests currently apply
historical source-isolation and serialized-version checks to every future HEAD.
This successor explicitly separates those responsibilities:

- Preserve every historical artifact byte. Verify the original protected-source
  hashes against the archived source from the original implementation commits
  recorded in their acceptance receipts: 894 compilation and 897 gate checks.
  Archives and source provenance are frozen in the diagnosis packet. No generic
  skip, source-hash replacement, or xfail is permitted.
- Replace the two active historical-on-current-HEAD test integrations with clearly
  named historical-certificate checks and current scientific compatibility checks.
  The original scorer files remain unchanged and runnable at their original
  revisions. Do not report the old criteria as passing on a new implementation.
- The 103 current baseline controls must match their complete frozen intent,
  compiled problem, direct trial query, blockers and indication outputs after ONLY
  removing independently validated target_reference fields and normalizing the
  exact new compiler-version component back to its frozen predecessor. No other
  output fields may be ignored. All existing indication gate controls remain exact.
- New milestone source isolation is evaluated separately against its preregistered
  baseline/file scope and preserved as this milestone's result; it does not
  retroactively redefine earlier isolation criteria.

## Frozen population and acceptance (all required)

Packet: `research/target_reference_identity_surface_diagnosis_v1/`.
Controls frozen in dea4fdb before baseline execution. No production change yet.

T1 — All 12 genuine synthetic query controls compile to the intended entity IDs;
      the two frozen refusal/unknown-fragment controls remain non-compilable.
      Legacy symbol/label and target semantics stay unchanged. Mixed equivalent
      names deduplicate; /, × and all seven affixes retain their existing roles.
T2 — Three entities x six connectors match all 18 exact requests in
      surface_request_oracle.json. No network calls. Programmatic qualified IDs and
      parser-produced references reach these same biological requests. No namespace
      metadata is emitted as source-query text.
T3 — All nine synthetic asset/target assertions match the existing exact-ID oracle,
      including CONFIRMED_OTHER_TARGET negatives. Source policy accepts the same
      three actual target entities; no other identity is admitted. Gate target
      comparisons preserve the corresponding exact-ID result.
T4 — Wrong entity/symbol pairs, unknown IDs, non-TARGET IDs, missing snapshots and
      version mismatches fail closed before acquisition. Bare GAX1 without a
      reference remains ambiguous. Contradictory/duplicate reference inputs cannot
      silently change target scope. Direct TargetQuery namespace input is rejected.
T5 — Legacy models without references serialize/round-trip exactly as before.
      Provided references survive intent -> BuyerProblem -> serialization -> reload.
      Non-target spans never retain a reference after separator demotion.
T6 — All 103 current scientific controls match under the exact metadata-only
      projection above. All original frozen artifacts and 1,791 archived historical
      source checks remain unchanged/passing. No historical scorer modification.
T7 — The parent's 4,704 frozen parses preserve target symbols, operator, blockers,
      ambiguity and all pre-existing span fields after the same metadata-only
      projection. All 16 raw resolver controls remain identical. Existing baseline
      affix discrepancy is not repaired. No new alias coverage is claimed.
T8 — Existing FXI diagnostic query compiles offline to the same exact F11 entity
      through plans, source adapter and attribution. Bare F11 remains ambiguous.
      Missing H17/H20 aliases remain missing in this dependency; do not rewrite or
      run those holdouts. This is development evidence, not generalization.
T9 — Identical intent/problem/plan/request outputs under hash seeds 0, 1 and 42.
T10 — All source changes stay within the declared interface scope below; human-PoC,
       global resolver, authority snapshot and scientific gate policies remain
       unchanged. No new decisional fact from co-occurrence or query provenance.
T11 — Full tests/se: every non-xfail test passes. Ruff clean for src/bve/se,
       tests/se and new scripts. Existing xfails remain unchanged.
T12 — H21–H25 and H6–H10 remain unrun/unprobed; no live acquisition or replay;
       failed prior milestones and their evidence remain intact.

## Allowed production scope

src/bve/se/schemas/contracts.py
src/bve/se/intent/intent.py
src/bve/se/intent/parser.py
src/bve/se/intent/compiler.py
src/bve/se/ontology/target_reference.py (new centralized interface)
src/bve/se/discovery/query.py
src/bve/se/acquisition/runner.py
src/bve/se/acquisition/policy.py
src/bve/se/acquisition/connectors.py (TargetQuery boundary only)
src/bve/se/pipeline.py (target-reference handoff only)
src/bve/se/gates/evaluator.py (target-reference lookup only)

New interface/evaluation tests and offline scripts are allowed. Existing tests may
be migrated only for the explicit reference/version interface or the two historical
contract integrations above; preserve their scientific expectations. No old frozen
research artifacts or historical scoring scripts may change. Documentation and
new frozen evidence are permitted.

## Decision and stop rule

Commit this preregistration and all frozen controls/oracles before implementation.
Develop focused tests, then run one formal frozen evaluation plus full tests and
Ruff. If any required criterion fails, record the failure and normally revert the
candidate; do not patch it or revise the rules after formal results. If all pass,
adopt, update the handoff, and resume the separate authority-backed alias milestone.
Stop before implementation if the reference cannot be propagated safely within
this declared interface; do not silently expand scientific or source behavior.
