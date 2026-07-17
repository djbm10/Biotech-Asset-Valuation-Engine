# Coverage-Aware Valuation Dislocation Signal V1 — Specification

## Status

Specification + unit-tested classification module. **No alpha, hit-rate, or
realized-return analysis has been run.** No investment threshold has been
selected. Nothing here is wired into shadow-mode or live scoring.

## What this workstream is for

Commit `962e322` (six-name completeness audit, 2026-07-15) established that a
company-level implied-PoS solve is not currently eligible for broad use: all
six frozen pilot configs score 30–38% complete by the audit's own (simple,
non-weighted) method, and none reaches a coverage level where a market-cap
residual can be safely attributed to the lead asset alone.

The purpose of this workstream is narrower than building the dislocation
signal itself: **prevent a partial company model from being compared against
the market value of an entire company and mislabeled undervalued or
overvalued.** A model that has only represented 30–40% of a company's
material components is not entitled to an opinion about whether the other
60–70% (whatever it is) is mispriced. The coverage-aware signal is a gate,
not a valuation engine — it decides *whether* a company is eligible to
receive `FULLY_MODELED_VALUATION` outputs (spread, gap ratio, implied PoS)
before any of those numbers are produced or interpreted.

The underlying question the broader program is answering is unchanged:

> Does conservative, point-in-time, dilution-adjusted biotech valuation
> contain investable information beyond simple benchmarks?

This spec does not answer that question. It defines the eligibility layer
that must exist before a cohort-scale attempt to answer it can be trusted.

## Relationship to the existing validation plan

`docs/valuation_dislocation_validation_plan.md` defines gates G1–G5 for the
broader dislocation-signal validation program. This workstream sits inside
G1/G2 and is a precondition for G3. See the "Current validation status"
section added to that document for the explicit gate-by-gate status this
spec updates.

## Implementation

- Module: `src/bve/analysis/coverage_aware_valuation_signal.py`
- Tests: `tests/test_coverage_aware_valuation_signal.py`
- Six-name application: `docs/historical_valuation_configs/six_name_coverage_aware_classification_2026-07-16.md`

The module is additive. It does not replace `analysis/valuation_bridge.py`'s
`compute_valuation_bridge()` / `solve_bridged_implied_pos()`, which remain
operational and are what the six-name audit and its bridge outputs continue
to use unchanged. `classify_coverage_aware_signal()` sits in front of
research reporting: it decides which of that bridge's outputs (if any) are
safe to publish for a given company at a given point in time.

## Three mutually exclusive output classes

Every company/point-in-time snapshot resolves to exactly one of:

### A. `FULLY_MODELED_VALUATION`

**Eligibility** (all required):

- `model_completeness_score >= 0.70` (provisional threshold, see below)
- no critical material component is omitted
- point-in-time market capitalization and share count are available
- net cash, debt, burn, dilution, and corporate overhead are represented
  (i.e. carry a credited `CoverageStatus`, not `omitted_potentially_material`
  / `not_publicly_knowable` / `insufficient_evidence`)
- all material approved products, clinical assets, indications,
  partnerships, and liabilities are represented or explicitly evidenced as
  immaterial (`evidenced_immaterial_or_zero`)
- scenario valuation completes successfully (`scenario_valuation_completed`
  and non-null `scenarios`)
- no unresolved date-contract or material provenance violation

**Outputs**: `scenario_weighted_equity_value`, `conservative_equity_value`,
`base_equity_value`, `upside_equity_value`, `equity_value_spread`,
`valuation_gap_ratio`, `dilution_adjusted_spread`, `robustness_status`,
`implied_pos_if_eligible`, `solver_status` (+ `solver_diagnostics` when the
solver did not resolve to a clean value in [0, 1]).

**Implied PoS** requires further, independent eligibility even inside this
class:

- the valuation function is monotonic (checked, not assumed — the six-name
  audit found endpoint-only monotonicity checks miss interior reversals;
  the reporting contract now grids the domain)
