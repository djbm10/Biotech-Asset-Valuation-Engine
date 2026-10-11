# INDICATION_REQUIREMENT_COMPILATION v2

Status: FAILED_ACCEPTANCE / REVERTED, 2026-10-11. Baseline 7f09c26. Compilation ONLY.
INDICATION_REQUIREMENT_SEMANTICS v1 remains FAILED_ACCEPTANCE / REVERTED and authoritative.

## Diagnosis, hypothesis and representation

The existing compiler promotes residual tokens into independent indication literals.
It cannot reconstruct a disease phrase across an AMBIGUOUS_TARGET span (NSCLC's `cell`).
V1 erased three diagnostic requirements, omitted Finding-typed hidradenitis suppurativa,
and changed downstream comparison and negation behavior. This experiment changes only
query construction: original coherent disease/purpose spans plus transparent uncertainty.

StrategicGap.indications stays list[str]. The existing B-cell request concept is preserved.
Other indications remain coherent literal phrases, not new IDs that the unchanged gate
cannot interpret. A compiler-only immutable span record carries original offsets/text,
RECOGNIZED / UNRESOLVED / DELEGATED_CLASS status, matched authority aliases/codes, and
source fingerprint. UNRESOLVED is normalization metadata, not a gate UNKNOWN verdict.
No disease synonym equivalence, subtype evaluation, indication compatibility or gate
PASS/FAIL/UNKNOWN semantics is added here. No product recovery criterion is imposed.

## Frozen population and source

research/se_indication_compilation_v2/population.json freezes 76 query constructions:
H2, H4, H11–H14, TAC01, mint5; all 16 v1 semantic request controls; all 18 v1 leakage
terms in both bare and `for` constructions; and 16 general positive/negative constructions.
It freezes current parsed intents/spans, compiled problems and trial queries, each exact
expected coherent requirement, all v1 failure-diagnosis records, all 16 existing gate
decisions, and JCAR014's accepted PASS on DLBCL, Not Otherwise Specified.

manifest.json seals population and ncit_query_roles.json before implementation. The query
role view is derived from ALL existing NCIt 26.08e flat records, with the source SHA256.
It retains Disease or Syndrome/Neoplastic Process names, Finding names separately, other
names, and source-typed molecular/therapeutic/research component names. Finding is never
promoted to a normalized disease. Roles locate spans or identify non-indication query
components; they do not assert scientific disease compatibility. No targeted alias list.
The existing parser grammar and class_terms format vocabulary are reused, not copied into
a diagnostic-specific stopword list. Nothing from H16–H20 is read/resolved/run.

## Exact compilation rule

1. Work on original query offsets. Split grammatical indication/purpose clauses at whole
   words `for` / `in` and sentence punctuation (.?!;). Keep commas/hyphens/slashes inside
   candidate spans. Grammar tokens at boundaries use existing parser _STOPWORDS.
2. Find maximal whole-word NCIt disease aliases within each clause; no substring, fuzzy,
   synonym replacement or clinical inflection. Finding aliases are uncertain clinical
   locators only. Single-word Finding aliases shared with a nonclinical role do not establish
   a clinical locator (`clinical` is one such ambiguous generic term).
3. Existing target, modality, evidence, phase, status and target-logic spans form component
   boundaries, except when inside a whole clinical locator. AMBIGUOUS_TARGET is a soft
   boundary: preserve it inside a coherent disease span without changing target logic.
   Within an explicit clinical clause with a clinical locator, TARGET spans may be retained
   as disease qualifiers; they never become independent indication requirements.
4. Entire existing UNRESOLVED_SCIENTIFIC class spans still delegate to the existing
   clarification mechanism when they exhaust the clause's non-component content. They
   remain coherent DELEGATED_CLASS provenance and do not acquire a new gate requirement.
   This preserves mint5 and existing scientific-class policy. A more specific clause with
   additional residual name/identifier text retains the entire uncertain clinical span.
5. Drop standalone molecular/therapeutic/format/research components using typed parser
   spans, the existing class_terms vocabulary, and the frozen authority role index.
   A standalone amino-acid substitution has the full-token structural form
   [ACDEFGHIKLMNPQRSTVWY][0-9]+[ACDEFGHIKLMNPQRSTVWY], case-insensitive; it is a query
   component, not an indication. This is not mutation-specific target interpretation.
   Regular plural `s` / `ies` folding is permitted ONLY for lookup of nonclinical components;
   disease alias matching is never stemmed. No target/product/query-specific exceptions.
6. With a clinical locator, preserve the enclosing original clinical phrase, including
   uncertainty, modifiers, negation and Not Otherwise Specified; do not strip negation
   tokens or collapse coordinations. A valid indication never disappears because alias
   normalization is uncertain. Leading/trailing independent therapeutic components may be
   removed; diagnostic qualifiers and interior words are not arbitrarily filtered.
7. Without a locator, an explicit `for` / `in` clause with unrecognized ordinary content
   is preserved as one coherent UNRESOLVED span. A clause exhausted by known nonclinical
   components produces no indication. Unanchored bare residual words are not indications.
8. The legacy full-phrase resolve_indication_phrase remains the only concept normalization.
   Otherwise requirement equals the original retained phrase. Exact unique NCIt disease
   surfaces may be marked RECOGNIZED in provenance; ambiguous, modified, negated,
   coordinated, Finding-only and unrecognized surfaces remain UNRESOLVED.

Caller-supplied indications remain unchanged. Parser output/residuals/retrieval are immutable.
Compiled problem ID, target expression, modality, phase, floors and all other fields are
unchanged. Only indications and an explicit compilation-version/source fingerprint may
change. No gate/evaluator/ontology-indications/identity/qualification/efficacy/ranking/
shortlist/pipeline code may change. Production source scope: compiler.py and a new
compiler-only indication_compilation.py; frozen query-role artifact is input data.

## Acceptance criteria and measurement — ALL mandatory

C1: Each of the 35 frozen positive query cases has exactly its preregistered requirement
list, as coherent text or the existing B-cell concept. No arbitrary per-token requirements.
(35 = seven benchmark/diagnostic positives + 16 semantic requests + 12 general positives.)
C2: All six diagnostic queries retain exactly one required disease span, including H2/H11
across `cell` and H13 Finding-typed disease. None of the frozen positive requests is erased.
C3: All 36 leakage constructions and all general negatives produce no indication requirement.
Nonclinical words in diagnostic queries produce no independent requirement.
C4: All uncertain/negated/NOS/coordinated positive constructions retain the exact original
coherent requirement with provenance. Finding-only, ambiguous or unrecognized normalization
is UNRESOLVED, never invented equivalence. Span text equals original_query[start:end].
C5: TAC01 indications exactly [INDICATION:B_CELL_LYMPHOMA]. JCAR014's existing indication
decision remains exactly its frozen PASS. All v1 B-cell gate controls remain byte-identical.
C6: mint5 indications remain []; compiled semantic fields/retrieval/parser remain identical.
Its scientific-class handling is delegated rather than erased or turned into a literal gate.
C7: Every frozen intent/residual/trial-query unchanged; every compiled problem field except
indications and provenance version unchanged. All 16 frozen gate controls byte-identical.
Protected source SHA256s unchanged, including gate engine/evaluator, indication ontology,
parser, identity, qualification, modality, efficacy, ranking/shortlist and trial attribution.
No scientific benchmark rank or membership is tuned. Structural source diff is compiler-only.
C8: Focused regression tests pass; full PYTHONPATH=src python3 -m pytest tests/se -q passes
apart from expected xfails; ruff check src/ is clean. Update only obsolete compilation-token
assertions to the preregistered phrase contract, before running acceptance. Existing gate
assertions remain unchanged. Tests assert query semantics, provenance and isolation.

The offline scorer checks the sealed inputs, reconstructs each frozen SearchIntent (no live
query), compiles requirements/provenance/problem/trial query, compares exact expected
values and untouched fields, and re-evaluates unchanged gate controls. It records every
criterion and before/after list. Targeted and full checks are recorded independently.
No scoring rule, oracle, threshold or implementation patch after frozen acceptance results.

## Stop, adoption/reversion and next milestone

Any frozen criterion fails: record FAILED_ACCEPTANCE; normal git revert of implementation;
retain failed attempt and frozen artifacts in history; no repair without new preregistration.
All pass: ADOPT compilation v2, record offline diagnostic compiled requirement changes and
unchanged JCAR014/gate semantics, update handoff. Do not require the 33 references to become
visible and do not infer generalization from development queries. Gate false FAILs remain
a separately diagnosed downstream problem. No live acquisition/replay or H16–H20 exposure.
Then preregister INDICATION_GATE_SEMANTICS v1 separately; do not implement it in this turn.

## Frozen result (no revised rule)

Preregistration 30bfdbe; implementation f46dd76. Offline exact compilation: 75/76.
C1 FAIL, C2 PASS, C3 PASS, C4 FAIL, C5 PASS, C6 PASS, C7 PASS, C8 FAIL.
All six diagnostic requirements became coherent; all 41 negative query controls passed.
TAC01, mint5, JCAR014 PASS, all 16 gate controls and protected source hashes preserved.
The general negation query requested `not NSCLC` but produced `NSCLC`. NCIt's NOT
molecular alias caused independent component trimming to erase a grammatical operator,
despite the existing AMBIGUOUS_TARGET span being a soft disease-span boundary. This can
turn a negative request into a positive assertion and blocks adoption. No patch follows.

Targeted tests: 114 passed, 2 failed. Full tests/se: 1,669 passed, 2 failed, 3 expected
xfails (1,674 collected). Ruff: FAIL, three E741 naming violations. Exact failed tests,
scoring, quality gates and root cause retained under research/se_indication_compilation_v2.
No gate milestone is preregistered or implemented because compilation has not been adopted.
Next option requires a NEW compilation-only preregistration giving query grammatical
operators precedence over molecular alias roles and conservatively retaining overlap.
H16–H20 remain untouched; no live acquisition/replay or outcome inspection.

Normal git revert 2e297c6 preserves implementation and failure record 2b0a80e.
Source/tests/scripts equal baseline 7f09c26 byte-for-byte; restored 108 indication/intent
tests pass and ruff check src/ is clean. No revised implementation was attempted.
