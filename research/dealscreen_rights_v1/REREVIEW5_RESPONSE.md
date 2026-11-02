# Response to the R1 adversarial re-review 5 (REREVIEW5.md): revision 7

Revision 7 is the working tree on `dealscreen-mvp` as of 2026-11-01. Nobody has reviewed it yet. This file is the
implementer's account, not a review: every claim below should be checked by running code. The reviewer and the
implementer are both AI; neither is a human approval and nothing here is validation.

## 1. The highest-value fix: the plain forms read what they accept, in the buyer's terms

REREVIEW5 section 11 found that revision 6's plain forms were word patterns on lower-cased text, so they accepted
texts that fit their words and meant the opposite. Revision 7 changes `rights_allow.plain_form` and the gate around it.

- **Places as written (PF1).** Places are read on the clause as written, before lower-casing, so "U.S." inside a
  party span or after a comma is seen. Every place a clause names is compared with the **buyer territory**, not with
  the U.S.: a "grant over other places only" needs at least one named place, none of them in the buyer territory,
  and a party span that names no place and carries no rights words.
- **Buyer territory (PF4).** `plain_form` takes the territory; the gate passes the buyer's. "Licensed in Europe to
  X" is other places for a U.S. buyer and not for an EU buyer; "Ex-Europe rights available" is not an offer to an
  EU buyer.
- **Subjects (PF2).** "The owner" is no longer the company. "We" and "it" count as the company only when the text is
  a single clause; across clauses a pronoun may point at the party just named, so the text blocks.
- **Notes (PF3).** A clause with a note in parentheses or brackets (other than the company's own name, a year, an
  excluded place such as "(ex-China)", or "(s)") is not a plain form.
- **Unread text never widened.** A plain form no longer accepts a text the reader marks unread, except the company
  keeping its rights ("rights kept by the company"), which the reader does not cover
  (`rights_gate.accepted_form`). The four U.S.-rights texts that revision 5 blocked and revision 6 passed block
  again.
- **Inputs read (OWN, QUOTE).** Ownership words (owned, owner, bought, purchased, merged, spun out, subsidiary,
  parent, holds) are rights words, so "Owned by X" in Partnerships is read and blocks. A rights row's own quote is
  read: an availability row's quote must itself be a plain form; any other row's quote blocks when it names a place
  in the buyer territory that the row's territory does not cover. The blocker quotes it and the question asks what
  the quote says.
- **Contests (LBL).** An understood contrary Partnerships or Geographic Notes text (for a buyer territory containing
  the U.S.) is now a conflict ("Which is current: … Reject the one that is wrong.") rather than an "uncontested"
  block.

## 2. The findings

Per-program cases run through `program_transaction`. The reviewer's scripts in `/tmp/claude-1000/rr6/` were re-run
unchanged against revision 7, with outputs in the implementer's scratch directory. Tests are in
`test_rights_rereview5.py` (72).

| Id | Severity | Revision 7 | Tests |
|---|---|---|---|
| PF1 U.S. in a party span | High | Not a plain form; the PF1 texts on all three fields, landscape and analyst, stay out of tiers 0 and 1 | `test_pf1_…` (16) |
| PF2 pronoun or role subject | High | Not a plain form across clauses; "We retain all U.S. rights" alone still reads as the company | `test_pf2_…` (5) |
| PF3 note inside the text | High | Not a plain form; a year, "(ex-China)" and "(s)" are not notes | `test_pf3_…` (7) |
| PF4 other places for any buyer | High | Read against the buyer territory (EU, US+CA, JP cases blocked); the same grant is other places for a U.S. buyer | `test_pf4_…` (7) |
| OWN ownership words | High | Read; "Owned by", "Bought by", "(owner)", "Merged into", "Spun out to", "Subsidiary of" block and are cited | `test_own_…` (7) |
| QUOTE row quotes | High | Read: ws_e ATG-022 is now rights unresolved, with the quote cited and asked about | `test_quote_…` (4) |
| TER-M {US, CA} buyer | Medium | The U.S.-rights field is read for any buyer territory containing the U.S.; a clear field position is not a clear position for the wider territory; an encumbrance keeps its effect | `test_ter_m_…` (2) |
| ORCD "or" | Medium | "Available for out-licensing or co-development" reads as an offer (tier 0 on the field path; tier 1 beside a China license) | `test_orcd_…` |
| S2 status ending with no source date | Judgement, adopted | Blocks: "ended only by its status '…', which no source date places before the as-of date" | `test_s2_…` (2) |
| NH noted holder or owner | Low | Not shown as holder or owner; the reason quotes it. DealScreen's own labels ("(shared)", "(recorded; conflicting)") are not notes | `test_nh_…` (3) |
| L1b availability sentence | Low | Says which inputs DealScreen read and that it reads row quotes only for places and rights words | memo |
| L2b assertions "read" | Low | A names-only Partnerships assertion is no longer listed as read by the transaction view | memo |
| L3b `assert` note | Low | Gives the gate's own verdict (`accepted_form`) for the workspace's buyer territory and as-of date, including the unread rule | `test_l3b_…` (2); two edited tests |
| LBL | Low | Fixed by PF1 (no false "other places" label) and the contest branch | `a_clean` B3 → CONFLICTING |
| WB | Low | Fixed by the unread rule: the field reads UNKNOWN and the tier is no longer a top tier | ws_f |
| R9 company-party guard breadth | Usefulness | A company's unattached row guards that company's programs only when its territory is unreadable or overlaps the buyer territory | `test_r9_…` (4) |
| Usefulness: "Partnered in China; U.S. rights available", "Worldwide rights (ex-China) available", "Seeking partner(s) … outside China", "Open to partnering discussions", "Open to co-promotion in the U.S." | Usefulness | Tier 1 beside a China license; "Open to partnering discussions" and "Open to co-promotion" tier 0 on the field path | `test_usefulness_…` (5) |
| Usefulness: "(Hong Kong) Limited" | Usefulness | A two-word known region before the corporate form is part of the legal name; a two-word non-region ("(Tessaly Pharma) Inc.") is still a note | `test_two_word_…`, `test_hong_kong_…` |
| One-word partner in parentheses ("(Tessaly) Inc.") | Judgement | Kept: read as a city, as in revision 6 | — |
| R2, R3 name-only ids and company-name variants | Judgement | Kept: guard nothing | — |
| T1, Q1–Q3, S1/S5, I1 | Judgement | Kept as in REREVIEW3/4 | — |

