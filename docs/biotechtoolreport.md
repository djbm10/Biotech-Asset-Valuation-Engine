Asset Valuation

Drug Asset
   │
   ▼
     [1] 
             POS MODEL
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
 Layer 1: Evidence Strength              Layer 2: Evidence Credibility
 "Is the drug promising?"                "Can the evidence support approval?"
          │                                       │
          ├─ Endpoint strength                    ├─ Trial design
          ├─ MoA precedent                        ├─ Comparator quality
          ├─ Prior-phase data                     ├─ Regulatory pathway
          ├─ Safety profile                       └─ Phase-specific scaling
          ├─ Biomarker selection
          └─ Sample size / power
          │                                       │
          └───────────────────┬───────────────────┘
                              ▼
                    Adjusted Probability of Success

Cumulative probability of approval 
   │
   ▼
[2] Revenue Forecast
│
▼
Define addressable market
│
├─ Eligible patients
├─ Diagnosis rate
├─ Treatment rate
├─ Line of therapy
└─ Geography
│
▼
Apply commercial assumptions
│
├─ Net price
├─ Gross-to-net discount
├─ Uptake curve
├─ Years to peak sales
├─ Launch archetype
└─ Payer access
│
▼
Apply competitive pressure
│
├─ Current standard of care
├─ Approved competitors
├─ Pipeline competitors
├─ Market share erosion
└─ Price erosion
│
▼
Revenue by year
│
▼
Subtract COGS + SG&A
│
▼
EBIT by year 
   │
   ▼
[3] Development Cost Model
│
├─────────────────────────────┐
│ │
▼ ▼
Clinical Trial Costs CMC / Manufacturing
│ │
├─ Phase 1 ├─ API development
├─ Phase 2 ├─ Formulation
├─ Phase 3 ├─ Scale-up
└─ NDA/BLA └─ Regulatory CMC
│ │
└───────────────┬─────────────┘
▼
Deal-Related Costs
│
├─ Upfront payments
├─ Payable milestones
├─ Co-development share
└─ Post-approval obligations
│
▼
Probability-weight + discount to today
│
▼
Total PV of Remaining Development Costs 
   │
   ▼
[4] rNPV Engine
   │
Projected Revenue
│
▼
EBIT
│
├─ subtract royalties
├─ subtract profit share
├─ subtract taxes
├─ subtract capex
└─ subtract working capital
│
▼
Free Cash Flow
│
▼
Discount to present value
│
▼
Multiply by probability of approval
│
▼
Risk-adjusted commercial value
│
▼
Subtract probability-weighted development costs
│
▼
Add receivable milestones / upfront receipts
│
▼
rNPV 
   │
   ▼
[5] Scenario Base Case Assumptions
│
▼
Shock key assumptions
│
├─ Clinical
├─ Regulatory
├─ Commercial
├─ Competition
├─ Costs / FCF
└─ Deal economics
│
▼
Run full valuation engine again
│
▼
Compare against base case
│
├─ rNPV change
├─ NAV/share change
├─ POS change
├─ Main value drivers
└─ Kill criteria triggered?
│
▼
Bull / Base / Bear Interpretation 
   │
   ▼
[6] Monte Carlo
   │
   ▼
Run thousands of simulations
│
▼
Each simulation randomly varies:
│
├─ Clinical success
├─ Approval timing
├─ Label breadth
├─ Patient population
├─ Net price
├─ Peak penetration
├─ Payer access
├─ Competition
├─ R&D costs
├─ Margins
├─ Tax rate
└─ WACC
│
▼
Each simulation reruns full rNPV engine
│
▼
Create distribution of possible values
│
├─ P5 downside case
├─ P50 median case
├─ P95 upside case
├─ Mean rNPV
├─ Downside value at risk
└─ Probability NAV > EV
│
▼
Risk / reward profile 
   │
   ▼
[7] Variant Perception Back-Solve
   │
   Current Market Valuation
│
▼
Company EV
│
├─ subtract net cash adjustment
├─ subtract other pipeline value
├─ subtract platform value
├─ subtract royalty streams
└─ subtract non-core value
│
▼
Asset-implied EV
│
▼
Compare to model's full-success value
│
▼
Back-solve what market is assuming
│
├─ Implied probability of approval
├─ Implied peak sales
├─ Implied penetration
├─ Implied price
└─ Implied patient population
│
▼
Model vs Market Gap
│
▼
Classify disagreement:
│
├─ Clinical
├─ Commercial
├─ Pricing
├─ Mixed
├─ Allocation-driven
└─ Indeterminate 


Sensitivity / Tornado Analysis 








M&A Probability Scanner
Layer 0 — Targetability Pre-Filters
Layer 0 decides whether a company should enter the M&A scanner and how it should be routed.
It does not assign a final M&A probability. It only determines:
Whether the company is eligible.
What type of deal model applies.
Whether target-level structural caps or flags apply.
Whether the company should be routed to diligence instead of ranked output.
Which buyer-specific checks must happen later in Layer 3.

0G. Data Confidence Output
Purpose:
Measure how much the model should trust its own M&A score.

Each target receives a data-confidence score based on both:
1. data completeness
2. data reliability / freshness
Inputs
Category
Examples
Market / valuation data
Market cap, enterprise value, share price, liquidity
Financial data
Cash, debt, quarterly burn, runway
Asset data
Lead asset, stage, trial status, clinical data, regulatory path
Commercial data
Revenue mix, approved products, LOE timing, payer exposure
Rights / ownership data
Partner rights, royalties, ROFR, regional splits, patent/IP status
Acquirer data
Acquirer profile freshness, TA priorities, deal capacity, recent deals
Source quality
SEC filing, 10-K, 8-K, press release, trial registry, investor deck, manual note
Freshness
How recently the data was updated

Formula
data_confidence_score =
0.30 × financial_data_confidence
+ 0.25 × asset_data_confidence
+ 0.20 × rights_ip_data_confidence
+ 0.15 × market_data_confidence
+ 0.10 × acquirer_profile_confidence
Treatment
Confidence score
Label
Treatment
≥0.80
High
Eligible for ranked output
0.60–0.79
Medium
Eligible but flagged
0.40–0.59
Low
Diligence queue by default
<0.40
Very low
Exclude from ranking

Other rule: If rights/IP data is missing or low confidence:
   cannot rank above Medium confidence


0A. Hard Exclusion Rules

Gate
Question
Possible output
0. Entity validity
Is this actually an operating biotech/pharma/life-science company?
Hard fail / pass
1. Standalone status
Is it still independently acquirable?
Hard fail / historical-only
2. Target Level eligibility
Is the target valid before pairing it with any acquirer?
Hard fail / pass
3. Asset visibility
Can we identify the asset, platform, pipeline, or product that drives value?
Hard fail / diligence queue
4. Asset viability
Is the lead value driver still alive and clinically/regulatorily viable?
Hard fail / severe cap / pass
5. Rights and IP
Does the company control ownable economics and durable protection?
Hard fail / cap / route to licensing
6. Financial feasibility
Is the company financially scorable and transactionally feasible?
Hard fail / cap / distress model
7. Market-data integrity
Are ticker, valuation, cash, debt, and status data current and reliable?
Refresh / diligence queue / pass
8. Legal and integrity risk
Are there sanctions, fraud, litigation, or compliance blockers?
Hard fail / severe cap
9. Commercial relevance
Is the opportunity large and differentiated enough to matter?
Severe cap / pass
10. Model routing
Is this a single-asset, portfolio, platform, commercial, licensing, or distress case?
Route to correct model


0B. Deal-Type Classification
Every eligible company is classified before scoring so the tool knows which M&A model should evaluate it.
This layer should not force every company into one bucket. Many biotech companies are hybrids. Therefore, each company receives:
Field
Meaning
Primary deal type
What the buyer is mainly underwriting
Secondary deal types
Other meaningful sources of deal value
Deal-type weights
Estimated importance of each deal type
Recommended model
Which scoring model should be used
Modifiers
Nuance such as lead-asset-heavy, platform-lite, rights-encumbered, or distress overlay
Rationale
Why the company was classified this way


Deal-Type Buckets
Deal type
Definition
Correct model
Single-asset takeout
Most value is tied to one clinical-stage or near-commercial asset
Lead-asset rNPV model
Pipeline portfolio takeout
Multiple meaningful clinical assets, often in the same TA, modality, or franchise
Portfolio M&A model
Platform acquisition
Value depends on a repeatable technology platform, not just one drug
Platform / technology-fit model
Commercial franchise acquisition
Approved products and revenue drive most value
Commercial synergy model
Asset license / partnership
Asset is attractive, but full-company acquisition is unlikely or rights are constrained
Licensing model
Distressed optionality
Low EV or cash pressure creates option value, but asset quality or financing risk is uncertain
Distress-adjusted model


Updated Logic
The classifier should estimate value shares rather than rely on one simple rule.
Signal
Classification implication
lead_asset_value_share > 70%
Primary = single-asset takeout
pipeline_value_share > 50%
Primary = pipeline portfolio takeout
platform_value_share > 35%
Add platform acquisition as primary or secondary
approved_revenue_value_share > 60%
Primary = commercial franchise acquisition
approved_revenue_value_share 30–60%
Commercial / pipeline hybrid
licensing encumbrance is high
Route to licensing model or add asset-license secondary type
cash runway < 12 months + viable asset
Add distressed optionality or route to distress-adjusted model


