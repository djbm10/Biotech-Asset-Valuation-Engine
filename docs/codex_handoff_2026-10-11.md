# 2026-10-12 TARGET QUERY COVERAGE — FROZEN SUITE; IDENTITY DEPENDENCY REVERTED

Human-PoC recovery remains STOPPED. H6–H10 remain UNRUN. Fresh H21–H25 primary
suite frozen first in **1e1705c**; still unrun/unprobed. No new holdout answers were
used for target development. Parent **TARGET_QUERY_ALIAS_COVERAGE v1** opened in
**e4a5b8d** with 672 authority forms / 276 entities / seven frames / 16 controls.

Diagnosis: IL-4Rα lacks Greek spelling equivalence to installed IL-4R-alpha;
authorities establish approved IL4R (IL4RA is a synonym). Factor XI has an NCIt
protein -> UniProt -> encoded HGNC gene relationship to F11; raw name matching
also finds a measurement concept and is insufficient. Bare F11 is ambiguous
with ZNF160. Unique FXI recognition subsequently loses identity by serializing
only F11, causing discovery compilation refusal. No new aliases implemented.

**TARGET_QUERY_RESOLVED_IDENTITY_PRESERVATION v1: FAILED / REVERTED.**
Preregistration **533c699**, candidate **612c088**, failure **ed33b7d**, revert
**7e8f58e**. Frozen audit: 4,704 parses with zero compared biological-target or
span/provenance differences; 16/16 resolver controls unchanged. FXI compiled five
plans; bare F11 remained ambiguous. New focused tests 14 pass; three hash seeds
produce identical JSON. Full tests: **1,709 pass / 6 fail / 3 existing xfails**;
Ruff clean. Failure I8 includes legacy AK6 serialization, sealed parser-output
contracts and a protected discovery-source hash. I6 independently fails: a
stubbed FDA connector searches `description:"TARGET:GAX1"` rather than GAX1.
No candidate changes after results. Restoration **106 tests pass** and full
src/tests/scripts diff against 533c699 is empty. Human-PoC bytes unchanged.

Evidence: `research/se_target_query_resolved_identity_preservation_v1/`.
Next justified work is an identity-versus-search-surface interface diagnosis,
including every consumer and historical frozen-contract migration semantics,
before preregistering another implementation. The shared canonical_id field
currently serves incompatible roles. Preserve historical failed results; never
change old frozen populations/source hashes to make a successor pass.

NCIt 26.09d public bulk structure survey: 13,032 identifier records; 6,060 satisfy
unique protein-accession/encoded-HGNC structural checks. This is NOT alias
admission; protein-form and P90 synonym semantics still require a contract.
Receipt and extracted assertions are preserved under the parent alias packet.
No target-specific source selection, new source calls at runtime, live runs or
replays. Alias capitalization nondeterminism and the failed prednisone/prednisolone
receipt oracle remain separate and unchanged; C056 remains unchanged.

Source reconciliation: connected GitHub m11-identity-graph was **979ba4d**, an
ancestor 237 commits behind local e4a5b8d when inspected. Checked Biotech Tool
Context Drive material was older (entity-layer design August); targeted handoff/
alias searches found no newer project policy. Newer local October evidence
governs. No private advice/meeting-preparation material was copied.

# 2026-10-12 TREATMENT_COHORT_ATTRIBUTION_REPRESENTATION v1 — FAILED / REVERTED

Policy: `docs/se_policies/treatment_cohort_attribution_representation_v1.md`.
Result: `research/se_treatment_cohort_attribution_representation_v1/result/summary.md`.
Preregistration **bbf52e5**; candidate **56513a2**; scoring freeze **a17d3af**;
formal failure **97a82c0**; normal implementation revert **98ed522**.

R1 failed because the new frozen receipt labels overclaimed receipt of each
alternative in “prednisone or prednisolone.” Both controls were incorrectly
labeled REGIMEN_RECEIPT. The 33 adopted attribution-audit labels were not changed.
R7's exact reader-output comparison also failed on pre-existing hash-dependent
case-variant alias selection (`human_poc.py:389`). Neither failure was patched or
rescored. Supplementary probes preserve all 98 reader decisions across three
hash seeds; only alias capitalization differs. The formal R7 failure stands.

R2–R6, R8 and R9 passed. Full candidate tests: **1,824 passed / 3 existing xfails**;
Ruff clean. Restoration tests: **87 passed**. All **1,707** pre-existing tracked
src/tests/scripts files and all **seven original result files** retain baseline
hashes. Diff of src/tests/scripts against **7103da1** is empty. C056 remains
unchanged, including the existing reader defect. No live runs or replays.

Failed-candidate counts: **15 ownership / 13 receipt / 26 regimen receipt /
44 unresolved**; these are not adopted relationships (two receipt labels fail
grounding). All 65 negative expectations remain non-owning. The previously
unresolved 14 still yield **nine regimen receipt / five unresolved / zero new
ownership**. No human-PoC fact, gate, shortlist membership or ranking changed.

**STOP further human-PoC recovery of these 14 until stronger sources or explicit
structured result attribution exist.** Do not implement another attribution
rule, fix alias ordering, retry this representation, or move to the next root
cause under this milestone. Historical materializer/scorer require the reverted
candidate model; archived source and exact failure evidence are retained.
H6–H10 remain **UNRUN**; H16–H20 remain development evidence.

# 2026-10-12 HUMAN_EFFICACY_TREATMENT_ATTRIBUTION_CONTRACT v1 — DESIGN COMPLETE

