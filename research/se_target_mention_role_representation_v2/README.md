# TARGET_MENTION_ROLE_REPRESENTATION v2

Preregistration `dec7b2c`; red controls `d8880b4`; candidate `4aca4d1`; schema version
and frozen evaluator `20ddc7e`. This retries v1's representation, not target semantics.

`analyze_target_mentions(intent, provenance=lookup)` is a separate read-only analysis.
The legacy parser/compiler never calls it. The existing target selection is exposed as
an observation; evidence or role records cannot create a target requirement.

## Exact provenance

`SidecarLookup` indexes only verified adopted assertion JSONL. Matching uses the existing
query normalization against the sidecar's stored normalized_key. Returned evidence
contains canonical ID, distinct resolver component ID, all matching assertion IDs,
source-record keys and assertion types. IDs locate exact raw artifacts/fields/components
and transformations in the adopted authority sidecar. Multiple assertions per canonical
ID are retained. Evidence describes matching origins, not a retrospective claim that
all origins caused the legacy winner. No resolver.get or snapshot-label reconstruction.

A missing adapter is UNAVAILABLE. A native observation without a raw sidecar match has
NO_RECOVERABLE_MATCH; no origin is synthesized. Fourteen diagnostic mention occurrences
have this state. Missing historical ChEMBL provenance is not repaired by this milestone.
Canonical-ID/direct-generated/fragment observations can also lack a raw exact match.

Roles and span ownership remain separate. Ownership is UNADJUDICATED; equal extents
are geometric equivalence, not biological identity. Embedded/contextual roles record
only the preregistered evidence/geometry or existing contextual claim. Other roles are
AMBIGUOUS_ROLE without an independent therapeutic-role certificate. All six enum states
exist, but confirmed target roles are not invented. Current target-bearing flags solely
mirror the exact existing production span and chosen identity.

## Artifacts and reproduction

Derived access index and full generated output:
`/home/djmann/se_runs/target_mention_role_representation_v2/`.
Index source: adopted sidecar
`/home/djmann/se_runs/authority_assertion_provenance_sidecar_v1/seed0/assertions.jsonl.gz`.
The index may be rebuilt with `assertion_sidecar_lookup.build_index`, supplying expected
assertions and snapshot SHA256 from the adopted receipts. It refuses an existing output
path, changed source bytes, or mismatched snapshot binding. `SidecarLookup` opens it
read-only and checks expected binding metadata; the evaluator independently verifies
all emitted origins by streaming the adopted sidecar, rather than trusting the index.

From repository root, run sequentially:

```bash
PYTHONHASHSEED=0 PYTHONPATH=src python research/se_target_mention_role_representation_v2/evaluate.py
PYTHONHASHSEED=1 PYTHONPATH=src python research/se_target_mention_role_representation_v2/evaluate.py --seed-only
PYTHONHASHSEED=42 PYTHONPATH=src python research/se_target_mention_role_representation_v2/evaluate.py --seed-only
```

Seed 0 checks all 6,199 decision hashes before/after analysis, repeats every analysis,
checks 1,687 spans and every pairwise geometry, closes all 77 historical failures, and
independently verifies exact sidecar IDs/components for every emitted lookup key. All
three seeds emit the 1,344 diagnosis plus 48 structural rows. Complete diagnostic bytes,
not merely counts, must match. The 103 adopted compatibility observations and the 4,704
alias survey parses are included in the full baseline. Both known wrong separator
expectations remain unchanged; current decisions, not repaired gold, are compared.

`results/mentions_seed_0.jsonl` preserves the full diagnostic record. Independent seed
receipts bind identical copies. `explainability.json` contains all 224 English mismatch
frames and 21 protected Greek frames; the Markdown index groups their 35 spelling
families. Full exact spans, roles, origins, relationships and current winner are retained
in JSON. Existing tests/se and Ruff remain independent adoption gates.

No semantic target-role rule, alias expansion, source acquisition or human-PoC work.
H21–H25 untouched; H6–H10 unrun. TARGET_MENTION_ROLE_DECISION v1 is a separate next
preregistration, not part of this representation.
