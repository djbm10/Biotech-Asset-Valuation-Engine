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
   modifiers, and value-share estimates.
2. **`DealStructureRouteResult`** — eleven transaction archetypes closer to
   how BD teams structure deals. This is the authoritative routing output added
   in the 2026-06-04 refactor.

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

`ASSET_LICENSE_PARTNERSHIP` maps to five licensing sub-routes based on
`asset_rights_scope`, `has_existing_partnership`, `royalty_stack_rate`, and
`financing_pressure_high`. The sub-route is determined by structural signal
overrides in `classify_deal_structure_route()`.

### Structural signal overrides

Layer 0B checks these signal conditions before the DealType-based mapping:

1. `financing_pressure_high AND lead_asset_quality_low` -> `DISTRESSED_OPTIONALITY`
2. `asset_rights_scope == "licensed_in"` -> `OPTION_TO_LICENSE_OR_ACQUIRE`
3. `asset_rights_scope == "regional_split"` -> `REGIONAL_LICENSE`
4. `has_existing_partnership AND product_count >= 3` -> `CO_DEVELOPMENT_OR_CO_COMMERCIALIZATION`
5. `royalty_stack_rate > 0.15` with global rights -> `OPTION_TO_LICENSE_OR_ACQUIRE`

### DealTypeClassification — six archetypes

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

Note: `MONITOR_ONLY` is not a `DealStructureRoute`. It is an action/cadence
recommendation owned by Layer 4.

Status: Implemented in code.

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

Layer 1 consumes analyst-normalized subfield scores in `[0, 1]`. Missing
subfields resolve to neutral `0.50` and reduce confidence instead of silently
creating a bullish or bearish view. Every subcomponent records score,
confidence, positive and negative drivers, missing-data labels, and any caps
triggered by hard conditions.

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

Base scoring rubric:

| Component | Weight | What a low score means | What a neutral score means | What a high score means |
|---|---:|---|---|---|
| Asset quality | 0.35 | Weak or unvalidated asset; poor clinical, regulatory, IP, CMC, commercial, or execution profile. | Mixed evidence or incomplete diligence; no clear high-quality or broken-asset conclusion. | Strong clinical/commercial asset with credible evidence, differentiation, regulatory path, protection, manufacturability, and market relevance. |
| Strategic scarcity | 0.25 | Crowded or strategically replaceable asset; limited industry demand. | Some scarcity or fit, but not enough to drive urgency by itself. | Scarce TA/modality/position with hard-to-replace strategic value. |
| Value creation | 0.20 | Limited upside at current value, poor rNPV quality, weak downside protection, or high completion burden. | Economics are plausible but not clearly compelling. | Attractive value gap, credible standalone rNPV, downside protection, manageable cost to complete, and favorable expectations gap. |
| Transaction setup | 0.15 | No seller pressure, no catalyst window, low openness, or stress driven by asset failure. | Some transaction setup exists, but timing and seller motivation are uncertain. | Financing, catalyst, seller, valuation, or prior-BD signals create a credible transaction window. |
| Structural cleanliness | 0.05 | Rights, IP, economics, diligence, or manufacturing transfer issues create residual friction. | Some complexity remains after Layer 0, but not enough to dominate target attractiveness. | Clean rights, IP, economics, diligence package, and transferability after Layer 0 hard checks. |

General score anchors:

| Score range | Interpretation |
|---:|---|
| 0.00-0.20 | Broken, absent, or severely adverse evidence. |
| 0.21-0.40 | Weak evidence or material unresolved risk. |
| 0.41-0.60 | Mixed, incomplete, or neutral evidence. |
| 0.61-0.80 | Positive, credible, and usable evidence. |
| 0.81-1.00 | Strong, de-risked, or best-in-class evidence. |

## Layer 1A: Asset Quality

**Purpose:** Score whether the target owns a high-quality clinical or commercial
asset independent of any specific buyer.

Layer 1A is the largest Layer 1 component. It includes clinical evidence,
differentiation, regulatory path, IP/exclusivity, CMC feasibility, commercial
meaningfulness, and management execution. Management execution has only 5%
subweight because governance and deal-process issues are handled elsewhere.

Asset-quality subweight rubric:

| Subweight | Weight | What it measures | Low score | Neutral score | High score |
|---|---:|---|---|---|---|
| Clinical evidence | 0.25 | Phase, trial design, endpoint quality, effect size, safety, and consistency. | No credible human efficacy, negative/mixed data, poor endpoint, or safety overhang. | Early, incomplete, single-arm, surrogate, or mixed evidence. | Robust positive human data, credible endpoint, clean safety, pivotal/registrational or approved evidence. |
| Differentiation | 0.20 | Advantage versus current and future standard of care. | Inferior, undifferentiated, or no clear treatment role. | Possible niche or incremental difference, but uncertain clinical/commercial relevance. | Clear efficacy, safety, convenience, biomarker, durability, or access advantage. |
| Regulatory path | 0.15 | Approval-path clarity, precedent, agency alignment, and filing readiness. | No credible approval path or major unresolved agency issue. | Plausible but uncertain pathway, limited precedent, or unresolved design questions. | Clear precedent, agency alignment, accepted endpoint, designation, SPA, or accepted filing. |
| IP / exclusivity | 0.15 | Patent estate, exclusivity runway, FTO, and ownership strength after Layer 0 hard checks. | Weak protection, short runway, ownership uncertainty, or FTO concern. | Reasonable but not fully diligenced protection or moderate runway. | Strong estate, clean ownership/FTO, long runway, and meaningful exclusivity. |
| CMC feasibility | 0.10 | Target-level manufacturability, scalability, maturity, and transferability. | Not scalable, not transferable, single fragile process, or unresolved CMC blocker. | Feasible but with meaningful scale-up, comparability, or tech-transfer work. | Mature, scalable, documented, transferable process with manageable supply risk. |
| Commercial meaningfulness | 0.10 | Market size, pricing/access plausibility, competitive relevance, and strategic revenue potential. | Too small, commercially unviable, or structurally blocked by COGS/access. | Niche or uncertain commercial opportunity. | Meaningful market with credible pricing, access, adoption, and strategic relevance. |
| Management execution | 0.05 | Management's clinical, regulatory, financing, disclosure, and BD execution quality. | Data integrity issue, repeated poor execution, or severe governance concern. | Mixed or limited execution record. | Strong, transparent execution across clinical, regulatory, financing, and partnering. |

Score generation:

| Subweight | Current source | Intended automated source |
|---|---|---|
| Clinical evidence | Analyst-normalized score, optionally informed by extraction output. | POS/science engine outputs: phase, prior-phase data, endpoint quality, effect size, safety, trial design, data maturity, and consistency. |
| Differentiation | Analyst-normalized score from clinical and competitive review. | Competitive landscape engine, head-to-head evidence, standard-of-care mapping, biomarker/route/convenience comparison, and market-access evidence. |
| Regulatory path | Analyst-normalized score from regulatory review. | POS/regulatory engine outputs: approval pathway, endpoint acceptability, precedent, designations, FDA/EMA meeting outcomes, hold/CRL status, and filing readiness. |
| IP / exclusivity | Analyst-normalized score from diligence. | Patent/exclusivity resolver using patent estate, Orange Book / Purple Book, FTO, litigation, ownership, LOE, and licensed-rights evidence. |
| CMC feasibility | Analyst-normalized score from CMC diligence. | Evidence ingestion from filings, manufacturing disclosures, CDMO dependence, scale-up status, comparability risk, GMP readiness, and tech-transfer facts. |
| Commercial meaningfulness | Analyst-normalized score from market model and commercial review. | Market model, epidemiology, pricing/access engine, competition model, COGS/access checks, and peak-sales/rNPV outputs. |
| Management execution | Analyst-normalized score or management-quality overlay. | Management diligence engine using trial execution, financing behavior, disclosure quality, BD history, governance, and data-integrity signals. |

POS handoff rule: POS does not replace Layer 1A. POS estimates probability of
technical/regulatory success and related scientific risk; Layer 1A converts
those outputs into the buyer-neutral asset-quality dimensions above. In the
future automated path, POS/science/regulatory outputs should pre-populate or
propose `clinical_evidence`, `regulatory_path`, parts of `differentiation`, and
parts of `commercial_meaningfulness`, with source-backed confidence and review
status. Layer 1A remains the asset-quality aggregation layer.

Hard-condition caps:

| Condition | Capped field | Cap |
|---|---|---:|
| `fatal_safety_signal=True` | clinical evidence | 0.20 |
| `pivotal_failure_no_salvage=True` | clinical evidence | 0.25 |
| `no_human_data=True` for clinical-stage asset | clinical evidence | 0.35 |
| `unresolved_clinical_hold=True` | regulatory path | 0.35 |
| `crl_without_credible_fix=True` | regulatory path | 0.40 |
| `active_material_ip_litigation=True` | IP/exclusivity | 0.60 |
| `manufacturing_not_transferable=True` | CMC feasibility | 0.40 |
| `cogs_breaks_commercial_model=True` | commercial meaningfulness | 0.55 |
| `fraud_or_data_integrity_issue=True` | management execution | 0.20 |
| clinical evidence < 0.35 after field caps | asset-quality group | 0.55 |

Boundary: CMC feasibility is target-level transferability. Buyer-specific
manufacturing capability belongs in Layer 3.

## Layer 1B: Strategic Scarcity

**Purpose:** Score whether the asset fills a scarce strategic hole in the market
or treatment landscape.

Strategic scarcity combines TA scarcity, modality/platform scarcity, competitive
position, pipeline-gap relevance, franchise optionality, and replacement
difficulty.

Strategic-scarcity subweight rubric:

| Subweight | Weight | Low score | Neutral score | High score |
|---|---:|---|---|---|
| TA scarcity | 0.25 | Crowded or low-demand therapeutic area. | Some unmet need or deal interest, but not scarce. | Hot TA with high unmet need, deal demand, or patent-cliff relevance. |
| Modality / platform scarcity | 0.20 | Common or easily replicated modality/platform. | Moderately differentiated platform or delivery approach. | Scarce modality, platform, delivery system, or know-how with barriers to entry. |
| Competitive position | 0.20 | Weak treatment role or inferior to current/future SoC. | Plausible but not clearly advantaged position. | Strong current/future treatment role with defensible positioning. |
| Pipeline-gap relevance | 0.15 | Limited relevance to broad industry pipeline gaps. | Relevant to some buyers or segments. | Directly addresses major industry pipeline gaps or revenue-cliff needs. |
| Franchise optionality | 0.10 | One narrow use with limited lifecycle options. | Some follow-on indications or combinations. | Broad indication, lifecycle, combination, or platform expansion potential. |
| Replacement difficulty | 0.10 | Easy to replicate, license around, or substitute. | Replaceable with time or capital. | Hard to recreate because of data, IP, know-how, access, or scarcity. |

Hard-condition caps:

| Condition | Capped field | Cap |
|---|---|---:|
| `clearly_inferior_to_future_soc=True` | competitive position | 0.45 |
| `no_clear_place_in_treatment_algorithm=True` | competitive position | 0.55 |
| `platform_unvalidated_no_clinical_asset=True` | modality/platform scarcity | 0.50 |

Boundary: broad market scarcity is Layer 1. A named buyer's actual pipeline gap
or urgency belongs in Layer 2 / Layer 3.

## Layer 1C: Value Creation

**Purpose:** Score whether the target appears economically attractive after
accounting for rNPV, downside protection, cost to complete, and market
expectations.

Value creation is guarded against value traps. Cheapness can increase
attractiveness only when asset quality is credible.

Value-creation subweight rubric:

| Subweight | Weight | Low score | Neutral score | High score |
|---|---:|---|---|---|
| Premium-adjusted rNPV gap | 0.35 | No upside after expected premium or negative strategic value gap. | Fairly valued or uncertain gap. | Meaningful upside after acquisition premium. |
| Standalone rNPV quality | 0.20 | rNPV depends on fragile assumptions or low-confidence inputs. | Model is usable but materially uncertain. | rNPV is supported by credible clinical, commercial, and cost assumptions. |
| Downside protection | 0.15 | Little residual value if lead thesis fails. | Some cash/platform/pipeline residual value. | Strong net cash, approved product, platform, or fallback asset support. |
| Cost to complete | 0.10 | Large unfunded development burden or high execution cost. | Manageable but material cost remains. | Low or well-funded cost to reach next value inflection. |
| Market expectations gap | 0.10 | Market already prices success or data are stale/illiquid. | Expectations roughly match model. | Market-implied expectations appear too low versus model/evidence. |
| Strategic option value | 0.10 | Limited optionality beyond the lead case. | Some optionality but not central to value. | Meaningful option value from indications, combinations, platform, or structure. |

Value-trap rules:

| Trigger | Treatment |
|---|---|
| `market_data_stale_or_illiquid=True` | `market_expectations_gap` capped at 0.50 |
| asset quality < 0.50 and premium-adjusted rNPV gap > 0.50 | rNPV gap clamped to neutral 0.50 |
| asset quality < 0.50 and market expectations gap > 0.50 | expectations gap clamped to neutral 0.50 |

The output records `value_trap_flags`, most importantly
`cheapness_not_allowed_to_rescue_low_asset_quality`.

## Layer 1D: Transaction Setup

**Purpose:** Score target-level conditions that could create a transaction
window without deciding whether BD should act.

Transaction setup includes financing pressure, catalyst proximity, seller
openness, valuation stress, and prior BD activity.

Transaction-setup subweight rubric:

| Subweight | Weight | Low score | Neutral score | High score |
|---|---:|---|---|---|
| Financing pressure | 0.30 | Well funded, little capital stress. | Moderate runway or future financing need. | Short runway, high burn, going-concern risk, or strong dilution pressure. |
| Catalyst proximity | 0.25 | No material catalyst or catalyst is far away. | Catalyst exists but timing/materiality is uncertain. | Near-term, material clinical/regulatory/financing/BD catalyst. |
| Seller openness | 0.20 | Management/board signals independence or unwillingness. | No clear openness or resistance signal. | Public/process/history signals indicate willingness to partner or transact. |
| Valuation stress | 0.15 | Valuation is stable or premium already embedded. | Some drawdown or EV compression. | Material dislocation versus strategic value, not solely from asset failure. |
| Prior BD activity | 0.10 | No history of partnering or external strategic activity. | Limited or dated BD activity. | Recent partnerships, licenses, options, or strategic outreach signals. |

Seller and stress caps:

| Condition | Capped field | Cap |
|---|---|---:|
| `founder_controlled_no_pressure=True` | seller openness | 0.45 |
| `management_committed_independence_well_funded=True` | seller openness | 0.40 |
| `valuation_stress_due_to_asset_failure=True` | valuation stress | 0.50 |

Boundary: transaction setup is a target-level setup score. Final timing,
watchlist class, and cadence are Layer 2 / Layer 4.

## Layer 1E: Structural Cleanliness

**Purpose:** Preserve residual target-level cleanliness after Layer 0 has already
handled hard rights, IP, economics, diligence, and manufacturing exclusions.

This is intentionally only 5% of Layer 1. It should not double-count Layer 0D-T.
It provides a small quality adjustment for clean rights, clean IP, economic
control, diligence readiness, and manufacturing transferability once the target
has already cleared the target-level gates.

Structural-cleanliness subweight rubric:

| Subweight | Weight | Low score | Neutral score | High score |
|---|---:|---|---|---|
| Rights clarity | 0.30 | Ambiguous, split, or encumbered rights after Layer 0. | Rights mostly understood but require diligence. | Clean global/field/indication rights with clear control. |
| IP cleanliness | 0.25 | Ownership, litigation, FTO, or estate issues remain. | Some uncertainty but no known blocker. | Clean ownership, FTO, litigation posture, and estate documentation. |
| Economic control | 0.20 | Royalty, milestone, profit-share, or cost obligations are complex. | Moderate economic burden or incomplete terms. | Simple economics with buyer-controllable upside. |
| Diligence readiness | 0.15 | Data room, clinical, regulatory, or CMC package is incomplete. | Diligence package usable but incomplete. | Complete, organized, source-backed package ready for diligence. |
| Manufacturing transferability | 0.10 | Process transfer remains uncertain despite Layer 0 pass. | Transfer possible with work. | Transfer package, suppliers, documentation, and process readiness are strong. |

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
| `composite_low_structural_cleanliness` | structural cleanliness < 0.35 | 0.65 |

Runtime output:

| Field | Meaning |
|---|---|
| `raw_score` | Weighted Layer 1 score before composite caps. |
| `capped_score` | Score after all Layer 1 caps. |
| `confidence_adjusted_score` | Capped score multiplied by confidence multiplier. |
| `overall_confidence` | Weighted confidence across subgroups. |
| `active_caps` | Full list of subgroup and composite caps. |
| `layer_ownership_warnings` | Warnings for buyer-specific or downstream signals that should not affect Layer 1. |

Anti-double-counting guardrails:

| Signal | Treatment |
|---|---|
| Hard eligibility exclusion | Layer 0 only. |
| Buyer affordability | Layer 3 only. |
| Buyer integration capability | Layer 3 only. |
| Buyer-specific ROFR / partner impact | Layer 3 only. |
| Buyer-specific antitrust | Layer 3 only. |
| Exact deal structure | Layer 4 only. |
| Calibrated probability | Layer 5 only. |

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

Base scoring rubric:

| Component | Weight | What a low score means | What a neutral score means | What a high score means |
|---|---:|---|---|---|
| Strategic Priority | 0.40 | Target does not matter enough strategically, has weak Layer 1 attractiveness, poor fit, low scarcity, or weak option value. | Strategically relevant, but not clearly urgent or differentiated. | High-quality attractive target with strong fit, scarcity, pipeline-gap relevance, and option value. |
| Deal Momentum | 0.30 | No target pressure, no buyer urgency, no catalyst, and no active transaction drivers. | Some pressure or urgency exists, but the transaction window is uncertain. | Multiple active target-side and buyer-side drivers create a credible near-term BD window. |
| Acquirer Pull | 0.20 | No credible buyer universe or weak fit across likely acquirers. | One or more possible buyers, but pull is shallow or unproven. | Multiple credible acquirers have strong TA/modality/gap fit and appetite. |
| Information Readiness | 0.10 | Stale, missing, or low-confidence evidence makes action unreliable. | Enough information to monitor or diligence, but not fully action-ready. | Fresh, sourced, high-confidence evidence supports BD action. |

Action-score anchors:

| Score range | Interpretation |
|---:|---|
| 0.00-0.30 | Pass or deprioritize; no active BD work justified. |
| 0.31-0.45 | Low priority; monitor only if strategically relevant. |
| 0.46-0.60 | Watch / diligence queue; action depends on missing facts or upcoming catalysts. |
| 0.61-0.75 | High-priority BD diligence or relationship work. |
| 0.76-1.00 | Active pursuit candidate, subject to Layer 3 feasibility. |

## Layer 2A: Strategic Priority

**Purpose:** Decide whether this target matters strategically enough to justify
BD attention.

Layer 2A can auto-populate from `Layer1Output` when available. It blends target
attractiveness with acquirer strategic fit, scarcity, pipeline-gap urgency, and
strategic option value.

Strategic-priority subcomponent rubric:

| Subcomponent | Weight | Low score | Neutral score | High score |
|---|---:|---|---|---|
| Layer 1 attractiveness | 0.35 | Target is fundamentally weak or capped. | Target is plausible but not compelling. | Target is intrinsically attractive. |
| Acquirer strategic fit | 0.25 | Poor TA/modality/franchise fit for likely buyers. | Some plausible fit, but not obvious. | Strong strategic fit for one or more credible acquirers. |
| Strategic scarcity | 0.20 | Replaceable or crowded asset. | Some scarcity. | Scarce and hard to replace. |
| Pipeline-gap urgency | 0.10 | No urgent buyer gap. | Gap exists but timing is unclear. | Clear buyer or industry gap requiring action. |
| Strategic option value | 0.10 | Little strategic optionality. | Some optionality. | High platform, indication, franchise, or structure optionality. |

Subcomponent caps:

| Trigger | Cap |
|---|---:|
| weak asset quality | strategic priority capped at 0.55 |
| weak acquirer strategic fit | strategic priority capped at 0.50 |
| low scarcity and low pipeline-gap urgency | strategic priority capped at 0.60 |

## Layer 2B: Deal Momentum

