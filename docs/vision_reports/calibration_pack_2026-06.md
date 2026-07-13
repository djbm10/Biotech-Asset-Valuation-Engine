# POS Model Validation Report

**Generated:** 2026-06-22  
**Model:** pos_model  
**Total records:** 145  
**TAs with data:** 1 of 7  

_Scope: probability calibration & discrimination quality only — not trading return / backtest performance._

## Summary metrics

| Metric | Value | Baseline |
|--------|-------|----------|
| Brier Score | 0.2339 | 0.2500 (no skill) |
| Brier Skill | +0.0161 | 0.0000 |
| AUC-ROC | 0.6941 | 0.5000 (random) |
| ECE | 0.1404 | — |

## Brier decomposition (Murphy)

Binned identity: Brier = Reliability − Resolution + Uncertainty.

| Component | Value | Direction |
|-----------|-------|-----------|
| Reliability | 0.0236 | lower is better |
| Resolution | 0.0295 | higher is better |
| Uncertainty | 0.2499 | irreducible |
| Binned Brier | 0.2440 | = REL − RES + UNC |

## Per-TA calibration (in-sample)

| TA | Phase | N | Base Rate | Model Mean | Actual Rate | Brier | AUC | ECE | Dir |
|-------|-------|---|-----------|------------|-------------|-------|-----|-----|-----|
| oncology | phase_2 | 79 | 25% | 27% | 44% | 0.261 | 0.668 | 0.170 | under |
| oncology | phase_3 | 66 | 50% | 57% | 59% | 0.201 | 0.829 | 0.150 | calibrated |

_* N < 20: low-confidence estimate_

## Interpretation

Brier skill > 0 indicates the model outperforms the no-skill baseline. AUC > 0.55 indicates meaningful discrimination. ECE < 0.05 indicates well-calibrated probability estimates. Direction 'calibrated' = |predicted - actual| ≤ 5pp.
