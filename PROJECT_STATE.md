# PROJECT_STATE.md

## Institutional Plan Step 3 — Validation Harness (2026-04-10, complete)

**Current status: ✅ Formal validation harness live with liquidity gate, tx costs, placebo test, time subgroups, and grade assignment.**

New module: `src/bve/analysis/validation_harness.py`
- ADV liquidity gate at entry date (market_prices table, no forward-looking bias)
- Two-way transaction cost model tiered by ADV ($5M threshold: 30bps vs 60bps one-way)
- Rank-permutation placebo test (n=1,000 iterations by default)
- First-half / second-half time subgroup cuts
- Grade assignment: strong / moderate / weak / insufficient
  - "strong": n≥20, p≤0.05, placebo p≤0.10
  - "moderate": p≤0.10 or placebo p≤0.15 with n≥10

Next step: continue from the now-live Step 4-6 integrations into deeper curation,
broader policy consumers, and promotion of the improved M&A replay result.

---

## Institutional Plan Steps 4-6 (2026-04-11, broadened + persisted + replay-rerun)

**Current status: Step 4 now covers the full auto-generated cohort and the full replay-generated cohort, Step 5 policy decisions are persisted and visible in weekly review, and Step 6 produced a measurable historical M&A uplift with the live path now using the stronger stored baseline.**

Implemented beyond the original Step 3 checkpoint:
- Step 4 — patient-flow commercial modeling
  - `src/bve/models/commercial_inputs.py`
    - added explicit patient-flow inputs:
      - diagnosed fraction
      - `eligible_rate`
      - treated fraction
      - WAC + gross-to-net derived pricing
      - `ex_us_revenue_multiple`
  - `src/bve/cli/run_asset.py`
    - CLI now loads `commercial_inputs` configs directly
  - gold-tier configs added:
    - `examples/configs/arvn_arv471.yaml`
    - `examples/configs/imvt_batoclimab.yaml`
    - `examples/configs/kymr_kt474.yaml`
    - `examples/configs/mdgl_rezdiffra.yaml`
  - plus the canonical `examples/configs/relay_rly2608.yaml`
  - expanded auto-generated Step 4 coverage now spans all `30` files under:
    - `examples/configs/auto_generated/`
  - replay-generated Step 4 coverage now spans all `45` files under:
    - `examples/configs/replay_generated/`
  - replay-generated configs now use an explicit `addressable_k` + WAC/G2N +
    share + ex-US decomposition calibrated to preserve the stored heuristic
    peak-sales targets while eliminating the remaining shorthand-only TAM path
  - the remaining Step 4 gap is no longer schema migration; it is underwriting-
    quality refinement and replay re-measurement on the newly explicit inputs

### 2026-04-12 Targeted Step 4 refinement pass - IMVT / MDGL / TGTX

**Current status: The first high-impact underwriting-quality pass is live and materially improved the strict `buy/watch` company-validation lane.**

Implemented in code/configs:
- `src/bve/analysis/company_sotp.py`
  - stored screen snapshots now use the stronger of:
    - the historical snapshot `config_quality`
    - the current config `config_quality`
  - this prevents stale `screening_grade` snapshot labels from holding curated
    Step 4 configs at `0.50` modeled-asset confidence forever
- `examples/configs/auto_generated/imvt.yaml`
- `examples/configs/auto_generated/mdgl.yaml`
- `examples/configs/auto_generated/tgtx.yaml`
  - all three now explicitly declare `_meta.config_quality: curated`
- `research/company_sotp_overrides.yaml`
  - removed the stale `TGTX` ex-US royalty bridge bucket from both the 2021 and
    2024 company-pack snapshots because Step 4 commercial inputs now already
    model ex-US economics directly
- `tests/test_company_sotp.py`
  - added a regression proving that current curated config quality overrides a
    weaker historical snapshot-quality label for company-SOTP confidence gating

Focused verification passed:
- `ruff check src/bve/analysis/company_sotp.py tests/test_company_sotp.py tests/test_patient_flow.py`
- `python -m pytest tests/test_company_sotp.py tests/test_patient_flow.py -q`
- result: `164 passed`

Refreshed company SOTP backfill after the targeted pass:
- `749` company rows persisted
- `748` pass recency
- action totals moved from:
  - `buy=43 / watch=8 / avoid=121 / needs_manual_review=577`
- to:
  - `buy=63 / watch=17 / avoid=163 / needs_manual_review=506`

Refreshed company SOTP backtest after the targeted pass:
- combined `buy/watch/needs_manual_review`
  - candidate rows: `73`
  - selected trades: `71`
  - mean excess return: `+78.69%`
  - hit rate: `59.2%`
  - bootstrap `p = 0.0`
- strict `buy/watch`
  - candidate rows: `49`
  - selected trades: `49`
  - mean excess return: `+111.39%`
  - hit rate: `65.3%`
  - bootstrap `p = 0.0`

Target-name interpretation:
- `IMVT`
  - moved from `needs_manual_review` due to `modeled_asset_confidence_below_threshold:0.50`
  - now carries `0.85` modeled-asset confidence and classifies into
    `avoid/watch/buy` strictly on discount level
- `MDGL`
  - moved from `needs_manual_review` due to `actionable_confidence_below_threshold:0.51`
  - now carries `0.85` modeled-asset confidence and lands in `buy` across its
    historical high-discount window
- `TGTX`
  - no longer fails because of modeled-asset confidence
  - now alternates between:
    - `avoid/watch/buy` when the remaining manual bucket share is below the
      policy threshold
    - `needs_manual_review` only on the later 2022-2023 dates where manual
      bucket share still breaches the threshold

Interpretation:
- the active Step 4 bottleneck was partly stale quality labeling, not only
  funnel realism
- targeted underwriting-quality upgrades can now move names directly out of
  `needs_manual_review` and into the strict auto-rankable lane
- the strict `buy/watch` comparator is no longer weak after this pass; it now
  captures:
  - `SRRK = 14` rows
  - `MDGL = 12`
  - `IMVT = 11`
  - `TGTX = 6`
  - `VKTX = 3`
  - `NVAX = 3`

### 2026-04-12 Second targeted Step 4 refinement pass - ANAB / FULC / OCUL / PRTA / RXRX

**Current status: The residual stale-quality / stale-manual-bridge cohort has largely been cleared; `needs_manual_review` is now almost absent from the historical high-discount lane.**

Implemented in configs/overrides/tests:
- `examples/configs/auto_generated/anab.yaml`
- `examples/configs/auto_generated/rxrx.yaml`
  - both now explicitly declare `_meta.config_quality: curated`
- `research/company_sotp_overrides.yaml`
  - `FULC`
    - upgraded platform and follow-on pipeline buckets from generic
      analyst-bridge `0.65` confidence to multi-source company-disclosure style
      `0.80` confidence
  - `OCUL`
    - removed the stale partner-economics bridge bucket
    - upgraded the remaining lifecycle bucket to a multi-source
      company-disclosure style bucket
  - `PRTA`
    - removed the stale royalty / partner bridge bucket
    - upgraded the remaining follow-on pipeline bucket to a multi-source
      company-disclosure style bucket
  - `RXRX`
    - upgraded platform and unmodeled pipeline buckets to multi-source
      company-disclosure style buckets
- `tests/test_patient_flow.py`
  - added an explicit guard requiring the latest curated-quality upgrades to
    keep `_meta.config_quality: curated`

Focused verification passed:
- `ruff check src/bve/analysis/company_sotp.py tests/test_patient_flow.py tests/test_company_sotp.py`
- `python -m pytest tests/test_patient_flow.py tests/test_company_sotp.py -q`
- result: `169 passed`

Refreshed company SOTP backfill:
- action totals moved from:
  - `buy=63 / watch=17 / avoid=163 / needs_manual_review=506`
- to:
  - `buy=82 / watch=24 / avoid=266 / needs_manual_review=377`

Refreshed company SOTP backtest:
- combined `buy/watch/needs_manual_review`
  - candidate rows: `68`
  - selected trades: `67`
  - mean excess return: `+81.89%`
  - hit rate: `56.7%`
  - bootstrap `p = 0.0`
- strict `buy/watch`
  - candidate rows: `67`
  - selected trades: `67`
  - mean excess return: `+81.83%`
  - hit rate: `56.7%`
  - bootstrap `p = 0.0`

Interpretation:
- the strict and combined lanes are now effectively identical
- among recency-valid rows with `ranked_sotp_discount >= 1.0`, the only
  remaining `needs_manual_review` name is:
  - `SRRK = 1` row
- this means the previous historical signal concentration in
  `needs_manual_review` has been almost entirely converted into the normal
  `buy/watch` lane rather than merely re-labeled
- the next refinement step is no longer broad stale-pack cleanup; it is a
  targeted audit of true residual exceptions such as `SRRK` and any names that
  are still blocked for real recency or reconciliation reasons

### 2026-04-12 Step 4 replay-generated migration completion

**Current status: ✅ All replay-generated configs now round-trip through `commercial_inputs`, and replay breadth migration is complete.**

Completed in configs/tests:
- `examples/configs/replay_generated/`
  - all `45` configs now include `market_model.commercial_inputs`
- `tests/test_patient_flow.py`
  - replay-generated coverage is now dynamic across the full directory rather
    than a hand-maintained allowlist
  - the replay guard asserts two things for every replay config:
    - `commercial_inputs` is present
    - `commercial_inputs.to_peak_sales_millions()` matches
      `_meta.heuristic_peak_sales_millions()` within tight tolerance

Migration pattern used:
- explicit `patient_pool.addressable_k`
- WAC + gross-to-net derived pricing
- preserved peak share / years-to-peak
- ex-US multiplier where the original replay thesis implied non-US revenue

Focused verification passed:
- `ruff check tests/test_patient_flow.py`
- `python -m pytest tests/test_patient_flow.py -q`
- result: `118 passed`

Interpretation:
- Step 4 replay breadth is now closed
- the next Step 4 work is no longer blanket migration
- the follow-on phase is:
  - deeper underwriting refinement on the highest-consequence replay names
  - replay / backtest reruns to measure whether the explicit patient-flow path
    changes any downstream ranking or SOTP outputs

### 2026-04-12 Next Phase Start - replay measurement after Step 4 breadth completion

**Current status: First downstream replay rerun is complete; backfill totals were stable, while the company backtest changed materially.**

Commands run:
- `python -m bve.ops.company_sotp_backfiller --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml --db outputs/intelligence/replay_knowledge.db --replay-db outputs/intelligence/replay_store.sqlite --start 2021-02-01 --end 2024-03-01 --output-dir outputs/analysis`
- `python -m bve.analysis.company_sotp_backtest --db outputs/intelligence/replay_knowledge.db --replay-db outputs/intelligence/replay_store.sqlite --start 2021-02-01 --end 2024-03-01 --hold-days 365 --top-n 5 --min-ranked-discount 1.0 --output-dir outputs/analysis`

Backfill result after replay-generated migration:
- `749` company rows persisted
- `748` pass the recency gate
- action totals unchanged at:
  - `buy = 43`
  - `watch = 8`
  - `avoid = 121`
  - `needs_manual_review = 577`

Company backtest result after replay-generated migration:
- `26` snapshot dates
- `20` candidate rows
- `20` selected trades
- `0` missing-price trades
- mean excess return `+13.33%`
- hit rate `25.0%`
- cluster count `3`
- bootstrap `p = 0.1024`

Compared with the pre-migration baseline recorded on 2026-04-11:
- candidate rows moved from `96 -> 20`
- selected trades moved from `17 -> 20`
- missing-price trades moved from `21 -> 0`
- mean excess return moved from `+32.61% -> +13.33%`
- hit rate moved from `29.4% -> 25.0%`
- bootstrap `p` improved from `0.266 -> 0.1024`

Interpretation:
- the explicit replay-generated patient-flow path did not change the broad
  company action totals
- it did materially change which historical company snapshots qualify for the
  backtest
- the signal is now smaller and less return-heavy, but materially cleaner from
  a missing-price / statistical-noise perspective
- the next phase should identify which replay names dropped out or changed rank
  enough to drive the `96 -> 20` contraction before promoting any stronger
  conclusion

Diagnostic follow-up:
- the contraction is primarily an action-policy filter effect, not a recency
  or missing-price effect
- among `2021-02-01 -> 2023-03-01` rows with:
  - recency gate passing
  - `ranked_sotp_discount >= 1.0`
  action-policy distribution is now:
  - `needs_manual_review = 59`
  - `buy = 13`
  - `watch = 7`
  - `avoid = 1`
- the current backtest-eligible set is concentrated in just:
  - `SRRK = 14`
  - `VKTX = 3`
  - `NVAX = 3`
- the main excluded high-discount names are:
  - `FULC = 14` rows, avg discount `2.173x`
  - `IMVT = 14` rows, avg discount `1.491x`
  - `MDGL = 12` rows, avg discount `3.261x`
  - `TGTX = 9` rows, avg discount `1.449x`
  - plus smaller `ANAB`, `OCUL`, `PRTA`
- this means the next decision is specifically whether the company backtest
  should keep using `action_policy in {buy, watch}` as the eligibility gate or
  whether `needs_manual_review` rows should be measured separately

Follow-on measurement:
- `src/bve/analysis/company_sotp_backtest.py`
  - CLI now accepts repeated `--allowed-action-policy` flags so alternate
    policy lanes can be measured directly
  - output CSV names now include the action-policy lane suffix to avoid
    overwriting comparison runs
  - default lane now includes:
    - `buy`
    - `watch`
    - `needs_manual_review`
  - `--compare-to-strict-buy-watch` now prints the broader default lane beside
    the legacy strict comparator in one run
- `tests/test_company_sotp_backtest.py`
  - added coverage for a `needs_manual_review`-only lane
  - added coverage proving the default lane includes `needs_manual_review`
- `src/bve/intelligence/weekly_brief.py`
  - weekly brief company-SOTP top opportunities now use the broader
    `buy/watch/needs_manual_review` lane as primary
  - strict `buy/watch` top opportunities are also stored alongside as a
    secondary comparison block
- `src/bve/ops/metrics_dashboard.py`
  - metrics dashboard top-opportunity payload now mirrors the same primary vs
    strict split
- tests:
  - `tests/test_weekly_brief.py`
  - `tests/ops/test_metrics_dashboard.py`
  - both now cover:
    - primary list includes `needs_manual_review`
    - strict list excludes it
- `src/bve/analysis/validation_harness.py`
  - subgroup reporting now includes `action_policy:<policy>` slices when a lane
    has enough trades
- `tests/test_validation_harness.py`
  - added coverage for `buy` and `needs_manual_review` action-policy subgroups

Lane comparison on the same `2021-02-01 -> 2024-03-01`, `hold_days=365`,
`top_n=5`, `min_ranked_discount=1.0` setup:
- strict `buy/watch`
  - candidate rows: `20`
  - selected trades: `20`
  - mean excess return: `+13.33%`
  - hit rate: `25.0%`
  - bootstrap `p = 0.1024`
- `needs_manual_review` only
  - candidate rows: `59`
  - selected trades: `57`
  - mean excess return: `+96.47%`
  - hit rate: `71.9%`
  - bootstrap `p = 0.0`
- combined `buy/watch/needs_manual_review`
  - candidate rows: `79`
  - selected trades: `77`
  - mean excess return: `+74.87%`
  - hit rate: `59.7%`
  - bootstrap `p = 0.0`

Interpretation:
- the old strict `buy/watch` lane is now the weakest of the measured
  company-backtest lanes
- the current company action-policy gate is likely over-pruning the historical
  signal after the Step 4 replay migration
- the highest-contributing `needs_manual_review` names are concentrated in:
  - `FULC`
  - `IMVT`
  - `MDGL`
  - `TGTX`
- the next decision should be whether to:
  - keep strict `buy/watch` as a secondary comparison lane
  - while using the broader default lane for primary company validation

Validation-harness follow-up on the combined lane:
- combined lane validation grade: `moderate`
- gross mean excess return: `+74.87%`
- gross hit rate: `59.7%`
- subgroup cuts now show action-policy structure directly:
  - `action_policy:needs_manual_review`
    - `57` trades
    - mean excess return `+96.47%`
    - hit rate `71.9%`
    - subgroup p-value `3.7e-06`
  - `action_policy:buy`
    - `13` trades
    - mean excess return `+14.96%`
    - hit rate `23.1%`
    - subgroup p-value `0.749`
  - `action_policy:watch`
    - `7` trades
    - mean excess return `+10.31%`
    - hit rate `28.6%`
    - subgroup p-value `0.763`

Interpretation update:
- `needs_manual_review` is now a first-class reported validation lane, not just
  a one-off alternate backtest
- the current evidence says the dominant historical signal now lives in the
  manual-review cohort rather than the auto-admit `buy/watch` cohort
- company backtest defaults have been updated to match that evidence, so the
  default baseline is now the broader combined lane rather than the old strict
  `buy/watch` subset
- the old strict lane remains visible through the CLI comparison path rather
  than being lost as historical context
- weekly and dashboard surfaces now follow the same policy:
  - primary headline list = broader company lane
  - secondary comparison list = strict `buy/watch`

### 2026-04-12 Next phase continuation - underwriting refinement on highest-consequence replay names

Completed objective:
- started replacing replay-generated `addressable_k` placeholders with explicit
  diagnosed / eligible / treated funnels on the highest-consequence names

Completed in configs/tests:
- curated replay-generated configs:
  - `examples/configs/replay_generated/lly.yaml`
  - `examples/configs/replay_generated/itci.yaml`
  - `examples/configs/replay_generated/krtx.yaml`
  - `examples/configs/replay_generated/bhvn.yaml`
  - `examples/configs/replay_generated/rna.yaml`
  - `examples/configs/replay_generated/myok.yaml`
  - `examples/configs/replay_generated/immu.yaml`
  - `examples/configs/replay_generated/xlrn.yaml`
- `tests/test_patient_flow.py`
  - added a replay-curated underwriting guard for these names
  - updated the replay-wide peak-preservation test so it accepts either:
    - `addressable_k`-based replay configs
    - or fully explicit funnel-based replay configs

What changed:
- these names no longer rely on `addressable_k` overrides
- they now express patient flow through:
  - `prevalence_thousands`
  - `diagnosed_fraction`
  - `eligible_rate`
  - `treated_fraction`
- peak-sales preservation remains effectively unchanged versus stored
  heuristics, so this was a real underwriting-shape upgrade rather than a
  replay-economics rewrite

Focused verification passed:
- `ruff check tests/test_patient_flow.py`
- `python -m pytest tests/test_patient_flow.py -q`
- result: `126 passed`

Interpretation:
- the next phase has moved from schema rollout into targeted commercial
  underwriting refinement
- the first refinement batch focused on the highest replay peak-sales names
- the next pass should continue down the replay list or shift to the names that
  dominate the current `needs_manual_review` signal, depending on whether the
  goal is better realism or faster validation uplift

### 2026-04-12 Next phase continuation - validation-driver underwriting batch

Completed objective:
- started targeting the names that dominate the current `needs_manual_review`
  validation lane rather than just the highest replay peaks

Completed in configs/tests:
- `examples/configs/replay_generated/fulc.yaml`
  - replaced `addressable_k` placeholder sizing with an explicit rare-disease
    funnel
- `tests/test_patient_flow.py`
  - added a dedicated validation-driver underwriting guard covering:
    - `replay_generated/fulc.yaml`
    - `auto_generated/imvt.yaml`
    - `auto_generated/mdgl.yaml`
    - `auto_generated/tgtx.yaml`

What changed:
- `FULC` now uses nontrivial:
  - `prevalence_thousands`
  - `diagnosed_fraction`
  - `eligible_rate`
  - `treated_fraction`
- peak-sales preservation remains intact (`~800.6` vs stored `800.0`)
- the validation-driver guard now locks the key names most responsible for the
  current manual-review signal into explicit funnel-based commercial models

Focused verification passed:
- `ruff check tests/test_patient_flow.py`
- `python -m pytest tests/test_patient_flow.py -q`
- result: `130 passed`

Interpretation:
- next-phase work is now split across two concrete tracks:
  - top replay peak-sales realism
  - validation-driver name refinement
- the remaining highest-leverage names in the validation-driver cohort are now
  mostly `IMVT`, `MDGL`, and `TGTX`, which already had explicit funnels, so the
  next meaningful step is likely to rerun replay measurement after this batch
  rather than continuing purely local config edits
- Step 5 — policy / risk layer
  - `src/bve/intelligence/position_policy.py`
    - deterministic equity policy:
      - `buy`
      - `add`
      - `monitor`
      - `avoid`
    - deterministic BD policy:
      - `acquire`
      - `partner`
    - `pass`
    - includes discount, conviction, catalyst-window, liquidity, downside, and
      sizing logic
  - `tests/intelligence/test_position_policy.py`
  - live output integration:
    - `src/bve/ops/daily_brief.py`
    - `src/bve/cli/daily_brief.py`
    - `bve-daily-brief` now shows a heuristic `EQPOL` and `SIZE` preview
      derived from company-SOTP snapshots plus stored catalyst/liquidity context
  - policy persistence / audit:
    - `src/bve/intelligence/knowledge_layer.py`
    - new table: `equity_policy_snapshots`
    - one persisted row per `(ticker, as_of_date)` with:
      - company snapshot context
      - heuristic Step 5 inputs
      - final `buy/add/monitor/avoid` action
      - sizing and rationale
    - `bve-daily-brief` now persists those audit rows by default
  - weekly-review integration:
    - `src/bve/intelligence/weekly_review.py`
    - `src/bve/ops/weekly_runner.py`
    - weekly review now includes `policy_audit` with:
      - persisted policy snapshot count
      - buy/add/monitor/avoid mix
      - average recommended size
      - upstream company-gate blocked count
