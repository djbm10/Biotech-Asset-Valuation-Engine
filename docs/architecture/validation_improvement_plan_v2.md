# Validation Improvement Plan v2
## BVE POS Backtest + Historical Replay — Path to Institutional Grade

**Date:** 2026-05-16
**Branch:** core-engine-v1
**Supersedes:** validation_improvement_plan.md

---

## I. True State Audit

The first plan made several errors about what exists. This section corrects the record with precise file-level findings.

### 1.1 What is fully implemented and working

| Module | File | Status | Notes |
|---|---|---|---|
| Cluster-robust significance | `analysis/replay_significance.py` | COMPLETE | Cameron-Miller sandwich SE, cluster bootstrap, graduation flag |
| Walk-forward engine | `analysis/walk_forward.py` | COMPLETE | 18-policy grid, 3 expanding folds, stability grades, CSV/YAML export |
| Multi-TA POS calibration | `analysis/pos_calibration.py` | COMPLETE | ECE, AUC, Brier, time-split, MD export, industry base rates |
| 7-baseline runner | `analysis/baselines.py` | COMPLETE | All A–G strategies, `compare_to_model()`, `print_comparison()` |
| Failure diagnostics | `analysis/failure_diagnostics.py` | COMPLETE | 10 failure categories, remediation taxonomy |
| Shadow book | `analysis/shadow_book.py` | COMPLETE | Append-only, SHA-256 hash-locked, full CLI |
| Attribution taxonomy | `intelligence/replay_summary.py` | COMPLETE | Counts for all 6 attribution types, `skill_adjusted_mean_return_pct` |

Every module listed above is production-quality code. The primary work is **integration** — wiring these modules together so they run as part of the standard CLI output.

### 1.2 What the first plan missed — four critical design issues

These are not missing features. They are design problems in the existing code that will produce wrong answers if unaddressed.

---

**Design issue 1: pos_calibration.py uses reconstructed predictions, not stored model scores**

File: `analysis/pos_calibration.py:530–591` (`load_from_backtest_csv`)
File: `analysis/pos_calibration.py:647–681` (`_heuristic_pos_from_row`)

When the calibration suite loads a backtest CSV, it reconstructs POS predictions via `_heuristic_pos_from_row()` — a simplified log-odds approximation using only 4 features. It does not use actual stored model output scores (`heuristic_pos`, `statistical_pos` from `BacktestResult`).

This means: the `POSCalibrationSuite` is measuring calibration of a reconstructed surrogate, not the actual model. The ECE, Brier, and AUC reported by `pos_calibration.py` currently do not reflect model performance.

**Impact:** All calibration metrics from `pos_calibration.py` are currently wrong unless actual model scores are passed in directly. The `run_backtest()` function in `backtest.py` does compute true model scores, but those results are never fed into `pos_calibration.py`.

**Fix:** `backtest.py:run_backtest()` must emit `POSCalibrationRecord` objects using actual `heuristic_pos` and `statistical_pos` values from `BacktestResult`, then call `run_pos_calibration_from_records()`. The `_heuristic_pos_from_row()` path should be deprecated with a warning.

---

**Design issue 2: walk_forward.py cannot correctly vary max_hold_days**

File: `analysis/walk_forward.py:374–386` (`_apply_policy`)
File: `analysis/walk_forward.py:72–77` (`DEFAULT_POLICY_GRID`)

The policy grid includes `max_hold_days` as a variable parameter [14, 21, 28]. But `_apply_policy()` does not filter by `max_hold_days` at all — the function only filters by `min_model_score` and `require_catalyst_days`. The `max_hold_days` dimension silently has no effect.

This matters because `max_hold_days` determines when positions are closed and at what price. To genuinely vary `max_hold_days`, you need either:
(a) separate replay runs with different hold periods, or
(b) all daily prices stored for every held position so exit can be recomputed

With the current data model, the walk-forward analysis can only validly vary `min_model_score` and `require_catalyst_days`. The 18-policy grid effectively has 6 valid configurations (3 × 2), not 18.

**Impact:** The selected "best policy" from walk-forward may have `max_hold_days=14` or `max_hold_days=28` in its label, but both were evaluated identically. The stability grade for `max_hold_days` is meaningless.

**Fix:** Reduce the policy grid to the two filterable parameters: `min_model_score` × `require_catalyst_days`. Add a note to `WalkForwardReport.summary()` clarifying that `max_hold_days` variants require separate replay seeds. Separately, run three complete replay seeds with `max_hold_days` = 14, 28, 45 and compare their summary statistics as parallel experiments, not within a single walk-forward run.

---

**Design issue 3: replay_significance.py over-clusters, deflating statistical power**

File: `analysis/replay_significance.py:92–103`

The significance analysis clusters by `asset_id` only. This is too conservative: two decisions on the same asset in different years around genuinely different catalysts should be treated as independent. Clustering them together reduces the effective degrees of freedom and makes the model harder to graduate.

The correct cluster definition for a biotech replay strategy is `(asset_id, catalyst_event_id)`. Decisions tied to the same catalyst are correlated. Decisions tied to different catalysts on the same asset across different years are largely independent (different market conditions, different thesis claims).

**Impact:** With 20 distinct `asset_id` values and 3 decisions per asset, the current clustering gives df = 19. With proper `(asset_id, event_id)` clustering and 2 decisions per event, df would be approximately 30. This affects the cluster_p value and graduation flag.

**Fix (minor):** Add `cluster_by` parameter to `replay_significance.analyze()` with default = `"asset_id"` (preserving current behavior for backward compat) and a new option `"asset_catalyst"` that uses a concatenation of `asset_id + catalyst_event_id`. Add `days_to_catalyst_at_entry` to `replay_decisions` schema to support this. Document the conservative vs. precise clustering options.

---

**Design issue 4: replay_decisions schema is missing fields required by walk_forward and baselines**

File: `ops/historical_replay.py:170–185` (`ReplayStore._ensure_schema`)

The `replay_decisions` table schema does not include:
- `days_to_catalyst_at_entry` — required by `walk_forward._apply_policy()` `require_catalyst_days` filter
- `decision_cluster_id` — required for independent N count and precise clustering
- `catalyst_event_id` — required for Design Issue 3 fix
- `xbi_return_during_hold`, `ibb_return_during_hold` — required for regime controls
- `gross_return_pct`, `friction_cost_bps`, `net_return_pct` — required for friction-adjusted returns

