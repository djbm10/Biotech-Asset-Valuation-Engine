# Session Work + Science Thesis Layer Breakdown

**Date:** 2026-06-22 (science layer merged into `core-engine-v1` 2026-06-27)
**Scope:** (1) recent engineering on `core-engine-v1`; (2) the Science Thesis layer, phases 1–10
**Source of truth:** current repository code and the phase plan docs

This file is formatted in the same spirit as `docs/full_mna_layer_breakdown.md`:
primary files, layer purpose, formulas, weights, boundaries, and known limits.
Part 1 documents the session's additive work. Part 2 is a standalone reference
for the Science Thesis layer, written so someone who has never opened the code
can understand what each phase owns and where its limits are.

## Table Of Contents

- [Part 1 — Session Work (`core-engine-v1`)](#part-1--session-work-core-engine-v1)
  - [ROI #2: Config-Quality Dashboard](#roi-2-config-quality-dashboard)
  - [ROI #3: Calibration Math](#roi-3-calibration-math)
  - [Slice-2 Materiality Mapping Audit](#slice-2-materiality-mapping-audit)
  - [Housekeeping And Branch Merge](#housekeeping-and-branch-merge)
- [Part 2 — Science Thesis Layer (Phases 1–10)](#part-2--science-thesis-layer-phases-110)
  - [Core Layer Files](#core-layer-files)
  - [Architecture Overview](#architecture-overview)
  - [Layer Ownership And Double-Counting Rules](#layer-ownership-and-double-counting-rules)
  - [The Seven Science Questions (TDBHMSQ)](#the-seven-science-questions-tdbhmsq)
  - [Phase 1: Scoring Contract + Heuristic Modifier](#phase-1-scoring-contract--heuristic-modifier)
  - [Phase 2: Deterministic Builder + BD Mode](#phase-2-deterministic-builder--bd-mode)
  - [Phase 3a/3b: Memo + Watchlist + CLI Surfacing](#phase-3a3b-memo--watchlist--cli-surfacing)
  - [Phase 4: Compact JSON Summaries](#phase-4-compact-json-summaries)
  - [Phase 5: Structured Evidence Landing Zone](#phase-5-structured-evidence-landing-zone)
  - [Phase 6a: Deterministic Evidence Extraction](#phase-6a-deterministic-evidence-extraction)
  - [Phase 6b: LLM Schema-Filling Extraction](#phase-6b-llm-schema-filling-extraction)
  - [Phase 7: Evidence Pipeline Wiring](#phase-7-evidence-pipeline-wiring)
  - [Phase 8: Evidence Artifact Persistence](#phase-8-evidence-artifact-persistence)
  - [Phase 9: Compact Evidence Surfacing](#phase-9-compact-evidence-surfacing)
  - [Phase 10a: Outcome Diagnostics](#phase-10a-outcome-diagnostics)
  - [Phase 10b: Calibration Readiness Hooks](#phase-10b-calibration-readiness-hooks)
  - [Validation And Known Limits](#validation-and-known-limits)

---

# Part 1 — Session Work (`core-engine-v1`)

After the test-suite-greening effort (ROI #1), the session worked through a
short, deliberately ordered list. Each item was additive, shipped as its own
commit, and was ordered so the cheap/informative work ran before the riskier
work it might justify.

## ROI #2: Config-Quality Dashboard

**Purpose:** Tell an analyst, before spending compute on an asset, how
trustworthy its YAML config actually is.

Primary files:

- `src/bve/ops/config_quality.py`
- `src/bve/cli/config_quality_report.py` (CLI `bve-config-quality`)
- `tests/test_config_quality.py` (17 tests)
- `pyproject.toml` (entry-point registration)

Core formula:

```text
completeness_score =
    Σ over scored fields [ field_weight * field_credit ]

field_credit (most fields) = 1.0 if present, 0.0 if defaulted
field_credit (commercial_inputs) = curated_funnel 1.0 / derived 0.5 / none 0.0
```

Top-level weights (`QUALITY_SCORE_VERSIONS["v1.0"]`, sum to 1.0):

| Field | Weight |
|---|---:|
| net_price_per_patient_usd | 0.20 |
| addressable_patients_annual | 0.15 |
| success_probability | 0.15 |
| commercial_inputs | 0.15 |
| total_addressable_market_millions | 0.10 |
| peak_penetration | 0.10 |
| patent_life_years | 0.05 |
| years_to_peak | 0.05 |
| discount_rate | 0.05 |

Design rules that keep it honest:

- **Versioned weights.** The weight table is labeled `v1.0` with an explicit
  `CURRENT_QUALITY_VERSION`. Re-scoring rules bumps the version so old reports
  stay interpretable — the same pattern as the actionable-score versions.
- **Two evidence axes kept separate.** A field can be weak because it is
  **missing** (`_meta.defaulted_fields`) or because it is present but only
  **coarsely sourced** (`commercial_inputs` provenance). These are scored
  independently; the second is *not* folded into the first.
- **`None`, not `0`, when metadata is absent.** A config with no quality metadata
  scores `None` (honest "unknown"), never a fake `0` that would read as "bad."

What it found: 20 derived M&A configs scored 0.23 (a curation queue); 45 replay
configs honestly returned n/a, confirming that quality metadata is not uniformly
present across config vintages. Materiality/leverage was deferred to slice 2.

## ROI #3: Calibration Math

**Purpose:** Measure whether the engine's probability predictions are
trustworthy — when it says 70%, do 70% of those happen?

Primary files:

- `src/bve/analysis/calibration_metrics.py` (`brier_decomposition`, `BrierDecomposition`)
- `src/bve/analysis/pos_calibration.py` (wired decomposition into existing report)
- `tests/test_calibration_decomposition.py` (11 tests)
- `docs/vision_reports/calibration_pack_2026-06.md` (dated artifact)

Design choice: **extend the three existing calibration modules** rather than add
a fourth `analysis/calibration.py` — avoids a competing "source of truth."

Core identity (Murphy 1973):

```text
binned_brier = reliability − resolution + uncertainty   (exact, to fp precision)

reliability  = how far stated probabilities sit from observed frequency (lower better)
resolution   = how well the model separates winners from losers (higher better)
uncertainty  = base-rate variance; the irreducible difficulty of the problem
```

Regression anchors (oncology dataset, authoritative path
`run_backtest_from_csv(csv).to_calibration_records()`, captured 2026-06-22):

| Metric | Value |
|---|---:|
| N | 145 |
| Brier | 0.2339 |
| AUC | 0.6941 |
| ECE | 0.1404 |
| reliability | 0.024 |
| resolution | 0.030 |
| uncertainty | 0.250 |

Boundaries: the anchors use the **real** model scores, not the deprecated
`load_from_backtest_csv` proxy (whose own warning says its metrics "do not
reflect true model performance"). The dated pack measures **prediction quality
only**, NOT trading P&L. Plain reading: adequately calibrated for directional
use, not a precision instrument.

## Slice-2 Materiality Mapping Audit

**Purpose:** Decide — report only, no feature code — whether the dashboard's
flagged fields can be joined to the tornado sensitivity outputs to rank "what
matters most" without inventing precision.

Primary file: `docs/vision_reports/slice2_materiality_mapping_audit_2026-06.md`.

Decisive structural fact: the tornado (`analysis/sensitivity.py`, 8 specs) shocks
**legacy `market_model` scalars only** and never touches the `commercial_inputs`
decomposition. Because 50/51 configs carry a TAM number, price / patient
population / gross-to-net are never the shock target.

Coverage: of 15 economic fields — exact 5, derived→unmapped 1, ambiguous 2,
unmapped 7. Of the 7 core categories, ≈3.5 map cleanly; **price, timing, and
cost do not map at all.**

Verdict: **do not build the materiality ranker yet.** It would silently omit
price, cost, and timing. Unblock it first with named sensitivity hooks (the next
planned task) or richer config provenance.

## Housekeeping And Branch Merge

- Refreshed stale `CLAUDE.md` POS-backtest numbers (N 99→145, P2 44.3%, P3
  59.1%, Brier 0.2339, AUC 0.6941, ECE 0.140 + Murphy pointers).
- Removed the leftover `/tmp/bve-ingestion-verify` Codex worktree.
- **Merged `science-wip/evidence-workflow` into `core-engine-v1`** (commit
  `ce5fab1`, `--no-ff`). Clean merge, no textual conflicts. Lint clean; full
  suite **14035 passed, 1 skipped**. Pushed to `origin/core-engine-v1`
  (`5e388e4..ce5fab1`). The pre-existing working-tree changes (`AGENTS.md` etc.)
  were never staged and stayed out of the push.

Session commit chain (config side): `c166839` → `f2f31a5` → `58b81ce` →
`cad897e` → summary docs → `ce5fab1` (merge).

---

# Part 2 — Science Thesis Layer (Phases 1–10)

The Science Thesis layer is a **deterministic, heuristic** Layer 0 subsystem. It
answers, *before* you trust a probability: "what must be biologically true for
this drug to work, and what is the actual evidence for each of those things?" It
is **not calibrated**, it makes **no network calls**, and — except the optional
Phase 6b extractor — it uses **no LLM**.

Governing contract: *missing evidence → lower confidence → diligence question →
next readout.* It must never fabricate PK/PD, biomarker validation, human
proof-of-concept, clinical meaningfulness, or buyer fit.

## Core Layer Files

- `src/bve/intelligence/science_thesis.py` (Phase 1 models + scoring + modifier + BD logic)
- `src/bve/intelligence/science_thesis_builder.py` (Phase 2 deterministic builder)
- `src/bve/intelligence/science_thesis_summary.py` (Phase 4 compact summaries)
- `src/bve/intelligence/science_evidence.py` (Phase 5 evidence schemas)
- `src/bve/intelligence/science_evidence_extractor.py` (Phase 6a deterministic mapper)
- `src/bve/intelligence/science_evidence_llm_extractor.py` (Phase 6b LLM extractor)
- `src/bve/intelligence/science_evidence_artifact.py` (Phase 8 persistence)
- `src/bve/intelligence/science_evidence_surface.py` (Phase 9 surfacing)
- `src/bve/intelligence/science_outcomes.py` (Phase 10a outcome diagnostics)
- `src/bve/intelligence/science_calibration.py` (Phase 10b calibration readiness)
- `src/bve/models/science_score.py` (shared science-score primitives)

Plan docs: `docs/vision_reports/science_thesis_layer_phase{1,2,4,5,6a,7,8_10}_plan.md`,
`docs/science_thesis_workflow.md`.

## Architecture Overview

One shared `ScienceThesis` object powers two operating modes:

```text
Discovery / Investment mode
  "what must be true?"
  -> score the 7 science questions (TDBHMSQ)
  -> binding constraint = weakest question
  -> heuristic POS modifier (auditable, NOT calibrated probability)
  -> belief update as evidence arrives

BD mode
  buyer problem definition
  -> hard gates (irrelevant assets gated out before scoring)
  -> BD actionability score
  -> deal route recommendation (avoid / option / collaboration / license / acquisition)
```

Evidence flows in from progressively richer sources, but always through the same
typed schema before it can touch a thesis:

```text
documents / readouts / decks / filings
  -> ScienceEvidenceItem / ScienceEvidenceBundle      (Phase 5 schema)
  -> deterministic mapper (6a) OR LLM extractor (6b)
  -> optional ScienceThesisBuilder.from_existing_evidence
  -> ScienceThesis -> modifier / BD result
  -> compact JSON summary (4) / memo + watchlist (3) / evidence surface (9)
  -> durable artifact (8) for replay without re-running the LLM
  -> retrospective outcome diagnostics (10a) -> calibration readiness (10b)
```

Both paths are **structured ranking and diligence-assistive logic, not a
validated probability model.**

## Layer Ownership And Double-Counting Rules

The central rule: the *thesis* (what is true) is kept separate from the *POS
modifier* (how that should nudge probability) and from *BD fit* (whether a
specific buyer should act).

| Signal | Owning piece | Rule |
|---|---|---|
| What must be biologically true | 7 science questions (Phase 1 components) | Each question scored once; the weakest is the binding constraint. |
| Nudge to technical POS | `ScienceModifierResult.heuristic_science_modifier` | Single auditable multiplier, capped; never relabeled as calibrated probability. |
| Program-killing facts | `ScienceKillFlag` + `modifier_cap` | Apply a hard cap once; not re-penalized downstream. |
| Buyer relevance | BD hard gates | Irrelevant assets fail before any BD scoring. |
| Buyer action priority | `BDActionabilityResult` | Computed only after hard gates pass. |
| Deal form | `BDRoute` | Recommendation only; not a probability. |
| Evidence facts | `ScienceEvidenceItem` (source-backed) | Items must carry a source; ambiguous/unsourced become warnings, never silent facts. |
| Retrospective failure reason | `ScienceOutcomeLabel` | Diagnostics only; never mutates weights. |
| Weight retuning | `ScienceCalibrationDiagnostic` | Always `weight_update_allowed=False`; recalibration is a separate phase. |

## The Seven Science Questions (TDBHMSQ)

Phase 1 decomposes a thesis into seven components. Six are the "must be true"
questions; the seventh (Q) is a cross-cutting evidence-quality grade.

| Key | Question (`ScienceQuestion`) | What it asks |
|---|---|---|
| T | `right_target` | Is this the right target / pathway? |
| D | `enough_drug` | Can you get enough drug to the target (PK/PD, exposure)? |
| B | `biomarker_translation` | Does the biomarker translate to clinical benefit? |
| H | `human_poc` | Is there human proof-of-concept? |
| M | `clinical_meaningfulness` | Is the effect clinically meaningful vs standard of care? |
| S | `safety_margin` | Is the safety / tolerability margin acceptable? |
| Q | (evidence quality) | How good is the evidence behind the above (species, model, sample size, reproducibility, independent validation, recency, source)? |

## Phase 1: Scoring Contract + Heuristic Modifier

**Purpose:** Create the minimum deterministic data shapes and scoring path so
Layer 0 can feed POS and BD workflows — keeping the thesis separate from the
probability modifier.

Primary file: `science_thesis.py`. Key models: `ScienceThesis`,
`ScienceComponentScore`, `ScienceModifierResult`, `BeliefState`.

Phase weights (`_PHASE_WEIGHTS`, per development stage — the same evidence
matters differently before vs after human data):

| Phase | T | D | B | H | M | S | Q |
|---|---:|---:|---:|---:|---:|---:|---:|
| preclinical | 0.30 | 0.25 | 0.20 | 0.05 | 0.05 | 0.05 | 0.10 |
| phase 1 | 0.20 | 0.30 | 0.20 | 0.10 | 0.05 | 0.05 | 0.10 |
| phase 2 | 0.15 | 0.15 | 0.15 | 0.25 | 0.15 | 0.10 | 0.05 |
| phase 3 / NDA-BLA | 0.10 | 0.10 | 0.10 | 0.25 | 0.20 | 0.20 | 0.05 |

Core formula (`compute_science_modifier`):

```text
weighted          = Σ component_score[k] * phase_weight[k]
binding_constraint = score of the weakest binding question (or manual override)

science_score     = min(weighted, binding_constraint + 0.15)
heuristic_modifier = 0.70 + 0.40 * science_score          # ranges 0.70 .. 1.10
modifier           = min(heuristic_modifier, modifier_cap)
```

Kill-flag caps (applied once, lowering `modifier_cap`):

| Condition | `ScienceKillFlag` | Cap |
|---|---|---:|
| Target/pathway refuted | `target_refuted` | 0.40 |
| Clear negative human POC | `negative_human_poc` | 0.60 |
| No feasible exposure at active dose | `infeasible_exposure` | 0.65 |

Key behaviors: the **binding constraint** ties the score to the weakest link
(`science_score` can never exceed it by more than 0.15). An **ambiguous** negative
human POC produces a warning, not a kill-flag (it won't fabricate certainty). A
high score with low confidence emits `low_confidence_high_score`.

Boundaries: this is an **auditable heuristic sensitivity**, not calibrated
probability math. Every result stamps `calibration_status = heuristic`,
`scoring_version = science_thesis_phase1`, `weight_set_version = phase1_v1`.

## Phase 2: Deterministic Builder + BD Mode

**Purpose:** Populate the Phase 1 contract from whatever the repo already knows
about an asset, apply buyer-specific BD logic, and never invent missing evidence.

Primary file: `science_thesis_builder.py` (`ScienceThesisBuilder`). It pulls from
existing science assessments, science results, and (when present) a
`ScienceEvidenceBundle`, then builds the seven components. Where evidence is
absent it records **gaps and diligence questions** instead of guessing — e.g.
`target_score = 0.65 if has_target_rationale else 0.40`.

It also derives the **binding question** (the component with the lowest score),
the **secondary questions** (other components under 0.50), and the **next
readout** that would resolve the binding question.

BD-mode logic in `science_thesis.py`:

- `evaluate_bd_hard_gates(buyer_problem, ...)` — returns failed gates; irrelevant
  assets are gated out before any scoring.
- `compute_bd_actionability(...)` — only runs if hard gates pass. Formula:

```text
bd_actionability =
    0.30 * buyer_problem_fit (+0.05 * time_sensitivity)
  + 0.15 * science_thesis_fit
  + 0.15 * evidence_quality
  + 0.10 * diligence_readiness
  + 0.10 * modality_capability_fit
  + 0.10 * buyer_owner_advantage (+ portfolio / lifecycle / scarcity bumps)
  + 0.10 * deal_feasibility (− 0.05 * internal_overlap_risk)
```

- `recommend_bd_route(...)` → `BDRoute`: `avoid` (fails gates / refuted) →
  `option` / `collaboration` → `license` → `acquisition`, gated on human-POC
  strength, strategic fit, and urgency thresholds (e.g. acquisition needs POC ≥
  0.70, fit ≥ 0.70, urgency ≥ 0.70).

## Phase 3a/3b: Memo + Watchlist + CLI Surfacing

**Purpose:** Make the thesis and BD-fit visible to users without changing
valuation math.

CLI flags (see `docs/science_thesis_workflow.md`):

```bash
bve-asset --config <cfg> --science-thesis                       # render thesis section
bve-asset --config <cfg> --science-thesis --apply-science-pos-modifier
bve-asset --config <cfg> --science-thesis \
          --buyer-problem <buyer.yaml> --buyer-problem-id <id>  # BD mode
```

Failure rules (fail clearly): `--apply-science-pos-modifier` requires
`--science-thesis`; `--buyer-problem` requires `--science-thesis`;
`--buyer-problem-id` requires `--buyer-problem`; unknown buyer-problem IDs error.

Boundaries: the modifier flag applies the heuristic modifier to the first
remaining technical POS — treat as sensitivity, not calibrated probability.

## Phase 4: Compact JSON Summaries

**Purpose:** Persist what users saw for audit/replay, without serializing the
full rich `ScienceThesis` / `BDActionabilityResult` objects.

Primary file: `science_thesis_summary.py`. Rule: **persist what users saw, not
every internal object** — compact, JSON-safe summaries only.

## Phase 5: Structured Evidence Landing Zone

**Purpose:** Add typed evidence objects and a conservative adapter, so future
extraction is safe. No document parsing, no LLM, no scoring change here.

Primary file: `science_evidence.py`. Key enums: `ScienceEvidenceDirection`
(supportive / negative / ambiguous / missing), `ScienceEvidenceSourceType`
(company_deck, press_release, clinical_readout, paper, SEC_filing, …),
`ScienceEvidenceMappedComponent` (T/D/B/H/M/S/Q), `ScienceEvidenceMappedField`
(target_pathway, pkpd, exposure, biomarker_validation, human_poc,
efficacy_signal, clinical_meaningfulness, …).

Boundary: items must be source-backed; the adapter maps conservatively into
`ScienceThesisBuilder` and does not score directly.

## Phase 6a: Deterministic Evidence Extraction

**Purpose:** Map existing **structured** repo objects into a
`ScienceEvidenceBundle`. A mapper, not an interpreter.

Primary file: `science_evidence_extractor.py`. Rule set:

```text
structured object has explicit source-backed evidence -> create ScienceEvidenceItem
structured object is ambiguous                         -> bundle warning / unresolved gap
structured object lacks source or quote/span           -> skip item and warn
```

## Phase 6b: LLM Schema-Filling Extraction

**Purpose:** Allow an LLM to fill the *same* evidence schema from unstructured
documents — fenced in tightly.

Primary file: `science_evidence_llm_extractor.py`. The LLM may extract
source-backed evidence items; it **may not** score science, modify POS, or
recommend. Output is still a `ScienceEvidenceBundle`, validated like any other.

## Phase 7: Evidence Pipeline Wiring

**Purpose:** Make the 6b extractor usable from existing document-replay /
ingestion flows. No new science logic — wiring only.

```text
document replay / ingestion -> ScienceEvidenceLLMExtractor -> ScienceEvidenceBundle
  -> optional ScienceThesisBuilder -> science_summary / memo output
```

## Phase 8: Evidence Artifact Persistence

**Purpose:** Make extracted evidence replayable and auditable without re-running
the LLM.

Primary file: `science_evidence_artifact.py` (`ScienceEvidenceArtifact`, a JSON
wrapper around a bundle). Identity / versioning fields: `schema_version`,
`extractor_version`, `prompt_version`, `model_id`, `document_hash`, `created_at`,
`source_document_id`, `asset_id`.

Replay CLI flags: `--science-evidence-output-dir`, `--science-evidence-artifact`,
`--science-evidence-artifact-hash-policy warn|fail|ignore`. A loaded-artifact
hash mismatch must warn or fail clearly.

Guardrails: persist compact validated artifacts (not rich runtime objects);
loading an artifact must avoid another LLM call and must not directly update POS,
BD actionability, or the thesis.

## Phase 9: Compact Evidence Surfacing

**Purpose:** Show source-backed evidence in human-facing output without long
dumps.

Primary file: `science_evidence_surface.py` (`build_compact_evidence_surface`).
Surfaces: evidence counts per component, top source-backed snippets,
rejected/ambiguous warning count, unresolved gaps. Full tables stay in the
artifact JSON; surfacing stays concise and creates no new scoring logic.

## Phase 10a: Outcome Diagnostics

**Purpose:** Define a retrospective outcome taxonomy *before* any calibration
work.

Primary file: `science_outcomes.py`. `ScienceOutcomeLabel`:

```text
target_pathway_failure · exposure_dose_failure · biomarker_translation_failure
efficacy_failure · safety_failure · commercial_strategic_failure · success · unknown
```

`ScienceOutcomeRecord` + `build_science_diagnostics(records) ->
ScienceDiagnosticsReport` aggregate deterministically by outcome, binding
question, modifier, and missing-evidence count.

Guardrails: diagnostics are retrospective only; science failures are kept
distinct from commercial/strategic failures; production weights are never
mutated.

## Phase 10b: Calibration Readiness Hooks

**Purpose:** Add readiness checks that explicitly *refuse* to retune heuristic
weights on small samples.

Primary file: `science_calibration.py`. `evaluate_calibration_readiness(n_labeled_cases,
min_cases_required=50, ...)` → `ScienceCalibrationDiagnostic` with
`calibration_status = "heuristic"` and **`weight_update_allowed = False`** always.
Recommendation enum: `insufficient_data` (< 50 labeled) → `diagnostics_only` →
`ready_for_recalibration_review`.

Guardrail: recalibration requires a separate, deliberate phase; small-sample
diagnostics are never permission to change weights.

## Validation And Known Limits

**Purpose:** State what is implemented and where this layer should be treated as
decision support, not ground truth.

Status:

- Phases 1–10 are implemented in code and merged into `core-engine-v1`
  (`ce5fab1`); full test suite green (14035 passed, 1 skipped).
- Useful today for structured diligence, ranking, and memo discipline.

Known limits:

- The modifier is **heuristic, not calibrated** — every result says so
  (`calibration_status = heuristic`). The 0.70–1.10 modifier band and the
  phase weights are evidence-informed priors, not fitted coefficients.
- Component scores are coarse (e.g. 0.65 vs 0.40 toggles on a boolean like
  `has_target_rationale`); they encode presence/absence of evidence, not
  graded effect sizes.
- Builder output is only as good as the structured inputs; absent evidence
  becomes a visible gap, which is the intended behavior but limits coverage.
- The LLM extractor (6b) may fill evidence but is firewalled from scoring;
  artifact loading never re-derives scores.
- A high science score is not a prediction of approval. It means the asset's
  current biological case is stronger under present evidence — and points at the
  one question that would change the picture.
