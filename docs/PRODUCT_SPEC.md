# Product Specification — Biotech Asset Valuation Engine

**Version:** 2.0
**Date:** 2026-05-26
**Status:** Current — governs all development and output communication

---

## 1. What BVE Is

BVE helps biotech investors and BD/strategy teams evaluate whether a biotech asset is
**undervalued by the market**, **strategically actionable for BD/M&A**, or **worth
monitoring before a clinical or regulatory catalyst**.

It is a structured research and triage engine — not an autonomous investment system.
Every output is annotated with its confidence level and the assumptions that drive it.

---

## 2. Who It Is For

| Audience | Primary question BVE answers | Primary workflow |
|---|---|---|
| **BD / Corporate Strategy** | Is this target actionable? Which buyers fit? | `bve-evaluate-target` |
| **Biotech Investors** | Is this asset undervalued? What does the market imply? | `bve-morning-screen` |
| **Analysts / Researchers** | How credible are the model outputs? What is validated? | `bve-validate` |

---

## 3. The Three Canonical Workflows

### Workflow 1 — Evaluate Target

```bash
bve-evaluate-target --ticker SRPT
```

**Output:** A single Markdown decision report composing:
- Valuation (rNPV, NAV/share, implied upside vs. market)
- M&A probability score and best-fit acquirer
- Management quality assessment and auto-generated diligence questions
- Input integrity and staleness flags
- Prediction log history for the ticker
- Model validation summary

**Use when:** You have a specific company in mind and need a structured, all-surfaces
view before a meeting, diligence call, or investment committee.

**Trust level:** Model-dependent. Accuracy depends on the quality of the underlying
valuation config and how recently it was updated. Check the staleness section.

---

### Workflow 2 — Morning Screen

```bash
bve-morning-screen
bve-morning-screen --top 15 --output outputs/screen_2026-05-26.md
```

**Output:** A ranked daily screen with six sections:
1. Top M&A / BD Action Candidates (ranked by M&A probability score)
2. Top Valuation Dislocations (sorted by absolute implied upside)
3. Catalyst / Watchlist Items (upcoming catalysts from tracked universe)
4. ClinicalTrials.gov Changes (trial status diffs)
5. Stale / Low-Integrity Inputs (tickers with staleness warnings)
6. Unresolved Prediction Log Items (open predictions awaiting resolution)

**Use when:** Starting the day and need to know what in the tracked universe deserves
attention. The screen degrades gracefully — any section with no data says so clearly.

**Trust level:** Directional. Rankings are relative within the currently tracked
universe. Assets not in `outputs/intelligence/ops.db` are invisible.

---

### Workflow 3 — Validate Model

```bash
bve-validate
bve-validate --output outputs/validation_report.md
```

**Output:** A validation and credibility report covering:
- POS model backtest grade (Brier score, AUC, calibration buckets)
- Known-answer suite results (historical cases with verifiable outcomes)
- Model governance summary
- Overall letter grade (A / B / C / D)

**Use when:** Before presenting outputs to a new audience, after a material model
change, or as a regular credibility check before acting on any screen output.

**Trust level:** Validated. This is the highest-confidence surface in BVE. A grade
below B is a signal to re-examine upstream calibration before using other outputs.

---

## 4. What to Trust — Output Confidence Table

For the full score-by-score breakdown, see [`docs/output_trust_guide.md`](output_trust_guide.md).

| Output | Confidence | Short answer |
|---|---|---|
| rNPV / NAV/share | Model-dependent | Right math; inspect the inputs and tornado first |
| P(approval) | Directional | Use for ranking, not absolute probability |
| M&A probability score | Directional | Screen signal; not a deal forecast |
| Model validation grade | Validated | Most reliable output in the system |
| POS backtest (Brier/AUC) | Validated | N=99 oncology; ~15% skill vs. baseline |
| Backtest alpha (replay) | Not yet actionable | Directionally positive; statistically underpowered |
| Management quality | Analyst-judgment | Structured diligence template, not an empirical score |

---

## 5. What Not to Over-Trust

1. **Screening-grade configs** — peak sales assumptions can be off by 5–10x when
   built from industry defaults. Check `_meta.screening_grade` before any capital use.
2. **M&A probability as a percentage** — it is a rank signal, not a calibrated forecast.
   Never cite it as "X% probability of acquisition" in an external document.
3. **Stale outputs** — the morning screen pulls from stored files. If the last run was
   >90 days ago, the ranking is degraded.
4. **Management quality composite number** — the components are structured expert inputs,
   not statistically calibrated. Use the diligence questions, not the composite.
5. **Backtest alpha claims** — current N ≈ 60–130 decisions is below the ~111 threshold
   for p < 0.10. Do not cite as demonstrated forward alpha.

---

## 6. Scaffolding a New Asset

```bash
bve-init-asset --ticker SRPT
```

Creates seven annotated template files under `configs/SRPT/` and `outputs/SRPT/`.
Fill in the templates and run `bve-asset --config configs/SRPT/asset_profile.yaml`
to generate the valuation output that powers `bve-evaluate-target`.

---

---

## Mode Governance (unchanged from v1.0)

## Purpose

This section defines the three operating modes of the Biotech Asset Valuation Engine, the
rules that govern each mode, and the explicit prohibitions that prevent the system from
exceeding its current level of validation.

The system is not a fund. It is a structured research and triage tool being evolved, in
disciplined phases, toward institutional underwriting quality. Treating it as anything more
than what it currently is — at any given phase — is the primary failure mode to prevent.

---

## The Three Modes

### Mode 1 — Screening

**Definition:** A broad-coverage, heuristic-grade scan of the universe. Screening-grade
valuations are produced from parametric configs built from industry defaults with limited
manual curation. They are good enough to rank relative mispricing; they are not good enough
to justify capital deployment.

