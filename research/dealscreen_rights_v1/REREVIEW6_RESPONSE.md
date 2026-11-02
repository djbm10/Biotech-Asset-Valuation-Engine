# Response to the R1 adversarial re-review 6 (REREVIEW6.md): revision 8

Revision 8 is the working tree on `dealscreen-mvp` as of 2026-11-01, on top of 50fd206 (revisions 6 and 7). Nobody
has reviewed it yet. This file is the implementer's account, not a review: every claim below should be checked by
running code. The reviewer and the implementer are both AI; neither is a human approval and nothing here is
validation.

## 1. The highest-value fix: a grant's party is a name and nothing else

REREVIEW6 found that the "grant over other places only" form read the place part strictly but took anything after
"to" as a party name: "… to Chinaco Pharma and in the Americas to Tessaly Pharma", "… for ROW", "… elsewhere",
"… - Tessaly Pharma has the rest". Revision 8 matches the form on the clause as written (case kept) and accepts the
party only if it is a name: capitalised words, digits and corporate punctuation, with no lower-case word, no dash, no
place the territory reader knows, no place-like word it does not know ("Americas", "Asia", "worldwide", "ROW",
"International", …) and no rights word (`rights_allow._party_ok`). A trailing "only" is allowed.

The other four High findings:

- **SPK.** A quote's "Name:" prefix is removed only when the name is the row's own grantor or the program's company
  (`rights_gate._speaker_stripped`). "Subject to Tessaly Pharma consent: …", "After Tessaly Pharma's U.S. option
  expires in 2027: …" and "Tessaly Pharma: …" are read whole, and block.
- **QW.** A non-availability row's quote is read clause by clause (`rights_gate._quote_problem`). A clause that names a
  buyer-territory place the row does not cover, or that reaches wider (an option, "worldwide", "global", "rest of
  the world", "ROW", "outside", "excluding", "North American", "right of first negotiation", "elsewhere"), passes
  only when it is a plain form saying no grant was made there or the company kept the rights. This also removes the
  inverted usefulness cost: "Chinaco Pharma licenses China rights; Origin Bio retains U.S. rights" now passes. A row
  whose own territory already covers the buyer territory is left to the ledger.
- **QT.** An offer that names places is "an offer" only if the places cover the buyer territory. "U.S. rights
  available" is not an offer to an EU buyer, nor to a {US, CA} buyer.
- **DATE.** A termination, return, option lapse or acquisition dated only to a year or month that contains the
  as-of date is not applied. It blocks and gets a question: "On what day did … take effect: before or after
  <as-of>?" (`rights_ledger._Ledger.straddling`, `rights_checks`). A status reported in a source dated only to such
  a period is judged on the end of the period (E2).

Low: L1c, the memo sentence now says "DealScreen's word rules found nothing else … (word rules can miss a condition
written in other words)". L3c is fixed by PLACE: the `assert` note gives the gate's verdict.

## 2. The findings

Tests are in `test_rights_rereview6.py` (60).

| Id | Severity | Revision 8 | Tests |
|---|---|---|---|
| PLACE | High | The nine `g1` phrasings have no plain form and stay out of tiers 0 and 1 on all three fields; beside an availability statement they are no longer tier 0; EU, JP and US+CA buyer variants block; plain grants ("Licensed in Greater China to Chinaco Pharma", "Exclusive China license to Chinaco Pharma Co., Ltd.", "Licensed to Chinaco Pharma for Japan") still pass | `test_place_…` (32) |
| SPK | High | Third-party or conditional prefixes block; "Origin Bio:" and "Origin Bio Inc.:" are still stripped | `test_spk_…` (5) |
| QW | High | Options and wider territories in a quote block; quotes that confirm the company kept its rights pass | `test_qw_…` (8) |
| QT | High | A U.S. offer is not an offer to an EU or {US, CA} buyer; offers to a U.S. buyer unchanged | `test_qt_…` (6) |
| DATE | High | Year- or month-dated endings containing the as-of date block, with the record named and a question; endings whose whole period precedes the as-of date still clear | `test_date_…` (9) |
| L1c, L3c | Low | Reworded; fixed by PLACE | memo |
| Q10 availability row with no territory | Judgement | Kept: it counts for any buyer, as REREVIEW6 lists | — |
| One-word partner in parentheses (N3) | Judgement | Kept | — |
| Usefulness: "Origin Bio is actively seeking a partner to develop and commercialize … in the U.S.", "… said it is seeking a U.S. partner", "European rights available" (EU buyer), "Chinaco Pharma (China license)", "Greater China: Chinaco Pharma" | Usefulness | Still held back: each has a word the plain forms do not read ("to develop", "said", the adjective "European", a note or a colon), and the reader marks the Partnerships formats unread | — |

## 3. Measured result

| Check | Result |
|---|---|
| Tests | `tests/dealscreen`: 876 pass (816 at revision 7; 60 new). `ruff` and `mypy` clean on `bve.dealscreen` and the CLI |
| Reviewer's scripts (`/tmp/claude-1000/rr7/`), re-run | Top-tier cases: `g1` 43 → 1 (Q10, judgement); `l1` 11 → 3 (L7, L14, L16, which the reviewer marked correct); `u1` 8 → 2 (U3, U6, clean controls); `t1` 1 → 0; `n1`: N3 (judgement). `pf`: every PLACE text has no plain form for its buyer |
| Reviewer's end-to-end workspaces, re-screened from copies | ws_g top-tier placements 6 → 0 (ATG-022 is now rights unresolved); ws_d: only the unflagged control; ws_e, ws_f: none |
| CLDN18.2 (`after_v8/`) | Identical to revision 7 in every screening field of all 62 programs; transaction CSV and memo identical |
| Science | 0 of 62 CLDN18.2 scientific fields changed (`compare.py`). Cross-version: 0 of 312 scientific changes and 0 transaction changes against revision 7. Cycle-4 equivalence: byte-identical, fast path, 4 of 4 |
| Usefulness against general Claude (B) | Unchanged: 10 right / 4 partial / 1 missed against B's 14 / 1 / 0. No advantage is demonstrated |

## 4. Costs and open issues

1. **Still word patterns.** Each round has found phrasings that fit a form and mean something else; revision 8 closes
   the ones found and narrows the "other places" form to a name, but AC14 cannot be self-certified.
2. **A party name with a lower-case word** ("Johnson and Johnson", "Laboratoires de X", "Acme plc") is not a name to
   the form, so such a grant blocks: an over-caution cost.
3. **Quote words.** A quote with "excluding" or "outside" beside a China license now blocks unless a clause says the
   company kept the rights; on real vendor quotes this will hold back some clean programs, each with a question.
4. **Recall is capped by the rights file**; this, not the gate, is why general Claude still leads on usefulness.
