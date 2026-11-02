# Response to the R1 adversarial re-review 8 (REREVIEW8.md): revision 10

Revision 10 is R1 on top of revision 9 (b3e3fe9), on `dealscreen-mvp`, as of 2026-11-02. Nobody has reviewed it
yet. This file is the implementer's account, not a review: every claim below should be checked by running code. The
reviewer and the implementer are both AI. Neither is a human approval, and nothing here is validation. AC14 is not
claimed.

## 1. The highest-value fix: the quote reader now fails closed

REREVIEW8 §8 asked to stop extending word lists and to pass a cited quote only when every clause is a form the gate
can read. Revision 10 does this in a new module, `rights_quote.quote_problem`, and removes revision 9's deny-lists
from `rights_gate` (`_NAMED_RIGHTS`, `_HEDGE`, `_CAP_SPAN`, `_CORPORATE`, `_VERB_PARTY`, `_TO_PARTY`, `_DESCRIBES`,
`_other_parties`, `_unread_places`). A clause of a cited quote passes only if each of these holds:

1. **Every capitalised name is placed.** A run of capitalised words passes only if DealScreen can place it as:
   - a row party, the program's company or the program (its name, ids and codes), including corporate words and
     legal suffixes after the known name ("Chinaco Pharma Co., Ltd.", "Chinaco Group");
   - a place, and only a place: "Tessaly's U.S." is not a place;
   - a code, month, regulator, exchange, currency or acronym the quote itself defines;
   - a person (after "said" or before a title), an adviser ("… LLC advised …"), or a news source ("… has
     learned").

   Anything else is an unknown name, and the gate asks who it is. A name no longer has to carry a corporate word or
   a listed verb to be found. Passive voice, possessives, colons and abbreviations all give an unknown name.
   "a subsidiary of X" is read as describing a party only directly after a known party (A8).
2. **Every rights word restates the row.** Rights words fall into kinds (grant, develop, transfer, option,
   co-development, end, acquire, hold, reach; `rights_signals`). A clause may use only the kinds of its own row
   type. So a licence may say "licenses", "exclusive" or "develop" but not "option", "holds" or "expansion"; a
   lapse may say "option" (U8).
3. **No time word on an ending** ("will", "effective", "intends", "notice", "may", "disputed", "arbitration",
   "still", "stay", "extended"). A grant or an acquisition may use announcement words ("will receive", "will pay …
   to acquire", "subject to closing"), but no others.
4. **No hedge word on an ending** ("except", "exception", "apart", "most", "only", "partial", "remaining").
5. **On a row that does not cover the buyer territory, no wide word** ("other markets", "everywhere", "all
   markets", "remainder", "NA", "ROTW") **and no buyer-territory place** the row lacks. A place now includes
   states, provinces and member states ("Puerto Rico", "Guam", "Hawaii", "Bavaria").
6. **On an ending, no year later than the row's own.**

Plain forms (the company keeps the rights; no grant was made) still pass whole. Because the reader fails closed, a
word missing from a class only stops that word from counting as harmless. It cannot open a path into the top tiers.

## 2. The other findings

| Id | Revision 10 | Tests |
|---|---|---|
| PARTY2 (A1–A19, B20, W1–W4, W27) | Closed by §1.1. A10 ("Tessaly's U.S. license") was the last one: a run that contains a place is now placed only if nothing but places is left in it | `test_party2_…` (24) |
| HEDGE2 (B1–B15) | Closed by §1.3–1.4 | `test_hedge2_…` (15) |
| WIDER2, WN (W5–W26) | Closed by §1.2 and §1.5. The licensee's own "exclusive option" is an option word on a licence row; "international … rights" is a wide word | `test_wider2_…` (19) |
| PN3 | A party name may not contain a sub-place ("Delaware", "New Jersey"), an area word ("Everywhere Else", "North", "Western Hemisphere", "Remainder", "Upon Exercise", "Thereafter"), a capitalised signal ("ROTW", "WW", "NA", "TBD", "Plus") or any word with a rights, wide, time or hedge signal. After the last company word only legal forms may follow (`rights_allow._name_words_ok`) | `test_pn3_…` (25) |
| FUT2 (E1, E1b, E2, E3, E7) | A grant in the buyer territory dated after the as-of date blocks unless its source date is a day after the as-of date. That covers no source date and a coarse source date, and in live use the as-of date is today. The blocker says it "may have been agreed by the as-of date". A future grant outside the buyer territory no longer blocks (E8, the revision 9 cost) | `test_fut2_…` (7) |
| ACQ-X (F1, F1b, F3) | An acquisition whose acquired party is neither the program's company nor a party to a recorded grant is not applied. It blocks, asks "What rights to this program did X hold when Y acquired it?", and is cited on every path | `test_acq_x_…` (3) |
| LBL-NONE | When rights rows are recorded but none applies on the as-of date, the position is the new `RIGHTS_ROWS_NOT_APPLIED` ("rights rows recorded, none applied on the as-of date"), not `NO_RIGHTS_EVIDENCE` | `test_lbl_none_…` |
| LBL-CODE | Program codes and headline words are no longer reported as companies. A code has a digit, so it is neutral. A Title Case headline is split into signal words and names | usefulness tests |
| Q-FUT2 | The question for a future grant asks "Which rights in the buyer territory does … grant, from when, and was it agreed by <as-of>?" | in `test_fut2_…` |
| L3e, L1e | Follow from PN3: the `assert` note and the memo line no longer accept "… Tessaly Pharma Everywhere Else" | — |
| ACQ-X wording | Follows from ACQ-X: such an acquisition no longer produces an owner position | — |

Judgement items kept, unchanged:
- B18 ("Omega Holdings to acquire Origin Bio"): an owner change, not a third-party grant.
- "Chinaco & Tessaly" (China only).
- U7 ("Chinaco Pharma, a subsidiary of Tessaly Holdings, licenses … for mainland China"): China only.
- E11 (a future acquisition of the company): an owner change.
- S5 (T1/O8), Q10/T6, N-addr, and "U.S. rights: TBD" read as no grant.
- B19 ("closing is expected") now blocks on "expected".

## 3. Measured result

| Check | Result |
|---|---|
| Tests | `tests/dealscreen`: 1,300 pass (1,178 at b3e3fe9; `test_rights_rereview8.py` 122 cases). `ruff` and `mypy` clean on `bve.dealscreen` and the CLI |
| CLDN18.2 (AC8, AC13) | 0 of 62 scientific fields changed (`compare.py` against the frozen baseline). `after_transaction.csv` is byte-identical to revision 9, and so is the memo. Still 0 top-tier programs (`after_v10/`) |
| Cross-version | 0 of 312 programs changed, in science or transaction fields, against revision 9 (synthetic 192, FcRn v1 40, FcRn v2 40, C5 40) |
| Cycle-4 equivalence | byte-identical, fast path, 4 of 4 |
| Reviewer's ws_i, end to end (C3 buyer, as-of 2026-10-29) | The seven top-tier placements of REREVIEW8 §2g are all `RIGHTS_UNRESOLVED` (#1 ATG-022 tier 0; #2 QLS31905, #3 JS107, #4 BL-M05D1, #5 SKB315, #6 Spevatamig, #7 TORL-2-307-ADC tier 1). 0 top-tier programs. Sonesitatug's blocker now names Tessaly Pharma (A8). ASP2138's acquisition of Sideco Bio is not applied, blocks and is asked about (ACQ-X). ASP546C no longer has the false "names ASP546C" blocker (LBL-CODE) |
| Reviewer's ws_h | Unchanged except RC118, whose position is now "rights rows recorded, none applied on the as-of date" instead of `NO_RIGHTS_EVIDENCE` (LBL-NONE). TORL-2-307-ADC stays tier 1 (its quote: the company "retains rights in the rest of the world") |
| Reviewer's probe scripts (`rr9/a`) | Top-tier results: q9 42 → 13, w9 29 → 8, pn9 26 → 5, d9 14 → 7, u9 1 → 4. Every remaining one is a clean control the review lists (G1–G4, G10, G11, G13, G14, B16, B17, C1–C4, C8, C11, C13, C15, C18, C19, S1, S4, S6, U3, U4, U8, E8) or a judgement item in §2 (B18, E9, E11, S5, U7, "Chinaco & Tessaly"). The u9 rise is three usefulness fixes (U3 all caps, U4 headline, U8 lapse quote). REREVIEW7's pf8 accepted forms: 29 → 16, all plain China grants to one or two named licensees |
| Real CLDN18.2 quotes | Each read as the program's only rights evidence (`rr10/real_quotes.py`): 1 of 17 blocks, row 10 (the co-promotion option whose quote gives worldwide rights), as at revision 9. Two fixes came from this check: a currency code ("will pay EUR 422 million") is not a party, and an acquisition may use announcement words ("will pay … to acquire") |
| Usefulness against general Claude | Not re-measured: the CLDN18.2 output is unchanged, so the score stays at 10 / 4 / 1 against 14 / 1 / 0. No advantage is shown |

## 4. Costs and open issues

1. **The reader is still built from words.** Classes replace lists, and an unknown capitalised name now fails
   closed. Lower-case words are read only through their signal classes, though. A lower-case third party with no
   rights or time word ("… with tessaly") is still not found.
2. **Clean press wording that names an unplaced party blocks.** Examples are an investor without "LLC" or a
   university ("discovered at Kestrel University"). Such a quote is held for review with a question naming the
   party. It is not dropped.
3. **A party name that is a known name plus a group word is the same company.** "Chinaco Group" beside a licensee
   "Chinaco Pharma" is read as that licensee's group.
4. **Recall** is still capped by the rights file. No real vendor export has been tested.
5. **AC14 is open** until a fresh adversarial review of revision 10.
