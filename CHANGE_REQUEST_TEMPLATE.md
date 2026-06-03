# Change Request Template

Copy this template into every PR description or Claude/Codex prompt before work begins.

---

## Change Request

**Title:**
**Date:**
**Requestor:**

---

## Classification (required)

```yaml
lane: "1 | 2 | 3 | 4"        # Must pick exactly one primary lane
cross_lane: false              # true if this touches multiple lanes
affected_modules:
  - src/bve/...
core_output_changed: false     # true if rNPV / NAV / POS / M&A score / watchlist classification changes
backward_compatible: true      # false = breaking change, requires migration plan
requires_migration: false      # true = migration script must be provided and tested
feature_flag: null             # name of feature flag if this is behind one, else null
tests_required:
  - unit: true
  - integration: false
  - backtest_regression: false  # required if core_output_changed: true
```

---

## Problem Statement

*What breaks or is missing? Why is this needed now?*

---

## Proposed Solution

*What modules are created or changed? What is the minimal scope?*

---

## Impact Assessment

| Output | Changed? | Change direction | Test coverage |
|--------|----------|-----------------|---------------|
| rNPV | no / yes | +/- / neutral | test name |
| POS | no / yes | +/- / neutral | test name |
| M&A score | no / yes | +/- / neutral | test name |
| Watchlist class | no / yes | +/- / neutral | test name |
| Historical replay | no / yes | +/- / neutral | test name |

---

## Validation Requirements

*If `core_output_changed: true`, describe the backtest regression test:*

- Baseline Brier / AUC before change:
- Baseline Brier / AUC after change:
- Acceptance criterion:

---

## Rollback Plan

*How do we undo this if it causes issues in production?*

---

## Sign-offs Required

Based on lane classification:

| Lane | Sign-off required from |
|------|----------------------|
| 1 | quant + clinical |
| 2 | bd + corporate strategy |
| 3 | analyst + quant |
| 4 | engineering |
| Cross-lane | all affected lane owners |

- [ ] Sign-off 1:
- [ ] Sign-off 2:
