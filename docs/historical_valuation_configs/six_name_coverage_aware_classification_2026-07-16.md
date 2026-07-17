# Six-Name Coverage-Aware Classification (2026-07-16)

## Scope and baseline preservation

This applies `src/bve/analysis/coverage_aware_valuation_signal.py`'s
classification layer to the six frozen pilot companies from the 2026-07-15
completeness audit (BIND, GNCA, CEMP, OCUL, ACAD, TSRO). It does not modify
the audit, its frozen configs, `compute_valuation_bridge()` outputs, or the
`six_name_model_behavior_report_2026-07-12.md` / bridge-corrected outputs.
The underlying `market cap`, `net-cash bridge`, `modeled lead value`, and
`unexplained residual` numbers below are the same numbers already published
in the 2026-07-15 audit — this document reclassifies them, it does not
recompute them.

## Method

Each company's component inventory from the 2026-07-15 audit (its CE / SP /
DZ / OM / NK classifications) was mapped onto the coverage-aware signal
module's `ComponentType` / `CoverageStatus` taxonomy and default weights (see
`coverage_aware_signal_v1_spec.md`), then run through
`classify_coverage_aware_signal()`. Mapping notes:

- The audit's paired "clinical/regulatory state (CE) + commercial value (SP)"
  rows for the lead asset collapse to a single `lead_asset` component at
  `modeled_standardized_prior`, since the dollar figure that actually enters
  the bridge is the SP-classified commercial value.
