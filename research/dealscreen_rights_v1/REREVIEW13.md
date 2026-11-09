# Adversarial re-review 13: cycle R1 revision 14, rights evidence (CLDN18.2)

**AI-SIMULATED INTERNAL REVIEW.** I am an AI (Claude) playing a skeptical pharma BD analyst and auditor. I am not a
human reviewer. I approve nothing, and nothing here is validation. I did not trust REREVIEW12_RESPONSE.md. I checked
each claim by running code or reading outputs. I report only what I ran or read.

## Scope and method

- Revision 14 is commit 624b2f0 (HEAD of `dealscreen-mvp`). SHA-256 of all 37 files in `src/bve/dealscreen/` recorded
  at the start (`/tmp/claude-1000/rr14/sha_start.txt`) and at the end (`sha_end.txt`): identical (§10).
- All my scripts and outputs are in `/tmp/claude-1000/rr14/`. Harness `h14.py` and `a/lib14.py` are copies of the
  previous reviewer's `h13.py` and `lib13.py`. Per-program cases go through `screening.program_transaction`. Defaults
  as in REREVIEW11/12: company "Nerida Bio", program NB-7, buyer {US}, as-of 2025-06-01, max age 730 days,
  `encumbered_rights: deprioritize`. "C" = "Chinaco Pharma licenses NB-7 for mainland China"; "China license" =
  Nerida Bio → Chinaco Pharma, exclusive, mainland China, 2025-01-01. Every party is fictional; URLs are
  `example.test`.
- New probes: `a/p14.py` (57 inputs), `a/p14b.py` (11), `a/u14.py` (18 realistic clean sentences), `a/dbg14.py`
  (masked clause, template text, places, verdict). End to end: `e2e/ws_o` = a copy of `~/.cache/rights_v1/fin14_ws`
  with the 17 transcribed CLDN18.2 rows plus my 8 fictional rows Z01–Z08 (`e2e/rights_o.csv`). Confirmation tests:
  `conf/conf14.sh` on `conf/ws_conf` (a copy of my `e2e/ws_i2`).
- **Confirmations I recorded (AI-recorded tests, scratch copy only):** `conf/ws_conf` dec:00001 (CONFIRMED, kind
  HUMAN, reviewer `rr14-ai-test`, rationale "AI-RECORDED TEST BY REREVIEW13 (an AI reviewer); NOT A HUMAN
  CONFIRMATION", recorded through the CLI with `env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT`) and dec:00002 (its
  WITHDRAWN). No other HUMAN record was made. Three further attempts (CLI, CLI with empty variables, Python API) were
  refused, as intended. No original workspace, committed output or measurement in this report uses them.

## Summary

- **The response's fixes hold on the inputs they name.** Every REREVIEW12 attack input blocks; my re-runs of all
  earlier probes (p10 … p13b, u10 … u13) are byte-identical to the implementer's `fin14/out`. ws_n has 0 top-tier
  programs. CLDN18.2 output is unchanged (CSV byte-identical to `after_v13`; memo identical apart from the generation
  line; 0 of 62 science fields changed). The API now refuses a rights-row confirmation in this AI shell, an empty
  variable counts, and WITHDRAW-STALE is closed.