- lead-asset attributable market value can be isolated
- no material unmodeled company component remains
- the solved value falls in [0, 1]

If any of these fail, `implied_pos_if_eligible` is `None` and
`solver_status` / `solver_diagnostics` carry the reason (e.g.
`non_monotonic`, `required_pos_above_one`) instead of silently reporting a
clamped value like 0.99.

### B. `PARTIAL_MODEL`

Used when the accounting bridge (cash, debt, at least the lead asset) is
available but coverage is below 70%, or a potentially material component is
omitted regardless of aggregate score.

**Outputs**: `partial_modeled_value`, `known_net_cash_after_burn`,
`modeled_lead_asset_value`, `modeled_other_asset_value`,
`known_partnership_or_commercial_value`, `known_liabilities_and_overhead`,
`market_value_unexplained`, `model_completeness_score`,
`unmodeled_component_count`, `unmodeled_material_components`,
`critical_omission_reasons`.

**Explicitly withheld**: undervalued/overvalued classification, investable
ranking, valuation-gap investment signal, implied PoS. The dataclass simply
does not carry these fields — `hasattr(result, "valuation_gap_ratio")` is
`False` on a `PartialModelSignal`, not a suppressed/null value on a shared
schema. This is enforced structurally, not by convention.

`value_label` is `"modeled_value_lower_bound"` only when **all** of the
following hold: `lower_bound_requested`, `all_negative_claims_modeled`,
`all_overhead_modeled`, `all_dilution_modeled`, `all_liabilities_modeled`,
and every omitted component is explicitly flagged
`omitted_value_constrained_nonnegative=True`. Otherwise it is
`"partial_modeled_value"` — no implicit claim that the omissions can only
help, not hurt, the estimate.

### C. `INSUFFICIENT_EVIDENCE`

Used when point-in-time price, share count, cash, debt, pipeline identity,
or date-contract resolution is missing, or a material provenance violation
exists.

**Outputs**: `signal_status`, `missing_required_inputs`,
`research_priority`, `coverage_failure_reasons`. No valuation comparison, no
ranking.

## Weighted completeness methodology

Completeness is **not** a count of populated fields. Each potentially
material component carries:

| Field | Purpose |
|---|---|
| `component_type` | which of the 12 `ComponentType` buckets (below) |
| `estimated_materiality_weight` | fixed ex-ante weight, not fit to outcomes |
| `coverage_status` | one of the six `CoverageStatus` values |
| `evidence_type` | filing / disclosure / regulatory / market / standardized prior / analyst derivation / none |
| `point_in_time_source` | citation, when credited |
| `knowability_date` | when the value became knowable pre-cutoff |
| `modeled_value_millions` | the number actually used, when credited |
| `omission_reason` | required whenever the status is a blocking one |

### Coverage statuses and credit

| `CoverageStatus` | Credit | Meaning |
|---|---:|---|
| `modeled_company_specific` | 1.0 | Company-specific, pre-cutoff evidence |
| `modeled_standardized_prior` | 0.5 | Modeled, but the number itself is a standardized industry prior, not company-specific |
| `evidenced_immaterial_or_zero` | 1.0 | Evidenced that the component does not apply / is genuinely zero (not merely a modeling simplification) |
| `omitted_potentially_material` | 0.0 | Exists, is potentially material, not modeled — triggers the critical-omission gate when `critical=True` |
| `not_publicly_knowable` | 0.0 | Not knowable with useful precision at the cutoff (e.g. future financing terms) |
| `insufficient_evidence` | 0.0 | Not assessed / evidence quality too low to classify |

`score = sum(weight * credit) / sum(weight)` — see
`calculate_weighted_completeness()`. Components with 0 credit still count in
the denominator (unlike the six-name audit's original simple-count method,
which excluded `not_publicly_knowable` items from the denominator entirely —
see "Relationship to the six-name audit's original score" below).

