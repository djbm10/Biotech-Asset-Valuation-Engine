# HUMAN_EFFICACY_QUANTITY_BINDING_CONTRACT v1

**Decision: DESIGN RECORDED / NOT IMPLEMENTATION-READY.** No production change
or implementation preregistration. The required full-chain acceptance target
is **not met**. The clinical-content sub-contract matches all 33 frozen labels,
but strict asset-specific binding preserves only 5/19 removed clinical rows,
plus both legacy positives and all eight controls; all four numerical false
witnesses reject. The 14 remaining rows have unresolved or incompatible
treatment/identity/regimen edges. Their frozen expected labels are unchanged.

This is an architectural/acceptance-constraint finding, not another efficacy
fix. No post-result patch to the contract checker or frozen annotations was
made. H16–H20 remain diagnostic/development data. H6–H10 remain **UNRUN**.

## Inputs, freeze and evaluation

Read first: the current handoff, `human_efficacy_boundary_diagnosis_v2.md`, and
its exact side-by-side register, frozen in diagnosis commit `814328c`.

Evidence: `research/se_human_efficacy_quantity_binding_contract_v1/`.

- `relation_population.json` and `relation_table.md`: all 33 original witnesses,
  with exact treatment/candidate, cohort, outcome and numerical spans; typed
  edges; clause boundaries; source continuations; current, expected and proposed
  decisions; and reasons. Offsets specify whether they address the original
  escaped passage, decoded passage or saved source abstract.
- `population_freeze.json`: original v2 register hash and hashes of the design
  population and added cases, committed as **120b669 before contract evaluation**.
- `additional_discourse_cases.json`: three necessary synthetic designs. No v2
  witness demonstrates true adjacent-sentence treatment/cohort anaphora:
  `vs.` truncation is one sentence, not anaphora. D1 has a unique treatment and
  explicit evaluable-cohort reference; D2 has competing treatment arms; D3 puts
  the requested treatment beyond the immediately preceding sentence.
- `check_quantity_binding_contract_v1.py`, `offline_result.json`: deterministic
  validation of **manually grounded relation records**, not a raw-text extractor
  or an end-to-end engine benchmark. The checker has no asset/query/article-ID
  exceptions and never consults expected labels to decide acceptance.
- `verification.json`, `packet_manifest.json`: source preservation and packet
  integrity. Existing frozen input/label/result packets remain unchanged.

The source spans are hand-annotated evidence, not newly discovered automated
parsing capability. Therefore a correct graph decision is not evidence that
the current extractor can construct that graph from unrestricted prose.
Synthetic discourse checks exercise scope/uniqueness, not general coreference.

## Smallest representation

Current `efficacy_statements()` selects the first `_VALUE` match in a sentence
that co-occurs with human, efficacy and asset cues. `EfficacyStatement` holds
asset name, endpoint, sentence, value and document ID. It has no cohort object,
quantity role, arm assignment, semantic links or evidence spans. The failed
v1 `_clinical_outcome_value()` exists only in the reverted archival attempt;
it is not a live production binder available for direct modification.

The smallest proposed extension is a local, typed **ResultBinding** record
inside the existing human-PoC module, consumed by the existing statement path:

```
source spans / assertion scope
  treatment(candidate identity, arm, regimen scope)
    -> cohort(actual clinical participants, treated/evaluable subset)
      -> outcome(existing endpoint concept, observed status)
        -> quantity(value, unit, measurement role, comparator position)
```

Each node and edge carries source-document identity, exact offsets and a
relation kind. The quantity finder returns a binding with its evidence, not
the first nearby number. The existing fact emitter receives a statement only
after the binding and all existing attribution guards pass. No parallel
extractor, new target/indication/qualification/identity/ranking route, or new
fact ontology is proposed. This record is **specified here, not implemented**.

Source normalization must preserve an offset map from decoded source fields
to the original snapshot. It must not treat JSON escapes or field names as
numeric clinical text. A sentence/section boundary record must distinguish a
grammatical sentence from the current regex's `vs.` and decimal fragments.

## One deterministic contract on grounded records

A candidate binding is ACCEPT only if **all** conditions below hold. A missing,
ambiguous or unsupported condition gives REJECT in the design table, meaning
**UNKNOWN / emit no human-PoC fact** at runtime, not proof of no efficacy.

**G1 — Provenance and bounded assertion.** All nodes share one document and
one supported assertion scope defined below. Every node has a source span and
every edge has a permitted relation kind. A title or source-type label may
help disambiguate study world; it cannot supply a missing treated cohort,
asset identity or outcome number. No cross-document or corpus-level inference.

