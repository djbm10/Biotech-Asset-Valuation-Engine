# Adversarial re-review: cycle R1 revision 2, rights evidence (CLDN18.2)

**AI-SIMULATED INTERNAL REVIEW.** I am an AI playing a skeptical pharma BD analyst and auditor. I am not a human
reviewer and I approve nothing. I did not trust REVIEW_RESPONSE.md; every claim below was re-checked.

Scope: the uncommitted working tree on `dealscreen-mvp`, snapshot taken 2026-10-30 08:23 (hashes in
`/tmp/claude-1000/rr2/snapshot/SHA256SUMS`). At about 08:30 another process edited docstrings in
`rights_territory.py`, `rights_position.py` and `transaction.py` (company names replaced by "Example Pharma"/"Acme").
No logic changed, and `after_v2/` and `inputs/` did not change. I edited nothing under `src/` or `tests/`.
Scripts are `/tmp/claude-1000/rr2/adv2.py` to `adv5.py` and `cross_version.py`. Their outputs (`*.out`) are copied
below. Workspace experiments ran on copies (`/tmp/claude-1000/rr2/ws_e1`, `ws_e2`, `ws_norights`).

Baseline checks: `tests/dealscreen` 390 passed (85 in `test_rights_evidence.py`). `ruff` is clean. No test covers any
failure in section 3.

## 1. Transcription fidelity (`inputs/rights_cldn18.csv`)

Machine check: for all 17 rows, Source Quote, URL, Source Date and Program ID equal the library item exactly. All 13
non-empty Territory values appear verbatim in their quotes. Deal types and exclusivity match the quote wording. The 11
skipped items are payment terms, plus item 57, which duplicates item 58. I found **no invented deal, type, territory
or link.**

| Row(s) | Finding | Severity |
|---|---|---|
| R07 | Still undated, with no Related Deal. Verified: "Turning Point" appears in no library item, so the BMS succession is not in evidence. Judgement call: R07's quote says "LM-302/TPX-4589" and R06's says "TPX-4589 (LM-302)". The shared code could support a Related Deal link without inventing a party. | medium (keeps LM-302 CONFLICTING) |
| R08 | **Resolved.** Deal Date is now `2024` (year precision), from "last year" in a 2025-07 article. The item title "LaNova bought by Sino Biopharm" is still not transcribed, so the owner shows as LaNova only. | low |
| R10 | **Resolved.** Now "Co-promotion option". | ok |
| R12 | **Resolved.** Partners are listed with I-Mab first. Outputs say "partners I-Mab and ABL Bio". | ok |
| R03/04, R06, R09/10, R11, R13/14, R15, R16 | The party name is not in the quote. It comes from the item title (Hengrui, Evopoint, RemeGen, the AZ←KYM direction), the filer (Turning Point: the quote says "we"), the ticker "ELEV", or another item (Flame, from item 110). All match the reference. But `build_rights_file.py:3-4` says parties are "read from the quote only", and the outputs show only the quote. | low |
| R03/04, R09/10, R11, R13/14, R15 | Deal Date is the publication date, which the quote does not state. No effect: the ledger uses the source date anyway. | low |

## 2. Were the misleading rankings corrected? (`baseline/` vs `after_v2/after_transaction.csv`)

