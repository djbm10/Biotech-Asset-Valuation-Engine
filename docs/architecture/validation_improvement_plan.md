# Validation Improvement Plan
## BVE POS Backtest + Historical Replay — Path to Institutional Grade

**Date:** 2026-05-16
**Branch:** core-engine-v1
**Status:** PLAN — do not execute until reviewed

---

## Current State Audit

Before building anything, this is what already exists and what the actual gaps are.

### POS Backtest — what exists

File: `src/bve/analysis/backtest.py`

| Feature | Status |
|---|---|
| Brier score (overall + per phase) | DONE |
| AUC-ROC (trapezoidal, no sklearn) | DONE |
| Calibration buckets (4 wide: 0-25, 25-50, 50-75, 75-100) | DONE — too coarse |
| No-skill baseline Brier | DONE |
| Brier skill score vs no-skill | DONE |
| ECE (expected calibration error) | MISSING |
| Calibration slope / intercept | MISSING |
| Precision by decile (10 bins) | MISSING |
| TA-level baselines (phase-only, TA+phase, TA+phase+modality) | MISSING |
| Subgroup breakdown by phase / TA / modality | MISSING |
| Non-oncology datasets | MISSING — oncology only, N=99 |
| Point-in-time discipline validator | MISSING |
| Hierarchical shrinkage for thin TAs | MISSING |
| Validation label on output (unvalidated for non-oncology) | DONE — model_grade.py |

Dataset: `research/data/oncology_phase_transitions.csv` (N=99, oncology only)

Validation labels live in `src/bve/validation/model_grade.py`.

### Historical Replay — what exists

| Feature | Status |
|---|---|
| Attribution taxonomy (confirmed_thesis, pos_error, timing_error, etc.) | DONE |
| Attribution counts in ReplaySummary | DONE |
| Skill-adjusted mean return (excludes pos_error) | DONE — replay_summary.py:84 |
| Validation status on every print() | DONE |
| Baselines A–G | DONE — analysis/baselines.py |
| Walk-forward with 3 expanding windows | DONE — analysis/walk_forward.py |
| Failure mode postmortems | DONE — analysis/failure_diagnostics.py |
| Shadow book | DONE — analysis/shadow_book.py |
| Replay significance (bootstrap) | EXISTS — analysis/replay_significance.py |
| Attribution MEAN RETURN by type (not just count) | MISSING |
| Attribution P&L CONTRIBUTION by type | MISSING |
| Independent decision count (deduped by cluster) | MISSING |
| Market regime controls (XBI/IBB/SPY adjustment) | MISSING |
| Trading friction model (slippage, ADV cap, execution delay) | MISSING |
| Regime-split subgroup reports (risk-on/risk-off, XBI above/below MA) | MISSING |
| Permutation test (shuffle model scores vs random) | MISSING |
| Decile monotonicity report | MISSING |
| Regression with controls (score + size + liquidity + phase + XBI) | MISSING |
| Full 2021-2026 replay run (price data exists) | NOT YET RUN |
| Expanded universe (27 assets → 60-100) | NOT YET DONE |

---

## Gap Summary

The two most impactful gaps right now are:

1. **Replay attribution only reports counts — not mean return or P&L per type.** This hides whether confirmed_thesis decisions are actually generating returns or whether positive total return comes from market_drift.

2. **No independent decision count.** Raw N=60 is not the right number to report. Multiple entries on the same ticker around the same catalyst inflate N artificially. The permutation test and p-values must use deduplicated cluster IDs.

Everything else (baselines, walk-forward, failure diagnostics) exists as modules but needs to be wired into the replay summary output and tested against a larger decision set.

---

## Sprint Plan

### Sprint 1 — Attribution return breakdown + independent N
**Goal:** Every replay summary prints mean return, median return, and P&L contribution by attribution type. Add decision_cluster_id and independent N.

**Priority:** Highest — uses only existing data, no new collection required.

#### 1.1 Extend `ReplaySummary`

File: `src/bve/intelligence/replay_summary.py`

Add fields:

```python
# Per-attribution return stats
returns_by_attribution: dict[str, list[float]] = field(default_factory=dict)
# Keys: confirmed_thesis, timing_error, thesis_error, pos_error, market_drift, unclassified
# Values: list of return_pct for each closed decision in that category

# Independent decision count
n_independent_decisions: int = 0
# Raw N minus decisions sharing same (ticker, catalyst_type, catalyst_date) cluster

# Mean and median return by attribution (computed at summarize time)
mean_return_by_attribution: dict[str, float] = field(default_factory=dict)
median_return_by_attribution: dict[str, float] = field(default_factory=dict)
pnl_contribution_by_attribution: dict[str, float] = field(default_factory=dict)
# P&L contribution = sum(returns) / total_sum(abs(returns)) — fraction of signed P&L
```

