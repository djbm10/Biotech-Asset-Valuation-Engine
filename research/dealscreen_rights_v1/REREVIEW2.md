# Adversarial re-review 2: cycle R1 revision 3, rights evidence (CLDN18.2)

**AI-SIMULATED INTERNAL REVIEW.** I am an AI (Claude) playing a skeptical pharma BD analyst and auditor. I am not a
human reviewer. I approve nothing, and nothing here is validation. I did not trust REREVIEW_RESPONSE.md. I re-checked
each claim by running code or reading the outputs.

Scope and method:
- Revision 3 is the uncommitted working tree on `dealscreen-mvp` after e805f0b. Snapshot taken 2026-10-30 12:43 EDT;
  hashes in `/tmp/claude-1000/rr3/snapshot/SHA256SUMS`. At the end of the review all 11 `src/bve/dealscreen` files
  still matched those hashes. One test was added during the review
  (`test_e2_an_analyst_rights_assertion_against_the_rights_file_is_a_conflict`, field `us_rights` only). No `src/`
  file changed.
- I edited nothing except this file. Scripts, workspace copies and outputs are in `/tmp/claude-1000/rr3/`.
- Ledger cases: `adv_top.py`, `adv_ledger.py`, `adv_order.py`, `adv_coarse.py`, `adv_field.py` (helper `h.py`).
  The first three also ran on the revision-2 snapshot (`RR_VERSION=v2`, `/tmp/claude-1000/rr2/snapshot`), to tell new
  errors from old ones. Outputs: `*.v3.out`, `*.v2.out`. Defaults: buyer territory {US}, as-of 2025-06-01, max age 730
  days, `encumbered_rights: deprioritize`, licensor "Origin Bio" unless stated. All parties are fictional.
- End-to-end runs: copies of the CLDN18.2 workspace (C3 buyer, as-of 2026-10-29), with fictional rows appended to the
  rights file (`ws_a`, `ws_b`, `ws_d`) or analyst assertions (`ws_b`, `ws_c`), then `import-rights`, `screen`,
  `export` and `memo`. Outputs in `out_a/`, `out_c/`, `out_d/`.
- The previous reviewer's `adv2.py`–`adv5.py` were re-run unchanged (`prev/*.v3.out`).
- Checks: `tests/dealscreen` 443 passed (53 collected in `test_rights_rereview.py`). `ruff check src/bve/dealscreen
  tests/dealscreen` is clean. Every definite finding in §2 and §3 fails on this tree, so no passing test asserts its
  expected value.

## Summary

- **CLDN18.2: no tier and no call changed.** Revision 3 now cites FL-301's acquisition row and asks whether
  LM-302's 2022 license is still in force. Error counts against the reference are unchanged. Usefulness against
  general Claude (B) is unchanged: 10 right, 4 partial, 1 missed, versus B's 14, 1, 0.
- 22 of the 23 exact inputs in REREVIEW.md now give the expected answer. K6 is half fixed. B1 is fixed end to end.
- **Revision 3's own new rules open new paths into tier 1**: a grant that names no licensee (N1), an acquisition
  limited to another territory (N3a), and an option dated only by its report (R1). Close variants of six claimed fixes
  still reach tier 0 or 1 (E2, E3, F1, A1–A3, S1, K6).
- Net: a small audit gain on CLDN18.2. No robustness gain on held-out inputs: the false-clearance risk moved; it
  did not close.

Definite new errors (not reported in REREVIEW.md). None of them occurs in the CLDN18.2 output.

| Severity | Introduced by revision 3 | Claimed fixed, fails on a close variant | Older, first reported here | Total |
|---|---|---|---|---|
| High: reaches tier 0 or 1 while a third party may hold U.S. rights, or on contrary, undated or stale evidence | 3: N1, N3a, R1 | 6: E2-holder, E3-ids, F1-analyst, N6, N7b/c, N8 | 2: N2 (with H1, a new route in rev 3), N7a | **11** |
| Medium: false encumbrance or wrong owner that changes the tier | 1: P1 | 0 | 2: N3b, negated words | **3** |
| Low: false label, flag or wording; no tier change | 4: W1, N7e, NA-label, H6 wording | 0 | 5: memo "no effect", originator note, H5, H3/N7c wording, N10 | **9** |

## 1. REREVIEW_RESPONSE.md, claim by claim