Formula Structure
The tool should use a shared base quality score plus the deal-type-specific overlay.
base_target_quality =
clinical_evidence
+ differentiation
+ regulatory_path
+ IP_durability
+ CMC_feasibility
+ commercial_meaningfulness
Then each active deal type gets its own score.
single_asset_score =
0.30 × clinical_evidence
+ 0.20 × differentiation
+ 0.15 × regulatory_path
+ 0.15 × IP_durability
+ 0.10 × commercial_meaningfulness
+ 0.10 × lead_asset_dependency
portfolio_score =
0.25 × lead_asset_quality
+ 0.20 × follow_on_asset_quality
+ 0.20 × franchise_coherence
+ 0.15 × pipeline_depth
+ 0.10 × risk_diversification
+ 0.10 × acquirer_TA_fit
platform_score =
0.30 × repeatability
+ 0.25 × platform_validation
+ 0.20 × asset_generation_count
+ 0.15 × strategic_fit
+ 0.10 × manufacturing_or_delivery_advantage
commercial_franchise_score =
0.25 × revenue_growth
+ 0.20 × margin_quality
+ 0.20 × durability_LOE_IP
+ 0.15 × payer_access
+ 0.10 × lifecycle_expansion
+ 0.10 × commercial_synergy
licensing_score =
0.25 × asset_quality
+ 0.20 × partner_need
+ 0.15 × rights_fit
+ 0.15 × development_cost_share_logic
+ 0.15 × deal_structure_feasibility
+ 0.10 × economics_attractiveness
distress_score =
0.25 × asset_salvage_value
+ 0.20 × valuation_dislocation
+ 0.20 × financing_pressure
+ 0.15 × near_term_catalyst
+ 0.10 × buyer_bargaining_power
+ 0.10 × downside_containment
Important:
The blended deal-type score is currently used for memo, audit, and diagnostic purposes. It should not directly change live M&A probability unless explicitly enabled through a separate residual structure bonus.
Example Output
Hybrid Company Blending
If a company fits multiple buckets, the tool should blend the active formulas using the deal-type weights.
Example:
Revolution Medicines deal-type weights:
pipeline portfolio = 0.55
platform acquisition = 0.25
single-asset takeout = 0.20

blended_deal_type_score =
0.55 × portfolio_score
+ 0.25 × platform_score
+ 0.20 × single_asset_score
Example:
Alpine deal-type weights:
single-asset takeout = 0.80
pipeline portfolio = 0.15
platform acquisition = 0.05

blended_deal_type_score =
0.80 × single_asset_score
+ 0.15 × portfolio_score
+ 0.05 × platform_score



0C. Target Size / Buyer Universe Pre-Screen

Layer 0 happens before the target is paired with a specific acquirer. Therefore, 0C does not calculate final affordability for each buyer.

Purpose:
Estimate the target’s deal size and identify what type of buyer universe could realistically acquire it.

Formula:

expected_acquisition_cost =
enterprise_value × (1 + expected_takeout_premium)

Default takeout premium = 35%

Output:
target_size_bucket
expected_acquisition_cost
minimum_buyer_capacity_needed
requires_large_cap_buyer
mega_deal_flag
sub_scale_flag
data_gaps

Target Size Bucket
EV / Market Cap Range
Likely Buyer Universe
Sub-scale
< $100M
Small specialty buyer, PE, licensing, or distressed optionality
Small-cap
$100M–$500M
Mid-cap specialty pharma or large-cap bolt-on
Mid-cap
$500M–$5B
Core biotech M&A universe
Large-cap
$5B–$25B
Large pharma / top specialty pharma
Mega-deal
> $25B
Top pharma only

Important:
0C does not apply a score penalty at Layer 0.
True pair-specific affordability is calculated later in Layer 3A.




  0D. Target-Level Asset-Control / Encumbrance Profile
Step 1 — Identify Encumbrance Type
Bucket
What it checks
Why it matters
Rights control
Who owns global, regional, and indication rights
Buyer needs to know what it actually gets
Economic control
Royalties, milestones, profit shares, revenue splits
Reduces deal value and buyer economics
Partner encumbrance facts
Existing partnership, ROFR, opt-in, consent rights, governance complexity
Records target-level facts; buyer-specific impact is handled later in Layer 3B
IP control
Patent ownership, disputes, exclusivity runway
Determines whether value is protectable
Manufacturing readiness
Process transferability, supply redundancy, GMP readiness, scale capacity
Flags manufacturing complexity; buyer-specific capability is handled later in Layer 3B
Data/control readiness
Data room, trial data access, CMC package, regulatory files
Determines whether diligence can be completed cleanly

Final Asset-Control Score

 asset_control_score =
  0.25 × rights_control_score
+ 0.20 × economic_control_score
+ 0.20 × partner_encumbrance_facts_score
+ 0.15 × ip_control_score
+ 0.10 × manufacturing_readiness_score
+ 0.10 × diligence_readiness_score

Convert score into treatment

After calculating the asset-control score, the model decides how harsh the penalty should be.


Asset-control score
Treatment
Multiplier
Max M&A score cap
≥0.85
Clean
×1.00
None
0.70–0.84
Mild penalty
×0.95
None
0.50–0.69
Meaningful penalty
×0.80
None, but flagged
0.35–0.49
Severe cap
×0.60
0.55
<0.35
Route to licensing / fail
×0.40
0.40


Layer 0D only records target-level encumbrance risk.

Buyer-specific issues are handled later in Layer 3B, including:
ROFR impact on a specific buyer
Existing partner waiver or advantage
Consent rights for a specific change-of-control
Acquirer manufacturing fit
Regional rights fit
This can also produce an encumbrance-adjusted rNPV multiplier for valuation, separate from M&A probability scoring.

0E. Commercial Complexity / Integration Flag
Layer 0 happens before the target is paired with an acquirer. Therefore, 0E does not apply a final buyer-specific penalty.
Purpose:
Identify whether the target has commercial or operational complexity that may make post-acquisition integration difficult.

This layer does not reward commercial synergy.
This layer does not decide whether the target is attractive.
This layer only identifies raw integration complexity and sends the issue downstream for pair-specific evaluation.

raw_integration_complexity =
  0.15 × product_complexity
+ 0.10 × indication_complexity
+ 0.15 × salesforce_burden
+ 0.15 × manufacturing_transfer_complexity
+ 0.15 × geographic_complexity
+ 0.15 × payer_access_complexity
+ 0.10 × channel_complexity
+ 0.05 × systems_and_compliance_transfer_risk

Layer 0E identifies the problem.
Layer 3 decides whether each buyer can handle the problem.

0F. Distress Quality Guard

Purpose:
Prevent distressed, cash-burning biotechs from ranking highly just because they are cheap or need money.

Capital pressure only helps the M&A thesis if the company still owns something strategically valuable.

distress_pressure_score =
0.35 × financing_pressure
+ 0.25 × runway_pressure
+ 0.20 × valuation_distress
+ 0.10 × capital_market_access_risk
+ 0.10 × near_term_funding_need

distress_quality_score =
0.35 × lead_asset_quality
+ 0.20 × platform_validation
+ 0.15 × clinical_salvageability
+ 0.15 × strategic_scarcity
+ 0.15 × asset_control_cleanliness

Rules:
if distress_pressure_score < 0.35:
    no distress guard applied

if distress_pressure_score >= 0.60 and distress_quality_score >= 0.60:
    route_to = "distressed_optionality_model"
    reason_code = "distress_with_viable_asset"

if distress_pressure_score >= 0.60 and distress_quality_score < 0.35:
    mna_probability_cap = 0.25
    reason_code = "distress_without_strategic_asset"

if distress_pressure_score >= 0.80 and distress_quality_score < 0.25:
    mna_probability_cap = 0.15
    reason_code = "broken_distress_case"

Core principle:
Distress ≠ deal thesis.
High distress + viable asset = possible opportunity.
High distress + weak asset/no platform = value trap.

0H. Layer 0 Decision Summary

Purpose:
Summarize the Layer 0 result in a simple, auditable format.

Output:
live_ranking_eligible
historical_training_eligible
routing_verdict
active_score_caps
data_confidence_label
primary_deal_type
target_size_bucket
required_downstream_checks
warning_flags
plain_english_verdict

Example:
Eligible for live ranking.
Routed to pipeline portfolio model.
Medium confidence due to rights data gap.
Requires Layer 3 affordability and partner-rights checks.
No distress cap applied.


Layer 1 — BD M&A Scoring of Asset
Five Diagnostic Components
Layer1_Strategic_Attractiveness =
0.35 × asset_quality (1. Is the asset actually good?)
+ 0.25 × strategic_scarcity (2. Is this asset strategically scarce?)
+ 0.20 × value_creation (3. Is there enough value to justify BD attention?)
+ 0.15 × transaction_setup (4. Are there target-level reasons this could become actionable?)
+ 0.05 × structural_cleanliness (5. Is the target clean enough to avoid immediate BD friction?)
1A — Asset Quality Score
Weight in composite: 35%
Asset Quality asks:
“Is the asset/company fundamentally good enough for BD to care?”
asset_quality =
0.25 × clinical_evidence
+ 0.20 × differentiation
+ 0.15 × regulatory_path
+ 0.15 × ip_exclusivity
+ 0.10 × cmc_feasibility
+ 0.10 × commercial_meaningfulness
+ 0.05 × management_execution
Sub-Dimension
Weight
Rationale
clinical_evidence
25%
Human data strength, endpoint quality, effect size, statistical credibility, safety, durability
differentiation
20%
Efficacy / safety / convenience vs current and future standard of care
regulatory_path
15%
FDA/EMA clarity, precedent, endpoint acceptability, accelerated approval viability
ip_exclusivity
15%
Patent runway, composition-of-matter strength, exclusivity, FTO, royalty burden
cmc_feasibility
10%
Scalability, supply chain, manufacturing transferability, COGS, GMP risk
commercial_meaningfulness
10%
Addressable market, unmet need, pricing power, payer access, adoption feasibility
management_execution
5%
Clinical execution, regulatory execution, transparency, financing track record

Protection:
if clinical_evidence < 0.35:
asset_quality_score capped at 0.55
Meaning: a weak clinical package cannot become “high quality” just because the market is large.
Additional protections:
if asset_quality < 0.45:
Layer 1 composite capped at 0.50

if differentiation < 0.35 and commercial_meaningfulness < 0.50:
Layer 1 composite capped at 0.55

if regulatory_path < 0.35:
Layer 1 composite capped at 0.55

