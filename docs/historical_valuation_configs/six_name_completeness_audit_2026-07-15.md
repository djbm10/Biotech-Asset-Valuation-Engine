# Six-Name Model-Completeness and Valuation-Attribution Audit (2026-07-15)

## Scope and baseline preservation

This is the narrow follow-on audit to commit `376bce5`. It uses only the six
already-frozen point-in-time configs and their pre-cutoff evidence. It does not
add historical names, calculate alpha or hit rate, tune an assumption to a
realized return, or assign a plug value to an unknown platform or pipeline.

The pre-audit outputs and configs were not edited. Their pre-audit SHA-256
hashes are:

| Frozen artifact | SHA-256 |
|---|---|
| `six_name_model_behavior_report_2026-07-12.md` | `0c9667fc4794901bbd8bd72f9ce7660b5b161d457b6e6bedd622e7f492327498` |
| `six_name_scenario_definitions_2026-07-12.md` | `fcefc1738be8d3902bc10cca7809251befd997392d7141c20dbc07963dabdafc` |
| BIND config | `2dbb9ece522a08611bd31313038521dce4ad707798f4adc934783bb06f1442e8` |
| GNCA config | `ea8cfd5a3ba2784aeffce38bbe14780b6b92828c32f6637b26549640c284875f` |
| CEMP config | `244a2d44c804f1a0979600222029219f1cb07f4fc24228b005104c8e5557e9b0` |
| OCUL config | `d87bdb76fdf89b70f5ced26c0fbd59daf786497dcf0d167f4aed6fae8e7ec940` |
| ACAD config | `f94f59d7d42bea127160f031b1b307b5f90e3ef5e4666007447bcb18fc2945c0` |
| TSRO config | `cd35f17aef61802a4d4c522128ff90ce6bd8ac812301925de21f6499ad3c2d6c` |

## Classification and score method

The classifications are:

- **CE** — modeled with company-specific, pre-cutoff evidence;
- **SP** — modeled with a standardized prior;
- **DZ** — deliberately assigned zero (a modeling treatment, not proof of no value);
- **OM** — omitted despite being potentially material;
- **NK** — not publicly knowable with useful precision at the cutoff.

A component gets one conservative classification based on its valuation, not
merely whether its existence was disclosed. For example, an approved product
whose addressable population, price, and penetration are generic priors is SP,
even though its approval status is company-specific evidence. This is why lead
clinical/regulatory state and lead commercial value are separate rows.

The `model_completeness_score` is deliberately simple and not outcome-based:

> count of potentially material components modeled with CE / count of
> potentially material components publicly knowable at the cutoff

NK components are excluded from both numerator and denominator. SP, DZ, and OM
components remain in the denominator but not the numerator. No partial credit
or materiality weights are used; those would introduce discretion unsupported
by this six-name diagnostic. A zero debt balance supported by the cutoff filing
is CE because the senior-claim component was actually measured. A zero bridge
value for a disclosed pipeline is DZ and receives no credit.

## Component inventory

### BIND — 2015-10-09

| Potentially valued component | Class | Point-in-time audit finding |
|---|---|---|
| BIND-014 clinical/regulatory state | CE | Phase 2 state and pending readouts were evidenced pre-cutoff. |
| BIND-014 NSCLC commercial value | SP | Phase-transition rates, population, price, penetration, timing, and costs are standardized priors. |
| BIND-014 mCRPC and other indications | OM | Disclosed and potentially material; single-indication config excludes them. |
| Earlier Accurin candidates / other clinical assets | DZ | Known to exist; bridge assigns other assets zero. |
| Partner economics, royalties, milestones, licenses | DZ | Lead royalty is explicitly zero; broader disclosed-collaboration economics are not valued. |
| Accurin platform / technology | DZ | Platform is described but standalone platform value is zero. |
| Approved/commercial products | DZ | No approved product identified at the cutoff; not scored as a material component. |
| Cash and marketable securities | CE | $53.4M from the Q2 2015 10-Q. |
| Debt and senior claims | CE | $3.8M current long-term debt is bridged. |
| Corporate overhead | OM | Burn is evidenced ($9.15M/quarter), but no standalone corporate-cost PV is modeled. |
| Expected dilution | NK | Need for financing was inferable; timing, size, and price were not knowable. |

