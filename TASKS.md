# TASKS.md — Biotech Asset Valuation Engine

## Overview

This file tracks the implementation roadmap for evolving the system into a calibrated biotech intelligence platform.

**Architecture progression:**
```
data → signals → structured intelligence → calibration → workflow → propagation → AI research
```

**Core principles:**
- Data first, modeling second
- Calibration before automation
- Human review before valuation change
- Confidence gating (discard < 0.3, review < 0.5, auto-process ≥ 0.5)
- Trading-day time alignment (NYSE holiday calendar, not Mon–Fri)
- Document deduplication (hash before storage)

**What the system becomes when finished:**
```
connectors
→ document ingestion
→ signal extraction
→ knowledge graph intelligence
→ calibration engine
→ analyst workflow
→ calibrated propagation
→ AI research synthesis
```

---

## To Do

### Wave 2 — Structured Intelligence

> Adds structured understanding of clinical development and competition.

#### 2C — Trial Design Extraction ✓

#### 2B — Competitor Program Discovery ✓

---

### Wave 3 — Calibration & Learning

> Transforms raw event data into model improvement. Replaces static scoring rules with empirically grounded estimates once sufficient outcome data exists.

#### 3A — Event Impact Ledger ✓

#### 3B — Forecast Tracking ✓

#### 3C — Reviewer Annotations ✓

---

### Wave 4 — Workflow Layer

> Provides operational usability for analysts interacting with the system daily.

#### 4A — Streamlit Review Queue
- [x] `review_app.py` — Streamlit UI for the ReviewQueue
- [x] Actions: Approve, Reject, Modify
- [x] Displayed fields: signal source, LLM extraction, trial design summary, proposed valuation change, valuation delta preview
- [x] Run: `streamlit run review_app.py`

#### 4B — Weekly Opportunity Brief
- [x] One-page executive summary: top opportunities, alerts fired, new signals, model changes, open review items, competitive developments
- [x] CLI: `bve-weekly-brief`

#### 4C — Portfolio Ranking + Clustering
- [x] Constraint filtering: `max_assets_per_indication`, `max_assets_per_company`
- [x] Clusters built using KG `same_indication` edges
- [x] *(Monte Carlo portfolio simulation intentionally deferred to later)*

---

### Wave 5 — Calibrated Propagation

> Uses real outcome data to estimate cross-asset effects. All propagation still routes through ReviewQueue.

#### 5A — Competitor Failure Propagation
- [x] Estimate PoS uplift when a competitor fails (e.g., historical oncology median ~+4.2%)
- [x] Proposal confidence proportional to calibration sample size
- [x] Routed through ReviewQueue before any valuation change

#### 5B — Class-Effect Safety Propagation
- [x] Safety signals propagate across assets sharing `same_mechanism` KG edge
- [x] Magnitude estimated empirically from `event_outcomes` ledger
- [x] Review required before valuation change applied

---

### Wave 6 — AI Research Agents

> Activated only when system maturity conditions are met:
> - ≥ 100 resolved events
> - ≥ 6 months of outcomes
> - ≥ 50 KG nodes
> - ≥ 3 calibration cycles

#### 6A — Mechanism of Action Summary Agent
- [x] Synthesizes mechanism data across all ingested documents
- [x] Output: `target_class`, `mechanism_description`, `novelty_score`, `competitive_differentiation`

#### 6B — Competitive Landscape Agent
- [x] Produces structured comparison table: drug, company, phase, mechanism, risk_score

#### 6C — Automated Literature Review Agent
- [x] Aggregates PubMed corpus for an asset
- [x] Output: `efficacy_summary`, `safety_summary`, `mechanism_summary`, `knowledge_gaps`

#### 6D — Research Report Generator
- [x] Final report structure: executive summary, investment thesis, clinical evidence, competitive analysis, financial model, risk factors, calibration metrics

---

### Wave 7 — Continuous Runtime & Productization

> Evolves the current CLI-centric workflow into a continuously running intelligence service.

#### 7A — Runtime Contracts + Service Foundation (Phase 1)
- [x] Add `run_state` table with: `run_id, stage, asset_id, status, started_at, finished_at, checkpoint_json, error_json`
- [x] Write `run_state` rows at stage start/finish/failure for every asset
- [x] Add stage-level checkpoint resume semantics using `checkpoint_json`
- [x] Add non-overlapping run lock in scheduler/service loop
- [x] Implement `src/bve/services/intelligence_service.py` and `src/bve/services/scheduler.py`