- **The new retention check adds places together.** `_read_retention` takes the union of every place in the clause.
  A clause that names a scope and then an exclusion ("retains worldwide rights to NB-7, excluding the United
  States", "retains global rights to NB-7 outside the United States", "retains ROW rights excluding the U.S.")
  covers the US by union and passes. The quote says the US is not retained. Tier 1; on a termination row, RETURNED
  tier 1. End to end: QLS31905, JS107, Spevatamig (`ws_o`).
- **Partial retention still passes when the part is a verb or an indication:** "retains all rights to develop NB-7
  in the United States", "… to commercialize …", "the rights to market and sell …", "U.S. rights to NB-7 for gastric
  cancer". The response says partial retentions block. End to end: ATG-022.
- **An elision is not read.** "[...]" and "(...)" are dropped by the tokenizer, so a quote that itself says text was
  removed passes. End to end: BL-M05D1.
- **Usefulness:** payment sentences now pass (UC33, UC34, and my UC40). 8 of my 18 realistic clean sentences are
  held back without a sound reason (two-verb payment sentences, "full rights", "will be responsible for", unlisted
  multi-word dateline cities, "Following the termination, …"). Real CLDN18.2 quotes: still 15 of 17 block directly,
  4 of 17 through the gate. Against general Claude the score is unchanged at 8 / 6 / 1 (B 14 / 1 / 0): no advantage
  is shown.

Definite new errors (not reported in REREVIEW12.md). None occurs in the CLDN18.2 output.

| Severity | Introduced by revision 14 | Claimed fixed, fails on a close variant | Older, first reported here | Total |
|---|---|---|---|---|
| High: tier 0 or 1 while a third party may hold buyer-territory rights, or on contrary evidence | 0 | 1: RET-PLACE2 (the union is new code) | 0 | **1** |
| Medium: wrong owner, a wider grant read as the row, a process hole | 0 | 1: RET-PARTIAL2 | 1: ELISION | **2** |
| Low: wording, unrealistic input, replay-only | 1: RET-REASON | 0 | 2: DATELINE-DATE, HEADLINE-1WORD | **3** |

Judgement calls and usefulness costs are listed separately (§2g, §4) and not counted.

## 1. REREVIEW12_RESPONSE.md, claim by claim

| § | Claim | Verdict | Evidence (run or read) |
|---|---|---|---|
| 0 | No confirmation recorded by the implementer for any measurement | **Unverifiable; consistent** | No decision log in `fin14/out/ws_*` that I copied holds a CONFIRM_RIGHTS_ROW record that changes a tier I measured; my re-screens match theirs |
| 1 | RET-GRANTOR: retention counts only when the grantor is one legal entity with the program's company | **Held** | RG4 blocks ("says a party other than the program's company keeps rights"); ws_n ATG-022 blocks. RG6 (company = licensee) blocks on the owner check |
| 1 | RET-PLACE: the union of the places a retention names must include the buyer territory | **Held for one place. Refuted for two** | RT1–RT3, RT7, RX3 block. But the union is the wrong operation when a second place is an exclusion: RU1 "C; Nerida Bio retains worldwide rights to NB-7, excluding the United States" → tier 1 (§2a, RET-PLACE2) |
| 1 | "The rest of the world" beside the row means everything the row does not grant | **Held as designed; unsafe when combined** | UC36, RW1 pass. ROW1 "Nerida Bio retains ROW rights excluding the U.S." → tier 1: "ROW" is read as everything but CN, then united with "all but US" (§2a) |
| 1 | No place only with "all other rights" / "all remaining rights" | **Held** | RX1 blocks; RU16 ("all remaining rights") passes, RU15 ("all other rights … outside the United States") blocks |
| 1 | Partial and future retentions block (RT4, RT5, RT12) | **Held for the named words. Refuted on close variants** | RT4, RT5, RT12 block. RU7 "retains all rights to develop NB-7 in the United States", RU8 "… to commercialize …", RU9 "the rights to market and sell …", RU10 "U.S. rights to NB-7 for gastric cancer" → tier 1 (§2b) |
| 1 | Not changed: RT6, RT8, RT9/RT10 still pass | **Held (disclosed)** | p13 tags RT6, RT8, RT9, RT10 are TOP |
| 2 | HEADLINE3: a multi-word dateline city must be on `_MULTI_WORD_CITIES` | **Held** | DL1, DL2 and ws_n BL-M05D1 block. A one-word "city" may still be any word: "TAKEOVER, Mass., March 3, 2025 /PRNewswire/ -- C" → tier 1 (HEADLINE-1WORD, Low, §2e) |
| 2 | "Province" allowed after a region part | **Held** | DL7 / UC35 pass |
| 2 | UNPLACED2: signing sentences need a place unless the row covers the buyer territory | **Held** | SG1–SG4, SG6, X19 block; ws_n TORL blocks; SG7 and SG9 (with place) pass, SG10 (option signing, no place) blocks |
| 2 | ACQ-TWO2: rival acquirers grouped by `_entity_key` | **Held** | AQ1, AQ2 block; AQ5 ("NERIDA BIO"), AQ6 ("Nerida-Bio"), AQ7 ("Nerida Bio, Inc.") block "who owns it is not established" |
| 2 | SUBSID: subsidiary clause removed only when the parent is the company | **Held** | SB1–SB3, ws_n JS107 block; SB4 ("Chinaco Pharma, a wholly owned subsidiary of Nerida Bio, licenses …") passes, as designed |
| 2 | PUNCT: a "?" blocks; "I found no realistic quote where [other punctuation] changes who holds rights" | **"?" held. Second sentence refuted** | PU1 blocks. EL1 "Nerida Bio granted Chinaco Pharma exclusive rights to NB-7 [...] in mainland China" → tier 1; the quote itself says text was removed (ELISION, §2c) |
| 2 | ROW12-REASON: "worldwide rights, excluding …" is one place; row 12 now blocks on "shares … rights equally" | **Held** | `real_quotes.out` line 36: row 12 DIRECT "is not one of the sentences DealScreen reads as restating the row" (revision 13: "names CN/HK/KR/MO/TW …") |
| 2 | CONFIRM-API: `DecisionLog.record` refuses CONFIRMED in an agent shell, even with an empty variable | **Held. Limit wider than stated** | C1 (CLI), C2 (`CLAUDECODE=` empty), C3 (Python API) all "REFUSED: this shell is run by an AI agent (CLAUDECODE is set)". But the list holds 2 of the 10 `CLAUDE*` variables set in this shell; with only those two removed `agent_shell()` returns None while `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID` and six others are still set (C4), and C6 recorded a HUMAN confirmation. The response's limit "an agent that unsets the variable" covers this |
| 2 | WITHDRAW-STALE: a withdrawal removes every version; empty withdrawal refused | **Held** | C5, C10 "REFUSED: no confirmation of this row or an earlier version of it is recorded"; C8 "rx:c2044250:28 CONFIRMED_EARLIER_VERSION -> WITHDRAWN"; C9 after reverting the row: TORL blocked |
| 2 | UC33, UC34 pass; UC37, UC38 still block | **Held** | `prev/u13.out`: 6 of 8 pass; UC37, UC38 block |
| 2 | O4: the memo keeps the decision id | **Held (unchanged)** | C6 reason "…recorded as a human analyst (DealScreen cannot verify this; dec:00001, 2026-11-08)…" |
| 2 | Tests: `test_rights_rereview12.py` 49 tests; `test_rights_rereview10.py` no longer expects the payment sentence to block | **Held** | 49 collected. The rereview10 edit removes one entry from `REV12_BLOCKED`; it matches the new payment templates and loosens no other expectation |
| 3 | `tests/dealscreen` 1,803 pass; ruff and mypy clean | **Held** | 1,803 passed, 5 warnings (147.4 s); ruff "All checks passed!"; mypy "Success: no issues found in 37 source files" |
| 3 | CLDN18.2: 0 of 62; CSV and memo byte-identical to revision 13 | **Held** | `compare.py` "AC8 scientific fields changed: 0 of 62"; my CSV `cmp`-identical to `after_v13`; memo identical without the generation line. The JSON differs from `after_v13` only in `unknown_diagnostics` of 3 programs (U1 revision 8) |
| 3 | Cycle-4 equivalence 4 of 4 | **Held** | 4 of 4 `byte_identical: true`, `fast_path: true` (`/tmp/claude-1000/rr14/equiv.json`); tracked file md5 `94450c24…` before and after |
| 3 | p13 11/41, p13b 2/13, ws_n 0, p12 26/93, p12b 10/32, p12c 6/13, p12d 0/6, p10 0/75, p11 5/75; other workspaces unchanged | **Held** | All 17 probe outputs `cmp`-identical to `fin14/out`; tiers and memos of ws_h2, ws_i2, ws_j2, ws_l, ws_m, ws_n identical (top-tier counts 3, 2, 0, 0, 0, 0) |
| 3a | What still reaches a top tier in p13/p13b is a control, a usefulness row or a disclosed judgement row | **Held** | p13 TOP: RT0, RT6, RT8, RT9, RT10, DL4–DL9; p13b TOP: SG5, RX7 |
| 4 | Usefulness: 7 of 43, 16 of 24, 6 of 8, 15 of 17 direct, 4 of 17 gate | **Held** | `prev/u10.out` "HELD BACK 36 of 43"; `u12.out` 16 of 24; `u13.out` 6 of 8; `e2e/real_quotes.out` 15 / 4 |
| 5 | REREVIEW12 §6 stands (0 false unobstructed, 1 labelled wrong holder, 2 missed returns, 2 missed owners; 8/6/1 vs 14/1/0) | **Held** | No position changed (§6) |
| 6 | Costs 1–5 | **Held, with additions** | Add: the retention union (§2a), the elision (§2c), and the narrow agent-variable list (C4) |

## 2. Paths into the top tiers

Outputs copied from `a/p14.out`, `a/p14b.out`. `NOT_ENC/T1` = `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE /
NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder=None owner='Nerida Bio'`, no blocker. `RET/T1` =
`RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder='Nerida Bio' owner='Nerida Bio'`, no blocker.
Expected in every row of §2a–2c: blocked, naming the clause.

### 2a. RET-PLACE2: the retention adds an exclusion to its scope (High; claimed fixed: RET-PLACE)

| Id | Row | Quote | Output |
|---|---|---|---|
| RU1 | China license | "C; Nerida Bio retains worldwide rights to NB-7, excluding the United States" | NOT_ENC/T1 |
| RU2 | China license | "C; Nerida Bio retains global rights to NB-7 outside the United States" | NOT_ENC/T1 |
| RU3 | China license | "C; Nerida Bio retains worldwide rights to NB-7 outside of the United States" | NOT_ENC/T1 |
| RU4 | China license | "C; Nerida Bio retains ex-U.S. rights to NB-7 worldwide" | NOT_ENC/T1 |
| RU19 | China license | "C; Nerida Bio retains worldwide rights to NB-7 except the U.S. and Canada" | NOT_ENC/T1 |
| ROW1 | China license | "C; Nerida Bio retains ROW rights excluding the U.S." | NOT_ENC/T1 |
| RU18 | China option | "Nerida Bio granted Chinaco Pharma an option on NB-7 in mainland China; Nerida Bio retains global rights to NB-7, excluding the United States" | NOT_ENC/T1 |
| RU5 | US license D1 + termination | "Alpha Bio terminated the U.S. license with Nerida Bio; Nerida Bio retains worldwide rights to NB-7, excluding the United States" | RET/T1 |
| ws_o QLS31905 | Z01 China license | "Chinaco Pharma licenses QLS31905 for mainland China; Qilu Pharmaceutical retains worldwide rights to QLS31905, excluding the United States" | memo "#1 QLS31905: no third-party grant in evidence; rights position: no grant over the buyer territory per evidence (recorded grants do not cover US; …)" |
| ws_o JS107 | Z03 | "…; NingBo Junyan Hongshi Biosciences retains ROW rights excluding the U.S." | memo "#3 JS107: no third-party grant in evidence" |
| ws_o Spevatamig | Z05 US license + Z06 termination | Z06 "Alpha Bio terminated the U.S. license with Phanes Therapeutics; Phanes Therapeutics retains global rights to Spevatamig outside the United States" | memo "#5 Spevatamig (PT886): no third-party grant in evidence; rights position: rights returned per evidence" |

Controls that block: RT1–RT3 (one place), RU6 (one span "worldwide … other than the United States" on a row whose
quote has no grant clause), RU15, RU17 ("rest of the world outside the United States" as one span).

Cause, read in `a/dbg14.py`: RU1 becomes `G retains R rights to P , R` with places `[worldwide]` and `[all but US]`.
`_read_retention` adds them (`covered |= regions`, `rights_template.py:616-622`), so the union is every region and
`buyer <= covered` holds (`:624-627`). The template allows two places (`what` has `(?:R )?` and `_PROGRAM` is
`P(?: R)?`, `:470-475`, `:398`). `_world_first` (`:157-170`) joins "worldwide rights, excluding X" only when the
exclusion follows "rights" directly; with "to NB-7" in between it does not. ROW1: "ROW" alone does not parse, so
`_with_rest_of_world` (`:600-605`) reads it as everything the row does not grant, which is then united with "all but
US". A BD analyst reads every one of these quotes as "the US rights are not with the company". Realism: moderate;
"retains worldwide rights to X outside of the U.S." is common phrasing when a U.S. deal exists elsewhere.

### 2b. RET-PARTIAL2: a partial retention written with a verb or an indication (Medium; claimed fixed: RT4, RT5)

| Id | Quote (China license) | Output |
|---|---|---|
| RU7 | "C; Nerida Bio retains all rights to develop NB-7 in the United States" | NOT_ENC/T1 |
| RU8 | "C; Nerida Bio retains all rights to commercialize NB-7 in the United States" | NOT_ENC/T1 |
| RU9 | "C; Nerida Bio retains the rights to market and sell NB-7 in the United States" | NOT_ENC/T1 |
| RU10 | "C; Nerida Bio retains U.S. rights to NB-7 for gastric cancer" (program text "gastric cancer") | NOT_ENC/T1 |
| ws_o ATG-022 | Z02 "Chinaco Pharma licenses ATG-022 for mainland China; Antengene Biologics retains all rights to develop ATG-022 in the United States" | memo "#2 ATG-022: no third-party grant in evidence" |

Cause: the partial check looks only for "development rights" or "commercial(ization) rights"
(`rights_template.py:631`), but the object of `_retention` allows "rights to <verbs> P" (`:472`, `{_DEV_LIST}`),
and `_PURPOSE` folds "for gastric cancer" after the program (`:344`, `:377`). The response itself treats a partial
retention as a block (RT4, RT5); these are the same statement in other words. Medium: the partner who holds the
other half is unnamed. RU10 needs the indication written in lower case in a landscape field; in ws_o (title case)
Z08 blocked, but for the wrong reason (§2e).

### 2c. ELISION: an omission mark is not read (Medium; older, first reported here)

| Id | Row | Quote | Output |
|---|---|---|---|
| EL1 | China license | "Nerida Bio granted Chinaco Pharma exclusive rights to NB-7 [...] in mainland China" | NOT_ENC/T1 |
| EL2 | China license | "Nerida Bio granted Chinaco Pharma exclusive rights to NB-7 (...) in mainland China" | NOT_ENC/T1 |
| EL4 | US license + termination | "Alpha Bio terminated the [...] license with Nerida Bio" | RET/T1 |
| EL7 | China license | "C; Nerida Bio retains [...] rights to NB-7 in the United States" | NOT_ENC/T1 |
| ws_o BL-M05D1 | Z04 | "Sichuan Baili Pharmaceutical granted Chinaco Pharma exclusive rights to BL-M05D1 [...] in mainland China" | memo "#4 BL-M05D1: no third-party grant in evidence" |

Control: EL3 (Unicode "…" without brackets) blocks, because "..." ends a clause. Cause: `_WORD`
(`rights_template.py:271-272`) matches marks, words and commas only, so `[`, `]`, `(`, `)` and `.` are skipped and
the omitted text is never seen; `_unreadable` checks only non-ASCII. Vendor deal databases often excerpt with "[...]".
The omitted words may be "U.S. and" (EL1) or "U.S. portion of the" (EL4). The response says other punctuation does
not change who holds rights; an omission mark is the source saying "something here was not quoted".

### 2d. Payment sentences (no new path found)

Payment sentences cannot carry a holder or a wider place: PY3 ("for worldwide rights"), PY4 ("royalties on net sales
in the United States"), PY6 (a second payee), PY7 ("upon exercise"), PY10, PY12 (a 2026 date), PY13, PY14 all block.
PY1, PY2, PY5, PY11 pass. Judgement, not counted: a quote that is only a payment ("Chinaco Pharma paid Nerida Bio $20
million", PY8; on an option row, PY9; ws_o TORL-2-307-ADC) passes, although it says nothing about territory or what
was licensed. Revision 14 blocks X19 ("G and E entered into a license agreement", no place) for exactly that reason
("reads as the whole program"). The two rules disagree.

### 2e. Low findings

| Id | Input | Output | Expected | Cause |
|---|---|---|---|---|
| HEADLINE-1WORD | DL16 "TAKEOVER, Mass., March 3, 2025 /PRNewswire/ -- C"; DL15 "DIVESTITURE, U.S., …"; DL10 "TESSALY-CONTROLLED, U.S., …"; DL11 "TESSALY, U.S., …" | NOT_ENC/T1 each | blocked: a one-word "city" that is no city | `_city_ok` accepts any one word that passes `_name_ok` (`rights_quote.py:232-236`). Disclosed as design; low realism |
| DATELINE-DATE | DT1 US license + termination "BOSTON, Mass., March 3, 2026 /PRNewswire/ -- Alpha Bio terminated the U.S. license with Nerida Bio" (as-of 2025-06-01; row date 2025-01-15) | RET/T1 (also with the row's source date 2026-03-03, DT1s) | blocked, as DT3 (the same date in the body) is: "may be after the as-of date" | `_strip_dateline` removes the date unread (`rights_quote.py:203-214`); the ledger judges the row by its event date. Matters only for a historical as-of |
| RET-REASON | ws_o Z08 "…; Sichuan Kelun-Biotech Biopharmaceutical retains U.S. rights to SKB315 for gastric cancer" | blocked, reason "names US, which the row's own territory (CN) does not cover" | blocked, with a reason about the retention | a retention that misses `_retention` falls to the grant place check (`rights_template.py:646-654`); the reason calls a kept right a granted one |

### 2f. What held (selected)

RG4, RG6 (non-company grantor), RT1–RT3, RT7, RX1, RX3, RU6, RU11, RU15, RU17, RW2, RW3; DL1, DL2 (headlines),
DL13/UC49–UC51 (unlisted cities block, never pass); SG1–SG4, SG6, SG10; AQ1, AQ2, AQ5–AQ7; SB1–SB3, SB6; PU1;
PY3–PY14 except the payment-only rows.

### 2g. Judgement calls (not counted)

- RU14 "Nerida Bio kept U.S. rights to NB-7" and RU20 "retained … in 2019": past tense says nothing about now (as RT6).
- RG7: the landscape names the licensee ("Chinaco Pharma") as the program's company and the only row is its
  sublicense; "Chinaco Pharma retains all rights … in the United States" passes with owner Chinaco. With that input
  DealScreen cannot know a licensor exists.
- SG8: a signing sentence whose only place is on the royalties ("… plus royalties on net sales in mainland China")
  satisfies the place rule.
- PY8/PY9 payment-only quotes (§2d).
- The agent-variable list (C4): 2 of the 10 `CLAUDE*` variables in this shell are checked. A prefix test would catch
  an agent that removes only the two listed names; nothing catches one that clears its environment.

## 3. The confirmation (CONFIRM_RIGHTS_ROW)

Run by `conf/conf14.sh` on `conf/ws_conf` (TORL-2-307-ADC, row 28, event `rx:9d396ce9:28`, blocked on "Chinaco
Pharma licenses China rights and also receives an exclusive option"). Output: `conf/conf14.out`.

| # | Input | Output (copied) | Verdict |
|---|---|---|---|
| C1 | CLI `decide … --new-state CONFIRMED --reviewer-kind HUMAN` in this shell | "REFUSED: this shell is run by an AI agent (CLAUDECODE is set); …" | held |
| C2 | same with `env CLAUDECODE= CLAUDE_CODE_ENTRYPOINT=` | same refusal | held (REREVIEW12 C3 closed) |
| C3 | Python `ws.decision_log().record(…, reviewer_kind=HUMAN, context=…)` | "REFUSED: this shell is run by an AI agent (CLAUDECODE is set) …" | held (REREVIEW12 C-API closed) |
| C4 | `agent_shell(env)` with only `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT` removed (no record) | "agent_shell -> None", while `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID`, `CLAUDE_CODE_EXECPATH` and 5 more are set | limit (judgement) |
| C5 | WITHDRAWN with nothing recorded | "REFUSED: no confirmation of this row or an earlier version of it is recorded, so there is nothing to withdraw" | held |
| C6 | AI-recorded test: `env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT decide … CONFIRMED` | "recorded dec:00001"; TORL `NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, reason "the quote on rights row 28 (license) was confirmed as restating the row by rr14-ai-test, recorded as a human analyst (DealScreen cannot verify this; dec:00001, 2026-11-08); it is not read again" | disclosed limit |
| C7 | re-import with row 28's quote changed (adds "; Tessaly Pharma holds U.S. rights") | TORL `RIGHTS_UNRESOLVED`, blocker quotes the changed text | held |
| C8 | withdraw through the changed row's id, in the agent shell | "rx:c2044250:28 CONFIRMED_EARLIER_VERSION -> WITHDRAWN" | held (withdrawal is allowed in an agent shell; that is the safe direction) |
| C9 | re-import the original file | TORL blocked | held (WITHDRAW-STALE closed) |
| C10 | withdraw again | refused, nothing to withdraw | held |

What a confirmation binds to (read, `rights_model.py:85-107`, `review.py:181-202`): the hash covers external id,
deal, related deal, type, parties, territory as written, exclusivity, dates, status, URL and quote, so a changed row
loses it and another program cannot share it. A withdrawal now also removes every stored confirmation with the same
program, deal and type (`row_key`); two different rows of one deal and type therefore withdraw together (safe
direction), and the "earlier version" note may name a sibling row (read, not run; wording). Not bound: buyer
territory and as-of date (REREVIEW12 noted; unchanged). A confirmed row is still read by the ledger and for party
notes; only its quote is skipped (`rights_gate.py:284-292`). The decision log is per workspace; a copied log carries
its confirmations to the copy (by design). Only `ReviewerKind.HUMAN` records confirm (`review.py:183`);
`apply-fixture` records SYNTHETIC_FIXTURE and is refused (`review.py:276-277`). Outputs say who confirmed and that
DealScreen cannot verify it (C6).

## 4. Over-caution and usefulness

These are usefulness costs, not safety errors.

| Measure | Result | Source |
|---|---|---|
| REREVIEW10's 43 clean cases | 7 pass (response: 7) | `prev/u10.out` "HELD BACK 36 of 43" |
| REREVIEW11's 24 sentences | 16 pass (response: 16) | `prev/u12.out` |
| REREVIEW12's 8 sentences | 6 pass (response: 6) | `prev/u13.out` |
| Real CLDN18.2 quotes, directly / through the gate | 15 of 17 / 4 of 17 block | `e2e/real_quotes.out` (= `fin14/out`) |
| My 18 realistic sentences (`a/u14.py`) | 8 pass; 8 held back without a sound reason; 2 blocks I judge sound | `a/u14.out` |

Clean cases held back (reviewer-written, fictional; each `RIGHTS_UNRESOLVED`):

| Id | Quote | Why it blocks |
|---|---|---|
| UC41 | "Nerida Bio will receive an upfront payment of $20 million and is eligible to receive up to $200 million in milestone payments" | two payment verbs in one clause |
| UC42 | "… up to $200 million in development and sales milestones, as well as tiered royalties on net sales" | "as well as" |
| UC43 | "Chinaco Pharma obtains exclusive rights to NB-7 in Greater China; Nerida Bio retains full rights to NB-7 outside of Greater China" | "full" |
| UC47 | "Chinaco Pharma will be responsible for the development and commercialization of NB-7 in mainland China" | no template |
| UC49–UC51 | datelines "NORTH WALES, Pa.", "SOUTH PLAINFIELD, N.J.", "WEST LAFAYETTE, Ind." | multi-word city not on `_MULTI_WORD_CITIES` (disclosed cost) |
| UC54 | "Following the termination, Nerida Bio regains U.S. rights to NB-7" | "Following" read as a name |

Sound blocks: UC53 ("has notified … of its decision to terminate": not yet ended), UC55 ("regained worldwide
rights" on a U.S. row: wider than the row). Passing: UC40 (one-clause upfront + milestones + royalties), UC44
("retains global rights outside of China"), UC45, UC46 (dateline, tickers, "today announced that it has entered
into …"), UC48, UC52, UC56, UC57.

Judgement on usefulness: the response's counts are honest. Payment sentences were the most common clean lines and
now pass, which is a real gain. A real multi-sentence release still nearly always needs one analyst confirmation
(15 of 17 real quotes), and one confirmation per row, kept across re-imports of an unchanged row (C5 in REREVIEW12,
C7–C9 here), is a fair cost for a deal list of this size. The dateline city list will keep producing small costs.

## 5. Output honesty

In favour: no memo I produced (CLDN18.2, ws_n, ws_o) calls a program available or open; "open" and "available"
occur only in the fixed boilerplate ("one open gate", "availability must be evidenced"). No position, tier or action
code appears in memo prose (0 hits in `cldn_memo.md`, `memo_n.md`, `memo_o.md`). A confirmed row names its confirmer
and says the kind cannot be verified (C6). Every holder shown in ws_o is cited.

| # | Where | Output (copied) | Problem | Cause |
|---|---|---|---|---|
| O5 | `e2e/memo_o.md` #1 QLS31905 | "no grant over the buyer territory per evidence (recorded grants do not cover US; …)" beside the cited quote "…; Qilu Pharmaceutical retains worldwide rights to QLS31905, excluding the United States"; ask "Who holds US rights? Recorded deals cover other territories only" | the reason reads as clean beside a quote that excludes the US | RET-PLACE2 |
| O6 | `memo_o.md` #5 Spevatamig | "rights returned per evidence (… rights returned per source to Phanes Therapeutics …)" beside "Phanes Therapeutics retains global rights to Spevatamig outside the United States" | the reason contradicts the quote it prints | RET-PLACE2 |
| O7 | `memo_o.md` #4 BL-M05D1 | tier 1 beside a quote with "[...]" | the memo prints an elided quote as evidence for a clear position | ELISION |
| O8 | `memo_o.md` #8 SKB315 | "…which names US, which the row's own territory (CN) does not cover" for a retention | reason misnames a kept right as granted | RET-REASON |
| O4 | confirmed row reason | "…dec:00001, 2026-11-08…" | an internal id in memo prose; harmless (unchanged) | `rights_gate.py:288-291` |

The CLI `rights_reading_note` is unchanged by revision 14 (`git diff d6d2d7f 624b2f0 -- src/bve/cli/` is empty);
it speaks only for asserted availability text. No contradiction found.

## 6. CLDN18.2 measured against the reference and B

| Item | Result |
|---|---|
| `after_transaction.csv` (62 programs), my HEAD re-screen of a copy of `fin14_ws` | `cmp`-identical to `fin14/out` and to `after_v13` |
| screening.json vs `after_v13` | 3 screens differ, only in `unknown_diagnostics` (U1 revision 8: [18F]F-RESCA-3A12, DR30303, IBI343) |
| Memo | identical to `after_v13/memo_R1v13.md` without the generation line |
| Scientific fields (`compare.py`, frozen `baseline_ws/screening.json`) | **0 of 62** |
| Tiers | 44 RIGHTS_UNRESOLVED, 17 DEPRIORITIZED, 1 EXCLUDED_BY_BUYER_PREFERENCE; **0 top tier** |

Error classes against `reference_calls.csv`, re-read for the programs with rights evidence and the reference's deal
programs. No position or holder changed, so they are REREVIEW12's:

| Class | Count | Programs |
|---|---|---|
| False unobstructed | **0** | — (no top tier) |
| False encumbrance | 0 definite; 2 likely outdated | EO-3021, SYSA1801 (reference "RETURNED_TO_ORIGINATOR_UNCLEAR"; tool: licensed to Elevation Oncology, deprioritized) |
| Wrong holder | 1, labelled | LM-302 "Turning Point Therapeutics (recorded; conflicting)" |
| Wrong territory | 0 | — |
| Missed return | 2 | SKB315 (`NO_RIGHTS_EVIDENCE`; reference: MSD returned global rights, Aug 2024; not in the rights file), LM-302 (conflicting) |
| Missed owner | 2 (not a false call) | Zolbetuximab, IMAB362 (`RIGHTS_ROWS_NOT_APPLIED`; reference: Astellas via Ganymed) |

Usefulness against general Claude (B) on REREVIEW.md's 15 deal programs: **DealScreen 8 right / 6 partial / 1
missed; B 14 / 1 / 0**. I checked that no position or holder changed; I did not re-score each row. No advantage is
shown.

## 7. Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | ws_o "25 events, 0 rejected rows"; ws_n, ws_h2 … ws_m import logs unchanged; provenance on every evidence line |
| AC2 | PARTIAL | CLDN18.2: no OPEN tier, nothing called available. Held-out: ws_o reaches tier 1 for QLS31905, JS107, Spevatamig (US excluded in the quote), ATG-022 (partial retention), BL-M05D1 (elided quote) |
| AC3 | PARTIAL | Grant places, unplaced grants and signing sentences block. Not met: a retention adds an exclusion to its scope (RET-PLACE2), partial retention by verb or indication (RET-PARTIAL2), elided quotes (ELISION) |
| AC4 | PARTIAL | RX3 and RW2 block. Not met: a termination whose quote says the company keeps only ex-US rights gives RETURNED tier 1 (RU5, ws_o Spevatamig); "terminated the [...] license" passes (EL4); LM-302 still not RETURNED (data) |
| AC5 | PASS for the inputs I ran | Option signing needs a place (SG9 passes with one, SG10 blocks); PY7 ("upon exercise") blocks |
| AC6 | PASS for the inputs I ran | AQ1, AQ2, AQ5–AQ7 block as two acquirers; the position is not CONFLICTING (judgement, unchanged) |
| AC7 | PASS (age) | Staleness unchanged. Note DATELINE-DATE (Low): a dateline after the as-of date is not read |
| AC8 | PASS | 0 of 62; equivalence 4 of 4 byte-identical; JSON differs only in U1 diagnostics |
| AC9 | PARTIAL | Preferences work. 8 of 18 realistic clean sentences and 15 of 17 real quotes still need a confirmation |
| AC10 | PARTIAL | Every applied row is cited; a confirmed row names its confirmer. Not met: memo reasons beside quotes that exclude the US or are elided (O5–O7) |
| AC11 | PARTIAL | Blocked rows ask a specific question; on the §2 paths the ask "Who holds US rights? Recorded deals cover other territories only" ignores the exclusion the quote states |
| AC12 | PASS | 286 added lines of `git diff d6d2d7f 624b2f0 -- src/` checked against 236 CLDN18.2 program, company, licensee and licensor names: only generic hits ("China", "view") |
| AC13 | PARTIAL | IBI343, SHR-A1904 not unobstructed; RC148, FL-301, XNW27011 encumbered; LM-302 CONFLICTING, not returned |
| AC14 | FAIL | 1 new High and 2 new Medium errors on held-out inputs (§2); none in the CLDN18.2 output |

## 8. Remaining issues, ranked

1. **(Safety, High) RET-PLACE2.** A retention clause with two places is read by union, so "retains worldwide rights
   to P, excluding the United States", "global rights … outside the United States" and "ROW rights excluding the
   U.S." pass. End to end: QLS31905, JS107, Spevatamig (a termination read as RETURNED).
2. **(Medium) RET-PARTIAL2.** "retains all rights to develop/commercialize P in the U.S.", "the rights to market and
   sell", "U.S. rights … for <indication>" pass. End to end: ATG-022.
3. **(Medium) ELISION.** "[...]" and "(...)" are not read. End to end: BL-M05D1.
4. **(Usefulness)** 15 of 17 real quotes, 36 of 43, 8 of 24, 2 of 8 and 8 of my 18 earlier clean cases need a
   confirmation; unlisted multi-word dateline cities block.
5. **(Low)** DATELINE-DATE (replay only), HEADLINE-1WORD, RET-REASON wording, a decision id in memo prose.
6. **(Judgement)** payment-only quotes pass while unplaced signing sentences block; past retentions (RT6, RU14,
   RU20); business-word variants (RT9/RT10); the two-name agent-variable list; confirmations not bound to buyer
   territory or as-of date.
7. **(Recall)** The rights file still caps recall (LM-302's and SKB315's returns); no real vendor export tested.

## 9. The single highest-value next fix

Make a retention accept exactly one place span, or none with "all other/remaining rights", and read that span as the
whole retained territory: block a retention clause with two or more place markers (or one built by
`_with_rest_of_world` beside another), and block any retention object other than plain "rights" ("rights to
<verb> P", "rights … for <indication>"). In the same change, block a quote that contains an omission mark ("[...]",
"(...)", "[…]") before tokenizing. These close the High path and both Medium paths with three small checks in
`rights_template._read_retention` and `rights_quote.quote_problem`, and cost no clean case I found (UC44 and UC36
have one place).

## 10. Checks

| Check | Result |
|---|---|
| `tests/dealscreen` at HEAD | 1,803 passed, 5 warnings (147.4 s) |
| `ruff check --no-cache src/bve/dealscreen src/bve/cli/dealscreen.py` | "All checks passed!" |
| `mypy src/bve/dealscreen/` (cache in `/tmp/claude-1000/rr14/mypy_cache`) | "Success: no issues found in 37 source files" |
| `compare.py` (frozen baseline) | "AC8 scientific fields changed: 0 of 62" |
| Cycle-4 equivalence (`rr12/run_equiv.py`, which does not write the tracked file) | 4 of 4 `byte_identical: true`, `fast_path: true`; tracked `cycle4/equivalence_result.json` md5 `94450c24dd45550248f008573c800843` before and after |
| Previous probes re-run (p10, p10b, av10, d10, d10b, rt10, u10, p11, q11, p12, p12b, p12c, p12d, u12, p13, p13b, u13) | all byte-identical to `fin14/out` |
| End to end (CLDN18.2, ws_h2, ws_i2, ws_j2, ws_l, ws_m, ws_n) | tiers and memos identical to `fin14/out`; CSV identical to `after_v13` |
| SHA-256 of `src/bve/dealscreen/*.py` | start and end identical: no file changed during the review |
| Git | no commit, stash or checkout by me; the only new file from me is this report (the U1 reviewer's `REVIEW8.md` also appeared) |
