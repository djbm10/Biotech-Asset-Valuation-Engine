# DealScreen readiness scorecard

The same 15 dimensions every cycle. No numerical readiness score. Status values:
DEMONSTRATED, PARTIAL, NOT DEMONSTRATED, BLOCKED. Evidence is internal development unless
stated otherwise.

## Scorecard as of Audit 0 (2026-10-28, before Cycle 1)

| # | Dimension | Implemented | Known defects | Evidence | Status | Next improvement |
|---|---|---|---|---|---|---|
| 1 | Landscape ingestion and integrity | CSV/XLSX, mapping profiles, exact row accounting, duplicates, rejections with reasons, manifest | No refresh/diff between exports; one source reference per row (field provenance lives outside the importer) | 200/200 synthetic, 40/40 real; tests | PARTIAL | Refresh diff (Gate I) |
| 2 | Identity reconciliation | Keyed by source ID; shared-code flag; same-company authority merge proposal | Same molecule under a different holder not flagged (HBM9161 / batoclimab); merges cannot be applied | MB-102 test; real run | PARTIAL | Flag cross-holder same-molecule pairs |
| 3 | Screening accuracy and coverage | S&E GateEngine over cited facts | 5/9 in-scope real programs UNRESOLVED; 8/29 out-of-scope UNRESOLVED; indication FAIL never possible | Real assessment (same-author reference) | PARTIAL | Close unknowns in-tool (dim 5) |
| 4 | Source traceability | Row/column claims; agent citations with spans; field provenance in the real builder | Field provenance is not imported into DealScreen; it lives in a side file | Provenance completeness test | PARTIAL | Carry citations on analyst facts |
| 5 | Resolving UNKNOWN decisions | Confirm/reject claims; confirm agent findings | 38/39 real open gates have no in-tool path | `results/manual_actions.json` | NOT DEMONSTRATED | **Analyst fact entry with citation (Cycle 1)** |
| 6 | AI diligence usefulness | Offline library + public CT.gov provider; proposals only | Narrow pattern extraction; misses approval statements; 1 useful real finding | Real run | PARTIAL | Approval/status extraction |
| 7 | Ownership, rights, licensing | Rights status from vendor text; silence = UNKNOWN | No rights-holder concept; U.S. label not used; all 40 real UNKNOWN | Real run | NOT DEMONSTRATED | Rights-holder vs availability model |
| 8 | Buyer strategy and capability | BuyerProblemV2 hard gates; capability modalities as a preference | Capability constraints untested on real data | Synthetic only | PARTIAL | Later |
| 9 | Ranking | Declared lexicographic preferences within a disposition | No evidence-strength or rights component | Tests | PARTIAL | Not the bottleneck |
| 10 | Review and approval | Hash-chained log; HUMAN / SYNTHETIC / AI_PREPARED kinds; limits | No real human has used it; no UI beyond CLI and Excel | Tests | PARTIAL | Gate H needs a person |
| 11 | Financial readiness and correctness | Readiness checklist; scenario-order check; reconciliation tests; deal prototype | No stage check: marketed products could be valued pre-approval; deal CLI awaits Lane 1 sign-off | Audit + tests | PARTIAL | Block commercial-stage pre-approval valuation |
| 12 | Excel and report quality | 8-sheet companion workbook, memo, honest labels | Not reviewed by a user | Generated files | PARTIAL | User feedback |
| 13 | Performance and reliability | Synthetic demo 66 s, real import/screen ~50 s each | ~30 s and 1.7 GB per CLI call from ontology loads | Timed runs | PARTIAL | Cache or optional ontology |
| 14 | Security, licensing, integration | License metadata required in profile; public-only data | No security review; no licensed connector | — | NOT DEMONSTRATED | Blocked on approvals |
| 15 | Real-world validation | Real public landscape, same-author reference | No human user; no independent reference | — | NOT DEMONSTRATED | External dependency |


## Scorecard after Cycles 1-2 (2026-10-28)

