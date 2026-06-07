# Biotech Asset Valuation Engine (BVE) — Technical Report v2

**Repository:** `biotech-asset-valuation-engine`
**Report date:** 2026-05-17
**Scope:** Full code-level review of the upgraded codebase, with emphasis on
modules introduced since the prior report.

This report is written from source. Every section was produced by reading the
actual files in `src/bve/` and supporting configuration / tests, not from the
project's README or CLAUDE.md.

---

## Table of contents

1. Executive summary
2. Full system map
3. Data inputs (Pydantic schemas)
4. Core models and calculations
   - 4a. POS model — original log-odds + new calibrated system
   - 4b. Timeline distribution model
   - 4c. Revenue model (geography, payer access, label breadth, audits)
   - 4d. Cost model (CMC, confirmatory trials, tax profile)
   - 4e. rNPV model + financing / dilution / runway
   - 4f. Scenario analysis (shocks, scenario tree)
   - 4g. Monte Carlo (variable table, correlations, catalyst payoff)
   - 4h. Variant perception / implied expectations
   - 4i. M&A and acquisition intelligence
   - 4j. Intelligence engines
   - 4k. Composite scoring and decision layer
   - 4l. Monitoring and feedback
   - 4m. Capital structure and financing
   - 4n. Historical replay
5. Exact formula library
6. Configuration / YAML audit
7. Output artifacts
8. Tests and validation
9. Institutional-grade critique
10. Code-level issues
11. End-to-end example
12. Beginner explanation
13. Improvement roadmap
14. Final deliverables (one-pager, file table, glossary, key assumptions, risks, improvements)

---

## 1. Executive summary

### What the tool was, what it is now

The Biotech Asset Valuation Engine (BVE) began as a relatively standard
risk-adjusted NPV (rNPV) calculator. The earlier shape of the tool was:

- A YAML configuration describing a clinical asset, its trials, and a
  market model.
- A `ValuationEngine` that computed probability of success (POS) via a
  two-layer log-odds model (industry base rates with hand-calibrated
  qualitative adjusters), a deterministic revenue curve, probability-weighted
  trial costs, and a final rNPV plus Bull / Base / Bear scenarios and a
  Monte Carlo simulation.
- A small intelligence layer with a SQLite-backed knowledge store, a
  thesis tracker, and a weekly runner producing actionable recommendations
  for a fixed universe of biotech tickers.
- A historical replay loop that re-ran the decision policy against
  previously seeded prices and events for backtesting.

The current codebase is materially broader. It now contains:

- **Multiple parallel POS systems**. The original log-odds engine
  (`models/pos_model.py`) is still authoritative for `ValuationEngine`, but
  three new POS pathways live alongside it: a **statistically regressed
  mirror** (`pos_statistical.py`, explicitly marked as not empirically
  calibrated), a **Platt-scaled calibration layer** trained on the N=99
  oncology dataset (`pos_calibration.py`), and a **hierarchical Bayesian
  calibrated model** that blends per-bin posteriors with industry priors
  using the live `KnowledgeStore` (`pos_calibrated.py`). The
  `probability_stack.py` module composes a four-layer probability stack
  (technical, regulatory, label breadth, commercial realization) and
  exposes a `ProbabilityStack` artifact that downstream code can consume
  in place of a single PoS number.
- **Structured science diligence**. `science_score.py`,
  `trial_design_score.py`, `endpoint_validity.py`, `safety_scorer.py`,
  `sample_size_scorer.py`, `safety_context.py`, and `analog_matcher.py`
  together implement a deterministic, no-LLM science quality score with
  named subscores and rationales. They are designed to be both
  human-auditable and feedable into the probability stack.
- **A regulatory inference layer** (`regulatory_inference.py`) that
  produces a probability and timing distribution for FDA decisions.
- **A commercial and market-access subsystem**. `market_access.py`,
  `payer_access.py`, `geography.py`, `commercial_inputs.py`,
  `commercial_model_profile.py`, `launch_archetype.py`,
  `label_breadth_model.py`, `revenue_sanity.py`, and `revenue_audit.py`
  collectively replace the legacy single-knob revenue model with a
  driver-based commercial build keyed off launch archetypes, payer access
  states, geography weights, and label breadth probabilities. Sanity and
  audit modules check the resulting numbers against benchmarks.
- **A financing, dilution, runway, and capital-structure model**.
  `financing_risk.py`, `dilution_model.py`, `runway_forecast.py`,
  `valuation/financing_model.py`, and `intelligence/capital_structure.py`
  build a multi-tier distress model with explicit dilution scenarios that
  feed back into the probability stack.
- **An approval scenario and scenario tree framework**. Bull/Base/Bear
  scenarios are still produced by the engine, but `models/scenario_shock.py`,
  `models/scenario_tree.py`, and the parallel `valuation/scenario_tree.py`
  layer add a richer scenario-tree representation with approval-pathway
  branches (full approval, accelerated, conditional, CRL/resubmission,
  full failure). `approval_scenarios.py` weights those branches.
- **A revamped Monte Carlo layer**. `mc_variable_table.py` declares all
  uncertain variables, with distributions and bounds. `correlations.py`
  declares the cross-variable correlation matrix used by the Gaussian
  copula. `catalyst_payoff.py` adds catalyst-level payoff trees that can
  be fed into expected-value pricing of upcoming readouts.
- **An M&A / acquisition intelligence subsystem**. This is the largest
  new piece of work. Roughly twenty intelligence modules — including
  `ma_eligibility.py`, `ma_scoring.py`, `ma_calibration.py`,
  `ma_bd_decomposition.py`, `ma_layer3_gate.py`, `ma_layer4_routing.py`,
  `ma_layer5_calibration.py`, `acquisition_readiness.py`,
  `acquisition_likelihood.py`, `acquisition_fit.py`,
  `acquisition_screen.py`, `acquisition_memo.py`, `acquirer_profiles.py`,
  `acquirer_profile_validation.py`, `comparable_deals.py`, and
  `strategic_fit/strategic_fit.py` — combine to produce per-asset M&A
  scores, eligibility gates, acquirer-target fit matrices, comparable
  deals, and BD-style acquisition memos.
- **Intelligence engines**. Six new engine modules
  (`science_engine.py`, `dynamic_competition_engine.py`,
  `financing_engine.py`, `market_access_engine.py`,
  `variant_view_engine.py`, `catalyst_payoff_trees.py`) wrap the
  structured subsystems into orchestrators that the weekly runner can
  call. `composite_scorer.py`, `decision_layer.py`,
  `portfolio_decision_engine.py`, `recommender.py`,
  `mispricing_screener.py`, `readthrough_engine.py`,
  `variant_view.py`, `revaluation_triggers.py`, `competition_graph.py`,
  and `market_expectations.py` round out the intelligence stack.
- **Monitoring + feedback loop**. `continuous_monitoring.py`,
  `calibration_feedback_loop.py`, `operating_layer.py`, and
  `forecast_tracker.py` plus `revaluation_triggers.py` close the loop so
  that ex-post observations can be ingested and fed back into calibration.

### What business / investment problem it solves

The tool, taken end-to-end, supports three related decision contexts:

1. **Single-asset valuation for BD or licensing.** A user encodes an asset
   in a YAML file (e.g. `examples/configs/relay_rly2608.yaml`) and runs
   `bve-asset` to produce a memo, charts, a JSON artifact, and a scenario
   distribution. The memo is targeted by audience (BD, VC, HF). This is
   the longest-standing capability and is still the deepest path through
   the code.
2. **Portfolio / universe surveillance for a fund.** The intelligence
   layer maintains a knowledge store of thesis claims, events, and
   forecasts. The weekly runner re-ranks the tracked universe of biotech
   tickers and emits a `WeeklyActionableReport`. The new intelligence
   engines and composite scorer turn this from a single-score ranking into
   a multi-engine, multi-layer decision pipeline with monitoring and
   feedback. The historical replay module backtests the decision policy
   on a frozen no-lookahead store.
3. **Acquisition / M&A target identification.** The new M&A subsystem
   evaluates each tracked asset against an acquirer profile library and
   comparable-deal database, applies multi-layer eligibility and routing
   gates, and emits an `AcquisitionMemo` for the highest-fit candidates.

### Honest assessment

**What it does well.**

- *Transparent log-odds POS.* Every POS adjustment is traceable to a
  specific table entry, and the system warns when both `POSAdjusters` and
  `TrialDesignFeatureSet` adjust the same factor.
- *Structured science diligence without LLMs.* The
  `endpoint_validity`, `trial_design_score`, `safety_scorer`, and
  `sample_size_scorer` modules implement deterministic, auditable scoring
  with explicit rationales, modifier lists, deductions, and a quality
  tier.
- *Multi-indication and franchise cost-sharing math is real and tested.*
  Programs with primary + secondary indications correctly cascade PoS,
  apply per-indication cost-sharing, and surface
  `cost_sharing_benefit_millions`.
- *No-lookahead replay infrastructure.* The replay clock, isolated
  store, and `ThesisTracker.snapshot(as_of_date=...)` form a
  scientifically credible backtest substrate.
- *Calibration awareness baked into module-level constants.*
  `pos_statistical.IS_EMPIRICALLY_CALIBRATED = False` and the per-bin
  posterior approach in `pos_calibrated.py` mean that the system is
  honest about when it is and is not actually grounded in real outcome
  data.

**What it still does not do.**

- *The four-layer probability stack and the original `ValuationEngine`
  are not yet unified.* `valuation_engine.py` calls
  `ProbabilityModel`, which in turn calls `compute_pos` from
  `pos_model.py`. The `probability_stack` artifact is computed but is
  not the primary driver of rNPV in the existing engine path. This
  creates a real risk that downstream users see a `composite_pos` from
  the probability stack and a `cumulative_pos` from the original engine
  that disagree.
- *M&A intelligence is largely standalone.* The M&A modules consume the
  ValuationEngine's outputs in some paths but the acquisition score
  does not feed back into the per-asset rNPV. It is a parallel ranking
  system.
- *Calibration feedback is plumbed but lightly evidenced.* The
  `calibration_feedback_loop.py` module exists and is wired to the
  forecast tracker, but the actual write-back to the heuristic
  log-odds tables in `pos_model.py` does not happen — the heuristic
  tables are constants in source. The "feedback" updates a separate
  `CalibratedPOSModel` blend, which only the calibrated path uses.
- *Science score weights are still hand-set, not empirically derived.*
  `science_score.compute_science_score` uses fixed weights
  (`endpoint_validity 0.30, trial_design 0.30, analog 0.20, safety 0.20`)
  with no out-of-sample validation in the test suite.
- *Many of the new commercial inputs (geography, payer access, launch
  archetype, label breadth) are reasonable structurally but the
  default values and TA mappings are largely heuristic.* The audit /
  sanity layer catches gross errors but does not replace good inputs.
- *Output bloat.* Each run now produces ProbabilityStack,
  ScienceDiligenceResult, RegulatoryInferenceResult,
  ApprovalScenarios, LabelBreadthResult, TimelineDistributionResult,
  FinancingRiskV2, plus the legacy `ValuationOutput`. Without a
  curated front-end, a user has to know which artifact is canonical.

---

## 2. Full system map

### 2.1 Top-level package layout

`src/bve/` contains the following first-class subpackages. (File counts are
approximate — some packages have grown 5–10× since the prior report.)

| Subpackage           | Role                                                                                  | Approx. files |
|----------------------|---------------------------------------------------------------------------------------|---------------|
| `bve.entities`       | Core domain objects (`Asset`, `Company`, `ClinicalTrial`, `Indication`, `Acquirer`).  | ~6            |
| `bve.config`         | Industry assumptions YAML, the `AssumptionsLoader` singleton, calibration files.      | ~6            |
| `bve.models`         | All Pydantic models that participate in the valuation pipeline.                       | 55+           |
| `bve.valuation`      | The `ValuationEngine`, scenario builder, sensitivity, financing/scenario-tree helpers.| ~9            |
| `bve.analysis`       | Backtest harness, calibration metrics, sensitivity computation.                       | ~6            |
| `bve.empirical`      | Empirical POS engine + calibration / overlay artifacts. (Newer alternate POS path.)   | ~5            |
| `bve.expectations`   | Market-implied PoS back-solve.                                                        | ~2            |
| `bve.intelligence`   | The entire intelligence + M&A + decision layer (~80 modules).                         | ~90           |
| `bve.ingestion`      | Market data + reference price ingestion.                                              | ~3            |
| `bve.connectors`     | External data adapters (market prices, press releases).                               | ~3            |
| `bve.cli`            | All `bve-*` console entry points.                                                     | ~35           |
| `bve.reporting`      | Memo (Jinja → Markdown → Word), charts, exports, tables.                             | ~5            |
| `bve.visualization`  | Matplotlib chart functions for valuation, clinical timeline, competitor maps.         | ~4            |
| `bve.event_study`    | Catalyst event window utilities for replay attribution.                               | ~2            |
| `bve.ops`            | Operational glue: weekly runner, historical replay, metrics.                          | ~4            |
| `bve.pipeline`       | State machine, change detector, history replay, auto-config generator.                | ~6            |
| `bve.features`       | Trial-feature extraction.                                                             | ~2            |
| `bve.alerts`         | Slack / email / telegram / local channel dispatchers.                                 | ~6            |
| `bve.agents`         | LLM data-ingestion agents (FDA, ClinicalTrials, PubMed, SEC, News).                   | ~6            |
| `bve.ui`             | Streamlit dashboard (asset, opportunity) + cache.                                     | ~5            |
| `bve.services`       | Scheduler + rate limiter.                                                             | ~2            |
| `bve.utils`          | Trading-calendar helpers.                                                             | ~2            |