**Purpose:** Measure whether there is enough target-side and buyer-side pressure
for a transaction window.

Layer 2B builds a transaction-driver ledger. Drivers have weight, strength,
confidence, activation thresholds, source references, freshness, and rationale.

Deal-momentum rubric:

| Driver group | Low score | Neutral score | High score |
|---|---|---|---|
| Target-side pressure | No financing, seller, catalyst, valuation, or governance pressure. | One moderate pressure signal, or signals are stale/uncertain. | Multiple fresh target-side pressures point to a transaction window. |
| Buyer-side urgency | No buyer gap, LOE pressure, FOMO, or recent BD pattern. | Some buyer urgency, but not enough to force action. | Strong buyer urgency from pipeline gaps, revenue cliffs, deal waves, or competitive FOMO. |
| Driver quality | Drivers are weak, stale, unsourced, or below activation thresholds. | Drivers are mixed or partially sourced. | Drivers are fresh, sourced, above threshold, and mutually reinforcing. |

Driver weights:

| Driver | Weight |
|---|---:|
| financing pressure | 1.25 |
| major catalyst | 1.25 |
| seller openness | 1.20 |
| buyer pipeline gap | 1.20 |
| LOE or revenue cliff | 1.10 |
| external deal wave | 1.00 |
| valuation distress | 0.90 |
| activist or governance pressure | 0.90 |
| competitive FOMO | 0.90 |
| scarcity plus fit | 0.80 |
| recent BD pattern | 0.80 |
| existing partnership | 0.70 |

Driver activation thresholds range from 0.40 to 0.55. Recent BD pattern
activates at 0.40, external deal wave at 0.45, most pressure drivers at 0.50,
and scarcity plus fit at 0.55.

Momentum caps:

| Trigger | Cap |
|---|---:|
| no active drivers | deal momentum capped at 0.35 |
| one active driver | deal momentum capped at 0.60 |
| no target-side pressure | deal momentum capped at 0.50 |

## Layer 2C: Acquirer Pull

**Purpose:** Summarize whether one or more acquirers have a credible strategic
reason to pull the target into a BD process.

Layer 2C scores individual acquirers and keeps depth metrics:

Acquirer-pull rubric:

| Signal | Low score | Neutral score | High score |
|---|---|---|---|
| TA fit | Buyer has little or no relevant therapeutic-area footprint. | Adjacent or partial TA fit. | Direct TA franchise or strategic mandate. |
| Modality fit | Buyer lacks capability or appetite for the modality. | Some capability or prior exposure. | Strong modality capability and deal appetite. |
| Pipeline-gap urgency | No clear gap. | Possible gap but timing or priority uncertain. | Clear gap from patent cliff, failed internal program, or strategic white space. |
| Buyer deal appetite | Inactive, constrained, or recently overextended buyer. | Normal activity level. | Active external BD pattern in similar assets. |
| Relationship / FOMO | No relationship or competitive urgency. | Some relationship or market interest. | Existing relationship, partner path, or competitive urgency creates pull. |

| Depth metric | Definition |
|---|---|
| `buyer_universe_depth` | Count of acquirers above the high pull threshold, 0.65. |
| `acquirer_pull_depth` | Count of acquirers above the medium pull threshold, 0.55. |
| `top_acquirers` | Per-acquirer score, confidence, fit subcomponents, source refs, and freshness. |

If no acquirer rows are available, the layer records the mapping gap rather than
pretending neutral pull is a real signal.

## Layer 2D: Information Readiness

**Purpose:** Decide whether the BD priority output is supported by enough fresh
evidence to act.

Information readiness combines Layer 1 confidence, acquirer-profile freshness,
transaction-driver source quality, valuation-data freshness,
rights-encumbrance clarity, and catalyst-date confidence.

Missing or stale information lowers confidence and can route otherwise
interesting names to diligence queue instead of active pursuit.

Information-readiness rubric:

| Input | Low score | Neutral score | High score |
|---|---|---|---|
| Layer 1 confidence | Many missing or low-confidence target facts. | Some gaps remain. | Target attractiveness is supported by fresh, sourced facts. |
| Acquirer-profile freshness | Buyer profile is stale or manually sparse. | Profile is usable but not current. | Profile is recent and source-backed. |
| Transaction-driver source quality | Drivers are unsourced, stale, or speculative. | Drivers have partial support. | Drivers have high-quality source refs and freshness. |
| Valuation data freshness | Market/valuation inputs are stale or missing. | Some current data, some gaps. | Current market, EV, rNPV, and expectations inputs. |
| Rights/catalyst clarity | Rights/catalyst details are unclear. | Main facts known, details missing. | Rights and catalyst timing are source-backed and auditable. |

Caps:

| Trigger | Cap |
|---|---:|
| Strategic Priority < 0.40 | 0.50 |
| Deal Momentum < 0.30 | 0.65 |
| Acquirer Pull < 0.35 | 0.55 |
| Information Readiness < 0.40 | 0.60 |

Action classifications:

| Action class | Priority condition |
|---|---|
| Distress Trap Warning | financing pressure >= 0.70, valuation distress >= 0.65, asset quality < 0.50 |
| Active Pursuit Candidate | strategic priority >= 0.75, deal momentum >= 0.65, acquirer pull >= 0.65, information readiness >= 0.60 |
| High-Priority BD Diligence | strategic priority >= 0.70, acquirer pull >= 0.60, information readiness < 0.60 |
| Catalyst Watch | catalyst timing >= 0.70, strategic priority >= 0.55, deal momentum between 0.45 and 0.70 |
| Diligence Queue | information readiness < 0.50 and BD score >= 0.45 |
| Strategic Watch | strategic priority >= 0.70 and deal momentum < 0.45 |
| Relationship Build | strategic priority >= 0.65, acquirer pull >= 0.60, deal momentum < 0.50, weak existing relationship |
| Acquirer Mapping Needed | strategic priority >= 0.60 and acquirer pull < 0.45 |
| Low Priority / Pass | BD score < 0.45 |

Timing windows:

| Trigger | Window |
|---|---|
| information readiness < 0.40 | uncertain |
| distress trap warning | 0-6 months |
| financing pressure >= 0.70 and catalyst timing >= 0.70 | 0-6 months |
| catalyst timing >= 0.55 and deal momentum >= 0.60 | 6-18 months |
| strategic priority >= 0.70 and deal momentum < 0.45 | strategic watch only |
| strategic priority >= 0.55 and deal momentum >= 0.45 | 18-36 months |

Runtime output:

| Field | Meaning |
|---|---|
| `raw_bd_action_score` | Weighted score before final caps. |
| `capped_bd_action_score` | Score after Layer 2 caps. |
| `confidence_adjusted_score` | Capped score multiplied by confidence multiplier. |
| `strategic_priority`, `deal_momentum`, `acquirer_pull`, `information_readiness` | Rich subgroup outputs with subcomponents, confidence, and diagnostics. |
| `transaction_drivers` | Active and inactive driver ledger. |
| `action_classification` | Priority-ordered BD action class. |
| `estimated_timing_window` | High-level action timing. |
| `upgrade_triggers`, `downgrade_triggers` | Event hooks that would move priority. |
| `active_caps` | Subgroup and final caps. |
| `preliminary_friction_warnings` | Non-blocking early warnings handed to Layer 3. |

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

Base scoring rubric:

| Component | Weight | What a low score means | What a neutral score means | What a high score means |
|---|---:|---|---|---|
| Affordability | 0.20 | Buyer cannot realistically fund the deal at expected cost. | Deal is fundable only with meaningful structure, dilution, debt, or staged economics. | Deal is comfortably fundable with cash, debt, stock, or normal mix. |
| Consideration realism | 0.15 | The available currency or package is unacceptable to one or both shareholder bases. | A workable package may exist, but requires CVR, milestones, tax structuring, or negotiation. | Cash/stock/CVR mix is commercially plausible and precedent-consistent. |
| Rights/control fit | 0.20 | ROFR, consent, regional rights, exclusivity, or partner constraints impair this buyer. | Some friction exists, but may be structured around. | Buyer can obtain the needed control or rights cleanly. |
| Integration capability | 0.15 | Buyer is poorly equipped for the target's manufacturing, commercial, payer, geographic, or systems complexity. | Buyer can integrate with work or external support. | Buyer has strong capabilities that offset the target complexity. |
| Antitrust feasibility | 0.15 | Pair has severe overlap, concentration, or required divestiture that destroys deal logic. | Review risk exists but appears manageable. | Low antitrust risk or straightforward remedy path. |
| Strategic conflict | 0.10 | Ownership conflicts with buyer products, pipeline, pricing, partners, or organization. | Some conflict exists, but strategic rationale may outweigh it. | Target fits buyer strategy without meaningful cannibalization or partner conflict. |
| Process closing | 0.05 | Board, shareholder, financing, diligence, litigation, or timing friction threatens closing. | Closing process is plausible but not clean. | Closing path is straightforward and execution-ready. |

Pair-feasibility anchors:

| Score range | Interpretation |
|---:|---|
| 0.00-0.39 | Poor pair; severe cap or hard fail likely. |
| 0.40-0.54 | Weak pair; executable only with major structuring. |
| 0.55-0.69 | Workable pair with meaningful friction. |
| 0.70-0.84 | Strong pair with manageable friction. |
| 0.85-1.00 | Highly executable pair. |

Layer 3 confidence:

```text
overall_confidence =
    weighted confidence across affordability, consideration realism,
    rights/control fit, integration, antitrust, strategic conflict,
    and process closing
```

Missing pair facts normally reduce confidence. They become hard blockers only
when the missing fact prevents a meaningful pair calculation, such as missing
target EV for affordability. Hard failures are explicit and set adjusted BD
score to zero.

Runtime output:

| Field | Meaning |
|---|---|
| `pair_feasibility_score` | Diagnostic weighted pair score. |
| `pair_feasibility_multiplier` | Multiplier applied to upstream Layer 2 score. |
| `pair_level_cap` | Maximum allowed adjusted score after pair constraints. |
| `adjusted_bd_score` | Layer 2 score after pair realism multiplier and cap. |
| `hard_fail` | Whether the pair is non-executable. |
| `hard_fail_reasons` | Fatal pair blockers. |
| `remediation_paths` | Possible ways to improve feasibility, such as option structure or alternative consideration. |
| `positive_drivers`, `negative_drivers` | Explainability labels. |
| `data_gaps` | Pair diligence gaps. |

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

Affordability rubric:

| Evidence | Low score | Neutral score | High score |
|---|---|---|---|
| Deal capacity | Expected cost exceeds realistic cash/debt/stock capacity. | Deal can work only with meaningful structuring or stretch financing. | Expected cost is comfortably inside realistic capacity. |
| Stock quality | Stock is volatile, low-multiple, or dilution-sensitive. | Stock can support limited issuance. | Stock is strong, stable, and usable as deal currency. |
| Balance-sheet flexibility | Buyer has limited cash/debt capacity after buffer. | Some flexibility. | Strong cash, debt capacity, or financing flexibility. |

Layer 3 mapping:

- no penalty: diagnostic score around 0.90,
- mild penalty: score around 0.65 and possible cap around 0.80,
- severe penalty: score around 0.35 and cap around 0.60,
- hard fail: pair fail.

Missing EV should be treated as a data gap, not as a universal target failure.

Remediation paths:

| Band | Typical remediation |
|---|---|
| `MILD_PENALTY` | optimize cash/stock mix or stage payment structure |
| `SEVERE_PENALTY` | use option-to-acquire, CVR, structured milestone, or syndicate economics |
| `HARD_FAIL` | remove buyer from active pair list or test non-control structure |

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

Consideration-realism rubric:

| Subcomponent | Low score | Neutral score | High score |
|---|---|---|---|
| Cash/stock mix feasibility | Likely mix is unacceptable or infeasible. | Mix can work with negotiation. | Mix is normal for both parties and financing context. |
| Target shareholder acceptability | Consideration undervalues target or uses unacceptable currency. | Acceptability depends on terms. | Consideration is credible and attractive to target holders. |
| Acquirer shareholder acceptability | Dilution, leverage, or strategic logic likely faces pushback. | Shareholder reaction is uncertain. | Deal terms are defensible to acquirer holders. |
| CVR/milestone suitability | Uncertainty cannot be cleanly structured. | CVR/milestone can help but adds complexity. | CVR/milestone naturally matches the risk profile. |
| Tax / precedent consistency | Structure is tax-inefficient or unusual. | Some complexity. | Structure is tax/practice/precedent-consistent. |

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

Route sensitivity: the pair-control helper changes weights by deal structure.
Full-company takeout emphasizes global rights, change-of-control freedom, and
blocking rights. Licensing routes emphasize geography, field-of-use, economics,
and partner governance. Distressed optionality gives more weight to whether
rights can actually be separated or restructured.

Rights/control pair-fit rubric:

| Signal | Low score | Neutral score | High score |
|---|---|---|---|
| Control path | Buyer cannot obtain required control without ROFR, consent, or partner blocker. | Control path exists but requires negotiation or structure. | Buyer can obtain needed control cleanly. |
| Geography / field fit | Rights scope mismatches buyer strategy. | Partial geography or field fit. | Rights align with buyer's intended territory, field, and route. |
| Partner impact | Existing partner creates blocking or value leakage. | Partner can be managed but adds friction. | Partner status helps or does not impair this buyer. |
| Manufacturing fit | Target process conflicts with buyer capability. | Buyer can manage transfer with work. | Buyer capability strongly fits the target process. |

## Layer 3D: Integration Capability

**Purpose:** Offset target integration complexity by the specific acquirer’s
commercial, manufacturing, payer, geography, systems, and prior-integration
capability.

