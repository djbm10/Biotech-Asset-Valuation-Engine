# Biotech Asset Valuation Engine — Methodology White Paper

**Version:** 1.0 | **Date:** 2026-05-15 | **Status:** RESEARCH_GRADE

---

## 1. Purpose and Intended Use

The Biotech Asset Valuation Engine (BVE) is a quantitative tool designed to support
structured analysis of biopharmaceutical assets for:

- BD / M&A screening and prioritisation
- Event-driven investment thesis development
- Portfolio risk management and position sizing
- IC-level discussion facilitation

The system integrates probability-of-success (POS) modelling, risk-adjusted NPV (rNPV)
computation, competitive dynamics, and deal economics into a single reproducible framework.

---

## 2. Not Intended Uses

- **Autonomous capital deployment:** Model outputs are not a substitute for human IC review.
- **Regulatory submission:** No output of this system constitutes clinical or regulatory advice.
- **Real-time trading signals:** Scores are batch-computed and not designed for HFT or intraday use.
- **Legal or compliance advice:** M&A probability estimates are not legal opinions.
- **Company-level underwriting without enhancement:** The current model is asset-centric; company-level credit or equity underwriting requires additional layers.

---

## 3. rNPV Methodology

### Formula

```
rNPV = P(approval) × PV(EBIT post-launch) − Σ[P(reaching phase_i) × PV(cost_i)]
```

### Revenue computation

- Revenue materialises from years 1 through `patent_life_years` post-launch.
- Three revenue modes: `lines_of_therapy`, patient-based, TAM-based.
- SG&A ramps from 40% → 20% over 5 years post-launch.
- Optional LOE tail: post-patent revenue collapses per modality-specific erosion profile.

### Cost computation

- Phase costs discounted at midpoint = `(year_start + year_end) / 2`.
- Each phase cost is weighted by `P(reaching that phase)`.
- Deal terms: `cdev_cost_share` scales R&D; milestone PVs folded into cost stream.

### Discount rate

- Default: 10% p.a. (appropriate for well-capitalised drug candidates with known risk profile)
- Adjustable per asset; higher rates appropriate for earlier-stage or higher-risk assets.

---

## 4. POS Model

### Architecture

Two-layer log-odds model applied to Biomedtracker/IQVIA industry base rates:

**Layer 1 — POSAdjusters:**
- Endpoint type (surrogate vs. primary)
- MoA precedent
- Sample size adequacy
- Safety signal
- Competitive pressure
- Biomarker enrichment (+0.40 log-odds)
- Breakthrough designation (+0.20 log-odds)
- Prior phase data strength

**Layer 2 — TrialDesignFeatureSet:**
- EndpointBasis (mechanistic, surrogate, clinical)
- EvidenceDesign (observational, single-arm, RCT)
- ApprovalPathway (standard, accelerated, breakthrough, PRV)
- Phase-conditional scaling applied (Phase 1: low weight; Phase 3: full weight)

### Anti-double-counting

A `check_pos_layer_overlap()` guard detects when both layers adjust the same factor
(e.g., endpoint_type ↔ endpoint_basis overlap) and emits a `LayerOverlapReport`.

### Current calibration status: SCREENING_GRADE

N=99 programs (oncology Phase 2/3). Brier=0.2127, AUC=0.74. Target for IC_REVIEW_GRADE: N≥300.

---

## 5. Revenue Model

Revenue is computed by `RevenueModel.compute(market_model)`:

1. Uptake curve: S-curve from `years_to_peak` and `peak_penetration`.
2. Annual revenue = uptake × addressable_patients × net_price (or LOT/TAM mode equivalents).
3. Gross profit = revenue × (1 − COGS).
4. EBIT = gross profit − SG&A (ramping schedule).
5. LOE tail: optional 3-year tail at modality-specific erosion rates.

**Boundary**: Revenue model has no deal parameters. All royalty reduction happens in RNPVModel.

---

## 6. Cost Model

Inputs: `ProbabilityResult`, `discount_rate`, optional `DealEconomics`.

- Phase costs probability-weighted and PV'd at midpoint.
- `cdev_cost_share` scales all trial costs (default: 1.0 = fully borne by asset owner).
- Payable milestone PVs added at appropriate probabilities.
- Upfront cost at face value.

---

## 7. M&A Scoring

### Current status: UNVALIDATED

The M&A scoring layer (`intelligence/ma_probability.py`) produces a composite score:

```
composite = ranking × 0.50 + thesis × 0.30 + opportunity × 0.20
```

With `thesis_strength=None` (no resolved claims), the neutral value of 0.5 is substituted.
Assets scoring ≥ 0.50 receive "add" action.

