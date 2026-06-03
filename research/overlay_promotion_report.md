# Overlay Promotion Report — Sprint 8
**Date:** 2026-04-16 | **Dataset:** bundled oncology (99 records) | **Cutoff:** 2019

---

## 1. Evaluation Setup

| Parameter | Value |
|---|---|
| Dataset | Bundled oncology (pembrolizumab, nivolumab, sotorasib, etc.) |
| Total records | 99 |
| Overall success rate | 50.5% |
| Time-split cutoff | 2019 |
| Train fold (≤ 2019) | 45 records — 35.6% success |
| Test fold (> 2019) | 54 records — 63.0% success |
| Phase distribution (train) | Ph2: 25 / Ph3: 20 |
| Phase distribution (test) | Ph2: 23 / Ph3: 31 |
| Overlay regularization | α = 1.0 (L2) |
| Calibration | Platt scaling, fitted on train fold |

> **Note on success rate shift:** The test fold (2020–2025) has a 63% success rate versus
> 36% in training. This reflects the post-2020 oncology landscape — targeted therapies with
> biomarker-selected populations matured significantly. Any mode that cannot adapt to this
> shift will be systematically under-predicting on the test set.

---

## 2. Mode Comparison — Held-Out Test Set (n=54)

| Mode | Brier ↓ | AUC ↑ | ECE ↓ | Notes |
|---|---|---|---|---|
| heuristic_only | 0.2321 | 0.6926 | 0.1784 | Hand-tuned log-odds; no empirical base |
| empirical_base_only | 0.2373 | 0.5971 | 0.1126 | Phase-level Laplace rate; no adjusters |
| **empirical_heuristic** | **0.2056** ✓ | 0.7162 | **0.1198** ✓ | Empirical base + heuristic adjusters |
| empirical_fitted | 0.2200 | **0.7309** ✓ | 0.1939 | Empirical base + fitted overlay |

**Winner by metric:**
- Brier (primary): `empirical_heuristic` — 0.2056
- AUC: `empirical_fitted` — 0.7309
- ECE: `empirical_heuristic` — 0.1198

**Fitted vs heuristic (Brier):** fitted wins — 0.2200 < 0.2321
**Fitted vs empirical_heuristic (Brier):** fitted loses — 0.2200 > 0.2056

---

## 3. Operational Diagnostics (Test Set, n=54)

| Metric | Value |
|---|---|
| Thin-data warnings (< 5 obs in matched cell) | 0 / 54 (0%) |
| Published-rate fallback (no empirical cell) | 0 / 54 (0%) |
| Overlay applied | 54 / 54 (100%) |
| n_matched records per cell (range) | 9 – 29 |

The base rate table has adequate cell coverage for the test set — no fallback or sparsity issues.
All 54 test records received an overlay-adjusted prediction.

---

## 4. Overlay Training Metrics

| Metric | Base-only | Overlay |
|---|---|---|
| Train Brier | 0.2405 | **0.0997** |
| Test Brier | 0.2373 | **0.2200** |
| Test AUC | 0.5971 | **0.7309** |

**Train-to-test Brier degradation:** 0.0997 → 0.2200 (54% increase)
This gap signals meaningful overfitting. With 45 training records and 12 free parameters
(11 features + intercept), the model fits approximately 1 parameter per 3–4 records.
The L2 penalty is insufficient to close this gap at the current data volume.

---

## 5. Coefficient Table

| Feature | Fitted | Heuristic | Sign? | N_nonzero | Interpretation |
|---|---|---|---|---|---|
| moa_novel | **−1.541** | −0.350 | ✓ | 26 | Correct direction; magnitude 4× heuristic — novel MoA is the strongest failure predictor in this dataset |
| safety_clean | **+1.056** | +0.100 | ✓ | 11 | Correct direction; 10× heuristic — clean safety profile is a strong success predictor in oncology |
| safety_concerning | **−0.832** | −0.350 | ✓ | 12 | Correct direction; 2.4× heuristic |
| biomarker_selected | **+0.790** | +0.400 | ✓ | 16 | Correct direction; ~2× heuristic — consistent with oncology literature |
| **safety_serious** | **+0.717** | **−0.800** | **⚠ WRONG** | **1** | **n=1 training example; coefficient is pure noise. Heuristic is almost certainly correct (serious AE → failure). BLOCKER.** |
| competition_low | **+0.623** | +0.150 | ✓ | 14 | Correct direction; 4× heuristic — aggressive but directionally sound |
| competition_high | **−0.404** | −0.150 | ✓ | 10 | Correct direction; 2.7× heuristic |
| **endpoint_hard_clinical** | **−0.281** | **+0.350** | **⚠ WRONG** | 24 | Sign flip with 24 training examples — clinically ambiguous. Hard endpoints in Ph3 oncology may genuinely be harder to achieve (OS vs ORR), but this contradicts the heuristic. Requires deliberate resolution before promotion. |
| moa_validated | 0.000 | +0.350 | ~0 | **0** | No training examples — completely unlearned |
| endpoint_surrogate_novel | 0.000 | −0.300 | ~0 | **0** | No training examples — completely unlearned |
| endpoint_biomarker_only | 0.000 | −0.550 | ~0 | **0** | No training examples — completely unlearned |

