# Intelligence-to-Valuation Mapping Specification

**Version:** Phase 0
**Status:** Canonical reference — generated from `bve.intelligence.mapping.EVENT_PARAMETER_MAP`
**Frozen engine version:** v1.0 (`core-engine-v1` branch)

---

## Purpose

This document specifies how each detected intelligence event type maps to
valuation assumption parameters in the frozen rNPV engine, and how changes
to those parameters are authorized.

The rules are stored in:
- `src/bve/intelligence/config/mapping_rules.yaml` (editable source of truth)
- loaded and validated into `MappingRule` objects by `src/bve/intelligence/mapping.py`

This document is the human-readable reference. If this document and YAML/code
conflict, **the YAML+code govern**; update this document to match.

---

## Change Modes

| Mode | Description | Human required? |
|------|-------------|-----------------|
| **AUTO** | System applies a bounded, rule-based delta automatically. | No |
| **BOUNDED** | System proposes a specific delta; human reviewer must confirm before application. | Yes (confirm or override) |
| **MANUAL** | System flags the event as potentially material but proposes no numeric delta. Analyst determines any change and enters it directly. | Yes (full determination) |

**Bound semantics:** For AUTO and BOUNDED rules, `bound_pct` is the maximum
allowable `|proposed_delta_pct|`, where
`proposed_delta_pct = (proposed − current) / |current| × 100`.
A proposal exceeding the bound is rejected at construction.

---

## Parameter Namespace

The following parameter paths are legal targets for `AssumptionChangeProposal`.
The `[*]` wildcard is resolved to a specific trial phase at apply-time.

```
trials[*].success_probability
trials[*].cost_millions
trials[*].duration_years
market_model.addressable_patients_annual
market_model.total_addressable_market_millions
market_model.net_price_per_patient_usd
market_model.peak_penetration
market_model.patent_life_years
market_model.lifecycle_events          ← non-scalar; always MANUAL
market_model.competition_model         ← non-scalar; always MANUAL
asset.discount_rate
```

---

## Event Type Mapping Table

### Clinical Events

#### `trial_readout` — Primary endpoint results from a Phase 1/2/3 trial

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `trials[*].success_probability` | **AUTO** | ±20% | Either | Positive Ph3 topline → step-up POS; negative → step-down. Direction from `StructuredSignal.primary_endpoint_met`. |
| `trials[*].duration_years` | **AUTO** | ±15% | Decrease | Completed readout collapses remaining duration estimate for that phase. |
| `market_model.peak_penetration` | **BOUNDED** | ±15% | Either | Strong efficacy (HR < 0.65 or ORR > 40%) supports higher penetration; weak data reduces it. |

#### `interim_analysis` — DSMB/IDMC interim cut

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `trials[*].success_probability` | **BOUNDED** | ±10% | Either | Interim data is partial; modest POS adjustment, human confirmation required. |
| `trials[*].cost_millions` | **BOUNDED** | ±10% | Either | Adaptive sample-size re-estimation changes trial cost. |

#### `enrollment_update` — Trial enrollment rate above/on/below plan

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `trials[*].duration_years` | **AUTO** | ±20% | Either | Enrollment rate delta translates linearly to duration change. |
| `trials[*].cost_millions` | **AUTO** | ±15% | Either | Duration change × quarterly burn rate = cost delta. |

#### `endpoint_change` — Protocol amendment modifying primary endpoint

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `trials[*].success_probability` | **MANUAL** | — | Either | Endpoint changes fundamentally alter the regulatory bar. Analyst must assess new endpoint precedent and FDA history. |
| `market_model.addressable_patients_annual` | **MANUAL** | — | Either | Eligibility criterion changes alter the addressable population. |

#### `safety_signal` — AE, SUSAR, DILI, or black-box warning

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `trials[*].success_probability` | **BOUNDED** | −25% | Decrease | Grade 3+ safety signals increase CRL probability. Propose 10–25pp reduction. |
| `asset.discount_rate` | **BOUNDED** | +15% | Increase | Elevated development risk warrants higher WACC (+1–2pp). |
| `market_model.net_price_per_patient_usd` | **MANUAL** | — | Decrease | Black-box warnings depress net price; magnitude requires analyst judgment. |

