# Response to the R1 adversarial re-review 16 (REREVIEW16.md): revision 18

Revision 18 is R1 on top of revision 17 (3dd6b51), on `dealscreen-mvp`, as of 2026-11-11. Nobody has reviewed it
yet. This file is the implementer's account, not a review: every claim below should be checked by running code. The
reviewer and the implementer are both AI. Neither is a human approval, and nothing here is validation. AC14 is not
claimed.

The implementer recorded no confirmation for any measurement in this file.

## 1. The highest-value fix: endings are read against the deal they end

REREVIEW16 §9 asked for three things, and revision 18 does all three:
- compare every date in an ending or lapse quote with the date of the deal the row ends;
- run the use check after descriptions are folded but before uses are;
- apply the use check to lapses too.

- **DATE-BEFORE (High).** For TERMINATION, RIGHTS_RETURNED and OPTION_LAPSED rows:
  - `rights_gate._ended_day` finds the cited row whose `deal_id` is the row's `related_deal_id` and passes that
    row's date to `quote_problem` (`ended`). When several cited rows carry the deal id, it takes the latest.
  - `read_clause` blocks when any date in the clause ends before it: "dates the ending (2023-01-15) before the deal
    it ends (2024-03-01), so it may describe an earlier deal, and the party to the later deal may still hold rights".
  - DQ1, DQ2, DB1, DB2, DB3 and DB6 block.
  - DB4 (an ending dated after the deal and before the row) still passes, as the review's judgement allows. So does
    a quote with no date.
  - When the cited rows hold no date for the ended deal, only the as-of date is read, as before.
- **USE-AFTER-DESC (Medium).** `use_limit` first writes a description set apart by two commas ("P , an antibody ,")
  as "P ,", so the use after it is read. A description that starts with "for" or "in" is a use, not a description, and
  is not folded.
  - RP1, RP2, RQ1, RP6-RP9, RQ2-RQ4, RP13 and RP14 block.
  - RU5 ("NB-7, an antibody for solid tumors", one comma) still passes, as REREVIEW15 accepted.
- **PARTIAL-LAPSE (Medium).** The same use check runs on OPTION_LAPSED rows: "says the option lapsed only for solid
  tumors, so the option holder may still hold an option for other uses". LP2, LP5, LQ1 and LQ2 block. LPc ("did not
  exercise its option on NB-7") and LP6 (a description, judgement) pass.

## 2. The Low findings and usefulness

- **CUT2.** Closing marks (`"`, `'`, `)`, `.`, `/`, `$`, with spaces) are stripped before the trailing-cut check, so
  `G,"`, `G,”`, `G,)`, `G, .`, `G --"`, `G -.`, `G,'`, `G, /` and `G,$` block.
- **START-CUT.** A quote that starts with ",", ":", ";", "." or "-" (after any opening quote mark or bracket)
  blocks: "looks cut off at the start".
- **DASH-UNICODE.** The em dash and the horizontal bar are written as " -- ". An en dash is a hyphen only between two
  digits ("2024–2025"); anywhere else it is " -- ". DU1-DU3 and DU8 block.
- **TILDE-DATE.** "~" passes only before "$" or before a number followed by "%", "million" or "billion". MK1 and MK2
  ("~2024") block; RM1 and MK7 ("~$20 million") pass.
- **NAME-MARK.** A party or program name that holds a mark other than "&" is not blanked before the mark check, so
  "Chinaco Pharma*" blocks on its "*". "Chen & Wu Pharma" still passes.
- **RESP-ASCII2.** The quote reader now also blocks the following, each with the reason "has the mark …, which
  DealScreen does not read where it stands":
  - an unpaired "(" or ")";
  - an unpaired '"';
  - an unpaired "'" that is not an apostrophe;
  - a "$" before no amount;
  - a "/" at the start of a word or followed by a space.

  MK10-MK14 block. The module docstring now lists each mark, where it is read and where it blocks. I checked it by
  adding every printable ASCII mark to a clean grant at the end, in the middle and at the start. Only "." at the end,
  and "," or ":" in the middle, leave it passing. A pair of quote marks or brackets around the grant passes.
- **Usefulness (UQ24).** "R&D" is read as "research and development", and the rights-kind wording reads "research and
  development (and commercialization) rights". UQ24 passes. A retention of "R&D rights" only still blocks. Any other
  "&" outside a known name still blocks (UQ21, disclosed cost 3).

## 3. Measured (implementer, 2026-11-11)