Only the dimensions that changed are listed. Everything else is as in Audit 0.

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 2 | Identity reconciliation | Cross-holder same-molecule pairs flagged (review only); MB-102 class still isolated | Real: 2 batoclimab licensee/code pairs flagged; tests I1-I3 | PARTIAL (merges still cannot be applied) |
| 3 | Screening accuracy and coverage | With 9 cited actions, in-scope resolved 4/9 → 7/9, 0 wrong | `cycle1/assessment_after.json` (same-author reference; simulated analyst) | PARTIAL |
| 4 | Source traceability | Analyst assertions carry URL, title, date and verbatim quote, and are listed with their gate effects | Tests C4, C7 | PARTIAL → stronger |
| 5 | Resolving UNKNOWN decisions | In-tool path for 39/39 open gates; retract restores the screen byte-for-byte; every gate change disclosed | Tests C1-C7 + 9 review regressions; real run | **DEMONSTRATED (technically; no human has used it)** |
| 7 | Ownership, rights, licensing | Rights assertions need a quote stating the status; AVAILABLE + partnership → CONFLICTING even when confirmed (bug fixed) | Tests | NOT DEMONSTRATED (no real rights data) |
| 11 | Financial readiness and correctness | Commercial-stage programs blocked from pre-approval rNPV | Real: nipocalimab blocked; tests V1-V2 | PARTIAL → stronger |

**Gate status:**
- **Gate C:** technically demonstrated. Supported unknowns are resolved in-tool with evidence preserved and decisions recalculated. It is **not** demonstrated with a human, and analyst time is unmeasured.
- **All other gates:** unchanged.

**After Cycle 3:**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 7 | Ownership, rights, licensing | U.S. rights holder kept separate from availability. Holder taken only from cited evidence (FDA labeler, or an assertion); conflicts shown | Real: holder known for 8/40, AVAILABLE 0/40; tests R1-R5 | PARTIAL (no availability data; no licensor/licensee extraction) |

- **Gate D:** PARTIAL. Suitability, marketing status, holder, encumbrances and unknown availability are now distinct fields. Actual licensing availability has never been demonstrated, because no public source in hand states it.

**After Cycle 4:**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 13 | Performance and reliability | Ontology loaded once at import; screens run from a target cache, and fall back to the full path when a decision introduces an uncached target or the ontology changed | CLI screen 33.5 s / 1.7 GB → 0.53 s / 88 MB; byte equality on 4 workspaces | PARTIAL → stronger (import still ~25-50 s) |

**After Cycle 5 (and the review fixes):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 1 | Landscape ingestion and integrity | Re-import is a refresh: previous import archived; diff of assets and values with source and date; decisions checked | Tests F1-F5 + 6 review regressions | PARTIAL → stronger (no vendor-style refresh tested on real data) |
| 10 | Review and approval | Decisions survive reordered refreshes; changed-value decisions orphaned and reported, never transferred; decided assets with changed content flagged | Reproduced regression now passes | PARTIAL |
| 7 | Ownership, rights, licensing | Holder wording corrected to "U.S. labeler per FDA label; not a rights statement" | Review M1 | PARTIAL |

- **Gate I:** PARTIAL. Refresh comparison works on reordered and edited public exports. It has not been tested with a real vendor export.

**After analyst-simulation cycle A1 (AI-SIMULATED analyst; 2026-10-28):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 3 | Screening accuracy and coverage | Qualified indication names read (disclosed) as NCIt parent; vendor area label alone can no longer exclude | Real: in-scope ELIGIBLE 4/9 → 6/9, 0 wrong (same-author reference); held-out 75k condition strings: 1 reading, correct | PARTIAL → stronger |
| 9 | Ranking | Negated activity no longer ACTIVE; MARKETED separate | Real: 5 false ACTIVE → 0 | PARTIAL (terminated programs still not demoted) |
| 11 | Financial readiness and correctness | Deal CLI refuses unread keys; prints discount rate used and perspective; `value` no longer crashes | Tests; analyst config reproduced | PARTIAL |
| 12 | Excel and report quality | No "approved" for AI candidates; labeler wording; identity flags in memo; why no valuation ran | Simulated analyst + critic | PARTIAL (no human reader) |

