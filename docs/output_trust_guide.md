# BVE Output Trust Guide

**Version:** 1.0 | **Date:** 2026-05-26

---

This document answers a single question: **I got a number from BVE. Should I trust it?**

Every output BVE produces carries a confidence level. The levels are:

| Level | Meaning |
|---|---|
| **Validated** | Backtested against held-out historical data; methodology tested with real outcomes. |
| **Model-dependent** | Mathematically correct given the inputs; accuracy depends entirely on input quality. |
| **Directional** | Useful for relative ranking and screening; not reliable as an absolute forecast. |
| **Analyst-judgment** | Structured template for expert assessment; no empirical calibration. |
| **Not yet actionable** | Present in the output but statistically underpowered or methodologically incomplete. |

---

## Score-by-Score Trust Calibration

| Output | Where it appears | Confidence | Validated? | What to do with it |
|---|---|---|---|---|
| **rNPV (base case)** | `valuation.json`, decision report | Model-dependent | Methodology validated; input assumptions are not | Read the tornado chart first. Identify the top 2 sensitivity drivers and stress-test them before using the number. |
| **P(approval)** | `valuation.json`, morning screen | Directional | POS model: Brier 0.2127, AUC 0.74 (N=99, oncology only) | Use for relative ranking across candidates, not as an absolute probability forecast. Non-oncology TAs are extrapolated — flag and verify. |
| **NAV / share** | `valuation.json`, decision report | Model-dependent | Depends on balance-sheet inputs | Always verify the cash and share count against the most recent 10-Q before acting. |
| **Implied upside (morning screen)** | Morning screen section 2 | Model-dependent | Same as rNPV | Treat as a screen flag, not a target price. Verify whether the valuation config is screening-grade or capital-candidate-grade. |
| **M&A probability score** | M&A section, morning screen | Directional | Not statistically validated against deal outcomes | Use to prioritise targets for deeper diligence. Do not cite as a deal probability in any external document. |
| **Acquirer fit score** | Evaluate-target report, morning screen | Directional | Acquirer profiles manually curated; not backtested | Use to structure the conversation about likely buyers, not to assert which buyer will move. |
| **Management quality composite** | Evaluate-target report | Analyst-judgment | No empirical calibration | Use as a structured diligence checklist. The composite number is less important than the individual component flags and the auto-generated questions. |
| **Management receptivity** | Evaluate-target report | Analyst-judgment | No empirical calibration | Treat as a starting hypothesis. Requires corroboration from public statements, partnership history, and proxy filings. |
| **Input integrity score** | Evaluate-target report | Model-dependent | Freshness rules validated; scores not | A low score means data is stale — investigate. A high score does not mean the assumptions are correct. |
| **Thesis strength** | Intelligence OS, weekly runner | Directional | Methodology validated; depends on claim population | Meaningful only when ≥ 3 claims are resolved. Single-claim thesis strength is noise. |
| **Morning screen ranking** | Morning screen | Directional | Depends on ops.db population | Relative rank within the tracked universe only. Assets not in ops.db are invisible to the screen. |
| **Backtest alpha (historical replay)** | Replay summary | Not yet actionable | N ≈ 60–130, p > 0.10 | Do not use as evidence of forward alpha. The signal is directionally positive but statistically underpowered. Extend the date range before drawing conclusions. |
| **POS backtest (Brier / AUC)** | `bve-validate` output | Validated | N=99, oncology Phase 2–3 | The most reliable validation metric in the system. Trust the directional conclusion; do not extrapolate outside oncology without recalibrating. |
| **Model validation grade** | `bve-validate` output | Validated | Systematic; see validation registry | The highest-confidence signal in BVE. If the grade is below B, treat all downstream outputs with extra caution. |

---

## What "Validated" Means in This System

Validated does **not** mean the model is correct. It means the methodology has been tested against historical data with known outcomes, the results have been documented, and the test is reproducible.

BVE's primary validation surface is the POS backtest (`research/data/oncology_phase_transitions.csv`, N=99). The Brier score of 0.2127 represents a ~15% skill improvement over a no-skill baseline. That is meaningful for relative ranking; it is not sufficient for individual-asset probability estimates used in capital decisions.

The historical replay is implemented correctly but is statistically underpowered. The current N ≈ 60 decisions is below the ~111 needed for p < 0.10. The replay infrastructure is trustworthy; the conclusions from the current data are not yet.

---

## Five Things Not to Do With BVE Outputs

1. **Do not cite M&A probability scores as deal forecasts.** The score is a structured ranking signal, not a calibrated probability. Saying "BVE gives SRPT a 72% acquisition probability" misrepresents the output.

2. **Do not use screening-grade configs for capital decisions.** Screening configs use industry defaults for peak sales and patient counts. These can be off by 5–10x for specific assets. Always check `_meta.screening_grade` before using a valuation in a decision context.

3. **Do not act on the morning screen without checking staleness.** The screen flags assets based on stored outputs. If the underlying valuation was run on stale inputs (>90 days), the ranking signal is degraded. Check the "Stale / Low-Integrity Inputs" section before acting.

4. **Do not treat management quality scores as diligence conclusions.** The seven-component formula is a structured placeholder for analyst judgment. A composite of 0.80 means the analyst-supplied inputs are strong — it does not mean management quality has been independently verified.

5. **Do not extend backtest alpha claims outside the current methodology.** Current replay results (mean return +3.3%) are directionally positive but not statistically significant. Extending the claim to say "BVE has demonstrated positive alpha" would be premature.

---

## Pre-Action Checklist

Before acting on any BVE output in a real decision context:

- [ ] Identify the confidence level of the specific output you are using (see table above).
- [ ] Check whether the underlying valuation config is `screening_grade: true` or has been through a capital-candidate review.
- [ ] Verify the balance-sheet inputs (cash, shares, burn rate) against the most recent public filing.
- [ ] Run `bve-validate` and confirm the overall model grade is B or above.
- [ ] Read `docs/model_limitations.md` for the specific limitation relevant to your decision.
- [ ] If the output is being used for M&A diligence: corroborate with at least one external source before presenting.

---

## Relationship to the Three Mode Levels

The trust levels above interact with the product's three operating modes:

| Mode | What it unlocks | Trust floor required |
|---|---|---|
| Screening | Universe ranking, morning screen | Directional outputs acceptable |
| Capital Candidate | Sizing recommendations, shadow book entry | Model-dependent outputs must be verified; no screening-grade configs |
| Shadow Book | Paper position tracking, P&L | All material inputs must be non-stale; human sign-off required |

See `docs/PRODUCT_SPEC.md` for the full mode governance table.
