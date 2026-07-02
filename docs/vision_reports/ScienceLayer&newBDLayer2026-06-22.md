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
- `src/bve/intelligence/killer_question.py`
- `src/bve/intelligence/layer15_buyer_match.py`
- `src/bve/intelligence/se_shortlist.py`
- `src/bve/cli/se_shortlist.py`
- `src/bve/reporting/templates/se_shortlist.md.j2`
- `src/bve/models/probability_stack.py`
- `src/bve/config/assumptions_loader.py`
- `src/bve/config/industry_assumptions.yaml`
- `src/bve/config/industry_assumptions_2024q2.yaml`
- `src/bve/config/clinical_meaningfulness_bars.yaml`
- `src/bve/config/meaningfulness_bars.py`

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

**`buyer_owner_advantage` composition (Idea 15, 2026-06-30).** The owner-advantage
term is set by the matcher's `_owner_advantage` and adjusted in the scorer only by
`+0.05 * internal_portfolio_fit + 0.05 * combination_or_lifecycle_fit`. Scarcity is
**not** a separate scorer term — the old `+ 0.05 * scarcity_value` addend was removed
because it double-counted scarcity and let general "hotness" leak into value.
Scarcity now has one home inside `_owner_advantage` and is constrained to *sandbox
scarcity*: the `+0.05` bump fires only when `alternative_assets_available` is empty
(no credible alternative solves the same buyer problem). When high scarcity coexists
with named alternatives the scorer emits `scarcity_inconsistent_with_alternatives`.
See §14b and `tests/test_bd_scorer_boundary.py`.

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

Primary class: `Layer15BuyerMatcher`. Single-asset flow:

```text
asset + buyer context
  -> hard gates (evaluate_bd_hard_gates)
  -> buyer problem fit
  -> BDActionabilityResult (carries killer_question_set)
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

**Search & Evaluation shortlist (Idea 13, 2026-06-30).** The single-asset read
above is driven over a whole universe for one buyer problem by
`intelligence/se_shortlist.py:build_se_shortlist` (pure join of
`ScienceThesisBuilder` -> `Layer15BuyerMatcher` -> `build_buyer_problem_shortlist`),
surfaced by the `bve-shortlist` CLI (table / json / memo) and the
`reporting/templates/se_shortlist.md.j2` template. Output shape:

```text
BuyerProblemShortlist
  .ranked:   list[ShortlistEntry]   # passed hard gates, sorted desc by bd_actionability
                                    #   each row carries decisive_killer_question (the spine)
  .excluded: list[ExcludedEntry]    # failed a hard gate; carries (asset_id, asset_name,
                                    #   failed_gates) so the analyst sees which door it hit (Idea 14)