Script: `scratchpad/fin18/measure.sh` (revision 17's, plus REREVIEW16's probes `p17`, `p17b`, its workspace `ws_r`,
the U1 REVIEW11 workspaces and its probes).

| Check | Revision 17 | Revision 18 |
|---|---|---|
| `tests/dealscreen` | 2,076 pass | 2,316 pass (with U1 revision 12); ruff and mypy clean |
| CLDN18.2 science fields | 0 of 62 | 0 of 62 |
| CLDN18.2 `after_transaction.csv`, memo, `screening.json` | — | byte-identical to revision 17 (memo apart from the generation line) |
| Cycle-4 equivalence | 4 of 4 | 4 of 4 byte-identical |
| Cross-version | 0 of 312 | 0 of 312 |
| REREVIEW16 p17 (top tier) | 50 of 76 | 10 of 76 |
| REREVIEW16 p17b | 21 of 32 | 6 of 32 |
| REREVIEW16 ws_r (programs in a top tier) | 7 | 0 |
| Every earlier probe (p10 … p16b, u10 … u14, cf15) | — | byte-identical to revision 17 |
| End to end ws_h2 … ws_q | — | tier files byte-identical to revision 17 |
| Real CLDN18.2 quotes | 15 / 4 of 17 block | 15 / 4 of 17 block |
| AC12 (`ac12.py`, 193 landscape and rights-file names against `src/`) | 0 hits | 0 hits |

### 3a. What still reaches a top tier

- p17:
  - controls: LPc, CQ10, MK5, MK7;
  - usefulness rows that should pass: MK11 (a paired '"' inside the quote) and MK16 (now read because "R&D" is
    read);
  - by design: OT1 and OT2 (a China grant or exercise "for solid tumors"; the use is outside the buyer territory);
  - judgement rows the review lists: LP6 (a description of the program) and DQ3 (a retention dated before the
    deal; the RT6/RU20 family).
- p17b:
  - controls: RQ5, LQ5, DB5, UQ23;
  - UQ24 ("R&D" in a grant, now read);
  - DB4 (judgement).

Beyond §1-§2, three rows of the same families now block: DU9 "Pharma -exclusive" and DU10 "Pharma- exclusive" (a
hyphen touching only one word; "first- and second-line" is not a cut), and CU6 "C,. G" (a comma closed by a full
stop inside the quote).

### 3b. What changed in the earlier outputs

- No earlier probe changed outcome or reason.
- Three real CLDN18.2 quotes that already blocked now give "looks cut off at the start". Each starts "(Nasdaq: …), a
  …": the company's name was left out when the quote was transcribed, so the reason is accurate. The counts are
  unchanged.
- In the U1 probe outputs, a label that two NCIt codes share now shows the codes (U1 Q7). No class changed.

## 4. Against the reference and general Claude

No CLDN18.2 rights position changed (see §3), so REREVIEW16 §6 stands:
- 0 false unobstructed;
- 1 labelled wrong holder (LM-302);
- 2 missed returns (SKB315, LM-302);
- 2 missed owners.

Usefulness is 8 right / 6 partial / 1 missed, against general Claude's 14 / 1 / 0. No advantage is shown, and none
is claimed.

## 5. Costs and limits

1. An ending or lapse quote that gives a date before the deal it ends blocks, even when the date is the deal's own
   date written as a year before it ("the 2023 license" for a deal recorded 2024-03-01). The two disagree, so an
   analyst must look.
2. A row whose ended deal is not among the cited rows is read only against the as-of date.
3. A full date between the deal and the row's own date (DB4) still passes. An announcement may precede the
   effective date.
4. A use after a closed description blocks in a retention, an ending and a lapse, however short the use.
5. Unpaired quote marks or brackets, a lone "$" or "/", and a quote starting with a mark all block, even when a vendor
   only trimmed the text badly.
6. Unchanged:
   - "&" joining places blocks;
   - a retention "for all indications" blocks;
   - descriptions of the program (RU5, RU6, RU16, PE6, LP6) pass, as judged before;
   - the agent check does not prove a person made a HUMAN record;
   - recall is capped by the rights file.

## 6. The highest-value next issue

Unchanged. The reader fails closed on every path the reviews have found so far. Recall and usefulness are limited by
the input, not the reader:
- the rights file misses returns and owners (LM-302, SKB315);
- 15 of 17 real quotes need one analyst confirmation each.

The next step that would change a BD analyst's answer is a real vendor export (licensed data). It needs the owner's
approval and cannot be done here.