| Program | Baseline | Revision 2 | Reference | Verdict |
|---|---|---|---|---|
| IBI343 | OPEN, unresolved #1 | DEPRIORITIZED; LICENSED, Takeda, "worldwide outside of Greater China" | Takeda ex-GC | fixed |
| SHR-A1904 | OPEN, txn #3 | DEPRIORITIZED #10; OPTION_HELD, Merck KGaA; stale | Merck KGaA option | fixed |
| RC148 | OPEN | DEPRIORITIZED; LICENSED, AbbVie | AbbVie ex-GC | fixed |
| FL-301 | OPEN | DEPRIORITIZED; LICENSED, Leap (via recorded acquisition), "territories excluding China"; stale | Flame/Leap ex-China | fixed (R1's territory error is gone); the acquisition row is not cited (§4) |
| XNW27011 | DEPRIORITIZED (sponsor) | DEPRIORITIZED #13; LICENSED, Astellas | Astellas ex-GC | right, now evidence-based |
| LM-302 | OPEN #1 | RIGHTS_UNRESOLVED #1; CONFLICTING; holder "Turning Point Therapeutics (recorded; conflicting)"; owner LaNova Medicines; asks whether BMS succeeded Turning Point | returned; LaNova/Sino Biopharm | no false availability; holder wrong but labelled; **AC13 not met** |
| Givastomig | OPEN | RIGHTS_UNRESOLVED; SHARED, "I-Mab and ABL Bio (shared)" | both, equally | fixed |
| EO-3021 / SYSA1801 | OPEN | DEPRIORITIZED; LICENSED, Elevation; stale | licensed 2022, then discontinued; unclear | likely outdated; the stale flag and question mitigate |
| AZD0901 / CMG901 | DEPRIORITIZED (sponsor) | DEPRIORITIZED; LICENSED, AZ, global; stale | AZ global | right |
| Zolbetuximab / IMAB362 | EXCLUDED / DEPRIORITIZED | same tiers; OWNER_ACQUIRED, Astellas | Astellas owns | fixed (the "third party" label is gone) |
| SKB315 | OPEN #7 | RIGHTS_UNRESOLVED #6; NO_RIGHTS_EVIDENCE | MSD returned global rights (reference #1) | missed (not in the library) |
| Sonesitatug vedotin, ASP546C | DEPRIORITIZED (sponsor) | same; NO_RIGHTS_EVIDENCE; identity flag to AZD0901 / XNW27011 | AZ / Astellas | partial: the twin's evidence is not carried over |
| 47 other no-record programs | OPEN or DEPRIORITIZED | NO_RIGHTS_EVIDENCE, first contact named | mostly unknown | honest |

| Error class (vs reference) | Baseline | R1 (first review) | Revision 2 |
|---|---|---|---|
| False "unobstructed" (third-party U.S. rights shown OPEN or in a top tier) | 4 definite + zanidatamab | 0 | **0** (no program is in tier 0 or 1) |
| False encumbrance | 0 | 0 definite, 2 likely outdated | **0 definite**, 2 likely outdated (EO-3021/SYSA1801, stale-flagged) |
| Wrong holder | n/a | 3 | **1**, labelled (LM-302) |
| Wrong territory reading | n/a | 1 | **0** |
| Missed return | n/a | 1 (SKB315) | 1 (SKB315) |

Also re-confirmed fixed, by my reruns: T1–T7, L1–L7 and P2 on their exact inputs. The sponsor is no longer an input
to the position. The memo summary, the duplicate Diligence rows, the duplicated reasons and the staleness anchor are
fixed. IBI343 now appears in the memo (line 31).

## 3. New errors (adversarial inputs)

Buyer territory {US}, as-of 2025-06-01, max age 730 days, `encumbered_rights: deprioritize`, unless noted. Parties
are fictional. "Actual" text is copied from the `.out` files.

### 3a. Paths into the two top tiers (definite unless marked)

| # | Input | Actual | Expected | Cause |
|---|---|---|---|---|
| D1 | License to A 2020; termination by A 2022-03-01; **the same termination again, undated**; re-license to A 2025-03-01 | `position=RIGHTS_RETURNED_PER_EVIDENCE tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE (tier order 1)`; "grant to Alpha Bio ended in US per source" printed twice; asks "have they been re-licensed since?" | LICENSED or CONFLICTING | `rights_position.py:233` drops ended grants before the ambiguity test; undated outcomes run last (`:199`). The CLDN18.2 file has this exact shape: R07 (undated) and R08 (2024) report one termination. |
| D2 | License to A 2020; termination by A 2022; **undated termination naming only the licensor**; license to B (US) 2025 | `RIGHTS_RETURNED_PER_EVIDENCE ... NO_THIRD_PARTY_GRANT_IN_EVIDENCE`; "grant to Beta Pharma ended in US per source" | LICENSED to B | same |
| U1 | North America license to A; termination "as to **Mexico**" (also "Latin America"; also a return for "Asia ex-Japan") | `RIGHTS_RETURNED_PER_EVIDENCE tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE`; "grant to Alpha Bio ended in US per source" | LICENSED | `:268`: an unreadable territory (`None`) on an outcome clears the whole grant. This is R1's T1 again, on the outcome side. |
| U2 | Worldwide option to A; lapse stated for "Japan" | `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE ... NO_THIRD_PARTY_GRANT_IN_EVIDENCE`; "option to Alpha Bio lapsed per source" | OPTION_HELD | `:262-267` ignore a lapse's territory (and an exercise's, `:256`) |
| A1 | Fresh statement "seeking partners for **Europe and Latin America**" (also "Australia and New Zealand"); no grants | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED tier=AVAILABILITY_STATED_UNVERIFIED (tier order 0)`; reason "the statement does not name a territory" | not U.S. availability | `:393` counts `None` as covering. The reason is false: the statement names a territory. |
| A2 | Seeking-partner row with vendor status COMPLETED (or TERMINATED) | `tier=AVAILABILITY_STATED_UNVERIFIED (tier order 0)` | not counted | `:204` ignores status |
| A3 | Statement 2024-01; U.S. license 2024-03 (the partner was found); terminated 2025-01 | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED`, tier order 0 | RETURNED, tier 1 | `:394` treats a statement as superseded only by grants that are still active |
| B1 | C3 buyer plus `territory: [USA]` (also `U.S.`, `UNITED STATES`), screened end to end on CLDN18.2 | exit 0, no warning. `SHR-A1904 ELIGIBLE txn_rank=2 tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE pos=NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE`. IBI343, RC148, EO-3021, SYSA1801, givastomig and FL-301 read the same. Reason: "recorded grants do not cover USA" | validation error | `transaction.py:57` and `screening.py:264` accept any string |
| E2 | Analyst `assert us_rights="Exclusively licensed to BigPharma Inc. in the U.S."` on QLS31905, plus an imported China-only license | `QLS31905 ELIGIBLE txn_rank=1 tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, while the same screen's commercial display reads "ENCUMBERED (source-provided)" | CONFLICTING | `screening.py:279` reconciles only AVAILABLE_* landscape statuses with the evidence |
| E3 | ATG-022: China-only license accepted; U.S. license dated "Q3 2025" | import: "REJECTED rights row 20: unreadable event_date 'Q3 2025'". Screen: `ATG-022 ELIGIBLE txn_rank=2 tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, with no mention of the rejected row | RIGHTS_UNRESOLVED and a note | a rejected row never reaches its program |
| F1 | No rights row; the landscape U.S.-rights text says "Not currently available" (also "Rights no longer available", "available only in China") | `AVAILABLE_PER_SOURCE -> AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED -> tier AVAILABILITY_STATED_UNVERIFIED` | not available | The regex in `commercial.py:42` predates R1. `transaction.py:86-89` now routes it to the new top tier, with no date check. |
| D3 (judgement) | As D1, but the second termination is dated only by its report (source 2025-02), after a 2024-06 re-license | RETURNED, tier 1 | CONFLICTING | `rights.py:169-176` uses the report date as the event date. A report date is only an upper bound. |

