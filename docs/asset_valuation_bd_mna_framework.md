Asset Valuation + BD/M&A Framework
(Proposed best version — reflects future_fixes.md direction; items marked [PROPOSED] are not yet built)

  Drug Asset / Company
     │
     ▼
  Prior clinical trial result with TA base rate of next phase probability based on prior phase success
     │
     ▼

  [1] POS MODEL
  Purpose: estimate whether the drug can work and get approved.
     │
     ├─ Layer 0: Science of drug — target validity / drug delivery [PROPOSED — HARVEY-0, HARVEY-1]
     │     ├─ Target validity (genetic association, clinical analog, pathway precedent)
     │     └─ Drug delivery / PK-PD (drug at target site, dose-response, tissue biodistribution)
     │
     ├─ Layer 1: Evidence Strength
     │     "Is the biological evidence strong?"
     │     ├─ Endpoint strength
     │     ├─ MoA precedent
     │     ├─ Prior-phase data
     │     ├─ Safety profile
     │     ├─ Biomarker selection
     │     ├─ Sample size / power
     │     ├─ Regulatory approval bar
     │     └─ Breakthrough therapy designation
     │     Cap: ±0.80 log-odds on combined Layer 1 adjustment
     │
     └─ Layer 2: Evidence Credibility
           "Will regulators believe the result?"
           ├─ Evidence design quality (trial type / blinding)
           ├─ Comparator / Standard of care fit
           ├─ Regulatory pathway risk
           ├─ Clinical effect magnitude (MCID)
           └─ Phase-specific scaling
                 Phase 1: 0.20 × raw | Phase 2: 0.50 × | Phase 3: 1.00 × | NDA/BLA: 0.90 ×
           Cap: +0.30 / −0.60 log-odds on combined Layer 2 adjustment
     │
     ▼
  Cumulative Probability of Approval


  [2] REVENUE FORECAST
  Purpose: estimate how much the drug could sell if approved.
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
  EBIT by year


  [3] DEVELOPMENT COST MODEL
  Purpose: estimate remaining cost to approval and launch.
     │
     ├─ Clinical trial costs
     │     ├─ Phase 1
     │     ├─ Phase 2
     │     ├─ Phase 3
     │     └─ NDA / BLA
     │
     ├─ CMC / Manufacturing
     │     ├─ API development
     │     ├─ Formulation
     │     ├─ Scale-up
     │     └─ Regulatory CMC
     │
     └─ Deal-related costs
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


  [4] rNPV ENGINE
  Purpose: calculate standalone risk-adjusted asset value.
     │
     ▼
  Projected Revenue
     │
     ▼
  EBIT
     │
     ├─ subtract royalties
     ├─ subtract profit share
     ├─ subtract taxes [PROPOSED — NOL carryforward + corporate tax rate not yet modeled]
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
  rNPV / NAV per share


  [5] SCENARIO ANALYSIS
  Purpose: test bull / base / bear assumptions.
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


  [6] MONTE CARLO
  Purpose: show the full range of possible values.
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
  Risk / Reward Profile


  [7] VARIANT PERCEPTION BACK-SOLVE
  Purpose: compare model view vs market view.
     │
     ▼
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
  Classify disagreement
     │
     ├─ Clinical
     ├─ Commercial
     ├─ Pricing
     ├─ Mixed
     ├─ Allocation-driven
     └─ Indeterminate


  [8] MACRO / DEAL ENVIRONMENT
  Purpose: assess whether the outside world is friendly or hostile for biotech deals.
  Note: not yet built — planned addition.
     │
     ▼
  Read external environment
     │
     ├─ Capital markets regime
     ├─ Biotech financing window
     ├─ Patent-cliff / pipeline pressure
     ├─ Regulatory / pricing climate
     ├─ Antitrust posture
     ├─ Geopolitical / supply-chain risk
     └─ Therapeutic-area sentiment
     │
     ▼
  Apply macro modifiers downstream
     │
     ├─ Seller willingness adjustment (Layer 2)
     ├─ Buyer urgency adjustment (Layer 2)
     ├─ Valuation discipline adjustment (Layer 3)
     ├─ Antitrust cap strictness (Layer 3)
     ├─ Execution-risk cap strictness (Layer 3)
     └─ Preferred deal-structure bias (Layer 4)
     │
     ▼
  Macro Tailwind / Headwind


  [9] BD/M&A LAYER 0 — ELIGIBILITY + ROUTING + TARGET PRE-SCREEN
  Purpose: hard gate, deal-type ceiling, and target-level quality flags before any scoring runs.
  Runtime order: 0G (data confidence) → 0A (hard exclusion) → 0C / 0D-T / 0E / 0F → 0B (deal route)
     │
     ▼
  Layer 0A — Hard eligibility check (binary; blocks everything below if failed)
     ├─ Therapeutic vs non-therapeutic / SPAC / shell / services-only
     ├─ Already acquired / pending acquisition / historical-only
     ├─ Self-company / known acquirer filter
     ├─ Royalty / diagnostics / tools / services classification
     ├─ Asset viability (discontinued lead, fatal safety, no regulatory path)
     ├─ Rights / IP / ownership (no ownable rights, fully licensed away, IP dispute)
     ├─ Financial / going concern (bankruptcy, liquidation, missing valuation data)
     ├─ Legal / integrity (sanctions, fraud, GMP failure, SEC cloud)
     └─ Hard exclusion flags / distress-only cases
  Emits: PASS / DILIGENCE_QUEUE / REFRESH_REQUIRED / LEGAL_REVIEW_QUEUE /
         SEVERE_CAP / HISTORICAL_ONLY / HARD_FAIL
     │
     ▼
  Layer 0B — Deal-type classification (sets ceiling on deal structure for Layer 4)
  Runs for PASS, DILIGENCE_QUEUE, REFRESH_REQUIRED, SEVERE_CAP, LEGAL_REVIEW_QUEUE only.
     ├─ FULL_COMPANY_TAKEOUT
     ├─ LEAD_ASSET_TAKEOUT
     ├─ PIPELINE_PORTFOLIO_TAKEOUT
     ├─ PLATFORM_ACQUISITION
     ├─ COMMERCIAL_FRANCHISE_ACQUISITION
     ├─ GLOBAL_LICENSE / REGIONAL_LICENSE
     ├─ OPTION_TO_LICENSE_OR_ACQUIRE
     ├─ CO_DEVELOPMENT_OR_CO_COMMERCIALIZATION
     ├─ MINORITY_EQUITY_PLUS_COLLABORATION
     └─ DISTRESSED_OPTIONALITY
     │
     ▼
  Layer 0C — Target-size pre-screen (informational; no affordability penalty here)
     ├─ SUB_SCALE  (< $100M EV)
     ├─ SMALL_CAP  ($100M–$500M)
     ├─ MID_CAP    ($500M–$5B)
     ├─ LARGE_CAP  ($5B–$25B)
     └─ MEGA_DEAL  (> $25B)
  Pair-specific affordability deferred to Layer 3A.
     │
     ▼
  Layer 0D-T — Target-level asset control
  "Does the target own enough of the asset for any acquirer to underwrite it?"
     ├─ Rights control         (global rights, key geography, indication, change-of-control freedom)
     ├─ Economic control       (royalty cleanliness, milestone burden, profit share, cost obligations)
     ├─ Partner encumbrance    (blocking rights, governance control, encumbrance severity)
     ├─ IP control             (patent strength, exclusivity runway, FTO, ownership cleanliness)
     ├─ Manufacturing readiness (process transferability, supply redundancy, GMP, scale capacity)
     └─ Diligence readiness    (clinical data, CMC package, regulatory files, safety DB, data room)
  Score → multiplier applied to M&A score: CLEAN (1.00) / MILD (0.95) / MEANINGFUL (0.80) /
          SEVERE_CAP (0.60, cap 0.55) / ROUTE_TO_LICENSING_OR_FAIL (0.40, cap 0.40)
  Hard blockers: no_ownable_rights / fatal_ip_dispute / fully_licensed_away → cap or hard fail.
     │
     ▼
  Layer 0E — Integration complexity flag (target-level; buyer capability offset deferred to Layer 3D)
     ├─ Product complexity
     ├─ Indication complexity
     ├─ Salesforce burden
     ├─ Manufacturing transfer complexity
     ├─ Geographic complexity
     ├─ Payer access complexity
     ├─ Channel complexity
     └─ Systems / compliance transfer risk
  Buyer-adjusted penalty = raw_complexity × (1 − buyer_integration_capability) [scored at Layer 3D]
     │
     ▼
  Layer 0F — Distress quality guard
  "Is this a strategic opportunity or a financial trap?"
     ├─ Distress pressure score  (financing pressure, runway, valuation distress, capital access)
     └─ Distress quality score   (lead asset quality, platform validation, clinical salvageability,
                                  strategic scarcity, asset control cleanliness)
  High distress + high quality → distressed optionality route.
  High distress + low quality → probability cap. Distress scored once here; not re-penalized downstream.
     │
     ▼
  Layer 0G — Data confidence (runs first at runtime; feeds 0A exclusion logic)
     ├─ Financial data confidence
     ├─ Asset data confidence
     ├─ Rights / IP data confidence
     ├─ Market data confidence
     └─ Acquirer profile confidence
  Low confidence → score cap + UNCALIBRATED warning in output.
     │
     ▼
  Eligibility / Routing Output
     ├─ Eligible / ineligible (EligibilityStatus)
     ├─ Live ranking vs historical-only
     ├─ Deal-type ceiling (from 0B — DealStructureRoute)
     ├─ Size bucket (from 0C)
     ├─ Asset control score + multiplier (from 0D-T)
     ├─ Integration complexity flag (from 0E)
     ├─ Distress quality classification (from 0F)
     ├─ Data confidence score (from 0G)
     └─ Initial score cap or exclusion reason


  [10] BD/M&A LAYER 1 — TARGET / ASSET ATTRACTIVENESS
  Purpose: score the intrinsic quality of the asset independent of any specific buyer or timing.
  Design principle: no timing signals here. Seller willingness, financing pressure, catalyst
  proximity, and management receptivity belong in Layer 2. A great asset is equally great
  whether the seller has 6 months of cash or 3 years.
     │
     ▼
  Four scored buckets (weights sum to 1.0):

  Asset Quality (0.45)
  "If approved, is this a good drug?"
     ├─ Clinical evidence strength        (feeds from POS Layer 1 output)
     ├─ TPP / future label potential      (what claim and use-case are we buying?)
     ├─ Differentiation vs standard of care
     ├─ Regulatory path clarity
     ├─ CMC / manufacturing feasibility
     └─ Commercial meaningfulness         (market size, pricing, access plausibility)

  Strategic Scarcity (0.30)
  "How hard is it to find a substitute for this asset?"
     ├─ IP / exclusivity runway
     ├─ MoA uniqueness
     ├─ Platform value
     └─ Competitive density of similar assets

  Value Creation (0.20)
  "How much value does acquiring this create vs. the cost?"
     ├─ rNPV vs current EV (model vs market gap from [7])
     ├─ Pipeline gap it fills
     └─ Franchise extension or defense value

  Structural Cleanliness (0.05)
  "Are there structural reasons this deal is hard to close?"
     ├─ Rights / ownership clarity
     ├─ FTO status
     └─ Asset encumbrance
     │
     ▼
  Layer 1 Output
     ├─ Target attractiveness score
     ├─ Asset quality score + sub-scores
     ├─ Strategic scarcity score
     ├─ Value creation score
     ├─ Structural cleanliness score
     ├─ Key strengths
     └─ Key diligence gaps


  [11] BD/M&A LAYER 1.5 — BUYER PROBLEM / PORTFOLIO GAP MATCH [PROPOSED — most important unbuilt layer]
  Purpose: match the asset against live strategic problems across many acquirers.
  Shifts the question from "which asset looks attractive?" to "what problem does this buyer need to solve?"
     │
     ▼
  Build buyer problem library (maintained per acquirer)
     ├─ Patent cliff / revenue replacement need
     ├─ Weak internal pipeline
     ├─ Franchise defense
     ├─ New modality need
     ├─ New therapeutic-area entry
     ├─ Platform capability gap
     ├─ Near-term revenue need
     ├─ Failed internal program replacement
     ├─ Competitive threat response
     └─ Recent BD / collaboration pattern

  Each problem stored with:
     ├─ Buyer current problem
     ├─ Problem urgency
     ├─ Problem source / trigger event
     ├─ Problem as-of date
     └─ Confidence
     │
     ▼
  Match asset to buyer problems
     ├─ Asset problem-solution fit
     ├─ TA fit
     ├─ Modality fit
     ├─ Product / label fit
     ├─ Capability leverage
     ├─ Franchise expansion or defense
     ├─ Relationship status
     └─ Evidence source / confidence
     │
     ▼
  Problem Match Output
     ├─ Which buyer problem this asset solves
     ├─ Best-fit acquirers (ranked)
     ├─ Why this buyer
     ├─ Why this asset
     ├─ Why now
     ├─ Why not buy
     └─ Confidence / missing context


  [12] BD/M&A LAYER 2 — BD ACTION PRIORITY (URGENCY OVERLAY)
  Purpose: decide how urgently to act — not whether to act.
  Design principle: Layer 2 controls cadence and timing. It does not gate routing.
  Route class is determined by Layer 1 + Layer 3. Layer 2 answers: "given the right
  asset and feasible buyer, how fast do we need to move?"
     │
     ▼
  Timing and urgency signals
     ├─ Seller willingness / openness to deal
     ├─ Financing runway (distress accelerates timeline)
     ├─ Catalyst proximity (readout in N days)
     ├─ Acquirer pull (recent buyer event trigger)
     ├─ Existing relationship / partner path
     ├─ Information / diligence readiness
     └─ Evidence coverage gaps
     │
     ▼
  BD Action Output
     ├─ Urgency level (act now / 30 days / 90 days / watchlist)
     ├─ Recommended cadence (weekly / monthly / quarterly)
     ├─ Days to act
     ├─ Urgency reasons
     ├─ Watchlist class
     ├─ Relationship-build candidate
     ├─ Catalyst-watch candidate
     └─ Reason to act now vs wait


  [13] BD/M&A LAYER 3 — PAIR-SPECIFIC DEAL REALISM
  Purpose: for a specific acquirer, can they realistically do this deal?
     │
     ▼
  Score buyer-target fit
     ├─ Matched buyer problem (from Layer 1.5)
     ├─ TA fit
     ├─ Modality fit
     ├─ Pipeline gap filled
     ├─ Patent-cliff need
     ├─ Commercial infrastructure fit
     ├─ Prior BD behavior
     └─ Relationship path to deal
     │
     ▼
  Score deal feasibility
     ├─ Deal affordability (Layer 3A — pair-specific EV affordability)
     ├─ Consideration realism
     ├─ Rights / control fit (Layer 3B/3C — pair-specific ROFR, consent, regional rights)
     ├─ Integration capability (Layer 3D — buyer capability offsets Layer 0E complexity)
     ├─ CMC capability fit
     ├─ Antitrust overlap
     ├─ Strategic conflict (internal buyer conflicts only)
     ├─ Process / closing risk
     ├─ Seller willingness
     └─ Macro cap modifiers (from [8])
     │
     ▼
  Pair Realism Output
     ├─ Buyer-target pair score
     ├─ Best buyer list (ranked)
     ├─ Pair-specific caps applied
     ├─ Pair-specific blockers
     ├─ Antitrust cap applied
     ├─ Affordability cap applied
     ├─ Integration / execution-risk cap
     ├─ Why this buyer
     └─ Why not this buyer


  [14] BD/M&A LAYER 4 — DEAL STRUCTURE + ROUTING
  Purpose: assemble route class, deal structure, and urgency into one actionable output.
  Design principle: three separate fields, three separate sources.
    - Route class    ← Layer 1 + Layer 3 (asset quality + pair feasibility)
    - Deal structure ← Layer 0B ceiling + Layer 1/3 signals (never invented by Layer 4)
    - Urgency overlay ← Layer 2 only

  This keeps the output trustworthy: BD professionals trust the route because it comes
  from quality and feasibility, not a timing model.
     │
     ▼
  Route class (from Layer 1 + Layer 3)
     ├─ ACTIVE_PURSUIT
     ├─ PARTNER_OR_LICENSE_CANDIDATE
     ├─ CATALYST_WATCH
     ├─ RELATIONSHIP_BUILD
     ├─ MONITOR_ONLY
     └─ NO_ACTIONABLE_DEAL
     │
     ▼
  Deal structure (bounded by Layer 0B ceiling)
     ├─ Full acquisition
     ├─ Asset acquisition
     ├─ License
     ├─ Option-to-acquire
     ├─ CVR-heavy acquisition
     ├─ Minority equity / collaboration
     └─ Regional rights deal
     │
     ▼
  Urgency overlay (from Layer 2)
     ├─ Urgency level
     ├─ Recommended cadence
     └─ Days to act
     │
     ▼
  Deal Structure Output
     ├─ Route class
     ├─ Preferred deal structure
     ├─ Alternative deal structures
     ├─ Why full acquisition is / is not realistic
     ├─ Why license / option may be better
     ├─ Urgency overlay
     └─ BD next action


  [15] BD/M&A LAYER 5 — CALIBRATION + CONFIDENCE
  Purpose: attach fair probability language without overstating precision.
     │
     ▼
  Compare against historical data
     ├─ Historical acquisitions
     ├─ Historical non-deals
     ├─ Prior model scores vs actual outcomes
     ├─ Deal values
     ├─ Deal structures
     ├─ Post-deal asset outcomes
     └─ No-lookahead replay data
     │
     ▼
  Calibration Output
     ├─ p_any_strategic_transaction_12m  (primary calibrated output)
     ├─ p_full_acquisition_12m           (derived: acquisition_fraction × p_any)
     ├─ p_license_or_partner_12m         (derived: license_fraction × p_any)
     ├─ Strategic interest level
     ├─ Calibration status (calibrated / uncalibrated — requires N ≥ 30 + acceptable ECE)
     ├─ Reliability diagnostics
     ├─ Known weak areas
     ├─ Confidence label
     └─ Score warning


  [16] FINAL OUTPUT — DUAL-TRACK VERDICT  [BUILT — analysis/dual_track.py]
  Purpose: present TWO independent conclusions plus an interpretive cross-read.
  Design principle: the investment view and the BD/M&A view are scored on
  separate axes and are NEVER averaged into a single "attractiveness" score.
  A name can be a poor stock (already richly priced) yet a strong BD target —
  or undervalued on fundamentals yet not an obvious takeout. The cross-read only
  *describes* the relationship between the two axes; it does not collapse them.
     │
     ├─ TRACK 1 — INVESTMENT VERDICT   "Is the stock undervalued?"
     │     ├─ stance: long / neutral / avoid / not_assessed
     │     ├─ valuation label: undervalued / fair / overvalued
     │     ├─ rNPV vs EV (asset-implied EV preferred; company EV fallback)
     │     ├─ NAV/share vs current price (implied upside %)
     │     ├─ market expectation read: too low / too high / roughly fair
     │     ├─ POS, bull / base / bear, Monte Carlo distribution
     │     └─ confidence + rationale
     │
     ├─ TRACK 2 — BD / M&A VERDICT      "Is the asset a good BD target?"
     │     ├─ strategic relevance: high / moderate / low / not_assessed
     │     ├─ best-fit acquirer + why this buyer
     │     ├─ buyer can execute (feasibility / transaction realism)
     │     ├─ timing: act now / 30d / 90d / watch
     │     ├─ recommended route: acquire / license / option / watchlist / no action
     │     ├─ p(strategic transaction, 12m) + recommended action
     │     ├─ macro deal read, why now, why not buy
     │     └─ confidence + main risks + ranked diligence priority
     │
     └─ CROSS-READ  "How do the two lenses relate?"  (descriptive, not a score)
           ├─ Quadrant (investment attractiveness × BD attractiveness):
           │     • dual_opportunity  — undervalued AND a credible target
           │     • bd_only           — limited stock upside, high BD relevance
           │     • investment_only   — undervalued, not an obvious takeout
           │     • low_conviction    — limited appeal on both lenses
           │     • incomplete        — one lens not assessed
           ├─ one-line headline (e.g. "Limited standalone upside, but high BD
           │     strategic relevance — Vertex is the natural acquirer.")
           ├─ divergence flag (true when the two lenses disagree)
           └─ EXPLICIT "not run" state: a missing lens is shown as "not run" /
                 "not assessed", NEVER as a negative verdict. An investment-only
                 report does not imply a weak BD case, and vice versa. The BD
                 lens is "not run" until the M&A scan (bve-ma-probability) runs.

  Surfaces (BUILT): bve-report top "Dual-Track Verdict" section; valuation.json
  `dual_track` block; run_asset console investment line.
  Surfaces (ADDITIVE, wired surface by surface): ranking / screen columns
  `investment_stance` + `bd_route`. The legacy blended composite score is
  retained unchanged for backward compatibility.
