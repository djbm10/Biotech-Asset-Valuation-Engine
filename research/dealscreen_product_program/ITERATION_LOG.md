# Iteration log

Each cycle: problem, success criteria (written before code), baseline, change, measured result,
adversarial review, and what was not achieved.

## Cycle 1: analyst fact entry with citation (started 2026-10-28)

**Problem.** On the real FcRn / gMG landscape, 38 of 39 open gate questions on unresolved
programs have no in-tool path; the analyst must edit the source file and re-import (audit
finding 1). It is a missing capability, not a source-data defect: the facts exist in public
sources, but DealScreen has nowhere to put an analyst's cited judgement.

**Baseline.**
- 1 of 39 open gates closable in-tool;
- screen 4 ELIGIBLE / 14 UNRESOLVED / 22 EXCLUDED;
- 0 wrong inclusions or exclusions against the pre-committed reference.

**Success criteria (frozen before implementation):**

| | Criterion |
|---|---|
| C1 | `ASSERT_FACT` records one field value for one asset. It is refused, writing nothing, unless it has: a reviewer, a rationale, a supported field, a non-empty value, a source URL and a quoted evidence span |
| C2 | The value must be readable by that field's existing normalizer (target symbol, modality term, phase label, mechanism direction). An unreadable assertion is refused with a message saying what the field accepts. An assertion that cannot change a decision is not stored as if it did |
| C3 | AI_PREPARED records cannot assert facts |
| C4 | Assertions act only through the existing FactBuilder / GateEngine path, as analyst-confirmed claims. The decision cites the assertion's decision id. Imported claims and `import.json` stay byte-identical |
| C5 | Where an assertion overrides a readable, different source value, the screen lists the override (field, asserted value, superseded claim ids). Nothing is silently replaced |
| C6 | `RETRACT_FACT` withdraws an assertion. Re-screening then gives a `screening.json` byte-identical to the screen before the assertion |
| C7 | The workbook and memo show assertions with their citation, asserter and reviewer kind |
| C8 | Real landscape: in-tool paths go from 1/39 open gates to 39/39 by capability. A labelled simulated-analyst pass is then run, using only public citations, and reported as INTERNAL DEVELOPMENT (not a human): actions taken, programs resolved, any new wrong decisions |
| C9 | No regression: synthetic 200 demo, real pinned baseline (before assertions), DealScreen / valuation / S&E suites |

**Adversarial review (AI reviewer in a separate context; not independent human validation).**
Findings, all fixed before acceptance:
- **High:** an assertion on a multi-valued field (indication) silently overturned a therapeutic-area FAIL. Fixed: every screen now compares asserted assets with and without their assertions and lists every gate and disposition change, flagging any overturned source FAIL in the workbook and memo.
- **High:** unvalidated indication and area assertions could be stored without effect. Fixed: they must be NCIt / classified-area names, and an assertion that changes no gate is shown as "no effect".
- **High:** weak rights text was accepted, and a confirmed AVAILABLE skipped the partnership conflict check. Fixed: the quote must itself state the rights status; AVAILABLE + partnership → CONFLICTING even when confirmed (this was a real pre-existing bug).
- **Medium:** the library path `record(context=None)` bypassed the checks. Fixed: context is required.
- **Medium:** partly tautological tests. Fixed: 9 regression tests, one per finding.
- **Not fixed (accepted):**
  - list-order tie-breaking among several confirmations;
  - multi-target assertions are refused, with a message that could be clearer.

**Result (C8, real landscape; simulated analyst = AI run under the labelled SYNTHETIC_FIXTURE kind, INTERNAL DEVELOPMENT):**

| | Before | After |
|---|---:|---:|
| Open gates with an in-tool path | 1 / 39 | 39 / 39 (every gate field is assertable) |
| ELIGIBLE / UNRESOLVED / EXCLUDED | 4 / 14 / 22 | 7 / 11 / 22 |
| In-scope programs resolved (reference) | 4 / 9 | 7 / 9 |
| Wrong inclusions / exclusions | 0 / 0 | 0 / 0 |
| Actions taken | — | 9 (1 confirm, 6 cited assertions, 2 diligence requests) |
| Apply + re-screen time | — | 0.26 s (excludes ~25 s one-time ontology load) |
| Source FAILs overturned | — | 0 |

**Not achieved:**
- Efgartigimod IV / SC stay UNRESOLVED. The label calls it an "IgG1 antibody fragment", and asserting "monoclonal antibody" would be false; whether Fc fragments count is a buyer-spec decision, recorded as a diligence request.
- 8 out-of-scope programs stay UNRESOLVED (no citation was in hand for their targets).
- No human performed any of it, so analyst time is not measured.

