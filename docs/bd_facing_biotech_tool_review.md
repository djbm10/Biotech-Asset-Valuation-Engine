# Biotech Valuation and M&A Engine — BD-Facing Quick Review

**Audience:** Business development, search & evaluation, corporate strategy  
**Purpose:** Fast review of what the tool does, where M&A logic is useful, and where BD feedback is most valuable.
**Source of truth:** Current repository code and configs.  
**Style note:** Formatted like the older technical report, but shortened for a BD reader.

## Executive Readout

| Question | Short answer |
|---|---|
| What is this? | A prototype valuation and M&A screening system for biotech assets and companies. |
| What business problem does it solve? | It turns asset assumptions into rNPV/NAV and then asks which buyers might care, why, and how actionable the situation is. |
| What is strongest today? | Single-asset valuation, scenario analysis, market-implied expectation comparison, acquisition discount, acquirer-fit ranking. |
| What is weakest today? | Exact takeout probabilities, seller willingness, hidden rights/control issues, antitrust, deal structure likelihood, and buyer-specific private strategy. |
| How should BD use it? | As a structured discussion tool and diligence checklist, not as an automatic answer. |
| Where is BD feedback most valuable? | M&A logic: strategic urgency, buyer priorities, deal blockers, rights, competitive bidders, and likely structure. |

## 1. One-Page Overview

This is a prototype biotech valuation and M&A screening system. It values individual biotech assets using risk-adjusted NPV, compares the model value to market value, and then screens which pharma/biotech acquirers might logically care about the asset.

The tool is trying to support decisions like:

- Is this asset undervalued relative to its clinical/commercial risk?
- What would the asset be worth if the clinical thesis works?
- Which companies are plausible acquirers?
- Is the target merely strategically interesting, or actually actionable?
- What hidden deal blockers should diligence focus on?

The most useful BD feedback is not "is the code right?" It is whether the M&A logic reflects how real BD teams think: strategic urgency, internal pipeline gaps, hidden rights issues, seller willingness, competitive bidders, preferred deal structures, and what would make a buyer act now.

Current maturity:

- Valuation engine: useful and fairly mature.
- M&A ranking: useful for screening, but still needs expert validation.
- M&A probability: directional only, not investment-grade probability.
- Hidden deal blockers: not yet captured deeply enough.

## 2. How the Tool Works at a High Level

The tool starts with an asset config: drug, indication, stage, trial path, success probabilities, costs, commercial assumptions, company cash, share count, and market price.

It then:

1. Estimates probability of approval.
2. Builds a revenue curve.
3. Estimates R&D and CMC costs.
4. Computes risk-adjusted NPV.
5. Converts that into NAV/share.
6. Runs scenario and Monte Carlo analysis.
7. Compares model value to market value.
8. Screens whether the asset looks like an acquisition candidate.
9. Scores acquirer-target fit against curated pharma profiles.
10. Ranks likely acquirers and M&A attractiveness.

Plain-English version:

```text
Asset value = probability-adjusted future cash flow - probability-weighted development cost
M&A interest = strategic fit + de-risking + valuation + urgency + feasibility
```

Old-report-style formula version:

```text
rNPV =
    P(approval) * PV(after-tax commercial free cash flow)
  - PV(probability-weighted development cost)
  + PV(receivable deal economics)
  - PV(payable deal economics)

Acquisition attractiveness =
    asset quality
  + value dislocation
  + strategic fit
  + buyer urgency
  + seller willingness
  - feasibility / control / antitrust / rights penalties
```

The first formula is closer to a working financial model. The second is a structured BD heuristic. The tool implements meaningful pieces of the BD heuristic, but the most important judgmental inputs still need expert review.

## 3. Where BD Feedback Is Most Valuable