Add to `print()`:

```
  Attribution return breakdown:
  Type               N    Mean      Median    P&L contrib
  confirmed_thesis   18   +14.2%    +11.5%    +35.2%
  timing_error       12    -6.5%     -5.1%    -18.3%
  thesis_error       14    -9.1%     -7.8%    -29.6%
  pos_error           6    +8.4%     +7.0%    +11.8%
  market_drift       10    +3.0%     +2.8%     +7.0%
  unclassified        0      n/a       n/a       n/a

  Raw decisions:        60
  Independent decisions: 44  (deduplicated by ticker+catalyst+date)
```

#### 1.2 Add `decision_cluster_id` to replay decisions

File: `src/bve/intelligence/replay_policy.py`

Add field:

```python
decision_cluster_id: Optional[str] = None
# Format: f"{ticker}_{catalyst_type}_{catalyst_date_iso}"
# None if no catalyst seeded for this decision
```

Compute in `src/bve/ops/historical_replay.py` at decision-generation time. Store in `replay_decisions` table.

Independent decision count = count distinct `decision_cluster_id` values (non-None clusters count once each; None decisions each count as independent).

#### 1.3 Update `to_dict()` to include all new fields for JSON export

#### 1.4 Tests

File: `tests/test_replay_attribution_breakdown.py`

Test cases:
- `test_attribution_mean_return_correct()` — feed known decisions, verify per-type mean
- `test_pnl_contribution_sums_to_approximately_one()` — signed P&L fractions sum correctly
- `test_independent_decision_count_deduplication()` — same cluster counted once
- `test_independent_n_less_than_or_equal_raw_n()` — invariant
- `test_print_includes_attribution_table()` — print() output contains attribution table

**Acceptance criteria:** `ReplaySummary.print()` shows attribution return table and independent N on every run.

---

### Sprint 2 — Full 2021–2026 replay run
**Goal:** Use existing price data (48 tickers, seeded from 2021-01-01) to run the maximum possible window. Identify where independent N falls short and which years have the most decisions.

**Priority:** High — no code changes needed, just execution + reporting.

#### 2.1 Run full window

```bash
python -m bve.ops.historical_replay run \
  --start 2021-01-01 \
  --end 2026-05-15 \
  --cadence weekly \
  --decision-policy top2_add \
  --max-hold-days 28 \
  --min-thesis-score 0.5 \
  --require-catalyst-days 90 \
  --catalyst-timing \
  --cooling
```

#### 2.2 Run yearly sub-windows to find decision density

Run one replay per calendar year: 2021, 2022, 2023, 2024, 2025.

Expected output per year:
```
Year   Raw N   Independent N   Mean return   Hit rate
2021     8           5           -2.1%          40%
2022    12           9           +1.5%          55%
...
```

This identifies which years have enough events to contribute meaningfully.

#### 2.3 Run policy grid

Vary one parameter at a time, lock others at base:

```
decision-policy : top1_add / top2_add / top3_add
max-hold-days   : 14 / 28 / 45
require-catalyst-days : 30 / 60 / 90 / 180
```

Record results in `outputs/validation/replay_policy_grid.csv`. Do NOT use these results to pick the best policy — that is Sprint 9's job (walk-forward). The purpose here is to understand sensitivity.

#### 2.4 Record audit trail

Create `outputs/validation/replay_run_audit.yaml`:

```yaml
run_date: 2026-05-16
price_data_coverage:
  tickers_seeded: 48
  date_range: 2021-01-01 to 2026-05-15
  missing_tickers: []
event_data_coverage:
  total_events_seeded: 130
  date_range: 2021-01-04 to 2026-03-15
  events_by_type:
    clinical_readout: 47
    PDUFA: 22
    ...
replay_run_id: <uuid>
raw_n: <int>
independent_n: <int>
target_n_research_grade: 100
target_n_screening_grade: 250
```

**Acceptance criteria:** Run completes without errors. `raw_n` and `independent_n` documented. Gap to research-grade threshold (N=100) quantified.

---

### Sprint 3 — Expand asset universe (Tier 1: 20–30 tickers)
**Goal:** Increase the eligible replay universe from 27 to 50–60 assets by selecting public liquid names from the existing registries that had catalysts in 2021–2026.

**Priority:** High — directly increases independent N toward the 100 threshold.

#### 3.1 Tier 1 selection criteria

Select from `src/bve/entities/target_registry_*.py`. A ticker qualifies for Tier 1 if ALL of:

- Listed on NYSE or NASDAQ (public)
- Ticker available in yfinance price history back to 2021-01-01
- Had at least one identifiable Phase 2 or Phase 3 catalyst between 2021 and 2026
- Market cap was above $200M at time of catalyst (liquidity floor)
- Company had measurable cash runway (not already bankrupt at time of decision)

Disqualify:
- Private companies (no ticker)
- Tickers with missing price history before 2023
- Companies that merged/acquired before 2022 (no price history)
- Tickers with < 5 identifiable catalyst events in the period

#### 3.2 Seed prices

```bash
python -m bve.ops.historical_replay seed \
  --tickers <TIER1_LIST> \
  --start 2021-01-01 \
  --end 2026-05-15
```

Verify price coverage. Any ticker with > 10% missing daily data should be dropped from the universe.

#### 3.3 Seed historical events

For each new ticker, create structured events in `replay_knowledge.db`.

Required event types per ticker (minimum to be useful):
- At least 2 `clinical_readout` events with `announced_at` dates
- At least 1 `PDUFA` or `NDA_submission` (if applicable)

Event schema fields that MUST be populated:
```
ticker, asset_id, event_type, event_date, announced_at, source, known_at
```

The `known_at` field must be <= `announced_at`. Announced dates must come from public sources (press releases, SEC filings). Do not reconstruct announced dates from outcome knowledge (point-in-time discipline).

#### 3.4 Add new tickers to `UNIVERSE` in `ops/weekly_runner.py`

Each new universe entry needs:
- `ticker`, `asset_id`, `company_id`, `indication`
- `ranking_score` (initial estimate, 0–1)
- `opportunity_score` (initial estimate, 0–1)
- `conviction` (Tier A/B/C)
- `catalyst` (next expected or last known catalyst date)
- `claim_type`, `claim_assertion` (seeded thesis claim)

#### 3.5 Rerun full replay, report updated N

Target: raw_n >= 120, independent_n >= 80 after this sprint.

**Acceptance criteria:** Universe expanded to 50+ tickers. Independent N >= 80. All new prices and events seeded.

---

### Sprint 4 — Backtest metric improvements
**Goal:** Improve `backtest.py` to distinguish ranking skill from probability calibration, add 7-bucket calibration, ECE, calibration slope, and baseline comparison.

**Priority:** Medium — improves interpretability of existing N=99 result. No new data collection.

#### 4.1 Add 7-bucket calibration

Replace the 4-bucket system in `_build_calibration()` with 7 buckets matching the plan spec:

```
0–10%   10–20%   20–30%   30–40%   40–50%   50–70%   70%+
```

Add confidence interval to each bucket:
```python
@dataclass
class CalibrationBucket:
    label: str
    n: int
    n_success: int
    predicted_mean: float
    ci_lower: float   # Wilson score interval lower bound
    ci_upper: float   # Wilson score interval upper bound

    @property
    def actual_rate(self) -> float: ...
    @property
    def calibration_gap(self) -> float:
        return self.actual_rate - self.predicted_mean
```

Wilson score interval (no scipy dependency):
```python
def _wilson_ci(n_success: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = n_success / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, center - half), min(1.0, center + half))
```

#### 4.2 Add ECE (Expected Calibration Error)

```python
def _compute_ece(buckets: list[CalibrationBucket]) -> float:
    """Weighted mean absolute calibration gap across buckets."""
    total_n = sum(b.n for b in buckets if b.n > 0)
    if total_n == 0:
        return float("nan")
    return sum(
        (b.n / total_n) * abs(b.calibration_gap)
        for b in buckets if b.n > 0 and not math.isnan(b.calibration_gap)
    )
```

#### 4.3 Add calibration slope and intercept

Fit a linear regression of actual_rate ~ predicted_mean across buckets (weighted by N):

```python
def _compute_calibration_slope(buckets: list[CalibrationBucket]) -> tuple[float, float]:
    """Returns (slope, intercept). Perfectly calibrated = slope 1.0, intercept 0.0."""
    # Weighted least squares using bucket N as weights
    # Reject buckets with n < 5
    ...
```

Interpretation:
- slope > 1 → model is underconfident (actual rates more extreme than predicted)
- slope < 1 → model is overconfident (predictions too extreme)
- Target: slope ∈ [0.8, 1.2]

#### 4.4 Add baseline comparison in `BacktestReport`

Add `BaselineComparison` dataclass:

```python
@dataclass
class BaselineComparison:
    name: str               # "phase_only" | "ta_phase" | "ta_phase_modality"
    brier: float
    auc: float
    ece: float
    brier_improvement_vs_model_heuristic: float  # negative = model is better
    auc_improvement_vs_model_heuristic: float
```

