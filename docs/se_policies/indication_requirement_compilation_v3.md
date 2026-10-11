# INDICATION_REQUIREMENT_COMPILATION v3

Status: ADOPTED, 2026-10-11. Baseline clean HEAD 2633539.

## Diagnosis and hypothesis

V2 is permanently FAILED_ACCEPTANCE / REVERTED (30bfdbe / f46dd76 / 2b0a80e /
2e297c6 / 2633539). Its population, policy and result files are SHA256 protected.
V2's existing compiler handles 75/76 queries correctly. Its sole semantic failure is
grammatical `not` being trimmed as NCIt's molecular alias NOT. The target resolver
actually returns AMBIGUOUS for NOT (ALG3 and NR4A2); assigning that lexical role first
allows molecular component trimming to override negation. Hypothesis: assigning a
clinical grammatical operator before entity resolution and respecting it during span
compilation fixes this collision without changing any other scientific interpretation.

## Scope and exact rule

Restore the v2 compilation implementation as the v3 starting algorithm, with its three
E741 variable-name defects corrected before acceptance. Do not change its broader rules.
Add one pre-resolution syntactic mechanism, a GRAMMATICAL_OPERATOR intent span.

1. A standalone case-insensitive grammatical `not` token must be separated from its
   following phrase by whitespace; attached affixes (e.g. NOT-directed), parentheses,
   punctuation and sentence boundaries do not imply this grammatical role.
2. Establish the role when the immediately following whole-word phrase begins with an
   exact clinical alias in the SAME frozen v2 NCIt query-role index (Disease or Syndrome /
   Neoplastic Process, or the existing Finding locator rule). Match from the first word
   to a whole alias endpoint before punctuation, using the existing alias normalization;
   do not perform target lookup to determine this role. Single-word Finding aliases shared
   with nonclinical roles are not clinical anchors, exactly as in v2. Longest matching
   clinical anchor supplies explainability, not disease equivalence or gate compatibility.
3. Record that `not` as GRAMMATICAL_OPERATOR with original offsets/text, NOT operator
   value and named syntactic rule. Mark it consumed BEFORE the ordinary longest-phrase
   vocabulary/entity loop. Entity lookup cannot claim that span. Do not change entity
   resolution itself, its ambiguity, target-affix handling or target facts/compatibility.
4. The existing v2 compiler treats such operator spans as protected tokens in its coherent
   clinical clause. Component trimming cannot remove them. A retained negated clause
   remains its original text and UNRESOLVED normalization metadata; it is never promoted
   to the positive B-cell concept or a positive disease assertion. No negation enforcement
   is added to the asset gate. Caller-supplied indications remain authoritative.
5. Without a clinical syntactic anchor, do not manufacture a grammatical or biological
   role. Leave existing resolver behavior untouched. NOT-directed, NOT protein/target,
   and parenthetical NOT next to explicitly named ALG3/NR4A2 retain existing biological
   alias/candidate behavior. Bare NOT/not and unanchored unknown constructions retain
   ambiguity and existing no-unambiguous-target refusal. No global NOT blacklist.

Share the immutable v2 role-index loader between the grammar prepass and compiler to
avoid duplicate memory/source truth. That extraction is mechanical. Production scope:
intent/parser.py (one prepass), intent/intent.py (one span kind), intent/compiler.py,
intent/indication_compilation.py (v2 algorithm plus operator protection), intent/grammar.py.
Compiled version explicitly identifies compilation v3 and the unchanged role-index SHA.
Existing non-negation intents/retrieval remain byte-identical. Negation cases may change
only operator versus overlapping ambiguous/entity span, corresponding ambiguity terms /
warnings, and indications/version. Their actual resolved targets and other semantics remain
fixed. Unsupported bare queries remain refused for lacking an unambiguous target.

## Frozen population

research/se_indication_compilation_v3/population.json has 103 exact queries:
all 76 v2 queries, 18 expanded negation constructions, six entity contexts, three ambiguous
contexts. Expanded negation covers NSCLC, non-small cell lung cancer, melanoma, psoriasis
and B-cell lymphoma in bare, full-query and longer efficacy queries, plus an implicit
clinical clause, front-position clinical clause and uppercase NOT. Including v2's failed
control there are 19 grammatical-negation queries. Biological controls use actual local
authority behavior: NOT ambiguous ALG3/NR4A2; both explicit symbols resolve uniquely.
Preserving these candidates rather than inventing a unique NOT identity is required.

Fresh baseline intents, compiled problems where compilable, trial queries, blockers,
resolver outcomes, all 16 v2 gate controls, JCAR014 accepted PASS and exact indication
oracle lists are frozen before code. manifest.json seals population/diagnosis and the
unchanged v2 NCIt query-role artifact. Protected hashes cover all other src files and all
v2 research files/policy. H6–H10/H16–H20 are neither read nor resolved nor run.

