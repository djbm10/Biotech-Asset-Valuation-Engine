# TARGET_MENTION_ROLE_REPRESENTATION v1 — FAILED ACCEPTANCE

Preregistration d26949f; red tests cbdb8d2 (missing module, as expected); candidate 1bbfceb. No post-result code or oracle patch. Normal revert required.

## What passed

All 6,199 exact canonical-JSON decision hashes match the frozen baseline; parser intent, compiled buyer problem and trial query are unchanged before/after analysis. All 1,687 required mention intervals are present. All 14,949 examined mentions mirror existing source IDs and production selection, with no new target promotion. All 103 adopted compatibility and 48 structural current decisions are preserved. The incorrect S041/S042 expectations were not changed or used as new expected decisions.

All 6,199 repeat analyses match. Complete new records for 1,344 diagnosis observations plus 48 structural controls are byte-identical under independent seeds 0, 1 and 42. One content-identical ledger is retained as mentions_seed_0.jsonl; the independent run receipts retain all three SHA256 values. The first 1,344 lines are the required diagnostic population. This proves determinism of the new representation, not a repair of the separate existing alias-capitalization issue.

Full tests/se: 1,835 passed, three existing xfails, zero failures/errors. All seven new focused tests pass. Ruff clean. No existing production file or authority snapshot was edited.

## What failed

**R3: 77 mention observations lack the preregistered exact source provenance. R8 is also incomplete in seven required English explanation frames.**

1. 35 observations of `gene` produce 70 assertions whose raw source label is ` gene` but whose represented value is `gene`. SourceAlias performs whitespace normalization. The evidence has the source key but does not preserve the raw field and its transformation. This is a raw-text fidelity failure, not an invented biological identity; the criterion is not relaxed after measurement.
2. 21 observations of `MRCK` and 21 of `E2` expose a deeper existing resolver provenance boundary. Canonical IDs are elected symbols, while records are grouped by cross-reference identifiers. Distinct unjoined groups can receive the same canonical ID. `_build` overwrites `_entities[id]` with the last group but retains all groups in `_by_type` and all alias-index entries. An alias can therefore resolve by an earlier group's entry while `get(id)` returns a different group's records. The candidate faithfully preserved the current decision but could not certify the alias from that returned component.

The frozen collision trace shows two components with TARGET:CDC42BPA and seven with TARGET:SNORA62. For MRCK, the supporting source record is open_targets:ENSG00000143776, whereas get returns chembl:CHEMBL3308982 without that alias. For E2, the relevant SNORA62 alias assertion exists in a different source component from the retained open_targets:ENSG00000272015. These are component-addressing collisions; this study does not decide whether any groups should be biologically merged. No identity repair or source join was attempted.

`provenance_failure_diagnosis.json` accounts for every failed observation; `canonical_id_collisions.json` preserves the exact components and source records. The diagnostic scripts use only the installed snapshot. The scorer's combined R3_R7 failure tag is disambiguated here: no new identity was merged; source traceability failed under R3.

## Diagnostic counts (not tuning objectives)

Across 1,344 observations: 3,164 mentions; 364 queries with one mention; 980 with multiple; zero with none. 448 queries have overlapping/contained/equal-extent mentions; seven have crossing overlaps. 742 embedded mentions across 448 queries. Zero confirmed target roles, deliberately: no grammar certificate was invented. Zero AMBIGUOUS_ROLE labels because the frozen annotation priority classified the crossing mentions as embedded; all geometric crossing relations remain visible. 294 authority-conflict mentions across 224 queries. Source ambiguity/identity conflict is separate from query-role ambiguity.

## Handling and next boundary

Revert candidate 1bbfceb and its red-test commit cbdb8d2 normally; preserve this packet and the preregistration. Do not implement a post-result patch. The representation/decision separation was neutral, but adoption fails on provenance.

Before a successor representation or role-decision implementation, diagnose the authority lookup/component provenance contract separately: raw source-field transformations and alias-index claimant-to-component ownership must be explicit. Do not silently merge components or repair target identities to make this representation pass. Human-PoC remains stopped; no H17/H20 alias fix; no H21–H25 inspection/run; H6–H10 unrun. Existing C056, ranking, qualification, duplicates and capitalization issues remain separate.

Scorer/diagnostic scripts require the historical candidate module and are retained as evidence, not runnable current-production tools after reversion.