Implement baselines:
- `phase_only`: predicted POS = mean success rate for that phase in dataset
- `ta_phase`: predicted POS = mean success rate for (TA, phase) in dataset — currently oncology only, so same as phase_only; this bucket is ready for multi-TA expansion
- `ta_phase_modality`: add modality column to CSV, predicted POS = mean success rate for (TA, phase, modality)

Add `baselines: list[BaselineComparison]` to `BacktestReport`.

Graduation rule (enforce in `print_report()`):

```python
GRADUATION_BRIER_LIFT = 0.10   # model must improve Brier by >=10% vs ta_phase baseline
GRADUATION_AUC_LIFT   = 0.03   # model AUC must be >=0.03 above ta_phase baseline
GRADUATION_ECE_MAX    = 0.08   # ECE must be <=0.08

def _check_graduation(report: BacktestReport) -> list[str]:
    """Returns list of unmet graduation criteria. Empty list = passes."""
    ...
```

#### 4.5 Add three new validation metrics to `BacktestReport`

```python
ece_heuristic: float = float("nan")
calibration_slope_heuristic: float = float("nan")
calibration_intercept_heuristic: float = float("nan")
ece_statistical: float = float("nan")
calibration_slope_statistical: float = float("nan")
calibration_intercept_statistical: float = float("nan")
```

#### 4.6 Add point-in-time validator

```python
def validate_point_in_time(row: dict) -> bool:
    """
    Returns True if the row passes point-in-time discipline.
    Excludes rows where known_at > model_prediction_date.
    """
    pred_date = row.get("model_prediction_date")
    readout_date = row.get("readout_date")
    known_at = row.get("known_at_date")

    if pred_date and readout_date:
        if pred_date >= readout_date:
            return False  # prediction uses future knowledge
    if pred_date and known_at:
        if known_at > pred_date:
            return False  # used data not yet available at prediction time
    return True
```

Add `n_excluded_point_in_time` to `BacktestReport`. Report exclusions in `print_report()`.

#### 4.7 Expand CSV schema

Add columns to `research/data/oncology_phase_transitions.csv`:
- `modality` — "small_molecule" | "biologic_antibody" | "biologic_other" | "cell_therapy" | "gene_therapy"
- `readout_date` — ISO date string
- `model_prediction_date` — ISO date string (use trial start date as proxy)
- `known_at_date` — ISO date string (same as model_prediction_date for historical cases)
- `failure_reason` — free text for failed programs

Do NOT add these columns by guessing. Add only where the data is known with confidence.

#### 4.8 Tests

File: `tests/test_backtest_metrics.py`

Test cases:
- `test_ece_zero_for_perfect_calibration()` — perfect predictions → ECE = 0
- `test_ece_positive_for_overconfident_model()`
- `test_calibration_slope_one_for_perfect_model()`
- `test_seven_bucket_calibration_boundaries()`
- `test_wilson_ci_coverage()` — CI contains true rate at expected frequency
- `test_baseline_comparison_phase_only()`
- `test_graduation_gate_passes_when_criteria_met()`
- `test_graduation_gate_fails_correctly()`
- `test_point_in_time_validator_excludes_future_knowledge()`

**Acceptance criteria:** `print_report()` shows ECE, slope, 7 calibration buckets, and baseline comparison table. Graduation gates evaluated on every run.

---

### Sprint 5 — Statistical testing for replay
**Goal:** Add bootstrap CI, permutation test, and decile monotonicity to replay analysis. Wire these into the replay summary output.

**Priority:** Medium-high — required for research-grade graduation.

#### 5.1 Complete `replay_significance.py`

Check current implementation in `src/bve/analysis/replay_significance.py`. Add any missing pieces:

Bootstrap (cluster-aware):
- Resample decisions by `decision_cluster_id` (preserve correlation within clusters)
- 10,000 bootstrap iterations
- Report: mean return CI [2.5%, 97.5%], median return CI, Sharpe CI, hit rate CI

Permutation test:
- Shuffle model scores across eligible candidates on each decision date
- Run 10,000 permutations
- Report: percentile of observed mean return vs permutation distribution
- p-value = fraction of permutations that beat observed mean return

Decile monotonicity:
- Divide all closed decisions into 10 deciles by composite score at entry
- Compute mean return per decile
- Report: decile returns, Spearman rank correlation
- Pass threshold: Spearman rho > 0 at p < 0.10

#### 5.2 Add `StatisticalTestResults` to `ReplaySummary`