if ip_exclusivity < 0.35:
Layer 1 composite capped at 0.60
Asset Quality Scoring Buckets
Bucket
Start
Add points for
Subtract points for
Question
Clinical evidence
0.50
Randomized human data; clinically meaningful endpoint; strong effect size; clean safety; replicated effect; durable response; subgroup consistency; dose response
Small N; single-arm design; open-label bias; surrogate-only endpoint; marginal p-value; wide confidence interval; safety imbalance; missing durability
“Would this clinical package survive internal diligence?”
Differentiation
0.50
Better efficacy; cleaner safety; easier dosing; broader label; faster onset; durable response; biomarker-enriched population; strong head-to-head data
Me-too profile; worse tolerability; crowded class; inconvenient administration; no clear treatment-algorithm role; weak future positioning
“Is this differentiated enough for a buyer to care?”
Regulatory path
0.50
FDA alignment; accepted endpoint; clear precedent; SPA; breakthrough / fast track; viable accelerated approval path; manageable confirmatory risk
Endpoint uncertainty; FDA disagreement; advisory committee risk; no precedent; unresolved hold; CRL without clear fix
“Would regulatory teams view this path as clean?”
IP / exclusivity
0.50
Composition-of-matter patent; long runway; NCE/BLA/orphan exclusivity; clean FTO; no litigation; manageable royalty stack
Method-of-use only; short patent life; IPR/Paragraph IV risk; active litigation; licensed IP complexity; high royalty burden
“Is this asset cleanly ownable and protectable?”
CMC feasibility
0.50
Standard manufacturing; scalable process; GMP readiness; no supply bottleneck; validated release assays; manageable COGS; redundant suppliers
Cell/gene complexity; potency assay issues; batch failures; inspection risk; cold-chain burden; single-source supplier; poor transferability
“Would CMC be a hidden deal blocker?”
Commercial meaningfulness
0.50
High unmet need; large addressable population; pricing power; clean payer story; clear adoption path; strong geography mix
Narrow market; weak reimbursement; generic pressure; crowded market; low adoption; unrealistic peak sales assumption
“Is this commercially worth a full acquisition or major BD effort?”
Management / execution
0.50
Strong clinical execution; credible regulatory history; transparent communication; good financing history; prior partnerships; clean governance
Repeated delays; poor disclosure; governance concerns; bad financing decisions; weak trial execution; credibility issues
“Can this team preserve value until a buyer or partner acts?”

Asset Quality Sub-Formulas
clinical_evidence =
0.20 × human_data_strength
+ 0.20 × endpoint_quality
+ 0.15 × effect_size
+ 0.15 × statistical_credibility
+ 0.10 × trial_design
+ 0.10 × safety_compatibility
+ 0.10 × replication_durability


differentiation =
0.30 × efficacy_advantage
+ 0.20 × safety_tolerability_advantage
+ 0.15 × convenience_dosing
+ 0.15 × durability
+ 0.10 × label_breadth
+ 0.10 × future_competitive_resilience


regulatory_path =
0.25 × endpoint_acceptability
+ 0.20 × agency_precedent
+ 0.15 × development_path_clarity
+ 0.15 × design_alignment
+ 0.10 × expedited_pathway_support
+ 0.10 × confirmatory_risk
+ 0.05 × geographic_regulatory_transferability


ip_exclusivity =
0.30 × composition_of_matter_strength
+ 0.20 × remaining_exclusivity_runway
+ 0.15 × freedom_to_operate
+ 0.15 × litigation_cleanliness
+ 0.10 × regulatory_exclusivity
+ 0.10 × economic_burden_from_royalties_milestones


cmc_feasibility =
0.25 × process_maturity
+ 0.20 × scale_risk
+ 0.15 × cost_of_goods
+ 0.15 × supply_chain_robustness
+ 0.10 × tech_transferability
+ 0.10 × quality_compliance_risk
+ 0.05 × redundancy


commercial_meaningfulness =
0.25 × addressable_market
+ 0.20 × unmet_need
+ 0.15 × pricing_power
+ 0.15 × payer_access
+ 0.10 × adoption_feasibility
+ 0.10 × competitive_durability
+ 0.05 × geographic_relevance


management_execution =
0.30 × clinical_execution
+ 0.20 × regulatory_execution
+ 0.15 × financing_execution
+ 0.15 × transparency
+ 0.10 × partnership_history
+ 0.10 × governance
1B — Strategic Scarcity Score
Weight in composite: 25%
Strategic Scarcity replaces the old Strategic Fit / Right-to-Win bucket.
The old version asked:
“Is the buyer strategically advantaged?”
That belongs mostly in Layer 3, because it depends on the specific acquirer.
The new Layer 1 question is:
“Is this the kind of asset that multiple serious BD teams would care about?”
strategic_scarcity =
0.25 × ta_scarcity
+ 0.20 × modality_platform_scarcity
+ 0.20 × competitive_position
+ 0.15 × pipeline_gap_relevance
+ 0.10 × franchise_optionality
+ 0.10 × replacement_difficulty
Sub-Dimension
Weight
Rationale
ta_scarcity
25%
Is the therapeutic area strategically active and supply-constrained?
modality_platform_scarcity
20%
Is the modality/platform strategically important or hard to build?
competitive_position
20%
Can this asset win against current/future alternatives?
pipeline_gap_relevance
15%
Does this asset map to broad industry pipeline gaps?
franchise_optionality
10%
Does this create follow-on shots on goal?
replacement_difficulty
10%
Could buyers easily find/build something similar?

Strategic Scarcity Scoring Buckets
Bucket
Start
Add points for
Subtract points for
Question
TA scarcity
0.50
Hot TA; recent deal activity; major unmet need; pharma patent cliff exposure; few credible late-stage assets
TA out of favor; failed deal history; crowded target class; weak payer environment
“Is this disease area scarce and strategically relevant?”
Modality / platform scarcity
0.50
Validated modality; hard-to-build platform; strong delivery/manufacturing moat; repeatable asset engine; scarce talent/IP
Unvalidated platform; hype without clinical proof; easy-to-copy modality; weak IP; no repeatability
“Is this modality/platform scarce or strategically valuable?”
Competitive position
0.50
Better product profile; clear treatment role; strong future positioning; switching advantage; KOL/guideline potential
Inferior to future standard of care; unclear treatment role; crowded pipeline; no adoption reason
“Can this asset win in its category?”
Pipeline gap relevance
0.50
Patent cliff relevance; broad pharma white space; franchise adjacency; shortage of late-stage assets; strategic theme relevance
Low industry demand; many alternatives; no clear pharma portfolio need
“Does this asset map to broad industry gaps?”
Franchise optionality
0.50
Follow-on indications; follow-on assets; lifecycle expansion; combinations; geographic expansion; platform reuse
One-shot binary asset; speculative preclinical optionality; no credible lifecycle path
“Does this create more than one shot on goal?”
Replacement difficulty
0.50
Few similar assets; hard to recreate; strong IP/know-how; clinical data lead; manufacturing barrier
Many alternatives; easy to license/build; weak barriers; no unique clinical lead
“Could buyers easily find or build something similar?”

Strategic Scarcity Sub-Formulas
modality_platform_scarcity =
0.25 × strategic_relevance
+ 0.20 × technical_barrier
+ 0.20 × validation
+ 0.15 × asset_generation_potential
+ 0.10 × manufacturing_delivery_advantage
+ 0.10 × talent_ip_scarcity


competitive_position =
0.30 × relative_product_profile
+ 0.20 × market_entry_position
+ 0.15 × pipeline_threat_adjustment
+ 0.15 × switching_adoption_barriers
+ 0.10 × durability_of_advantage
+ 0.10 × KOL_guideline_potential


pipeline_gap_relevance =
0.30 × patent_cliff_relevance
+ 0.25 × franchise_adjacency
+ 0.20 × late_stage_scarcity
+ 0.15 × strategic_theme_relevance
+ 0.10 × portfolio_diversification_value


franchise_optionality =
0.25 × follow_on_indications
+ 0.20 × follow_on_assets
+ 0.20 × lifecycle_expansion
+ 0.15 × combination_potential
+ 0.10 × geographic_expansion
+ 0.10 × platform_reuse


replacement_difficulty =
0.30 × scarcity_of_alternatives
+ 0.20 × time_to_recreate
+ 0.20 × IP_knowhow_barriers
+ 0.15 × clinical_data_lead
+ 0.15 × manufacturing_operational_barrier
TA scarcity scoring guide:
0.85–1.00 = hot TA, scarce assets, high buyer demand
0.70–0.84 = attractive TA with active deal interest
0.55–0.69 = relevant but not urgent
0.40–0.54 = lower-priority TA
<0.40 = limited strategic demand
1C — Value Creation Score
Weight in composite: 20%
Value Creation asks:
“Is there enough economic value to justify serious BD attention?”
This should not become Layer 3 affordability. Layer 1 can assess whether the target is economically attractive on a standalone and market-implied basis, but it should not decide whether Pfizer, Novartis, Lilly, etc. can afford it.
value_creation =
0.35 × premium_adjusted_rnpv_gap
+ 0.20 × standalone_rnpv_quality
+ 0.15 × downside_protection
+ 0.10 × cost_to_complete
+ 0.10 × market_expectations_gap
+ 0.10 × strategic_option_value
Sub-Dimension
Weight
Rationale
premium_adjusted_rnpv_gap
35%
Is the target worth more than a realistic acquisition price including premium?
standalone_rnpv_quality
20%
Are the value assumptions credible and institutionally underwritable?
downside_protection
15%
If the main thesis fails, is there residual value?
cost_to_complete
10%
How much capital/time is needed before de-risking?
market_expectations_gap
10%
Is the market underpricing the asset?
strategic_option_value
10%
Does this asset create future strategic choices?

Protection:
if asset_quality_score < 0.50:
premium_adjusted_rnpv_gap contribution = 0
Meaning: cheapness cannot rescue a low-quality asset.
Value Creation Sub-Formulas
premium_adjusted_gap =
(buyer_neutral_strategic_value - expected_acquisition_cost)
/ expected_acquisition_cost

expected_acquisition_cost =
enterprise_value × (1 + expected_takeout_premium)


