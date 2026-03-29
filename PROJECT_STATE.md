# PROJECT_STATE.md

## Current Module Being Worked On

**All ROADMAP phases complete (Sprints 10–24). System is operational.**

Full roadmap: ROADMAP.md | Full task history: TASKS.md

## Replay Statistical Graduation Status (Sprint 24 — 2026-03-29)

**Current status: ⚠️ Directional (pre-institutional) — signal weak, not infrastructure-limited**

### Graduation Criteria (all must pass for ✅ Pre-institutional HF grade)

| Criterion | Target | Current (run 906fc24b) | Status |
|-----------|--------|------------------------|--------|
| N closed positions | ≥ 30 | **83** (capped, max 15/asset) | ✅ |
| ALNY cluster share | ≤ 20% | **18.1%** (15/83) | ✅ |
| Mean excess return | > 0% | **+1.42%** | ✅ |
| Hit rate | > 50% | **51.8%** | ✅ |
| Naive t-stat | > 1.65 (p<0.10) | 0.86 (p=0.39) | ❌ |
| Alpha survives clustered SE | p < 0.10 | Not yet computed | ❌ |
| Bootstrap 90% CI excludes 0 | Lower bound > 0 | Not yet computed | ❌ |
| Score decile monotonicity | Decile 9-10 > Decile 1-2 | N insufficient | ❌ |

### Sprint 24 Improvements (2026-03-29)

**Per-asset concentration cap** added to `ReplayPolicyConfig.max_decisions_per_asset`:
- Previous best: N=22 (catalyst-gated) or N=103 with 39% ALNY cluster
- Sprint 24 result: N=83, ALNY=18.1%, mean excess=+1.42%, hit rate=51.8%
- Cap flag: `--max-decisions-per-asset 15`

**Sprint 23 improvements**: 42 trial readout events seeded for 2021-2023 (from 88 → 130 total
historical events). Catalyst gate N improved from 22 → 21 (marginal, as expected — seeded events
are announcement dates not forward-scheduled catalysts).

### Why Alpha Doesn't Survive Statistical Tests

N=83 trades over 5 years with std=15.03% per trade requires N≥302 for p<0.10 at the observed
1.42% mean excess (power calculation: N = (z × σ / μ)² = (1.645 × 15.03 / 1.42)² ≈ 302).

This is a fundamental statistical limit, not an infrastructure bug. To achieve p<0.10:
- **Option A**: Continue accumulating live decisions (estimated: 5–7 more years at current pace)
- **Option B**: Improve signal quality — reduce thesis_error rate (current: 31/83 = 37% of decisions)

### Edge Decomposition (run 906fc24b, capped)
- **thesis_error** dominates negatively (N=31, −6.5% avg) — signal firing on claims without resolution
- **market_drift** is the positive driver (N=35, +14.4% avg) — broad biotech beta
- Signal carriers: KYMR (N=10, mean=+13.6%), RVMD (N=9, mean=+8.0%), MDGL (N=9, mean=+4.7%)

### Path to Improved Graduation
1. **Reduce thesis_error rate**: Resolve more KnowledgeStore claims so thesis_strength ≠ 0.5 (neutral)
   — currently all claims default to neutral (no resolved outcomes), making thesis score noise
2. **Run bve-daily-brief regularly**: accumulate screen_snapshots and resolved claims over time
3. **Live decision tracking**: use `pos_predictions` table to record predictions; resolve outcomes
   when readouts occur; feed into `CalibratedPOSModel` to improve the model PoS signal

### Data Coverage (2026-03-29)
- Price history: 48 tickers, 2021-01-04 to 2026-03-20
- Total seeded events: 130 (69 pre-2024 trial/PDUFA; 61 from 2024-2026)
- POS backtest dataset: N=99 (Phase 2=39.6%, Phase 3=60.8%), Brier=0.213, AUC=0.74
- KnowledgeStore claims resolved: 0 (all thesis_strength = 0.5 neutral)

## Last Change

**Sprint 9 Phase 2 (revenue/cost corrections) complete (2026-03-26):**
- Task 9.5: S-curve uptake warning — `MarketModel._check_uptake_shape` validator emits
  `UserWarning` when `use_s_curve=False` for patient-based or TAM-based market models.
  LoT models skip the check (validator returns early when `lines_of_therapy` is set).
- Task 9.6: Modality compliance rates — `compliance_by_modality` table in YAML;
  `AssumptionsLoader.compliance_rate(modality)` with "biologic" → "biologic_iv" alias
  and "other" fallback. Engine warns when gene/cell therapy asset has `compliance_rate < 1.0`.