```python
@dataclass
class ReplayStatTests:
    bootstrap_mean_ci_lo: Optional[float] = None
    bootstrap_mean_ci_hi: Optional[float] = None
    bootstrap_median_ci_lo: Optional[float] = None
    bootstrap_median_ci_hi: Optional[float] = None
    bootstrap_hit_rate_ci_lo: Optional[float] = None
    bootstrap_hit_rate_ci_hi: Optional[float] = None
    permutation_pvalue: Optional[float] = None
    permutation_percentile: Optional[float] = None
    decile_spearman_rho: Optional[float] = None
    decile_spearman_pvalue: Optional[float] = None
    n_bootstrap_iterations: int = 10000
    n_permutation_iterations: int = 10000
```

Add `stat_tests: Optional[ReplayStatTests] = None` to `ReplaySummary`.

Add to `print()`:
```
  Statistical tests (N=44 independent decisions):
  Bootstrap CI (mean return):  [-1.2%, +7.8%]
  Permutation p-value:          0.087
  Decile Spearman rho:          0.31  (p=0.09)
  Validation label:             DIRECTIONAL_ONLY (need N>=100 for research-grade)
```

#### 5.3 Tests

File: `tests/test_replay_statistics.py`

Test cases:
- `test_bootstrap_ci_contains_true_mean()` — synthetic known-distribution decisions
- `test_permutation_p_value_is_uniform_under_null()` — random scores → uniform p-value
- `test_decile_monotonicity_perfect_model()` — higher score → higher return
- `test_stat_tests_require_minimum_n()` — raise warning if N < 20

**Acceptance criteria:** `summary --run-id <id>` output includes CI and p-value. Validation label auto-updated based on N and p-value.

---

### Sprint 6 — Market regime controls
**Goal:** Decompose replay returns into XBI-adjusted alpha vs. pure beta. Add regime-split subgroup report.

**Priority:** Medium — required for screening-grade graduation.

#### 6.1 Add market regime fields to replay decisions

Extend `replay_decisions` table:

```sql
ALTER TABLE replay_decisions ADD COLUMN xbi_return_during_hold REAL;
ALTER TABLE replay_decisions ADD COLUMN ibb_return_during_hold REAL;
ALTER TABLE replay_decisions ADD COLUMN spy_return_during_hold REAL;
ALTER TABLE replay_decisions ADD COLUMN xbi_above_20d_ma_at_entry INTEGER;  -- 0 or 1
ALTER TABLE replay_decisions ADD COLUMN vix_level_at_entry REAL;
```

Populate these when closing positions (during `_step_resolve`). Source: yfinance price data for XBI, IBB, SPY.

#### 6.2 Add `RegimeReport` to `ReplaySummary`

```python
@dataclass
class RegimeSubgroupResult:
    label: str              # e.g. "xbi_above_20d_ma"
    n: int
    mean_return_pct: Optional[float]
    hit_rate: Optional[float]
    xbi_adjusted_alpha: Optional[float]

@dataclass
class RegimeReport:
    xbi_adjusted_mean_return: Optional[float] = None
    ibb_adjusted_mean_return: Optional[float] = None
    spy_adjusted_mean_return: Optional[float] = None
    subgroups: list[RegimeSubgroupResult] = field(default_factory=list)
    # Required subgroups: xbi_above_20d_ma, xbi_below_20d_ma, high_vix (>25), low_vix
```

Beta adjustment:
```python
xbi_adjusted_alpha = mean_return - beta_to_xbi * mean_xbi_return_during_holds
```

Beta estimated from regression of per-decision returns on XBI returns during same hold period (OLS, min 20 decisions required).

#### 6.3 Graduation gate

For screening-grade graduation, XBI-adjusted alpha must remain positive. If alpha goes negative after XBI adjustment, output:

```
WARNING: All positive return disappears after XBI adjustment.
         This is beta, not alpha. Do not claim model skill.
         [VALIDATION: BETA_ONLY — not eligible for SCREENING_GRADE]
```

#### 6.4 Tests

File: `tests/test_regime_controls.py`

- `test_xbi_adjusted_alpha_zero_when_returns_equal_xbi()`
- `test_regime_subgroup_split_counts_are_exhaustive()`
- `test_beta_estimated_correctly_on_synthetic_data()`

**Acceptance criteria:** Replay summary includes regime report. XBI alpha displayed on every run with N >= 30.

---

### Sprint 7 — Trading friction model
**Goal:** Add realistic execution costs so returns are reportable as net returns, not idealized gross returns.

**Priority:** Medium — required before any institutional comparison.

#### 7.1 `FrictionModel` dataclass

File: `src/bve/analysis/friction_model.py` (new file)