Without `days_to_catalyst_at_entry`, the walk-forward `require_catalyst_days` filter silently passes all decisions (the field is None, so `int(None)` would raise but the current code does `d.get("days_to_catalyst")` which returns None, and `None > threshold` returns False → all decisions are filtered OUT when a catalyst gate is set). This means the walk-forward analysis currently runs zero decisions when `require_catalyst_days > 0`, and the policy grid tests are not doing what they appear to be doing.

**Impact:** This is the most severe issue. The `require_catalyst_days` parameter in the policy grid is completely broken until this field is stored.

**Fix:** Add all missing columns to `replay_decisions` at decision-record time (not alter-table, since replay store is recreated per run).

---

### 1.3 What is genuinely missing (not a design issue, just not built)

| Gap | Priority | Effort |
|---|---|---|
| Attribution breakdown by return (mean, median, P&L contribution per type) | High | Low |
| Independent decision count (dedup by cluster) | High | Low |
| Market regime columns (XBI/IBB return during hold) | Medium | Medium |
| XBI-adjusted alpha calculation | Medium | Medium |
| Trading friction model | Medium | Medium |
| Permutation test (score-shuffle, feasible with existing data) | Medium | Low |
| Wire `replay_significance` into `summary` CLI command | High | Very Low |
| Wire `walk_forward` into `historical_replay` CLI | High | Low |
| Wire `baselines` into `summary` output | High | Low |
| Wire `failure_diagnostics` into `summary` output | Medium | Low |
| Connect shadow book registration to weekly runner | Medium | Low |
| 7-bucket calibration (current: 5 buckets in pos_calibration.py) | Low | Very Low |
| Non-oncology POS datasets | Low | Data-collection bottleneck |
| Universe expansion (27 → 80+ assets) | High | Medium |

---

## II. Root Cause Summary

The validation system has been built as a collection of independent, high-quality analytical modules. None of them run automatically. A user running `python -m bve.ops.historical_replay summary --run-id <id>` currently gets attribution counts and mean return. They do not get:

- cluster-robust significance test (exists in `replay_significance.py`)
- baseline comparison (exists in `baselines.py`)
- walk-forward policy stability (exists in `walk_forward.py`)
- failure mode postmortem (exists in `failure_diagnostics.py`)
- market-adjusted alpha (not built)

The conclusion: build order must be **fix design issues first, wire modules second, add new capabilities third, expand data fourth**.

---

## III. Sprint Plan

Organized into four tiers based on leverage and dependency.

---

### Tier A: Fix design issues (no user-visible features, must go first)

These fix silent failures in existing code. They unblock all subsequent work.

---

#### Sprint A1: Fix replay_decisions schema

**Files changed:** `ops/historical_replay.py`

Add to `replay_decisions` table in `_ensure_schema()`:

```sql
-- Required for walk_forward require_catalyst_days filter (currently broken)
days_to_catalyst_at_entry   INTEGER,   -- days between decided_at and nearest catalyst_date

-- Required for independent N count and precise clustering
decision_cluster_id         TEXT,      -- f"{ticker}_{catalyst_event_id}"
catalyst_event_id           TEXT,      -- NULL if no catalyst seeded

-- Required for market regime analysis
xbi_return_during_hold      REAL,      -- XBI close-to-close over [entry_date, exit_date]
ibb_return_during_hold      REAL,      -- IBB close-to-close same period
spy_return_during_hold      REAL,      -- SPY benchmark
xbi_above_20d_ma_at_entry   INTEGER,   -- 1 if XBI > 20-day MA at decided_at, else 0

-- Required for friction-adjusted returns
gross_return_pct            REAL,      -- = current return_pct (rename existing)
friction_cost_bps           REAL,      -- modelled execution cost in basis points
net_return_pct              REAL       -- gross_return_pct - friction_cost_bps/100
```

Populate `days_to_catalyst_at_entry` in `_step_decision()` when building `ScoredCandidate`. This requires the nearest upcoming catalyst date to be accessible at decision time.

Populate `decision_cluster_id` as `f"{ticker}_{catalyst_event_id}"` where `catalyst_event_id` is the `event_id` from `historical_events` for the nearest upcoming catalyst. Set to `f"{ticker}_no_catalyst"` if no event seeded.

Populate `xbi_return_during_hold` and regime fields in `_step_resolve()` by fetching XBI/IBB/SPY prices from `historical_prices` table (these tickers must be seeded alongside the universe).

**Backward compat:** existing replay run DBs are unaffected. New runs will have the fields populated. Old runs will have NULLs for new columns when queried.

**Tests added:** `tests/test_replay_schema.py`
- `test_new_schema_fields_populated_for_decision()`
- `test_days_to_catalyst_correct_for_known_event()`
- `test_decision_cluster_id_format()`
- `test_regime_fields_null_when_xbi_not_seeded()`
- `test_regime_fields_populated_when_xbi_seeded()`

**Acceptance criterion:** `SELECT days_to_catalyst_at_entry FROM replay_decisions` returns non-NULL values when a catalyst was seeded. Walk-forward `require_catalyst_days` filter now produces different results than `0`.

---

#### Sprint A2: Fix walk_forward policy grid

**Files changed:** `analysis/walk_forward.py`

Remove `max_hold_days` from `DEFAULT_POLICY_GRID` and `PolicyConfig`. The field remains on `PolicyConfig` as documentation but is excluded from grid search:

```python
@dataclass(frozen=True)
class PolicyConfig:
    min_model_score: float = 0.50
    require_catalyst_days: int = 30
    # max_hold_days is NOT varied here — requires separate replay seeds
    # See: docs/architecture/validation_improvement_plan_v2.md Sprint A2
```

New `DEFAULT_POLICY_GRID` — 6 configurations (3 × 2):

```python
DEFAULT_POLICY_GRID = [
    PolicyConfig(min_model_score=s, require_catalyst_days=c)
    for s in [0.40, 0.50, 0.60]
    for c in [0, 90]
]
```

Add a separate function for multi-hold-days comparison:

```python
def compare_hold_days(
    decisions_by_hold: dict[int, list[dict]],  # {hold_days: decisions}
    *,
    model_name: str = "historical_replay",
) -> dict[int, PolicyMetrics]:
    """
    Compare performance across replay runs with different max_hold_days.
    These are separate runs, not post-hoc filters.
    Returns {hold_days: PolicyMetrics} for plotting.
    """
```

Add warning to `WalkForwardReport.summary()`:

```
NOTE: max_hold_days was not varied in this walk-forward analysis.
      To test hold period sensitivity, run separate replay seeds:
      --max-hold-days 14 / 28 / 45
      Then compare using walk_forward.compare_hold_days().
```