Gates H and B are unchanged: an AI-simulated analyst is not a human user or an independent curator.

**After analyst-simulation cycles A2-A3 (AI-SIMULATED; 2026-10-28):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 2 | Identity reconciliation | Closed resolution vocabulary; human SAME_MOLECULE groups counted in memo ("at most N"); never merged | Tests; A2 analyst | PARTIAL → stronger |
| 3 | Screening accuracy | Combination products no longer pass on one vendor modality | Held-out C5 buyer: 1 wrong eligibility → 0 | PARTIAL → stronger |
| 5 | Resolving UNKNOWN decisions | AI assistant can propose cited facts; a different human confirms; content hash-pinned | A2 analyst recorded 4 proposals | DEMONSTRATED technically (no human confirmation yet) |
| 11 | Financial readiness | `value-config` preview makes the exact handoff config reproducible without approval | Test; A2 finding #3 | PARTIAL |
| 12 | Excel and report quality | Rank reasons column; identity groups; activity notes | A2 analyst | PARTIAL (no human reader) |

**After cycle R1 revision 4 (AI-SIMULATED; 2026-10-31):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 4 | Source traceability | Rights events keep file hash, row, URL, quote, dates with precision; every rights call cites them (JSON, workbook, memo) | `research/dealscreen_rights_v1/`; tests | PARTIAL → stronger |
| 7 | Ownership, rights, licensing | Deals/rights export imported through a profile; a rights ledger per program and buyer territory (licenses, options, exercises, lapses, terminations, returns, acquisitions, sublicenses, co-development, availability statements); no OPEN tier; a top tier only when the evidence is complete, specific, current and uncontested | CLDN18.2: false unobstructed 4 → 0; 3 adversarial reviews; 122 held-out tests; reviewers' flagged held-out top-tier placements 12 → 0 (revision 4, implementer-measured) | NOT DEMONSTRATED → PARTIAL (recall capped by the imported file; no real vendor export) |
| 9 | Ranking | Transaction rank uses evidence-based tiers and buyer-declared preferences, separate from the scientific rank | CLDN18.2 outputs | PARTIAL |
| 12 | Excel and report quality | Rights evidence, stale flags and diligence questions in the Screening sheet and the memo, in words | regenerated outputs | PARTIAL (no human reader) |

**After cycle R1 revision 5 (AI-SIMULATED; 2026-11-01):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 7 | Ownership, rights, licensing | One fail-closed top-tier gate on the rights-file and field paths: ended grants checked beside a statement, the position must rest on the landscape company, every U.S.-rights statement and holder read by a strict reader, rights rows not applied guard the programs they may concern | 141 more held-out tests (653 in all); round-4 reviewer's flagged top-tier placements 13 → 0 (implementer-measured); CLDN18.2 calls unchanged | PARTIAL (unchanged: recall capped by the imported file; no real vendor export) |
| 12 | Excel and report quality | Memo rights summary computed and in words; rows not applied listed with their parties; the "also exists" line counts the reasons it omits | regenerated outputs | PARTIAL (no human reader) |

Gates H, B and I are unchanged.

**After cycle R1 revision 6 (AI-SIMULATED; 2026-11-01):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 7 | Ownership, rights, licensing | The top-tier gate's default inverted: beside a clear position a rights text passes only as a plain form; Partnerships, Geographic Notes and notes in party and company names are read; status-flag endings and undated acquisitions no longer clear a grant; the field path applies only to a U.S.-only buyer territory | 90 more held-out tests (743 in all); round-5 reviewer's flagged top-tier placements 18 → 0 (implementer-measured); CLDN18.2 calls unchanged | PARTIAL (unchanged: recall capped by the imported file; no real vendor export) |
| 12 | Excel and report quality | The memo's availability sentence no longer describes checks as proof; assertions listed with their fields; a program's own rejected rights row shown in its line; `assert` says whether the gate accepts a text | regenerated outputs | PARTIAL (no human reader) |

