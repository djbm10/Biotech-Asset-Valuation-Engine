# Before / after results — AI-SIMULATED / INTERNAL DEVELOPMENT

Same real public FcRn / gMG landscape (40 rows), same buyer. Reference = the pre-committed
`reference_manual_assessment.csv` (same author as the tool, so not independent). No human
time-saving is claimed from simulated timings.

## Cycle A1

| Measure | Before (A1 baseline) | After A1 fixes |
|---|---|---|
| Funnel eligible / unresolved / excluded | 4 / 14 / 22 | 6 / 12 / 22 |
| In-scope (reference IN) programs ELIGIBLE | 4 / 9 | 6 / 9 |
| Wrong decisions vs reference (IN excluded or OUT eligible) | 0 | 0 |
| Rows with indication gate UNKNOWN | 22 | 1 (21 moved to PASS via a disclosed reading; the 1 left is belimumab's misspelt "Myasthaenia", correctly unread) |
| Rows wrongly marked ACTIVE ("no recruiting … COMPLETED") | 5 | 0 |
| Marketed rows with activity UNKNOWN | 8 | 0 (MARKETED) |
| Spurious therapeutic-area FAIL from a vendor label alone | 1 (belimumab; masked) | 0 |
| Deal CLI silently ignoring misplaced keys | yes | refused, exit 2, with the correct location |
| Deal CLI states discount rate used and perspective | no | yes |
| `value` with nothing approved | traceback | plain message, exit 0 |
| Finalists note for AI candidates | "7 approved finalist(s)" | "5 candidate not approved (AI_PREPARED)" |
| Memo: FDA labeler described as rights holder | yes | "labeler or holder named … not the legal owner … not availability" |
| Memo: same molecule listed twice without warning | yes | flagged on each line |
| Import prints identity flags | no | yes (and `queue` lists them) |

**Held-out check of the indication reading (not used to design it).** Across 75,434 condition
strings from the S&E indication pilot files, the rule produced 1 reading ("Relapsed Refractory
Multiple Myeloma (RRMM)" → "Refractory Multiple Myeloma"), which is correct. Synthetic 200:
0 readings, funnel unchanged.

**Remaining in-scope programs not ELIGIBLE (3):** efgartigimod IV and SC (vendor modality
"Protein"; the buyer spec has no Fc-fragment term, which is a buyer decision, D1), IMVT-1402
(no sourced target, mechanism or modality in the landscape; needs a human-entered cited fact).

**What a BD reviewer would still object to:** orilanolimab (development terminated) is ELIGIBLE
and ranks 5 of 6 because inactivity is only a missing preference, not a demotion; rozanolixizumab
shows as "Phase 4 or marketed"; batoclimab is still three records.

## Cycle A2 re-test (fresh blind analyst on A1+A2 code, plus a held-out buyer)

From the frozen `ANALYST_FINDINGS_A2.md` (bada391):

| Measure | A1 analyst (pre-fix) | A2 analyst (post A1+A2) |
|---|---|---|
| FcRn funnel | 4 / 14 / 22 | 6 / 12 / 22 |
| Wrong in/out gate calls found by the analyst (FcRn) | batoclimab split 3 ways; gMG wording | none |
| Wrong in/out gate calls (held-out C5 buyer) | not run | none, but 1 wrong *eligibility* through modality: Pozelimab + Cemdisiran (siRNA component) passed as "Antibody" and ranked #1 |
| `value` crash / silent valuation defaults | yes / yes | no / refused with location hint |
| Workbook "approved" for AI candidates | yes | no |
| AI-found cited facts usable by a human | no path | 4 proposals recorded for human confirmation (NOT COMPLETED BY HUMAN) |
| Valuation reached | no | no (human approval required, by design; direct CLI needed invented company data) |

## Cycle A3 (fixes from the A2 re-test)

Measured by re-screening copies of the A2 analyst's own workspaces with the new code
(`measure/before_A3_*.json`, `measure/after_A3_*.json`):

| Measure | Before A3 | After A3 |
|---|---|---|
| Held-out C5 funnel | 5 / 11 / 24 | 4 / 12 / 24 |
| Combination product ELIGIBLE on one vendor modality | RW-17 ELIGIBLE, rank 1 | RW-17 UNRESOLVED, reason disclosed; the other ranks each move up by one |
| FcRn funnel and ranks | 6 / 12 / 22 | unchanged |
| BD Finance can see the exact valuation config without approval | no | `value-config` writes it, labelled PREVIEW; nothing run or recorded |
| Rank reasons visible | no | workbook column per program |
| README identity example works | no | yes (flag ids printed by `queue`; a name resolving to several flags lists their ids) |

## Cycle A4 (fixes from the A3 re-test)

| Measure | Before A4 | After A4 |
|---|---|---|
| Peak sales 320 vs 400 explained to the reader | no (invisible ×0.80) | yes, on memo, workbook, preview config and console (factor read from the engine default) |
| A config setting `market_model.compliance_rate` | silently ignored | refused on DealScreen paths, naming the key |
| Headline eligible count with 3 records of one molecule | no warning | funnel line states how many eligible records share open identity flags |
| Engine labelling/source-table defects (P3-P7) | present | **unchanged** (protected); written up for Lane 1 |