**Tests added:** `tests/test_walk_forward_v2.py`
- `test_policy_grid_does_not_include_max_hold_days()`
- `test_require_catalyst_days_filter_uses_days_to_catalyst_field()`
- `test_compare_hold_days_returns_per_hold_metrics()`
- `test_walk_forward_reports_correct_warning_about_hold_days()`

**Acceptance criterion:** Running `run_walk_forward(decisions)` with `require_catalyst_days=90` now filters differently than `require_catalyst_days=0`. The `max_hold_days` field is absent from policy grid.

---

#### Sprint A3: Fix pos_calibration.py to use stored model scores

**Files changed:** `analysis/backtest.py`, `analysis/pos_calibration.py`

The fix has two parts.

**Part 1: Add `to_calibration_records()` to BacktestReport**

In `backtest.py`, add to `BacktestReport`:

```python
def to_calibration_records(self) -> list["POSCalibrationRecord"]:
    """
    Convert BacktestResult list to POSCalibrationRecord objects using ACTUAL
    stored model scores (heuristic_pos). Not reconstructed from features.
    """
    from bve.analysis.pos_calibration import POSCalibrationRecord
    records = []
    for r in self.results:
        records.append(POSCalibrationRecord(
            therapeutic_area="oncology",  # current dataset is oncology only
            phase=r.case.phase,
            predicted_pos=r.heuristic_pos,  # ACTUAL model score
            actual_success=r.case.success,
            drug=r.case.drug,
            company=r.case.company,
            indication=r.case.indication,
            year=r.case.year,
        ))
    return records
```

Also add a `to_calibration_records_statistical()` variant using `statistical_pos`.

**Part 2: Deprecate `_heuristic_pos_from_row()` in pos_calibration.py**

Add a `DeprecationWarning` to `_heuristic_pos_from_row()`:

```python
def _heuristic_pos_from_row(row: dict, phase: str) -> float:
    import warnings
    warnings.warn(
        "_heuristic_pos_from_row() reconstructs a simplified proxy of model predictions. "
        "Use BacktestReport.to_calibration_records() for actual model scores. "
        "Calibration metrics computed via this path do not reflect true model performance.",
        DeprecationWarning,
        stacklevel=2,
    )
    ...
```

**Part 3: Update `run_backtest_from_csv()` to run calibration as part of standard output**

```python
def run_backtest_from_csv(csv_path: str | Path) -> BacktestReport:
    cases = load_cases_from_csv(csv_path)
    report = run_backtest(cases)
    # Attach calibration suite using actual model scores
    from bve.analysis.pos_calibration import run_pos_calibration_from_records
    calibration_records = report.to_calibration_records()
    report.calibration_suite = run_pos_calibration_from_records(
        calibration_records,
        model_name="heuristic_oncology",
        time_split_year=2020,
    )
    return report
```

Add `calibration_suite: Optional[POSCalibrationSuite]` field to `BacktestReport`.

**Tests added:** `tests/test_backtest_calibration_integration.py`
- `test_to_calibration_records_uses_actual_heuristic_pos()`
- `test_calibration_records_predicted_pos_matches_backtest_result()`
- `test_heuristic_pos_from_row_emits_deprecation_warning()`
- `test_run_backtest_from_csv_attaches_calibration_suite()`
- `test_calibration_suite_ece_differs_from_heuristic_reconstruction()`

**Acceptance criterion:** `BacktestReport.calibration_suite.overall.ece` uses actual `heuristic_pos` values. Value differs from the old `load_from_backtest_csv()` path, confirming the fix.

---

### Tier B: Wire existing modules into the CLI (high leverage, mostly plumbing)

These sprints connect the fully-implemented analytical modules so they run automatically.

---

#### Sprint B1: Wire replay_significance into `summary` command

**Files changed:** `ops/historical_replay.py` (the `cmd_summary()` function)

Currently the `summary` subcommand calls `ReplaySummary.print()`. Add:

```python
# In cmd_summary():
decisions = store.get_closed_decisions(run_id)
if len(decisions) >= 5:
    from bve.analysis.replay_significance import analyze as sig_analyze, print_report as sig_print
    sig_result = sig_analyze(
        [d._asdict() for d in decisions],
        run_id=run_id,
        bootstrap_samples=2000,
    )
    sig_print(sig_result)
else:
    print(f"  Significance: N={len(decisions)} — minimum 5 closed decisions required")
```

No changes to `replay_significance.py` needed. It already handles the computation correctly.

The output will include the full significance report including cluster-robust SE, graduation flag, and bootstrap CI that already exist in the module.

**Tests added:** `tests/test_replay_summary_significance.py`
- `test_significance_auto_runs_on_summary_with_closed_decisions()`
- `test_significance_skipped_gracefully_below_min_n()`
- `test_summary_output_includes_graduation_flag()`

**Acceptance criterion:** `python -m bve.ops.historical_replay summary --run-id <id>` prints the cluster-robust significance report beneath the attribution table.

---

#### Sprint B2: Wire walk_forward into replay CLI

**Files changed:** `ops/historical_replay.py`

Add a new `walk-forward` subcommand:

```
python -m bve.ops.historical_replay walk-forward --run-id <run_id>
python -m bve.ops.historical_replay walk-forward --run-id <run_id> --save-csv outputs/wf.csv
python -m bve.ops.historical_replay walk-forward --run-id <run_id> --save-yaml outputs/locked_policy.yaml
```

Implementation:

```python
def cmd_walk_forward(args):
    store = ReplayStore(str(REPLAY_STORE_PATH))
    decisions = store.get_closed_decisions(args.run_id)
    if len(decisions) < 20:
        print(f"Walk-forward requires ≥20 closed decisions; found {len(decisions)}.")
        return
    from bve.analysis.walk_forward import run_walk_forward, DEFAULT_FOLDS
    decision_dicts = [
        {
            "entry_date": d.decided_at[:10],
            "return_pct": d.return_pct,
            "composite_score": d.composite_score,
            "asset_id": d.asset_id,
            "days_to_catalyst": d.days_to_catalyst_at_entry,  # added in Sprint A1
        }
        for d in decisions if d.return_pct is not None
    ]
    report = run_walk_forward(decision_dicts, model_name=f"run_{args.run_id[:8]}")
    print(report.summary())
    if args.save_csv:
        report.save_csv(args.save_csv)
    if args.save_yaml:
        report.save_locked_policy_yaml(args.save_yaml)
    if args.stability_report:
        print(report.parameter_stability_report())
```

**Tests added:** `tests/test_replay_walk_forward_integration.py`
- `test_walk_forward_subcommand_runs_on_sufficient_decisions()`
- `test_walk_forward_subcommand_rejects_insufficient_n()`
- `test_walk_forward_decision_dict_keys_match_walk_forward_expectations()`

