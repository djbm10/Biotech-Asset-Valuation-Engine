# Slice-2 Materiality Mapping Audit (report-only)

**Date:** 2026-06-22
**Question:** Does the repo have enough structural alignment between
`_meta.defaulted_fields` (what the config-quality dashboard flags) and the
tornado/sensitivity parameters to support a materiality ranking — *without
inventing precision*?

**Scope:** read-only. No materiality implementation. This decides only whether
slice 2 is worth building.

---

## Inputs

- **Defaulted fields** observed across `examples/configs/auto_generated/*.yaml`
  (51 configs). Distinct economic fields and their frequency are in the table.
- **Tornado parameters**: `analysis/sensitivity.py` defines 8 `SensitivitySpec`s
  (`pos`, `peak_sales`, `penetration`, `discount_rate`, `patent_life`, `g2n`,
  `tax_rate`, `competition`). This is the active path
  (`valuation_engine.py` → `compute_sensitivity`).
- **Config shapes**: every config carries *both* legacy `market_model` scalars
  (TAM / net price / penetration / patent life) *and* a `commercial_inputs`
  decomposition (patient_pool / pricing / share). 50/51 have a non-null
  `total_addressable_market_millions`.

## Decisive structural fact

The tornado shocks **legacy `market_model` scalars + asset + trial fields
only**. It never reads or perturbs the `commercial_inputs` decomposition.
Moreover `peak_sales` and `g2n` both branch on TAM: *if TAM is present they shock
TAM*, else net price. Because 50/51 configs have TAM, **`net_price_per_patient_usd`
is never the shock target for this corpus**, and `addressable_k` / `wac_per_year_usd`
/ `gross_to_net_rate` (the very fields the dashboard flags as "derived") are
invisible to sensitivity.

## Mapping table

| defaulted_field | n | config location / shape | candidate sensitivity param | status | notes |
|---|---|---|---|---|---|
| success_probability | (trials) | `trials[].success_probability` | `pos` | **exact** | direct shock; rarely in defaulted list (profile usually supplies) |
| peak_penetration | 20 | `market_model.peak_penetration` | `penetration` (+`competition`) | **exact** | direct shock target |
| discount_rate | 20 | `asset.discount_rate` | `discount_rate` | **exact** | direct |
| patent_life_years | 20 | `market_model.patent_life_years` | `patent_life` | **exact** | direct |
| total_addressable_market_millions | 20 | `market_model.*` | `peak_sales` / `g2n` | **exact** | direct shock when TAM present (50/51) |
| net_price_per_patient_usd | 20 | `market_model.*` + `commercial_inputs.pricing.wac_per_year_usd` | `peak_sales`/`g2n` (fallback only) | **derived → unmapped** | shocked only when TAM absent; TAM present in 50/51, so never the bar in practice |
| (commercial_inputs.pricing.gross_to_net_rate) | 51 | `commercial_inputs.pricing` | `g2n` (mislabeled) | **ambiguous** | `g2n` spec actually shocks TAM/net price ±10%, not the g2n rate field |
| addressable_patients_annual | 20 | `market_model.*` + `commercial_inputs.patient_pool.addressable_k` | — | **unmapped** | no spec; patient-based revenue path not exercised by tornado |
| endpoint_type | 23 | `trials[].endpoint_type` | `pos` (indirect, via design model) | **ambiguous** | feeds POS log-odds, not a dedicated bar; double-attribution risk with `pos` |
| duration_years | 23 | `trials[].duration_years` | — | **unmapped** | timing affects discounting; no bar |
| cost_millions | 23 | `trials[].cost_millions` | — | **unmapped** | no cost bar in tornado |
| years_to_peak | 23 | `market_model.years_to_peak` + `commercial_inputs.share.years_to_peak` | — | **unmapped** | ramp timing; no bar |
| cogs_rate | 23 | `market_model.cogs_rate` | — | **unmapped** | margin; no bar |
| sgna_rate_launch | 23 | `market_model.sgna_rate_launch` | — | **unmapped** | margin; no bar |
| sgna_rate_mature | 23 | `market_model.sgna_rate_mature` | — | **unmapped** | margin; no bar |

Company-level defaults (`cash_millions`, `shares_outstanding_millions`,
`burn_rate_millions_per_quarter`, `debt_millions`, `current_price`,
`market_cap_millions`) drive per-share / runway, **not** the rNPV tornado —
different output surface; out of scope for materiality-on-rNPV.

## Legacy `market_model` vs `commercial_inputs`

The two shapes coexist in every config but the engine's sensitivity layer is
**legacy-only**. `commercial_inputs` is consumed by the revenue/rNPV build but
the tornado re-shocks the legacy scalars. Consequence: any materiality ranking
keyed off tornado output would attribute $-impact to TAM / penetration /
patent-life / discount / POS, and would be **structurally unable** to attribute
impact to the commercial_inputs sub-fields (`addressable_k`, `wac_per_year_usd`,
`gross_to_net_rate`) that slice-1 specifically flags as coarse/derived.

## Coverage summary

**By distinct economic field (15 rows above):** exact 5 · derived→unmapped 1 ·
ambiguous 2 · unmapped 7.

**By the user's high-leverage core set:**

| core category | status |
|---|---|
| peak share / penetration | ✅ exact |
| success probability | ✅ exact |
| discount rate | ✅ exact |
| addressable population / TAM | ⚠️ TAM exact; addressable population unmapped |
| price / WAC / net price | ❌ unmapped in practice (TAM dominates; WAC/g2n untouched) |
| timing / duration | ❌ unmapped (no bar) |
| cost | ❌ unmapped (no bar) |

≈ 3.5 of 7 core categories map cleanly. Price, timing, and cost — three of the
seven — are unmapped, and the commercial_inputs decomposition is entirely
invisible to sensitivity.

## Verdict

**Do not build a full materiality ranking yet.** The core economic defaults are
*not* mostly exact/defensible-derived: timing, cost, and price (in practice) are
unmapped, and the commercial_inputs layer the dashboard scores is bypassed by
the tornado.

Per the slice-2 stop rule: materiality needs **either** richer config provenance
**or** named sensitivity hooks before a full ranking is defensible. Concretely,
slice 2 should be unblocked by one of:

1. **Named sensitivity hooks** for the missing drivers — add tornado specs that
   shock `cost_millions`, `duration_years`/timing, `cogs_rate`,
   `sgna_rate_*`, and a price bar that perturbs `commercial_inputs.pricing`
   (so net price/WAC/g2n become first-class bars), plus an
   `addressable_k`/patient-pool bar. Then `defaulted_field → spec` is a clean
   join.
2. **Richer config provenance** that records, per defaulted field, which engine
   input it feeds — a static map maintained alongside the generator.

**Defensible interim option (optional, must be scoped honestly):** a *narrow*
materiality layer over only the 5 cleanly-mapped drivers (POS, penetration,
discount_rate, patent_life, TAM). This is buildable today but would silently
omit price, cost, timing, and the entire commercial_inputs layer — so it must be
labelled "partial coverage" or it gives false comfort. Recommendation: prefer
option 1 (named hooks) before shipping any materiality ranking.
