# Product Specification — Biotech Asset Valuation Engine

**Version:** 1.0
**Date:** 2026-04-09
**Status:** Phase 0 baseline — governs all subsequent development

---

## Purpose

This document defines the three operating modes of the Biotech Asset Valuation Engine, the
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