**Acceptance criterion:** `walk-forward` subcommand runs end-to-end on a replay store with ≥20 decisions. `locked_policy.yaml` is written. Stability grade appears in output.

---

#### Sprint B3: Wire baselines into summary output

**Files changed:** `ops/historical_replay.py`, `intelligence/replay_summary.py`

The `baselines.py:BaselineRunner.run_all()` takes a list of `BaselineCandidate` objects. To generate these from a replay run, we need to know, for each decision that was ELIGIBLE (not just selected), what its characteristics and realized return were.

The current replay store only records SELECTED decisions, not the full eligible universe at each decision date. This is a data availability constraint.

**Near-term solution** — "model decisions as baseline universe": treat all closed decisions as the eligible universe and run baselines A/B/C/D against this set. This is a weaker test but is feasible immediately.

```python
# In cmd_summary():
from bve.analysis.baselines import BaselineRunner, BaselineCandidate, BaselineConfig
candidates = [
    BaselineCandidate(
        ticker=d.ticker,
        return_pct=d.return_pct,
        phase="phase_2",          # approximate — need phase in schema
        catalyst_days_away=d.days_to_catalyst_at_entry,
        ranking_score=d.composite_score,
    )
    for d in decisions if d.return_pct is not None
]
runner = BaselineRunner(BaselineConfig(top_n=2, n_random_trials=1000))
baselines = runner.run_all(candidates)
if summary.mean_return_pct is not None:
    print(runner.print_comparison(summary.mean_return_pct, len(decisions), baselines))
```

**Long-term requirement (Sprint C3):** Store ALL eligible candidates at each decision date in a new `replay_eligible_universe` table, enabling proper baseline comparison against the full opportunity set.

**Schema addition for Sprint A1 (retroactive):** Add `phase` column to `replay_decisions`.

**Tests added:** `tests/test_replay_baselines_integration.py`
- `test_baselines_run_on_closed_decisions()`
- `test_random_baseline_uses_same_n_as_model()`
- `test_model_comparison_outputs_advantage_per_strategy()`

**Acceptance criterion:** `summary` command prints baseline comparison table after significance report. Random baseline (F) shows that model is above X percentile of 1000 random samples.

---

#### Sprint B4: Wire failure_diagnostics into summary output

**Files changed:** `ops/historical_replay.py`

The `failure_diagnostics.diagnose_failures()` takes a list of trade dicts. Add to `cmd_summary()`:

```python
from bve.analysis.failure_diagnostics import diagnose_failures
losing_decisions = [
    {
        "ticker": d.ticker,
        "asset_id": d.asset_id,
        "return_pct": d.return_pct,
        "attribution_type": d.attribution_type,
        "days_to_catalyst": d.days_to_catalyst_at_entry,
        "composite_score": d.composite_score,
    }
    for d in decisions if d.return_pct is not None and d.return_pct < 0
]
if losing_decisions:
    failure_report = diagnose_failures(losing_decisions)
    print(failure_report.summary())
```

Only include this section if there are losing decisions. This prevents empty sections on strong-performing runs.

**Tests:** `tests/test_replay_failure_diagnostics_integration.py`
- `test_failure_diagnostics_runs_on_losing_decisions()`
- `test_failure_report_skipped_gracefully_with_no_losers()`

**Acceptance criterion:** `summary` command prints failure mode breakdown for losing trades.

---

#### Sprint B5: Connect shadow book registration to weekly runner

**Files changed:** `ops/weekly_runner.py`

Currently the weekly runner generates `WeeklyActionableReport` but does not write to the shadow book.

Add to `WeeklyRunner.run()` after actionable generation:

```python
from bve.analysis.shadow_book import ShadowBook
shadow = ShadowBook("outputs/intelligence/shadow_book.db")
shadow.initialize()

for action in weekly_report.actions:
    if action.action == "add" and action.composite_score >= MIN_SHADOW_BOOK_SCORE:
        # Only register if catalyst_date is in the future
        if action.catalyst_date and action.catalyst_date > today:
            shadow.register(
                ticker=action.ticker,
                asset_id=action.asset_id,
                model_score=action.composite_score,
                entry_price_usd=action.current_price_usd or 0.0,
                entry_date=today.isoformat(),
                catalyst_date=action.catalyst_date.isoformat(),
                catalyst_type=action.catalyst_type or "unknown",
                rationale=action.rationale or action.claim_assertion or "",
                max_hold_days=28,
            )
```

`MIN_SHADOW_BOOK_SCORE = 0.55` — only pre-register high-conviction decisions to avoid cluttering the shadow book with marginal calls.

Add a check: if `entry_price_usd` is 0.0, log a warning and skip registration. Shadow book entries require a valid entry price.

**Tests:** `tests/test_weekly_runner_shadow_book.py`
- `test_shadow_book_registration_on_add_signal()`
- `test_shadow_book_skipped_for_past_catalyst()`
- `test_shadow_book_skipped_below_score_threshold()`
- `test_shadow_book_skipped_when_no_entry_price()`

**Acceptance criterion:** Running `weekly_runner.run()` automatically pre-registers qualifying decisions in `shadow_book.db`. `shadow_book summary` shows growing N over weekly runs.

---

### Tier C: Add genuinely missing analytical capabilities

These are new capabilities that do not exist in any form.

---

#### Sprint C1: Attribution return breakdown

**Files changed:** `intelligence/replay_summary.py`, `ops/historical_replay.py`

This is the highest-impact missing feature. Attribution counts exist but not the returns.

**Add to `ReplaySummary`:**

```python
# Per-attribution type: mean return, median return, total signed P&L fraction
attribution_mean_return: dict[str, Optional[float]] = field(default_factory=dict)
attribution_median_return: dict[str, Optional[float]] = field(default_factory=dict)
attribution_pnl_contribution: dict[str, Optional[float]] = field(default_factory=dict)
# P&L contribution = sum(returns_in_type) / sum(abs(all_returns))
# Shows whether a type is a source or drag on total P&L

# Independent decision count
n_independent_decisions: int = 0
# = count of distinct decision_cluster_id values (non-None)
# + count of decisions with NULL decision_cluster_id (each counted separately)
```

**Compute in `ops/historical_replay.py`** `_build_summary()` function:

```python
attribution_returns: dict[str, list[float]] = {}
for d in closed_decisions:
    key = d.attribution_type or "unclassified"
    attribution_returns.setdefault(key, []).append(d.return_pct)

total_abs_pnl = sum(abs(r) for returns in attribution_returns.values() for r in returns)

attribution_mean = {}
attribution_median = {}
attribution_pnl = {}
for atype, returns in attribution_returns.items():
    attribution_mean[atype] = statistics.mean(returns) if returns else None
    attribution_median[atype] = statistics.median(returns) if returns else None
    if total_abs_pnl > 0:
        attribution_pnl[atype] = sum(returns) / total_abs_pnl
    else:
        attribution_pnl[atype] = None

# Independent N
cluster_ids = set()
independent_n = 0
for d in closed_decisions:
    if d.decision_cluster_id and not d.decision_cluster_id.endswith("_no_catalyst"):
        cluster_ids.add(d.decision_cluster_id)
    else:
        independent_n += 1  # no catalyst → each counts separately
independent_n += len(cluster_ids)
```

**Add to `print()`:**

```
  Attribution return breakdown (N=60 raw | 44 independent):
  ─────────────────────────────────────────────────────────────
  Type               N    Mean      Median    P&L contrib
  confirmed_thesis   18   +14.2%    +11.5%    +35.2%   ← skill
  market_drift       10    +3.0%     +2.8%    +07.0%   ← beta
  pos_error           6    +8.4%     +7.0%    +11.8%   ← luck
  timing_error       12    -6.5%     -5.1%    -18.3%   ← learn
  thesis_error       14    -9.1%     -7.8%    -29.6%   ← learn
  unclassified        0      —         —         —
  ─────────────────────────────────────────────────────────────
  Skill-adjusted return: +X.X% (excludes pos_error and market_drift)
  NOTE: confirmed_thesis + thesis_error must be reviewed for quality.
```

**Tests:** `tests/test_replay_attribution_breakdown.py`
- `test_attribution_mean_return_correct_for_known_decisions()`
- `test_pnl_contribution_fractions_sum_to_one_approximately()`
- `test_independent_n_deduplication_by_cluster_id()`
- `test_independent_n_all_unique_when_no_clusters()`
- `test_skill_adjusted_excludes_pos_error_and_market_drift()`
- `test_print_output_contains_attribution_table()`

**Acceptance criterion:** `summary` command prints attribution return table. Independent N is printed alongside raw N. Skill-adjusted return accounts for pos_error and market_drift, not just pos_error.

---

#### Sprint C2: Market regime analysis

**Files changed:** `ops/historical_replay.py` (population of regime fields at resolve time), new `analysis/regime_analysis.py`

XBI/IBB/SPY prices are already in `historical_prices` table (if seeded). The regime fields added in Sprint A1 need to be populated at resolve time.

**Populate in `_step_resolve()`:**

```python
def _fetch_holding_period_return(store, ticker: str, entry_date: date, exit_date: date) -> Optional[float]:
    """Compute close-to-close return for a ticker over a holding period."""
    entry_price = store.get_price(ticker, entry_date)
    exit_price = store.get_price(ticker, exit_date)
    if entry_price and exit_price and entry_price > 0:
        return (exit_price - entry_price) / entry_price * 100
    return None

# At resolve time, for each closed decision:
decision.xbi_return_during_hold = _fetch_holding_period_return(
    store, "XBI", entry_date, exit_date
)
decision.ibb_return_during_hold = _fetch_holding_period_return(
    store, "IBB", entry_date, exit_date
)
decision.spy_return_during_hold = _fetch_holding_period_return(
    store, "SPY", entry_date, exit_date
)
```

**New `analysis/regime_analysis.py`:**

```python
@dataclass
class RegimeSubgroup:
    label: str
    n: int
    mean_return_pct: Optional[float]
    mean_xbi_return: Optional[float]
    xbi_adjusted_alpha: Optional[float]
    hit_rate: Optional[float]

@dataclass
class RegimeReport:
    overall_beta_to_xbi: Optional[float]       # OLS regression coefficient
    xbi_adjusted_mean_return: Optional[float]   # mean_return - beta * mean_xbi
    ibb_adjusted_mean_return: Optional[float]
    spy_adjusted_mean_return: Optional[float]
    subgroups: list[RegimeSubgroup]
    # Subgroups: xbi_above_20d_ma, xbi_below_20d_ma (split by xbi_above_20d_ma_at_entry)
    alpha_survives_xbi_adjustment: bool
    n_with_regime_data: int

def compute_regime_report(decisions: list[dict]) -> RegimeReport:
    """
    Compute XBI-adjusted alpha and regime subgroup analysis.

    Beta estimation: OLS of decision_return ~ xbi_return_during_hold.
    Minimum 15 decisions with non-None xbi_return_during_hold required.

    If beta cannot be estimated (too few regime-matched decisions),
    returns RegimeReport with all Optional fields as None.
    """
```

**Beta estimation notes:**
- Simple OLS: `beta = cov(r_decision, r_xbi) / var(r_xbi)`
- No intercept suppression — alpha = intercept from the regression
- Report both: `mean_raw_return` and `alpha` (intercept)
- If `var(r_xbi)` near zero (all holding periods in same regime), report `beta = None`
- Minimum 15 decisions for beta estimation; below that, report as insufficient

**Add to summary output:**

```
  Market regime analysis (N=38 decisions with XBI data):
  Beta to XBI: 0.62 (R² = 0.18)
  Raw mean return: +3.29%
  XBI-adjusted alpha: +1.84%  ← this is what remains after removing market beta
  XBI above 20d MA at entry: N=24, mean=+4.1% | below: N=14, mean=+1.8%
  [ALPHA SURVIVES XBI ADJUSTMENT: YES]
```

**Seed XBI and IBB prices** at the same time as universe tickers:

```bash
python -m bve.ops.historical_replay seed --tickers XBI IBB SPY --start 2021-01-01 --end 2026-05-15
```

**Tests:** `tests/test_regime_analysis.py`
- `test_beta_estimation_correct_on_synthetic_data()`
- `test_xbi_adjusted_alpha_zero_when_returns_equal_xbi()`
- `test_regime_report_none_when_insufficient_data()`
- `test_subgroup_counts_exhaustive()`
- `test_alpha_flag_false_when_raw_positive_but_xbi_adjusted_negative()`

**Acceptance criterion:** `summary` command prints regime report when XBI data available. `alpha_survives_xbi_adjustment` flag used in graduation check.

---

#### Sprint C3: Permutation test (score-shuffle)

**Files changed:** `analysis/replay_significance.py`

The full eligible-universe permutation test requires storing all eligible candidates per decision date (not implemented yet). The feasible permutation test shuffles model scores among the decisions that WERE made.

This tests whether the rank-ordering of decisions by composite_score predicts their returns. It does not test whether the decision to enter vs. not-enter was skilled.

**Add to `replay_significance.py`:**