Contract: `docs/se_policies/human_efficacy_treatment_attribution_contract_v1.md`.
Packet: `research/se_human_efficacy_treatment_attribution_contract_v1/`.
Captured evidence and annotated controls frozen in **eaf98d2 before evaluation**.

Complete 33-row source/arm/alias audit; 9,359 registry document entries scanned
across the seven frozen runs (includes repeated snapshots). Raw CT.gov arm
labels, intervention links, IDs and aliases exist, but no validated result-arm
bridge rescues any of the 14 unresolved asset-specific claims. Background
references, ordinary-word protocol/acronym matches and candidate trial lists
are explicitly excluded as ownership proof.

Recovery counts for asset-specific efficacy: **0 safely certifiable; 0 blocked
only by identity; 0 recoverable by representation alone; 14 unsupported under
the captured result scope** (12 regimen/pooled-result limitations, two non-
treatment candidates). **9/14 have certifiable receipt-only component edges**;
those do not license regimen efficacy inheritance. Three PI-specific result
strata remain missing. Clinical-content and quantity labels are unchanged.

Grounded contract checks: 65/65 existing negative expectations remain UNKNOWN;
six existing positive attribution reader outputs unchanged; eight structured
and three prior discourse designs match their constraints. Current reader
still falsely accepts C056's first regimen-list item; that parser defect is
not fixed by this design. These are grounded-record checks, not automatic
prose extraction or generalization validation. The 33-row scientific decision
remains 15 scoped positives / 18 UNKNOWN, not a rescore of primary validation.

**Human-PoC behavior is NOT implementation-ready.** Minimum extension:
TreatmentCohortAttribution with separate receipt and efficacy-owner status,
asset/trial/arm/result-group identities, regimen scope, exact provenance,
qualifiers and contradiction reasons. Raw payload retention is already
available; current flat statements/clinical results lack this certificate.
Next proposed separately preregistered milestone:
**TREATMENT_COHORT_ATTRIBUTION_REPRESENTATION v1**, lossless representation only,
without human-PoC promotion, identity changes or routing changes. Not opened.

Stop before implementation. No production/source/tests/scripts changes; all
still match c5bc865. Earlier frozen packets remain hash-identical. H16–H20 stay
diagnostic/development data; **H6–H10 remain UNRUN**. No searches or replays.

# 2026-10-11 HUMAN_EFFICACY_QUANTITY_BINDING_CONTRACT v1 — NOT IMPLEMENTATION-READY

Design: `docs/se_policies/human_efficacy_quantity_binding_contract_v1.md`.
Packet: `research/se_human_efficacy_quantity_binding_contract_v1/` (every-witness
relation table, exact spans/edges, unchanged expected labels, offline results,
and smallest proposed local ResultBinding extension). Design inputs plus three
necessary discourse ambiguity cases were frozen in **120b669 before evaluation**.

**No production change or implementation preregistration.** The offline check
operates on manually grounded semantic records, not a new text extractor.
Clinical-content binding matches all **33/33** labels: four false witnesses
reject; all 19 removed clinical rows, both legacy positives and all eight
controls retain positive content. Full asset-specific binding matches only
**19/33**, preserving **5/19** removed clinical rows, both legacy positives and
all controls, while rejecting the four false numerical cases. The remaining
14 positive-content rows cannot certify their candidate treatment edge under
strict identity/regimen policy (PET30/though, regimen components/pooled arms,
and unresolved compound-treatment identity). Labels remain frozen; this is
not a holdout rescore or a declaration that their clinical outcomes are false.

**Required full-chain acceptance target FAILED; stop before implementation.**
The proposed representation is local typed treatment/cohort/outcome/quantity
spans and relation kinds, with existing fact routing and attribution guards
retained. It is not coded. A minimal grammar/grounder and boundary provenance
are absent from the current flat EfficacyStatement. Implementation readiness
requires reconciling positive clinical-content expectations with asset-specific
emission, plus specifying/test-grounding automatic edges and multi-span limits.
A representation cannot make a conjunction or response stratum into a drug.

Previous efficacy v1 remains REVERTED. Source/tests/scripts still match c5bc865;
v1 and diagnosis-v2 packet hashes are intact. No target/indication/qualification/
identity/modality/ranking/routing changes, searches or replays. False human-PoC
remains first priority. H16–H20 are diagnostic/development data, never future
generalization evidence; **H6–H10 remain UNRUN**.

# 2026-10-11 HUMAN_EFFICACY_BOUNDARY_DIAGNOSIS v2 — DIAGNOSIS ONLY / COMPLETE

Frozen diagnosis: `docs/se_policies/human_efficacy_boundary_diagnosis_v2.md`.
Evidence packet: `research/se_human_efficacy_boundary_diagnosis_v2/` (exact
side-by-side passages, source context, offsets, current/archived predicate
traces, selection and integrity checks).

Compared all **4 false claim witnesses (3 distinct passages)**, all **19 v1
clinical claim/run losses (12 distinct passages)**, both changed legacy
positives, and 8 representative accepted claims. All 33 reproduce PASS under
restored human_poc_v4. All 21 wrongly lost clinical/legacy inputs pass the
archived population check but fail its quantity binder. This isolates the
failed attempt's preservation defect to its clause/quantity-link mechanism.

Supported semantic boundary: an observed clinical-result proposition must
resolve clinical participants, disease outcome, outcome magnitude, and treated
asset/arm roles. Those roles can span clauses and bounded comparison
continuations. Identifiers, assay measurements, modeled entities/parameters,
confidence levels, thresholds, baseline burden and cohort size have different
roles. Clinical-content truth is separate from strict asset/regimen attribution;
existing regimen and nonasset identity concerns are recorded without changing
frozen labels.

