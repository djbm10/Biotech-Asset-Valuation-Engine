# Science Layer + New BD Layer Breakdown

**Date:** 2026-06-22; updated for the current science ownership refactor and new
BD actionability layer.

**Scope:** Current science layer and new BD layer only. This file intentionally
omits the older session-summary material, historical seven-component scoring
model, and superseded pre-refactor weights.

**Maintenance rule:** Future science-layer or BD-layer architecture changes
should update this file, especially changes to ownership, scoring formulas,
guardrail caps, assumptions YAML, or memo/output behavior.

**Source truth:** current repository code, especially:

- `src/bve/intelligence/science_thesis.py`
- `src/bve/intelligence/layer15_buyer_match.py`
- `src/bve/models/probability_stack.py`
- `src/bve/config/assumptions_loader.py`
- `src/bve/config/industry_assumptions.yaml`
- `src/bve/config/industry_assumptions_2024q2.yaml`

## 1. Current Architecture

The current architecture separates three jobs that used to be mixed together:

1. **Science layer:** scores unresolved biological thesis risk.
2. **POS layer:** scores clinical/regulatory probability.
3. **BD layer:** scores whether the asset is actionable for a buyer problem.

The key ownership rule is:

```text
Science = T/D/B biological thesis risk
POS     = clinical/regulatory probability
BD      = buyer problem fit, human PoC, clinical meaning, and deal actionability
```

This avoids double-counting signals like human proof-of-concept, clinical
meaningfulness, and safety/tolerability. Those signals matter, but they no longer
receive positive credit in both the science modifier and POS.

## 2. Science Layer Ownership

The science layer now has three explicit buckets.

| Bucket | Model | Purpose | Scores POS modifier? |
|---|---|---|---|
| Scored questions | `ScienceScoredQuestions` | Biological thesis risk | Yes |
| Context | `ScienceContext` | Audit, memo, and BD routing context | No |
| Guardrails | `ScienceGuardrail` | Downside caps and derates | Downside only |

### Scored Science Questions

Only T/D/B carry positive score weight:

| Key | Field | What it asks |
|---|---|---|
| T | `right_target` | Is the target/pathway biologically right? |
| D | `enough_drug` | Can enough drug reach and engage the target? |
| B | `translation_bridge` | Does the biomarker/model bridge translate to clinical benefit? |

These are the science-layer signals that POS does not directly own. They are the
cleanest representation of unresolved biological thesis risk.

### Science Context

H/M/Q moved out of positive science scoring:

| Old key | Current home | Current role |
|---|---|---|
| H | `ScienceContext.human_poc` | BD/conviction/memo context, not POS multiplier credit |
| M | `ScienceContext.clinical_meaningfulness` | BD actionability and memo context, not science modifier credit |
| Q | `ScienceContext.evidence_quality` | Confidence and audit quality, not point-estimate score |

Human PoC and clinical meaningfulness remain important. The change is ownership:
they should influence BD conviction and diligence routing instead of being
multiplied into technical POS twice.

### Science Guardrails

Safety and refutation signals are downside-only:

| Signal | Current role |
|---|---|
| Target refuted | Hard cap |
| Infeasible exposure | Hard cap |
| Biomarker bridge refuted | Hard cap |
| Negative human PoC | Hard cap or soft derate, depending on interpretability |
| Manageable safety concern | Soft derate |
| Unacceptable safety | Hard cap |
| Mechanism-linked severe safety | Severe hard cap |

There is no positive science credit for "clean safety." Safety upside already
belongs in POS. The science layer only prevents a biology thesis from receiving a
high modifier when safety or clinical data undercuts the thesis.

## 3. Science Scoring Formula

Primary function: `compute_science_modifier`.

The formula scores only T/D/B:

```text
science_score =
  T_weight * right_target.score
+ D_weight * enough_drug.score
+ B_weight * translation_bridge.score
```

That score is mapped into a heuristic POS multiplier band, then guardrails are
applied. The output remains explicitly heuristic:

```text
scoring_version       = science_thesis_phase2
weight_set_version    = phase2_tdb_v1
calibration_status    = heuristic
```

The probability stack composes the result at one point:

```text
technical = technical * science_modifier
```

`science_modifier` is already the effective post-guardrail value by the time it
reaches the probability stack.

## 4. T/D/B Phase Weights

Primary config: `science_phase_weights_tdb`.