```python
@dataclass
class PermutationResult:
    n: int
    observed_score_return_corr: float    # Pearson r between composite_score and return_pct
    permutation_p: float                 # fraction of shuffles with |corr| >= observed
    n_permutations: int
    percentile_vs_random: float          # percentile of observed corr in permutation dist
    skill_in_ranking: bool               # permutation_p < 0.10

def permutation_test(
    decisions: list[dict],
    n_permutations: int = 5000,
    seed: int = 42,
) -> PermutationResult:
    """
    Test whether composite_score rank-orders returns better than random.

    Shuffles composite_score labels among decisions and recomputes score-return
    correlation. The observed correlation is compared to the permutation distribution.

    Note: this tests RANKING skill only. A significant result means higher-scored
    decisions return more than lower-scored decisions. It does not test whether
    any decision should have been made at all.

    Requires: decisions with both composite_score and return_pct populated.
    Minimum: 15 decisions.
    """
```

**Add to the combined significance report in `cmd_summary()`:**

```
  Permutation test (score-return rank correlation):
  Observed Pearson r: +0.24 (positive = higher score → higher return)
  Permutation p-value: 0.043  (fraction of shuffles with |r| >= 0.24)
  Percentile: 96th vs. 5000 random shuffles
  RANKING SKILL: YES (p < 0.10)
```

**Tests:** `tests/test_permutation_test.py`
- `test_permutation_p_uniform_under_null()` — random scores → p ~ U(0,1)
- `test_permutation_detects_perfect_ranking()` — score == return → p = 0
- `test_permutation_reports_percentile_correctly()`
- `test_permutation_minimum_n_enforced()`

**Acceptance criterion:** Permutation test runs as part of `summary` output. `skill_in_ranking` flag appears in graduation summary section.

---

#### Sprint C4: Trading friction model

**Files changed:** new `analysis/friction_model.py`, `ops/historical_replay.py`

**`analysis/friction_model.py`:**

```python
@dataclass(frozen=True)
class FrictionModel:
    """
    Simulates execution costs for a small-cap biotech strategy.

    Default parameters represent a realistic small fund trading $1-5M positions
    in mid-cap biotech names.
    """
    entry_timing_delay_days: int = 1    # days between signal and execution
    slippage_bps: float = 12.0          # one-way market impact
    bid_ask_half_spread_bps: float = 15.0  # typical for $500M–$5B cap names
    commission_bps: float = 1.0         # institutional commission
    max_pct_adv: float = 0.05           # cap at 5% of 20-day avg dollar volume

    @property
    def round_trip_cost_bps(self) -> float:
        """Total round-trip friction in basis points."""
        return 2 * (self.slippage_bps + self.bid_ask_half_spread_bps + self.commission_bps)

    def net_return(self, gross_return_pct: float) -> float:
        return gross_return_pct - self.round_trip_cost_bps / 100

INSTITUTIONAL_FRICTIONS = FrictionModel(
    entry_timing_delay_days=1,
    slippage_bps=15.0,
    bid_ask_half_spread_bps=20.0,
    commission_bps=1.0,
)
RETAIL_FRICTIONS = FrictionModel(
    entry_timing_delay_days=0,
    slippage_bps=5.0,
    bid_ask_half_spread_bps=8.0,
    commission_bps=0.5,
)
```

**Populate `friction_cost_bps` and `net_return_pct` in `_step_resolve()`** using `INSTITUTIONAL_FRICTIONS.round_trip_cost_bps` by default.

**Update `ReplaySummary`:**

```python
gross_mean_return_pct: Optional[float] = None       # = current mean_return_pct
net_mean_return_pct: Optional[float] = None         # after institutional frictions
friction_cost_mean_bps: Optional[float] = None      # avg round-trip cost in bps
friction_model_label: str = "institutional"
```

**Print both gross and net:**

```
  Mean return (gross): +3.29%
  Mean return (net):   +2.55%  (after ~74 bps round-trip institutional frictions)
  NOTE: all significance tests below use NET return.
```

**After this sprint:** all graduation gates use net return, not gross. The significance test in Sprint B1 must be updated to use `net_return_pct`.

**Tests:** `tests/test_friction_model.py`
- `test_net_return_less_than_gross()`
- `test_round_trip_cost_bps_calculation()`
- `test_institutional_frictions_higher_than_retail()`
- `test_friction_applied_symmetrically_to_winners_and_losers()`

**Acceptance criterion:** `summary` command prints gross and net return. Significance test uses net return. Graduation gates reference net return.

---

### Tier D: Data expansion

These sprints require external data collection. They cannot be automated. Code scaffolding can be built in parallel but the data gates the graduation outcome.

---

#### Sprint D1: Run full 2021–2026 replay and document the gap

**No code changes required.** Execute using existing infrastructure.

**Step 1: Seed XBI, IBB, SPY prices** (needed for regime analysis):

```bash
python -m bve.ops.historical_replay seed \
  --tickers XBI IBB SPY \
  --start 2021-01-01 \
  --end 2026-05-15
```

**Step 2: Full replay run** with best-guess parameters before walk-forward selection:

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

**Step 3: Record results in `outputs/validation/replay_run_audit_v1.yaml`:**

```yaml
run_date: 2026-05-16
parameters:
  start: 2021-01-01
  end: 2026-05-15
  max_hold_days: 28
  min_thesis_score: 0.5
  require_catalyst_days: 90
results:
  raw_n_decisions: ~
  independent_n_decisions: ~
  mean_return_pct: ~
  net_mean_return_pct: ~
  hit_rate: ~
  cluster_t_stat: ~
  graduation_flag: ~
gap_analysis:
  current_independent_n: ~
  research_grade_target: 100
  gap: ~
  primary_constraint: price_data / event_density / universe_size
```

**Step 4: Run walk-forward on this run's decisions** (Sprint B2 required first):

```bash
python -m bve.ops.historical_replay walk-forward --run-id <id> \
  --save-yaml outputs/validation/locked_policy_v1.yaml
```

**Step 5: Run separate max_hold_days seeds**:

```bash
# Hold 14 days
python -m bve.ops.historical_replay run --max-hold-days 14 [...]
# Hold 45 days
python -m bve.ops.historical_replay run --max-hold-days 45 [...]
```

Compare three runs: `compare_hold_days({14: decisions_14, 28: decisions_28, 45: decisions_45})`.

**Acceptance criterion:** Gap to research-grade graduation is quantified. Primary constraint (universe size vs. event density vs. parameter sensitivity) identified.

---

#### Sprint D2: Tier 1 universe expansion (20–30 new tickers)

**Goal:** Increase independent N toward the 100 research-grade threshold.