### 2.2 `bve.models` — file-by-file

The models package is now the single largest source-of-truth in the
codebase. Each file is described below in one paragraph.

**Pre-existing core (extended).**

- `asset.py` (in `bve.entities`) — frozen Pydantic `Asset` with id, company id,
  therapeutic area, modality, indication, stage, approval pathway, discount
  rate, effective tax rate, NOL benefit years, mechanism of action, post-
  approval R&D, net ownership.
- `entities/trial.py` — `ClinicalTrial` (phase, cost, cost_source enum,
  success_probability, design adjusters input). Includes `EndpointType`,
  `GeneTherapyConcern`, `TrialPhase` enums.
- `models/market_model.py` — `MarketModel` (TAM mode, patient mode, or
  `LineOfTherapySegment` list). Carries `cogs_rate`, SG&A profile,
  `compliance_rate`, lifecycle events, optional `commercial_model` profile,
  modality, geography weights, etc.
- `models/probability_model.py` — bridges between trial-level success
  probabilities and per-phase / cumulative POS used by `RNPVModel`.
- `models/revenue_model.py` — applies LOE erosion, the three revenue modes
  (LOT, patient×price, TAM), peak penetration, peak duration, and now emits a
  `revenue_audit` table by year.
- `models/cost_model.py` — probability-weighted PV of trial R&D costs, deal
  share, CMC costs, post-approval R&D, confirmatory trial costs, optional
  inflation adjustment.
- `models/rnpv_model.py` — composes prob × PV(EBIT) − PV(costs) + milestones.
- `models/monte_carlo.py` — Gaussian-copula MC over the
  `MCVariableTable` (see below) using correlations from `correlations.py`.
- `models/drug_asset_program.py` — frozen container that bundles
  `Asset`, trial list, `MarketModel`, `DealEconomics`, `CommercialPlan`,
  `CMCCosts`, cost-inflation rate, optional `ConfirmatoryTrialObligation`.
- `models/competition_model.py` — `CrowdingModel`, `FirstMoverConfig`,
  `ClassSaturationProfile` (unchanged in shape but reused by new engines).
- `models/multi_indication.py` — `MultiIndicationProgram` and the cascade
  PoS + franchise cost sharing engine.
- `models/catalyst_model.py` — catalyst event timeline model used by
  ranking and EV computation.

**POS subsystem (one original + three new paths).**

- `models/pos_model.py` — the canonical heuristic log-odds engine. Defines
  `POSAdjusters` (endpoint type, MoA precedent, sample size adequacy,
  safety profile, competitive pressure, biomarker selection, prior phase
  data, BTD flag, extraordinary evidence flag, gene/cell therapy concerns,
  MoA exception flags). Implements `compute_pos`,
  `_compute_layer1_adjustment`, `apply_pos_to_trials`. Tables include
  TA-specific endpoint log-odds for ~14 therapeutic areas, gene/cell
  therapy concern overlays, sample-size and safety log-odds with legacy
  aliases. Layer-1 cap is ±0.80 (extended positive cap +1.00 when
  `extraordinary_evidence=True`). Includes accelerated-approval base-rate
  discount of 18% at NDA/BLA.
- `models/trial_design_features.py` — second POS layer (existing). Provides
  `TrialDesignFeatureSet` and `check_pos_layer_overlap` to flag
  double-counting against `POSAdjusters`.
- `models/pos_statistical.py` — logistic-regression mirror of the heuristic
  model. Explicitly declares `IS_EMPIRICALLY_CALIBRATED = False`. Trained
  at module load on a synthetic 750-program dataset whose
  data-generating process is `pos_model.py` itself. Useful for inspecting
  feature contributions and for the `retrain_on_csv()` path, but not an
  independent calibration source.
- `models/pos_calibration.py` — Platt-scaling layer trained on the
  research/data/oncology_phase_transitions.csv N=99 dataset.
  `POSCalibrationLayer.fit_on_oncology_dataset()` returns slope, intercept,
  Brier, ECE, calibration improvement, net bias label.
- `models/pos_calibrated.py` — `CalibratedPOSModel`, a hierarchical
  Bayesian model. Builds per-(TA, phase) bins from records in the live
  `KnowledgeStore` (or supplied in-memory). Uses N_PRIOR_ONLY=10 and
  N_FULL_POSTERIOR=50 to blend a Jeffreys-prior Beta posterior with the
  industry prior. Exposes `base_rate`, `confidence_interval`, `bin_summary`,
  `all_bins`. Constructed via `from_records` or `from_store`. This is the
  closest thing the system has to a true calibrated PoS source.
- `models/probability_stack.py` — composes a four-layer probability stack:
  technical success, regulatory approval, label breadth, commercial
  realization. Has two distinct versions:
  - **Phase-E form** (`build_probability_stack`, `ProbabilityStackInputs/
    Result`) blends `base_pos`, science / design scores, regulatory
    inference, label breadth, financing, market access, management
    execution, and competitor read-through.
  - **Step-7 form** (`compute_probability_stack`, `ProbabilityStack`,
    `ProbabilityLayerV2`) uses fixed per-phase base rates
    (`PHASE_BASE_RATES`), applies science / financing / regulatory
    designation modifiers, and produces scenario probabilities for
    `ApprovalScenarioV2` (FULL_APPROVAL, ACCELERATED, CONDITIONAL,
    CRL_RESUBMISSION, COMPLETE_FAILURE).
- `models/science_score.py` — `ScienceScore` / `ScienceDiligenceResult`.
  `compute_science_score()` weights endpoint validity (0.30), trial
  design (0.30), analog (0.20), safety (0.20) — only including
  sub-scores whose `confidence > 0.2`. The output carries top positives,
  top risks, and rationales for every subscore.
- `models/trial_design_score.py` — `TrialDesignQualityScore`. Eight
  dimensions (randomization, blinding, comparator, sample size,
  endpoint appropriateness, population selection, statistical power,
  duration) with phase-specific weights (`_PHASE_WEIGHTS`). Output tiers
  EXCELLENT / GOOD / ADEQUATE / WEAK with `pos_multiplier` ranging from
  1.10 down to 0.80. Used by `science_score` and downstream by the
  probability stack.
- `models/endpoint_validity.py` — `score_endpoint(name, is_primary)` looks
  up an `EndpointProfile` from `ENDPOINT_LIBRARY` (covers OS, PFS, ORR,
  DFS, EFS, CR, DOR, TTP, MRD, pCR, PRO, HbA1c, LDL, FEV1, ACR, EASI,
  psychiatric PRO scales). Each profile has a `RegulatoryWeight` of
  GOLD (1.0), SILVER (0.85), BRONZE (0.65), or EXPLORATORY (0.40).
  Secondary endpoints receive a 0.90× adjustment.
- `models/safety_scorer.py` — `score_safety(SafetyParams)` returns
  `SafetyScoringResult`. Combines a base log-odds adjustment from a
  `SafetyProfile` enum with seven additive modifiers (reversible,
  monitorable, comparable to control, high discontinuation rate,
  treatment-related deaths, organ-toxicity signal, class-known risk).
  Final adjustment clamped to [−0.90, +0.15].
- `models/sample_size_scorer.py` — `score_sample_size(SampleSizeParams)`.
  Computes effective N = planned × (1 − dropout) × design-efficiency
  multiplier. Calculates statistical power from continuous (Cohen's d
  → two-sample t) or binary (control rate + risk difference →
  two-proportion Z) formulas. Maps power to a tier
  (WELL_POWERED ≥0.90, ADEQUATE ≥0.80, BORDERLINE ≥0.70, otherwise
  UNDERPOWERED). Applies a design tier cap (single arm → BORDERLINE,
  exploratory/registry → EXPLORATORY) and a TA-specific minimum-N
  downgrade table covering 14 TAs (rare disease minimum N=15 in Phase 2,
  cardiovascular 1000 in Phase 3). High-placebo-response penalty for
  CNS / psychiatry binary endpoints.
- `models/safety_context.py` — `SafetyContextV2`,
  `compute_safety_context(asset_id, signals)`. Aggregates list of
  `SafetySignalV2` events into an overall_safety_score, rationale, and
  tiered alerts. Consumed by `science_score`.
- `models/analog_matcher.py` — Token-based mechanism × indication match
  against a 30-entry curated `ANALOG_DATABASE` of well-known drug
  programs (GLP-1, PCSK9, PD-1/L1, KRAS G12C, CAR-T, gene therapy,
  BTK, CDK4/6, PARP, EGFR, IL-17/23, SGLT2, RNAi, etc.). Returns
  `AnalogMatchResult` with success rate, failure rate, analog score
  (`success_rate` if ≥0.6, `1 - failure_rate` if failure rate ≥0.6,
  else 0.5), and median peak sales.
- `models/timeline_distribution_model.py` — Two versions:
  `infer_timeline_distribution()` (Phase-E) returns a single
  on-time / delayed pair with a delay probability blending design,
  regulatory, and financing risk; and `compute_timeline_distribution()`
  (Step 7) walks the phase order, applies fast-track / breakthrough /
  enrollment-status / prior-hold modifiers, and produces a per-phase
  `PhaseTimeline` with p10/p50/p90 months + `TimelineRisk`
  classification (on_track / minor_delay / major_delay / hold /
  terminated) and overall delay probability.

**Regulatory and approval scenarios.**

- `models/regulatory_inference.py` — produces
  `RegulatoryInferenceResult` (approval probability + rationale) used by
  `probability_stack`.
- `models/approval_scenarios.py` —
  `build_approval_scenarios(ApprovalScenarioInputs)` returns a list of
  `ApprovalScenarioWeight` (full / accelerated / CRL / etc.) feeding
  the probability stack.
- `models/management_risk.py` — encodes management execution and
  governance risk, plugged into the Step-7 probability stack via
  `management_execution_score`.

**Commercial and market access.**

- `models/market_access.py` — payer dynamics scoring. Inputs include
  formulary tier, prior auth burden, cost-effectiveness risk, step-edit
  requirement, RWE requirement, Medicare-heavy flag, orphan-drug
  designation, WAC, commercial coverage %, net/list ratio. Output
  `MarketAccessResult` carries an effective patient pool multiplier
  (range 0.30–1.0), adoption-speed modifier (−0.30 to +0.10), peak
  penetration modifier (−0.20 to +0.05), net-price durability years,
  access risk score / tier, and explicit risk / tailwind lists.
- `models/payer_access.py` — sister module focused on the payer-access
  state machine (negotiation outcomes, formulary placement decisions).
- `models/geography.py` — geography decomposition (US, EU5, Japan,
  rest-of-world) with per-region weights, launch lag months, gross-to-net
  ratios, and currency normalization.
- `models/commercial_inputs.py` — driver-based commercial build (price,
  patient volume, compliance, market share trajectory). Replaces the
  legacy two-knob revenue model when a profile is selected.
- `models/commercial_model_profile.py` — named profile (specialty pharma,
  rare disease, gene/cell therapy, primary care) that supplies SG&A,
  COGS, ramp, geography defaults.
- `models/launch_archetype.py` — launch shape: fast specialty,
  conservative primary care, single-administration gene therapy, etc.
- `models/label_breadth_model.py` — `infer_label_breadth(LabelBreadthInputs)`
  returns broad-label probability conditional on design, biomarker logic,
  safety, regulatory approval, endpoint strength.
- `models/revenue_audit.py` — declarative audit-row schema attached to
  `RevenueResult.audit_table`. Each year carries patient count, price,
  COGS, SG&A, EBIT, PV, sources for each figure.
- `models/revenue_sanity.py` — runtime sanity checks
  (`check_commercial_assumptions(MarketModel)`) emitted as `UserWarning`s
  (e.g. price/volume mismatches, off-formulary assumptions for
  Medicare-heavy indications, etc.).

**Cost subsystem.**

- `models/cmc_costs.py` — Chemistry, Manufacturing, and Controls costs
  (process development, validation, GMP runs).
- `models/confirmatory_trial.py` — `ConfirmatoryTrialObligation` for
  accelerated-approval assets. Carries status enum
  (`ConfirmatoryTrialStatus.WITHDRAWN_FAILED` triggers a warning in
  `ValuationEngine.run`).