**No implementation-ready rule has been preregistered. No efficacy fix or other
root-cause work is authorized by this diagnosis. Stop here.** The failed v1
attempt remains REVERTED; all source/tests/scripts still match c5bc865 and the
prior preregistered/first-result packet hashes remain intact. False human-PoC
remains first priority; a later proposal must make the relational boundary
concrete before changing behavior. H16–H20 remain diagnostic/development data,
not future generalization evidence. **H6–H10 remain UNRUN.**

# Codex handoff — S&E engine, 2026-10-11

## Current outcome — HUMAN_EFFICACY_CONTEXT_SAFETY v1 REVERTED

Clean milestone baseline / primary diagnosis **c5bc865**. Preregistration **38ca6c8**;
implementation **755e9c1**; scorer fixture completion **b1645a3** (before scoring);
failed-result record **5b5eccf**; normal fixture revert **7abb0bc** and implementation
revert **39bcef1**. Production source/tests/scripts are byte-identical to c5bc865;
extractor is again `human_poc_v4`. No post-result behavior or label patch was made.

Frozen rules: `docs/se_policies/human_efficacy_context_safety_v1.md`.
First result: `docs/se_policies/human_efficacy_context_safety_v1_result.md`.
Population, accepted/UNKNOWN examples, independent witness judgments, attempted code,
all first-result scores/quality logs and byte-restoration proofs:
`research/se_human_efficacy_context_safety_v1/` and its `result/` directory.
Failed scorer is retained in the result packet and in b1645a3 history; it is removed
from production scripts by the normal revert. Do not run it against restored source
and overwrite the preserved failed attempt.

**Frozen E1–E10:** E1 PASS; E2 PASS; E3 FAIL; E4 PASS; E5 FAIL; E6 FAIL;
E7 PASS; E8 PASS; E9 FAIL; E10 FAIL. **Decision: FAILED_ACCEPTANCE / REVERTED.**
Both exact H18/H19 false witnesses reject under the attempt, but that is not adoption.
The structural quantity matcher preserves only **143/162** pre-adjudicated clinical
claim/run witnesses, rejects **57/59** independently adjudicated false numerical witnesses,
and preserves **94/96** legacy reader-call outcomes. The frozen population includes
110 distinct admitted passages, 71 new semantic controls, 13 structured controls and
all 96 existing reader inputs captured during the baseline full suite.

Attempt quality: **1,971 passed / 20 failed / 3 expected xfails**, 1,994 total.
Required Ruff checks clean (cache-write sandbox failure retried without cache, no code change).
After normal reversion: all **87** old human-PoC tests pass; restored-source Ruff clean.
Full tests/se was not rerun after reversal: exact source/tests/scripts restoration is
independently verified against the baseline full run of **1,701 passed / 3 expected xfails**.
Every protected policy/source and original selected run hash is unchanged.

Failure details BEFORE any future preregistration:
- Clinical grammar is over-restricted: `10/16 evaluable pts ... ongoing BM CR`, measured
  flare-risk reduction, comparator ellipses and plain patient-count outcome formulations
  lose valid admission. Some receptor/identifier ratios still masquerade as outcome values.
- C056 was baseline PASS but frozen expected UNKNOWN: a first-item regimen attribution
  weakness, outside the intended nonclinical-context scope. Do not retroactively remove
  this failed control or silently change the v1 expectation.
- Earlier `test_indication_gate_semantics_v3.py::test_frozen_compilation_and_source_isolation`
  pins the old human-PoC source hash and rejects any authorized later module change. An
  explicit historical-test lifecycle/ownership decision is needed before a new attempt.
  No old hash oracle was edited or xfailed. Even without that conflict, E6/E9 fail.

**No durable efficacy fix is adopted.** The two original false human-PoC defects remain
unresolved under restored production. Context safety remains the first milestone priority,
but a future v2 needs new diagnosis/preregistration; v1 may never be patched or rescued.
Stop here. No target-alias, qualification, modality, identity, ranking or routing milestone
was implemented. Later causes stay separate: H17/H20 aliases; H19 qualification/PEPTIDE/
discovery; H18 trade names; H16 modality-before-target ordering.

## Primary validation and diagnosis — preserved

Primary H16–H20 validation is **FAIL 0/5**, label commit **eed63eb**, result **ab0f02b**,
diagnosis **c5bc865**. `PRIMARY_VALIDATION_FAILURE_DIAGNOSIS v1` and the 66-entry failure
boundary register remain frozen. H16/H18/H19 INCOMPLETE outputs are valid scoring inputs
under preregistered `--allow-incomplete`; H17/H20 are frozen refusals, not rephrased.
Original interrupted H17/H18 runs remain excluded. **H16–H20 are now exposed diagnostic /
development data, never fresh generalization evidence. H6–H10 remain UNRUN.** No live search,
corpus replay, top20 optimization or later root-cause implementation was launched.

All older “untouched H16–H20” descriptions below are historical states, superseded here.
The adopted indication stack remains intact. The previous outcomes are preserved verbatim.

## Historical handoff — prior outcomes

# Codex handoff — S&E engine, 2026-10-11

## Current outcome — INDICATION_GATE_SEMANTICS v3 ADOPTED (2026-10-11)