Edited existing tests, each for a stated rule: the `rights_reading_note` wording in `test_rights_rereview3` and
`test_rights_rereview4` (it now names the buyer territory), and the allow-list row "Licensed in Greater China to
Other Pharma U.S. Inc." (PF1: "U.S." is read as written, even inside a name, so the text now blocks; an
over-caution cost on such names).

## 3. Measured result

| Check | Result |
|---|---|
| Tests | `tests/dealscreen`: 816 pass (744 at revision 6; 72 new in `test_rights_rereview5.py`). `ruff` and `mypy` clean on `bve.dealscreen` and the CLI. Full repository suite at revision 6: 13 failures, the same 13 pre-existing ones as revision 5, none in DealScreen |
| Reviewer's scripts, re-run | `p_forms`: no PF1–PF3 text has a plain form. `a_gate`: every PF1–PF4, OWN and QUOTE case is out of tiers 0 and 1; the two still in a top tier are the control A4f (China license + the company as holder, EU buyer) and the names-only Partnerships value "Partner: Tessaly Pharma" (neutral by design). `a_ledger`: the remaining top-tier cases are the reviewer's accepted judgements (S1, S5, T1, T2, Q1–Q3, I2) |
| Reviewer's end-to-end workspaces, re-screened from copies | ws_e top-tier placements 7 → 0 (#6 Spevatamig blocked by S2); ws_f 5 → 0; ws_d: only the unflagged control (Spevatamig, China license only); ws_0 memo and transaction view identical to `after_v6` |
| Usefulness cases (`a_clean`) | Against revision 6, every change is towards the reviewer's expected tier: the Hong Kong holder and company, the five ordinary phrasings and ORCD now reach the top tier; B3 is now CONFLICTING. No case left the top tier |
| CLDN18.2 (`after_v7/`) | Identical to revision 6 in every screening field of all 62 programs; transaction CSV and memo identical |
| Science | 0 of 62 CLDN18.2 scientific fields changed (`compare.py`). Cross-version: 0 scientific changes on 312 assets against the R1 science dump; 0 transaction changes on synthetic, FcRn v1 and C5. FcRn v2: 8 programs no longer show a holder because their landscape holder cell carries a source note ("… (U.S. labeler per FDA label; not a rights statement)"); the reason quotes it; no tier changed (NH). Cycle-4 equivalence: byte-identical, fast path, on all four |
| Usefulness against general Claude (B) | Unchanged: no CLDN18.2 call changed. 10 right / 4 partial / 1 missed against B's 14 / 1 / 0 on the 15 deal programs. No advantage is demonstrated |

## 4. Costs and open issues

1. **The plain forms are still word patterns.** Revision 7 reads places as written and in the buyer's terms, refuses
   notes and cross-clause pronouns, and never widens the reader, but a phrasing that fits a form and means something
   else may still exist. AC14 cannot be self-certified; revision 7 needs a fresh adversarial review.
2. **Row quotes are read only for places and rights words.** A quote that states a condition without naming a place
   ("subject to the partner's consent") is not read on a non-availability row.
3. **Over-caution:** "U.S." inside a legal name ("Other Pharma U.S. Inc.") now blocks a China-license text; noted
   holders are hidden even when the note is harmless (the FcRn v2 labeler notes).
4. **Recall is capped by the rights file** (LM-302's successor, SKB315's return, EO-3021's discontinuation). This,
   not the gate, is why general Claude still leads on usefulness.