Primary file: `src/bve/intelligence/ma_integration_complexity.py`.

Layer 3D applies the buyer capability adjustment described in Layer 0E. The
target raw complexity is multiplied by `1 - buyer_integration_capability`.

Integration-capability rubric:

| Capability | Low score | Neutral score | High score |
|---|---|---|---|
| Commercial capability | Buyer lacks commercial footprint/channel. | Buyer can build or partner. | Buyer has strong relevant commercial infrastructure. |
| Manufacturing capability | Buyer lacks process capability or capacity. | Capability exists but needs tech-transfer work. | Buyer has proven relevant manufacturing capability. |
| Payer/access capability | Buyer lacks access infrastructure. | Some payer/access capability. | Strong payer, channel, and pricing capability. |
| Geographic/systems capability | Buyer lacks geography or integration systems. | Integration is manageable. | Buyer has demonstrated cross-border and systems integration strength. |

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

Antitrust-feasibility rubric:

| Subcomponent | Low score | Neutral score | High score |
|---|---|---|---|
| Current product overlap | High overlap in marketed products. | Some overlap, likely manageable. | Little or no marketed-product overlap. |
| Pipeline overlap | Direct pipeline substitute or innovation competition concern. | Related pipeline but manageable. | Pipeline overlap is low or complementary. |
| Market concentration | Deal materially increases concentration. | Concentration concerns need review. | Market remains unconcentrated. |
| Divestiture / jurisdiction | Remedy destroys deal logic or multi-jurisdictional risk is severe. | Remedy or filing risk exists. | Straightforward filing path and remedies, if any. |

## Layer 3F: Strategic Conflict

**Purpose:** Score whether the target fits the buyer's internal strategy after
distinguishing complementary overlap, defensive/franchise-protective overlap,
and value-destructive cannibalization.

```text
strategic_conflict =
    0.25 * portfolio_overlap_fit
  + 0.20 * defensive_franchise_rationale
  + 0.15 * cannibalization_severity_inverse
  + 0.15 * channel_conflict
  + 0.10 * partner_conflict
  + 0.10 * pricing_contracting_conflict
  + 0.05 * organizational_conflict
```

Portfolio overlap is not automatically bad. A next-generation asset can be
strategically attractive if it lets the buyer defend a franchise, manage a
transition before loss of exclusivity, prevent a competitor from controlling the
asset, or move patients to a better product. It is a conflict only when owning
the target would destroy more value than it protects or creates.

Strategic-conflict rubric:

| Conflict | Low score | Neutral score | High score |
|---|---|---|---|
| Portfolio overlap fit | Target directly undermines buyer's existing product or pipeline without a transition rationale. | Overlap exists, but the strategic impact is mixed. | Target is complementary or creates a credible franchise-transition path. |
| Defensive franchise rationale | Buyer has little reason to control the asset. | Defensive logic exists but is uncertain. | Buying the target protects a franchise, fills a future gap, or prevents a competitor from controlling disruption. |
| Cannibalization severity inverse | Target would accelerate erosion, reset pricing lower, or destroy margin without offsetting value. | Cannibalization is manageable or staged. | Cannibalization risk is low, delayed, or outweighed by franchise protection. |
| Channel/pricing conflict | Target conflicts with buyer channel, payer, or contracting strategy. | Conflict requires management. | Target fits buyer channel and pricing model. |
| Partner conflict | Existing partner obligations conflict with buyer strategy. | Partner conflict is manageable. | No meaningful partner conflict. |
| Organizational conflict | Ownership creates internal strategic or operating friction. | Some operating friction. | Buyer organization can absorb and champion the asset. |

Interpretation:

| Overlap type | Treatment |
|---|---|
| Complementary overlap | Positive strategic fit; no conflict penalty. |
| Defensive / franchise-protective overlap | Can support acquisition if protected value exceeds cannibalization cost. |
| Value-destructive cannibalization | Penalize or cap when the target damages buyer economics without enough defensive or transition value. |

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

Process/closing rubric:

| Subcomponent | Low score | Neutral score | High score |
|---|---|---|---|
| Board/shareholder alignment | Board or shareholders likely resist. | Approval path is uncertain. | Board and shareholders are likely receptive. |
| Management retention | Key personnel likely leave or block transition. | Retention requires incentives. | Retention or transition plan is credible. |
| Financing/process readiness | Financing or process preparation is weak. | Process can proceed with work. | Financing, diligence, and process steps are ready. |
| Cross-border/timeline/litigation | Execution timeline or litigation risk is severe. | Some timing or legal friction. | Closing timeline is realistic and litigation risk low. |

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

Diligence-blocker rubric:

| Result | Meaning | Treatment |
|---|---|---|
| No blocker | No pair-specific fatal issue identified. | Continue using pair-feasibility score. |
| Remediable blocker | Issue blocks current route but may be solved with structure, consent, option, divestiture, or alternative buyer. | Cap pair score and create remediation path. |
| Fatal blocker | Issue makes this buyer-target pair non-executable. | Set adjusted BD score to zero for this pair. |

The important boundary is that Layer 3 is pair-specific. A target can be
attractive in Layer 1 and high priority in Layer 2 while failing Layer 3 for a
particular acquirer because of affordability, antitrust, rights, or process
constraints.

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

Base routing rubric:

| Watchlist class | Typical score/evidence profile | Operating meaning |
|---|---|---|
| `pass` | Low asset quality, weak strategic fit, or poor deal feasibility. | Do not allocate BD time unless a major new event changes the setup. |
| `data_insufficient` | Potentially interesting but data confidence is too low. | Fill evidence gaps before assigning a stronger class. |
| `strategic_radar` | Strategically relevant but low transaction readiness. | Track periodically; no near-term outreach required. |
| `relationship_build` | Strong strategic rationale but seller/process readiness is weak. | Build relationship and monitor openness. |
| `catalyst_watch` | Adequate quality/fit with a defined catalyst that can change actionability. | Monitor tightly around readout, regulatory, financing, or BD events. |
| `active_pursuit` | Strong priority and momentum with adequate feasibility. | Begin active diligence or outreach. |
| `process_ready` | Strong strategic priority, seller willingness, transaction readiness, and pair feasibility. | Candidate is actionable now. |

Routing-score anchors:

| Score/evidence range | Interpretation |
|---|---|
| Fails hard gate | `pass`. |
| Data confidence below minimum | `data_insufficient`. |
| Strategic but transaction readiness < 0.40 | `strategic_radar`. |
| Strategic priority strong but seller willingness low | `relationship_build`. |
| Catalyst timing high and asset/fit adequate | `catalyst_watch`. |
| Strategic priority, transaction readiness, and drivers high | `active_pursuit`. |
| Active-pursuit profile plus stronger seller willingness and feasibility | `process_ready`. |

Classification gates:

| Gate | Threshold |
|---|---:|
| Pass hard gate: asset quality minimum | 0.35 |
| Pass hard gate: strategic fit minimum | 0.35 |
| Pass hard gate: deal feasibility minimum | 0.30 |
| Data confidence minimum for classification | 0.60 |
| Process ready: strategic priority | >= 0.75 |
| Process ready: transaction readiness | >= 0.70 |
| Process ready: seller willingness | >= 0.60 |
| Process ready: deal feasibility | >= 0.60 |
| Active pursuit: strategic priority | >= 0.70 |
| Active pursuit: transaction readiness | >= 0.60 |
| Active pursuit: seller willingness | >= 0.40 |
| Active pursuit: active driver buckets | >= 2 |
| Catalyst watch: asset quality | >= 0.55 |
| Catalyst watch: strategic fit | >= 0.60 |
| Relationship build: strategic priority | >= 0.70 |
| Relationship build: seller willingness | < 0.40 |
| Relationship build: transaction readiness | 0.35-0.55 |
| Strategic radar: strategic priority | >= 0.65 |
| Strategic radar: transaction readiness | < 0.40 |

The classifier uses first-match priority. A process-ready target is classified
before active pursuit. Pass and data-insufficient checks run before any positive
class.

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

Deal-structure rubric:

| Structure family | Low-fit evidence | Better-fit evidence |
|---|---|---|
| Full acquisition | Rights, affordability, uncertainty, or integration complexity makes control inefficient. | Clean rights/control, strong asset quality, high strategic fit, and feasible pair economics. |
| Asset/license route | Full-company control is unnecessary or inefficient. | Asset-specific value, rights scope, or economics support licensing. |
| Option route | Asset is too uncertain for immediate control. | Defined catalyst can de-risk the asset and justify option economics. |
| Co-development / collaboration | Buyer cannot or should not take full risk alone. | Shared capabilities, risk sharing, or platform learning are strategically useful. |
| Regional rights | Global ownership is unnecessary or rights are split. | Buyer has region-specific capability or rights fit. |
| Minority equity | Control is premature or seller is not open. | Relationship-building and alignment have strategic value. |
| Monitor only | Evidence, fit, or feasibility does not support action. | Used when tracking is more appropriate than engagement. |

Deal-structure selection thresholds:

| Structure | Trigger |
|---|---|
| `monitor_only` | pass or data-insufficient class |
| `regional_rights` | asset control < 0.50 |
| `full_acquisition` | asset quality >= 0.70 and transaction readiness >= 0.65 |
| `option_to_acquire` | asset quality >= 0.65 and de-risking stage < 0.55 |
| `asset_license` | strategic fit >= 0.65 and deal feasibility < 0.50 |
| `research_collaboration` | strategic fit >= 0.60 and de-risking stage < 0.35 |
| `minority_equity` | relationship-build class |
| `co_development` | fallback when asset quality >= 0.55 and strategic fit >= 0.55 |

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

Persistence logic:

```text
if prior_classification is missing:
    accept candidate class
elif candidate == prior:
    accept candidate class
elif major_event_override:
    accept candidate class
elif consecutive_new_class_signals >= 2:
    accept candidate class
else:
    hold prior class and set classification_suppressed=True
```

Runtime output:

| Field | Meaning |
|---|---|
| `watchlist_class` | Seven-tier BD class. |
| `recommended_bd_action` | Imperative action string for BD. |
| `recommended_structure` | Deal structure selected by Layer 4. |
| `time_horizon` | Expected action window. |
| `review_cadence` | Revisit cadence. |
| `promotion_trigger`, `demotion_trigger` | Class-specific events to move the target. |
| `confidence_level` | `high`, `medium`, `low`, or `insufficient`. |
| `owner_next_step` | First operational step for BD owner. |
| `reason_codes` | Machine-readable classification reasons. |
| `candidate_class` and `classification_suppressed` | Persistence/churn audit fields. |
| `primary_deal_type`, `secondary_deal_types`, `recommended_model` | Optional Layer 0B deal-type passthrough. |
| `diagnostic_deal_type_score_ceiling` | Memo-only overlay, capped at final score and unable to increase live score. |
| `final_score_with_structure_bonus` | Only populated when residual bonus is explicitly enabled. |

Confidence:

| Data confidence | Layer 4 confidence |
|---:|---|
| class is `data_insufficient` | insufficient |
| >= 0.85 | high |
| >= 0.70 | medium |
| < 0.70 | low |

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

Layer 5 preserves the Layer 3 rank score as the ordering signal. Probability is
an interpretive overlay, with source tags and confidence controls so users can
see whether a number is fitted, fallback, derived, or stage-adjusted.

Layer 5 input sources:

| Source layer | Inputs |
|---|---|
| Layer 1 | asset quality, seller willingness |
| Layer 2 | strategic priority, transaction readiness |
| Layer 3 | post-gate rank score, percentile, active drivers, gate IDs, positive/negative drivers |
| Layer 4 | watchlist class, data confidence, promotion triggers, data gaps |
| Calibration data | base rate, comparable bucket rate, comparable N, optional logistic probability |

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

Base calibration rubric:

| Input/result | Low meaning | Neutral meaning | High meaning |
|---|---|---|---|
| Rank score | Weak ordering signal after Layer 3 gates. | Middle-of-pack candidate; probability depends heavily on cohort/base rate. | Strong ordering signal; top candidate within relevant cohort. |
| Comparable N | Sparse sample; heavy shrinkage to base rate. | Some comparable evidence, but not enough for high confidence. | Enough comparable cases to trust bucket behavior more. |
| Data confidence | Output should avoid false precision and emphasize gaps. | Probability can be shown as a range with caution. | Probability language can be more specific. |
| Watchlist class | `pass` or `data_insufficient` suppresses probability confidence. | Watch/radar classes remain low-to-moderate unless cohort data says otherwise. | Process-ready or active-pursuit classes can support higher probability bands. |
| Close feasibility | Encumbrance, antitrust, or seller uncertainty materially reduces effective close probability. | Close feasibility uncertain; show wider range. | Clean close path supports the strategic transaction probability. |

Probability interpretation rubric:

| Probability band | How to read it |
|---|---|
| very low | Background-rate or weak candidate; do not treat as actionable M&A probability. |
| low | Some signal exists, but probability remains modest and highly uncertain. |
| moderate | Meaningful M&A setup; useful for watchlist/action prioritization. |
| high | Strong, rare setup; requires careful diligence and calibration support. |
| exceptional / requires manual review | Very rare output; should be reviewed for overfitting, lookahead, or exceptional factual setup. |

Confidence thresholds:

| Conditions | Confidence |
|---|---|
| data confidence >= 0.85 and comparable N >= 20 | high |
| data confidence >= 0.65 and comparable N >= 10 | medium |
| data confidence >= 0.50 | low |
| data confidence < 0.50 or excluded class | very low |

Low-confidence modifiers:

| Trigger | Treatment |
|---|---|
| watchlist class is `pass` or `data_insufficient` | confidence very low |
| fitted calibration params missing | confidence capped to very low |
| comparable bucket rate source is fallback | confidence capped to low |
| seller willingness anchor is `UNKNOWN` | confidence degraded one tier |
| deal encumbrance is `UNKNOWN` | confidence degraded one tier |
| antitrust risk is `UNKNOWN` | confidence degraded one tier |

Probability ranges:

Layer 5 always produces `probability_range_low` and
`probability_range_high`. The displayed probability string depends on
confidence: high confidence can show a point estimate plus range, medium shows
point estimate with wider range, low shows band/range emphasis, and very-low
confidence suppresses false precision.

Calibration cohorts:

| Watchlist class | Cohort |
|---|---|
| `process_ready` | High-readiness targets |
| `active_pursuit` | Active-setup targets |
| `catalyst_watch` | Catalyst-driven targets |
| `relationship_build` | Relationship-stage targets |
| `strategic_radar` | Strategic-radar targets |
| `data_insufficient` | Excluded from calibrated output |
| `pass` | Excluded from calibration |

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

Catalyst-hazard rubric:

| Evidence | Low / back-loaded | Neutral | High / front-loaded |
|---|---|---|---|
| Catalyst timing | No catalyst or >365 days away. | Catalyst exists but timing is moderate or uncertain. | Catalyst is within 90-180 days. |
| Catalyst materiality | Routine update or low-information event. | Meaningful but not binary catalyst. | Phase 3, regulatory, financing, or other value-defining catalyst. |
| Schedule confidence | Date is unknown or unreliable. | Date is estimated. | Date is source-backed and current. |

Hazard outputs:

```text
p_takeout_6m = p_any_strategic_transaction_12m * scale_6m
p_takeout_18m = 1 - (1 - p_any_strategic_transaction_12m) ^ exponent_18m
```

Layer 5 records `timing_shape`, `timing_rationale`, `scale_6m_applied`, and
`scale_18m_exponent_applied` so the timing transform is auditable.

## Seller Willingness

| Seller willingness | Multiplier |
|---|---:|
| `ACTIVELY_SEEKING` | 0.90 |
| `OPEN` | 0.70 |
| `NEUTRAL` | 0.50 |
| `RELUCTANT` | 0.30 |
| `HOSTILE` | 0.10 |
| `UNKNOWN` | 0.50, with lower confidence |

Seller-willingness rubric:

| Anchor | Meaning |
|---|---|
| `ACTIVELY_SEEKING` | Company has explicit process, strategic review, banker, sale mandate, or urgent partner search. |
| `OPEN` | Management history, comments, financing needs, or BD behavior indicate openness. |
| `NEUTRAL` | No strong open or resistant signal. |
| `RELUCTANT` | Management emphasizes independence or has little pressure. |
| `HOSTILE` | Board/founder/control structure or public posture strongly resists a transaction. |
| `UNKNOWN` | Evidence is insufficient; use neutral multiplier with confidence penalty. |

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

Close-probability adjustment rubric:

| Factor | Low close probability | Neutral | High close probability |
|---|---|---|---|
| Encumbrance | ROFR, option, consent, or partner rights can redirect or block closing. | Encumbrance status unknown or manageable. | No material encumbrance. |
| Antitrust | Blocked/high overlap or hostile regime. | Medium review risk or uncertain overlap. | Low overlap and manageable regime. |
| Jurisdiction | Multi-jurisdictional path is complex. | Standard filing path. | Simple or permissive review path. |

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

Stage-prior rubric:

| Stage profile | Acquisition prior meaning | License / partnership prior meaning |
|---|---|---|
| Early-stage / platform-heavy | Full acquisition is less common because uncertainty is high. | Partnership, option, research collaboration, or license structures dominate. |
| Mid-stage proof-of-concept | Acquisition becomes more plausible as data improves. | Licensing remains common when risk, rights, or cost sharing matter. |
| Late-stage / registrational | Full acquisition share rises because asset risk is lower and control matters. | Licensing remains relevant for rights splits, affordability, or regional strategy. |
| Approved / commercial | Acquisition prior is highest because revenue/control value is clearer. | Partnership share falls unless commercial rights or geography are split. |

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

Probability source tags:

| Output | Source tag behavior |
|---|---|
| `p_any_strategic_transaction_12m` | `CALIBRATED` when fitted params load; otherwise `FALLBACK` |
| `p_full_acquisition_12m` | `DERIVED` or `DERIVED_STAGE_ADJUSTED` |
| `p_license_or_partner_12m` | `DERIVED` or `DERIVED_STAGE_ADJUSTED` |
| `p_takeout_6m` | `DERIVED` from 12-month p_any |
| `p_takeout_18m` | `DERIVED` from 12-month p_any |

Rank-vs-probability divergence:

| Divergence | Trigger |
|---|---|
| high rank / low probability | rank percentile >= 0.85 and calibrated probability < 0.10 |
| low rank / high probability | rank percentile < 0.50 and calibrated probability > 0.25 |

Gate-to-driver translation:

Layer 5 converts gate IDs into plain-English negative drivers.

| Gate | Meaning |
|---|---|
| `G1` | Broken asset - clinical quality below acceptance threshold |
| `G2` | No right-to-win - acquirer strategic fit insufficient |
| `G3` | No transaction rationale - zero active driver buckets |
| `G4` | Weak transaction setup - insufficient driver strength |
| `G5` | Seller not ready - no active engagement or process signal |
| `G6` | Capital pressure without quality - distress alone is not a deal thesis |
| `G7` | Encumbrance - rights or control issues block full acquisition |
| `G8` | Deal feasibility - affordability, antitrust, or integration risk |

Runtime output:

| Field | Meaning |
|---|---|
| `rank_score` | Primary rank signal, unchanged from Layer 3. |
| `p_takeout_12m`, `p_takeout_6m`, `p_takeout_18m` | Backward-compatible takeout outputs. |
| `p_any_strategic_transaction_12m` | Primary calibrated strategic-transaction output. |
| `p_full_acquisition_12m`, `p_license_or_partner_12m` | Stage/type split outputs. |
| `p_effective_close_12m` | Strategic transaction probability after encumbrance and antitrust close multipliers. |
| `probability_band`, `probability_range_low`, `probability_range_high` | Probability display controls. |
| `confidence_level` | high / medium / low / very low. |
| `calibration_cohort` | Comparable historical bucket. |
| `top_positive_drivers`, `top_negative_drivers` | Explainability strings. |
| `what_would_change_score` | Promotion events from upstream layers. |
| `data_gaps` | Confidence-reducing diligence gaps. |
| `rank_probability_divergence_flag` | Rank/probability disagreement diagnostic. |
| `calibration_fitted`, `calibration_params_source`, `calibration_warning` | Calibration truthfulness audit. |
| `seller_willingness_flag`, `bucket_rate_warning` | Additional confidence/audit warnings. |

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