Gates H, B and I are unchanged.

**After cycle R1 revision 7 (AI-SIMULATED; 2026-11-01):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 7 | Ownership, rights, licensing | The plain forms read places as written and in the buyer's territory, refuse notes and cross-clause pronouns, and never accept what the reader cannot read; ownership words and rights rows' quotes are read; the U.S.-rights field is read for any buyer territory containing the U.S. | 72 more held-out tests (816 in all); round-6 reviewer's end-to-end top-tier placements 12 → 0 (implementer-measured); CLDN18.2 calls unchanged | PARTIAL (unchanged: recall capped by the imported file; no real vendor export; revision 7 not reviewed) |
| 12 | Excel and report quality | Memo says which inputs were read; names-only Partnerships assertions not listed as read; `assert` gives the gate's verdict for the buyer territory | regenerated outputs | PARTIAL (no human reader) |

Gates H, B and I are unchanged.

**After cycle R1 revision 8 (AI-SIMULATED; 2026-11-01):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 7 | Ownership, rights, licensing | The "other places" form accepts only a name as the party; quotes keep conditions before a colon and are read for options and wider territories; offers must cover the buyer territory; year- or month-dated endings that contain the as-of date are not applied | 60 more held-out tests (876 in all); round-7 reviewer's end-to-end top-tier placements 6 → 0 (implementer-measured); CLDN18.2 calls unchanged | PARTIAL (recall capped by the imported file; no real vendor export; revision 8 not reviewed) |

Gates H, B and I are unchanged.

