# Assembler A vs Assembler B — Milestone 8 (genuinely independent second assembler)

## Provenance

- Assembler A = `scripts/pdcd1_rebase_v1_m8_benchmark_finalization.py` (original M8
  benchmark-finalization driver; unchanged, same code path as its existing
  historical release `pdcd1-rebase-v1-m8-benchmark-final-23ab4ae5a94b49b2bf746e66`).
- Assembler B = `scripts/pdcd1_rebase_v1_m8_benchmark_finalization_assembler_b.py`, a
  new, separate module that independently reads the same frozen M1-M7
  release artifacts (M6 v2-authoritative only) and independently
  reconstructs the same canonical M8 ledgers. It does not import, call, or
  wrap Assembler A's code in any form, and was written without reading
  Assembler A's output ledgers as a reference. Static non-delegation is
  enforced by `tests/test_pdcd1_rebase_v1_m8_assembler_independence.py`
  (6/6 static checks, all passing).

Both assemblers were run against the same frozen, freshly re-verified
extracted milestone releases at `/tmp/pdcd1_verify.S9B8Rk/{M1..M7}/extracted/`
(Part A of this task), using the same `run_id`
(`m8assemble1786745321`) so outputs are directly comparable byte-for-byte.

### I/O wiring note

Assembler A's `--src-root` expects a directory tree shaped like
`<src-root>/<NN_stage_name>/<run_id>/...` (matching the live
`artifacts/pipeline/pdcd1_rebase_v1/stages/` layout), whereas the
Part-A-verified fresh extracts sit directly at
`/tmp/pdcd1_verify.S9B8Rk/{M4,M5,M6,M7}/extracted/<run_id>/...`. To run
Assembler A (and, for consistency, Assembler B, which reads the same
`--src-root` layout) against the fresh extracts without modifying either
script's logic, a synthetic `--src-root` was built at
`/tmp/pdcd1_m8_src/artifacts/pipeline/pdcd1_rebase_v1/stages/` containing
only **symlinks** into the frozen fresh-extract directories, one per
prerequisite stage/run_id pair (`05_candidate_identity_adjudication/<M5>`,
`06_frozen_row_identity_mapping/<M6-v2>`, `07_candidate_chronology/<M7>`,
`04_external_product_authority/<M4>`). No file content was copied, edited,
or regenerated; no assembler source code was changed. This is the only I/O
adaptation made.

## Results

- **Validator metrics: identical.** Both assemblers report the same
  validator metrics dict (224 canonical candidates, 300/300 unique rows,
  182 distinct referenced candidate_ids, 181 chronology candidates / 71
  chronology NCTs, 316 chronology pairs / 102 matching M6-v2 exact pairs /
  214 beyond-snapshot, 76 M5 unresolved conflicts, 148 M6 unresolved rows,
  214 modality/intent rows, same 300-row outcome distribution
  CANDIDATE_LINKED=103 / CONFLICTING_MULTI_PRODUCT=84 /
  EXPLICIT_NONCANDIDATE=49 / IDENTITY_CONFLICT_UNRESOLVED=30 /
  INSUFFICIENT_EVIDENCE=34). All validator checks passed on both sides.

- **Ledger-level comparison: 11/12 canonical artifacts byte-identical.**

  | Artifact | Result |
  |---|---|
  | `candidates/canonical_candidate_ledger.jsonl` | byte-identical |
  | `candidates/alias_development_code_ledger.jsonl` | byte-identical |
  | `candidates/rejected_alias_ledger.jsonl` | byte-identical |
  | `candidates/m5_conflict_resolution_ledger.jsonl` | byte-identical |
  | `rows/row_outcome_ledger.jsonl` | byte-identical |
  | `rows/row_candidate_mapping_ledger.jsonl` | byte-identical |
  | `rows/combination_component_ledger.jsonl` | byte-identical |
  | `rows/unresolved_row_ledger.jsonl` | byte-identical |
  | `modality/candidate_modality_intent_ledger.jsonl` | **differs (see below)** |
  | `chronology/finalized_candidate_chronology_ledger.jsonl` | byte-identical |
  | `chronology/m7_validation_summary.json` | byte-identical |
  | `evidence/row_evidence_binding_ledger.jsonl` | byte-identical |

  This is expected: eight of the twelve artifacts are pure pass-through
  copies of frozen upstream ledgers (M5/M6/M7 output verbatim), where there
  is no judgment call to make and both assemblers necessarily agree
  byte-for-byte. `chronology/finalized_candidate_chronology_ledger.jsonl`
  and `chronology/m7_validation_summary.json` are likewise verbatim copies
  of frozen M7 outputs and agree for the same reason. Only
  `modality/candidate_modality_intent_ledger.jsonl` is a *derived* artifact
  (a mechanical join across three frozen sources), and it is the one
  artifact where the two assemblers' independently-authored traversal
  strategies could plausibly diverge.

### Reconciling the one difference: `candidate_modality_intent_ledger.jsonl`

- Both files contain exactly 214 records.
- Sorting both files line-wise and comparing shows the two ledgers contain
  **the same 214 records** (same `candidate_id`, `m4_subject_id`,
  `frozen_row_id`, `modality_assertion_types`, `derivation` fields on every
  row) — the only difference is **row order**.
- This is the expected consequence of the two assemblers' deliberately
  different, genuinely independent traversal strategies for this join:
  Assembler A iterates the M6 `row_candidate_mapping` ledger
  mapping-record-first (so its output order is M6 ledger insertion order);
  Assembler B iterates the M5 canonical-candidate ledger candidate-first
  (sorted by `candidate_id`), scanning M6 mappings per-candidate (so its
  output order is canonical `(candidate_id, m4_subject_id)` order). Both
  independently perform the identical mechanical join specified by
  Assembler A's own docstring (assertion_type contains `MODALITY`, joined
  via `row_candidate_mapping.binding_path`) — this is not a judgment call
  with two defensible answers, it is a fully mechanical join over frozen
  evidence, so agreement on the *set* of records (214/214, content
  identical) is the correct outcome and was reached independently, not by
  one assembler copying the other.
- **Resolution:** no new judgment call is required. The reconciled/merged
  M8 output adopts Assembler A's original insertion order for this ledger
  (no functional difference in content; row order in this ledger carries no
  semantic meaning — it is a derived join table, not a frozen ledger with
  its own canonical ordering), and this comparison document records the
  order-only divergence and its resolution for the audit trail.

## Authoritative output

Because content-level agreement is 12/12 (100%) once the one artifact's row
order is normalized, and every validator invariant passes identically on
both sides, the M8 benchmark package's canonical content is unchanged by
running Assembler B — Assembler B independently corroborates Assembler A's
existing historical release
(`pdcd1-rebase-v1-m8-benchmark-final-23ab4ae5a94b49b2bf746e66`) rather than
superseding it. No reconciliation of substantive content was required.