**Selection methodology:**

Candidates must satisfy ALL of the following, evaluated as of 2021-01-01 (not retroactively filtered by outcome):

1. Listed on NYSE or NASDAQ
2. yfinance price history available from at least 2020-01-01
3. Had Phase 2 or Phase 3 clinical trial with primary completion date in 2021–2026 (query clinicaltrials.gov)
4. Market cap > $150M at start of their first eligible catalyst year
5. At least 2 identifiable catalyst events in 2021–2026 with public announced_at dates

Explicitly exclude any ticker selected because its performance in 2021–2026 is known. Selection criteria must be structural, not outcome-based.

**Source registries:** `src/bve/entities/target_registry_*.py` — these have 198 targets. Filter by the above criteria.

**Event seeding protocol:**

For each new ticker, insert into `historical_events` only events with known `announced_at` dates from contemporaneous public sources (press releases, SEC 8-K filings). Do not infer announced_at dates from trial completion dates.

**Minimum event quality bar per ticker:**
- `announced_at` must be before or on `event_date`
- `source` must be one of: "press_release", "sec_8k", "clinicaltrials_gov", "fda_calendar"
- `outcome_label` must be `NULL` for future events, or one of {"positive", "negative", "mixed", "inconclusive"} for past events

Seed XBI/IBB/SPY prices (Sprint D1) before seeding new tickers.

**Acceptance criterion:** Universe ≥ 50 tickers. Full replay re-run shows independent N ≥ 80. Event density report shows ≥ 1.5 catalysts per ticker-year on average.

---

#### Sprint D3: Tier 2 universe expansion (further 30–50 tickers)

Same selection methodology as Sprint D2 with slightly relaxed criteria:
- Market cap floor lowered to $80M
- One identifiable catalyst event allowed (vs. two in Tier 1)
- Tickers with incomplete price history before 2022 allowed if 2022–2026 data exists (reducing effective window)

**Target:** independent N ≥ 180 after Sprint D3.

---

#### Sprint D4: POS dataset expansion — immunology

**Priority within Tier D:** Highest, because the model currently has zero validated predictive capability outside oncology, and this limits BD usefulness.

**Minimum viable dataset for immunology:**

- N ≥ 75 labeled programs
- Phase 2 and Phase 3 transitions only (no Phase 1 or NDA)
- At least 50% must have known `moa_precedent`, `endpoint_type`, `biomarker_enriched` features
- `readout_date` and `known_at_date` both required — point-in-time discipline
- Outcome labels restricted to `success` or `failure` only (no `immature` or `terminated_business_reason` in primary set)

**Data sources (priority order):**
1. FDA Drugs@FDA database — approval dates for successful programs
2. Citeline/Evaluate Pharma pipeline tracker — Phase 2/3 completions with outcomes
3. Biomedtracker historical database — if accessible
4. Manual review of key sponsor press releases for top 50 RA/SLE/atopic derm/IBD programs