- `models/tax_profile.py` — effective tax rate by jurisdiction, NOL carryforward
  treatment, R&D credit utilization assumptions.
- `models/deal_models.py` — `ComparableDeal`, `ComparableDealAnalysis`.
  Standalone module (no cycle with `intelligence/comparable_deals.py`).

**Financing / capital structure.**

- `models/financing_risk.py` — both the legacy `FinancingRiskAssessment`
  and the Step-4 `FinancingRiskV2` model. `compute_financing_risk()`
  takes cash, monthly burn, market cap, catalyst months away, trial
  cost remaining and produces runway, dilution low/mid/high estimates,
  `DistressTier` (NONE / LOW / MEDIUM / HIGH / CRITICAL),
  `financing_adjusted_value_haircut` (1.00 at NONE, down to 0.50 at
  CRITICAL).
- `models/dilution_model.py` — `compute_dilution_scenarios()` produces
  low/mid/high dilution given current shares, current price, and
  capital needed.
- `models/runway_forecast.py` — `RunwayForecastV2` and `compute_runway()`.
  Takes asset id, cash on hand, burn rate (`estimate_burn_rate`).

**Scenario tree and shocks.**

- `models/scenario_shock.py` — declarative shock definitions (peak sales
  ±30%, discount rate ±2pp, POS ±20%, patent life ±3yrs, peak
  penetration ±30%, tax ±5pp, gross-to-net ±10pp, competitor +1/+2).
- `models/scenario_tree.py` — `ScenarioTree` structure with named
  branches (Bull / Base / Bear or arbitrary tree).
- `models/mc_variable_table.py` — declarative table of Monte Carlo
  variables with distributions and bounds.
- `models/correlations.py` — Gaussian-copula correlation matrix between
  MC variables.
- `models/catalyst_payoff.py` — `compute_catalyst_payoff()` produces a
  `CatalystPayoffResult` (binary up / down / no-move EV decomposition
  for a near-term catalyst).
- `models/evidence_grade.py` — letter-grade classification (A/B/C/D) of
  the evidence base for a given thesis claim.

### 2.3 `bve.valuation` — file-by-file

- `valuation/valuation_engine.py` — the main orchestrator. Constructor
  takes `Asset`, `Company`, list of `ClinicalTrial`, `MarketModel`,
  optional `Indication`, per-phase `POSAdjusters`, per-phase
  `TrialDesignFeatureSet`, MC params, comparable deals, an optional
  `empirical_pos_engine`, and a `pos_mode` string
  (`"heuristic" | "empirical_raw" | "empirical_calibrated" |
  "empirical_fitted"`). `from_program()` builds the engine from a
  `DrugAssetProgram`. `run()` returns a `ValuationOutput` with
  base-case rNPV, scenarios, Monte Carlo, sensitivities, assumption
  log, lifecycle event summary, provenance (config + assumptions
  hashes), comps fair-value band, revenue audit, market expectation,
  catalyst payoff, analog match, top acquirers, runway forecast,
  dilution analysis, and variant perception.
- `valuation/scenario.py` — original `build_scenarios()` returning Bull /
  Base / Bear.
- `valuation/scenario_tree.py` — Step-7 scenario tree builder consuming
  `models/scenario_tree.py` definitions and producing per-branch rNPV
  with probabilities for downstream EV aggregation.
- `valuation/assumptions.py` — `build_assumption_log()`. Walks every key
  number in the run and labels it with its source (`assumptions_loader`
  path, analyst override, default, etc.) and a sensitivity rating.
- `valuation/implied_expectations.py` — back-solver that compares model
  rNPV to the trading EV and emits implied PoS, implied peak sales,
  and an implied discount rate.
- `valuation/financing_model.py` — financing scenario tree (no raise /
  bridge / follow-on / dilutive / partnership) consuming
  `FinancingRiskV2` outputs and producing per-scenario rNPV adjustments.
- `valuation/outputs.py` — `ValuationOutput` Pydantic model carrying
  every produced artifact. ~30 fields.
- `valuation/portfolio.py` — multi-asset portfolio aggregation.

### 2.4 `bve.intelligence` — file-by-file (the major upgrade surface)

Because this package has expanded so dramatically, I have grouped the
files into logical clusters rather than walking them strictly in
filesystem order.

**Knowledge layer + thesis tracking (existing, lightly extended).**

- `knowledge_layer.py` — SQLite-backed `KnowledgeStore`. Tables for
  thesis claims, events, forecasts, decisions, plus calibration tables
  (`pos_predictions`, `pos_outcomes`). All new layers (decision layer,
  forecast tracker, calibration feedback) attach extra tables here.
- `thesis_tracker.py` — `ThesisTracker.snapshot(asset_id, as_of_date)`.
  Supports time-frozen queries for replay.
- `actionable_output.py` — `ActionableGenerator` and
  `WeeklyActionableReport`. Composite formula: `ranking × 0.50 +
  thesis × 0.30 + opportunity × 0.20`. With thesis_strength=None the
  neutral 0.5 is used. Assets scoring ≥0.50 receive "add".
- `taxonomy.py` — controlled vocabularies for claim types, indication
  buckets, modality groups.
- `catalyst_calendar.py` — calendar of upcoming catalysts; consumed by
  the catalyst payoff trees and ranking.
- `catalyst_ev.py` — `CatalystEVCalculator` (Wave 1) that computes
  expected value of upcoming events with up / no-move / down branches.

**Composite scoring + decision (the new ranking stack).**

- `composite_scorer.py` — six additive signal layers
  (catalyst_ev, enrollment flags, phase correlation Bayesian posterior
  delta, endpoint z-score, competitor impact, capital risk) sitting on
  top of the legacy base composite. Weights loaded from
  `industry_assumptions.yaml` under `scoring_weights:`.
- `decision_layer.py` — Wave-J record-keeping for decisions, positions,
  and outcome attributions. Three SQLite tables (`decision_records`,
  `position_snapshots`, `outcome_attributions`) with explicit
  recommended vs executed action, portfolio exposure snapshot,
  attribution taxonomy (pos_error, timing_error, sizing_error,
  thesis_error, market_drift, confirmed_thesis, unclassified).
- `position_policy.py` — sizing rules per conviction tier and liquidity
  bucket.
- `portfolio_decision_engine.py` — orchestrator that takes
  ScoredCandidates, current positions, capacity, and risk limits, and
  emits a list of `DecisionRecord` recommendations.
- `recommender.py` — exposed Recommender interface used by the weekly
  runner. Produces `ScoredCandidate` lists.
- `mispricing_screener.py` — screens the universe for mispricing using
  variant view vs market expectations.
- `variant_view.py` and `variant_view_engine.py` — produce a
  per-asset "variant view" (model output vs consensus) with confidence
  bands.
- `market_expectations.py` — consensus expectations (street EPS, peak
  sales, PoS) for comparison.
- `readthrough_engine.py` — given an event for asset A, estimate the
  read-through impact on related assets B (same target / same TA / same
  mechanism / shared sponsor).
- `revaluation_triggers.py` — declarative trigger rules
  (catalyst hit / missed, thesis claim refuted / confirmed, financing
  event) that cue revaluation.
- `competition_graph.py` — graph data structure connecting assets to
  competitors and shared mechanisms; consumed by readthrough and the
  dynamic competition engine.

**Intelligence engines.**

- `science_engine.py` — wraps the deterministic `science_score` /
  `trial_design_score` / `endpoint_validity` modules into a single
  `ScienceAssessment` per asset, with named subscores and
  confidence band. Used by `probability_stack`.
- `dynamic_competition_engine.py` — builds a time-varying competition
  model from the competition graph, replacing the static
  `CompetitionModel` for assets that have live competitor catalysts.
- `financing_engine.py` — wraps `FinancingRiskV2`,
  `RunwayForecastV2`, dilution, and capital structure into one
  per-asset `FinancingAssessment`.
- `market_access_engine.py` — wraps `MarketAccess` / `PayerAccess`
  modules.
- `catalyst_payoff_trees.py` — builds the multi-branch payoff trees for
  each upcoming catalyst. Distinct from `models/catalyst_payoff.py`
  which is the per-asset binary EV computation.
- `continuous_monitoring.py` — daily ingestion loop that updates
  position snapshots, recomputes scores, fires revaluation triggers.
- `calibration_feedback_loop.py` — when an outcome resolves
  (`OutcomeAttribution`), updates the `pos_outcomes` table so
  `CalibratedPOSModel.from_store()` produces a refreshed posterior.
- `operating_layer.py` — coordinator that runs the daily / weekly
  monitoring cadence, materializing snapshots into the KnowledgeStore.
- `forecast_tracker.py` — records consensus forecasts and the model's
  own forecasts over time; supports calibration drift detection.

**M&A subsystem (entirely new).**

- `ma_eligibility.py` — Layer 0 (eligibility, deal-type routing,
  affordability, encumbrance, complexity, distress guard, data
  confidence). Returns `Layer0Result` consumed by all downstream
  scoring.
- `ma_scoring.py` — Layer 2 BD Decision Engine. Three decomposed
  sub-scores (`TargetAttractivenessScore`, `DealLikelihoodScore`,
  `AcquirerFitDecomposed`), saturation penalties, financing-pressure
  gate, transaction-driver counting, dual-gate cap, 2×3 BD action
  matrix, watchlist classification (`STRATEGIC_WATCH` vs
  `NEAR_TERM_TRANSACTION`).
- `ma_calibration.py` — calibration of M&A scoring against historical
  deal outcomes (precision / recall, threshold tuning).
- `ma_bd_decomposition.py` — full decomposition of the BD score into
  named components for reporting (used by `acquisition_memo.py`).
- `ma_layer3_gate.py` — Layer 3 gates (additional checks beyond
  Layer 0/2; e.g. recent IPO blackout, regulatory blockers).
- `ma_layer4_routing.py` — routes scored candidates to specialized
  scoring pipelines based on deal type (single-asset vs platform vs
  commercial-franchise).
- `ma_layer5_calibration.py` — applies an empirical calibration curve
  to the raw composite (Platt-like scaling so output approximates a
  probability rather than a pure rank).
- `acquisition_readiness.py` — per-target readiness score (data room
  maturity, IP cleanliness, partnership conflicts).
- `acquisition_likelihood.py` — final M&A probability output for the
  weekly runner.
- `acquisition_fit.py` — pairwise acquirer × target fit scoring.
- `acquisition_screen.py` — universe-level screen; emits the ranked
  watchlist.
- `acquisition_memo.py` — Markdown / Word memo generator for the
  highest-fit candidates.
- `acquirer_profiles.py` — profile library of ~30 large biopharma
  acquirers with TA priorities, modality preferences, budget tiers,
  recent deal history.
- `acquirer_profile_validation.py` — schema validation for
  `acquirer_profiles.yaml` and integrity checks across the library.
- `comparable_deals.py` — `ComparableDealMatcher` (matches against
  curated deal database; produces fair value band) plus
  `ComparableDealSet` data structure.
- `strategic_fit/strategic_fit.py` — strategic fit scoring with the
  acquirer-side perspective (what does the acquirer need; how well
  does this target fill that gap).
- `evidence_ingestion.py` — pulls evidence (deal announcements,
  partnership filings, executive moves) into the KnowledgeStore for
  use by the M&A engine.

**Other intelligence modules (operational + research).**

- `replay_clock.py` — `ReplayClock` for the historical replay loop.
- `capital_structure.py` — `CapitalStructureAssessment` with
  `CapitalRiskLevel` (LOW / MEDIUM / HIGH / CRITICAL) consumed by
  `composite_scorer`.
- `target_monitor.py` — monitors progress of identified M&A targets.
- `research_report.py` — long-form research report generator.
- `weekly_brief.py` — concise weekly brief format.
- `weekly_review.py` — engine that classifies thesis outcomes
  (confirmed / refuted / expired) for review meetings.
- `portfolio_ranking.py`, `portfolio_sizing.py` — companion modules
  that produce ranked / sized portfolio outputs.
- `trial_design_assessment.py` — converts raw trial features into a
  structured assessment (feeder for `trial_design_score`).
- `trial_design_feature_extractor.py` — LLM-assisted feature
  extraction from CSR / press release text.
- `competitor_discovery.py`, `competitor_catalyst_linker.py` — discover
  competitor pipelines and link competitor catalysts to focal asset.
- `cross_asset_propagation.py` — event propagation across related
  assets in the universe.
- `event_impact_ledger.py` — ledger of event impacts on prices /
  forecasts.
- `enrollment_snapshot_extractor.py` — enrollment-rate snapshot
  extraction from ClinicalTrials.gov.
- `phase_correlation_updater.py` — Bayesian update of PoS given
  intra-phase events (Wave 5).