### Component types and default weights (sum to 1.00)

| `ComponentType` | Weight |
|---|---:|
| `lead_asset` | 0.20 |
| `other_clinical_assets` | 0.12 |
| `additional_indications` | 0.08 |
| `approved_commercial_products` | 0.12 |
| `partnerships_royalties` | 0.08 |
| `platform_technology` | 0.05 |
| `cash_marketable_securities` | 0.08 |
| `debt_senior_claims` | 0.06 |
| `corporate_overhead` | 0.06 |
| `expected_burn` | 0.06 |
| `expected_dilution` | 0.07 |
| `other_liabilities` | 0.02 |

These weights are a provisional V1 allocation, fixed before any cohort-level
return work, not derived from or fit to the six pilot companies. A
multi-asset company can split a type's allocation across several
`ComponentCoverage` records that share the same `component_type`.

### Critical-omission gate

Any component flagged `critical=True` that resolves to a blocking status
(`omitted_potentially_material` or `insufficient_evidence`) forces
`PARTIAL_MODEL` regardless of the aggregate score — a 90%-complete company
missing one critical component (e.g. a disclosed second approved product)
does not get to claim `FULLY_MODELED_VALUATION`. `not_publicly_knowable`
does not trigger the critical gate, since by definition no amount of
research effort resolves it before the cutoff.

### The 70% threshold is provisional

It is not derived from, and must not be adjusted to fit, the six existing
pilot outputs (all of which score well below it under this weighted method).
Changing it after seeing those scores would be fitting the gate to the
sample it is meant to gate.

## Relationship to the six-name audit's original score

The 2026-07-15 audit used a deliberately simple method: `count(CE) /
count(publicly knowable)`, with `not_publicly_knowable` (NK) items excluded
from the denominator and no partial credit for standardized priors (SP). All
six configs scored 30–38% under that method.

Re-running the same underlying component classifications through the
materiality-weighted method in this spec produces different (not
necessarily higher or lower) scores per company, because it (a) grants
partial credit to standardized-prior components instead of zero credit, (b)
keeps `not_publicly_knowable` components in the denominator rather than
excluding them, and (c) weights components by estimated materiality instead
of counting them equally. See
`six_name_coverage_aware_classification_2026-07-16.md` for the resulting
per-company scores (24–41%) — still uniformly below the 70% gate, which is
the load-bearing conclusion this spec needs: **the two methods disagree on
the exact number but agree on the eligibility conclusion.**

## Recommended next coverage-uplift pilot

The smallest pilot that could plausibly move a company above 70% without
hindsight or unreasonable research burden: **pick the single company with
the fewest, most concretely researchable omitted components and attempt to
convert them from `omitted_potentially_material` to
`modeled_company_specific` or `evidenced_immaterial_or_zero` using only
pre-cutoff public filings.**

Based on the six-name application (see the classification report), **CEMP**
and **ACAD** are the best candidates — both already score 41% under the
weighted method with only 7 unmodeled components each, no critical omission,
and a small number of disclosed-but-unvalued items (CEMP: other antibiotic
pipeline, partnership economics, corporate overhead PV; ACAD: trofinetide,
ACP-044, ACP-319, partnership economics, corporate overhead PV). Converting
`corporate_overhead` (0.06) and `partnerships_royalties` (0.08) from omitted
to modeled — both are usually derivable from the same 10-K/10-Q used for
cash and debt, without any new company research — would already add 14
points, and would be the cheapest, most mechanical first uplift step to
pilot before attempting harder components like other-clinical-asset SOTPs.
This pilot should be scoped as: does honestly modeling corporate-overhead PV
and partnership/royalty economics from already-collected filings move CEMP
and ACAD meaningfully closer to 70%, and does the same mechanical step
generalize to the other four names? It should not by itself be expected to
clear the gate — closing `other_clinical_assets` (0.12) and
`additional_indications` (0.08) will still be required and is a larger,
separate research question explicitly out of scope here.