**Intercept:** −0.1248 (modest negative global bias; acceptable — indicates slight downward global shift vs phase-only base rate)

**Summary of coefficient health:**
- 7 / 11 features: correct sign ✓
- 2 / 11 features: wrong sign ⚠ (one a clear blocker, one ambiguous)
- 3 / 11 features: zero / unlearned (zero training observations)

---

## 6. Top 10 Divergences: Fitted vs Heuristic

Records ranked by absolute delta between `empirical_fitted` and `heuristic_only`.

| # | Program | Phase | Outcome | Heuristic | Base | Emp+H | Fitted | Δ |
|---|---|---|---|---|---|---|---|---|
| 1 | poziotinib_2023 | Ph2 | **✗ FAIL** | 0.240 | 0.400 | 0.430 | **0.727** | **+0.487** |
| 2 | navitoclax_2021 | Ph3 | ✗ FAIL | 0.463 | 0.604 | 0.335 | **0.086** | −0.376 |
| 3 | galunisertib_2020 | Ph3 | ✗ FAIL | 0.550 | 0.604 | 0.417 | **0.179** | −0.371 |
| 4 | dostarlimab_2021 | Ph2 | **✓ PASS** | 0.437 | 0.400 | 0.650 | **0.788** | +0.351 |
| 5 | umbralisib_2022 | Ph3 | ✗ FAIL | 0.513 | 0.604 | 0.712 | **0.228** | −0.285 |
| 6 | navicixizumab_2022 | Ph2 | ✗ FAIL | 0.320 | 0.400 | 0.387 | **0.087** | −0.233 |
| 7 | inavolisib_2024 | Ph3 | ✓ PASS | 0.668 | 0.604 | 0.920 | **0.895** | +0.227 |
| 8 | inavolisib_breast_2024 | Ph3 | ✓ PASS | 0.668 | 0.604 | 0.920 | **0.895** | +0.227 |
| 9 | lorlatinib_2021 | Ph3 | ✓ PASS | 0.634 | 0.604 | 0.908 | **0.851** | +0.216 |
| 10 | brigatinib_2020 | Ph3 | ✓ PASS | 0.634 | 0.604 | 0.908 | **0.851** | +0.216 |

### Feature-level decomposition for top 5

**#1 poziotinib_2023** — fitted=0.727, actual=FAIL, Δ=+0.487
```
  biomarker_selected   : +0.790   (drug had biomarker-enriched population)
  safety_serious       : +0.717   ← WRONG SIGN (n=1 artifact)
  intercept            : −0.125
  base prior (Ph2)     :  0.400
  → overlay pushed a failed drug to 0.727 — the worst error in the dataset
  → root cause: safety_serious coefficient is noise from one training record
```

**#2 navitoclax_2021** — fitted=0.086, actual=FAIL, Δ=−0.376
```
  moa_novel            : −1.541   (BCL2 inhibitor — novel mechanism at time)
  safety_concerning    : −0.832   (thrombocytopenia signal)
  endpoint_hard_clinical: −0.281
  intercept            : −0.125
  base prior (Ph3)     :  0.604
  → correctly predicted failure; largest correct downward move in dataset
```

**#3 galunisertib_2020** — fitted=0.179, actual=FAIL, Δ=−0.371
```
  moa_novel            : −1.541   (TGF-β inhibitor — novel MoA)
  endpoint_hard_clinical: −0.281
  intercept            : −0.125
  base prior (Ph3)     :  0.604
  → correctly predicted failure
```

**#4 dostarlimab_2021** — fitted=0.788, actual=PASS, Δ=+0.351
```
  safety_clean         : +1.056   (PD-1 inhibitor, tolerable profile)
  biomarker_selected   : +0.790   (dMMR/MSI-H selection)
  intercept            : −0.125
  base prior (Ph2)     :  0.400
  → correctly predicted success (FDA accelerated approval)
```

**#5 umbralisib_2022** — fitted=0.228, actual=FAIL, Δ=−0.285
```
  safety_concerning    : −0.832   (hepatotoxicity concern)
  competition_high     : −0.404   (crowded PI3Kδ space)
  endpoint_hard_clinical: −0.281
  intercept            : −0.125
  base prior (Ph3)     :  0.604
  → correctly predicted failure (ultimately withdrawn from market)
```

**Pattern:** 9 of 10 top divergences are directionally correct. The single egregious error
(poziotinib) is entirely attributable to the `safety_serious` coefficient learned from one data point.

