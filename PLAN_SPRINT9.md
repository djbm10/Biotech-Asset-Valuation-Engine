# PLAN_SPRINT9.md — Institutional Grade Fix Plan
# Generated: 2026-03-25 | Based on forensic audit

## Context

This plan addresses every finding from the 2026-03-25 forensic audit.
The system is currently rated **⚠️ Pre-institutional (structured screening only)**.
The target after this sprint is **✅ Pre-institutional → Institutional-grade** for
BD deal screening and VC portfolio support, and **⚠️ → ✅ directional** for HF use
(full HF grade requires statistical replay graduation in Phase 5).

---

## Sequencing Strategy

The fixes are grouped into six phases. Phase 1 must be done first because the UFCF
tax treatment, POS cap, and WACC changes all alter `rnpv_millions` — which is the
anchor for every regression fixture in the test suite. All model math changes are
batched into Phase 1 so regression fixtures are updated exactly once.

```
Phase 1 (model math)    → update all regression baselines once
Phase 2 (revenue/cost)  → more fixture changes, extend same update pass
Phase 3 (validation)    → no fixture changes; additive new tests only
Phase 4 (scoring)       → intelligence layer only; isolated
Phase 5 (calibration)   → backtest/replay; isolated from core engine
Phase 6 (provenance)    → metadata/audit; no model output changes
```

Phases 1+2 should be implemented as a single PR so regression baselines are
updated once. Phases 3-6 are independent and can be parallelised.

---

## PHASE 1 — Core Model Math Corrections

> All changes here alter `rnpv_millions`. Implement as one PR.
> After this phase: run `python -m pytest tests/ -v`, update all changed
> fixture values, commit with `chore: update regression baselines post-Sprint-9-Phase1`.

---

### Task 9.1 — UFCF / Tax Treatment (CRITICAL)

**Audit finding:** RNPVModel discounts `ebit_by_year` directly. EBIT is not cash
flow. Omitting a 21% effective tax rate overstates every rNPV by ~15–20%.

**Root cause:** `RNPVModel.compute()` line 161:
```python
gross_revenue_pv += (ebit * effective_ownership) / (1.0 + r) ** abs_year
```
There is no `(1 - tax_rate)` factor anywhere in the pipeline.

**Fix — three-step:**

**Step 1: `src/bve/config/industry_assumptions.yaml`**
Add a new top-level section after `wacc:`:
```yaml
tax:
  # US statutory corporate rate post-TCJA. Clinical-stage biotechs often have
  # NOL carryforwards that defer cash taxes for years post-approval; this rate
  # models the steady-state blended effective rate once NOLs are exhausted.
  # Callers may override on Asset when non-US domicile or known NOL position.
  # Source: US statutory rate 21%; blended effective rate ~18-22% for specialty pharma.
  effective_rate_default: 0.21
  # NOL benefit window: years from first revenue where cash taxes are deferred.
  # During this window, effective tax rate = 0.0. After it, use effective_rate_default.
  # Set to 0 to disable NOL modeling (conservative, always-taxes approach).
  nol_benefit_years: 0
```

**Step 2: `src/bve/entities/asset.py`**
Add field to `Asset`:
```python
effective_tax_rate: float = Field(
    default=0.21, ge=0.0, le=0.50,
    description=(
        "Effective corporate tax rate applied to EBIT to derive UFCF. "
        "Default 21% (US statutory post-TCJA). Override for non-US domicile "
        "or assets with known NOL carryforward positions."
    )
)
nol_benefit_years: int = Field(
    default=0, ge=0,
    description=(
        "Years from first commercial revenue where NOL carryforwards defer "
        "cash taxes. During this window effective_tax_rate is treated as 0.0. "
        "Set to 0 to disable NOL modeling."
    )
)
```

**Step 3: `src/bve/models/rnpv_model.py`**
In `RNPVModel.compute()`, replace the EBIT discounting loop:
```python
# BEFORE
gross_revenue_pv += (ebit * effective_ownership) / (1.0 + r) ** abs_year

# AFTER
tax_rate = asset.effective_tax_rate
nol_window = asset.nol_benefit_years
# During NOL window (yr 1..nol_benefit_years), taxes are deferred → rate = 0
effective_tax = 0.0 if yr <= nol_window else tax_rate
after_tax_ebit = ebit * (1.0 - effective_tax)
gross_revenue_pv += (after_tax_ebit * effective_ownership) / (1.0 + r) ** abs_year
```

Expose in `RNPVResult`:
```python
effective_tax_rate: float = 0.21
nol_benefit_years: int = 0
```

**Step 4: Scenarios**
`src/bve/valuation/scenario.py` — add `tax_rate_add: float = 0.0` to
`ScenarioAssumptions`. Apply in `build_scenarios()` so the Bear scenario can
model a tax rate increase (+0.03 additive).

**Step 5: Sensitivity**
`src/bve/valuation/valuation_engine.py` — add `effective_tax_rate` as the 6th
parameter in `_compute_sensitivities()`, perturbing ±5pp around base (e.g. 16%
to 26%). This will likely be the 3rd or 4th largest sensitivity for most assets.

**Files touched:**
- `src/bve/config/industry_assumptions.yaml`
- `src/bve/entities/asset.py`
- `src/bve/models/rnpv_model.py`
- `src/bve/valuation/scenario.py`
- `src/bve/valuation/valuation_engine.py`
- `src/bve/valuation/outputs.py` (add `effective_tax_rate` to `ValuationOutput.meta`)
- All example YAML configs (add `effective_tax_rate: 0.21` as explicit field)
- All regression test fixtures

**Regression impact:** All `rnpv_millions` values decrease by ~15-20%. The
canonical RLAY case will drop from ~$139M to ~$112-118M.

**Acceptance criteria:**
- `RNPVResult.rnpv_millions` at `tax_rate=0.0` == pre-fix baseline (backward compat test)
- `RNPVResult.rnpv_millions` at `tax_rate=0.21` == `baseline × (1 - 0.21)` within rounding
- NOL window: years 1..nol_benefit_years use rate=0.0; years after use `effective_tax_rate`
- Sensitivity tornado includes `effective_tax_rate` as a parameter
- All existing tests pass with updated fixture values

---

### Task 9.2 — POS Layer 1 Adjuster Cap (CRITICAL)

**Audit finding:** `POSAdjusters` (Layer 1) has no combined cap on log-odds
adjusters. Maximum theoretical stacked upward adjustment is +1.80 log-odds,
pushing a 32% oncology Phase 2 base to ~62%. Layer 2 has a cap; Layer 1 does not.

**Root cause:** `compute_pos()` in `src/bve/models/pos_model.py` sums all
adjusters without any total bound check.

**Fix:**

**Step 1: `src/bve/config/industry_assumptions.yaml`**
Add to `pos_model:` section (create if absent):
```yaml
pos_model:
  # Maximum combined log-odds adjustment from Layer 1 (POSAdjusters).
  # Prevents stacked optimistic signals from producing implausibly high POS.
  # Symmetric: same magnitude for positive and negative caps.
  # Rationale: +0.80 log-odds at a 32% Phase 2 base → ~47% adjusted POS.
  # A 47% Phase 2 oncology POS is rare but not impossible for biomarker-
  # selected populations. +1.80 (62%) is implausible for any indication.
  layer1_cap_logodds_positive:  0.80
  layer1_cap_logodds_negative: -0.80
```