Audit **ff2a69b**, preregistration **6b82d42**, implementation **625db7a**,
adoption **dc16bdb**. Clean baseline 8da5e61. **V3-G1–V3-G10 all PASS.**
Production gate bytes exactly match the v2 attempt 148b71e; only the new validation
oracle differs. Psoriasis Vulgaris is UNKNOWN because the pinned NCIt authority has
no disease alias. No special alias, threshold, scientific exception or post-score patch.
Failed v2 and all earlier experiments are permanently preserved below and in history.

Policy: docs/se_policies/indication_gate_semantics_v3.md (sealed preregistration);
result: docs/se_policies/indication_gate_semantics_v3_result.md. Frozen artifacts,
authority proofs, fresh score, review, quality and post-adoption projections:
research/se_indication_gate_semantics_v3/. Scorers:
scripts/score_indication_gate_semantics_v3.py and readout_indication_gate_semantics_v3.py.

Frozen population: 38 references, 655 historical diagnostic indication-only exclusions,
eight original result hashes including TAC01/mint5, all 28 controls (9 authority-proved
PASS / 19 UNKNOWN), JCAR014, and all 103 compilation-v3 controls. Direct preimplementation
authority audit proves each positive identity/synonym/path or accepted B-cell rule.
Every control correct; all 103 compiled outputs exact; all historical artifact hashes
and compiler hashes unchanged. No non-indication source/facts/decision/policy changed.

Rules: PASS from unique frozen disease ID/synonym, observed-descendant/requested-parent
authority path, or accepted B-cell positive rule. Reverse direction unsupported -> UNKNOWN.
One compatible record suffices after existing conflict/staleness guards. Missing,
ambiguous, incomplete, unrelated or unresolved evidence -> UNKNOWN. Registry evidence
never establishes indication FAIL. Negative-query semantics remain limited/deferred.
INDICATION_NEGATIVE_EVIDENCE_CONTRACT v1 is deferred, not implemented.

Fresh targeted **86 passed**. Full tests/se **1,701 passed / 3 expected xfails**,
1,704 total, zero failures. **ruff check src/ clean.** Fresh sample review: 124 witnesses,
20 distinct pairs, zero unsupported; expanded post-adoption review: all 27 distinct new
PASS pairs across 128 diagnostic new PASS assets, zero unsupported.

References **0 PASS / 5 UNKNOWN / 33 FAIL -> 18 PASS / 20 UNKNOWN / 0 FAIL**;
visible/rankable **5/38 -> 38/38**, all 33 recovered. Diagnostic indication-only
exclusions **655 -> 0**. TAC01 all 157 prior PASS preserved; 324 unsupported FAIL -> UNKNOWN,
membership **545 -> 747**, top-20 order changed; JCAR014 PASS. mint5 unchanged:
membership **244 -> 244**, top-20 order unchanged. Ranking policy unchanged.

Six development top-20 lists: confirmed 30 TARGET_UNKNOWN_FILL, 10 NON_PRODUCT,
2 DUPLICATE, 35 RELEVANT; **41 new rows UNLABELED**. Precision bounds 29.2%–63.3%,
not a point estimate. Exact per-query bounds/rows in diagnostic_readout.json. Full
new blind labels are needed to determine the dominant remaining shortlist root cause;
do not infer junk/off-target status from unknown evidence or start later milestones.
These are development data, not generalization evidence.

**The indication stack is sufficiently finalized for a separate untouched validation
stage. H16–H20 remain completely untouched; H6–H10 unrun.** No targets, reference
products or outputs from those suites were inspected; no live acquisition/replay run.
Stop before holdout execution. Next: separately authorize/plan primary validation,
with terminal commands only when requested; do not automatically run or inspect it.

## Preserved failed outcomes

## Current outcome — INDICATION_GATE_SEMANTICS v2 REVERTED (2026-10-11)

User resolved diagnosis 4cf8485: no negative-evidence contract now; current registry
indications may establish positive PASS or UNKNOWN only. That decision remains valid.
Preregistration **43c7cc5**, implementation **148b71e**, failure record **5a4940e**,
normal revert **518185c**. Source and tests are byte-identical to 4cf8485; adopted
compilation v3 stayed frozen throughout. No post-result behavior/test/control patch.

Policy: docs/se_policies/indication_gate_semantics_v2.md. Population, authority manifest,
score, manual review, quality logs, failure and restoration:
research/se_indication_gate_semantics_v2/. Scorer preserved at
scripts/score_indication_gate_semantics_v2.py (requires the failed implementation to
reproduce; checkout its commit plus the preserved scorer, not restored production).

Frozen: 38 references, all 655 historical diagnostic indication-only exclusions,
eight original run hashes including TAC01/mint5, original 16 controls plus 12 new
controls, JCAR014 NOS and compilation-v3 source/query preservation.
**V2-G1 PASS; G2 PASS; G3 FAIL; G4 PASS; G5 PASS; G6 PASS; G7 PASS;
G8 PASS; G9 PASS; G10 FAIL.** 27/28 semantic controls correct.
Failure: psoriasis_synonym expected PASS for Psoriasis Vulgaris, but no alias exists
in the selected frozen NCIt disease names (nor disease/finding query roles). The
implementation correctly preserved insufficient normalization as UNKNOWN; however,
the frozen PASS criterion failed. The positive-control authority premise was not
verified before preregistration. Do not amend, retroactively rescue or adopt v2.

Targeted **85 passed / 1 failed**. Full tests/se **1,700 passed / 1 failed /
3 expected xfails** (1,704 collected), sole failure psoriasis_synonym. Attempt and
restored-source Ruff clean. Full suite not rerun after normal reversion; exact source/
tests restoration independently verified. Test logs retain harmless cache-write warnings.

