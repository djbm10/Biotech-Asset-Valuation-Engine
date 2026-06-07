# Biotech Asset Valuation Engine — BD Overview
### A practical brief for business development discussions

---

## What this tool is

A quantitative valuation platform for pre-commercial drug programs. It computes a
**risk-adjusted NPV (rNPV)** — the single number that accounts for both the probability
the drug succeeds *and* the time-value of cash flows if it does.

For a BD person, the key outputs are:

| Question | Output |
|---|---|
| What is this asset worth? | rNPV with full probability and revenue decomposition |
| What should the deal structure look like? | Upfront / milestone / royalty modeled explicitly |
| Is the seller's ask reasonable? | Comparable deal benchmarking (P25/P50/P75) |
| Who else will bid? | Acquirer ranking across 10 major pharma/biotech |
| How sensitive is value to our key assumptions? | Tornado chart across 8 parameters |
| What is the market pricing in? | Back-solved implied probability of approval |
| What do we need to believe for this price to work? | Variant perception analysis |

---

## The core valuation — how rNPV is built

Four engines run in sequence. Each is isolated and auditable.

```
[1] PROBABILITY MODEL
    Clinical trials → per-phase P(success) → cumulative P(approval)

[2] REVENUE MODEL
    Market assumptions → year-by-year revenue and EBIT post-launch

[3] COST MODEL
    Trial R&D + deal costs → probability-weighted PV of development spend

[4] rNPV MODEL
    Combines (1)(2)(3) + tax + ownership → single risk-adjusted value
```

**The formula in plain English:**

```
rNPV = [P(approval) × PV of after-tax profits we capture]
       − [PV of development costs we bear]
       + [PV of milestone payments we receive]
       + [upfront payments we receive]
```

**NAV** (for public company targets) adds net cash:

```
NAV = rNPV + net cash on balance sheet
NAV per share = NAV / diluted shares outstanding
```

---

## Probability of Success — how the model scores clinical risk

This is the most differentiated part of the engine. It does not use a static base rate.

**Starting point:** Industry base rates from Biomedtracker/IQVIA by therapeutic area and phase.

**Then applies eight qualitative adjusters in log-odds space:**

| Adjuster | What it captures | Range (log-odds) |
|---|---|---|
| Endpoint type | Hard outcome vs. surrogate vs. biomarker-only | −0.55 to +0.45 |
| MoA precedent | Validated class → first-in-class → known liability | −0.60 to +0.35 |
| MoA exception flags | Genetic validation, human POM, bad-drug failures | up to +0.25 rescue |
| Sample size adequacy | Statistical power quality (not raw N) | −0.50 to +0.20 |
| Safety profile | Clean → mechanism-linked boxed-warning risk | −0.80 to +0.10 |
| Competitive pressure | Regulatory bar to clear (unmet need vs. H2H required) | −0.30 to +0.10 |
| Biomarker enrichment | Validated predictive selection vs. post-hoc weak | −0.10 to +0.40 |
| Prior phase data | Replicated strong signal → prior failure | −0.35 to +0.30 |

Log-odds ensures adjusters add up cleanly and the result always stays between 0 and 1.
Total analyst adjustment is capped at ±0.80 log-odds to prevent implausible outputs.

**Accelerated approval:** NDA/BLA base rate is discounted 18% for AA programs
to reflect confirmatory trial failure risk — this is a base rate correction, not an adjuster.

**Example (rare disease, Phase 2):**
- Industry base rate (Phase 2, rare disease): ~52%
- After adjusters: validated target (+0.35), clean safety (+0.10), strong prior data (+0.20),
  validated biomarker enrichment (+0.40) → adjusted POS: ~72%
- Phase 3 base ~67%, adjusted to ~74%
- NDA/BLA base ~85%
- **Cumulative P(approval): 72% × 74% × 85% = 45%**

---

## Revenue and Profit Modeling

**Three ways to model the commercial opportunity:**

| Mode | Best for |
|---|---|
| Lines of Therapy (LOT) | Oncology with distinct 1L/2L/3L patient pools |
| Patient-based | Rare disease with known prevalence and annual incident pool |
| TAM-based | Early-stage programs where market sizing is top-down |

**Revenue curve mechanics:**
- Uptake ramp from launch to peak (configurable years-to-peak)
- Competition haircut applied each year (time-aware — not a static discount)
- Payer access and compliance rates applied
- SG&A auto-selected by modality: gene/cell therapy launches at 55%, rare disease 45%,
  standard pharma 40% — all ramping down to 20–28% at maturity

**Post-patent tail (LOE erosion):**
Up to 5 tail years can be modeled with year-specific revenue loss fractions.
Post-LOE EBIT margin is often *higher* than pre-LOE because marketing spend collapses
faster than revenue (modeled explicitly — not assumed away).

---

