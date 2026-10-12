# HUMAN_EFFICACY_BOUNDARY_DIAGNOSIS v2

**Status: DIAGNOSIS ONLY / COMPLETE. No production change, implementation
preregistration, new acceptance score, or adoption decision.**

The failed `HUMAN_EFFICACY_CONTEXT_SAFETY v1` attempt remains **REVERTED**. Its
first-result scores and frozen labels stand. This diagnosis starts from restored
`human_poc_v4` at `813b215`. H16–H20 are development/diagnostic data, never future
generalization evidence. H6–H10 remain **UNRUN**.

## Frozen comparison

Evidence packet: `research/se_human_efficacy_boundary_diagnosis_v2/`.

- `side_by_side.md`: every required witness, exact passage, clinical world,
  quantity roles, cross-clause relationships, attribution caveats, current and
  archived-attempt results.
- `witness_register.json`: exact asset/candidate names; all asset, human,
  efficacy and numerical match offsets; surface-fragment indices; every current
  predicate; complete saved source abstract/title and source type; snapshot path
  and verified SHA-256; exact source location and neighboring text.
- `selection.json`, `input_manifest.json`, `verification.json`,
  `packet_manifest.json`, and `collect_boundary_v2.py`: selection, provenance,
  read-only checks, frozen hashes, reproducible collection.

The comparison contains **33 rows**: all four known false claim witnesses, all
19 clinical claim/run witnesses wrongly removed by v1, both changed legacy
inputs, and eight representative accepted claim witnesses. The four false
claims represent **three distinct passages**; the 19 losses represent **12
distinct passages**. Repeated claims across accepted runs remain separate rows.
All 31 publication rows match their decoded passage in the saved abstract;
the remaining two rows are synthetic legacy tests. Exact original passages are
preserved, including escaped Unicode and truncated sentence boundaries.

The eight accepted controls were selected deterministically from frozen survey
IDs 0, 1, 2, 8, 14, 15, 24 and 29: flare rates, administered cell therapy,
survival durations/confidence intervals, unfavorable remission results,
evaluable-cohort response rates, word-valued remission counts, CAR T remission,
and efficacy alongside safety. This is structural coverage, not a new benchmark
or a random generalization sample.

## Current predicate boundary

Every selected exact witness produces a statement under restored v4. For the
four false witnesses, asset mention, human context, efficacy term and numerical
value all fire. None is stopped by eligibility, unreported-result, nonhuman,
safety/non-efficacy, regimen or regimen-list vetoes. This is admission failure
before normalization, not downstream identity inheritance.

| False claim | Human cue / endpoint / selected value | What the evidence actually establishes | First failure boundary |
|---|---|---|---|
| H18 Tirzepatide, `claim:9954996062248331a551`, survey 97 | `human` / `response` / raw `219330%` | Human **myotubes**, laboratory respiration. The first percentage belongs to semaglutide/cagrilintide; a later respiration percentage concerns tirzepatide. Title explicitly says **In Vitro**. | Evidence-world and quantity-role interpretation: human-derived material is not a treated clinical cohort; assay responses are not clinical efficacy. |
| H19 Sacituzumab Tirumotecan, `claim:6c5b35e2a5871015f940`, survey 109 | `patient` / `survival` / `5%` | Partitioned survival **model**, simulated patient trajectories and economic evaluation. Five percent is an annual **discount rate**. | A modeled population is mistaken for observed clinical participants, and a model parameter for efficacy. |
| H16 Ivermectin, `claim:fda8d13dfda69b782423`, survey 64 | `patient` / `complete remission` / `4/13` | A patient achieved qualitative remission on a **combination**; `4/13` occurs in interleukin receptor-pathway nomenclature. | The numeric regex accepts a biological identifier as a result. Component attribution is an additional independent concern. |
| H16 Dupilumab, `claim:6fe84fe83a76085b6cb1`, survey 64 | Same shared passage and predicates | Same qualitative combination outcome and receptor identifier. | Same quantity-role failure; parenthetical apposition also defeats immediate-name combination detection. |

The two H16 rows are distinct asset claims, not independent source evidence.
H18's raw escaped `\u2193` adjoins a percent token and alters the selected
number. Fixing representation alone would not turn respiration into clinical
efficacy. A genuine clinical case report likewise does not make every number
in the sentence an efficacy quantity.

These are all `publication_abstract` prose claims. Source-type admission allows
the publication route but does not establish clinical study type. The source
title/abstract can identify laboratory or modeled work even when the sentence
contains no existing veto phrase. Structured ClinicalResult handling did not
produce these four claims and is not changed or newly evaluated here.

## Why preserving clinical results needs more than clause proximity

All 19 lost witnesses regain PASS under restored v4 and remain UNKNOWN under
the archived failed attempt. The archived population detector returns true for
all 19 and both changed legacy inputs; its outcome-value binder returns None
for all 21. The shared loss is therefore not failure to recognize a human
population: it is the narrower clause/quantity-link mechanism. For example,
CTL019's count precedes CR with treated-cohort language between them, and
drugx's percentage precedes flare after “reduction in,” while the result verb
“produced” is outside the selected number-to-endpoint span. Their clinical labels are unchanged. The archive
is imported under a separate module solely to reproduce the failed decision;
the old scorer and engine/corpus runs are not executed.