```python
@dataclass(frozen=True)
class FrictionModel:
    """Parameters for simulated execution costs."""
    entry_timing: str = "next_open"     # "signal_close" | "next_open" | "next_close"
    exit_timing: str = "scheduled_close"
    slippage_bps: float = 10.0          # minimum slippage in basis points
    bid_ask_half_spread_bps: float = 15.0
    execution_delay_days: int = 1       # days between signal and execution
    max_pct_adv: float = 0.05          # max position size as % of 20-day ADV
    # Effective slippage = max(slippage_bps, 0.1 * bid_ask_half_spread * 2) bps
```

#### 7.2 Apply frictions in historical_replay `_step_resolve`

For each closed decision:
- Compute `gross_return_pct` (current behavior)
- Compute `net_return_pct = gross_return_pct - total_friction_cost_pct`
- Record both in `replay_decisions` table

Add columns to table:
```sql
ALTER TABLE replay_decisions ADD COLUMN gross_return_pct REAL;
ALTER TABLE replay_decisions ADD COLUMN friction_cost_bps REAL;
ALTER TABLE replay_decisions ADD COLUMN net_return_pct REAL;
```

#### 7.3 Report both gross and net

`ReplaySummary` add:
```python
gross_mean_return_pct: Optional[float] = None
net_mean_return_pct: Optional[float] = None   # = current mean_return_pct becomes gross
friction_cost_mean_bps: Optional[float] = None
```

#### 7.4 Tests

- `test_net_return_less_than_gross_return()`
- `test_friction_model_zero_when_params_zero()`
- `test_adv_cap_applied_correctly()`

**Acceptance criteria:** Replay summary prints gross and net return. All subsequent performance claims use net return.

---

### Sprint 8 — Expand universe to 80-100 assets (Tier 2)
**Goal:** Add 30–50 more tickers beyond Sprint 3, targeting independent N >= 200.

**Priority:** Medium — required for screening-grade graduation.

#### 8.1 Tier 2 selection criteria

Relax Sprint 3 criteria slightly:
- Market cap floor lowered to $100M
- Missing catalyst date allowed if Phase 2+ trial completion date is in clinicaltrials.gov
- Companies with 1 identifiable catalyst event in the window are eligible (Sprint 3 required 2)

#### 8.2 Same seeding process as Sprint 3

Seed prices and events. Apply same point-in-time discipline.

#### 8.3 Targets

After Sprint 8: raw_n >= 250, independent_n >= 160.

**Acceptance criteria:** Universe >= 90 tickers. Independent N >= 160.

---

### Sprint 9 — Walk-forward validation (lock parameters)
**Goal:** Lock policy parameters using only in-sample data. Generate OOS walk-forward results.

**Priority:** Medium-high — prevents overfitting that would be discovered post-deployment.

#### 9.1 Current state of `walk_forward.py`

The module exists with 3 expanding windows:
- Fold 1: train 2021-2022, test 2023
- Fold 2: train 2021-2023, test 2024
- Fold 3: train 2021-2024, test 2025

Policy grid: `min_model_score` [0.40, 0.50, 0.60], `max_hold_days` [14, 21, 28], `require_catalyst` [True, False].

#### 9.2 Verify implementation is wired to actual replay decisions

The current `walk_forward.py` may be a standalone module not yet integrated with `historical_replay`. Verify that `run_walk_forward(decisions)` can consume actual `ReplayDecision` objects and produce `WalkForwardReport`.

If integration is missing, add a CLI entry point:

```bash
python -m bve.ops.historical_replay walk-forward --run-id <run_id>
```

#### 9.3 Add stability report

`WalkForwardReport.parameter_stability_report()` must output:

```
Parameter Stability Report
--------------------------
min_model_score : [0.50, 0.50, 0.60] — MODERATELY STABLE (2/3 agree)
max_hold_days   : [28, 28, 28]       — STABLE
require_catalyst: [True, True, True] — STABLE

OOS performance by fold:
  Fold 1 (test 2023): mean=+1.2%, hit=52%, N=18 independent
  Fold 2 (test 2024): mean=+2.8%, hit=58%, N=24 independent
  Fold 3 (test 2025): mean=-0.5%, hit=47%, N=21 independent
  Combined OOS       : mean=+1.2%, hit=52%

WARNING: Fold 3 OOS return is negative. Model may not generalize to 2025 regime.
```

#### 9.4 Lock policy file

Save `outputs/validation/locked_policy_by_period.yaml` after every walk-forward run.

#### 9.5 Tests

- `test_walk_forward_locks_policy_before_test_window()`
- `test_oos_uses_only_locked_policy()`
- `test_stability_report_classification_correct()`

**Acceptance criteria:** Walk-forward integrated with replay. OOS results reported by fold. Locked policy saved to YAML.

---

### Sprint 10 — POS dataset expansion (immunology + rare disease)
**Goal:** Collect N >= 75 labeled outcomes for immunology and rare disease. Build TA-specific calibration.

