# Asset Valuation and M&A Scoring Technical Report

**Date:** 2026-05-28
**Scope:** Single-asset biotech valuation and M&A / acquirer scoring logic
**Source of truth:** Current repository code and configs
**Primary files:** `src/bve/valuation/`, `src/bve/models/`, `src/bve/intelligence/acquisition_screen.py`, `acquirer_fit.py`, `ma_probability.py`, `ma_scoring.py`, `ma_bd_decomposition.py`, `ma_layer3_gate.py`, `ma_layer4_routing.py`, `ma_layer5_calibration.py`, `ma_calibration_dataset.py`

## 1. Executive Summary

The tool has two connected jobs:

1. Value a biotech asset using a risk-adjusted NPV framework.
2. Translate that valuation into an M&A / acquirer-fit screen.

The valuation layer asks:

```text
What is this asset worth if we account for clinical risk, commercial opportunity,
development cost, deal economics, taxes, and discounting?
```

The M&A layer asks:

```text
Which buyer-target pairs are strategically logical, financially attractive,
transactionally plausible, and feasible enough to deserve BD attention?
```

The tool is strongest as a structured valuation and prioritization system. Since the last report (2026-05-17), the POS model has been significantly expanded with modality-specific base rates, data maturity and CMC risk adjusters, competitive benchmark position, prior regulatory action penalties, POS uncertainty intervals, and a BTD type-conditional table. The M&A layer has been extended with deal encumbrance nuance (ROFR vs ROFN), antitrust regime modeling, stage-specific transaction priors, and a calibration dataset framework. The main remaining institutional gaps are exact royalty stacks, seller willingness signal depth, acquirer-profile freshness, and large-scale pair-level calibration history.

## 2. End-to-End Architecture

```text
Asset YAML / watchlist / research configs
        |
        v
DrugAssetProgram / WatchlistAsset
        |
        v
ValuationEngine
  -> POS model (Layer 1: log-odds adjusters + modality/subtype base rates)
  -> POS model (Layer 2: trial design / regulatory evidence)
  -> ProbabilityModel
  -> RevenueModel
  -> CostModel
  -> RNPVModel
  -> NAV/share
  -> scenario / Monte Carlo / sensitivity
        |
        v
ValuationOutput
        |
        v
M&A intelligence
  -> acquisition screen
  -> acquisition readiness
  -> comparable deals
  -> acquirer fit
  -> M&A probability scanner
  -> institutional BD layers (L1–L5)
  -> deal encumbrance + antitrust (L5)
  -> catalyst hazard scaling (L5)
  -> calibration dataset framework
  -> calibration / replay
```

| Layer | Main module | Core output |
|---|---|---|
| Valuation orchestration | `valuation_engine.py` | `ValuationOutput` |
| POS | `pos_model.py`, `trial_design_features.py` | Per-phase adjusted POS |
| Probability | `probability_model.py` | Cumulative approval probability |
| Revenue | `market_model.py`, `revenue_model.py` | Annual revenue / EBIT |
| Cost | `cost_model.py`, `cmc_costs.py`, `deal_economics.py` | PV-weighted development obligations |
| rNPV | `rnpv_model.py` | Asset rNPV |
| Acquisition screen | `acquisition_screen.py` | Acquisition discount |
| Acquirer fit | `acquirer_fit.py` | Buyer-target fit ranking |
| M&A probability | `ma_probability.py` | Target ranking across acquirers |
| Institutional BD | `ma_bd_decomposition.py`, `ma_layer3_gate.py`, `ma_layer4_routing.py`, `ma_layer5_calibration.py` | Score decomposition, gates, routing, probability bands |
| Calibration dataset | `ma_calibration_dataset.py` | Schema, no-lookahead validation, fit readiness gate |

## 3. Asset Valuation Engine

### 3.1 Core Valuation Question

The asset valuation model is an rNPV engine. It estimates the present value of future commercial free cash flow, probability-adjusts it for approval risk, subtracts development obligations, and incorporates deal economics.

Core equation:

```text
rNPV =
    P(approval)
  × Σ [ after_tax_FCF_t × net_ownership / (1 + WACC)^t ]
  - PV_weighted_development_obligations
  + PV(receivable_milestones)
  + upfront_receipts
```

The model separates:

| Concept | Owned by |
|---|---|
| Probability of approval | POS + ProbabilityModel |
| Commercial revenue / EBIT | RevenueModel |
| Outgoing development and deal costs | CostModel |
| Royalties, profit share, taxes, FCF, rNPV | RNPVModel |
| Company equity value | NAV/share calculation |

### 3.2 POS Layer 1: Evidence-Based Log-Odds Adjustment

The POS model starts with a phase/therapeutic-area base rate and shifts it using evidence signals. Since 2026-05-17, the base rate itself can be overridden by a modality-specific or indication-subtype-specific rate before any log-odds adjustment is applied.

#### Base Rate Hierarchy

```text
1. Therapeutic-area base rate (PHASE_SUCCESS_RATES from industry_assumptions.yaml)
2. If gene_therapy_modality is set → modality phase rate overrides TA rate
3. If indication_subtype is set → subtype rate overrides modality rate
   (If both modality and subtype set: subtype wins; emits flag
   modality_base_rate_overridden_by_subtype)
```

#### Log-Odds Adjustment

