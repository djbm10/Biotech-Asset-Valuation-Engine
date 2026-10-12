# TARGET_QUERY_RESOLVED_IDENTITY_PRESERVATION v1

Status: PREREGISTERED dependency of TARGET_QUERY_ALIAS_COVERAGE v1; production unchanged.

## Diagnosis and hypothesis
A recognized alias can uniquely resolve to an entity whose approved symbol is also
claimed by another entity. The parser serializes only that symbol, so downstream
query compilation re-resolves an ambiguous name and refuses. Existing resolver
canonical IDs already preserve entity identity: TARGET:F11 resolves to the exact
entity, while bare F11 remains ambiguous. FXI is a development diagnostic only.
No new authority aliases are admitted in this dependency.

Use the existing canonical-ID representation; do not add an identity policy.
For every resolved parser entity, retain its current display-symbol reference only
if that symbol resolves uniquely back to that same entity. Otherwise retain the
entity's exact canonical ID. Apply the same operation to ordinary and separator
whole-name spans. Deduplicate on that stable reference. Keep the human-readable
label equal to the entity's approved symbol. Existing resolver ambiguity and
fragment policies are unchanged. Discovery query literals use the resolved symbol
rather than an internal namespace-prefixed ID; metadata retains the exact ID.

## Frozen scope and acceptance
Before implementation, commit this document and the unchanged 672-form/4,704-parse
baseline from the parent survey, plus its 16 controls. No new population selected
by candidate outcomes. The installed snapshot remains pinned to
chembl_ChEMBL_37__open_targets_26.06__resolver_v2__modality_v2.

I1: Toy authority fixture with two distinct identifier-linked entities sharing a
symbol: a unique alias carries the correct canonical ID through parse, intent
compilation and discovery planning; bare shared symbol remains ambiguous/refused.
I2: The same unique entity under mixed equivalent aliases occurs once; anti-,
-directed, -targeted, -targeting, -blocking, -binding, -specific preserve identity.
I3: Distinct targets separated by / or × remain distinct and preserve ALL semantics;
unknown fragments remain subject to existing separator safeguards.
I4: FXI's exact existing diagnostic query compiles offline to nonempty discovery
plans for TARGET:F11. No internal namespace token appears as a search literal.
Bare F11 remains ambiguous. H17/H20 missing aliases remain unchanged here.
I5: Across all 4,704 frozen parses, biological target symbols, target operators,
ambiguity lists, blockers, and target-span text/rule/provenance/offsets remain
identical. Only a necessary canonical-ID reference may differ. All 16 raw resolver
control outcomes remain identical. Existing affix discrepancy is not repaired.
I6: Gate target normalization maps the carried ID to the same approved symbol;
identifier-based authority seeding remains on that same entity. No global
resolver, authority snapshot, attribution, identity, indication, qualification,
modality, ranking, evidence, or source acquisition changes.
I7: Deterministic fixture outputs under PYTHONHASHSEED 0, 1, 42. No changes to the
separate human-PoC capitalization defect or failed receipt oracle.
I8: Full tests/se passes except existing xfails; Ruff clean for src/bve/se,
tests/se and new evaluation scripts. Human-PoC source bytes unchanged.

Permitted production files: intent/parser.py, intent/intent.py,
discovery/query.py only. New tests and offline audit script permitted. Version
becomes intent_v1__resolved_target_identity_v1; no schema migration. No live runs,
replays, H6–H10 or H21–H25 probes. No generalization claim from development checks.

One formal evaluation after implementation. If any criterion fails, record it,
normally revert behavior changes and retain evidence. Do not change this contract
or patch a failed candidate after formal results. Mechanical implementation errors
may be corrected during focused development before the formal evaluation.

## Frozen result — FAIL / REVERTED (2026-10-12)

Preregistration 533c699; candidate 612c088; failure record ed33b7d; normal revert
7e8f58e. Full tests: 1,709 passed, six failed, three existing xfails; Ruff clean.
I6 and I8 fail. The successful 4,704-parse/16-control audit and FXI plan diagnostic
do not override those failures. No post-result rule changes. See
research/se_target_query_resolved_identity_preservation_v1/summary.md and
interface_diagnosis.md. Restoration: 106 tests pass; src/tests/scripts exactly
match preregistration HEAD. This dependency is not adopted.
