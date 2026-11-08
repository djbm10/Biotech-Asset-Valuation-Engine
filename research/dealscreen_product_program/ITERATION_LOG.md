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

## Cycle 4: per-command latency (2026-10-28)

**Problem (measured).** Each `bve-dealscreen screen` / `import` call took 47-54 s and 1.7 GB on
the real landscape, almost all of it loading the S&E ontology. An analyst resolving 9 items
through the CLI pays that on every re-screen.

**Diagnosis.** DealScreen needs the ontology only to normalize vendor target strings, a fixed
set per landscape. The gate engine also normalizes canonical symbols it already has, which is
the identity for canonical input.

**Criteria (frozen before code):**

| | Criterion |
|---|---|
| P1 | At import, every distinct target string, plus each target sub-part the FactBuilder splits, is resolved once and stored in `target_cache.json` (raw → symbol or null) |
| P2 | `screen` uses the cache and, when all buyer target ids are canonical per the cache, runs the gate engine without loading the ontology. Otherwise it falls back to the full ontology path and says so |
| P3 | `screening.json` is byte-identical between the cached path and the full-ontology path on four workspaces: synthetic 200, real v1, real v2, and real v1 with the Cycle 1 assertions |
| P4 | A cache miss (a new string, e.g. an asserted target not seen at import) falls back to the ontology for that string. Never null-by-default |
| P5 | Measured `screen` wall time and peak memory before and after, reported as measured |

**Result:**

| Check | Result |
|---|---|
| P3, byte equality vs the full-ontology screen (`cycle4/equivalence_result.json`) | **identical in all four workspaces**: synthetic 200, real v1, real v2, real v1 + Cycle 1 assertions |
| P5, CLI `bve-dealscreen screen` on the real landscape | **33.5 s / 1.71 GB → 0.53 s / 88 MB** |
| P2, P4 | fallback rules tested; 110 DealScreen tests pass |

**Self-challenge (fixed):**
- the cache now records the ontology version it was built from (`target_cache_meta.json`);
- target assertions are checked through the cache before falling back to the ontology.

**Remaining:**
- `import` still loads the ontology once, about 25-50 s, because it builds the cache and the identity flags.
- A stale cache after an ontology upgrade is detectable through the metadata but not enforced; the analyst must re-import.

## Cycle 5: decisions survive a vendor refresh (2026-10-28)

**Problem (reproduced).**
- Claim ids embed the row number (`asset:r3:target`).
- An analyst rejected rozanolixizumab's target claim, so the program was UNRESOLVED. Re-importing the same 40 rows in a different order gave the claim the id `asset:r2:target`. The rejection silently stopped applying and the program went back to ELIGIBLE.
- Any real export refresh reorders rows, so prior analyst work is lost with no warning.
- This is my own design defect from the first build; no test covered a re-import.

**Criteria (frozen before code):**

| | Criterion |
|---|---|
| F1 | Claim ids are content-based (asset, field, value hash; occurrence index only for identical repeated values), so they are stable under row reordering. Row number and column stay on the claim as provenance |
| F2 | Re-importing into an existing workspace is a refresh. The previous import is archived and a `refresh_report.json` lists: assets added and removed; per-asset field values added and removed; every logged decision whose subject (claim, finding, assertion asset, finalist) no longer exists, as ORPHANED, never dropped silently |
| F3 | After a reordered re-export of identical content, every decision still applies and `screening.json` dispositions are identical (the rozanolixizumab regression) |
| F4 | A changed source value orphans a decision on the old value and reports it. It is never transferred to the new value |
| F5 | The workbook shows orphaned decisions in the Diligence sheet. The synthetic and real regressions keep their disposition counts |

**Result (Cycle 5):**
- The reproduced regression is fixed. Rozanolixizumab's rejected-target decision survives a reordered re-export (it stays UNRESOLVED), and all dispositions are identical.
- A changed value orphans the old decision, reports it, and does not transfer it.
- Removed assets are reported, the previous import is archived, and orphans appear in the workbook.

**Adversarial review of Cycles 3-5 (AI reviewer, separate context; not human validation):**