**Step 2: `src/bve/models/pos_model.py`**
After summing all adjusters, before converting back to probability:
```python
# Apply Layer 1 combined cap
_L1_CAP_POSITIVE = 0.80   # load from constants/assumptions
_L1_CAP_NEGATIVE = -0.80

# ... (existing adjuster summation) ...

# Cap the ADJUSTMENT (delta from base), not the total log-odds
total_adjustment = log_odds - base_log_odds
total_adjustment = max(_L1_CAP_NEGATIVE, min(_L1_CAP_POSITIVE, total_adjustment))
log_odds = base_log_odds + total_adjustment
```

Note: the cap applies to the adjustment relative to the base rate, not the
absolute log-odds. This preserves the semantics of "how much can analyst
qualitative inputs move POS from the TA prior."

**Step 3: Add `_compute_layer1_adjustment()` helper**
Extract the adjustment summing into a named function so tests can verify the
cap triggers at the boundary.

**Files touched:**
- `src/bve/config/industry_assumptions.yaml`
- `src/bve/config/constants.py` (export cap constants)
- `src/bve/models/pos_model.py`
- `tests/test_phase1.py` (add cap boundary tests)

**Regression impact:** Any existing test with a "best case" POS scenario that
stacks 4+ positive adjusters will see lower POS. Tests using default adjusters
are unaffected.

**Acceptance criteria:**
- Stacking all maximum positive adjusters for oncology Phase 2 produces POS ≤ 50%
  (32% base + 0.80 cap → ~47%)
- Cap applies symmetrically: stacking all negative adjusters floors at ~20% for
  oncology Phase 2 (32% base - 0.80 cap → ~21%)
- Single-adjuster tests below cap threshold: no change in output
- `check_pos_layer_overlap()` tests unaffected

---

### Task 9.3 — BTD Log-odds Correction

**Audit finding:** `has_breakthrough_designation: +0.20 log-odds` is
methodologically wrong. BTD is a process designation that correlates with faster
review timelines, not higher binary approval probability. The +0.20 reflects
selection bias (BTD programs are better assets) not a causal FDA approval effect.

**Fix:**

**`src/bve/models/pos_model.py`**
```python
# BEFORE
if adjusters.has_breakthrough_designation:
    log_odds += 0.20  # modest boost; BTD correlates with faster/easier approval

# AFTER
if adjusters.has_breakthrough_designation:
    # BTD is a process designation; primary effect is faster review, not higher
    # binary approval probability. Prior literature shows no significant PoS lift
    # once controlling for indication and target quality. +0.05 retains a tiny
    # signal for FDA engagement while preventing selection-bias inflation.
    log_odds += 0.05
```

**`src/bve/config/industry_assumptions.yaml`** — add to `pos_model` section:
```yaml
  btd_logodds: 0.05   # was 0.20; reduced per FDA outcome data (process ≠ probability)
```

**Files touched:**
- `src/bve/models/pos_model.py`
- `src/bve/config/industry_assumptions.yaml`
- `tests/test_phase1.py` (update BTD test expected values)

**Regression impact:** Any existing asset with `has_breakthrough_designation: True`
will see slightly lower POS. Typically a 1-2pp reduction at oncology Phase 2 base.

**Acceptance criteria:**
- BTD-only adjustment produces +0.05 log-odds (not +0.20)
- Comment explains the methodological rationale
- Non-BTD paths unchanged

---

### Task 9.4 — WACC Modernization

**Audit finding:** `wacc.default: 0.10` is stale for a 4.2% risk-free rate
environment (current 10Y Treasury ~4.2%). Clinical-stage small-cap biotech WACC
should be 12-14%. The 10% WACC overstates all rNPV outputs by 15-20% vs. market
cost of capital.

**Fix:**

**`src/bve/config/industry_assumptions.yaml`**
```yaml
wacc:
  vintage: "2026-Q1"       # ADD — for audit trail; update each year
  default:    0.12          # WAS 0.10 — clinical-stage biotech
  small_cap:  0.14          # WAS 0.12 — < $500M market cap
  large_cap:  0.10          # WAS 0.09 — > $5B market cap
  risk_free:  0.043         # WAS 0.04 — 10Y Treasury proxy 2026-Q1
  erp_biotech: 0.077        # ADD — biotech equity risk premium used to derive above
```

**`src/bve/entities/asset.py`**
Change default:
```python
discount_rate: float = Field(
    default=0.12,   # WAS 0.10
    ...
)
```

**All example YAML configs:** Any config using `discount_rate: 0.10` should be
updated to `0.12`. Configs with explicit overrides are unaffected in behavior but
should be reviewed for appropriateness.

**Files touched:**
- `src/bve/config/industry_assumptions.yaml`
- `src/bve/entities/asset.py`
- `examples/configs/*.yaml`
- All regression test fixtures (rNPV will decrease for assets using default WACC)

**Regression impact:** All tests using `discount_rate=0.10` (default) will
see rNPV decrease ~8-12%. Tests that explicitly set `discount_rate` are unaffected.

**Acceptance criteria:**
- `AssumptionsLoader.wacc("default")` returns `0.12`
- `Asset()` with no explicit `discount_rate` uses `0.12`
- `wacc.vintage` field is present and parseable as `YYYY-QN` format
- Canonical RLAY case uses explicit `discount_rate: 0.12` in its config

---

### Task 9.5 — S-curve Adoption Warning

**Audit finding:** Default uptake is a linear ramp (`use_s_curve: False`).
Linear ramp front-loads revenue, overstating early cash flows that are
disproportionately weighted by discounting. For specialty pharma (oncology,
rare disease), S-curve adoption is the realistic default.

**Rationale for advisory (not breaking change):** Changing the global default
from linear to S-curve would break all existing configs silently. Instead, emit
a `UserWarning` when `use_s_curve=False` on specialty TAs so analysts are forced
to make an explicit choice. New configs and examples should use `use_s_curve: true`.

**Fix:**

**`src/bve/models/market_model.py`** — add to `_build_uptake_curve` validator:
```python
import warnings

SPECIALTY_TAS = {"oncology", "rare_disease", "cns"}

@model_validator(mode="after")
def _check_uptake_shape(self) -> "MarketModel":
    # Only warn for non-LOT mode (LOT segments set their own curve)
    if self.lines_of_therapy:
        return self
    if not self.use_s_curve:
        warnings.warn(
            f"MarketModel for asset '{self.asset_id}' is using a linear uptake "
            "ramp. For specialty pharma assets (oncology, rare disease, CNS), "
            "an S-curve better reflects realistic KOL-driven adoption. "
            "Set use_s_curve=True to suppress this warning.",
            UserWarning,
            stacklevel=2,
        )
    return self
```

**`src/bve/config/industry_assumptions.yaml`** — add documentation note to
commercial.defaults section about S-curve recommendation.

**All example YAML configs:** Update `examples/configs/*.yaml` to set
`use_s_curve: true` explicitly, demonstrating the recommended practice.

**Files touched:**
- `src/bve/models/market_model.py`
- `src/bve/config/industry_assumptions.yaml` (documentation only)
- `examples/configs/*.yaml`
- `tests/` — add test confirming warning fires for linear specialty assets

**Regression impact:** None (no output values change; warning only).

**Acceptance criteria:**
- `MarketModel(asset_id="x", ..., use_s_curve=False)` emits `UserWarning`
- `MarketModel(asset_id="x", ..., use_s_curve=True)` is silent
- Warning message is actionable (tells analyst what to do)
- Example configs all have `use_s_curve: true`

---

## PHASE 2 — Revenue & Cost Model Accuracy

> These changes also alter `rnpv_millions`. Implement in the same PR as Phase 1
> so regression baselines are updated only once.

---

