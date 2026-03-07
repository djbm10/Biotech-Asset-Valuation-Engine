# Case Studies

Three real public companies analyzed through different institutional lenses.
Each case study produces a full memo, 5 charts, and a machine-readable valuation JSON.

All inputs are documented in the YAML config with source citations.
All outputs are reproducible: re-run the command to get the same result (seed=42).

---

## Case 1: Relay Therapeutics (RLAY) / RLY-2608

**Type:** BD Acquisition Analysis
**Asset:** RLY-2608 — mutant-selective PI3Ka inhibitor (H1047R)
**Indication:** HR+/HER2- metastatic breast cancer (2nd/3rd line), US
**Stage:** Phase 2 (ACUITY cohort expansion ongoing)

**Key question:** Is RLY-2608 worth acquiring, and at what price?

**Valuation summary (base case):**

| Metric | Value |
|--------|-------|
| rNPV | $129M |
| P(Approval) | 34.6% |
| Peak Sales | $539M |
| NAV/Share (incl. $410M cash) | $5.76 |
| Current Price | $5.80 |
| Implied upside to NAV | -1% |
| MC P50 | $38M |
| MC P10 – P90 | -$60M to $262M |
| Bull / Base / Bear | $858M / $129M / -$120M |

**Variant perception:** Market-implied P(approval) ≈ 20%; model says 34.6%.
Gap driven by underappreciation of inavolisib approval de-risking the regulatory path
and RLY-2608's tolerability advantage enabling CDK4/6 combinations.

**Kill criterion:** Phase 2 ORR < 30% in H1047R cohort.

**Config:** [`../examples/configs/relay_rly2608.yaml`](../examples/configs/relay_rly2608.yaml)

**Outputs:**
- [`relay_rly2608/RLAY/bd_memo.md`](relay_rly2608/RLAY/bd_memo.md) — BD acquisition memo
- [`relay_rly2608/RLAY/hf_memo.md`](relay_rly2608/RLAY/hf_memo.md) — HF event-driven analysis
- [`relay_rly2608/RLAY/valuation.json`](relay_rly2608/RLAY/valuation.json) — full machine-readable output
- [`relay_rly2608/RLAY/charts/`](relay_rly2608/RLAY/charts/) — 5 charts

**Reproduce:**
```bash
bve-asset --config examples/configs/relay_rly2608.yaml --all-memos --charts \
          --out case_studies/relay_rly2608 --seed 42
```

---

## Case 2: EyePoint Pharmaceuticals (EYPT) / EYP-1901

**Type:** Hedge Fund — Market Mispricing Thesis
**Asset:** EYP-1901 (vorolanib) — sustained-release pan-VEGF TKI via Durasert implant
**Indication:** Neovascular AMD (wet AMD), US
**Stage:** Phase 3 (ACUITY trial, NCT05536297)

**Key question:** Is the market mispricing the dosing-burden advantage of semi-annual treatment?

**Valuation summary (base case):**

| Metric | Value |
|--------|-------|
| rNPV | $235M |
| P(Approval) | 71.9% |
| Peak Sales | $220M |
| NAV/Share (incl. $195M cash) | $13.02 |
| Current Price | $14.50 |
| Implied upside to NAV | -10% |
| MC P50 | $132M |
| MC P10 – P90 | $29M to $331M |
| Bull / Base / Bear | $712M / $235M / -$37M |

**Variant perception:** Market treats EYP-1901 as "me-too anti-VEGF" and discounts
delivery innovation. Real-world wet AMD adherence data shows ~40% of patients undertreated
with current monthly/bimonthly regimens — semi-annual dosing is the structural fix.
Market appears to price ~35% P(approval); model says 71.9% (ophthalmology Phase 3 priors +
validated MoA + strong Phase 2 NI data + clean safety).

**Kill criterion:** ACUITY BCVA inferiority by > 4 ETDRS letters vs. aflibercept; OR < 50%
of patients maintaining 6-month dosing interval.

**Key risks:** Payer pricing resistance (vs. generic alternatives in smaller patient subsets);
NI trial design provides no evidence of superiority — approved label will say "non-inferior."

**Config:** [`../examples/configs/eypt_eyp1901.yaml`](../examples/configs/eypt_eyp1901.yaml)

**Outputs:**
- [`eypt_eyp1901/EYPT/hf_memo.md`](eypt_eyp1901/EYPT/hf_memo.md) — HF mispricing analysis
- [`eypt_eyp1901/EYPT/bd_memo.md`](eypt_eyp1901/EYPT/bd_memo.md) — BD memo (acquisition framing)
- [`eypt_eyp1901/EYPT/valuation.json`](eypt_eyp1901/EYPT/valuation.json) — full machine-readable output
- [`eypt_eyp1901/EYPT/charts/`](eypt_eyp1901/EYPT/charts/) — 5 charts