**Risk noted:** SYNTHETIC_FIXTURE can confirm findings. Outputs label it, but an AI using that kind is honest only by labelling.

## Cycle 2: commercial-stage valuation block, cross-holder same-molecule flag (2026-10-28)

**Problems.** Audit findings 4 and 5: a marketed finalist could be valued with a pre-approval trial model, and the same molecule held by a different company (HBM9161 / batoclimab) is invisible.

**Criteria (frozen before code):**

| | Criterion |
|---|---|
| V1 | A selected finalist whose screened stage order is ≥ 6 (marketed / Phase 4), or whose assumptions give stage `approved`, is NOT READY with an explicit commercial-stage reason. No pre-approval rNPV is run, even with complete inputs |
| V2 | Pre-approval finalists are unaffected (the synthetic demo valuations are unchanged) |
| I1 | Records from different holders whose distinct names resolve to one authority drug get a `SAME_MOLECULE_DIFFERENT_HOLDER` flag (UNCERTAIN_RELATIONSHIP, review only, never merged) |
| I2 | A match arising only from one shared normalized name (the MB-102 class) does not raise I1; it remains SHARED_CODE |
| I3 | Real landscape: HBM9161 / batoclimab flagged; no other new flag unless explained |

**Result (real landscape, real S&E ontology):**
- **I1 / I3:** `SAME_MOLECULE_DIFFERENT_HOLDER` raised for batoclimab (Immunovant) vs HBM9161 (Harbour BioMed), and for HBM9161 vs RVT-1401. Nothing merged. No other cross-holder flag.
- **I2:** the MB-102 test still yields only SHARED_CODE. The eculizumab biosimilars are not flagged, which is correct: they are different products.
- **V1:** nipocalimab (U.S.-marketed) is NOT READY with the commercial-stage reason.
- **V2:** IMVT-1402 is unchanged (READY, valued). The synthetic demo's three valuations are unchanged (end-to-end test).
- **Tests:** 101 DealScreen tests pass. No AI review this cycle: the change is small and fully specified by tests. Noted as a process limitation.

**Self-criticism:** this cycle fixes defects introduced by my own earlier design (no stage check; the MB-102 rule hiding licensee pairs). Both were reachable from the first build's own test data.

## Cycle 3: U.S. rights holder separated from licensing availability (2026-10-28)

**Problem.** Every one of the 40 real programs shows U.S. rights UNKNOWN, including three
U.S.-marketed products whose FDA labeler is a public fact. DealScreen has one rights field and
cannot say "we know who holds U.S. rights, and we don't know whether they would license"
(audit finding 2, Gate D).

**Criteria (frozen before code):**

| | Criterion |
|---|---|
| R1 | A new optional canonical field `us_rights_holder` (profile-mapped) and an assertable field of the same name. The holder is shown separately from availability, with the evidence it came from |
| R2 | A known holder never changes availability. With no explicit availability statement, availability stays UNKNOWN (test) |
| R3 | A registry sponsor is not a holder. The real builder fills the holder only from an FDA labeler of a U.S. label listing the indication, and records that as "U.S. commercializer per FDA label", not as a license fact |
| R4 | Different holder values for one asset are shown as conflicting, never resolved silently |
| R5 | Real landscape, as a new versioned file (v1 stays pinned): programs with a sourced U.S. holder go from 0 to the count of gMG-labelled products. Programs shown AVAILABLE stay 0. Dispositions are unchanged (4/14/22) |

**Result (real v2 landscape, real ontology; `cycle3_measurement.json`):**
- Programs with a sourced U.S. holder: 0 → 8, exactly the gMG-labelled products (argenx ×2, Janssen, Alexion ×2, Amgen, Teva, UCB).
- Availability: UNKNOWN for all 40; AVAILABLE for 0.
- Dispositions unchanged at 4/14/22. v1 stays byte-identical and pinned.
- Tests R1-R5 pass (105 DealScreen tests).

**Not achieved:**
- Rozanolixizumab has no holder because openFDA lacks its label (source gap). It can be closed by one cited assertion from UCB's release.
- No licensor / licensee structure is extracted automatically. The 10-Q territory sentence does not name the asset, so it needs an analyst's judgement (shown in test R1).
- Availability remains unknown everywhere: no public source in this landscape states it. That is the honest state of public data, not a tool defect.

**Self-criticism:** "U.S. commercializer per FDA label" is evidence of commercial control, not of who owns the IP. The label text says exactly that, and nothing downstream treats it as availability.