#### 7B — Idempotency Keys (cross-cutting)
- [x] Enforce raw document idempotency key: `(source, document_hash)`
- [x] Enforce structured signal idempotency key: `signal_id`
- [x] Enforce event idempotency key: stable `event_key`
- [x] Enforce opportunity alert idempotency key: `(asset_id, event_type, window)`

#### 7C — Data Ingestion Agents (Phase 2 / System 3)
- [x] Add `src/bve/agents/data_ingestion/` wrappers for FDA, ClinicalTrials, PubMed, SEC, and news
- [x] Implement source checkpoint cursors (`last_run` per source/asset)
- [x] Ensure ingestion feeds existing extraction pipeline without duplicating artifacts

#### 7D — Opportunity Scanner (Phase 3 / System 6)
- [x] Add `src/bve/intelligence/opportunity_scanner.py` for continuous mispricing detection
- [x] Reuse ranking + market expectation components for scanner outputs
- [x] Trigger alerts only after dedupe key check and severity threshold evaluation

#### 7E — Visualization + Dashboard (Phase 4-5 / Systems 4 and 2)
- [x] Add `src/bve/visualization/` reusable chart spec generators (Plotly JSON)
- [x] Add Streamlit dashboard shell in `src/bve/ui/dashboard/`
- [x] Add dashboard cache versioning metadata on every view:
  `cache_version, source_run_id, source_model_version, generated_at`
- [x] Display current cache/run/version provenance in dashboard header

#### 7F — Investment Memo Agent (Phase 6 / System 5)
- [x] Add deterministic `investment_memo_agent.py` (assembly-first, render-second)
- [x] Add Jinja template `templates/investment_memo.md.j2`
- [x] Add CLI entrypoint `bve-investment-memo`

#### 7G — Full Automation + Hardening (Phase 7)
- [x] Integrate end-to-end stage flow in scheduler loop
- [x] Add per-asset failure isolation (one asset failure does not halt run)
- [x] Add structured run metrics and stage telemetry (documents, signals, diffs, alerts)
- [x] Add replay-safe recovery test for crash between extraction and valuation

---

### Wave 8 — Acquisition Lens + M&A Replay

> Adds an acquisition-oriented screen on top of the existing valuation, intelligence,
> and replay stack without mutating the catalyst/ranking workflow.

#### 8A — Acquisition Discount Screener
- [x] Build a separate acquisition screen using valuation snapshots plus EV snapshots
- [x] Persist `acquisition_discount_snapshots` and expose a CLI/report for the universe
- [x] Resolve numerator semantics before implementation: current `rnpv_millions`
      already embeds `P(approval)`; do not multiply by PoS twice
- [x] Flag candidates at `acquisition_discount > 2.0` and surface missing-data reasons

#### 8B — Comparable Deal Database
- [ ] Curate 30-50 recent biotech M&A deals (last 3 years) into YAML with:
      `target_name, indication, phase_at_acquisition, ev_to_peak_sales, acquirer, deal_date`
- [x] Add a thin loader/validator and percentile comparison vs watchlist assets
- [x] Keep the research collection workflow manual; keep the engineering layer deterministic
- [x] Seed status: `research/mna/comparable_deals.yaml` now has 35 screenable
      public deals (target: 30–50); `research/mna/deal_universe_2020_2026.yaml`
      holds a broader 43-deal sourcing universe for unresolved private/platform
      takeouts; `research/mna/target_monitor.yaml` tracks named live/public targets
      that do not belong in the closed-deal comp file

#### 8C — Acquisition Readiness Filter
- [x] Reuse `trial_design_feature_extractor.py` and `phase_correlation_updater.py`
      outputs to create an acquisition-readiness gate
- [x] Default the acquisition screen to Phase 2 proof-of-concept or later, with
      explicit inclusion/exclusion reasons
- [x] Avoid changing the underlying trial-design or Bayesian phase-correlation math in v1

#### 8D — M&A Replay Profile
- [x] Add quarterly cadence and 12-month hold support to historical replay
- [x] Add a true top-8 open-position cap; current replay `max_positions` is only a
      per-step decision cap
