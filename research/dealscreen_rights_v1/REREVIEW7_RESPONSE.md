# Response to the R1 adversarial re-review 7 (REREVIEW7.md): revision 9

Revision 9 is R1 on top of U1 revision 4 (04faab7), on `dealscreen-mvp`, as of 2026-11-02. Nobody has reviewed it
yet. This file is the implementer's account, not a review: every claim below should be checked by running code. The
reviewer and the implementer are both AI. Neither is a human approval, and nothing here is validation. AC14 is not
claimed.

## 1. The highest-value fix: every cited quote is read, with one party rule

REREVIEW7 §8 asked for one fail-closed rule over every cited row's quote, whatever the row type, and for the
`territory <= own` shortcut to go. Revision 9 does both (`rights_gate._quote_problem`). Each clause of a cited quote
is read, and the gate blocks in four cases. In each case it names the reason and asks about the party or place.

- **Another company.** The clause names a company other than the row's grantor, the grantee or the program's
  company. A company is either:
  - a run of capitalised words with a corporate word in it ("Tessaly Pharma", "Omega Holdings", "Merck KGaA"); or
  - a capitalised name that holds, takes or receives rights ("Kappa holds …", "sold to Kappa",
    "Kappa has U.S. rights").

  Places, contract roles ("the Company", "Licensee") and pronouns are not parties. A lone corporate suffix ("Ltd"
  split from "Co., Ltd") is part of the name before it. "X, a subsidiary of Y" describes the row's own party. No
  list of company names is involved.
- **A partial or conditional ending.** On a termination, return, lapse or acquisition, the clause makes the ending
  partial, conditional or not yet in effect, or passes the rights on: "except", "until", "transition", "keeps",
  "remain", "re-licensed", "only", "subject to", "sold" and similar words.
- **An unknown place.** A capitalised name stands just before "rights" and the territory reader does not read it
  as a place ("Puerto Rico rights", "California rights").
- **Outside the row's territory** (as in revision 8, for a row that does not cover the buyer territory). The
  clause names a buyer-territory place the row does not cover, or uses a wider word.

In all four cases, a clause passes if it is a plain form saying that no grant was made or that the company kept the
rights.

Every non-availability quote is now read, whatever words it contains. An availability quote that says nothing about
rights still adds nothing, because the plain-form test already covers it.

## 2. The other findings

| Id | Revision 9 | Tests |
|---|---|---|
| PN-CASE, PN-WORD | A party name may not contain a joining, place or condition word, compared case-folded: and, or, in, to, the, rest, elsewhere, stateside, has, holds, rofn, rofr, first, look, opt-in, option, subject, pending, consent, approval, until, except, and others (`rights_allow._NOT_IN_NAME`). "&" may join name words ("L & M Bio", "Kappa & Kappa") but not two companies ("Chinaco Pharma & Tessaly Pharma"). Lower-case corporate forms ("Chinaco plc") are name words | `test_pn_…` (15 texts, per program and as cell or assertion) |
| COVER R1–R10 | Closed by §1. The plain ending "Alpha Bio returns U.S. rights to Origin Bio" still clears | `test_cover_…` (9) |
| QW2 | Closed by §1. The wider-word list adds "all other markets/countries", "remaining territories", "ex China", "non-China", "beyond", "further territories", "first refusal/look", "right to negotiate", "buy-out", "opt-in" and "ROFO" | `test_qw2_…` (18) |
| FUT | Suppose a grant is dated after the as-of date but its source is dated on or before it. The grant was known on the as-of date. It is still not applied as a grant before it takes effect, but it now blocks, gives a reason ("reported before the as-of date … but effective after it") and asks which rights it grants and from when | `test_fut_…` (4) |
| DATE-AV | An availability statement dated only to a year or month that contains the as-of date is not applied and blocks, as an ending so dated already does. The same applies to an undated statement whose source date is such a year | `test_date_av_…` (4) |
| Q-FUT | When such a grant exists, the question reads "Recorded deals in force on the as-of date cover other territories only", not "Recorded deals cover …" | in `test_fut_…` |
| L3d | Follows from PN-CASE: the `assert` note now says the text is not a plain form | (CLI note uses `accepted_form`) |
| L1d | The ws_h memo no longer has a tier-0 program, so the sentence is not printed for ATG-022 | — |
| Usefulness (§3) | The quote's wider-word list no longer matches these: "option" except as "option to/on/for/over …" followed within the clause by a rights word, "ROW" in lower case, "global" except before rights, licence, territory or commercialisation, "International" except before rights, territories or markets, "except" and "excluding" on their own (the hedge and party rules cover them on endings). The company keeping rights "in the rest of the world", "in the U.S. and the rest of the world" or "for the U.S." is a plain form | `test_usefulness_…` (14) |