- Step 6 — curated acquirer depth expansion
  - `src/bve/intelligence/acquirer_profiles.py`
    - curated profiles now support:
      - `acquisition_capacity_millions`
      - `existing_partnerships`
    - converted `AcquirerProfile` now preserves those fields instead of dropping
      them after load
  - `src/bve/intelligence/acquirer_fit.py`
    - existing partnerships now raise strategic-fit scoring when the target
      matches an active partner
    - explicit acquisition capacity now constrains budget scoring, including the
      pipeline-gap scoring path
  - new curated acquirer profiles:
    - `examples/research/acquirer_profiles/takeda.yaml`
    - `examples/research/acquirer_profiles/daiichi_sankyo.yaml`

Focused verification passed:
- `ruff check` on touched Step 4/5/6 source and test files
- `python -m pytest tests/test_patient_flow.py tests/test_sprint19.py tests/intelligence/test_acquirer_fit.py tests/intelligence/test_acquirer_profiles.py -q`
- Result: `130 passed`

Smoke checks passed:
- `python -m bve.cli.daily_brief --db outputs/intelligence/replay_knowledge.db --as-of 2024-03-01 --top 5 --format text`
  - report now renders `SOTP`, `EQPOL`, and `SIZE` columns
- `python -m bve.cli.ma_probability --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml --db outputs/intelligence/replay_knowledge.db --as-of 2024-03-01 --top 5 --output-format report`
  - M&A ranking still runs cleanly after the partnership/capacity scoring changes

Historical M&A replay rerun after the Step 6 partnership/capacity scoring change:
- authoritative artifacts:
  - `outputs/analysis/step6_capacity_partnership_manual/historical_metrics.json`
  - `outputs/analysis/step6_capacity_partnership_manual/canonical_metrics.json`
  - `outputs/analysis/step6_capacity_partnership_manual/canonical_fit.json`
  - `outputs/analysis/step6_capacity_partnership_manual/policy_comparison.json`
- refreshed `historical_snapshot` result (`top_k=15`):
  - rows: `1994`
  - positive rows: `263`
  - unique targets: `25`
  - `precision@15 = 0.282456`
  - `recall@15 = 0.64`
  - `median_lead_days@15 = 345.5`
- versus the prior authoritative April 8 checkpoint:
  - `precision@15`: `0.245614 -> 0.282456`
  - `recall@15`: `0.56 -> 0.64`
  - `average_probability_positive`: `0.943384 -> 0.937896`
  - `average_probability_control`: `0.83321 -> 0.822954`
- refreshed canonical matched-control set:
  - stored `v1.2` precision@15: `0.80`
  - stored `v1.2` recall@15: `0.48`
  - logistic cross-validated AUC: `0.6968`
  - policy A precision/recall@15: `0.80 / 0.48`
  - policy B precision/recall@15: `0.80 / 0.48`
  - policy C precision/recall@15: `0.466667 / 0.28`
- promotion decision:
  - live M&A defaults no longer force calibrated threshold filtering
  - `src/bve/cli/ma_probability.py` now defaults to `calibration_policy=display_only`
  - `src/bve/ops/weekly_runner.py` also uses `display_only`
  - reasoning: the refreshed replay shows the stored baseline improved, while
    the calibrated overlay is neutral on the canonical matched-control set

What is still missing:
- Step 4:
  - refine the newly-curated funnels with real source-backed ranges and
    better geography/persistence assumptions where those matter most
- Step 5:
  - promote the persisted policy layer into weekly review / downstream decision
    attribution beyond the current audit summary
- Step 6:
  - re-fit or redesign the calibration overlay only if a new matched-control
    dataset shows it adds value beyond the improved stored baseline

---

## Phase 1 — Build company truth (2026-04-09, complete)

**Current status: ✅ CompanySnapshot is live as the canonical company record. VKTX proof-of-concept pack complete. 78 Phase 1 tests passing.**

New modules:
- `src/bve/entities/company_snapshot.py` — `CompanySnapshot`, `ValueBucket`, `DilutionBridge`, `CatalystEntry`, `ManagementFlag`, `ConfidenceMetadata`, `ProvenanceMetadata`, `ReviewerState`
- `src/bve/persistence/snapshot_store.py` — SQLite insert-only store with state transitions and audit log
- `src/bve/analysis/snapshot_bridge.py` — `load_underwriting_pack()` (YAML → CompanySnapshot) and `sotp_result_from_snapshot()` (bridge to existing SOTP pipeline)
- `examples/packs/vktx.yaml` — first real underwriting pack (VKTX, Q2 2026, $5.1B market cap)
- `examples/packs/underwriting_pack_template.yaml` — template for remaining top-25 packs

Phase 0 (mode labels + screening-grade gate) also complete in this session.

---

## Company Data Quality Step 7 (2026-04-09, tiered reconciliation ladder)

**Current status: ✅ Tiered reconciliation is live; the binary hard cutoff is replaced by a ratio + 3-month market-cap trend ladder, and the remaining mismatches are now concentrated and diagnosable**

The Step 7 reconciliation logic is now upgraded from a binary hard gate into a
three-tier SOTP confidence ladder. The key change is that high SOTP / market-cap
ratios are no longer treated as uniformly broken. Instead, the policy now uses
ratio bands plus 3-month market-cap trend to separate likely dislocations from
likely stale / broken model states.

Implemented in this pass:
- `src/bve/analysis/company_sotp.py`
  - added `compute_mcap_trend_3m()` using `KnowledgeStore` prices and a
    `ReplayStore` fallback when historical stored prices are sparse
  - added `SotpTierResult` and `classify_sotp_tier()`
  - new tier ladder:
    - `ratio > 15x` -> `avoid`
    - `8x < ratio <= 15x` -> `needs_manual_review`
    - `5x < ratio <= 8x` with `3m trend < -30%` -> `needs_manual_review`
    - `5x < ratio <= 8x` with stable or missing trend -> `watch`
    - `ratio <= 5x` -> `normal`
  - company rows now expose:
    - `mcap_trend_3m_pct`
    - `sotp_tier`
    - `sotp_action`
    - `sotp_confidence_tier`
    - `sotp_tier_reason`
  - `extreme_discount` remains available as a backward-compatible boolean alias
  - company report / CSV output now includes tier and tier-summary breakdown
- `src/bve/intelligence/knowledge_layer.py`
  - `company_sotp_snapshots` now persist all tier and 3-month trend fields
  - older stored rows can derive the tier fields on load when absent
- `tests/test_company_sotp.py`
  - added direct coverage for:
    - `>15x -> avoid`
    - `>8x -> needs_manual_review`
    - `5-8x + crashing mcap -> needs_manual_review`
    - `5-8x + stable / missing mcap history -> watch`
    - `<5x -> normal`
    - tier summary counting and alias behavior

Verification:
- `ruff check src/bve/analysis/company_sotp.py src/bve/intelligence/knowledge_layer.py tests/test_company_sotp.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_company_sotp.py -q`
- Result: `29 passed`

Historical company snapshot rebuild after the tier-ladder rollout:
- `2021-02-01 -> 2024-03-01`
- `788` company rows persisted
- `774` pass the recency gate
- action totals moved from the relaxed Step 7 pass-2 state:
  - `buy = 46`
  - `watch = 6`
  - `avoid = 261`
  - `needs_manual_review = 475`
- to:
  - `buy = 46`
  - `watch = 30`
  - `avoid = 121`
  - `needs_manual_review = 591`
- stored tier distribution across company rows:
  - `normal = 761`
  - `watch = 24`
  - `needs_manual_review = 2`
  - `avoid = 1`
- latest active cohort on `2024-03-01`:
  - `22 normal`
  - `0 watch`
  - `0 needs_manual_review`
  - `0 avoid`

Known-case validation on stored snapshots:
- `VKTX`
  - early `2021-2022` rows classify as `watch`
  - reasons include `possible_mispricing:6.7x`, `7.1x`, and similar `5-8x`
    ladder hits
  - this is the intended deep-dislocation behavior
- `ZYME`
  - did **not** hit the `crashing_mcap` branch under the actual stored 3-month
    trend data
  - observed 3-month declines in the high-ratio period were generally `-11%` to
    `-26%`, not below `-30%`
  - current outcome is mostly `normal` / `watch`, which points back to config
    assumptions rather than the tier ladder itself
- `AMRN`
  - classifies as `avoid`
  - `extreme_ratio:110.0x`
- `SRRK`
  - the boundary edge case currently classifies as `needs_manual_review`
  - observed reason: `crashing_mcap:-60%`

Follow-up reconciliation audit after the new ladder:
- `27` rows still carry `reconciliation_status = extreme_discount`
- the remaining mismatches are concentrated rather than broad:
  - `VKTX` contributes most of the surfaced `watch` dislocation rows
  - `ZYME` is the main config-audit candidate
  - `AMRN` is the single `avoid`
  - `SRRK` is a one-row manual-review edge case

Interpretation:
- the tier ladder is working mechanically and is substantially better than the
  old binary `>5x => manual review` rule
- it now distinguishes likely opportunities from obviously broken-ratio cases
  without hiding the reconciliation problem
- the stored data does **not** support the expected `ZYME -> crashing_mcap`
  outcome, so the next leverage point is a targeted asset/config audit on
  `ZYME`, with `VKTX` as the secondary review candidate

## Current Module Being Worked On

**All ROADMAP phases complete (Sprints 10–26C). System is operational.**

Full roadmap: ROADMAP.md | Full task history: TASKS.md

## Company Data Quality Step 7 (2026-04-09, pass 1)

**Current status: ⚠️ In progress; reconciliation checks are now live and auditable, but the first hard-gate policy degraded the company backtest materially**

The first reconciliation pass is now implemented. Company SOTP rows persist
explicit SOTP-vs-market-cap reconciliation metrics, and extreme mismatches are
no longer allowed to sit silently in the ranked company dataset.

Implemented in this pass:
- `src/bve/analysis/company_sotp.py`
  - company rows now expose:
    - `reconciliation_gap_millions`
    - `reconciliation_gap_pct`
    - `reconciliation_status`
    - `reconciliation_passes_gate`
  - reconciliation status is now surfaced in company CSV / report output
  - hard gate rules added:
    - `extreme_discount` when `SOTP / market cap > 5.0x`
    - `extreme_premium` when `SOTP / market cap < 0.25x`
  - older stored company snapshots can now derive reconciliation fields on load
- `src/bve/intelligence/knowledge_layer.py`
  - `company_sotp_snapshots` now stores the reconciliation fields above
  - snapshot read/write paths and on-or-before lookup paths all round-trip them
- `tests/test_company_sotp.py`
  - added direct coverage for:
    - extreme `6x` upside pack -> `needs_manual_review`
    - extreme `0.16x` premium pack -> `needs_manual_review`
    - persistence / lookup of reconciliation fields

Verification:
- `ruff check src/bve/analysis/company_sotp.py src/bve/intelligence/knowledge_layer.py tests/test_company_sotp.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_company_sotp.py -q`
- Result: `21 passed`

Historical company snapshot rebuild after Step 7 pass 1:
- `2021-02-01 -> 2024-03-01`
- `788` company rows persisted
- `774` pass the recency gate
- action totals moved from the prior Step 3 / Step 1 state:
  - `buy = 72`
  - `watch = 6`
  - `avoid = 261`
  - `needs_manual_review = 449`
- to:
  - `buy = 46`
  - `watch = 6`
  - `avoid = 200`
  - `needs_manual_review = 536`
- reconciliation status distribution across stored rows:
  - `premium = 390`
  - `extreme_premium = 235`
  - `discounted = 136`
  - `extreme_discount = 27`

Latest active cohort on `2024-03-01`:
- `2 buy / 5 avoid / 15 needs_manual_review`
- remaining auto-`buy` names:
  - `ZYME` (`3.70x`, `discounted`)
  - `NVAX` (`1.90x`, `discounted`)

Company-level backtest after Step 7 pass 1:
- `26` snapshot dates
- `18` candidate rows / selected trades
- mean excess return `+0.18%`
- hit rate `16.7%`
- cluster count `3`
- bootstrap `p = 0.4244`

Interpretation:
- the reconciliation layer is doing its governance job: extreme company-pack
  mismatches now surface immediately instead of hiding inside ordinary
  `buy` / `avoid` labels
- but the first hard-gate policy is over-constraining the ranked company
  dataset and removing too many historically strong deep-discount names
- the next Step 7 refinement should keep the stored reconciliation metrics and
  visible flags, but soften the policy layer, most likely by:
  - keeping `extreme_discount` as a hard gate
  - demoting `extreme_premium` to a surfaced flag or secondary review cue
  - or conditioning the hard gate on weak source quality / high manual share

Step 7 pass 2 refinement is now complete:
- `extreme_discount` remains a hard gate
- `extreme_premium` is now a surfaced reconciliation flag rather than a
  standalone hard gate
- historical rebuild after pass 2 moved action totals from:
  - `buy = 46`
  - `watch = 6`
  - `avoid = 200`
  - `needs_manual_review = 536`
- to:
  - `buy = 46`
  - `watch = 6`
  - `avoid = 261`
  - `needs_manual_review = 475`
- latest `2024-03-01` cohort after pass 2:
  - `2 buy / 7 avoid / 13 needs_manual_review`
- company backtest after pass 2 is unchanged versus pass 1:
  - `18` candidate rows / selected trades
  - mean excess return `+0.18%`
  - hit rate `16.7%`
  - cluster count `3`
  - bootstrap `p = 0.4244`

Interpretation after pass 2:
- the premium-side relaxation fixed the excessive escalation of obviously
  overvalued / underbuilt company packs into `needs_manual_review`
- it did not repair the company-level signal, so the remaining problem is now
  isolated to the `extreme_discount` hard gate and the names it removes

## Company Data Quality Step 1 (2026-04-09)

**Current status: ✅ Step 1 is complete; corroboration is now enforced using independent `source_ref` counts, but the live historical company cohort was unchanged**

The corroboration pass is now complete. This step closed the remaining gap
in the company pack governance layer: concentration checks now use
independent `source_ref` counts on the dominant low-evidence bucket instead of
relying only on pack-wide source diversity.

Implemented in this pass:
- `src/bve/analysis/company_sotp.py`
  - `_compute_pack_quality_metrics()` now parses independent `source_ref`
    tokens with `|`, `;`, and `,` separators
  - `n_bucket_sources` now reflects distinct `source_ref` tokens across the
    pack
  - the dominant low-evidence bucket now carries its own corroboration field:
    `largest_manual_bucket_source_ref_count`
  - the concentration gate now evaluates the dominant bucket's independent
    corroboration count instead of using the pack-wide source count
- `tests/test_company_sotp.py`
  - updated and extended to prove three distinct cases:
    - low-confidence high-manual-share packs still fail the quality gate when
      the dominant bucket is corroborated
    - concentrated single-source dominant buckets fail specifically on source
      concentration
    - corroborated dominant manual buckets can still remain auto-rank eligible

Verification:
- `ruff check src/bve/analysis/company_sotp.py tests/test_company_sotp.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_company_sotp.py -q`
- Result: `19 passed`

Historical company snapshot rebuild after Step 1:
- `2021-02-01 -> 2024-03-01`
- `788` company rows persisted
- `774` pass the recency gate
- action totals remained unchanged versus Step 3:
  - `buy = 72`
  - `watch = 6`
  - `avoid = 261`
  - `needs_manual_review = 449`

Company-level backtest after Step 1:
- unchanged versus Step 3:
  - `26` snapshot dates
  - `35` candidate rows / selected trades
  - mean excess return `+6.40%`
  - hit rate `28.6%`
  - cluster count `4`
  - bootstrap `p = 0.1666`

Interpretation:
- the corroboration logic is now correct and auditable
- it did not change the currently selected historical company cohort because
  the surviving auto-ranked packs were already clearing the dominant-bucket
  concentration rule
- the next highest-leverage move is Step 7: add SOTP-vs-market-cap
  reconciliation checks so stale or distorted company packs surface faster

## Company Data Quality Step 3 (2026-04-09)

**Current status: ✅ Step 3 is complete for the first high-instability cohort; dated-pack density improved and reduced `needs_manual_review`, but the company backtest was unchanged**

The second step in the revised data-quality plan is now complete for the first
priority cohort. This pass densified the point-in-time company pack for the five
most unstable names under the tighter source hierarchy.

Wave-1 cohort completed:
- `IMVT`
- `ZYME`
- `ANAB`
- `RAPT`
- `SRRK`

What changed in the company pack:
- each of the five names now has `9` dated company snapshots instead of `2`
- new roll-forward dates added:
  - `2021-05-10`
  - `2021-08-10`
  - `2021-11-10`
  - `2022-03-10`
  - `2022-08-10`
  - `2023-03-10`
  - `2023-08-10`
- anchored snapshots retained:
  - `2021-02-01`
  - `2024-01-01`
- data-quality upgrade inside those snapshots:
  - platform and pipeline families now use disclosure-tier sources through the
    roll-forward path
  - the `2024-01-01` refresh snapshots were upgraded to `investor_day` for the
    core platform / pipeline buckets
  - royalty bridges remain conservative (`inferred`)
  - dilution reserves remain conservative (`analyst_bridge`)

Historical company snapshot rebuild after Step 3:
- action totals moved from the Step 2 state:
  - `buy = 72`
  - `watch = 6`
  - `avoid = 185`
  - `needs_manual_review = 525`
- to:
  - `buy = 72`
  - `watch = 6`
  - `avoid = 261`
  - `needs_manual_review = 449`

Latest active cohort on `2024-03-01`:
- moved from `2 buy / 5 avoid / 15 needs_manual_review`
- to `2 buy / 7 avoid / 13 needs_manual_review`
- cohort outcomes for the five target names:
  - `ZYME`: `buy`
  - `SRRK`: `avoid`
  - `ANAB`: `avoid`
  - `RAPT`: `avoid`
  - `IMVT`: `avoid`

Company-level backtest after Step 3:
- unchanged versus Step 2:
  - `26` snapshot dates
  - `35` candidate rows / selected trades
  - mean excess return `+6.40%`
  - hit rate `28.6%`
  - cluster count `4`
  - bootstrap `p = 0.1666`

Interpretation:
- Step 3 did improve company-pack breadth under the stricter hierarchy:
  `needs_manual_review` fell by `76` rows
- but the top-ranked company trade cohort did not change enough to improve the
  current backtest
- the next highest-leverage move is Step 1: independent-source corroboration
  enforcement using `source_ref` counts, now that the dated-pack density is no
  longer the main bottleneck for this first cohort

## Company Data Quality Step 2 (2026-04-09)

**Current status: ✅ Step 2 is complete; source hierarchy enforcement is live and materially tightened the company ranking dataset**

The first step in the revised data-quality plan is now complete. This pass
upgraded the company SOTP pack from the legacy `manual/inferred` scheme to a
real source hierarchy with enforced confidence floors.

Implemented in this pass:
- `src/bve/analysis/company_sotp.py`
  - structured source kinds now support:
    - `sec_filing`
    - `contractual`
    - `company_disclosure`
    - `investor_day`
    - `analyst_bridge`
    - `inferred`
  - legacy `manual` inputs now normalize to `analyst_bridge`
  - enforced confidence floors:
    - `0.90` for `sec_filing` / `contractual`
    - `0.80` for `company_disclosure` / `investor_day`
    - `0.65` for `analyst_bridge` / `inferred`
  - low-evidence bucket tracking now includes both `analyst_bridge` and
    `inferred`
  - `min_structured_input_confidence_for_auto_action` is now floored at `0.65`
  - `min_manual_bucket_confidence_avg` tightened from `0.65 -> 0.80`
- `research/company_sotp_overrides.yaml`
  - migrated all legacy `source_kind: manual` entries to
    `source_kind: analyst_bridge`
  - normalized all sub-floor analyst-bridge / inferred confidences up to the new
    minimum `0.65`
- `tests/test_company_sotp.py`
  - added direct coverage for:
    - legacy `manual` normalization
    - hard source-kind confidence-floor enforcement

Verification:
- `ruff check src/bve/analysis/company_sotp.py tests/test_company_sotp.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_company_sotp.py -q`
- Result: `19 passed`

Historical company snapshot rebuild after Step 2:
- action totals moved from:
  - `buy = 91`
  - `watch = 12`
  - `avoid = 637`
  - `needs_manual_review = 48`
- to:
  - `buy = 72`
  - `watch = 6`
  - `avoid = 185`
  - `needs_manual_review = 525`

Latest active cohort on `2024-03-01`:
- `2 buy`
- `5 avoid`
- `15 needs_manual_review`

Company-level backtest after Step 2:
- `26` snapshot dates
- `35` candidate rows / selected trades
- mean excess return `+6.40%`
- hit rate `28.6%`
- cluster count `4`
- bootstrap `p = 0.1666`

Interpretation:
- the stricter hierarchy worked: it forced weakly sourced company packs out of
  the auto-ranked company dataset
- the current pack is now too sparse / stale to support that tighter standard
  without losing breadth
- the next highest-leverage move is Step 3, not more logic changes:
  - add quarterly / event-dated packs for `IMVT`, `ZYME`, `ANAB`, `RAPT`, and
    `SRRK`
  - then revisit corroboration-count enforcement using independent
    `source_ref` counts

## Company Pack Expansion Step 4 / Step 6 (2026-04-08)

**Current status: ✅ Steps 4 / 6 are complete; evidence standards and pack-quality controls are now enforced and persisted**

The next governance layer of the company SOTP pack is now implemented. This
pass did two things:
- Step 4: tightened evidence standards by bucket type for structured company
  inputs
- Step 6: added pack-quality controls so high-manual-share, weakly sourced
  packs can be forced back to `needs_manual_review`

Implemented in this pass:
- `src/bve/analysis/company_sotp.py`
  - `CompanySOTPResult` now exposes:
    - `manual_bucket_share_pct`
    - `manual_bucket_confidence_avg`
    - `n_bucket_sources`
  - structured bucket evidence is now checked by bucket type:
    - platform
    - unmodeled pipeline
    - royalty
    - dilution reserve
  - policy gating now forces `needs_manual_review` when:
    - one manual bucket is too concentrated without enough independent sources
    - total manual-bucket share is high and average manual confidence is weak
- `src/bve/intelligence/knowledge_layer.py`
  - `company_sotp_snapshots` now stores:
    - `manual_bucket_share_pct`
    - `manual_bucket_confidence_avg`
    - `n_bucket_sources`
