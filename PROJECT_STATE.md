# PROJECT_STATE.md

## Current Module Being Worked On

Sprint 9 — Institutional grade model fixes (Phase 1 complete)

## Last Change

**Sprint 9 Phase 1 (core model math) complete (2026-03-25):**
- Task 9.1: UFCF/Tax treatment — applied 21% effective tax to EBIT in RNPVModel;
  added `effective_tax_rate` + `nol_benefit_years` to Asset; `tax_rate_add` to
  ScenarioAssumptions; `effective_tax_rate` as 6th sensitivity tornado parameter.
  All rNPV baselines decreased ~40-45%.
- Task 9.2: POS Layer 1 cap — ±0.80 log-odds cap on combined adjuster delta;
  extracted `_compute_layer1_adjustment()` helper.
- Task 9.3: BTD log-odds correction — reduced from +0.20 to +0.05; BTD is a process
  designation (faster review), not a binary approval probability booster.
- Task 9.4: WACC modernization — default discount_rate 0.10 → 0.12 (2026-Q1);
  added `vintage` and `erp_biotech` calibration fields to wacc section.
- Regression fixtures updated in: test_phase1.py, test_step2.py, test_step3.py,
  test_step6.py, test_step7.py (all 6 test files, all passing).
- Pre-existing test bugs fixed: test_competition_crowding.py floor test (floor_residual_share
  became configurable; test now sets it explicitly).

## Next Step

Sprint 9 Phase 2 (revenue/cost corrections):
- Task 9.5: S-curve uptake warning when not configured
- Task 9.6: Compliance rate differentiation by modality
- Task 9.7: SG&A ramp profiles by commercial stage
- Task 9.8: Accelerated approval pathway POS differentiation
- Task 9.9: Post-approval R&D cost modeling
- Task 9.10: LOE extension to 5-year tail for small molecules

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

Extend weekly output with the top-10 M&A probability scan and new threshold-cross names.
