# Six-Name Model-Behavior Diagnostic Report (2026-07-12)

Three distressed/bankrupt pilots (BIND, GNCA, CEMP) plus three mechanically
selected diagnostic controls (OCUL — cash-rich flagship-plus-tail survivor;
ACAD — genuinely multi-asset company; TSRO — early-launch, eventually-
acquired company), run through `solve_bridged_implied_pos()` under the
original (unnetted) equation, the corrected bridge at base commercial
assumptions, and the three predetermined low/base/high scenarios defined in
`six_name_scenario_definitions_2026-07-12.md` **before** any of these
numbers were generated.

This is a model-behavior diagnostic only. It does not compute alpha, hit
rate, or a Gate-3 metric, and no pilot or control assumption was adjusted
after seeing its output.

## Headline table (base-case commercial assumptions)

| Ticker | Category | Market cap ($M) | Net cash ($M) | Residual ($M) | Original-equation required multiple | Corrected-bridge required multiple | Status |
|---|---|---|---|---|---|---|---|
| BIND | distressed pilot | 93.79 | 49.6 | 44.19 | 2.39x | 1.82x | `REQUIRED_POS_ABOVE_ONE` |
| GNCA | distressed pilot | 122.33 | 56.4 | 65.93 | 1.99x | 1.54x | `REQUIRED_POS_ABOVE_ONE` |
| CEMP | distressed pilot | 395.47 | 248.9 | 146.57 | 24.15x | 9.50x | `REQUIRED_POS_ABOVE_ONE` |
| OCUL | cash-rich survivor (not strictly single-asset) | 372.26 | 112.73 | 259.53 | n/a (control) | 9.65x | `REQUIRED_POS_ABOVE_ONE` |
| ACAD | multi-asset company | 4095.60 | 631.96 | 3463.64 | n/a (control) | 5.09x | `REQUIRED_POS_ABOVE_ONE` |
| TSRO | eventually-acquired company | 4631.17 | 380.87 | 4250.31 | n/a (control) | 4.25x | `REQUIRED_POS_ABOVE_ONE` |

"Original-equation" = raw market cap passed to the solver with zero netting
(reproducing the pre-fix bug); computed only for the 3 pilots, since the
controls were never run under the old equation. Every one of the six names
lands in `REQUIRED_POS_ABOVE_ONE` at base-case assumptions — this is a
central, load-bearing finding of this diagnostic, not an artifact of one
pilot's circumstances (see Q1 below).

## Full results across low / base / high commercial-prior scenarios

| Ticker | low (0.375x) | base (1.0x) | high (1.875x) |
|---|---|---|---|
| BIND | `NON_MONOTONIC` | `REQUIRED_POS_ABOVE_ONE`, 1.82x | `SOLVABLE`, implied PoS = 0.938 |
| GNCA | `NON_MONOTONIC` | `REQUIRED_POS_ABOVE_ONE`, 1.54x | `SOLVABLE`, implied PoS = 0.688 |
| CEMP | `REQUIRED_POS_ABOVE_ONE`, 26.76x | `REQUIRED_POS_ABOVE_ONE`, 9.50x | `REQUIRED_POS_ABOVE_ONE`, 5.18x |
| OCUL | `REQUIRED_POS_ABOVE_ONE`, 26.05x | `REQUIRED_POS_ABOVE_ONE`, 9.65x | `REQUIRED_POS_ABOVE_ONE`, 5.21x |
| ACAD | `REQUIRED_POS_ABOVE_ONE`, 13.59x | `REQUIRED_POS_ABOVE_ONE`, 5.09x | `REQUIRED_POS_ABOVE_ONE`, 2.71x |
| TSRO | `REQUIRED_POS_ABOVE_ONE`, 11.34x | `REQUIRED_POS_ABOVE_ONE`, 4.25x | `REQUIRED_POS_ABOVE_ONE`, 2.27x |

## Answering the six questions

