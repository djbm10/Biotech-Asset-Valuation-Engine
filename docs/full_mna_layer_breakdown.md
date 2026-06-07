# Full M&A Layer Breakdown

**Date:** 2026-06-04
**Scope:** M&A / acquirer scoring layers only
**Source of truth:** current repository code and current technical reports

This file is a standalone M&A reference formatted in the same spirit as the POS
section in `docs/full_institutional_biotech_tool_report.md`: primary files,
layer purpose, formulas, weights, boundaries, and known limits.

## Table Of Contents

- [Core Layer Files](#core-layer-files)
- [Architecture Overview](#architecture-overview)
- [Layer Ownership And Double-Counting Rules](#layer-ownership-and-double-counting-rules)
- [Layer 0: Target Pre-Screening](#layer-0-target-pre-screening)
- [Layer 1: Strategic Attractiveness](#layer-1-strategic-attractiveness)
- [Layer 2: BD Priority](#layer-2-bd-priority)
- [Layer 3: Pair-Specific Deal Realism](#layer-3-pair-specific-deal-realism)
- [Layer 4: Routing And Deal Structure](#layer-4-routing-and-deal-structure)
- [Layer 5: Calibration, Confidence, And Close Probability](#layer-5-calibration-confidence-and-close-probability)
- [Live Scanner: TA / DL / AF Path](#live-scanner-ta--dl--af-path)
- [Other M&A Support Modules](#other-ma-support-modules)
- [Validation And Known Limits](#validation-and-known-limits)

---

## Core Layer Files

- `src/bve/intelligence/ma_probability.py`
- `src/bve/intelligence/ma_scoring.py`
- `src/bve/intelligence/ma_eligibility.py`
- `src/bve/intelligence/exclusions/*`
- `src/bve/intelligence/deal_type_classification.py`
- `src/bve/intelligence/ma_target_size.py`
- `src/bve/intelligence/ma_asset_control_target.py`
- `src/bve/intelligence/ma_integration_complexity.py`
- `src/bve/intelligence/ma_distress_guard.py`
- `src/bve/intelligence/ma_data_confidence.py`
- `src/bve/intelligence/ma_layer1_attractiveness.py`
- `src/bve/intelligence/ma_layer2_bd_priority.py`
- `src/bve/intelligence/ma_pair_affordability.py`
- `src/bve/intelligence/ma_pair_asset_control.py`
- `src/bve/intelligence/ma_layer3_pair_realism.py`
- `src/bve/intelligence/ma_layer4_routing.py`
- `src/bve/intelligence/ma_layer5_calibration.py`
- `src/bve/intelligence/ma_calibration_dataset.py`

---

## Architecture Overview

The M&A system has two related paths:

```text
Live scanner path
  target/acquirer universe
  -> targetability and eligibility gates
  -> MAProbabilityScanner scoring
  -> legacy TA/DL/AF BD layer
  -> Layer 5 probability calibration
  -> ranked watchlist output

Institutional BD path
  Layer 0 target pre-screening
  -> Layer 1 target strategic attractiveness
  -> Layer 2 BD action priority
  -> Layer 3 pair-specific deal realism
  -> Layer 4 routing and deal-structure recommendation
  -> Layer 5 calibrated probabilities and confidence
```

The live scanner powers weekly target ranking. The institutional path is the
deeper scorecard for BD review. Both should be read as structured ranking and
probability-assistive logic, not as a fully validated takeout probability model.

---

## Layer Ownership And Double-Counting Rules

The most important design rule is that target-level facts and buyer-specific
feasibility are kept separate.

| Signal | Owning layer | Rule |
|---|---|---|
| Eligibility / hard exclusion | Layer 0A | Hard fail, severe cap, diligence queue, or route. |
| Deal archetype | Layer 0B | Routing / annotation only. |
| Target size | Layer 0C | Informational pre-screen only; no numeric affordability penalty. |
| Universal rights, economics, IP, manufacturing readiness | Layer 0D-T | Target-level multiplier/cap and valuation multiplier. |
| Raw commercial / operational integration complexity | Layer 0E | Target-level flag only. |
| Distress versus strategic quality | Layer 0F | Route or cap once; avoid re-penalizing downstream. |
| Missing or stale data | Layer 0G | Confidence label and data cap semantics. |
| Intrinsic target attractiveness | Layer 1 | Target-only quality, scarcity, value creation, setup, residual cleanliness. |
| BD action priority | Layer 2 | Whether BD should act and why. |
| Affordability for one buyer | Layer 3A | Pair-specific multiplier / cap / fail. |
| ROFR, consent, regional rights fit, buyer manufacturing fit | `ma_pair_asset_control.py` / Layer 3C in pair-realism | Pair-specific impact only. |
| Integration capability for one buyer | Layer 3D | Buyer capability offsets target complexity. |
| Antitrust, conflict, process close risk | Layer 3E-3H | Pair-specific feasibility and blockers. |
| Watchlist route and deal structure | Layer 4 | Recommendation layer; not empirical calibration. |
| Calibrated probability / close probability | Layer 5 | Probability language, shrinkage, confidence, catalyst hazard, encumbrance, antitrust. |

---

# Layer 0: Target Pre-Screening

**Purpose:** Decide whether a company enters the M&A scanner, where it routes,
and which target-level caps or diligence flags apply.

Layer 0 decides whether a company enters the M&A scanner and how it should be
routed. It does not assign the final M&A score.

Implementation order differs from conceptual numbering: `evaluate_layer0()`
computes 0G data confidence first because 0A hard exclusions use it for
insufficient-data decisions. The runtime order is:

```text
0G data confidence
  -> 0A hard exclusion (emits EligibilityStatus: PASS / DILIGENCE_QUEUE /
     REFRESH_REQUIRED / LEGAL_REVIEW_QUEUE / SEVERE_CAP / HISTORICAL_ONLY / HARD_FAIL)
  -> 0C target size, 0D asset control, 0E integration, 0F distress
  -> 0B deal-structure route (runs when 0A is PASS, DILIGENCE_QUEUE,
     REFRESH_REQUIRED, SEVERE_CAP, or LEGAL_REVIEW_QUEUE — not on HARD_FAIL
     or HISTORICAL_ONLY)
  -> 0H decision summary
```

Conceptual numbering still presents 0A before 0G because 0A is the first
business gate. Runtime order puts 0G first because 0A consumes its output.

**Architectural separation (refactored 2026-06-04):**

0A is a pure **stoplight / eligibility gate**. It answers "can we evaluate this
target?". It does NOT route companies to specialist models. Model routing is
owned exclusively by Layer 0B.

0B is a pure **deal-structure classification layer**. It answers "what deal
form fits this target?" using `DealStructureRoute` (11 transaction archetypes).
It runs even for imperfect targets (DILIGENCE_QUEUE, REFRESH_REQUIRED, etc.) to
provide a tentative route for analyst review.

## Layer 0A: Structured Exclusion Engine

**Purpose:** Remove companies that should not enter the live M&A ranking or route
them to the right non-standard model.

Primary files:

- `src/bve/intelligence/ma_eligibility.py`
- `src/bve/intelligence/exclusions/engine.py`
- `src/bve/intelligence/exclusions/rules.py`
- `src/bve/intelligence/exclusions/models.py`
- `src/bve/intelligence/exclusions/enums.py`

Implemented gate concepts:

| Gate concept | Examples | Output style |
|---|---|---|
| Entity validity | non-biotech, SPAC/shell, holding company, passive royalty vehicle, services-only, restricted entity | hard fail or route |
| Standalone status | already acquired, merged, delisted, pending definitive acquisition, ticker mismatch | remove, historical-only, or diligence queue |
| Target universe | known acquirer in target universe | route to buyer universe or hard fail |
| Asset visibility | no lead asset, no platform, inactive pipeline, vague pipeline | hard fail or diligence queue |
| Asset viability | discontinued lead, failed pivotal trial, fatal safety, unresolved hold, no regulatory path | hard fail, severe cap, or queue |
| Rights / IP / ownership | no ownable rights, fully licensed away, unavailable territory, IP dispute, royalty stack | hard fail, route, cap, or queue |
| Financial / going concern | bankruptcy, liquidation, short runway, missing cash/debt/valuation data | hard fail, distress route, or queue |
| Market data / liquidity | stale market data, illiquidity, OTC risk, corporate action confusion | cap, exclude, or refresh required |
| Legal / integrity | sanctions, fraud, data-integrity issue, SEC cloud, GMP failure | hard fail, cap, or legal-review queue |
| Commercial relevance | too-small market, no unmet need, undifferentiated asset, reimbursement/adoption barrier | cap or route |
| Model routing | licensing-only, distress-only, commercial-only, platform-only, historical-only | route to proper model |

Layer 0A emits one of seven `EligibilityStatus` values via
`EligibilityAssessment`:

| Status | Meaning | Enters live ranking? |
|---|---|---|
| `PASS` | All hard gates clear. | Yes |
| `DILIGENCE_QUEUE` | Insufficient or stale data (e.g. missing cash/valuation). | No — queued for enrichment |
| `REFRESH_REQUIRED` | Stale market data; prior data is too old for scoring. | No — re-evaluate after data update |
| `LEGAL_REVIEW_QUEUE` | Gate 8 non-fatal issue (sanctions exposure, GMP cloud, SEC matter). | No — legal review first |
| `SEVERE_CAP` | Hard cap applied but not a full exclusion (e.g. adverse safety on primary asset). | No — capped score only |
| `HISTORICAL_ONLY` | Already acquired; eligible for training set only. | No |
| `HARD_FAIL` | Non-biotech, shell/SPAC, no lead asset, fully acquired/liquidated. | No |

Note: `ROUTE_TO_OTHER_MODEL` has been **removed** from 0A as of the 2026-06-04
refactor. Specialist model routing (licensing, platform, distress, commercial)
is now owned by Layer 0B (`DealStructureRoute`). Only
`historical_training` sentinel → `HISTORICAL_ONLY` remains in Gate 10.

Status: Implemented in code.

## Layer 0B: Deal-Structure Route Classification

**Purpose:** Classify the natural transaction archetype and own all specialist
model routing. 0B runs when 0A returns PASS, DILIGENCE_QUEUE, REFRESH_REQUIRED,
SEVERE_CAP, or LEGAL_REVIEW_QUEUE. It does NOT run for HARD_FAIL or
HISTORICAL_ONLY targets.

Primary file: `src/bve/intelligence/deal_type_classification.py`.

Layer 0B produces two complementary outputs:

1. **`DealTypeClassification`** — six canonical deal archetypes with weights,
   modifiers, and value-share estimates (unchanged since Sprint 21).
2. **`DealStructureRouteResult`** — eleven transaction archetypes closer to
   how BD teams structure deals. This is the new authoritative routing output
   added in the 2026-06-04 refactor.

### DealStructureRoute — 11 transaction archetypes

| Route | Recommended model | Meaning |
|---|---|---|
| `FULL_COMPANY_TAKEOUT` | `lead_asset_rnpv_model` | Clean global rights, small pipeline. Full company acquisition. |
| `LEAD_ASSET_TAKEOUT` | `lead_asset_rnpv_model` | Multiple products or partial rights; structured as lead-asset deal. |
| `PIPELINE_PORTFOLIO_TAKEOUT` | `portfolio_mna_model` | Multiple distinct clinical programs; portfolio deal. |
| `PLATFORM_ACQUISITION` | `platform_fit_model` | Platform / technology engine is primary value driver. |
| `COMMERCIAL_FRANCHISE_ACQUISITION` | `commercial_synergy_model` | Approved revenue / franchise drives value. |
| `GLOBAL_LICENSE` | `licensing_model` | Global rights deal; no territorial restriction. |
| `REGIONAL_LICENSE` | `licensing_model` | Rights are geographically split or limited. |
| `OPTION_TO_LICENSE_OR_ACQUIRE` | `licensing_model` | Future optionality structure; uncertainty or encumbrance present. |
| `CO_DEVELOPMENT_OR_CO_COMMERCIALIZATION` | `licensing_model` | Shared development or commercialization responsibility. |
| `MINORITY_EQUITY_PLUS_COLLABORATION` | `licensing_model` | Strategic minority stake with collaboration agreement. |
| `DISTRESSED_OPTIONALITY` | `distress_adjusted_model` | Financing pressure or quality issue; distress-option structure. |

`ASSET_LICENSE_PARTNERSHIP` (DealType) maps to five licensing sub-routes based
on `asset_rights_scope`, `has_existing_partnership`, `royalty_stack_rate`, and
`financing_pressure_high`. The sub-route is determined by structural signal
overrides in `classify_deal_structure_route()`.

### Structural signal overrides (priority order)

Layer 0B checks these signal conditions before the DealType-based mapping:

1. `financing_pressure_high AND lead_asset_quality_low` → `DISTRESSED_OPTIONALITY`
2. `asset_rights_scope == "licensed_in"` → `OPTION_TO_LICENSE_OR_ACQUIRE`
3. `asset_rights_scope == "regional_split"` → `REGIONAL_LICENSE`
4. `has_existing_partnership AND product_count >= 3` → `CO_DEVELOPMENT_OR_CO_COMMERCIALIZATION`
5. `royalty_stack_rate > 0.15` (with global rights) → `OPTION_TO_LICENSE_OR_ACQUIRE`

### DealTypeClassification — six archetypes (backward compat)

| Deal type | Recommended model |
|---|---|
| `SINGLE_ASSET_TAKEOUT` | `lead_asset_rnpv_model` |
| `PIPELINE_PORTFOLIO_TAKEOUT` | `portfolio_mna_model` |
| `PLATFORM_ACQUISITION` | `platform_fit_model` |
| `COMMERCIAL_FRANCHISE_ACQUISITION` | `commercial_synergy_model` |
| `ASSET_LICENSE_PARTNERSHIP` | `licensing_model` |
| `DISTRESSED_OPTIONALITY` | `distress_adjusted_model` |

Modifiers: `LEAD_ASSET_HEAVY`, `PIPELINE_IN_A_PRODUCT`, `PLATFORM_LITE`,
`COMMERCIAL_PIPELINE_HYBRID`, `RIGHTS_ENCUMBERED`, `DISTRESS_OVERLAY`,
`HISTORICAL_ONLY`.

Note: `MONITOR_ONLY` is NOT a `DealStructureRoute`. It is an action/cadence
recommendation owned by Layer 4.

Status: Implemented in code (refactored 2026-06-04).

## Layer 0C: Target-Size Pre-Screen

**Purpose:** Estimate rough acquisition scale and buyer-universe fit without
applying pair-specific affordability penalties.

Primary file: `src/bve/intelligence/ma_target_size.py`.

Target size is informational at Layer 0. It flags the likely buyer universe but
does not apply a numeric affordability penalty.

```text
expected_acquisition_cost =
    enterprise_value * (1 + expected_takeout_premium)

default expected_takeout_premium = 35%
```

| Bucket | EV / market-cap range | Meaning |
|---|---:|---|
| `SUB_SCALE` | < $100M | Small specialty buyer, licensing, distressed optionality, or special situation. |
| `SMALL_CAP` | $100M-$500M | Standard small biotech M&A range. |
| `MID_CAP` | $500M-$5B | Core biotech M&A universe. |
| `LARGE_CAP` | $5B-$25B | Large pharma / top specialty buyer likely required. |
| `MEGA_DEAL` | > $25B | Top pharma only; rare. |
| `UNKNOWN` | missing EV and market cap | Data gap. |

True pair-specific affordability is calculated later in Layer 3A.

Status: Implemented in code.

## Layer 0D-T: Target-Level Asset Control

**Purpose:** Measure whether the target controls enough rights, economics, IP,
manufacturing readiness, and diligence materials for a full acquisition to be
structurally underwritable.

Primary file: `src/bve/intelligence/ma_asset_control_target.py`.

Layer 0D-T asks whether the target controls enough of the asset, rights,
economics, IP, manufacturing package, and diligence package for any acquirer to
underwrite it. It is target-level only.

Composite:

```text
asset_control_score =
    0.25 * rights_control
  + 0.20 * economic_control
  + 0.20 * partner_encumbrance_facts
  + 0.15 * ip_control
  + 0.10 * manufacturing_readiness
  + 0.10 * diligence_readiness
```

Bucket formulas:

```text
rights_control =
    0.40 * global_rights_control
  + 0.25 * key_geography_control
  + 0.20 * indication_control
  + 0.15 * change_of_control_freedom

economic_control =
    0.35 * royalty_cleanliness
  + 0.25 * milestone_burden
  + 0.20 * profit_share_cleanliness
  + 0.20 * cost_obligation_cleanliness

partner_encumbrance_facts =
    0.50 * no_blocking_rights
  + 0.30 * clean_governance_control
  + 0.20 * partner_encumbrance_severity

ip_control =
    0.35 * patent_strength
  + 0.25 * exclusivity_runway
  + 0.20 * freedom_to_operate
  + 0.20 * ownership_cleanliness

manufacturing_readiness =
    0.35 * process_transferability
  + 0.30 * supply_redundancy
  + 0.20 * gmp_quality_readiness
  + 0.15 * scale_capacity

diligence_readiness =
    0.30 * clinical_data_completeness
  + 0.25 * cmc_package_completeness
  + 0.20 * regulatory_file_completeness
  + 0.15 * safety_database_quality
  + 0.10 * data_room_readiness
```

Gate treatment:

| Asset-control score | Gate treatment | Score multiplier | Max M&A score cap |
|---:|---|---:|---:|
| >= 0.85 | `CLEAN` | 1.00 | None |
| 0.70-0.849 | `MILD_PENALTY` | 0.95 | None |
| 0.50-0.699 | `MEANINGFUL_PENALTY` | 0.80 | None |
| 0.35-0.499 | `SEVERE_CAP` | 0.60 | 0.55 |
| < 0.35 | `ROUTE_TO_LICENSING_OR_FAIL` | 0.40 | 0.40 |

Hard blockers:

| Condition | Treatment |
|---|---|
| `no_ownable_rights=True` | `HARD_FAIL`, multiplier `0.20`, cap `0.40` |
| `fatal_ip_dispute=True` | Composite capped at `0.30`; route away from clean full-acquisition logic |
| `fully_licensed_away=True` | Composite capped at `0.30`; route to licensing |

Target-level valuation multiplier:

```text
r_mult = 0.50 + 0.50 * rights_score
e_mult = 0.55 + 0.45 * economic_score
i_mult = 0.60 + 0.40 * ip_score
m_mult = 0.70 + 0.30 * manufacturing_readiness_score

encumbrance_valuation_multiplier =
    r_mult * e_mult * i_mult * m_mult
```

Important boundary: Layer 0D-T records ROFR, opt-in, consent, partner, regional
rights, and manufacturing-complexity facts. Whether those facts help or hurt a
specific buyer is handled in Layer 3B / 3C.

Status: Implemented in code.

## Layer 0E: Integration Complexity Flag

**Purpose:** Identify target-level commercial and operational complexity before
buyer capability is considered.

Primary file: `src/bve/intelligence/ma_integration_complexity.py`.

Layer 0E identifies target-level integration complexity. It does not apply the
final buyer-specific penalty and does not reward synergy.

```text
raw_integration_complexity =
    0.15 * product_complexity
  + 0.10 * indication_complexity
  + 0.15 * salesforce_burden
  + 0.15 * manufacturing_transfer_complexity
  + 0.15 * geographic_complexity
  + 0.15 * payer_access_complexity
  + 0.10 * channel_complexity
  + 0.05 * systems_compliance_transfer_risk
```

Buyer-specific handling is deferred to Layer 3D:

```text
buyer_integration_capability =
    0.25 * commercial_infrastructure_fit
  + 0.20 * manufacturing_capability_fit
  + 0.20 * payer_access_capability_fit
  + 0.15 * geographic_footprint_fit
  + 0.10 * systems_compliance_capability_fit
  + 0.10 * prior_integration_experience

adjusted_integration_penalty =
    raw_integration_complexity_score * (1 - buyer_integration_capability)
```

Pair treatment:

| Adjusted penalty | Treatment | Multiplier | Cap |
|---:|---|---:|---:|
| <= 0.15 | no penalty | 1.00 | None |
| <= 0.30 | mild penalty | 0.95 | None |
| <= 0.50 | meaningful penalty | 0.85 | None |
| <= 0.70 | severe penalty / cap | 0.70 | 0.60 |
| > 0.70 | pair-level cap or fail | 0.50 | 0.50 |

Pair fail is reserved for very high complexity with very weak buyer capability.

Status: Implemented in code.

## Layer 0F: Distress Quality Guard

**Purpose:** Separate strategic M&A attractiveness from financial distress or
negative-enterprise-value traps.

Primary file: `src/bve/intelligence/ma_distress_guard.py`.

Layer 0F prevents distressed companies from ranking highly just because they are
cheap. It separates financing distress from strategic asset quality.

```text
distress_pressure_score =
    0.35 * financing_pressure
  + 0.25 * runway_pressure
  + 0.20 * valuation_distress
  + 0.10 * capital_market_access_risk
  + 0.10 * near_term_funding_need

distress_quality_score =
    0.35 * lead_asset_quality
  + 0.20 * platform_validation
  + 0.15 * clinical_salvageability
  + 0.15 * strategic_scarcity
  + 0.15 * asset_control_cleanliness
```

Interpretation:

- High distress plus high quality can route to distressed optionality.
- Very high distress plus weak quality receives a probability cap.
- Distress is handled here and should not be re-counted as generic pair friction
  downstream.

Status: Implemented in code.

## Layer 0G: Data Confidence

**Purpose:** Grade whether the model has enough fresh, reliable data to trust the
M&A score.

Primary file: `src/bve/intelligence/ma_data_confidence.py`.

Layer 0G measures how much the model should trust the M&A score.

```text
data_confidence_score =
    0.30 * financial_data_confidence
  + 0.25 * asset_data_confidence
  + 0.20 * rights_ip_data_confidence
  + 0.15 * market_data_confidence
  + 0.10 * acquirer_profile_confidence
```

Treatment:

| Score | Label | Ranking treatment |
|---:|---|---|
| >= 0.80 | `HIGH` | eligible for ranked output |
| 0.60-0.79 | `MEDIUM` | eligible but flagged |
| 0.40-0.59 | `LOW` | diligence queue by default |
| < 0.40 | `VERY_LOW` | exclude from ranking |

Cap rules:

- rights/IP data confidence below `0.50` caps the label at `MEDIUM`,
- missing asset profile caps at `LOW`,
- missing valuation data caps at `LOW`,
- missing asset ownership data caps at `MEDIUM`.

Status: Implemented in code.

## Layer 0H: Decision Summary

**Purpose:** Aggregate Layer 0 decisions into an audit-friendly routing summary.

Layer 0H is the audit aggregation generated by `evaluate_layer0()`. It records:

- live-ranking and historical-training eligibility,
- routing verdict,
- active target-level multiplier and caps,
- data-confidence label,
- primary deal type,
- target-size bucket,
- required downstream pair checks,
- warning flags and double-count guards.

It is audit-only and does not add a new score.

Status: Implemented in code.

---

# Layer 1: Strategic Attractiveness

**Purpose:** Score the intrinsic target-level attractiveness of the company or
asset, before buyer-specific feasibility.

Primary file: `src/bve/intelligence/ma_layer1_attractiveness.py`.

Layer 1 answers:

```text
"Assuming this company passed Layer 0, how fundamentally attractive is this
asset/company as a BD target?"
```

Layer 1 does not answer eligibility, buyer affordability, deal timing, exact
deal structure, or calibrated probability.

Core formula:

```text
raw_score =
    0.35 * asset_quality
  + 0.25 * strategic_scarcity
  + 0.20 * value_creation
  + 0.15 * transaction_setup
  + 0.05 * structural_cleanliness

capped_score = min(raw_score, all_triggered_layer1_caps)

confidence_adjusted_score =
    capped_score * confidence_multiplier
```

Top-level weights:

| Component | Weight | Purpose |
|---|---:|---|
| Asset quality | 0.35 | Clinical, regulatory, IP, CMC, commercial, and execution quality. |
| Strategic scarcity | 0.25 | Scarcity of TA, modality/platform, competitive position, and gap relevance. |
| Value creation | 0.20 | rNPV gap, standalone rNPV quality, downside protection, expectations gap. |
| Transaction setup | 0.15 | Conditions that could create a transaction window. |
| Structural cleanliness | 0.05 | Residual cleanliness after Layer 0 hard checks. |

Subweights:

| Component | Subweights |
|---|---|
| Asset quality | clinical evidence 0.25; differentiation 0.20; regulatory path 0.15; IP/exclusivity 0.15; CMC feasibility 0.10; commercial meaningfulness 0.10; management execution 0.05 |
| Strategic scarcity | TA scarcity 0.25; modality/platform scarcity 0.20; competitive position 0.20; pipeline-gap relevance 0.15; franchise optionality 0.10; replacement difficulty 0.10 |
| Value creation | premium-adjusted rNPV gap 0.35; standalone rNPV quality 0.20; downside protection 0.15; cost to complete 0.10; market expectations gap 0.10; strategic option value 0.10 |
| Transaction setup | financing pressure 0.30; catalyst proximity 0.25; seller openness 0.20; valuation stress 0.15; prior BD activity 0.10 |
| Structural cleanliness | rights clarity 0.30; IP cleanliness 0.25; economic control 0.20; diligence readiness 0.15; manufacturing transferability 0.10 |

Confidence multiplier:

| Overall confidence | Multiplier |
|---:|---:|
| >= 0.80 | 1.00 |
| >= 0.60 | 0.90 |
| >= 0.40 | 0.75 |
| < 0.40 | 0.50 |

Layer 1 composite caps:

| Cap name | Trigger concept | Cap |
|---|---|---:|
| `composite_low_clinical_evidence` | clinical evidence < 0.35 | 0.55 |
| `composite_low_asset_quality` | asset quality < 0.45 | 0.50 |
| `composite_no_differentiation_or_commercial` | differentiation < 0.35 and commercial meaningfulness < 0.50 | 0.55 |
| `composite_low_regulatory_path` | regulatory path < 0.35 | 0.55 |
| `composite_low_ip_exclusivity` | IP/exclusivity < 0.35 | 0.60 |
| `composite_value_trap_stress` | asset quality < 0.50 and valuation stress > 0.70 | 0.50 |
| `composite_value_trap_financing` | financing pressure > 0.70 and asset quality < 0.50 | 0.45 |
| `composite_low_strategic_scarcity` | strategic scarcity < 0.35 | 0.60 |

Status: Implemented in code.

Known weakness: weights are evidence-informed priors, not empirically fitted
coefficients.

---

# Layer 2: BD Priority

**Purpose:** Translate target attractiveness into business-development action
priority and timing urgency.

Primary file: `src/bve/intelligence/ma_layer2_bd_priority.py`.

Layer 2 answers:

```text
"Given Layer 1 target attractiveness, should BD act now, monitor, build a
relationship, map buyers, or pass?"
```

Core formula:

```text
BD_Action_Score =
    0.40 * Strategic_Priority
  + 0.30 * Deal_Momentum
  + 0.20 * Acquirer_Pull
  + 0.10 * Information_Readiness
```

Strategic Priority:

```text
Strategic_Priority =
    0.35 * layer1_attractiveness
  + 0.25 * acquirer_strategic_fit
  + 0.20 * strategic_scarcity
  + 0.10 * pipeline_gap_urgency
  + 0.10 * strategic_option_value
```

Deal Momentum:

```text
Deal_Momentum =
    0.55 * target_side_pressure
  + 0.45 * buyer_side_urgency
```

Target-side pressure:

```text
target_side_pressure =
    0.30 * financing_pressure
  + 0.20 * seller_openness
  + 0.20 * catalyst_timing
  + 0.15 * valuation_distress
  + 0.15 * governance_activist_pressure
```

Buyer-side urgency:

```text
buyer_side_urgency =
    0.30 * pipeline_gap_urgency
  + 0.25 * loe_revenue_cliff_urgency
  + 0.20 * competitive_fomo
  + 0.15 * recent_bd_pattern
  + 0.10 * strategic_priority_recency
```

Acquirer Pull:

```text
Acquirer_Pull =
    0.25 * ta_fit
  + 0.20 * modality_fit
  + 0.20 * pipeline_gap_urgency
  + 0.15 * buyer_deal_appetite
  + 0.10 * existing_relationship
  + 0.10 * competitive_fomo
```

Information Readiness:

```text
Information_Readiness =
    0.25 * layer1_confidence
  + 0.20 * acquirer_profile_freshness
  + 0.20 * transaction_driver_source_quality
  + 0.15 * valuation_data_freshness
  + 0.10 * rights_encumbrance_clarity
  + 0.10 * catalyst_date_confidence
```

Caps:

| Trigger | Cap |
|---|---:|
| Strategic Priority < 0.40 | 0.50 |
| Deal Momentum < 0.30 | 0.65 |
| Acquirer Pull < 0.35 | 0.55 |
| Information Readiness < 0.40 | 0.60 |

Action classifications include:

- Distress Trap Warning
- Active Pursuit Candidate
- High-Priority BD Diligence
- Catalyst Watch
- Diligence Queue
- Strategic Watch
- Relationship Build
- Acquirer Mapping Needed
- Low Priority / Pass

Preliminary friction warnings are warnings, not hard blockers.

Status: Implemented in code.

---

# Layer 3: Pair-Specific Deal Realism

**Purpose:** Decide whether a specific acquirer can realistically acquire a
specific target.

Primary files:

- `src/bve/intelligence/ma_layer3_pair_realism.py`
- `src/bve/intelligence/ma_pair_affordability.py`
- `src/bve/intelligence/ma_pair_asset_control.py`
- `src/bve/intelligence/ma_integration_complexity.py`

Layer 3 answers:

```text
"For this specific acquirer-target pair, is the deal executable, or should
the Layer 2 BD Action Score be capped?"
```

Diagnostic weighted score:

```text
pair_feasibility_score =
    0.20 * affordability
  + 0.15 * consideration_realism
  + 0.20 * rights_control_fit
  + 0.15 * integration_capability
  + 0.15 * antitrust_feasibility
  + 0.10 * strategic_conflict
  + 0.05 * process_closing
```

Enforcement:

```text
if hard_fail:
    adjusted_bd_score = 0.0
else:
    adjusted_bd_score = min(
        upstream_layer2_score * pair_feasibility_multiplier,
        pair_level_cap,
    )
```

Pair score to multiplier:

| Pair feasibility score | Multiplier |
|---:|---:|
| >= 0.85 | 1.00 |
| >= 0.70 | 0.90 |
| >= 0.55 | 0.75 |
| >= 0.40 | 0.55 |
| < 0.40 | 0.40 |
| hard fail | 0.00 |

## Layer 3A: Affordability

**Purpose:** Test one acquirer’s cash, debt, and realistic stock capacity against
one target’s expected acquisition cost.

Primary file: `src/bve/intelligence/ma_pair_affordability.py`.

```text
expected_acquisition_cost =
    target_ev_millions * (1 + expected_takeout_premium)

realistic_stock_component =
    acquirer_market_cap_millions
  * max_stock_issuance_pct
  * stock_quality_multiplier

deal_capacity =
    cash_available
  + estimated_debt_capacity
  + realistic_stock_component
  - minimum_balance_buffer

affordability_ratio =
    expected_acquisition_cost / deal_capacity
```

Stock quality multiplier:

```text
base = investor_dilution_tolerance  # default 0.50
P/B >= 4.0       -> +0.15
P/B < 1.5        -> -0.20
volatility < 20% -> +0.10
volatility 20-40 -> -0.10
volatility > 40% -> -0.25
clamp to [0.10, 1.00]
```

Affordability treatment:

| Affordability ratio | Treatment | Multiplier |
|---:|---|---:|
| <= 0.50 | `NO_PENALTY` | 1.00 |
| <= 0.85 | `MILD_PENALTY` | 0.90 |
| <= 1.10 | `SEVERE_PENALTY` | 0.60 |
| > 1.10 | `HARD_FAIL` | 0.00 |

Layer 3 mapping:

- no penalty: diagnostic score around 0.90,
- mild penalty: score around 0.65 and possible cap around 0.80,
- severe penalty: score around 0.35 and cap around 0.60,
- hard fail: pair fail.

Missing EV should be treated as a data gap, not as a universal target failure.

## Layer 3B / 3C Numbering Note

Two current modules use overlapping sublayer labels:

- `ma_pair_asset_control.py` calls pair-specific asset-control `Layer 3B`.
- `ma_layer3_pair_realism.py` calls consideration realism `3B` and rights/control
  fit `3C`.

The orchestrated pair-realism order below follows `ma_layer3_pair_realism.py`.
The standalone pair asset-control helper remains implemented and documented in
code as `Layer 3B`; it feeds the rights/control fit component.

## Layer 3B: Consideration Realism

**Purpose:** Penalize buyer-target pairs where the headline transaction currency
is theoretically available but commercially unrealistic.

Primary file: `src/bve/intelligence/ma_layer3_pair_realism.py`.

```text
consideration_realism =
    0.30 * cash_stock_mix_feasibility
  + 0.20 * target_shareholder_acceptability
  + 0.15 * acquirer_shareholder_acceptability
  + 0.15 * cvr_milestone_suitability
  + 0.10 * tax_efficiency
  + 0.10 * precedent_consistency
```

This layer tests whether the likely consideration package is realistic for both
shareholder bases and whether CVR/milestone mechanics fit the uncertainty.

## Layer 3C: Rights / Control Pair Fit

**Purpose:** Apply buyer-specific penalties for ROFR, opt-in, consent, regional
rights, exclusivity conflicts, and manufacturing fit.

Primary files:

- `src/bve/intelligence/ma_layer3_pair_realism.py`
- `src/bve/intelligence/ma_pair_asset_control.py`

Pair-specific rules:

| Fact | Pair-specific treatment |
|---|---|
| Existing partner acquirer | ROFR / consent impact may be waived or mitigated. |
| Blocking ROFR for non-partner buyer | Multiplier <= 0.65, cap <= 0.55. |
| Active opt-in right | Multiplier <= 0.80. |
| Consent required for this change-of-control | Multiplier <= 0.70. |
| Buyer-specific exclusivity conflict | Multiplier <= 0.80. |
| Regional rights severe mismatch, overlap < 0.50 | Multiplier <= 0.75, cap <= 0.65. |
| Regional rights partial mismatch, overlap < 0.80 | Multiplier <= 0.90. |
| High-complexity manufacturing plus weak buyer fit | Multiplier <= 0.75, cap <= 0.65. |
| Medium-complexity manufacturing plus weak buyer fit | Multiplier <= 0.85. |
| High-complexity manufacturing plus moderate buyer fit | Multiplier <= 0.90. |
| Buyer manufacturing fit >= 0.80 | No manufacturing mismatch penalty. |

## Layer 3D: Integration Capability

**Purpose:** Offset target integration complexity by the specific acquirer’s
commercial, manufacturing, payer, geography, systems, and prior-integration
capability.

Primary file: `src/bve/intelligence/ma_integration_complexity.py`.

Layer 3D applies the buyer capability adjustment described in Layer 0E. The
target raw complexity is multiplied by `1 - buyer_integration_capability`.

## Layer 3E: Antitrust Feasibility

**Purpose:** Identify pair-specific antitrust risk before probability calibration.

Primary file: `src/bve/intelligence/ma_layer3_pair_realism.py`.

```text
antitrust_feasibility =
    0.25 * current_product_overlap
  + 0.20 * pipeline_overlap
  + 0.20 * market_concentration
  + 0.15 * innovation_competition_risk
  + 0.10 * divestiture_complexity
  + 0.10 * jurisdictional_complexity
```

Required divestiture that removes the core deal value is a hard-fail condition.

## Layer 3F: Strategic Conflict

**Purpose:** Fail or cap acquirers whose existing strategy conflicts with owning
the target.

```text
strategic_conflict =
    0.30 * product_cannibalization
  + 0.20 * pipeline_cannibalization
  + 0.15 * channel_conflict
  + 0.15 * partner_conflict
  + 0.10 * pricing_contracting_conflict
  + 0.10 * organizational_conflict
```

## Layer 3G: Process / Closing Feasibility

**Purpose:** Capture deal-process friction that is specific to the buyer-target
pair.

```text
process_closing =
    0.20 * target_board_alignment
  + 0.15 * shareholder_approval_likelihood
  + 0.15 * management_retention_feasibility
  + 0.15 * financing_process_readiness
  + 0.10 * diligence_package_readiness
  + 0.10 * cross_border_execution_feasibility
  + 0.10 * timeline_feasibility
  + 0.05 * litigation_risk_inverse
```

## Layer 3H: Diligence Blockers

**Purpose:** Record pair-specific fatal blockers discovered during diligence.

Layer 3H is where pair-specific fatal blockers are recorded, such as:

- self-acquisition,
- parent/subsidiary conflict,
- existing majority-owner complications,
- impossible affordability,
- strategic conflict,
- antitrust impossibility,
- diligence issue that blocks closing.

Status: Implemented in code.

---

# Layer 4: Routing And Deal Structure

**Purpose:** Convert upstream scores into BD operating language: pursue, monitor,
license, partner, avoid, or route to another model.

Primary files:

- `src/bve/intelligence/ma_layer4_routing.py`
- `src/bve/intelligence/ma_layer4_bd_routing.py`
- `src/bve/intelligence/ma_deal_structure_rationale.py`
- `src/bve/intelligence/ma_deal_structure_bonus.py`

Layer 4 converts upstream scores into BD operating language.

Runtime classification order in `compute_layer4()`:

```text
pass hard gates
  -> data_insufficient
  -> process_ready
  -> active_pursuit
  -> catalyst_watch
  -> relationship_build
  -> strategic_radar
  -> default data_insufficient
```

Watchlist classes:

| Class | Meaning |
|---|---|
| `pass` | Do not spend active BD time. |
| `data_insufficient` | Key information missing; diligence or refresh needed. |
| `strategic_radar` | Worth tracking, but no near-term action. |
| `relationship_build` | Good fit but not process-ready; build connection. |
| `catalyst_watch` | Monitor around defined readout / regulatory / financing event. |
| `active_pursuit` | Begin active BD diligence or outreach. |
| `process_ready` | Candidate is actionable and pair feasibility is strong. |

Deal-structure recommendations:

| Structure | Typical use |
|---|---|
| `full_acquisition` | Clean control target with high strategic fit and feasible pair economics. |
| `asset_license` | Rights/control, affordability, or uncertainty makes full acquisition less efficient. |
| `option_to_acquire` | High uncertainty with a defined future inflection point. |
| `co_development` | Shared development risk or complementary capabilities matter. |
| `regional_rights` | Geography-specific capability or rights split drives structure. |
| `research_collaboration` | Platform or early science; asset not mature enough for takeout. |
| `minority_equity` | Alignment or relationship building without control. |
| `monitor_only` | Track but do not act. |

Review cadence:

| Watchlist class | Review cadence | Time horizon |
|---|---|---|
| `pass` | `none` | `n/a` |
| `data_insufficient` | `as_needed` | `n/a` |
| `strategic_radar` | `quarterly` | `24+ months` |
| `relationship_build` | `monthly` | `12-24 months` |
| `catalyst_watch` | `bi_weekly` | `0-6 months` |
| `active_pursuit` | `weekly` | `3-12 months` |
| `process_ready` | `weekly` | `0-6 months` |

Design principles:

- Routing uses strict priority / first-match logic.
- Persistence suppression requires repeated observations unless a major event occurs.
- Deal-type overlay is diagnostic and memo-only.
- Deal-structure residual bonus is disabled by default.

Status: Implemented in code.

---

# Layer 5: Calibration, Confidence, And Close Probability

**Purpose:** Convert score outputs into probability language, confidence labels,
hazard-scaled timing, and closing-feasibility-adjusted probability.

Primary files:

- `src/bve/intelligence/ma_layer5_calibration.py`
- `src/bve/intelligence/ma_calibration_dataset.py`
- `src/bve/intelligence/ma_probability_calibration.py`
- `src/bve/intelligence/ma_segment_calibration.py`
- `src/bve/intelligence/ma_no_lookahead_replay.py`
- `src/bve/intelligence/ma_postmortem.py`
- `src/bve/intelligence/ma_threshold_optimizer.py`
- `src/bve/intelligence/ma_model_governance.py`

Layer 5 converts score output into probability language and audit artifacts. It
does not make a weak target attractive; it calibrates the score and communicates
uncertainty.

## Core Calibration

Default logistic settings:

```text
slope = 8.0
midpoint = 0.68
```

Calibration tries to load `src/bve/config/ma_calibration_params.json`. If the
file is absent, the code uses warning-backed defaults.

Important runtime behavior: when fitted calibration parameters are absent or
invalid, `calibration_fitted=False`, `calibration_params_source` is
`hard_coded_defaults`, and output confidence is capped to `very_low`. The rank
score is still useful for ordering, but the probability should be treated as
fallback, not fitted.

Shrinkage weights by comparable sample size:

| Comparable N | Base-rate weight | Logistic weight | Bucket weight |
|---:|---:|---:|---:|
| < 10 | 0.60 | 0.20 | 0.20 |
| 10-19 | 0.50 | 0.30 | 0.20 |
| 20-29 | 0.40 | 0.40 | 0.20 |
| >= 30 | 0.30 | 0.50 | 0.20 |

Probability bands:

| Band | Threshold |
|---|---:|
| very low | < 0.05 |
| low | < 0.15 |
| moderate | < 0.30 |
| high | < 0.50 |
| exceptional / requires manual review | >= 0.50 |

## Catalyst Hazard Scaling

Catalyst types:

| Type | Meaning |
|---|---|
| `NONE` | No specific binary catalyst. |
| `INVESTOR_UPDATE` | Conference / investor day / routine update. |
| `PHASE_2_POC` | Phase 2 proof-of-concept readout. |
| `FDA_MEETING` | FDA meeting or advisory committee. |
| `REGULATORY_DECISION` | PDUFA, EMA opinion, CRL response, or equivalent. |
| `PHASE_3_READOUT` | Pivotal Phase 3 top-line data. |
| `UNKNOWN` | No reliable catalyst schedule. |

Timing shape:

| Shape | Trigger | 6-month share | 18-month exponent |
|---|---|---:|---:|
| strongly front-loaded | <=90 days and Phase 3 / regulatory catalyst | 0.80 | 1.10 |
| front-loaded | <=180 days and meaningful non-routine catalyst | 0.68 | 1.25 |
| neutral | default | 0.55 | 1.35 |
| back-loaded | >365 days | 0.38 | 1.55 |

## Seller Willingness

| Seller willingness | Multiplier |
|---|---:|
| `ACTIVELY_SEEKING` | 0.90 |
| `OPEN` | 0.70 |
| `NEUTRAL` | 0.50 |
| `RELUCTANT` | 0.30 |
| `HOSTILE` | 0.10 |
| `UNKNOWN` | 0.50, with lower confidence |

## Encumbrance And Antitrust Close Probability

Layer 5 separates strategic transaction probability from effective close
probability.

Encumbrance multipliers:

| Encumbrance | Multiplier |
|---|---:|
| `NONE` | 1.00 |
| `OPTION_TO_ACQUIRE` | 0.95 |
| `ROFN` | 0.90 |
| `ROFR` | 0.75 |
| `UNKNOWN` | 1.00, with lower confidence |

Antitrust risk:

| Antitrust risk | Base multiplier |
|---|---:|
| `LOW` | 1.00 |
| `MEDIUM` | 0.88 |
| `HIGH` | 0.72 |
| `BLOCKED` | 0.00 |
| `UNKNOWN` | 1.00, with lower confidence |

Regime modifiers:

| Regime | Modifier |
|---|---:|
| `US_PERMISSIVE` | +0.05 |
| `US_STANDARD` | 0.00 |
| `US_HOSTILE` | -0.08 |
| `EU_STANDARD` | -0.03 |
| `MULTI_JURISDICTIONAL` | -0.10 |

Formula:

```text
antitrust_multiplier =
    clamp(base_antitrust_multiplier + regime_modifier, 0.0, 1.0)

p_effective_close_12m =
    p_any_strategic_transaction_12m
  * encumbrance_multiplier
  * antitrust_multiplier
```

Important boundary: encumbrance and antitrust affect
`p_effective_close_12m`. They do not mutate the rank score or
`p_any_strategic_transaction_12m`.

## Stage-Specific Transaction Priors

Stage priors are read from `transaction_mix_by_stage` in
`src/bve/config/industry_assumptions.yaml`.

| Stage | Acquisition fraction | License / partnership fraction |
|---|---:|---:|
| Preclinical | 0.15 | 0.75 |
| Phase 1 | 0.25 | 0.65 |
| Phase 2 | 0.40 | 0.55 |
| Phase 3 | 0.65 | 0.30 |
| NDA/BLA | 0.75 | 0.20 |
| Approved | 0.80 | 0.15 |
| Fallback | 0.60 | 0.35 |

The fractions do not sum to 1.0 because other structures can absorb the
remaining probability.

Layer 5 output splits:

```text
p_any_strategic_transaction_12m = primary calibrated 12-month output
p_full_acquisition_12m = acquisition_fraction * p_any_strategic_transaction_12m
p_license_or_partner_12m = license_fraction * p_any_strategic_transaction_12m
p_takeout_12m = backward-compatible alias for p_full_acquisition_12m
p_takeout_6m and p_takeout_18m = hazard-scaled derivatives of p_any
```

## Calibration Dataset Framework

Primary file: `src/bve/intelligence/ma_calibration_dataset.py`.

The dataset framework supports:

- labeled M&A outcomes,
- point-in-time feature snapshots,
- no-lookahead validation,
- positive/negative class balance checks,
- fit-readiness checks before logistic calibration.

Fit-readiness is intentionally conservative. Calibration remains limited until a
large, clean, point-in-time dataset exists.

Status: Implemented in code, but empirical label coverage is still limited.

## Layer 5 Sidecar Modules

These modules are implemented M&A support layers. They are not separate runtime
steps in the core 0-5 path, but they support calibration, audit, governance, and
explainability.

| Module | What it does |
|---|---|
| `ma_outcome_dataset.py` | Builds historical outcome labels and excludes leaky cases. |
| `ma_no_lookahead_replay.py` | Replays M&A pipeline snapshots as of historical dates. |
| `ma_probability_calibration.py` | Provides Platt, Bayesian-bin, and isotonic calibration helpers. |
| `ma_segment_calibration.py` | Blends segment / hierarchy calibration rates and detects out-of-domain segments. |
| `ma_threshold_optimizer.py` | Recommends threshold changes for operating modes; does not silently rewrite production thresholds. |
| `ma_postmortem.py` | Classifies prediction errors and writes postmortem ledgers. |
| `ma_drift_detection.py` | Detects score distribution, base-rate, calibration-quality, and categorical drift. |
| `ma_model_governance.py` | Generates model cards, governance checklists, validation reports, and audit records. |
| `ma_score_decomposition.py` | Optional attribution breakdown attached when Layer 5 decomposition is requested. |

---

# Live Scanner: TA / DL / AF Path

**Purpose:** Preserve the current production-style watchlist ranking path that
uses target attractiveness, deal likelihood, and acquirer fit.

Primary files:

- `src/bve/intelligence/ma_probability.py`
- `src/bve/intelligence/ma_scoring.py`

The live scanner ranks target-acquirer combinations using target quality,
strategic fit, valuation discount, de-risking, vulnerability, scarcity, external
deal pressure, catalyst proximity, and targetability gates.

The older scoring decomposition uses:

| Component | Meaning |
|---|---|
| `TA` | Target attractiveness / targetability. |
| `DL` | Deal likelihood or transaction pressure. |
| `AF` | Acquirer fit. |

Representative legacy BD action formula:

```text
BD_Action_Raw =
    0.50 * Strategic_Priority
  + 0.35 * Transaction_Probability
  + 0.15 * AF
```

This path is useful for watchlist ranking. The institutional Layers 0-5 are the
cleaner breakdown for BD memos and deeper diligence.

Status: Implemented in code.

---

# Other M&A Support Modules

**Purpose:** List implemented support modules that enrich, explain, audit, or
govern the M&A workflow.

The repo also contains implemented support modules used by scanner enrichment,
management diligence, strategy memos, and calibration workflows.

| Module | Purpose |
|---|---|
| `ma_bd_decomposition.py` | Older BD decomposition helpers for asset quality, value creation, timing, fit, and feasibility. |
| `ma_layer3_gate.py` | Institutional gate-system predecessor / companion to pair-realism scoring. |
| `ma_transaction_realism.py` | Seller readiness, price alignment, and transaction realism scoring. |
| `ma_buyer_mandate.py` | Buyer mandate and executive-alignment scoring. |
| `ma_relationship_history.py` | Buyer-target relationship history scoring. |
| `ma_buyer_thesis.py` | Aggregates buyer-target underwriting thesis. |
| `ma_internal_conflict.py` | Scores internal buyer conflict / cannibalization risk. |
| `ma_management_quality.py` | Management quality and value-preservation scoring. |
| `ma_management_receptivity.py` | Sell-side management receptivity gate and process-closing cap helper. |
| `ma_management_diligence.py` | Generates management diligence questions. |
| `ma_layer2_inputs_builder.py` | Adapters from real data sources into Layer 2 inputs. |
| `ma_deal_type_formulas.py` | Deal-type overlay formulas for 0B diagnostics. |
| `ma_deal_structure_rationale.py` | Narrative rationale for recommended deal structure. |
| `ma_deal_structure_bonus.py` | Experimental residual bonus; disabled by default in Layer 4. |
| `ma_calibration.py`, `ma_backtest.py`, `ma_calibration_audit.py`, `ma_calibration_models.py`, `ma_negative_set.py`, `ma_calibrated_probability_band.py` | Calibration dataset, backtest, audit, model, negative-set, and display-band utilities. |
| `weekly_ma_screen.py` | Weekly M&A screen result formatting. |

---

# Validation And Known Limits

**Purpose:** State what is implemented, what is calibrated, and where the M&A
layer should still be treated as decision support rather than ground truth.

Status:

- Layer 0-5 modules are implemented in code.
- The scanner is useful for ranking, triage, and memo discipline.
- Layer 5 calibration framework exists, but takeout probability is still limited
  by sparse historical labels.

Known limits:

- Many weights are expert priors, not fitted coefficients.
- Hidden rights, exact royalty stacks, unpublished consent rights, and private
  management willingness often require manual configuration.
- rNPV is intrinsic value and does not fully model control premiums, synergies,
  goodwill, platform know-how, or auction tension.
- Buyer profiles can become stale; profile freshness matters for Layer 2 and
  Layer 5 confidence.
- A high score is not a prediction that a deal will be announced. It means the
  target deserves higher BD attention under the current data.