**Indication focus for initial 75 programs:**
- Rheumatoid arthritis: ~25 programs (largest labeled dataset, well-studied endpoints)
- Atopic dermatitis / psoriasis: ~20 programs (clear endpoint precedent)
- IBD (Crohn's/UC): ~20 programs
- SLE: ~10 programs

**After data collection:** Run `run_pos_calibration_from_records()` against the immunology dataset. Compare immunology AUC/Brier to oncology baseline. If performance degrades significantly (AUC drops below 0.60 for immunology), diagnose which features differ most between TAs.

**Schema:** `research/data/pos_outcomes/immunology_outcomes.csv` using the standard schema defined in the plan section below.

**Acceptance criterion:** immunology dataset N ≥ 75 with both success and failure labels. `pos_calibration.py` reports immunology-specific Brier, AUC, ECE. Shrinkage calibration applied if N < 100.

---

## IV. Complete Data Schemas

These schemas are fixed. Any future data collection must conform to them.

### 4.1 POS outcomes schema

File: `research/data/pos_outcomes/{ta}_outcomes.csv`

```
program_id          — unique string e.g. "imm-2015-001"
company             — sponsor name
drug                — INN or code name
indication          — free text clinical indication
therapeutic_area    — oncology | immunology | cns | cardiovascular | metabolic | rare_disease
modality            — small_molecule | biologic_antibody | biologic_other | cell_therapy | gene_therapy | adc | oligonucleotide
phase               — phase_2 | phase_3
trial_design        — "randomized_controlled" | "single_arm" | "platform" | "basket"
endpoint_type       — hard_clinical | surrogate_validated | surrogate_novel | composite | biomarker_only
biomarker_selected  — true | false
sample_size         — integer (enrolled)
control_arm         — true | false
readout_date        — ISO date (when primary endpoint data became available)
model_prediction_date — ISO date (must be ≤ readout_date)
known_at_date       — ISO date (must be ≤ model_prediction_date)
predicted_pos       — float 0.0–1.0 (actual model output; NULL = use reconstructed)
actual_outcome      — success | failure | mixed | terminated_business_reason | immature | unknown
outcome_label       — success | failure (derived; NULL for non-primary outcomes)
failure_reason      — free text (only for failure rows)
source_url          — public source confirming outcome
moa_precedent       — validated | partial | novel
safety_profile      — clean | minor | concerning | serious
competitive_pressure — low | moderate | high
notes               — free text
```

Only rows where `outcome_label` is `success` or `failure` are used in primary validation.

### 4.2 Replay event schema (for `historical_events` table)

```
event_id            — UUID
asset_id            — matches universe asset_id
ticker              — exchange ticker
event_type          — clinical_readout | PDUFA | AdCom | NDA_submission | BLA_submission |
                       trial_start | trial_completion | financing | partnership | competitor_readout |
                       safety_update | M&A_rumor | M&A_confirmed
announced_at        — ISO datetime (when company publicly disclosed; NOT the event_date)
effective_date      — ISO date (actual event date if different from announced_at)
outcome_label       — positive | negative | mixed | inconclusive | NULL (for future events)
headline            — one-line summary
source              — press_release | sec_8k | clinicaltrials_gov | fda_calendar | bloomberg | other
known_at            — ISO date (must be ≤ announced_at; set equal to announced_at by default)
```

---

## V. Graduation Gates (Precise)

### 5.1 POS model graduation

Graduation status is determined by `pos_validation_status()` in `model_grade.py`. The function currently exists with a threshold table. The specific thresholds:

```
UNVALIDATED       : N < 30 OR no labeled outcomes
DIRECTIONAL_ONLY  : 30 ≤ N < 75 OR AUC < 0.65 OR Brier lift < 0.05
RESEARCH_GRADE    : 75 ≤ N < 150 AND AUC ≥ 0.68 AND Brier lift ≥ 0.08 AND ECE ≤ 0.10
SCREENING_GRADE   : 150 ≤ N < 300 AND AUC ≥ 0.70 AND Brier lift ≥ 0.10 AND ECE ≤ 0.08 AND slope ∈ [0.8, 1.2]
DECISION_GRADE    : N ≥ 300 AND ≥3 TAs AND AUC ≥ 0.70 OOS AND Brier lift ≥ 12% AND ECE ≤ 0.07
```

Current oncology status: **RESEARCH_GRADE** (N=99, AUC=0.74).
All other TAs: **UNVALIDATED**.

### 5.2 Historical replay graduation

Graduation is determined by calling `replay_significance.analyze()` and checking multiple criteria. These must ALL pass:

```python
@dataclass
class ReplayGraduationResult:
    # The four criteria that must all pass for research-grade
    cluster_t_passes: bool           # cluster_t > 1.645 (one-sided p < 0.10)
    bootstrap_ci_passes: bool        # 90% CI lower bound > 0
    net_return_positive: bool        # net_mean_return_pct > 0 (after frictions)
    alpha_survives_xbi: bool         # xbi_adjusted_alpha > 0 (requires Sprint C2)

    # Additional criteria for higher grades
    permutation_ranking_skill: bool  # permutation test p < 0.10 (Sprint C3)
    walk_forward_positive_oos: bool  # ≥2 of 3 WF folds OOS return > 0
    independent_n: int

    @property
    def research_grade(self) -> bool:
        return (
            self.cluster_t_passes
            and self.bootstrap_ci_passes
            and self.net_return_positive
            and self.independent_n >= 60
            # alpha_survives_xbi not required for research-grade
        )

    @property
    def screening_grade(self) -> bool:
        return (
            self.research_grade
            and self.alpha_survives_xbi
            and self.permutation_ranking_skill
            and self.independent_n >= 150
        )

    @property
    def institutional_grade(self) -> bool:
        return (
            self.screening_grade
            and self.walk_forward_positive_oos
            and self.independent_n >= 300
        )
```

Current status: **PRE-RESEARCH** (cluster_t likely < 1.645 at N~44 independent).

Note: research-grade requires `independent_n ≥ 60`, not a specific raw N. Independent N will be larger than current ~44 after Schema A1 fix identifies true non-clustered decisions.

---

## VI. Build Order and Dependencies

```
Sprint A1 (schema fix)
  │
  ├── Sprint A2 (walk_forward fix) — depends on A1 (days_to_catalyst field)
  ├── Sprint B1 (wire significance) — independent of A1 (uses asset_id clustering)
  │
Sprint A3 (pos_calibration fix) — independent of A1/A2
  │
  └── Sprint B4/C metrics that use calibration

Sprint A1, A2, A3 must complete before:
  Sprint B2 (walk_forward CLI) — needs days_to_catalyst from A1, fixed grid from A2
  Sprint C1 (attribution breakdown) — needs decision_cluster_id from A1

Sprint B1, B2, B3 (wiring sprints) — can run in any order after their Tier A deps
Sprint B5 (shadow book) — independent of all above

Sprint C1 — needs A1 (decision_cluster_id)
Sprint C2 — needs A1 (xbi_return columns) + D1 step 1 (XBI prices seeded)
Sprint C3 — needs nothing new (uses composite_score and return_pct which exist)
Sprint C4 — can run after B1 (to update significance test to use net return)

Sprint D1 — needs B1, B2, C1, C2 all wired (to get full summary output)
Sprint D2 — needs D1 (to know what independent N gap needs to be closed)
Sprint D3 — needs D2
Sprint D4 — independent of D1-D3 (different track)
```

**Minimum viable path to research-grade:**

```
A1 → B1 → C1 → C4 → D1 → D2
```

This path: fix schema, wire significance, add attribution returns, add frictions, run full window, expand universe. If independent N ≥ 60 and cluster_t > 1.645 and net return positive after D2, the model graduates research-grade.

**All other sprints improve interpretability, institutional credibility, or higher graduation tiers** but are not on the critical path to research-grade.

---

## VII. Anti-Patterns and Red Lines

These are specific mistakes that would compromise the validity of any results reported.

**1. Do not report `walk_forward` graduation before Sprint A2 is complete.**
The `max_hold_days` dimension is broken. Any walk-forward results using current code include a silent no-op parameter and report false stability.

**2. Do not report calibration metrics from `pos_calibration.py` until Sprint A3 is complete.**
All current ECE, Brier, and AUC from the calibration suite use a reconstructed surrogate. The numbers are not wrong by a large margin (the surrogate captures most of the model), but they are methodologically unsound. Do not publish them.

**3. Do not count raw N as the independent decision count.**
Use `n_independent_decisions` from Sprint C1. If Sprint C1 is not complete, report "independent N: unknown" rather than reporting raw N.

**4. Do not tune `min_thesis_score` or `require_catalyst_days` after seeing the full 2021–2026 results.**
These parameters must be locked from the walk-forward training window before the test window is evaluated. Sprint B2 and Sprint D1 must be executed in this order.

**5. Do not add tickers to the Tier 1 universe after seeing their 2021–2026 performance.**
Selection criteria must be specified before looking at outcomes. The tier assignment date must be documented in the run audit file.

**6. Do not report XBI-adjusted alpha before Sprint C2 is complete.**
The current `baselines.py:baseline_e` XBI comparison is a proxy (uses XBI as a candidate if it happens to be in the list, otherwise falls back to universe mean). This is not a proper market adjustment.

**7. Do not claim significance at p < 0.10 using naive SE.**
The `replay_significance.py` module computes both naive and cluster-robust SE. Graduation requires the cluster-robust test to pass, not the naive. Naive SE will always show lower p-values on small samples with clustered decisions.

**8. Do not report `pos_error` decisions as model validation.**
`pos_error` means the thesis was wrong but the stock went up. It is not evidence of model skill. The `skill_adjusted_mean_return_pct` field excludes these — use that field for any performance claim.

**9. Do not remove validation disclaimers from printed output.**
`validation_disclaimer()` in `model_grade.py` is called by every print function. It must not be suppressed. Every human-readable output includes the validation label.

**10. Do not graduate a TA from UNVALIDATED based on the existing `_heuristic_pos_from_row()` calibration path.**
Until Sprint A3 is complete, calibration metrics for non-oncology TAs are computed via the surrogate reconstruction function and are not valid. Run actual model predictions through `to_calibration_records()` for every TA before claiming any calibration result.