Score: **3/9 = 33%**.

### GNCA — 2021-07-02

| Potentially valued component | Class | Point-in-time audit finding |
|---|---|---|
| GEN-011 clinical/regulatory state | CE | First-in-human Phase 1/2a status and absence of efficacy data were evidenced. |
| GEN-011 commercial value | SP | Phase mapping, PoS, eligible population, cell-therapy price, penetration, timing, and costs use priors. |
| GEN-009 and other clinical assets | DZ | Disclosed second program; bridge assigns other assets zero. |
| Additional GEN-011 indications | OM | Broad solid-tumor optionality is not separately valued. |
| Partner economics, royalties, milestones, licenses | DZ | Lead royalty is zero and no broader economics are valued. |
| ATLAS platform / technology | DZ | Disclosed platform and partnering optionality receive zero. |
| Approved/commercial products | DZ | None identified at cutoff; not scored as a material component. |
| Cash and marketable securities | CE | $66.0M pre-cutoff balance is bridged. |
| Debt and senior claims | CE | $9.6M borrowings are bridged. |
| Corporate overhead | OM | $12.4M quarterly burn and runway guidance are evidenced, but corporate-cost PV is zero. |
| Expected dilution | NK | ATM use made dilution risk visible; future issuance quantum and price were unknowable. |

Score: **3/9 = 33%**.

### CEMP — 2016-11-03

| Potentially valued component | Class | Point-in-time audit finding |
|---|---|---|
| Solithromycin CABP regulatory state | CE | NDA status plus manufacturing and liver-signal disclosures are used in the derived PoS. |
| Solithromycin CABP commercial value | SP | Patient count, course price, penetration, launch timing, and cost structure are priors. |
| Solithromycin gonorrhea / other indications | OM | Disclosed studied indication is excluded. |
| Other antibiotic assets | DZ | Broader pipeline is acknowledged but assigned zero in the bridge. |
| Partner economics, royalties, milestones, licenses | DZ | Lead royalty and all other licensing economics are valued at zero. |
| Platform / technology | DZ | No distinct material platform identified; not scored as material. |
| Approved/commercial products | DZ | None identified at cutoff; not scored as material. |
| Cash and marketable securities | CE | $248.9M is bridged from the Q3 2016 10-Q. |
| Debt and senior claims | CE | No long-term-debt line was identified; evidenced zero is represented. |
| Corporate overhead | OM | $23.75M quarterly burn is evidenced, but corporate-cost PV is zero. |
| Expected dilution | NK | Future financing need, amount, and terms were not publicly knowable. |

Score: **3/8 = 38%**.

### OCUL — 2022-04-01

| Potentially valued component | Class | Point-in-time audit finding |
|---|---|---|
| DEXTENZA approved/commercial state | CE | Approval, label expansion, and commercial status are evidenced. |
| DEXTENZA commercial value | SP | Population, net price, penetration, timing, and margins are standardized priors. |
| Additional DEXTENZA indications | OM | Label breadth is combined rather than separately modeled and evidenced. |
| OTX-TKI, OTX-TIC, and dry-eye pipeline | DZ | Disclosed clinical pipeline receives zero other-asset value. |
| ReSure Sealant | DZ | Second marketed product is disclosed but receives zero commercial value. |
| Partner economics, royalties, milestones, licenses | DZ | No nonzero economics are represented. |
| Hydrogel platform / technology | DZ | Disclosed platform underlying multiple programs receives zero. |
| Cash and marketable securities | CE | $164.164M is bridged from the FY2021 10-K. |
| Debt and senior claims | CE | $51.435M notes and convertible debt are bridged. |
| Corporate overhead | OM | No standalone corporate-cost PV is modeled. |
| Expected dilution | NK | Timing, amount, and terms of future issuance were not knowable. |