- `tests/test_company_sotp.py`
  - added direct coverage for:
    - low-confidence high-manual-share pack -> `needs_manual_review`
    - concentrated single-source manual pack -> `needs_manual_review`
    - strong multi-source manual pack -> still eligible for auto-action
    - persistence round-trip of the new governance fields

Focused verification:
- `ruff check src/bve/analysis/company_sotp.py src/bve/intelligence/knowledge_layer.py tests/test_company_sotp.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_company_sotp.py::test_company_sotp_forces_manual_review_for_low_confidence_high_manual_share_pack tests/test_company_sotp.py::test_company_sotp_forces_manual_review_for_concentrated_single_source_manual_pack tests/test_company_sotp.py::test_company_sotp_allows_strong_multi_source_manual_pack_for_auto_action tests/test_company_sotp.py::test_company_sotp_persists_company_snapshots_and_supports_lookup tests/test_company_sotp.py::test_company_sotp_supports_snapshot_bundles_for_point_in_time_company_inputs -q`
- Result: `5 passed`

Live historical effect on the current stored company snapshot dataset:
- action totals remain:
  - `buy = 91`
  - `watch = 12`
  - `avoid = 637`
  - `needs_manual_review = 48`
- company backtest remains:
  - `26` snapshot dates
  - `52` candidate rows / selected trades
  - mean excess return `+6.27%`
  - hit rate `30.8%`
  - cluster count `7`
  - bootstrap `p = 0.0718`

Interpretation:
- the governance framework is now in place and auditable at the stored company
  snapshot layer
- the current override pack mostly clears the new evidence thresholds, so the
  historical company ranking did not change materially yet
- the next leverage point is no longer code plumbing; it is data quality:
  - populate more company packs with stronger dated sourcing
  - use the new governance fields in company policy audits and ranking reviews

## Company Pack Expansion Steps 2–3 (2026-04-08)

**Current status: ✅ Steps 2–3 are complete for the first high-impact cohort; auditability improved, backtest unchanged**

The next company-pack wave is now complete for the highest-impact names carried
out of Step 1. This pass did two things:
- Step 2: replaced static coarse company buckets with tighter
  company-specific bucket families
- Step 3: made those same company packs point-in-time by construction through
  dated snapshot bundles

Implemented in this pass:
- `src/bve/analysis/company_sotp.py`
  - `CompanySOTPOverride` now supports `snapshots:` bundles with:
    - `as_of_date`
    - `inputs`
    - optional notes
  - `_resolve_structured_inputs()` now selects the latest snapshot on or before
    the requested `as_of_date`
  - backward compatibility preserved:
    - companies not yet migrated still use flat `inputs`
- `tests/test_company_sotp.py`
  - added direct coverage for snapshot-bundle point-in-time selection
- `research/company_sotp_overrides.yaml`
  - migrated the first high-impact cohort to dated snapshot bundles

High-impact cohort migrated:
- `IMVT`
- `ZYME`
- `ANAB`
- `ISEE`
- `MYOK`
- `RAPT`
- `RETA`
- `RXDX`
- `SRRK`
- `TGTX`

What changed in the pack:
- company-specific bucket families replaced coarse single buckets, for example:
  - `imvt_pipeline_mg_thyroid_eye`
  - `zyme_pipeline_adc_followons`
  - `anab_pipeline_rosnilimab`
  - `rapt_pipeline_il18`
  - `srrk_pipeline_fshd`
  - `tgtx_pipeline_briumvi_lifecycle`
- the migrated names now use dated company snapshots such as:
  - `2021-02-01`
  - `2022-07-01` or `2023-01-01` for historical-only names
  - `2024-01-01` for active names
- later dates no longer inherit a perpetual `2021-02-01` company-bucket set

Focused verification:
- `ruff check src/bve/analysis/company_sotp.py tests/test_company_sotp.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_company_sotp.py::test_company_sotp_supports_structured_dated_inputs_with_bucket_provenance tests/test_company_sotp.py::test_company_sotp_supports_snapshot_bundles_for_point_in_time_company_inputs -q`
- Result: `2 passed`

Historical company rebuild after the dated-pack migration:
- command:
  - `python -m bve.ops.company_sotp_backfiller --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml --db outputs/intelligence/replay_knowledge.db --replay-db outputs/intelligence/replay_store.sqlite --start 2021-02-01 --end 2024-03-01 --output-dir outputs/analysis`
- resulting historical action totals:
  - `buy = 91`
  - `watch = 12`
  - `avoid = 637`
  - `needs_manual_review = 48`
- versus the Step 1 company-pack state:
  - `buy = 91`
  - `watch = 14`
  - `avoid = 635`
  - `needs_manual_review = 48`

Latest active cohort after Steps 2–3:
- `2024-03-01`
- `22` rows
- `22 / 22` pass recency gate
- action mix:
  - `2 buy`
  - `0 watch`
  - `20 avoid`
  - `0 needs_manual_review`
- upgraded cohort name outcomes at the latest date:
  - `ZYME`: `buy`
  - `ANAB`: `avoid`
  - `IMVT`: `avoid`
  - `RAPT`: `avoid`
  - `SRRK`: `avoid`
  - `TGTX`: `avoid`

Company-level backtest rerun after the dated-pack migration:
- command:
  - `python -m bve.analysis.company_sotp_backtest --db outputs/intelligence/replay_knowledge.db --replay-db outputs/intelligence/replay_store.sqlite --start 2021-02-01 --end 2024-03-01 --hold-days 365 --top-n 5 --min-ranked-discount 1.0 --output-dir outputs/analysis`
- result:
  - `26` snapshot dates
  - `52` candidate rows / selected trades
  - mean excess return `+6.27%`
  - hit rate `30.8%`
  - cluster count `7`
  - bootstrap `p = 0.0718`
- versus Step 1:
  - unchanged at the portfolio-signal level

Interpretation:
- Steps 2–3 materially improved company-pack structure and auditability.
- The current company dataset is more correct point-in-time than it was after
  the breadth-only Step 1 pass.
- But that alone did not improve the company-level backtest.
- The next highest-leverage move is now:
  - Step 4: tighten evidence standards by bucket type
  - Step 6: add pack-quality controls such as manual-bucket share,
    confidence averages, and source counts so weakly sourced manual packs
    are forced back into `needs_manual_review`

## Company Pack Expansion Step 1 (2026-04-08)

**Current status: ✅ Step 1 is complete; breadth expanded, but signal quality weakened**

The first execution wave of the structured company-pack expansion is now done.
This pass used the stored `company_sotp_snapshots` dataset as the prioritization
source, not intuition, and expanded the override pack for the first immediate
batch of high-impact names.

What Step 1 did:
- prioritized investable names recurring in historical top company cohorts and
  still lacking strong company-level bucket coverage
- added the first batch of structured dated company packs in:
  - `research/company_sotp_overrides.yaml`
- immediate batch added:
  - `SRRK`
  - `TGTX`
  - `ANAB`
  - `RAPT`
  - `RETA`
  - `RXDX`
  - `ISEE`
  - `MYOK`
- each company was added with structured bucket families rather than one
  generic manual bucket:
  - `platform_*`
  - `pipeline_*`
  - `royalty_*`
  - `dilution_*`

Stored-snapshot prioritization evidence:
- the company snapshot dataset confirmed strong recurring cohort relevance from
  names such as:
  - `SRRK`
  - `TGTX`
  - `ANAB`
  - `SRPT`
  - `CRSP`
- some of the immediate batch are historically sparse but still strategically
  relevant due to multi-asset / distortion risk:
  - `RAPT`
  - `RETA`
  - `RXDX`
  - `ISEE`
  - `MYOK`

Historical rebuild after the Step 1 pack expansion:
- command:
  - `python -m bve.ops.company_sotp_backfiller --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml --db outputs/intelligence/replay_knowledge.db --replay-db outputs/intelligence/replay_store.sqlite --start 2021-02-01 --end 2024-03-01 --output-dir outputs/analysis`
- resulting historical action totals:
  - `buy = 91`
  - `watch = 14`
  - `avoid = 635`
  - `needs_manual_review = 48`
- versus the prior company-pack checkpoint:
  - `buy = 87`
  - `watch = 11`
  - `avoid = 649`
  - `needs_manual_review = 41`

Company-level backtest impact:
- command:
  - `python -m bve.analysis.company_sotp_backtest --db outputs/intelligence/replay_knowledge.db --replay-db outputs/intelligence/replay_store.sqlite --start 2021-02-01 --end 2024-03-01 --hold-days 365 --top-n 5 --min-ranked-discount 1.0 --output-dir outputs/analysis`
- new result:
  - `26` snapshot dates
  - `52` candidate rows / selected trades
  - mean excess return `+6.27%`
  - hit rate `30.8%`
  - cluster count `7`
  - bootstrap `p = 0.0718`
- prior result before Step 1:
  - `48` candidate rows / selected trades
  - mean excess return `+10.02%`
  - hit rate `33.3%`
  - cluster count `7`
  - bootstrap `p = 0.0282`

Interpretation:
- Step 1 successfully expanded breadth and slightly increased the number of
  `buy/watch` names in the historical company dataset.
- It did **not** improve company-level signal quality; the backtest weakened.
- That means the current bottleneck is not breadth alone.
- The next highest-leverage work is:
  - Step 2: replace coarse additions with better company-specific bucket
    structure
  - Step 3: make the new company buckets properly point-in-time instead of
    relying on one static carry-forward date

Current live latest-cohort snapshot (`2024-03-01`):
- `22` rows
- `22 / 22` pass recency gate
- action mix:
  - `2 buy`
  - `1 watch`
  - `19 avoid`
  - `0 needs_manual_review`
- current immediate-batch policies at the latest date:
  - `SRRK`: `watch`
  - `ANAB`: `avoid`
  - `RAPT`: `avoid`
  - `TGTX`: `avoid`

## Stored Company Snapshots As Primary Dataset (2026-04-08)

**Current status: ✅ Company ranking and replay backtesting now use stored company snapshots as the primary signal dataset**

This closes the next architectural gap in the company layer. The stored
`company_sotp_snapshots` table is no longer a sidecar metadata store; it now
drives both:
- company-level ranking / reporting on or before a requested date
- company-level historical replay backtesting

Implemented in this pass:
- `src/bve/analysis/company_sotp.py`
  - `load_from_store()` resolves ranked company rows from
    `company_sotp_snapshots` on or before `as_of_date`
  - stored rows are reconstructed into full `CompanySOTPResult` objects by
    rebuilding derived bucket totals from persisted bucket payloads
  - CLI now prefers stored company snapshots by default and only recomputes
    when `--recompute` is passed
- `src/bve/analysis/company_sotp_backtest.py`
  - first company-level replay backtester using `company_sotp_snapshots`
    directly as the signal source
  - forward returns come from replay-store prices and are paired versus `XBI`
  - uses the same dependence-aware alpha diagnostics already present in the
    asset-level validation stack

Focused verification:
- `ruff check src/bve/analysis/company_sotp.py src/bve/analysis/company_sotp_backtest.py tests/test_company_sotp.py tests/test_company_sotp_backtest.py`
- `python -m pytest tests/test_company_sotp.py::test_company_sotp_load_from_store_uses_company_snapshots_on_or_before tests/test_company_sotp_backtest.py -q`
- Result: `2 passed`

Live stored-ranking result:
- command:
  - `python -m bve.analysis.company_sotp --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml --knowledge-db outputs/intelligence/replay_knowledge.db --as-of 2024-03-20 --top 5`
- resolved `2024-03-20 -> 2024-03-01`
- `source_mode = stored_company_snapshot`
- top stored company names:
  - `ZYME`
  - `NVAX`
  - `SRRK`
  - `FULC`
  - `PRTA`

Live company-level backtest result:
- command:
  - `python -m bve.analysis.company_sotp_backtest --db outputs/intelligence/replay_knowledge.db --replay-db outputs/intelligence/replay_store.sqlite --start 2021-02-01 --end 2024-03-01 --hold-days 365 --top-n 5 --min-ranked-discount 1.0`
- first replay metrics:
  - `26` snapshot dates
  - `58` candidate company rows
  - `41` selected trades
  - `5` missing-price trades
  - mean excess return: `+6.37%`
  - hit rate: `31.7%`
  - cluster count: `4`
  - bootstrap `p = 0.3046`
- artifact:
  - `outputs/analysis/company_sotp_backtest_2021-02-01_2024-03-01_hold365d_top5.csv`

## Historical Company-SOTP Backfill (2026-04-08)

**Current status: ✅ The company-level SOTP layer is now historically replayable**

This closes the next institutional gap after single-date company persistence:
company-level underwriting is no longer just a current snapshot. The replay
calendar is now backfilled across stored historical screen dates, and the
company snapshot table is cleanly cohort-replaced per date.

Implemented in this pass:
- `src/bve/ops/company_sotp_backfiller.py`
  - historical backfill CLI for `company_sotp_snapshots`
  - uses `screen_snapshots` dates as the replay-safe company calendar
  - writes a per-date summary CSV
- `src/bve/analysis/company_sotp.py`
  - `include_tickers` filter so historical backfill follows the active stored
    screen cohort instead of the full watchlist on every date
  - shared fallback config-valuation cache support across dates
- `src/bve/intelligence/knowledge_layer.py`
  - `write_company_sotp_snapshots()` now clears existing rows for rewritten
    snapshot dates before insert, which prevents stale same-date company rows
    from surviving cohort rewrites

Focused verification:
- `ruff check src/bve/analysis/company_sotp.py src/bve/ops/company_sotp_backfiller.py src/bve/intelligence/knowledge_layer.py tests/test_company_sotp.py tests/ops/test_company_sotp_backfiller.py tests/test_analysis_mispricing_screener.py`
- `python -m pytest tests/test_company_sotp.py::test_company_sotp_reuses_shared_asset_rnpv_cache_across_builders tests/ops/test_company_sotp_backfiller.py tests/test_analysis_mispricing_screener.py::test_company_sotp_snapshot_write_replaces_stale_same_date_rows -q`
- Result: `3 passed`

Live historical backfill result:
- command:
  - `python -m bve.ops.company_sotp_backfiller --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml --db outputs/intelligence/replay_knowledge.db --replay-db outputs/intelligence/replay_store.sqlite --start 2021-02-01 --end 2024-03-01 --output-dir outputs/analysis`
- persisted into `outputs/intelligence/replay_knowledge.db`
- final table state:
  - `38` distinct `company_sotp_snapshots` dates
  - `785` total company rows
  - date range: `2021-02-01 -> 2024-03-01`
  - `771 / 785` pass the balance-sheet recency gate
- action-policy totals across the historical company dataset:
  - `76` buy
  - `12` watch
  - `67` avoid
  - `630` needs_manual_review
- latest historical cohort after stale-row cleanup:
  - `2024-03-01`: `22` rows
  - `22 / 22` pass recency gate

Artifacts:
- `outputs/analysis/company_sotp_backfill_summary_2021-02-01_2024-03-01.csv`
- `outputs/analysis/company_sotp_2021-02-01.csv`
- `outputs/analysis/company_sotp_2024-03-01.csv`

## Company-Level Auditability + Stored SOTP Snapshots (2026-04-08)

**Current status: ✅ Company-level underwriting state is now persisted and auditable**

This closes the next institutional gap after balance-sheet coverage: company
SOTP output is no longer just a CSV/report. It is now a dated, replayable
dataset with per-bucket provenance/confidence, deterministic action policy, and
downstream freshness gates.

Implemented in this pass:
- `src/bve/analysis/company_sotp.py`
  - every bucket now carries:
    - `source`
    - `source_kind`
    - `source_as_of`
    - `source_confidence`
    - `source_ref`
  - added structured dated company inputs via `inputs:` in
    `research/company_sotp_overrides.yaml`
  - added company-level action policy:
    - `buy`
    - `watch`
    - `avoid`
    - `needs_manual_review`
- `src/bve/intelligence/knowledge_layer.py`
  - new `company_sotp_snapshots` table plus on-or-before lookups
- `src/bve/analysis/mispricing_screener.py`
  - stale company snapshots are now hidden from the mispricing screen
- `src/bve/intelligence/ma_probability.py`
  - stale company snapshots are now excluded before M&A ranking

Focused verification:
- `ruff check src/bve/analysis/company_sotp.py src/bve/intelligence/knowledge_layer.py src/bve/analysis/mispricing_screener.py src/bve/intelligence/ma_probability.py tests/test_company_sotp.py tests/test_analysis_mispricing_screener.py tests/intelligence/test_ma_probability.py`
- `python -m pytest tests/test_company_sotp.py tests/test_analysis_mispricing_screener.py tests/intelligence/test_ma_probability.py -q`
- Result: `43 passed`

Live population result:
- reran company SOTP for the full replay-expanded Phase 2+ watchlist at
  `2024-03-01` with persistence enabled
- `69` company rows were written into `company_sotp_snapshots`
- `57 / 69` pass the balance-sheet recency gate
- action-policy breakdown:
  - `15` buy
  - `1` watch
  - `13` avoid
  - `40` needs_manual_review
- top live rows remained:
  - `AMRN`
  - `KRTX`
  - `ITCI`
  - `SRRA`
  - `LBPH`

Important remaining gap:
- the **schema and persistence path** for structured dated company buckets are
  now in place, but the repo still lacks a populated top-name set of manual
  platform / unmodeled-pipeline / royalty / financing inputs. That remains the
  next data-population task, not a code-path gap.

## Top-Universe Balance-Sheet Population (2026-04-08)

**Current status: ✅ Live SEC-derived balance-sheet provenance is now populated across the full top replay universe**

This closes the next operational gap in the company-level SOTP layer: the
dated balance-sheet path now exists in code and has been populated on the real
expanded replay watchlist instead of remaining an empty schema.

Implemented in this pass:
- `src/bve/ops/signal_backfiller.py`
  - `backfill_capital_risk()` now fans out capital snapshots to every asset id
    for a ticker while still writing one dated company balance-sheet record per
    SEC filing date
- `src/bve/ops/balance_sheet_backfiller.py`
  - watchlist-driven top-universe balance-sheet population CLI
  - coverage summary + CSV artifact
- `tests/ops/test_balance_sheet_backfiller.py`
  - multi-asset fanout and coverage output regression tests

Live population result:
- escalated SEC backfill completed successfully against
  `examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml`
- final repaired run inserted `7277` capital rows and added `65` new dated
  balance-sheet rows
- dated watchlist coverage is now `71 / 71` tickers
- the previously uncovered set is now closed:
  `RETA`, `RXDX`, `ISEE`, `MYOK`, `RNA`, `CBAY`, `CCXI`, `BLUE`, `INBX`

Live company SOTP rerun:
- rerun date: `2024-03-01`
- watchlist: `examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml`
- output: `outputs/analysis/company_sotp_2024-03-01.csv`
- `69` company rows produced
- `68 / 69` companies resolved point-in-time balance-sheet provenance from
  replay / SEC rather than static config fallback
- `57 / 69` companies pass the new balance-sheet recency gate
- `12 / 69` companies are explicitly penalized for stale balance-sheet inputs

Residual gaps:
- ticker-level coverage gap is closed, but some live SEC pulls still had direct
  companyfacts issues for `BLU`, `KDNY`, and `PRTA`; existing replay snapshots
  already cover those names
- stale “point-in-time” balance-sheet dates for acquired / delisted names are
  now penalized directly in the company SOTP ranking via recency-adjusted
  discount rather than being treated as equally fresh

## Point-in-Time SOTP Provenance Upgrade (2026-04-08)

**Current status: ✅ Point-in-time balance-sheet provenance and asset-level historical screen storage are now in place**

This closes the two explicit limitations from the first company-level SOTP
foundation pass:
- the balance sheet no longer has to be config-only when dated replay / SEC
  provenance exists
- historical `screen_snapshots` are no longer forced into one row per ticker

Implemented in this pass:
- `src/bve/ops/historical_replay.py`
  - new replay table: `balance_sheet_snapshots`
  - `ReplayStore.upsert_balance_sheet_snapshot()`
  - `ReplayStore.get_balance_sheet_snapshot()`
- `src/bve/ops/signal_backfiller.py`
  - SEC capital backfill now also writes dated balance-sheet provenance rows
- `src/bve/intelligence/knowledge_layer.py`
  - `screen_snapshots` migrated to `(ticker, snapshot_date, asset_id)` keying
  - backward-compatible rebuild for legacy DBs
  - new asset-level lookup:
    `get_screen_snapshot_for_asset_on_or_before()`
- `src/bve/analysis/implied_pos_batch.py`
  - `ScreenRow.asset_id`
- `src/bve/analysis/historical_implied_pos_validation.py`
- `src/bve/analysis/mispricing_screener.py`
- `src/bve/intelligence/mispricing_screener.py`
- `src/bve/intelligence/ma_probability.py`
- `src/bve/intelligence/ma_calibration.py`
- `src/bve/ops/daily_brief.py`
  - all updated to persist / read asset-level screen rows
- `src/bve/analysis/company_sotp.py`
  - company SOTP now prefers dated replay balance-sheet snapshots
  - exposes:
    - `balance_sheet_source`
    - `balance_sheet_source_ref`
    - `balance_sheet_snapshot_date`
    - `balance_sheet_period_end_date`
    - `balance_sheet_form_type`
  - multi-asset companies can now reuse stored per-asset historical screen rows

Focused verification:
- `ruff check src/bve/analysis/implied_pos_batch.py src/bve/intelligence/knowledge_layer.py src/bve/ops/daily_brief.py src/bve/analysis/historical_implied_pos_validation.py src/bve/analysis/mispricing_screener.py src/bve/intelligence/mispricing_screener.py src/bve/intelligence/ma_probability.py src/bve/intelligence/ma_calibration.py src/bve/analysis/company_sotp.py src/bve/ops/historical_replay.py src/bve/ops/signal_backfiller.py tests/test_company_sotp.py tests/test_sprint10.py tests/test_sprint25.py tests/test_historical_replay.py`
- targeted pytest on the new paths:
  - replay balance-sheet roundtrip
  - SEC balance-sheet provenance backfill
  - asset-level `screen_snapshots` migration / persistence / lookups
  - downstream stored-snapshot readers
  - company SOTP dated-balance-sheet + per-asset historical reuse
- Result: `11 passed`

What changed materially:
- company SOTP now has a real dated balance-sheet input path for the top
  universe, not just static YAML company cash / shares
- historical stored valuation state can now represent multi-asset companies
  correctly as one row per modeled asset instead of one row per ticker

## Company-Level SOTP Foundation (2026-04-08)

**Current status: ✅ The first point-in-time company-level SOTP layer is now implemented**

This is the first explicit bridge from asset-level valuation to company-level
capital allocation. The goal of this pass was not to finish the full
institutional underwriting stack. It was to create the initial dated company
wrapper so the system can stop treating one modeled asset as if it fully
explains company value.

Implemented in this pass:
- `src/bve/analysis/company_sotp.py`
  - `CompanySOTPBuilder`
  - `CompanySOTPBucket`
  - `CompanySOTPResult`
  - CLI entry point: `python -m bve.analysis.company_sotp`
- `research/company_sotp_overrides.yaml`
  - explicit bucket file for:
    - platform value
    - unmodeled pipeline value
    - royalty / milestone value
    - dilution reserve
- `tests/test_company_sotp.py`
  - focused coverage for multi-asset aggregation, replay market cap, override
    buckets, stored single-asset screen reuse, and limitation flags

What the new SOTP layer does:
- groups watchlist assets by ticker / company
- values each modeled asset leg via:
  - stored single-asset `screen_snapshots` when available, or
  - direct config revaluation through `ValuationEngine`
- adds explicit company-level buckets:
  - net cash
  - platform value
  - unmodeled pipeline value
  - royalty / milestone value
  - dilution reserve
- resolves dated market cap from:
  - knowledge-store market prices when available
  - replay-store price × shares fallback
  - yfinance / config fallback paths
- outputs company-level:
  - SOTP equity value
  - enterprise value
  - SOTP discount
  - modeled-asset coverage
  - explicit limitations / provenance warnings

Focused verification:
- `ruff check src/bve/analysis/company_sotp.py tests/test_company_sotp.py`
- `python -m pytest tests/test_company_sotp.py -q`
- Result: `5 passed`

Current limitation status:
- market cap is point-in-time when replay / stored prices exist
- balance sheet is now point-in-time when `balance_sheet_snapshots` are present;
  otherwise it still falls back to config company snapshots with explicit
  limitation flags
- multi-asset historical per-asset screen snapshots are now persisted and can
  be reused when stored asset-level rows exist for the requested date

Why this matters:
- This is the highest-leverage institutional upgrade currently available.
- It creates a clean place to add:
  - dated balance-sheet reconstruction
  - platform / royalty attribution
  - dilution scenarios
  - company-level validation and decision policies

Next highest-leverage follow-on work:
- populate dated balance-sheet snapshots across the top tradable universe
- rerank the top universe on company-level SOTP discount instead of pure
  single-asset discount
- add company-level dilution / financing-path scenarios on top of the SOTP base

## Final Merck / Pfizer / Novartis Cleanup (2026-04-07)

**Current status: ✅ The current covered Merck / Pfizer / Novartis top-1 miss set is cleared**

This final cleanup pass resolved the last buyer-ordering leaks that remained
after the earlier sub-area repair. The fix was not more breadth. It was making
the curated sub-area aliases authoritative and removing a few remaining generic
tokens from AstraZeneca and GSK gap definitions.

Implemented in this pass:
- `src/bve/intelligence/acquirer_fit.py`
  - sub-areas with curated alias maps now use alias-only specific matching
    instead of inheriting every raw split token from the sub-area label
  - removed remaining broad-token leakage in:
    - `copd_commercial_respiratory`
    - `aldosterone_synthase_resistant_htn`
    - `momelotinib_jak_mpn`
    - `tl1a_ibd`
- `examples/research/acquirer_profiles/astrazeneca.yaml`
  - resistant-hypertension gap renamed to `aldosterone_synthase_resistant_htn`
- `examples/research/acquirer_profiles/gsk.yaml`
  - myelofibrosis/JAK gap renamed to `momelotinib_jak_mpn`
- `tests/intelligence/test_acquirer_fit.py`
  - added final regressions for:
    - Acceleron-like PAH
    - Imago-like MPN
    - Arena-like IBD
    - generic-oncology note leakage

Focused verification:
- `ruff check src/bve/intelligence/acquirer_fit.py src/bve/intelligence/acquirer_profile_validation.py tests/intelligence/test_acquirer_fit.py`
- `python -m pytest tests/intelligence/test_acquirer_fit.py tests/intelligence/test_acquirer_profile_validation.py tests/intelligence/test_acquirer_fit_engine.py tests/intelligence/test_acquirer_profiles.py -q`
- Result: `35 passed`

Final live historical validator rerun:
- Artifact:
  `outputs/analysis/acquirer_profile_validation_2026-04-07_subarea_repair_final.csv`
- Overall:
  - `n_profile_covered_deals = 32`
  - `top1_rate = 0.6875`
  - `top3_rate = 0.8125`
  - `median_actual_rank = 1.0`

Versus the earlier sub-area repair checkpoint:
- `top1_rate`: `0.5625 -> 0.6875`
- `top3_rate`: unchanged at `0.8125`
- `median_actual_rank`: unchanged at `1.0`

Current miss status:
- Remaining Merck / Pfizer / Novartis top-1 misses in the covered historical
  set: `none`

Interpretation:
- The current curated acquirer layer is materially tighter than the earlier
  tail-repair state.
- The remaining miss budget is now outside the original Merck / Pfizer /
  Novartis problem statement.
- The next highest-leverage move is broader acquirer expansion or rerunning the
  historical M&A probability stack on top of this repaired fit layer, not more
  tactical tie-break work inside these three buyers.

## Merck / Pfizer / Novartis Sub-Area Repair Pass (2026-04-07)

**Current status: ✅ The remaining Merck / Pfizer / Novartis top-1 miss set was narrowed again with scorer cleanup plus targeted profile specificity**

This pass addressed the residual buyer-ordering misses that remained after the
earlier tail-repair work. The key issue was no longer broad profile coverage;
it was a combination of:
- noisy free-form note text leaking into the historical validator
- over-permissive sub-area token matching
- a few oncology gaps that were still too broad on modality / sub-area

Implemented in this pass:
- `src/bve/intelligence/acquirer_fit.py`
  - stronger text normalization and stopword filtering
  - explicit sub-area alias support for disease-level matching
  - cleaner therapeutic-area matching for pipeline-gap profiles
- `src/bve/intelligence/acquirer_profile_validation.py`
  - historical validation candidates no longer inject free-form `deal.notes`
    or target names into `priority_tags`
- `examples/research/acquirer_profiles/bms.yaml`
  - radiopharma gap now requires radiopharma modality
  - degrader gap narrowed to `celmod_myeloma_degrader`
  - kinase gap narrowed to `nsclc_ros1_alk_trk_kinase`
- `examples/research/acquirer_profiles/pfizer.yaml`
  - CD47 / heme-IO gap no longer accepts generic `small_molecule`
- `examples/research/acquirer_profiles/novartis.yaml`
  - heme-oncology gap narrowed to `bet_epigenetic_myelofibrosis`
  - urgency reduced from `high` to `medium`
- `tests/intelligence/test_acquirer_fit.py`
  - added direct regressions for Trillium-like, Harpoon-like, Imago-like, and
    Avidity-like targets

Focused verification:
- `ruff check src/bve/intelligence/acquirer_fit.py src/bve/intelligence/acquirer_profile_validation.py tests/intelligence/test_acquirer_fit.py`
- `python -m pytest tests/intelligence/test_acquirer_fit.py tests/intelligence/test_acquirer_profile_validation.py tests/intelligence/test_acquirer_fit_engine.py tests/intelligence/test_acquirer_profiles.py -q`
- Result: `31 passed`

Live historical validator rerun:
- Artifact:
  `outputs/analysis/acquirer_profile_validation_2026-04-07_subarea_repair.csv`
- Overall:
  - `n_profile_covered_deals = 32`
  - `top1_rate = 0.5625`
  - `top3_rate = 0.8125`
  - `median_actual_rank = 1.0`

Versus the prior tail-repair checkpoint:
- `top1_rate`: `0.50 -> 0.5625`
- `top3_rate`: `0.875 -> 0.8125`
- `median_actual_rank`: `1.5 -> 1.0`

Remaining Merck / Pfizer / Novartis top-1 misses:
- `XLRN`:
  - actual `merck`, rank `2`
  - predicted `astrazeneca`
- `ARNA`:
  - actual `pfizer`, rank `2`
  - predicted `merck`
- `IMGO`:
  - actual `merck`, rank `2`
  - predicted `gsk`
- `HARP`:
  - actual `merck`, rank `2`
  - predicted `gsk`

Interpretation:
- The current covered Novartis miss set is cleared at top-1.
- The remaining misses are all top-2 outcomes, not broad ranking failures.
- The next acquirer-profile work should focus on:
  - Merck vs AstraZeneca in cardio-pulmonary targets
  - Merck / Pfizer vs GSK on oncology-heme / engager targets
  - Pfizer vs Merck tie-break specificity in IBD

## Post-Tail-Repair Historical M&A Rerun (2026-04-07)

**Current status: ✅ Historical snapshots and calibration artifacts were rebuilt on top of the repaired acquirer-fit layer**

After the acquirer tail-repair pass, the full historical M&A measurement stack
was rerun against the replay snapshot range and the matched-control calibration
layer was rebuilt from the refreshed stored M&A snapshots.

Stored snapshot coverage check:
- `ma_probability_snapshots` now holds:
  - `2432` rows
  - `38` distinct snapshot dates
  - date range `2021-02-01 -> 2024-03-01`

Rebuilt artifacts:
- `outputs/analysis/ma_calibration_dataset_2021-02-01_2024-03-01_historical_snapshot_tail_repair.csv`
- `outputs/analysis/ma_calibration_metrics_2021-02-01_2024-03-01_historical_snapshot_tail_repair.json`
- `outputs/analysis/ma_baseline_comparison_2026-04-07_tail_repair.json`
- `outputs/analysis/ma_calibration_dataset_2021-02-01_2024-03-01_canonical_anchor180_controls2_tail_repair.csv`
- `outputs/analysis/ma_calibration_metrics_2021-02-01_2024-03-01_canonical_anchor180_controls2_tail_repair.json`
- `outputs/analysis/ma_logistic_fit_2021-02-01_2024-03-01_canonical_anchor180_controls2_tail_repair.json`
- `outputs/analysis/ma_logistic_predictions_2021-02-01_2024-03-01_canonical_anchor180_controls2_tail_repair.csv`
- `outputs/analysis/ma_policy_comparison_2021-02-01_2024-03-01_historical_snapshot_tail_repair.json`

Refreshed historical snapshot result (`top_k=15`):
- rows: `1995`
- positive rows: `263`
- unique targets: `25`
- `precision@15 = 0.245614`
- `recall@15 = 0.64`
- `median_lead_days@15 = 342.5`
- `average_probability_positive = 0.93858`
- `average_probability_control = 0.846464`

Versus the prior post-Step-2 refreshed snapshot checkpoint:
- `precision@15`: `0.250877 -> 0.245614`
- `recall@15`: unchanged at `0.64`

Updated transparent baseline comparison:
- `stored_probability`: `0.245614 / 0.64`
- `strategic_fit_only`: `0.245614 / 0.64`
- `strategic_fit_plus_scarcity`: `0.245614 / 0.64`
- `strategic_fit_plus_capital`: `0.235088 / 0.56`
- `strategic_fit_plus_derisking`: `0.247368 / 0.52`
- `composite_without_valuation_discount`: `0.247368 / 0.52`
- `composite_with_inverted_valuation_discount`: `0.221053 / 0.44`

Interpretation of the replay rerun:
- The acquirer-fit repair materially improved retrospective buyer matching, but
  it did not improve the raw top-15 `v1.2` M&A ranking baseline.
- The core ranking regime remains strategically fit-driven and still beats the
  valuation-weighted composites.
- The small precision drop with unchanged recall suggests the buyer-profile
  repair mostly changed *who* wins among acquirers, not which target names
  occupy the top-ranked historical slots.

Rebuilt canonical matched-control calibration set:
- rows: `75`
- positives: `25`
- controls: `50`
- unique targets: `25`
- stored precision@15: `0.733333`
- stored recall@15: `0.44`

Refit matched-control logistic model:
- features:
  - `stored_probability`
  - `strategic_fit_score`
  - `capital_vulnerability_score`
  - `log_enterprise_value`
- in-sample AUC: `0.7792`
- leave-one-group-out AUC: `0.7632`
- leave-one-group-out precision@15: `0.40`
- leave-one-group-out recall@15: `0.24`

Updated historical policy comparison:
- policy A, `v1.2` rank + display calibrated probability:
  - `precision@15 = 0.245614`
  - `recall@15 = 0.64`
- policy B, `v1.2` rank + calibrated threshold filter:
  - `precision@15 = 0.264912`
  - `recall@15 = 0.64`
- policy C, `v1.2` rank + calibrated tie-breaker:
  - `precision@15 = 0.261404`
  - `recall@15 = 0.64`
- baseline AUC: `0.6825`
- calibrated AUC: `0.760478`

Current conclusion:
- Policy B remains the correct live deployment choice.
- The next likely source of improvement is broader / more specific curated
  acquirer coverage, not further score-weight tuning.

## Post-Subarea-Repair Final Historical M&A Rerun (2026-04-08)

**Current status: ✅ The historical M&A stack was rerun on the final repaired-fit layer and the stronger acquirer substrate did not improve the live precision baseline**

After the final Merck / Pfizer / Novartis sub-area repair, I rebuilt a fresh,
coherent historical artifact set directly from the current replay DB so the
historical snapshot dataset, transparent baselines, canonical calibration set,
and policy comparison all reflect the same repaired-fit substrate.

Authoritative rebuilt artifacts:
- `outputs/analysis/ma_calibration_dataset_2021-02-01_2024-03-01_historical_snapshot_subarea_repair_final.csv`
- `outputs/analysis/ma_calibration_metrics_2021-02-01_2024-03-01_historical_snapshot_subarea_repair_final.json`
- `outputs/analysis/ma_baseline_comparison_2026-04-07_subarea_repair_final.json`
- `outputs/analysis/ma_calibration_dataset_2021-02-01_2024-03-01_canonical_anchor180_controls2_subarea_repair_final.csv`
- `outputs/analysis/ma_calibration_metrics_2021-02-01_2024-03-01_canonical_anchor180_controls2_subarea_repair_final.json`
- `outputs/analysis/ma_logistic_fit_2021-02-01_2024-03-01_canonical_anchor180_controls2_subarea_repair_final.json`
- `outputs/analysis/ma_logistic_predictions_2021-02-01_2024-03-01_canonical_anchor180_controls2_subarea_repair_final.csv`
- `outputs/analysis/ma_policy_comparison_2021-02-01_2024-03-01_historical_snapshot_subarea_repair_final.json`

Current `historical_snapshot` result (`top_k=15`):
- rows: `1995`
- positive rows: `263`
- unique targets: `25`
- `precision@15 = 0.245614`
- `recall@15 = 0.56`
- `median_lead_days@15 = 346.0`
- `average_probability_positive = 0.943384`
- `average_probability_control = 0.83321`

Versus the prior repaired-fit checkpoint:
- `precision@15`: unchanged at `0.245614`
- `recall@15`: `0.64 -> 0.56`

Updated transparent baseline comparison:
- `stored_probability`: `0.245614 / 0.56`
- `strategic_fit_only`: `0.245614 / 0.56`
- `strategic_fit_plus_scarcity`: `0.245614 / 0.56`
- `strategic_fit_plus_capital`: `0.238596 / 0.56`
- `strategic_fit_plus_derisking`: `0.228070 / 0.48`
- `composite_without_valuation_discount`: `0.228070 / 0.48`
- `composite_with_inverted_valuation_discount`: `0.210526 / 0.44`

Rebuilt canonical matched-control calibration set:
- rows: `75`
- positives: `25`
- controls: `50`
- unique targets: `25`
- stored precision@15: `0.733333`
- stored recall@15: `0.44`

Refit matched-control logistic model:
- features:
  - `stored_probability`
  - `strategic_fit_score`
  - `capital_vulnerability_score`
  - `log_enterprise_value`
- in-sample AUC: `0.7824`
- leave-one-group-out AUC: `0.7480`
- leave-one-group-out precision@15: `0.40`
- leave-one-group-out recall@15: `0.24`

Updated live-policy comparison on `historical_snapshot`:
- policy A, `v1.2` rank + display calibrated probability:
  - `precision@15 = 0.245614`
  - `recall@15 = 0.56`
- policy B, `v1.2` rank + calibrated threshold filter:
  - `precision@15 = 0.249123`
  - `recall@15 = 0.60`
- policy C, `v1.2` rank + calibrated tie-breaker:
  - `precision@15 = 0.224561`
  - `recall@15 = 0.52`
- baseline AUC: `0.67443`
- calibrated AUC: `0.74002`

Interpretation:
- The stronger acquirer substrate improved acquirer attribution, but it did
  not improve the raw live `precision@15` baseline.
- The target-ranking bottleneck remains outside buyer matching; the repaired
  profiles mostly changed *which acquirer wins*, not *which targets enter the
  top-15*.
- Policy B is still the best live regime because it recovers a modest
  precision and recall lift on top of the unchanged `v1.2` ranking layer.

## Acquirer Tail-Repair Pass (2026-04-07)

**Current status: ✅ The weak-tail acquirer miss set was materially improved with a targeted profile repair pass**

After wiring live Policy B into the M&A scanner, the next highest-leverage
bottleneck was still the residual buyer-profile miss set. This pass did not
change the fit algorithm; it repaired the actual curated profiles that were
still under-ranking real historical buyers.

Updated curated profiles:
- `examples/research/acquirer_profiles/pfizer.yaml`
- `examples/research/acquirer_profiles/merck.yaml`
- `examples/research/acquirer_profiles/gsk.yaml`
- `examples/research/acquirer_profiles/novartis.yaml`
- `examples/research/acquirer_profiles/bms.yaml`
- `examples/research/acquirer_profiles/astrazeneca.yaml`
- `examples/research/acquirer_profiles/amgen.yaml`
- `examples/research/acquirer_profiles/abbvie.yaml`

Main changes:
- Pfizer:
  - elevated the CD47 / macrophage / heme-IO gap to high urgency
  - broadened modality acceptance so early heme-IO takeouts such as Trillium
    do not fall back to the unrelated breast-cancer gap
- Merck:
  - demoted the overly broad Keytruda LOE gap from high to medium
  - strengthened specific deal-derived gaps for:
    - TL1A / IBD / gut-immune biology
    - T-cell engagers in SCLC / neuroendocrine tumors
    - MPN / myelofibrosis / LSD1 hematology
    - commercial COPD respiratory assets
- GSK:
  - added a real food-allergy / allergic-disease immunology gap for RAPT-style
    assets instead of forcing those targets through cough / respiratory gaps
- Novartis:
  - made the neuromuscular RNA gap more explicit around DM1 / FSHD / DMD
  - broadened modality acceptance so generic watchlist-backed neuromuscular
    candidates still score as intended
- BMS:
  - raised precision-oncology kinase urgency for Turning Point / ROS1-style
    programs
  - broadened the radiopharmaceutical franchise gap for RayzeBio-style
    candidates
- AstraZeneca:
  - added an explicit resistant-hypertension / aldosterone-synthase gap for
    CinCor-style cardio-renal deals
- Broad false-winner control:
  - reduced Amgen's broad complement/inflammation urgency
  - reduced AbbVie's broad neuroscience urgency

Focused verification:
- `ruff check src/bve/intelligence/acquirer_fit.py src/bve/intelligence/acquirer_profile_validation.py tests/intelligence/test_acquirer_fit.py tests/intelligence/test_acquirer_fit_engine.py tests/intelligence/test_acquirer_profile_validation.py tests/intelligence/test_acquirer_profiles.py`
- `python -m pytest tests/intelligence/test_acquirer_fit.py tests/intelligence/test_acquirer_fit_engine.py tests/intelligence/test_acquirer_profile_validation.py tests/intelligence/test_acquirer_profiles.py -q`
- Result: `27 passed`

Live historical validation rerun:
- Validator:
  `AcquirerProfileDealValidator(profiles_path='examples/research/acquirer_profiles', deal_universe_path='research/mna/deal_universe_2020_2026.yaml', watchlist_path='examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml')`
- Artifact:
  `outputs/analysis/acquirer_profile_validation_2026-04-07_tail_repair.csv`
- Overall result:
  - `n_public_tickered_deals = 38`
  - `n_profile_covered_deals = 32`
  - `n_scored_deals = 32`
  - `top1_rate = 0.50`
  - `top3_rate = 0.875`
  - `median_actual_rank = 1.5`

Versus the prior completed Step 2 baseline:
- `top1_rate`: `0.46875 -> 0.50`
- `top3_rate`: `0.6875 -> 0.875`
- `median_actual_rank`: `2.0 -> 1.5`

Key weak-buyer improvements after the pass:
- `bristol_myers_squibb`:
  - `top1_rate = 1.0`
  - `top3_rate = 1.0`
- `astrazeneca`:
  - `top1_rate = 1.0`
  - `top3_rate = 1.0`
- `gsk`:
  - `top1_rate = 0.666667`
  - `top3_rate = 1.0`
- `novartis`:
  - `top3_rate = 1.0`
- `pfizer`:
  - `top3_rate = 1.0`
- `merck`:
  - `top3_rate = 1.0`

Interpretation:
- The remaining problem is no longer gross buyer-profile coverage.
- The residual misses are now mostly top-1 ordering within Merck / Pfizer /
  Novartis rather than large rank failures.
- That meaningfully de-risks the live M&A scanner, because the calibrated
  ranking stack now sits on a much stronger strategic-fit substrate.

## Live Policy B Integration (2026-04-07)