### 3b. False encumbrance, wrong holder, hidden grant

| # | Input | Actual | Expected | Severity |
|---|---|---|---|---|
| G4 | License to SmallCo from Origin; **Origin acquires SmallCo** | `LICENSED_IN_TERRITORY_PER_EVIDENCE tier=DEPRIORITIZED holder='Origin Bio' owner=None`; "license to Origin Bio covering US"; asks "would Origin Bio sublicense or transfer it?" | the owner holds all rights; no third-party grant | medium |
| G3 | BigPharma worldwide license, **sublicensed** for the U.S. to SmallCo; the buyer deprioritizes BigPharma, `encumbered_rights: ignore` | `tier=RIGHTS_UNRESOLVED holder='SmallCo' holders=['SmallCo']` | BigPharma named and counted → DEPRIORITIZED | medium (`:332` skips the head license; contradicts REVIEW_RESPONSE S8) |
| G2 | U.S. license to A, plus a license to BigPharma for "the Americas" (unreadable) | `tier=RIGHTS_UNRESOLVED holders=['Alpha Bio']`. BigPharma appears in no reason and no question. | named, asked about, counted | medium (`:404` passes only readable grants; AC3 says "with a question") |
| G1 | Exclusive options to A (worldwide) and to B (US) | `OPTION_HELD...`; "also recorded over US: option to Beta Pharma" | CONFLICTING (AC6's own example) | low |
| P | Territory "Worldwide excluding U.S" or "Worldwide, ex-U.S" (no final period) | the parse includes `'US'` | all regions but the U.S. | low (false encumbrance) |
| K6 | Co-development between A and B; termination naming B | "grant to Alpha Bio ended in US per source" | name B; A may hold the rights | low |

### 3c. Mislabelled or over-conservative

| # | Input | Actual | Expected |
|---|---|---|---|
| K1 | Only a return row: BigCo returned worldwide rights to Origin, 2024-08 (the SKB315 shape) | `NO_RIGHTS_EVIDENCE tier=RIGHTS_UNRESOLVED`; "no usable grant recorded"; question "Who holds rights?" | RETURNED, with a question naming BigCo and Origin. **Adding one SKB315 row would not surface the return.** |
| D5 | Deal D-X dated "2024"; termination linked to D-X, dated 2024-09 | CONFLICTING: "may predate the grant to Alpha Bio (2024)" | RETURNED. A linked termination cannot predate its own deal. |
| D6 | Option dated "2023"; lapse dated 2023-11 | CONFLICTING: "a option lapse (2023-11-30) ... may predate" | lapsed. The wording "a option" is also wrong (`_what`). |

### 3d. Evidence that decides a position is not cited (definite; affects AC10 and AC7)

- **Acquisition rows are never cited**, even when they rename the holder (`:399-400`). This appears in the live output:
  FL-301 names Leap as holder, but its evidence is R16 only, and R17 is absent from the JSON, the workbook and the CSV.
  G5: `cited rows=[41]`, with the acquisition row absent. M1: R06+R07+R08 plus one BMS-acquires-Turning-Point row
  gives the right answer (`RIGHTS_RETURNED`, owner LaNova Medicines), but cites only rows `[50, 52]`. The
  acquisition and the undated termination are dropped.
- **Option exercises are never cited, and staleness ignores them.** M3: a 2025-03 exercise gives `cited rows=[56]`,
  "latest supporting evidence is dated 2021-01-01", stale=True. K5: an exercise "for Japan" turns the whole worldwide
  option into a license.

Judgement calls, not counted as errors:
- **D4.** A license dated only by a 2025 filing, plus a 2024 termination, gives LICENSED with "ending an earlier deal
  not in the evidence". That reading assumes a deal nobody recorded, though it errs conservative.
- **S1.** A 2015 return still ranks in tier 1. It is flagged stale.
- **S2.** A fresh 2025 option hides a stale 2016 deciding license: stale=False.

## 4. Output honesty (memo, workbook, CSV)

- No CLDN18.2 output uses "open" or "available" as a rights state. "OPEN" appears only in the Diligence column
  "Question state" (91 rows). The 13 programs with evidence show the same position and holder in the JSON, the
  workbook and the memo. There is one rights row per program in Diligence. Every program has at least one question,
  and the question names the party where one is known.
- **Quotes are truncated without warning** (`workbook.py:474`). Quotes are cut at 300 characters and still closed
  with a quote mark, with no ellipsis. Four of the 13 cited grants lose the territory they were classified on: IBI343
  (R05), LM-302 (R06), EO-3021 (R13) and SYSA1801 (R14). IBI343's quote ends "...two late-stage oncology medicine":
  neither "IBI343" nor "worldwide outside of Greater China" survives.
- **FL-301 has no evidence for its holder.** The holder is "Leap Therapeutics", but the evidence cell shows only
  "license; Flame Biosciences from NovaRock Biotherapeutics" (§3d).
- **The memo cites less than AC10 requires.** Evidence bullets give date, type, parties, territory and URL, but no
  quote and no event id (`memo.py:308-310`). Line 31 lists 10 programs as position and holder only, with no
  evidence, no reason and no stale flag. Six of the 10 are stale (CMG901, EO-3021, SYSA1801, FL-301, IMAB362,
  zolbetuximab).
- The memo prose prints codes, e.g. "RIGHTS_UNRESOLVED; rights position CONFLICTING_EVIDENCE" and
  "OWNER_ACQUIRED_PER_EVIDENCE". Line 9 uses words. The AZD0901 entry says it is stale three times.
- Memo line 9 says "Nothing is shown as available without an explicit, dated statement" (`memo.py:341`). That is true
  for this run, but the code does not enforce it: path F1 has no date check.
- The Screening sheet column "U.S. licensing availability (independent of science)" reads UNKNOWN for all 62 rows.
  For 8 of them it sits beside "LICENSED_IN_TERRITORY_PER_EVIDENCE". Not false, but it gives two rights answers side
  by side.
- `after_transaction.csv` is a research comparison file with row numbers only. That is acceptable for its purpose.

## 5. Usefulness vs general Claude (B), the 15 deal programs

| Program | DealScreen rev 2 | Score | B | Better |
|---|---|---|---|---|
| CL-01 zolbetuximab | OWNER_ACQUIRED Astellas; excluded (marketed) | right | right | tie |
| CL-02 IMAB362 | OWNER_ACQUIRED Astellas | right | right | tie |
| CL-03 AZD0901 / CL-04 CMG901 | LICENSED AZ, global; stale | right / right | right / right | tie |
| CL-05 sonesitatug vedotin | no record; sponsor AZ "not a rights statement"; identity flag | partial | right | B |
| CL-06 IBI343 | LICENSED Takeda ex-GC; asks whether the license is exclusive | right | right | DS (exclusivity question) |
| CL-07 LM-302 | CONFLICTING; Turning Point "(recorded; conflicting)"; successor question | partial | right | B |
| CL-08 SHR-A1904 | OPTION_HELD Merck KGaA; exercise question; stale | right | right | tie |
| CL-11 XNW27011 | LICENSED Astellas ex-GC | right | right | tie |
| CL-13 givastomig | SHARED, I-Mab and ABL Bio | right | right | tie |
| CL-14 EO-3021 | LICENSED Elevation; stale; "still in force?" | partial | right | B (knows of the discontinuation) |
| CL-15 SYSA1801 | same as CL-14 | partial | partial | tie |
| CL-26 RC148 | LICENSED AbbVie ex-GC | right | right | tie |
| CL-27 SKB315 | NO_RIGHTS_EVIDENCE | missed | right | B |
| CL-30 FL-301 | LICENSED Leap, ex-China; stale | right | right | tie (DS cites no acquisition row) |
| **Totals** | | **10 right / 4 partial / 1 missed** | **14 / 1 / 0** | |

DealScreen is better on audit and restraint:
- Every call ties to a verbatim quote, row, file hash and date. CRITIC_FINAL §4 found 2 of B's 8 rights citations
  unsupported and 2 weak.
- Staleness is explicit.
- Questions are specific: exclusivity, option outcome, successor.
- It never turns "no record" into "unencumbered".

B is better on recall, because it searched beyond the 27-quote library: SKB315, Sino Biopharm for LM-302, EO-3021's
discontinuation. It also carries a twin's holder (CL-05). K1 shows that recording SKB315's return would still
produce NO_RIGHTS_EVIDENCE.

## 6. Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | Imports through the profile. Each event keeps hash, row, URL, quote and dates with their precision. Unknown labels and unreadable dates are rejected (E3 import line). |
| AC2 | PARTIAL | PASS on the CLDN18.2 outputs: no OPEN tier, and 49 no-record programs read NO_RIGHTS_EVIDENCE. But the code puts non-U.S., withdrawn, superseded or "not currently available" statements in the "availability stated" tier (A1, A2, A3, F1). |
| AC3 | PARTIAL | Grant parsing is now conservative (T1–T7 fixed; "Worldwide (exclusive)" reads as unstated). Shared rights are flagged. But an unreadable second grant gets no question (G2), and "ex-U.S" reads as covering the U.S. |
| AC4 | PARTIAL | Clean returns and re-licenses work. False RETURNED results remain: D1/D2 (undated or licensor-only outcomes) and U1 (an outcome with an unreadable territory). A return with no recorded grant reads NO_RIGHTS_EVIDENCE (K1). LM-302 is not RETURNED. |
| AC5 | PARTIAL | Exercise, lapse and held options work. A partial lapse clears the whole option (U2); a partial exercise converts the whole option (K5); a same-year lapse becomes a conflict (D6); exercises are not cited (M3). |
| AC6 | PARTIAL | Two licenses, and availability alongside a grant, both conflict and both are cited. Two exclusive options do not (G1). An analyst-asserted encumbrance does not (E2). Same-period linked outcomes over-fire (D5, D6). |
| AC7 | PARTIAL | Age is measured from the analysis date and the source date, and stale availability is dropped. But staleness ignores exercise and acquisition rows (M3), a fresh second grant masks a stale deciding license (S2), status is ignored (A2), and the landscape-field path has no date check (F1). |
| AC8 | PASS | 0 of 62 CLDN18.2 scientific fields changed, both vs baseline and vs a no-rights screen. Cross-version run (baseline 0ee7752 vs revision 2): synthetic_200 (192), FcRn v1 (40), FcRn v2 (40) and C5 held-out (40) each show 0 changes. The cycle-4 harness compares cached and full-ontology screens; it is not a before/after test. |
| AC9 | PARTIAL | The preferences work, and the defaults never imply availability. But `territory` accepts any string, and `[USA]` silently moves every licensed program into tier 1 (B1). |
| AC10 | PARTIAL | The JSON cites most events. Acquisitions and exercises are uncited (FL-301 holder). Workbook quotes are cut before the territory (4 rows). The memo shows no quote or event id, and no evidence for 10 programs. |
| AC11 | PARTIAL | PASS on CLDN18.2 outputs. Held-out gaps: K1/K2 ask "Who holds rights?" without naming the parties; G2 and G3 ask nothing of the hidden holder. |
| AC12 | PASS (now) | A grep of the 9 new or changed `src/` files finds no CLDN18.2 name. At 08:23 the docstrings at `rights_territory.py:135`, `rights_position.py:134` and `transaction.py:191-192` named Bristol Myers Squibb, Merck and Astellas. They were removed during the review by another process. |
| AC13 | PARTIAL | IBI343 and SHR-A1904 are fixed. RC148, FL-301 and XNW27011 are encumbered. No-record programs read NO_RIGHTS_EVIDENCE. LM-302 is CONFLICTING, not returned. |
| AC14 | FAIL as written | New false no-obstacle or availability paths: D1, D2, U1, U2, A1–A3, B1, E2, E3, F1. New false encumbrance or wrong holder: G4, G3, "ex-U.S". None of these occurs in the CLDN18.2 output. |

## 7. Ranked remaining issues

1. **Weak inputs promote programs to the top tiers** (D1, D2, U1, U2, A1, A2, A3). On clearing events and availability
   statements, the ledger reads "unreadable", "undated" and "status not active" in the permissive direction. This
   is the false-availability shape that R1 set out to remove.
2. **The buyer territory is not validated** (B1). One typo recreates the baseline's IBI343, SHR-A1904 and RC148
   errors, silently.
3. **The rights file overrides other rights evidence** (E2, E3). An analyst-asserted or landscape U.S. encumbrance is
   ignored once any rights row exists, and a rejected row disappears.
4. **Landscape free text "not currently available" lands in the availability tier** (F1).
5. **Uncited acquisitions and exercises** (§3d). FL-301 in the live output; staleness is wrong as a result.
6. **Holder logic** (G4 buy-back, G3 sublicense head, G2 unreadable second grant). The buyer's holder preference is
   missed.
7. **Output gaps**: truncated quotes hide the territory (4 live rows); the memo lacks quotes, event ids and stale
   flags; codes appear in prose.
8. **Returns with no recorded grant read NO_RIGHTS_EVIDENCE** (K1). This blocks the SKB315 fix. Linked outcomes
   also produce false conflicts (D5, D6).
9. LM-302 is still CONFLICTING. Recall is capped by the library. Both are known and honestly labelled.

**Single highest-value next fix:** add one promotion guard in the transaction view. A program may enter
AVAILABILITY_STATED_UNVERIFIED or NO_THIRD_PARTY_GRANT_IN_EVIDENCE only if all of the following hold:

- (a) every clearing event and availability statement it relies on has a readable territory (when a territory was
  written), an active or unknown status, and an unambiguous match. Ended grants count as candidates for undated or
  report-dated outcomes.
- (b) the buyer territory is a subset of `REGIONS`.
- (c) the program has no rejected rights row and no landscape or analyst encumbrance.

Otherwise the program stays RIGHTS_UNRESOLVED, with a question naming the event that failed. Add D1, D2, U1, U2,
A1–A3, B1, E2 and E3 as held-out tests. One guard closes every top-tier path found here. The modelling fixes (partial
lapse, supersession, buy-back, citing acquisitions) can follow.
