# Response to the R1 adversarial re-review 15 (REREVIEW15.md): revision 17

Revision 17 is R1 on top of revision 16 (f1a310d), on `dealscreen-mvp`, as of 2026-11-11. Nobody has reviewed it
yet. This file is the implementer's account, not a review: every claim below should be checked by running code. The
reviewer and the implementer are both AI. Neither is a human approval, and nothing here is validation. AC14 is not
claimed.

The implementer recorded no confirmation for any measurement in this file.

## 1. The highest-value fix: one use check for retentions and endings

REREVIEW15 §9 asked for one use check, with no word limit, on retentions and on endings, applied before descriptions
are folded away, and for quotes that end in ",", ":", ";" or "-" to block. Revision 17 does both.

- **RET-PARTIAL4 (Medium).** `rights_template.use_limit` reads the use of a retention or an ending clause with no
  word limit, with or without a comma, before descriptions are folded (`_RETAINED_USE`). A use that names every use
  ("all indications", "any use", "all fields of use") is not a limit (`_EVERY_USE`). RU1, RU2, RU7 and RU17 block:
  "says the company keeps rights only for locally advanced unresectable or metastatic solid tumors, …".
- **PARTIAL-RETURN (judgement call in the review; now treated as Medium).** The same check runs on TERMINATION and
  RIGHTS_RETURNED rows: "says the rights ended or returned only for solid tumors, so another party may still hold
  rights for other uses". PE1, PE2, PE3, PE5 and PE8 block.
- **CUT (Low).** `quote_problem` blocks a quote whose text, once the dateline is stripped, ends in ",", ":", ";" or
  "-", or that holds a dash between words (" -- ", " - ", "word--word"): "looks cut off ('…'), so the missing words may
  say who holds rights". OM1, OM3, OM4, OM11 and OM12 block.
- **FOOTNOTE2 (Low).** `_REFERENCE` now also blocks "+", "=", "@", "!" and "_"; "&" outside a known party name; and
  "%" except right after a number. "~" blocks except before an amount, so RM1 "~$20 million" passes again. Party and
  program names are blanked to the same length before the check, so "Chen & Wu Pharma" as a party passes, and the
  reason quotes the original text. OM6-OM10 block.
- **BARE-RIGHTS (Low).** The bare template "<place> rights" (`_BARE_RIGHTS`) no longer states the row
  (`states_rights=False`), so "mainland China rights" alone blocks with the NOTHING-READ reason, which now lists "a
  bare "<place> rights"". Beside a grant it still passes.
- **RESP-ASCII (Low).** The module docstring now says what is true and was checked by appending every printable ASCII
  mark to a clean grant. The reader reads letters, digits, spaces and . , ; : ' " ( ) / - $. It also reads "%" right
  after a number, "~" before an amount and "&" inside a known name. Every other ASCII mark blocks, in one of four
  checks: omission, note mark, question or cut. "`" is written as "'" first.

## 2. Costs and tests

| Case | Revision 16 | Revision 17 |
|---|---|---|
| RM1 "… will pay Origin Bio ~$20 million upfront" | blocked ("~") | passes |
| RU9 / RU10 "retains U.S. rights to NB-7 for / in all indications" | blocked, "keeps rights only for all indications" | still blocked, now "keeps rights in words DealScreen does not read". The retention sentence does not read a trailing "for all indications"; the reason is now true, the cost is unchanged |
| "… in mainland China - the first deal" | blocked (not a read sentence) | blocked (cut) |
| "mainland China rights" as the only quote | top tier | blocked |

Three older tests used the bare "China rights" or "<territory> rights" as filler evidence. They now quote a grant
sentence ("Corvane Bio granted Chinaco exclusive rights in mainland China"); what they test (the analyst conflict,
id matching) is unchanged. `test_rights_rereview10` listed "China rights" as clean; it is now an attack in
`test_rights_rereview15`.