Failed-development readout: references **18 PASS / 20 UNKNOWN / 0 FAIL**, all 33 former
indication-only excluded references free of other FAIL gates (gate-rankable; shortlist
membership/order not recomputed). Diagnostic indication-only exclusions **655 -> 0**;
128 newly PASS diagnostic assets. Manual sample: 124 witness records, 20 distinct
disease pairs, zero unsupported positive claims. TAC01 preserves 157 old PASS,
324 unsupported FAIL -> UNKNOWN, no new PASS; JCAR014 control PASS. mint5 unchanged.
These are failed-attempt observations, not adoption or generalization evidence.

After revert, durable counts remain **0 PASS / 5 UNKNOWN / 33 FAIL** references and
**655** diagnostic indication-only exclusions. Historical visible references 5/38;
top-20 diagnostic pollution remains 57 TARGET_UNKNOWN_FILL, 40 NON_PRODUCT_GENERATION
plus one QUALIFICATION_MISS, four duplicates. No post-adoption precision/membership/
order readout applies. Ranking and all other policy layers stayed unchanged.

**Next:** independently verify authority coverage for every positive control before
a NEW gate preregistration. No invented synonym or post-result expectation change.
Keep insufficient normalization UNKNOWN. INDICATION_NEGATIVE_EVIDENCE_CONTRACT v1
is deferred: claim type, identity, indication, negative relation, authority/provenance,
review/confidence and contradictions must be designed separately; nothing added here.

The indication stack is **NOT finalized** for primary validation. **H16–H20 remain
completely untouched; H6–H10 unrun.** No live acquisitions/replays launched. No user
terminal run is justified now. All prior failures and diagnosis remain preserved below.

## Preserved diagnosis and previous outcomes

## Current gate milestone — DIAGNOSIS ONLY, evidence contract unresolved (2026-10-11)

Production remains adopted compilation v3 at **ebbb554**. No gate code or query
compilation changed. Diagnosis and baseline freeze:
docs/se_policies/indication_gate_semantics_v1_diagnosis.md and
research/se_indication_gate_semantics_v1/ (manifest, provenance audit, baseline population).
Frozen: 38 references, 655 historical diagnostic indication-only exclusions, prior
16 semantic controls, TAC01/mint5, compilation readout and all source hashes.
Current reference indication decisions: **0 PASS / 5 UNKNOWN / 33 FAIL**.

All 9,127 indication facts across eight existing runs are unreviewed registry first-
condition strings, not exhaustive asset inventories or negative incompatibility
assertions. Different disease evidence cannot establish asset-level incompatibility.
G3 cannot be made nonvacuous from these facts without a new negative-evidence contract.
Stop under the user's unresolved scientific/architecture exception: decide whether
to authorize an explicit reviewed, claim-backed asset-level incompatibility assertion
contract, or separately defer FAIL/G3. No preregistration or acceptance score exists
yet; do not treat this diagnosis as an adopted/reverted experiment.

Next: resolve that contract, then preregister and execute gate semantics. All prior
failures and compilation v3 remain preserved. **H16–H20 completely untouched;
H6–H10 unrun.** No live acquisition/replay or terminal run is needed now.

## Preserved adopted compilation result

## Current outcome — INDICATION_REQUIREMENT_COMPILATION v3 ADOPTED (2026-10-11)

Clean baseline **2633539**, preregistration **5e972d5**, implementation **4cdfa8a**.
All frozen criteria C3.1–C3.8 PASS. Entire v2 population 76/76; expanded population
103/103. All 19 grammatical-negation controls retain the negator in one coherent
UNRESOLVED disease span. Parser consumes that grammatical operator before entity
lookup. Compiler preserves it against molecular component trimming and positive concept
normalization. No global NOT suppression: six biological contexts and actual resolver
NOT ambiguity (ALG3/NR4A2) are unchanged; explicit ALG3/NR4A2 remain uniquely resolved.
Three syntax-insufficient controls retain ambiguity and existing refusal.

Scope: compilation only. Production changes are the five preregistered intent files:
parser.py prepass, intent.py GRAMMATICAL_OPERATOR, compiler.py coherent construction,
indication_compilation.py (v2 algorithm plus operator protection), grammar.py (shared
frozen query-role loader and syntactic rule). No downstream gate/compatibility/identity/
qualification/modality/efficacy/ranking/routing/attribution changes. All protected source
hashes and every v2 research/policy hash remain fixed. No patch after acceptance results.

Targeted tests **117 passed**. Full tests/se **1,672 passed, 3 expected xfails** (1,675
collected); `ruff check src/` clean. TAC01 and mint5 retain semantic equivalence;
JCAR014's accepted PASS and all 16 gate controls are byte-identical. Failed v2/v1 history
below is permanently preserved; v3 does not amend or retroactively adopt either attempt.

Policy: docs/se_policies/indication_requirement_compilation_v3.md. Frozen population,
manifest, authority diagnosis, exact scorer output, combined acceptance, quality logs and
offline diagnostic readout: research/se_indication_compilation_v3/. Offline scorer:
scripts/score_indication_compilation_v3.py. Correct compilation for H2/H4/H11–H14:
non-small cell lung cancer, ulcerative colitis, non-small cell lung cancer, paroxysmal
nocturnal hemoglobinuria, hidradenitis suppurativa, multiple myeloma, respectively.
Each is one coherent requirement, with no target/mutation/format residual requirements.
H13 source Finding remains unresolved normalization, rather than erased or declared disease.