- `pdufa_extractor.py` — PDUFA date extraction from FDA filings.
- `endpoint_benchmarking.py` — competitor / historical endpoint
  benchmarking (`EndpointEvaluation` with z-score; Wave 6).
- `opportunity_scanner.py`, `opportunity_monitor.py`,
  `opportunity_snapshot.py` — older opportunity-screen path that
  has been partially superseded by the composite_scorer pipeline but
  is still wired in.
- `conference_detector.py`, `earnings_transcript.py` — text-based
  ingestion adapters.
- `price_reaction.py` — price reaction analysis around catalyst
  events.
- `trade_attribution.py` — backtest trade attribution.
- `kg_integrity.py` — knowledge-graph integrity checks (orphan
  records, broken refs).
- `memo_generation.py`, `moa_summary_agent.py`,
  `literature_review_agent.py`, `investment_memo_agent.py`,
  `critic_agent.py` — text-generation agents that consume the
  knowledge store.
- `mapping.py`, `phase2/` — entity resolution and mapping rules.
- `extraction/` — LLM extraction utilities (prompt builder, llm
  client, result schema, validation, raw_document).
- `schemas/` — typed schemas for `core`, `proposals`, `knowledge`,
  `runs`, `signals`.

### 2.5 End-to-end data flow

For a single-asset run from `bve-asset --config relay_rly2608.yaml`:

```
YAML config
   ↓
run_asset.py loads → Asset, Company, ClinicalTrial[], MarketModel,
                     POSAdjusters[], TrialDesignFeatureSet[],
                     DealEconomics, CommercialPlan, CMCCosts,
                     ConfirmatoryTrialObligation
   ↓
DrugAssetProgram.build(...)
   ↓
ValuationEngine.from_program(program, company)
   ↓
ValuationEngine.run() →
   _prepare_trials() →
       (apply_pos_to_trials OR empirical engine route) →
       trial_design_features overlay (with overlap check)
   _resolve_market_model_with_sgna() (modality / TA auto-profile)
   revenue_sanity.check_commercial_assumptions(market_model)
   _check_compliance_rate()  (gene/cell therapy guard)
   _apply_trial_cost_defaults(trials) (TA-calibrated defaults)
   ProbabilityModel.compute(asset, trials)
   RevenueModel.compute(market_model, loe_profile)
   CostModel.compute(prob, discount_rate, deal, cmc_costs, inflation)
   RNPVModel.compute(asset, prob, rev, cost, deal)
   build_scenarios(...) → Bull/Base/Bear
   run_monte_carlo(...) → mean/median/percentiles
   compute_sensitivity(...) → 8 sensitivity points
   build_assumption_log(...)
   ComparableDealMatcher.analyze(...)  (if deals supplied)
   _compute_market_expectation(rnpv)   → ImpliedPoSResult
   _compute_runway_forecast()           → RunwayForecastV2
   _compute_dilution_analysis(rnpv)     → DilutionAnalysis
   _compute_analog_match()              → AnalogMatchResult
   _compute_catalyst_payoff(...)        → CatalystPayoffResult
   _compute_variant_perception_result(...)  → VariantPerceptionResult
   rank_acquirers(...)                  → top_acquirers list
   ↓
ValuationOutput
   ↓
reporting/export.py     → outputs/<TICKER>/valuation.json
reporting/memo_generator.py → bd_memo.md → bd_memo.docx
reporting/charts.py         → 5 PNG charts
```

The intelligence layer (weekly runner) runs separately:

```
ops/weekly_runner.py
   ↓
For each asset in UNIVERSE:
   - ThesisTracker.snapshot(asset_id) → ThesisSnapshot
   - Recommender produces ScoredCandidate
   - ScienceEngine / FinancingEngine / MarketAccessEngine /
     VariantViewEngine / CatalystPayoffTrees populate context
   - CompositeScorer.compute_adjustments(context) → per-signal delta
   - PortfolioDecisionEngine combines into a ranked decision list
   ↓
ActionableGenerator.compose(...) → WeeklyActionableReport
   ↓
DecisionLayer.record_decision(...) (persisted to ops.db)
```

The M&A layer runs from `bve-acquisition-screen` /
`bve-acquirer-fit` / `bve-ma-probability`:

```
Universe + AcquirerProfiles
   ↓
evaluate_layer0(target, acquirers) → Layer0Result
  (hard exclusion, deal type, affordability, encumbrance,
   complexity, distress guard, data confidence)
   ↓
For each (target, acquirer) pair that passes:
   compute_target_attractiveness(...) → TargetAttractivenessScore
   compute_deal_likelihood(...)        → DealLikelihoodScore
   compute_acquirer_fit_decomposed(...) → AcquirerFitDecomposed
   compute_bd_layer2(ta, dl, af, confidence) → Layer2Output
     (strategic_priority, transaction_probability, bd_action_score,
      classification, recommended_action)
   ma_layer3_gate.apply(...)  → pass / fail / cap
   ma_layer4_routing.route(...) → deal-type specific scoring
   ma_layer5_calibration.calibrate(...) → final probability
   ↓
acquisition_screen builds the ranked watchlist
acquisition_memo writes per-target memos
```

### 2.6 CLI entry points (from `pyproject.toml`)

The project exposes 40+ `bve-*` console scripts. Below are the most
important ones grouped by purpose.

**Valuation runs.**
- `bve-asset` — single-asset valuation
- `bve-batch` — batch over a config directory
- `bve-portfolio` — portfolio aggregation
- `bve-portfolio-backtest` — portfolio backtest against KS snapshots

**Config and data.**
- `bve-generate-config` — auto-generate a YAML config from universe data
- `bve-data-quality` — data quality report
- `bve-paper-snapshot` / `bve-paper-summary` — paper-trading snapshots

**Intelligence + ranking.**
- `bve-rank` — re-rank the universe
- `bve-portfolio-rank` — portfolio-aware ranking
- `bve-recalibrate` — re-run POS / ranking calibration
- `bve-opportunities` — opportunity screen
- `bve-weekly-brief` — concise weekly brief
- `bve-daily-brief` — daily brief
- `bve-watchlist-run` — watchlist runner
- `bve-investment-memo` — investment memo
- `bve-literature-review` — literature review agent
- `bve-research-report` — long-form research report
- `bve-competitive-landscape` — competitive landscape map
- `bve-note` — analyst note entry

**Replay + calibration + audit.**
- `bve-replay-document` / `bve-replay-documents` — replay a document
  through the extraction stack
- `bve-rebuild-dossiers` — rebuild asset dossiers from KS
- `bve-compute-event-scores` — recompute event scores
- `bve-calibration-report` — produce calibration report
  (Brier, ECE, AUC)
- `bve-audit-log` — audit log of decisions and overrides
- `bve-claim-resolve` — manually resolve a thesis claim
- `bve-seed-catalysts` / `bve-seed-replay-events` /
  `bve-seed-replay-claims` — seed replay store

**M&A.**
- `bve-acquisition-screen` — universe acquisition screen
- `bve-screen` — generic screen runner
- `bve-acquirer-fit` — per-pair acquirer fit
- `bve-ma-probability` — final M&A probability ranking
- `bve-universe-screen` — universe screen
- `bve-catalyst-calendar` — catalyst calendar

**Reviews + alerts + extraction.**
- `bve-review-phase2` — phase 2 review queue UI
- `bve-extract` — extraction CLI
- `bve-alert-test` — alert dispatch test
- `bve-service` — service control (scheduler / queue worker)

### 2.7 What's genuinely new vs prior version

| Category                       | Files added (samples)                              | Status                                    |
|--------------------------------|----------------------------------------------------|-------------------------------------------|
| Calibrated POS                 | pos_calibrated, pos_calibration, pos_statistical   | New, partially wired                      |
| Science score                  | science_score, trial_design_score, endpoint_validity, safety_scorer, sample_size_scorer, analog_matcher, safety_context | New, fully wired into probability_stack and into ValuationEngine helpers |
| Probability stack              | probability_stack, approval_scenarios, timeline_distribution_model, regulatory_inference | New; ValuationEngine does NOT yet treat composite_pos as the canonical PoS |
| Commercial overhaul            | market_access, payer_access, geography, commercial_inputs, commercial_model_profile, launch_archetype, label_breadth_model, revenue_audit, revenue_sanity | Partially wired |
| Cost subsystem                 | cmc_costs, confirmatory_trial, tax_profile         | Wired into CostModel and DrugAssetProgram |
| Financing                      | financing_risk (V2), dilution_model, runway_forecast, valuation/financing_model | Wired into ValuationEngine.run output     |
| Scenario / MC                  | scenario_shock, scenario_tree (models + valuation), mc_variable_table, correlations, catalyst_payoff | Partially wired |
| Variant perception             | variant_view, variant_view_engine, implied_expectations, market_expectations | New; surfaced in ValuationOutput          |
| M&A                            | ma_*, acquisition_*, strategic_fit, comparable_deals, acquirer_profiles, evidence_ingestion | New, large; standalone pipeline           |
| Intelligence engines           | science_engine, dynamic_competition_engine, financing_engine, market_access_engine, variant_view_engine, catalyst_payoff_trees, portfolio_decision_engine, readthrough_engine, recommender, mispricing_screener, composite_scorer | New, fully wired into weekly runner       |
| Monitoring + calibration       | continuous_monitoring, calibration_feedback_loop, operating_layer, forecast_tracker, revaluation_triggers | New, partially wired                      |
| Decision + position layer      | decision_layer                                     | New, schema present and used              |
| Capital structure              | capital_structure                                  | New, feeds composite_scorer               |

---

## 3. Data inputs (Pydantic schemas)

### 3.1 Asset entity (`entities/asset.py`)

`Asset` is the primary domain object. Required fields include `id`,
`name`, `indication`, `therapeutic_area` (enum: `oncology`, `oncology_solid`,
`hematology`, `rare_disease`, `cns`, `psychiatry`, `cardiovascular`,
`metabolic`, `immunology`, `dermatology`, `gastroenterology`, `pulmonary`,
`renal`, `infectious_disease`, `ophthalmology`, `other`), `stage`
(`preclinical`, `phase_1`, `phase_2`, `phase_3`, `nda_bla`, `approved`),
`modality` (`small_molecule`, `biologic`, `gene_therapy`, `cell_therapy`,
`adc`, `rna_therapy`, `other`). Optional fields include
`mechanism_of_action` (free text used by `find_analogs`), `discount_rate`
(defaults to `wacc.default = 0.12`), `effective_tax_rate` (0.21 default),
`nol_benefit_years` (0 default), `royalty_rate` (out-license rate),
`net_ownership` (1 − royalty by default), `post_approval_rd_millions`,
`approval_pathway` (`STANDARD | PRIORITY | BREAKTHROUGH | ACCELERATED |
FAST_TRACK`). If `approval_pathway == ACCELERATED`, the NDA/BLA base
rate is discounted by `accelerated_approval_nda_discount = 0.18`.

### 3.2 Company entity (`entities/company.py`)

`Company` carries `id`, `name`, `ticker`, `cash_millions`, `debt_millions`,
`shares_outstanding_millions`, `burn_rate_millions_per_quarter`,
`current_price`, and a free-form `notes`. Several downstream artifacts
are conditionally suppressed by missing fields:

- `_compute_market_expectation` requires `current_price > 0`.
- `_compute_runway_forecast` requires `burn_rate_millions_per_quarter > 0`.
- `_compute_dilution_analysis` requires `current_price > 0` and
  `shares_outstanding_millions > 0`.
- `_compute_variant_perception_result` requires `current_price > 0`.

### 3.3 ClinicalTrial (`entities/trial.py`)

Each trial carries `asset_id` (must match the parent asset),
`phase`, `nct_id`, `success_probability`, `duration_years`,
`cost_millions`, `cost_source` (`override` | `default` |
`default_applied`), `enrollment`, `primary_endpoint`, `endpoint_type`
(enum: HARD_CLINICAL, SURROGATE_VALIDATED, SURROGATE_NOVEL,
BIOMARKER_ONLY, plus 20+ specific values like OS, PFS, ORR, DOR,
MRD_NEGATIVITY, etc.). Trials with `cost_source="default"` are replaced
with TA-calibrated values from `phase_cost_defaults` at run time, with a
warning. `success_probability` is overwritten by `apply_pos_to_trials`
when `apply_pos_model=True`.

### 3.4 MarketModel (`models/market_model.py`)

Three revenue modes are supported and validated mutually exclusive at
construction:

1. `lines_of_therapy: list[LineOfTherapySegment]` — explicit per-line
   patient pools, share, price. Preferred for oncology with 1L/2L/3L pools.
2. Patient-based: `addressable_patients_annual: int`,
   `net_price_per_patient_usd: float`.
3. TAM-based: `total_addressable_market_millions: float`.