- [x] Disable the catalyst gate for the M&A profile and widen loss blocking to `-40%`
- [x] Benchmark the M&A profile against the current short-horizon replay configuration

---

## In Progress

### Phase 1 — Institutional Grade (Sprint 10–12, active)

> Converts the rNPV engine from "valuation calculator" into "mispricing detector."
> Full roadmap: see ROADMAP.md

#### Sprint 10 — Market-Implied PoS at Universe Scale ✓

- [x] **10.1** `research/universe_params.yaml` — per-ticker valuation params for all 27 UNIVERSE names
- [x] **10.2** `ops/universe_configs.py` — parametric `DrugAssetProgram` + `Company` builder
- [x] **10.3** `analysis/implied_pos_batch.py` — batch runner producing `ScreenRow` list
- [x] **10.4** Wire implied PoS into `weekly_runner report` output (persist to KnowledgeStore screen_snapshots)

#### Sprint 11 — Unified Screener CLI ✓

- [x] **11.1** `cli/universe_screen.py` — `bve-universe-screen` command with `--as-of` flag
- [x] **11.2** `pyproject.toml` — registered `bve-universe-screen` entry point

#### Sprint 12 — Survivorship Bias Fix ✓

- [x] **12A** Added 5 Phase 2 failures + 18 Phase 3 successes to `research/data/oncology_phase_transitions.csv`
      (N=99; Phase 2=39.6%, Phase 3=60.8%, AUC=0.74, Brier=0.213)
- [x] **12B** `ops/universe_builder.py` — rules-based universe filter from XBI/IBB constituents
      ($200M–$10B mktcap, ADV > $2M, Phase 2+; universe_snapshots table in KnowledgeStore)

#### Sprint 16 — Calibration database ✓

- [x] `analysis/calibration_metrics.py` — `PredictionRecord`, `OutcomeRecord`, `compute_calibration()`
      (Brier score, Brier skill score, AUC-ROC, ECE, 5-bucket reliability diagram)
- [x] KnowledgeStore `pos_predictions` + `pos_outcomes` tables; `insert_pos_prediction()`,
      `get_pos_predictions()`, `upsert_pos_outcome()`, `get_pos_outcomes()` methods
- [x] `tests/test_sprint16.py` — 30 tests: Brier, AUC, buckets, compute_calibration(),
      persistence, survivor-bias warning, edge cases

#### Sprint 15 — Real-time event monitoring ✓

- [x] **15.1** `ops/event_monitor.py` — `DetectedEvent` dataclass, `poll_fda_events()` (OpenFDA API),
      `poll_edgar_8k()` (EDGAR EFTS); dedup by (ticker, event_type, headline[:80], date)
- [x] **15.2** `ops/recompute_trigger.py` — `check_and_trigger(store, as_of)` returns tickers with new
      material events; `pending_trigger_count()` convenience wrapper
- [x] KnowledgeStore `detected_events` table with UNIQUE(ticker, event_type, headline_key, detected_date);
      `insert_detected_events()` + `get_detected_events()` methods
- [x] `tests/test_sprint15.py` — 30 tests: DetectedEvent, classify, match, poll_fda (mocked),
      poll_edgar (mocked), KnowledgeStore persistence, recompute trigger

#### Sprint 14 — Commercial model layer ✓

- [x] `models/commercial_inputs.py` — `PatientPool`, `PricingModel`, `ShareModel`, `CommercialInputs`
      (explicit patient × price × share build-up; `to_peak_sales_millions()` + `sample_peak_sales(rng)`)
- [x] `MarketModel.commercial_inputs` — optional Mode 4 field; `_check_mode` accepts it as a valid mode
- [x] `relay_rly2608.yaml` — updated with `commercial_inputs` block (H1047R mBC derivation)
- [x] `tests/test_sprint14.py` — 29 tests: all 3 sub-models, CommercialInputs, MarketModel integration,
      MC width validation, backward compat

#### Sprint 13 — Acquirer pipeline gap analysis ✓

- [x] `intelligence/strategic_fit/acquirer_profiles.yaml` — 3 curated profiles (Pfizer, Lilly, Novo Nordisk)
      with TA priorities, stage preferences, mechanism gaps, deal size ranges, avoid lists
- [x] `intelligence/strategic_fit/strategic_fit.py` — `StrategicFitScore` dataclass + `score_fit()` function
      (ta_match×0.35 + stage×0.20 + mechanism_novelty×0.30 + commercial×0.15; avoid_penalty=0.40)