Limits: the unchanged gate still compares most literal disease requests exactly; synonym,
case/spacing, subtype and incomplete indication evidence remain downstream defects.
Negation is represented correctly but the gate does not enforce exclusion semantics.
No claim of recovering the 33 indication-excluded references or improving shortlist
precision/recall; no development result is generalization evidence. The readout measures
compilation only and does not recompute product/ranking outcomes.

**Next separate milestone: INDICATION_GATE_SEMANTICS v1.** Diagnose/preregister its
population and criteria before implementing same-disease/synonym/subtype PASS, positive
incompatibility FAIL, sparse/incomparable evidence UNKNOWN, and incomplete NCIt typing.
That milestone is NOT implemented here. Qualification/routing/target milestones remain
deferred. **H16–H20 remain completely untouched; H6–H10 remain unrun.** No live acquisition
or long replay launched. No terminal run is needed now; stop before gate implementation.

## Preserved prior outcomes

## Current outcome — INDICATION_REQUIREMENT_COMPILATION v2 REVERTED (2026-10-11)

Preregistration **30bfdbe**, implementation **f46dd76**, failure record **2b0a80e**,
normal git revert **2e297c6**. The failed indication-semantics v1 history below remains
authoritative and preserved. Worktree source/tests/scripts equal clean baseline 7f09c26.

Frozen population: 76 exact queries (six diagnostic queries H2/H4/H11–H14, TAC01,
mint5, every v1 semantic/leakage control and failure, JCAR014, and general constructions),
35 positive and 41 negative compilation controls, 16 unchanged gate controls, all protected
source hashes. Frozen NCIt roles locate query spans only; no new disease gate semantics.
See docs/se_policies/indication_requirement_compilation_v2.md and
research/se_indication_compilation_v2/ (manifest, population, scorer output, failure and
restoration records). Acceptance: C1 FAIL, C2 PASS, C3 PASS, C4 FAIL, C5 PASS,
C6 PASS, C7 PASS, C8 FAIL. Exact query controls: 75/76.

The attempt coherently compiled all six diagnostic disease phrases and removed their
nonclinical residual leakage; TAC01, mint5 and JCAR014 PASS remained equivalent. All
parser/retrieval/non-indication fields, 16 gate decisions and protected source were fixed.
However, frozen `not NSCLC` produced `NSCLC`. Existing parser marks `not` ambiguous
between TARGET:ALG3/TARGET:NR4A2; NCIt also lists NOT as a molecular alias. Independent
component trimming overrode grammatical negation and the intended soft boundary. This
can replace a negative disease request with a positive assertion. No post-result patch.

Attempt targeted tests: 114 passed / 2 failed. Full tests/se: 1,669 passed / 2 failed /
3 expected xfails (1,674 collected). Ruff failed with 3 E741 violations. After normal
reversion: 108 indication/intent tests pass, ruff check src/ clean, exact byte restoration
verified. Full suite was not rerun after reversion; the failed-attempt suite is retained.

No durable diagnostic improvement: all requirements/results return to baseline. Reference
visibility remains the frozen 5/38, with 33 indication-only exclusions; 57 TARGET_UNKNOWN_FILL
and 40 NON_PRODUCT_GENERATION plus one QUALIFICATION_MISS top-20 rows remain recorded.
No post-adoption remeasurement applies because this milestone was reverted.

Next principled option: NEW compilation-only preregistration with query grammatical
operator/span binding preceding molecular-role trimming and conservative retention of
overlapping lexical roles. Do not retry v1's broad compilation+gate implementation.
INDICATION_GATE_SEMANTICS v1 is deferred and has NOT been preregistered/implemented:
compilation must first be adopted. Qualification/routing/target milestones remain deferred.
H16–H20 remain completely untouched. No live acquisition/replay launched; no user
terminal run is required at this point.

## Preserved previous outcome

## Current outcome — INDICATION_REQUIREMENT_SEMANTICS v1 REVERTED (2026-10-11)

The operator authorized v1. It was preregistered at `0aefe85`, implemented at `93c1f83`,
scored/recorded FAILED_ACCEPTANCE at `8f466b4`, and reverted normally at `d8f5023`.
Engine source and tests are byte-identical to `c70461e` (engine `f0e90e6`).
Worktree remains `/home/djmann/projects/bve-b8`, branch `m11-identity-graph`.

Authoritative record: `docs/se_policies/indication_requirement_semantics_v1.md`.
Frozen artifacts: `research/se_indication_semantics_v1/`. 38 reference products, 33
indication-only reference exclusions, 655 indication-only excluded assets, 16 semantic
controls, 18 non-disease terms, and TAC01/mint5 accepted artifacts were frozen before code.

Criteria: I1 FAIL; I2 PASS; I3 PASS; I4 PASS; I5 FAIL; I6 FAIL; I7 PASS; I8 FAIL.
Attempt tests/se: 1,653 passed, 10 failed, 3 expected xfails. Attempt and restored ruff
check src/ are clean. After reversion, 108 indication/intent tests passed. The full suite
was not rerun after reversion; source/tests restoration is verified byte-for-byte.

The attempt made 31/33 excluded references visible, but 21 through absent requirements,
only 10 through proper PASS decisions; Crovalimab and zilucoplan still FAIL. TAC01 lost
JCAR014's accepted PASS (Not Otherwise Specified treated as negation), with 14/20 order
positions changed; mint5 stayed invariant. All non-indication data/decisions stayed fixed;
23 positive condition strings reviewed, no false positive indication assertion found.