Modes 2 and 3 share `peak_penetration` (0–1), `years_to_peak` (int),
`patent_life_years` (int). All modes share `cogs_rate`, `sgna_rate_launch`,
`sgna_rate_mature`, `sgna_ramp_years`, `compliance_rate`. Optional
`commercial_model` — when set, the SG&A profile auto-selection in
`ValuationEngine._resolve_market_model_with_sgna` is suppressed.

### 3.5 POSAdjusters (`models/pos_model.py`)

The most influential fields:

- `endpoint_type` (default `SURROGATE_VALIDATED`).
- `moa_precedent` (`VALIDATED_CLASS / CLINICALLY_VALIDATED_TARGET /
  PATHWAY_VALIDATED / PARTIAL / PRECLINICAL_ONLY / NOVEL /
  PRIOR_FAILURES / KNOWN_LIABILITY`). Default `PARTIAL`.
- `sample_size_adequacy` (`WELL_POWERED / ADEQUATE / BORDERLINE /
  UNDERPOWERED / UNVERIFIABLE / EXPLORATORY`). Default `ADEQUATE`.
- `safety_profile` (`CLEAN / MANAGEABLE / MONITORABLE_CONCERN /
  DOSE_LIMITING / SERIOUS / MECHANISM_LINKED_SEVERE`). Default `MINOR`.
- `competitive_pressure` (four-tier + legacy three-tier). Default `MODERATE`.
- `biomarker_selection` (`VALIDATED / STRONG_RATIONALE / EXPLORATORY /
  NO_SELECTION / POST_HOC_WEAK`). Default `NO_SELECTION`.
- `prior_phase_data` (`STRONG_REPLICATED / STRONG_SINGLE / DOSE_RESPONSE /
  MIXED / WEAK / FAILED`). Default `MIXED`.
- `has_breakthrough_designation: bool` (default False).
- `extraordinary_evidence: bool` (default False) — expands positive cap to +1.00.
- `gene_cell_therapy_concerns: list[GeneTherapyConcern]`.
- `moa_exception_flags: list[MoAExceptionFlag]`.

### 3.6 TrialDesignFeatureSet (`models/trial_design_features.py`)

Second POS layer. Fields include `evidence_design` (RCT double blind, RCT
open label, single arm objective, single arm subjective, registry/observational,
etc.), `comparator_fit`, `approval_pathway`. Phase scaling (Phase 1 = 0.20,
Phase 2 = 0.50, Phase 3 = 1.00, NDA/BLA = 0.90) applied multiplicatively.
Asymmetric cap (+0.30, −0.60). `check_pos_layer_overlap()` raises `ValueError`
when both layers adjust the same factor.

### 3.7 DealEconomics (`models/deal_economics.py`)

Optional. Carries `upfront_payment_received_millions`,
`upfront_payment_payable_millions`, `royalty_rate_payable`,
`royalty_rate_receivable`, `profit_share_rate`, `cdev_cost_share`,
milestone schedules (receivable / payable) with probability conditioning by
phase. Consumed by `CostModel` and `RNPVModel`.

### 3.8 CommercialPlan (`models/drug_asset_program.py`)

Three states: `unset` (engine fetches LOE from `AssumptionsLoader`),
`suppressed` (no post-patent tail), `modality:<name>` (explicit profile).
Constructor rejects ambiguous states.

### 3.9 CMCCosts, ConfirmatoryTrialObligation, new M&A inputs

- `CMCCosts` — process development, validation, GMP-run costs by year.
- `ConfirmatoryTrialObligation` — WITHDRAWN_FAILED status triggers a warning.
- `TargetEligibilityInput` — every signal needed for Layer 0.
- `AcquirerCapacityInput` — per-acquirer cash, debt capacity, stock, buffer.
- `TargetProfile` — lightweight target for the fit engine.
- `AcquirerProfile` — loaded from `acquirer_profiles.yaml`.

### 3.10 New science / probability inputs

- `ProbabilityStackInputs` — `base_pos`, `ScienceAssessment`,
  `RegulatoryInferenceResult`, `years_to_approval`,
  `financing_risk_score`, `market_access_pressure_score`,
  `management_execution_score`, `competitor_readthrough_score`.
- `LabelBreadthInputs`, `TimelineDistributionInputs`, `ApprovalScenarioInputs`.

---

## 4. Core models and calculations

### 4a. POS model

The system now contains **four** POS paths.

#### 4a.i Original heuristic log-odds (`models/pos_model.py`)

Still the canonical path used by `ValuationEngine`.

```
base_rate = PHASE_SUCCESS_RATES[ta][phase]      # from industry_assumptions.yaml
if approval_pathway == ACCELERATED and phase == NDA_BLA:
    base_rate *= (1.0 - 0.18)
log_odds = log(base / (1 - base))
delta = (
    endpoint_logodds(endpoint_type, ta)
  + MOA_LOGODDS[moa_precedent]
  + Σ MOA_EXCEPTION_LOGODDS[flags]
  + SAMPLE_LOGODDS[sample_size_adequacy]
  + SAFETY_LOGODDS[safety_profile]
  + COMPETITION_LOGODDS[competitive_pressure]
  + BIOMARKER_LOGODDS[biomarker_selection]
  + PRIOR_PHASE_LOGODDS[prior_phase_data]
  + (0.05 if has_breakthrough else 0)
  + Σ GENE_THERAPY_LOGODDS[concerns]
)
cap_pos = +1.00 if extraordinary_evidence else +0.80
delta = clamp(delta, −0.80, cap_pos)
pos = sigmoid(log_odds + delta)
```

The BTD adjustment is only +0.05 by design — reduced from +0.20 pre-Sprint-9.
The `_ENDPOINT_LOGODDS_BY_TA` table covers ~14 therapeutic areas with up to
20 endpoint-specific entries each.

#### 4a.ii Statistical mirror (`models/pos_statistical.py`)

Logistic regression with 14 dummy features. Fitted at module import on a
750-row synthetic dataset generated by `pos_model.py` itself.
`IS_EMPIRICALLY_CALIBRATED = False`. Emits a `UserWarning` on every call.

#### 4a.iii Platt-scaling layer (`models/pos_calibration.py`)

`calibrated_pos = sigmoid(slope × logit(raw_pos) + intercept)` fitted on
N=99 oncology dataset. **Critical bug**: uses a slimmer log-odds table than
`pos_model.py`, meaning the calibration is against a degraded version of the
heuristic and cannot be directly applied to live `compute_pos` output.

#### 4a.iv Hierarchical Bayesian calibrated model (`models/pos_calibrated.py`)

Per (TA, phase) bin: α = n_success + 0.5, β = n_failure + 0.5.
blend_weight ramps 0→1 as N goes from 10 to 50.
`blended_rate = blend_weight × posterior_mean + (1−blend_weight) × industry_prior`.
Only consumed when `pos_mode="empirical_calibrated"` is explicitly passed.

#### 4a.v Probability stack (`models/probability_stack.py`)

Two coexisting versions. Step-7 form (`compute_probability_stack`):

```
PHASE_BASE_RATES = {
  phase2: tech 0.40, reg 0.82, label 0.65, comm 0.55, delay 0.25, crl 0.15
  phase3: tech 0.65, reg 0.85, label 0.70, comm 0.65, delay 0.30, crl 0.20
  nda_bla: tech 0.90, reg 0.87, label 0.75, comm 0.70, delay 0.35, crl 0.25
}
science_modifier   = 1.00 if no science_result else (0.70 + score × 0.40)
financing_modifier = 1.00 / 0.95 / 0.85 / 0.70 for NONE/LOW, MEDIUM, HIGH, CRITICAL
composite_pos = technical × regulatory
full_value_prob = composite_pos × label × commercial
```

This is NOT the PoS that `ValuationEngine.run()` plugs into `RNPVModel`.

#### 4a.vi – 4a.xi Science score, trial design, endpoint validity, safety scorer, sample size scorer, analog matcher

See Section 5 for exact formulas. Key points:
- `science_score` weights: endpoint_validity 0.30, trial_design 0.30, analog 0.20, safety 0.20.
- `trial_design_score` quality tiers: EXCELLENT (≥0.85, multiplier 1.10) through WEAK (<0.55, 0.80).
- `endpoint_validity` GOLD/SILVER/BRONZE/EXPLORATORY (1.00/0.85/0.65/0.40).
- `safety_scorer` clamped to [−0.90, +0.15].
- `sample_size_scorer` maps power to WELL/ADEQUATE/BORDERLINE/UNDERPOWERED with TA minimum-N downgrade.
- `analog_matcher` 30-entry curated DB; combined = 0.70 × mechanism + 0.30 × indication.

### 4b. Timeline distribution model

V2 (`compute_timeline_distribution`): PHASE_DURATIONS p10/p50/p90 per phase;
fast_track → p50 × 0.85; breakthrough → p50 × 0.80; !enrollment → p50 × 1.20;
prior_hold → p90 × 1.20. Overall delay = 1 − Π(1 − phase.delay_prob).

### 4c. Revenue model (updated)

`RevenueModel.compute()` produces year-by-year revenue with LOE erosion tail.
Driver-based build via `commercial_inputs`: peak = prevalence × diagnosed ×
treated × peak_share × net_price. `revenue_sanity.check_commercial_assumptions()`
fires `UserWarning`s for gross errors. `market_access.assess_market_access()`
produces `effective_patient_pool_multiplier` (0.30–1.0) but is not yet
automatically routed into `MarketModel`.

### 4d. Cost model (updated)

`CostModel.compute()` produces `CostStream` with trial_costs_pv_weighted,
cmc_costs_pv_weighted, payable_milestones_pv, upfront_cost_pv,
post_approval_rd_pv, total_pv_weighted_millions. `tax_profile.py` provides
per-year cash tax with NOL absorption.

### 4e. rNPV model + financing / dilution / runway

```
adjusted_EBIT_t  = EBIT_t − revenue_t × royalty_rate − EBIT_t × profit_share_rate
cash_tax_t       = max(adjusted_EBIT_t − usable_NOL_t, 0) × tax_rate_t
after_tax_EBIT_t = adjusted_EBIT_t − cash_tax_t
FCF_t            = after_tax_EBIT_t − capex_t − ΔWC − launch_capex_t
rNPV = P(approval) × Σ_t [FCF_t × net_ownership / (1+WACC)^(years+t)] − costs + milestones
NAV = rNPV + net_cash; NAV/share = NAV / shares
```

`financing_adjusted_value_haircut` is available but NOT automatically applied
to rNPV — the caller applies it via the probability stack's financing_modifier.

### 4f–4n. Scenario analysis, Monte Carlo, variant perception, M&A, intelligence engines, composite scoring, monitoring, capital structure, historical replay

See Sections 5 and 9 for formulas and critique. Key points:
- Catalyst payoff: delta_ev = pos × upside − (1−pos) × downside; asymmetry_ratio = upside/downside.
- M&A five layers: 0=eligibility, 2=BD scoring, 3=gates, 4=routing, 5=calibration.
- Composite scorer: 6 additive signals on top of base composite.
- Decision layer: recommended vs executed action, attribution taxonomy.
- Historical replay: no-lookahead via isolated SQLite + time-frozen SQL.

---

## 5. Exact formula library

### 5.1 Heuristic POS (`pos_model.compute_pos`)

```
base = PHASE_SUCCESS_RATES[ta][phase]
if approval_pathway == ACCELERATED and phase == NDA_BLA:
    base *= (1 - 0.18)
base = clamp(base, 0.01, 0.99)
log_odds = log(base / (1 - base))

delta = endpoint_logodds(endpoint_type, ta)
      + MOA_LOGODDS[moa_precedent]
      + Σ MOA_EXCEPTION_LOGODDS[moa_exception_flags]
      + SAMPLE_LOGODDS[sample_size_adequacy]
      + SAFETY_LOGODDS[safety_profile]
      + COMPETITION_LOGODDS[competitive_pressure]
      + BIOMARKER_LOGODDS[biomarker_selection]
      + PRIOR_PHASE_LOGODDS[prior_phase_data]
      + (0.05 if has_breakthrough_designation else 0)
      + Σ GENE_THERAPY_LOGODDS[gene_cell_therapy_concerns]

cap_pos = 1.00 if extraordinary_evidence else 0.80
delta = clamp(delta, -0.80, cap_pos)

pos = 1.0 / (1.0 + exp(-(log_odds + delta)))
cumulative_pos = Π pos_per_phase
```

### 5.2 Calibrated POS — Beta-binomial blend (`pos_calibrated`)

```
α = n_success + 0.5
β = n_failure + 0.5
posterior_mean = α / (α + β)

blend_weight = 0.0                              if n < 10
             = (n − 10) / (50 − 10)             if 10 ≤ n < 50
             = 1.0                              if n ≥ 50

blended_rate = blend_weight × posterior_mean
             + (1 − blend_weight) × industry_prior
```

### 5.3 Platt calibration (`pos_calibration`)

```
calibrated_pos = sigmoid(slope × logit(raw_pos) + intercept)
slope > 1 → underconfident; slope < 1 → overconfident
intercept > 0 → optimistic bias
```

