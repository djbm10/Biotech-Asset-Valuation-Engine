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

## Last Change

**Sprints 26A/26B/26C complete (2026-03-29)** — see Sprint 26 Summary above.
Test baseline: **2789 passing, 1 skipped** (full suite as of 2026-03-29).

## Next Steps

The system is fully operational. Three potential directions for future work:

### Option A: Accumulate live signal (recommended — no new code)
Run `bve-daily-brief` and `bve-universe-screen` weekly. Use `bve-claim-resolve resolve`
when trial readouts occur to update thesis_strength in real time. After ~3–6 months of
claim resolution, re-run the thesis-gated replay (`--min-thesis-score 0.5`) to see if
N=111 is approaching.

### Option B: Extend replay time range for more statistical power
Seed prices from 2021-01-01 for all 27 universe names (already done) and extend to
2026-03-29. The thesis-gated run needs ~111 trades for p<0.10; extending the window
from 5 years to 6+ years adds ~12 decisions/year at current pace.

```bash
python -m bve.ops.historical_replay run \
    --start 2021-01-01 --end 2026-03-29 --cadence weekly \
    --decision-policy top2_add --max-hold-days 28 \
    --max-decisions-per-asset 15 --min-thesis-score 0.5
```

### Option C: New feature sprint
Candidate sprints not yet implemented:
- **Sprint 27**: Score decile monotonicity analysis — verify top-score deciles outperform bottom deciles (requires N≥200)
- **Sprint 28**: Live weekly runner automation — cron / systemd timer to run `bve-daily-brief` + `bve-universe-screen` daily and persist to ops.db
- **Sprint 29**: Bootstrap CI and clustered SE on replay returns — complete the remaining ❌ graduation criteria