**Reproduce:**
```bash
bve-asset --config examples/configs/eypt_eyp1901.yaml --all-memos --charts \
          --out case_studies/eypt_eyp1901 --seed 42
```

---

## Case 3: Praxis Precision Medicine (PRAX) / ulixacaltamide

**Type:** Venture Capital — Neurology Platform Investment
**Asset:** ulixacaltamide (PRAX-944) — selective T-type calcium channel blocker
**Indication:** Essential tremor (moderate-severe), US
**Stage:** Phase 3 (ESSENTIAL trial, NCT05173220)

**Key question:** Is Praxis a compelling VC-stage investment and partnership target?

**Valuation summary (base case):**

| Metric | Value |
|--------|-------|
| rNPV | $545M |
| P(Approval) | 44.8% |
| Peak Sales | $739M |
| NAV/Share (incl. $325M cash) | $15.82 |
| Current Price | $22.00 |
| Implied upside to NAV | -28% |
| MC P50 | $399M |
| MC P10 – P90 | $123M to $980M |
| Bull / Base / Bear | $1,663M / $545M / $11M |

**Variant perception:** The market applies generic CNS Phase 3 base rates (~30%)
to a program with unusually strong Phase 2 signal (p<0.001; -22pp treatment difference
on FDA-validated TETRAS endpoint). The market also fails to size the untreated ET
market correctly: 75% of moderate-severe ET patients have never been treated —
the main barrier is tolerability, not efficacy, and ulixacaltamide is the first drug
to solve it mechanistically.

**Kill criterion:** ESSENTIAL primary endpoint miss (TETRAS-ADL superiority not achieved);
OR Phase 2 effect fails to replicate (observed treatment difference < 10pp vs. 22pp in PRISM).

**Key risks:** CNS placebo response is the enemy — TETRAS-ADL is patient-reported
and heterogeneous across ET subtypes; high placebo response in Phase 3 is the primary
execution risk. Payer step-edits requiring failed propranolol/primidone trials will
slow first-line uptake despite superior tolerability.

**Platform optionality:** PRAX-628 (Nav1.2/1.6 inhibitor for focal epilepsy) in Phase 2
is unmodeled here and represents significant additional option value if positive.

**Config:** [`../examples/configs/prax_ulixacaltamide.yaml`](../examples/configs/prax_ulixacaltamide.yaml)

**Outputs:**
- [`prax_ulixacaltamide/PRAX/vc_memo.md`](prax_ulixacaltamide/PRAX/vc_memo.md) — VC investment memo
- [`prax_ulixacaltamide/PRAX/hf_memo.md`](prax_ulixacaltamide/PRAX/hf_memo.md) — HF event-driven
- [`prax_ulixacaltamide/PRAX/valuation.json`](prax_ulixacaltamide/PRAX/valuation.json) — full output
- [`prax_ulixacaltamide/PRAX/charts/`](prax_ulixacaltamide/PRAX/charts/) — 5 charts

**Reproduce:**
```bash
bve-asset --config examples/configs/prax_ulixacaltamide.yaml --all-memos --charts \
          --out case_studies/prax_ulixacaltamide --seed 42
```

---

## Cross-Case Comparison

| | RLAY / RLY-2608 | EYPT / EYP-1901 | PRAX / ulixacaltamide |
|-|-----------------|-----------------|----------------------|
| Memo type | BD acquisition | HF mispricing | VC platform |
| TA | Oncology | Ophthalmology | CNS |
| Stage | Phase 2 | Phase 3 | Phase 3 |
| P(approval) | 34.6% | 71.9% | 44.8% |
| rNPV | $129M | $235M | $545M |
| Peak sales | $539M | $220M | $739M |
| MC P50 | $38M | $132M | $399M |
| Key risk | Phase 3 bar vs. inavolisib | Payer pricing resistance | CNS placebo response |
| Market mispricing | POS gap: +15pp | EV gap: model >> market | Untreated market undersized |

---

## Methodology notes

- All three cases use identical engine, parameters, and random seed (42).
- Each case is a different therapeutic area with area-specific POS priors.
- Decision framing (variant perception, kill criteria, downside drivers) is hand-authored per case.
- Assumption sources are cited in the YAML config and rendered in Appendix A of each memo.
- All outputs are reproducible from the config + seed alone.

**These are analytical exercises, not investment recommendations.**
Verify all inputs against primary sources before any use in actual decision-making.
