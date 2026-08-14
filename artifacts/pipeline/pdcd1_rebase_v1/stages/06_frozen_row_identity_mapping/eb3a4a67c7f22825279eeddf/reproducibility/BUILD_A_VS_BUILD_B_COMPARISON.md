# Build A vs Build B — Milestone 6 v2 (genuinely independent second build)

## Provenance correction vs v1

The v1 release (`pdcd1-rebase-v1-m6-row-identity-mapping-e07fade12e18d972e3ea8743`)
claimed "two independent mapping builds with 0 disagreements." That claim was
false: v1's "Build B" was v1's Build A `lib.map_rows()` invoked a second time
with reversed row input order — not a separate implementation. Reversing
input order to an idempotent, order-independent per-row mapping function
trivially reproduces identical output; it is not evidence of independent
agreement.

This v2 release replaces that fabricated comparison with a real one:

- Build A = the original v1 mapping (unchanged; same code path, same outputs).
- Build B = `scripts/pdcd1_rebase_v1_row_identity_mapping_mapper_b.py`, a new,
  separate module that independently parses the frozen M3 row/occurrence
  bindings, resolves subjects against M4's authority ledger and M5's
  canonical-candidate / alias / conflict / boundary / subject-outcome
  ledgers, and independently decomposes combination strings. It does not
  import, call, or wrap Build A's code in any form, and was written without
  reading Build A's M6 output ledgers as a reference (see module docstring).
  Static non-delegation is enforced by
  `tests/test_pdcd1_rebase_v1_row_identity_mapping_mapper_independence.py`.

## Results

- **Row-level outcome agreement: 300/300 (100%)** across all six canonical
  outcomes (CANDIDATE_LINKED=103, EXPLICIT_NONCANDIDATE=49,
  CONFLICTING_MULTI_PRODUCT=84, INSUFFICIENT_EVIDENCE=34,
  IDENTITY_CONFLICT_UNRESOLVED=30, GENERIC_OR_NONIDENTIFYING=0). This
  agreement was reached through genuine iteration on Build B (fixing a
  missing primary per-subject lookup, an outcome-priority ordering bug, and
  two combination-string parsing gaps), not by copying Build A's answers.

- **Candidate-ID-set-level agreement (within the supplementary
  `row_candidate_mapping_ledger`): 297/300 (99%).** Three
  CONFLICTING_MULTI_PRODUCT rows — `row_151_NCT07629817_0`,
  `row_212_NCT03108495_1`, `row_219_NCT03486873_6` — show Build B including
  one additional candidate id beyond Build A's set, produced by Build B's
  generic combination-fragment name-matching against the M5 candidate/alias
  pool. Build A's set for these rows is directly grounded in explicit M5
  corpus records (either a same-row second bound M3 occurrence, or an
  explicit M5 decomposition record); Build B's extra id in each case is not
  corroborated by such a record. These three disagreements are documented in
  `reconciliation_ledger.jsonl` with per-row rationale and are resolved in
  favor of Build A's evidence-grounded set. The row-level outcome
  (CONFLICTING_MULTI_PRODUCT) is unaffected — both builds independently
  agree on it for all three rows.

  This residual ambiguity reflects a real limit of frozen-ledger
  reconstruction: Build A's exact trigger for decomposing a "+"/"/"-joined
  combination phrase into multiple tracked candidates versus treating a
  trailing term as background/backbone therapy is not fully recoverable from
  the frozen M1-M5 artifacts via generic string-matching alone. It is
  reported here rather than silently forced to match, per the review
  requirement that disagreements be resolved from evidence, not by making
  one build parrot the other.

## Authoritative output

The authoritative `row_outcome_ledger` for v2 (`rows/row_outcome_ledger.jsonl`)
is unchanged from v1's — all 300 rows already agreed at the outcome level.
What changes in v2 is the release's *evidentiary basis*: the "independent
Build B" is now real, the reconciliation ledger is now real, and the 3
residual candidate-set-level disagreements are disclosed rather than hidden
by a fabricated 0-disagreement comparison.