| § | Claim | Verdict | Evidence (run or read) |
|---|---|---|---|
| 1 #1 | Weak inputs fixed in the ledger and guarded (D1, D2, U1, U2, A1, A2, A3) | **Held for the exact inputs. Refuted as a general guard.** | D1–D3 LICENSED; U1, U1b, U3 LICENSED with a question; U2 OPTION_HELD; A1, A1b, A2, A2b not counted; A3 RETURNED. But an undated statement still counts when any other statement is fresh (N6). New rules create N1, N3a and R1. |
| 1 | "The promotion guard is `CLEAR_POSITIONS` plus the checks above" | **Refuted** | The transaction view checks only `guard or pos.stale` (`transaction.py:204-208`). It does not see unmatched exercises (N2), grants with no licensee (N1), acquisition scope (N3a), the analyst holder (E2-holder), unlinked ids (E3-ids) or analyst text (F1-analyst). |
| 1 #2 | B1 fixed at three levels | **Held** | `[USA]`, `[U.S.]`, `[usa]`, `[UNITED STATES]` → "unknown territory code 'USA'; use one of ['CA', 'CN', 'EU', 'HK', 'JP', 'KR', 'MO', 'ROW', 'TW', 'UK', 'US'] (for example US, not USA)". `[us ]` → `['US']`. `rights_position(territory={'USA'})` → "buyer territory must be region codes from [...]; got ['USA']". |
| 1 #3 | E2 fixed | **Held for `us_rights`. Refuted for `us_rights_holder`.** | The new test and my ws_b JS107 run give CONFLICTING. A dated analyst `us_rights_holder = "BigPharma Inc."` leaves QLS31905 at tier 1, #1 (§2b E2-holder). |
| 1 #3 | E3 fixed | **Held for rows that carry a program id. Refuted otherwise.** | ws_d QLS31905 (row 19, "Q3 2026") and BL-M05D1 (row 25, unknown label) → RIGHTS_UNRESOLVED, row named. A row with no program id, or id `cl-24` for `CL-24`, leaves its program in tier 1 (§2b E3-ids). |
| 1 #4 | F1 fixed | **Held for the plain landscape cell. Refuted for analyst text.** | Field: "Not currently available", "Rights no longer available", "Never available", "Unavailable" → `NOT_AVAILABLE_PER_SOURCE`; "available only in China", "Available outside the U.S.", "Available except in the U.S." → `UNKNOWN`; plain "Rights available" not counted. Analyst: "Available for licensing: no" → tier 0 (§2b F1-analyst). New label: NOT_AVAILABLE shows as "licensed" (§3). |
| 1 #5 | Acquisitions and exercises cited; count for staleness | **Held, with a side effect** | FL-301 cites rows 16 and 17 in the JSON, the workbook ("rights row 17; undated (source 2023-01); acquisition; Leap Therapeutics acquired Flame Biosciences; ... event rx:328b9bee:17") and the memo ("[rights rows 16, 17]"). G5, M1, M3, K5 pass. Side effect: an unrelated later acquisition now makes old evidence look current (N7b/c, N7e). |
| 1 #6 | G4, G3, G2 fixed | **Held for the inputs. The G4 rule creates new errors.** | G4 OWNER_ACQUIRED; G3 head licensee named, DEPRIORITIZED; G2 BigPharma named with a question. The same `merge_internal` fires when a grant names no licensee (N1) and ignores an acquisition's territory (N3a). |
| 1 #7 | Output gaps fixed | **Mostly held** | See the §3 rows of this table and §4. |
| 1 #8 | K1/K2 read as RETURNED; D5/D6 follow their grant | **Held** | K1, K2 RETURNED with the missing-grant question; D5 RETURNED; D6 NOT_ENCUMBERED. But "option outcomes follow by definition" also creates R1, and the return-only reading puts scope-unknown endings in tier 1 (N4, judgement). |
| 1 #9 | LM-302 and recall not fixed | **Held (acknowledged)** | LM-302 CONFLICTING; SKB315 NO_RIGHTS_EVIDENCE. |
| 2 | D4 → CONFLICTING | **Held** | "may predate the grant to Alpha Bio (reported 2025-03): the dates cannot order them". The rule is not applied to options (R1). |
| 2 | S1 → RIGHTS_UNRESOLVED for every clear position | **Held for its input. Bypassed.** | S1, D7 and N7d go to RIGHTS_UNRESOLVED. Add a 2025 acquisition row and a 2014 return is tier 1 with stale=False (N7b/c). |
| 2 | S2 → CONFLICTING, old license named | **Held** | "the newest evidence for the license to Alpha Bio is dated 2016-01-01, more than 730 days before 2025-06-01; it may have ended since". W3 and W6 also right. Side effect: W1 (§3). |
| 2 | G1 → CONFLICTING | **Held** | |
| 2 | K6: both partners named, no owner invented | **Wording held. Tier not addressed.** | "co-development between Alpha Bio and Beta Bio ended in US per source", "owner not established". Still tier 1 (§2b N8). |
| 3 | Quotes clipped with an ellipsis | **Held** | Memo quotes end "…" at 200 characters. Workbook quotes stop at 1,000 with "…" (largest cell 1,440). IBI343's quote now ends "...worldwide outside of Greater China." |
| 3 | Workbook lines give row and event id; memo gives row and quote | **Held** | "rights row 16; ... event rx:328b9bee:16". The memo cites rights rows, not event ids. |
| 3 | Words, not codes, in memo prose | **Mostly held** | Two reason templates still print codes: "landscape U.S.-rights field reads AVAILABLE_ANALYST_CONFIRMED (no rights record)" (`transaction.py:134`) and "reads ENCUMBERED (source-provided)" (`screening.py:283`). |
| 3 | "Also exists" line gives position words, stale flag and rows | **Held as stated** | Memo line 31. It still has no quote, URL, date or reason for its 10 programs (AC10). |
| 3 | Memo line 9 is now enforced | **Refuted** | ws_a: "#1 Spevatamig (PT886): availability stated, unverified" rests on "undated availability statement" (row 24). ws_c: tier 0 rests on an undated and a 2015 analyst assertion. Both memos print "Nothing is shown as available without an explicit, dated statement." |
| 3 | Screening column renamed | **Held** | |
| 3 | `rights_position.py` split | **Held** | 785 lines; `rights_words.py` 74 lines. |
| 4 | 35 reviewer cases meet the expected value; none reaches a top tier the reviewer ruled out | **Held** | Re-ran `adv2.py`–`adv5.py`: every result as listed. K6 is tier 1; the old expectation did not rule that out explicitly. |
| 5 | 2 programs changed; tiers unchanged | **Held** | after_v2 vs after_v3: LM-302 (new reason and question) and FL-301 (rows 16;17). Eight stale programs also change one phrase ("latest supporting evidence" → "latest evidence for this position"). Eligible tiers: rights unresolved 8, deprioritized 6. |
| 5 | Error-class table | **Held** | §5b. |
| 5 | "Re-review findings still failing: 0" | **Held for the exact inputs. Refuted for variants.** | E2-holder, E3-ids, F1-analyst, N6 (A1–A3), N7b/c (S1), N8 (K6). |
| 5 | Usefulness unchanged | **Held** | §5c. |
| 5 | "With a sourced return row SKB315 would now read RETURNED (K1)" | **Held for the position, not the tier** | ws_a, fictional row X11 (BigCo returned worldwide rights, 2024-08-01): "rights returned per evidence (stale evidence)", tier "rights unresolved", #8. 819 days > 730. |
| 6 | Science unchanged, 0 of 62 | **Held** | `compare.py`: baseline vs after_v3 0 of 62; also 0 of 62 for each of my 4 adversarial workspaces (ws_a to ws_d) and a no-rights screen. |
| 6 | Cross-version 0 changes | **Held** | I ran `cross_version.py` on revision 3 and compared with the pre-R1 run built from 0ee7752 (`/tmp/claude-1000/rr2/xv_base`): synthetic_200 192, FcRn v1 40, FcRn v2 40, C5 40 assets; 0 scientific differences. These buyers declare no transaction preferences, so they barely exercise the rights code. |
| 6 | Cycle-4 harness byte-identical | **Held** | I imported the harness's `main()` and ran it into my directory from the repo root: byte_identical and fast_path true on all 4. Note: run from any other directory, the ontology path (`data/se/ontology/current`, `src/bve/se/ontology/targets.py:30`) does not resolve, and the harness still prints byte_identical true (fast_path false). The `research/` result file was not touched. |
| 6 | Tests pass; ruff clean; no `src/` change outside `src/bve/dealscreen` | **Held** | 443 passed; ruff clean; `git status -- src/`. |
| 6 | Full repository suite | **Not reported** | The file still says "FULL_SUITE_RESULT". I did not run the full suite (instructed not to). |
| 6 | Repo-wide ruff: 7,568 findings | **Unverified** | Not run. |