#### `conference_presentation` — Data at ASCO, ASH, ADA, etc.

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `trials[*].success_probability` | **BOUNDED** | ±10% | Either | Conference data is frequently preliminary; cap adjustment at 10% relative. |
| `market_model.peak_penetration` | **BOUNDED** | ±10% | Either | KOL enthusiasm or skepticism signals future commercial uptake. |

#### `publication` — Peer-reviewed journal publication

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `trials[*].success_probability` | **BOUNDED** | ±10% | Either | Published final data; modest POS update relative to original readout. |
| `market_model.net_price_per_patient_usd` | **MANUAL** | — | Either | Published cost-effectiveness analyses inform payer negotiations. |

---

### Regulatory Events

#### `fda_approval` — NDA/BLA approved (full or accelerated)

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `trials[*].success_probability` | **AUTO** | 100% | Increase | Set approval-phase `success_probability` to 1.0. |
| `market_model.addressable_patients_annual` | **BOUNDED** | ±20% | Either | Approved label may differ from modeled; validate against actual label language. |
| `market_model.patent_life_years` | **MANUAL** | — | Either | Analyst confirms actual patent expiry vs. modeled LOE date. |

#### `fda_rejection` — Complete Response Letter (CRL)

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `trials[*].success_probability` | **AUTO** | 100% | Decrease | CRL terminates this regulatory cycle; set to 0.0. |
| `market_model.net_price_per_patient_usd` | **MANUAL** | — | Decrease | Re-submission delay may compress eventual launch price due to competitive entrenchment. |

#### `fda_designation` — BTD, RMAT, ODD, Fast Track, Priority Review

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `trials[*].success_probability` | **BOUNDED** | +15% | Increase | FDA alignment signal; +5–15pp POS by designation type (BTD > ODD > FTD). |
| `trials[*].duration_years` | **BOUNDED** | −20% | Decrease | BTD enables rolling review; Priority Review halves PDUFA clock. |

#### `regulatory_hold` — Full or partial clinical hold

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `trials[*].success_probability` | **BOUNDED** | −25% | Decrease | Clinical hold raises failure probability; magnitude varies with hold type (safety vs. CMC). |
| `trials[*].duration_years` | **BOUNDED** | +50% | Increase | Hold duration highly uncertain; model extends phase 6–24 months. Wide bound reflects real-world range. |
| `asset.discount_rate` | **BOUNDED** | +20% | Increase | Regulatory risk premium; propose +2pp WACC. |

#### `label_expansion` — Supplemental NDA/BLA for new indication

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `market_model.addressable_patients_annual` | **BOUNDED** | +40% | Increase | New indication adds patient pool; human confirms scale. |
| `market_model.total_addressable_market_millions` | **BOUNDED** | +40% | Increase | TAM-mode alternative when patient-based model not available. |
| `market_model.lifecycle_events` | **MANUAL** | — | Increase | Analyst adds `LifecycleEvent(event_type='label_expansion', ...)` to YAML. |

#### `payer_coverage` — CMS NCD, formulary, ICER, step-therapy decision

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `market_model.net_price_per_patient_usd` | **BOUNDED** | ±20% | Either | Coverage breadth directly affects rebate levels and realized net price. |
| `market_model.peak_penetration` | **BOUNDED** | ±20% | Either | Access restrictions cap the penetration ceiling. |

---

### Business Events

#### `partnership` — License, collaboration, co-development, or acquisition

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `asset.discount_rate` | **BOUNDED** | −15% | Decrease | Large-pharma partnership validates program; propose −1pp WACC. |
| `trials[*].cost_millions` | **BOUNDED** | −50% | Decrease | Partner co-funding reduces company cost share; wide bound reflects deal structure range. |
| `market_model.competition_model` | **MANUAL** | — | Either | Co-promotion changes competitive posture (non-scalar; update YAML). |

#### `financing` — Equity offering, convertible, or debt raise

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `asset.discount_rate` | **BOUNDED** | ±10% | Either | Successful financing at low dilution reduces WACC; distressed raise increases it. |