standalone_rnpv_quality =
0.25 × POS_credibility
+ 0.20 × revenue_credibility
+ 0.15 × cost_credibility
+ 0.15 × margin_fcf_credibility
+ 0.15 × sensitivity_robustness
+ 0.10 × assumption_provenance


downside_protection =
0.25 × net_cash_support
+ 0.20 × pipeline_residual_value
+ 0.20 × platform_technology_residual
+ 0.15 × commercial_royalty_residual
+ 0.10 × IP_salvageability
+ 0.10 × strategic_optionality


cost_to_complete =
0.30 × remaining_clinical_cost_burden
+ 0.20 × CMC_cost_burden
+ 0.20 × time_to_derisking
+ 0.15 × confirmatory_postmarketing_burden
+ 0.15 × commercial_build_burden


market_expectations_gap =
0.40 × implied_POS_gap
+ 0.25 × implied_peak_sales_gap
+ 0.15 × implied_penetration_gap
+ 0.10 × implied_price_gap
+ 0.10 × consensus_disagreement_quality


strategic_option_value =
0.25 × follow_on_indication_value
+ 0.20 × combination_value
+ 0.20 × platform_extension
+ 0.15 × defensive_blocking_value
+ 0.10 × geographic_expansion
+ 0.10 × manufacturing_knowhow_option
Premium-adjusted gap score mapping:
Premium-Adjusted Gap
Score
> +75%
1.00
+40% to +75%
0.85
+15% to +40%
0.70
0% to +15%
0.55
-15% to 0%
0.40
< -15%
0.20

1D — Transaction Setup Score
Weight in composite: 15%
Transaction Setup replaces the old Transaction Timing / Seller Willingness Score.
Transaction Setup asks:
“Are there target-level reasons this company could become actionable?”
This is not full transaction probability. Layer 2 and Layer 3 handle actionability and transaction realism.
transaction_setup =
0.30 × financing_pressure
+ 0.25 × catalyst_proximity
+ 0.20 × seller_openness_signals
+ 0.15 × valuation_stress
+ 0.10 × prior_BD_activity
Sub-Dimension
Weight
Rationale
financing_pressure
30%
Does the company need capital soon?
catalyst_proximity
25%
Is there an upcoming event that could force strategic action?
seller_openness_signals
20%
Is management/board behavior consistent with openness to BD?
valuation_stress
15%
Is the equity valuation creating pressure or opportunity?
prior_BD_activity
10%
Has the company shown willingness to transact before?

Transaction Setup Sub-Formulas
financing_pressure =
0.35 × runway_pressure
+ 0.25 × funding_need
+ 0.15 × capital_market_access_risk
+ 0.15 × dilution_risk
+ 0.10 × debt_going_concern_stress


catalyst_time_decay = e^(-days_to_catalyst / 90)

catalyst_proximity =
0.50 × time_decay
+ 0.30 × materiality
+ 0.20 × strategic_relevance


seller_openness =
0.25 × strategic_review_signals
+ 0.20 × board_activist_pressure
+ 0.15 × financing_stress_behavior
+ 0.15 × prior_BD_behavior
+ 0.15 × portfolio_prioritization
+ 0.10 × insider_governance_alignment


valuation_stress =
0.25 × EV_compression
+ 0.20 × drawdown
+ 0.20 × EV_vs_strategic_value
+ 0.15 × EV_vs_cash
+ 0.10 × coverage_sponsorship_weakness
+ 0.10 × liquidity_stress


prior_BD_activity =
0.30 × partnership_history
+ 0.25 × strategic_investor_partner_presence
+ 0.20 × regional_licensing_openness
+ 0.15 × option_structured_deal_openness
+ 0.10 × management_deal_track_record
Runway score mapping:
Runway
Score
>30 months
0.10
18–30 months
0.30
12–18 months
0.55
6–12 months
0.80
<6 months
1.00

Catalyst modifiers:
Catalyst Type
Modifier
pivotal Phase 3 readout
+0.20
regulatory decision
+0.20
major Phase 2 proof-of-concept
+0.15
financing before readout
+0.10
minor data update
-0.10
non-core program update
-0.20

Guardrails:
if financing_pressure > 0.70 and asset_quality < 0.50:
flag value_trap
do not allow distress to boost Layer 1

if valuation_stress_due_to_asset_failure:
valuation_stress_contribution = 0
1E — Structural Cleanliness Score
Weight in composite: 5%
Structural Cleanliness replaces the old Deal Feasibility Score.
Structural Cleanliness asks:
“Is the target clean enough that BD would not immediately view it as a mess?”
This should stay small because Layer 0 and Layer 3 already handle structural/feasibility issues heavily.
structural_cleanliness =
0.30 × rights_clarity
+ 0.25 × ip_cleanliness
+ 0.20 × economic_control
+ 0.15 × diligence_readiness
+ 0.10 × manufacturing_transferability
Sub-Dimension
Weight
Rationale
rights_clarity
30%
Is it clear what the company owns?
ip_cleanliness
25%
Are unresolved IP issues likely to slow diligence?
economic_control
20%
How much of the economics are actually available?
diligence_readiness
15%
Can a buyer diligence this quickly and cleanly?
manufacturing_transferability
10%
Can supply/control be transferred without major disruption?

Structural Cleanliness Sub-Formulas
ip_cleanliness =
0.40 × ownership_clarity
+ 0.25 × litigation_absence
+ 0.20 × FTO_clarity
+ 0.15 × patent_chain_cleanliness


economic_control =
0.30 × royalty_burden
+ 0.25 × milestone_burden
+ 0.20 × profit_share_simplicity
+ 0.15 × co_commercialization_complexity
+ 0.10 × debt_synthetic_claims


diligence_readiness =
0.25 × clinical_data_package
+ 0.20 × regulatory_package
+ 0.20 × CMC_package
+ 0.15 × IP_contract_package
+ 0.10 × financial_package
+ 0.10 × data_room_organization


manufacturing_transferability =
0.30 × process_documentation
+ 0.25 × supplier_redundancy
+ 0.20 × tech_transfer_feasibility
+ 0.15 × GMP_quality_readiness
+ 0.10 × equipment_facility_complexity
Rights clarity score mapping:
Score
Meaning
0.90–1.00
Clean global rights
0.70–0.89
Mostly clean, minor regional/field limitations
0.50–0.69
Some encumbrance but still acquirable
0.30–0.49
Material complexity
<0.30
Likely licensing/partnership case, not full acquisition

Important:
Pair-specific affordability, antitrust, integration capability, ROFR impact, regional rights fit, and acquirer manufacturing fit belong in Layer 3 — not Layer 1.
Simple Scoring Scale
Use this scale across all Layer 1 components:
0.90–1.00 = best-in-class / very clean
0.75–0.89 = strong
0.60–0.74 = good but has diligence questions
0.45–0.59 = mixed
0.30–0.44 = weak
<0.30 = major red flag
Layer 1 Institutional Gates
Layer 1 gates cap the composite. They never boost it.
These gates should only cover issues Layer 1 owns.
Gate
Condition
Cap
Meaning
G1 — Weak Clinical Package
clinical_evidence < 0.35
0.55
Weak human evidence prevents high Layer 1 score
G2 — Low Asset Quality
asset_quality < 0.45
0.50
Weak asset cannot rank highly
G3 — Poor Differentiation + Weak Commercial Case
differentiation < 0.35 AND commercial_meaningfulness < 0.50
0.55
Me-too asset with weak market should be capped
G4 — Weak Regulatory Path
regulatory_path < 0.35
0.55
Unclear approval path limits attractiveness
G5 — Weak IP / Exclusivity
ip_exclusivity < 0.35
0.60
Poor protection limits strategic value
G6 — Low Strategic Scarcity
strategic_scarcity < 0.35
0.60
Not scarce enough for serious BD attention
G7 — Value Trap
asset_quality < 0.50 AND valuation_stress > 0.70
0.50
Cheap/distressed but low quality
G8 — Distress Without Quality
financing_pressure > 0.70 AND asset_quality < 0.50
0.45
Funding pressure cannot rescue bad asset
G9 — Structural Messiness
structural_cleanliness < 0.35
0.65
Structure is messy, but Layer 3 can apply stricter buyer-specific caps later

Anti-Double-Counting Rule
Each concept should belong to one layer.
Concept
Correct Layer
Is this company eligible?
Layer 0
Is this asset good?
Layer 1
Is this asset strategically scarce?
Layer 1
Is there target-level transaction setup?
Layer 1
Should BD act now?
Layer 2
Can this specific acquirer afford it?
Layer 3
Can this specific acquirer integrate it?
Layer 3
Does ROFR block/help a specific buyer?
Layer 3
What deal structure should be used?
Layer 4
How should scores be calibrated?
Layer 5



