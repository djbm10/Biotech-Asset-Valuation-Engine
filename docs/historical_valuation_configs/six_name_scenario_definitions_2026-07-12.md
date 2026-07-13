# Six-Name Diagnostic — Predetermined Commercial-Prior Scenarios (2026-07-12)

Defined **before** running any of the six names (3 pilots + 3 diagnostic
controls) through `solve_bridged_implied_pos`, per the explicit instruction
not to choose scenario deltas after seeing outputs.

## Scenario deltas

Applied as multipliers on each config's own base-case `market_model`
fields, uniformly across all six names — no name-specific tuning:

| Scenario | `peak_penetration` multiplier | `net_price_per_patient_usd` multiplier | combined commercial-value multiplier (approx.) |
|---|---|---|---|
| **low** | x0.50 | x0.75 | ~0.375x |
| **base** | x1.00 (config as-is) | x1.00 (config as-is) | 1.0x |
| **high** | x1.50 | x1.25 | ~1.875x |

`addressable_patients_annual` is left untouched in all three scenarios —
population size is an epidemiological input, not a commercial-execution
assumption, and varying it would conflate "how many patients exist" with
"how much of the market we capture at what price," which is what these
scenarios are meant to isolate.

For the `lines_of_therapy` market-model mode (if used by any control),
the same two multipliers apply per segment's `peak_penetration` and
`net_price_per_patient_usd` fields.

## Rationale

- Symmetric-ish but not identical (0.375x / 1.0x / 1.875x) rather than a
  flat +/-50% on the combined multiplier, because penetration and pricing
  assumptions carry different degrees of analyst discretion in these
  pilot configs (`peak_penetration` is consistently the more speculative,
  standardized-prior figure across BIND/GNCA/CEMP; `net_price_per_patient_usd`
  is comparatively better-anchored to disclosed class pricing comps) —
  penetration is flexed further in both directions.
- Applied mechanically to all six names via the same multiplier pair, not
  picked per-name, so the resulting spread is informative about model
  sensitivity rather than being reverse-engineered to make any particular
  name solvable.

## What this does NOT do

- Does not touch `success_probability` / trial-level POS inputs — those
  are frozen per-pilot assumptions (already documented in each ledger) and
  are explicitly not to be re-tuned based on observed bridge outcomes.
- Does not compute alpha, hit rate, or any Gate-3 metric from these
  scenario runs — this is a model-behavior diagnostic only.