## Deal Structure Modeling — the M&A layer

This is where the engine earns its keep for a BD team. Every component of a real
deal structure can be modeled and valued simultaneously.

---

### Upfront payments

Both outflows and inflows at deal signing are modeled at face value (no discounting —
they are time-0 cash flows):

- `upfront_cost_millions` — what Vertex pays at signing
- `upfront_receipt_millions` — what Vertex receives (e.g., in a licensing deal where
  Vertex is the licensor)

Upfront flows directly subtract from or add to rNPV and appear in the full audit output.

---

### Milestone payments — the most detailed M&A feature

Every milestone is individually priced using the asset's clinical timeline
and probability structure. Five trigger types are supported:

| Trigger | When it pays | Probability used |
|---|---|---|
| `PHASE_START` | On entering a clinical phase | P(reaching that phase) |
| `PHASE_SUCCESS` | On completing a phase successfully | P(reaching) × P(passing) |
| `APPROVAL` | On FDA approval | Cumulative P(approval) |
| `FIRST_SALE` | On first commercial sale (can lag approval) | Cumulative P(approval) |
| `SALES_THRESHOLD` | First year annual revenue ≥ target | P(approval) × P(threshold crossed) |

**What this means practically:** A "$50M Phase 3 success milestone" is worth approximately:

```
PV = $50M × P(reaching Phase 3) × P(Phase 3 success) / (1 + WACC)^year_end_of_phase3
```

If P(reaching Phase 3) = 0.72, P(Phase 3 success) = 0.74, WACC = 10%, Phase 3 ends in 5 years:
```
PV = $50M × 0.72 × 0.74 / (1.10)^5 = $50M × 0.533 / 1.611 = $16.5M
```

The tool computes this for every milestone in the structure simultaneously, giving you
the **total probability-weighted PV of the milestone package** — which is always
substantially less than the headline "biobucks" figure.

**Sales threshold milestones** scan the revenue curve to find the first year revenue
crosses the threshold, then price the milestone to that specific year. A "$200M sales
threshold" triggers later in a niche orphan disease program than in an immunology blockbuster.

**Direction:** Each milestone is tagged PAYABLE (Vertex pays) or RECEIVABLE (Vertex receives).
The model tracks both simultaneously — relevant for co-development or option structures.

**Launch year offset:** FIRST_SALE milestones can be set to trigger N years after approval
to model commercial launch lag. Set `launch_year_offset = 0.5` to model a 6-month lag
between approval and first sale.

---

### Royalty and profit share — explicit separation

Two distinct economic deductions are modeled, and they are **not interchangeable**:

**Royalty rate** (`deal.royalty_rate`) — paid on net revenue (top-line):
```
royalty_payment = annual_revenue × royalty_rate
```

**Profit share** (`deal.profit_share_rate`) — paid on EBIT:
```
profit_share_payment = annual_EBIT × profit_share_rate
```

**Why the distinction matters:** A 10% royalty on $500M revenue reduces EBIT by $50M.
A 10% profit share on $150M EBIT reduces EBIT by only $15M. The tool models both
simultaneously and tracks each as a separate line item in the output.

**Royalty stacking:** Vertex's own equity stake (net ownership after any existing
royalties on the Asset) and the deal royalty operate multiplicatively:

```
effective_capture = gross_EBIT × Vertex_equity_stake × (1 − deal_royalty_rate)
```

Example: Vertex has 80% ownership in an asset and pays a 12% royalty to a licensor:
```
effective_capture = EBIT × 0.80 × (1 − 0.12) = 70.4% of EBIT
```

---

### Co-development cost sharing

`cdev_cost_share` controls what fraction of clinical R&D Vertex bears:

- `1.0` = Vertex funds 100% of development (full buyout or full risk)
- `0.5` = 50/50 co-development split (reduces cost burden, typically reduces revenue share too)
- `0.3` = partner funds 70%, Vertex funds 30% (e.g., Vertex brings platform, partner brings capital)

This is applied to all clinical trial costs before probability-weighting and discounting.

**The value of co-dev:** Halving cost share on a $400M Phase 3 program with 50% P(approval)
frees up ~$100M in probability-weighted PV of costs. That is a direct increase in rNPV.

---

### Tax modeling — BD/M&A grade

Two tax modes available:

**Simple (default):** Effective tax rate applied after an NOL benefit window.
Quick to set up; appropriate for early screening.

**Full TaxProfile (BD/M&A memo grade):** Per-year NOL tracking with an explicit
dollar balance, 80% utilization limit (post-TCJA), jurisdiction-split blended rates,
maintenance capex, working capital build, and one-time launch capex.