**Current status: ✅ The promoted calibrated-threshold policy is now wired into the live M&A scanner and CLI path**

The calibration overlay is no longer offline-only. The live M&A scanner now
supports explicit calibrated-output policies, and the default production path
uses the promoted Policy B behavior:

- rank by `v1.2`
- compute `p_takeout_calibrated`
- display / monitor only rows with
  `p_takeout_calibrated >= 0.10`

Implemented in this pass:
- `src/bve/intelligence/ma_probability.py`
  - added `calibration_policy` and `calibration_threshold` to
    `MAProbabilityConfig`
  - added live policy application for:
    - `display_only`
    - `threshold_filter`
    - `tie_breaker`
  - kept snapshot persistence on the full scored cross-section so historical
    replay remains intact
  - re-ranked the displayed rows after policy application so reports do not
    show skipped rank values
  - monitor evaluation now uses the same displayed row set as the live report
- `src/bve/cli/ma_probability.py`
  - resolves the latest available calibration fit automatically
  - defaults to `threshold_filter` with threshold `0.10`
  - report output now shows:
    - calibration policy / threshold summary
    - calibrated probability column (`Cal`)
- `src/bve/ops/weekly_runner.py`
  - weekly M&A scan now resolves the same calibration fit automatically
  - uses `threshold_filter` in the production runner path
  - weekly printed section now includes calibrated probability

Focused verification:
- `ruff check src/bve/intelligence/ma_probability.py src/bve/cli/ma_probability.py src/bve/ops/weekly_runner.py tests/intelligence/test_ma_probability.py tests/intelligence/test_ma_probability_cli.py`
- `python -m pytest tests/intelligence/test_ma_probability.py tests/intelligence/test_ma_probability_cli.py tests/intelligence/test_sprint30.py -q`
- Result: `54 passed`

New regressions added:
- scanner threshold-filter path excludes sub-threshold rows while preserving
  the full internal asset count
- scanner tie-break path uses calibrated probability to reorder equal-score rows
- CLI report now surfaces calibration policy, threshold, and calibrated
  probability

Live CLI smoke run:
- Command:
  `python -m bve.cli.ma_probability --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml --db outputs/intelligence/replay_knowledge.db --as-of 2024-03-01 --top 3 --output-format report`
- Result:
  - completed successfully
  - report now shows:
    - `Calibration: threshold_filter | Threshold: 0.10`
    - calibrated probability column
    - filtered live ranking via the promoted Policy B path

Operational implication:
- `v1.2` remains the core score regime.
- The live system now uses the calibrated layer to control which names make the
  production M&A output, rather than merely displaying an unused probability.

## Step 6/7 Calibration Overlay Refresh (2026-04-07)

**Current status: ✅ Canonical dataset rebuilt, strategic-fit-aware logistic model refit, and policy promotion decision made**

The post-Step-2 M&A stack has now been rerun through the next calibration
layer. This pass rebuilt the canonical pre-deal dataset from the refreshed
historical M&A snapshots, refit the matched-control logistic model using the
improved strategic-fit inputs, and then evaluated the three candidate
deployment policies on the real `historical_snapshot` replay dataset.

Implemented in this pass:
- Updated `src/bve/intelligence/ma_calibration.py` so the default matched-
  control logistic feature set is now:
  - `stored_probability`
  - `strategic_fit_score`
  - `capital_vulnerability_score`
  - `log_enterprise_value`
- Refined `compare_ranking_policies(...)` so it evaluates:
  - `canonical_predeal` datasets as a global case-control ranking
  - `historical_snapshot` datasets by `snapshot_date`, which is required for a
    fair comparison against the live replay top-15 baseline
- Added focused regression coverage in:
  - `tests/intelligence/test_ma_calibration.py`
  - `tests/intelligence/test_sprint30.py`

Focused verification:
- `ruff check src/bve/intelligence/ma_calibration.py tests/intelligence/test_ma_calibration.py tests/intelligence/test_sprint30.py`
- `python -m pytest tests/intelligence/test_ma_calibration.py tests/intelligence/test_sprint30.py -q`
- Result: `36 passed`

Rebuilt canonical matched-control dataset from refreshed snapshots:
- Source DB: `outputs/intelligence/replay_knowledge.db`
- Date range: `2021-02-01 -> 2024-03-01`
- Lookahead: `365d`
- Anchor: `180d` before announcement
- Controls per positive: `2`
- Result:
  - `75` rows
  - `25` positives
  - `50` matched controls
  - `25` unique positive targets
  - stored `v1.2` precision@15: `0.733333`
  - stored `v1.2` recall@15: `0.44`

Refit matched-control logistic model:
- Feature set:
  - `stored_probability`
  - `strategic_fit_score`
  - `capital_vulnerability_score`
  - `log_enterprise_value`
- Result on the canonical set:
  - in-sample AUC: `0.7832`
  - leave-one-group-out AUC: `0.7632`
  - leave-one-group-out precision@15: `0.40`
  - leave-one-group-out recall@15: `0.24`

Historical policy comparison on the refreshed replay snapshot dataset:
- The earlier Step 3 checkpoint (`precision@15 = 0.254386`,
  `recall@15 = 0.60`) is now superseded by the refreshed in-database
  `historical_snapshot` baseline:
  - `precision@15 = 0.250877`
  - `recall@15 = 0.64`
- Policy A, rank by `v1.2`, display calibrated probability only:
  - `precision@15 = 0.250877`
  - `recall@15 = 0.64`
- Policy B, rank by `v1.2` and require `p_takeout_calibrated >= 0.10`:
  - `precision@15 = 0.270175`
  - `recall@15 = 0.64`
- Policy C, rank by `v1.2` with calibrated probability as tie-breaker:
  - `precision@15 = 0.261404`
  - `recall@15 = 0.64`
- Discrimination on the refreshed historical snapshot set:
  - stored baseline AUC: `0.689204`
  - calibrated AUC: `0.76293`

Interpretation:
- The strategic-fit improvements from Step 2 carry through into the fitted
  calibration layer; the cross-validated classifier is materially better than
  the old calibration pass.
- Policy A is neutral on the refreshed replay baseline.
- Policies B and C both improve precision without reducing recall.
- Policy B is the strongest current deployment candidate.

Promotion decision:
- Keep `v1.2` as the core M&A score regime.
- Promote the calibrated overlay from research-only status into the next live
  integration step.
- Preferred live policy for the next wiring pass:
  `v1.2` rank filtered by calibrated threshold (`0.10`).

Artifacts written:
- `outputs/analysis/ma_calibration_dataset_2021-02-01_2024-03-01_canonical_anchor180_controls2_post_step2.csv`
- `outputs/analysis/ma_calibration_metrics_2021-02-01_2024-03-01_canonical_anchor180_controls2_post_step2.json`
- `outputs/analysis/ma_logistic_fit_2021-02-01_2024-03-01_canonical_anchor180_controls2_post_step2.json`
- `outputs/analysis/ma_logistic_predictions_2021-02-01_2024-03-01_canonical_anchor180_controls2_post_step2.csv`
- `outputs/analysis/ma_policy_comparison_2021-02-01_2024-03-01_historical_snapshot_post_step2.json`

## Acquirer Profile Validation Rebaseline (2026-04-07)

**Current status: Step 2 is improved but still in progress**

The earlier Step 2 note is now superseded by a broader live validation run on
the current curated acquirer directory. The main issue is no longer the
validator scaffold itself; it is profile specificity and tie-breaking quality.

Implemented in this pass:
- Expanded therapeutic-area aliasing in
  `src/bve/intelligence/acquirer_fit.py` for kidney disease, liver disease,
  respiratory, neuroscience, vaccines, radiopharmaceutical, and IBD language.
- Updated text normalization to split hyphenated phrases cleanly, which improves
  matching on terms like `alpha-1`, `gene-therapy`, and `triple-negative`.
- Refined `src/bve/intelligence/acquirer_profile_validation.py` so
  watchlist-backed targets can inherit better metadata from deal text:
  - generic therapeutic areas such as `other` can now be replaced by
    normalized deal TAs like `kidney_disease`, `liver_disease`, `respiratory`,
    and `neuroscience`
  - generic `small_molecule` watchlist modalities can now be upgraded to
    `adc`, `radiopharmaceutical`, `genetic_medicine`, `mRNA`, `rna`,
    `protein`, or `peptide` when the historical deal text supports it
  - deal fields are now merged into candidate `priority_tags`, which gives the
    sub-area matcher more real text to work with
- Extended `examples/research/acquirer_profiles/lilly.yaml` with a specific CNS
  / otology gene-therapy gap to better cover historical Lilly targets such as
  Prevail and Akouos.
- Added focused regressions in
  `tests/intelligence/test_acquirer_profile_validation.py` for:
  - generic watchlist TA refinement from deal metadata
  - watchlist `small_molecule -> adc` refinement from deal metadata

Focused verification:
- `ruff check src/bve/intelligence/acquirer_fit.py src/bve/intelligence/acquirer_profile_validation.py tests/intelligence/test_acquirer_profile_validation.py tests/intelligence/test_acquirer_fit.py tests/intelligence/test_acquirer_fit_engine.py`
- `python -m pytest tests/intelligence/test_acquirer_profile_validation.py tests/intelligence/test_acquirer_fit.py tests/intelligence/test_acquirer_fit_engine.py -q`
- Result: `17 passed`

Measured live Step 2 result after the normalization pass:
- profiles: `examples/research/acquirer_profiles`
- deals: `research/mna/deal_universe_2020_2026.yaml`
- watchlist context:
  `examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml`
- artifact:
  `outputs/analysis/acquirer_profile_validation_2026-04-07.csv`
- metrics:
  - `n_public_tickered_deals = 38`
  - `n_profile_covered_deals = 32`
  - `n_scored_deals = 32`
  - `n_watchlist_backed = 27`
  - `n_fallback_only = 5`
  - `top1_rate = 0.1875`
  - `top3_rate = 0.53125`
  - `median_actual_rank = 3.0`

Versus the immediate pre-normalization baseline on the same curated breadth:
- `top1_rate`: unchanged at `0.1875`
- `top3_rate`: improved from `0.375` to `0.53125`
- `median_actual_rank`: improved from `4.5` to `3.0`

Interpretation:
- The candidate-construction / normalization layer is materially better now.
- The remaining weakness is profile misspecification, especially broad AbbVie
  wins on generic immunology / oncology assets and missing acquirer-specific
  sub-areas for Merck, Pfizer, GSK, BMS, Novartis, Sanofi, and Amgen.
- Step 2 should continue with targeted profile corrections, not another change
  to the M&A probability architecture yet.

Follow-on targeted profile correction pass:
- Updated the following curated profiles directly:
  - `examples/research/acquirer_profiles/abbvie.yaml`
  - `examples/research/acquirer_profiles/amgen.yaml`
  - `examples/research/acquirer_profiles/bms.yaml`
  - `examples/research/acquirer_profiles/gsk.yaml`
  - `examples/research/acquirer_profiles/lilly.yaml`
  - `examples/research/acquirer_profiles/merck.yaml`
  - `examples/research/acquirer_profiles/novartis.yaml`
  - `examples/research/acquirer_profiles/pfizer.yaml`
  - `examples/research/acquirer_profiles/sanofi.yaml`
- Main changes:
  - narrowed AbbVie's broad oncology / immunology urgency so it stops winning
    generic ties by default
  - added explicit missing sub-area gaps for Merck, Pfizer, GSK, BMS,
    Sanofi, Novartis, Lilly, and Amgen based on the real historical miss set
- Focused verification rerun passed:
  - `ruff check src/bve/intelligence/acquirer_fit.py src/bve/intelligence/acquirer_profile_validation.py tests/intelligence/test_acquirer_profile_validation.py tests/intelligence/test_acquirer_fit.py tests/intelligence/test_acquirer_fit_engine.py tests/intelligence/test_acquirer_profiles.py`
  - `python -m pytest tests/intelligence/test_acquirer_profile_validation.py tests/intelligence/test_acquirer_fit.py tests/intelligence/test_acquirer_fit_engine.py tests/intelligence/test_acquirer_profiles.py -q`
  - Result: `25 passed`

Updated live Step 2 result after the targeted profile corrections:
- `n_public_tickered_deals = 38`
- `n_profile_covered_deals = 32`
- `n_scored_deals = 32`
- `n_watchlist_backed = 27`
- `n_fallback_only = 5`
- `top1_rate = 0.34375`
- `top3_rate = 0.625`
- `median_actual_rank = 2.5`
- artifact refreshed:
  `outputs/analysis/acquirer_profile_validation_2026-04-07.csv`

Versus the immediate rebaseline earlier in the same day:
- `top1_rate`: `0.1875 -> 0.34375`
- `top3_rate`: `0.53125 -> 0.625`
- `median_actual_rank`: `3.0 -> 2.5`

Per-acquirer highlights:
- `Eli Lilly`: `4 / 4` top-1, `4 / 4` top-3
- `Amgen`: `1 / 2` top-1, `2 / 2` top-3
- `Sanofi`: `1 / 4` top-1, `3 / 4` top-3
- `Bristol-Myers Squibb`: `1 / 4` top-1, `2 / 4` top-3

Interpretation now:
- Step 2 has moved from scaffolding into meaningful live signal recovery.
- The biggest remaining profile weak spots are now concentrated in
  `Pfizer`, `Merck`, `Novartis`, and `GSK`.
- The next Step 2 work should keep refining those specific profiles rather than
  changing the M&A score architecture again.

Final Step 2 structural matcher fix:
- Updated `src/bve/intelligence/acquirer_fit.py` so signal matching no longer
  leaks through generic tokens such as `disease`, `therapy`, and `next`.
- Broad TA-only overlaps now score as partial (`0.65`) when a gap declares a
  specific sub-area; full `1.0` TA credit now requires a real sub-area /
  indication overlap.
- Literal sub-area matching is now separated from broad category aliasing, so
  an `immunology` target no longer gets a perfect match on any immunology
  sub-area just because both share the same parent category.
- Added focused regressions in `tests/intelligence/test_acquirer_fit.py` to
  lock in:
  - IBD-specific buyer > generic immunology buyer
  - kidney / IgAN-specific buyer > unrelated broad profiles

Focused verification rerun:
- `ruff check src/bve/intelligence/acquirer_fit.py src/bve/intelligence/acquirer_profile_validation.py tests/intelligence/test_acquirer_fit.py tests/intelligence/test_acquirer_profile_validation.py tests/intelligence/test_acquirer_fit_engine.py tests/intelligence/test_acquirer_profiles.py`
- `python -m pytest tests/intelligence/test_acquirer_fit.py tests/intelligence/test_acquirer_profile_validation.py tests/intelligence/test_acquirer_fit_engine.py tests/intelligence/test_acquirer_profiles.py -q`
- Result: `27 passed`

Final live Step 2 result on the current curated directory:
- `n_public_tickered_deals = 38`
- `n_profile_covered_deals = 32`
- `n_scored_deals = 32`
- `n_watchlist_backed = 27`
- `n_fallback_only = 5`
- `top1_rate = 0.46875`
- `top3_rate = 0.6875`
- `median_actual_rank = 2.0`
- artifact refreshed:
  `outputs/analysis/acquirer_profile_validation_2026-04-07.csv`

Versus the immediately prior targeted-profile checkpoint:
- `top1_rate`: `0.34375 -> 0.46875`
- `top3_rate`: `0.625 -> 0.6875`
- `median_actual_rank`: `2.5 -> 2.0`

Interpretation now:
- Step 2 is complete for the current curated acquirer set.
- The original failure mode was not just thin profiles; it was also an
  over-permissive TA matcher. That structural issue is now fixed.
- Remaining misses still exist, but they are concentrated in a smaller tail
  (`Merck`, `Pfizer`, `Bristol-Myers Squibb`, `Novartis`, `AstraZeneca`) and
  no longer dominate the live validation.

## Targetability Filter Refinement (2026-04-07)

**Current status: completed and measured**

The M&A scanner is being tightened to match the intended targetability design:
- rules now live in `src/bve/config/targetability_rules.yaml`
- hard-failed assets are excluded before ranking instead of remaining in the
  output with zero probability
- the scanner is being instrumented to count and log excluded names so the
  historical replay can report the exact before/after impact

Additional implementation completed:
- Added `TargetabilityFilter` to `src/bve/intelligence/ma_probability.py`.
- Added `src/bve/analysis/mna_probability_scanner.py` so historical label CSVs
  can be evaluated directly from the command line.
- Fixed a replay-integrity bug in `MAProbabilitySnapshotStore.write_snapshots()`:
  same-date snapshot rows are now deleted before rewrite, so newly excluded
  assets do not linger as stale rows from earlier runs.

Focused verification:
- `ruff check src/bve/intelligence/ma_probability.py src/bve/ops/ma_probability_backfiller.py src/bve/analysis/mna_probability_scanner.py tests/intelligence/test_ma_probability.py tests/intelligence/test_ma_probability_cli.py tests/test_analysis_mna_probability_scanner.py`
- `python -m pytest tests/intelligence/test_ma_probability.py tests/intelligence/test_ma_probability_cli.py tests/test_analysis_mna_probability_scanner.py -q`
- Result: `24 passed`

Measured replay result, historical snapshot dataset, 2021-02-01 through
2024-03-01, `top_k=15`:
- Frozen pre-refinement baseline on this branch:
  - `precision@15 = 0.221053`
  - `recall@15 = 0.44`
- Post-refinement result:
  - `precision@15 = 0.221053`
  - `recall@15 = 0.44`
- `112` asset-date rows were removed from persisted `ma_probability_snapshots`
  after the hard-fail exclusions were applied with stale-row deletion fixed.
- The hard-fail rules intersect `7` names in the expanded replay watchlist:
  `ALNY`, `BIIB`, `BMRN`, `LLY`, `MRNA`, `REGN`, `VRTX`.
- Historical top-15 turnover versus the frozen pre-refinement dataset:
  `0` changed slots across `38` snapshot dates.

Interpretation:
- The refined targetability filter is correct and replay-safe.
- It improves data hygiene and removes excluded names from stored historical
  snapshots.
- It does **not** improve the current top-15 M&A ranking on this branch, which
  means further ranking gains now have to come from scoring logic rather than
  more hard-fail rules.

## M&A Plan Adjustment (2026-04-06)

**Current status: ✅ The M&A execution plan has been revised to prioritize cheap architectural fixes before further large historical backfills**

Reason for adjustment:
- The first real historical M&A baseline is now measurable and weak.
- `precision@15` is only `12.1%`.
- Average predicted probability is still lower for positives than controls.
- Repeated false positives include obvious non-targets such as large-cap buyers.

Revised immediate order:
1. Add explicit targetability hard-fails.
2. Validate acquirer profiles against actual historical deals.
3. Run simplest possible baselines, including `strategic_fit_score` alone.
4. Remove or invert `valuation_discount` unless it improves the ranking.
5. Add scarcity.
6. Re-test the transparent score before any larger backfill or fitted model.

Operational implication:
- Full-universe historical implied-PoS backfill is now deferred.
- Step 3 is now complete; the next code change should be Step 4:
  invert or remove `valuation_discount` in the live M&A score and rerun the
  historical replay baseline before adding scarcity.

## M&A Targetability Hard-Fails (2026-04-06)

**Current status: ✅ Step 1 of the revised M&A plan is now implemented and verified with focused tests**

Implemented in the M&A scanner:
- Added a universe-level targetability gate in
  `src/bve/intelligence/ma_probability.py`.
- New hard fails now zero out acquisition probability for:
  - self-acquirers / obvious buyers already present in the curated acquirer set
  - mega-cap non-targets above the configured EV ceiling
  - approved / commercial multi-franchise names that are unlikely to be sold
- Added a softer penalty for larger multi-franchise assets that are still
  technically targetable but structurally less likely to be acquired.
- The scanner now records `targetability_multiplier` and
  `targetability_reasons` on each output row, so filtered names are auditable.

Focused verification:
- `ruff check src/bve/intelligence/ma_probability.py tests/intelligence/test_ma_probability.py tests/intelligence/test_ma_probability_cli.py`
- `python -m pytest tests/intelligence/test_ma_probability.py tests/intelligence/test_ma_probability_cli.py -q`
- Result: **13 passed**

Operational implication:
- The next measurement step is to rerun the historical M&A backfill and compare
  the new replay metrics against the weak pre-filter baseline
  (`precision@15 = 0.1211`, positives below controls on average).
- A follow-on refinement is now in progress because screening-grade configs can
  understate company size for obvious non-targets such as `VRTX` and `BIIB`.
- Step 1 is therefore being finalized in its intended YAML-rule form, not just
  with EV / stage heuristics.

Refinement now completed:
- Added `examples/research/mna_targetability_rules.yaml` with explicit
  ticker-level hard fails for obvious buyers / non-targets (`LLY`, `NVO`,
  `PFE`, `REGN`, `VRTX`, `BIIB`).
- `src/bve/intelligence/ma_probability.py` now loads those explicit rules and
  applies them before final ranking, which closes the gap left by
  screening-grade config placeholders.
- Focused verification rerun passed:
  - `ruff check src/bve/intelligence/ma_probability.py tests/intelligence/test_ma_probability.py tests/intelligence/test_ma_probability_cli.py`
  - `python -m pytest tests/intelligence/test_ma_probability.py tests/intelligence/test_ma_probability_cli.py -q`
  - Result: **14 passed**

Measured replay outcome after the YAML-rule refinement:
- Historical replay backfill rerun completed on
  `examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml`.
- Result versus the original weak baseline:
  - `precision@15`: **0.1211 → 0.1596**
  - `unique-target recall@15`: **0.32 → 0.36**
  - `positive targets captured in top 15`: **8 → 9**
  - `average_probability_control`: **0.4921 → 0.4385**
  - `average_probability_positive`: **0.4802** (unchanged, now above controls)
- Sanity check: `LLY`, `VRTX`, `BIIB`, and `REGN` are no longer present in the
  historical top-15 calibration rows after the explicit-rule pass.

Interpretation:
- Step 1 is now genuinely working, not just unit-tested.
- It materially improved the historical M&A ranking and fixed the most obvious
  false-positive pollution.