- [x] `bve-universe-screen --mna` — FIT + BEST_FIT_FOR columns across all 3 acquirers
- [x] `tests/test_sprint13.py` — 45 tests covering scoring, YAML structure, edge cases

---

## Completed

### Core Valuation Engine (Steps 1–7)
- [x] rNPV model: P(approval) × PV(EBIT) − PV(costs) + milestones
- [x] POS model: log-odds adjusters, Biomedtracker base rates, trial design features
- [x] Four-engine architecture: `ProbabilityModel`, `RevenueModel`, `CostModel`, `RNPVModel`
- [x] LOE erosion tail (Step 3): post-patent revenue + collapsed SG&A
- [x] `DrugAssetProgram` container with `CommercialPlan` (3-state LOE semantics)
- [x] `DealEconomics`: royalties, cost-share, milestone PV (payable + receivable)
- [x] Scenarios (Bull/Base/Bear), Monte Carlo (10k draws, Gaussian copula), tornado sensitivity
- [x] Competition model: `CrowdingModel`, `FirstMoverConfig`, `ClassSaturationProfile`
- [x] Multi-indication: cascade PoS, `FranchiseCostSharing`, `IndicationResult`
- [x] Regression fixture hardening (Step 7)
- [x] Reporting: Jinja2 memos (BD/VC/HF), 5 matplotlib charts, JSON export
- [x] Historical backtests: VRTX ivacaftor 2010, INCY ruxolitinib 2010
- [x] Market validation: implied PoS NAV back-solve framework

### Intelligence Pipeline
- [x] Document ingestion: ClinicalTrials, FDA, SEC EDGAR, press release connectors
- [x] LLM extraction with confidence gating (discard < 0.3, review < 0.5, auto ≥ 0.5)
- [x] `StructuredSignal`, `ValuationProposal`, `ReviewQueue` schemas
- [x] Phase 2 mapping engine + policy routing
- [x] `KnowledgeStore` (SQLite): `raw_documents`, `structured_signals`, `valuation_proposals`
- [x] Alerting layer: `AlertModel`, multi-channel router (Slack, email, Telegram, local)
- [x] Ranking engine: `RankedOpportunity` with score, PoS gap, opportunity tier
- [x] `WatchlistPipelineRunner` wiring connectors → extraction → mapping → ranking

### Wave 1 — Empirical Data Foundation
- [x] **1A — Market Price History**: `market_prices` table, `MarketPriceConnector` (yfinance), volume spike detection (> 2× 20-day avg), prices refreshed each cycle
- [x] **1B — Event Outcomes + Price Reaction Tracker**: `event_outcomes` table, T+1/5/30/90/180 trading-day windows, independent per-window resolution, `fully_resolved` flag
- [x] **1C — PubMed Connector**: NCBI esearch + efetch, topic keyword filter, 429 backoff (exponential, up to 4 retries), `NCBI_API_KEY` support, structured abstract parsing
- [x] **1D — Market Expectation Modeling**: `ImpliedPoSEstimator` NAV back-solve, `market_expectations` table, `pos_gap` surfaced in `RankedOpportunity` and `bve-rank` output

### Wave 2B — Competitor Program Discovery
- [x] `CompetitorProgram` Pydantic model (program_id, asset_id, company, drug_name, nct_id, phase, status, primary_endpoint_type, indication)
- [x] `competitor_programs` table with `UNIQUE(asset_id, nct_id)` — idempotent across runs
- [x] `CompetitorDiscoveryEngine.discover(asset_id, asset_node_id, indication)` — injectable `search_fn` for testability
- [x] Skips inactive statuses (only RECRUITING, ACTIVE_NOT_RECRUITING, NOT_YET_RECRUITING, COMPLETED)
- [x] Upserts KG node per program + `competes_with` edge from asset node
- [x] Errors captured in result; no exceptions propagate to caller
- [x] No direct valuation changes; result routed to ReviewQueue by callers