#### `sec_filing` — 10-K, 10-Q, 8-K with material pipeline disclosure

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `trials[*].cost_millions` | **MANUAL** | — | Either | Updated R&D spend guidance in filing; analyst reconciles with model estimates. |
| `trials[*].duration_years` | **MANUAL** | — | Either | Timeline updates in filings may conflict with ClinicalTrials.gov data; analyst resolves. |
| `market_model.addressable_patients_annual` | **MANUAL** | — | Either | Management market-size guidance in investor presentations embedded in 8-K. |

#### `management_change` — CEO, CMO, or CSO hire or departure

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `asset.discount_rate` | **MANUAL** | — | Either | Leadership transition shifts risk profile; direction requires analyst judgment. |
| `market_model.competition_model` | **MANUAL** | — | Either | New BD/commercial leadership may reorient competitive strategy (non-scalar). |

---

### Competitive Events

#### `competitor_event` — Competitor trial readout, approval, or setback

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `market_model.peak_penetration` | **BOUNDED** | −30% | Decrease | Competitor approval in same indication compresses peak market share ceiling. |
| `market_model.competition_model` | **MANUAL** | — | Either | Analyst updates competitor entries (launch year, peak share, approval probability). |
| `market_model.net_price_per_patient_usd` | **BOUNDED** | −15% | Decrease | Similar-profile competitor creates pricing pressure; specialist markets compress faster. |

#### `patent_event` — IPR, litigation, patent grant, LOE extension

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `market_model.patent_life_years` | **MANUAL** | — | Either | IPR decisions or new continuations change effective patent life; analyst recalculates LOE date. |
| `market_model.lifecycle_events` | **MANUAL** | — | Either | Settlement terms granting new-formulation exclusivity → analyst adds/removes `LifecycleEvent` entries. |

---

### Program Lifecycle

#### `program_discontinuation` — Asset dropped from pipeline

| Parameter | Mode | Bound | Direction | Rationale |
|-----------|------|-------|-----------|-----------|
| `trials[*].success_probability` | **AUTO** | 100% | Decrease | Program terminated; set all downstream phase POS to 0.0. Binary — no confirmation required. |
| `market_model.addressable_patients_annual` | **AUTO** | 100% | Decrease | Zero out this asset's addressable contribution in any multi-indication model. |

---

## Invariants (enforced in code and tests)

1. Every `EventType` has at least one `MappingRule`.
2. AUTO rules always have `bound_pct` set (not None).
3. MANUAL rules always have `bound_pct=None`.
4. BOUNDED rules have `bound_pct` between 5 and 50 (sanity range, inclusive).
5. All `MappingRule.parameter` values are members of `LEGAL_PARAMETER_PATHS`.
6. `AssumptionChangeProposal` construction rejects AUTO/BOUNDED proposals
   whose `|proposed_delta_pct|` exceeds `bound_pct`.

---

## Open Issues

1. **Non-scalar proposals (Phase 1).**  `market_model.lifecycle_events` and
   `market_model.competition_model` are structured objects, not scalars.
   Phase 0 marks all rules targeting them as MANUAL and stores only a flag.
   Phase 1 should introduce a `StructuredObjectChangeProposal` variant that
   carries a typed diff (e.g. `lifecycle_event_to_add: LifecycleEvent`).

2. **Trial phase discriminator (Phase 1).**  `trials[*].success_probability`
   uses a wildcard `[*]`.  Phase 1 must resolve this to a specific
   `TrialPhase` at apply-time by matching the proposal's phase discriminator
   against the engine asset's trial list.

3. **Multi-asset events.**  `competitor_event` and `patent_event` may affect
   multiple assets simultaneously (e.g. a BTK class ruling).  Phase 0 requires
   one `Event` + one `StructuredSignal` per affected asset.  Phase 1 should
   support broadcast events that fan out to a set of asset IDs.

4. **Confidence-weighted AUTO bounds.**  Today, AUTO bounds are fixed
   percentages.  A more sophisticated model would scale `bound_pct` by
   `StructuredSignal.extraction_confidence` and trial N so that noisier
   signals produce smaller automatic adjustments.

5. **Competing signals.**  When two signals contradict (positive interim
   followed by negative final readout), Phase 0 creates two proposals with
   opposing signs.  Phase 1 needs a signal reconciliation layer that identifies
   and resolves conflicts before proposal generation.