| Phase | T | D | B |
|---|---:|---:|---:|
| preclinical | 0.40 | 0.35 | 0.25 |
| phase 1 | 0.25 | 0.45 | 0.30 |
| phase 2 | 0.25 | 0.25 | 0.50 |
| phase 3 / NDA-BLA | 0.34 | 0.33 | 0.33 |

Late-stage de-emphasis is not handled by making phase 3 weights tiny. It is
handled by the late-stage unresolved-biology gate. That keeps the weights
normalized and makes the rule easier to audit.

## 5. Late-Stage Gate

Primary helper: `_has_unresolved`.

For phase 3 and NDA/BLA assets, the science modifier defaults back to `1.0`
unless there is a real unresolved biological issue.

The unresolved rule requires all three:

1. The binding T/D/B component is weak enough to matter.
2. The component is unresolved, refuted, or has evidence against it.
3. The same factor was not already captured by a narrow POS adjuster.

Primary threshold:

```yaml
unresolved_threshold: 0.50
```

This prevents late-stage assets from getting a positive science boost just
because clinical data already answered the biology question. If biology is still
the binding issue, the science layer can still matter.

## 6. Guardrail Composition

Primary function: `apply_science_guardrail`.

Guardrails use two operations:

```text
effective_modifier = min(base_modifier, *hard_caps) * combined_soft_derate
```

Hard caps set a ceiling. Soft derates multiply downward. Soft derates are floored
so several mild warnings cannot silently behave like a kill:

```yaml
soft_derate_floor: 0.70
```

Current guardrail priors:

| Guardrail | Type | Value |
|---|---|---:|
| `target_refuted` | hard cap | 0.20 |
| `infeasible_exposure` | hard cap | 0.30 |
| `biomarker_bridge_refuted` | hard cap | 0.65 |
| `negative_human_poc_clear` | hard cap | 0.60 |
| `negative_human_poc_ambiguous` | soft derate | 0.85 |
| `manageable_safety_concern` | soft derate | 0.85 |
| `unacceptable_safety` | hard cap | 0.40 |
| `mechanism_linked_severe_safety` | hard cap | 0.10 |

These values live in both assumptions YAML files and are exposed through
`AssumptionsLoader.science_guardrails`.

## 7. Evidence And Overlap Rules

Primary function: `check_science_pos_overlap`.

The overlap guard exists because the science modifier multiplies technical POS.
If the same source-backed evidence drives both science and POS, the model can
double-count it.

Current rule:

| Case | Result |
|---|---|
| Same `ScienceEvidenceItem` used by science and POS | Fail-level warning |
| Related but not identical signal | Warn-level warning |
| Distinct evidence for distinct layer jobs | Allowed |

The guard is source-based because that is machine-checkable. Intent-level overlap
is surfaced as a warning, not an automatic numeric change.

## 8. New BD Layer

The new BD layer answers a different question from science and POS:

```text
Is this asset actionable for a buyer's specific problem?
```

Primary files:

- `src/bve/intelligence/science_thesis.py`
- `src/bve/intelligence/layer15_buyer_match.py`

Core result:

```text
BDActionabilityResult
```

Important fields:

| Field | Purpose |
|---|---|
| `buyer_problem_fit` | Fit to the buyer's actual strategic or pipeline need |
| `human_poc_strength` | Human clinical conviction signal routed to BD |
| `clinical_meaningfulness` | Whether the observed effect matters commercially/clinically |
| `evidence_quality` | Quality of evidence available at screening |
| `evidence_grade` | Whether evidence is public screening-grade or diligence-grade |
| `pre_diligence` | Marks public-data outputs as not yet buyer-confirmed |
| `modality_capability_fit` | Whether the buyer can develop/commercialize the modality |
| `buyer_owner_advantage` | Whether this buyer has a special right-to-win |
| `deal_feasibility` | Whether a realistic deal path exists |

`science_thesis_fit` is retained for backward compatibility, but the new
structure explicitly splits human PoC and clinical meaningfulness so those
signals are not hidden inside a generic science field.

## 9. BD Actionability Formula

Primary function: `compute_bd_actionability`.

Current Stage 2 weights:

| Component | Weight |
|---|---:|
| Buyer problem fit | 0.25 |
| Human PoC strength | 0.20 |
| Clinical meaningfulness | 0.15 |
| Evidence quality | 0.10 |
| Modality capability fit | 0.10 |
| Buyer owner advantage | 0.10 |
| Deal feasibility | 0.10 |

Formula:

```text
bd_actionability =
  0.25 * buyer_problem_fit
+ 0.20 * human_poc_strength
+ 0.15 * clinical_meaningfulness
+ 0.10 * evidence_quality
+ 0.10 * modality_capability_fit
+ 0.10 * buyer_owner_advantage
+ 0.10 * deal_feasibility
```

`time_sensitivity` is not part of the fit score. It is a routing/urgency signal,
not evidence that the asset is a better strategic fit.

## 10. Screening Cap

Public data can support screening, ranking, and memo discipline. It should not
pretend to be confirmed buyer diligence.

Current cap:

```text
SCREENING_PUBLIC_ACTIONABILITY_CAP = 0.75
```

If `evidence_grade == screening_public`, the BD actionability score is capped at
`0.75` and `pre_diligence` remains true. That means a public-data screen can be
highly interesting, but not "transaction-ready" without diligence.

## 11. Buyer Problem And Shortlist Flow

Primary class: `Layer15BuyerMatcher`.

Current flow:

```text
asset + buyer context
  -> buyer problem fit
  -> BDActionabilityResult
  -> buyer route / shortlist / memo output
```

The buyer layer should surface:

- why this asset solves a buyer-specific problem,
- whether the buyer has capability and owner advantage,
- whether human PoC and clinical meaning make the asset more actionable,
- whether public evidence is still only screening-grade,
- what diligence questions remain before a BD conclusion.

The intended output is not a generic "good asset" score. It is a buyer-specific
actionability read.

## 12. Layer Boundaries

| Signal | Current owner | Rule |
|---|---|---|
| Right target/pathway | Science | Positive scored T component |
| Exposure/PK/PD | Science | Positive scored D component |
| Translation bridge | Science | Positive scored B component |
| Human proof-of-mechanism | POS | POS adjuster, not science H credit |
| Human proof-of-concept | BD/context/guardrail | Positive BD conviction; downside guardrail if negative |
| Clinical meaningfulness | BD/POS context | BD actionability; avoid duplicate science boost |
| Safety/tolerability | POS + science guardrail | POS owns safety tier; science only caps/derates downside |
| Evidence quality | Confidence/audit | Does not directly raise point estimate |
| Time sensitivity | BD routing | Does not raise BD fit score |

## 13. Validation Status

Focused validation from the implementation pass:

```text
207 focused tests passed
ruff passed on touched files
```

Known non-doc caveats from that pass:

- Full suite had one unrelated failure in an untracked
  `tests/test_pos_prior_phase_fallback.py`.
- Relay sanity run was blocked by an existing
  `TrialDesignFeatureSet.evidence_design` mismatch in `run_asset.py`.

This document is descriptive. It does not change runtime behavior.

**Landing status:**

- **Part 1 (Chris-aligned actionability, sections 9–11)** is implemented in the
  `core-engine-v1` working tree (`science_thesis.py`: `EvidenceGrade`,
  `ShortlistEntry`, `build_buyer_problem_shortlist`). A standalone earlier copy
  also exists on branch **`bd-chris-aligned-part1`** (commit `5e663ac`, worktree
  `/home/djmann/projects/bve-bd-part1`) — now redundant with the main-tree
  version; do not merge it (it would conflict against the science-ownership
  guardrail work). Treat the main-tree implementation as authoritative.
- **Part 2 (dual-source buyer-problem intake + parallel compare)** is committed
  **directly on `core-engine-v1`** (commit `466b441`) as standalone new modules
  `intelligence/buyer_problem_inferencer.py` and
  `analysis/buyer_problem_reconciliation.py` (+ tests). No edits to
  `science_thesis.py`: provenance lives in a `BuyerProblemDraft` sidecar so the
  core model stays clean and there was no collision with in-flight work.

## 14. Known Limits

- The science modifier is still heuristic, not calibrated.
- Guardrail caps and derates are priors, not fitted coefficients.
- T/D/B component scores are coarse evidence-presence and thesis-quality signals,
  not measured biological effect sizes.
- The overlap guard catches source-level reuse better than intent-level reuse.
- Public BD actionability is capped because public evidence is not buyer
  diligence.
- Human PoC and clinical meaningfulness are influential through BD and memo
  logic, not through another positive science multiplier.

## 15. Open Follow-Ups

- Finish any remaining buyer-problem intake inference work if it is still not
  implemented.
- Re-baseline valuation snapshots affected by removing H/M/S from positive
  science scoring.
- Keep `science_guardrails` and `science_phase_weights_tdb` synchronized across
  both assumptions YAML files.
- Add future changes to this file instead of the old session-summary document.
