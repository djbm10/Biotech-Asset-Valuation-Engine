# project_state.md — Live Project State

Last updated: 2026-04-19
Branch: core-engine-v1

---

## Platform Build Plan Status

| Step | Description | Status |
|------|-------------|--------|
| 1 | Data ingestion layer (7 typed clients + RawEvent schema) | ✅ Complete (60 tests) |
| 2 | Evidence store + event classifier | ✅ Complete (76 tests) |
| 3 | Asset + acquirer dossier builders | ✅ Complete (54 tests) |
| 4 | Financing + dilution models | ✅ Complete (61 tests) |
| 5 | Market expectations / implied value | ✅ Complete (64 tests) |
| 6 | Science + trial-design scoring | ✅ Complete (75 tests) |
| 7 | Layered probability stack | ✅ Complete (68 tests) |
| 8 | Competition + readthrough engine | ✅ Complete (72 tests) |
| 9 | Variant thesis + catalyst payoff | Not started |
| 10 | Unified recommendation engine | Not started |
| 11 | Monitoring + recompute pipeline | Not started |
| 12 | Learning + calibration | Not started |
| 13 | UI | Not started |

---

## Test baseline

| Suite | Tests |
|-------|-------|
| Original engine (Sprints 1–26) | ~1,407 |
| Gap-fill Phases 1–6 | 226 |
| Total collected | 4,445 |

---

## Completed work

### Original valuation engine (Sprints 1–26)

Full rNPV pipeline: POS model, revenue model, cost model, Monte Carlo, scenarios,
sensitivities, LOE erosion, deal economics, multi-indication, competition model,
historical replay, POS backtest (N=99, Brier=0.21, AUC=0.74).

### Master build plan Phases A–O (2026-04-17)

All 15 phases implemented:

| Phase | What |
|-------|------|
| A | Architecture contract + master doc |
| B | Canonical asset graph (company/asset/trial/target/mechanism nodes + edges) |
| C | Automated evidence ingestion (CT.gov / SEC / press release parsers, conflict resolver) |
| D | Science diligence engine (8 sub-scores: mechanism, target, modality, biomarker, translational, analog, safety, trial design) |
| E | Layered probability stack (technical / regulatory / label / commercial + 5 approval scenarios) |
| F | Dynamic competition engine (graph-driven rerating on competitor events) |
| G | Financing engine (runway, raise timing, dilution band, financing-adjusted value) |
| H | Market access engine (patient funnel, access friction, constrained revenue) |
| I | Market expectations comparison (model vs implied PoS / peak sales / dilution) |
| J | Variant view engine (VariantThesis, VariantDelta, KillCriterion, falsifiers) |
| K | Catalyst payoff trees (8-scenario payoff distribution per catalyst) |
| L | Portfolio decision engine (portfolio-aware sizing, concentration/liquidity penalties) |
| M | Continuous monitoring engine (recompute queue, material alerts) |
| N | Calibration feedback loop (PoS priors, scenario weights, bias tracking) |
| O | Operating layer (audit, provenance, scenario diff, stale-input dashboard) |

### Gap-fill Phases 1–6 (2026-04-18)

| Phase | What | Tests |
|-------|------|-------|
| 1 | 22 state-object modules across analysis / models / intelligence / learning | 89 |
| 2 | GapFillStore SQLite persistence (9 tables + DecisionRecord / OutcomeRecord / ParameterVersion) | 31 |
| 3 | Monitoring pipeline: NewsMonitor, EventRouter, ModelTriggerEngine, AlertDispatcher | 35 |
| 4 | SignalFusionEngine + UnifiedRecommendationEngine (7-domain weighted fusion) | 22 |
| 5 | Learning loop: OutcomeLinker, RecalibrationJob, ShadowBacktest, WeightPromoter | 25 |
| 6 | Dashboard panels: ModelVsMarket, Recommendations, ThesisStatus, Calibration, EventHeatmap, DashboardBuilder | 24 |

---

## Completed — Catalyst Intelligence Phase 1 (Foundation)

35 tests passing. 14 new files:

| Package | Files |
|---------|-------|
| `src/bve/biology/` | `pathway_graph.py` (PathwayGraph — typed bio KG), `mechanism_reasoner.py` (template reasoner) |
| `src/bve/trials/` | `trial_parser.py` (CT.gov v2 + flat dict parser), `endpoint_library.py` (oncology/rare/rheum/derm) |
| `src/bve/regulatory/` | `fda_precedent_store.py` (approval/CRL corpus), `adcom_monitor.py` (adcom calendar) |
| `src/bve/knowledge/dossiers/` | `target_dossier.py`, `indication_dossier.py`, `asset_dossier.py` |