- Task 9.7: SG&A auto-selection — `ValuationEngine._resolve_market_model_with_sgna()`;
  gene/cell therapy → gene_cell_therapy profile (55%/28%/7yr); rare_disease → rare_disease
  profile (45%/22%/4yr); explicit SG&A override preserved; emits advisory UserWarning.
- Task 9.8: Accelerated approval NDA discount — 18% base-rate reduction at NDA/BLA phase
  only; `ApprovalPathwayType` enum on Asset; `compute_pos()` accepts `approval_pathway`;
  PRIORITY_REVIEW has no effect. Oncology NDA/BLA: 83% standard → 68% accelerated.
- Task 9.9: Post-approval R&D cost — `post_approval_rd_millions` field on Asset (default 0.0);
  `CostModel.compute()` discounts at `years_to_approval`, weighted by `cumulative_approval_probability`;
  exposed as `post_approval_rd_pv_millions` on `CostStream`.
- Task 9.10: LOE tail 5-year extension — `_LOE_TAIL_KEYS` extended to 5 entries; backward
  compat via `break` for old 3-key profiles; all 7 YAML modality profiles extended with
  `year_4_loss` and `year_5_loss`; small_molecule `terminal_loss` 0.85→0.95.
- Regression fixtures updated: test_step2.py, test_step3.py, test_step6.py, test_step7.py
  (LOE 3→5 yr: 81.01→83.13, 82.36→84.27, 223.19→228.04, 1.41→2.71).
- Acceptance tests added: `tests/test_sprint9_phase2.py` (47 tests, all passing).
- Run_asset.py F401 lint fix (unused `_TrialPhase` import removed).
- Test baseline: 512 passing (was 465).

## Next Step

OR resume Sprint 8 Task 8.7 Step 6:
- Extend weekly output with top-10 M&A probability scan

**Sprint 8 context (before Sprint 9 audit detour):**
- Acquisition screener implemented with persisted
  `acquisition_discount_snapshots` and `bve-acquisition-screen`.
- Comparable-deal loader/matcher implemented with manual research files in
  `research/mna/`.
- Acquisition-readiness filter implemented as a strict Phase 2 POC+ gate.
- M&A replay profile implemented with quarterly cadence, 365-day holds, top-8
  open-position cap, no catalyst gate, and `-40%` loss blocking.
- Manual comp research is seeded but not exhausted:
  `comparable_deals.yaml` currently contains 26 screenable public deals and
  `deal_universe_2020_2026.yaml` contains a broader 43-deal sourcing universe.
- Named live/public targets are tracked separately in
  `research/mna/target_monitor.yaml` so open targets do not get mixed into the
  closed-deal comparable database.
- Added Task 8.6 to `tasks.md` for acquirer pipeline gap analysis, fit scoring,
  and acquisition-memo generation.
- Created `research/mna/pipeline_gaps.yaml` with the initial Regeneron profile.
- Seeded Step 1 fields for:
  - therapeutic-area gaps / franchise-pressure lanes
  - preferred modalities
  - strategic priorities
  - recent deal history with implied valuation bands
  - budget snapshot with dated primary-source metadata
- Added `src/bve/intelligence/acquirer_profiles.py` with typed Pydantic models,
  YAML loading, case-insensitive acquirer lookup, and validation for duplicate
  IDs, value-band consistency, and budget net-cash consistency.
- Added `tests/intelligence/test_acquirer_profiles.py` covering repository YAML
  loading plus validation failures for duplicate IDs, invalid net cash, invalid
  value bands, and unknown acquirer lookup.
- Added `src/bve/intelligence/acquirer_fit.py` with:
  - `AcquirerFitCandidate`
  - `AcquirerFitScore`
  - `AcquirerFitScorer`
  - component-level scoring for therapeutic-area fit, modality fit,
    stage/readiness fit, strategic-priority overlap, valuation fit, and budget
    fit
  - explicit hard-fail reasons such as `outside_budget` and
    `not_acquisition_ready`
- Added `tests/intelligence/test_acquirer_fit.py` covering strong-match scoring,
  budget hard fails, readiness gating, valuation sensitivity, and
  `from_acquisition_row()` mapping.
- Extended `src/bve/intelligence/acquirer_fit.py` with:
  - `AcquirerFitIntegrationConfig`
  - `AcquirerFitRow`
  - `AcquirerFitResult`
  - `AcquirerFitEngine`
  - integration of acquirer profiles, acquisition-screen rows, comparable-deal
    analysis, and context-derived modality mapping into one stable ranked output
- Added `tests/intelligence/test_acquirer_fit_engine.py` covering:
  - watchlist-level ranking across integrated acquisition-screen rows
  - hard-filter propagation for non-ready assets
  - stable tie-breaking by `asset_id`