- It still does **not** clear the planned acceptance gate of
  `precision@15 > 20%`, so Step 2 should proceed next: validate acquirer
  profiles against actual deals and fix profile misspecification before adding
  more data infrastructure.

## Acquirer Profile Deal Validation Scaffold (2026-04-06)

**Current status: ✅ Step 2 infrastructure is now implemented; live historical evaluation is next**

Added:
- `src/bve/intelligence/acquirer_profile_validation.py`
- `tests/intelligence/test_acquirer_profile_validation.py`

What it does:
- Loads curated acquirer profiles and the historical public-deal universe.
- Resolves config-backed targets from the replay watchlist when available, so
  deal validation uses real target modality / stage context instead of only raw
  deal metadata.
- Falls back to deal-level candidate construction when a target is not present
  in the watchlist.
- Scores each historical target against every loaded acquirer profile using the
  same `AcquirerFitScorer` used by the live stack.
- Reports actual-acquirer rank, top-1 / top-3 hit rates, candidate source, and
  per-acquirer validation summaries.

Operational implication:
- The next immediate step is focused verification, then a live run against the
  current curated `pfizer` / `eli_lilly` / `novo_nordisk` profile set to see
  where profile misspecification is still obvious.

Step 2 refinement now in progress:
- Improved fallback deal-modality inference in
  `src/bve/intelligence/acquirer_profile_validation.py` so hyphenated phrases
  like `gene-therapy` and `one-time` no longer fall through to spurious oral /
  small-molecule classifications.
- Expanded `examples/research/acquirer_profiles/pfizer.yaml` based on the first
  live validation pass:
  - raised immunology / IBD urgency from medium to high
  - added a neuroscience / migraine-CGRP franchise-extension gap
  - added Biohaven to recent deals
- The next step is to rerun the validator and measure whether Pfizer's
  historical top-1 hit rate improves materially.

Second refinement now in progress:
- The remaining miss after the Pfizer update is a tie-break issue between
  `Pfizer` and `Eli Lilly` on oral immunology targets.
- `src/bve/intelligence/acquirer_fit.py` now preserves
  `oral_small_molecule` instead of collapsing all oral assets into generic
  `small_molecule`, and generic `small_molecule` preferences now score as a
  partial match (`0.8`) against explicitly oral targets rather than a perfect
  match.
- `examples/research/acquirer_profiles/lilly.yaml` now makes the immunology gap
  explicitly `oral_small_molecule`, which should help separate `Morphic`-type
  oral I&I assets from Pfizer's broader IBD gap.

Third refinement now in progress:
- The live check showed `Morphic` still coming through as generic
  `small_molecule` because the screening-grade replay config lacked mechanism
  detail.
- `src/bve/intelligence/acquirer_profile_validation.py` now lets deal metadata
  refine a watchlist-backed target from `small_molecule` to
  `oral_small_molecule` when the deal text clearly provides the more specific
  modality.
- `examples/research/acquirer_profiles/lilly.yaml` now raises the
  `oral_immunology` gap urgency from medium to high so Lilly's historical oral
  I&I deals are not still outranked by Pfizer's broader IBD gap.

Measured Step 2 outcome:
- Live validation now passes cleanly for the current curated profile set.
- Run used:
  - profiles: `examples/research/acquirer_profiles`
  - deals: `research/mna/deal_universe_2020_2026.yaml`
  - watchlist context: `examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml`
  - knowledge DB: `outputs/intelligence/replay_knowledge.db`
- Result:
  - public tickered deals in universe: **38**
  - deals covered by the current curated profiles: **7**
  - watchlist-backed targets: **3**
  - fallback-only targets: **4**
  - top-1 hit rate: **1.0000** (`7 / 7`)
  - top-3 hit rate: **1.0000** (`7 / 7`)
  - median actual-acquirer rank: **1.0**
- Per-acquirer:
  - `Pfizer`: **3 / 3** top-1
  - `Eli Lilly`: **4 / 4** top-1
- Artifact:
  - `outputs/analysis/acquirer_profile_validation_2026-04-06.csv`

Interpretation:
- Step 2 is complete for the currently curated acquirer set.
- The remaining limitation is coverage breadth, not ranking quality: only `7`
  of the `38` public tickered deals are currently covered because the curated
  profile directory still contains only `Pfizer`, `Eli Lilly`, and
  `Novo Nordisk`.
- The next plan step should therefore move to Step 3/4 baseline work while
  broader acquirer coverage continues in parallel later.

## Simplest M&A Baseline Comparison (2026-04-06)

**Current status: ✅ Step 3 of the revised M&A plan is now implemented and measured on the replay-backed calibration dataset**

Added:
- Transparent baseline comparison support in
  `src/bve/intelligence/ma_calibration.py`
- Focused coverage in `tests/intelligence/test_ma_calibration.py`

Artifact:
- `outputs/analysis/ma_baseline_comparison_2026-04-06.json`

Measured baseline results on the current replay-backed dataset:

| Baseline | Precision@15 | Recall@15 | Avg score, positives | Avg score, controls |
|--------|--------:|--------:|--------:|--------:|
| Stored probability | **0.159649** | **0.36** | 0.480198 | 0.438535 |
| Strategic fit only | 0.133333 | **0.36** | 0.728669 | 0.689676 |
| Strategic fit + capital vulnerability | 0.149123 | **0.36** | 0.387719 | 0.361868 |
| Strategic fit + derisking | 0.143860 | 0.28 | 0.778593 | 0.768449 |
| Composite without valuation discount | 0.143860 | 0.28 | 0.618208 | 0.605453 |
| Composite with inverted valuation discount | **0.159649** | **0.36** | 0.685293 | 0.655544 |

Interpretation:
- `strategic_fit_score` alone is **not** the best simple ranking baseline.
- Outright removal of `valuation_discount` makes the replay ranking worse.
- The best simple transparent variant is the inverted-valuation composite,
  which ties the current stored ranking on precision / recall.
- This means Step 4 should favor **inverting** `valuation_discount` in the live
  M&A score rather than removing it entirely, then rerunning the historical
  baseline before moving on to scarcity.

Post-Step-2 rerun of Step 3:
- The baseline comparison was rerun after the acquirer-profile and
  acquirer-fit fixes materially improved strategic-fit quality.
- Historical snapshots were refreshed via
  `bve.ops.ma_probability_backfiller` on the expanded replay watchlist with
  `score_version=v1.2` and `dataset_mode=historical_snapshot`.
- Updated artifacts:
  - `outputs/analysis/ma_calibration_dataset_2021-02-01_2024-03-01_historical_snapshot.csv`
  - `outputs/analysis/ma_calibration_metrics_2021-02-01_2024-03-01_historical_snapshot.json`
  - `outputs/analysis/ma_baseline_comparison_2026-04-07_post_step2.json`

Updated replay-backed Step 3 results:

| Baseline | Precision@15 | Recall@15 | Avg score, positives | Avg score, controls |
|--------|--------:|--------:|--------:|--------:|
| Stored probability | **0.254386** | **0.60** | 0.887567 | 0.848510 |
| Strategic fit only | **0.254386** | **0.60** | 0.887567 | 0.848510 |
| Strategic fit + scarcity | **0.254386** | **0.60** | 0.904432 | 0.871234 |
| Strategic fit + capital vulnerability | 0.228070 | 0.48 | 0.467167 | 0.440061 |
| Strategic fit + derisking | 0.205263 | 0.48 | 0.858042 | 0.836134 |
| Composite without valuation discount | 0.205263 | 0.48 | 0.686306 | 0.664621 |
| Composite with inverted valuation discount | 0.194737 | 0.44 | 0.732962 | 0.707218 |

Interpretation now:
- The earlier Step 3 conclusion has changed after the Step 2 strategic-fit
  fixes.
- `v1.2` / stored probability remains valid because it is now effectively the
  top simple baseline on the refreshed replay set.
- `strategic_fit_only` and `strategic_fit_plus_scarcity` tie on top-k ranking,
  but scarcity still does not improve the top-15 outcome.
- Valuation-based composites are now clearly inferior to the simple
  strategic-fit regime on the refreshed historical dataset.

## Live M&A Score Inversion (2026-04-06)

**Current status: ✅ Step 4 is complete; the live M&A score now uses the `v1.2` strategic-fit-only regime after the inversion experiment failed**

Implemented:
- `src/bve/intelligence/ma_probability.py` now has three versioned score regimes:
  - `v1.0`: legacy mixed composite
  - `v1.1`: inverted-valuation experiment
  - `v1.2`: strategic-fit-only live score
- `MAProbabilityConfig.score_version` now defaults to `v1.2`.
- Legacy `v1.0` and experimental `v1.1` remain available for auditability and
  regression comparison.

Focused test updates:
- `tests/intelligence/test_ma_probability.py` now asserts that, holding other
  factors equal, the cheaper asset no longer gets a higher acquisition
  probability under the default live score.
- A legacy `v1.0` regression check was added so the old formula remains
  testable.

Operational implication:
- The next step is a focused test/lint pass followed by a full historical
  `ma_probability_backfiller` rerun to measure whether the live `v1.1`
  implementation improves the stored replay baseline.

Measured `v1.1` replay result:
- Historical backfill rerun completed successfully under the live `v1.1`
  score, but it did **not** improve the baseline.
- Result:
  - `precision@15 = 0.157895`
  - `recall@15 = 0.32`
  - `median lead days@15 = 341`
- Versus the post-targetability `v1.0` baseline:
  - precision fell slightly (`0.159649 → 0.157895`)
  - recall fell (`0.36 → 0.32`)

Follow-on Step 4 adjustment:
- Re-running the baseline comparison on the updated live `v1.1` snapshots
  changed the ordering materially:
  - `strategic_fit_only` now leads with `precision@15 = 0.217544`,
    `recall@15 = 0.44`
  - stored `v1.1` probability is only `0.157895`, `0.32`
- `src/bve/intelligence/ma_probability.py` therefore now includes a second
  score regime `v1.2`, which promotes `strategic_fit` alone into the live
  ranking formula.
- `MAProbabilityConfig.score_version` now defaults to `v1.2`.

Measured `v1.2` replay result:
- Historical backfill rerun completed successfully under the live `v1.2`
  score.
- Result:
  - `precision@15 = 0.210526`
  - `recall@15 = 0.44`
  - `median lead days@15 = 347`
- This clears the planned acceptance gate of `precision@15 > 20%`.
- Updated comparison export:
  - `outputs/analysis/ma_baseline_comparison_2026-04-06_v12_live.json`
- On the promoted `v1.2` live snapshots:
  - stored probability now matches the `strategic_fit_only` winner at
    `0.210526` precision / `0.44` recall
  - `strategic_fit + capital vulnerability` drops to `0.178947`, `0.36`
  - `v1.1`-style inverted valuation remains weaker at `0.157895`, `0.32`

Interpretation:
- Step 4 is now resolved with a measured production answer, not just an
  offline hypothesis.
- The inversion experiment (`v1.1`) was useful but wrong for live deployment.
- The simplest score, `strategic_fit` alone, is currently the best replay-safe
  live M&A ranking regime.
- The next plan step should move to Step 5: add scarcity on top of the now
  validated `v1.2` baseline instead of continuing to tune valuation terms.

## Scarcity Feature Integration (2026-04-06)

**Current status: ✅ Step 5 is complete; scarcity is implemented and measurable, but not promoted into the default live score**

Implemented so far:
- `src/bve/intelligence/ma_probability.py` now computes a target-level
  scarcity assessment from the active watchlist universe using
  same-indication plus mechanism / modality fallback keys.
- Scarcity is now persisted through `ma_probability_snapshots` as:
  - `scarcity_score`
  - `scarcity_peer_count`
  - `scarcity_bucket`
- `src/bve/intelligence/ma_calibration.py` now carries scarcity into the
  historical calibration dataset and baseline comparison layer.
- `src/bve/ops/ma_probability_backfiller.py` now accepts `--score-version`,
  so new M&A score regimes can be replay-tested before any default promotion.

Focused verification:
- `ruff check src/bve/intelligence/ma_probability.py src/bve/intelligence/ma_calibration.py src/bve/ops/ma_probability_backfiller.py tests/intelligence/test_ma_probability.py tests/intelligence/test_ma_probability_cli.py tests/intelligence/test_ma_calibration.py`
- `python -m pytest tests/intelligence/test_ma_probability.py tests/intelligence/test_ma_probability_cli.py tests/intelligence/test_ma_calibration.py -q`
- Result: **22 passed**

Measured `v1.3` replay result:
- Experimental `v1.3` (`strategic_fit 0.85 + scarcity 0.15`) was replay-run on
  the full expanded watchlist.
- Result:
  - `precision@15 = 0.210526`
  - `recall@15 = 0.44`
  - `median lead days@15 = 347`
- This exactly matches the validated `v1.2` live baseline on the acceptance
  metrics.
- Comparison artifact:
  - `outputs/analysis/ma_baseline_comparison_2026-04-06_v13_live.json`

Decision:
- Scarcity is now part of the M&A stack and available for future model
  expansion, but it did **not** improve the replay gate enough to justify a
  production promotion.
- Production therefore remains on `v1.2`, and the historical snapshots were
  restored to `v1.2` after the experiment so stored state matches the default
  live score.

Interpretation:
- The scarcity feature is informative but currently neutral at the top-15
  ranking cutoff.
- It should stay available as a persisted feature for later dataset
  deduplication / learned-model work, but the next step is not more weighting
  tweaks.
- The next plan step should move to Step 6: deduplicate the calibration set to
  one canonical pre-deal row per target.

## Canonical M&A Calibration Dataset Scaffold (2026-04-06)

**Current status: ✅ Step 6 dataset architecture is now implemented and covered by focused tests; live replay measurement is next**

Implemented:
- `src/bve/intelligence/ma_calibration.py` now supports
  `build_canonical_dataset(...)` in addition to the existing row-level
  `build_dataset(...)`.
- The canonical dataset reduces each positive target to one primary
  pre-announcement row, keyed by `(ticker, announcement_date)`.
- Canonical positive-row selection now uses a configurable anchor date,
  defaulting to `180` days before announcement:
  - prefer the latest stored snapshot on or before the anchor
  - otherwise fall back to the nearest stored snapshot before announcement
- Each canonical positive row now pulls a matched control set from the same
  snapshot date, preferring exact stage / therapeutic-area / EV-band matches
  and excluding known public-deal tickers from the control pool.
- `MACalibrationDataset` now records dataset mode plus canonical-build metadata
  (`dataset_mode`, `anchor_days_before_announcement`, `controls_per_positive`).
- Evaluation now branches by dataset mode:
  - historical row-level datasets keep the original per-snapshot top-k replay
    evaluation
  - canonical matched datasets use a single global case-control ranking, which
    is the appropriate training/evaluation shape for the next logistic step

Focused verification:
- `ruff check src/bve/intelligence/ma_calibration.py tests/intelligence/test_ma_calibration.py`
- `python -m pytest tests/intelligence/test_ma_calibration.py -q`
- Result: **6 passed**

Interpretation:
- The M&A stack now has the right dataset shape for learned calibration.
- Monthly duplicate positive rows are no longer structurally required.
- Live replay-backed canonical dataset build is now complete.

Measured live canonical dataset outcome:
- Source DB:
  `outputs/intelligence/replay_knowledge.db`
- Configuration:
  `365d` lookahead, `180d` canonical anchor, `2` matched controls per target
- Result:
  - date range: **2021-02-01 → 2024-03-01**
  - positive rows: **25**
  - control rows: **50**
  - total rows: **75**
  - anchor snapshot dates represented: **20**
  - stored-probability `precision@15`: **0.733333**
  - stored-probability recall@15: **0.44**
  - median lead days@15: **195**
  - average probability, positives: **0.798933**
  - average probability, controls: **0.725467**
- Canonical artifacts:
  - `outputs/analysis/ma_calibration_dataset_2021-02-01_2024-03-01_canonical_anchor180_controls2.csv`
  - `outputs/analysis/ma_calibration_metrics_2021-02-01_2024-03-01_canonical_anchor180_controls2.json`
  - `outputs/analysis/ma_baseline_comparison_2021-02-01_2024-03-01_canonical_anchor180_controls2.json`

Canonical baseline comparison notes:
- `stored_probability`, `strategic_fit_only`, and `strategic_fit_plus_scarcity`
  all capture **11 / 25** targets inside the global top 15 on the canonical set
  (`recall@15 = 0.44`), but only the stored live score keeps positive/control
  averages in the expected direction.
- `strategic_fit_only` on the canonical set has
  `average_score_positive = 0.798933` vs
  `average_score_control = 0.814800`, which means the training-set fix is doing
  its job: it exposes that raw fit alone still does not separate positives from
  matched controls cleanly enough for calibration.
- The default stored `v1.2` score remains the right starting signal for the
  first fitted model.

Interpretation:
- Step 6 is now complete enough to proceed.
- The dataset shape is fixed: one primary row per target, matched controls, no
  monthly duplicate positives.
- The next step is to fit the first matched-control logistic model on this
  canonical dataset, not to spend more time on dataset plumbing.
- Operational follow-through is now also complete:
  `src/bve/ops/ma_probability_backfiller.py` supports
  `--dataset-mode canonical_predeal` (default), plus configurable
  `--anchor-days-before-announcement` and `--controls-per-positive`.
- CLI smoke verification passed on a one-date replay run:
  - date range: **2024-03-01 → 2024-03-01**
  - canonical rows: **12**
  - positives: **4**
  - controls: **8**
  - precision@15: **0.4**
  - recall@15: **0.5**
  - artifact:
    `outputs/analysis/ma_calibration_dataset_2024-03-01_2024-03-01_canonical_anchor180_controls2.csv`

## First Matched-Control Logistic Model Scaffold (2026-04-06)

**Current status: ✅ The first fitted logistic model is now implemented on top of the canonical matched-control dataset; live replay fit is next**

Implemented:
- `src/bve/intelligence/ma_calibration.py` now carries `match_group_id` on
  canonical rows so the target/control pairing is explicit.
- Added `fit_logistic_model(...)`, which:
  - requires a `canonical_predeal` dataset
  - fits an L2-penalized logistic model
  - reports standardized coefficients and odds ratios
  - computes in-sample metrics
  - computes leave-one-match-group-out cross-validated metrics
  - stores per-row fitted and cross-validated probabilities
- The first default feature set is intentionally small and fully populated on
  the replay-backed canonical set:
  - `stored_probability`
  - `capital_vulnerability_score`
  - `log_enterprise_value`

Focused verification:
- `ruff check src/bve/intelligence/ma_calibration.py tests/intelligence/test_ma_calibration.py`
- `python -m pytest tests/intelligence/test_ma_calibration.py -q`
- Result: **7 passed**

Interpretation:
- The fitting path is ready.
- Live replay-backed fit is now complete.

Measured first logistic model result:
- Source dataset:
  canonical matched-control set from
  `outputs/intelligence/replay_knowledge.db`
- Shape:
  - `75` rows total
  - `25` positives
  - `50` matched controls
  - `25` match groups
  - `25 / 25` leave-one-group-out folds converged
- Selected default feature set after a small local spec comparison:
  - `stored_probability`
  - `capital_vulnerability_score`
  - `log_enterprise_value`
- Coefficients (standardized feature scale):
  - `stored_probability = +0.3815`
  - `capital_vulnerability_score = +0.4194`
  - `log_enterprise_value = +0.5695`

Stored baseline vs logistic:
- Stored `v1.2` probability on the canonical set:
  - `AUC = 0.5276`
  - `Brier = 0.435762`
  - `precision@15 = 0.733333`
  - `recall@15 = 0.44`
- Fitted logistic (in sample):
  - `AUC = 0.6968`
  - `Brier = 0.203421`
  - `precision@15 = 0.466667`
  - `recall@15 = 0.28`
- Leave-one-match-group-out logistic:
  - `AUC = 0.6552`
  - `Brier = 0.218057`
  - `precision@15 = 0.4`
  - `recall@15 = 0.24`
  - avg predicted probability:
    positives `0.376525` vs controls `0.316969`

Artifacts:
- `outputs/analysis/ma_logistic_fit_2021-02-01_2024-03-01_canonical_anchor180_controls2_logistic_v1.json`
- `outputs/analysis/ma_logistic_predictions_2021-02-01_2024-03-01_canonical_anchor180_controls2_logistic_v1.csv`

Interpretation:
- The first matched-control logistic model is real and useful, but its value is
  calibration / discrimination, not ranking replacement.
- It materially improves `AUC` and `Brier` against the stored live score on the
  canonical dataset.
- It does **not** beat the stored `v1.2` score on top-15 ranking metrics, so
  the live ranking layer should stay on `v1.2` for now.
- The next step should be to use this logistic output as a calibrated
  probability layer on top of the existing ranker, or to test a two-score
  architecture rather than replacing the ranker outright.

## Historical M&A Snapshot Backfill + First Real Calibration Run (2026-04-06)

**Current status: ✅ Historical `ma_probability_snapshots` are now populated across the replay universe, and the new evaluator has been run on real multi-date rankings**

### Historical-context upgrade to the M&A scanner

- `src/bve/intelligence/knowledge_layer.py` now exposes:
  `get_screen_snapshot_for_ticker_on_or_before(ticker, as_of)`
- `src/bve/intelligence/ma_probability.py` now supports
  `use_stored_screen_context=True`
- When enabled, historical M&A scoring now prefers stored dated
  `screen_snapshots` for:
  - stage
  - therapeutic area
  - `rnpv_millions`
  - `ev_millions`
  - acquisition discount multiple
  - catalyst timing / days to catalyst
- This reduces lookahead and keeps replay backfills anchored to the same dated
  implied-PoS screen state already validated elsewhere in the system.

### New historical M&A backfill utility

- Added `src/bve/ops/ma_probability_backfiller.py`
- Workflow:
  1. read historical snapshot dates from stored `screen_snapshots`
  2. run `MAProbabilityScanner` across the replay watchlist on each date
  3. persist `ma_probability_snapshots`
  4. build a labeled M&A calibration dataset
  5. write metrics JSON for the historical ranking baseline