### Task 9.6 — Modality-Appropriate Compliance Rates

**Audit finding:** `compliance_rate: 0.80` is applied uniformly across all
modalities. Gene therapy (single administration) should be 1.0. IV-administered
biologics in monitored settings should be 0.95. This is material for gene therapy
and cell therapy assets whose revenue is meaningfully understated.

**Fix:**

**`src/bve/config/industry_assumptions.yaml`** — add to `commercial:`:
```yaml
  compliance_by_modality:
    # Fraction of modeled treatment duration patients remain adherent.
    # For single-administration therapies (gene/cell), compliance = 1.0 by definition.
    # Source: published adherence studies + internal modeling practice.
    gene_therapy:      1.00   # single administration; no ongoing adherence
    cell_therapy:      1.00   # single administration
    biologic_iv:       0.95   # monitored infusion; high adherence
    biologic_sc:       0.83   # self-injection; moderate drop-off
    small_molecule:    0.78   # oral; consistent with published adherence literature
    adc:               0.95   # IV monitored oncology setting
    rna_therapy:       0.85   # typically SC; moderate
    other:             0.80   # conservative fallback
```

Note: `biologic` modality (generic) maps to `biologic_iv` as the conservative
default. Users with SC-administered biologics should use the `biologic_sc` rate.

**`src/bve/models/market_model.py`** — add a `_warn_compliance_mismatch()` method:
When `compliance_rate == 0.80` (the bare default) and no explicit override exists,
the engine should warn for gene/cell therapy assets that the rate should be 1.0.
Full auto-population from modality is not done here (MarketModel doesn't hold
the Asset entity), but the warning at engine level is.

**`src/bve/valuation/valuation_engine.py`** — in `run()`, add a check:
```python
if (self.asset.modality in (Modality.GENE_THERAPY, Modality.CELL_THERAPY)
        and not self.market_model.lines_of_therapy
        and self.market_model.compliance_rate < 1.0):
    warnings.warn(
        f"Asset '{self.asset.id}' is {self.asset.modality.value} (single-administration). "
        f"compliance_rate={self.market_model.compliance_rate} — consider setting to 1.0.",
        UserWarning,
    )
```

**Files touched:**
- `src/bve/config/industry_assumptions.yaml`
- `src/bve/valuation/valuation_engine.py`
- `tests/` — add modality compliance warning tests

**Regression impact:** None on existing tests (no default value changes, warning only).
New gene/cell therapy test cases will show higher rNPV at compliance=1.0.

**Acceptance criteria:**
- `ValuationEngine` emits warning for gene/cell therapy with `compliance_rate < 1.0`
- `industry_assumptions.yaml` has compliance table with all 7 modality entries
- No existing test values change

---

### Task 9.7 — Modality-Appropriate SG&A Profiles

**Audit finding:** The single SG&A ramp (40% → 20% over 5 years) is wrong for
gene/cell therapy (treatment center certification, patient-finding programs, not
traditional commercial promotion) and rare disease (patient support > KOL
promotion). Using one ramp for all modalities misprices BD deals for novel modalities.

**Fix:**

**`src/bve/config/industry_assumptions.yaml`** — replace the single `sgna:` block
with `sgna_profiles:`:
```yaml
sgna_profiles:
  # Source: public company filings, Evaluate Pharma, internal BD modeling practice.
  # All profiles represent guidance; asset configs should override when known.

  specialty_pharma:        # default for oncology small molecule, immunology
    rate_launch: 0.40
    rate_mature: 0.20
    ramp_years:  5

  rare_disease:            # smaller patient population; more MSL/advocacy-heavy
    rate_launch: 0.45
    rate_mature: 0.22
    ramp_years:  4         # faster maturation (smaller targeted launch)

  gene_cell_therapy:       # treatment center setup, patient ID programs, no repeat Rx
    rate_launch: 0.55      # higher: one-time dosing requires intensive pre/post support
    rate_mature: 0.28
    ramp_years:  7         # slow maturation; program complexity high long-term

  primary_care:            # broad indication, high patient volumes, competitive market
    rate_launch: 0.50
    rate_mature: 0.30
    ramp_years:  6

  # Legacy key — preserved for backward compat; maps to specialty_pharma
  default:
    rate_launch: 0.40
    rate_mature: 0.20
    ramp_years:  5
```

Keep the old `sgna:` key as an alias for `sgna_profiles.default` to preserve
backward compatibility with existing code that calls `AssumptionsLoader.sgna()`.

**`src/bve/valuation/valuation_engine.py`** — in `run()`, auto-select SG&A
profile from modality/TA if `MarketModel` is using default SG&A rates:
```python
def _resolve_sgna_profile(self) -> dict:
    modality = self.asset.modality
    ta = self.asset.therapeutic_area
    if modality in (Modality.GENE_THERAPY, Modality.CELL_THERAPY):
        return loader.sgna_profile("gene_cell_therapy")
    if ta == TherapeuticArea.RARE_DISEASE:
        return loader.sgna_profile("rare_disease")
    return loader.sgna_profile("specialty_pharma")
```

Emit a `UserWarning` when the profile was auto-selected (not explicitly set in
config) so the analyst is aware.

**Files touched:**
- `src/bve/config/industry_assumptions.yaml`
- `src/bve/config/assumptions.py` (add `sgna_profile(name)` loader method)
- `src/bve/valuation/valuation_engine.py`
- `tests/` — add SG&A profile selection tests

**Regression impact:** Gene/cell therapy assets in existing tests may see
slightly different EBIT (higher SG&A launch rate from 40% to 55%). Other assets
unaffected unless they are explicitly rare disease or primary care.

**Acceptance criteria:**
- `AssumptionsLoader.sgna_profile("gene_cell_therapy")` returns `rate_launch=0.55`
- `AssumptionsLoader.sgna_profile("default")` returns `rate_launch=0.40` (backward compat)
- Auto-selection emits warning with profile name chosen and reason
- Explicit config override suppresses auto-selection

---

### Task 9.8 — Accelerated Approval Confirmatory Risk

**Audit finding:** NDA/BLA success rate for oncology is 83% uniformly. This mixes
full-approval programs (~90%) and accelerated approval programs using single-arm
surrogate endpoints (~65-70%), which face confirmatory trial conversion risk.
Single-arm Phase 2 → accelerated NDA/BLA is a materially different risk profile.

**Fix:**

**`src/bve/entities/asset.py`** — add:
```python
class ApprovalPathwayType(str, Enum):
    STANDARD = "standard"
    ACCELERATED = "accelerated"    # AA under Subpart H; surrogate endpoint; confirmatory required
    PRIORITY_REVIEW = "priority_review"  # process only; no probability change

approval_pathway: ApprovalPathwayType = Field(
    default=ApprovalPathwayType.STANDARD,
    description=(
        "Regulatory approval pathway. ACCELERATED applies a confirmatory trial "
        "risk discount to the NDA/BLA success rate."
    )
)
```

**`src/bve/config/industry_assumptions.yaml`** — add to `pos_model:`:
```yaml
  accelerated_approval_nda_discount: 0.18
  # Discount applied to base NDA/BLA success rate for accelerated approval programs.
  # Rationale: AA programs using single-arm surrogate endpoints have historically
  # faced ~15-20% post-market withdrawal/conversion failure rate (FDA AA withdrawal
  # data 2013-2023). This discount is applied at the NDA/BLA phase only.
  # Source: Darrow JJ et al. (2021) JAMA Internal Medicine; FDA 2023 AA report.
```

**`src/bve/models/pos_model.py`** — in `apply_pos_to_trials()`:
```python
# When asset has AcceleratedApproval pathway and trial is NDA/BLA phase,
# apply the confirmatory discount to success_probability
if (asset.approval_pathway == ApprovalPathwayType.ACCELERATED
        and trial.phase == TrialPhase.NDA_BLA):
    discount = loader.get("pos_model.accelerated_approval_nda_discount", 0.18)
    # Apply as a multiplicative reduction to the NDA/BLA success rate
    # BEFORE log-odds adjusters (this is a base-rate correction, not an adjuster)
    adjusted_base_rate = base_rate * (1.0 - discount)
    # ... continue with log-odds adjusters on adjusted_base_rate
```

**Files touched:**
- `src/bve/entities/asset.py`
- `src/bve/config/industry_assumptions.yaml`
- `src/bve/models/pos_model.py`
- `tests/test_phase1.py` (add accelerated approval tests)

**Regression impact:** None for existing assets (default is `STANDARD`). New AA
test cases will show lower cumulative POS than standard path.

**Acceptance criteria:**
- `Asset(approval_pathway=ACCELERATED)` with oncology NDA/BLA uses ~68% success
  rate (83% × (1-0.18) ≈ 68%)
- `Asset(approval_pathway=STANDARD)` unchanged
- `approval_pathway` field appears in exported `ValuationOutput`

---

### Task 9.9 — Post-Approval R&D Cost Placeholder

**Audit finding:** `CostModel` stops at NDA/BLA. Real post-approval costs include
Phase 4 commitments, REMS programs, pharmacovigilance, and label expansion trials.
These are material in BD deal NPV modeling (adds $50-150M to cost side).

**Fix (minimal, conservative):**

**`src/bve/entities/asset.py`** — add:
```python
post_approval_rd_millions: float = Field(
    default=0.0, ge=0.0,
    description=(
        "Expected post-approval R&D obligations in USD millions (nominal, undiscounted). "
        "Includes: Phase 4 commitments, REMS program, pharmacovigilance, label "
        "expansion studies. Discounted at years_to_approval in CostModel."
    )
)
```

**`src/bve/models/cost_model.py`** — in `CostModel.compute()`, after the existing
phase cost loop, add:
```python
# Post-approval R&D: discounted at years_to_approval (the earliest they begin)
# Weighted by cumulative approval probability (same logic as revenue weighting)
post_approval_cost = getattr(asset_ref, "post_approval_rd_millions", 0.0)
if post_approval_cost > 0.0:
    years_to_approval = sum(p.year_end - p.year_start for p in prob.phases)
    post_approval_pv = post_approval_cost / (1.0 + r) ** years_to_approval
    post_approval_pv_weighted = post_approval_pv * prob.cumulative_approval_probability
    total += post_approval_pv_weighted
    # Expose in CostStream decomposition
```

Note: `CostModel` currently doesn't receive the `Asset`. The cleanest fix passes
`post_approval_rd_millions` as an explicit parameter to `CostModel.compute()` to
maintain the stateless engine boundary:
```python
@staticmethod
def compute(
    prob: ProbabilityResult,
    discount_rate: float,
    deal: Optional["DealEconomics"] = None,
    post_approval_rd_millions: float = 0.0,   # NEW
) -> CostStream:
```

**Files touched:**
- `src/bve/entities/asset.py`
- `src/bve/models/cost_model.py`
- `src/bve/models/rnpv_model.py` (`compute_rnpv_full` passes the new param)
- `src/bve/valuation/valuation_engine.py` (pass `asset.post_approval_rd_millions`)
- `tests/test_step5.py` (add post-approval cost tests)

**Regression impact:** None for existing tests (default is 0.0).

**Acceptance criteria:**
- `post_approval_rd_millions=0.0` (default): identical output to pre-fix
- `post_approval_rd_millions=100.0` at 10% WACC, 7-yr timeline:
  PV ≈ 100/(1.10)^7 ≈ $51.3M × P(approval) added to cost
- Post-approval cost appears in `CostStream` decomposition fields

---

### Task 9.10 — LOE Tail Extension (3 → 5 Years)

**Audit finding:** `_LOE_TAIL_KEYS = ("year_1_loss", "year_2_loss", "year_3_loss")` —
only 3 tail years appended. For small molecules, branded residual at year 4-5
post-LOE is still $20-80M on a $500M peak asset. For rare disease with orphan
pricing, the branded tail persists 5-7 years. The 3-year hard cutoff understates
long-tail deal NPV.

**Fix:**

**`src/bve/config/industry_assumptions.yaml`** — extend all `loe_erosion_profiles`:
```yaml
  small_molecule:
    year_1_loss: 0.40
    year_2_loss: 0.65
    year_3_loss: 0.80
    year_4_loss: 0.88     # ADD — further erosion
    year_5_loss: 0.92     # ADD — near-complete generic substitution
    terminal_loss: 0.95   # Year 6+ branded floor (~5% of peak)
    post_loe_sgna_fraction: 0.25

  biologic:
    year_1_loss: 0.20
    year_2_loss: 0.40
    year_3_loss: 0.60
    year_4_loss: 0.68     # ADD
    year_5_loss: 0.72     # ADD
    terminal_loss: 0.75
    post_loe_sgna_fraction: 0.30

  # ... extend all other modality profiles with year_4_loss, year_5_loss
```

**`src/bve/models/revenue_model.py`** — update:
```python
_LOE_TAIL_KEYS = (
    "year_1_loss", "year_2_loss", "year_3_loss",
    "year_4_loss", "year_5_loss",   # ADD
)
```

The existing loop over `_LOE_TAIL_KEYS` already handles arbitrary length, so no
loop logic changes. The `loe_tail_years` count will increase from 3 to 5 for any
profile that defines the new keys.

**Backward compatibility:** Profiles that do not define `year_4_loss` or
`year_5_loss` will silently skip those tail years (existing loop uses `loe_profile[key]`
which would raise `KeyError`). Add `.get()` with a fallback that terminates the
loop early when keys are absent:
```python
for key in _LOE_TAIL_KEYS:
    if key not in loe_profile:
        break   # tail ends here; profile does not define further erosion
    ...
```

**Files touched:**
- `src/bve/config/industry_assumptions.yaml`
- `src/bve/models/revenue_model.py`
- `tests/test_step3.py` (update LOE tail year count from 3 to 5)

**Regression impact:** Any test checking `loe_tail_years == 3` will need updating
to `loe_tail_years == 5`. Total rNPV will increase slightly (years 4-5 add small
discounted cash flows at terminal loss).

**Acceptance criteria:**
- `RevenueStream.loe_tail_years == 5` for all modality profiles
- Year 4 and year 5 post-LOE revenues are correct fractions of peak
- Profiles missing year_4/year_5 keys terminate early without KeyError
- `total_years == patent_life_years + 5` for standard profiles

---

## PHASE 3 — Input Validation & False Precision

> No output value changes. New validation logic and warnings only.
> Can be implemented independently of Phases 1+2.

---

### Task 9.11 — G2N / Price Basis Validation

**Audit finding:** There is no validation that `net_price_per_patient_usd` is
actually a net price (post-G2N) rather than a WAC/list price. Users passing WAC
overstate revenue by 30-45% depending on modality — silently.

**Fix:**

**`src/bve/models/market_model.py`** — add a `price_basis` field:
```python
class PriceBasis(str, Enum):
    NET = "net"         # already net of G2N — no adjustment applied
    WAC = "wac"         # wholesale acquisition cost — G2N will be auto-applied
    LIST = "list"       # same as WAC for modeling purposes

price_basis: PriceBasis = Field(
    default=PriceBasis.NET,
    description=(
        "Whether net_price_per_patient_usd (or TAM) is already net of gross-to-net "
        "discounts (G2N). If WAC/LIST, the engine will apply the modality-appropriate "
        "G2N rate from industry_assumptions.yaml automatically."
    )
)
```

