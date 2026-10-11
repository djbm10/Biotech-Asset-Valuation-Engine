# INDICATION_REQUIREMENT_SEMANTICS v1

Status: PREREGISTERED, 2026-10-11. Baseline c70461e (engine f0e90e6).
Ranking is frozen. No live acquisition or replay is authorized for this evaluation.

## Diagnosis and hypothesis

The existing compiler emits residual word literals except for B-cell lymphoma. Exact
whole-condition IN comparison falsely excludes 33/38 reference products. Missing
indication evidence remains UNKNOWN, creating shortlist fill. Disease concept compilation
and conservative ontology comparison should recover these false FAILs without inventing
compatibility. No qualification, target, identity, modality, efficacy or routing change.

## Frozen population and source

`research/se_indication_semantics_v1/population.json` freezes the six existing diagnostic
results, their SHA256s, problems, decisions, all 38 reference asset IDs, and all 655 assets
whose sole FAIL is strategy.indication (444/2/27/62/33/87 for H2/H4/H11/H12/H13/H14).
It also freezes TAC01/mint5 protoid_v1 results. Existing evidence only; no discovery rerun.
`controls.json` freezes 16 semantic cases and 18 non-disease terms, including independent
same/synonym/subtype, explicit incompatible, broader, unrecognized and B-cell controls.
`manifest.json` seals these files and the disease vocabulary.

NCIt 26.08e flat source is already locally available. The committed source-derived
`ncit_diseases.json` includes ALL Disease or Syndrome/Neoplastic Process records, names
and disease parent edges, with source SHA256. This is a typed view of the existing NCIt
authority, not a diagnostic-specific vocabulary. No names added manually. No use of H16–H20.

## Exact rule

Normalize case/punctuation into space-separated alphanumeric words. Recognize only
whole-word disease aliases in the frozen NCIt typed vocabulary; multiple codes for a name
are ambiguous. Query compilation consumes maximal, non-overlapping unique disease aliases
within existing adjacent RESIDUAL spans. A disease alias embedded in a longer residual
phrase stays one concept. Other residual words are not indication requirements. Retrieval
residuals and parser spans are unchanged. Caller-supplied indication names are resolved
by the same evaluator; unrecognized requests return UNKNOWN, even for identical text.

Concept IDs are NCIt codes with INDICATION:NCIT: prefix. Existing B-cell request surfaces,
positive subtype terms, explicit disjoint terms and broader terms keep their priority.
Unrecognized B-cell conditions become UNKNOWN rather than the old default NO.

For NCIt requests, a unique observed disease alias names the same code or a descendant:
PASS. An ancestor, ambiguous alias, missing or unrecognized evidence, or relationship
that cannot be established: UNKNOWN. A fully recognized whole-condition diagnosis can
be incompatible (FAIL) only if neither concept is ancestor of the other and no disease
descendant in the frozen graph belongs to both. An embedded alias can establish a
positive match, but cannot establish incompatibility for unexplained surrounding text.
Conditions containing explicit negation tokens `not`, `without`, `excluding`, `negative`
are incomparable (UNKNOWN). No unrestricted substring or fuzzy matching.
Across requested alternatives and observed conditions: any PASS wins; otherwise any
UNKNOWN yields UNKNOWN; FAIL only if all comparisons are positively incompatible.
Non-string evidence is UNKNOWN. Preserve gate missing/conflict precedence.

Explainability retains requested concept ID, authoritative source/version, observed fact
IDs and original condition facts. Rationale states the semantic comparison and status.

## Acceptance and measurement (all mandatory)

I1: All 33 previously excluded frozen reference asset IDs receive PASS or UNKNOWN for
indication, and remain visible/rankable (no other FAIL or low-support change).
I2: All four explicit incompatible controls remain FAIL (NSCLC/UC both directions and
B-cell/Hodgkin and B-cell/T-cell). This forbids blanket FAIL-to-UNKNOWN conversion.
I3: All five same/synonym/subtype positive controls are PASS.
I4: All seven uncertainty controls are UNKNOWN, including unrecognized identical text.
I5: None of the 18 frozen non-disease terms compile an indication requirement. Each of
the six diagnostic disease phrases compiles at least one coherent disease concept,
never residual word literals; query residuals/trial retrieval remain unchanged.
I6: TAC01 keeps all accepted indication PASSes, broader UNKNOWNs and explicit disjoint
FAILs; no new scientifically false PASS. TAC01 and mint5 top-20 asset IDs/order unchanged.
mint5 requirements, all decisions and dispositions identical. No benchmark tuning.
I7: Offline evaluation replaces only indication decisions against identical frozen facts;
every other decision and all candidates, qualification, identity, target, modality, efficacy,
trial attribution, low-support IDs and search attempts remain byte-identical. Source diff
is limited to indication ontology, compiler, evaluator and indication evaluator dispatch.
Ranking and shortlist code unchanged. No new positive match without authoritative
same/subtype or existing B-cell match evidence. Review every newly PASS condition string.
I8: Targeted regression tests pass; PYTHONPATH=src python3 -m pytest tests/se -q passes
except existing expected xfails; ruff check src/ is clean.

Offline scorer checks input hashes, re-evaluates ONLY indication against frozen evidence,
recalculates dispositions from unchanged other decisions and builds the frozen shortlist.
It emits every criterion, decision transitions, reference visibility and top-20 diagnostics.
Do not infer generalization from these development queries. Report TARGET_UNKNOWN_FILL
and NON_PRODUCT remaining using frozen row labels for old rows; newly entering rows are
classified from evidence, and ambiguous product types are reported unresolved rather than
invented. Record all newly PASS condition strings with authoritative code/relationship.

