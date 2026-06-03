# User Guide

**Version:** 1.0 | **Date:** 2026-05-15

---

## Quick Start

### 1. Run a single asset valuation

```bash
bve-asset --config examples/configs/relay_rly2608.yaml --memo bd --charts
```

Output lands in `outputs/<TICKER>/`.

### 2. Run a batch of assets

```bash
bve-batch --config-dir examples/configs/ --memo bd --charts
```

### 3. Check model validation grades

```python
from bve.validation.validation_registry import get_registry
from bve.reporting.validation_badges import render_badge_block

reg = get_registry()
print(render_badge_block(["pos_model", "valuation_model", "mna_ranking"], registry=reg))
```

### 4. Apply a stress scenario

```python
from bve.scenarios.stress_runner import ScenarioLibrary, StressRunner

library = ScenarioLibrary()
runner = StressRunner(library=library)

base_params = {"years_to_approval": 7.0, "pos_phase3": 0.60, "trial_cost": 200.0}
result = runner.run("trial_delayed_18_months", base_params)
print(result.describe())
```

### 5. Evaluate deal structures

```python
from bve.deals.optimizer import DealOptimizer, DealOptimizerInput

optimizer = DealOptimizer()
inp = DealOptimizerInput(
    buyer_rnpv_full_acquisition_usd_m=800.0,
    seller_standalone_rnpv_usd_m=200.0,
    seller_cash_runway_months=18.0,
    budget_usd_m=500.0,
    min_seller_acceptance_probability=0.35,
    approval_probability=0.50,
)
result = optimizer.optimize(inp)
print(result.describe())
```

### 6. Generate red-team bear cases

```python
from bve.redteam.redteam_generator import RedTeamGenerator, AssetContext

gen = RedTeamGenerator()
ctx = AssetContext(
    asset_id="VKTX-001",
    ticker="VKTX",
    phase="phase_2",
    therapeutic_area="oncology",
    competitive_entrants=2,
    cash_runway_months=20.0,
)
report = gen.generate(ctx)
print(report.summary())
```

### 7. Check decision policies

```python
from bve.policy.decision_policy import DecisionPolicy
from bve.policy.policy_engine import DecisionPolicyEngine, ModelScores

engine = DecisionPolicyEngine()
scores = ModelScores(
    composite_score=0.78,
    asset_quality_score=0.70,
    strategic_fit_score=0.72,
    seller_willingness_score=0.45,
    expected_return=0.30,
    downside_floor_exists=True,
    liquidity_usd=15_000_000,
    catalyst_days_away=90,
    biology_score=0.70,
    capital_to_poc_usd=80_000_000,
    exit_buyer_count=4,
)
recommendations = engine.evaluate_all(scores, DecisionPolicy())
for policy_name, rec in recommendations.items():
    print(rec.describe())
```

---

## Architecture Overview

The system has four lanes. Understanding which lane you're working in matters for sign-off requirements:

| Lane | Scope | Sign-off |
|------|-------|---------|
| 1 | Core valuation (rNPV, POS, revenue, cost) | quant + clinical |
| 2 | M&A / acquisition scanner | bd + corporate strategy |
| 3 | Intelligence / thesis tracker | analyst + quant |
| 4 | Platform / governance / UI | engineering |

See `ROADMAP_LOCK.md` and `ARCHITECTURE_BOUNDARIES.md` for full boundary rules.

---

## Before Using Any Output

1. **Check validation grade.** Any model not at DECISION_GRADE carries a warning label.
2. **Check assumption staleness.** Use `AssumptionReviewer` to identify expired inputs.
3. **Run stress scenarios.** Every IC memo requires base, bear, bull + 3 stress scenarios.
4. **Generate red-team report.** Active pursuit classification requires ≥3 bear cases + kill criteria.
5. **Submit for review.** Use `ApprovalLog` to track required reviewer sign-offs.

---

## Configuration Reference

Asset configs live in `examples/configs/`. The canonical config is `relay_rly2608.yaml`.

Key YAML sections:

```yaml
asset:
  ticker: RLAY
  name: "RLY-2608"
  therapeutic_area: oncology
  modality: small_molecule

trials:
  - phase: phase_2
    success_probability: 0.40
    duration_years: 2.5
    cost_millions: 80

market_model:
  peak_penetration: 0.08
  addressable_patients_annual: 12000
  net_price_per_patient_usd: 120000
  years_to_peak: 4
  patent_life_years: 10

competition:
  - name: "Competitor A"
    status: pipeline
    launch_year_relative: 1
    peak_market_share: 0.30
    approval_probability: 0.50
```

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---------|-------------|-----|
| `STALE_INPUT` warning | Assumption expired | Review and update `AssumptionOwner` records |
| M&A classification capped at `catalyst_watch` | Expired assumptions | Fix stale inputs first |
| `UNVALIDATED` badge on output | No backtest run | Accept for screening only; do not size capital |
| `PermissionError` | Role lacks permission | Check `permissions.yaml`; request role upgrade |
| `KeyError: scenario not found` | Invalid scenario ID | Check `src/bve/scenarios/library.yaml` for valid IDs |