In `MarketModel.revenue_in_year()`, if `price_basis == WAC`:
```python
# Auto-apply G2N at calculation time (not stored — price field stays as-entered)
g2n = loader.gross_to_net(asset_modality)  # from assumptions
effective_price = self.net_price_per_patient_usd * (1.0 - g2n)
# use effective_price instead of self.net_price_per_patient_usd
```

Note: `MarketModel` doesn't know the asset modality. Pass `modality` as an
optional init argument, or compute the G2N factor externally and store it as
`_g2n_rate: float` on the model (computed in `ValuationEngine` at construction
time from `asset.modality`).

Preferred design: Add `gross_to_net_rate: Optional[float] = None` to `MarketModel`.
When `price_basis == WAC` and `gross_to_net_rate` is set, auto-apply. When
`price_basis == WAC` and `gross_to_net_rate` is None, emit `UserWarning` with
the modality-default G2N rate and instruct the analyst to set it.

**Plausibility ceiling check:**
```python
# Soft warning: price > $2M/patient for non-gene-therapy is unusual
if (self.net_price_per_patient_usd > 2_000_000
        and self.price_basis == PriceBasis.NET):
    warnings.warn(
        f"net_price_per_patient_usd={self.net_price_per_patient_usd:,.0f} is unusually "
        "high for a non-gene-therapy asset. Confirm this is a net price (post-G2N) "
        "and not a WAC/list price.",
        UserWarning,
    )
```

**Files touched:**
- `src/bve/models/market_model.py`
- `src/bve/valuation/valuation_engine.py` (pass G2N rate at construction)
- `src/bve/config/assumptions.py` (add `gross_to_net(modality)` loader)
- All example YAML configs (add `price_basis: net` explicitly)
- `tests/` (add G2N auto-apply tests, price plausibility warning tests)

**Acceptance criteria:**
- `price_basis: wac` with `gross_to_net_rate: 0.30` produces revenue 30% lower
- `price_basis: net` produces unchanged revenue
- Plausibility warning fires for `net_price > $2M` for non-gene-therapy
- Example configs all have explicit `price_basis: net`

---

### Task 9.12 — Output Precision Guard

**Audit finding:** `rnpv_millions: 138.82` (to cents) on a model where the
dominant input (peak penetration) has ±50% uncertainty. Reporting to 2 decimal
places is epistemically dishonest and will be challenged by institutional reviewers.

**Fix:**

**`src/bve/models/rnpv_model.py`** — change the final return rounding:
```python
# BEFORE
rnpv_millions=round(rnpv, 2),

# AFTER: round to nearest $1M; false precision below $1M is noise
rnpv_millions=round(rnpv, 0),
```

Apply same rounding to all major output fields in `RNPVResult`:
- `gross_revenue_pv_millions`: round to 0
- `probability_adjusted_revenue_pv_millions`: round to 0
- `trial_costs_pv_millions`: round to 1 (costs matter to $0.1M)
- `peak_sales_millions`: round to 0

**`src/bve/models/monte_carlo.py`** — round MC percentiles to nearest $5M:
```python
# MC output: round P5/P25/P75/P95 to nearest $5M
# rationale: MC precision is entirely determined by ESS priors;
# reporting $47.3M vs $50M implies false sample accuracy
def _round_to_nearest(value: float, nearest: float = 5.0) -> float:
    return round(value / nearest) * nearest
```

**`src/bve/reporting/`** — update memo templates to display rNPV as whole numbers
with a note that figures are rounded to the nearest $1M.

**Files touched:**
- `src/bve/models/rnpv_model.py`
- `src/bve/models/monte_carlo.py`
- All regression test fixtures (expected values change in decimal places only)

**Regression impact:** Test fixture values need decimal place updates, not
substantive changes. Tests should use `pytest.approx(value, abs=1.0)` for
monetary comparisons rather than exact equality.

**Acceptance criteria:**
- `RNPVResult.rnpv_millions` is always an integer-valued float (e.g., 139.0 not 138.82)
- MC P5/P95 are multiples of 5
- All existing tests pass with `abs=1.0` tolerance

---

### Task 9.13 — Tornado Expansion (5 → 8 Parameters)

**Audit finding:** Sensitivity analysis tests only 5 parameters: POS, peak sales,
discount rate, years to peak, patent life. Tax rate (after Task 9.1), G2N rate,
and competitive entry count are first-order sensitivities missing from the tornado.

**Fix:**

**`src/bve/valuation/valuation_engine.py`** — in `_compute_sensitivities()`,
add three new perturbation cases:

```python
# 6. Effective tax rate ±5pp
# (0.16 → 0.26 for base of 0.21)
sensitivity_points.append(
    _perturb_tax_rate(asset_modified, trials, market_model, loe_profile, deal,
                      low_delta=-0.05, high_delta=+0.05)
)

# 7. Gross-to-net rate ±10pp
# (models payer pressure scenarios; net revenue sensitivity)
sensitivity_points.append(
    _perturb_g2n_rate(asset, trials, market_model_modified, loe_profile, deal,
                      low_delta=-0.10, high_delta=+0.10)
)

# 8. Competitive entries (+1 / +2 approved competitors at launch)
# (models crowding scenarios using CompetitionModel or penetration haircut)
sensitivity_points.append(
    _perturb_competition(asset, trials, market_model_modified, loe_profile, deal)
)
```

The G2N perturbation applies multiplicatively to `net_price_per_patient_usd`
(or TAM): `effective_revenue = revenue × (1 - g2n_delta)`.

The competition perturbation adds 1 or 2 generic competitors to `CompetitionModel`
(or reduces peak penetration by `competition.penetration_haircut_per_competitor`
per the existing YAML config) if no explicit `CompetitionModel` is set.

**Files touched:**
- `src/bve/valuation/valuation_engine.py`
- `src/bve/valuation/outputs.py` (SensitivityPoint stays the same; just more of them)
- `tests/` (update sensitivity count from 5 to 8; add parameter name checks)

**Acceptance criteria:**
- `ValuationOutput.sensitivities` has 8 entries
- Tornado sorted by `|swing|` still works (highest-swing parameter first)
- `effective_tax_rate`, `gross_to_net`, `competition_entries` appear as parameter names

---

### Task 9.14 — POS Double-Counting Block

**Audit finding:** `check_pos_layer_overlap()` only warns about
`has_breakthrough_designation ↔ BREAKTHROUGH_DESIGNATION` and
`endpoint_type ↔ endpoint_basis` overlap. It does not block. An analyst can
double-count +0.70 log-odds of endpoint effect with no error.

**Fix:**

**`src/bve/models/pos_model.py` / `src/bve/models/trial_design_features.py`**

Change `check_pos_layer_overlap()` to raise `ValueError` when
`has_critical_overlap == True`, unless the caller explicitly passes
`allow_overlap=True` to opt-out.

```python
def check_pos_layer_overlap(
    pos_adjusters: POSAdjusters,
    design_features: TrialDesignFeatureSet,
    phase: TrialPhase,
    *,
    allow_overlap: bool = False,   # ADD escape hatch for tests
) -> LayerOverlapReport:
    ...
    if report.has_critical_overlap and not allow_overlap:
        raise ValueError(
            f"Critical POS layer overlap detected: {report.overlapping_signals}. "
            f"Estimated double-count: {report.estimated_double_count_logodds:.2f} log-odds. "
            "Remove the overlapping factor from one layer or set allow_overlap=True to proceed."
        )
    return report
```