## Stop/revert

Any failed criterion: record FAILED_ACCEPTANCE; revert implementation with normal git
revert; retain preregistration, frozen source/population, scorer and results in history.
No patches after acceptance results, threshold changes or history rewriting. Revised
approach needs a new preregistration. Adopt only after every criterion passes, then update
handoff and report diagnostics. H16–H20 remain untouched until finalization; operator runs
any subsequent long live validation, using exact frozen commands only after adoption.


## Result — FAILED_ACCEPTANCE, 2026-10-11

Preregistration `0aefe85`; unchanged implementation `93c1f83`. Frozen offline results:
`research/se_indication_semantics_v1/{score,acceptance,condition_review,quality_gates,failure_diagnosis}.json`.
The offline scorer is `scripts/score_indication_semantics_v1.py`; the read-only failure
diagnoser is `scripts/diagnose_indication_semantics_v1_failure.py`. These evaluate the
historical implementation, not the restored HEAD. Neither launches acquisition or replay.

| Criterion | Result | Evidence |
|---|---|---|
| I1 | FAIL | Only 10/33 receive PASS and are visible. 21 become visible through removal of the requirement (invalid recovery); Crovalimab and zilucoplan still FAIL. Attempt visibility 31/33, not adoption evidence. |
| I2 | PASS | 4/4 frozen explicit incompatibility controls FAIL. |
| I3 | PASS | 5/5 same/synonym/subtype controls PASS. |
| I4 | PASS | 7/7 uncertainty controls UNKNOWN. |
| I5 | FAIL | 18/18 non-disease terms do not leak, but H2/H11/H13 compile no disease requirement. H4/H12/H14 compile coherent NCIt IDs. |
| I6 | FAIL | TAC01 loses JCAR014's accepted indication PASS; 14/20 rank positions change. mint5 requirements, decisions, dispositions and top-20 order are preserved. |
| I7 | PASS | Frozen input hash checks pass; all non-indication decisions and data remain identical. Source diff touches only the four preregistered indication files. All 23 newly positive condition strings reviewed; no false positive disease assertion found. No ranking code changed. |
| I8 | FAIL | Targeted 39 passed / 9 failed. Full tests/se: 1,653 passed / 10 failed / 3 expected xfails, 1,666 collected. ruff check src/ is clean. |

Several old test failures memorialize literal fallback, which this milestone intended to
replace. They were not rewritten after results. There are also genuine B-cell regression
failures; independently I1, I5 and I6 fail, so this result cannot be adopted even if old
literal assertions were updated. No behavior patch or threshold change was made.

### Failure mechanisms observed, not patched

1. H2/H11: the parser correctly preserves an ambiguous `cell` span. Residual-only phrase
   grouping cannot reconstruct `non-small cell lung cancer` across that boundary. Both
   requirements disappear. This needs whole disease-phrase handling in the compiler
   without changing target recognition or query retrieval.
2. H13: NCIt labels Hidradenitis Suppurativa (C128429) as `Finding`, not `Disease or Syndrome`.
   The blanket semantic-type filter omits a real disease. Disease typing must follow an
   authority taxonomy with explicit semantics; including all findings would be unsafe.
3. Crovalimab's frozen indication facts contain only aHUS; zilucoplan's only COVID-19.
   Different known diagnoses do not prove an asset's indication inventory is exhaustive.
   The v1 distinct-concept rule still turns incomplete coverage into FAIL. A revised rule
   must preregister what positively establishes incompatibility under open-world evidence.
4. `b cell lymphoma` is ambiguous between C188021 (B-cell malignant neoplasm) and C3457
   (B-cell NHL), weakening legacy unrelated-disease FAILs. An established legacy concept
   needs a source-anchored semantic mapping, not unqualified label lookup.
5. The broad negation token rule mistakes `Diffuse Large B-Cell Lymphoma, Not Otherwise
   Specified` for negation, changing JCAR014 PASS to UNKNOWN. Disease-scoped negation,
   rather than arbitrary tokens anywhere in a condition, is required.

### Diagnostics and stopping decision

No durable improvement: implementation reverted normally. Frozen diagnostic baseline
therefore remains 5/38 visible references, 33 indication-only exclusions; 57
TARGET_UNKNOWN_FILL rows and 40 NON_PRODUCT_GENERATION plus 1 QUALIFICATION_MISS row in
the top-20 diagnosis. Dominant shortlist failure remains indication exclusions upstream
and target-UNKNOWN fill among bad rows. The failed attempt's counts are development-only.
Post-adoption remeasurement is not applicable; no new blind labels were invented.

Next principled option: a NEW preregistration for indication semantics v2, deriving full
disease spans and conservative compatibility from an authority taxonomy, explicitly
testing incomplete histories, ambiguous legacy mapping and diagnostic qualifiers before
implementation. Do not silently modify v1 or start non-product/routing/target milestones.
H16–H20 remain entirely untouched. No H16–H20 commands are issued: validation is premature
while the indication milestone has not been adopted.


### Normal reversion and restoration verification

Failed evidence committed at `8f466b4`; implementation reverted at `d8f5023`.
`git diff c70461e -- src tests` is empty: the accepted source and tests are restored
byte-for-byte. Restored indication and intent regression tests: **108 passed**.
`ruff check src/`: **clean**. The full suite was not rerun after reversion; the failed
attempt's complete full-suite outcome is retained, and source/test identity establishes
restoration. See `restoration_verification.json`. Milestone status: **REVERTED**.
No live acquisition/replay, ranking change or H16–H20 exposure occurred.