Score: **3/10 = 30%**.

### ACAD — 2021-04-01

| Potentially valued component | Class | Point-in-time audit finding |
|---|---|---|
| NUPLAZID PDP approved/commercial state | CE | Approval and $441.755M FY2020 product revenue are evidenced pre-cutoff. |
| NUPLAZID PDP commercial value | SP | The revenue anchor is only a sanity check; the modeled population, price, penetration, timing, and margins remain priors. |
| NUPLAZID DRP and schizophrenia indications | DZ | Both are disclosed; DRP is structurally excluded and all expansion value is zero. |
| Trofinetide, ACP-044, and ACP-319 | DZ | Three disclosed clinical programs receive zero other-asset value. |
| Other approved/commercial products | DZ | None identified at cutoff; not scored as material. |
| Partner economics, royalties, milestones, licenses | DZ | No nonzero economics are represented. |
| Platform / technology | DZ | No separate material platform identified; not scored as material. |
| Cash and marketable securities | CE | $631.958M cash plus securities are bridged. |
| Debt and senior claims | CE | No notes/long-term debt were identified; evidenced zero is represented. |
| Corporate overhead | OM | Operating liabilities and company costs are not converted to corporate-cost PV. |
| Expected dilution | NK | Future issuance quantum and terms were not knowable. |

Score: **3/8 = 38%**.

### TSRO — 2017-12-01

| Potentially valued component | Class | Point-in-time audit finding |
|---|---|---|
| ZEJULA approved/early-launch state | CE | US approval and launch state are evidenced; EU timing remained less certain in the frozen evidence. |
| ZEJULA commercial value | SP | Population, price, penetration, launch curve, margins, and patent life are standardized priors. |
| ZEJULA additional indications / geographies | OM | Expansion and geographic optionality are not separately modeled. |
| Other clinical assets | OM | Company pipeline outside the flagship is not valued. |
| VARUBI/VARUBY | DZ | Second marketed product is disclosed but assigned zero. |
| Partner economics, royalties, milestones, licenses | DZ | No nonzero economics are represented. |
| Platform / technology | DZ | No separate material platform identified; not scored as material. |
| Cash and marketable securities | CE | $521.265M is bridged from the Q3 2017 10-Q. |
| Debt and senior claims | CE | $140.4M carrying value is bridged; the filing's $751.4M fair value exposes a material measurement caveat. |
| Corporate overhead | OM | No standalone corporate-cost PV is modeled. |
| Expected dilution | NK | Future issuance was not knowable; in-the-money converts also complicate fully diluted equity value. |

Score: **3/9 = 33%**.

## Completeness conclusion

| Ticker | CE / knowable material components | Score | Eligibility implication |
|---|---:|---:|---|
| BIND | 3 / 9 | 33% | Ineligible for company-level implied PoS |
| GNCA | 3 / 9 | 33% | Ineligible for company-level implied PoS |
| CEMP | 3 / 8 | 38% | Ineligible for company-level implied PoS |
| OCUL | 3 / 10 | 30% | Ineligible for company-level implied PoS |
| ACAD | 3 / 8 | 38% | Ineligible for company-level implied PoS |
| TSRO | 3 / 9 | 33% | Ineligible for company-level implied PoS |

The scores are not company-quality scores. They measure coverage of the frozen
configs. All six configs are good enough to diagnose solver behavior and none
is complete enough to treat a company-level residual as if it belonged only to
the lead asset.

## Market-to-model attribution

The additive identity below is exact for the frozen base-case runs:

> market cap = net cash + modeled lead value + modeled other-asset value +
> partnered/commercial/platform value - corporate-cost adjustment +
> unexplained residual