**Priority:** Lower — requires real data collection, not code. Code scaffolding can be done earlier.

#### 10.1 Data schema

Create per-TA CSV files following this schema:

File: `research/data/pos_outcomes/`

Each file: `{ta}_outcomes.csv`

Required columns:
```
program_id, company, drug, indication, therapeutic_area, modality,
phase, trial_design, endpoint_type, biomarker_selected, sample_size,
control_arm, readout_date, model_prediction_date, predicted_pos,
actual_outcome, outcome_label, failure_reason, source_url, known_at_date
```

Valid `outcome_label` values:
```
success, failure, mixed, terminated_business_reason, immature, unknown
```

Only `success` and `failure` used in primary validation. The others are excluded with `n_excluded_non_primary` count.

#### 10.2 Prioritized collection order

1. Immunology (target: N=100 by 2026-Q3)
   - Source: Biomedtracker, IQVIA pipeline tracker, FDA database
   - Focus on: RA, SLE, IBD, atopic dermatitis, asthma
   - Phase transitions 2010–2025

2. Rare disease (target: N=75)
   - Source: FDA rare disease database, Evaluate Pharma
   - Focus on: metabolic, neurological, musculoskeletal rare diseases
   - Phase transitions 2010–2025

3. CNS (target: N=75)
   - Higher noise, lower base rates — requires careful label validation

#### 10.3 Multi-TA `run_backtest_from_dir()`

```python
def run_backtest_from_dir(data_dir: str | Path) -> dict[str, BacktestReport]:
    """
    Load all *_outcomes.csv files in data_dir. Return per-TA BacktestReport.
    Combined report uses hierarchical shrinkage.
    """
```

#### 10.4 Hierarchical calibration shrinkage

File: `src/bve/analysis/pos_calibration.py` (check existing content)

```python
def shrinkage_weight(n_ta: int, k: int = 100) -> float:
    """Empirical Bayes shrinkage weight. k=100 means half-weight at N=100."""
    return n_ta / (n_ta + k)

def shrinkage_calibrated_pos(
    ta_predicted_pos: float,
    global_predicted_pos: float,
    n_ta: int,
    k: int = 100,
) -> float:
    w = shrinkage_weight(n_ta, k)
    return w * ta_predicted_pos + (1 - w) * global_predicted_pos
```

Emit warning when `n_ta < 30`:
```
WARNING: TA=immunology N=22 < 30 minimum. Pooled global estimate used (w=0.18).
```

Emit error when `n_ta < 10` — refuse to produce TA-specific estimate.

#### 10.5 Validation label by TA

Extend `model_grade.py`:

```python
def pos_validation_status(ta: str, n: int, auc: float, brier_lift: float) -> BacktestValidationStatus:
    if n < 30:
        return BacktestValidationStatus.UNVALIDATED
    if n < 75 or auc < 0.65:
        return BacktestValidationStatus.DIRECTIONAL_ONLY
    if n < 150 or auc < 0.70 or brier_lift < 0.05:
        return BacktestValidationStatus.RESEARCH_GRADE
    if n < 300 or auc < 0.70 or brier_lift < 0.10:
        return BacktestValidationStatus.SCREENING_GRADE
    return BacktestValidationStatus.DECISION_GRADE
```

**Acceptance criteria:** At least 2 TAs (oncology already done; immunology or rare disease added) with labeled outcomes. Hierarchical shrinkage applied when TA N < 100.

---

### Sprint 11 — Live shadow book
**Goal:** Pre-register weekly decisions for 6–12 months of prospective tracking.

**Priority:** Lowest sprint priority but highest institutional credibility.

#### 11.1 Shadow book is already implemented

File: `src/bve/analysis/shadow_book.py` exists.

Verify it can:
- Record a decision with timestamp, model score, and reasoning at time of entry
- Record exit outcome when catalyst resolves
- Compare live accuracy to backtest accuracy

#### 11.2 Pre-registration discipline

Every decision recorded in shadow book must be pre-registered BEFORE the outcome is known. Add:

```python
@dataclass(frozen=True)
class ShadowEntry:
    ticker: str
    entry_date: date
    model_score: float
    catalyst_expected: Optional[date]
    thesis_claim: str
    registered_at: datetime   # must be before catalyst_expected
    locked: bool = True       # once locked, entry cannot be modified
```

Add a lock mechanism. A locked entry cannot be modified or deleted. If a locked entry is attempted to be modified, raise `ShadowBookViolation`.

#### 11.3 Comparison report

After 6 months of tracking:
- Live hit rate vs backtest hit rate
- Live mean return vs backtest mean return
- Regime conditions during live period vs backtest periods