### Acquirer fit scoring

Strategic fit sub-score based on: therapeutic area overlap, pipeline gap analysis,
patent cliff urgency, balance sheet capacity.

### Validation requirement

Before M&A scores are labelled IC_REVIEW_GRADE: N≥150 deals with non-deal controls,
Precision@10 ≥ 0.20, Buyer-ID Top-3 accuracy ≥ 0.40.

---

## 8. Calibration Method

### POS calibration

Expected Calibration Error (ECE) and Brier score computed across holdout set.
Calibration bucket analysis: 10 bins of 0.1 each, actual vs. predicted frequencies.

### Recalibration schedule

- Triggered when ECE drift > 0.03 from baseline OR on 6-month schedule.
- All recalibrations logged to governance log with before/after metrics.

---

## 9. Data Sources

See `DATA_SOURCE_POLICY.md` and `src/bve/data/source_contracts.yaml` for full specifications.

| Source | Use | PIT safe | License |
|--------|-----|----------|---------|
| ClinicalTrials.gov | Trial data | partial | public |
| SEC EDGAR | Financials | full | public |
| yfinance | Prices (research only) | no | scraped |
| FDA drug DB | Approval dates | partial | public |
| Biomedtracker | Base rates | no | licensed |

---

## 10. Validation Results

See `VALIDATION_STANDARD.md` for full gate definitions.

| Model | Grade | N | Brier | AUC |
|-------|-------|---|-------|-----|
| POS model | SCREENING_GRADE | 99 | 0.2127 | 0.74 |
| Valuation model | RESEARCH_GRADE | 2 | n/a | n/a |
| M&A ranking | UNVALIDATED | 0 | n/a | n/a |
| Catalyst model | UNVALIDATED | 0 | n/a | n/a |

---

## 11. Known Limitations

1. **Company-level underwriting absent.** The current engine is asset-centric. Company management quality, balance sheet, and option value across multiple programs are not fully modelled.

2. **Survivor bias in historical data.** yfinance and IQVIA estimates exclude delisted/failed programs. Results may be optimistic.

3. **Small POS backtest dataset.** N=99 is insufficient for statistical significance at IC_REVIEW_GRADE. Phase 2 and Phase 3 base rates are at realistic industry levels; further expansion needed.

4. **No-lookahead relay but seeding risk.** Historical replay isolates data by `known_at`, but seeded catalyst events require manual date accuracy verification.

5. **Revenue model is aggregate, not patient-level.** Payer mix, geography, and indication-specific adherence are simplified.

6. **M&A scores are unvalidated.** All M&A outputs carry an UNVALIDATED badge and must not be used for capital deployment decisions.

7. **Discount rate is fixed per-asset.** Stochastic discount rate modelling (e.g., macro rate scenarios) is not yet implemented.

---

## 12. Model Governance

See `ROADMAP_LOCK.md` for the four-lane architecture boundary.
See `ARCHITECTURE_BOUNDARIES.md` for allowed cross-lane patterns.
See `CHANGE_REQUEST_TEMPLATE.md` for required change classification.

All Lane 1 changes require quant + clinical sign-off.
All material assumption changes must be documented via `AssumptionOwner` records.
Expired assumptions trigger `STALE_INPUT` warnings and cap M&A classification at `catalyst_watch`.

---

## 13. Change Control

1. Complete `CHANGE_REQUEST_TEMPLATE.md` before starting work.
2. If `core_output_changed: true`, run full regression test suite.
3. Validate that Brier / AUC does not materially worsen.
4. Update `ValidationRegistry` grade if appropriate.
5. Commit with Conventional Commit message citing lane and affected outputs.

---

## 14. Example Case Study

**Case: VRTX ivacaftor (2010)**

- Phase: Phase 3
- Therapeutic area: rare disease (cystic fibrosis)
- Pre-validation evidence: mechanistic precedent for CFTR potentiation, strong Phase 2 signal
- Actual outcome: FDA approval 2012; peak sales ~$1.8B
- Implied POS from market cap: out-of-range (market pricing multi-indication platform optionality)
- Key lesson: single-indication rNPV model underestimates franchise value; pipeline optionality requires multi-indication engine (`MultiIndicationProgram`).

**Case: INCY ruxolitinib (2010)**

- Phase: Phase 3
- Therapeutic area: hematologic malignancy (MF)
- Actual outcome: FDA approval 2011; later approved in PV, GvHD, alopecia
- Implied POS ~114%: NPV conservative; market pricing multi-indication expansion
- Key lesson: JAK inhibitor class was novel in 2010; MoA precedent adjuster should have been more cautious.
