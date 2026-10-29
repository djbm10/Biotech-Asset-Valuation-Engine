# Preliminary valuation (workflow C2, AI_PREPARED, HYPOTHETICAL inputs, UNVALIDATED)

DealScreen's own `value` step REFUSED to run: valuation requires a HUMAN-approved finalist selected
for valuation (AI_PREPARED can only record CANDIDATE_NOT_APPROVED). Human approval: NOT COMPLETED BY HUMAN.
So these numbers come from the tool's documented PREVIEW path: `bve-dealscreen value-config`
(writes the exact config the handoff would run) + `bve-dealscreen-value` (PROTOTYPE CLI, n-sims 2000, seed 42).
The memo therefore correctly says "No valuation was run" through DealScreen. Configs + JSON: `valuation_runs/`.

## Inputs
Shared hypothetical (protocol file): 6,000 pts/yr, $150,000 net price, peak penetration 0.15, 5 yrs to peak,
12 yr patent life, discount 10%; Ph2 $60M/2y/p=0.35; Ph3 $180M/3y/p=0.50; NDA $20M/1y/p=0.90;
license $100M upfront + 12% royalty + $500M milestones; acquisition $400M upfront.
C2's own labelled assumptions: COGS 15%; SG&A 35% launch / 20% mature; milestone split $200M on Ph3 success +
$300M on approval; modality `biologic`; no POS adjusters; asset-level (no balance sheet); stage per row:
ATG-022 and JS107 treated as entering Ph3 (ATG-022 is really Ph2 expansion per web reports; vendor says Ph3), SKB315 as entering Ph2.
Engine default (not settable): 0.80 compliance factor on peak sales.

## Results ($M, rNPV)
| Program | P(approval) | Peak sales | Bear | Base (asset-holder, no deal) | Bull | Acquisition (buyer, base) | U.S./ex-China license (buyer, base) |
|---|---:|---:|---:|---:|---:|---:|---:|
| ATG-022 (CL-16) | 0.45 | 108 | −160 | −65 | 100 | −465 (bear −560 / bull −300) | −351 (bear −341 / bull −301) |
| JS107 (CL-24) | 0.45 | 108 | −160 | −65 | 100 | −465 (−560 / −300) | −351 (−341 / −301) |
| SKB315 (CL-27) | 0.1575 | 108 | −89 | −73 | −11 | −473 (−489 / −411) | −227 (−203 / −231) |

ATG-022 and JS107 are identical because the inputs are identical: the shared hypothetical inputs do not
differentiate programs. Perspective: "base" = asset holder bearing all remaining development cost; deal columns =
buyer after paying the deal terms and bearing full development (cdev_cost_share 1.0).

## Arithmetic I can reproduce
- Peak sales = 6,000 × $150,000 × 0.15 × 0.80 = $108.0M ✓ (all three).
- P(approval) Ph3 start = 0.50 × 0.90 = 0.45 ✓; Ph2 start = 0.35 × 0.50 × 0.90 = 0.1575 ✓.
- Acquisition = base − 400: −65 − 400 = −465 ✓; −73 − 400 = −473 ✓ (upfront undiscounted at t=0).
- License cost PV (ATG-022) = trial PV 163.2 + upfront 100 + 200 × 0.50 / 1.1^3 (75.1) + 300 × 0.45 / 1.1^4 (92.2) = 430.5 ✓ (engine 430.5).
- License cost PV (SKB315) = 101.8 + 100 + 200 × 0.175 / 1.1^5 (21.7) + 300 × 0.1575 / 1.1^6 (26.7) = 250.2 ✓.
- Base rNPV = P-adjusted revenue PV less cost PV holds only after the engine's EBIT margin step: ATG-022 98.0 (P-adj revenue PV) → EBIT then minus 163.2.

## What I cannot reproduce by hand
- Trial-cost PV (163.2, 101.8) and revenue PV (218, 180): the engine's within-phase cost timing and uptake curve shape are internal.
- License revenue PV (177 vs 218 × 0.88 = 191.8): royalty base/timing differs from my simple calculation; not reconciled.
- Bear/bull: engine-internal scenario shocks (e.g. bear P = 0.2205, peak 59; bull P = 0.6435, peak 162 for Ph3); I did not set them.
- SKB315 license bull (−231) below base (−227): out-of-order result; with higher P, more milestones/royalties are paid. Real arithmetic per the README's explanation of such cases, not verified by me.
Every number is reproducible by re-running the saved config with the same CLI and seed.

## Reading
At the shared placeholder market (peak $108M), none of the three is value-positive for a buyer under either
structure; the market assumption, not the asset, drives this. No transaction conclusion should be drawn.
