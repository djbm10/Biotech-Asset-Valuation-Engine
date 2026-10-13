# AUTHORITY_LOOKUP_SOURCE_COMPONENT_PROVENANCE_DIAGNOSIS v1

## Decision: boundary B — original upstream lineage needs a schema extension

Baseline `cc609b1`; frozen population commit `5aa8fdd`. Diagnosis only. No production,
identity, parser, source, or snapshot change. No implementation preregistration is
opened: a snapshot-field locator is feasible, but must not be represented as an exact
original upstream label/component locator. No target-mention retry is authorized by
this artifact.

## Population and evidence

`research/se_authority_lookup_source_component_provenance_diagnosis_v1/` contains
124 frozen observations: all 77 previous failures and 47 controls. Eight structural
categories contribute five lexicographically selected raw values each: canonical
symbol, canonical name, synonym, Greek, spelled form, overlapping authorities,
component collision, multiple assertions. Seven explicit existing-lookup controls
include CD19 and its common name, MRCK, E2, CAR, an absent name, and empty input.
These cover multiple aliases for one identity, ambiguity and unresolved lookup.
No aliases were added. `population.json` and `freeze.json` were committed before
contract derivation. `audit.json` contains every observation, exact input and span,
normalized key, current resolution/basis, every matching raw snapshot assertion,
field locator, all source components and full source records for each matched ID.
`audit.md` is the readable index. No holdout data was read.

There are 60 RESOLVED, 62 AMBIGUOUS and two UNRESOLVED observations. All 77 prior
failed observations have matching snapshot assertions. All 443 assertion locators
round-trip to the original stored value. All 124 query/surface offsets round-trip;
each of the 77 historical surfaces has exactly one occurrence in its query.
Snapshot records SHA256:
`986fa262e3c275424968996b78703614563304cf22f5e2a2f1d3c39e0fc6f50b`.

## Trace and failure classification

1. `sources/chembl.py:parse_chembl_target` flattens target-component synonyms into a
   record-wide alias list. `_clean_synonyms` strips field prefixes, splits semicolon
   values and strips whitespace. `add` deduplicates normalized value/type pairs.
   Original component accession-to-alias ownership, synonym ordinal, raw spelling,
   prefix and originating field are not retained in SourceEntityRecord.
2. `sources/open_targets.py:_synonym_labels` extracts strings from several fields;
   `parse_open_targets_target` merges these into aliases. `add` normalizes and
   deduplicates. Original synonym collection/ordinal and discarded spellings are
   not retained. Snapshot source manifests give release-level locators, not those
   missing per-assertion paths. This is D, source-loader provenance loss, with C,
   synonym collapse. Upstream originals cannot be uniquely reconstructed from
   the snapshot: these transformations are many-to-one.
3. `records.py:SourceAlias.strip_value` collapses whitespace. `all_aliases` converts
   raw symbol/label into SourceAlias and deduplicates normalized value/type. The
   raw `label` field remains intact in the snapshot and SourceEntityRecord, so
   the 35 `gene` observations are recoverable. Their 70 assertions refer to two
   raw labels ` gene`. This is A plus E, not proof of a distinct-label collision.
4. `resolver.py:_build_entity` collapses same-key/type assertions across records;
   it retains record keys, but not each raw spelling/field. This is C/E where
   applicable. The audit lists all assertions rather than electing one spelling.
5. `_canonical_id` uses a symbol, whereas `_group_records` groups cross-reference
   components. `_build` stores entities by canonical ID (last writer wins) while
   `_by_type` retains components; `_index` stores only alias type/canonical ID.
   MRCK and E2 account for 42 prior failures. TARGET:CDC42BPA has two components;
   TARGET:SNORA62 has seven. These are B/E. The original index hit's component
   cannot be recovered from the tuple itself. All matching components can still
   be reconstructed from snapshot records and retained component groups.
6. `_resolved` reconstructs basis from the entity retrieved by canonical ID; its
   direct-ID fallback may have no asserting records even for an alias lookup.
   This is lookup API return-shape loss E, not evidence of a real direct-ID match.
7. No downstream serialization-only loss F was demonstrated. Per-row category G
   means multiple observed boundaries; it is not a new biological diagnosis.

The phrase “source component” has two distinct meanings: a resolver cross-reference
component and an upstream ChEMBL target component. The former is reconstructible
from current snapshot grouping; the latter's alias ownership is not. They must have
different fields. None of these findings authorizes joining their identities.

## Deterministic provenance contract