---

## 7. Critical Issues

### BLOCKER: safety_serious coefficient is clinically nonsensical

- **Fitted:** +0.717 (predicts serious adverse events *increase* probability of success)
- **Heuristic:** −0.800 (serious AEs decrease probability — clinically correct)
- **Root cause:** exactly 1 training record had `safety_serious = True` (poziotinib, which
  advanced in 2019 despite concerns). L2 regularization at α=1.0 did not shrink this to
  zero because the optimizer still sees positive gradient pressure from one success outcome.
- **Impact:** produces the largest and most dangerous error in the test set (poziotinib_2023:
  actual failure predicted at 0.727). Any asset with a serious adverse event signal will
  receive an *inflated* POS rather than a penalty.
- **Fix required:** a minimum-observations guard (`n_feature_nonzero < 5` → use heuristic
  value) or a hard prior constraint forcing safety features to match the heuristic sign.

### WARNING: endpoint_hard_clinical sign flip

- **Fitted:** −0.281 | **Heuristic:** +0.350 — opposite signs with n=24 observations
- **Possible valid interpretation:** hard clinical endpoints (OS vs ORR in Ph3 oncology)
  are genuinely harder to achieve, so the data may be capturing real regulatory risk that
  the heuristic over-credits. The 2020–2025 test set success rate of 63% does not
  sufficiently punish hard endpoints to resolve this ambiguity.
- **Not a clear blocker** but requires deliberate documented resolution before promotion.
  Currently the fitted model will penalize trials with hard endpoints; the heuristic rewards
  them. These are opposite financial recommendations.

### DATA GAP: three features have zero training observations

- `moa_validated`, `endpoint_surrogate_novel`, `endpoint_biomarker_only` — all zero nonzero
  training records in the 45-record train fold.
- For any asset with these features, the fitted overlay contributes nothing (coefficient = 0)
  where the heuristic would apply ±0.30–0.55 log-odds. The fitted path silently degrades to
  the base rate for these cases.

### OVERFITTING: train-to-test Brier gap

- Train Brier 0.0997 → Test Brier 0.2200: 54% degradation.
- 45 training records / 12 free parameters ≈ 3.75 records per parameter.
- α=1.0 is insufficient regularization at this data volume. A reasonable target is
  α=3.0–5.0 to prevent unstable coefficients on low-count features.

---

## 8. Verdict

> ### KEEP EXPERIMENTAL — do not promote to default

### What went right

The overlay has absorbed real signal from the data. Novel MoA is the strongest failure
predictor (−1.541). Clean safety profile and biomarker enrichment are the strongest
success predictors. Competition pressure lands in the correct direction. In 9 of 10 largest
divergence cases, the overlay made a directionally correct call that the heuristic missed or
understated. On AUC, the fitted overlay leads all modes (0.7309).

### Why it cannot be promoted

**Primary bar not cleared:** The decision rule requires fitted to clearly beat heuristic on
held-out Brier. It does beat the heuristic (0.2200 vs 0.2321), but loses to
`empirical_heuristic` (0.2200 vs 0.2056). Empirical base + heuristic adjusters is currently
the better combination — it provides the superior Brier and ECE without the coefficient
instability risk.

**Safety blocker:** The `safety_serious` coefficient is wrong-signed and learned from one
observation. This is not a model failure that can be tuned away at the current data volume
— it is a data availability failure. Promoting a model that rewards serious adverse events
with higher POS estimates is clinically unacceptable.

**ECE regression:** ECE = 0.1939 for fitted vs 0.1198 for empirical_heuristic. The fitted
overlay is less calibrated than the heuristic-augmented path on the held-out set. For
valuation purposes, calibration error directly affects rNPV accuracy.

---

## 9. Recommended Path to Promotion

| Step | Action | Target |
|---|---|---|
| 1 | Expand dataset | ≥ 150 records; ≥ 5 each for `safety_serious`, `moa_validated`, `endpoint_surrogate_novel` |
| 2 | Add minimum-obs guard | Zero out coefficients with `n_feature_nonzero < 5`; replace with heuristic value |
| 3 | Increase regularization | Try α = 3.0 – 5.0 to shrink low-evidence coefficients further |
| 4 | Resolve endpoint_hard_clinical | Accept data-driven sign with documentation, or pin to heuristic sign |
| 5 | Re-run evaluation | Fitted must beat `empirical_heuristic` on Brier **and** not worsen ECE vs heuristic |
| 6 | Calibrate the fitted overlay | Apply Platt/isotonic on top of fitted path to recover ECE gap |

Until steps 1–3 are complete, `empirical_heuristic` is the recommended default empirical mode.
The fitted overlay should be available as an experimental opt-in (`POSMode.EMPIRICAL_FITTED`)
for research use with explicit disclosure of the `safety_serious` instability.