## Completed — Catalyst Intelligence Phase 2 (Decision Intelligence)

49 tests passing. 9 new files across 3 new packages:

| Package | Files |
|---------|-------|
| `src/bve/expectations/` | `market_implied_pos.py` (annuity backsolve), `implied_move.py` (IV + analog table), `variant_perception.py` (PerceptionDimension, net_conviction) |
| `src/bve/alpha/` | `asymmetry_score.py` (composite formula + instrument selector), `readthrough_engine.py` (8-rule competitor event assessment) |
| `src/bve/valuation/` | `scenario_tree.py` (6-branch tree builder, skew_ratio, setup_score), `financing_model.py` (runway, P(raise), distress tier, fin_risk) |

## Completed — Catalyst Intelligence Phase 3 (Trading Layer)

60 tests passing. 5 new files in `src/bve/trading/`:

| File | What |
|------|------|
| `instrument_selector.py` | 5-rule instrument picker (equity/call/put/straddle/no_trade) |
| `position_sizer.py` | Kelly-inspired sizer with financing + liquidity adjustments + hard caps |
| `exposure_decomposer.py` | HHI concentration, TA/phase bucketing, binary risk %, near-term catalyst % |
| `trade_signal.py` | Combines instrument + size → TradeSignal with action mapping |

## Completed — Catalyst Intelligence Phase 4 (Learning Layer)

52 tests passing. 3 new files in `src/bve/learning/`:

| File | What |
|------|------|
| `prediction_log.py` | SQLite-backed log; matched_pairs; Brier score + calibration error |
| `postmortem.py` | PostmortemStore; 8-category ErrorCategory enum; error_distribution |
| `rule_suggester.py` | Pattern-triggered rule suggestions; always requires_human_review |

## Completed — Catalyst Intelligence Phase 5 (Depth)

75 tests passing. 4 new files:

| File | What |
|------|------|
| `trials/oncology_endpoints.py` | 21 endpoints; by_tumor_type, established_primaries, surrogates |
| `trials/rare_disease_endpoints.py` | 17 endpoints across 5 indication areas; validated_endpoints |
| `regulatory/precedent_expander.py` | 16 records incl. 2 CRLs; lessons_for_modality |
| `biology/controversy_layer.py` | 7-type controversy tracker; weighted controversy_score |

---

## ALL CATALYST INTELLIGENCE PHASES COMPLETE (2026-04-18)

| Phase | Tests |
|-------|-------|
| Foundation (biology, trials, regulatory, dossiers) | 35 |
| Decision Intelligence (expectations, alpha, scenario tree, financing) | 49 |
| Trading layer (instrument selector, position sizer, exposure, signal) | 60 |
| Learning layer (prediction log, postmortem, rule suggester) | 52 |
| Depth (endpoint libraries, precedent corpus, controversy layer) | 75 |
| **Total new** | **271** |

---

## Package map (current)

```
src/bve/
  agents/          data ingestion sub-agents (fda, ct, pubmed, sec, news)
  alerts/          alert channels (log, slack, email, telegram)
  analysis/        implied_prob, backtest, SOTP, signal_fusion, unified_recommendation,
                   implied_expectations, market_vs_model, variant_view, catalyst_payoff,
                   portfolio_context, recommendation_engine, risk_budget
  architecture/    architecture contract tooling
  biology/         [NEW] pathway_graph, mechanism_reasoner
  cli/             run_asset, run_batch, calibrate, investment_memo, etc.
  config/          constants, settings, industry_assumptions
  connectors/      clinicaltrials, fda, pubmed, sec_edgar, press_release, market_prices
  dossier/         builder, asset_graph, dossier
  empirical/       empirical POS layer
  entities/        asset, company, indication, trial, company_snapshot
  event_study/     events, abnormal_returns
  features/        trial_features
  ingestion/       market_data, pricing_refs
  intelligence/    knowledge_layer, knowledge_graph, evidence_ingestion, science_engine,
                   dynamic_competition_engine, financing_engine, market_access_engine,
                   market_expectations, variant_view_engine, catalyst_payoff_trees,
                   portfolio_decision_engine, continuous_monitoring, calibration_feedback_loop,
                   operating_layer, competition_graph, readthrough_engine, revaluation_triggers,
                   + 40+ supporting intelligence modules
  knowledge/       [NEW] dossiers/target_dossier, indication_dossier, asset_dossier
  learning/        calibration, weight_updates, bias_report, outcome_linker,
                   recalibration_job, shadow_backtest, weight_promotion
  models/          pos_model, probability_model, revenue_model, cost_model, rnpv_model,
                   monte_carlo, competition_model, drug_asset_program, deal_economics,
                   multi_indication, probability_stack, label_breadth_model,
                   timeline_distribution_model, approval_scenarios, financing_risk,
                   dilution_model, runway_forecast, science_score, trial_design_score,
                   endpoint_validity, analog_matcher, safety_context
  normalization/   normalizer, registries, types, synonym configs
  ops/             historical_replay, weekly_runner, metrics
  persistence/     gap_fill_store
  pipeline/        news_monitor, event_router, model_trigger_engine, alert_dispatcher,
                   + pipeline state, change_detector, universe_registry
  regulatory/      [NEW] fda_precedent_store, adcom_monitor
  reporting/       memo_generator, charts, tables, export
  services/        scheduler, rate_limiter
  similarity/      scorer, stage_proximity, types
  trials/          [NEW] trial_parser, endpoint_library
  ui/dashboard/    model_vs_market_panel, recommendation_panel, thesis_status_panel,
                   calibration_panel, event_heatmap_panel, dashboard_builder
  utils/           trading_calendar
  valuation/       valuation_engine, scenario, outputs, assumptions, portfolio
  visualization/   valuation_charts, clinical_timeline, portfolio_charts, competitor_maps
```

