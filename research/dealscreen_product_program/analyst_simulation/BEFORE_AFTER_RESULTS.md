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
