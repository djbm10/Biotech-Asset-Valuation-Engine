# Phase intent, compiled into the gate

`SearchIntent.phases` had been parsed since M9C and read by nothing. "in phase 2" in a typed
question reached the parser, was printed in the interpretation, and then changed nothing about
the run. This closes that, as a scientific gate rather than as a filter applied to the
finished shortlist.

## 1. Audit — what already existed

| Piece | State before | Used |
| --- | --- | --- |
| `SearchIntent.phases` | populated by `_PHASE_PATTERN` / `_normalize_phase` (`PHASE1`…`PHASE4`, `EARLY_PHASE1`, slash forms) | by nothing |
| `compile_intent` | built `StrategicGap` from targets/modalities/indications | never read `phases` |
| `intent_to_trial_query` | passed `statuses` | never passed phases |
| `EvidenceFloor.minimum_stage` | `GTE` over `development_stage_order` | benchmark YAMLs |
| `GateEngine` | eight gates, each one `BuyerRequirement` → `evaluate_requirement` | yes |
| `development_stage_order` facts | minted in `evidence/clinicaltrials.py` from `designModule.phases` of the asset's own trial records | yes |
| MINIMUM vocabulary ("at least", "or later", "+") | **did not exist anywhere** | — |

Two consequences shaped the fix. First, the gate contract is already generic — a requirement
is a fact type, an operator and an expected value — so phase needed no second filtering
system, only a requirement. Second, MINIMUM intent could not be *expressed*, so the parser had
to be extended as well as the compiler.

## 2. Semantics

`PhaseConstraintOperator` is explicit about which question was asked:

| Query | Operator | Requirement |
| --- | --- | --- |
| `phase 2` | `EXACT` | `development_stage_order == 3` |
| `phase 1 or phase 2`, `phase 1/2` | `ANY_OF` | `development_stage_order IN [2, 3]` |
| `phase 2 or later`, `at least phase 2`, `phase 2+` | `MINIMUM` | `development_stage_order >= 3` |

Bare `phase 2` is deliberately **not** mapped onto `EvidenceFloor.minimum_stage`. That would
have been one line and would have answered a different question: every Phase 3 asset admitted
into a Phase 2 search. `minimum_stage` is untouched and still means what it meant.

`PHASE_STAGE_ORDER` mirrors `clinicaltrials._STAGE_ORDER` exactly, because the gate compares
against the facts that module mints. The two must not drift.

## 3. Gate behaviour

The constraint compiles to one `BuyerRequirement` (`evidence.phase_constraint`, domain
`EVIDENCE_SUFFICIENCY`, gate `evidence_floor`) and is decided by the ordinary evaluator, which
is what gives it the right absence semantics for free:

- admissible Phase 2 evidence → **PASS**
- admissible known non-Phase-2 evidence → **FAIL** → excluded
- no stage fact, or stage facts that disagree → **UNKNOWN** → review queue

Unknown phase is never a mismatch. `observed_fact_ids` and
`supporting_or_contradictory_claim_ids` carry the evidence that caused the decision, so PASS,
FAIL and UNKNOWN are each traceable to a document.

**Only asset-specific evidence counts.** `development_stage_order` is minted from an asset's
own registry records; the discovery-context text a candidate happened to be found in is a
different fact type and cannot reach this gate however many phases it names.

Retrieval is deliberately **not** narrowed by phase. `intent_to_trial_query` still issues the
same queries, so the corpus a run measures its own coverage against does not change shape when
a phase is named; the constraint decides dispositions, not what gets looked at. Pre-filtering
retrieval would make an asset's absence and its exclusion indistinguishable.

## 4. Backward compatibility

`StrategicGap.phase_constraint` defaults to `None`. Every BuyerProblem authored before this
change validates unchanged, and no phase decision is emitted for it, so benchmark runs without
phase intent are byte-identical.

## 5. Reporting

The shortlist reports the gate's decision beside the stage evidence that produced it — the
`Phase` fact carries `phase gate PASS/FAIL/UNKNOWN: <rationale>` and its trial citations, and
a PASS also appears in "why this asset matched". The renderer does not decide anything; it
would be indistinguishable from a second, silent filter if it did.

## 6. Tests

`tests/se/test_phase_intent_gate.py`, 18 tests. They discriminate: folding `EXACT` onto `GTE`
fails `test_phase_2_does_not_behave_as_phase_2_plus` and
`test_known_phase_3_fails_exact_phase_2`.