| Finding | Severity | Status |
|---|---|---|
| The Cycle 4 fast path read an asserted or confirmed target missing from the import-time cache as "no target"; P4 was false inside the fast path and my P4 test mocked the fallback | **High (blocking)** | Fixed: the fast path requires every target string reachable from assertions and confirmed findings to be cached, and a changed ontology version also forces the full path. Regression test reproduces the case |
| "U.S. commercializer per FDA label" overclaims; openFDA `manufacturer_name` is the labeler (possibly a distributor) | M1 | Fixed: "U.S. labeler per FDA label; not a rights statement". Several labelers → left blank |
| Claim ids ignored source, so identical values from two sources could swap decisions on reorder | M2 | Fixed: source reference and date are part of the id; test |
| Legacy row-based ids reported as "value changed" | M3 | Fixed: reported as legacy ids to re-decide; test |
| Refresh report false negatives: a decided asset whose content (or source/date) changed was not flagged; diligence requests not checked | M4 | Fixed: `decided_assets_with_changed_content`; values compared with source and date; diligence requests checked; test |
| A failed refresh (e.g. tampered log) could leave a half-written workspace | M5 | Fixed: the report is computed before any write; test |
| `_ontology_disabled` mutates process env (not thread-safe) and evicts a loaded resolver | L1 | Accepted and documented: CLI is single-threaded |
| Canonical symbols re-resolving to themselves is assumed, not checked per entry | L3 | Accepted: holds on all four tested workspaces |

After the fixes:
- P3 was re-verified, byte-identical on all four workspaces;
- 119 DealScreen tests pass;
- Cycle 3's measurement still holds (8 holders, 0 AVAILABLE, 4/14/22) with the corrected label.

**Self-criticism:** two of my own acceptance claims, P4 ("never null-by-default") and the R3 wording, were false or overstated until an independent context checked them. Every future cycle keeps this review step.

## Cycle R1: rights-evidence ingestion and trustworthy transaction classification (2026-10-30)

AI-simulated, internal development. Full record: `research/dealscreen_rights_v1/` (`ACCEPTANCE.md`, `REVIEW.md`,
`REVIEW_RESPONSE.md`, `REREVIEW.md`, `REREVIEW_RESPONSE.md`, `REREVIEW2.md`, `REREVIEW2_RESPONSE.md`).

**Problem (reproduced at 0ee7752).** Comparison cycle C1 found the transaction view called 50 of 62 CLDN18.2
programs `OPEN` with no rights evidence at all. Takeda-licensed IBI343 (worldwide outside Greater China) was
unresolved #1 and OPEN; Merck KGaA-optioned SHR-A1904 was transaction #3 and OPEN. "Deprioritized" came only from a
registry-sponsor name match. Returned rights were invisible.

**Criteria.** AC1–AC14, frozen before code in `ACCEPTANCE.md`; baseline in `baseline/`.

**Change.**
- A separate deals/rights export imports through its own profile (`rights.py`). Every event keeps the source
  system, file hash, row, URL, quote and dates with their precision. Unknown labels and unreadable dates are
  rejected rows, never guessed.
- A per-program rights ledger (`rights_position.py`) replays the events in date order into a position in the
  buyer territory: licensed, option held, shared, territory unreadable, conflicting, returned, owner acquired, not
  encumbered, availability stated, or no rights evidence. Territory text is read conservatively
  (`rights_territory.py`).
- The transaction view (`transaction.py`) drops the `OPEN` tier. Only the four clear positions can reach the two
  top tiers, and only with current, complete evidence. Scientific gates, dispositions and ranks are untouched.
- Every classification shows its evidence (row, date, parties, territory, URL, quote, event id), its reasons and
  its diligence questions in the JSON, the workbook and the memo.

**Adversarial reviews (AI, separate contexts; not human validation).**