| Area | What the tool currently assumes | Why BD expertise matters | Questions for BD person |
|---|---|---|---|
| Strategic fit | TA/modality/pipeline-gap matching from curated profiles | Public priorities can be generic or stale | Would this buyer actually care, or is this only superficially related? |
| Acquirer priorities | Manually curated stated priorities and gaps | Internal priorities differ from investor-deck language | Which stated priorities are real enough to drive a deal? |
| Therapeutic area fit | Token/category matching plus profile gaps | Sub-indication nuance matters | Is this indication in the buyer's real wheelhouse? |
| Modality fit | Preferred modality lists | Capability is not the same as appetite | Would this buyer own/develop/manufacture this modality? |
| Pipeline gap fit | Curated pipeline gaps with urgency | Urgency depends on internal failures and LOE | Is the gap urgent or merely nice-to-have? |
| LOE / revenue-cliff urgency | Partially represented in profiles and gaps | Exact franchise cliffs drive BD timing | What revenue cliff or franchise defense would make this urgent? |
| Deal appetite | Recent deal history and budget | Some buyers are inactive despite cash | Is this buyer acquisitive now? |
| BD history | Recent deals in profile YAMLs | Prior deals predict style, not always targets | How much should prior deal history influence score? |
| Buyer-specific valuation | Comps and budget headroom | Buyers value synergies differently | Would this buyer pay more than generic comps? |
| Royalty stacks | Deal economics exist, but target-specific stacks sparse | Royalties can destroy economics | What royalty burden would be unacceptable? |
| Existing partnerships | Profile field exists | Partnerships can imply data rights or options | Does the partnership create a real acquisition path? |
| Regional rights | Not modeled deeply | Split rights can block full acquisition | How should split rights change structure and value? |
| Change-of-control clauses | Mostly missing | CoC can trigger payments or block transfer | What clauses should be captured? |
| Asset-control issues | Placeholder/gate in BD layers | Control determines structure | Is clean title required for this buyer? |
| IP/exclusivity | Generic patent life/LOE mostly | Real exclusivity drives valuation | Which IP facts matter most before taking this seriously? |
| CMC/manufacturing | Cost model exists; risk depth limited | Manufacturing fit can make or break deals | Would this buyer see CMC as manageable? |
| Commercial infrastructure | TA fit approximates it | Salesforce/customer overlap matters | Does buyer already call on the right prescribers? |
| Antitrust risk | Placeholder in gate layers | Strategic overlap can create regulatory risk | Would this buyer create antitrust issues? |
| Seller willingness | Financing/catalyst/signals approximate it | Often non-public | What public signs suggest a seller is open? |
| Competitive bidding | Mostly missing | Bidders affect probability and price | Who else would bid, and why? |
| Deal structure likelihood | Routing module exists, but not deeply validated | Structure often matters more than binary M&A | Full acquisition, option, license, co-dev, or regional deal? |

## 4. Detailed M&A Scanner Explanation

### What the scanner is trying to predict

The scanner is not just asking "is this asset good?" It is asking:

```text
Is this target attractive enough, cheap enough, strategically relevant enough,
and transactability-positive enough that a real buyer might act within a useful time window?
```

That distinction matters. A target can be scientifically attractive and still be a poor acquisition candidate if the seller is unwilling, rights are encumbered, the buyer has no urgency, valuation is stretched, or the likely structure is a partnership rather than a full acquisition.

### How the model scores acquirer-target fit

For each target and acquirer, the model evaluates:

- therapeutic-area fit
- modality/platform fit
- pipeline gap or strategic priority
- stage and acquisition readiness
- valuation relative to comps
- budget/capacity fit
- existing partnership bonus

If an acquirer profile has explicit pipeline gaps, the model focuses heavily on whether the target fills that gap and how urgent the gap is.

### What makes a company more likely to buy

The model currently treats an acquirer as more likely when:

- it has a relevant pipeline gap
- the target modality matches buyer capabilities
- the target is affordable
- similar deals appear in its history
- there is an existing partnership or option relationship
- external deal activity suggests urgency

What is too simplistic:

- It cannot truly know internal priorities.
- It does not deeply model corporate politics or portfolio tradeoffs.
- It may overweight public statements.
- It does not fully model antitrust or rights complications.

### What makes a target more attractive

The target scores better when:

- it is clinically de-risked
- it trades at a discount to model rNPV
- it has meaningful peak sales
- it is scarce in its category
- it has a near-term catalyst
- it has capital vulnerability
- it is not too large or too diversified

What reduces score:

- pre-Phase 2 stage
- missing valuation config
- missing market cap
- weak acquisition readiness
- too large for buyer
- target is itself an acquirer/mega-cap
- no transaction urgency
- seller not pressured

### How the model estimates deal value

It uses enterprise value, rNPV, EV/peak-sales comps, and recent precedent deals. This is useful for screening but not a full deal model. A real BD model would need:

- exact rights and royalty burden
- tax treatment
- synergies
- integration cost
- competing bidder assumptions
- deal structure
- diligence haircut

### How it handles strategic urgency

Strategic urgency comes from:

- pipeline gaps in acquirer profile
- gap urgency level
- external deal activity
- scarcity of similar assets
- catalyst timing
- franchise/LOE logic where captured in profiles

BD feedback needed:

- Which gaps are actually urgent?
- Which gaps are already solved internally?
- Which gaps would be solved by partnership rather than acquisition?

### How it handles capital vulnerability

The scanner uses cash runway, financing pressure, vulnerability signals, and target activity. If a company is well-funded with no buyer urgency, the model caps probability.

BD feedback needed:

- Does cash pressure actually make management more likely to sell?
- Is the board/investor base sale-friendly?
- Would a financing solve the issue instead?

### How it ranks likely acquirers