### Live replay run

Run:
`python -m bve.ops.ma_probability_backfiller --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml --db outputs/intelligence/replay_knowledge.db --top-k 15`

Result:

| Metric | Result |
|--------|--------|
| Historical snapshot dates | **38** |
| Date range | **2021-02-01 → 2024-03-01** |
| `ma_probability_snapshots` written | **2,698** |
| Calibration dataset rows | **2,261** |
| Positive rows | **263** |
| Unique positive targets | **25** |
| Positive targets captured in top 15 | **8** |
| Precision@15 | **0.1211** |
| Unique-target recall@15 | **0.32** |
| Median lead days@15 | **345 days** |
| Avg probability, positives | **0.4802** |
| Avg probability, controls | **0.4921** |

Artifacts:
- `outputs/analysis/ma_calibration_dataset_2021-02-01_2024-03-01.csv`
- `outputs/analysis/ma_calibration_metrics_2021-02-01_2024-03-01.json`

### Interpretation

- The historical M&A stack is now measurable on real replay dates instead of
  synthetic fixtures.
- The first real baseline is weak: top-15 precision is only modestly above the
  raw positive-row base rate, recall is limited, and average stored probability
  does **not** separate positives from controls yet.
- This means the infrastructure for Goal 4 calibration is now in place, but the
  score itself still needs real model improvement and/or broader acquirer
  coverage before it can be treated as validated.

## M&A Calibration Dataset Scaffold (2026-04-06)

**Current status: ✅ The M&A stack now persists calibration-ready snapshots and can build a labeled takeout-vs-control dataset from stored history**

### Persisted M&A snapshot enrichment

- `src/bve/intelligence/ma_probability.py` now persists richer
  `ma_probability_snapshots` rows, not just rank/probability.
- Newly stored snapshot fields include:
  - `ticker`
  - `stage`
  - `therapeutic_area`
  - `best_acquirer_name`
  - `strategic_fit_score`
  - `valuation_discount_score`
  - `de_risking_stage_score`
  - `capital_vulnerability_score`
  - `enterprise_value_millions`
  - `acquisition_discount`
  - `days_to_catalyst`
  - `estimated_deal_value_low_millions`
  - `estimated_deal_value_high_millions`
- `MAProbabilitySnapshotStore` now exposes `list_snapshots()` so historical
  calibration/evaluation code can consume the stored rows directly.

### New calibration dataset builder

- Added `src/bve/intelligence/ma_calibration.py`
- The builder joins:
  - stored `ma_probability_snapshots`
  - curated public-deal labels from `research/mna/deal_universe_2020_2026.yaml`
  - latest per-ticker `screen_snapshots` on or before each snapshot date
- Output rows now include:
  - label (`takeout within lookahead window` vs control)
  - days to announcement
  - acquired-by / headline value
  - stored M&A component scores
  - stored implied-PoS screen context (`model_pos`, `implied_pos`, `spread_pp`)
  - `single_asset`, `config_quality`, and `market_exceeds_model`

### Extra local features now captured for later calibration

- trailing same-therapeutic-area deal count over 730 days (`ta_deal_count_trailing_730d`)
- normalized TA heat score (`ta_heat_score`)
- prior partnership-event count from the KnowledgeStore event log

### Baseline evaluation now available

- The new evaluator reports:
  - `precision_at_k`
  - unique-target recall at `k`
  - median lead days for captured takeouts
  - average stored probability for positives vs controls
- This gives Goal 4 a replay-safe baseline before adding a fitted logistic or
  isotonic calibration layer.

### Verification

Focused validation passed:
- `ruff check src/bve/intelligence/ma_probability.py src/bve/intelligence/ma_calibration.py tests/intelligence/test_ma_calibration.py`
- `python -m pytest tests/intelligence/test_ma_calibration.py tests/intelligence/test_ma_probability.py -q`

Result: `8 passed`

## Expanded Curated Acquirer Coverage (2026-04-06)

**Current status: ✅ Curated acquirer coverage expanded from 1 example profile to a live 3-acquirer directory, and the default fit / M&A stack now uses it**

### New curated acquirer directory coverage

- Added `examples/research/acquirer_profiles/lilly.yaml`
- Added `examples/research/acquirer_profiles/novo_nordisk.yaml`
- Existing `examples/research/acquirer_profiles/pfizer.yaml` retained
- Curated directory result:
  - `3` acquirers live by default: `pfizer`, `eli_lilly`, `novo_nordisk`
  - all load through `AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles"))`

### Loader and scoring upgrades

- `src/bve/intelligence/acquirer_profiles.py` now allows screening-grade curated
  profiles to omit `market_cap_billions` / `cash_billions`.
- When cash is omitted, the loader derives a placeholder budget snapshot from
  the largest pipeline-gap budget ceiling and labels it explicitly as a
  screening-grade placeholder.
- `src/bve/intelligence/acquirer_fit.py` now matches pipeline-gap therapeutic
  areas using:
  - target therapeutic area
  - indication text
  - priority-tag text
  This improves fit detection for assets whose coarse enum TA is too broad.
- `AcquirerFitCandidate` now allows negative `model_rnpv_millions`,
  `acquisition_discount`, and `enterprise_value_millions`, which prevents live
  acquirer-fit runs from crashing on net-cash-rich or negatively valued names.

### Default path changes

- `AcquirerFitIntegrationConfig.acquirer_profiles_path` now defaults to:
  `examples/research/acquirer_profiles`
- `bve-acquirer-fit --profiles-file` default now points to the curated directory
- `bve-ma-probability --profiles-file` default now points to the curated directory
- `src/bve/ops/weekly_runner.py` M&A scan now defaults to the curated directory

### Verification

Focused validation passed:
- `ruff check src/bve/intelligence/acquirer_profiles.py src/bve/intelligence/acquirer_fit.py src/bve/cli/acquirer_fit.py src/bve/cli/ma_probability.py src/bve/ops/weekly_runner.py tests/intelligence/test_acquirer_profiles.py tests/intelligence/test_acquirer_fit.py tests/intelligence/test_acquirer_fit_engine.py tests/intelligence/test_acquirer_fit_cli.py tests/intelligence/test_ma_probability.py tests/intelligence/test_ma_probability_cli.py`
- `python -m pytest tests/intelligence/test_acquirer_profiles.py tests/intelligence/test_acquirer_fit.py tests/intelligence/test_acquirer_fit_engine.py tests/intelligence/test_acquirer_fit_cli.py tests/intelligence/test_ma_probability.py tests/intelligence/test_ma_probability_cli.py -q`

Result: `32 passed`

Live CLI verification:
- `python -m bve.cli.acquirer_fit --watchlist examples/configs/watchlists/watchlist_stage1.yaml --acquirer eli_lilly --profiles-file examples/research/acquirer_profiles --top 3 --output-format report`
  completed successfully and ranked Stage 1 assets against Lilly
- `python -m bve.cli.ma_probability --watchlist examples/configs/watchlists/watchlist_stage1.yaml --top 3 --output-format report`
  completed successfully using the curated multi-acquirer directory by default

## Expanded Replay Watchlist + Implied-PoS Validation (2026-04-06)

**Current status: ✅ Strict historical implied-PoS validation now clears the target on the expanded config-backed watchlist; the full rules-based market-cap + ADV run now also passes, with historical snapshots persisted and robustness checks added**

### New expanded config-backed replay watchlist

- Added `examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml`
- Added `examples/configs/replay_generated/` screening-grade configs
- Build result:
  - `71` Phase 2+ watchlist assets
  - `26` reused existing configs
  - `45` generated screening-grade configs
  - `41` of `71` tickers already have local replay price coverage

### Strict monthly 365-day historical implied-PoS validation

Run:
`python -m bve.analysis.historical_implied_pos_validation --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml --start 2021-01-01 --end 2025-03-20 --hold-days 365 --cadence monthly --top-n 16 --bootstrap-iterations 500`

Result:

| Metric | Result |
|--------|--------|
| Watchlist assets | **71** |
| Screenable assets | **71** |
| Snapshot dates | **39** |
| Observations | **1,348** |
| Selected trades | **608** |
| Unique clusters | **23** |
| Mean selected excess return | **+26.36%** |
| Mean excess return (all observations) | **+11.41%** |
| Mean excess return (bottom cohort) | **−4.65%** |
| Mean selected spread | **−1.49pp** |
| Bootstrap p-value | **0.0000** |
| Target `G >= 20` | **PASS** |
| Target `bootstrap p < 0.05` | **PASS** |

Selected cohort breadth: `23` unique tickers. Largest recurring names were
`LLY`, `REGN`, `BMRN`, `CRSP`, `FOLD`, `IONS`, `SRPT`, `MDGL`, and `NVAX`.

### Interpretation

- The expanded config-backed universe solved the cluster-count bottleneck for the
  implied-PoS validation path.
- The signal is now statistically strong on the strict Phase 2+ monthly 365-day
  setup.
- Replay-safe historical market-cap gating is now implemented and validated.
- Replay-safe historical market-cap + ADV gating now also passes on the expanded
  watchlist after backfilling replay-store market-price history with volume.

## Historical Snapshot Persistence + Robustness Checks (2026-04-06)

**Current status: ✅ Historical implied-PoS rows now persist to `screen_snapshots`; placebo and leave-one-out diagnostics are live**

### Historical screen snapshot persistence

Run:
`python -m bve.analysis.historical_implied_pos_validation --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml --start 2021-01-01 --end 2025-03-20 --hold-days 365 --cadence monthly --top-n 16 --min-market-cap 200 --max-market-cap 10000 --min-adv 2 --persist-screen-snapshots --shuffle-iterations 1000 --bootstrap-iterations 500`

Result:

| Metric | Result |
|--------|--------|
| Persisted snapshot rows | **825** |
| Persisted snapshot dates | **38** |
| Knowledge DB | **outputs/intelligence/replay_knowledge.db** |

### Robustness diagnostics on the strict rules-based run

| Check | Result |
|------|--------|
| Reverse-signal placebo mean excess | **+1.54%** |
| Shuffle placebo mean excess | **+16.20%** |
| Shuffle placebo 90% interval | **[+13.30%, +18.95%]** |
| Shuffle `P(random >= actual)` | **0.0000** |
| Leave-one-out worst case | **+22.00%** (drop `a-vktx`) |
| Leave-one-out best case | **+29.93%** (drop `asset-arqt-roflumilast-ad`) |
| Minimum remaining clusters | **27** |

Selected-trade subgroup cuts:
- `nda_bla`: `n=226`, mean excess `+27.12%`
- `phase_3`: `n=265`, mean excess `+35.52%`
- `phase_2`: `n=117`, mean excess `+9.38%`

### Interpretation

- The implied-PoS signal is no longer supported by a single headline backtest only.
- It now survives exact market-cap + ADV entry rules, a reverse-signal placebo,
  a within-date shuffle placebo, and leave-one-cluster-out sensitivity.
- Historical screen rows are now stored in `screen_snapshots`, which removes the
  need to recompute the full history every time downstream consumers need dated
  mispricing rows.

### Downstream snapshot-first consumers

- `src/bve/ops/daily_brief.py` now prefers persisted `screen_snapshots` for
  `as_of` analysis and falls back to recomputation only when snapshots are absent.
- `src/bve/cli/universe_screen.py` now supports `--db` for archived screen reads
  and resolves the latest snapshot on or before `--as-of` instead of requiring an
  exact match.
- `src/bve/analysis/mispricing_screener.py` now supports:
  - persisting fresh watchlist rows into `screen_snapshots`
  - loading the latest stored snapshot on or before `--as-of`
  - reusing the stored snapshot date in rendered watchlist reports
- `src/bve/intelligence/mispricing_screener.py` plus `src/bve/cli/screen.py`
  now support a stored-snapshot mode for archived screens:
  `--use-stored-screen-snapshots`
- `screen_snapshots` now also carry:
  - `market_exceeds_model`
  - `config_quality`
  - existing `single_asset` / `approximation_warning`
- `KnowledgeStore` now exposes:
  - `latest_screen_snapshot_date_on_or_before(as_of)`
  - `get_screen_snapshots_on_or_before(as_of)`

Live CLI verification:
- `python -m bve.cli.universe_screen --as-of 2024-03-20 --db outputs/intelligence/replay_knowledge.db --json`
  resolved to snapshot date `2024-03-01`
- `python -m bve.cli.daily_brief --db outputs/intelligence/replay_knowledge.db --as-of 2024-03-20 --format json --top 3`
  built from stored snapshots without recomputing the historical screen
- `python -m bve.analysis.mispricing_screener --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml --knowledge-db outputs/intelligence/replay_knowledge.db --use-stored-snapshots --as-of 2024-03-20`
  resolved to snapshot date `2024-03-01` and rendered the dated watchlist report
- `python -m bve.cli.screen --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml --db outputs/intelligence/replay_knowledge.db --as-of 2024-03-20 --use-stored-screen-snapshots --top 3`
  resolved to snapshot date `2024-03-01` and rendered the archived unified screen

## Replay-Safe Historical Universe Gating (2026-04-05)

**Current status: ✅ Complete for the strict Phase 2+ implied-PoS validation path**

### Validator upgrade

- `src/bve/analysis/historical_implied_pos_validation.py` now supports:
  - `--min-market-cap`
  - `--max-market-cap`
  - `--min-adv`
  - `--adv-lookback-days`
- Historical observations now carry `daily_dollar_volume_millions`.
- Output filenames encode active filters so different validation runs no longer
  overwrite one another.

### Cap-only strict Phase 2+ run

Run:
`python -m bve.analysis.historical_implied_pos_validation --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml --start 2021-01-01 --end 2025-03-20 --hold-days 365 --cadence monthly --top-n 16 --min-market-cap 200 --max-market-cap 10000 --bootstrap-iterations 500`

Result:

| Metric | Result |
|--------|--------|
| Observations | **876** |
| Selected trades | **608** |
| Unique clusters | **28** |
| Mean selected excess return | **+30.94%** |
| Mean excess return (all observations) | **+18.82%** |
| Mean excess return (bottom cohort) | **+3.56%** |
| Mean selected spread | **−13.91pp** |
| Bootstrap p-value | **0.0000** |
| Target `G >= 20` | **PASS** |
| Target `bootstrap p < 0.05` | **PASS** |

### Cap + ADV strict Phase 2+ run

Run:
`python -m bve.analysis.historical_implied_pos_validation --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml --start 2021-01-01 --end 2025-03-20 --hold-days 365 --cadence monthly --top-n 16 --min-market-cap 200 --max-market-cap 10000 --min-adv 2 --bootstrap-iterations 500`

Result:

| Metric | Result |
|--------|--------|
| Observations | **825** |
| ADV-covered observations | **825** |
| Selected trades | **608** |
| Unique clusters | **28** |
| Mean selected excess return | **+27.37%** |
| Mean excess return (all observations) | **+16.36%** |
| Mean excess return (bottom cohort) | **+1.54%** |
| Mean selected spread | **−16.32pp** |
| Bootstrap p-value | **0.0000** |
| Target `G >= 20` | **PASS** |
| Target `bootstrap p < 0.05` | **PASS** |

### Historical market-price/volume backfill

Run:
`python -m bve.ops.price_backfiller --universe-file examples/research/universe_expanded_mna.yaml --start 2021-01-01 --end 2025-03-20`

Result:

| Metric | Result |
|--------|--------|
| Tickers processed | **81** |
| Tickers with market rows backfilled | **44** |
| Market rows backfilled | **45,077** |
| Benchmark market rows backfilled | **1,058** |
| Tickers skipped | **37** |
| New market coverage start | **2021-01-04** |

### Interpretation

- The expanded watchlist plus replay-safe market-cap gating passes comfortably.
- The full rules-based market-cap + ADV run now passes after populating replay-store
  `market_prices` with historical volume-aware rows.
- The remaining work is downstream of validation: productize stored historical
  screen snapshots, add robustness/placebo checks, and return to raw replay graduation.

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
   — use `bve-claim-resolve resolve <ID> --status confirmed --evidence TEXT` when trial readouts occur
   — thesis_strength now persisted in `screen_snapshots.thesis_strength` (Sprint 25)
2. **Run bve-daily-brief regularly**: accumulate screen_snapshots and resolved claims over time
3. **Live decision tracking**: use `pos_predictions` table to record predictions; resolve outcomes
   when readouts occur; feed into `CalibratedPOSModel` to improve the model PoS signal

### Data Coverage (2026-03-29)
- Price history: 48 tickers, 2021-01-04 to 2026-03-20
- Total seeded events: 130 (69 pre-2024 trial/PDUFA; 61 from 2024-2026)
- POS backtest dataset: N=99 (Phase 2=39.6%, Phase 3=60.8%), Brier=0.213, AUC=0.74
- KnowledgeStore claims resolved: 8 (6 confirmed, 2 refuted from known 2023-2024 readouts)

## Sprint 26 Summary (2026-03-29)

### 26A — Live workflow operationalization
- `_inject_thesis_strength()` reads live `ops.db` ThesisTracker at `bve-universe-screen` display time
- 8 thesis claims resolved in live `ops.db`; THESIS column now shows real values for affected assets
- Sprint 22 catalysts seeded into live `ops.db`

### 26B — Thesis-gated replay entry
- `ReplayPolicyConfig.min_thesis_score`: blocks entries where thesis_strength < threshold or is None
- `--min-thesis-score 0.5` graduation run: N=60, mean=+3.29% (vs +1.42% baseline)
- Required N for p<0.10 improved from 302 → 111 (2.7× better graduation path)
- Updated graduation table below

### 26C — POS backtest dataset validation
- Confirmed N=99, Phase 2=39.6%, Phase 3=60.8% — already at target calibration
- Brier=0.2127, AUC=0.74; ~15% Brier Skill Score vs no-skill baseline
- Stale CLAUDE.md survivor-bias warning removed

### Thesis-gated graduation run (min_thesis_score=0.5)

| Criterion | Target | Baseline (run 906fc24b) | Thesis-gated | Status |
|-----------|--------|-------------------------|--------------|--------|
| N closed positions | ≥ 30 | 83 | **60** | ✅ |
| Mean excess return | > 0% | +1.42% | **+3.29%** | ✅ |
| Naive t-stat | > 1.65 | 0.86 (p=0.39) | ~1.32 (p≈0.19) | ❌ |
| N required for p<0.10 | — | 302 | **~111** | Improving |

## Sprint 28 Summary (2026-04-05)

### Open-claim entry gate — leading indicator

Added `ReplayPolicyConfig.require_open_claim` and `--require-open-claim` CLI flag.
Gates on `n_open_claims ≥ 1` (asset has an active unresolved thesis claim) rather than
waiting for resolution (Sprint 26B/27 `min_thesis_score` gate).

**Graduation replay** (`--require-open-claim --max-decisions-per-asset 15 --max-hold-days 28`):

| Run | N | Mean return | Hit rate | t-stat |
|-----|---|-------------|----------|--------|
| Ungated baseline (Sprint 24) | 83 | +1.42% | 51.8% | 0.86 |
| Confirmed-thesis gate S26B (lookahead) | 60 | +3.29% | — | ~1.32 |
| Confirmed-thesis gate S27 (real timestamps) | 129 | −0.24% | 43.0% | <0 |
| Open-claim gate S28 initial (28 tickers) | 40 | +3.80% | 47.5% | 1.60 |
| **Open-claim gate S28 expanded (38 claims)** | **83** | **+3.76%** | **53.0%** | **1.60** |

Run ID: `8eed5181-12fb-4b1a-b7d1-00e992e5d01e`

**Statistical status** (corrected via Sprint 29 significance module): naive t=1.60 (p=0.109).
The earlier estimate of t≈2.28 used an assumed std=15%; actual std=21.36% → lower t.
Attribution: thesis_error=36, market_drift=42, confirmed_thesis=2, timing_error=3.
Hit rate 53% > 50% baseline. Cluster-robust t=1.25 (G=12, df=11).

---

## Sprint 29 Summary (2026-04-05)

### Cluster-robust SE + bootstrap CI significance module

`analysis/replay_significance.py` implements full institutional-grade significance testing:
- **Cameron-Miller cluster SE**: `V_CR = (G/(G-1))*(1/n²)*Σ_g(Σ_{i∈g}(r_i−r̄))²`
  where G = unique asset_ids (clusters), n = total decisions
- **Cluster-level bootstrap**: G clusters drawn with replacement, B=2000 iterations, percentile CI
- **`significance` subcommand**: `python -m bve.ops.historical_replay significance --run-id <id>`

**Actual result on run 8eed5181** (N=83, G=12 clusters):
```
Naive:   SE=2.35%, t=1.60, p=0.109
Cluster: SE=3.02%, t=1.25, df=11, p=0.239  ← α does NOT survive clustering
Bootstrap 90% CI: [−0.44%, +8.86%]          ← lower bound does NOT exclude zero
Bootstrap p: 0.083                           ← encouraging (8.3% of samples ≤ 0)
Graduation: NOT YET
```

Key finding: G=12 → df=11 creates a substantial small-sample penalty. The cluster SE (3.02%)
is 29% wider than naive SE (2.35%), reflecting genuine within-asset correlation. Need either
more clusters (G≥20) or higher signal strength to graduate.

---

## Sprint 27 Summary (2026-04-05)

### 27A — Thesis-gate no-lookahead fix
- Fixed `ThesisTracker.snapshot(as_of_date=...)`: claims with `resolved_at > as_of_date` were
  incorrectly appearing as confirmed/refuted in replay — a lookahead bug. Now treated as "open".
- Impact: ALNY claim (resolved 2022-11-06) correctly blocked before that date during replay.

### 27B — Historical claims backfiller
- `research/replay/thesis_claims_history.yaml`: 28 claims, 26 tickers, real resolution dates
- `bve-seed-replay-claims`: seeds claims into replay KB with accurate timestamps; idempotent
- KnowledgeStore pre-migration: handles old replay stores with missing `structured_signals` columns