• Layer 2 does two things:

  1. It calculates the three inputs: TA, DL, and AF.
  2. Then it combines them into Strategic Priority, Transaction Probability, and BD Action Score.

  TA: Target Attractiveness

  Formula in code:

  TA =
    0.35 * de_risking_stage
  + 0.30 * valuation_discount
  + 0.20 * scarcity
  + 0.15 * peak_sales_signal

  Meaning:

  | TA Bucket | How It Scores |
  |---|---|
  | de_risking_stage | Higher if asset is Phase 3, filed, approved, or otherwise clinically de-risked |
  | valuation_discount | Higher if target trades below model value / rNPV |
  | scarcity | Higher if few similar late-stage assets exist |
  | peak_sales_signal | Log-scaled from expected peak sales, capped around $10B |

  peak_sales_signal is not linear. A $10B peak-sales asset does not get 10x the score of a $1B asset; it
  uses log scaling to avoid mega-assets dominating.

  DL: Deal Likelihood

  Formula:

  DL =
    0.40 * financing_pressure
  + 0.25 * external_deal_activity
  + 0.20 * insider_board_signals
  + 0.15 * catalyst_proximity

  Meaning:

  | DL Bucket | How It Scores |
  |---|---|
  | financing_pressure | Higher if cash runway is short / company needs capital |
  | external_deal_activity | Higher if similar assets or TAs are seeing deals |
  | insider_board_signals | Higher if board, management, activist, or ownership signals suggest openness
  |
  | catalyst_proximity | Higher when a major catalyst is near |

  Catalyst proximity is calculated from days to catalyst:

  catalyst_score = exp(-days_to_catalyst / 90)

  So:

  0 days  -> 1.00
  90 days -> ~0.37
  180 days -> ~0.14
  365+ days -> near 0

  There is also a financing-pressure gate:

  if financing_pressure < 0.25
  and no strong scarcity / activist override:
      DL capped at 0.40

  Meaning: a well-funded company with no pressure should not look like a near-term seller just because
  the asset is interesting.

  AF: Acquirer Fit

  Formula:

  AF =
    0.40 * ta_modality_fit
  + 0.30 * pipeline_gap_alignment
  + 0.20 * deal_affordability
  + 0.10 * existing_partnership_bonus

  Where:

  ta_modality_fit =
    0.55 * therapeutic_area_score
  + 0.45 * modality_score

  Meaning:

  | AF Bucket | How It Scores |
  |---|---|
  | therapeutic_area_score | Does the buyer care about this disease area? |
  | modality_score | Does the buyer like / understand this modality? |
  | pipeline_gap_alignment | Does this asset fill a stated buyer pipeline gap? |
  | deal_affordability | Is the target within the buyer’s realistic deal capacity? |
  | existing_partnership_bonus | Full point if there is an existing partnership match |

  So AF is buyer-specific. The same target can have high AF for Vertex and low AF for Pfizer.

  Then Layer 2 combines them:

  Strategic Priority =
    0.45 * AF
  + 0.35 * TA
  + 0.20 * TA.scarcity

  Transaction Probability =
    0.45 * DL
  + 0.25 * AF
  + 0.15 * TA
  + 0.15 * driver_strength

  driver_strength = number_of_drivers / 6

  Drivers are financing pressure, external deal activity, catalyst proximity, scarcity plus fit,
  activist/board signal, and valuation distress.

  BD Action Raw =
    0.50 * Strategic Priority
  + 0.35 * Transaction Probability
  + 0.15 * AF

  Then it applies:

  + interaction bonuses
  - imbalance penalty
  - saturation penalty
  * data confidence multiplier

  Important distinction: compute_bd_layer2() expects TA, DL, and AF objects. The helper functions
  compute_target_attractiveness(), compute_deal_likelihood(), and compute_acquirer_fit_decomposed()
  calculate those objects from sub-scores. The tool does not magically read all news and infer every
  sub-score perfectly; the upstream pipeline/configs have to convert facts into those inputs.

Layer 2 — BD Decision Engine
compute_bd_layer2(
   layer1_attractiveness,
   acquirer_pull,
   deal_momentum,
   information_readiness,
   data_confidence
)
→ Layer2Output
Purpose:
Layer 2 decides whether BD should prioritize a target now.
It does not decide whether the target is eligible. That is Layer 0.
 It does not re-score asset quality. That is Layer 1.
 It does not determine whether a specific deal can actually close. That is Layer 3.
Layer 2 answers:
Is this strategically important, is there buyer pull, is there transaction momentum, and do we know enough to act?

Score 1 — Strategic Priority
Question:
Is this target strategically important enough for BD to care?
Formula:
SP =
0.35 × Layer1Attractiveness.score
+ 0.25 × AcquirerPull.score
+ 0.20 × Layer1Attractiveness.strategic_scarcity
+ 0.10 × pipeline_gap_urgency
+ 0.10 × strategic_option_value
Rationale:
Layer 1 attractiveness remains the largest input because BD should not prioritize weak targets. Acquirer pull matters, but it should not dominate Layer 2 because buyer-specific feasibility is handled later in Layer 3.
Inputs include:
Layer 1 score
Asset quality
Strategic scarcity
Value creation
TA fit
Modality fit
Pipeline gap urgency
Patent cliff / LOE urgency
Strategic option value
Recent acquirer BD behavior
Caps:
if Layer1 asset_quality < 0.50:
   SP cap = 0.55

if AcquirerPull.score < 0.35:
   SP cap = 0.50

if strategic_scarcity < 0.35 and pipeline_gap_urgency < 0.40:
   SP cap = 0.60

Score 2 — Deal Momentum
Question:
Is there a reason this could move in the next 6–18 months?
Formula:
DealMomentum =
0.55 × TargetSidePressure
+ 0.45 × BuyerSideUrgency
Target-side pressure:
TargetSidePressure =
0.30 × financing_pressure
+ 0.20 × seller_openness
+ 0.20 × catalyst_timing
+ 0.15 × valuation_distress
+ 0.15 × governance_or_activist_pressure
Buyer-side urgency:
BuyerSideUrgency =
0.30 × pipeline_gap_urgency
+ 0.25 × LOE_or_revenue_cliff_urgency
+ 0.20 × competitive_FOMO
+ 0.15 × recent_BD_pattern
+ 0.10 × strategic_priority_recency
Rationale:
A transaction requires both sides. A desperate target is not enough if buyers do not care. A perfect buyer fit is not enough if the target has no reason to transact.

Mechanic 1 — Weighted Driver Strength
Old version:
driver_strength = n_drivers / 6
New version:
weighted_driver_strength =
sum(active_driver_weights) / sum(all_driver_weights)
Drivers:
financing_pressure: 1.25
major_catalyst: 1.25
seller_openness: 1.20
external_deal_activity: 1.00
valuation_distress: 0.90
activist_pressure: 0.90
scarcity_plus_fit: 0.80
existing_partnership: 0.70
Each driver should store:
driver_name
active
strength
confidence
source
freshness
direction
Caps:
if active_transaction_drivers == 0:
   DealMomentum cap = 0.35

if active_transaction_drivers == 1:
   DealMomentum cap = 0.60

if financing_pressure < 0.30
and catalyst_timing < 0.30
and seller_openness < 0.30:
   DealMomentum cap = 0.50

Score 3 — Acquirer Pull
Question:
How strong is the buyer-side strategic pull?
Formula:
AcquirerPull =
0.25 × TA_fit
+ 0.20 × modality_fit
+ 0.20 × pipeline_gap_urgency
+ 0.15 × buyer_deal_appetite
+ 0.10 × existing_relationship
+ 0.10 × competitive_fear_of_missing_out
Rationale:
This is not full buyer feasibility. It does not decide affordability, antitrust, integration, ROFR impact, or closing risk. Those belong to Layer 3.
Layer 2 should also calculate:
top_acquirer_pull
second_best_acquirer_pull
buyer_universe_depth
buyer_concentration_risk
Definitions:
buyer_universe_depth =
number of acquirers with AcquirerPull ≥ 0.65

buyer_concentration_risk =
top_acquirer_pull - second_best_acquirer_pull
Interpretation:
High top buyer, low second buyer = single-buyer risk
Multiple high buyers = competitive process potential
No strong buyers = acquirer mapping needed

Score 4 — Information Readiness
Question:
Do we know enough to justify BD action?
Formula:
InformationReadiness =
0.25 × Layer1_confidence
+ 0.20 × acquirer_profile_freshness
+ 0.20 × transaction_driver_source_quality
+ 0.15 × valuation_data_freshness
+ 0.10 × rights_encumbrance_clarity
+ 0.10 × catalyst_date_confidence
Rationale:
Layer 2 should not over-rank targets based on stale buyer profiles, weak transaction-driver evidence, or outdated valuation data.
Readiness labels:
≥0.80     High
0.60–0.79 Medium
0.40–0.59 Low
<0.40     Very low / diligence queue

Score 5 — BD Action Score
Question:
Should BD prioritize this now?
Formula:
bd_action_raw =
0.40 × StrategicPriority
+ 0.30 × DealMomentum
+ 0.20 × AcquirerPull
+ 0.10 × InformationReadiness
Rationale:
Strategic priority gets the largest weight because BD should not chase non-strategic targets. Deal momentum is second because a great target with no reason to transact should be watchlisted, not actively pursued.

Mechanic 2 — Balance / Fragility Penalty
If one leg of the thesis is much weaker than the others, the score is penalized.
Use:
fragility_ratio =
min(SP, DealMomentum, AcquirerPull) /
max(SP, DealMomentum, AcquirerPull)
Penalty:
<0.35       −0.10
0.35–0.50   −0.05
≥0.50        0.00
Example:
SP = 0.90
AcquirerPull = 0.85
DealMomentum = 0.05

fragility_ratio = 0.05 / 0.90 = 0.056
penalty = −0.10
Meaning:
Great target + great buyer logic is not enough if there is no transaction momentum.

Mechanic 3 — Interaction Bonuses
Bonuses are capped at 0.08 total.
Condition                                      Bonus
SP ≥0.70 and AcquirerPull ≥0.65                +0.03
DealMomentum ≥0.65 and AcquirerPull ≥0.60      +0.03
SP ≥0.70 and DealMomentum ≥0.60                +0.03
SP ≥0.70 and DealMomentum ≥0.60
and AcquirerPull ≥0.65                         +0.05
Rationale:
Bonuses help only when signals reinforce each other. They should not rescue weak base scores.

Mechanic 4 — Layer 2 Caps
Layer 2 caps only issues Layer 2 owns.
if StrategicPriority < 0.40:
   bd_action_cap = 0.50

if DealMomentum < 0.30:
   bd_action_cap = 0.65

if AcquirerPull < 0.35:
   bd_action_cap = 0.55

if InformationReadiness < 0.40:
   bd_action_cap = 0.60
Do not cap for:
affordability
antitrust
ROFR impact
integration risk
regional rights mismatch
manufacturing fit for specific buyer
Those belong to Layer 3.

Mechanic 5 — Saturation Penalty
The saturation penalty prevents crowded near-perfect scores.
Apply to:
StrategicPriority
DealMomentum
AcquirerPull
BD_Action_PreConfidence
Purpose:
Prevent false precision
Prevent too many scores clustering near 1.0
Reduce inflated outputs from correlated inputs

