# M&A Module Institutional Gap Roadmap

**Objective:** Turn the current M&A/acquirer module from a useful research-grade screen into a more institutionally credible BD decision-support system.

## Executive Summary

The M&A module is no longer a placeholder. The repo has acquisition screening, readiness gating, comparable deals, acquirer profiles, acquirer-target fit, M&A probability snapshots, BD decomposition layers, routing, calibration scaffolding, and replay infrastructure. The institutional gap is not that the system lacks M&A logic. The gap is that the most important BD facts are still sparse, manually curated, or not validated at pair level.

The roadmap therefore prioritizes data structure and validation before more scoring complexity.

| Roadmap bucket | Current issue | Institutional objective |
|---|---|---|
| Rights/control | Too shallow for real deal feasibility | Know whether an asset can actually be acquired, licensed, or optioned. |
| Acquirer profiles | Useful but stale risk exists | Make every buyer assumption source-dated and BD-reviewable. |
| Calibration | Sparse takeout/control labels | Convert ranking heuristics into defensible probability bands. |
| IP/LOE | Generic unless configured | Tie buyer urgency and target value to exact exclusivity windows. |
| Seller willingness | Approximated from public signals | Separate "strategically attractive" from "transaction-ready." |
| Deal structure | Routing exists, not validated | Predict acquisition vs license vs option vs partnership with reasons. |

## Current M&A Module Map

| Current component | Main files | Roadmap implication |
|---|---|---|
| Acquisition discount | `src/bve/intelligence/acquisition_screen.py` | Keep; add rights/IP caveats to avoid false positives. |
| Acquisition readiness | `src/bve/intelligence/acquisition_readiness.py` | Keep; strengthen with clinical-evidence and catalyst freshness. |
| Comparable deals | `src/bve/intelligence/comparable_deals.py`, `research/mna/comparable_deals.yaml` | Expand quality grades and deal-structure tags. |
| Acquirer profiles | `src/bve/intelligence/acquirer_profiles.py`, `examples/research/acquirer_profiles/*.yaml` | Add freshness, BD review, LOE urgency, CMC capability, and strategy confidence. |
| Acquirer fit | `src/bve/intelligence/acquirer_fit.py` | Add rights, antitrust, exact infrastructure fit, and buyer-specific valuation. |
| M&A probability | `src/bve/intelligence/ma_probability.py` | Keep directional; attach calibration confidence everywhere. |
| Layer 3 gates | `src/bve/intelligence/ma_layer3_gate.py` | Feed with structured rights/control/seller data. |
| Layer 4 routing | `src/bve/intelligence/ma_layer4_routing.py` | Calibrate deal-structure likelihood by history. |
| Layer 5 calibration | `src/bve/intelligence/ma_layer5_calibration.py` | Expand labeled dataset before increasing model complexity. |

## Priority 1: Add Structured Rights, Royalty, and Control Model

| Field | Detail |
|---|---|
| Problem | The current model only partially captures royalties and existing partnerships; it does not deeply model ROFR/ROFN, regional rights, change-of-control provisions, consent rights, or asset encumbrances. |
| Why it matters | These terms can block an acquisition or force a license/option structure even when strategic fit is high. |
| Current repo status | `DealEconomics` supports royalties/profit share economically; acquirer profiles support existing partnerships; Layer 3 has asset-control gates. Target-specific rights schema is missing. |
| Data needed | SEC collaboration agreements, licensing docs, company disclosures, BD expert review. |
| Suggested implementation | Add `AssetControlProfile` with royalty burden, regional rights, ROFR/ROFN, option rights, CoC clauses, consent rights, encumbrance score, and evidence refs. |
| Files/modules likely affected | `src/bve/entities/`, `src/bve/intelligence/acquisition_screen.py`, `acquirer_fit.py`, `ma_probability.py`, `ma_layer3_gate.py`, YAML configs. |
| Acceptance criteria | M&A row shows control-risk status and recommended structure changes when rights are encumbered. |
| Priority | Must fix now |

## Priority 2: Acquirer Profile Freshness and BD Review Workflow

| Field | Detail |
|---|---|
| Problem | Profiles are curated YAMLs and can become stale. |
| Why it matters | Acquirer strategy changes after earnings, pipeline failures, new approvals, and recent deals. |
| Current repo status | Profiles include `profile_as_of` and source refs, but stale-profile warnings are not central to every output. |
| Data needed | Earnings calls, R&D days, investor decks, deal announcements, BD expert comments. |
| Suggested implementation | Add profile freshness score, required review cadence, and `bd_reviewed_by/date/notes` fields. Warn when profile is older than 180 days. |
| Files/modules likely affected | `acquirer_profiles.py`, `acquirer_profile_validation.py`, `acquirer_fit.py`, CLI renderers. |
| Acceptance criteria | Every acquirer-fit report surfaces profile age and stale-profile warning. |
| Priority | Must fix now |