---

## Planned modules (Phase 2–5)

```
src/bve/expectations/  market_implied_pos, implied_move, variant_perception
src/bve/valuation/     scenario_tree, financing_model  (extend existing valuation/)
src/bve/alpha/         asymmetry_score, readthrough_engine
src/bve/trading/       instrument_selector, position_sizer
src/bve/learning/      prediction_log, postmortem, rule_suggester
```

---

## NEW DIRECTION — Biotech M&A + Public Markets Intelligence Platform (2026-04-18)

**Transformation:** Extend BVE from a YAML-driven asset valuation tool into a live M&A + public-markets decision system.

### What already exists (reusable)
- rNPV valuation core (probability model, revenue model, cost model, Monte Carlo)
- Catalyst intelligence phases 1–5 (biology KG, trial parser, endpoint library, FDA precedent, implied PoS, variant perception, asymmetry score, readthrough engine, scenario trees, trading layer, learning layer)
- Gap-fill phases 1–6 (persistence store, monitoring pipeline, signal fusion, learning loop, dashboard panels)
- Ingestion: CT.gov v2, SEC EDGAR, market data (yfinance)
- Entities: Asset, Company, Trial, Indication
- Dossier: AssetDossier builder with provenance fields
- Normalization: entity normalizer

### What needs to be built
| Component | Priority |
|-----------|----------|
| PostgreSQL + SQLAlchemy 2.0 + Alembic (replace SQLite for prod) | P0 |
| Acquirer entity + AcquirerProfile (big pharma strategic profiles) | P0 |
| Acquisition fit engine (strategic/modality/affordability/timing) | P0 |
| FastAPI application (16 endpoints) | P0 |
| Next.js web app (6 pages) | P0 |
| Redis + Dramatiq worker queue | P1 |
| News ingestion client | P1 |
| Entity resolution (alias + fuzzy + conflict queue) | P1 |
| Full acquirer universe (PFE, LLY, MRK, AZN, BMY, ROCHE, NVO, etc.) | P1 |
| Variant thesis CRUD with kill criteria | P1 |
| Alert dispatcher | P2 |
| Slack/email notifications | P3 |

### 16-step execution plan: see tasks.md

### Current step: Step 1 — Database foundation


---

## Platform Build Progress (2026-04-19)

### Completed steps

| Step | What | Tests |
|------|------|-------|
| 1 | DB foundation: PostgreSQL-compatible ORM (16 tables), Alembic migrations, 4 repos | 38 |
| 2 | Acquirer entity + EntityResolver (alias table, fuzzy, conflict detection) | 42 |
| 8 | Acquisition fit engine: 7-dimension scoring, timing buckets, rank_targets/rank_acquirers | 37 |
| 13 | FastAPI app: 6 routers, 10 endpoints, TestClient suite | 40 |

**Total new platform tests: 157 (all passing)**

### Remaining steps (priority order)

| Step | Focus | Priority |
|------|-------|----------|
| 3 | Ingestion clients (SEC, news, PubMed) | P1 |
| 4 | Evidence store + event classifier | P1 |
| 5 | Asset + acquirer dossier sync | P1 |
| 6 | Science/trial scoring modules | P2 |
| 7 | Probability stack + financing-adjusted EV | P2 |
| 9 | Catalyst trees + variant thesis | P2 |
| 10 | Recommendation fusion layer | P2 |
| 11 | Dramatiq + Redis background jobs | P3 |
| 12 | Learning/calibration loop | P3 |
| 14 | Next.js web app | P3 |
| 15 | Alerts + dashboards | P3 |
| 16 | Docs + blueprint freeze | P3 |

