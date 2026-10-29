# Preliminary valuation (workflow A, AI-SIMULATED / INTERNAL DEVELOPMENT)

**Perspective:** the hypothetical U.S. buyer (in-licensor / acquirer). **All market, development and deal numbers are HYPOTHETICAL placeholders** from `inputs/valuation_market_inputs_hypothetical.yaml`; items marked ANALYST are my own assumptions. None is a sourced fact. Availability of all three programs is NOT evidenced — these are "if available" screens. Live formulas: `workbook.xlsx`, sheets `Val_CL-07`, `Val_CL-16`, `Val_CL-27` (columns B/C/D = Base/Bear/Bull; the workbook was written with openpyxl and has not been recalculated in Excel — values below are from a Python mirror of the same formulas).

## Method (same for all)
- Peak sales = 6,000 patients × $150,000 × penetration (0.15 base; ANALYST bear 0.5×, bull 1.5×) = **$135M base / $67.5M bear / $202.5M bull**.
- Launch year L = sum of remaining phase durations (from now = year 0). Sales year k (1..12) at year L+k = peak × min(k/5, 1); zero after 12 years.
- Cumulative PoS = product of remaining phase PoS (bear: each phase PoS × 0.8, ANALYST).
- R&D cost: each phase cost spread evenly over its duration, × probability of reaching that phase.
- EBIT = revenue × 40% operating margin (ANALYST) × PoS.
- Licence: CF = −cost + rev×PoS×(0.40 − 0.12 royalty) − $500M milestones×PoS at year L (ANALYST: all milestones paid at launch); then −$100M upfront at t=0.
- Acquisition: CF = −cost + rev×PoS×0.40; −$400M upfront at t=0.
- Discount: end-of-year, 10%: CF_t/(1.10)^t. rNPV = Σ discounted CF − upfront.

## Results ($M, buyer rNPV)
| Program | Start | L | PoS (base/bear) | Licence base / bear / bull | Acquisition base / bear / bull |
|---|---|---|---|---|---|
| LM-302 (CL-07) | Phase 3 | 4 | 0.45 / 0.288 | −349.8 / −333.9 / −319.9 | −470.5 / −527.3 / −427.7 |
| ATG-022 (CL-16) | Phase 3 | 4 | 0.45 / 0.288 | −349.8 / −333.9 / −319.9 | −470.5 / −527.3 / −427.7 |
| SKB315 (CL-27) | Phase 2 | 6 | 0.1575 / 0.0806 | −224.3 / −206.2 / −215.7 | −472.5 / −481.5 / −460.1 |

Worked check, LM-302 base: PV(prob-weighted cost) = 60/1.1 + 60/1.1² + 60/1.1³ + (20×0.5)/1.1⁴ = 156.0; PV(unrisked revenue) = Σ_{k=1..12} 135·min(k/5,1)/1.1^(4+k) = 475.2.
Acquisition = −156.0 + 475.2×0.45×0.40 − 400 = **−470.5**. Licence = −156.0 + 475.2×0.45×0.28 − 500×0.45/1.1⁴ (153.7) − 100 = **−349.8**.
SKB315 base: PV cost 97.2, PV unrisked revenue 392.7, PoS 0.1575 → acquisition −97.2 + 392.7×0.1575×0.40 − 400 = **−472.5**; licence −97.2 + 392.7×0.1575×0.28 − 44.5 − 100 = **−224.3**.

## Reading
- With the shared placeholder market ($135M peak), no deal at the placeholder terms clears zero: the market is too small for a $100M+$500M licence or $400M acquisition. LM-302 and ATG-022 are identical because the inputs are generic (no program-specific data were used).
- Artifact: bear licence is *less* negative than base because PoS-weighted milestones fall with PoS — a quirk of paying milestones only on success, not a real upside.
- Licence beats acquisition in every case (lower fixed outlay). Breakeven needs roughly 3–4× the placeholder peak sales or much lower upfront — to be tested once real epidemiology (CLDN18.2-high ~35–40% of G/GEJ; global, not just previously treated U.S. patients) replaces the placeholder.
- Seller's perspective was not modelled.
