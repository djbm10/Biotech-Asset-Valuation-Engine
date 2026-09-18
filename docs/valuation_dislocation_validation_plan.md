# Valuation Dislocation Engine — Validation Plan (not a build plan)

> **Status:** planning only. No code in this doc. Keep this file **untracked**
> (same policy as `future_help.md`, `conviction_generalization_plan.md`,
> `idea20_backtest_plan.md`).
>
> **The question being answered:** *Does point-in-time, dilution-adjusted biotech
> rNPV — compared against enterprise value — contain investable information beyond
> simpler benchmarks, once failed/delisted/acquired companies are included?*
>
> **Correction this plan makes to the original ask:** this is **not** a "build Engine 1
> from scratch" project. Nearly every component the original four-engine plan called
> for already exists, tested, in this repo. The actual work is closing one gap
> (survivorship bias) and running the existing harness at real N — then reading the
> result honestly. If the answer is "no signal," stop here; do not build the event,
> M&A, or short engines.

---

## 0. What already exists (confirmed in-tree, not assumed)

| Plan component | Existing implementation | State |
|---|---|---|
| Point-in-time company valuation (cash, debt, share count) | `entities/company_snapshot.py` — `CompanySnapshot` with `ReviewerState` lifecycle (`draft → reviewed → approved ← quarantined ← stale`), gated eligibility (`approved` + `pack_version ≥ 1` + not stale) | Built, tested (`test_company_snapshot.py`) |
| Point-in-time company SOTP (asset rNPVs + dated market cap + dated balance sheet) | `analysis/company_sotp.py` (2,253 lines) — explicit provenance/coverage flags, dated replay balance-sheet snapshots | Built, tested (`test_company_sotp.py`, `test_company_sotp_backtest.py`, `ops/test_company_sotp_backfiller.py`) |
| Market-implied POS / peak-sales back-solve | `analysis/implied_pos.py`, `analysis/implied_probability.py` | Built, tested (`test_implied_pos.py`, `test_implied_expectations.py`, `test_p17_market_implied_pos.py`) |
| Dilution scenarios | `models/dilution_model.py` | Built, tested (`test_p19_runway_dilution.py`, `test_p22_financing_dilution.py`) |
| Runway / burn forecasting | `models/runway_forecast.py` | Built, tested (same P19/P22 tests) |
| Robustness / baseline comparison (vs XBI, reversal, equal-weight, etc.) | `analysis/baselines.py` — baselines A–G | Built, tested (`benchmark/test_baselines.py`) |
| Historical replay of the dislocation signal vs. XBI | `analysis/historical_implied_pos_validation.py` — `HistoricalImpliedPoSValidator`, forward-hold-window excess-return comparison | Built, tested (`test_historical_implied_pos_validation.py`) — **not yet run at scale with a published result** |
| Product surface | `bve-morning-screen` (§2 "Top Valuation Dislocations, sorted by absolute implied upside"), `bve-evaluate-target`, `bve-validate` | Shipped, documented in `docs/PRODUCT_SPEC.md` v2.0 (2026-05-26) |

`docs/PRODUCT_SPEC.md`'s own trust table already says the honest thing: rNPV/NAV is
"model-dependent," M&A probability is "directional," and **"Backtest alpha (replay)"
is "Not yet actionable — directionally positive, statistically underpowered"** (N≈60–130
vs. ~111 needed). That line refers to the ops/`historical_replay` conviction-driven
decision replay. The implied-PoS dislocation harness in this plan is a *different*
module with its own test coverage — but no dated report shows it has ever been run
end-to-end at real N. That is the actual gap.

---

## 1. The gap that defines this project

`analysis/historical_implied_pos_validation.py` has **no survivorship-bias handling**:
grep confirms zero references to delisted, bankrupt, or acquired names anywhere in the
file. It draws its asset universe from curated watchlists
(`examples/configs/watchlists/*.yaml` — `watchlist_stage1.yaml`, `watchlist_rvmd.yaml`,
etc.), all of which list currently-tracked, currently-live companies, and reads prices
from `ReplayStore` (yfinance-backed).

This is the same class of gap CLAUDE.md already documents for `portfolio_backtest.py`
("delisted names are excluded from yfinance returns"). It exists here too, just
undocumented. **Any dislocation signal measured on a survivor-only watchlist is
unreliable by construction** — a "cheap and stays cheap because the science was wrong
and the company went to zero" case is exactly the failure mode a valuation-dislocation
strategy must be tested against, and today it cannot be, because those companies are
not in the eligible universe at all.

---

## 2. Immediate scope — what to actually do

**Do not build new valuation, dilution, or SOTP logic. It exists.** The work is:

### 2.1 Survivorship-inclusive universe (the blocker)

- Build or extend a watchlist (or new config format) that includes failed / delisted /
  acquired companies alongside live ones.
- **Correction (locked, see §2.1a):** these 30 adverse-outcome names are a **stress-test
  cohort**, not the validation sample itself. They are deliberately enriched for extreme
  outcomes to test terminal-value/exit-handling logic. The actual G3 "does the signal
  beat baselines" test must run on a separately constructed, representative point-in-time
  investable universe (winners + ordinary survivors + failures, not just failures) — see
  §2.1b. Conflating the two would trade survivorship bias for an equally invalid adverse-
  selection bias.

#### 2.1a Exit-price conventions by outcome type (locked)

The naive framing in the original draft — "acquired names exit at the deal price" —
introduces hindsight (you don't know a deal will close at signing) and would quietly
convert this into a merger-arbitrage backtest instead of a valuation-dislocation one.
Corrected conventions, by outcome type:

| Outcome | Engine 1 exit convention |
|---|---|
| Definitive acquisition | Exit at the **first realistically tradable close after the announcement**, not the eventual deal price |
| Acquisition already announced before entry | **Exclude as an entry** — including it tests merger arbitrage, not valuation dislocation |
| Bankruptcy | Mark to market through the last tradable date, then use **actual shareholder recovery**; default to zero **only** when no distribution is confirmed to have occurred |
| Exchange delisting but OTC trading continues | Continue with the successor ticker and adjusted price history — not an exit |
| Reverse merger | Preserve the original shareholder return through the transaction, **including the conversion ratio**; flag separately since the investment thesis may have changed post-merger |
| Liquidation / wind-down | Include actual cash distributions, CVRs, and final liquidation payments |
| Ticker / name change | Link security identifiers; not an exit |
| Data disappears with no verified corporate action | **Quarantine** — do not auto-assign −100% |

This applies to `historical_implied_pos_validation.py`'s current fixed-hold-window logic
(`exit_date = snapshot_date + timedelta(days=self.hold_days)`), which needs a per-outcome
early-exit path per the table above rather than one blanket rule.

#### 2.1b Two-cohort design (locked)

Run two separate analyses, not one:

1. **Point-in-time investable universe** — winners, ordinary survivors, and failures in
   realistic proportion. This is the sample G3 (signal vs. baselines) must run on. Not
   yet built — a separate task from the 30-name cohort below.
2. **The 30-name adverse-outcome cohort** (`research/universe/failed_delisted_biotech_candidates.csv`)
   — used only as a **survivorship and terminal-value stress test**: does the exit-price
   mapping in §2.1a behave sensibly on the hardest cases? This cohort does not answer G3
   on its own and must never be substituted for the representative universe.

### 2.2 Run the existing harness, don't rewrite it

- `HistoricalImpliedPoSValidator` already does the point-in-time solve + forward
  excess-return comparison against XBI. Run it twice: once against the representative
  investable universe (§2.1b.1, answers G3), once against the 30-name stress cohort
  (§2.1b.2, answers G1/G2/G4 on exit-handling robustness only).
- Compare against `analysis/baselines.py` (A–G) — already built, already the right
  comparison set. No new baseline code needed.

### 2.3 Report honestly

- One dated report under `docs/vision_reports/` (e.g.
  `valuation_dislocation_validation_<date>.md`): N, excess return distribution vs. each
  baseline, whether failed/acquired inclusion changes the sign or magnitude of the
  result, and an explicit insufficient-N flag if N < the threshold needed for the
  claimed effect size at p<0.10 (same discipline as the existing replay N≈111 threshold
  — compute the equivalent number for this sample, don't reuse 111 blindly).

### 2.4 Shadow-mode integration (only if §2.3 is positive)

- `bve-morning-screen`'s "Top Valuation Dislocations" section already surfaces this
  signal today — it does not need new plumbing to display results. What it lacks is a
  validated survivorship-inclusive backtest behind it. If §2.3 comes back positive at
  sufficient N, the existing screen output can be annotated with a validation citation.
  If not, no product change is needed — the screen already carries a "directional, not
  validated" framing per PRODUCT_SPEC's trust table.

---

## 3. What should remain out of scope

Same exclusions as the original four-engine plan, restated because they remain correct:

- Real-time/continuous news ingestion
- Trial-result expectation reconstruction (catalyst engine)
- Options/borrow data, short recommendations
- Acquisition prediction refinements (already has its own infra — `acquirer_fit`,
  `acquisition_readiness` — not touched here)
- Relative-value pair matching
- Trade execution

None of these are dependencies of proving or disproving the foundational thesis.

---

## 4. Validation gates (continuous, not a Phase-4 afterthought)

| Gate | Question | Pass condition |
|---|---|---|
| G1 | Can historical valuation snapshots be reconstructed without leakage for failed/acquired names, not just survivors? | No-lookahead assertable; acquired-name exits use deal date, not a fixed hold window |
| G2 | Are the model-implied POS estimates economically sensible on the expanded universe? | Spot-check a handful of failed-company implied-POS values against what was actually priced in pre-failure |
| G3 | Does the dislocation signal outperform `baselines.py` A–G on the expanded universe? | Excess return vs. each baseline, with confidence bands |
| G4 | Does performance persist once dilution, slippage, and failed-company inclusion are all included? | Same sign/magnitude as G3 with failed names in vs. out |
| G5 | Does prospective shadow performance (going forward) resemble the backtest? | Requires a live shadow period after G3/G4 pass — not gated on this doc alone |

### Current validation status (as of 2026-07-16)

- **Gate 1** (point-in-time reconstruction): demonstrated as feasible on the
  six-name pilot sample (`docs/historical_valuation_configs/six_name_completeness_audit_2026-07-15.md`
  and its underlying frozen configs) — but **not yet proven at cohort
  scale**. No-lookahead, per-outcome exit handling (§2.1a) has not been run
  against a real survivorship-inclusive cohort.
- **Gate 2** (economic sensibility of implied POS): the universal,
  company-level implied-PoS approach **failed economic-sensibility testing**
  on the six-name pilot — required peak-sales multiples of 1.5x–9.6x and
  required penetration exceeding 100% for four of six names, with the
  other two reversing to non-monotonic before reaching an interior root.
  Gate 2 is now **conditional**: implied PoS may only be published for a
  company that separately clears the coverage-aware signal's
  `FULLY_MODELED_VALUATION` eligibility (see
  `coverage_aware_signal_v1_spec.md`), not for any company with a
  computable market-cap residual.
- **Gate 3** (signal vs. baselines): **blocked**. It requires both (a) a
  coverage-aware signal that can tell a fully-modeled company apart from a
  partial one (built and unit-tested this workstream — see
  `coverage_aware_signal_v1_spec.md` and
  `src/bve/analysis/coverage_aware_valuation_signal.py`) and (b) an eligible,
  representative cohort where a meaningful fraction of names actually clear
  the 70% completeness gate. Neither the six-name pilot nor any larger
  cohort has yet produced a company that clears it — all six score 24–41%
  under the weighted method (see
  `six_name_coverage_aware_classification_2026-07-16.md`). Gate 3 cannot be
  attempted until a coverage-uplift pilot (see the spec's recommended next
  step) demonstrates that real companies can be honestly raised above 70%.
- **Gates 4–5**: not started. Both depend on Gate 3 passing first.

---

## 5. Phasing

| Phase | Deliverable | Acceptance criterion |
|-------|-------------|----------------------|
| P0 | Confirm exact failure-mode handling per delisted/acquired name (terminal price vs. deal price vs. exclusion) | Documented per-company in the new watchlist config, not inferred |
| P1 | Build the 30–50 name survivorship-inclusive watchlist (live + failed + acquired) | Config file exists, reviewed, matches CLAUDE.md's existing survivorship-bias warning |
| P2 | Extend `historical_implied_pos_validation.py` only as needed for early-exit-on-acquisition | Unit test proves acquired names exit on deal date, not `hold_days` later |
| P3 | Run harness vs. `baselines.py` A–G on expanded universe | G1–G4 answered with N and bands |
| P4 | Dated report + Tool Update | First defensible, survivorship-inclusive dislocation result, honestly scoped |

---

## 6. The decision this unlocks (and only this)

**The question, stated plainly:** *does point-in-time, dilution-adjusted rNPV vs. EV
contain investable information once failed companies can't silently disappear from the
sample?*

- **If yes**, at sufficient N: the existing `bve-morning-screen` dislocation section
  earns a validated citation, and only then does it become worth discussing the
  catalyst/event-expectation engine, the M&A engine, or the short engine described in
  the original four-engine plan.
- **If no, or unmeasurable at this N**: stop. Do not build the event-expectation
  pipeline, the M&A optionality engine, or the short engine. The dislocation signal
  stays what PRODUCT_SPEC.md already honestly calls it — directional, not validated —
  and the weekly runner's existing composite ranking is not replaced.

**Non-goal:** this plan does not improve the valuation math, the SOTP builder, or the
dilution model. All three already exist and are not the bottleneck. It tells us whether
the survivorship-corrected version of what's already built contains signal worth acting
on.