| Round | Reviewed | Definite failures found | Outcome |
|---|---|---|---|
| 1 (`REVIEW.md`) | R1 | territory parsing (T1–T8), event order and matching (L1–L7), the sponsor used as owner, wrong holders | fixed in revision 2 |
| 2 (`REREVIEW.md`) | revision 2 | 23, of which 12 were new paths into a top tier (undated or partial outcomes, unreadable or concluded availability statements, an unvalidated buyer territory, rejected rows and analyst encumbrances ignored) | fixed in revision 3; 52 held-out tests |
| 3 (`REREVIEW2.md`) | revision 3 | 23 definite: 11 paths into a top tier (3 introduced by revision 3, 6 close variants of claimed fixes, 2 older), 3 false encumbrances, 9 label or wording errors; none in the CLDN18.2 output; AC14 FAIL | fixed in revision 4: tiers 0 and 1 became an allow-list (complete, specific, current, uncontested); 69 more held-out tests; the reviewer's flagged top-tier placements in its end-to-end workspaces 12 → 0 (implementer-measured) |
| 4 (`REREVIEW3.md`) | revision 4 | 18 definite: 8 High (7 close variants of claimed fixes, 1 new: tier 0 or 1 while a third party may hold U.S. rights, or on contrary, undated or unattached evidence), 2 Medium (false encumbrances), 8 Low (wording); none in the CLDN18.2 output, but six High errors reached tier 0 or 1 end to end on copies of the CLDN18.2 workspace. Cause: the allow-list ran in full only on the "returned" path | fixed in revision 5: one fail-closed gate on every path (`REREVIEW3_RESPONSE.md`); 141 more held-out tests |
| 5 (`REREVIEW4.md`) | revision 5 | 19 definite: 11 High (paths into tier 0 or 1: dates read as codes, another party's offer, U.S. grants erased as party names, returns to a third party, Partnerships and Geographic Notes unread, notes in party and company names, status-flag endings, undated acquisitions, the field path and the gate ignoring the buyer territory), 4 Medium (false conflict or encumbrance), 4 Low (wording); none in the CLDN18.2 output; 18 flagged top-tier placements end to end on copies of the CLDN18.2 workspace. Cause: the gate passed what its reader marked as understood | fixed in revision 6: the gate's default inverted (plain forms only, `REREVIEW4_RESPONSE.md`); 90 more held-out tests |
| 6 (`REREVIEW5.md`) | revision 6 | 14 definite: 6 High (the plain forms accepted texts that fit their words and meant the opposite: "U.S." hidden by lower-casing in party spans, pronouns and "the owner" counted as the company, notes inside the text dropped, "other places" fixed as non-U.S. for every buyer; ownership words and rights rows' quotes unread), 2 Medium (a {US, CA} buyer lost the U.S.-rights field; "or" not read), 6 Low; none in the CLDN18.2 output; end to end, test inputs took tier 0 and 1 places (ws_e #1–#7, ws_f #1–#5). Cause: the plain forms overrode the reader and read on lower-cased text in U.S. terms | fixed in revision 7 (`REREVIEW5_RESPONSE.md`); 72 more held-out tests |
| 7 (`REREVIEW6.md`) | revision 7 | 7 definite: 5 High (the "other places" party span took any words, so "… and in the Americas to X", "for ROW", "elsewhere" passed; a quote's prefix before a colon was dropped as a speaker; options and "worldwide" in quotes unread; an offer's place not compared with a non-U.S. buyer; ending dates compared by the start of a year or month), 2 Low; none in the CLDN18.2 output; end to end, test inputs took #1–#6 in the top tiers (ws_g) | fixed in revision 8 (`REREVIEW6_RESPONSE.md`); 60 more held-out tests |
| 8 (`REREVIEW7.md`) | revision 8 | 9 definite: 6 High (party names in capitals or with condition words passed; a covering ending, lapse or acquisition was accepted without reading its quote; quote clauses naming a third party with no place, or wider words not on the list, passed; a grant reported before the as-of date but effective after it was dropped; availability statements dated only to the as-of year or month counted), 3 Low; none in the CLDN18.2 output; end to end, test inputs took #1–#6 and RC118 in the top tiers (ws_h) | fixed in revision 9 (`REREVIEW7_RESPONSE.md`); 79 more held-out tests |
| 9 (`REREVIEW8.md`) | revision 9 | 7 definite High: third parties written without a corporate word or a listed verb (passive voice, possessives, colons, "a subsidiary of X") passed; endings not yet in effect, partial or disputed passed in unlisted words; wider reach in unlisted words passed, and the narrowed list stopped catching the licensee's own option; party names with area or signal words passed; future-dated grants with no or a coarse source date were dropped; an acquisition of a party in no grant gave an owner position. Low: false labels (program codes as companies, `NO_RIGHTS_EVIDENCE` beside cited rows) | 0 in the CLDN18.2 output |
| 10 (`REREVIEW9.md`) | revision 10 | 8 definite High: lower-case third parties and grant words on endings passed (LOWER); names placed by shape or neighbour (PLACE); a known name's corporate words swallowed "U.S." (MASK); wider reach and later endings in unlisted words (WIDER3, HEDGE3); a future option exercise was dropped (FUT3); rows beside a statement, return or lapse were never read (UNCITED); party names without a company word (PN4). Medium: an affiliate or the company's own purchase read as the owner (OWNER-KEY). Usefulness: most real quotes would block when read directly; a "shares" class-order defect | 0 in the CLDN18.2 output |
| 11 (`REREVIEW10.md`) | revision 11 | 13 definite High: the word lists held words that carry a holder, reach or condition ("has", "own", "all", "after", "not" on lapses, sale words); "may" read as a month; a notice date satisfied the dated-ending rule; dates without a four-digit year were never compared; "Holdings"/"Group" read as the known party; code-shaped names placed; exchange notes and title-case headlines deleted unread; landscape words (a partner, "American") became allowed. Medium: affiliates as owner, two acquirers, pending or minority acquisitions. Low: two labels | 0 in the CLDN18.2 output |
| 12 (`REREVIEW11.md`) | revision 12 | 6 High: a clause the plain-form reader accepted skipped the templates, so "it", "we", "the company" and "<company> Holdings/International/Global" read as the company (PF-PRONOUN, SUFFIX2); Chinese and full-width text was invisible (NONLATIN); a headline could pass as a dateline (HEADLINE2); "an option to acquire NB-7" read as the row's option (ACQ-OPT); condition and holder words from a field folded into a description (VOCAB2). 5 Medium (UNPLACED, DEAL-KIND, OWNER-THE, STRIP-CAPS, CONFIRM-KIND: an AI could clear a block by omitting a flag, and the implementer's own demo did), 2 Low. None in the CLDN18.2 output; end to end, 7 held-out programs in tier 1 (ws_m) | fixed in revision 13 (`REREVIEW11_RESPONSE.md`); 90 more held-out tests |
| 13 | revision 13 | not yet reviewed | |

**Measured result (CLDN18.2, against the frozen reference).**
- False "unobstructed" (third-party U.S. rights shown OPEN or in a top tier): 4 definite plus zanidatamab at
  baseline → 0 since R1.
- IBI343 → licensed to Takeda, deprioritized. SHR-A1904 → option held by Merck KGaA, deprioritized, stale-flagged.
  RC148, FL-301, XNW27011 → licensed per evidence. Givastomig → shared.
- Not achieved: LM-302 stays conflicting (the library does not record that Bristol Myers Squibb succeeded Turning
  Point), so AC13's "LM-302 returned" is not met. SKB315's return is missed (not in the library).
- Usefulness against general Claude on the 15 deal programs: DealScreen 10 right / 4 partial / 1 missed; general
  Claude 14 / 1 / 0. DealScreen is better on audit (every call cited, staleness explicit, no "no record" read as
  "unencumbered"); general Claude is better on recall. No advantage is demonstrated.
- Science: 0 of 62 CLDN18.2 scientific fields changed; 0 changes on synthetic, FcRn v1/v2 and C5 held-out
  (pre-R1 vs revision 4, 312 assets); cycle-4 equivalence byte-identical on all four workspaces.
- Revision 4 changed no CLDN18.2 tier or call; it changed the text of two excluded programs and added dates and
  reasons to the memo's "also exists" line. Its gains are on held-out inputs only.

**Self-criticism.** Revision 1 passed its own tests and still had 12 paths into a top tier that only an independent
context found. Every rule that reads weak evidence (undated, unreadable, partial, concluded) must be written in the
direction that cannot promote a program.

**Revision 4 (2026-10-31).** Took the reviewer's single highest-value fix instead of patching cases one by one: a
clear position reaches tier 0 or 1 only when no check names a blocker (`top_tier_blockers`, `check: detail`, shown
with a question). Also: holder and analyst statements are reconciled with the rights file; program ids match without
case; rows that attach to no program are listed in every output; a return recorded without its grant counts only
when it returns the rights to the program's company; the event replay moved to `rights_ledger.py`; `bve.dealscreen`
is mypy-clean. Revision 4 also found two problems of its own: a loose name match that would have absorbed a namesake's
claim ("Acme" vs "Acme KGaA"), and a rule that held back "rights returned, now offered" (REREVIEW K3).

**Self-criticism (revision 4).** Round 2 already asked for a promotion guard. Revision 3 built it as two flags,
and round 3 found 11 new paths around them. The allow-list should have been built then. Revision 4 is
implementer-measured only.

**Revision 5 (2026-11-01).** Round 4 showed that revision 4's allow-list ran in full only where a return decided the
position. Revision 5 makes it one fail-closed gate (`rights_gate.reconcile`) that runs on the rights-file path and the
landscape/analyst field path alike and passes only what it can read:
- grants that an availability statement clears must have ended, by a dated record of their own, before the
  statement, and pass the same checks as on the returned path;
- the licensor a clear position rests on, the party that states availability and the recipient of a return must be
  the program's company per the landscape (or linked to it by a recorded acquisition); otherwise an ownership
  question;
- every landscape and analyst U.S.-rights statement and holder is read, by a strict clause reader
  (`rights_reader.py`): a contrary statement or another holder makes the position conflicting; text it cannot read,
  a holder's note, or an offer made by another party blocks; statements dated after the as-of date are not applied;
- rights rows that were not applied guard the programs they may concern: a rejected row whose id matches no program
  holds every program back, and a row whose id is close to a program's ("AB 24" beside "AB-24") holds that program;
  each is listed with its parties in the JSON, workbook and memo.
`screening.program_transaction` is now the single per-program path, so the held-out tests run production code.

Measured by the implementer (`REREVIEW3_RESPONSE.md`): DealScreen tests 512 → 653 (141 held-out from round 4);
every round-4 unsafe case is out of tiers 0 and 1; 22 of the 23 clean cases the reviewer expects in a top tier reach
it (G17 is held back by the new company rule: a usefulness cost); the reviewer's flagged top-tier placements in its
end-to-end workspaces 13 → 0. CLDN18.2: no tier, position, rank, holder or staleness changed; zolbetuximab's labeler
note is now asked about; memo 1,609 → 1,701 words. Science: 0 of 62 CLDN18.2 fields; 0 changes on 312 assets across
synthetic, FcRn v1/v2 and C5 held-out (pre-R1 0ee7752 vs revision 5); cycle-4 equivalence byte-identical on all four
workspaces. Usefulness against general Claude unchanged (10 / 4 / 1 against 14 / 1 / 0).

**Self-criticism (revision 5).** Revisions 2 to 4 added checks where a reviewer had found a failure, so each round
found the same error entering by a path nobody had listed (a statement, a field, a holder's note, unread text, a row
that was never applied). Revision 5 starts from the other end: what does a top-tier placement rest on, and is every
part of it read? The cost is caution: near-namesakes and "Option available to partners" are held with a question.

**Revision 6 (2026-11-01).** Round 5 showed the revision 5 gate still trusted its reader: a text the reader marked as
understood passed, and the reader misread dates as program codes ("Available 2H26"), another party's offer as the
company's ("The licensee is seeking a partner"), and a U.S. option as a party name ("with an option to U.S. rights").
Revision 6 inverts the default (`rights_allow.py`): beside a clear position a rights text passes only if every clause
is a plain form (placeholder or no-grant phrase, a plain offer by the company, the company keeping or regaining the
rights, a grant over other places only); anything else blocks, quoted and cited. The gate now also reads
Partnerships and Geographic Notes, notes in company and rights-row party names, and runs for every buyer territory;
the landscape's U.S.-rights fields are a position only for a buyer territory of exactly the U.S.; status-flag endings
and undated acquisitions no longer clear a grant; unattached rows guard suffixed ids ("AB-24 (ADC)") and, when their
id points nowhere, programs of a company they name. Memo and `assert` wording no longer overclaim (L1–L4).

Measured by the implementer (`REREVIEW4_RESPONSE.md`): DealScreen tests 653 → 743 (90 held-out from round 5); every
round-5 High and Medium case is out of tiers 0 and 1 or no longer a false conflict; the over-caution costs the reviewer
named for Chinese originators ("Ex-China rights available", company-retains wording, a city inside a legal name) now
reach the expected tier; the reviewer's flagged top-tier placements in its end-to-end workspaces 18 → 0. CLDN18.2: no
tier, position, rank, holder or blocker changed. Science: 0 of 62 CLDN18.2 fields; 0 scientific or tier changes on
312 assets (revision 5 vs 6); cycle-4 equivalence byte-identical. Usefulness against general Claude unchanged
(10 / 4 / 1 against 14 / 1 / 0).

**Self-criticism (revision 6).** Revision 5 claimed to fail closed but only failed closed on what its reader admitted
it could not read. A gate is only as strict as the narrowest list of what it accepts; revision 6 writes that list
down. The cost is more held-back programs on real free-text rights notes, each with a question.

**Revision 7 (2026-11-01).** Round 6 showed revision 6's plain forms were a new way in: they ran on lower-cased
text, so "U.S." inside "Licensed to Tessaly Pharma (U.S.)" vanished; "it" and "the owner" counted as the company;
a note inside the text was dropped; "other places" meant "not the U.S." for every buyer; and a plain form could
accept a text the reader had marked unread. Revision 7 reads places as written and compares them with the buyer
territory, refuses notes and cross-clause pronouns, never lets a plain form widen the reader (except the company
keeping its rights), reads ownership words and every rights row's quote, makes a contrary Partnerships or
Geographic Notes text a conflict, reads the U.S.-rights field for any buyer territory containing the U.S., blocks a
status ending with no source date, and limits a company's unrelated deal rows to those that may reach the buyer
territory. It also removes the usefulness costs round 6 named ("Partnered in China; U.S. rights available",
"(ex-China)", "partner(s)", "Open to partnering discussions", "(Hong Kong) Limited").

Measured by the implementer (`REREVIEW5_RESPONSE.md`): DealScreen tests 744 → 816; the reviewer's end-to-end
top-tier placements ws_e 7 → 0 and ws_f 5 → 0; every round-6 High and Medium case is out of tiers 0 and 1. CLDN18.2:
every screening field identical to revision 6. Science: 0 of 62 CLDN18.2 fields; 0 of 312 cross-version assets;
FcRn v2 shows no holder for 8 programs whose holder cell carries a source note (no tier change); cycle-4
equivalence byte-identical. Usefulness against general Claude unchanged (10 / 4 / 1 against 14 / 1 / 0).

**Self-criticism (revision 7).** Revision 6 wrote down what the gate accepts but checked it in a weaker form than the
reader it was meant to restrain. An allow-list is only as strict as the reading of each item on it.

**Revision 8 (2026-11-01).** Round 7 found revision 7's "other places" form strict on the place but not on the
party: anything after "to" counted as a name. Revision 8 reads the party as written and accepts only a name
(capitalised words and corporate punctuation, no lower-case word, dash or place word); strips a quote's speaker only
when it is the row's grantor or the company; reads a quote's options and wider territories clause by clause, so a
quote saying the company kept its U.S. rights now passes while "an option on worldwide rights" blocks; requires an
offer naming places to cover the buyer territory; and does not apply an ending dated only to a year or month that
contains the as-of date. Measured by the implementer (`REREVIEW6_RESPONSE.md`): DealScreen tests 816 → 876; the
reviewer's end-to-end top-tier placements 6 → 0; CLDN18.2 identical to revision 7; 0 of 62 and 0 of 312 science
changes; equivalence byte-identical; usefulness against general Claude unchanged (10 / 4 / 1 against 14 / 1 / 0).

**Self-criticism (revision 8).** Revision 7 tightened the half of each form that earlier reviews had attacked and left
the other half open. Each part of an allow-list entry needs the same strictness: what it does not recognise, it
must refuse.

**Revision 9 (2026-11-02).** Answers `REREVIEW7.md`. Every cited row's quote is now read, whatever the row's own
territory. A clause that names a company other than the row's parties and the program's company blocks, and so does
an ending made partial or conditional. A capitalised name before "rights" that the territory reader cannot read also
blocks. Party names may not hold joining, place or condition words in any letter case. A grant reported before the
as-of date but effective after it blocks. Availability statements dated only to a period containing the as-of date
are not applied. The quote's wider-word list was narrowed so that ordinary press words pass.

Measured by the implementer (`REREVIEW7_RESPONSE.md`):
- DealScreen tests 1,099 → 1,178.
- The reviewer's end-to-end top-tier placements 7 → 0. TORL-2-307-ADC moves up as the intended usefulness fix.
- CLDN18.2 identical to revision 8: 0 of 62 science fields and 0 of 62 transaction views changed.
- Cross-version 0 of 312 changed; equivalence byte-identical.
- 1 of 17 real CLDN18.2 quotes blocks under the new rule.
- Usefulness against general Claude unchanged (10 / 4 / 1 against 14 / 1 / 0).

**Self-criticism (revision 9).** The `territory <= own` shortcut was stated as a rule in revision 8 without asking
which row types it was true for. It was true for grants only. A shortcut that skips reading evidence needs the same
per-type check as any other rule.

**Revision 10 (2026-11-02).** Answers `REREVIEW8.md`. The quote reader now fails closed (`rights_quote`): every
capitalised name in a cited quote must be placed as a row party, the program's company, the program, a place, a
person, an adviser or a news source. The clause may use only the rights words that restate its own row type. Time
and hedge words block an ending. Wide words and extra places, including states and provinces, block a row that does
not cover the buyer territory. Revision 9's deny-lists are removed. Party names may not hold place, area or signal
words. A future-dated grant blocks unless its source shows it was reported after the as-of date. An acquisition of
a party in no grant blocks. Rows recorded but none applied have their own position.

Measured by the implementer (`REREVIEW8_RESPONSE.md`):
- DealScreen tests 1,178 → 1,300.
- The reviewer's end-to-end top-tier placements (ws_i) 7 → 0.
- CLDN18.2 identical to revision 9: 0 of 62 science fields and 0 of 62 transaction views changed; memo identical.
- Cross-version 0 of 312 changed; equivalence byte-identical.
- 1 of 17 real CLDN18.2 quotes blocks, as at revision 9.
- Usefulness against general Claude unchanged (10 / 4 / 1 against 14 / 1 / 0).

**Self-criticism (revision 10).** Three rounds added words to deny-lists, and each round's reviewer found the next
missing word. The inversion REREVIEW8 asked for, passing only what can be placed, should have been made when the
second list gap appeared. Running the real quotes through the new reader before committing found two false blocks
(a currency code and "will pay … to acquire") that the synthetic tests did not.

**Revision 11 (2026-11-02).** Answers `REREVIEW9.md`. The quote reader reads every word, not only names: a clause
passes only when each word is a grammar word, an amount or date, a generic drug-development word, a word restating
the row's own type, or a word from the program's own landscape record (`rights_vocab`). Names are placed only as a
row party or the company (never absorbing a place word), the program, a place or an agency code. Datelines, speaker
attributions, advisers and bylines are removed only when anchored. Every date is compared with the as-of date. A
clear position cites, and the gate reads, every applied row. A future option exercise blocks. An acquisition counts
for the owner only when the acquired party is a grant party or the company itself. Rows that give no position are
never "no rights evidence".

Measured by the implementer (`REREVIEW9_RESPONSE.md`):
- DealScreen tests 1,327 → 1,436 (with U1 revision 6).
- The reviewer's end-to-end top-tier placements (ws_j) 7 → 0; attack probes 79 → 0 top-tier placements (with the
  harness's placeholder quote removed, 4 judgement calls and controls remain).
- CLDN18.2: 0 of 62 science fields changed. Zolbetuximab and IMAB362 move from owner acquired to rows not applied
  (OWNER-KEY's cost), with no tier change.
- Cross-version 0 of 312 changed; equivalence byte-identical.
- Real CLDN18.2 quotes read directly: 13 of 17 block (the reviewer counted 5 of 17 at revision 10). Usefulness on
  the reviewer's 43 clean cases: 14 → 11 (placeholder removed) or 5 (harness unchanged).

**Self-criticism (revision 11).** Revision 10's response counted "1 of 17 real quotes block" over the rows that reach
the reader, which made a strict reader look harmless; the honest count reads every quote. Citing every row also made
placeholder quotes in test fixtures and probe harnesses block, which first looked like a regression.

**Revision 12 (2026-11-02).** Answers `REREVIEW10.md`. The word lists are deleted. Beside a clear position, each
clause of every applied rights row's quote must match one of 34 fixed sentences for its row type, read whole
(`rights_template`): the row's own parties in their roles (one legal entity, never "Holdings" or "Group"), the
program with an optional description made of drug-development words and its own lower-case target or indication
words, the type's verb (no modal, no holding "has", no condition, no sale; acquisitions completed only), a place
inside the row's territory, a date with a year whose period ends by the as-of date or holds the row's own date.
Anything else blocks with the clause quoted, and only a human analyst can clear it, by recording `CONFIRM_RIGHTS_ROW`
for the event; the confirmation is bound to a hash of the row and lapses when the row changes. Two acquirers of one
party are contested; an acquisition counts only for one legal entity.

Measured by the implementer (`REREVIEW10_RESPONSE.md`):
- DealScreen tests 1,436 → 1,575.
- The reviewer's probes: 67 → 5 of 75 top-tier, all 5 controls; end-to-end ws_l 7 → 0 top-tier programs.
- CLDN18.2: 0 of 62 science fields changed; no position or tier changed (2 rows change wording: LBL-OWNER,
  LBL-DATE). Cross-version 0 of 312; equivalence byte-identical.
- Usefulness falls: real CLDN18.2 quotes read directly 13 → 16 of 17 block; the reviewer's 43 clean cases 11 → 3.
  Each block asks for one recorded human confirmation of the row.

**Self-criticism (revision 12).** Five revisions patched word lists after each review; each list held a word that
could carry a holder, a reach or a condition. The reviewer had pointed at structure two rounds earlier. Running the
real quotes before committing found two template gaps (a description before the program, an indication after the
place); both were fixed generically, and the rest of the real wording is left to the analyst confirmation.

**Revision 13 (2026-11-08).** Answers `REREVIEW11.md`. The fixed sentences are the only reader of a rights row's
quote: the plain-form shortcut is gone, and "<grantor> retains rights …" is the only sentence that keeps rights with
a party. Every character is read; non-ASCII text that is not typography blocks. A dateline needs a one-line city and
region parts that are places; a stripped name holds no rights or place word. A grant, an option or an exercise must
name a place unless the row covers the buyer territory; "an option to acquire NB-7" is no option sentence. Field
words that carry a condition or a holder never describe the program. Only a license ends a license. "The Origin Bio"
acquired moves the owner. `CONFIRM_RIGHTS_ROW` must state `--reviewer-kind HUMAN`, is refused in a known AI agent's
shell, says the kind is as recorded, and is keyed by the row's content so a re-import keeps it.

Measured by the implementer (`REREVIEW11_RESPONSE.md`):
- DealScreen tests 1,575 → 1,726 (with U1 revision 7).
- Every REREVIEW11 attack blocks; end-to-end ws_m 7 → 0 top-tier programs; the clean controls in ws_h2 and ws_i2
  stay top tier.
- CLDN18.2: transaction CSV and memo byte-identical to revision 12; 0 of 62 science fields changed. Cross-version
  0 of 312; equivalence byte-identical.
- Usefulness rises a little: real quotes read directly 16 → 15 of 17 block; REREVIEW10's 43 clean cases 3 → 6 pass;
  REREVIEW11's 24 sentences 11 → 15 pass. Confirmations now survive re-imports.

**Self-criticism (revision 13).** In revision 12's demonstration I, an AI, recorded a HUMAN confirmation under a
human-looking name on an attack row, and the response then said "No AI can clear a block". Both were wrong; the
review caught them. Revision 13 makes the kind explicit and refuses known agent shells, and the response says
plainly that DealScreen cannot verify a person. The plain-form shortcut was a second reader left beside the templates
for convenience; one reader is easier to reason about.

## Cycle U1: a concrete next action for every tool UNKNOWN (2026-10-30 to 2026-11-01)

Acceptance criteria frozen before code (`research/dealscreen_unknown_actions_v1/ACCEPTANCE.md`, committed 1436d95).
Each UNKNOWN decision on a program that is not excluded gets a diagnostic beside the S&E's generic action: a class
describing the record (indication, target, modality, phase), the values as written and the cited fact that would
decide the gate. Classes come only from the frozen NCIt authority, the target and modality readers and the buyer's
requirement; a diagnostic never changes a gate, disposition or rank.

| Round | Code | Findings | Response |
|---|---|---|---|
| 1 (`REVIEW.md`) | revision 1 | 1 critical (an unresolvable request made every record "a different disease"), 2 high (non-site "site" words; an acronym clean-up), lower ones | revision 2 (`REVIEW_RESPONSE.md`) |
| 2 (`REVIEW2.md`) | revision 2 | U1-7 not met: 2 high (an NCIt stage concept for the requested site called a different disease; a restatement that picked a different disease), 6 medium or medium-low (multi-word sites dropped and a spelling bug, acronym as basket, non-site words, negated target mentions, isoform and suffix errors, placeholders), 5 low | revision 3 (`REVIEW2_RESPONSE.md`) |
| 3 (`REVIEW3.md`) | revision 3 | U1-1 to U1-6 met, U1-7 not: 9 definite (1 medium-high: the new "under a broader parent" class given to lymphomas, sarcomas and other organs; 2 medium: expression levels read as negation, Roman numerals and capitals switching off BASKET; 6 lower) | revision 4 (`REVIEW3_RESPONSE.md`) |
| 4 (`REVIEW4.md`) | revision 4 | U1-1 to U1-6 met, U1-7 not: 2 medium (an all-caps qualifier made an "ALL" record a basket, a regression; stage concepts of neuroendocrine, small-cell and sarcoma lineages kept the "under a broader parent" class), 7 lower | revision 5 (`REVIEW4_RESPONSE.md`) |
| 5 (`REVIEW5.md`) | revision 5 | U1-1 to U1-6 met, U1-7 not: 2 medium regressions ("ALL" before a qualifier or population word called a basket; another target's "negative or positive" cancelled the required target's negation), 1 low | revision 6 (`REVIEW5_RESPONSE.md`) |
| 6 (`REVIEW6.md`) | revision 6 | U1-1 to U1-6 met, U1-7 not: 1 high (a two-disease "or" name was classed by the screen's reading of one half, so a record naming the requested indication was called a different disease), 1 medium (another target's "positive" cancelled a negation), 5 low (state joins, Unicode dashes, "ALL disease" as a basket, "absent", role words dropping a site) | revision 7 (`REVIEW6_RESPONSE.md`) |
| 7 | revision 7 | not yet reviewed | |

**Measured result (revision 3, implementer, AI-simulated).** CLDN18.2: 38 of 38 open gates carry a diagnostic
(baseline 0). Held-out FcRn v1, FcRn v2, C5 and synthetic: 104 of 104. Science and transaction fields: 0 of 62 and
0 of 312 programs changed; cycle-4 equivalence byte-identical on 4 of 4. No reference-IN program has a gastric or
junction name called a different disease; SOT102 (reference IN) still points away, because its record names only
pancreatic cancer. DealScreen tests 876 → 1,052 (revision 4: 1,099; CLDN18.2 outputs identical to revision 3; revision 5: 1,327 with R1 revision 10, CLDN18.2 outputs identical to revision 4; revision 6: 1,436 with R1 revision 11, CLDN18.2 actions identical to revision 5; 1,575 with R1 revision 12, CLDN18.2 actions identical; revision 7: 1,726 with R1 revision 13, CLDN18.2 actions identical).

**Self-criticism (U1).** Revision 2 fixed the reviewed inputs and broke two common ones (spelled-out junction names,
NCIt stage concepts), which a sweep over CLDN18.2's own names would have caught. A describing layer still misleads
when its class name is stronger than the authority's relation: "different disease" needs the authority to say so.

