# Validation Standard

**Version:** 1.0 | **Enforced from:** 2026-05-15

This document defines the minimum gates that must be passed before any model output
is labelled with a grade above UNVALIDATED.

---

## Validation Grades

| Grade | Meaning | Allowed uses |
|-------|---------|-------------|
| `UNVALIDATED` | No backtest or calibration performed | Internal exploration only |
| `RESEARCH_GRADE` | Some backtesting; not peer-reviewed | Research memos; do not size capital |
| `SCREENING_GRADE` | Passes minimum gates on a limited dataset | Watchlist classification; initial triage |
| `IC_REVIEW_GRADE` | Passes primary gates; ready for IC-level discussion | IC memos; diligence initiation |
| `DECISION_GRADE` | All gates pass; holdout validated; human-reviewed | Trade sizing; M&A active pursuit |

Any output that is not `DECISION_GRADE` must display:

> This output is [GRADE]-grade only. Do not use for trade sizing or acquisition probability.

---

## Minimum Gates by Model

### POS Model

```yaml
pos_model:
  min_n: 300
  max_ece: 0.08          # Expected Calibration Error
  max_brier: 0.22
  min_auc: 0.65
  required_holdout: true
  holdout_fraction: 0.20
```

Current status: N=99 (SCREENING_GRADE — N < 300 required for IC_REVIEW_GRADE)

---

### M&A Ranking

```yaml
mna_ranking:
  min_deal_universe_n: 150
  require_non_deal_controls: true
  precision_at_10_min: 0.20
  buyer_identification_top3_min: 0.40
```

Current status: UNVALIDATED

---

### Catalyst Model

```yaml
catalyst_model:
  min_events_n: 200
  expected_move_direction_accuracy_min: 0.55
  calibration_error_max: 0.10
```

Current status: UNVALIDATED

---

### Valuation Model

```yaml
valuation_model:
  launch_analog_backtest_min_n: 25
  median_peak_sales_error_max_pct: 35
```

Current status: RESEARCH_GRADE (N=2 historical cases)

---

## Grade Promotion Rules

1. A model must pass ALL gates for its target grade — partial compliance is not permitted.
2. Grade is stored in `ValidationRegistry`; it cannot be self-assigned by the model code.
3. Holdout data must be held out *before* any model training or calibration.
4. Grade is invalidated whenever:
   - Core model parameters change (Lane 1 change with `core_output_changed: true`)
   - Dataset changes (N drops, source changes)
   - 12 months pass without re-validation

---

## Grade Labels in Output

Every public output must include a `validation_badge` field:

```json
{
  "validation_badge": {
    "model": "pos_model",
    "grade": "SCREENING_GRADE",
    "last_validated": "2026-05-15",
    "warning": "This output is SCREENING_GRADE only. Do not use for trade sizing or acquisition probability."
  }
}
```