### 5.4 Probability stack (Step 7, `probability_stack`)

```
science_modifier   = 0.70 + 0.40 × science.overall_score          (1.00 if science None)
financing_modifier = {NONE/LOW:1.00, MED:0.95, HIGH:0.85, CRIT:0.70}

technical  = base_tech  + 0.05 [breakthrough] + 0.05 [prior_phase] − 0.10 [prior_phase_false]
regulatory = base_reg   + 0.05 [breakthrough] + 0.03 [fast_track]  + 0.04 [orphan]
label      = base_label + 0.05 [orphan]
commercial = base_comm

technical  *= science_modifier
commercial *= financing_modifier
all clamped to [0.01, 0.99]

composite_pos    = technical × regulatory
full_value_prob  = composite_pos × label × commercial

accel_prob       = composite_pos × (0.15 if breakthrough|orphan else 0.05)
conditional_prob = composite_pos × 0.08
crl_prob         = composite_pos × base_crl
failure_prob     = 1 − composite_pos
full_approval    = composite_pos × max(0, 1 − delay − crl) × label
```

### 5.5 Science score (`science_score`)

```
weights = {endpoint_validity:0.30, trial_design:0.30, analog:0.20, safety:0.20}
overall = Σ_{i, conf_i > 0.2} (score_i × weight_i) / Σ_{i, conf_i > 0.2} weight_i
```

### 5.6 Trial design score (`trial_design_score`)

```
overall = Σ (dim_score × phase_weight[dim])
if has_adaptive_design: overall = min(1.0, overall + 0.05)
quality_tier = EXCELLENT if ≥0.85 else GOOD if ≥0.70 else ADEQUATE if ≥0.55 else WEAK
pos_multiplier = {EXCELLENT:1.10, GOOD:1.00, ADEQUATE:0.90, WEAK:0.80}
```

### 5.7 Safety scorer (`safety_scorer`)

```
adjustment = SAFETY_LOGODDS[category]
           + (+0.05 if reversible)
           + (+0.05 if monitorable)
           + (+0.05 if comparable_to_control)
           + (−0.10 if discontinuation_rate > 0.15)
           + (−0.20 if treatment_related_deaths > 0)
           + (−0.15 if organ_toxicity_signal)
           + (−0.15 if class_known_risk)
adjustment = clamp(adjustment, −0.90, +0.15)
```

### 5.8 Sample size power (`sample_size_scorer`)

```
effective_n = planned_n × (1 − dropout) × design_efficiency

continuous: power = Φ(ncp − z_α) + Φ(−ncp − z_α),  ncp = |d| × sqrt(n_per_arm / 2)
binary:     power = Φ(|p1 − p0| / SE − z_α),       SE = sqrt(2 p̄(1−p̄) / n_per_arm)

tier = WELL_POWERED  if power ≥ 0.90
     = ADEQUATE      if power ≥ 0.80
     = BORDERLINE    if power ≥ 0.70
     = UNDERPOWERED  otherwise

if effective_n < TA_MIN[ta][phase] and tier in {WELL, ADEQUATE}:
    downgrade tier
```

### 5.9 Endpoint validity (`endpoint_validity`)

```
WEIGHT_TO_SCORE = {GOLD:1.00, SILVER:0.85, BRONZE:0.65, EXPLORATORY:0.40}
validity_score = WEIGHT_TO_SCORE[match.regulatory_weight] × (1.0 if primary else 0.90)
no_match → EXPLORATORY (0.40 or 0.36)
```

### 5.10 Analog matcher (`analog_matcher`)

```
mech_match    = 1 if any (len>3) word from query.mechanism appears in analog.mechanism
ind_match     = 1 if same for indication
combined      = 0.70 × mech_match + 0.30 × ind_match
(top 5 by combined)

success_rate  = |successes| / |matched|
failure_rate  = |failures|  / |matched|
analog_score  = success_rate    if success_rate ≥ 0.6
              = 1 − failure_rate if failure_rate ≥ 0.6
              = 0.5              otherwise
```

### 5.11 Catalyst payoff (`catalyst_payoff`)

```
current_value     = rnpv(base PoS)
value_if_success  = rnpv(PoS=1.0)
value_if_failure  = rnpv(PoS=0.0)
upside            = value_if_success − current_value
downside          = current_value − value_if_failure
delta_ev          = pos × upside − (1 − pos) × downside
std_dev           = sqrt(pos × (upside − delta_ev)² + (1−pos) × (−downside − delta_ev)²)
signal_strength   = delta_ev / max(std_dev, 0.50 × |delta_ev|)
asymmetry_ratio   = upside / downside
```

### 5.12 Implied PoS (`expectations/market_implied_pos`)

```
pipeline_value   = market_cap − net_cash − trial_costs_pv
NPV_per_$1M_peak = Σ_{t=1..patent_life} revenue_fraction(t) × ebit_margin × (1−r) × (1−tax) / (1+wacc)^(years+t)
implied_pos      = pipeline_value / (peak_sales × NPV_per_$1M_peak)
```

### 5.13 rNPV (`rnpv_model`)

```
adjusted_EBIT_t  = EBIT_t × (1 − profit_share_rate) − revenue_t × royalty_rate
cash_tax_t       = max(adjusted_EBIT_t − usable_NOL_t, 0) × tax_rate_t
after_tax_t      = adjusted_EBIT_t − cash_tax_t
FCF_t            = after_tax_t − capex_t − ΔWC_t − launch_capex_t

rNPV = P(approval) × Σ_t [FCF_t × net_ownership / (1 + WACC)^(years_to_approval + t)]
     − total_pv_weighted_dev_costs
     + PV(receivable_milestones)
     + upfront_receipt

NAV         = rNPV + net_cash
NAV/share   = NAV / shares_outstanding
```

### 5.14 Financing risk (`financing_risk`)

```
runway_months = cash / monthly_burn

p_pre_catalyst_raise =
    0.05 if runway > 1.5 × catalyst_months
    0.30 if runway > 1.2 × catalyst_months
    0.60 if runway > 0.8 × catalyst_months
    0.85 if runway > 0.5 × catalyst_months
    0.95 otherwise

dilution = capital_needed / market_cap
dilution_low  = dilution × 0.85
dilution_mid  = dilution × 1.10
dilution_high = dilution × 1.40
(all × 100 for % and capped at 200%)

distress_tier:
    CRITICAL  if runway < 6 or dilution_high > 100%
    HIGH      if runway < 12 or dilution_high > 50%
    MEDIUM    if runway < 18 or dilution_high > 25%
    LOW       if runway < 30
    NONE      otherwise

financing_adjusted_value_haircut = {NONE:1.00, LOW:0.95, MED:0.85, HIGH:0.70, CRIT:0.50}
```

### 5.15 M&A composite (`ma_scoring.compute_bd_layer2`)

```
TA_score  = sat_pen(0.35×de_risking + 0.30×val_disc + 0.20×scarcity + 0.15×ps_signal)
DL_raw    = sat_pen(0.40×fin_press + 0.25×ext_deal + 0.20×insider + 0.15×cat_prox)
DL_score  = financing_pressure_gate(DL_raw, fin_press, scarcity, ...)
AF_score  = sat_pen(0.40×(0.55×TA + 0.45×mod) + 0.30×pipeline_gap + 0.20×afford + 0.10×partner_bonus)

n_drivers = count of (fin_press, ext_deal, cat_prox, scarcity+fit,
                      activist, val_distress) that clear their min thresholds

strategic_priority      = 0.45×AF + 0.35×TA + 0.20×TA.scarcity
transaction_probability = 0.45×DL + 0.25×AF + 0.15×TA + 0.15×(n_drivers/6)

bd_action_score_raw     = 0.50×SP + 0.35×TP + 0.15×AF
penalty                 = 0.10 if balance < 0.35 else 0.05 if < 0.50 else 0
bonus                   = strategic_convergence + actionable_buyer + full_convergence  (capped 0.08)
pre_conf                = sat_pen(raw + bonus − penalty)
bd_action_score         = pre_conf × confidence_multiplier
                          (HIGH 1.00, MED 0.93, LOW 0.85, VERY_LOW 0.00)

Composite caps:
    dual gate (not_pressured AND no_buyer_urgency) → cap 0.50
    DL gate active                                  → cap 0.65
    n_drivers < 2                                   → cap 0.65
    n_drivers == 0                                  → cap 0.45
```

### 5.16 Composite signal scorer (`composite_scorer`)

```
adj_catalyst_ev      = clip(catalyst_signal, ±1) × w.catalyst_ev
adj_enrollment       = (−0.05 × site_stall − 0.05 × vel_low − 0.10 × slip) × w.enrollment
adj_phase_correlation= (posterior − prior) × w.phase_correlation
adj_endpoint_z       = clip(endpoint_z, ±2) × w.endpoint_z
adj_competitor       = −clip(mean_competitor_signal, ±1) × w.competitor_impact
adj_capital_risk     = CAPITAL_RISK_DISCOUNT[risk_level] × w.capital_risk

new_composite = base_composite + Σ adj_*    (composite clamped to [0,1])
```

### 5.17 Approval scenarios (`approval_scenarios`)

```
full_approval     = tech × reg × label × comm
narrow_label      = tech × reg × (1 − label) × max(0.4, comm)
delayed_approval  = tech × reg × delay × 0.8
crl_setback       = tech × (1 − reg) × 0.65
non_approval      = max(0, 1 − (full + narrow + delayed + crl))
(then normalised to sum to 1.0)
```

### 5.18 Regulatory inference (`regulatory_inference`)

```
base = BASE_APPROVAL_PROBABILITY[pathway]      # 0.78 ACCELERATED .. 0.91 BREAKTHROUGH
delta = 0
  − 0.08 × prior_crl_count (max −0.20)
  − 0.12 if safety_serious_events
  − 0.15 if adcom == negative; − 0.05 if mixed; + 0.05 if positive
  − 0.08 if !manufacturing_clear
  − 0.05 if class_prior_crl_rate > 0.20
  − 0.10 if endpoint == biomarker_only
  − 0.05 if endpoint == surrogate_novel
  + 0.02 if endpoint == hard_clinical
approval_prob = clamp(base + delta, 0.30, 0.97)
pos_modifier  = clamp(delta × 0.40, −0.40, +0.15)
```

---

## 6. Configuration / YAML audit

### 6.1 `industry_assumptions.yaml` — what's new

- `phase_success_rates` — expanded from 8 to 16 TAs.
- `cogs_rate_by_modality` — values RAISED in Sprint D1 (biologic 0.20→0.28; gene_therapy 0.30→0.45; cell_therapy 0.40→0.60; ADC 0.22→0.30).
- `wacc.default` — raised to 0.12 (from 0.10) to reflect 4.3% risk-free rate (2026-Q1).
- `loe_erosion_profiles` — small_molecule, biologic, gene_therapy, cell_therapy, adc, rna_therapy.
- `sgna_profiles` — 4 named profiles + default alias.
- `commercial_model_profiles` — 6 archetypes (NEW Sprint D2).
- `monte_carlo.peak_sales_cv_by_stage` — NEW (preclinical 0.65 down to approved 0.15).
- `phase_cost_defaults` — NEW per-TA × per-phase cost defaults (16 TAs).
- `pre_readout_scoring` — NEW; thresholds for trial-design feature extractor.
- `phase_correlation` — NEW; Bayesian Phase 2→3 update parameters.
- `capital_structure` — NEW; buffer_months, ADV multipliers, risk thresholds.
- `catalyst_calendar` — NEW; readout lag windows, signal strength thresholds.
- `endpoint_benchmarking` — NEW; per-endpoint prior_std for z-score shrinkage.
- `enrollment_quality` — NEW; recruiting ratio warning thresholds.
- `competitor_impact` — NEW; tau_years by TA, pos_delta/market_share_delta.
- `scoring_weights` — NEW; six signal weights for `CompositeScorer`.

### 6.2 Most sensitive assumptions

1. `phase_success_rates[ta][phase]` — moves rNPV linearly.
2. `loe_erosion_profiles[modality]` — controls 30–50% of NPV tail for small-molecule assets.
3. `wacc.default` — every 100bps moves typical clinical-stage rNPV by 8–12%.
4. `cogs_rate_by_modality` — Sprint D1 hike was material for biologic/gene/cell.
5. `commercial.sgna_profiles` — launch vs mature rates compound with ramp years.
6. `pos_model.layer1_cap_logodds_positive` (0.80) — limits stacked POSAdjusters.
7. `trial_design.logodds.evidence_design_quality` — large directional impact for single-arm.
8. `monte_carlo.peak_sales_cv_by_stage` — drives MC distribution width.

### 6.3 Weakly sourced vs well-sourced

Well-sourced (literature citations): phase success rates (Biomedtracker, Thomas 2016, Citeline 2023), tax rate (US TCJA), DiMasi-derived phase cost defaults.

