# Preliminary valuation — Workflow B (AI-SIMULATED, INTERNAL DEVELOPMENT; NOT COMPLETED BY HUMAN)

Perspective: **the hypothetical buyer** (U.S. rights, buyer bears all remaining development cost). All figures USD millions.
Reproduce: `TMPDIR=$HOME/.cache/dealscreen_suite python3 build.py` → `valuation_table.csv`.

## Inputs
HYPOTHETICAL shared (`inputs/valuation_market_inputs_hypothetical.yaml`): 6,000 pts × $150k, peak pen 15%, 5 yrs linear ramp, 12 yrs sales from launch then zero, r=10%; phase cost/duration/PoS table; license = $100 upfront + 12% royalty + $500 milestones; acquisition = $400 upfront.
ANALYST ASSUMPTIONS (labelled, not sourced): operating margin 40% of net sales before royalty; bear = pen 10%, PoS ×0.8; bull = pen 20%, PoS ×1.2 (capped at 1); dev cost paid at start of each phase, weighted by probability of reaching it; all $500 milestones paid at approval (risked); sales mid-year discounted; ATG-022 and LM-302 treated as needing a U.S.-enabling Phase 3 + BLA (China/Australia Ph3 assumed not sufficient — open question); SKB315 needs Ph2+Ph3+BLA.

## Formula
peak = 6000×150000×pen/1e6. P_cum = Π PoS. NPV_dev = −Σ P(reach phase)·cost/(1.1)^t_start.
NPV_sales = P_cum·Σ_{y=1..12} peak·min(1,y/5)·(0.40 − royalty)/(1.1)^(T+y−0.5), T = total remaining dev years.
License: −100 − P_cum·500/(1.1)^T. Acquisition: −400.

## Results (buyer NPV, $M)
| Program | Phases left | Deal | Bear | Base | Bull |
|---|---|---|---|---|---|
| CL-16 ATG-022 | Ph3+BLA (4y) | License | −357.6 | −378.4 | −382.3 |
| | | Acquisition | −547.7 | −497.8 | −429.5 |
| CL-07 LM-302 | Ph3+BLA (4y) | License | −357.6 | −378.4 | −382.3 |
| | | Acquisition | −547.7 | −497.8 | −429.5 |
| CL-27 SKB315 | Ph2+Ph3+BLA (6y) | License | −219.6 | −240.5 | −258.0 |
| | | Acquisition | −494.2 | −488.3 | −470.3 |
Peak sales bear/base/bull = 90 / 135 / 180. P_cum base: 0.45 (Ph3 assets), 0.1575 (SKB315).

## Reading
Under the shared hypothetical market (peak ~$135M, 12-yr life) **no deal structure is NPV-positive**; the $500M milestone stack alone exceeds risked, discounted operating profit, which is why the license gets *worse* in bull (higher PoS → milestones more likely paid). ATG-022 and LM-302 are identical because the inputs do not differentiate them — this is a stage-only model, not asset-specific. Value hinges on market size (1L use, ex-U.S., other CLDN18.2 tumours) that the hypothetical inputs exclude. Break-even sensitivity and asset-specific data are open work.