**What is allowed:**
- Implied PoS spread computation
- Relative ranking across the universe
- Acquisition discount signal
- Catalyst-proximity scoring
- Generating the review queue (flagging names for deeper work)
- Including in daily/weekly brief as ranked candidates

**What is NOT allowed:**
- "add", "buy", "size", "starter", "medium", "full" action labels
- Inclusion in the shadow book or paper portfolio
- Use as primary justification for a capital decision
- Claiming the valuation is "institutional quality"

**Identification:** configs with `_meta.screening_grade: true`. All replay-generated configs
are screening-grade by default.

**Mode label in outputs:** `[MODE: SCREENING]`

---

### Mode 2 — Capital Candidate

**Definition:** A small set of names (target: ≤ 25) that have been through a full underwriting
pack — dated, corroborated assumptions; a company-level snapshot; a dilution bridge; platform
and unmodeled pipeline bridges. These names can receive sizing recommendations, but only after
a human review step that explicitly approves the pack.

**What is allowed (in addition to Screening):**
- Sizing recommendation labels (watch / starter / medium / full / trim / exit)
- Inclusion in the shadow book
- Generating a formal review memo
- Use in portfolio construction

**What requires human sign-off before becoming active:**
- Initial "approved for capital candidate" classification
- Any sizing change above starter
- Any material assumption change after pack approval

**What is NOT allowed:**
- Automated capital deployment (Phase 8+)
- Removing "needs review" gate on first-time additions
- Using screening-grade assumptions even if the name is on the top-25 list

**Identification:** `company_snapshot.reviewer_state == "approved"` AND
`company_snapshot.pack_version >= 1`.

**Mode label in outputs:** `[MODE: CAPITAL-CANDIDATE]`

---

### Mode 3 — Shadow Book

**Definition:** The paper portfolio that tracks capital-candidate names with paper positions,
transaction-cost assumptions, and a weekly decision cycle. The shadow book is the validation
mechanism for the sizing engine. It runs for 6–12 months before any real capital is deployed.

**What is allowed (in addition to Capital Candidate):**
- Paper position entries and exits
- P&L tracking (paper)
- Pre-mortem and post-mortem logging
- Attribution to error taxonomy categories

**What is NOT allowed:**
- Real capital deployment until Gate 4 (shadow book operating credibility) is passed
- Bypassing the review memo for new shadow book entries
- Adding screening-grade names directly to the shadow book

**Identification:** a name enters the shadow book only via an explicit `ShadowBookEntry` record
created through the review workflow.

**Mode label in outputs:** `[MODE: SHADOW-BOOK]`

---

## Governance Table

| Action | Screening | Capital-Candidate | Shadow-Book |
|--------|-----------|-------------------|-------------|
| Universe ranking / spread signal | Yes | Yes | Yes |
| Daily/weekly brief inclusion | Yes | Yes | Yes |
| "add" action label | **No** | Yes (after review) | Yes |
| Sizing labels (starter/medium/full) | **No** | Yes (after review) | Yes |
| Shadow book entry | **No** | **No (needs review)** | Yes |
| Paper position tracking | **No** | **No** | Yes |
| Real capital action | **No** | **No** | **No (Phase 8+ gate)** |

---

## Screening-Grade Prohibition

Any code path that produces an "add", "buy", "size", "starter", "medium", or "full" label for
a screening-grade config MUST raise an error or be blocked before output is written. This is a
hard gate, not a soft warning.

**Rationale:** screening-grade valuations routinely have 40–80% error on peak sales assumptions
because they are built from industry defaults, not researched company facts. A system that
automatically generates "buy AMRN" from a $4B TAM assumption that is 100x wrong (the actual
case before the April 2026 AMRN config fix) destroys trust and harms decision quality.

**Implementation note:** the gate is implemented in `src/bve/intelligence/actionable_output.py`
via `ScreeningGradeActionError`. Any name with `screening_grade=True` in its company metadata
is blocked from action labels that imply capital deployment.

---

## What We Are Not

At the time this spec is written (April 2026):

- Not a hedge fund
- Not a system with validated, calibrated, forward-tested position sizing
- Not a replacement for a human analyst's company-level underwriting judgment
- Not producing durable alpha beyond organized public information

**What we are:**
- A structured triage engine that ranks mispricing signals across 27–50 universe names
- A platform being built toward institutional underwriting quality, one phase at a time
- A disciplined record of assumptions, predictions, and outcomes that will compound in value
  as the calibration database grows

**Realistic target:** Beat naive public-consensus workflows. Excel in small/mid-cap, catalyst-heavy,
underfollowed zones. Produce enough disciplined edge that the system earns the right to expand.

---

## Phase progression required before upgrading a name's mode

```
Screening → Capital-Candidate requires:
  1. Full company pack (Phase 1 deliverable)
  2. Two-source corroboration on all material buckets (Phase 2 deliverable)
  3. Human reviewer sign-off with explicit rationale
  4. No active quarantine flags

Capital-Candidate → Shadow-Book requires:
  1. EV-to-size engine live (Phase 4 deliverable)
  2. Portfolio rules functioning (Phase 4 deliverable)
  3. Explicit review memo approved
  4. No stale-data flags on material assumptions

Shadow-Book → Real Capital requires:
  1. Gate 4 passed: 6–12 months shadow operation
  2. Gate 3 passed: action credibility validation complete
  3. Gate 2 passed: validation credibility confirmed
  4. Explicit decision to move, with documented rationale
```

---

## Review and update schedule

This spec should be reviewed and updated at the completion of each phase. The mode definitions
and governance table are the stable anchor; the implementation notes will evolve. If a phase
completion changes what is allowed in a mode, update this document before shipping the code.