## Priority 3: Pair-Level M&A Calibration Dataset

| Field | Detail |
|---|---|
| Problem | Current M&A probability is not backed by a sufficiently large labeled acquirer-target-date panel. |
| Why it matters | Probability outputs are not institutionally credible without calibration. |
| Current repo status | `ma_calibration.py` builds datasets from snapshots and takeout events; sparse labels limit conclusions. |
| Data needed | Public takeouts, control universe, acquirer labels, announcement dates, historical snapshots. |
| Suggested implementation | Backfill monthly/quarterly acquirer-target snapshots from 2020-2026 and evaluate target hit rate plus acquirer top-k accuracy. |
| Files/modules likely affected | `ma_calibration.py`, `historical_replay.py`, `ma_probability_backfiller.py`, `research/mna/deal_universe_2020_2026.yaml`. |
| Acceptance criteria | Report precision@k, recall, AUC/Brier, top-1/top-3 acquirer accuracy, and confidence intervals. |
| Priority | Must fix now |

## Priority 4: IP / Exclusivity / LOE Urgency Module

| Field | Detail |
|---|---|
| Problem | LOE and patent life are modeled generically unless configured; buyer urgency requires exact franchise cliffs and target exclusivity. |
| Why it matters | Pharma BD often reacts to product cliffs and exclusivity windows. |
| Current repo status | LOE erosion profiles implemented; exact IP dates and acquirer cliff pressure are partial/config-driven. |
| Data needed | Orange Book, patent databases, exclusivity, litigation, product revenue by franchise. |
| Suggested implementation | Add `ExclusivityProfile` and `AcquirerLOEPressure` fields; score urgency by revenue at risk and timing. |
| Files/modules likely affected | `market_model.py`, `revenue_model.py`, `acquirer_profiles.py`, `ma_scoring.py`, configs. |
| Acceptance criteria | Acquirer fit can explain "urgent because buyer has $XM revenue cliff in YYYY." |
| Priority | High-value next |

## Priority 5: Seller Willingness Model

| Field | Detail |
|---|---|
| Problem | Current seller willingness is approximated through financing pressure, target signals, catalysts, and vulnerability. |
| Why it matters | A target can be perfect strategically but unavailable. |
| Current repo status | `vulnerability_signals.py`, `capital_structure.py`, `ma_scoring.py` support signals; direct seller-willingness model is incomplete. |
| Data needed | Cash runway, financing history, activist ownership, strategic-review announcements, board changes, banker/process signals. |
| Suggested implementation | Create explicit `SellerWillingnessAssessment` with evidence refs and confidence. |
| Files/modules likely affected | `vulnerability_signals.py`, `ma_scoring.py`, `ma_layer3_gate.py`, `ma_probability.py`. |
| Acceptance criteria | Scores distinguish "strategic watch" from "actionable process-ready" using seller evidence. |
| Priority | High-value next |

## Priority 6: Deal Structure Prediction

| Field | Detail |
|---|---|
| Problem | Layer 4 routes deal structure, but structure likelihood is not calibrated or deeply rights-aware. |
| Why it matters | BD output should say acquisition vs option vs license vs partnership, not just target probability. |
| Current repo status | `ma_layer4_routing.py` has deal-structure enums and routing rules. |
| Data needed | Historical deal structures by stage, modality, rights state, buyer, and target status. |
| Suggested implementation | Add structure probabilities and tie them to rights/control, stage, budget, and buyer behavior. |
| Files/modules likely affected | `ma_layer4_routing.py`, `ma_layer5_calibration.py`, `comparable_deals.py`. |
| Acceptance criteria | Report shows primary and alternate structures with reason codes. |
| Priority | High-value next |

## Priority 7: Antitrust / Commercial Overlap Risk

| Field | Detail |
|---|---|
| Problem | Antitrust is a placeholder/gate field but not materially computed. |
| Why it matters | High strategic overlap can increase regulatory risk and reduce feasibility. |
| Current repo status | Layer 3 and Layer 4 include antitrust flags; data/scoring is missing. |
| Data needed | Product market definitions, market share, overlapping assets, FTC/EC precedent. |
| Suggested implementation | Add overlap-based antitrust risk and force score caps for high-risk buyer-target pairs. |
| Files/modules likely affected | `ma_layer3_gate.py`, `acquirer_fit.py`, new commercial overlap data. |
| Acceptance criteria | Same-TA overlap can lower feasibility even when strategic fit is high. |
| Priority | Medium |