**1. Does the corrected bridge change the qualitative conclusion from the
three-pilot report, or only the magnitude?**
Only the magnitude, for the three original pilots. All three still require
PoS above 1.0 at base-case assumptions both before and after the bridge
fix — netting cash/debt shrinks the residual materially (especially for
CEMP, where net cash was 63% of market cap) and shrinks the required
multiple accordingly (BIND 2.39x→1.82x, GNCA 1.99x→1.54x, CEMP 24.15x→9.50x),
but does not flip any of the three to solvable. The qualitative conclusion
("the market price cannot be rationalized by this asset-only model at
base-case assumptions") survives the accounting fix unchanged; only the
size of the gap the model must explain shrinks.

**2. Is `REQUIRED_POS_ABOVE_ONE` unique to distressed/failed names, or does
it also appear for ordinary survivors and successes?**
It also appears for all three controls, at base-case assumptions. This is
the most important finding of this diagnostic: `REQUIRED_POS_ABOVE_ONE` is
NOT a distress-specific signature. A cash-rich, non-distressed survivor
(OCUL), a genuinely multi-asset company (ACAD), and an early-launch
eventually-acquired company (TSRO) all land in the identical status as the
three failed pilots. The status alone cannot distinguish "the market is
irrationally pricing in failure risk this model doesn't capture" from "the
market is correctly pricing in real value (pipeline, optionality, control
premium) this narrow asset-only model was never built to capture."

**3. For the multi-asset control (ACAD), does the gap look like a pipeline-
attribution artifact rather than a genuine mispricing signal?**
Yes, and this is by design and by construction, not incidental. ACAD's
config deliberately models only the marketed NUPLAZID PDP indication and
treats the DRP sNDA, the schizophrenia Phase 3 program, trofinetide,
ACP-044, and ACP-319 — five real, disclosed, pre-cutoff pipeline programs —
as unmodeled "other assets" (bridge default of 0). ACAD's $3.46B residual
and required 5.09x multiple should be read primarily as "the bridge has no
real estimate of ACAD's substantial pipeline value to net out," not as
"the market is overpricing NUPLAZID specifically." This is exactly the
kind of pipeline-driven ceiling case the audit anticipated, and the
`other_asset_value_millions=0.0` default's documented-simplification
notes (in every `ValuationBridgeResult`) exist precisely to flag it.

**4. For the cash-rich, non-distressed control (OCUL), does the same
required-multiple pattern appear even without distress?**
Yes — OCUL's base-case required multiple (9.65x) is comparable in
magnitude to CEMP's (9.50x), despite OCUL being an ordinary, non-distressed
commercial-stage survivor rather than a company that went bankrupt. Two
compounding factors are documented, not hidden: OCUL is not strictly
single-asset either (a second marketed product plus an active pipeline are
unmodeled, per finding #2 in its ledger), and this config's DEXTENZA
commercial assumptions are order-of-magnitude standardized priors rather
than a DEXTENZA-specific commercial model. The size of OCUL's gap is
therefore not surprising once its own limitations section is read, but the
fact that it lands in the same status bucket as a bankrupt pilot, at a
similar multiple, is direct evidence for the answer to Q2: status alone is
not diagnostic of company health.

**5. Does the eventually-acquired control (TSRO) show any distinguishing
signature — e.g., a smaller required multiple, or `SOLVABLE` at high
commercial assumptions — that would suggest the model is at least
partially detecting real value the market later confirmed?**
No, and the finding here is explicitly counterintuitive and is stated
plainly in TSRO's ledger: the eventual GSK acquisition price ($75.00/share,
announced Dec 2018) was BELOW this snapshot's $85.16/share entry price. The
GSK premium was measured against a depressed 2018 30-day VWAP ($35.67), not
against the Dec 2017 level modeled here. TSRO's required multiple (4.25x
at base) is the smallest of the three post-bridge distressed-adjacent
figures alongside ACAD's (5.09x), but this should not be read as "the model
partially detected the eventual takeout value" — if anything, an investor
using this snapshot's price as an entry point would have been holding above
the eventual deal price for most of the intervening year. This control
does not support a "the model under-detects real M&A value" narrative at
this specific entry date.

**6. Does varying commercial assumptions (low/base/high) reveal materially
different sensitivity across the six names, and does any name become
solvable under a plausible high-case?**
Yes, and this is the most differentiating single result in the whole
diagnostic. BIND and GNCA both flip to `SOLVABLE` under the high-commercial
scenario (implied PoS 0.938 and 0.688 respectively) — meaningfully
different from CEMP, OCUL, ACAD, and TSRO, all four of which remain
`REQUIRED_POS_ABOVE_ONE` even at the high (1.875x) commercial multiplier.
This tells us BIND/GNCA's residuals are within reach of a plausible
commercial-assumption stretch, while CEMP/OCUL/ACAD/TSRO's residuals are
not — a genuinely useful discriminator the old 0.99-ceiling clamp could
never have produced. Separately, BIND and GNCA both hit `NON_MONOTONIC` at
the low-commercial scenario: shrinking peak sales far enough interacts with
the underlying trial-cost structure such that rNPV(PoS) stops increasing
monotonically over the search range, and the explicit-status protocol
correctly flags this as an unresolvable edge case rather than returning a
misleading number. This is itself evidence for the value of replacing the
silent clamp with explicit statuses: a silent solver would have returned
some bisection-search artifact number here with no signal that anything
had gone wrong.

## What this report does not do

- Does not compute alpha, hit rate, or a Gate-3 metric from any of these
  runs.
- Does not adjust any pilot's or control's frozen assumptions in response
  to the observed outputs — every number above was produced from
  assumptions locked before this run (pilots) or set from independently
  verified point-in-time research (controls), and the predetermined
  scenario deltas were fixed before any of the six names were run.
- Does not claim the `REQUIRED_POS_ABOVE_ONE` status is itself informative
  about mispricing without further work — Q2-Q5 above establish the
  opposite: the status is common across genuinely different company
  situations, and distinguishing "real mispricing" from "real unmodeled
  value" requires either richer bridge inputs (a non-zero, evidenced
  `other_asset_value_millions`) or a fundamentally different validation
  design than this six-name diagnostic was scoped to provide.