**After cycle R1 revision 18 (AI-SIMULATED; 2026-11-11):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 7 | Ownership, rights, licensing | An ending or lapse quote dated before the deal it ends blocks; the use check runs after a closed description and on lapses; cuts closed by a mark or at the start, unpaired marks, unspaced dashes and "~" before a date block; "R&D" is read | REREVIEW16's ws_r 7 → 0 top-tier programs; p17 50 → 10 of 76 and p17b 21 → 6 of 32 (controls, by-design, judgement and two usefulness rows remain); CLDN18.2 transaction CSV, memo and screening byte-identical; 15 of 17 real quotes still need an analyst confirmation | not reviewed |
| 5 | Resolving UNKNOWN decisions (U1 revision 12) | An ordinary modifier no longer reads an unrelated disease (counted from NCIt's own labels); a trailing stage pair keeps the name; lineage words are not sites; a label two codes share shows both codes | REVIEW11's Q1-Q7 rows give the expected reading in three letter cases; a 250-label sweep reads "L, stage III or IV" as requested for 250 of 250; CLDN18.2 screening byte-identical | not reviewed |

Gates H, B and I are unchanged.

**After cycle R1 revision 17 (AI-SIMULATED; 2026-11-11):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 7 | Ownership, rights, licensing | One use check on retentions, terminations and returns; a cut quote or an unread mark blocks; a bare "<place> rights" states nothing; "~" before an amount is read | REREVIEW15's ws_q 5 → 0 top-tier programs; p16 31 → 16 of 67 (controls, by-design and judgement rows remain); CLDN18.2 transaction CSV byte-identical; 15 of 17 real quotes still need an analyst confirmation | not reviewed |
| 5 | Resolving UNKNOWN decisions (U1 revision 11) | Letter case no longer decides what U1 reads: a capitals list keeps its unread pieces, acronyms and synonyms are read in any case, adjectives are refused in any case; a borrowed ending keeps its site; inverted numbered lists keep their word | REVIEW10's P1-P8 rows give the expected reading in lower, mixed and upper case; CLDN18.2 class counts unchanged | not reviewed |

Gates H, B and I are unchanged.

**After cycle R1 revision 16 (AI-SIMULATED; 2026-11-10):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 7 | Ownership, rights, licensing | A quote with an omission or reference mark blocks; a quote must state a grant, a placed retention or an ending; a retention for one use blocks with or without a comma; "Upon the termination" is no ending; the word after a dateline date opens the sentence | REREVIEW14's ws_p 7 → 0 top-tier programs; CLDN18.2 transaction CSV byte-identical; realistic sentences 9 → 12 of 16; 15 of 17 real quotes still need an analyst confirmation | not reviewed |
| 5 | Resolving UNKNOWN decisions (U1 revision 10) | Any leading modifier is tried with the next name's head; an adjective is never read alone as another concept; a number keeps its word; a population keeps its concept; capitals cells the gate reads use the gate's reading | REVIEW9's N1-N5 rows give the expected reading end to end; CLDN18.2 class counts unchanged | not reviewed |

Gates H, B and I are unchanged.

**After cycle R1 revision 15 (AI-SIMULATED; 2026-11-08):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 7 | Ownership, rights, licensing | A retention names one place and keeps plain rights; a quote with "[...]" blocks; a dateline's date is read; a quote of payments alone blocks | REREVIEW13's ws_o 5 → 0 top-tier programs; CLDN18.2 outputs byte-identical; 15 of 17 real quotes still need an analyst confirmation | not reviewed |
| 5 | Resolving UNKNOWN decisions (U1 revision 9) | "Chronic or acute X" reads both concepts; basket pieces are baskets; capitals, populations and inverted names are read | REVIEW8's D1-D5 rows give the expected class end to end; CLDN18.2 screening byte-identical | not reviewed |

Gates H, B and I are unchanged.

**After cycle R1 revision 14 (AI-SIMULATED; 2026-11-08):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 7 | Ownership, rights, licensing | A "retains rights" sentence counts only for the program's company and only where its places include the buyer territory; multi-word dateline cities must be listed; signing sentences need a place; rival acquirers are grouped as succession is; a subsidiary clause is kept unless the parent is the company; payment sentences pass; the agent-shell refusal is in `DecisionLog.record` for every caller, and a withdrawal removes every version of a row's confirmation | 1,803 tests; round-13 probes 27 → 11 of 41 and 11 → 2 of 13 top tier (the rest controls, clean datelines or listed judgement rows); end-to-end ws_n 7 → 0 (implementer-measured); CLDN18.2 outputs byte-identical; read directly, 15 of 17 real quotes block before confirmation; 8/6/1 vs general Claude 14/1/0 | Not reviewed; usefulness depends on analyst confirmations; DealScreen cannot verify that a HUMAN record was made by a person |
| 5 | Resolving UNKNOWN decisions (U1 revision 8) | The record's own "or" list is read on every path; modifier and stage pieces are never looked up alone; a list naming the request is never unreadable; "absent" after another target no longer negates the required one | CLDN18.2 38/38, held-out 104/104, 0/62 and 0/312 science changes; one CLDN18.2 sentence now names both requested readings | U1-7 open (revision 8 not reviewed) |

Gates H, B and I are unchanged.

**After cycle R1 revision 13 (AI-SIMULATED; 2026-11-08):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 7 | Ownership, rights, licensing | The fixed sentences are the only reader of a rights row's quote (no plain-form shortcut; the grantor-retains sentence only); every character is read; a dateline must be a one-line city with region parts that are places; grants, options and exercises name a place unless the row covers the buyer territory; field words carrying a condition or a holder never describe the program; only a license ends a license; `CONFIRM_RIGHTS_ROW` needs an explicit HUMAN kind, is refused in a known AI agent's shell and survives a re-import of the unchanged row | 1,726 tests; every round-12 attack blocks; end-to-end ws_m 7 → 0 (implementer-measured); CLDN18.2 outputs byte-identical; read directly, 15 of 17 real quotes block before confirmation; 8/6/1 vs general Claude 14/1/0 | Not reviewed; usefulness depends on analyst confirmations; DealScreen cannot verify that a HUMAN record was made by a person |

Gates H, B and I are unchanged.

**After cycle R1 revision 12 (AI-SIMULATED; 2026-11-02):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 7 | Ownership, rights, licensing | A rights row's quote restates its row only as one of 34 fixed sentences for its type (own parties in their roles, the program, the type's verb with no modal, condition or sale, a place inside the row, a dated period by the as-of date); anything else blocks until a human analyst records a hash-bound `CONFIRM_RIGHTS_ROW`. One legal entity per acquired party; two acquirers are contested | 1,575 tests; round-11 reviewer's probes 67 → 5 of 75 top-tier (all controls) and end-to-end ws_l 7 → 0 (implementer-measured); CLDN18.2 science and positions unchanged; read directly, 16 of 17 real quotes block before confirmation; 8/6/1 vs general Claude 14/1/0 | Not reviewed; usefulness depends on analyst confirmations |