- Added `src/bve/intelligence/acquisition_memo.py` with:
  - `IndicativeDealTerms`
  - `AcquisitionMemo`
  - `AcquisitionMemoGenerator`
  - reuse of the existing `bd` memo generator for the base memo
  - reuse of `DealEconomics` + `DrugAssetProgram` + `ValuationEngine.from_program()`
    for deterministic post-deal economics
  - deterministic acquirer-fit addendum appended to each memo
- Added `tests/intelligence/test_acquisition_memo.py` covering:
  - base BD memo reuse plus acquirer-fit addendum rendering
  - stage-aware indicative deal-term planning for milestone-heavy Phase 2 targets
- Added `src/bve/cli/acquirer_fit.py` and registered `bve-acquirer-fit` so the
  acquirer-fit flow can be run directly from the command line with:
  - report or JSON ranking output
  - optional per-target acquisition memo generation to markdown
  - optional memo persistence into the knowledge store
- Added `tests/intelligence/test_acquirer_fit_cli.py` covering report output,
  JSON output, and memo-writing / persistence flag forwarding
- Added Task 8.7 to `tasks.md` for the M&A probability scanner built on top of
  acquirer-fit scoring plus target-side vulnerability signals.
- Started Step 1 with `research/mna/vulnerability_signals.yaml`.
- The initial vulnerability-signal file now:
  - separates dynamically computed cash-runway pressure from manually curated
    overlays
  - defines staleness windows for insider, board-change, and same-space deal
    signals
  - seeds the first same-space external-deal signal for obesity using the
    existing Regeneron / Hansoh in-license research
- Added `src/bve/intelligence/vulnerability_signals.py` with:
  - typed Pydantic models for vulnerability signal policy, target-specific
    signals, and same-space external deal activity
  - duplicate `signal_id` validation across target and external signals
  - staleness-window validation tied to declared manual signal types
  - query helpers for target matching and same-space deal lookup
- Added `tests/intelligence/test_vulnerability_signals.py` covering repository
  YAML parsing, duplicate-signal rejection, staleness-window validation,
  identifier requirements, and stale-signal filtering
- Added `src/bve/intelligence/ma_probability.py` with:
  - `MAProbabilityScanner` on top of `AcquirerFitEngine`
  - multi-acquirer target evaluation with one best-acquirer probability per
    asset
  - explicit component separation for valuation discount, strategic fit,
    de-risking stage, and vulnerability
  - target-side vulnerability assessment using dynamic cash-runway pressure plus
    manual board / insider / same-space deal overlays
- Added an as-of-aware capital-risk helper in
  `src/bve/intelligence/capital_structure.py` so probability scans can be run
  deterministically for arbitrary snapshot dates
- Added `tests/intelligence/test_ma_probability.py` covering:
  - multi-acquirer ranking
  - runway / catalyst vulnerability contribution
  - separation of strategic-fit and valuation components
- Extended `src/bve/intelligence/ma_probability.py` with:
  - `MAProbabilitySnapshotRecord`
  - `MAProbabilitySnapshotStore`
  - `MAProbabilityMonitorConfig`
  - `MAProbabilityMonitorResult`
  - `MAProbabilityMonitor`
  - deterministic scan timestamps derived from `snapshot_date`
  - persisted daily M&A probability snapshots for all ranked rows
  - idempotent `ma_probability_threshold_cross` and
    `ma_probability_top_n_entry` alerts stored through `opportunity_alerts`
- Extended `tests/intelligence/test_ma_probability.py` with coverage for:
  - snapshot persistence across scan dates
  - threshold-cross alert emission at the configured probability threshold
  - top-entry alert emission when a target moves into the configured rank
    window
  - duplicate suppression on same-day reruns
- Added `src/bve/cli/ma_probability.py` and registered
  `bve-ma-probability` with:
  - report and JSON output for watchlist-level M&A probability scans
  - explicit `--emit-alerts` control so ad hoc runs stay read-only by default
  - configurable `--alert-threshold`, `--top`, and research-file overrides
- Added `tests/intelligence/test_ma_probability_cli.py` covering:
  - report output
  - JSON output
  - forwarding of `--emit-alerts`, `--alert-threshold`, `--top`, `--as-of`,
    and readiness-filter settings

## Next Step

Sprint 10: build `research/universe_params.yaml` → `ops/universe_configs.py` → `analysis/implied_pos_batch.py` → `cli/universe_screen.py` → `bve-universe-screen` CLI.
The spread signal (model_pos - implied_pos) is the primary mispricing output for the daily PM workflow.