All dollar values are millions. Negative lead value is possible because the
engine includes risk-adjusted development costs. Zero other/partner/corporate
columns are documented omissions or simplifications, not findings of zero
economic value.

| Ticker | Market cap | Net-cash bridge | Modeled lead | Modeled other assets | Partnered / commercial / platform | Corporate-cost adjustment | Unexplained residual |
|---|---:|---:|---:|---:|---:|---:|---:|
| BIND | 93.79 | 49.60 | -35.00 | 0.00 | 0.00 | 0.00 | 79.19 |
| GNCA | 122.33 | 56.40 | -40.00 | 0.00 | 0.00 | 0.00 | 105.93 |
| CEMP | 395.47 | 248.90 | -5.00 | 0.00 | 0.00 | 0.00 | 151.57 |
| OCUL | 372.26 | 112.73 | 25.00 | 0.00 | 0.00 | 0.00 | 234.53 |
| ACAD | 4,095.60 | 631.96 | 673.00 | 0.00 | 0.00 | 0.00 | 2,790.64 |
| TSRO | 4,631.17 | 380.87 | 990.00 | 0.00 | 0.00 | 0.00 | 3,260.31 |

This decomposition does not claim each residual is economically mysterious.
It says the current model has not attributed it. Pipeline, partnership, and
platform values remain inside the explicit residual until supported values are
available.

## Conditional solver report

The reporting contract now exposes implied PoS only for `SOLVABLE` cases. The
monotonicity gate evaluates a nine-point grid across the 0–1 search domain,
rather than comparing only the two endpoints. For every other status it exposes
the solver status and, where the engine can be evaluated, valuation gap,
required peak sales with PoS held at approximately 100%, required penetration,
and unexplained residual. Required penetration is not capped at 100%; exceeding
100% is a useful infeasibility diagnostic.

This tighter gate changes the *new reporting classification*, not the preserved
July 12 output: BIND and GNCA both decline between the near-zero endpoint and
the first interior grid point at base assumptions. The endpoint-only check in
the pre-audit report missed that reversal and labeled both
`REQUIRED_POS_ABOVE_ONE`. The frozen report remains unchanged as the baseline;
the audited status below is `NON_MONOTONIC`.

| Ticker | Status | Implied PoS | Base valuation gap / unexplained residual ($M) | Value at PoS≈100% ($M) | Required peak sales at PoS≈100% ($M) | Required peak-sales multiple | Required penetration |
|---|---|---:|---:|---:|---:|---:|---:|
| BIND | `NON_MONOTONIC` | — | 79.19 | -27.00 | 189.10 | 1.82x | 21.8% |
| GNCA | `NON_MONOTONIC` | — | 105.93 | -3.00 | 345.58 | 1.54x | 15.4% |
| CEMP | `REQUIRED_POS_ABOVE_ONE` | — | 151.57 | 2.00 | 76.03 | 9.50x | 47.5% |
| OCUL | `REQUIRED_POS_ABOVE_ONE` | — | 234.53 | 26.00 | 125.44 | 9.65x | 77.2% |
| ACAD | `REQUIRED_POS_ABOVE_ONE` | — | 2,790.64 | 680.00 | 1,709.43 | 5.09x | 101.8% |
| TSRO | `REQUIRED_POS_ABOVE_ONE` | — | 3,260.31 | 1,000.00 | 1,698.82 | 4.25x | 106.2% |

The required-sales calculation holds every noncommercial term at the frozen
config value. It is a commercial-stretch diagnostic, not a forecast and not a
license to replace missing SOTP components with higher lead-asset sales.

## Cause attribution