Failures to diagnose BEFORE a newly preregistered v2:
- NSCLC crosses the parser's AMBIGUOUS_TARGET `cell` span; residual-only grouping erases
  the disease requirement. Recover full disease spans without changing target parsing.
- NCIt C128429 Hidradenitis Suppurativa is typed Finding; the disease-type filter omits it.
  Use an authority taxonomy with explicit indication semantics, not all Findings.
- Different observed diseases do not establish an exhaustive drug indication history:
  Crovalimab has only aHUS facts, zilucoplan only COVID-19 in the frozen rows. Preregister
  the positive incompatibility evidence needed under incomplete/open-world coverage.
- Legacy B-cell lymphoma has a broad/subtype name ambiguity (C188021/C3457), and disease
  qualifiers cannot be handled by an unrestricted negation-token veto.

No behavior patch after results. Failed attempt remains in history. No durable diagnostic
improvement: frozen baseline remains 5/38 visible references, 33 indication-excluded,
57 TARGET_UNKNOWN_FILL, 40 NON_PRODUCT_GENERATION plus 1 QUALIFICATION_MISS top-20 rows.
No post-adoption remeasurement applies. Do not start qualification/routing/target milestones.
**H16–H20 remain entirely untouched. Do not run or inspect them.** No long live acquisition
or benchmark replay was launched. Next action: a NEW v2 preregistration resolving these
indication semantics failures; untouched validation is premature until adoption.


Start here, then read `docs/se_handoff_state.md` for the older context. That file predates
the target-recognition work, so this file wins wherever the two disagree.

## 1. Where you are

- **Worktree:** `/home/djmann/projects/bve-b8`. This is **not** the main repo checkout at
  `~/projects/biotech-asset-valuation-engine`.
- **Branch:** `m11-identity-graph`. **HEAD:** `a508831`, the diagnosis commit (or later).
  The tree is clean apart from this file.
- **Engine code version:** `f0e90e6`. Every later commit is docs, labels or research scripts
  only.
- **Environment:**
  - conda env `biotech-env`;
  - `PYTHONPATH=/home/djmann/projects/bve-b8/src` when running anything from this worktree
    (an editable install may point at another worktree);
  - tests: `python -m pytest tests/se -q`, last run 1,663 passed, 3 xfailed;
  - lint: `ruff check src/`.
- **Live runs:** `bve-se-search` with `--source-index ~/se_runs/aacr_probe5/source_index.yaml`,
  output under `~/se_runs/<name>/`.

  **Never launch live runs or TAC01/mint5 replays yourself.** Background jobs are
  memory-reaped. Ask the operator to run them in their own terminal, giving the exact
  command.

## 2. Non-negotiable workflow rules (operator)

1. Every milestone gets a preregistration doc in `docs/se_policies/<NAME>_v<k>.md`, which
   freezes the population and acceptance criteria. It is committed **before** any
   implementation.
2. Adopt or revert strictly. Never patch after results, and never weaken criteria to fit an
   implementation. A failed version is recorded as FAILED_ACCEPTANCE, reverted, and
   re-preregistered as v<k+1>.
3. No query-specific, product-specific or name-list exclusions.
4. Do **not** tune ranking. The order in `reporting/shortlist._rank_key` is frozen.
5. Never combine distinct root causes in one implementation.
6. UNKNOWN is preferable to a false target. Preserve every adopted TAC01/mint5 identity,
   target, modality and efficacy rule.
7. Commits use conventional messages via `git commit -m ... -m ...`. A hook blocks
   `--no-verify` and the `printf | git commit -F` pattern. End every commit message with
   `Co-Authored-By:` attribution.

## 3. Validation sets and their status

| Set | Doc | Status | Use |
|---|---|---|---|
| TAC01, mint5 | (benchmarks) | **FROZEN** | Only to confirm a fix for an independently found bug |
| H1–H5 | `heldout_validation_suite_v1.md` | Run; FAIL 0/5 | Diagnostic only, never generalization evidence |
| H6–H10 | `heldout_validation_suite_v2.md` | **Unrun**, partially exposed | Secondary confirmation only |
| H11–H15 | `heldout_validation_suite_v3.md` §5 | Run at f0e90e6; FAIL 0/5; target recognition 4/5 exact | Now **diagnostic** only |
| **H16–H20** | `heldout_validation_suite_v4.md` (`eaace55`) | **Untouched**: never run, never resolved, no outputs inspected | **Primary** validation for the next shortlist fix |

H16–H20 must stay untouched. Do not run their queries, do not resolve their targets, and do
not look up their reference products in any run output.

Rubric, used by every suite:
- labels: RELEVANT, WRONG_TARGET, DUPLICATE, NON_ASSET, UNVERIFIABLE;
- blind labels are committed before scoring;
- per query: P@20 ≥ 0.70, Recall@all ≥ 0.60, NON_ASSET ≤ 1, DUP ≤ 2, false human-PoC = 0;
- suite: PASS at ≥4/5.

Scorers live at `scripts/score_heldout_suite_v{1,3}.py`, with labels in
`research/se_heldout/labels_v{1,3}.json`.

## 4. What was just finished

- **TARGET_AFFIX_RECOGNITION v5 ADOPTED** (`f0e90e6`): `anti-X` and `X-directed` parse exactly
  as bare `X`.