Keep the existing ResolutionResult and all its decisions unchanged. A future additive
lookup envelope would carry `legacy_resolution` plus an ordered assertion ledger;
callers may ignore the ledger. Do not retrofit the legacy basis by silently substituting
an alternate entity or canonical label.

Each assertion carries:

- exact lookup input and optional original query/span, with a surface round-trip;
- normalized match key and named/versioned normalization operations;
- exact raw field text, field kind and loaded/normalized forms separately;
- snapshot content digest, file, one-based JSONL line, source/source_id, and field
  pointer (`label`, `canonical_symbol`, or alias ordinal/value);
- resolver component key: digest of sorted source-record keys, namespaced by the
  snapshot digest; canonical target ID is a separate, non-unique attribute;
- source release and retained source provenance, match type, collision membership;
- upstream locator/raw assertion/component fields, only if actually retained;
  otherwise explicit `UPSTREAM_LINEAGE_UNAVAILABLE`, never invented values.

Enumerate assertions before alias deduplication. Preserve multiple raw assertions
sharing one match key, source record, or canonical ID. Sort by snapshot/line/field/
component key/type; never use set iteration to choose display spellings. Match-key
normalization controls matching only. Assertion identity is its content-addressed
field locator. Component-key equality is snapshot-local provenance, not biological
equivalence. All colliding canonical IDs retain all component keys.

Separate `matching_assertions`, `legacy_selected_id`, and `legacy_returned_component`.
A resolved canonical ID can have several matching components and a different returned
component; preserve that fact rather than choosing a causal source after the fact.
Alias precedence, non-queryable/fragment-only status and direct canonical-ID lookup
must be explicitly distinguishable. A direct-ID match is a resolver-generated key,
not a fabricated source label. Unresolved names retain input and reason with an empty
match ledger (or separately identified ineligible assertions). Ambiguous lookups retain
all claimants and all matching assertions, without becoming a resolved target.

Raw matching assertions alone do not certify query role, target identity equivalence,
or therapeutic relevance. Production decisions are an observation, not an assertion
that every matching source supports the selected identity.

## Answers to the five architecture questions

1. Every resolution can retain exact **snapshot-field** provenance. Exact original
   upstream alias spelling cannot always be retained from this snapshot: no.
2. Distinct resolver components sharing an ID can remain distinguishable: yes,
   with a separate component key and assertion ledger. Upstream component ownership
   needs retained upstream assertion paths.
3. Normalization can be deterministic while preserving lineage: yes prospectively;
   discarded pre-snapshot distinctions cannot be recreated retrospectively.
4. Callers can ignore additive provenance and retain today's behavior: yes by design;
   a future implementation must prove this over all 6,199 frozen decisions, not infer
   neutrality from this diagnostic script.
5. Stable snapshot record/field locators exist using file digest + line + field.
   Stable original upstream assertion/component locators do not exist in the current
   record schema. A record ID or release URL alone does not identify an alias field.

## Minimum architectural extension

Retain a source-assertion sidecar at ingestion, before cleanup/deduplication. Each row
must identify the captured upstream artifact by digest, upstream record ID and exact
field/array path, raw value, source component/accession where present, transformations,
and resulting snapshot record/alias associations. Keep every origin when several
assertions normalize into one alias. A raw payload content reference plus deterministic
field pointers is sufficient; copying entire payloads into every lookup is unnecessary.
The source manifest must bind the sidecar and payload content digests. Existing snapshots
must honestly mark absent lineage; do not silently backfill by guesswork.

Then a separately preregistered lookup-ledger implementation can index source assertion
locators and resolver component keys in parallel with the unchanged legacy lookup.
It must satisfy P1–P9 from the user: all 77 exact provenances, all 6,199 decisions,
determinism, no snapshot mutation, full tests/se and Ruff. Original upstream lineage
requires its own snapshot/schema milestone first; this diagnosis neither regenerates
snapshots nor preregisters a misleading “complete provenance” implementation.

## Limits and stop

Existing staging paths were observed to exist, but upstream data was not imported or
used to reconstruct missing lineage: the frozen population uses only existing target
snapshots. A later lineage milestone may evaluate captured raw artifacts under an
explicit scope. Historical snapshot raw fields remain auditable now. This finding does
not invalidate all authority identities or justify changing existing decisions.

Stop at B. No production tests were rerun because production code/tests are unchanged;
offline field/offset validation and diagnostic-script Ruff are recorded separately.
Human-PoC remains stopped. H21–H25 untouched; H6–H10 unrun. No alias, Greek, role,
identity graph, indication, qualification, ranking, or source acquisition changes.