If live accuracy is within 10 percentage points of backtest: shadow book confirms signal.
If live accuracy is more than 20 percentage points below backtest: possible overfitting or regime break.

**Acceptance criteria:** Shadow book records weekly decisions starting from sprint completion date. First comparison report available 6 months after start.

---

## Graduation Gate Summary

### POS Model Graduation Levels

| Level | N | TAs | AUC OOS | Brier lift | ECE | Slope |
|---|---|---|---|---|---|---|
| **Research-grade** (current) | ≥99 | 1 (oncology) | ≥0.70 | reported | reported | reported |
| **Screening-grade** | ≥300 | ≥3 | ≥0.70 | ≥10% vs TA/phase | ≤0.08 | 0.8–1.2 |
| **Decision-grade** | ≥500 | ≥5 | ≥0.72 | ≥15% | ≤0.06 | 0.85–1.15 |

Current status: **Research-grade** (oncology only). Non-oncology: **UNVALIDATED**.

### Historical Replay Graduation Levels

| Level | Independent N | Net return | XBI alpha | Permutation p | Walk-forward |
|---|---|---|---|---|---|
| **Research-grade** | ≥100 | positive | not required | < 0.15 | not required |
| **Screening-grade** | ≥250 | positive net-of-costs | positive | < 0.10 | not required |
| **Institutional-grade** | ≥500 | positive WF OOS | positive | < 0.05 | passes 3-fold OOS |

Current status: **Pre-research-grade** (independent N ~44, no net-of-cost returns, no baselines run at scale).

---

## Build Order Rationale

The ordering is constrained by:

1. **Sprint 1** (attribution returns + independent N) is cheap and uses no new data. It changes the denominator for every subsequent significance calculation. Must go first.

2. **Sprint 2** (full 2021-2026 run) reveals the actual independent N before any expansion effort begins. Avoids building the wrong expansion plan.

3. **Sprint 3** (Tier 1 expansion) is the fastest path from pre-research to research-grade (N >= 100). Cannot permute or bootstrap meaningfully until N is there.

4. **Sprint 4** (backtest metrics) is independent and can proceed in parallel with Sprints 2–3. It is lower priority than expansion because the existing N=99 result is directionally valid.

5. **Sprints 5–7** (statistics, regime, frictions) build on each other and need N >= 100 to be meaningful. Do not run permutation tests on N=44.

6. **Sprint 8** (Tier 2 expansion) bridges screening-grade. Target: independent N >= 200.

7. **Sprint 9** (walk-forward) requires at least 3 years of decisions to have meaningful folds. Do not attempt before Sprint 8 completes.

8. **Sprint 10** (POS expansion beyond oncology) is data-collection-bottlenecked and independent of replay work. Can proceed in parallel with Sprints 5–8 on a separate track.

9. **Sprint 11** (shadow book) starts as soon as Sprint 3 completes and runs for 6–12 months in the background.

---

## Parameter Lock Table

These parameters MUST NOT be tuned on test-window data. They must be selected on training data only (Sprint 9 walk-forward).

| Parameter | Grid values | Lock mechanism |
|---|---|---|
| `min_thesis_score` | [0.40, 0.50, 0.60] | `locked_policy.yaml` |
| `max_hold_days` | [14, 21, 28, 45] | `locked_policy.yaml` |
| `require_catalyst_days` | [30, 60, 90, 180] | `locked_policy.yaml` |
| `cooling_window_days` | [7, 14] | `locked_policy.yaml` |
| `entry_window_days` | [3–10 before catalyst] | `locked_policy.yaml` |
| `min_composite_score` | [0.45, 0.50, 0.55] | `locked_policy.yaml` |

Any result reported using test-window data must note: "OOS — parameters locked from training window."
Any result reported using full-window data must note: "IS — parameters may be overfit; see OOS fold results."

---

## What NOT to Do

1. **Do not tune `--min-thesis-score` on the full dataset and report the best result.** This is in-sample selection. The p-value will be meaningless.

2. **Do not report raw N=60 as the sample size for significance tests.** Use independent N only.

3. **Do not add assets to the universe after seeing their historical performance.** Selection bias. All Tier 1 and Tier 2 assets must be selected on criteria independent of their outcomes.

4. **Do not count `pos_error` decisions as model validation.** These are decisions where the thesis was wrong but the stock made money. They inflate hit rate without reflecting model skill.

5. **Do not compare model returns to XBI total return without holding-period matching.** Model holds are 14-45 days. XBI "return" for comparison must be computed over the same calendar windows, not full-year returns.

6. **Do not add non-oncology POS predictions to the UI until those datasets exist and are validated.** The current model_grade system enforces this. Do not remove the enforcement.