**G2 — Treatment identity and attribution.** The treatment node is the same
candidate under existing identity rules. The candidate is the treatment arm
responsible for the result, not an assay category, conjunction, prior therapy,
comparator-only mention, or an individual component inheriting a regimen
result. All existing regimen/product/eligibility safeguards must also pass.
Passing a substring-based current guard is necessary but does not prove this
edge. No new alias equivalence or component-to-regimen equivalence is inferred.

**G3 — Actual patient cohort.** The cohort node denotes observed clinical
participants, with a receive/treat/administer relation to the treatment, an
explicit treated-arm designation, or an unambiguous observed outcome reported
for that treatment in those patients. Administered cell therapies can be
treatment nodes; human cells, tissue and modeled subjects are not patient
cohorts. Simulated trajectories do not acquire observed status from the word
patients. Retrospective, pooled and unfavorable clinical results are not
excluded merely for their study design or direction of effect.

**G4 — Observed endpoint.** The cohort is the subject/population of a reported
result on an existing accepted efficacy concept. CR/response/survival/flare
surface forms and already accepted virological or disease-improvement concepts
retain their meaning. No new efficacy concept is authorized. Definitions,
methods, baseline conditions, eligibility, future plans and modeled projections
do not become observed outcomes. A result can contain an endpoint definition
or an estimand; those words alone cannot veto its observed attainment rate.

**G5 — Measured outcome value.** The quantity is an argument of that outcome
proposition by one of the following structural relations, not by distance:

| Relation | Required structure | Quantity ownership |
|---|---|---|
| Event proportion | Percentage/fraction **of a clinical cohort** that achieves/has/retains the outcome | Numerator measures the event; cohort size alone does not. |
| Event count | Count, including word-valued count, is the subject of the observed outcome verb or quantified participants in the outcome assertion | `3 achieved remission` and `all six ... remission`; enrollment numbers are separate. No count is synthesized from singular `patient`. |
| Labeled result/rate | Named clinical outcome's reported rate/value with an explicit patient population | A rate before or after the endpoint can bind through cohort/treatment modifiers without a character-distance cutoff. |
| Labeled duration/effect | A reported duration/effect explicitly measures the named endpoint | Survival months are the result; CI percentage is uncertainty about it. |
| Observed threshold attainment | Reported count/proportion of patients attaining a defined clinical endpoint | Attainment percentage is the result; threshold, cutoff and baseline quantity are separate. |
| Ordered comparison/ellipsis | Explicit ordered endpoint or arm list matched to an equally sized result list, with compatible units | `respectively`, named groups or explicit repeated endpoint/arm structure resolve ownership. Unresolved or pooled-to-component mapping gives UNKNOWN. |

An action verb may precede the numerical span, follow it, or govern a coordinated
result across modifiers. Its grammatical argument relation matters; it need
not occur inside the number-to-endpoint substring. Definitions and baseline,
uncertainty, dose, identifier, economic/model, laboratory, PK and safety
quantities are separate roles, not outcome magnitudes. A clinical setting or
nearby response word does not change those roles.

**G6 — Unique complete chain and guards.** Treatment→cohort, cohort→observed
outcome and outcome→quantity are all supported, with unique arm ownership for
the selected result. Existing exclusions remain in force; safe mixed efficacy
and safety behavior remains available only for independently supported
efficacy. An ambiguous graph is not resolved by picking the first number,
nearest asset, favorable arm or an expected label.

Formally:

```
content = same_document AND allowed_scope AND actual_clinical_population
          AND observed_existing_efficacy_outcome AND outcome_measure_quantity
          AND supported(cohort -> outcome) AND supported(outcome -> quantity)

emit = content AND same_candidate_treatment AND unique_treated_arm
       AND supported(treatment -> cohort) AND no_existing_guard_veto
```

`content` is an offline diagnostic ablation, **never sufficient to emit**.
The checker evaluates these predicates on frozen grounded records. It does not
implement the grammar that discovers records from text. This remains a design
specification; automatic edge grounding is an unresolved implementation task.

## Permitted clause and sentence scope

1. **Same grammatical sentence:** binding follows explicit predicate/argument,
   modifier, relative-clause, apposition or coordinated-list structure. Commas,
   parentheses, colons and conjunctions do not erase those relationships.
   Unrelated coordinated measurements keep their own roles. No arbitrary
   within-sentence distance licenses an edge.
2. **Abbreviation continuation:** a source fragment split at `vs.` is joined
   only as the continuation of that explicit comparison in the same source
   sentence, up to its actual terminator. This repairs a boundary description,
   not a permission to join unrelated sentences. Units may be shared within an
   explicit measure list; an unlabeled number cannot borrow a unit from an
   unrelated result.