### Wave 2C — Trial Design Assessment
- [x] `TrialDesignAssessment` model: quality tier, multiplier, power, low-power flag
- [x] Tier priority: SINGLE_ARM > OS_RCT > PFS > SURROGATE > STANDARD
- [x] Design quality multipliers: OS+RCT ×1.10, PFS ×1.00, SURROGATE ×0.85, SINGLE_ARM ×0.80
- [x] Two-sided z-test power (alpha/2), clamped to [0, 1]
- [x] `power_inputs` dict records n_patients, effect_size, alpha explicitly
- [x] `AlertTrigger.LOW_STATISTICAL_POWER` added to alert_model
- [x] `make_low_power_alert()` — HIGH severity, message includes power value
- [x] Guard: raises `ValueError` when called with `low_power_flag=False`

### Wave 2A — Knowledge Graph
- [x] `kg_nodes` and `kg_edges` tables in KnowledgeStore
- [x] Node types: asset, company, indication, target, mechanism, trial, competitor_program
- [x] Edge types: treats, targets, competes_with, same_indication, same_target, same_mechanism, same_trial_phase, same_endpoint, same_population, partnered_with
- [x] `add_node()`, `upsert_node()`, `get_node()`, `find_by_type()`, `add_edge()`, `neighbors()`, `get_subgraph(depth)`, `find_competing_assets()`
- [x] Edges store extraction confidence (clamped [0, 1])
- [x] `KGNode`, `KGEdge`, `NodeType`, `EdgeType` in `knowledge_graph.py`

### Wave 3A — Event Impact Ledger
- [x] `EventImpactLedger` with EWM scoring: `w_i = exp(-ln2 * age_days / half_life)`, `score = Σ(w_i * r_i) / Σ(w_i)`
- [x] Minimum observations gate: N ≥ 20 per category before `active=True`
- [x] Categories stratified by `(event_type, trial_phase, endpoint_type)` via `json_extract` on payload
- [x] `event_scores` table in KnowledgeStore with `UNIQUE(event_type, trial_phase, endpoint_type)`
- [x] `DEFAULT_EVENT_TYPE_SCORES` — static priors for all 20 event types; `effective_t30_score()` uses dynamic if N ≥ 20, else static
- [x] CLI: `bve-compute-event-scores`
- [x] 35 tests in `tests/test_event_impact_ledger.py`, all passing

### Wave 3B — Forecast Tracking
- [x] `forecast_records` table: signal_id, event_id, asset_id, event_type, signal_date, extraction_confidence, predicted_direction, predicted_delta_pct, actual_market_return_t30/t180, outcome_correct, resolved
- [x] `ForecastRecord` Pydantic model in `forecast_tracker.py`
- [x] `record_forecast(signal, diff, store)` hook — infers direction (primary_endpoint_met → fda_action_type → delta_npv sign), delta_pct from valuation_delta or NPV ratio
- [x] `resolve_forecasts(store)` — matches resolved event_outcomes to open forecasts; fills actuals + outcome_correct
- [x] `CalibrationReporter.report(store)` — directional accuracy, magnitude RMSE, Spearman ρ, confidence calibration bins (10 deciles), false positive rate
- [x] CLI: `bve-calibration-report`
- [x] 30 tests in `tests/test_forecast_tracker.py`, all passing
- [x] `horizon_days` (default 30) — explicit forecast window stored on every record
- [x] `predicted_at` — signal-extraction timestamp, separate from `created_at` (DB write time)

### Wave 3C — Reviewer Annotations
- [x] `ReviewDecision` extended: `reviewer_confidence` (0–1), `analyst_tags: list[str]`, `supporting_quote: Optional[str]`
- [x] `review_decisions` table: new columns `reviewer_confidence`, `analyst_tags_json`, `supporting_quote` (migration-safe via `_ensure_column`)
- [x] `audit_log` table — append-only; indexed on `(entity_type, entity_id)` and `(actor_id, created_at)`
- [x] `_append_audit_log()` called automatically inside `add_review_decision()` — no caller change needed
- [x] `query_audit_log(entity_type, entity_id, actor_id, action, limit)` — filter + paginate
- [x] CLI: `bve-audit-log` with `--json` output option
- [x] 30 tests in `tests/test_reviewer_annotations.py` (schema, persistence, audit append, filtering, forecast field tests)

### Pre-Wave-2 Hardening
- [x] DB deduplication: `INSERT OR IGNORE` on `raw_documents`, `UNIQUE` on `event_outcomes.event_id`
- [x] NYSE holiday calendar (2010–2035) replacing pure Mon–Fri busday arithmetic
- [x] Implied PoS guardrails: `WARNING` log when equity_value < 0, `INFO` log when raw implied > 1.0
- [x] PubMed 429 exponential backoff (2s → 4s → 8s → 16s, capped 60s)