```

Gate-failers are never scored; they appear in `excluded` with the exact gate token
they tripped (`ta_outside_buyer_strategy`, `target_outside_buyer_sandbox`,
`modality_excluded`, `does_not_solve_buyer_problem`, …). See §14b.

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

**Landing status (on `core-engine-v1`):**

- **Part 1 — Chris-aligned actionability (sections 9–11):** implemented in
  `science_thesis.py` (`EvidenceGrade`, `ShortlistEntry`,
  `build_buyer_problem_shortlist`).
- **Part 2 — dual-source buyer-problem intake + parallel compare:** two standalone
  modules.
  - `intelligence/buyer_problem_inferencer.py` — `BuyerProblemProvenance`
    (`analyst` / `inferred` / `analyst_corrected`); `BuyerProblemDraft` sidecar
    carrying provenance, `inference_confidence`, `evidence_citations`,
    `inferred_by_model`, `corrected_fields` (the core `BuyerProblem` stays clean);
    `BuyerProblemExtractor` protocol as the LLM-over-ingestion seam (no network
    dependency); `BuyerProblemInferencer.infer()` drafts from public data;
    `apply_analyst_correction()` is immutable and logs the inferred-vs-corrected
    diff per changed field through an injected sink.
  - `analysis/buyer_problem_reconciliation.py` — `reconcile_buyer_problem()` is a
    pure join of the problem-in `BuyerProblemShortlist` against universe-out scan
    scores, labelling each asset `agreed` / `problem_only` / `scan_only` /
    `neither`. It describes, never blends. `scan_only` surfaces strong broad-scan
    hits that failed the buyer's hard gates — the key feedback loop.

Not yet built: the weekly-runner hook to run both lenses on schedule, and the
later-phase news-driven discovery of new buyers/targets.

## 14. Killer-Question Spine (Batch A)

A new selection/ranking layer that sits **on top of** the science objects and
surfaces the 1–2 questions whose resolution actually decides an asset, ranked by
value-of-information (VOI). It is framed as the model's **proposed diligence
agenda, never the truth** — built falsifiable, overridable, and backtestable.
Grounded in the Chris Folts (gate-then-obsess-over-the-few-open-things) and
Harvey Chin (find the one or two questions that bifurcate the prediction) advice.

**New code:**

- `src/bve/intelligence/killer_question.py` — `KillerArchetype`,
  `KillerQuestion`, `KillerQuestionSet`, the `BranchValuator` protocol with a
  default `RnpvBranchValuator`, and `derive_killer_questions(...)`.
- `src/bve/config/clinical_meaningfulness_bars.yaml` +
  `src/bve/config/meaningfulness_bars.py` — per-indication effect-size bars
  (e.g. SCD 15% HbF, obesity ~20% TBWL), loaded with the `AssumptionsLoader`
  conventions (frozen data, `"other"` fallback + `UserWarning`).

**Archetypes (six).** Derived from — not identical to — the existing
`ScienceQuestion` source signals:

| Archetype | Reads (read-only) |
|---|---|
| `TARGET_VALIDITY` | `RIGHT_TARGET` (T) |
| `DELIVERY_EXPOSURE` | `ENOUGH_DRUG` (D), pre-human-dosing evidence basis |
| `DOSE_ADEQUACY` | `ENOUGH_DRUG` (D), human PK / dose-response basis |
| `DIFFERENTIATION` | `CLINICAL_MEANINGFULNESS` (M) + the bar registry |
| `TOLERABILITY_CEILING` | `SAFETY_MARGIN` (S) via guardrail flags |
| `NOVEL_OR_UNMODELED_RISK` | escape hatch — analyst/LLM-supplied question |

Delivery and dose share `ENOUGH_DRUG` but keep distinct labels and are made
mutually exclusive by evidence basis (pre-human → delivery; human dosing →
dose adequacy), so they never tie.

**How it ranks (three stages).**

1. *Liveness* — each archetype's predicate over the science objects decides
   whether the question is still open (e.g. a validated target makes
   `TARGET_VALIDITY` dormant; a claimed effect that clears the bar within noise
   makes `DIFFERENTIATION` dormant).
2. *VOI* — `voi = normalize(swing) × openness`, where `swing` is
   `|rNPV_confirmed − rNPV_refuted|` from two `compute_rnpv_full` runs (the
   governing phase's success probability forced high vs ~0) and `openness` comes
   from `EvidenceResolution`. Using the *spread*, not the absolute rNPV, cancels
   much of the far-out assumption noise. When no asset/valuator is supplied the
   VOI falls back to openness-only ranking.
3. *Select + safeguard* — rank candidates (top 5), mark only the top 1–2
   `decisive`, and **abstain** when the field is flat (no dominant question).
   A `company_focus_mismatch` flag fires when the sponsor is de-risking a
   different archetype than the one the model picked.

**Posterior (v1).** Deterministic: component score + a `+0.10` bump when the
evidence basis shows a human dose-response trend (Harvey's "barely-missed-but-
trended" should raise, not reset, confidence). The Bayesian updater is deferred.

**Ownership boundary (enforced).** `derive_killer_questions` only *reads*
`ScienceScoredQuestions` (T/D/B), `ScienceContext` (H/M), and `ScienceGuardrail`
(S); it never writes back into `compute_science_modifier` or POS. H/M/S can be
elevated to a decisive **diligence** question but are never reintroduced as
positive science-score components. A regression test asserts
`compute_science_modifier` output is byte-for-byte identical with and without the
killer engine having run.

**Tests:** `tests/test_killer_question.py` (13 anchors) — validated vs novel
target, CNS delivery, dose-response posterior lift, below-bar vs noise
differentiation, flat-field abstention, novel escape hatch, company-focus
mismatch, VOI ordering (stub valuator), and the ownership-boundary guard.

**Batch B wiring (implemented 2026-06-30):** `KillerQuestionSet` is now attached
to runtime `ScienceThesis`, copied onto `BDActionabilityResult`, summarized into
`science_summary.killer_question_set` and `bd_summary.killer_question_set`, and
rendered in the BD memo as a compact "Killer Question Diligence Agenda." BD
actionability diligence questions now include decisive killer questions when one
exists. Flat-field abstention remains visible in memo/JSON instead of forcing a
fake winner.

**Still deliberately deferred:** BD route bias and memo-headline rewriting. The
current wiring surfaces the diligence agenda but does not change POS, the science
modifier, BD actionability scoring, or `recommend_bd_route`.

## 14b. S&E Shortlist Cluster (Ideas 14 / 13 / 15, implemented 2026-06-30)

Chris's "the shortlist is the product" cluster. Built on the existing
`BuyerProblem` → `evaluate_bd_hard_gates` → `compute_bd_actionability` →
`build_buyer_problem_shortlist` chain; no new scoring, same ownership boundary
(POS / science modifier / `recommend_bd_route` untouched).

- **Idea 14 — gate audit trail.** `BuyerProblemShortlist.excluded` is now
  `list[ExcludedEntry]` (`asset_id`, `asset_name`, `failed_gates`) instead of bare
  ids. The build step threads the already-computed `result.failed_gates` through
  instead of discarding it, so every rejected asset shows *which* gate it tripped.
- **Idea 13 — S&E surface.** New pure driver `intelligence/se_shortlist.py`
  (`build_se_shortlist`) runs one buyer problem over a universe via
  `ScienceThesisBuilder` + `Layer15BuyerMatcher`. New `bve-shortlist` CLI
  (table / json / memo) + `reporting/templates/se_shortlist.md.j2`. Each ranked
  row carries the spine's decisive killer question
  (`ShortlistEntry.decisive_killer_question`) as the one thing to diligence.
- **Idea 15 — scorer boundary.** Scarcity now has **one home**:
  `buyer_owner_advantage`, set by the matcher and constrained to *sandbox
  scarcity* — the matcher's bump fires only when no credible alternative solves the
  same problem, and the scorer flags `scarcity_inconsistent_with_alternatives`
  when high scarcity coexists with named alternatives. The duplicate
  `+ 0.05 * scarcity_value` term was removed from `compute_bd_actionability`.
  `time_sensitivity` is routing-only and never enters the score. Locked by
  `tests/test_bd_scorer_boundary.py`.

Commits: gate trail `31f2d15`, S&E surface `fac8b05`, scorer boundary `a12b5c9`.

## 14c. Conviction Update Layer (Batch 2 — Harvey's falsification/posterior cluster)

Harvey's cluster (future_help Ideas 4/5/6/7). A **separate, auditable trail** that
raises *or lowers* conviction on a killer question as evidence arrives — and can
**refute**, which is where a falsification engine earns credibility. It updates
`KillerQuestion.posterior` only; it is **not POS and not scoring**. The posterior
never re-enters POS or `compute_science_modifier` — same hard ownership boundary as
the spine (§14) and the S&E cluster (§14b), pinned by a byte-identical test.

Built kernel-first (like Batch A's VOI kernel), then plug evidence sources in.

### PR-1 — kernel + readout interpreter (`6582ec4`, 2026-07-01)

New module `intelligence/conviction_update.py`; `tests/test_conviction_update.py`
(12 anchors).

- **`update_killer_question_posterior(question, updates, *, human_override=…)`** →
  `(new immutable KillerQuestion, ConvictionRecord)`. Composition is in
  **log-odds**: `L = logit(prior)`, each update adds
  `informativeness × ln(likelihood_ratio)`, `posterior = sigmoid(L)`, clamped to
  `(1e-6, 1-1e-6)`. This guarantees a single strong refutation is **never drowned by
  weak confirms**, and extremes never produce exactly 0/1.
- **`EvidenceUpdate` (frozen):** `source` (READOUT / DOSE_RESPONSE /
  EXPECTED_SIGNATURE / MANUAL), `likelihood_ratio` (>0), `informativeness` (0–1,
  Idea 5 weight), `rationale`, `provenance`, `as_of`, `direction`
  (CONFIRMING / REFUTING / NEUTRAL, derived from the LR).
- **`ConvictionRecord` (frozen):** the audit trail kept *off* `KillerQuestion` —
  `archetype`, `prior`, `posterior`, `updates`, `human_override`, `untested_flags`.
- **`interpret_readout` (Idea 7):** maps a clinical readout against the Batch-A
  clinical-meaningfulness bar (`MeaningfulnessBars.delta(indication)`) into four
  buckets → LRs: `clean_hit` 3.0, `near_miss_with_trend` 1.5, `clean_miss` 0.33,
  **`silence` → no update** (returns `None`). Noise band 5%, near-miss band 15%; LRs
  are named seed constants (`_LR_*`), calibration targets for the Idea 20 backtest,
  not final magic numbers.

**Hard boundaries (user-locked, test-pinned):** posterior never feeds POS or
`compute_science_modifier`; every update carries provenance + rationale; **refuting
updates are first-class**; **silence ≠ refutation** (absence of evidence is not
evidence of absence, and yields an explicit `untested` flag rather than a downgrade);
a **human override exists from day one** and is logged as an explicit MANUAL update,
never a hidden mutation. The behavior Harvey most wanted proven — his Amgen
"barely-missed-but-dose-response-trended" case — is a testable rule:
**near-miss + trend → posterior UP; near-miss + no trend → posterior DOWN.** Trend is
the discriminator (`test_trend_is_the_discriminator`).

### Surfacing — conviction trail into memo + JSON (`1b1cf38`, 2026-07-01)

The kernel is only useful if an analyst can see `prior → evidence update →
posterior`, so the follow-up wired the trail into output. **Presentation only — no
POS / science-modifier / route / scoring change.** `tests/test_conviction_surfacing.py`
(6 anchors); broad memo/report/engine/summary/layer15 regression 866 passed.

- **`EvidenceUpdate.label`** carries the human-facing bucket (e.g. `clean_hit`) as a
  first-class field; `conviction_record_to_dict` / `build_conviction_summary` are
  shared JSON-safe serializers in `conviction_update.py` (no duplicated walkers).
- **Carriers:** `ScienceThesis` and `BDActionabilityResult` each hold a read-only
  `conviction_records: list` (`exclude=True`, loosely typed — the same decoupling
  pattern as `killer_question_set`). Layer15 `_attach_killer_questions` copies the
  trail thesis → BD result alongside the killer set.
- **JSON:** `build_science_summary` / `build_bd_summary` emit a `conviction_trail`
  key (only when non-empty).
- **Memo:** a compact **Conviction Trail** block in `bd_memo.md.j2` — prior → posterior
  per archetype, and per update: source / bucket / LR / informativeness / rationale;
  header states explicitly it is a diligence artifact that does not feed POS or
  valuation. Context assembled by `_conviction_context` in `memo_generator`.

At the surfacing stage the trail was still invisible on normal runs
(`conviction_records` defaulted empty) — PR-2 supplied the first producer.

### PR-2 — dose-response producer (`ed1a225`, 2026-07-01)

The first in-pipeline producer. Replaces the hardcoded `+0.10` dose-adequacy
posterior bump with a log-odds `EvidenceUpdate` through the kernel, so the trail now
appears in memo/JSON on normal `bve-asset` runs when human dose-/exposure-response
evidence exists. `tests/test_dose_response_conviction.py` (5 anchors); engine/memo/e2e
regression 293 passed.

- **`killer_question._dose_adequacy`** now emits the **raw component score** as the
  posterior and only sets the `dose_response_trend` flag (trigger:
  `EvidenceResolutionBasis.HUMAN_DOSE_RESPONSE` / `HUMAN_EXPOSURE_RESPONSE`); the
  `_DOSE_RESPONSE_POSTERIOR_BONUS` constant is gone.
- **`conviction_update.apply_dose_response_conviction(kqs)`** finds flagged
  DOSE_ADEQUACY questions, applies a `DOSE_RESPONSE` `EvidenceUpdate` (LR 1.5) via
  `update_killer_question_posterior` → raised posterior + `ConvictionRecord`. Flat /
  no-trend questions are untouched (no update, no record); the set is returned
  unchanged when nothing fires.
- **`valuation_engine._attach_killer_questions`** runs the producer after deriving the
  set and attaches both `killer_question_set` and `conviction_records` to the thesis.
- **Directional preservation, now auditable:** trend > flat exactly as in Batch A, but
  the raise is a bounded log-odds update with a rationale trail rather than a flat add.
  Removing the inline bump does **not** change which question is decisive — VOI =
  `swing × openness`, and the posterior is not a selection input. (Footnote: at a 0.5
  prior, LR 1.5 coincidentally lands on +0.10; the tests use a 0.6 prior to prove the
  update is log-odds, not a flat add.)

### Pending (Batch 2)

- **PR-3 — Idea 4 expected signature (gated).** `hypothesis → expected-signature →
  evidence-check` against a **human-curated** mechanism/target signature library
  (`config/expected_signatures.yaml`, `meaningfulness_bars.py` pattern). Decision
  locked: **manual/config-fed v1 only — no data ingestion, no runtime free-form
  signature generation** (the hallucination trap). Match → CONFIRMING; contradiction
  → REFUTING; silence → no update + `signature_untested` flag.
- **Idea 20 backtest** is a *consumer* of the `ConvictionRecord` trail (picker/updater
  hit rate), not part of this batch; the record schema is shaped to plug in later.

Design doc (untracked, private): `docs/conviction_update_build_plan.md`.

## 15. Known Limits

- The science modifier is still heuristic, not calibrated.
- Guardrail caps and derates are priors, not fitted coefficients.
- T/D/B component scores are coarse evidence-presence and thesis-quality signals,
  not measured biological effect sizes.
- The overlap guard catches source-level reuse better than intent-level reuse.
- Public BD actionability is capped because public evidence is not buyer
  diligence.
- Human PoC and clinical meaningfulness are influential through BD and memo
  logic, not through another positive science multiplier.

## 16. Open Follow-Ups

- **Done 2026-06-30 (§14b):** S&E shortlist cluster — gate audit trail (Idea 14),
  `bve-shortlist` S&E surface (Idea 13), scarcity one-home scorer boundary (Idea 15).
- **Done 2026-07-01 (§14c):** Conviction Update Layer — PR-1 kernel + readout
  interpreter (`6582ec4`), conviction-trail surfacing into BD memo + JSON (`1b1cf38`),
  and PR-2 dose-response producer (`ed1a225`, first producer to fill the trail on
  normal runs). Pending in Batch 2: PR-3 curated expected-signature library (Idea 4,
  gated on the manual/config-fed data-source decision), Idea 20 backtest consuming
  `ConvictionRecord`. This supersedes the "Bayesian posterior updater" line below.
- The problem-in shortlist lens now exists as `build_se_shortlist` / `bve-shortlist`;
  remaining work is to wire the weekly runner to run *both* BD lenses (problem-in
  shortlist + universe-out scan) on schedule and emit the reconciliation report.
- Provide production `BuyerProblemExtractor` (LLM over ingested filings / press / CT.gov) persist analyst corrections KnowledgeStore.
- Later phase: news-driven discovery new buyers/targets feeding same pipeline.
- Consider BD route bias and memo-headline rewriting only after surfaced Killer-Question output stabilizes. Later batches: Bayesian posterior updater, catalyst-inflection view, killer-question backtest (picker hit rate).
- Re-baseline valuation snapshots affected by removing H/M/S from positive science scoring.
- Keep `science_guardrails` `science_phase_weights_tdb` synchronized across both assumptions YAML files.
- Add future changes to this file instead of the old session-summary document.