- Audit "DZ" (deliberately assigned zero, not evidenced immaterial) maps to
  `omitted_potentially_material` when the underlying asset genuinely exists
  and has unknown value (e.g. Accurin platform, other clinical pipeline), and
  to `evidenced_immaterial_or_zero` only when the audit's own finding is that
  no such component exists at all (e.g. "no approved product identified at
  the cutoff").
- Two real second-marketed-products the audit filed under "DZ" — OCUL's
  ReSure Sealant and TSRO's VARUBI/VARUBY — are genuinely material and
  disclosed, so they map to `omitted_potentially_material` with
  `critical=True`, not to evidenced-immaterial treatment.
- `corporate_overhead` and `expected_burn` are both `omitted_potentially_material`
  for all six: burn rates are disclosed qualitatively in every audit entry,
  but no company's net-cash bridge actually nets burn or overhead PV
  quantitatively (`known_net_cash_after_burn = cash - debt` in all six
  frozen bridges), so crediting either component would misrepresent what the
  bridge actually did.
- `other_liabilities` is `insufficient_evidence` for all six — the audit did
  not separately assess it.

This mapping is a reclassification exercise on existing audit findings, not
new company research; no new facts, filings, or values were introduced.

## Results

| Ticker | Output class | Weighted completeness | Audit's original (simple-count) score | Critical omissions |
|---|---|---:|---:|---|
| BIND | `PARTIAL_MODEL` | 36% | 33% | none |
| GNCA | `PARTIAL_MODEL` | 36% | 33% | none |
| CEMP | `PARTIAL_MODEL` | 41% | 38% | none |
| OCUL | `PARTIAL_MODEL` | 24% | 30% | ReSure Sealant assigned zero commercial value |
| ACAD | `PARTIAL_MODEL` | 41% | 38% | none |
| TSRO | `PARTIAL_MODEL` | 29% | 33% | VARUBI/VARUBY assigned zero commercial value |

All six are `PARTIAL_MODEL`. None reaches the 70% gate; none is blocked
*only* by the gate — OCUL and TSRO also carry an independent critical
omission from a real second approved product assigned zero value, which
would block full-model eligibility even at a higher aggregate score. The
weighted method disagrees with the audit's original simple-count method on
the exact number for every company (weighted scores range 24–41% vs. the
audit's 30–38%) because it grants partial credit to standardized-prior
components, keeps not-publicly-knowable components in the denominator, and
weights by materiality instead of counting equally — but both methods agree
on the eligibility conclusion for all six.

## Permitted vs. suppressed outputs (all six)

**Permitted** (`PARTIAL_MODEL` outputs): `partial_modeled_value`,
`known_net_cash_after_burn`, `modeled_lead_asset_value`,
`modeled_other_asset_value`, `known_partnership_or_commercial_value`,
`known_liabilities_and_overhead`, `market_value_unexplained`,
`model_completeness_score`, `unmodeled_component_count`,
`unmodeled_material_components`, `critical_omission_reasons`.

**Suppressed** for all six (not present on `PartialModelSignal` — structural,
not a null field): undervalued/overvalued classification, investable
ranking, valuation-gap investment signal, `implied_pos_if_eligible`,
`valuation_gap_ratio`, `equity_value_spread`, `dilution_adjusted_spread`,
`solver_status`. None of the six can claim `modeled_value_lower_bound` —
`lower_bound_requested` was not asserted for any of them, and burn/dilution/
overhead are not modeled in any of the six bridges, so the lower-bound
eligibility condition would fail even if requested.

## Per-company detail

### BIND (2015-10-09)

- Market cap $93.79M · known net cash after burn $49.60 (cash $53.4M − debt
  $3.8M) · modeled lead value −$35.00M · `partial_modeled_value` $14.60M ·
  `market_value_unexplained` $79.19M
- Unmodeled material components (8): other clinical assets (Accurin
  candidates), additional indications (mCRPC, other), partnerships/royalties,
  platform (Accurin), corporate overhead, expected burn, expected dilution,
  other liabilities
- Research required to reach full eligibility: value the non-lead Accurin
  pipeline and platform, model partnership/royalty economics beyond the
  zeroed lead royalty, convert disclosed quarterly burn into a corporate
  overhead PV, and resolve dilution timing/size (may remain
  `not_publicly_knowable` even after research — this component alone caps
  achievable completeness below 100% for a company that later required
  financing).

### GNCA (2021-07-02)

- Market cap $122.33M · known net cash after burn $56.40 (cash $66.0M − debt
  $9.6M) · modeled lead value −$40.00M · `partial_modeled_value` $16.40M ·
  `market_value_unexplained` $105.93M
- Unmodeled material components (8): other clinical assets (GEN-009),
  additional GEN-011 indications, partnerships/royalties, platform (ATLAS),
  corporate overhead, expected burn, expected dilution, other liabilities
- Research required: value GEN-009 and additional GEN-011 solid-tumor
  optionality, value ATLAS platform/partnering economics, convert disclosed
  burn/runway guidance into corporate overhead PV. Dilution likely remains
  not-publicly-knowable given active ATM usage at the cutoff.

### CEMP (2016-11-03)

- Market cap $395.47M · known net cash after burn $248.90 (cash $248.9M −
  debt $0.0M) · modeled lead value −$5.00M · `partial_modeled_value`
  $243.90M · `market_value_unexplained` $151.57M
- Unmodeled material components (7): other clinical assets (other antibiotic
  pipeline), additional indications (gonorrhea), partnerships/royalties,
  corporate overhead, expected burn, expected dilution, other liabilities
  (platform is `evidenced_immaterial_or_zero` — no distinct material platform
  was identified)
- Research required: value the disclosed other-antibiotic pipeline and the
  gonorrhea indication, model partnership economics, convert disclosed
  quarterly burn into corporate overhead PV. This is the smallest remaining
  gap of the six (7 unmodeled components, no critical omission) — see the
  recommended next pilot in the spec doc.

### OCUL (2022-04-01)

- Market cap $372.26M · known net cash after burn $112.73 (cash $164.164M −
  debt $51.435M) · modeled lead value $25.00M (DEXTENZA) ·
  `partial_modeled_value` $137.73M · `market_value_unexplained` $234.53M
- Unmodeled material components (9), **including one critical omission**:
  ReSure Sealant (critical — real second marketed product zeroed), other
  clinical pipeline (OTX-TKI, OTX-TIC, dry-eye), additional DEXTENZA
  indications, partnerships/royalties, platform (hydrogel), corporate
  overhead, expected burn, expected dilution, other liabilities
- Research required: value ReSure Sealant's actual commercial contribution
  first (the critical blocker independent of the aggregate score), then the
  clinical pipeline, additional DEXTENZA label breadth, and hydrogel platform
  optionality.

### ACAD (2021-04-01)

- Market cap $4,095.60M · known net cash after burn $631.96 (cash $631.958M
  − debt $0.0M) · modeled lead value $673.00M (NUPLAZID PDP) ·
  `partial_modeled_value` $1,304.96M · `market_value_unexplained` $2,790.64M
- Unmodeled material components (7): other clinical assets (trofinetide,
  ACP-044, ACP-319), additional indications (NUPLAZID DRP, schizophrenia),
  partnerships/royalties, corporate overhead, expected burn, expected
  dilution, other liabilities (platform is `evidenced_immaterial_or_zero` —
  no distinct material platform was identified)
- Research required: value the three disclosed clinical programs and the DRP/
  schizophrenia expansion, model partnership economics, convert disclosed
  burn into corporate overhead PV. Tied with CEMP for smallest remaining gap
  (7 unmodeled components, no critical omission), but the unmodeled dollar
  magnitude (three clinical programs plus a label expansion) is larger than
  CEMP's.

### TSRO (2017-12-01)

- Market cap $4,631.17M · known net cash after burn $380.87 (cash $521.265M
  − debt $140.4M) · modeled lead value $990.00M (ZEJULA) ·
  `partial_modeled_value` $1,370.87M · `market_value_unexplained` $3,260.31M
- Unmodeled material components (8), **including one critical omission**:
  VARUBI/VARUBY (critical — real second marketed product zeroed), other
  clinical assets outside the flagship, additional ZEJULA
  indications/geographies, partnerships/royalties, corporate overhead,
  expected burn, expected dilution, other liabilities (platform is
  `evidenced_immaterial_or_zero`)
- Research required: value VARUBI/VARUBY's actual commercial contribution
  first (the critical blocker), then non-flagship clinical assets and ZEJULA
  geographic/indication expansion. Also carries the audit's noted convertible
  -debt fair-value measurement caveat ($751.4M fair value vs. $140.4M
  carrying value), which should be resolved before any future full-model
  attempt even though it does not appear as a separate component here.

## Conclusion

Under the coverage-aware signal's materiality-weighted method, none of the
six pilot companies is eligible for `FULLY_MODELED_VALUATION`, matching the
audit's own conclusion under its simpler method. OCUL and TSRO have an
additional, independent blocker (a real disclosed second product assigned
zero value) that would need to be resolved even if their aggregate scores
crossed 70% some other way. CEMP and ACAD have the fewest unmodeled
components (7 each, no critical omission) and are the most plausible
starting points for the coverage-uplift pilot recommended in
`coverage_aware_signal_v1_spec.md`.