## 2. Paths into the two top tiers

Tier 0 is AVAILABILITY_STATED_UNVERIFIED. Tier 1 is NO_THIRD_PARTY_GRANT_IN_EVIDENCE. "Actual" text is copied from the
`.out` files or the workspace outputs. Line numbers are in `rights_position.py` unless another file is named.

### 2a. Introduced by revision 3 (revision 2 kept these out of tiers 0 and 1). Definite.

| # | Input | Actual | Expected | Cause |
|---|---|---|---|---|
| N1a | Exclusive LICENSE, **Licensee blank**, Licensor Origin Bio, "United States", 2025-01-01 | `position=NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE`. Reason "recorded grants do not cover US; this is not a statement of availability". Question "Who holds US rights (owner not established)? Recorded deals cover other territories only." Rev 2: LICENSED, DEPRIORITIZED. | LICENSED to an undisclosed licensee, or unresolved. Never tier 1. | `:256` uses the licensor as holder when no licensee is named. `merge_internal` (`:353-358`) then sees holder = licensor and ends the grant, with no acquisition. `:653-659` then reports "do not cover". |
| N1b, N1c | The same with an exclusive worldwide OPTION, or a worldwide CO_DEVELOPMENT naming one partner | Same output. Rev 2: OPTION_HELD; SHARED. | OPTION_HELD; SHARED or unresolved | same |
| N1, end to end | ws_a, QLS31905 (CL-20), row X01: `Licensing, Exclusive, [no licensee], Origin Bio, United States, 2026-06-01` | Memo: "#2 QLS31905: no third-party grant in evidence; rights position: no grant over the buyer territory per evidence (recorded grants do not cover US; ...)" above its own evidence "(rights row 18): 2026-06-01 license, - from Origin Bio, United States" | not tier 1 | same |
| N3a | LICENSE Alpha Bio ← Origin Bio, worldwide, 2021-01-01. ACQUISITION Origin Bio ← Alpha Bio, territory **"Greater China"**, 2024-06-01. | `OWNER_ACQUIRED_PER_EVIDENCE tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE`. "Origin Bio acquired Alpha Bio; the grant between Origin Bio and Alpha Bio is now held within one company per source". Rev 2: LICENSED. | Alpha keeps the U.S.: LICENSED | `_acquisitions` (`:193-207`) applies every acquisition to the whole company. Territory and date are ignored (`:204`). `merge_internal` then ends the worldwide grant. |
| N3a, end to end | ws_a, TORL-2-307-ADC (CL-37): X09 license to Alpha, worldwide, 2025-03-01; X10 acquisition, Origin acquires Alpha, "Greater China", 2026-05-01 | "#6 TORL-2-307-ADC: no third-party grant in evidence; rights position: owner acquired per evidence" | not tier 1 | same |
| R1 | OPTION to Alpha, worldwide, **no event date, source date 2024-06**. OPTION_LAPSED naming Alpha, 2023-03-01. | `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE`. "option to Alpha Bio lapsed in US per source; not a statement of availability". Rev 2: OPTION_HELD. | OPTION_HELD or CONFLICTING. The same input with a license gives CONFLICTING (R3), per the D4 rule. | `order()` now puts a report-dated grant at the start of the replay (`:237-240`). Option outcomes "follow" by definition (`:289`), so `_may_follow` is skipped. |
| R1b | Same, the lapse also dated only by its report (2023-03) | same | same | same |

The same ordering also makes R5 (license 2019, termination 2021, re-license reported 2024) say "a termination
(2021-01-01) naming Alpha Bio could apply to 2 grants; none was cleared" and that the 2019 license "may have ended
since". The position is still right. Not counted.

### 2b. Claimed fixed, but a close variant still reaches tier 0 or 1. Definite.

