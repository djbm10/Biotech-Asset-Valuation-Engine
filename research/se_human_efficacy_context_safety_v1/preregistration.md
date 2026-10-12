# HUMAN_EFFICACY_CONTEXT_SAFETY v1

**Status: PREREGISTERED before implementation, against clean `c5bc865`.**
Diagnosis and all witness judgments below precede behavioral changes. H16–H20 are exposed
diagnostic/development data, never fresh generalization evidence. H6–H10 remain UNRUN.
Frozen primary-validation labels, scores, queries and source artifacts remain unchanged.

## Diagnosis and frozen population

The exact H18 claim `claim:9954996062248331a551` and H19 claim
`claim:6c5b35e2a5871015f940` are `reported_efficacy_sentence` outputs of `human_poc_v4`.
H18 fires human=`human`, endpoint=`response`, value=`219330%`; the biological assay is
not matched by the old sentence-wide nonhuman veto. H19 fires human=`patient`,
endpoint=`survival`, value=`5%`; the value is a discount rate in economic/model methods.
Neither sentence fires the safety/non-efficacy or planned-result veto. Both name the
asset and clear the unchanged adjacent-regimen/list attribution guards. Publication
abstracts are admitted by source capability, which does not itself establish clinical
study context. Full traces and original abstracts are frozen in the prior diagnosis packet.

H18's raw JSON escape yields an incorrect numeric token. Decoding the original abstract
gives 30% and still produces a false PASS. A decoder alone is insufficient; a whole-document
ban on modeling/laboratory words would also discard clinical results with mixed analyses.

Population is fully frozen under `research/se_human_efficacy_context_safety_v1/`:

- Existing full `tests/se` baseline passes with three expected xfails. Every captured reader
  call is frozen: 24 positive and 63 negative prose input/output combinations; one positive
  and eight negative structured-result combinations. No existing test behavior is relabeled.
- All True human-PoC facts and cited witnesses from TAC01/mint5 protoid-v1 benchmarks,
  accepted AACR-design and TAC01-regimen artifacts, and diagnostic H16/H18/H19 are captured.
  These contain 221 currently admitted claim witnesses, with 110 distinct passages.
- All 38 target-PASS / human-PoC-UNKNOWN benchmark assets are captured, not a score-selected
  subset. Existing negative test reader inputs and their structured results freeze UNKNOWN
  examples. This milestone cannot create a previously absent fact.
- Each distinct admitted passage is independently adjudicated before implementation.
  81 numerical clinical-content witnesses must remain admitted. The 29 specific numerical
  false witnesses in `witness_adjudications.json` must become UNKNOWN: methods/cohort n,
  formulation concentrations, treatment-use/referral percentages, molecular assays,
  predicted/model outcomes, endpoint definitions, target/phase numerals, or qualitative
  clinical claims whose only number does not measure benefit. These are explicit E6/E9
  exceptions supported by source text, not retroactive removals after seeing a score.
- 71 new semantic controls freeze laboratory/material, PD/biomarker, simulated cohorts,
  model/economic/statistical, safety, PK, planned/eligibility, legitimate clinical and mixed
  cases. Positive controls use patients/participants/subjects/recipients/volunteers/pts,
  observed response/remission/progression/symptom/flare outcomes, and existing alias rules.
  Structured population/endpoint controls are frozen separately before implementation.

Names, publication IDs, queries and exact values occur only in data and audit tooling;
no production rule may branch on any of them. Survey labels judge numerical clinical
content under the existing attribution guards; no regimen or asset-identity redesign is
authorized. Some legacy witnesses contain pre-existing component/comparator attribution
limitations; v1 neither loosens those guards nor claims to solve every ownership problem.

## Frozen implementation contract

One narrow guard is added inside the human-PoC reader. Only
`src/bve/se/evidence/human_poc.py` may change production behavior. Tests and audit/scoring
tooling may be added. No pipeline, snapshot loader, source capability, target, indication,
qualification, identity, modality, ranking, schema or shortlist-routing changes.

1. **Keep the existing admission ladder and attribution checks.** A prior UNKNOWN input
   cannot become PASS. Existing length, named-asset, eligibility, planned-result,
   adverse-event/nonhuman and strict regimen/list checks remain load-bearing.
2. **Require a clinical population.** Positive member terms are bounded patient,
   participant, subject, recipient, volunteer, pts/pt; a cohort/individuals group requires
   an explicitly clinical/treated/evaluable/trial register. Bare `human` or bare `cohort`
   is insufficient. Patient-derived biological material and simulated/virtual/synthetic
   cohorts are not clinical treatment populations.
