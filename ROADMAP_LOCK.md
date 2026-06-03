# ROADMAP LOCK

**Version:** 1.0 | **Status:** Active | **Enforced from:** 2026-05-15

Every proposed change must be classified into one of the four lanes below and must
complete the CHANGE_REQUEST_TEMPLATE.md before work begins.

---

## Lane Definitions

### Lane 1: Core Valuation Engine
Modules directly in the rNPV / revenue / cost / POS computation path.

Canonical modules:
- `src/bve/models/` (pos_model, rnpv_model, revenue_model, cost_model, probability_model,
  competition_model, multi_indication, deal_economics, drug_asset_program, monte_carlo)
- `src/bve/valuation/` (valuation_engine, scenario, outputs, assumptions, portfolio)
- `src/bve/features/` (trial_features)
- `src/bve/config/` (industry_assumptions.yaml, constants.py)

**Owner:** quant / clinical
**Core outputs affected:** rNPV, NAV/share, POS

---

### Lane 2: M&A / Acquisition Scanner
Modules that score acquirer fit, acquisition probability, and deal economics.

Canonical modules:
- `src/bve/intelligence/` (ma_probability, strategic_fit, dynamic_competition_engine)
- `src/bve/deals/` (structure, optimizer, seller_utility)
- `src/bve/analysis/` (implied_probability, implied_pos, variant_perception)

**Owner:** bd / corporate strategy
**Core outputs affected:** M&A score, watchlist classification

---

### Lane 3: Intelligence / Thesis Tracker
Modules that maintain the live universe, track thesis claims, and surface actionable candidates.

Canonical modules:
- `src/bve/intelligence/` (knowledge_layer, thesis_tracker, actionable_output, evidence_ingestion,
  continuous_monitoring, calibration_feedback_loop)
- `src/bve/ops/` (weekly_runner, historical_replay, ma_probability_backfiller)
- `src/bve/learning/`
- `src/bve/alpha/`

**Owner:** analyst / quant
**Core outputs affected:** watchlist classification, historical replay

---

### Lane 4: Platform / Governance / UI
Infrastructure, governance, review workflow, security, observability, and UI.

Canonical modules:
- `src/bve/governance/`
- `src/bve/policy/`
- `src/bve/validation/`
- `src/bve/benchmark/`
- `src/bve/pit/`
- `src/bve/portfolio/`
- `src/bve/workflow/`
- `src/bve/redteam/`
- `src/bve/scenarios/`
- `src/bve/runtime/`
- `src/bve/security/`
- `src/bve/data/`
- `src/bve/ui/`
- `apps/`

**Owner:** engineering / platform
**Core outputs affected:** none (infrastructure only)

---

## Change Classification Rules

| Rule | Requirement |
|------|-------------|
| All changes must declare a lane | No lane = change blocked |
| Lane 1 changes require quant + clinical sign-off | Cannot merge without approval |
| Cross-lane changes require all affected lane owners | e.g., Lane 1+2 requires quant + bd |
| `core_output_changed: true` requires regression tests | Tests must cover affected output |
| `requires_migration: true` blocks release until migration is verified | |
| Surprise roadmap modules are only allowed if isolated, backward-compatible, not in Lane 1/2 run path | |

---

## Blocked Until Further Notice

The following activities are **frozen** until explicitly unlocked by a new ROADMAP_LOCK revision:

- Adding new Lane 1 parameters without Brier/AUC backtest evidence
- Changing base rates in `industry_assumptions.yaml` without holdout validation
- Exposing raw scores as "probabilities" without calibration labels
- Adding UI features that bypass the validation badge system

---

## Lock Revision History

| Date | Change | Author |
|------|--------|--------|
| 2026-05-15 | Initial lock — four-lane architecture established | System |