- **DUAL_TARGET_SEPARATOR_SAFETY ADOPTED** (earlier).
- **HELDOUT v3 (H11–H15) scored** (`b0580ec`): FAIL 0/5, with no false human-PoC.
- **SHORTLIST_NONPRODUCT_OFFTARGET_DIAGNOSIS v1** (`a508831`), diagnosis only. Read
  `docs/se_policies/shortlist_nonproduct_offtarget_diagnosis_v1.md`. Data is in
  `research/se_shortlist_diag/`.

Key findings:
- **All 38/38 reference products in H2, H4 and H11–H14 were discovered, and 33 are
  EXCLUDED solely by `strategy.indication` FAIL.**
  - `ontology/indications.py` knows a single concept (B_CELL_LYMPHOMA).
  - `intent/compiler.residual_indications` turns every other disease phrase into single-word
    literals, e.g. `["non-small","lung","cancer"]`.
  - It also includes non-disease words such as `inhibitors`, `G12C` and `complement`.
  - These literals are compared by exact `IN` against whole registry condition strings. So
    any asset *with* indication evidence FAILs, while evidence-less names stay UNKNOWN and are
    shown.
- The 102 bad top-20 rows break down as:

  | Class | Rows |
  |---|---|
  | D TARGET_UNKNOWN_FILL | 57 |
  | A NON_PRODUCT_GENERATION | 40 (all qualify via `DIRECT_APPROVED_NAME` = a ChEMBL molecule name) |
  | B QUALIFICATION_MISS | 1 (methane; the NCIt veto sits below the ontology route) |
  | H DUPLICATE | 4 (trade name vs INN) |
  | C false target PASS, E known incompatible, G discovery miss | 0 each |

- F (ranking) has 3 relevant rows displaced because modality precedence comes before the
  target decision. This is recorded only.
- **Requiring target PASS is unsafe.** 5 of the 15 RELEVANT rows are target-UNKNOWN (all of
  H4's TL1A hits, plus gumokimab and netakimab).
- **An entity link is not a junk discriminator.** 5 of the 15 RELEVANT rows also have none.
- **H15_EXTRA_TARGET_DIAGNOSIS v1** is recorded but not fixed (`h15_extra_target_diagnosis_v1.md`):
  - the LDLR alias "familial hypercholesterolemia" turned the disease phrase into a target;
  - the H15 indication became `["inhibitors","homozygous"]`.

## 5. Historical v1 recommendation (superseded by the outcome above)

The diagnosis recommends this milestone as having the highest precision benefit and the
lowest false-negative risk. The operator subsequently authorized it; v1 was attempted and reverted as recorded above.

Proposed shape:
- Disease phrases compile to concepts, matched against registry conditions by
  name-or-subtype. This generalizes the adopted B-cell-lymphoma mechanism in
  `ontology/indications.py` and `gates/evaluator.evaluate_indication`.
- Non-disease residual words are no longer indication literals. `residual_terms` must stay
  untouched, because they drive trial retrieval (see the docstring of `residual_indications`).
- A phrase that cannot be matched yields **UNKNOWN, never FAIL**.
- The vocabulary must come from an authority, not hand-picked per query. A hand-picked
  list would be tuning on diagnostic data.
- Preregister:
  - a population of query disease phrases and registry conditions that is **not** drawn from
    H11–H20;
  - acceptance criteria that include the off-indication admission risk;
  - TAC01/mint5 parity;
  - `tests/se` green.

  Then validate on H16–H20, with the operator running it live.

Later milestones, each separate, in this order:
1. NONPRODUCT_QUALIFICATION v1 (A+B). Use an authority substance-type discriminator above
   the `DIRECT_APPROVED_NAME` route. No name lists, no entity-link rule.
2. TARGET_UNKNOWN_SHORTLIST_ROUTING v1 (D). Re-measure after the indication fix first.
3. TARGET_AUTHORITY_COVERAGE v1.
4. TRADE_NAME_IDENTITY v1 (H).
5. H15_EXTRA_TARGET_DIAGNOSIS.
6. D-var (KRAS G12C) and D-iso (Claudin 18.2).
7. Merged-survivor display-name cleanup.

## 6. Code map (only what you need next)

| Path | Role |
|---|---|
| `src/bve/se/intent/parser.py` | Query to spans. Contains the affix and separator rules (adopted; do not touch) |
| `src/bve/se/intent/compiler.py` | `residual_indications` builds `strategic_gap.indications` |
| `src/bve/se/ontology/indications.py` | Indication concept vocabulary (frozen by `indication_gate_semantics.md`; a change is declared) |
| `src/bve/se/gates/engine.py` (~L227) and `gates/evaluator.py` (`evaluate_indication`, `evaluate_requirement`) | The indication gate |
| `src/bve/se/discovery/asset_qualification.py` | `qualification_reason` (route order) and `qualification_veto` |
| `src/bve/se/pipeline.py` (~L915–1030) | Qualification, low-support routing, gating |
| `src/bve/se/reporting/shortlist.py` | `build_shortlist`, `_rank_key` (frozen) |
| `scripts/score_heldout_suite_v3.py` | Template for a v4 scorer (swap REFS/INTENDED/paths/labels) |

## 7. Known caveats

- Ruff flags style issues (E702, E741, F401) in `research/se_shortlist_diag/*.py`. They are
  research scripts outside the `src/` lint scope, and they reproduce their committed JSON
  outputs.
- Under the frozen matching rule, suffixed INNs (`pozelimab-bbfg`) don't match the bare
  reference. This is recorded as-is in v3 §5 and carried into v4 §2.
- In the final report of the previous session, the diagnosis commit hash was misquoted as
  "4a0e1c2…". The correct hash is **`a508831`**.