Judgement items kept from earlier rounds, unchanged: Q10/T6 (an offer with no place counts for any buyer), N-addr
("Nerida Bio Inc., Tessaly, Japan:" is read as an address), T1/O8 (D1h, D1i, D3e), and "U.S. rights: TBD" read as
no grant.

## 3. Measured result

| Check | Result |
|---|---|
| Tests | `tests/dealscreen`: 1,178 pass (1,099 at 04faab7; `test_rights_rereview7.py` 79 cases). `ruff` and `mypy` clean on `bve.dealscreen` and the CLI |
| CLDN18.2 (AC8, AC13) | 0 of 62 scientific fields changed (`compare.py` against the frozen baseline); 0 of 62 transaction views differ from revision 8, including blockers, reasons and questions. Still 0 top-tier programs (44 rights unresolved, 17 deprioritised, 1 excluded by preference) (`after_v9/`) |
| Cross-version | 0 of 312 programs changed, in science or transaction fields, against revision 8 (synthetic 192, FcRn v1 40, FcRn v2 40, C5 40) |
| Cycle-4 equivalence | byte-identical, fast path, 4 of 4 |
| Reviewer's ws_h, end to end | The six held-out top-tier placements (#1 ATG-022 tier 0; #2 QLS31905, #3 JS107, #4 BL-M05D1, #5 SKB315, #6 Spevatamig tier 1) and RC118 (DATE-AV, tier 0) are now RIGHTS_UNRESOLVED, each with a question naming the third party, date or text. #8 TORL-2-307-ADC ("… retains rights in the rest of the world") moves from unresolved to tier 1, the intended usefulness fix. Science 0 of 62 changed |
| Reviewer's probe scripts (`a/`) | Top-tier results: d8 17 → 10, g8 53 → 20, q8 11 → 8. Accepted forms: pf8 48 → 29, pf8b 3 → 6. Every remaining top-tier result is either a clean control the review lists as held, or a judgement item named in §2. The new top-tier results and accepted forms are all §3 usefulness cases: clean China licences with "option", "row" or "International"; kept rights in the rest of the world; "&", "plc" |
| Real CLDN18.2 quotes | Read with the new rule as if each were the only evidence: 1 of 17 blocks. That is row 10, a mainland-China co-promotion option whose quote gives Merck KGaA worldwide rights, which revision 8 also blocked. Before the three fixes for bylines, suffixes and subsidiaries it was 5 of 17 |
| Usefulness against general Claude | Not re-measured: unchanged at 10 / 4 / 1 against 14 / 1 / 0. No advantage is shown |

## 4. Costs and open issues

1. **The party rule is still a word rule.** A third party written in lower case, or with no corporate word and no
   rights verb ("… with tessaly", "Tessaly co-commercialises"), is not found. A news byline that contains a company
   word ("Biotech Wire has learned") blocks a clean ending (`test_cost_…`).
2. **"Kappa and Kappa"** and other names that contain a joining word are refused as party names.
3. **A parent named as "a subsidiary of Y"** is read as describing the row's party. A quote that uses that phrase
   for a real third party would pass this check.
4. **FUT keeps the deal unapplied.** DealScreen still does not treat a known future grant as an encumbrance. It
   blocks the top tiers and asks instead.
5. **Recall** is still capped by the rights file. No real vendor export has been tested.
6. **AC14 is open** until a fresh adversarial review of revision 9.