Judgment-heavy (no published prior): `scoring_weights`, `competitor_impact.tau_years` (labeled "internal calibration; directional only"), `pre_readout_scoring.*` thresholds, `acquirer_profiles.yaml` strategic priorities, trial design log-odds magnitudes.

### 6.4 Conflicts and inconsistencies

- `_AA_NDA_DISCOUNT = 0.18` hardcoded in `pos_model.py`; YAML `pos_model.accelerated_approval_nda_discount` is unused. Python constant wins.
- `BTD_LOGODDS` same issue — hardcoded 0.05 in Python, duplicated in YAML.
- `compliance_by_modality` distinguishes `biologic_iv` from `biologic_sc`, but `Asset.modality` enum has no administration route field.
- `commercial.defaults.peak_penetration: 0.10` is conservative — silently penalizes assets that omit the field.

### 6.5 Hardcoded vs configurable

Hardcoded in Python source: `_L1_CAP_POSITIVE` 0.80, `_BTD_LOGODDS` 0.05, `_AA_NDA_DISCOUNT` 0.18, all Step-7 `PHASE_BASE_RATES`, all M&A composite weights and caps.

Configurable via YAML: phase success rates, costs, durations, WACC, tax rate, COGS/SG&A/G2N/compliance by modality, LOE erosion profiles, trial design log-odds, composite signal weights, capital structure parameters.

---

## 7. Output artifacts

### 7.1 `ValuationOutput` (single-asset run)

~30 fields: asset/company/trials echo, `RNPVResult`, `ScenarioResult[]` (Bull/Base/Bear), `MCResult`, `SensitivityPoint[]` (8 tornado points), `assumption_log`, `comps_fair_value_band`, `revenue_audit_table`, `market_expectation` (`ImpliedPoSResult`), `catalyst_payoff` (`CatalystPayoffResult`), `analog_match` (`AnalogMatchResult`), `top_acquirers`, `runway_forecast`, `dilution_analysis`, `variant_perception` (`VariantPerceptionResult`), provenance hashes.

### 7.2 New auxiliary artifacts (not all in JSON export)

`ProbabilityStack` (Step-7), `ScienceDiligenceResult`, `RegulatoryInferenceResult`, `ApprovalScenarioWeight[]`, `LabelBreadthResult`, `TimelineDistributionV2`, `FinancingRiskV2`.

### 7.3 Memo and chart outputs

5 charts: POS waterfall, revenue curve, rNPV tornado, MC histogram, scenario bar. Memos: `bd_memo.md.j2` / `vc_memo.md.j2` / `hf_memo.md.j2` → Markdown → `.docx`.

### 7.4 Intelligence layer outputs

`WeeklyActionableReport`, `DecisionRecord`, `PositionSnapshot`, `OutcomeAttribution` (in ops.db), `CalibrationFeedbackAssessment` (proposals to YAML).

### 7.5 M&A layer outputs

`Layer0Result`, `Layer2Output` per (target, acquirer), `AcquisitionFitScore`, `AcquisitionMemo`, universe-level ranked CSV.

### 7.6 What to trust

**High trust**: phase success rates, phase costs, WACC vintage, rNPV math, MC shape.
**Medium trust**: science score subscores (deterministic but weights are judgment), label breadth probability, regulatory inference scenario allocations.
**Treat as directional**: M&A bd_action_score (no out-of-sample validation), variant perception (sensitive to assumed peak sales), composite_scorer adjustments (weights uncalibrated), acquisition likelihood (evidence-informed priors).

---

## 8. Tests and validation

### 8.1 Test surface

~100 test files. Core areas: `test_models.py`, `test_phase1..7.py`, `test_step1..7.py`, `test_competition_crowding.py`, `test_multi_indication.py`, `test_assumptions_loader.py`, `test_historical_replay.py`, `test_replay_policy.py`. New areas: `tests/intelligence/` (thesis, decision layer, composite scorer, capital structure, variant view), `tests/ma/` (eligibility, scoring, saturation, gates, drivers, classification), `tests/empirical/` (smoke tests).

### 8.2 What is well-tested

POS log-odds adjusters, cap behavior, TA fallback. rNPV math (royalty + profit share + ownership, NOL). LOE tail. Multi-indication cascade PoS and cost sharing. Replay no-lookahead invariant. MA saturation penalty, gates, driver-counting, classification. Layer 0 eligibility.

### 8.3 What is not well-tested

Calibrated POS end-to-end through rNPV. Science score out-of-sample predictiveness. Probability stack (Step-7) vs heuristic cumulative PoS numerical agreement not asserted. M&A calibration against observed deal frequencies. Composite scorer integration test (all 6 signals together). Cross-engine interaction tests are sparse.

---

## 9. Institutional-grade critique

### 9.1 Where the upgrade is materially stronger

**Honest calibration provenance** — `IS_EMPIRICALLY_CALIBRATED = False` is rare in commercial valuation tools. **Multi-layer probability stack** — separating technical/regulatory/label/commercial matches how institutional investors think. **Decomposed M&A scoring** — requiring multiple independent transaction drivers before clearing high composite scores matches BD practice. **Layer 0 eligibility gates** — eliminates SPACs, known acquirers, self-acquisitions before scoring. **Source references in `AcquirerProfile`** — `min_length=1` on `source_refs` enforces dated URL attribution. **Audit trail** — provenance fields in every `ValuationOutput`. **Decision vs execution drift** — `DecisionLayer` records both recommendation and actual trade. **No-lookahead replay** — scientifically clean.

### 9.2 Where new complexity adds fragility

Two coexisting probability-stack APIs. Three+ POS paths. Hard-coded weights everywhere (none calibrated on outcomes). Three caps stacking on the same M&A score (n_drivers, dual_gate, data confidence). Memo bloat across 27 universe names.

### 9.3 New double-counting risks

heuristic `cumulative_success_probability` vs `ProbabilityStack.composite_pos` are not the same number. `TrialDesignQualityScore` implicitly scores endpoint validity via ENDPOINT_APPROPRIATENESS dimension — if science_score and pos_adjusters both fire, endpoint quality counts twice. `FinancingRiskV2.financing_adjusted_value_haircut` and probability_stack's `financing_modifier` can both fire. `MarketAccess.adoption_speed_modifier` and commercial_realization's `market_access_pressure_score` can both pull down the same number.

### 9.4 New false-precision risks

Most scores reported to 6 decimal places for hand-set weights. Integer `n_drivers` threshold creates hard step from cap 0.65 to no cap. `signal_strength` called "Sharpe-like" but underlying variance is a binary up/down, not a return distribution.

### 9.5 M&A scoring — credibility check

No regression of historical deal outcomes on the three sub-scores. Acquirer profile staleness has no automated freshness check. Single-buyer assumption conflates "this acquirer wants this target" with "any acquirer wants this target." No counterfactual: "given the model's top-N predictions in Q1 2024, how many were actually acquired?"

For institutional use, the M&A layer should be treated as a screen, not a probability. The BD action classification (`Active Pursuit`, `Begin Relationship`, `Pass`) is more defensible than the raw `bd_action_score`.

### 9.6 Science scoring — can it replace domain expert judgment?

No. What it does well: forces explicit consideration of endpoint validity, trial design quality, safety, and analog precedent. Catches obvious red flags. What it does not do: adjust for novelty, capture timing-of-evidence dynamics, reason about scientific mechanism beyond token-matching.

### 9.7 Is the calibration feedback loop closing?

Partially. The loop closes only for the calibrated POS path (non-default). The heuristic path reads from Python constants the feedback loop does not modify. For the loop to truly close, `CalibrationFeedbackLoop` would need to write proposals to a YAML file that the heuristic loads, or migrate the heuristic tables to YAML. Neither is done today.

---

## 10. Code-level issues

### 10.1 Bugs / suspicious patterns

1. **Duplicated `compute_mna_composite_score`** — `ma_scoring.py` defines it twice (lines 514 and 934). Second shadows the first.
2. **`_compute_sensitivities` is dead** — `ValuationEngine` defines it (line 706) but `run()` calls `compute_sensitivity` from `bve.analysis.sensitivity` instead.
3. **Hardcoded YAML key duplicates Python constant** — `_AA_NDA_DISCOUNT` and `btd_logodds` in Python win over their YAML counterparts.
4. **`_check_compliance_rate` only warns about gene/cell** — a small molecule with `compliance_rate=0.30` will not warn.
5. **`_compute_catalyst_payoff` swallows all exceptions** — `except Exception: return None`. Silent failures repeat for `_compute_analog_match`, `_compute_variant_perception_result`, `_compute_runway_forecast`, `_compute_dilution_analysis`.
6. **`pos_calibration.py` uses slimmer log-odds table than `pos_model.py`** — Platt fit calibrated against a degraded version; cannot be directly applied to live `compute_pos` output.
7. **`probability_stack._rebuild_models` is fragile** — forward references resolved at import time; import order changes will fail non-obviously.
8. **`Layer2Output.imbalance_penalty_applied` has no upper bound** — arbitrary positive values without documented cap.

### 10.2 Hardcoded values worth flagging

- `_PEAK_SALES_LOG_MAX = math.log1p(10_000.0)` — caps peak sales scoring at $10B; Keytruda exceeds it.
- `_AFFORDABILITY_EV_MEGA_CAP_M = 15_000.0` — hardcoded $15B mega-cap threshold.
- `_DRIVER_*_MIN` thresholds (0.35 / 0.30 / 0.60 / 0.45) — judgment calls, none cited.
- `STAGE_A_FEATURE_WEIGHTS` in `acquisition_likelihood.py` — "evidence-informed priors" presented as a probability.
- `_HAIRCUT_BY_TIER` (1.00 / 0.95 / 0.85 / 0.70 / 0.50) — judgment calls.
- `_TIER_MULTIPLIER` in `trial_design_score.py` (1.10 / 1.00 / 0.90 / 0.80) — judgment calls.

### 10.3 Oversized functions

`valuation_engine.run()` ~170 lines with 20+ side-effect helper calls. `_compute_sensitivities` (dead) ~130 lines, should be table-driven. `evaluate_layer0()` and `compute_bd_layer2` both getting long.

### 10.4 Missing docstrings in new modules

`dynamic_competition_engine.py`, `readthrough_engine.py`, `revaluation_triggers.py`, `forecast_tracker.py` — internal helpers and trigger functions lack docstrings documenting threshold semantics.

### 10.5 Naming inconsistencies

`ScienceAssessment` vs `ScienceDiligenceResult`. `TimelineDistributionResult` vs `TimelineDistributionV2`. `ApprovalScenario` vs `ApprovalScenarioV2`. `ProbabilityLayer` vs `ProbabilityLayerV2`. `CompositeScorer` vs `compute_mna_composite_score`.

### 10.6 Dead / unused code

`valuation_engine._compute_sensitivities`. `pos_statistical.compare_models` and `calibration_report` (CLI-only). `intelligence/opportunity_*` family partially superseded.

### 10.7 Import issues

Lazy imports inside functions common (to break circular deps) — code smell but documented. `science_score._rebuild_models()` re-resolves forward refs at module import; silent failure if any referenced module fails to import.

---

## 11. End-to-end example — RLY-2608

Using `examples/configs/relay_rly2608.yaml`.

### 11.1 Input snapshot

- Asset: RLY-2608, PI3Kα H1047R-selective inhibitor, HR+/HER2- mBC, Phase 2, small molecule, discount_rate 0.10.
- Company: Relay Therapeutics (RLAY), cash $410M, 93.5M shares, burn $35M/quarter, price $5.80.
- Trials: Phase 2 (n=100, $85M), Phase 3 (n=450, $280M), NDA/BLA ($35M).
- Market: 17,000 addressable patients × $180K net price × 22% peak penetration × 5 years to peak × 12 years patent life.
- POS adjusters: endpoint_type=surrogate_validated, moa_precedent=validated, safety_profile=clean, biomarker_selected=true, strong_prior=true.

### 11.2 Step-by-step computation

**Step 1: POS per phase.**

Phase 2: base = 0.248. Adjusters: endpoint surrogate_validated +0.15, MoA validated +0.35, sample_size borderline −0.20, safety clean +0.10, competition high −0.15, biomarker validated +0.40, prior_phase strong_single +0.20. Raw delta = +0.85 → capped to +0.80. log_odds = −1.110 + 0.80 = −0.310. POS = sigmoid(−0.310) = **0.423**.

Phase 3: base = 0.495. Delta capped to +0.80. log_odds = −0.020 + 0.80 = +0.780. POS = **0.686**.

NDA/BLA: base = 0.916. log_odds = 2.390 + 0.80 = +3.190. POS = **0.960**.

Cumulative POS = 0.423 × 0.686 × 0.960 = **0.279**

**Step 2: Trial design overlay.**

Phase 2 single-arm + accelerated validated surrogate: −0.075 net delta. pos_after_design = **0.405**.
Cumulative post-design = 0.405 × 0.686 × 0.960 = **0.267**

