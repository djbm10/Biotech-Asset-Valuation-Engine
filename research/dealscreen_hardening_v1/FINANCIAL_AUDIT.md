# DealScreen hardening: financial correctness audit (2026-10-27)

Grade: INTERNAL DEVELOPMENT. No Lane 1 formula, default, calibration or assumption was
changed. Nothing in this audit has been signed off.

## 1. The RLAY `bve-asset` crash

**Reproduced.** `bve-asset --config examples/configs/relay_rly2608.yaml` failed with:

    AttributeError: 'TrialDesignFeatureSet' object has no attribute 'evidence_design'

**Cause: two defects in `bve.cli.run_asset`, both from b4e1f39 (2026-05-09).** That commit
renamed the design-layer fields to `evidence_design_quality` / `comparator_fit` /
`regulatory_pathway_risk`.

1. **Console summary.** The summary printed `feat.evidence_design` and `feat.approval_pathway`,
   so *every* config with `trial_design.apply_design_model: true` crashed. The crash happened
   before `engine.run()`, so no valuation was produced.
2. **Silent defaults (the material one).** `_build_design_adjusters` reads only the three new
   keys. RLAY's config still uses `evidence_design`, `approval_pathway` and `endpoint_basis`,
   which were dropped silently. Every phase was therefore valued as `rct_double_blind`,
   including RLAY's single-arm Phase 2.
   - Any path that skipped the console line was affected. That includes DealScreen's own
     prototype CLI, which reported RLAY at $65M in the first DealScreen session without any flag.

**Measured effect** (`rlay_design_layer_impact.json`, 200 simulations; the base case is
deterministic):

| RLAY variant | Base rNPV | P(approval) | Bear / Bull |
|---|---:|---:|---:|
| Design layer off | $44M | 26.3% | −117 / 488 |
| Legacy keys silently ignored (defaults) | **$65M** | 29.8% | −118 / 564 |
| Proposed migration (not applied) | $39M | 24.4% | −112 / 449 |

**Change made (CLI only, fail-closed; no valuation output changes for any config that
previously produced one):**
- the console summary prints the current fields;
- `_validate_config` rejects per-phase `trial_design` keys that the design builder does not
  read, naming them.

RLAY now stops with a clear validation error instead of a crash, and no config can again be
valued with silently defaulted design inputs.

**Blocked: the RLAY config migration.**
- Mapping `single_arm` → `single_arm_objective` and `rct_comparative` → `rct_open_label` etc.
  is a judgement that changes RLAY's rNPV by about −$26M against what it silently produced.
- It is prepared as `docs/change_requests/proposed/rlay_trial_design_migration.patch`. It
  applies cleanly and validates, but it is **not applied** and needs Lane 1 quant + clinical
  sign-off.
- Until then the canonical RLAY example does not run with its design layer.

## 2. Selimab: bear rNPV above base

**Reproduced:** bear −120, base −127, bull −108 ($M).

**Cause: not an engine error. Selimab's costs outweigh its revenue at these hypothetical inputs.**

Decomposition (`scenario_ordering_diagnostic.py`, which calls the engine's own
`compute_rnpv_full` with the engine's scenario shocks and reproduces −120 / −127 / −108
exactly):

| | Bear | Base | Bull |
|---|---:|---:|---:|
| Cumulative PoS | 7.4% | 21.6% | 40.2% |
| Probability-adjusted revenue PV | 2 | 15 | 54 |
| Probability-weighted development cost PV | 121.9 | 141.7 | 161.4 |
| rNPV | −120 | −127 | −108 |
| rNPV if every phase succeeds | −238 | −196 | −128 |

Selimab's peak sales are $43M (4,000 patients at $90,000 and 15% share) against $355M of
remaining development cost, so it loses money even if every phase succeeds.

How the bear case ends up above base:
- The bear shock multiplies every phase's PoS by 0.70.
- That cuts the chance of paying for the $260M Phase 3: expected cost falls by $19.8M.
- Expected revenue falls by only $13M.
- So bear is less negative than base.
- Bull rises above base for the opposite reason: higher price and PoS outweigh the higher spend.

Scenario labels name input shocks, not output ranks.

**Change made (DealScreen, Lane 4):**
- `valuation_handoff.scenario_check` checks bear ≤ base ≤ bull on every saved
  `valuation.json`, without sorting or recomputing anything.
- Out-of-order results are labelled `OUT_OF_ORDER_EXPLAINED_COST_DOMINATED` only when the
  saved output itself shows probability-adjusted revenue ≤ development cost (plus payable deal
  milestones). The memo and workbook then say so in words.
- Any other out-of-order result is `OUT_OF_ORDER_UNEXPLAINED_BLOCKED`: the workbook shows
  "BLOCKED" instead of numbers, and the memo withholds the valuation.

## 3. The prototype deal-economics path

`tests/dealscreen/test_financial_correctness.py` checks:
- **with deal terms** (upfront + royalty + approval milestone), the prototype CLI's rNPV
  equals `compute_rnpv_full(..., deal=DealEconomics(...), loe_profile=<engine default>)`;
- **upfront only**: the rNPV shifts by exactly the upfront, within the engine's $1M rounding;
- **no deal block**: it equals `bve-asset` (existing end-to-end test).

## 4. mypy

- The 13 DealScreen errors were missing `yaml` / `openpyxl` type stubs.
- Installing `types-PyYAML` and `types-openpyxl` (now in the `dev` extra) exposed 6 real
  `Optional` worksheet errors, which are fixed. DealScreen now has 0 mypy errors and no
  `ignore` was added.
- Repo-wide: 875 → 799.
  - The 755 non-stub errors are identical with and without the stubs: the stubs exposed
    nothing new elsewhere.
  - The 76 errors removed were all missing-stub errors.
- S&E alone: 102 → 101.
