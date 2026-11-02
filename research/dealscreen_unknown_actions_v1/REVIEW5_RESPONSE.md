# Response to the fifth U1 review (REVIEW5.md): revision 6

Revision 6 is U1 on top of revision 5 (b0388eb), committed with R1 revision 11, on `dealscreen-mvp`, as of
2026-11-02. Nobody has reviewed it yet. This file is the implementer's account, not a review: every claim below
should be checked by running code. The reviewer and the implementer are both AI. Neither is a human approval, and
nothing here is validation. U1-7 is not claimed.

## 1. The two medium findings

**N1 (regression from the D1 fix): "ALL" before a qualifier, population or function word was called a basket.**
`ir._before_basket_word` now reads a capitalised index acronym as the word "all" only before a tumour head, "solid" or
"comers" (the reviewer's suggestion). These are no longer baskets: "Relapsed ALL in adults", "Relapsed or
refractory ALL in adults", "ALL in children", "ALL RELAPSED", "ALL in adults", "ALL relapsed", "ALL patients", "ALL
Adults", "ALL REFRACTORY", "ALL - RELAPSED", "ALL ADVANCED" and "ALL PATIENTS". "ALL COMERS", "SOLID TUMORS (ALL
COMERS)", "ALL SOLID TUMORS" and "STAGE IV SOLID TUMORS" stay baskets.

In the reviewer's end-to-end workspace (`ws_e2e_all5`, re-screened):
- RC118, Q-1802, VBC108 and TQB2103 are UNREADABLE ("not a name the NCIt authority can read"), revision 4's answer;
- AK132 ("RELAPSED ALL") stays BROADER_THAN_REQUESTED.

**N2 (regression from the D3 fix): another target's "negative or positive" cancelled the required target's
negation.** The both-states test now runs on the negated part itself, and on the text written directly after it in
its cell (`dg._both_states`). The second state counts only when it is not followed by "for", "selection" or
"selected". So "X neg/pos", which the slash splits, is still read as both, while "X negative, positive for Y" keeps
the negation. The SOURCE_MAY_NAME sentence now lists the other parts ("also on record: …"), as the reviewer asked.

In the reviewer's end-to-end workspace (`ws_e2e_gas5`, re-screened):
- SG1906 ("not CLDN18.2; HER2 positive or negative") is SOURCE_NAMES_OTHER_TARGETS: "The record names 'HER2 positive
  or negative' … ('not CLDN18.2' states it is not CLDN18.2)";
- AK132 ("CLDN18.2 negative, positive for CD47") is SOURCE_NAMES_OTHER_TARGETS naming 'positive for CD47', with the
  negation shown.

## 2. N3 (low)

| Item | Revision 6 |
|---|---|
| "neg & pos" read as negated | "&" joins the two states |
| An en dash before "negative" missed | "–" and "—" are read like a hyphen before a negation word |
| "negative or low" | Not changed (judgement: expression "low" names the target, per REVIEW3 D2) |
| Quotes cut at the slash ("CLDN18.2 neg"), broken parentheses, "/ or CD3" | Not changed: the parts are the list splitter's, shared by every target diagnostic |

## 3. Measured result

| Check | Result |
|---|---|
| Tests | `tests/dealscreen`: 1,436 pass with R1 revision 11 (`test_unknown_actions.py` 274 cases, 24 new) |
| U1-1 coverage | CLDN18.2 38 of 38; held-out FcRn v1, FcRn v2, C5 and synthetic: no missing or extra diagnostic (`coverage.py`) |
| U1-3 science | CLDN18.2: 0 of 62 science fields against the frozen baseline. `measure.py` lists Zolbetuximab and IMAB362 as changed. The change is in their transaction view, from R1 revision 11 (OWNER-KEY, see `REREVIEW9_RESPONSE.md`), not from U1. Disposition, rank and decisions are unchanged. Cross-version 0 of 312; cycle-4 equivalence byte-identical, 4 of 4 |
| CLDN18.2 actions | `unknown_actions.csv` identical to revision 5 (38 rows). The memo differs from revision 5 only in the two R1 rights lines above |

## 4. Costs and open issues

1. D5, D6 and D7 are open (low), as before.
2. N3's quoting residues are open (low).
3. Word lists remain (J5).
4. U1-7 is open until a fresh adversarial review of revision 6.