**`src/bve/valuation/valuation_engine.py`** — call `check_pos_layer_overlap()`
in `_prepare_trials()` for each phase where both `pos_adjusters` and
`design_adjusters` are set. Raise before entering the computation, not after.

**Files touched:**
- `src/bve/models/trial_design_features.py`
- `src/bve/valuation/valuation_engine.py`
- `tests/test_phase1.py` (update overlap tests to expect `ValueError`)

**Acceptance criteria:**
- Setting `has_breakthrough_designation=True` in Layer 1 AND
  `ApprovalPathway.BREAKTHROUGH_DESIGNATION` in Layer 2 raises `ValueError`
- Same for `EndpointType.HARD_CLINICAL` + `EndpointBasis.HARD_CLINICAL`
- `allow_overlap=True` suppresses the error and returns the report with a
  `has_critical_overlap=True` flag
- Tests that currently test overlap warnings are updated to expect `ValueError`

---

### Task 9.15 — Phase Cost Override Enforcement

**Audit finding:** Assets without explicit phase cost overrides silently use
industry median costs ($25M/$75M/$225M). In rare disease (Phase 2 can cost $15M)
or large oncology RCT (Phase 3 can cost $500-800M), this is a 2-4× error.

**Fix:**

**`src/bve/entities/trial.py`** — add a `cost_source` field:
```python
cost_source: str = Field(
    default="default",
    description="'default' if cost is from industry median; 'override' if asset-specific."
)
```

**`src/bve/valuation/valuation_engine.py`** — in `run()`, check for default costs:
```python
from bve.config.constants import PHASE_COSTS_MILLIONS  # industry medians

for trial in self.trials:
    if trial.cost_source == "default":
        warnings.warn(
            f"Trial {trial.phase.value} for asset '{self.asset.id}' is using "
            f"the industry median cost (${trial.cost_millions:.0f}M). "
            "Override with asset-specific estimates for BD deal accuracy.",
            UserWarning,
        )
```

**All example YAML configs** — add `cost_source: override` to all trial
cost entries that have been explicitly researched, and `cost_source: default`
to any using the default value.

**Files touched:**
- `src/bve/entities/trial.py`
- `src/bve/valuation/valuation_engine.py`
- `examples/configs/*.yaml`
- `tests/` (add warning test for default costs)

**Acceptance criteria:**
- Default-cost trials emit `UserWarning` mentioning phase and asset_id
- Trials with `cost_source: override` are silent
- No existing test values change (warning only)

---

## PHASE 4 — Scoring System Safety

> Intelligence layer only. Isolated from core engine.
> Can be implemented in parallel with Phases 1-3.

---

### Task 9.16 — Capital Risk Hard Gate

**Audit finding:** `CapitalRisk.CRITICAL` applies only a -0.15 composite score
penalty. On a Tier A asset with `ranking_score: 0.72`, the composite can still
exceed 0.50 after the penalty — triggering "add" on a company potentially 3 months
from insolvency. This is a live risk with the current tracked universe.

**Fix:**

**`src/bve/intelligence/actionable_output.py`** — in `ActionableGenerator._score()`:
```python
# BEFORE: capital risk is a continuous penalty
composite -= capital_risk_discount  # -0.15 for CRITICAL

# AFTER: CRITICAL capital risk = hard "avoid" gate regardless of composite score
if capital_risk_level == CapitalRisk.CRITICAL:
    action = "avoid"
    composite = max(0.0, composite - 0.15)  # still penalise for ranking order
    # Do NOT apply the 0.50 threshold check — gate overrides it
    return ScoredCandidate(action="avoid", composite_score=composite, ...)
```

Also add a distinct `action: "reduce"` for `CapitalRisk.HIGH`:
- `HIGH` capital risk → composite penalty of -0.08 AND if composite crosses from
  above 0.50 to below 0.50, action = "reduce" instead of "hold".

**Files touched:**
- `src/bve/intelligence/actionable_output.py`
- `tests/` (add CRITICAL capital risk hard-gate test; verify "avoid" action
  fires even for Tier A assets with CRITICAL risk)

**Acceptance criteria:**
- Tier A asset (ranking=0.72) with CRITICAL capital risk → action = "avoid"
- Tier A asset with HIGH capital risk, composite after penalty < 0.50 → action = "reduce"
- Tier A asset with HIGH capital risk, composite after penalty ≥ 0.50 → action = "add" (no change)
- Composite score is still penalised for ranking order even when action is forced

---

### Task 9.17 — Score Bounds Clamping + Signal Validation

**Audit finding:** Stacked positive signal adjustments can produce composite
score > 1.0. No bounds check exists. Also, `LLM extraction confidence gating`
(0.3/0.5) is arbitrary and uncalibrated.

**Fix A — Score clamping:**

**`src/bve/intelligence/actionable_output.py`**:
```python
# After all signal adjustments are applied:
composite = max(0.0, min(1.0, composite))
```

Add an assertion in debug mode:
```python
assert 0.0 <= composite <= 1.0, f"Composite out of bounds: {composite}"
```

**Fix B — Confidence threshold documentation:**

**`src/bve/config/industry_assumptions.yaml`** — add:
```yaml
llm_extraction:
  # Confidence thresholds for signal routing.
  # These are PROVISIONAL and uncalibrated. Calibration requires:
  # - 200+ labeled signal outcomes (from forecast_tracker)
  # - Platt scaling or isotonic regression on predicted_confidence vs outcome_correct
  # Current values are conservative heuristics pending calibration.
  discard_threshold: 0.30    # signals below this are discarded entirely
  review_threshold:  0.50    # 0.30-0.50: routed to ReviewQueue
  auto_threshold:    0.50    # ≥ 0.50: auto-processed (still routed for sampling)
  calibration_status: "uncalibrated"   # DOCUMENT STATE
  calibration_required_n: 200          # minimum labeled outcomes before recalibration
```

No threshold value changes now. The fix is to explicitly document the uncalibrated
state so institutional reviewers can audit it, and add a `calibration_status` field
to `CalibrationReporter.report()` that flags when N < 200.

**Files touched:**
- `src/bve/intelligence/actionable_output.py`
- `src/bve/config/industry_assumptions.yaml`
- `src/bve/intelligence/calibration_reporter.py` (add calibration status flag)
- `tests/` (add score bounds test, calibration status test)

**Acceptance criteria:**
- Composite score is always in [0.0, 1.0] regardless of signal stack
- Stacking 5 positive signals on a 0.95 base does not produce > 1.0
- `CalibrationReporter.report()` includes `confidence_calibration_status: "uncalibrated"`
  when N < 200 labeled outcomes

---

## PHASE 5 — Calibration & Statistical Validity

> Replay and backtest work. Isolated from everything else.
> Can start immediately in parallel with Phases 1-4.

---

### Task 9.18 — POS Backtest Dataset Remediation

**Audit finding:** `research/data/oncology_phase_transitions.csv` has N=40 with
82.5% actual success rate. Survivor/selection bias makes all metrics meaningless.
Target: ~40% Phase 2 success rate matching Biomedtracker industry base.

**Fix:**

Add 30-40 real Phase 2/3 failures to the dataset. Each entry requires:
- `trial_id`, `drug_name`, `company`, `indication`, `phase`
- `trial_nct_id` (where available)
- `actual_outcome` (0 = failed, 1 = succeeded)
- `model_predicted_pos`
- `failure_reason` (efficacy, safety, regulatory, discontinued)
- Source reference

