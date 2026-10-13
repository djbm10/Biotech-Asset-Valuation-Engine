# AUTHORITY_ASSERTION_PROVENANCE_SIDECAR v1 — preregistration

Baseline 2a86312. Additive lineage only. Never modify current snapshots, resolver,
parser, aliases, target requirements, target-role logic or any diligence behavior.
No holdout inspection; human-PoC stopped. No representation-v2 implementation here.

## Frozen inputs and independently established expectations

All 124 provenance audit cases, 77 historical failures and 443 snapshot-field assertion
occurrences remain frozen at 5aa8fdd/2a86312. Pin their files and the 6,199-decision
baseline by SHA256. Pin installed snapshot files and the three original Open Targets
26.06 target shards. Preflight reproduced all 78,691 accepted Open Targets target
records exactly with the existing loader. No record mismatches or missing records.
The 5,869 ChEMBL target records lack retained ingestion-response artifacts (manifest
raw_files empty; original HTTP builder discards payload). A separate release database
is not the original ingestion payload; do not substitute it. Those historical assertions
must be UNRECOVERABLE, not assigned fabricated upstream paths. Frozen 44 original
Open Targets witness records permit independent field-level inspection.

Freeze expected audited assertion recovery by source: Open Targets RECOVERABLE;
ChEMBL UNRECOVERABLE. Unresolved query controls have no implied biological assertion.
Freeze synthetics before code for exact whitespace, punctuation/case, Greek preservation,
array duplicates, ChEMBL scalar component splitting/prefix removal, alias collisions,
component collisions, missing raw source and changed snapshot-record rejection.

## Implementation contract

New standalone provenance module and offline generation script. No import/call from
legacy resolver/parser/production snapshot build path. An ingestion caller may use the
new capture API on each raw record BEFORE parsing/deduplication; offline materialization
uses precisely that API on retained raw artifacts and verifies legacy parsed record
against the accepted snapshot. Existing loaders remain authoritative and unchanged.

An assertion identifies authority/release, raw artifact SHA256 and relative bundle path,
record ID and artifact row locator, exact source field path, upstream component index/
accession if present, scalar component interval/index, raw scalar and exact substring,
assertion type, transformations, normalized key, and snapshot-field linkage. A stable
ID hashes authority/release + artifact digest + row/record + field/component locator +
raw substring. No random/time fields; no absolute machine path in identity. Array
ordinals are stable locators within a content-addressed artifact, not runtime order.
Resolver component identity hashes sorted source-record keys and snapshot digest;
canonical ID and label are separate attributes. Never use get(canonical_id) to elect
component provenance. Iterate all existing resolver components without merging them.

Raw capture adapters mirror actual loader inputs: Open Targets approvedSymbol,
approvedName, synonyms, symbolSynonyms, nameSynonyms, obsoleteSymbols; string values
or selected label/name members retain exact path. ChEMBL pref_name and every target
component synonym preserve component/index/accession and scalar split intervals;
first eligible symbol also produces the canonical-symbol field. Empty/ignored values
do not enter snapshot assertions. Raw-to-snapshot linkage uses field-kind for direct
symbol/name and normalized-key + alias-type for retained alias fields; duplicate raw
assertions remain distinct and link many-to-one. Do not infer biological equivalence.

Operations are explicit: ChEMBL first '=' payload selection, semicolon component
selection, strip; SourceAlias whitespace collapse; normalize_lookup_key casefold,
'-'/'_'/'/' to spaces, whitespace collapse. No Unicode normalization, Greek
transliteration, fuzzy or extra punctuation operations. Preserve each step's input and
output. Whole raw scalar and interval remain available when one scalar yields aliases.

Historical sidecar is separate deterministic gzip JSONL (mtime=0, no filename header),
plus snapshot-assertion linkage JSONL, component map, raw artifact manifest, coverage,
transformation and collision reports. Large generated artifacts may be retained under
/home/djmann/se_runs/authority_assertion_provenance_sidecar_v1 with committed digests
and reproduction commands; do not put large upstream artifacts into git. Source files
never copied per assertion. Missing raw records emit explicit UNRECOVERABLE linkage;
no fake sidecar row, raw label, source component, or normalized-text-as-original.

## Acceptance, fixed before implementation

P1/P7: all 6,199 frozen full parser/compiler decisions exactly match baseline; all 124
lookup statuses/IDs/candidate IDs/rules unchanged; no existing production decision
file changed. Every Open Targets snapshot assertion field has >=1 exact raw origin;
every missing-original ChEMBL assertion explicitly UNRECOVERABLE. All 443 audited
occurrences obey their frozen source-specific expectation. Other unlinked available
source assertions are failure, not a waiver.
P2/P3: 100% emitted raw text and component intervals round-trip to original source;
distinct locators have distinct IDs, including normalized duplicates. Snapshot target
records reproduced exactly before any linkage. ChEMBL capture adapter tested only
with frozen synthetics; no claim of historical ChEMBL recovery.
P4: every assertion uses its source record's actual resolver component(s); distinct
components sharing a canonical ID remain distinct. Zero canonical-ID based replacement.
P5: 100% operation sequences replay to recorded key; no invented transformations.
P6: two sequential full generations with seeds 0/42 produce byte-identical artifacts
and assertion IDs. Stable artifact-relative locators, sorted components and manifests.
P8: zero original-source claims for unavailable artifacts; absence quantified.
P9: every pinned accepted snapshot file unchanged before/after; source hashes pinned.
P10: changes limited new provenance module, script, tests and study documents/artifacts.
P11: focused red-first tests, full tests/se (existing xfails only), Ruff src/bve/se tests/se
and new scripts. All must pass. No post-result patches. If acceptance fails, record all
results, normally revert implementation/dependent tests, preserve study and handoff.

## Report and stop

Report raw accepted assertion count, sidecar rows, unique canonical IDs, IDs with multiple
provenance assertions, normalized-key collisions (distinct raw text), source-component
collisions (distinct resolver component keys sharing canonical ID), recoverable and
unrecoverable snapshot assertion fields; distinguish occurrence counts from unique
assertions. Include all 124 query cases without treating unresolved lookup as a raw
assertion. Adopt independently only on all criteria. Then stop with representation v2
as a separately preregistered next milestone; do not change target roles or aliases.