The model scores every acquirer profile against each target, sorts candidates, and records the best acquirer plus runner-up. It can also persist daily M&A snapshots for historical replay.

Useful today:

- Generates a good first-pass list.
- Forces explicit reasons for buyer fit.
- Surfaces budget and gap assumptions.

Not yet enough:

- Needs BD review of hidden blockers.
- Needs richer buyer-specific behavior.
- Needs validation against actual deal history.

### What a BD person should review first

| Output | BD review question |
|---|---|
| Top acquirers | Are these actually plausible buyers, or just superficially similar companies? |
| Strategic-fit reason codes | Do the reasons match real buyer priorities? |
| Pipeline-gap score | Is the gap urgent enough to cause action? |
| Budget/valuation score | Would this buyer pay the implied price? |
| Acquisition discount | Is the market discount real, or is the model missing a fatal issue? |
| Deal trigger flags | Would a buyer act before or after the next catalyst? |
| Deal structure route | Is the likely path acquisition, option, license, partnership, or monitor-only? |
| Control/rights caveats | Are there ROFR, ROFN, regional rights, or change-of-control provisions that block the obvious deal? |

### What to trust versus not trust

| Output | Current read |
|---|---|
| "This asset is worth diligence" | Reasonable if valuation and evidence are current. |
| "This buyer is a plausible fit" | Useful starting point, especially with profile evidence. |
| "This buyer is the most likely acquirer" | Needs BD review before relying on it. |
| "Takeout probability is X%" | Directional only; do not over-read decimals. |
| "Full acquisition is likely" | Not yet reliable without rights/control and structure calibration. |
| "No hidden blockers exist" | The tool cannot know this from public data. |

## 5. Example BD Review Workflow

1. Pick one target biotech/company.
2. Show the model's asset valuation and key assumptions.
3. Show the likely acquirer ranking.
4. Ask whether the strategic logic makes sense.
5. Ask what hidden blockers the model misses.
6. Ask whether a full acquisition, option, license, regional deal, or partnership is realistic.
7. Ask what data fields should be added.
8. Convert feedback into model rules/config fields.
9. Rerun the screen and compare ranking changes.

## 6. Specific Questions to Ask a BD Person

### Strategic Fit

1. What would make this asset strategically urgent rather than merely interesting?
2. Is this a real pipeline gap for the buyer, or already covered internally?
3. Which sub-indications matter most for buyer fit?
4. Does modality fit mean the buyer can develop it, manufacture it, commercialize it, or all three?

### Deal Process

5. What public signal suggests this target is actually willing to transact?
6. Would this buyer act before or after the next catalyst?
7. Would the buyer prefer full acquisition or an option/license first?
8. What hidden process blockers would not show up in public data?

### Valuation

9. Which valuation metric would a buyer actually anchor on here?
10. Would rNPV, peak sales, platform value, or strategic scarcity drive price?
11. How much should the model haircut value for diligence uncertainty?
12. What would be an obvious walk-away price?

### Legal / Control Rights

13. Are there known royalties, ROFR/ROFN, options, or co-development rights?
14. How should split regional rights affect acquisition probability?
15. Would change-of-control provisions matter?
16. Is clean asset title required for this buyer?

### Commercial Fit

17. Does the buyer already have the commercial infrastructure?
18. Would the buyer get synergy from existing prescriber relationships?
19. Is this an attractive launch for the buyer's scale?
20. Would the buyer see this as franchise defense?

### CMC / Technical Risk

21. Would manufacturing complexity be a blocker?
22. Which buyers are credible owners of this modality?
23. Does CMC risk suggest partnership rather than acquisition?

### Competitive Dynamics

24. Who are the alternative bidders?
25. Would a competitor buying this target threaten the buyer?
26. Is the asset scarce enough to trigger competitive tension?

### Seller Willingness

27. Does cash runway pressure really create willingness here?
28. Are investors likely to support a sale?
29. Would management prefer standalone development?

### Model Credibility

30. Which variables are missing before you would trust an acquirer ranking?
31. Which current assumptions feel naive?
32. What would make this useful in a BD meeting?
33. What would make it embarrassing?

## 7. What I Want Feedback On

Checklist:

- Are the right variables included?
- Are the M&A weights directionally right?
- Are the acquirer profiles realistic?
- Which fields are missing?
- Which assumptions are unrealistic?
- Which outputs are most useful?
- Which outputs should be removed or caveated?
- What would make this useful to BD?
- What would make it not credible?

## 8. Final Ask Script

"I built a prototype tool that tries to value biotech assets and estimate which companies may be logical acquirers. The part I most want your feedback on is the M&A logic: strategic fit, deal likelihood, hidden blockers, and what real BD teams look at that public investors often miss. I am not asking you to validate the code; I am trying to understand what assumptions would make this more realistic."
