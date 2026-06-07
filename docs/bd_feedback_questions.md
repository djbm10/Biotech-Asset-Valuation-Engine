# Biotech M&A / Acquirer Model — BD Feedback Questions

This document contains 50 questions to ask a biotech/pharma BD, search & evaluation, or corporate strategy person. The goal is to improve the M&A/acquirer model with real-world deal logic.

**Use case:** Walk through one target and one or more likely acquirers, then mark each answer as either a model input, a model weight change, a diligence caveat, or a missing data field.

## How to Use This in a BD Conversation

| Step | What to do | Output to capture |
|---|---|---|
| 1 | Show the target, asset valuation, and top acquirer list. | Which outputs are plausible versus wrong. |
| 2 | Ask the must-ask questions first. | Missing fields and immediate deal blockers. |
| 3 | Ask the good-to-ask questions if the BD person has time. | Better weights, buyer behavior, and structure assumptions. |
| 4 | Ask advanced questions only after the basic strategic logic is clear. | Credibility threshold for a BD-facing model. |
| 5 | Convert answers into structured config changes. | Acquirer profile edits, rights/control flags, seller-willingness inputs, and deal-structure rules. |

## Answer Coding

| Code | Meaning |
|---|---|
| Add field | The model needs a new structured input. |
| Change weight | The variable exists, but the importance is wrong. |
| Add caveat | The output should warn users before over-interpreting a score. |
| Add source | The assumption needs a source reference or freshness date. |
| Manual override | Public data is insufficient; BD review should override the model. |

## Must Ask

### Strategic Fit

1. For this asset, what would make a buyer view it as strategically urgent rather than merely interesting?
2. Is the target indication actually inside the buyer's focus area, or only superficially adjacent?
3. Does the buyer have an internal program that already addresses this gap?
4. Would this asset defend an existing franchise, create a new franchise, or just add pipeline optionality?
5. Which therapeutic sub-area matters most for buyer fit?
6. How much does modality fit matter versus therapeutic-area fit?
7. Which buyers are credible technical owners of this modality?
8. What would make a buyer reject this asset despite strong apparent fit?

### Deal Process

9. What public signals suggest the target is willing to transact?
10. What non-public signals would BD teams care about most?
11. Would a buyer likely act before or after the next clinical/regulatory catalyst?
12. What would trigger a formal process?
13. Would the target likely run an auction or negotiate bilaterally?
14. What signs indicate management wants to remain independent?

### Valuation

15. What valuation anchor would a buyer use: rNPV, peak sales, comps, platform value, or strategic scarcity?
16. What control premium would be reasonable for this type of target?
17. How should the model haircut value for clinical diligence risk?
18. How should the model haircut value for commercial uncertainty?
19. What would be an obvious walk-away price?
20. Would a buyer pay for pipeline/platform optionality beyond the lead asset?

### Legal / Control Rights

21. What deal blockers would not show up in market data?
22. How should the model treat existing partnerships?
23. Does an existing partnership increase acquisition probability or reduce it by satisfying the buyer's need?
24. How should split regional rights affect acquisition probability?
25. How should royalty stacks affect value and buyer appetite?
26. Which control clauses matter most: ROFR, ROFN, option rights, co-development consent, change-of-control payments?

### Seller Willingness

27. Does cash runway pressure actually make this seller more likely to sell?
28. Would investors support a sale at today's valuation?
29. Is the board likely to prefer financing, partnering, or selling?
30. What management incentives could block a deal?

## Good To Ask

### Acquirer Behavior

31. How predictive is prior BD history for future behavior?
32. Which buyers say they want assets like this but rarely transact?
33. Which buyers are more likely to license or option rather than acquire?
34. Which buyers avoid early-stage risk even when strategic fit is strong?
35. Which buyers can move quickly without a formal auction?

### Commercial Fit

36. Does the buyer have the right salesforce and prescriber access?
37. Would this asset leverage existing market access infrastructure?
38. Would launch complexity make the buyer less interested?
39. Does the asset require a different commercial model than the buyer usually runs?
40. Would the buyer view this as a US-only, ex-US, or global opportunity?

### CMC / Technical Risk

41. Would manufacturing complexity be a gating issue?
42. Does the buyer have internal CMC capability for this modality?
43. Would tech transfer risk push the buyer toward partnership instead of acquisition?
44. What CMC diligence items should be modeled explicitly?

### Competitive Dynamics

45. Who are the most likely alternative bidders?
46. Would a competitor buying this target be strategically threatening?
47. Is the asset scarce enough to create auction tension?
48. Are there similar assets that would be easier or cheaper to buy?

## Advanced / If Time Allows

### Model Credibility

49. What fields would you need before trusting an acquirer ranking in a BD meeting?
50. What output from this tool would be most useful, and what output would you ignore?