```text
base_log_odds = log(base_probability / (1 - base_probability))

adjusted_log_odds =
    base_log_odds
  + endpoint_adjustment
  + mechanism_adjustment
  + sample_size_adjustment
  + safety_adjustment
  + competition_adjustment
  + biomarker_adjustment
  + prior_phase_adjustment
  + regulatory_designation_adjustment   (type-conditional BTD)
  + dose_selection_adjustment           (Phase 2/3)
  + clinical_effect_adjustment          (Phase 2/3)
  + placebo_response_adjustment         (CNS/psychiatry, Phase 2/3)
  + data_maturity_adjustment            (Phase 2/3)
  + cmc_risk_adjustment                 (Phase 3/NDA only)
  + competitive_benchmark_adjustment    (Phase 2/3)
  + prior_regulatory_action_adjustment  (phase-gated per action type)

adjusted_POS =
    1 / (1 + exp(-adjusted_log_odds))

final_POS =
    min(adjusted_POS, pos_ceiling)   [ceiling inactive if base_rate > 0.75]
```

Why log-odds:

| Reason | Explanation |
|---|---|
| Valid probability bounds | Final POS remains between 0 and 1 |
| Stable near extremes | Adjustments behave better than direct probability addition |
| Additive evidence | Multiple signals can be combined transparently |
| Auditability | Each signal has a visible contribution |

#### Layer 1 Adjuster Table

| Input | What it measures | Phase gate | Institutional concern |
|---|---|---|---|
| Endpoint type | Clinical/regulatory meaningfulness | All | Endpoint nuance may require KOL/regulatory review |
| MoA precedent | Human or approval precedent | All | Novel mechanisms are difficult to score generically |
| Sample size | Statistical reliability | All | Does not replace full statistical review |
| Safety | Clinical/tolerability risk | All | Safety severity is highly context-specific |
| Competitive pressure / regulatory bar | Approval bar in crowded space | All | Can double-count if also in revenue model |
| Biomarker selection | Enrichment and biological validation | All | Biomarkers are not always patient benefit |
| Prior phase data | Human evidence quality | All | Cross-trial comparisons can mislead |
| BTD type | Regulatory engagement and timeline | All | Designation is not approval; type-conditional table |
| Dose selection confidence | Dose optimality risk | All (downside only) | UNKNOWN emits flag; does not move point estimate |
| Clinical effect magnitude | Effect size vs MCID | Phase 2/3 | MCID must be user-specified per TA/endpoint |
| Placebo response concern | Inflation risk in CNS/psychiatry | Phase 2/3, selected TAs | UNKNOWN emits flag; does not move point estimate |
| Data maturity | Completeness of efficacy evidence | Phase 2/3 | Interim ≠ final; EARLY_INTERIM_UNPLANNED penalized most |
| CMC risk | Manufacturing readiness | Phase 3/NDA penalty; early warning Phase 1/2 | Complex modalities flagged at Phase 1/2 even without penalty |
| Competitive benchmark | Efficacy/safety vs SoC | Phase 2/3 | Approvability signal, not commercial — commercial inferiority belongs in revenue model |
| Prior regulatory actions | Adverse FDA history | Holds: all phases; CRL/AdCom: Phase 3/NDA | Penalty scaling by resolution and indication match; stacking cap −0.60 |

#### Modality-Specific Base Rates

Seven modalities have phase-specific rates loaded from `industry_assumptions.yaml` (`modality_phase_rates`). These are prior estimates, not empirically calibrated.

| Modality key | Phase 1 | Phase 2 | Phase 3 | NDA/BLA | Status |
|---|---:|---:|---:|---:|---|
| gene_therapy_aav | 0.55 | 0.38 | 0.50 | 0.82 | Prior estimate |
| gene_therapy_lentiviral | 0.52 | 0.35 | 0.48 | 0.79 | Prior estimate |
| car_t_autologous | 0.60 | 0.45 | 0.62 | 0.88 | Prior estimate |
| car_t_allogeneic | 0.44 | 0.30 | 0.45 | 0.75 | Prior estimate |
| lnp_mrna | 0.58 | 0.42 | 0.60 | 0.85 | Prior estimate |
| aso_rnai | 0.57 | 0.40 | 0.58 | 0.87 | Prior estimate |
| biologic_antibody | 0.62 | 0.38 | 0.61 | 0.88 | Prior estimate |

Modalities without a YAML entry (RETROVIRAL_EX_VIVO, BASE_EDITING, PRIME_EDITING, ZINC_FINGER_NUCLEASE) fall back to the TA base rate.

#### Indication Subtype Rates

Eight high-impact indication subtypes override the TA base rate when `indication_subtype` is set. Each subtype entry includes source, N, date range, confidence, and TA fallback.

| Subtype key | Phase 2 | Phase 3 | TA fallback | Confidence |
|---|---:|---:|---|---|
| gbm | 0.12 | 0.28 | oncology_solid | Medium |
| alzheimers | 0.18 | 0.42 | cns | Medium |
| ultra_rare_monogenic | 0.58 | 0.70 | rare_disease | Medium |
| nsclc_targeted | 0.28 | 0.51 | oncology_solid | Medium |
| nsclc_io_refractory | 0.19 | 0.39 | oncology_solid | Low |
| cll_btk_era | 0.38 | 0.63 | hematology | Low |
| psychiatry_mdd | 0.22 | 0.53 | psychiatry | Medium |
| pain_chronic | 0.20 | 0.45 | cns | Low |

#### Absolute POS Ceiling

A ceiling prevents implausible highs from adjuster stacking:

```text
pos_ceiling = min(0.75, max(base_rate × 2.5, base_rate + 0.25))
```

The ceiling is inactive when the base rate itself exceeds 0.75 (e.g. NDA/BLA phases where TA rates are 0.82–0.94). This preserves the ceiling for Phase 1/2/3 without masking high-approval-probability late-stage phases.

#### POS Uncertainty Intervals

A separate `compute_pos_with_ci()` function uses Triangular sampling to produce 90% confidence intervals around the point estimate.

```text
compute_pos_with_ci(phase, therapeutic_area, adjusters, n_mc_samples=500)
    -> POSWithCI(pos, pos_ci_low, pos_ci_high, pos_ci_width, n_mc_samples)
```