## Priority 8: Manufacturing / CMC Buyer Capability

| Field | Detail |
|---|---|
| Problem | CMC costs exist, but acquirer-specific manufacturing capability is shallow. |
| Why it matters | Complex modalities require specific owners; CMC risk affects structure and price. |
| Current repo status | `CMCCosts` implemented; modality fit exists in profiles. |
| Data needed | Manufacturing footprint, modality experience, tech-transfer complexity, capacity constraints. |
| Suggested implementation | Add `manufacturing_capability` to acquirer profiles and `manufacturing_complexity` to assets. |
| Files/modules likely affected | `acquirer_profiles.py`, `acquirer_fit.py`, asset configs. |
| Acceptance criteria | Fit score differentiates buyer capability for AAV, RNA, cell therapy, ADC, biologics, small molecules. |
| Priority | Medium |

## Priority 9: Expand Deal Universe and Comparable Quality

| Field | Detail |
|---|---|
| Problem | Comparable deal set exists but needs broader, source-graded, structure-aware coverage. |
| Why it matters | Valuation and calibration depend on deal sample quality. |
| Current repo status | `research/mna/comparable_deals.yaml` and loaders implemented. |
| Data needed | More public and paid deal data, terms, stage, asset rights, royalty terms, acquirer identity. |
| Suggested implementation | Add quality grades, disclosure confidence, structure tags, and acquirer-specific deal sets. |
| Files/modules likely affected | `comparable_deals.py`, `deal_models.py`, `research/mna/comparable_deals.yaml`. |
| Acceptance criteria | Reports separate high-quality comps from rough/biobucks/platform comps. |
| Priority | Medium |

## Priority 10: Output Governance and Probability Language

| Field | Detail |
|---|---|
| Problem | Scores can be misread as precise probabilities. |
| Why it matters | Institutional users need confidence bands and model-grade caveats. |
| Current repo status | Validation and model-grade modules exist; M&A reports should surface them more forcefully. |
| Data needed | Replay/significance metrics, calibration confidence. |
| Suggested implementation | Add `model_grade`, `validation_status`, and probability band to every M&A output. |
| Files/modules likely affected | `ma_probability.py`, `cli/ma_probability.py`, `validation/model_grade.py`. |
| Acceptance criteria | Any unvalidated M&A probability prints "directional only" and confidence range. |
| Priority | Must fix now |

## Recommended Implementation Sequence

| Sequence | Workstream | Why this order |
|---|---|---|
| 1 | Output governance and probability language | Prevents users from over-reading current uncalibrated scores. |
| 2 | Rights, royalty, and control schema | Removes the biggest false-positive risk in acquirer rankings. |
| 3 | Acquirer profile freshness and BD review workflow | Makes strategic-fit inputs auditable and current. |
| 4 | Pair-level calibration dataset | Gives the probability model a real empirical base. |
| 5 | IP/exclusivity and LOE urgency | Improves both valuation and buyer urgency. |
| 6 | Seller willingness | Separates strategic watchlist names from actionable transaction candidates. |
| 7 | Deal structure prediction | Makes output more useful to BD than binary takeout probability. |
| 8 | Antitrust and CMC capability | Adds buyer-specific feasibility realism. |
| 9 | Comparable deal quality expansion | Improves valuation and calibration once data structures are stable. |

## What "Institutionally Credible" Means Here

| Requirement | Acceptance standard |
|---|---|
| Every score has sources | Profile, target, deal, and rights assumptions include source references and dates. |
| Every probability has a grade | Outputs state whether they are calibrated, directional, or insufficient-data. |
| Every high-ranked target has deal feasibility checks | Rights/control, IP, seller willingness, antitrust, and structure are visible. |
| Every acquirer rank is explainable | The report shows why the buyer fits, what could block it, and what data is missing. |
| Backtests separate ranking from probability | Precision@k and calibration metrics are not conflated. |
| BD can correct the model | Expert feedback becomes structured config, not free-text notes only. |

## Lower-Priority Work to Avoid Until Data Improves

- Adding more score versions without more labeled deal history.
- Reporting probabilities with unnecessary decimal precision.
- Training complex models before source coverage and labels are credible.
- Optimizing dashboards before rights/control/profile freshness are solved.
- Treating public investor-deck language as equal to BD-confirmed strategy.
