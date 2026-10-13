# TARGET_MENTION_ROLE_REPRESENTATION v2 — preregistration

Baseline 27a2548. Retry v1 representation, no semantic target change. Reuse v1
interval enumeration, observations, geometry, stable mention IDs and existing-decision
projection. Do not reinstall its resolver-derived evidence. No alias or holdout work.

## Frozen inputs

Pin v1 baseline (6,199 complete decisions), required_mentions (1,687 spans across
1,344 diagnosis rows), original population manifest, failure packet, span/query-role
contract, and adopted sidecar manifests. The 48 structural controls and 103 adopted
compatibility observations are already in baseline; preserve both known wrong separator
oracles unchanged. All 96 name pairs, 224 English mismatch frames and 21 protected Greek
frames remain included. No new scientific oracle or alias list.

## Minimal integration

Introduce a read-only sidecar lookup adapter and standalone analyze_target_mentions.
Adapter index is a derived local SQLite artifact, built only from adopted assertions
JSONL after checking content hashes and snapshot binding. Store normalized_key from
sidecar (not reconstructed from a snapshot alias), assertion ID, assertion type,
source-record key, canonical ID and resolver component ID from each assertion's
resolver_components. Distinct origins never deduplicate by canonical ID or match key.
Deduplicate only identical tuples for the same assertion/component. Sort all returned
rows by canonical ID/component/assertion ID. No automatic index build or parser hook.

Lookup normalizes the query with the existing normalize_lookup_key and performs exact
key equality against the sidecar's recorded match keys. It does not infer aliases or
reverse-map canonical IDs. Group returned assertion IDs by canonical ID/component,
retaining source keys and assertion types. All provenance is sidecar-derived. The
adapter also records immutable source manifest and snapshot hashes. Content-addressed
assertion IDs are resolvable in the adopted artifact; do not copy huge raw text into
every diagnostic row. Direct canonical-ID and ineligible fragment observations can
have no raw assertion match; label them NO_RECOVERABLE_MATCH, never fabricate an origin.
A missing adapter yields UNAVAILABLE lineage, not resolver/snapshot fallback. Native
canonical IDs/status/claimants/rules remain separately labelled production observations.
No assertion that every matching origin caused the legacy winner: competing origin
claims remain explicit, alongside the existing selection.

SQLite is an access index, not a new authority. Its build metadata binds adopted
assertions bytes and snapshot bytes. A stale index/input must fail closed. Connection
opens read-only. Unit tests may use synthetic sidecar rows, explicitly not authority
claims. Index bytes are not a scientific determinism target; complete returned records
and diagnostic JSON are.

## Role and geometry

Support all six v1 roles. Preserve geometric contains/contained/overlap/equivalent/
independent relations; equivalent means equal text extent, never biological equivalence.
Ownership remains UNADJUDICATED. Assign EMBEDDED only when contained mention and at least
one containing mention both have raw authority evidence; CONTEXTUAL only with recoverable
authority evidence plus existing non-target/non-residual production claim overlap.
All other uncertified roles are AMBIGUOUS_ROLE (including crossing spans, missing raw
lineage, and standalone authority candidates without independent grammar certificates).
TARGET_CANDIDATE/CONFIRMED/NON_TARGET remain representable but are not manufactured.
Role evidence records the structural basis and explicitly says no therapeutic-role
certificate. Decision-bearing flag solely mirrors an exact existing TARGET span and
its already-selected identity. Creation of an evidence record cannot promote a target.

## Frozen checks

R1 exact canonical-JSON decisions for all 6,199 rows before/after analysis and against
v1 baseline; no projected-field waiver.
R2 all 1,687 required intervals/lookup keys and native states present.
R3 independently stream adopted assertions to verify complete equality of returned
IDs/components/source keys/types for every emitted lookup key; zero provenance values
from resolver entities, snapshot labels or guessed canonical-ID origins. Missing raw
matches remain explicit. Check accepted snapshot and sidecar input hashes unchanged.
R4 all 77 historical failure observations have nonempty complete sidecar evidence,
including the exact raw label/source components retained by adopted lineage; no old
source-normalization workaround.
R5 preserve all matching assertion/component tuples under normalization or canonical-ID
collisions. No distinct origins dropped; evidence completeness is sidecar-relative,
not a false claim that unavailable historical ChEMBL originals were recovered.
R6 existing decision-bearing flag matches only an existing target observation; all
other mentions cannot create target requirements. No analyzer import in legacy parser.
R7 all interval pairs have correct deterministic geometry, with every containing edge
reflected both ways; no forced ownership winner or span deletion.
R8 repeated builds/seeds 0,1,42 produce identical canonical JSON for all 1,392 diagnostic
and structural rows; seed 0 also repeats every analysis across full 6,199 rows.
R9 all 224 English and 21 Greek explanation rows carry full representation and observed
winner; unknown role/lineage remains visible, not guessed.
R10 only new provenance adapter, mention module, tests/evaluator/docs/research; no edits
to any existing production module or authority artifact.
R11 full tests/se, existing xfails only, and Ruff src/bve/se tests/se plus new scripts.

Commit before implementation, then red tests, smallest candidate, full frozen scoring.
Any failed criterion is recorded and candidate normally reverted; no post-result patch.
On success adopt independently, update handoff; TARGET_MENTION_ROLE_DECISION v1 remains
a separate preregistration. Human-PoC stopped. H21–H25 untouched; H6–H10 unrun.

## Frozen result — ADOPTED

Preregistration **dec7b2c**; red controls **d8880b4**; candidate **4aca4d1**;
final v2 schema identifier and frozen evaluator **20ddc7e**. All R1–R11 passed.
No post-scoring code or acceptance changes.

- **6,199/6,199** full frozen decisions unchanged before/after analysis.
- **1,687/1,687** required spans represented with unchanged native states.
- **77/77** former failures closed with exact adopted sidecar assertion IDs.
- Independent sidecar streaming confirms complete assertion/component/source/type
  equality for every emitted lookup key. No resolver-derived provenance fallback.
- **1,392** complete diagnostic/structural records byte-identical at seeds 0, 1, 42;
  all 6,199 analyses also repeat identically in the full seed-0 evaluation.
- **245** full explanations cover all 32 English and three protected Greek spelling
  families, seven frames each. Known separator oracle defects remain unchanged.
- Full tests/se: **1,839 passed, 3 existing xfails**, no failures/errors; four focused
  controls pass; required Ruff clean.

Among 1,344 diagnostic queries: 364 have one mention, 980 multiple, 448 overlapping.
The 3,164 mentions comprise 2,422 AMBIGUOUS_ROLE, 735 EMBEDDED_BIOLOGICAL_MENTION and
seven CONTEXTUAL_BIOLOGICAL_MENTION; no independent target-role certificate is invented.
Fourteen mention occurrences lack a recoverable raw match and remain explicitly
uncertified. These are diagnostic counts, not targets optimized by this milestone.

Committed evidence is under `research/se_target_mention_role_representation_v2/results/`.
The derived index and independent generated outputs remain at
`/home/djmann/se_runs/target_mention_role_representation_v2/`.
Adopted assertion source remains the independently adopted authority sidecar. Its missing
historical ChEMBL origins are not reconstructed. Representation is available only through
an explicit analysis call; no existing parser/compiler or target-selection path consumes it.

Next milestone: separately preregister TARGET_MENTION_ROLE_DECISION v1. V2 supplies
structure and provenance; it does not establish a rule for therapeutic query-role
selection, recover aliases, fix H17/H20, or validate generalization. Human-PoC remains
stopped, H21–H25 untouched, H6–H10 unrun.