## Acceptance — every criterion mandatory

| Criterion | Exact measurement |
|---|---|
| C3.1 grammatical precedence | All 19 negation cases produce exactly one GRAMMATICAL_OPERATOR span for the negator, no overlapping TARGET/AMBIGUOUS_TARGET span, no additional resolved target, and the exact original negated indication as one UNRESOLVED span. Resolver-call regression proves the negator is not submitted to entity lookup. |
| C3.2 no global suppression | All six entity-context intents/retrieval/target fields equal baseline, no operator span appears; NOT/ALG3/NR4A2 resolver statuses, rules, candidates and entity IDs equal frozen authority outcomes. |
| C3.3 original population | Exact indication oracle match 76/76, retaining all 75 previously correct cases and fixing general_negated. |
| C3.4 coherent spans / conservative ambiguity | Every positive frozen query matches its exact single original coherent span or legacy concept; provenance text equals query[start:end]. Three ambiguous controls retain the exact baseline intent/blockers and refuse compilation. Negated spans cannot normalize positively. |
| C3.5 leakage | All original 41 negative compilation controls remain empty; expanded entity/ambiguous cases introduce no independent indication leakage. |
| C3.6 benchmarks | TAC01 remains [INDICATION:B_CELL_LYMPHOMA], mint5 remains [], both retain baseline parser/non-indication problem/retrieval. JCAR014 and all 16 gate controls retain byte-identical decisions. |
| C3.7 isolation | Protected source and preserved v2 SHA256s match; every case preserves resolved targets/modality/phase/evidence/status/operator/trial query and all non-indication problem fields, except specified grammatical ambiguity provenance. All 75 non-negation v2 intents are byte-identical. Source diff lies solely in the five allowed production files. No gate/identity/qualification/efficacy/ranking/routing/attribution changes. |
| C3.8 quality | Targeted compilation/intent/indication tests pass; PYTHONPATH=src python3 -m pytest tests/se -q passes with only existing three expected xfails; ruff check src/ is clean. Update only the already-preregistered v2 obsolete lupus-token assertion; no gate test assertion changes. |

## Measurement, stop and adoption

Commit this preregistration before engine changes. The scorer reparses the exact frozen
queries against local authority files only (no acquisition/replay) to exercise pre-resolution
ordering, measures every requirement/provenance/parser/retrieval/problem/resolver/gate
contract, and checks seals. One acceptance record combines C3.1–C3.8 after targeted tests,
the full suite, lint and offline scoring. No patch, threshold/oracle revision or revised rule
after any frozen criterion result. Non-scientific lint/name corrections occur before this
acceptance run; V2 history remains immutable.

If ANY criterion fails, record FAILED_ACCEPTANCE, normally git-revert the implementation,
verify restoration, preserve all failure evidence, update handoff and report the next root
cause. If ALL pass, record ADOPTED, commit results/handoff and read out only the frozen
development compilation cases offline. No reference-visibility acceptance requirement:
the unchanged literal gate can still falsely FAIL correctly compiled disease phrases.
No development score is generalization evidence. Stop before gate implementation; next
separate milestone is INDICATION_GATE_SEMANTICS v1. No live acquisitions or long replays.
H16–H20 remain untouched primary validation; H6–H10 remain unrun secondary validation.

## Adoption result — frozen rules unchanged

Preregistration 5e972d5; implementation 4cdfa8a. C3.1–C3.8 ALL PASS.
Offline exact compilation: 103/103; entire original v2 population: 76/76.
All 19 grammatical negations retain one operator and one original UNRESOLVED clinical
span; no entity lookup receives the consumed negator. Six biological contexts and the
NOT/ALG3/NR4A2 resolver outcomes remain unchanged. Three ambiguous controls stay refused.
TAC01, mint5, JCAR014 PASS and all 16 gate controls preserved. Every protected source /
v2 policy/result hash matches; the source diff is solely the five preregistered files.

Targeted tests 117 passed. Full tests/se 1,672 passed, 3 expected xfails (1,675 collected).
ruff check src/ clean. No post-result source patch or oracle/criterion changes.
Research artifacts include the sealed population, raw score, combined acceptance, test/
lint output and offline diagnostic_compilation_readout.json. All six development disease
queries now produce one coherent requirement; H13 remains UNRESOLVED because its source
locator is Finding-typed. This is compilation correctness, not gate compatibility or
generalization evidence. Negation is retained, but exclusion semantics is not enforced
by the unchanged indication gate. No reference visibility/shortlist score is asserted.

The failed v2 record remains byte-identical and permanently retained. No gate milestone
implementation, live acquisition/replay, H16–H20 exposure or H6–H10 run occurred.
Next separate milestone: INDICATION_GATE_SEMANTICS v1, with its own diagnosis/population/
preregistration before changing same-disease, synonym/subtype, incompatibility or sparse-
evidence UNKNOWN decisions. Stop compilation work here.
