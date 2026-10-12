# Greek authority-form diagnosis — no candidate implementation

Baseline adopted target-reference dependency: `7cece53` (implementation `07d104b`, adoption `62c951f`). Population is the already frozen 96 Greek proposals in the parent 672-form survey. No new positive labels or admission rule have been set.

All 96 Greek forms remain unresolved. Their original authority spellings resolve 93 times and are ambiguous three times. Only 92 resolved symbols agree with the proposing source record. Three resolved entities contain more than one canonical symbol among their source records:

- A tubulin alias groups TUBA1A/TUBA1B, with a canonical-symbol disagreement flag.
- An interferon alias groups IFNA1/IFNA13 without that flag.
- A calmodulin alias from CALM1 groups CALM1/CALM2/CALM3 and elects CALM2, without that flag.

This is a source-record/identity question, not a Greek-spelling problem. Do not interpret `RESOLVED` alone as certification for adding aliases. Most other entity conflict flags are shared aliases elsewhere on the entity, so rejecting every entity with any conflict flag would discard unrelated unambiguous lookups. Examine the actual lookup and contributing source identities separately.

The current resolver's `_elect_symbol` records one symbol per source in a dictionary before calculating disagreement, so multiple records from the same authority can disappear from that disagreement check. `_group_records` joins on shared identifier keys. The evidence does not yet establish whether each multi-symbol group represents legitimate equivalent protein products, obsolete identifiers, or an unsafe gene-level merge. Do not change these groups or invent preferred genes in an alias milestone.

Also, 29 proposals contain more than five whitespace-delimited words. Parser MAX_NGRAM is five, with its own tokenization. Raw authority resolution and parser span coverage are separate boundaries; do not promise that orthography alone will fix long-name coverage.

Next diagnosis: inspect underlying identifier/source records for those three groups and determine a principled new-alias certification rule (or mark unresolved) without weakening existing ambiguity/biological qualifier semantics. Then preregister a general orthographic relation and its exact positives/abstentions before implementation. NCIt P90 synonym semantics remain a separate pending authority-admission task. No live runs/replays, holdout probes, human-PoC changes or production changes occurred here.