Mechanic 6 — Data Confidence Multiplier
Data Confidence    Multiplier    Effect
HIGH               1.00          No adjustment
MEDIUM             0.93          7% reduction
LOW                0.85          15% reduction
VERY_LOW           0.00          Excluded from ranking
Formula:
bd_action_score =
saturation_penalty(pre_gate_score) × confidence_multiplier
If InformationReadiness is very low, classification should become Diligence Queue, even if the raw score is high.

Layer 2 Classification Matrix
Strategic Priority
Deal Momentum
Acquirer Pull
Classification
High ≥0.75
High ≥0.65
High ≥0.65
Active BD pursuit
High ≥0.75
Medium 0.45–0.65
High/Medium
Catalyst watch / relationship build
High ≥0.75
Low <0.45
Any
Strategic watchlist
Medium 0.50–0.75
High ≥0.65
High ≥0.65
Opportunistic outreach
High/Medium
High
Low <0.35
Acquirer mapping needed
Any
Any
Any + low information readiness
Diligence queue
Low <0.50
High
Any
Distressed / non-core warning
Low
Low/Medium
Low/Medium
Pass


Recommended Actions
Active BD pursuit:
Prioritize now. Move to Layer 3 pair-realism checks.

High-priority BD diligence:
Attractive but needs missing data resolved before serious action.

Catalyst watch:
Monitor upcoming clinical/regulatory event and update after catalyst.

Strategic watchlist:
Strong target but weak near-term transaction momentum.

Relationship build:
Begin soft-touch coverage; not aggressive pursuit yet.

Acquirer mapping needed:
Good asset, but unclear buyer universe.

Diligence queue:
Score may be real, but data quality is insufficient.

Distress trap warning:
Target looks cheap/actionable, but asset quality or strategic logic is weak.

Pass:
Low BD priority.

Expected Action Window
Layer 2 should output timing.
0–6 months:
financing pressure high and catalyst within 180 days

6–18 months:
buyer urgency high and catalyst / financing / seller signals visible

18–36 months:
strategic priority high but transaction setup weak

Strategic watch only:
strong asset but no near-term pressure


Layer 3 — Realism Layer - Does this deal make sense
New version:
Layer 3 evaluates:
Pair-specific affordability / financing realism
Consideration realism
Rights / control / encumbrance fit
Pair-specific integration capability
Antitrust / regulatory deal risk
Strategic conflict / cannibalization risk
Process / governance / closing risk
Hidden diligence blockers
Layer 3 does not decide whether the target is attractive. That is Layer 1.
 Layer 3 does not decide whether BD should care now. That is Layer 2.
 Layer 3 only stress-tests whether the acquirer-target pair is executable.
Final score:
layer3_adjusted_score =
min(
   upstream_layer2_score × layer3_multiplier,
   min(triggered_gate_caps)
)
If a hard fail triggers:
layer3_adjusted_score = 0
Gates can only cap or fail. They never boost.

Layer 3 Core Formula
Layer 3 computes a pair-level feasibility score:
pair_feasibility_score =
 0.20 × affordability_financing_realism
+ 0.15 × consideration_realism
+ 0.20 × rights_control_fit
+ 0.15 × integration_capability
+ 0.15 × antitrust_feasibility
+ 0.10 × strategic_conflict_feasibility
+ 0.05 × process_closing_feasibility
Then convert score into a multiplier:
Pair Feasibility Score
Treatment
Multiplier
≥0.85
Clean
×1.00
0.70–0.84
Mild issue
×0.90
0.55–0.69
Meaningful issue
×0.75
0.40–0.54
Severe issue
×0.55
<0.40
Pair-level fail / route away
×0.00–0.40


3A — Pair-Specific Affordability / Financing Realism
Purpose:
 Determine whether the acquirer can realistically pay for the target without breaking its balance sheet, stock currency, rating profile, or capital-allocation constraints.
expected_acquisition_cost =
enterprise_value × (1 + expected_takeout_premium)
acquirer_deal_capacity =
 available_cash_after_buffer
+ realistic_debt_capacity
+ realistic_stock_component
+ divestiture_capacity
+ partner_financing_capacity
- competing_capital_commitments
affordability_ratio =
expected_acquisition_cost / acquirer_deal_capacity
Affordability realism:
affordability_financing_realism =
 0.25 × cash_capacity
+ 0.20 × debt_capacity
+ 0.20 × stock_currency_quality
+ 0.15 × balance_sheet_buffer
+ 0.10 × historical_deal_appetite
+ 0.10 × rating_leverage_tolerance
Treatment:
Affordability Ratio
Treatment
≤0.50
No penalty
0.50–0.85
Mild penalty
0.85–1.10
Severe penalty / cap
>1.10
Pair-level hard fail

Triggers:
if affordability_ratio > 1.10:
   hard_fail = true

if affordability_ratio >= 0.85:
   cap = 0.60

if acquirer_credit_stress_high and deal_requires_large_debt:
   cap = 0.55

if target_requires_cash_deal and buyer_cash_insufficient:
   cap = 0.50

3B — Consideration Realism
Purpose:
 Determine whether the likely form of payment is credible for both buyer and seller.
consideration_realism =
 0.30 × cash_stock_mix_feasibility
+ 0.20 × target_shareholder_acceptability
+ 0.15 × acquirer_shareholder_acceptability
+ 0.15 × CVR_or_milestone_suitability
+ 0.10 × tax_efficiency
+ 0.10 × precedent_consistency
Key questions:
Question
Why it matters
Can the buyer pay cash?
Seller certainty
Is buyer stock a credible currency?
Dilution / volatility
Would target shareholders accept stock?
Closing risk
Is a CVR appropriate?
Useful for binary biotech risk
Are milestones clearer than full cash value?
Reduces buyer downside
Is structure consistent with precedent?
Board / banker realism

Triggers:
if only_feasible_structure_is_stock_heavy and acquirer_stock_quality < 0.40:
   cap = 0.60

if target_requires_cash_certainty and buyer_cash_capacity_low:
   cap = 0.50

if CVR_needed_but_milestone_definition_unclear:
   cap = 0.70

3C — Rights / Control / Encumbrance Fit
Purpose:
 Determine whether target-level encumbrances actually block, help, or complicate this specific buyer.
Layer 0 records the facts.
 Layer 3 interprets the facts for the specific buyer.
rights_control_fit =
 0.25 × ROFR_ROFN_impact
+ 0.20 × consent_rights_impact
+ 0.20 × regional_rights_fit
+ 0.15 × economic_encumbrance_fit
+ 0.10 × exclusivity_conflict
+ 0.10 × existing_partner_status
Treatment:
Rights / Control Fit
Treatment
≥0.85
Clean
0.70–0.84
Mild penalty
0.50–0.69
Meaningful penalty
0.35–0.49
Severe cap
<0.35
Pair-level fail or route to licensing

Pair-specific examples:
Situation
Treatment
Acquirer is existing partner with ROFR
Lower penalty / possible advantage
Acquirer is not partner and ROFR blocks bidding
Severe cap
Regional rights exclude buyer’s core market
Severe cap
Consent rights likely unavailable
Severe cap or fail
Key economics already licensed away
Route to licensing / partnership

Triggers:
if self_acquisition:
   hard_fail = true

if acquirer_blocked_by_ROFR and not_existing_partner:
   cap = 0.45

if change_of_control_consent_required and consent_likely_unavailable:
   cap = 0.50

if regional_rights_do_not_include_buyer_core_market:
   cap = 0.55

if existing_partner_opt_in_removes_key_asset:
   hard_fail_or_license_only = true
Possible remediation paths:
partner waiver
asset carve-out
regional license
option-to-acquire
co-development
CVR / milestone structure
wait for ROFR expiry

3D — Pair-Specific Integration Capability
Purpose:
 Determine whether this acquirer can absorb the target’s commercial, manufacturing, geographic, medical, payer, and compliance complexity.
buyer_integration_capability =
 0.20 × commercial_infrastructure_fit
+ 0.20 × manufacturing_capability_fit
+ 0.15 × payer_access_capability_fit
+ 0.15 × geographic_footprint_fit
+ 0.10 × medical_affairs_KOL_fit
+ 0.10 × systems_compliance_capability_fit
+ 0.10 × prior_integration_experience
adjusted_integration_penalty =
raw_integration_complexity_score × (1 - buyer_integration_capability)
Treatment:
Adjusted Integration Penalty
Treatment
0.00–0.15
No penalty
0.15–0.30
Mild penalty
0.30–0.50
Meaningful penalty
0.50–0.70
Severe penalty / cap
>0.70
Pair-level cap or fail

Triggers:
if adjusted_integration_penalty > 0.70:
   cap = 0.45

if manufacturing_complexity_high and buyer_manufacturing_fit_low:
   cap = 0.55

if commercial_product_requires_specialty_field_force and buyer_lacks_infrastructure:
   cap = 0.60

if payer_access_complexity_high and buyer_payer_capability_low:
   cap = 0.65
Deal-type adjustment:
Deal Type
Integration focus
Clinical single-asset
CMC, development, regulatory
Commercial franchise
Sales force, payer, supply chain, PV, compliance
Platform acquisition
Talent retention, IP transfer, data systems, culture
Distressed target
Data room, CMC transfer, litigation, financing continuity


3E — Antitrust / Regulatory Deal Risk
Purpose:
 Determine whether regulators could challenge the deal because of product overlap, pipeline overlap, market concentration, or innovation competition.
antitrust_risk =
 0.25 × current_product_overlap
+ 0.20 × pipeline_overlap
+ 0.20 × market_concentration
+ 0.15 × innovation_competition_risk
+ 0.10 × divestiture_complexity
+ 0.10 × jurisdictional_complexity
antitrust_feasibility = 1 - antitrust_risk
Treatment:
Antitrust Risk
Treatment
0.00–0.20
Low risk
0.20–0.40
Manageable
0.40–0.60
Material diligence issue
0.60–0.80
Severe cap
>0.80
Pair-level hard fail

Triggers:
if direct_product_overlap_high and market_concentration_high:
   cap = 0.45

if pipeline_overlap_creates_innovation_competition_issue:
   cap = 0.60

if required_divestiture_removes_core_deal_value:
   hard_fail = true

if multi_jurisdiction_antitrust_complexity_high:
   cap = 0.65

