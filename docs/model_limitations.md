# Model Limitations

**Version:** 1.0 | **Date:** 2026-05-15

This document provides a frank assessment of what the BVE does not do well and where
outputs should not be trusted without additional validation.

---

## Asset-Level Limitations

### POS Model

| Limitation | Impact | Mitigation |
|-----------|--------|-----------|
| N=99 (oncology only) | Cannot generalise to other TAs reliably | Flag outputs in non-oncology TAs as RESEARCH_GRADE |
| Base rates from aggregated literature | May not reflect current regulatory environment | Annual review of base rates vs. FDA approval data |
| Log-odds adjusters are evidence-informed priors, not statistical estimates | Adjusters may be over- or under-specified | Calibration feedback loop via `calibration_feedback_loop.py` |
| No pathway-specific differentiation (e.g., Accelerated Approval vs. Regular) | Approval pathway timing not captured | TrialDesignFeatureSet partially addresses; needs expansion |

### Revenue Model

| Limitation | Impact | Mitigation |
|-----------|--------|-----------|
| Aggregate TAM, not patient-level | Misses payer mix, adherence, and indication-specific dynamics | Add `payer_access.py` inputs where available |
| Peak penetration is subjective | Wide range; dominates rNPV sensitivity | Sensitivity analysis mandatory; range should be stated |
| LOE erosion uses fixed modality profiles | Individual drugs may erode faster or slower | Allow per-drug override in YAML config |
| No geography modelling by default | US-centric unless multi-geography MarketModel used | Use geography.py for ex-US revenue |

---

## Portfolio-Level Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|-----------|
| No cross-asset correlation modelling | Portfolio Brier/VaR understated | Use `correlations.py` Gaussian copula in Monte Carlo |
| Position sizing uses simplified Kelly | May oversize in concentrated, illiquid markets | Apply `PortfolioConstraints` hard limits |
| No options or hedging strategies | Downside risk analysis is unhedged | Incorporate options where available |

---

## M&A Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|-----------|
| UNVALIDATED — no deal universe backtest | Precision unknown | Do not use for capital decisions until IC_REVIEW_GRADE |
| Acquirer fit is rules-based, not learned | May miss non-obvious acquirers | Expand strategic_fit module; validate against historical deals |
| Seller willingness is estimated, not observed | Probability of seller accepting is unreliable | Supplement with relationship intelligence |

---

## Data Limitations

| Source | Limitation |
|--------|-----------|
| yfinance | Not PIT-safe; not commercially licensed; survivorship bias |
| ClinicalTrials.gov | Sponsor-updated; not fully PIT-safe before 2022 |
| Biomedtracker base rates | Licensed; not available in open-source mode |
| IQVIA estimates | Survivorship bias; estimates revised without history |

---

## What to Do When Unsure

1. Check the `ValidationRegistry` grade for the model you're using.
2. Run sensitivity analysis on the top 3 parameters (tornado chart).
3. Apply at least 3 named stress scenarios from the scenario library.
4. Require bear cases and kill criteria before escalating to active pursuit.
5. Document assumption owners and check for stale inputs.
