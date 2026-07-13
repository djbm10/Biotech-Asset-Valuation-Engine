# Bridge-Corrected Outputs — BIND / GNCA / CEMP (2026-07-12)

This note documents the output of `solve_bridged_implied_pos()`
(`src/bve/analysis/valuation_bridge.py`) against the three pilot configs in
`examples/configs/pit/`, replacing the raw-market-cap-as-EV figures reported
in `docs/historical_valuation_configs/three_pilot_report_2026-07-12.md`
Section 5. It exists to satisfy the audit's requirement to document the
corrected bridge outputs as part of the same commit as the bridge code
itself, rather than leaving the numbers only in ad hoc verification output.

## The bug being corrected

The three-pilot report computed `EV = entry price x shares_outstanding` and
passed that number directly to `ImpliedPoSSolver.solve()` as
`current_ev_millions`. `ImpliedPoSSolver` performs no cash/debt netting
internally (locked by `tests/test_implied_pos_legacy_equation.py`) — it
treats whatever value it is given as directly comparable to
`model_rnpv_millions`, an asset-only quantity. Raw market cap therefore
overstates the value that must be explained by the asset by the full amount
of the company's net cash (and, more generally, by any other-asset/platform
value not carved out).

## Corrected figures

| | BIND | GNCA | CEMP |
|---|---|---|---|
| price | $4.52 | $2.25 | $7.55 |
| shares outstanding (M) | 20.75 | 54.37 | 52.38 |
| **market cap ($M)** | 93.79 | 122.33 | 395.47 |
| cash ($M) | 53.4 | 66.0 | 248.9 |
| debt ($M) | 3.8 | 9.6 | 0.0 |
| net cash ($M) | 49.6 | 56.4 | 248.9 |
| other-asset / platform / overhead terms | 0 (documented simplification) | 0 (documented simplification) | 0 (documented simplification) |
| **residual asset value ($M)** | 44.19 | 65.93 | 146.57 |
| net cash as % of market cap | 52.9% | 46.1% | 62.9% |
| **solver status** | `REQUIRED_POS_ABOVE_ONE` | `REQUIRED_POS_ABOVE_ONE` | `REQUIRED_POS_ABOVE_ONE` |
| model value at PoS=1.0 ($M) | -27.0 | -3.0 | (below residual; see note) |
| remaining gap ($M) | 71.2 | 68.9 | n/a |
| required peak-sales multiple (vs. base case) | 1.82x | 1.54x | ~9.5x |

CEMP's required-peak-sales multiple (~9.5x, regression-pinned in
`tests/test_valuation_bridge.py::test_cemp_pilot_moves_off_ceiling_ambiguity_with_quantified_gap`
at `abs=0.5`) is far larger than BIND's or GNCA's because solithromycin's
modeled base-case peak sales are small relative to the $146.6M residual —
the same accounting fix that shrinks CEMP's raw ambiguity the most (net
cash was 63% of its market cap) still leaves the largest proportional gap
once the asset-only value is isolated.

## What changed vs. the original three-pilot report

The original report's Section 5 table labeled `price x shares = market
cap` as "EV" for all three names, and separately noted all three saturated
the solver's `max_pos=0.99` ceiling — an outcome that could not
distinguish "just barely above 0.99" from "wildly unreachable" across the
three names. The corrected bridge:

1. Nets cash and debt out of market cap before comparing to model rNPV,
   removing $49.6M (BIND), $56.4M (GNCA), and $248.9M (CEMP) of value that
   was never attributable to the modeled asset in the first place.
2. Replaces the silent 0.99 clamp with an explicit `SolverStatus`
   (`REQUIRED_POS_ABOVE_ONE` for all three names here) plus quantified
   diagnostics: how much value is still unexplained after netting
   (`remaining_gap_millions`), and what multiple of assumed peak sales
   would be required to close that gap at PoS=1.0
   (`required_peak_sales_multiple`).

## What this does not change

The bridge fix materially shrinks the unexplained residual — most
dramatically for CEMP — but **none of the three pilots flip to
`SOLVABLE`**. All three still require a PoS above 1.0 (equivalently, peak
sales materially above the pilot configs' base-case assumptions) to
rationalize their entry prices under the current asset-only model. This is
reported as a finding, not tuned away: per explicit instruction, pilot
assumptions are not being adjusted post hoc to force a solvable result.
The corrected diagnostics do, however, differentiate the three names in a
way the old ceiling could not — BIND and GNCA's required multiples (1.8x,
1.5x) are far more modest than CEMP's (~9.5x), suggesting the size of the
unexplained residual, not just its sign, is informative and should carry
into the six-name diagnostic report (Section 8 of the governing audit).

## Reproducing these numbers

```python
from bve.analysis.valuation_bridge import compute_valuation_bridge, solve_bridged_implied_pos

bridge = compute_valuation_bridge(
    price=7.55, shares_outstanding_millions=52.38,
    cash_millions=248.9, debt_millions=0.0,
)
result = solve_bridged_implied_pos(
    "examples/configs/pit/cemp_solithromycin_pit_2016-11-03.yaml", bridge,
)
```

Analogous calls for BIND (`examples/configs/pit/bind_bind014_pit_2015-10-09.yaml`,
price=4.52, shares=20.75, cash=53.4, debt=3.8) and GNCA
(`examples/configs/pit/gnca_gen011_pit_2021-07-02.yaml`, price=2.25,
shares=54.37, cash=66.0, debt=9.6) reproduce the corresponding rows above.