| Ticker | Primary cause(s) of above-one status | What the six-name evidence rules out |
|---|---|---|
| BIND | Non-monotonic lead valuation plus conservative commercial priors and incomplete additional-indication, pipeline, partnership, and platform coverage. | Not primarily stage PoS: value is still short at PoS≈100%. The pre-audit high-commercial root is not eligible until it passes the stricter monotonicity gate. |
| GNCA | Non-monotonic lead valuation plus incomplete GEN-009/ATLAS SOTP and commercial assumptions. | Not primarily stage PoS. The 1.54x commercial requirement remains a stress diagnostic, not an implied probability. |
| CEMP | Narrow single-indication SOTP and very conservative standardized commercial build; the required 47.5% penetration shows PoS alone cannot repair it. | Not a clean stage-PoS signal and not yet a genuinely unexplained market valuation at 38% completeness. |
| OCUL | Missing ReSure, clinical pipeline, and hydrogel-platform value, compounded by a generic DEXTENZA commercial prior. | Distress and stage PoS are not explanations; DEXTENZA was approved and OCUL was an ordinary survivor. |
| ACAD | Incomplete company SOTP is dominant: five disclosed expansion/pipeline programs are zero. Commercial timing/discounting may also matter, but >100% required penetration makes lead-only attribution untenable. | Cannot be interpreted as NUPLAZID implied PoS; it is an approved product and the company completeness score is 38%. |
| TSRO | Missing VARUBI, other pipeline/indications/geographies, early-launch commercial uncertainty, and a material convertible-claim measurement caveat. | Not a clean PoS or M&A-value signal. Required penetration exceeds 100%, and completeness is 33%. |

Across all six, stage-PoS assumptions are not the primary explanation because
the lead-only model remains below market residual at PoS≈100%. Launch timing
and discounting contribute but cannot be isolated with the frozen three
commercial scenarios. Missing partnership/platform value is plainly important
for GNCA, BIND, and OCUL, but no arbitrary amount is assigned. No case reaches
the coverage threshold needed to label the remaining residual “genuinely
unexplained market valuation.”

## Proposed historical signal specification

The recommended primary signal is **a combination with eligibility gates**:

1. **Primary eligible-company signal: scenario-weighted equity-value spread.**
   Compare observed market cap with a company-level SOTP distribution that
   includes net cash, every material asset, partnership/commercial economics,
   corporate costs, and dilution scenarios. Report both dollar and percentage
   spread. Scenario weights must be specified before returns are inspected.
2. **Coverage diagnostic: valuation-gap ratio.** Define
   `(market_cap - modeled_equity_value) / market_cap`. Always pair it with the
   completeness score. At low completeness it measures model coverage failure,
   not mispricing direction.
3. **Implied PoS: eligible cases only.** Publish it only when all of the
   following hold: the solve is monotonic; the root lies in [0, 1]; completeness
   is at least 70%; no known material asset, commercial product, partnership, or
   platform is assigned zero; the modeled lead asset is the dominant operating
   value source; and cash, senior claims, corporate costs, and dilution are
   represented. Otherwise publish the explicit solver status and diagnostics.
4. **Required-peak-sales multiple: stress diagnostic, not standalone signal.**
   Use it to show how far a non-solvable case is from the frozen commercial
   model. Also show required penetration uncapped. Do not interpret it as alpha
   when completeness fails.

The 70% gate is a proposed ex-ante specification, not fitted to these outcomes;
all six are far below it. A future validation cohort should not begin until the
company-level SOTP schema and evidence requirements can meet this gate without
using realized returns. No alpha, hit rate, or Gate-3 result is produced here.

## Sources and reproducibility

Company-specific statements in this audit come from the six frozen configs and
their matching assumption ledgers, which cite the relevant pre-cutoff SEC
filings and contemporaneous disclosures. The numeric attribution and boundary
diagnostics are generated by `compute_valuation_bridge()` and
`solve_bridged_implied_pos()` in `src/bve/analysis/valuation_bridge.py` using
the unchanged base configs. Post-cutoff outcomes are not used in component
classification, scoring, cause attribution, or the proposed signal gates.