UNKNOWN adjusters have wider uncertainty bounds than explicitly-set values, so more unknown inputs produce wider intervals. CI is opt-in via `compute_pos_detailed(..., include_ci=True)`. Default is OFF because MC sampling adds overhead.

#### BTD Type-Conditional Table

The flat `has_breakthrough_designation` bool now has a type-conditional successor:

| BTD type | Log-odds | Notes |
|---|---:|---|
| NONE | 0.00 | No designation |
| FAST_TRACK_ONLY | +0.02 | Process signal only |
| GRANTED_STANDARD | +0.05 | Backward-compatible default |
| GRANTED_RARE_HEME | +0.10 | Best translation evidence |
| GRANTED_SOLID_TUMOR | +0.03 | Selection-bias adjusted |
| GRANTED_EARLY_PHASE | +0.08 | Strong early FDA engagement |
| BREAKTHROUGH_REVOKED | −0.15 | Loss of FDA confidence |

GRANTED_* types set `btd_timeline_acceleration_flag=True`. High-tier types with strong prior data and exceeds-MCID effect magnitude emit a `btd_overlap_warning`.

#### Layer 1 Caps

| Cap | Value | Scope |
|---|---:|---|
| L1 positive cap | +0.80 | Standard |
| L1 positive cap (extraordinary evidence) | +1.00 | Requires all three gating conditions + rationale |
| L1 negative cap | −0.80 | Always |
| Combined L1 + L2 cap | ±0.90 | Applied at ValuationEngine |
| Gene therapy total overlay | −0.60 | Sum of all gene_cell_therapy_concerns |
| Gene therapy durability sub-cap | −0.30 | SHORT_FOLLOWUP + WANING + SINGLE_DOSE_DURABILITY combined |
| Prior regulatory actions stacking | −0.60 | Sum of all RegulatoryActionRecord penalties |

### 3.3 POS Layer 2: Trial Design / Regulatory Evidence

Layer 2 asks whether the evidence package is credible enough for regulators and buyers.

```text
design_adjustment =
    evidence_quality
  + comparator_fit
  + regulatory_pathway_quality
  + design_penalties

phase_scaled_adjustment =
    design_adjustment × phase_weight

final_adjustment =
    clip(phase_scaled_adjustment, lower_cap, upper_cap)
```

Current phase weights:

| Phase | Weight |
|---|---:|
| Phase 1 | 0.20 |
| Phase 2 | 0.50 |
| Phase 3 | 1.00 |
| NDA/BLA | 0.90 |

Layer 1 versus Layer 2 boundary:

| Layer | Scores |
|---|---|
| Layer 1 | Endpoint strength, biology, prior evidence, safety, maturity, CMC, competitive position, regulatory history |
| Layer 2 | Design credibility, comparator fit, regulatory path |

Main risk: double-counting. An anti-double-counting guard (`check_pos_layer_overlap()`) detects when the same signal is credited in both layers and emits a `UserWarning`.

### 3.4 Cumulative Approval Probability

The probability model compounds phase success probabilities:

```text
P(reaching phase_i) =
    product(success_probability_j for all prior phases j)

P(approval) =
    product(success_probability_i for all remaining phases i)
```

Example:

```text
Phase 2 asset P(approval) =
    P(pass Phase 2)
  × P(pass Phase 3 | Phase 2 success)
  × P(pass NDA/BLA | Phase 3 success)
```

Interpretation:

| Output | Meaning |
|---|---|
| `prob_reaching` | Probability the asset survives to a future phase |
| `success_probability` | Conditional chance of passing that phase |
| `cumulative_approval_probability` | Full remaining path chance of approval |
| `years_to_approval` | Timing anchor for discounting and post-approval obligations |

### 3.5 Revenue Model

The revenue model forecasts commercial economics if the asset is approved. It does not apply approval probability; probability is applied later in rNPV.

Supported sizing modes:

| Mode | Use case |
|---|---|
| Patient-based | Best for detailed asset diligence |
| Line-of-therapy | Oncology and treatment-sequence models |
| TAM-based | Early rough screens |
| Hybrid commercial model | Patient funnel plus pricing, geography, access, competition |

Patient-based revenue:

```text
eligible_patients =
    population
  × prevalence_or_incidence
  × diagnosed_rate
  × eligible_rate
  × treatment_rate
  × line_of_therapy_share

treated_patients_t =
    eligible_patients
  × penetration_t
  × payer_access_t
  × geography_launch_t
  × competition_t

net_price_t =
    list_or_WAC_price_t
  × (1 - gross_to_net_discount_t)
  × pre_LOE_price_erosion_t

revenue_t =
    treated_patients_t
  × net_price_t
  × treatment_duration_factor
```

EBIT bridge:

```text
COGS_t = revenue_t × COGS_rate
SG&A_t = revenue_t × SG&A_rate_t
EBIT_t = revenue_t - COGS_t - SG&A_t
```

Revenue model features:

| Feature | Status | Why it matters |
|---|---|---|
| Gross-to-net pricing | Implemented | Avoids overvaluing list-price revenue |
| Geography launch timing | Implemented | Prevents ex-US revenue from arriving too early |
| Fractional launch delays | Implemented | More realistic launch interpolation |
| Payer access | Implemented | Captures PA burden, coverage delay, step edits |
| Competition | Implemented | Adjusts share and price erosion |
| LOE erosion | Implemented | Models post-exclusivity decline |
| COGS by modality | Implemented | Gene/cell/biologics/small molecules differ materially |
| SG&A by commercial model | Implemented | Self-commercialization vs partner/royalty economics |

Main limitation: the model can express detailed assumptions, but it does not verify that patient counts, penetration, pricing, or payer assumptions are correct.

### 3.6 Cost Model

The cost model estimates probability-weighted present value of development obligations.