| TaxProfile parameter | What it captures |
|---|---|
| `nol_balance_millions` | Vertex's existing NOL carryforwards applicable to this program |
| `nol_utilization_limit_rate` | 80% (US default post-TCJA §172) — max NOL applied per year |
| `jurisdiction_mode` | Blended rate vs. US/ex-US split (relevant for global royalty structures) |
| `us_revenue_fraction` | What share of peak sales the US represents |
| `maintenance_capex_rate` | Ongoing manufacturing/facilities CapEx as % of revenue |
| `launch_capex_millions` | One-time manufacturing ramp investment at launch year |
| `working_capital_rate` | Working capital build as % of incremental revenue |

Full TaxProfile produces a `TaxAudit` — a year-by-year table of taxable income,
NOL consumed, cash taxes paid, and after-tax FCF — exportable to JSON or the BD memo.

> **Practical note for Vertex:** Vertex carries significant NOL from years of CF
> investment. Modeling this explicitly changes the effective cost of early acquisitions
> materially — the simple 21% flat rate overstates near-term cash taxes.

---

### Putting a full deal structure together — example

A Phase 2 rare disease asset. Vertex is acquiring:

```python
DealEconomics(
    upfront_cost_millions     = 150,     # $150M at signing
    royalty_rate              = 0.08,    # 8% royalty to seller on net sales
    cdev_cost_share           = 0.70,    # Vertex funds 70% of remaining development
    launch_year_offset        = 0.5,     # First sale 6 months after approval
    milestones = [
        Milestone("Phase 3 start",    amount=75,   trigger=PHASE_START,   phase="phase_3"),
        Milestone("Phase 3 success",  amount=150,  trigger=PHASE_SUCCESS, phase="phase_3"),
        Milestone("FDA approval",     amount=200,  trigger=APPROVAL),
        Milestone("$250M sales",      amount=125,  trigger=SALES_THRESHOLD, threshold=250),
        Milestone("$500M sales",      amount=200,  trigger=SALES_THRESHOLD, threshold=500),
    ]
)
```

**What the engine returns:**
- Probability-weighted PV of each milestone individually
- Total headline "biobucks": $900M
- True probability-weighted PV of milestone package: ~$195M (example)
- upfront cost: $150M at face value
- Effective deal cost (probability-weighted PV of everything Vertex pays): ~$380M
- rNPV after deal terms: the number your IC needs

---

## Strategic Fit — Who Else Is Bidding

`rank_acquirers()` scores 10 major pharma/biotech against any target using
three weighted factors:

```
composite_score = 0.45 × TA_match + 0.35 × LOE_urgency + 0.20 × budget_fit
```

**TA match (45%):** Is this therapeutic area in the acquirer's stated strategic priorities?

**LOE urgency (35%):** How urgently does the acquirer need to replace revenue from
expiring franchises? Modeled from known LOE cliffs with revenue-at-risk estimates:

| Acquirer | Known LOE pressure | LOE urgency score |
|---|---|---|
| Merck | Keytruda ($25B peak, LOE 2028) | High |
| BMS | Revlimid + Opdivo (LOE 2026–2028) | High |
| Pfizer | Eliquis ($6.5B, LOE 2028) | Moderate |
| AbbVie | Post-Humira rebuilding | Moderate |

**Budget fit (20%):** Can the acquirer afford it?
```
firepower = cash + 2 × annual FCF
affordable = deal_size ≤ 25% of firepower
```

**Each acquirer profile also carries:**
- BD style (BOLT_ON / PLATFORM / BLOCKBUSTER / PARTNERSHIP_FIRST)
- Preferred deal stage (Phase 2, Phase 3, Approved)
- Active pipeline gaps by TA and modality (priority: low/medium/high/critical)
- Historical BD transaction history

> **For Vertex context:** This output tells you who is likely to be in the data room
> alongside you — and how urgently they need the asset relative to you.
> A competitor with high LOE urgency will pay a larger premium to beat a competing bid.

---

## Comparable Deal Benchmarking

The engine loads historical biotech M&A and licensing transactions and computes
**P25 / P50 / P75 price bands** by matching tier:

| Match tier | Criteria |
|---|---|
| Tier 1 (best) | Same TA + same phase + same modality |
| Tier 2 | Same TA + same phase |
| Tier 3 | Same TA only |

**Three value dimensions benchmarked simultaneously:**

| Metric | What it shows |
|---|---|
| Enterprise value band | Total deal EV vs. comparable acquisitions |
| Upfront band | Market expectation for upfront cash at signing |
| Total biobucks band | Headline deal value including all milestones |

Each deal is quality-tagged (HIGH / MEDIUM / LOW). A **high-quality band** filters
to only HIGH/MEDIUM quality comps so outliers with bad data do not distort the range.

**Each comparable deal record captures:**
- Enterprise value and peak sales (for EV/peak sales multiple)
- Upfront, total milestones, royalty rate range
- Geographic scope (global vs. US vs. ex-US)
- Deal type (M&A, license, co-development, option, royalty acquisition)
- Post-deal outcome (approved, discontinued, ongoing)
- Data quality rating with source