| # | Input | Actual | Expected | Cause |
|---|---|---|---|---|
| E2-holder | ws_b, QLS31905 (CL-20). Rights row Y01: `Licensing, Exclusive, ChinaCo, Origin Bio, mainland China, 2026-02-01`. Analyst assertion `us_rights_holder = "BigPharma Inc."`, URL example.test/assert1, source date 2026-09-01, span "(test) BigPharma Inc. holds U.S. rights". | `QLS31905 transaction_rank=1 tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE position=NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE`. Reason "the landscape also names a U.S. rights holder or labeler: BigPharma Inc.". Question "Who holds US rights (Origin Bio)? Recorded deals cover other territories only." | CONFLICTING: a dated assertion names a third-party U.S. holder | `screening.py:319-322` only appends the holder and a reason. `_reconcile_with_field` (`screening.py:268-285`) reads the `us_rights` status, never the holder. |
| E3-ids (a) | ws_d, JS107 (CL-24). Row Z03, China license to ChinaCo (accepted). Row Z04: `cl-24, Licensing, Exclusive, BigPharma Inc, Origin Bio, United States, 2026-03-01` (accepted; id in lower case). | Import console only: "UNLINKED: rights events for program id 'cl-24' match no landscape program". Screen: `JS107 rank=1 tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE pos=NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE`. Memo and workbook are silent. | not tier 1; the row named in the outputs | Events are keyed by exact `external_id` (`screening.py:304-305, 314`). Only `cli/dealscreen.py:399` reports unlinked ids. |
| E3-ids (b) | ws_d, SKB315 (CL-27). Row Z05, China license (accepted). Row Z06, the same U.S. license to BigPharma Inc, **Program ID blank**. | Import console only: "REJECTED rights row 23: missing external_id". Screen: `SKB315 rank=2 tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE`. Memo and workbook are silent. | Not tier 1 for any program while a row cannot be attributed; the row named in the outputs | `_rejected_rows` drops rows with no id (`screening.py:291`). |
| F1-analyst | ws_c, landscape U.S.-rights cell empty. Analyst `us_rights` assertions: QLS31905 "Available for licensing: no" (2026-09-01); JS107 "Available, but not in the U.S." (source date 2015-01-01); SKB315 "Ex-U.S. rights available" (no source date). | QLS31905 #1, JS107 #2, SKB315 #3, all `AVAILABILITY_STATED_UNVERIFIED`, stale=False, `evidence: []`. Reason "landscape U.S.-rights field reads AVAILABLE_ANALYST_CONFIRMED (no rights record)". Workbook: "AVAILABLE (analyst-asserted or -confirmed from a cited source; verify)". | Not availability: the text says no, excludes the U.S., or is 11 years old or undated | `commercial.py:31-32` catches a negation only before "available"; `:35` catches a restriction only after it; `:128-129` upgrades any AVAILABLE to AVAILABLE_ANALYST_CONFIRMED with no date or territory check. `transaction.py:113-116, 209-210` send it to tier 0. The field path never sets `stale`. |
| F1-analyst (ledger) | `adv_field.py`, analyst path: "China rights available", "Rights outside the United States are available", "Available? No.", "Was available until 2021", "Previously available" | Each: `AVAILABLE_ANALYST_CONFIRMED -> AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED -> AVAILABILITY_STATED_UNVERIFIED` | not availability | same |
| N6a (A1 bypass) | AVAILABILITY_STATED by Origin, **undated**, no territory. A second one for "Europe and Latin America", 2025-03-01. | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED tier=AVAILABILITY_STATED_UNVERIFIED`. Reasons "the statement does not name a territory" and "an availability statement (2025-03-01) naming Origin Bio names a territory that cannot be read (Europe and Latin America); not counted for US". | Not counted. The undated statement alone gives NO_RIGHTS_EVIDENCE (N6d). | `_staleness` accepts the position if any statement in `used` is fresh (`:765-766`). `used` also holds statements that were not counted (`:515`, `:521`) or were superseded (`:613`). |
| N6a, end to end | ws_a, Spevatamig (CL-31): X07 undated "Seeking partner"; X08 "Seeking partner", "Europe and Latin America", 2026-09-01 | "#1 Spevatamig (PT886): availability stated, unverified", evidence "(rights row 24): undated availability statement" | not tier 0 | same |
| N6b (A2 bypass) | Undated statement, plus a 2025-03-01 statement with status COMPLETED | tier 0; "has status completed; not counted" | not counted | same |
| N6c (A3 bypass) | Undated statement; statement 2024-01-01; U.S. license to Alpha 2024-03-01; termination 2025-01-01 | tier 0; "an availability statement (2024-01-01) naming Origin Bio was followed by a grant over US; superseded" | RETURNED (the A3 rule) | same |
| N7b, N7c (S1 bypass) | LICENSE Alpha ← Origin, worldwide, 2012-01-01; RIGHTS_RETURNED 2014-01-01; ACQUISITION 2025-01-01: Gamma acquires Origin (N7b) or Alpha (N7c) | `RIGHTS_RETURNED_PER_EVIDENCE tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE ... stale=False`. Without the acquisition (N7d): stale, RIGHTS_UNRESOLVED. Rev 2 at least flagged N7b stale. | stale; RIGHTS_UNRESOLVED | `grant_events` adds the acquisition chains of both parties (`:231-232`). `_cleared` makes them decisive (`:576`). `_staleness` takes the newest decisive date (`:771-775`). |
| N8 (K6, half fixed) | (a) CO_DEVELOPMENT Alpha + Beta, worldwide, 2024-01-01; TERMINATION naming Beta, 2025-01-01. (b) Co-development Alpha with Origin; termination naming Origin. | `RIGHTS_RETURNED_PER_EVIDENCE tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder=None owner=None`. "co-development between Alpha Bio and Beta Bio ended in US per source"; "Who holds the returned US rights now (owner not established)". End to end: ws_a BL-M05D1 #5. | Not tier 1. The partner that did not terminate may hold all rights (REREVIEW K6: "A may hold the rights"). | `_match` matches either partner of a shared grant (`:268`). `_apply` clears the whole grant (`:325-329`). |

### 2c. Older paths, first reported here. Definite.

| # | Input | Actual | Expected | Cause |
|---|---|---|---|---|
| N2a | LICENSE Alpha, mainland China, 2024-01-01. OPTION_EXERCISED by Beta Pharma, "United States", 2025-02-01. No option row. | `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE`. Reasons "recorded grants do not cover US; ..." and "an option exercise (2025-02-01) naming Beta Pharma matches no recorded grant". End to end: ws_a ATG-022 #3. | Beta holds a U.S. license per evidence: LICENSED or CONFLICTING | An unmatched outcome forces a conflict only when a grant already blocks the territory (`:614`). |
| N2b | Availability statement 2024-06-01, then the same exercise 2025-02-01 | tier 0 | not tier 0 | same |
| H1 (new route) | TERMINATION only (Alpha, Origin, no territory, 2024-06-01), then the same exercise by Beta, 2025-02-01 | `RIGHTS_RETURNED_PER_EVIDENCE tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE`. Rev 2: NO_RIGHTS_EVIDENCE. | not tier 1 | `_return_only` (`:543-569`) reads endings only. |
| N7a | AVAILABILITY_STATED, worldwide, event date 2015-03-01, source date 2025-03-01 | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED tier=AVAILABILITY_STATED_UNVERIFIED ... stale=False` | The statement is from 2015: stale, not counted (AC7) | `evidence_date` prefers the source date (`rights.py:179-181`). |
| N10 (low) | U.S. LICENSE 2023-01-01; TERMINATION 2026-01-15; as-of 2025-06-01 | `RIGHTS_RETURNED_PER_EVIDENCE tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE` | LICENSED as of 2025-06-01 | The replay has no as-of cut (`:236-249`). Matters only for back-dated analyses. |

### 2d. Judgement calls (top tier; I dispute them, but they are not definite errors)

| # | Input | Actual | My view | Cause |
|---|---|---|---|---|
| N4a (the REREVIEW K2 shape) | TERMINATION only, Delta Bio / Origin Bio, no territory, 2025-01-01 | RETURNED, tier 1. Question "Which territories did the deal with Delta Bio cover, and does Origin Bio hold the US rights now? The original grant is not in the evidence." End to end: ws_a JS107 #4. Rev 2: NO_RIGHTS_EVIDENCE. | RETURNED is right. Tier 1 is doubtful: the position's own question says the deciding fact is unknown. The previous reviewer's K2 expectation ("RIGHTS_RETURNED or CONFLICTING") allows it. | `_return_only` (`:547, 562-565`) |
| N4b, N4c | The same naming only the licensor ("a licensee not named"), or only the licensee ("the owner (not named)", owner None) | RETURNED, tier 1 | weaker still | same |
| N4d | RIGHTS_RETURNED: Delta Bio → Kappa Pharma, "United States" | tier 1, owner "Kappa Pharma" | Kappa may be a head licensee, not the owner. The landscape company is not compared. | `:567` sets owner = recipient |
| N4f, N5a, N5c, N9a, N9b | Undated endings or grants: undated worldwide termination only; undated license + undated termination; undated option + lapse; license 2024-03 + undated termination; undated license + termination 2025-01 | RETURNED or NOT_ENCUMBERED, tier 1, stale=False | Age unknown. S1 refuses a 2015 return but accepts one of unknown age. Undated statements are refused (N6d). | `_staleness` ignores undated events (`:771`) |
| N5b | Undated China-only license | tier 1 | age unknown | same |
| N3c | ACQUISITION only: Gamma acquires Origin, 2025 | OWNER_ACQUIRED, tier 1 | An M&A record says nothing about licenses | `:645-652` |
| N9c | U.S. license to Alpha 2024-03; termination naming only the licensor, 2025-01 | RETURNED, tier 1 | Which deal did Origin end? | `_match` by licensor (`:269-270`) |
| H7 | License to "Alpha Bio Holdings"; Origin acquires "Alpha Bio Inc" | OWNER_ACQUIRED, tier 1 | `party_key` strips "Holdings": one company | `party_key` |
| N1d | Intra-group license, Origin Bio Ltd → Origin Bio Inc, "United States" | tier 1, "recorded grants do not cover US" | The tier is defensible. The reason is false. | N1 cause |
| N11 | Return in 2010; `as_of=None` (direct caller) | tier 1, no staleness | The buyer spec requires `as_of_date`; low | `:772` |

Accepted top-tier results, not errors: K1 (worldwide return), K3, K4, A3, D5, D6, G4, M1, R6, R7, R8, C2, C4, C5, H2,
H3, H4, H6.

## 3. False encumbrance, wrong holder or owner, and labels (no top-tier effect)

| # | Input | Actual | Expected | Cause | Severity |
|---|---|---|---|---|---|
| P1 (introduced) | E2: worldwide OPTION to Alpha 2023; exercise for **Japan** 2024-06; OPTION_LAPSED, no territory, 2025-01; buyer US | `OPTION_HELD_IN_TERRITORY_PER_EVIDENCE tier=DEPRIORITIZED`; "an option lapse (2025-01-01) naming Alpha Bio could apply to 2 grants; none was cleared". Rev 2: CONFLICTING. | The rest of the option lapsed: not encumbered in the U.S. | `_exercise` builds the split license from the option's own event (`:351`). Option outcomes match every grant whose event is an option (`:263-264`), so the split license and the remainder both match (`:281-282`). | medium |
| P1 | E8: same option; exercise for the U.S. 2024-03; lapse for "worldwide excluding the U.S." 2025-01; buyer JP | OPTION_HELD in JP, DEPRIORITIZED. Rev 2: CONFLICTING. | lapsed in JP | same | (P1) |
| P1 | E7: option deal DX; U.S. exercise linked to DX; TERMINATION linked to DX, no territory, 2025 | `LICENSED_IN_TERRITORY_PER_EVIDENCE tier=DEPRIORITIZED`; "a termination (2025-01-01) naming Alpha Bio could apply to 2 grants; none was cleared". Rev 2: RETURNED. | RETURNED in the U.S. | Both grants carry deal id DX (`:265-266`). | (P1) |
| P1 | E1-JP (U.S. exercise, then a lapse; buyer JP) → OPTION_HELD. E3-JP (U.S. exercise, then a Japan exercise; buyer JP) → OPTION_HELD, not LICENSED. | | | same | (P1) |
| N3b | No grants. ACQUISITION Gamma ← Origin, territory "worldwide excluding the U.S.", 2025-01-01. Buyer deprioritizes Gamma. | `OWNER_ACQUIRED_PER_EVIDENCE tier=DEPRIORITIZED owner='Gamma Corp'`; "Would Gamma Corp license or sell US rights?" | U.S. owner is still Origin | Owner acquisitions ignore territory (`:205-206`, `:645-652`). | medium |
| Negated words | Landscape text "Not licensed", "Not licensed in the U.S.", "Never partnered", "Not optioned", "Not partnered; available". Analyst "Not licensed in the U.S." on ws_b JS107 (China license on file). | Field path: `ENCUMBERED_PER_SOURCE -> LICENSED_IN_TERRITORY_PER_EVIDENCE -> DEPRIORITIZED`. ws_b JS107: `CONFLICTING_EVIDENCE`, "the U.S.-rights field (landscape or analyst) reads ENCUMBERED (source-provided); the rights evidence records no third-party grant over the U.S." | UNKNOWN, or not encumbered | `_ENCUMBERED` has no negation check (`commercial.py:36, 64`). E2 now turns it into a conflict (`screening.py:265, 281-285`). | medium |
| NA-label (introduced via the F1 fix) | Landscape text "Not currently available" | `NOT_AVAILABLE_PER_SOURCE -> LICENSED_IN_TERRITORY_PER_EVIDENCE -> DEPRIORITIZED`, shown as "licensed in the buyer territory per evidence" | "not available per source"; no license is in evidence | `transaction.py:115` (older mapping, newly reached) | low |
| W1 (introduced) | U.S. license to Alpha 2015-01-01, and again 2025-01-01 | stale=True; "latest evidence for this position is dated 2015-01-01, more than 730 days before 2025-06-01". Rev 2: stale=False. | not stale | `_primary` keeps the older grant on a tie (`:377-378`); only it is decisive (`:461`). | low |
| N7e (introduced) | U.S. license to Alpha 2015; Gamma acquires the licensor 2025 | LICENSED, stale=False. Rev 2: stale=True. | stale | acquisition chain counted (`:231`, `:461`, `:771-775`) | low |
| H6 wording (introduced) | License to Alpha 2023; Gamma acquires Alpha 2024; Origin acquires Gamma 2025 | OWNER_ACQUIRED (right). Reason "Gamma Corp acquired Alpha Bio; the grant between Origin Bio and Alpha Bio is now held within one company per source". | Name Origin's acquisition of Gamma | `:587-589` takes the first acquisition of the chain. | low |
| Memo "no effect" | ws_c (F1-analyst) | "3 cited assertion(s) by HUMAN reviewer(s) changed decisions for 0 program(s); 0 override a different source value; no effect on: QLS31905, SKB315, JS107." Those three are transaction #1–#3 in tier 0. | Say the assertions put them in "availability stated" | `memo.py:235-242` counts gate effects only. | low |
| Originator note | Every RETURNED, including N4d (to Kappa) and N8 (co-development) | Note "rights returned to the originator per source (not a statement of availability)" | No originator claim unless evidenced | `transaction.py:190-191` | low |
| H5 | OPTION row with status EXPIRED | RIGHTS_RETURNED; "grant to Alpha Bio ended in US per source" | a lapsed option, worded as a lapse | `:257-259` with `:535` | low |
| H3, N7c | License to Alpha; termination; Gamma later acquires Alpha | "grant to Gamma Corp ended in US per source" | "grant to Alpha Bio (now Gamma Corp) ended" | `:540` uses the current name | low |

Confirmed improvements: E1, E3 and E9 are LICENSED in the U.S. (rev 2: CONFLICTING). E5 keeps the option, with a note
(rev 2: LICENSED). W7 is CONFLICTING. G1–G5 as claimed. "Worldwide excluding U.S" now excludes the U.S. Coarse
dates use the start of the period, so they err toward stale (C1, C3).

## 4. Output honesty

- **CLDN18.2 outputs hold.** No output uses "open" or "available" as a rights state. "OPEN" appears only as the
  Diligence "Question state" (91 rows). For the 13 programs with evidence, position, holder and rows agree across
  the JSON, the workbook and the memo. Every holder and owner shown is a cited party. The 8 stale programs are
  flagged in all three.
- **Quotes and ids hold.** Memo quotes stop at 200 characters with "…"; workbook quotes at 1,000. Workbook evidence
  lines start with the rights row and end with the event id.
- **Memo line 31 is still thin.** "Rights evidence also exists for 10 program(s)" gives position words,
  "(stale evidence)", holder and rows. It gives no quote, URL, date or reason.
- **Held-out outputs contradict themselves:**
  - N1 (ws_a): "recorded grants do not cover US" sits above its own evidence "license, - from Origin Bio, United
    States".
  - Memo line 9, "Nothing is shown as available without an explicit, dated statement", sits above "#1 Spevatamig
    (PT886): availability stated, unverified", whose evidence is an "undated availability statement" (ws_a). In
    ws_c, tier 0 rests on an undated and a 2015 assertion.
  - F1-analyst: the workbook shows "AVAILABLE (analyst-asserted or -confirmed from a cited source; verify)" for the
    text "Available for licensing: no". The JSON has `evidence: []` and the memo has no evidence line. The citation
    is only in the Diligence sheet's ANALYST_ASSERTION row; the undated one reads "<https://example.test/c1> (None)".
  - E2-holder: the reason says "the landscape also names ..." for an analyst assertion. The question names Origin
    Bio, not BigPharma.
  - E3-ids: unlinked and id-less rows appear only on the import console. The JSON, workbook and memo are silent,
    while the two affected programs rank #1 and #2.