3. **Bind quantity to a clinical outcome within a coherent clause.** Percentages/counts
   must quantify response/remission/relapse/progression/disease/symptom benefit, rather
   than appear elsewhere in a sentence. A clinically asserted efficacy/responder rate is
   an outcome; `efficacy cohort`, design, referral, exposure and cost registers are not.
   A patient reduction criterion explicitly reported using an efficacy estimand can
   establish an outcome; isolated biomarker/PD or concentration changes cannot.
4. **Typed quantities, not arbitrary numeric substrings.** Disregard cohort `n=`, doses,
   target/phase identifiers, p-values, interval confidence levels and definition thresholds
   as efficacy values. An observed clinical time-to-event duration or HR, or an explicit
   all-patient remission count, can preserve a previously admitted genuinely quantitative
   outcome when an incidental percentage triggered the legacy reader. This does not
   create a new PASS without the original admission ladder passing first.
5. **Context scope.** Semicolons, commas and independent conjunctions delimit measured
   assertions; preserve colons attaching endpoints to values. A quantity and efficacy
   assertion must be linked within at most 160 characters. A result relation is a reported
   outcome value, a quantified outcome predicate, an observed time-to-event/HR, or an
   explicit patient count achieving the outcome—not mere co-occurrence. Modeled,
   projected, predicted, virtual and methods/definition assertions cannot supply such a
   relation. In a mixed sentence, a separately established observed clinical outcome can
   survive unrelated model/economic/PK/safety data when existing attribution/vetoes allow.
6. **Source representation.** Locally decode JSON Unicode escapes and normalize number
   typography only for context/quantity analysis. Preserve original sentence bytes,
   document IDs, claim locators and attribution checks; do not change snapshot_cache or
   routing. Choose a genuine outcome quantity instead of an unrelated first numeric hit.
7. **Structured results.** Retain existing endpoint/value/incomplete-reporting requirements.
   Add the same nonclinical register veto and clinical population requirement: explicit
   clinical people or a positive typed `evaluable_patients` count, without contradictory
   biological-material/model population or non-efficacy endpoint. UNKNOWN emits no False
   human_poc fact. The existing accepted structured result must remain PASS.
8. Bump the extractor version to `human_poc_v5` so changed admissibility is auditable.
   Accepted facts' subject IDs and existing source citations remain stable.

Lexical classes may express general population, measurement and reporting registers; a
brittle ban on a particular assay noun, discount value, asset, publication or query is
prohibited. Rules require positive clinical/result/value evidence, not just added negative
keywords. Parsing does not infer benefit from biological activity or models.

## Acceptance checks (frozen)

- **E1:** Both exact primary false witnesses reject; no human_poc True fact for those witnesses.
- **E2:** All clinical/material/cohort semantic and structured population controls match frozen labels.
- **E3:** All numerical/endpoint controls match; incidental numeric quantities cannot establish PASS.
- **E4:** Planned/method/eligibility/projection controls and all baseline UNKNOWN reader calls remain UNKNOWN.
- **E5:** Every baseline attribution/control outcome is preserved; strict regimen/list code bytes unchanged.
- **E6:** All 81 independently adjudicated clinical-content passages and all 25 positive existing reader
  input combinations remain PASS. All 29 independently demonstrated numerical false passages reject.
  No adjudication may change after implementation/scoring.
- **E7:** Rejected prose/structured evidence yields no human_poc fact; an empty fact set gives gate UNKNOWN.
- **E8:** Only the allowed production module changes. Protected modules, original result hashes and
  primary-validation labels/scores/rubric bytes remain unchanged. No query run, corpus replay or H6–H10.
- **E9:** Re-evaluate saved TAC01/mint5/accepted benchmark fact witnesses only. Existing subjects keep
  their True fact whenever any frozen admitted clinical witness remains. Only subjects with exclusively
  pre-adjudicated false witnesses may lose their fact. No gains and no other fact changes. This is
  evidence-only diagnostic rescoring, not ranking, qualification, routing or a search replay.
- **E10:** Full `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/se -q -p no:cacheprovider`
  passes all non-xfail tests; exactly the baseline expected xfails are permitted. Required Ruff:
  `ruff check src/bve/se/evidence/human_poc.py tests/se/test_human_efficacy_context_safety.py
  scripts/score_human_efficacy_context_safety_v1.py` is clean.

All semantic controls, including mixed cases, are decisive, not advisory. First post-change
acceptance measurement is decisive. Do not patch semantic code or frozen labels after a
failed criterion. Record failure, restore production behavior by a normal revert, retain
failed evidence, update handoff, and stop. If all pass, adopt, record exact false witness/fact
removals and preserved positives, update handoff, and stop before the next root cause.

This does not validate search generalization, improve/re-score H18/H19 top20, execute any
target-alias work, or consume H6–H10. Later milestones remain separate.