**Target additions (publicly documented failures):**
```
Phase 3 failures (announced results):
- Agenus / Incagn2385 (CTLA-4/PD-1 combo) — Phase 2 NSCLC: failed efficacy
- ArQule / varlitinib (pan-HER) — Phase 3 biliary: missed primary endpoint
- Corcept / relacorilant — Phase 3 TNBC: failed (efficacy miss)
- Compass Pathways / psilocybin — Phase 2b TRD: missed secondary endpoints
- Zafgen / ZGN-1061 — Phase 2 obesity: safety signal → discontinued
- GenMark / eSensor — regulatory (comparator failure)
- AstraZeneca / MEDI3506 (tezepelumab PE) — Phase 3: failed primary
- MedImmune / MEDI-7734 — Phase 2 dermatomyositis: failed efficacy
...add to 30-40 failures total

Phase 2 failures:
- Forma / FT-4202 — Phase 2 SCD: missed primary endpoint
- Imago / bomedemstat — Phase 2 ET: missed endpoint
- Protagonist / eptinezumab — Phase 2 IDA: missed
...add to ~20 Phase 2 failures
```

After additions:
- Re-run `python -m bve.analysis.backtest research/data/oncology_phase_transitions.csv`
- Target: Brier score < 0.22, AUC > 0.60, Phase 2 success rate in dataset ~40%

**Files touched:**
- `research/data/oncology_phase_transitions.csv`
- `src/bve/analysis/backtest.py` (update expected baseline metrics in comments)
- `tests/` (add dataset balance check: actual_success_rate < 0.60)

**Acceptance criteria:**
- Dataset has N ≥ 70 entries (40 original + 30+ additions)
- `actual_success_rate` in dataset ≤ 55% (reasonable Phase 2/3 mix target)
- Brier score < 0.22
- AUC > 0.60
- Phase 2 subset: actual success rate between 35-45%

---

### Task 9.19 — Monte Carlo Distribution Improvements

**Audit finding:** Three MC weaknesses:
1. `peak_sales_cv: 0.35` is too narrow for Phase 1/2 assets (10× variation is
   plausible at early stage)
2. ESS values (25-40) are judgment calls with no derivation — too tight for
   early-stage assets
3. No correlation between WACC and commercial assumptions (rate environment
   affects both discount rate and market penetration)

**Fix:**

**`src/bve/config/industry_assumptions.yaml`** — differentiate CV by stage:
```yaml
monte_carlo:
  # Stage-conditional peak sales CV
  # Wider distributions for earlier stages reflect genuine commercial uncertainty
  peak_sales_cv_by_stage:
    phase_1:   0.60   # 10× variation plausible at Phase 1
    phase_2:   0.45   # 5× variation plausible
    phase_3:   0.30   # narrower: market model better defined
    nda_bla:   0.20   # filing stage: market substantially defined
    approved:  0.15   # approved: actual prescriber data begins to anchor
    default:   0.35   # fallback (current value)

  # Stage-conditional ESS for phase success Beta distributions
  # More outcome data at Phase 3 → tighter prior is justified
  phase_ess_by_stage:
    phase_1_ess: 20    # WAS 30 — wider distribution for early stage
    phase_2_ess: 20    # unchanged
    phase_3_ess: 25    # WAS 20 — tighter at Phase 3 (more precedent data)
    nda_bla_ess: 45    # WAS 40 — regulatory precedent well-established
```

**`src/bve/models/monte_carlo.py`** — auto-select `peak_sales_cv` from asset
stage when `mc_params.peak_sales_cv` is at the default value:
```python
def _resolve_peak_sales_cv(asset: Asset, params: MonteCarloParams) -> float:
    if params.peak_sales_cv != MC_PEAK_SALES_CV:  # explicitly set
        return params.peak_sales_cv
    stage_cvs = loader.get("monte_carlo.peak_sales_cv_by_stage", {})
    return stage_cvs.get(asset.stage.value, MC_PEAK_SALES_CV)
```

Add WACC-to-penetration correlation: add a new entry to `DEFAULT_CORRELATION`:
```python
# Higher WACC environments suppress commercial access (payer pushback, pricing pressure)
# Weak negative correlation (-0.15): rate environment affects pricing power
DEFAULT_CORRELATION = CorrelationSpec(pairs={
    ...existing pairs...,
    ("discount_rate", "peak_sales"): -0.15,   # ADD
})
```

**Files touched:**
- `src/bve/config/industry_assumptions.yaml`
- `src/bve/models/monte_carlo.py`
- `src/bve/models/correlations.py`
- `tests/test_models.py` (update MC width tests; Phase 1 should show wider CI than Phase 3)

**Acceptance criteria:**
- Phase 1 asset MC P5-P95 width is at least 1.5× wider than Phase 3 asset MC width
- ESS values match stage-conditional table
- WACC-to-peak-sales correlation is negative in the correlation matrix
- All existing MC tests pass with updated expected ranges

---

### Task 9.20 — Replay Statistical Graduation

**Audit finding:** The replay produces N=4-20 closed positions, which is
statistically inadmissible. `alpha_survives_corrections = False` on all runs.
`AlphaValidationReport` and `EdgeDecompositionReport` exist but cannot be run
meaningfully until N ≥ 30.

**Fix (two-step):**

**Step 1: Extend replay universe to 2024-01-01**

Seed all 27 universe tickers from 2024-01-01:
```bash
python -m bve.ops.historical_replay seed \
    --tickers VKTX ALNY SRPT NTLA VRTX CRSP BEAM RXRX MRNA BMRN REGN LLY \
              KYMR ARVN RVMD MDGL IMVT FULC FATE OCUL SRRK IOVA NVAX AMRN \
              PRTA EDIT ZYME XBI \
    --start 2024-01-01 --end 2026-03-01
```

Seed real 2024 catalyst events (minimum 25 events across the universe):
```yaml
# research/replay/events_2024.yaml — source list for manual seeding
# Each event requires: asset_id, event_type, announced_at (exact date), outcome
# Sources: press releases, SEC 8-K filings, company IR pages
#
# Priority events to seed (high signal value, well-documented dates):
# VRTX: VX-548 Phase 3 acute pain readout (Jan 2024) — positive
# ALNY: Alnylam Q1 enrollment update (Apr 2024)
# SRPT: SRP-9001 Phase 3 Duchenne readout (June 2024)
# NTLA: in vivo CRISPR Phase 1 update (Mar 2024)
# MDGL: resmetirom Phase 3 NASH (Mar 2024) — landmark positive
# LLY: orforglipron Phase 3 obesity (Jun 2024) — positive
# KYMR: KYM-001 Phase 2 (Q3 2024)
# ... target 25+ events with documented announcement dates
```

**Step 2: Run and validate**
```bash
# Run replay with extended universe
python -m bve.ops.historical_replay run \
    --start 2024-01-01 --end 2026-03-01 --cadence weekly \
    --decision-policy top2_add --max-hold-days 28 \
    --catalyst-timing --cooling --require-catalyst-days 14

# Run alpha validation (requires N≥10 closed; target N≥30)
python -m bve.analysis.alpha_validation --run-id <run_id>

# Run edge decomposition
python -m bve.analysis.edge_decomposition --run-id <run_id>

# Coverage audit to confirm seeding completeness
python -m bve.analysis.coverage_audit \
    --universe-file examples/research/universe_expanded_mna.yaml \
    --start 2024-01-01 --end 2026-03-01
```

**Step 3: Define formal graduation criteria**