3F — Strategic Conflict / Cannibalization Risk
Purpose:
 Determine whether the deal creates internal strategic conflict for the acquirer.
This is different from strategic fit.
 Layer 2 may say the buyer is interested.
 Layer 3 asks whether the deal creates conflict inside the buyer’s portfolio.
strategic_conflict_risk =
 0.30 × product_cannibalization
+ 0.20 × pipeline_cannibalization
+ 0.15 × channel_conflict
+ 0.15 × partner_conflict
+ 0.10 × pricing_contracting_conflict
+ 0.10 × organizational_conflict
strategic_conflict_feasibility = 1 - strategic_conflict_risk
Triggers:
if target_cannibalizes_buyer_core_franchise_without_replacement_logic:
   cap = 0.55

if buyer_has_exclusive_partnership_conflict:
   cap = 0.50

if deal_requires_killing_high_priority_internal_program:
   cap = 0.60
Examples:
Conflict
Why it matters
Buyer already owns competing Phase 3 asset
Internal pipeline conflict
Target competes with core franchise
Cannibalization
Existing partner conflict
Contractual / strategic issue
Deal undermines pricing strategy
Commercial risk
Buyer must kill internal program
Political / portfolio friction


3G — Process / Governance / Closing Risk
Purpose:
 Determine whether the deal can actually be signed and closed.
process_closing_feasibility =
 0.20 × target_board_alignment
+ 0.15 × shareholder_approval_likelihood
+ 0.15 × management_retention_feasibility
+ 0.15 × financing_process_readiness
+ 0.10 × diligence_package_readiness
+ 0.10 × cross_border_execution_feasibility
+ 0.10 × timeline_feasibility
+ 0.05 × litigation_risk
Triggers:
if shareholder_approval_unlikely:
   cap = 0.55

if founder_controlled_and_founder_unwilling:
   cap = 0.50

if unresolved_litigation_blocks_close:
   cap = 0.45

if management_retention_required_and_unlikely:
   cap = 0.65

3H — Hidden Diligence Blocker Check
Purpose:
 Identify diligence issues that can kill a deal even if the score looks strong.
This is a checklist, not a normal weighted score.
Hidden blockers include:
IP ownership uncertainty
undisclosed royalty stack
unfavorable change-of-control clause
trial data integrity issue
CMC package incomplete
GMP inspection issue
supply dependency
material litigation
sanctions / export control issue
FCPA or compliance issue
key employee retention risk
major adverse event not fully disclosed
commercial channel conflict
cyber / data room issue
Treatment:
Blocker Severity
Treatment
Minor
Flag only
Moderate
Mild cap
Major
Severe cap
Fatal
Hard fail

Each blocker should return:
blocker_name
severity
confidence
source
remediation_path
cap_or_fail

Institutional Gates
Layer 3 gates are evaluated independently.
 The most restrictive cap wins.
Gate
Trigger
Cap
G1 — Affordability Impossible
affordability_ratio > 1.10
Hard fail
G2 — Affordability Stretched
affordability_ratio 0.85–1.10
0.60
G3 — Consideration Not Credible
required structure is not acceptable to buyer/seller
0.50–0.70
G4 — Rights / Control Blocker
ROFR, consent, regional rights, or opt-in blocks buyer
0.45–0.55
G5 — Severe Integration Mismatch
adjusted_integration_penalty ≥0.50
0.60
G6 — Antitrust / Regulatory Deal Risk
material product/pipeline overlap or required divestiture
0.45–0.65
G7 — Strategic Conflict
cannibalization, partner conflict, or internal pipeline conflict
0.50–0.60
G8 — Process / Governance Risk
board, shareholder, litigation, or closing issue
0.45–0.65
G9 — Fatal Diligence Blocker
issue makes transaction non-executable
Hard fail

Examples:
G2 cap = 0.60
G4 cap = 0.45
G6 cap = 0.65

final cap = 0.45
This removes gate-order ambiguity.

Layer 4 — BD Watchlist Classification and Action Routing
Layer 4 answers:
 Given Layers 0–3, what should BD actually do next?
Layer 4 does not re-score asset quality, strategic attractiveness, BD priority, or pair feasibility. It converts upstream outputs into a practical BD route, deal structure, urgency, diligence plan, and monitoring plan.

Twelve Routing Classes
Rules are evaluated in strict priority order. First match wins.
Priority
Class
Core Condition
Meaning
1
pair_level_hard_fail
Layer 3 hard_fail = True
This acquirer-target pair is not executable
2
pass_do_not_pursue
Layer1 score <0.45 OR Layer2 BD action score <0.40
Not worth BD time
3
high_priority_diligence
BD action ≥0.70 AND information_readiness <0.60
Attractive, but data gaps must be resolved before action
4
remediation_required
Layer 3 severe cap exists AND remediation_path exists AND no hard fail
Interesting, but a blocker must be fixed first
5
active_pursuit
BD action ≥0.75 AND pair_feasibility ≥0.70 AND information_readiness ≥0.60 AND no hard fail
Prepare BD process now
6
partner_or_license_candidate
asset_quality ≥0.65 AND full acquisition feasibility weak due to affordability, rights, integration, or encumbrance
Full acquisition may be wrong; consider asset-level deal
7
option_to_acquire_candidate
asset_quality ≥0.60 AND catalyst_proximity ≥0.60 AND clinical uncertainty high AND pair_feasibility ≥0.55
Get exposure before binary de-risking
8
catalyst_watch
catalyst_proximity ≥0.65 AND strategic_priority ≥0.55 AND BD action <0.75
Prepare view before upcoming data
9
strategic_watch
strategic_priority ≥0.70 AND deal_momentum <0.45
Strategically relevant, but no urgency
10
relationship_build
strategic_priority ≥0.65 AND acquirer_pull ≥0.60 AND deal_momentum <0.50 AND existing_relationship weak
Build trust before a transaction
11
acquirer_mapping_needed
Layer1 score ≥0.65 AND acquirer_pull confidence <0.50
Good target, unclear buyer universe
12
monitor_only
Layer1 score 0.45–0.60 OR BD action 0.40–0.55
Keep in universe, but no active BD work

If no class matches after clearing hard fail and pass gates, default to high_priority_diligence if confidence is low; otherwise default to monitor_only.

Layer 4 Output Fields
Every Layer4Output includes:
Field
Meaning
route_class
Final routing class
recommended_bd_action
What BD should do next
recommended_structure
Best-fit deal structure
secondary_structures
Other reasonable deal structures
urgency_level
How quickly BD should act
escalation_level
Who should review it
outreach_status
Whether outreach should happen now
review_cadence
How often to re-evaluate
monitoring_triggers
Events that should update the route
promotion_trigger
What would move the target up
demotion_trigger
What would move the target down
required_diligence
Specific diligence tasks before action
remediation_plan
How to fix blockers
confidence_level
Confidence in routing decision
owner_next_step
Immediate BD team action
memo_summary
CRM / memo-ready summary

Additional audit fields:
Field
Meaning
reason_codes
Why the class was assigned
candidate_class
Class before churn suppression
classification_suppressed
Whether prior class was held
active_caps
Upstream caps affecting route
hard_fail_reasons
Fatal pair-level blockers
missing_data
Data gaps lowering confidence
warnings
Important routing caveats


Fourteen Deal Structures
Structure
Core Condition
no_action
pass_do_not_pursue or pair_level_hard_fail
monitor_only
monitor_only, strategic_watch, or low-confidence catalyst_watch
full_acquisition
pair_feasibility ≥0.70 AND rights clean AND affordability strong AND integration feasible AND antitrust manageable
asset_acquisition
lead asset drives most value AND company-level baggage is high
global_license
asset attractive AND full acquisition unnecessary or weak AND global rights available
regional_license
regional rights available AND global rights unavailable or unnecessary
option_to_acquire
asset attractive AND near-term catalyst exists AND uncertainty is high
option_to_license
asset attractive AND buyer wants rights after proof-of-concept
co_development
clinical-stage asset AND development cost/risk sharing makes sense
co_commercialization
near-commercial/commercial asset AND buyer brings commercial capability
minority_equity_investment
strategic relationship valuable AND seller not ready to sell
strategic_collaboration
platform or relationship value exists, but full deal is premature
CVR_heavy_acquisition
acquisition feasible AND valuation gap high AND binary catalyst risk high
structured_acquisition_with_milestones
buyer wants control now but staged economics are needed

The model recognizes that BD does not only buy companies. It can also:
license assets
take options
co-develop
co-commercialize
take minority equity
pursue regional rights
use CVRs or milestones
monitor only
pass

Urgency, Escalation, and Outreach
Route Class
Cadence
Time Horizon
Escalation
Outreach Status
pair_level_hard_fail
none
n/a
no escalation
blocked
pass_do_not_pursue
none / annual
n/a
no escalation
monitor only / blocked
high_priority_diligence
weekly
0–3 months
BD manager / senior BD
do not contact yet
remediation_required
weekly
blocker-dependent
BD manager / legal / finance
do not contact yet
active_pursuit
weekly
0–6 months
senior BD / IC prep
outreach ready
partner_or_license_candidate
weekly / monthly
3–12 months
BD manager / senior BD
soft-touch or outreach ready
option_to_acquire_candidate
weekly / event-driven
0–6 months
senior BD
soft-touch or outreach ready
catalyst_watch
weekly / event-driven
0–6 months
analyst / BD manager
monitor or soft-touch
strategic_watch
monthly
12–24+ months
analyst / BD manager
monitor only
relationship_build
monthly
12–24 months
BD manager
soft-touch only
acquirer_mapping_needed
monthly
n/a
analyst / BD manager
do not contact yet
monitor_only
quarterly
12+ months
analyst
monitor only