- **Codes in prose** remain in two reason templates (`transaction.py:134`, `screening.py:283`).

## 5. CLDN18.2 measured against the reference and B

### 5a. What changed from revision 2

| Program | Revision 2 | Revision 3 | Effect |
|---|---|---|---|
| LM-302 | CONFLICTING, #1 rights unresolved; successor question | adds "the newest evidence for the license to Turning Point Therapeutics is dated 2022-08, more than 730 days before 2026-10-29; it may have ended since" and "Is the license to Turning Point Therapeutics (2022-05-04) still in force?" | better question; same tier and position |
| FL-301 | LICENSED, Leap; cites row 16 only | cites rows 16 and 17 (the acquisition) | the holder is now evidenced |
| 8 stale programs (incl. FL-301) | "latest supporting evidence is dated ..." | "latest evidence for this position is dated ..." | wording only |
| All 62 | | tiers identical; eligible: 8 rights unresolved, 6 deprioritized; none in tier 0 or 1 | |

### 5b. Error classes against the reference

| Error class | Baseline | R1 | Revision 2 | Revision 3 |
|---|---|---|---|---|
| False "unobstructed" (third-party U.S. rights shown OPEN or in a top tier) | 4 definite + zanidatamab | 0 | 0 | **0** |
| False encumbrance | 0 | 0 definite, 2 likely outdated | same | **same** (EO-3021, SYSA1801; stale-flagged) |
| Wrong holder | n/a | 3 | 1, labelled (LM-302) | **1, labelled** (LM-302) |
| Wrong territory reading | n/a | 1 | 0 | **0** |
| Missed return | n/a | 1 (SKB315) | 1 | **1** (SKB315) |

### 5c. Usefulness against general Claude (B), the 15 deal programs

| Program | DealScreen revision 3 | Score | B | Change from rev 2 |
|---|---|---|---|---|
| CL-01 zolbetuximab | OWNER_ACQUIRED Astellas; excluded (marketed); stale | right | right | none |
| CL-02 IMAB362 | OWNER_ACQUIRED Astellas; stale | right | right | none |
| CL-03 AZD0901 / CL-04 CMG901 | LICENSED AstraZeneca, global; stale | right / right | right / right | none |
| CL-05 sonesitatug vedotin | NO_RIGHTS_EVIDENCE; identity flag to AZD0901 | partial | right | none |
| CL-06 IBI343 | LICENSED Takeda ex-Greater China; full quote | right | right | none |
| CL-07 LM-302 | CONFLICTING; Turning Point "(recorded; conflicting)"; asks about the successor and whether the 2022 license is in force | partial | right | new question |
| CL-08 SHR-A1904 | OPTION_HELD Merck KGaA; stale | right | right | none |
| CL-11 XNW27011 | LICENSED Astellas ex-Greater China | right | right | none |
| CL-13 givastomig | SHARED, I-Mab and ABL Bio | right | right | none |
| CL-14 EO-3021 | LICENSED Elevation; stale; "still in force?" | partial | right | none |
| CL-15 SYSA1801 | same as CL-14 | partial | partial | none |
| CL-26 RC148 | LICENSED AbbVie ex-Greater China | right | right | none |
| CL-27 SKB315 | NO_RIGHTS_EVIDENCE | missed | right | none |
| CL-30 FL-301 | LICENSED Leap, ex-China, via the cited acquisition row 17; stale | right | right | acquisition now cited |
| **Totals** | | **10 right / 4 partial / 1 missed** | **14 / 1 / 0** | unchanged |