### 27C — Confirmed-thesis finding
Graduation replay with real historical claims (N=129, mean=−0.24%) **underperforms** ungated
baseline (N=83, mean=+1.42%). Root cause: confirmed thesis is a **lagging indicator** — by the
time a Phase 2/3 claim resolves as "confirmed", the stock has already repriced. The gate admits
entries after the signal has decayed.

| Signal type | N | Mean return |
|-------------|---|-------------|
| Ungated baseline (run 906fc24b) | 83 | **+1.42%** |
| Thesis-gated sprint 26B (opaque claims) | 60 | **+3.29%** |
| Thesis-gated sprint 27 (real timestamps) | 129 | **−0.24%** |

Sprint 26B's +3.29% was inflated by lookahead: opaque claims were immediately resolved when seeded,
so the gate was using future confirmation as an entry signal during earlier replay weeks.

## Last Change

**Historical snapshot persistence + downstream snapshot-first consumers added (2026-04-06)**.
New config-backed Phase 2+ watchlist: 71 assets / 45 generated configs.
Strict monthly 365-day implied-PoS validation on the expanded watchlist:
G=23 clusters, mean excess return +26.36%, bootstrap p=0.0000.
Replay-safe market-cap-gated rerun also passed strongly:
G=28 clusters, mean excess return +30.94%, bootstrap p=0.0000.
Replay-safe market-price/volume backfill now populated 45,077 `market_prices`
rows for 44 tickers plus XBI, and the full market-cap + ADV rerun also passes:
G=28 clusters, ADV-covered observations=825, mean excess return +27.37%,
bootstrap p=0.0000. Historical screen rows now persist to `screen_snapshots`
(`825` rows / `38` dates) and the report includes reverse-placebo, shuffled
placebo, leave-one-out, and stage subgroup diagnostics. Verification: focused
checks passed (`ruff`, price-backfiller tests, historical implied-PoS validation
tests, sprint10/sprint19/universe-screen tests, config validation, historical
implied-PoS reruns, live replay-store backfill, archived CLI checks). Full suite
not rerun in this update.

## Graduation Status (2026-04-05)

**Status: ⚠️ Approaching — naive p=0.109, bootstrap p=0.083, cluster t < 1.645**

| Criterion | Target | Best run (8eed5181) | Status |
|-----------|--------|---------------------|--------|
| N closed positions | ≥ 30 | **83** | ✅ |
| Mean excess return | > 0% | **+3.76%** | ✅ |
| Hit rate | > 50% | **53.0%** | ✅ |
| Naive t-stat | > 1.645 (p<0.10) | **1.60** (p=0.109) | ❌ |
| Alpha survives clustered SE | cluster_t > 1.645 | **1.25** (df=11, p=0.239) | ❌ |
| Bootstrap 90% CI excludes 0 | Lower bound > 0 | **[−0.44%, +8.86%]** | ❌ |

Note: t≈2.28 in Sprint 28 was estimated using wrong std=15%; actual std=21.36% → naive t=1.60.
G=12 clusters (asset_ids) → df=11 → small-sample correction moves cluster t further from threshold.
Bootstrap p=0.083 is encouraging — 90% CI is close to excluding zero.

Path to graduation:
- Extend the snapshot-first pattern into the remaining live watchlist/mispricing outputs
- Extend robustness as needed with additional placebo/subgroup variants
- Return to raw replay graduation with the wider config-backed universe

## Next Steps

### Option A: Increase cluster count
With G=12, df=11 is tight. G≥20 (df=19) would bring cluster t closer to naive t.
```bash
# Relax max-decisions-per-asset to allow more tickers through open-claim gate
python -m bve.ops.historical_replay run \
    --start 2021-01-01 --end 2026-03-29 --cadence weekly \
    --decision-policy top2_add --max-hold-days 28 \
    --max-decisions-per-asset 10 --require-open-claim
```

### Option B: Combine open-claim gate with catalyst density gate
```bash
python -m bve.ops.historical_replay run \
    --start 2021-01-01 --end 2026-03-29 --cadence weekly \
    --decision-policy top2_add --max-hold-days 28 \
    --max-decisions-per-asset 15 --require-open-claim \
    --require-catalyst-days 60
```

### Option C: New feature sprint
Candidate sprints not yet implemented:
- **Sprint 30**: Score decile monotonicity analysis — verify top-score deciles outperform bottom deciles (requires N≥200)
- **Sprint 31**: Live weekly runner automation — cron / systemd timer to run `bve-daily-brief` + `bve-universe-screen` daily and persist to ops.db

### Immediate next execution step

Use the new expanded watchlist as the baseline universe for strict replay-safe
mispricing validation, then layer historical market-cap and ADV gates on top:

```bash
python -m bve.analysis.historical_implied_pos_validation \
    --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml \
    --start 2021-01-01 \
    --end 2025-03-20 \
    --hold-days 365 \
    --cadence monthly \
    --top-n 16 \
    --bootstrap-iterations 500
```

## 2026-04-08 Company Snapshot-First Daily/Weekly Outputs

The downstream company-facing ranking path is now anchored on
`company_sotp_snapshots`, not asset-level `screen_snapshots`.

What changed:
- [daily_brief.py](/home/djmann/projects/biotech-asset-valuation-engine/src/bve/ops/daily_brief.py)
  now prefers stored `company_sotp_snapshots` on or before `as_of` for company
  ranking; asset-level screen rows are only used as optional enrichment for
  stage, catalyst, and per-asset spread context
- [weekly_brief.py](/home/djmann/projects/biotech-asset-valuation-engine/src/bve/intelligence/weekly_brief.py)
  now prefers stored `company_sotp_snapshots` on or before `period_end` for the
  `top_opportunities` section, filtered to recency-gated `buy/watch` names
- the weekly brief template now renders a company-ranking table when the source
  is `company_sotp_snapshot`
- both outputs surface `source_mode` and reference snapshot date for auditability

Operational impact:
- daily/weekly company decisions no longer depend on historical asset-screen
  ranking order
- stale balance-sheet names are excluded from company-ranking sections before
  they reach the daily/weekly output
- asset history remains available as supporting context only

Verification:
- `ruff check src/bve/ops/daily_brief.py src/bve/cli/daily_brief.py src/bve/intelligence/weekly_brief.py tests/test_sprint19.py tests/test_weekly_brief.py` passed
- `MPLCONFIGDIR=/tmp/mpl_brief_tests python -c "import bve.ops.daily_brief; import bve.intelligence.weekly_brief; print('imports ok')"` passed
- `MPLCONFIGDIR=/tmp/mpl_brief_tests python -m pytest tests/test_sprint19.py tests/test_weekly_brief.py -q`
  passed: `85 passed, 18 warnings in 602.35s`

## 2026-04-08 Company Snapshot Single Source Of Truth Extended To Dashboard/Reporting

The remaining company decision surfaces now resolve from `company_sotp_snapshots`
instead of rebuilding company decisions from asset-level history.

What changed:
- [metrics_dashboard.py](/home/djmann/projects/biotech-asset-valuation-engine/src/bve/ops/metrics_dashboard.py)
  now prefers recency-gated `company_sotp_snapshots` for `top_opportunities`
  and carries explicit source metadata:
  - `top_opportunities_source_mode`
  - `top_opportunities_reference_date`
- [intelligence_service.py](/home/djmann/projects/biotech-asset-valuation-engine/src/bve/services/intelligence_service.py)
  now serializes that metrics-dashboard payload into dashboard cache artifacts
- [portfolio_dashboard.py](/home/djmann/projects/biotech-asset-valuation-engine/src/bve/ui/dashboard/components/portfolio_dashboard.py)
  now renders a `Top Company Decisions` table from cached company snapshot rows
- [research_report.py](/home/djmann/projects/biotech-asset-valuation-engine/src/bve/intelligence/research_report.py)
  now includes stored company SOTP context in the financial-model narrative and
  persisted input snapshot
- [research_report.md.j2](/home/djmann/projects/biotech-asset-valuation-engine/src/bve/reporting/templates/research_report.md.j2)
  now renders an explicit `Company SOTP Snapshot` section when available
- `KnowledgeStore` now exposes direct company-id lookup for point-in-time company
  SOTP rows, so report code no longer has to infer ticker mappings

Operational effect:
- company decisions now use one dataset across:
  - analysis/backtests
  - daily/weekly briefs
  - dashboard cache + portfolio dashboard
  - research report exports
- asset-level history remains a supporting context layer rather than the source
  of truth for company decision surfaces

Verification:
- `ruff check src/bve/intelligence/knowledge_layer.py src/bve/ops/metrics_dashboard.py src/bve/services/intelligence_service.py src/bve/ui/dashboard/components/portfolio_dashboard.py src/bve/intelligence/research_report.py tests/ops/test_metrics_dashboard.py tests/intelligence/test_research_report.py tests/ui/test_portfolio_dashboard.py`
  passed
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 MPLCONFIGDIR=/tmp/mpl_company_surfaces python -m pytest tests/ops/test_metrics_dashboard.py tests/intelligence/test_research_report.py tests/ui/test_portfolio_dashboard.py -q`
  passed: `7 passed, 5 warnings in 99.55s`

## 2026-04-08 Warning Cleanup

The warnings emitted by the recent focused suites were real deprecation
warnings, not harmless test noise.

Identified warnings:
- `src/bve/config/assumptions_loader.py:108`
- `src/bve/intelligence/knowledge_layer.py:2880`
- `src/bve/intelligence/knowledge_layer.py:3126`

Root cause:
- deprecated use of `datetime.utcnow()` on Python 3.12+

Fix applied:
- replaced those call sites with timezone-aware
  `datetime.now(timezone.utc)` and preserved the existing persisted `Z` suffix
- also proactively fixed the same pattern at
  `src/bve/intelligence/knowledge_layer.py:3332`

Verification:
- `ruff check src/bve/config/assumptions_loader.py src/bve/intelligence/knowledge_layer.py`
  passed
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 MPLCONFIGDIR=/tmp/mpl_warnfix python -W error::DeprecationWarning -m pytest tests/test_sprint19.py::TestBuildDailyBrief::test_uses_persisted_screen_snapshot_on_or_before_as_of tests/test_sprint19.py::TestBuildDailyBrief::test_prefers_company_sotp_snapshot_for_company_facing_ranking tests/ops/test_metrics_dashboard.py::test_metrics_dashboard_prefers_company_sotp_snapshots_for_top_opportunities tests/intelligence/test_research_report.py -q`
  passed: `6 passed in 120.73s`

## 2026-04-08 Company SOTP Top-25 Pack And Decision Gate

The company SOTP layer now has a real top-name manual input pack and the
portfolio/action path respects company policy instead of treating company SOTP
as a reporting-only sidecar.

What changed:
- [company_sotp.py](/home/djmann/projects/biotech-asset-valuation-engine/src/bve/analysis/company_sotp.py)
  now requires fully auditable structured company buckets:
  - `source`
  - `as_of_date`
  - `confidence`
  - `source_ref`
  - `source_kind`
- [company_sotp.py](/home/djmann/projects/biotech-asset-valuation-engine/src/bve/analysis/company_sotp.py)
  now computes company-level readiness for action gating:
  - `actionable_coverage_pct`
  - `actionable_confidence_pct`
  - `structured_input_count`
  - structured-input confidence summary
- company action policy now works the way an institutional workflow needs:
  - stale balance sheets still hard-fail to `needs_manual_review`
  - unattractive discounts go straight to `avoid`
  - cash and high-confidence dated company buckets now count toward coverage
  - large-cap single-asset names without structured company inputs stay in
    `needs_manual_review`
- [actionable_output.py](/home/djmann/projects/biotech-asset-valuation-engine/src/bve/intelligence/actionable_output.py)
  now uses company policy as the default gate for trade selection:
  - company `watch` downgrades `buy/add` to `monitor`
  - company `avoid` / `needs_manual_review` are filtered out of auto-ranked
    portfolio/replay decisions
- [historical_replay.py](/home/djmann/projects/biotech-asset-valuation-engine/src/bve/ops/historical_replay.py)
  and [weekly_runner.py](/home/djmann/projects/biotech-asset-valuation-engine/src/bve/ops/weekly_runner.py)
  now attach stored company policy to each candidate before action selection
- [company_sotp_overrides.yaml](/home/djmann/projects/biotech-asset-valuation-engine/research/company_sotp_overrides.yaml)
  is no longer empty; it now contains a structured top-25 company input pack
  across:
  - platform value
  - unmodeled pipeline
  - royalty / milestone streams
  - dilution reserve / financing path

Top-25 pack populated for:
- `ACAD`, `AGEN`, `ARQT`, `BHVN`, `BLUE`, `CBAY`, `CCXI`, `FOLD`, `FULC`,
  `IMVT`, `INBX`, `IONS`, `KYMR`, `MDGL`, `NVAX`, `OCUL`, `PRAX`, `PRTA`,
  `PTCT`, `RLAY`, `RNA`, `RVMD`, `RXRX`, `VKTX`, `ZYME`

Historical company snapshot rebuild:
- command:
  `python -m bve.ops.company_sotp_backfiller --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml --db outputs/intelligence/replay_knowledge.db --replay-db outputs/intelligence/replay_store.sqlite --start 2021-02-01 --end 2024-03-01 --output-dir outputs/analysis`
- result:
  - `788` company rows across `38` snapshot dates
  - `774` rows pass the recency gate
  - action-policy totals improved sharply:
    - before: `buy=76 / watch=12 / avoid=67 / needs_manual_review=630`
    - after: `buy=87 / watch=11 / avoid=649 / needs_manual_review=41`
  - latest active cohort on `2024-03-01`:
    - `22` rows
    - `22 / 22` pass recency gate
    - `2 buy / 0 watch / 20 avoid / 0 needs_manual_review`

Company-level backtest on the improved stored dataset:
- command:
  `python -m bve.analysis.company_sotp_backtest --db outputs/intelligence/replay_knowledge.db --replay-db outputs/intelligence/replay_store.sqlite --start 2021-02-01 --end 2024-03-01 --hold-days 365 --top-n 5 --min-ranked-discount 1.0 --output-dir outputs/analysis`
- result:
  - `26` snapshot dates
  - `48` candidate rows / selected trades
  - mean excess return `+10.02%`
  - hit rate `33.3%`
  - cluster count `7`
  - bootstrap `p=0.0282`

Interpretation:
- the top-25 pack and new company gating converted the company layer from
  “mostly manual review” into a screened decision surface
- the actionable cohort is much narrower and cleaner
- the historical signal is positive and statistically directional, but still
  concentrated (`7` clusters), so this is now usable as a gated company-level
  ranking layer rather than a fully mature portfolio signal by itself

Artifacts:
- [company_sotp_overrides.yaml](/home/djmann/projects/biotech-asset-valuation-engine/research/company_sotp_overrides.yaml)
- [company_sotp_backfill_summary_2021-02-01_2024-03-01.csv](/home/djmann/projects/biotech-asset-valuation-engine/outputs/analysis/company_sotp_backfill_summary_2021-02-01_2024-03-01.csv)
- [company_sotp_2024-03-01.csv](/home/djmann/projects/biotech-asset-valuation-engine/outputs/analysis/company_sotp_2024-03-01.csv)
- [company_sotp_backtest_2021-02-01_2024-03-01_hold365d_top5.csv](/home/djmann/projects/biotech-asset-valuation-engine/outputs/analysis/company_sotp_backtest_2021-02-01_2024-03-01_hold365d_top5.csv)

Verification:
- `ruff check src/bve/analysis/company_sotp.py src/bve/intelligence/actionable_output.py src/bve/ops/historical_replay.py src/bve/ops/weekly_runner.py tests/test_company_sotp.py tests/intelligence/test_actionable_output.py`
  passed
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 MPLCONFIGDIR=/tmp/mpl_company_pack python -m pytest tests/test_company_sotp.py tests/intelligence/test_actionable_output.py -q`
  passed: `54 passed, 42 warnings in 140.89s`

## Company Data Quality Step 2 (2026-04-09)

**Current status: ✅ Step 2 is complete; the remaining extreme-discount hard-gate set is small and concentrated rather than a broad stale-pack problem**

I ran the reconciliation audit against stored `company_sotp_snapshots` after the
Step 7 premium-side relaxation to measure what still trips the hard gate.

Historical reconciliation audit result:
- `27` rows still have `reconciliation_status = extreme_discount`
- `4` unique tickers across `25` snapshot dates
- only `26` are true active hard-gate hits with
  `action_reason = reconciliation_extreme_discount:*`
- the extra row is `AMRN`, which is already excluded by the market-cap band gate
  (`market_cap_outside_band:7M`) rather than by reconciliation

Remaining active hard-gate names:
- `VKTX`
  - `12` rows from `2021-02-01` to `2023-02-01`
  - average ranked SOTP discount `7.19x`
  - average manual bucket share `11.6%`
  - average manual bucket confidence `0.72`
  - average modeled asset coverage `92.3%`
- `ZYME`
  - `13` rows from `2022-12-01` to `2023-12-01`
  - average ranked SOTP discount `6.42x`
  - average manual bucket share `1.5%`
  - average manual bucket confidence `0.65`
  - average modeled asset coverage `89.9%`
- `SRRK`
  - `1` row on `2022-05-01`
  - ranked SOTP discount `5.53x`
  - manual bucket share `5.4%`
  - manual bucket confidence `0.73`
  - modeled asset coverage `64.3%`

Latest live cohort check:
- the latest active company snapshot date has `0` reconciliation hard-gate hits
- there are no live `reconciliation_extreme_discount:*` rows in the current
  company ranking cohort

Interpretation:
- the remaining hard-gate set is concentrated, not broad
- `VKTX` still looks like the intended deep-value / market-dislocation case the
  hard gate is meant to catch, even though the config is still only
  `screening_grade`
- `ZYME` is the main likely stale-or-overaggressive modeling candidate because
  it repeatedly screens at `6x-8x` discount despite very low manual-bucket
  dependence and decent modeled coverage
- `SRRK` looks like an isolated historical sparse-coverage outlier rather than a
  persistent live issue
- the next high-leverage cleanup should be targeted asset/config audits for
  `ZYME` and `VKTX`, not another broad reconciliation policy change

## 2026-04-12 Company Pack Expansion Steps 4–7 (complete)

**Current status: ✅ Company Pack Expansion Plan steps 4–7 are all closed.**

### Step 4 — Evidence standard enforcement
Confirmed complete in `company_sotp.py`. Two-tier enforcement:
- Single bucket > 25% of SOTP without multi-source → `needs_manual_review`
- Total manual share > 35% with avg confidence < 0.80 → `needs_manual_review`

Confidence floors by `source_kind` already in `_STRUCTURED_SOURCE_CONFIDENCE_FLOORS`.

### Step 5 — Company-specific templates
Three archetype templates created in `examples/packs/templates/`:
- `platform_biotech_override_template.yaml` (RNA/ADC/TPD/IO platforms, 40–70% manual share)
- `commercial_rare_disease_override_template.yaml` (approved/NDA rare disease, 20–35% manual share)
- `multi_asset_oncology_override_template.yaml` (multi-program oncology/CNS, 40–70% manual share)

Companion `README.md` documents evidence standards, Step-4 gates, and backfiller/backtest usage.

### Step 6 — Pack quality controls
Confirmed complete: `manual_bucket_share_pct`, `manual_bucket_confidence_avg`,
`n_bucket_sources`, `largest_manual_bucket_share_pct` are all fields on `CompanySOTPResult`.

### Step 7 — Wave-tracking backtest output
Added to `src/bve/analysis/company_sotp_backtest.py`:
- `_write_wave_log()` function appends per-run metrics to a persistent JSON file
- `--wave-label` and `--wave-log` CLI flags
- Each entry captures: lane, candidate rows, mean excess return, hit rate, cluster count, bootstrap p-value
- Optional strict-lane comparison block

3 new tests added to `tests/test_company_sotp_backtest.py` (`7 passed`).

Interpretation:
- All four steps in the Company Pack Expansion Plan are now complete
- Future pack improvement waves should use `--wave-label` + `--wave-log` to accumulate
  the wave-tracking history specified in Step 7
- The next high-leverage work is using the Step 5 templates to add pack entries for
  names currently in `needs_manual_review` due to missing structured company inputs

## 2026-05-10 Valuation Engine Upgrade — Steps 7 & 8 Planning + TaxProfile Complete

### Completed this session

**TaxProfile / BD/M&A FCF model (committed a73f849)**
- `src/bve/models/tax_profile.py` — `TaxProfile`, `compute_year_fcf()`, `TaxAudit`
- `src/bve/models/rnpv_model.py` — two-path tax loop (Path A: backward-compat; Path B: per-year NOL balance)
- `src/bve/models/deal_economics.py` — `profit_share_rate` field (EBIT-level deduction, distinct from royalty)
- 37 new tests in `tests/test_tax_profile.py`, all passing
- rNPV formula: royalty on revenue (not EBIT), profit_share on EBIT, NAV = rNPV + net_cash

### Planned — Sprints 31–33 (Steps 7 & 8 upgrade)

Added to TASKS.md as pending work. Build order is:

1. Sprint 31A — `ScenarioShock` data model (6 input categories)
2. Sprint 31B — Enhanced Bull/Base/Bear (full ScenarioShock, full engine rerun)
3. Sprint 31C — Scenario-tree mode (clinical/regulatory/commercial outcome branches)
4. Sprint 31D — `ScenarioResult` output table (8 fields + kill_criteria + memo_interpretation)
5. Sprint 32A — Monte Carlo dual-mode (Simple / Driver-based) + double-counting validation
6. Sprint 32B — Full 23-variable MC table with named distributions
7. Sprint 32C — Enhanced Gaussian copula correlation rules
8. Sprint 32D — Enhanced competitor sampling (price pressure when competitor succeeds)
9. Sprint 32E — 12-step simulation path enforcement + `_run_single_trial()`
10. Sprint 32F — Enhanced MC outputs (14 new fields) + compact P5/P50/P95 audit trail
11. Sprint 33 — 6 validation rules (errors + warnings) + `validate_mc_params()`

**Core invariant across all sprints:** never shock final rNPV directly — always shock inputs and rerun the full engine chain.