| Lost clinical structure | Frozen survey IDs and affected rows | Required interpretation |
|---|---|---|
| Rates separated from cohort or treatment description | 11 (two accepted runs), 62, 69 (two assets), 99 | The response proposition spans treatment-group modifiers, commas, parentheses or abbreviations. `respectively` maps rates to groups. |
| Clinical outcome count differs from the regex-selected percentage | 26 (two accepted runs) | Three achieved CR; 31.2% describes the subgroup receiving induction. A valid result exists, but the old selected number is not its magnitude. |
| Event verb differs from current accepted keyword | 42 | 28.6% **progressed**; current keyword is CR in `PET30-CR`. Endpoint meaning cannot depend exclusively on the first recognized token. |
| Time/comparison ellipsis spans coordinated assertions | 54 | Alive at six months, decline at twelve months, and progression-free survival rates are related outcomes. Repeating every cue is unnecessary. |
| Sentence splitter truncates `vs.` comparison | 78; 80 (five assets) | The saved source continues the same comparison. For 78, PFS is **15.6 vs. 12.0 months** and OS **38.4 vs. 32.0 months**. Current selected `n = 17` is a group size. For 80, the response proportion comparison continues after `70.1%vs.`. |
| Observed attainment includes an endpoint threshold | 92, 103, 104 | RNA cutoff, at-least-20% PS reduction, or at-least-30% LFC reduction defines the measurement. Separate observed attainment proportions establish what happened. An endpoint-definition or statistical-analysis phrase can occur inside an actual result. |

The two changed legacy positives are also restored: CTL019's **10/16 evaluable
pts** with ongoing BM CR, and drugx's **30% reduction in flare risk, observed in
194 patients**. The first needs existing abbreviation behavior; the second
places cohort confirmation in the neighboring comma clause.

The retained controls add two important distinctions. **CNCT19 cells** and
**ICG318 CAR T-cells** are interventions administered to patients, not assay
populations. Conversely, a confidence level or baseline blast percentage is
not the result magnitude: CNCT19's actual results are survival durations, and
blinatumomab's remission count is **all six**, while its matched `>5%` describes
pretreatment marrow blasts. An unfavorable result such as ruxolitinib's **1/10**
remission is still observed efficacy evidence under existing behavior.

## Supported semantic property and limits

The general property supported by these sources is a **reported clinical
result proposition** whose linked roles establish:

1. An observed treated/evaluable human clinical population, rather than human
   material or simulated entities.
2. A disease-relevant outcome actually measured in that population.
3. A numerical magnitude belonging to that outcome: proportion, count,
   duration or effect estimate. Population size, biological identifier,
   threshold, confidence level, model parameter, baseline burden, PK and safety
   quantities have different roles.
4. The treatment/arm responsible for the observed outcome, with the existing
   strict asset/regimen attribution requirements preserved.
5. An observed assertion, distinguished from methods, definitions, hypotheses,
   projections and planned outcomes.

These relationships may span clauses, comparative phrases, abbreviations and
bounded continuations of one source assertion. They cannot be established by
indiscriminately borrowing patients or percentages from neighboring sentences.
The relevant unit is the supported result proposition, not a fixed character
distance or mandatory one-clause conjunction. Source study context constrains
the assertion; broad source type alone does not prove it.

At the **clinical-content** level, this interpretation explains all 19 losses
and both legacy changes, while all four false witnesses lack a numerical
observed patient-efficacy result. This is a source-grounded diagnosis, **not an
executable classifier, acceptance score, or demonstrated implementation**.

Clinical-content truth and asset-specific attribution must remain separate.
The frozen v1 adjudications explicitly concern clinical content under existing
attribution guards. Examples 26, 69, 80 and 92 contain regimens; 42 names a
response stratum; 54 has candidate `though`, a conjunction. Those labels are
not changed, nor does this diagnosis certify those identities or component
attributions. Requiring a literal numerical result inside the old truncated
witness would also wrongly lose source-supported cases 78/80.

Consequently, there is **no implementation-ready rule preregistered here**.
A subsequent narrowly scoped proposal would need to specify bounded result
continuations, quantity-role binding, cohort-role resolution and preservation
of current attribution guards against this frozen register before modifying
behavior. The correct interpretation of clinical thresholds/estimands must
also preserve the accepted cases rather than reject analysis vocabulary.
This diagnosis does not authorize relaxing attribution or changing identity.

## Verification and stopping point

The collection asserts the expected 4/19/2/8 population, verifies each saved
snapshot against its prior frozen hash, locates every publication witness in
the decoded source abstract, and records exact restored and archived predicate
outputs. Current source/tests/scripts remain byte-identical to diagnosis
commit `c5bc865`; prior v1 packet hashes remain unchanged. No production tests,
source, benchmark labels, scores or artifacts are modified. This is a
documentation/evidence milestone; no new implementation quality gate is
claimed.

**Stop after recording this diagnosis.** False human-PoC remains first priority.
No efficacy fix, implementation preregistration, target-alias work, candidate
qualification/discovery, identity consolidation, ranking change, holdout run
or top-20 optimization is included.