Gates H, B and I are unchanged.

**After cycle R1 revision 11 (AI-SIMULATED; 2026-11-02):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 7 | Ownership, rights, licensing | Every word of every rights row's quote is read against a per-type allow-list plus the program's own record words; every applied row is read beside a clear position; dates are compared with the as-of date; a future option exercise blocks; an affiliate or the company's own purchase is not "owner acquired" | 1,436 tests; round-10 reviewer's end-to-end top-tier placements 7 → 0 and attack probes 79 → 0 (implementer-measured); CLDN18.2 science unchanged, 2 transaction views move to "rows not applied" with no tier change; read directly, 13 of 17 real quotes block | PARTIAL (recall capped by the imported file; no real vendor export; strict reader holds back most real wording; revision 11 not reviewed) |

Gates H, B and I are unchanged.

**After cycle R1 revision 10 (AI-SIMULATED; 2026-11-02):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 7 | Ownership, rights, licensing | The quote reader fails closed: a cited quote passes only when every name in it is placed and every rights word restates its row. Time and hedge words block endings; wide words and states or provinces block rows that do not cover the buyer territory. Future-dated grants block unless reported after the as-of date; an acquisition of a party in no grant blocks | 122 more held-out tests (1,300 in all); round-9 reviewer's end-to-end top-tier placements 7 → 0 (implementer-measured); CLDN18.2 calls unchanged; 1 of 17 real quotes blocks (misleading: counts only rows that reach the reader; see revision 11) | PARTIAL (recall capped by the imported file; no real vendor export; revision 10 not reviewed) |

Gates H, B and I are unchanged.

**After cycle R1 revision 9 (AI-SIMULATED; 2026-11-02):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 7 | Ownership, rights, licensing | Every cited quote is read, whatever the row's territory. Another company named in a clause blocks, as do a partial or conditional ending and an unknown place before "rights". Party names are checked in any letter case. Grants reported before the as-of date but effective after it block, and so do availability statements dated only to the as-of period. Ordinary press words in quotes no longer block | 79 more held-out tests (1,178 in all); round-8 reviewer's end-to-end top-tier placements 7 → 0 (implementer-measured); CLDN18.2 calls unchanged; 1 of 17 real quotes blocks (misleading: counts only rows that reach the reader; see revision 11) | PARTIAL (recall capped by the imported file; no real vendor export; revision 9 not reviewed) |

Gates H, B and I are unchanged.

**After cycle U1 revision 3 (AI-SIMULATED; 2026-11-01):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 5 | Resolving UNKNOWN decisions | Every UNKNOWN gate on a program that is not excluded carries a diagnostic: what the record holds, as written (a class from the NCIt authority, the target and modality readers and the buyer's requirement), and the one cited fact that would decide the gate. Never changes a gate | CLDN18.2 38/38 (baseline 0/38); held-out 104/104; 0/62 and 0/312 science changes; `research/dealscreen_unknown_actions_v1/MEASUREMENT.md` | PARTIAL (U1-7 adversarial review of revision 3 not done; no human reader) |
| 12 | Excel and report quality | Diligence sheet gives the DealScreen action beside the S&E text; Screening sheet gives the class per open gate and per name; the memo lists single-gate programs by gate and record class, with no class hidden | regenerated outputs (`after/`) | PARTIAL (no human reader) |

Gates H, B and I are unchanged.
