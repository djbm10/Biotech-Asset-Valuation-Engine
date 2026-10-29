# PROPOSAL (not applied): valuation input and output transparency

**Status:** PROPOSED. Needs Lane 1 (quant + clinical) sign-off. Nothing here has been changed.
**Origin:** AI-simulated BD Finance analyst, cycle A3 (`research/dealscreen_product_program/
analyst_simulation/ANALYST_FINDINGS_A3.md`, frozen c589367). INTERNAL DEVELOPMENT. The findings
were reproduced by engineering; they are not human-validated.

| # | Finding | Root cause (verified) | Proposed change | Risk |
|---|---|---|---|---|
| P1 | User-set `market_model.compliance_rate` (and `gross_to_net_rate`, `price_basis`) has no effect; peak sales carry an invisible ×0.80 | `run_asset._build_objects` constructs `MarketModel` from 13 named keys; others are dropped silently; `MarketModel.compliance_rate` defaults to 0.80 | Either pass these keys through, or fail closed on unread `market_model` keys (DealScreen already does the latter for its own path, cycle A4 J1). Print the compliance factor in the console summary | Passing through changes results for any config that already sets these keys (today ignored) — needs a scan of `examples/configs` first |
| P2 | Top-level keys such as `market:` in 10 example configs are ignored | Same loader; no unknown-key check | Fail closed, or migrate the 10 configs | Example outputs may change if `market:` was meant to be read |
| P3 | `gross_revenue_pv_millions` / `prob_adj_revenue_pv_millions` do not equal a revenue PV a reader can reproduce (A3: 604 vs ~1,100 by hand; rNPV = that figure − cost PV) | Field appears to hold a post-cost/post-margin figure under a revenue label (needs engine owner to confirm) | Rename or add the gross revenue PV; document the bridge from revenue to rNPV in `valuation.json` | Label change only if the math is confirmed correct |
| P4 | `assumptions.key_assumptions` attaches authoritative-looking sources (e.g. "Damodaran", "SEER, IQVIA") and lists a 30% gross-to-net and a POS methodology that the run did not use | Static assumption table, not generated from the run's actual inputs | Generate the table from the run's inputs; mark user inputs with the user's label (e.g. HYPOTHETICAL) | Report text only |
| P5 | Tornado rows "Peak Sales ±30%" and "Peak Penetration ±30%" identical; "Gross-to-Net ±10pp" varies an unused input; "Competition (+1/+2)" has both values below base | Sensitivity list fixed, not conditioned on which inputs are active | Drop inactive rows; label one-sided shocks | Report text only |
| P6 | A 1-year patent life still yields material revenue PV | Post-patent (LOE) tail applied by default | Disclose the tail in the summary and memo | Disclosure only |
| P7 | `valuation.json` `inputs.deal_economics` is null on a deal run; `net_ownership` 1.0 shown under a 15% royalty | Deal attached after construction in the prototype path; inputs snapshot taken before | Snapshot deal terms into `inputs` | Prototype path only |

DealScreen-side mitigations already in place (no engine change): unread keys refused on the
DealScreen paths; the compliance factor disclosed on every DealScreen valuation display; the
perspective line states the discount rate and whether deal terms were applied.