```text
total_PV_weighted_development_obligations =
    Σ PV_weighted(trial_R&D)
  + PV_weighted(CMC)
  + Σ PV_weighted(payable_milestones)
  + upfront_cost
  + PV_weighted(post_approval_commitments)
```

#### Trial R&D

```text
cost_after_share_i =
    phase_cost_i × cdev_cost_share

PV_gross_i =
    cost_after_share_i
  × (1 + cost_inflation_rate)^t
  / (1 + discount_rate)^t

PV_weighted_i =
    PV_gross_i × P(reaching phase_i)
```

Default timing:

```text
t = (phase_start + phase_end) / 2
```

If annual-uniform spend is selected, spending is split by year segment and discounted at each segment midpoint.

#### CMC / Manufacturing

CMC components:

| Component | What it covers |
|---|---|
| API development | Synthesis route, analytical methods, batches |
| Formulation | Dosage form, stability, fill-finish |
| Manufacturing scale-up | Tech transfer, PPQ, facility qualification |
| Regulatory CMC | Module 3, site inspections, CMC commitments |

Formula:

```text
CMC_total =
    API_development
  + formulation
  + manufacturing_scale_up
  + regulatory_CMC

PV_CMC =
    CMC_total / (1 + discount_rate)^anchor_year
  × probability_weight
```

Timing modes:

| Mode | Anchor |
|---|---|
| `parallel_to_phase_3` | Phase 3 midpoint |
| `post_phase_2` | Phase 2 end |
| `pre_phase_3_start` | Phase 3 start |
| `custom_year` | Analyst-specified |

Probability weight is normally `P(reaching Phase 3)`.

#### Payable Milestones

```text
PV_milestone_i =
    milestone_amount_i
  / (1 + discount_rate)^trigger_year_i
  × trigger_probability_i
```

| Trigger | Timing | Probability weight |
|---|---|---|
| Phase start | Phase start | `P(reaching phase)` |
| Phase success | Phase end | `P(reaching phase) × P(success)` |
| Approval | Years to approval | Cumulative approval probability |
| First sale | Approval + launch offset | Cumulative approval probability |
| Sales threshold | First year above threshold | Cumulative approval probability |

Sales-threshold milestones require revenue. If `CostModel` lacks a revenue stream, the rNPV path resolves those milestones later.

#### Upfront Costs

```text
PV_upfront_cost =
    upfront_cost_millions
```

No discounting and no probability weighting because it is a time-zero outflow.

#### Post-Approval Commitments

```text
PV_post_approval =
    post_approval_rd_millions
  / (1 + discount_rate)^years_to_approval
  × P(approval)
```

Includes Phase 4, REMS, pharmacovigilance, and label-expansion commitments.

### 3.7 rNPV and NAV/share

RNPV uses the revenue stream, probability stream, cost stream, tax/deal economics, and ownership.

```text
royalty_t = revenue_t × deal.royalty_rate
profit_share_t = EBIT_t × deal.profit_share_rate

adjusted_EBIT_t =
    EBIT_t
  - royalty_t
  - profit_share_t

cash_tax_t =
    tax_model(adjusted_EBIT_t, NOLs, tax profile)

after_tax_FCF_t =
    adjusted_EBIT_t
  - cash_tax_t
  - maintenance_capex_t
  - working_capital_t
  - launch_capex_t
```

Commercial PV:

```text
PV_commercial =
    P(approval)
  × Σ [ after_tax_FCF_t × net_ownership / (1 + WACC)^t ]
```

RNPV:

```text
rNPV =
    PV_commercial
  - PV_weighted_development_obligations
  + PV_receivable_milestones
  + upfront_receipts
```

NAV:

```text
NAV =
    asset_rNPV
  + net_cash
  - debt
  - corporate_overhead_PV
  + other_adjustments

NAV/share =
    NAV / diluted_shares
```

Key interpretation:

| Output | Use |
|---|---|
| rNPV | Asset value |
| NAV/share | Equity value |
| Probability-adjusted revenue PV | Approval-risk-adjusted commercial value |
| PV development obligations | Cost burden |
| Royalty/profit-share deductions | Partner economics |
| Tax audit | Cash tax and NOL bridge when `TaxProfile` exists |

### 3.8 Scenario and Monte Carlo

Scenario analysis shocks assumptions deterministically.

| Scenario | Peak sales | POS | Timing | Cost | WACC |
|---|---:|---:|---:|---:|---:|
| Bull | Higher | Higher | Faster | Lower | Lower |
| Base | Base | Base | Base | Base | Base |
| Bear | Lower | Lower | Slower | Higher | Higher |

Monte Carlo samples uncertainty distributions:

| Variable | Example approach |
|---|---|
| Phase success | Beta-style uncertainty |
| Peak sales | Lognormal |
| Revenue drivers | Lognormal multipliers |
| Discount rate | Normal, clipped |
| Timing | Gamma / rounded normal |
| Trial cost | Lognormal |
| Competitors | Sampled outcomes |

Outputs:

| Output | Meaning |
|---|---|
| Mean / median | Expected and central simulated value |
| Percentiles | Downside/upside range |
| Probability positive | Fraction with positive rNPV |
| VaR / downside | Tail risk |
| Variance drivers | Key uncertainty sources |

## 4. M&A / Acquirer Scoring

### 4.1 M&A Objective

The M&A system does not simply ask whether an asset is good. It asks:

```text
Which target-acquirer pair has enough asset quality, value creation,
strategic fit, transaction timing, and deal feasibility to justify BD work?
```

A credible M&A score requires:

| Requirement | Why |
|---|---|
| Asset worth owning | Buyers do not acquire bad assets just because they are cheap |
| Buyer right-to-win | Strategic fit must be buyer-specific |
| Value creation | Deal must work after premium and cost-to-complete |
| Seller willingness | Fit does not imply availability |
| Feasibility | Rights, antitrust, affordability, CMC can block deal |