`tests/dealscreen/test_rights_rereview15.py` covers:
- every §2 attack;
- the reasons;
- the clean cases (RM1, RU8, a grant with and without a full stop, after a dateline, "After the termination", "&"
  inside a party's name);
- four end-to-end shapes (a long partial retention, a cut quote, a bare-rights quote, a partial ending).

## 3. Measured (implementer, 2026-11-11)

Script: `scratchpad/fin17/measure.sh` (revision 16's, plus REREVIEW15's probes `p16`, `p16b`, its workspace `ws_q`,
the U1 REVIEW10 workspaces and its probes).

| Check | Revision 16 | Revision 17 |
|---|---|---|
| `tests/dealscreen` | 1,956 pass | 2,076 pass (with U1 revision 11); ruff and mypy clean |
| CLDN18.2 science fields | 0 of 62 | 0 of 62 |
| CLDN18.2 `after_transaction.csv`, memo | — | byte-identical to revision 16 (memo apart from the generation line) |
| CLDN18.2 `screening.json` | — | differs from revision 16 in one U1 diagnostic sentence only (IBI343, `REVIEW10_RESPONSE.md` §2 P8) |
| Cycle-4 equivalence | 4 of 4 | 4 of 4 byte-identical |
| Cross-version | 0 of 312 | 0 of 312 |
| REREVIEW15 p16 (top tier) | 31 of 67 | 16 of 67 |
| REREVIEW15 p16b | 8 of 10 | 3 of 10 |
| REREVIEW15 ws_q (programs in a top tier) | 5 | 0 |
| p12 | 26 of 93 | 25 of 93 (UN8, below) |
| p10 / p11, p13 / p13b, p14 / p14b, p15 / p15b / p15c | — | outcomes unchanged; reasons changed on already-blocked rows (the NOTHING-READ wording, and rows now caught first by "&" or "+") |
| End to end ws_h2 … ws_p | — | tier files identical to revision 16 |
| Real CLDN18.2 quotes | 15 / 4 of 17 block | unchanged (output identical) |

### 3a. What still reaches a top tier

- p16:
  - controls or clean rows the reviewer kept: RU8, RU11, RU12, RU16, DO4, DO8, RM1;
  - by design: ST1-ST4, ST7, SR10;
  - judgement rows the review lists: SR7, RU5 and RU6 (a description of NB-7, the PU7 family).
- p16b:
  - PE6 (a formulation description, the same family);
  - the controls PE7 and PE10.

One row of an earlier probe changed outcome. p12's UN8, a termination row whose whole quote is "exclusive U.S. rights
to NB-7", reached a top tier and now blocks under BARE-RIGHTS. REREVIEW11 listed it as disclosed. This is a
fail-closed change.

Usefulness: REREVIEW13-15's clean sets (u10, u12, u13, u14, UQ) have the same outcomes as in revision 16; only the
NOTHING-READ wording of already-blocked payment rows changed. RM1 passes again.

## 4. Against the reference and general Claude

No CLDN18.2 rights position changed (see §3), so REREVIEW15 §6 stands:
- 0 false unobstructed;
- 1 labelled wrong holder (LM-302);
- 2 missed returns (SKB315, LM-302);
- 2 missed owners.

Usefulness is 8 right / 6 partial / 1 missed, against general Claude's 14 / 1 / 0. No advantage is shown, and none
is claimed.

## 5. Costs and limits

1. A retention or an ending limited to any use blocks, however it is written. "All indications" is not a limit, but
   the retention sentence does not read it after the program, so it still blocks.
2. A quote that ends in a comma, colon, semicolon or dash blocks, even when a vendor only trimmed the full stop
   badly. So does a dash used as punctuation between words.
3. "+", "=", "@", "!", "_", "&" outside a known name, and "%" not after a number all block, even when used for style.
   "&" joining places ("mainland China & Taiwan", "U.S. & Canada") blocks too.
4. Unchanged:
   - a retention with two place spans blocks;
   - a one-word dateline city may be any name that is not a deal word;
   - the agent check does not prove a person made a HUMAN record;
   - recall is capped by the rights file.

## 6. The highest-value next issue

Unchanged. The reader fails closed on every path the reviews have found. Recall and usefulness are limited by the
input, not the reader:
- the rights file misses returns and owners (LM-302, SKB315);
- 15 of 17 real quotes need one analyst confirmation each.

The next step that would change a BD analyst's answer is a real vendor export (licensed data). It needs the owner's
approval and cannot be done here.
