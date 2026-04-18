# project_state.md — Live Project State

Last updated: 2026-04-18
Branch: core-engine-v1

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

## In progress

### Catalyst Intelligence and Asymmetry Engine — Phase 2 (Decision Intelligence)

| Module | Status |
|--------|--------|
| `src/bve/expectations/market_implied_pos.py` | planned |
| `src/bve/expectations/implied_move.py` | planned |
| `src/bve/expectations/variant_perception.py` | planned |
| `src/bve/valuation/scenario_tree.py` | planned |
| `src/bve/valuation/financing_model.py` | planned |
| `src/bve/alpha/asymmetry_score.py` | planned |
| `src/bve/alpha/readthrough_engine.py` | planned |

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
