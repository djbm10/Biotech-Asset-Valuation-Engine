# PROJECT_STATE.md

## Current Module Being Worked On

**All ROADMAP phases complete (Sprints 10–26C). System is operational.**

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
| **Open-claim gate S28 expanded (38 claims)** | **83** | **+3.76%** | **53.0%** | **~2.28** |

Run ID: `8eed5181-12fb-4b1a-b7d1-00e992e5d01e`

**Statistical status**: t≈2.28 > 1.96 threshold for p<0.05. This is the first run to exceed
the p<0.05 threshold. Attribution: thesis_error=36, market_drift=42, confirmed_thesis=2,
timing_error=3. Hit rate 53% > 50% baseline.

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

**Sprint 28 complete (2026-04-05)** — open-claim gate + expanded claims (38 total).
Best result: N=83, mean=+3.76%, hit rate=53.0%, t≈2.28 (p<0.05).
Test baseline: **2825 passing, 1 skipped** (21 new Sprint 28 tests).

## Graduation Status (2026-04-05)

**Status: ⚠️ Pre-institutional — approaching significance but requires clustered SE and bootstrap CI**

| Criterion | Target | Best run (8eed5181) | Status |
|-----------|--------|---------------------|--------|
| N closed positions | ≥ 30 | **83** | ✅ |
| Mean excess return | > 0% | **+3.76%** | ✅ |
| Hit rate | > 50% | **53.0%** | ✅ |
| Naive t-stat | > 1.65 (p<0.10) | **~2.28** | ✅ |
| Alpha survives clustered SE | p < 0.10 | Not yet computed | ❓ |
| Bootstrap 90% CI excludes 0 | Lower bound > 0 | Not yet computed | ❓ |

## Next Steps

### Option A: Run clustered SE + bootstrap validation (no new code)
With N=83 and t≈2.28, the naive t-stat passes. The remaining hurdles are
clustered standard errors (asset-level) and a bootstrap CI.

```python
# Run Python statsmodels OLS with clustered SE on the 83 decisions
import statsmodels.formula.api as smf
# Group by asset_id for cluster-robust SE
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
- **Sprint 27**: Score decile monotonicity analysis — verify top-score deciles outperform bottom deciles (requires N≥200)
- **Sprint 28**: Live weekly runner automation — cron / systemd timer to run `bve-daily-brief` + `bve-universe-screen` daily and persist to ops.db
- **Sprint 29**: Bootstrap CI and clustered SE on replay returns — complete the remaining ❌ graduation criteria