Notes:
- DealScreen still wins on audit and restraint. B still wins on recall (SKB315, LM-302's return, EO-3021's
  discontinuation, the twin's holder).
- SKB315 caveat (judgement, not an error): the reference dates MSD's return to August 2024. Under revision 3, a
  sourced return of that date is stale at the C3 as-of date (819 days > 730), so it lands in "rights unresolved"
  (ws_a #8), not tier 1. The buyer can raise `max_evidence_age_days`. At the default, the reference's top
  returned asset would stay out of the top tiers even with perfect evidence.
- Improvement or regression: on CLDN18.2, a small audit improvement and no change in calls. On held-out inputs,
  mixed: the 23 reported shapes are closed, and the same kind of error re-enters through new rules (§2a, §2b).

## 6. Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | Imports through the profile. Events keep source system, dataset hash, row, URL, quote and dates with precision. Unknown labels, unreadable dates and missing ids are rejected and printed (ws_d rows 19, 23, 25). |
| AC2 | PARTIAL | CLDN18.2: no OPEN tier; no-record programs read NO_RIGHTS_EVIDENCE; "OPEN" only as a question state. Held-out: "availability stated" is reached by an undated statement (N6), a 2015 statement (N7a) and analyst text that says "no" or excludes the U.S. (F1-analyst); the workbook then prints "AVAILABLE (...)". |
| AC3 | PARTIAL | My territory phrasings parse correctly; G2 is named with a question; co-promotion and co-development are shared. But a grant naming no licensee reads as not covering the U.S. (N1), and an acquisition's territory is ignored (N3a, N3b). |
| AC4 | PARTIAL | Clean returns, re-licenses, K1 and K2 work, with questions naming the parties. Not met: a co-development opt-out clears both partners (N8); a later third-party exercise is ignored (H1); LM-302 is not RETURNED. Scope-unknown and undated returns reach tier 1 (N4, judgement). |
| AC5 | PARTIAL | Whole and partial exercises for the buyer territory work (E1, E3, E9, K5, M3). An option with no outcome stays OPTION_HELD. Not met: a report-dated option is cleared by an earlier lapse (R1); after a partial exercise, a later lapse or termination clears nothing (P1); an exercise with no recorded option is ignored (N2); an EXPIRED option is labelled a return (H5). |
| AC6 | PARTIAL | Two exclusive grants (G1, W6), availability beside a grant (W3) and an analyst `us_rights` encumbrance (E2) give CONFLICTING and cite both. Not met: an analyst `us_rights_holder` (E2-holder); a third-party exercise beside a China license (N2a). Negated words create false conflicts (ws_b JS107). |
| AC7 | PARTIAL | Stale clear positions now go to RIGHTS_UNRESOLVED (S1, D7, C1). But both sentences fail on held-out inputs: a 2015 statement re-reported in 2025 is counted (N7a); an undated statement counts beside another fresh one (N6); an analyst assertion dated 2015 or undated is counted (ws_c). Unrelated acquisitions refresh old evidence (N7b/c, N7e). A fresh re-license is flagged stale (W1). |
| AC8 | PASS | 0 of 62 CLDN18.2 scientific fields changed against the frozen baseline, and 0 in each of my 4 adversarial workspaces (ws_a to ws_d) and a no-rights screen. Cross-version against pre-R1 0ee7752: 0 changes on 312 assets in 4 landscapes. Cycle-4 harness: byte-identical, fast path on all 4 (run from the repo root). |
| AC9 | PASS | Territory validated in `TransactionPreferences`, `CommercialDiligence` and `rights_position`; all B1 inputs refused with a message naming the codes; "us " read as US. Defaults never imply availability. (Up from PARTIAL in rev 2.) |
| AC10 | PARTIAL | JSON and workbook now cite acquisitions and exercises, clip quotes visibly and give event ids. Memo bullets give row and quote. Not met: memo line 31 (10 programs) has no quote, URL, date or reason; tier-0 analyst entries carry no evidence in the JSON or memo; unlinked and id-less rows appear in no output; N1's reason contradicts its evidence. |
| AC11 | PARTIAL | CLDN18.2: every program has a question; LM-302 now also asks whether the 2022 license is in force. Held-out: N1 asks a question with a false premise ("Recorded deals cover other territories only"); E2-holder asks about Origin Bio, not BigPharma; E3-ids ask nothing; N8 does not ask whether the remaining partner holds the rights. |
| AC12 | PASS | A grep of the 11 new or changed `src/bve/dealscreen` files for the 35 party and program names in the rights file, plus the CLDN18.2 program names and codes, finds no match. |
| AC13 | PARTIAL | Unchanged: IBI343 and SHR-A1904 are no longer unobstructed; RC148, FL-301 and XNW27011 are encumbered; no-record programs read NO_RIGHTS_EVIDENCE. LM-302 is CONFLICTING, not returned. |
| AC14 | FAIL | New false-clearance errors: N1, N3a, R1 (introduced); E2-holder, E3-ids, F1-analyst, N6, N7b/c, N8 (claimed fixed); N2, N7a (older). New false encumbrances: P1, N3b, negated words. None is in the CLDN18.2 output. All are reported here. |

Compared with REREVIEW.md, only AC9 changes grade (PARTIAL → PASS).

## 7. Ranked remaining issues

1. **Clear positions are still inferred from incomplete records** (N1, N3a, R1, N2 with H1, N8). Each new ledger rule
   clears rights from a record that lacks a party, a territory, an order or a remaining partner. These programs sit
   in tier 1, above every encumbered program.
2. **Evidence outside the ledger is not reconciled or not read** (E2-holder, F1-analyst, E3-ids). In my end-to-end
   runs each put a program at #1.
3. **Staleness is measured on the wrong events** (N6, N7a, N7b/c, N7e, W1). Undated clearing evidence is never stale
   (N4f, N5, N9; judgement).
4. **Partial-exercise bookkeeping** (P1: E2, E7, E8). The split license shares the option's event, so every later
   outcome is ambiguous. Under `encumbered_rights: exclude` these false encumbrances would hide programs.
5. **Owner and label errors** (N3b, negated words, NA-label, H5, H6 and H3 wording, originator note).
6. **Output honesty** (memo line 9 and the "no effect" line can be false; analyst tier-0 entries show no evidence;
   memo line 31 has no quotes; unlinked rows only on the console).
7. **Return-only rows of unknown scope reach tier 1** (N4a–c, judgement). The rule needs a stated policy.
8. LM-302 CONFLICTING and recall capped by the library (unchanged, honestly labelled). A sourced SKB315 return would be
   stale at the default age.

**Single highest-value next fix: make tiers 0 and 1 an allow-list, decided once, from the deciding events.** Today the
transaction view admits every clear position unless one of two flags is set (`transaction.py:204-210`). So every
ledger rule that infers clearance from a thin record lands in tier 1, and each review finds new ones. Instead, a
program may enter AVAILABILITY_STATED_UNVERIFIED or NO_THIRD_PARTY_GRANT_IN_EVIDENCE only if all four checks pass.
Otherwise it stays RIGHTS_UNRESOLVED, with a question naming the check that failed.

1. **Complete.** Every rights row for the program is attached and explained: no unmatched or ambiguous outcome
   (exercises included), no rejected row. Program ids match without regard to case. Rows with no program id are
   listed in the memo and workbook. Closes N2, H1, E3-ids.
2. **Specific.** Each deciding event names its counterparty. Each grant it relies on names licensor and licensee. An
   acquisition clears only the territory it states. A shared grant ended by one partner is not clear. Closes N1,
   N3a, N8 (and N4b/c).
3. **Current.** Each deciding event has its own date, is ordered against its grant by one rule for licenses and
   options, and is within the buyer's age limit on that date. Source dates, acquisitions and other statements do not
   refresh it. Undated never qualifies. Closes R1, N6, N7a, N7b/c (and N4f, N5, N9).
4. **Uncontested.** No landscape or analyst statement disagrees, holder included. Analyst text is read with the same
   negation, territory and date rules as rights rows. Closes E2-holder, F1-analyst.

Add every input in §2 and §3 as held-out tests with fictional parties. Then fix P1 (give the split license its own
identity) and N3b, which are false encumbrances that the check does not touch.
