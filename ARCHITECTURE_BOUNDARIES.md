# Architecture Boundaries

**Version:** 1.0 | **Enforced from:** 2026-05-15

These boundaries define what each subsystem is allowed to do, what it must not do,
and which modules are the canonical source of truth for each concern.

---

## Boundary 1: Valuation vs Intelligence

| Concern | Owner | Boundary rule |
|---------|-------|---------------|
| rNPV computation | Lane 1 (`valuation_engine`) | Intelligence layer MUST NOT call `compute_rnpv` directly |
| Thesis claims | Lane 3 (`knowledge_layer`) | Valuation engine MUST NOT read from ops.db |
| POS estimate | Lane 1 (`pos_model`) | Intelligence layer reads POS via `ValuationOutput`, never recomputes |
| Weekly scoring | Lane 3 (`weekly_runner`) | Only uses `ValuationOutput` artifacts, not engine internals |

## Boundary 2: Revenue vs Deal Economics

| Concern | Owner | Boundary rule |
|---------|-------|---------------|
| Gross commercial revenue | `revenue_model.py` | No deal parameters — revenue is pre-deal gross |
| Royalty and ownership | `rnpv_model.py` | All royalty stacking happens here, never in revenue model |
| Milestone payments | `deal_economics.py` + `cost_model.py` / `rnpv_model.py` | Payable → CostModel; Receivable → RNPVModel |

## Boundary 3: Point-in-Time vs Live

| Concern | Owner | Boundary rule |
|---------|-------|---------------|
| Historical replay | `ops/historical_replay.py` + `pit/` | Must use `known_at <= as_of_date` filter on ALL queries |
| Live operations | `ops/weekly_runner.py` + `ops.db` | Must never write replay events back to ops.db |
| Backtest snapshots | `analysis/portfolio_backtest.py` | Must use `BacktestSnapshot`, never live prices |

## Boundary 4: Model Output vs Decision Policy

| Concern | Owner | Boundary rule |
|---------|-------|---------------|
| Scores and probabilities | Lane 1/2/3 models | Output raw scores; never embed action thresholds |
| Allowed actions | `policy/policy_engine.py` | Translates scores → allowed actions per configurable policy |
| IC-ready labels | `workflow/review_state.py` | Only set after required reviewers approve |

## Boundary 5: Governance vs Computation

| Concern | Owner | Boundary rule |
|---------|-------|---------------|
| Assumption values | YAML configs + `AssumptionOwner` | Computation modules read values; governance tracks ownership |
| Expiration enforcement | `governance/assumption_review.py` | Expired assumptions surface `STALE_INPUT` warning; run is not blocked |
| Calibration results | `validation/validation_registry.py` | Stored grades cannot be set by the model itself |

## Boundary 6: Validation Grade vs Model Code

| Concern | Owner | Boundary rule |
|---------|-------|---------------|
| Validation grades | `validation/model_grade.py` | Grades are set by the validation runner, not the model |
| Grade display | `reporting/validation_badges.py` | Every public output must carry the grade badge |
| Grade requirements | `VALIDATION_STANDARD.md` | No model can declare itself DECISION_GRADE without passing all gates |

---

## Module Dependency Rules

```
Lane 4 (platform)
  → may import from Lane 1, 2, 3 for read-only access to output types
  → must NOT trigger valuation computation

Lane 3 (intelligence)
  → may import Lane 1 output types (ValuationOutput, RNPVResult)
  → must NOT import Lane 1 engine internals (ValuationEngine._*)

Lane 2 (M&A)
  → may import Lane 1 output types
  → must NOT call ValuationEngine directly (use cached ValuationOutput)

Lane 1 (valuation)
  → must NOT import from Lane 2, 3, 4
  → self-contained: models → valuation_engine → outputs
```

---

## Allowed Cross-Lane Patterns

```python
# ALLOWED: Lane 3 reads Lane 1 output artifact
output = ValuationOutput.load(run_id)
score = output.base_rnpv_millions

# ALLOWED: Lane 4 policy engine reads score from output
recommendation = policy_engine.evaluate(output, policy="bd_screening")

# NOT ALLOWED: Lane 3 triggers recomputation
engine = ValuationEngine(config)
result = engine.run()  # only Lane 1 code should do this
```