**The output grounds your IC conversation:** Instead of "we think $X is fair,"
you can say "Tier 1 comps show P25/P50/P75 of $X/$Y/$Z — our offer of $W is at
the 38th percentile for this TA and phase."

---

## Negotiation Leverage — Sensitivity and Market Signals

### Tornado analysis (8 parameters, one-at-a-time)

The engine varies each parameter and shows the rNPV impact. Sorted by absolute
swing so the biggest levers are visible immediately:

| Parameter | Variation | Typical swing direction |
|---|---|---|
| Peak sales | ±30% | Largest single driver in most programs |
| Discount rate | ±2pp | Amplified for long-dated programs |
| Phase POS | ±20% relative | Dominant for early-stage assets |
| Patent life | ±3 years | High impact in primary-care blockbusters |
| Peak penetration | ±30% | Large in competitive markets |
| Effective tax rate | ±5pp | Material when large NOL is present |
| Gross-to-net rate | ±10pp | Critical for payer-sensitive products |
| Competition entries | +1 / +2 approved | ~15% penetration haircut per entrant |

**For a BD negotiation:** The tornado immediately shows which assumption the seller
and buyer are most likely to disagree on. If peak sales has a ±$300M swing and
the deal is $200M apart, that is the assumption to put on the table.

### Market-implied POS (back-solving from stock price)

For publicly listed targets:

```
implied_pos = (market_EV − net_cash − trial_costs_pv) / pre-probability_revenue_pv
```

The output compares the market's implicit probability of approval to the model's estimate:
- **`pos_gap > 0`:** Market is more skeptical than the model — potential opportunity
- **`pos_gap < 0`:** Market is more optimistic — evaluate whether the premium is warranted

This is the number that tells you whether the current stock price already reflects a deal premium.

### Variant perception (what the market must believe)

Back-solves the market's implicit assumption on two axes:
- **What peak sales does the stock price imply?**
- **What P(approval) does the stock price imply?**

Useful when discussing a deal with an IC: "The stock is pricing in $800M peak sales —
our model says $550M. We need to explain that $250M gap before approving a bid above market."

### Monte Carlo distribution (10,000 simulations)

Correlated draws across all uncertain inputs simultaneously. Outputs:

| Statistic | Use case |
|---|---|
| P5 / P25 / P75 / P95 | Risk range for IC stress-testing |
| P(rNPV > 0) | Probability any positive return exists |
| Mean vs. median gap | Skewness — upside optionality vs. downside mass |
| NAV/share distribution | Share price range under the deal assumptions |

---

## What the Tool Does Not Do

Intellectual honesty matters in BD conversations. Current limitations:

| Gap | Practical impact |
|---|---|
| Section 382 NOL limitations | Post-acquisition ownership-change limits on NOL use are not modeled |
| Purchase accounting step-up | Tax basis step-up on acquired assets reduces future taxes — not modeled |
| Transfer pricing / BEAT / AMT | International tax optimization not captured |
| Country-by-country revenue launch | Geographic revenue split is a single blended rate, not sequential country launches |
| Competitive dynamics post-launch | Competition model assumes known entrants; surprise entrants require manual update |
| Acquirer universe is fixed | 10 pharma/biotech profiles are curated; private equity, specialty pharma, and non-US acquirers not included |

---

## How to Use It for a Specific Deal

**Step 1 — Screen the asset (15 min)**
Run with TA base rates + disclosed trial costs + analyst's peak sales estimate.
Get rNPV range and comparable deal bands. Decide if worth deeper diligence.

**Step 2 — Build your probability view (1–2 hrs)**
Fill in `POSAdjusters` for each phase using clinical data room documents.
Endpoint type, MoA precedent, safety profile, sample size are the four biggest drivers.
Run sensitivity to see how much the POS view moves rNPV.

**Step 3 — Model the deal structure (30 min)**
Enter the seller's proposed terms in `DealEconomics`.
The engine returns the probability-weighted PV of every milestone and royalty stream.
Compare to their headline "biobucks" to see how much headline value evaporates.

**Step 4 — Build your counter-proposal**
Vary upfront vs. milestone mix, royalty rate, and co-dev share to find
structures that meet your return threshold while remaining competitive with other bidders.
Tornado tells you which assumption to debate; comps tell you what is market.

**Step 5 — Package for IC**
Export: rNPV with full decomposition, scenario table (bull/base/bear), tornado chart,
deal structure PV breakdown, acquirer ranking, comparable deal bands, and assumption log.
All of these land in the BD memo template automatically.

---

*Engine version: core-engine-v1 | POS backtest validated: N=99 oncology programs, AUC 0.74 | Brier score 0.2127*