---

*Test suite: **1 245 tests**, all passing (as of 2026-03-08).*

---

### Sprint 9 — Institutional-Grade Calibration

#### Task 9.19 — Monte Carlo Distribution Improvements
- [x] `mc_peak_sales_cv_by_stage` table added to `industry_assumptions.yaml` (preclinical → approved)
- [x] Phase ESS updated: phase_1=20, phase_2=25, phase_3=25, nda_bla=45
- [x] `AssumptionsLoader.mc_peak_sales_cv_by_stage` property
- [x] `MC_PEAK_SALES_CV_BY_STAGE` exported from `constants.py`
- [x] `_resolve_peak_sales_cv(asset, params)` — stage lookup with explicit-override short-circuit
- [x] `MonteCarloResult.peak_sales_cv_used` field populated on every run
- [x] `DEFAULT_CORRELATION` — `("peak_sales", "discount_rate", -0.15)` negative pair documented
- [x] Phase 1 MC width ≥ 1.5× Phase 3 width (integration test)
- [x] 23 tests in `tests/test_sprint9_phase5.py`, all passing

#### Task 9.21 — ValuationOutput Provenance
- [x] `ValuationOutput.assumptions_yaml_hash` — 12-char SHA-256 of industry_assumptions.yaml
- [x] `ValuationOutput.config_hash` — 12-char SHA-256 of asset YAML config (None when absent)
- [x] `ValuationOutput.wacc_vintage` — vintage tag from YAML (e.g. "2026-Q1")
- [x] `ValuationOutput.analyst_overrides` — list of override strings vs. defaults
- [x] `ValuationEngine._build_provenance()` and `_hash_file()` methods
- [x] Override detection for discount_rate, effective_tax_rate, nol_benefit_years

#### Task 9.22 — Audit Log Signal Lineage
- [x] Five new columns on `audit_log`: assumption_field, assumption_old_value, assumption_new_value, evidence_signal_id, review_decision_id
- [x] Migration-safe via `_ensure_column()` — no schema breakage for existing stores
- [x] `_append_audit_log()` accepts lineage kwargs; auto-populated by `add_review_decision()`
- [x] `query_audit_log(assumption_field=, signal_id=)` filter parameters
- [x] 20 tests in `tests/test_sprint9_phase6.py`, all passing

#### Task 9.18 — POS Backtest Dataset Validation
- [x] Dataset expanded: N=69 → N=77 (added 9 real Phase 2 oncology failures)
- [x] Phase 2 success rate corrected: 54.3% → 44.2% (within 35-50% target range)
- [x] Phase 3 success rate: 41.2% (within 35-55% target range)
- [x] Overall success rate: 42.9% (no survivor bias)
- [x] Model now shows positive skill: AUC=0.63, Brier=0.236 (vs 0.245 no-skill baseline)
- [x] Brier Skill Score: +3.7% positive
- [x] 19 dataset balance tests in `tests/test_sprint9_phase4.py`, all passing

#### Task 9.20 — Replay Statistical Graduation
- [x] Price history: 48 tickers, 2021-01-04 to 2026-03-20 (exceeds 2024-01-01 target)
- [x] 2024+ catalyst events: 46 events seeded (target: ≥25) — documented in `research/replay/events_2024.yaml`
- [x] N closed positions: 103 (run e9ffd496, 2021-2026, top2_add_hold30d) — exceeds N≥30 target
- [x] `alpha_validation` run: N=103, mean excess +2.20%, AUC t-stat 1.11 (p=0.269)
- [x] `edge_decomposition` run: thesis_error dominant (N=50, −7.62%); market_drift drives returns (N=45, +16.08%)
- [x] `coverage_audit` run: 43/81 tickers with full price coverage for 2024-01-01 → 2026-03-01
- [x] Graduation criteria formally defined and checked (PROJECT_STATE.md updated)
- [x] **Graduation status: ⚠️ Directional** — alpha does not survive corrections (clustered p=0.186, bootstrap CI includes 0)
- [x] Path to graduation documented: tighten catalyst gate, reduce ALNY cluster concentration, improve thesis scoring