### 4.2 Acquisition Screen

The acquisition screen compares model value to market enterprise value.

```text
enterprise_value =
    market_cap
  - net_cash

acquisition_discount =
    model_asset_rNPV / enterprise_value
```

Interpretation:

| Acquisition discount | Possible read |
|---|---|
| > 2.0x | Model sees much more value than public EV |
| 1.0-2.0x | Potential value gap |
| < 1.0x | Market value exceeds model asset value |

Guardrail:

Do not multiply by POS again. rNPV already embeds probability.

### 4.3 Acquisition Readiness

The readiness gate prevents immature or weakly supported assets from ranking highly.

| Stage/evidence | Treatment |
|---|---|
| Phase 3 or later | Generally acquisition-ready |
| Phase 2 with proof-of-concept | Can pass readiness |
| Phase 2 pre-proof-of-concept | Lower score |
| Phase 1 / preclinical | Usually hard fail or severe penalty |

Evidence factors:

| Factor | Impact |
|---|---|
| Endpoint met | Improves readiness |
| Adequate design | Improves readiness |
| Posterior POS above prior | Improves readiness |
| Low-powered study | Penalizes |
| Prior failure / safety / label issue | Penalizes |

### 4.4 Comparable Deals

Comparable deal analysis estimates plausible deal value ranges.

Matching hierarchy:

| Level | Strength |
|---|---|
| Exact canonical indication + phase | Highest |
| Therapeutic area + phase | Medium |
| Phase only | Weak |

Common outputs:

| Output | Use |
|---|---|
| EV / peak sales median | Deal multiple benchmark |
| Upfront / milestone ranges | Structure benchmark |
| Fair value band | Acquisition valuation range |
| High-quality band | Better matched comps |

Limit:

Comparable deals can mislead if headline biobucks, platform value, rights scope, or stage are not comparable.

### 4.5 Acquirer Fit

The acquirer-fit model scores a target against each buyer profile.

General formula:

```text
fit_score =
    w_TA × therapeutic_area_score
  + w_modality × modality_score
  + w_stage × stage_score
  + w_priority × strategic_priority_score
  + w_valuation × valuation_score
  + w_budget × budget_score
  + partnership_bonus
  - penalties
```

Acquirer profile fields can include:

| Field | Why it matters |
|---|---|
| Therapeutic gaps | Identifies real buyer need |
| Preferred modalities | Determines technical fit |
| Strategic priorities | Converts stated strategy into scoring |
| Recent deals | Signals BD appetite |
| Budget / capacity | Screens affordability |
| Partnerships | Indicates relationship/control advantage |

Hard filters:

| Filter | Reason |
|---|---|
| Too early | Buyer unlikely to acquire pre-proof-of-concept asset |
| Not acquisition-ready | Evidence not sufficient |
| Outside budget | Deal size not plausible |

### 4.6 Stage-Specific Transaction Priors

Transaction type mix is now stage-conditional rather than flat. When `target_stage` is set, the model looks up priors from `industry_assumptions.yaml` (`transaction_mix_by_stage`).

| Stage | P(acquisition) | P(license or partnership) |
|---|---:|---:|
| Preclinical | 0.15 | 0.75 |
| Phase 1 | 0.25 | 0.65 |
| Phase 2 | 0.40 | 0.55 |
| Phase 3 | 0.65 | 0.30 |
| NDA/BLA | 0.75 | 0.20 |
| Approved | 0.80 | 0.15 |
| Fallback | 0.60 | 0.35 |

Fractions do not sum to 1.0 intentionally; the remainder represents other deal structures. Derived probabilities carry a `p_full_acquisition_source` tag (`DERIVED_STAGE_ADJUSTED` vs `DERIVED`) for audit.

### 4.7 Live M&A Probability Scanner

The live scanner ranks target-acquirer pairs and selects the best buyer per target.

Current score components:

| Component | Meaning |
|---|---|
| Valuation discount | Model value versus EV |
| Strategic fit | Buyer-specific fit |
| De-risking stage | Clinical/regulatory maturity |
| Capital vulnerability | Financing/seller pressure |
| Scarcity | How rare the asset is in its category |

Current v1.4 formula:

```text
raw_mna_score =
    0.00 × acquisition_discount_component
  + 0.65 × strategic_fit_score
  + 0.20 × de_risking_stage_score
  + 0.05 × capital_vulnerability_score
  + 0.10 × scarcity_score
```

The CLI default may use another score version unless configured directly. For current institutional review, v1.4 is more balanced because it includes strategic fit, de-risking, capital vulnerability, and scarcity.

Strategic fit mechanics:

```text
strategic_fit =
    min(
      urgency_adjusted_TA
    + modality
    + strategic_priority
    + budget
    + BD_pattern_adjustment
    - quality_penalties,
      strategic_fit_cap
    )
```

Current strategic-fit cap:

```text
strategic_fit_cap = 0.70
```

Gap urgency multipliers:

| Gap urgency | Multiplier |
|---|---:|
| High | 1.00 |
| Medium | 0.55 |
| Low | 0.28 |
| No matched gap | 0.15 |

Quality penalties:

| Penalty | Trigger |
|---|---|
| Weak commercial overlap | Low TA score |
| Poor modality fit | Low modality score |
| No pipeline gap | Weak strategic priority |
| Poor deal-size fit | Low budget score |

De-risking score:

| Bucket | Score |
|---|---:|
| Phase 3 or later | 0.62 |
| Phase 2 proof-of-concept | 0.50 |
| Phase 2 pre-proof-of-concept | 0.30 |
| Pre-Phase 2 | 0.08 |
| Unknown | 0.20 |

Additional de-risking adjustments:

| Signal | Direction |
|---|---|
| Better design tier | Positive |
| Posterior POS improvement | Positive |
| Breakthrough designation | Positive |
| Surrogate / single-arm design | Negative |
| Low power | Negative |
| Safety overhang | Negative |
| Prior failure | Negative |
| Label uncertainty | Negative |

Transaction-likelihood gates:

| Gate | Trigger | Cap |
|---|---|---:|
| No trigger | No financing/deal/catalyst/activist/value trigger | 0.55 |
| Dual low-pressure | Low financing pressure and low buyer urgency | 0.55 |
| High-score two-driver | Score > 0.75 with fewer than two drivers | 0.75 |

Transaction drivers:

| Driver | Threshold |
|---|---:|
| Financing pressure | >= 0.35 |
| External deal activity | >= 0.30 |
| Catalyst proximity | <= 90 days |
| Activist / target signal | >= 0.30 |
| Valuation distress | Valuation discount >= 0.45 and de-risking >= 0.50 |

Final flow:

```text
raw_mna_score
  -> saturation penalty
  -> transaction-likelihood gate
  -> targetability multiplier
  -> hard-fail zeroing
  -> best acquirer selection
  -> target ranking
  -> optional calibration display
```

### 4.8 Institutional BD Layer 1

The institutional BD decomposition is a richer scorecard for acquirer-target review.

```text
BD_M&A_score =
    0.30 × asset_quality
  + 0.20 × value_creation
  + 0.20 × transaction_timing
  + 0.25 × strategic_fit
  + 0.05 × deal_feasibility
```

#### Asset Quality

```text
asset_quality =
    0.25 × clinical_evidence
  + 0.20 × differentiation
  + 0.15 × regulatory_path
  + 0.15 × IP_durability
  + 0.10 × CMC_feasibility
  + 0.15 × commercial_meaningfulness
```

Cap:

```text
if clinical_evidence < 0.35:
    asset_quality = min(asset_quality, 0.55)
```

#### Value Creation

```text
value_creation =
    0.35 × premium_adjusted_rnpv_gap
  + 0.20 × synergy_upside
  + 0.15 × downside_protection
  + 0.15 × cost_to_complete
  + 0.15 × capital_solution_value
```

```text
premium_adjusted_rnpv_gap =
    model_rnpv
  - expected_acquisition_price
  - remaining_cost_to_complete
  + buyer_specific_synergy_value
```

#### Transaction Timing / Seller Willingness

```text
transaction_timing =
    0.25 × financing_pressure
  + 0.25 × seller_willingness
  + 0.20 × transaction_window_quality
  + 0.15 × external_deal_activity
  + 0.15 × catalyst_setup
```

#### Strategic Fit

```text
strategic_fit =
    0.20 × TA_fit
  + 0.15 × modality_fit
  + 0.20 × pipeline_gap_urgency
  + 0.15 × development_capability
  + 0.10 × commercial_capability
  + 0.10 × CMC_capability
  + 0.10 × relationship_control
```

#### Deal Feasibility

```text
deal_feasibility =
    0.35 × affordability
  + 0.20 × antitrust_feasibility
  + 0.20 × asset_control
  + 0.15 × integration_feasibility
  + 0.10 × bidder_competition_risk_adjusted
```

Layer 1 institutional gates:

| Gate | Trigger | Cap |
|---|---|---:|
| Broken asset | Asset quality < 0.35 | 0.40 |
| No right-to-win | Strategic fit < 0.45 | 0.55 |
| Poor value creation | Raw rNPV gap < 0 | 0.60 |
| Low seller willingness | Seller willingness < 0.30 and financing pressure < 0.30 | 0.55 |
| Encumbrance | Asset control < 0.40 | 0.50 |

### 4.9 Layer 3 Deal-Realism Gates

Layer 3 converts a pre-gate score into a final score by applying hard caps.

```text
final_score =
    min(pre_gate_score, most_restrictive_triggered_cap)
```

Driver buckets:

| Bucket | Formula / logic | Active threshold |
|---|---|---:|
| Capital pressure | Financing pressure | 0.35 |
| Buyer urgency | 0.60 × external deal activity + 0.40 × pipeline gap urgency | 0.30 |
| Seller willingness | 0.60 × activist signal + 0.40 × strategic review signal | 0.30 |
| Catalyst timing | Catalyst proximity | 0.35 |
| Asset scarcity | 0.60 × scarcity + 0.40 × acquirer fit | 0.60 |
| Valuation dislocation | Valuation discount >= 0.45 and de-risking >= 0.50 | Dual condition |

Gate caps:

| Gate | Meaning | Cap |
|---|---|---:|
| G1 | Broken asset | 0.35 |
| G2 | No right-to-win | 0.50 |
| G3 | No transaction rationale | 0.45 |
| G4 | Weak transaction setup | 0.65 |
| G5 | Seller not ready | 0.55 |
| G6 | Capital pressure without quality | 0.45 |
| G7 | Encumbrance / control | 0.50 |
| G8 | Deal feasibility | 0.60 |

G7 is now triggered specifically by ROFR, CO_DEVELOPMENT_LOCK, and FULL_BLOCK. CHANGE_OF_CONTROL and ROFN do not trigger G7 (they affect closing probability via the encumbrance multiplier but not the G7 hard cap).

### 4.10 Layer 4 Routing and Deal Structure

Layer 4 translates score into BD workflow.

| Watchlist class | Meaning |
|---|---|
| `pass` | Archive unless facts change |
| `data_insufficient` | Fill data gaps |
| `strategic_radar` | Relevant but no urgency |
| `relationship_build` | Strong fit, not actionable yet |
| `catalyst_watch` | Important event approaching |
| `active_pursuit` | High fit and real setup |
| `process_ready` | Strong target likely to transact soon |

Deal structures:

| Structure | Typical condition |
|---|---|
| Full acquisition | Clean rights, high quality, high urgency |
| Asset license | Asset attractive but full company not needed |
| Option to acquire | Buyer wants next data before control premium |
| Co-development | Risk/cost sharing preferred |
| Regional rights | Territory-specific opportunity |
| Research collaboration | Early platform relationship |
| Minority equity | Relationship without control |
| Monitor only | Not actionable |

### 4.11 Layer 5 Calibration

Layer 5 converts rank score into probability language.

```text
logistic_probability =
    sigmoid(8.0 × (rank_score - 0.68))
```

Shrinkage:

```text
p_takeout_12m =
    w_base × base_rate
  + w_logistic × logistic_probability
  + w_bucket × comparable_bucket_rate
```

Shrinkage weights:

| Comparable N | Base | Logistic | Bucket |
|---:|---:|---:|---:|
| < 10 | 60% | 20% | 20% |
| 10-19 | 50% | 30% | 20% |
| 20-29 | 40% | 40% | 20% |
| >= 30 | 30% | 50% | 20% |

Time windows:

```text
p_takeout_6m  = p_takeout_12m × scale_6m_applied
p_takeout_18m = 1 - (1 - p_takeout_12m)^exponent_18m_applied
```

The 6m scale and 18m exponent are now catalyst-timing-conditional (see Section 4.12).

Probability bands:

| Band | Range |
|---|---:|
| Very low | < 5% |
| Low | 5-15% |
| Moderate | 15-30% |
| High | 30-50% |
| Exceptional / manual review | > 50% |

Critical caveat:

Raw M&A scores are not probabilities. Calibration is only credible to the extent the historical label set is large, clean, point-in-time, and representative. A framework (`ma_calibration_dataset.py`) now enforces schema, no-lookahead validation, and a minimum-data gate before any logistic fitting can run.

### 4.12 Catalyst-Based Hazard Scaling

The 6m and 18m probability windows now adjust dynamically based on catalyst timing.

```text
timing_shape =
    strongly_front_loaded   (days <= 90, Phase 3 readout or regulatory decision)
  | front_loaded            (days <= 180, substantive catalyst)
  | neutral                 (no catalyst or UNKNOWN — backward-compatible default)
  | back_loaded             (days > 365)
```

Scaling tables:

| Timing shape | 6m scale | 18m exponent |
|---|---:|---:|
| strongly_front_loaded | 0.80 | 1.10 |
| front_loaded | 0.68 | 1.25 |
| neutral | 0.55 | 1.35 |
| back_loaded | 0.38 | 1.55 |

Default (`days_to_catalyst=None`, `catalyst_type=UNKNOWN`) produces neutral shape — identical to prior behavior. Audit fields `scale_6m_applied` and `scale_18m_exponent_applied` are included in `Layer5Output`.

### 4.13 Deal Encumbrance (ROFR vs ROFN)

Encumbrance affects closing probability, not strategic interest. `p_any_strategic_transaction_12m` is not mutated; a separate `p_effective_close_12m` field applies the multiplier.

```text
p_effective_close_12m =
    p_any_strategic_transaction_12m
  × encumbrance_close_multiplier
  × antitrust_multiplier
```

Encumbrance multipliers:

| Encumbrance type | Closing multiplier | Notes |
|---|---:|---|
| NONE | 1.00 | No encumbrance |
| CHANGE_OF_CONTROL | 0.92 | Adds cost, not veto |
| ROFN | 0.90 | Soft; 30-90d window then free to shop |
| ROFR | 0.68 | Partner can match any bid; price-capping risk |
| CO_DEVELOPMENT_LOCK | 0.50 | Mutual consent required |
| FULL_BLOCK | 0.10 | Structure reform needed |

G7 triggers for ROFR, CO_DEVELOPMENT_LOCK, FULL_BLOCK. CHANGE_OF_CONTROL and ROFN do not trigger G7.

### 4.14 Antitrust Regime Modeling

Antitrust risk affects `p_effective_close_12m` multiplicatively, combined with encumbrance.

```text
antitrust_multiplier =
    base_multiplier(antitrust_risk_tier)
  × regime_modifier(antitrust_regime)
  [clamped to 0.05–1.00]
```

Tier base multipliers:

| Tier | Multiplier | Observable anchor |
|---|---:|---|
| NEGLIGIBLE | 1.00 | No TA overlap, <$2B, novel mechanism |
| LOW | 0.97 | Minor overlap, acquirer <15% TA share |
| MODERATE | 0.85 | Meaningful overlap; likely second request |
| SIGNIFICANT | 0.70 | >30% combined share or TA-consolidating |
| LIKELY_CHALLENGED | 0.45 | FTC/DOJ challenged similar; >50% combined |
| BLOCKED_RISK | 0.20 | DOJ/FTC public concern; structural remedy required |

Regime modifiers:

| Regime | Modifier | Notes |
|---|---:|---|
| PRE_2021 | 1.10 | Lenient era; softens multiplier |
| AGGRESSIVE_2021_2024 | 0.90 | Stricter era; tightens multiplier |
| CURRENT_STANDARD | 1.00 | Reference |
| UNKNOWN | 0.90 | Conservative default (= aggressive) |

`p_any_strategic_transaction_12m` and `rank_score` are not affected by antitrust. The multiplier applies only to `p_effective_close_12m`.

### 4.15 M&A Calibration Dataset Framework

A schema, validator, and fit-readiness gate now guard any future logistic calibration.

Key schema fields per case:

| Field | Type | Purpose |
|---|---|---|
| `ticker`, `company_name` | str | Identity |
| `observation_date` | date | Point-in-time anchor |
| `target_stage`, `therapeutic_area`, `modality` | str | Context |
| `*_as_of` features | float/int | All observable before observation_date |
| `outcome_12m` | bool | Did a deal close within 12 months? |
| `outcome_type` | str | acquisition / license / partnership / none |
| `source_refs` | list[str] | Citable evidence for all values |
| `feature_as_of_dates` | dict[str, str] | Date each feature was sourced |
| `lookahead_pass` | bool | Analyst-confirmed no lookahead |

No-lookahead validator checks that all `feature_as_of_dates` entries predate `observation_date`.

Fit readiness gate blocks logistic fitting until:

| Condition | Threshold |
|---|---|
| Positive cases (deals) | ≥ 50 |
| Negative cases (non-deals) | ≥ 100 |
| Lookahead-validated cases | 100% |

A dataset that fails the gate cannot run `fit_logistic_calibration()`. A poorly curated calibration is worse than no calibration.

## 5. What BD Would Ask

| BD question | Technical answer |
|---|---|
| Is this an asset valuation model or M&A model? | Both. Valuation creates rNPV/NAV; M&A uses valuation plus buyer/transaction logic. |
| Does a high rNPV automatically mean likely acquisition? | No. Strategic fit, seller willingness, rights/control, and feasibility must also pass. |
| Does a high strategic fit mean buyer will act? | No. The model separates strategic watch from active pursuit/process-ready. |
| Does the tool know hidden deal blockers? | ROFR/ROFN/antitrust are now modeled. Exact royalty stacks, CoC clauses, and regional splits still require analyst configuration. |
| Can it rank Vertex or Regeneron targets? | Yes as a screen, using acquirer profiles and pipeline gaps. BD review is needed to validate internal priorities. |
| Can it recommend structure? | Yes through routing, but structure likelihood is not deeply calibrated. |
| What is the biggest false-positive risk? | Superficial TA fit plus missing rights/seller/antitrust data. |
| What is the biggest false-negative risk? | Non-public buyer urgency or relationship signals not in the data. |
| Should exact probabilities be used in a BD meeting? | Use bands and confidence language, not exact decimals. |
| How confident are the POS numbers? | `compute_pos_with_ci()` returns 90% intervals. More UNKNOWN inputs produce wider intervals. Use these to communicate uncertainty, not to replace point estimates. |

## 6. Institutional Gaps

| Area | Current status | Why it matters | Fix |
|---|---|---|---|
| POS calibration | Implemented; validation limited | POS drives value | Expand outcome dataset and calibrate by TA/stage/modality; Block 35 modality rates are prior estimates only |
| Modality base rates | Prior estimates (not calibrated) | Gene therapy rates differ materially from TA rates | Calibrate once ≥30 outcome events per modality are collected |
| Peak sales assumptions | Config-driven | Commercial optimism dominates rNPV | Add stricter patient-funnel validation |
| Rights/control | Partially modeled (encumbrance types) | Can block full acquisition | ROFR/ROFN/CO_DEV_LOCK implemented; exact CoC and regional splits still config-driven |
| Royalty stacks | Partial/config-driven | Can destroy deal value | Add exact asset-level royalty stack fields |
| Regional rights | Missing/deeply incomplete | Changes structure and buyer universe | Add territory rights model |
| Seller willingness | Partial | Fit does not imply process | Add board/investor/process signal model |
| Antitrust | Implemented (tier + regime model) | Strategic overlap can block deal | Tier assignment is still analyst-set; automated product-market overlap scoring would improve accuracy |
| Acquirer profile freshness | Config-driven | Buyer priorities change | Add profile age warnings and BD review workflow |
| Pair-level calibration | Framework in place; no fitted params yet | Needed for probabilities | Build historical acquirer-target panel meeting 50/100 positive/negative threshold |

## 7. Final Assessment

The valuation engine is mature enough to support serious asset-level diligence when inputs are reviewed carefully. It provides a clear value bridge from POS to revenue, costs, rNPV, NAV/share, scenario analysis, Monte Carlo, and market-implied expectations.

Since the last report, the POS model has grown substantially: 15+ adjusters with phase gates, modality and indication-subtype base rate overrides, uncertainty intervals, and a validated ceiling formula. The M&A engine now covers encumbrance type nuance, antitrust regime, catalyst-based hazard scaling, stage-specific transaction priors, and a calibration dataset framework with strict no-lookahead and minimum-data gates.

The M&A engine is useful for screening and prioritization. It can identify plausible acquirers, show strategic-fit logic, estimate whether model value exceeds public EV, and route targets into watchlist classes. It is not yet institutional-grade as a precise acquisition-probability engine because the hardest BD inputs (royalty stacks, exact rights, seller willingness depth) are still partial or config-driven, and no real calibration dataset has been fitted yet.

What can be trusted most today:

| Output | Trust level |
|---|---|
| rNPV bridge | High if inputs are reviewed |
| Cost obligation PV | High |
| Scenario / Monte Carlo mechanics | Medium-high |
| POS point estimate (Layer 1 + 2) | Medium — evidence-informed priors, not calibrated coefficients |
| POS uncertainty intervals | Medium — width reflects information quality; absolute bounds are not statistically validated |
| Market-implied POS | Medium |
| Acquisition discount | Medium |
| Acquirer fit | Medium |
| Encumbrance / antitrust close probability | Medium — multipliers are anchored estimates, not empirically fitted |
| M&A probability score | Directional only |
| Deal structure likelihood | Directional only |

Best use:

```text
Use the tool to create a ranked diligence agenda:
  1. Which assets are mispriced?
  2. Which buyers are plausible?
  3. Which assumptions drive value?
  4. Which hidden blockers need BD/legal/scientific review?
  5. What new evidence would promote or demote the target?
  6. How wide are the POS uncertainty intervals — and which UNKNOWN inputs should be resolved first?
```

It should be presented to BD teams as a structured decision-support and assumption-audit system, not as a black-box answer.