The system graduates from "⚠️ Directional" to "✅ Pre-institutional for HF use" when:
- N ≥ 30 closed positions
- `alpha_survives_corrections == True` (all three: overlap-adjusted, clustered SE, bootstrap)
- Clustered SE p-value < 0.10 (relaxed: small biotech universe limits cluster count)
- Bootstrap 90% CI excludes 0
- Score decile monotonicity: decile 9-10 mean excess return > decile 1-2

**Files touched:**
- `outputs/intelligence/replay_store.sqlite` (seeding)
- `research/replay/events_2024.yaml` (new — sourced catalyst event list)
- `logs/run_metrics.json` (updated post-run)
- `PROJECT_STATE.md` (updated graduation status)

**Acceptance criteria:**
- `coverage_audit` shows ≥ 20 tickers with full price coverage 2024-01-01 to 2026-03-01
- ≥ 25 historical events seeded with documented announcement dates
- N ≥ 30 closed positions after extended replay
- `AlphaValidationReport.stats.n_trades >= 30`
- All four graduation criteria defined above are formally checked and documented

---

## PHASE 6 — Provenance & Auditability

> No model output changes. Metadata and audit trail additions.
> Can be implemented last; does not unblock any other work.

---

### Task 9.21 — Assumption Provenance & Config Hash

**Audit finding:** `ValuationOutput.meta` lacks: assumptions YAML hash, config
hash, WACC vintage date. A reviewer cannot reconstruct why a specific output was
produced or verify the assumption set used.

**Fix:**

**`src/bve/valuation/outputs.py`** — add to `ValuationOutput`:
```python
# Provenance — added for institutional audit trail
assumptions_yaml_hash: Optional[str] = Field(
    default=None,
    description="SHA-256 (first 12 chars) of industry_assumptions.yaml used in this run."
)
config_hash: Optional[str] = Field(
    default=None,
    description="SHA-256 (first 12 chars) of the asset YAML config file."
)
wacc_vintage: Optional[str] = Field(
    default=None,
    description="WACC vintage tag from industry_assumptions.yaml (e.g. '2026-Q1')."
)
analyst_overrides: list[str] = Field(
    default_factory=list,
    description=(
        "Fields explicitly overridden from industry defaults in this run. "
        "e.g. ['discount_rate: 0.12 (default: 0.10)', 'peak_penetration: 0.25']"
    )
)
```

**`src/bve/valuation/valuation_engine.py`** — in `run()`, populate provenance:
```python
import hashlib

def _hash_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]

output.assumptions_yaml_hash = _hash_file(ASSUMPTIONS_YAML_PATH)
if self.config_path:
    output.config_hash = _hash_file(self.config_path)
output.wacc_vintage = loader.get("wacc.vintage", "unknown")
```

**Files touched:**
- `src/bve/valuation/outputs.py`
- `src/bve/valuation/valuation_engine.py`
- `src/bve/reporting/export.py` (include provenance fields in JSON export)
- `tests/` (add provenance field presence tests)

**Acceptance criteria:**
- `ValuationOutput.assumptions_yaml_hash` is populated and 12 chars long
- Re-running with same inputs produces the same hash (deterministic)
- Changing `industry_assumptions.yaml` produces a different hash
- `wacc_vintage` matches the value in the YAML

---

### Task 9.22 — Data Lineage: Signal → Valuation Change

**Audit finding:** When a signal is accepted via ReviewQueue and an assumption
changes, there is no audit trail connecting the specific clinical event to the
specific assumption delta. A compliance reviewer cannot answer "why did Phase 2
POS change from 0.32 to 0.38?"

**Fix:**

**`src/bve/intelligence/knowledge_layer.py`** — extend `audit_log` schema:
```sql
-- Extend the existing audit_log table with new columns (migration-safe via _ensure_column)
ALTER TABLE audit_log ADD COLUMN assumption_field TEXT;       -- e.g. "phase_2_pos"
ALTER TABLE audit_log ADD COLUMN assumption_old_value TEXT;   -- e.g. "0.32"
ALTER TABLE audit_log ADD COLUMN assumption_new_value TEXT;   -- e.g. "0.38"
ALTER TABLE audit_log ADD COLUMN evidence_signal_id TEXT;     -- FK → structured_signals.signal_id
ALTER TABLE audit_log ADD COLUMN review_decision_id TEXT;     -- FK → review_decisions.id
```

**`src/bve/intelligence/knowledge_layer.py`** — update `add_review_decision()`:
When a `ACCEPTED` decision is recorded and the attached `ValuationProposal` has a
`delta_npv` or assumption change, append to `audit_log` with the new fields populated.

**`src/bve/cli/audit_log.py`** — extend `bve-audit-log` CLI:
- Add `--assumption-field` filter
- Add `--signal-id` filter
- Formatted output: "Signal → Review → Assumption change" chain

**Files touched:**
- `src/bve/intelligence/knowledge_layer.py`
- `src/bve/cli/audit_log.py`
- `tests/test_reviewer_annotations.py` (add lineage chain tests)

**Acceptance criteria:**
- Accepting a signal with a POS change populates `assumption_field`, `old_value`,
  `new_value`, `evidence_signal_id` in the audit log entry
- `bve-audit-log --signal-id <id>` shows the full chain: signal → decision → change
- Existing audit log tests pass unchanged

---

## Regression Fixture Update Protocol

When Phases 1+2 are implemented:

1. Run `python -m pytest tests/ -v --tb=no -q` and capture all failures.
2. For each failing test: verify the new value is correct per the mathematical
   change (tax rate, WACC, LOE tail) — do NOT automatically accept changed values.
3. Update fixtures with the verified new values.
4. For tests using exact float equality on `rnpv_millions`, switch to
   `pytest.approx(expected, abs=1.0)` — rNPV to the nearest $1M is appropriate
   precision for a model with ±30% commercial uncertainty.
5. Add a `# updated: Sprint-9 Phase1 — tax treatment + WACC` comment on
   changed fixture values so future auditors can trace the change.
6. Run full suite and confirm zero failures before committing.

---

## Success Metrics

After completing all six phases, the system should meet:

| Metric | Before | Target |
|---|---|---|
| Tax treatment | Missing | UFCF = EBIT × (1-0.21) |
| POS stacking ceiling | None | +0.80 log-odds max Layer 1 delta |
| BTD log-odds | +0.20 | +0.05 |
| Default WACC | 10% | 12% |
| Default uptake shape | Linear (no warning) | Linear (with warning for specialty) |
| Compliance (gene therapy) | 0.80 | 1.00 (warned) |
| Accelerated approval discount | Not modeled | -18% NDA/BLA rate |
| LOE tail years | 3 | 5 |
| Post-approval R&D | Not modeled | Explicit field (default 0) |
| Tornado parameters | 5 | 8 |
| Output precision | 2 decimals | 0 decimals |
| POS double-counting | Warning | ValueError |
| Capital risk CRITICAL | -0.15 penalty | Hard "avoid" gate |
| Score bounds | Unbounded | Clamped [0.0, 1.0] |
| POS backtest success rate | 82.5% (biased) | ≤ 55% (realistic mix) |
| Replay N | 4-20 | ≥ 30 |
| Alpha survives corrections | False | True (target) |
| Provenance hash | Missing | SHA-256 (12-char) |
| Signal→change lineage | Missing | Full audit trail |

**Final tier after all phases complete:**
- Core engine: ✅ Pre-institutional (BD deal screening, VC portfolio support)
- HF use: ✅ Pre-institutional (conditional on replay graduation in Task 9.20)
