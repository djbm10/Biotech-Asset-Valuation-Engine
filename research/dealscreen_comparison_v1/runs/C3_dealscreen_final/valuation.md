# C3 preliminary valuations (AI-SIMULATED, INTERNAL DEVELOPMENT; HYPOTHETICAL inputs)

Status: PREVIEW configs written by `bve-dealscreen value-config` and run with `bve-dealscreen-value`
(n-sims 5000, seed 42). Nothing here is human-approved: finalist approval/selection is NOT COMPLETED BY HUMAN,
so the tool's own `value` step (which needs SELECTED finalists) was not used.
Perspective: asset-level rNPV to the owner of U.S./ex-China economics; "acquisition"/"license" rows are the
BUYER's net value after paying the hypothetical deal terms. Company balance sheet not modelled.

## Inputs
Protocol placeholders (`inputs/valuation_market_inputs_hypothetical.yaml`): 6,000 pts/yr, $150k net price,
15% peak penetration, 5 yrs to peak, 12-yr patent life, 10% discount; Ph2 $60M/2y/35%, Ph3 $180M/3y/50%,
BLA $20M/1y/90%; license $100M upfront + 12% royalty + $500M milestones; acquisition $400M upfront.
C3 labelled assumptions (`assumptions_C3.yaml`): COGS 12%, SG&A 40% launch / 25% mature, royalty paid by
seller 0; milestone split $100M at success of the first remaining phase + $400M at approval; LM-302 and
QLS31905 treated as entering U.S. Phase 3 (China Phase 3 assumed sufficient – a strong assumption), SKB315 as Phase 2.
Engine default: 0.80 compliance factor on peak sales.

## Results ($M)
| Program | Path | Bear | Base | Bull | P(approval) | MC mean |
|---|---|---:|---:|---:|---:|---:|
| LM-302 (CL-07) | standalone | -160 | -68 | 94 | 45% | -65 |
| LM-302 | acquisition (buyer) | -560 | -468 | -306 | | |
| LM-302 | U.S. license (buyer) | -330 | -346 | -304 | | |
| QLS31905 (CL-20) | standalone / acq / license | identical to LM-302 (same stage and inputs) |||||
| SKB315 (CL-27) | standalone | -89 | -74 | -13 | 15.75% | -73 |
| SKB315 | acquisition | -489 | -474 | -413 | | |
| SKB315 | U.S. license | -214 | -244 | -251 | | |

## Arithmetic checks (base)
- Peak sales = 6,000 × 150,000 × 0.15 × 0.80 = $108M ✓.
- P(approval): Ph3 0.50 × BLA 0.90 = 0.45 ✓; SKB315 0.35 × 0.50 × 0.90 = 0.1575 ✓.
- LM-302 standalone: prob-adjusted operating PV 212 × 0.45 = 95.4 (engine 96) − trial cost PV 163.2 = −67.2 → −68 ✓ (rounding).
  Trial cost PV: Ph3 $180M spread over 3 y = 156.02 (engine) + BLA 14.33 × 0.5 = 7.16 → 163.2 ✓.
- Acquisition: −68 − 400 = −468 ✓; SKB315 −74 − 400 = −474 ✓.
- License cost PV: 163.2 + 100 + 100 × 0.50 / 1.1^3 (37.6) + 400 × 0.45 / 1.1^4 (122.9) = 423.7 ✓.
  SKB315: 101.8 + 100 + 100 × 0.35 / 1.1^2 (28.9) + 400 × 0.1575 / 1.1^6 (35.6) = 266.3 ✓ (engine 266.2).
- License value: 77 − 423.7 = −346.7 → −346 ✓.

## Not reproduced by hand
- Operating PV of 212 (and 175 for SKB315): depends on the engine's uptake curve, margin ramp and LOE tail; read from valuation.json, not recomputed.
- License operating PV 172 vs standalone 212: royalty at 12% of revenue reduces operating profit by more than 12% of 212; exact royalty base not reconstructed.
- Bear/bull shocks: engine scenario definitions; not reproduced. ANOMALY: for the license path bear > base (LM-302 −330 vs −346) and for SKB315 license bull < base; I did not see the tool flag this in the bve-dealscreen-value run. Treat license scenario ranges as unreliable.
- SKB315 standalone trial PV 101.8 not decomposed.

Conclusion: at the shared hypothetical inputs every deal structure is value-destroying for the buyer
(peak sales only $108M against $400M/$100M+ upfronts). This reflects the placeholder market, not any program.