3. **Immediately adjacent sentence:** the preceding sentence explicitly
   establishes one candidate-treated patient cohort. The result sentence has
   an explicit reference to that cohort or an evaluable subset, e.g. these
   patients or evaluable patients. There must be exactly one compatible cohort
   antecedent and arm, in the same paragraph/abstract section and study world.
   No new cohort, alternative treatment, section boundary, unrelated experiment
   or intervening sentence may be crossed. No transitive reference chaining.
   A bare patient count after competing arms is insufficient. D1 satisfies this
   relation; D2 and D3 do not.

The adjacent-sentence rule is a **proposed architectural extension**, not
current behavior: the current function explicitly refuses asset/result
stitching across sentences. A future implementation would retain candidate and
regimen guards for both participating assertions and require an explicit edge
before allowing a result without a repeated asset name. It must not simply
widen a string window or disable those guards. Current sentence-size and source
routing safeguards are not authorized for removal. How their existing limits
apply to a referenced multi-span binding must be resolved before preregistration.

## Frozen offline result and incompatible acceptance target

| Population | Rows | Clinical-content labels matched | Full-chain labels matched | Full-chain ACCEPT |
|---|---:|---:|---:|---:|
| Known numerical false witnesses | 4 | 4 | 4 | 0 |
| v1 wrongly removed clinical witnesses | 19 | 19 | 5 | 5 |
| Changed legacy positives | 2 | 2 | 2 | 2 |
| Accepted controls | 8 | 8 | 8 | 8 |
| Total | 33 | 33 | 19 | 15 |

Three additional discourse scope/uniqueness designs match their frozen
expectations. This is not unseen generalization validation.

The 14 full-chain mismatches are not additional quantity-binder false negatives.
Their observed clinical content binds correctly; their candidate treatment
edge cannot be certified without violating or extending another requirement:

- PET30 and `though`: two rows. Source evidence establishes an assessment
  stratum and a conjunction, not a therapeutic asset. No full treatment chain
  exists for these candidate tokens.
- Venetoclax induction regimen: two rows across accepted runs. The numerical
  CR count is real, but belongs to VEN/AZA/IVO, not an independently observed
  single-agent result.
- Glecaprevir/pibrentasvir: two component rows for one combination result.
- Five protease-inhibitor/backbone rows: rates compare backbones across pooled
  regimens; no unique individual-product arm owns the requested result.
- Lamivudine: one DOR/3TC/TDF component row. The 89% value is the DOR regimen's
  attainment, not the other arm's 93% and not a lamivudine-only result.
- Bevacizumab comparative survival: one row whose source describes targeted
  agents combined with first-line chemotherapy. The observed bevacizumab-arm
  PFS is 12.0 months, but single-product attribution is not independently
  established by that regimen comparison.
- Relugolix: one row. Source expands CT as combination therapy; current aliases
  contain relugolix/TAK-385, not an independently established Relugolix-CT
  candidate. Inferring same-product combination identity is outside this scope.

These are **unsupported full-chain edges**, not retrospective changes to the
frozen clinical-content labels or a rescoring of H16–H20. At least the PET30
and `though` cases make unconditional full-chain ACCEPT of every frozen
positive impossible. A new representation cannot create a treatment role that
the text does not establish. Passing current imperfect attribution predicates
would not solve that logical conflict.

## Remaining decisions before implementation

The smallest safe architectural extension is the typed local ResultBinding
plus source-offset/boundary provenance described above. It can represent the
necessary relation chain; the existing flat statement cannot prove it.
Implementing it is **not authorized by this design**.

Implementation readiness additionally requires reconciliation of whether the
29 positive expectations certify clinical-content binding or asset-specific
fact emission. They currently certify the former; requiring the latter while
preserving every label contradicts the source roles. This must be handled
explicitly, without relabeling or loosening attribution here.

Other unresolved cases: automatic parse/edge grounding under limited grammar;
ambiguous pooled arm mappings; exact alias versus compound treatment identity;
paragraph/section recovery from snapshots; sentence-limit handling for typed
continuations; defining endpoint relevance for clinical laboratory thresholds
without admitting assay/PD-only measurements; mixed observed/model results;
and representation/provenance of corrected numerical witnesses. Structured
ClinicalResult handling was not evaluated by these prose examples and remains
unchanged. An independently grounded raw-text extraction test is required
before calling the relation checker an implementation acceptance gate.

**Stop here: NOT IMPLEMENTATION-READY.** The full requested acceptance target
failed; no implementation milestone is opened, no target/indication/identity
or other root-cause change is made, and no live searches, replays or H6–H10 runs
are launched. The handoff records the contract, failed target and architectural
and label-semantics issues for the next decision.