Diligence Workplan
Layer 4 generates specific diligence tasks from upstream weaknesses.
Weakness
Diligence Task
Low clinical confidence
Validate trial design, endpoint quality, effect size, safety, and subgroup consistency
Low regulatory confidence
Confirm endpoint acceptability, FDA/EMA precedent, accelerated approval path, and confirmatory risk
Low rights/control fit
Review ROFR, ROFN, opt-in, consent, regional rights, and change-of-control clauses
Low affordability realism
Test cash, debt, stock, CVR, milestone, license, and option structures
Low antitrust feasibility
Map product overlap, pipeline overlap, divestiture risk, and jurisdiction risk
Low integration capability
Assess commercial, CMC, payer, geographic, systems, and medical affairs fit
Low acquirer confidence
Refresh acquirer profile, pipeline gaps, recent deals, and strategic priorities
Stale valuation
Refresh EV, net cash, implied asset value, rNPV, and premium-adjusted valuation

Each task includes:
Field
Meaning
category
Clinical, regulatory, CMC, IP, finance, legal, antitrust, integration, commercial, acquirer mapping
question
Exact diligence question
priority
Critical, high, medium, low
owner
BD, legal, finance, clinical, CMC, commercial, regulatory, antitrust, analyst
source_needed
Documents or data required
due_window
Before outreach, before IC, before route upgrade, or ongoing
expected_score_impact
What decision could change


Remediation Logic
Layer 4 does not only say “blocked.” It says whether the blocker can be fixed.
Blocker
Possible Remediation
Affordability issue
License, option, CVR, milestone structure, asset deal
ROFR issue
Waiver, existing partner route, wait for expiry, asset carve-out
Consent issue
Legal review, waiver strategy, alternate structure
Regional rights mismatch
Regional license or geography-specific deal
Integration gap
Co-commercialization, CDMO support, narrower asset deal
Clinical uncertainty
Option-to-acquire, option-to-license, CVR, wait for catalyst
Valuation disagreement
CVR, milestones, staged acquisition
Antitrust risk
Divestiture, license instead of acquisition, pass if value destroyed
CMC gap
CMC diligence, tech-transfer plan, CDMO plan, delayed pursuit


Monitoring Triggers
Promotion Triggers
Trigger
Meaning
Positive Phase 2/3 data
Upgrade catalyst_watch or option candidate
Clean safety update
Increase actionability
FDA alignment / SPA / regulatory clarity
Reduce regulatory uncertainty
Runway falls below 12 months
Increase transaction pressure
Strategic review announced
Upgrade seller openness
Comparable deal at premium valuation
Increase external deal activity
Competitor failure
Increase scarcity
Buyer pipeline failure in same TA
Increase acquirer pull
ROFR expires or partner waives rights
Remove blocker
Valuation gap widens while quality intact
Improve value creation

Demotion Triggers
Trigger
Meaning
Negative clinical data
Lower asset quality
Safety signal
Increase clinical and regulatory risk
Financing extends runway >24 months
Lower transaction pressure
Competitor reports superior data
Lower differentiation
Buyer fills pipeline gap elsewhere
Lower acquirer pull
Target signs exclusive partnership
Reduce deal availability
Catalyst delayed >12 months
Lower urgency
Commercial assumptions weaken
Lower value creation
IP litigation worsens
Increase structural risk
Antitrust risk increases
Reduce pair feasibility


Persistence / Churn Suppression
Layer 4 prevents noisy weekly reclassification.
Class changes are allowed only if:
major_event_override == True
OR consecutive_new_class_signals >= 2
If not, the old class is held and the output records:
classification_suppressed = True
candidate_class = new_candidate_class
watchlist_class = prior_class
This matters because BD teams should not constantly reclassify targets based on tiny weekly score movement.
Major event override examples:
Event
Effect
Clinical readout
Allow immediate route change
FDA decision / CRL
Allow immediate route change
Financing / going-concern update
Allow immediate route change
Strategic review announced
Allow immediate route change
Acquisition / partnership announced
Allow immediate route change
ROFR waiver / consent update
Allow immediate route change
Major competitor data
Allow immediate route change
Antitrust/legal blocker discovered
Allow immediate route change


Layer 5 — Explaining the Models Output
Layer 5 adds six things:
Calibrated time-bounded transaction probabilities
Confidence classification
Segment/sample-size shrinkage
Rank-versus-probability divergence flags
Historical validation / postmortem learning
Plain-English explainability

Step 1 — Shows Calibrated Time-Bounded Probabilities
Layer 5 should not treat the raw M&A score as a true probability.
It produces separate calibrated estimates:
Output
Meaning
p_full_acquisition_6m
Probability of full acquisition within 6 months
p_full_acquisition_12m
Probability of full acquisition within 12 months
p_full_acquisition_24m
Probability of full acquisition within 24 months
p_any_strategic_transaction_12m
Acquisition, license, partnership, option deal, or strategic investment within 12 months
p_license_or_partner_12m
Probability of licensing / partnership transaction
p_active_process_12m
Probability of active strategic process within 12 months

Important:
Layer 5 should not output one generic “M&A probability.”
 Full acquisition, license, partnership, and active process are different outcomes.

Step 2 — Raw Score to Initial Probability
Layer 5 may still use a pseudo-logistic mapping as a starting point:
logistic_prob = σ(8.0 × (adjusted_score − 0.68))
Example calibration points:
Adjusted Score
Rough Logistic Probability
0.35
~7%
0.55
~26%
0.70
~54%
0.80
~72%

But this is only the starting estimate, not the final probability.
If an upstream fitted probability exists from a real calibration model, Layer 5 should use that instead.

Step 3 — Shrinkage Calibration
The final 12-month estimate should blend:
p_transaction_12m =
 w_base × base_rate
+ w_model × model_probability
+ w_bucket × comparable_bucket_rate
+ w_segment × segment_rate
Weights depend on sample size and segment reliability.
Tier
n threshold
w_base
w_model
w_bucket
w_segment
Very small
n < 10
0.65
0.15
0.10
0.10
Small
10 ≤ n < 30
0.50
0.25
0.15
0.10
Moderate
30 ≤ n < 100
0.35
0.35
0.15
0.15
Large
n ≥ 100
0.20
0.45
0.15
0.20

Interpretation:
Small sample → trust base rates more.
Large sample → trust model score and segment data more.
Sparse segment → use ranking, not true probability.
This prevents overfitting on thin comparable-deal cohorts.

Step 4 — Segment-Level Calibration
Layer 5 should calibrate by segment when possible.
Segments include:
therapeutic area
modality
clinical stage
deal type
market cap / EV bucket
public vs private
distress level
route class
acquirer type
rights encumbrance level
catalyst proximity
Rules:
Segment sample size
Treatment
n ≥ 100
Use segment calibration
30 ≤ n < 100
Blend segment with global calibration
n < 30
Use global calibration and show warning

Example warning:
Sparse historical segment — use as ranking, not calibrated probability.

Step 5 — Confidence Level
Layer 5 explicitly tells the user how much to trust the output.
Confidence depends on:
data confidence
comparable sample size
segment sample size
calibration quality
route class
presence of hard gates / caps
no-lookahead validation quality
drift status
Confidence
Display Format
VERY_LOW
“Insufficient data — ranking only”
LOW
“~20% — Low confidence / wide range”
MEDIUM
“~20% — Medium confidence”
HIGH
“20% — High confidence”

If confidence is very low:
do_not_use_as_probability = true

Step 6 — Time Horizon Adjustment
Layer 5 produces 6-month, 12-month, and 24-month probabilities.
The 12-month estimate is the anchor.
The 6-month and 24-month estimates are adjusted using:
transaction readiness
deal momentum
catalyst proximity
financing pressure
seller openness
Layer 4 route class
Layer 3 pair feasibility
Example:
High catalyst proximity + high deal momentum → higher 6-month probability.
High strategic priority but low deal momentum → lower 6-month, higher 24-month probability.
Catalyst Watch → lower near-term acquisition probability, but higher post-catalyst strategic transaction probability.

Step 7 — Rank / Probability Divergence Flag
Layer 5 detects when rank and calibrated probability disagree.
Example 1:
High rank score but low calibrated probability
Meaning:
“This looks strategically attractive, but similar companies have not often been acquired.”
Example 2:
Low rank score but high calibrated probability
Meaning:
“The target is not amazing, but it resembles companies that historically got bought.”
This is an audit flag, not an automatic override.

Step 8 — Historical Validation
Layer 5 validates each layer separately.
Layer
What Layer 5 validates
Layer 0
Did the pre-screen correctly include/exclude targets?
Layer 1
Did attractiveness predict strategic relevance?
Layer 2
Did BD priority predict actionability?
Layer 3
Did pair feasibility gates identify executable deals?
Layer 4
Did the route / structure recommendation match useful outcomes?

Metrics include:
Brier score
expected calibration error
AUC
precision@K
recall@K
route accuracy
structure accuracy
false positive rate
false negative rate
hit rate by score bucket

Step 9 — Postmortem Learning
Every resolved case should create a postmortem.
Postmortem fields:
predicted score
predicted route
predicted probability
actual outcome
time to outcome
error type
root cause
recommended model update
Example:
Prediction:
High-priority active pursuit.

Outcome:
No deal. Target raised capital and stayed independent.

Root cause:
Model overweighted financing pressure and underestimated seller ability to raise.

Suggested update:
Reduce financing-pressure weight unless capital-market-access risk is also high.
Layer 5 recommends changes. It should not automatically rewrite model weights without review.

Step 10 — Drift Detection
Layer 5 checks whether the M&A environment has changed.
Drift types:
financing regime drift
antitrust regime drift
takeout premium drift
deal volume drift
licensing vs acquisition drift
acquirer appetite drift
small-cap biotech valuation drift
Example:
Drift warning:
Distress-driven M&A signal has weakened because biotech financing conditions improved.

Recommendation:
Downweight financing pressure until recalibrated.

Step 11 — Explainable Text
Layer 5 should generate plain-English output.
Example:
The model ranks this target highly because it has strong asset quality, high strategic scarcity, and credible buyer interest.

However, the calibrated 12-month full-acquisition probability is only ~18% because comparable Phase 2 oncology targets with similar financing status have historically transacted infrequently within one year.

Confidence is medium because the comparable sample is moderate, but acquirer-profile freshness is incomplete.

Use this as a strategic-priority signal, not a definitive takeout probability.