**Step 3: Revenue.**

Peak sales = 17,000 × $180K × 0.22 = $673.2M. With 5-year ramp, 12-year patent life, small_molecule LOE tail, COGS 15%, SG&A 40%→20%: PV of revenue stream ≈ **$1,250M**.

**Step 4: Cost.** PV of Phase 2 ($85M), Phase 3 ($280M × 0.405), NDA ($35M × 0.405 × 0.686) ≈ **$320M**.

**Step 5: rNPV.** = 0.267 × $1,250M × 1.0 − $320M ≈ **$14M**. NAV = $14M + $410M = $424M. NAV/share = **$4.53**.

**Step 6: Implied PoS.** Pipeline value = $5.80 × 93.5M − $410M = $132M. Implied PoS ≈ 132 / (673 × 0.7) ≈ **28%** — close to model's 26.7%.

**Step 7: Catalyst payoff.** Upside = $916M, downside = −$99M. delta_ev = 0.267 × 916 − 0.733 × 99 = **+$172M**. Asymmetry ratio = **9.25**.

**Step 8: Science score.** endpoint "Confirmed ORR" → SILVER (0.85). trial_design Phase 2 ≈ 0.68 (GOOD). analog: limited matches, dropped. safety clean ≈ 0.85. Science overall ≈ **0.78 (strong)**.

**Step 9: Probability stack (Step 7).** technical = 0.40 × 1.01 ≈ 0.404. regulatory = 0.82. composite_pos = 0.331. full_value_prob = 0.331 × 0.65 × 0.55 = **0.118**. Note: heuristic cumulative_pos (0.267) vs Step-7 composite_pos (0.331) — not the same number.

**Step 10: M&A (against Pfizer).** Layer 0 passes. BD action score ≈ **0.485**. Classification: likely **Strategic Watchlist** — interesting but not in active BD funnel today.

---

## 12. Beginner explanation

### 12.1 What is this tool?

A toolkit that turns a structured description of a clinical-stage drug into: a valuation (rNPV + Bull/Base/Bear + Monte Carlo), a science diligence report, a probability stack decomposing approval into four layers, a financing risk assessment, a catalyst payoff decomposition, a market expectation comparison (what the stock implies vs the model), and an M&A screen. It also runs a weekly loop that scores a universe of biotechs and recommends positions.

### 12.2 What's new in plain English

The model now knows when it doesn't know — it carries calibrated probabilities with credible intervals when there's enough data, and falls back to industry priors when there isn't. It now scores M&A targets: not just "is this company attractive" but "is it about to transact, and for which buyer." It now records what you did vs what it suggested. It now flags when commercial assumptions look wrong.

### 12.3 M&A scoring in plain English

Three questions per target × acquirer pair: (1) Is the target attractive? (2) Is a deal likely soon? (3) Does this specific acquirer want this target? If only #1 → strategic watchlist. If #1 and #2 → start building a relationship. All three → active pursuit.

### 12.4 Science engine in plain English

Is the endpoint regulatorily credible? Is the trial designed to produce credible evidence? Are there historical analogs and what did they do? Is the safety profile a blocker? Combine into a 0–1 score with explicit rationales.

### 12.5 What to trust vs not trust

**Trust**: rNPV math, phase success rates from YAML, sanity warnings, provenance hashes.
**Be cautious with**: M&A composite scores (rankings, not probabilities), variant perception signals (small price changes shift them), Step-7 composite_pos vs heuristic cumulative_pos (not the same number).
**Don't trust**: Step-7 PHASE_BASE_RATES as exact probabilities (hand-set), acquisition probability as a true probability (not calibrated), composite scorer weights (explicitly provisional).

---

## 13. Improvement roadmap

### 13.1 Old must-fix issues — status

- "POS model is uncapped" — **RESOLVED** (±0.80 Layer 1 cap).
- "BTD log-odds overweighted" — **RESOLVED** (+0.20 → +0.05).
- "No accelerated-approval discount" — **RESOLVED** (18% NDA discount).
- "Revenue model lacks LOE tail" — **RESOLVED** (loe_erosion_profiles).
- "MarketModel SG&A is single-knob" — **PARTIALLY RESOLVED** (sgna_profiles exist; auto-selection broken by partial overrides).
- "No franchise cost sharing for multi-indication" — **RESOLVED**.
- "Multi-indication cascade PoS lacks confidence interval" — **STILL OPEN**.

### 13.2 New must-fix issues

1. **Unify the POS path** — decide canonical (heuristic / probability stack / calibrated); make others diagnostics.
2. **Wire the financing haircut into rNPV** — expose `rnpv_after_financing_haircut` as a standard field.
3. **Make calibration writes auditable** — `CalibrationFeedbackLoop` should write a dated YAML diff surfaced via `bve-calibration-review`.
4. **Validate science_score + pos_adjusters don't double count the endpoint** — extend `check_pos_layer_overlap` to science score path.
5. **Remove dead `_compute_sensitivities` method.**
6. **Stop silently swallowing exceptions in engine helpers** — at minimum, log them.
7. **Replace slim log-odds tables in `pos_calibration.py` with imports from `pos_model.py`.**

### 13.3 High-ROI next improvements

- **Empirical M&A calibration** — collect 50–100 historical deal outcomes, run logistic regression on three sub-scores.
- **Live science_score audit table** — attach sub-score values and rationales to JSON export.
- **Multi-acquirer roll-up** — per-acquirer scores → "any acquirer" probability via noisy-OR over top-3.
- **Per-catalyst payoff** — iterate over catalyst calendar rather than collapsing all trials.
- **Backtest science_score** — against N=99 oncology dataset.

### 13.4 Biggest gaps now

No regulatory information feed (auto-ingest from FDA filings). No price + volume reconciliation for variant perception. No portfolio-aware risk budget (correlation across portfolio). No survivorship-bias correction in historical replay.

---

## 14. Final deliverables

### 14.1 One-page summary

| Aspect | Today (Sprint ~26C) |
|---|---|
| Lines of code | ~50k Python, ~3k YAML config |
| Subsystems | Valuation (mature), Intelligence (mature), M&A (new + extensive), Replay (mature) |
| POS paths | 4: heuristic log-odds, statistical mirror, Platt calibration, Bayesian calibrated |
| Probability stacks | 2 (Phase E + Step 7) |
| Major outputs | rNPV + Bull/Base/Bear + MC + tornado + memo + charts + JSON + per-acquirer fit + watchlist + decision log |
| CLI entry points | 40+ console scripts |
| Calibration source | N=99 oncology dataset, Brier 0.21, AUC 0.74 |
| Live store | SQLite `outputs/intelligence/ops.db` |
| Replay store | Isolated SQLite `outputs/intelligence/replay_store.sqlite`; no-lookahead enforced |
| New since v1 | Science engine, M&A 5-layer pipeline, calibrated POS, probability stack, financing/dilution/runway, decision layer, calibration feedback loop, composite scorer, catalyst payoff trees, variant view engine, market access engine, dynamic competition engine |

### 14.2 Updated glossary

**rNPV** — risk-adjusted net present value. **NAV / NAV per share** — net asset value (rNPV + net cash), per share. **POS** — probability of success. **Cumulative POS** — product of per-phase POS values. **Log-odds** — `log(p/(1−p))`; space in which POS adjusters are additive. **Sigmoid** — `1/(1+exp(−x))`; inverse of log-odds. **ESS** — effective sample size, Beta-distribution prior weight. **LOE** — loss of exclusivity; patent expiry. **AA** — accelerated approval. **BTD** — Breakthrough Therapy Designation. **CRL** — Complete Response Letter. **PDUFA** — FDA action date. **Cohen's d** — standardized mean difference. **Brier score** — mean squared error of probabilistic predictions. **ECE** — Expected Calibration Error. **Layer 0 / 2 / 3 / 4 / 5** — the five M&A scoring layers. **BD action score** — final M&A composite from Layer 2. **Distress tier** — NONE / LOW / MEDIUM / HIGH / CRITICAL. **Variant view** — model vs consensus; the cheapness/richness signal. **Catalyst payoff** — EV decomposition around the next binary event. **Probability stack** — four-layer approval decomposition. **Composite scorer** — six additive signal layers on top of base composite. **DecisionLayer** — SQLite-backed store of recorded decisions and attributions.

### 14.3 Updated 20 most important assumptions

1. `phase_success_rates[TA][phase]` (16 TAs × 4 phases)
2. `wacc.default = 0.12`
3. `pos_model.layer1_cap_logodds_positive = 0.80`
4. `_AA_NDA_DISCOUNT = 0.18`
5. `loe_erosion_profiles[modality]` — small_molecule year_1 loss 0.40 vs biologic 0.20
6. `cogs_rate_by_modality` — biologic 0.28, gene/cell at 0.45/0.60
7. `sgna_profiles` defaults (specialty 0.40→0.20 over 5 years)
8. `commercial.compliance_by_modality` (1.0 for one-time therapies)
9. `monte_carlo.peak_sales_cv_by_stage` (Phase 1 0.60 down to approved 0.15)
10. `trial_design.phase_scaling` (Phase 1 0.20, Phase 3 1.00)
11. `scoring_weights` (catalyst_ev 0.15, phase_correlation 0.25)
12. `competition.penetration_haircut_per_competitor` (15% / 10% / floor 50%)
13. `science_score` weights (endpoint 0.30, design 0.30, analog 0.20, safety 0.20)
14. `trial_design_score._PHASE_WEIGHTS` (phase-specific dimension weights)
15. `regulatory_inference._BASE_APPROVAL_PROBABILITY` (STANDARD 0.85 → BREAKTHROUGH 0.91)
16. `financing_risk` distress tier thresholds (6 / 12 / 18 / 30 months runway)
17. `ma_scoring` weights (TA 0.35, DL 0.25, AF 0.40) and gate caps
18. `acquisition_likelihood` Stage A weights (de_risking 0.25, scarcity 0.20, vulnerability 0.20, ta_heat 0.15, val_disc 0.10, catalyst 0.10)
19. `capital_structure.buffer_months = 12`, ADV multipliers 20/30
20. `endpoint_benchmarking.prior_std` per endpoint (OS HR 0.08, ORR 0.13)

### 14.4 Updated 20 biggest risks

1. The four POS paths can disagree silently
2. Step-7 PHASE_BASE_RATES are hand-set, not loaded from YAML
3. M&A scores are not calibrated probabilities
4. Composite scorer weights are provisional but users see rankings that depend on them
5. `science_score` weights are uncalibrated and can systematically bias the probability stack
6. Double counting between science_score endpoint validity and pos_adjusters endpoint_type
7. Financing haircut computed but not auto-applied
8. Variant perception very sensitive to spot price (no smoothing)
9. `_compute_*` engine helpers silently swallow exceptions
10. Hardcoded $15B mega-cap threshold in M&A
11. Acquirer profile freshness has no automated check
12. Calibration feedback loop does not write back to heuristic POS
13. Survivorship bias still present in historical replay
14. `pos_calibration.py` uses different log-odds table than `pos_model.py`
15. Sanity warnings only fire for gross errors, not soft assumption drift
16. SG&A auto-selection suppressed if any single SG&A field is overridden
17. `commercial_inputs` and legacy patient × price fields can coexist; precedence is subtle
18. Lifecycle event modeling is fixed-effect (no PoS conditioning)
19. Decision drift tracking depends on analyst recording executed_action; no enforcement
20. `ops.db` has no migration strategy documented

### 14.5 Updated 20 best next improvements

1. Unify POS paths under one canonical engine
2. Wire financing haircut into rNPV (with explicit on/off field)
3. Empirically calibrate M&A scores against historical deal outcomes
4. Backtest science_score against the N=99 oncology dataset
5. Roll up per-acquirer M&A scores into an "any acquirer" probability via noisy-OR
6. Per-catalyst payoff (not just total)
7. Variant perception with rolling-window price smoothing
8. Auto-load Step-7 PHASE_BASE_RATES from YAML
9. Extend `check_pos_layer_overlap` to science_score
10. Remove dead `_compute_sensitivities`; document the canonical sensitivity path
11. Move all hardcoded M&A constants into YAML
12. Replace silent `except Exception: return None` with structured failure records
13. Add a "what changed since last run" diff to the assumption_log
14. Add an integration test that runs RLY-2608 end-to-end and asserts cumulative POS to within 1pp
15. Add a CI test that builds the probability stack and asserts it's within 5pp of heuristic cumulative POS for the relay config
16. Auto-archive memos older than 90 days
17. Survivorship-bias correction for historical replay
18. Acquirer profile freshness CLI (`bve-acquirer-freshness`)
19. Validation that `pos_calibration.py` uses the same log-odds table as `pos_model.py`
20. Provenance fingerprint for the M&A run (acquirer profile library hash, screen run hash)

---

*End of report.*
