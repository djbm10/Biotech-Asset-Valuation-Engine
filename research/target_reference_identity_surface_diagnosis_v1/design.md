# TARGET_REFERENCE_IDENTITY_SURFACE_DIAGNOSIS v1

Status: diagnosis/design in progress; no implementation authorized by this document.
Baseline: 5da4fdf, with the failed identity candidate normally reverted. Parent
TARGET_QUERY_ALIAS_COVERAGE v1 remains open. H21–H25 and H6–H10 are protected.

## Established boundary

`TargetTerm.canonical_id` is currently both an ontology reference and a biological
surface. The failed three-file implementation preserved the former but broke the
latter. The consumer inventory records 25 direct target/term reads across the
relevant modules, plus separately audited TargetQuery.or_group and attribution_for.
This is a source inventory, not proof of complete dataflow coverage.

| Consumer | Required role | Compatibility obligation |
| --- | --- | --- |
| Parser spans / TargetTerm | Exact resolved entity plus display text | Bare homonyms stay ambiguous; equivalent aliases deduplicate |
| Intent compiler | Ontology alias expansion | Use certified entity; do not re-resolve its ambiguous symbol |
| Direct trial-query compiler | Biological retrieval terms | Never add namespace IDs as literal search terms |
| Discovery vocabulary / authority seeds | Exact entity for lookup; biological aliases for text | Both outputs must refer to the same entity |
| Acquisition target adapter | Biological surface and aliases | Preserve connector requests for existing queries |
| FDA/PubMed/conference/SEC/bulk connectors | Biological text | No internal ontology namespace in external query text |
| Source policy validation | Declared supported target identity | Validate resolved identity without conflating surface syntax |
| Pipeline asset-target attribution | Exact ontology entity | No fallback from an ambiguous display symbol |
| Gates | Canonical entity comparison | No new target-attribution evidence or broader matches |
| TargetExpression deduplication | Same resolved entity | Do not emit two targets for equivalent old/new aliases |
| Human-readable explanations | Display plus provenance | Preserve matched alias, authority records, offsets and meaning |

## Preferred design direction to test

Investigate an additive typed ontology reference attached to a target term, while
retaining legacy biological symbols/labels for display and retrieval. The reference
must carry an exact entity ID and snapshot/version, with resolution provenance
preserved. The final field names/interface are not frozen yet. Avoid adding a
second independent source of biological truth: the reference and surface must be
validated together before compilation. A wrong entity/surface pair, missing
snapshot or mismatched snapshot must fail closed, not silently reinterpret input.
Legacy inputs without a reference retain existing ambiguity behavior.

Explicitly test all consumers with injected/no-network source functions. Passing
`compile_problem_queries` alone was insufficient. Include direct trial compilation,
source-policy validation, FDA description text, aliases, seeding, target attribution,
gates, serialization and round-trips. Keep all existing scientific target rules.

## Historical contract lifecycle boundary

The full-suite failures also exposed two distinct test responsibilities:

1. Historical milestone certification: exact frozen source hashes, allowed file
   scope and original serialized parser versions must continue to describe that
   milestone's adopted commit. Preserve its artifacts, scorers and outcome.
2. Current compatibility: a successor must preserve the scientific semantics of
   the frozen controls while explicitly declaring its new metadata/interface.

The indication-v3 scorer compares complete parser dictionaries and source scope
against its old baseline. Consequently any parser version bump fails old criteria
C3.2/C3.4/C3.6/C3.7 even when indication labels are identical. The gate-v3 test also
hash-pins discovery/query.py. Do not edit the frozen populations, expected labels,
source hashes or historical scoring rules. Do not add generic exclusions or a
blanket xfail. Before a successor implementation, define separate historical
verification and current semantic compatibility checks, and freeze precisely which
new interface/version fields may differ. All other control fields must remain
identical. This transition must be explicit and auditable, not retroactive relief
for candidate 612c088, whose failure remains final.

## Work required before implementation preregistration

- Complete consumer coverage, including dynamic/indirect canonical-ID uses.
- Freeze baseline requests and returned attribution/plan metadata for a general
  synthetic multi-entity authority fixture and existing development controls.
- Define a minimal reference representation and validation at each boundary.
- Freeze conflicts, missing snapshots, bare homonyms, alias-equivalent mentions,
  separators, unknown fragments, and source-literal negatives.
- Define the historical/current contract test separation without mutating frozen
  evidence. Include proof of old scorer results at the original adopted versions.
- Commit exact acceptance checks and file scope before production changes.

No human-PoC recovery, C056 fix, indication change, target alias addition, live run,
replay or heldout scoring belongs to this diagnosis. Alias capitalization and the
failed prednisone/prednisolone oracle remain separate.
