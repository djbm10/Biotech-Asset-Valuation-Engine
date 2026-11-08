# Adversarial re-review 12: cycle R1 revision 13, rights evidence (CLDN18.2)

**AI-SIMULATED INTERNAL REVIEW.** I am an AI (Claude) playing a skeptical pharma BD analyst and auditor. I am not a
human reviewer. I approve nothing, and nothing here is validation. I did not trust REREVIEW11_RESPONSE.md. I checked
each claim by running code or reading outputs. I report only what I ran or read.

## Scope and method

- Revision 13 is commit d6d2d7f (HEAD of `dealscreen-mvp`). SHA-256 of all 37 files in `src/bve/dealscreen/` recorded
  at the start (`/tmp/claude-1000/rr13/sha_start.txt`); see §10 for the end check.
- All my scripts and outputs are in `/tmp/claude-1000/rr13/`. Harness `h13.py` is a copy of the previous reviewer's
  `h12.py`. Per-program cases go through `screening.program_transaction`. Defaults as in REREVIEW11: company "Nerida
  Bio", program NB-7, buyer {US}, as-of 2025-06-01, max age 730 days, `encumbered_rights: deprioritize`. "China
  license" = Nerida Bio → Chinaco Pharma, exclusive, mainland China, 2025-01-01. Every party is fictional; URLs are
  `example.test`.
- "Rev 12" columns come from running the same script with `git archive 55ac585` first on the path
  (`a/run_rev12.py`, outputs `*_rev12.out`). No git state was changed.
- New probes: `a/p13.py` (41 inputs: retention, non-company grantors, subsidiary strips, datelines, punctuation,
  two acquirers), `a/p13b.py` (13: signing sentences with a scope, more retention), `a/u13.py` (8 realistic clean
  sentences), `a/dbg.py` (masked clause, slots, folded text; the plain-form line removed). End to end: `e2e/ws_n` =
  a copy of `~/.cache/rights_v1/fin13_ws` with the 17 transcribed CLDN18.2 rows plus my 11 fictional rows Y01–Y11
  (`e2e/rights_n.csv`). Confirmation tests: `e2e/conf.sh` on `e2e/ws_conf` (copy of my `ws_i2`) and
  `e2e/conf_api.out` on `e2e/ws_conf2`.
- **Confirmations I recorded (all AI-recorded tests, in scratch copies only, reviewer ids `rr13-ai-test` and
  `rr13-ai-test-api`, rationale "AI-RECORDED TEST BY REREVIEW12 (an AI reviewer); NOT A HUMAN CONFIRMATION"):**
  `ws_conf` dec:00001, dec:00003, dec:00005 (CONFIRMED, kind HUMAN, recorded through the CLI with the agent
  variables emptied or unset), dec:00002, dec:00004, dec:00006 (WITHDRAWN); `ws_conf2` dec:00001 (CONFIRMED, kind
  HUMAN, recorded through the Python API in this AI agent shell). `ws_conf_c7` is a copy of `ws_conf` and holds the
  same records. No original workspace, committed output or measurement in this report uses them, except §3, which
  tests them.

## Summary

- **Every REREVIEW11 attack input now blocks.** I re-ran all previous probes; each output is byte-identical to the
  implementer's `fin13/out` (p10, p10b, av10, d10, d10b, rt10, u10, p11, q11, p12, p12b, p12c, p12d, u12). What still
  reaches a top tier there is a control or one of REREVIEW11's judgement rows. All six end-to-end workspaces (CLDN18.2,
  ws_h2, ws_i2, ws_j2, ws_l, ws_m) give the same tiers and memos as `fin13/out`; ws_m now has 0 top-tier programs.
  CLDN18.2 output equals `after_v13` and changes no position; 0 of 62 science fields changed.
- **The new retention sentence is a new door.** `_retention` is checked before the place check and passes any place,
  and its subject is the row's grantor, whoever that is. So "…; Qilu Pharmaceutical retains rights to QLS31905 outside
  the United States" (the company keeps only ex-U.S. rights) and a sublicense row "…; Chinaco Pharma retains all
  rights to ATG-022 in the United States" (a licensee keeps U.S. rights) both give tier 1. Both blocked in revision 12.
- **Press furniture still hides text.** A one-line all-capitals headline whose verb is not on `_HOLD_WORDS`
  ("TESSALY BUYS SICHUAN BAILI, China, March 3, 2026 --") is stripped as a dateline. "<company>, a wholly owned
  subsidiary of <licensee>," is stripped to "<company>", which hides that the licensee controls the company.
- **Older paths that survive:** signing sentences that state a scope but no place ("entered into an exclusive license
  agreement to develop and commercialize NB-7"); two acquirers written "Nerida Bio" and "The Nerida Bio" are not seen
  as rivals (ACQ-TWO groups by `party_key`, succession now by `_entity_key`), so one acquirer silently wins.
- **End to end (`ws_n`):** 7 CLDN18.2 programs reach tier 1 through these paths: QLS31905, ATG-022, JS107, BL-M05D1,
  SKB315, Spevatamig, TORL-2-307-ADC. CLDN18.2 itself has 0 top-tier programs.
- **Confirmation:** keying by content works: a re-import keeps a confirmation, a changed row loses it and shows the
  "earlier version" note, and a withdrawal through the new event id works. But the agent-shell check is in the CLI
  only: in this AI agent shell (`CLAUDECODE=1`) the Python API `DecisionLog.record(..., reviewer_kind=HUMAN)` cleared a
  block, and `CLAUDECODE=` (empty) passes the CLI check. A withdrawal made after the row changed removes nothing, so
  when the vendor reverts the row the withdrawn confirmation clears the block again.
- **Usefulness:** the response's numbers hold (6 of 43; 15 of 24; 15 of 17 real quotes block directly; 4 of 17
  through the gate). Against general Claude the score is unchanged at 8/6/1 (B 14/1/0): no advantage is shown.

Definite new errors (not reported in REREVIEW11.md). None occurs in the CLDN18.2 output.

| Severity | Introduced by revision 13 | Claimed fixed, fails on a close variant | Older, first reported here | Total |
|---|---|---|---|---|
| High: tier 0 or 1 while a third party may hold buyer-territory rights, or on contrary evidence | 2: RET-GRANTOR, RET-PLACE | 1: HEADLINE3 | 0 | **3** |
| Medium: wrong owner, a wider grant read as the row, a process hole | 1: WITHDRAW-STALE | 3: UNPLACED2, ACQ-TWO2, CONFIRM-API | 1: SUBSID | **5** |
| Low: wording, unrealistic input; no realistic tier change | 0 | 1: ROW12-REASON | 1: PUNCT | **2** |

Judgement calls and usefulness costs are listed separately (§2h, §4) and not counted.

## 1. REREVIEW11_RESPONSE.md, claim by claim

| § | Claim | Verdict | Evidence (run or read) |
|---|---|---|---|
| 0 | The implementer, an AI, recorded `dec:00003 jdoe HUMAN …` in a scratch workspace during revision 12 | **Held as a disclosure** | Matches REREVIEW11 §3; ACCEPTANCE.md's added note says the same |
| 0 | "An AI agent that follows these instructions, or runs in a known agent shell, cannot clear a block" | **Refuted for "runs in a known agent shell"** | In this shell `CLAUDECODE=1`. `Workspace.decision_log().record(action=CONFIRM_RIGHTS_ROW, …, reviewer_kind=ReviewerKind.HUMAN, context=ws.decision_context())` recorded `dec:00001 HUMAN rx:9d396ce9:28 CONFIRMED`; after `screen`, TORL-2-307-ADC: `NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, blockers `[]` (`e2e/conf_api.out`). `agent_shell()` is called only in the CLI's `_decide` (`cli/dealscreen.py:139`), not in `DecisionLog.record` (`review.py:226-311`). The CLI check also passes with the variables set but empty: `env CLAUDECODE= CLAUDE_CODE_ENTRYPOINT= bve-dealscreen decide … --reviewer-kind HUMAN` → "recorded dec:00001" (`review.py:437` tests truthiness). The test suite itself records HUMAN confirmations through the API in this shell (`test_rights_rereview10.py:352-363`) |
| 1 | No plain-form path for quotes; `quote_problem` no longer calls `plain_form` | **Held** | Read `rights_quote.py:262-286`; PF1–PF15 all block (`prev/p12.out`, byte-identical to `fin13/out/p12.out`) |
| 1 | `_retention`: the subject is the masked grantor only; a pronoun, "the company", Holdings/Global is never G | **Held as stated. Unsafe as designed** | PF7, PF8, PF12 block. But "the masked grantor" is whoever the row's grantor is: a licensee that sublicenses, or the licensor of an in-licensed program (RET-GRANTOR, §2a). Business-word variants ("Nerida Bio Oncology", "Nerida Bio Pharma") are still masked as G (RT9, RT10; judgement, §2h) |
| 1 | "Whatever place a retention names stays with the grantor, so its place is not checked against the row's territory" | **Refuted as a safety argument** | A retention that names only places outside the buyer territory says the buyer-territory rights are not retained: "Nerida Bio retains rights to NB-7 outside the United States" → tier 1 (RET-PLACE, §2a) |
| 1 | Every character is read; typography mapped; other non-ASCII blocks (NONLATIN) | **Held for characters. Refuted for punctuation** | p12d: 0 of 6 top tier. ASCII punctuation outside `_WORD` (`? : ( ) [ ] " ~ &` …) is still never read: "Chinaco Pharma licenses NB-7 for mainland China?" → tier 1 (PUNCT, Low) |
| 1 | A grant, option or exercise sentence needs a place unless the row covers the buyer territory (UNPLACED, ACQ-OPT) | **Held for the `tp` sentences. Not for signing sentences that state a scope** | AO1–AO3, UN1, UN2, UN5–UN7, UN10 block. SG1 "Nerida Bio and Chinaco Pharma entered into an exclusive license agreement to develop and commercialize NB-7", SG2 "… for the development and commercialization of NB-7", SG4 (option row) "… an exclusive option and license agreement for NB-7" → tier 1 (UNPLACED2, §2c). The response says signing statements "do not say what was granted"; these do |
| 1 | "an option to acquire NB-7" removed from option and exercise sentences | **Held** | AO1–AO3 block; LP11 (lapse) passes as intended |
| 2 | HEADLINE2: one-line city, city words not template/rights/place words, region parts on a list | **Held for HD1–HD4. Refuted on a close variant** | "TESSALY BUYS NERIDA, U.S., March 3, 2025 -- …" and "TESSALY BUYS NB, Mass., …" → tier 1: "buys" is on neither `_HOLD_WORDS` nor `template_words()` (HEADLINE3, §2b) |
| 2 | STRIP-CAPS: named strips refuse names with rights, template or place words | **Held** | HD6–HD8 block |
| 2 | VOCAB2: condition and holder words dropped from field words, also per hyphen part | **Held for the listed words** | QC1–QC5, Q5, Q6, Q9 block. I found no realistic field word left that carries a holder or condition |
| 2 | DEAL-KIND: only a license (or a bare "the agreement") ends a license | **Held** | X4, X5 block |
| 2 | OWNER-THE: succession keyed by `_entity_key` | **Held for OK3. Opened ACQ-TWO2** | OK3 → owner Omega Holdings. But ACQ-TWO's rival check still groups by `party_key` (`rights_ledger.py:197`, `:234`), which keeps "the": "Omega acquired Nerida Bio" + "Sideco acquired The Nerida Bio" → no rival, owner Sideco Bio, tier 1 (§2d) |
| 2 | CONFIRM-KIND: `record` refuses CONFIRM_RIGHTS_ROW without a kind; CLI refuses in a known agent shell | **Held as coded (CLI only)** | C1 "REFUSED: this shell is run by an AI agent (CLAUDECODE is set)"; C2 (variables unset, no kind) "REFUSED: a rights row confirmation states its reviewer kind explicitly". See row 0 above for the API path |
| 2 | CONFIRM-REIMPORT: keyed by content; re-import keeps it; another program never shares it; withdrawal through the new event id removes it | **Held for an unchanged row. Refuted for a withdrawal after a change** | C5: re-import with one row appended (event id `rx:a69d510b:28`) → still tier 1, confirmation kept. C6: withdrawal via the new id → blocked again. C8/C9: after the row changed, a withdrawal through the changed row's id records "UNCONFIRMED -> WITHDRAWN" and removes nothing; re-importing the earlier file brings tier 1 back on the withdrawn confirmation dec:00005 (WITHDRAW-STALE, §3). External id is hashed (`rights_model.py:90-91`), so a row of another program cannot share a hash |
| 2 | "earlier version of this row" note is reachable | **Held** | `ws_conf_c7` after importing the changed file: blocker ends "(a confirmation was recorded for an earlier version of this row)" |
| 2 | MEMO-CODE: the question has no action code or event id; the workbook lists the event id | **Held** | Question: "… a human analyst who has read the source can confirm the row in DealScreen." Workbook Screening sheet: "…; event rx:9d396ce9:28". The memo reason still prints the decision id ("dec:00001"), which is an internal id but harmless |
| 2 | UC1, UC2, UC6, UC19 now pass | **Held** | `prev/u12.out` |
| 2 | Real row 12 blocks "now for the right reason" | **Refuted** | `a/dbg.py`: slots "… shares R rights , R , equally with G", places `[worldwide]`, `[ex-CN/HK/KR/MO/TW]`; verdict "names CN/HK/KR/MO/TW, which the row's own territory (CA/EU/JP/ROW/UK/US) does not cover". "worldwide rights, excluding Greater China and South Korea" is still split into two places; the block names the excluded regions as if they were granted (ROW12-REASON, Low) |
| 2 | ACQ-TWO not CONFLICTING; PF9/PF14 now block | **Held** | AQ3 control blocks "who owns it is not established"; PF9, PF14 blocked |
| 3 | `tests/dealscreen` 1,726 pass; ruff, mypy clean | **Held** | 1,726 passed (173.5 s); ruff "All checks passed!"; mypy "Success: no issues found in 38 source files" |
| 3 | Probe counts p12 27/93, p12b 10/32, p12c 6/13, p12d 0/6; ws_m 0; others unchanged | **Held** | My re-runs byte-identical to `fin13/out`; tiers and memos of ws_h2, ws_i2, ws_j2, ws_l, ws_m identical (generation stamps ignored) |
| 3 | §3a: what still reaches a top tier is a control or a judgement row | **Held** | I checked each of the 27 + 10 + 6 tags against REREVIEW11 §2i/§2j |
| 3 | CLDN18.2: 0 of 62 science fields; CSV and memo byte-identical to revision 12; screens identical without the two new fields | **Held** | `compare.py`: "AC8 scientific fields changed: 0 of 62". `after_v13` vs `after_v12` CSV identical; 13 screens differ raw, 0 after removing `external_id`/`related_deal_id` from evidence; my re-screen equals `after_v13` |
| 3 | Cycle-4 equivalence 4 of 4; cross-version 0 of 312 | **Equivalence: see §10. Cross-version: not re-run** | I did not re-run cross-version (U1's reviewer covers it) |
| 4 | Usefulness: 6 of 43; 15 of 24; 15 of 17 direct; 4 of 17 gate | **Held** | `prev/u10.out` "HELD BACK 37 of 43"; `prev/u12.out` 15 of 24; `real_quotes.out` byte-identical to `after_v13/real_quotes.txt` |
| 6 | Costs 1–5 | **Held, with two additions** | Cost 2 is wider: the API path needs no variable change. Cost 3 holds (§3). Add: retention now passes places the template reader never checks (§2a) |

## 2. Paths into the top tiers

All outputs copied from `a/p13.out`, `a/p13b.out` unless stated. Abbreviations: `NOT_ENC/T1` =
`NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder=None owner='Nerida Bio'`, blk:
(none); `RET/T1` = `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder='Nerida Bio'
owner='Nerida Bio'`, blk: (none). "C" = "Chinaco Pharma licenses NB-7 for mainland China". Expected in every row of
§2a–2e: blocked, naming the clause.

### 2a. RET-GRANTOR and RET-PLACE: the retention sentence (High; both introduced by revision 13)

| Id | Row | Quote | Output | Rev 12 |
|---|---|---|---|---|
| RG4 | China license (Nerida Bio → Chinaco Pharma) + sublicense row Chinaco Pharma → Sideco Bio, mainland China, 2025-02-01 | sublicense: "Chinaco Pharma licensed NB-7 to Sideco Bio for mainland China; Chinaco Pharma retains all rights to NB-7 in the United States" | NOT_ENC/T1 | blocked |
| RT1 | China license | "C; Nerida Bio retains rights to NB-7 outside the United States" | NOT_ENC/T1 | blocked |
| RT2 | China license | "C; Nerida Bio retains rights to NB-7 in Japan and Europe" | NOT_ENC/T1 | blocked |
| RT3 | China license | "C; Nerida Bio retains ex-US rights to NB-7" | NOT_ENC/T1 | blocked |
| RX3 | US license D1 + termination | "Alpha Bio terminated the U.S. license with Nerida Bio; Nerida Bio retains rights to NB-7 outside the United States" | RET/T1 | blocked |
| ws_n ATG-022 | Y02 China license + Y03 sublicense | Y03 "Chinaco Pharma licensed ATG-022 to Sideco Bio for mainland China; Chinaco Pharma retains all rights to ATG-022 in the United States" | memo "#2 ATG-022: no third-party grant in evidence; rights position: no grant over the buyer territory per evidence (recorded grants do not cover US; …)" | — |
| ws_n QLS31905 | Y01 | "Chinaco Pharma licenses QLS31905 for mainland China; Qilu Pharmaceutical retains rights to QLS31905 outside the United States" | memo "#1 QLS31905: no third-party grant in evidence" | — |
| ws_n Spevatamig | Y07 + Y08 | Y08 "Alpha Bio terminated the U.S. license with Phanes Therapeutics; Phanes Therapeutics retains rights to Spevatamig outside the United States" | memo "#6 Spevatamig (PT886): no third-party grant in evidence; rights position: rights returned per evidence" | — |

RG4: a licensee that sublicenses is the sublicense row's grantor, so it is "G" and may "retain" U.S. rights; the quote
says a third party holds U.S. rights. RT1–RT3, RX3: a company that "retains rights outside the United States" has
said where its rights are, and the buyer territory is not among them. A BD analyst reads that as "U.S. rights are
with someone else". Causes: `read_clause` returns OK for any `_retention` match before it checks any place
(`rights_template.py:556-557`); `_retention` uses the frame subject "G" (`:427`), and "G" is the row's grantor
(`rights_quote.py:180`), never checked against the program's company. The controls hold: with only the
in-licensing row (RG0–RG3, RG5) the owner check blocks ("the owner per the rights evidence is Tessaly Pharma, but the
landscape names Nerida Bio"); RG4 passes because the China license names Nerida Bio as the owner. The tests in
`test_rights_rereview11.py:159-161` cover only retention by the company.

### 2b. HEADLINE3: a headline whose verb is off the list (High; claimed fixed: HEADLINE2)

| Id | Quote (China license) | Output | Rev 12 |
|---|---|---|---|
| DL1 | "TESSALY BUYS NERIDA, U.S., March 3, 2025 -- C" | NOT_ENC/T1 | T1 |
| DL2 | "TESSALY BUYS NB, Mass., March 3, 2025 -- C" | NOT_ENC/T1 | T1 |
| DL3 | "TESSALY TAKES OVER -- (BUSINESS WIRE) -- C" | blocked ("names TESSALY, TAKES, OVER, BUSINESS, WIRE …") | T1 |
| ws_n BL-M05D1 | Y05 "TESSALY BUYS SICHUAN BAILI, China, March 3, 2026 -- Chinaco Pharma licenses BL-M05D1 for mainland China" | memo "#4 BL-M05D1: no third-party grant in evidence" | — |

The city may be up to four capitalised words on one line; `_name_ok` refuses only `_HOLD_WORDS` and template words
(`rights_quote.py:188-199`, `:211`). "BUYS", "TAKES", "ACQUIRING", "MERGES" and a company name are allowed, so "TESSALY
BUYS <company>" (a third party bought the owner) is removed unread. Realism: low to moderate (a headline on the same
line as the dateline, followed by a listed region); REREVIEW11 counted the same shape (HD1) as High. DL3 now blocks,
which revision 12 passed.

### 2c. UNPLACED2: signing sentences that state a scope (Medium; claimed fixed: UNPLACED, ACQ-OPT)

| Id | Row | Quote | Output | Rev 12 |
|---|---|---|---|---|
| SG1 | China license | "Nerida Bio and Chinaco Pharma entered into an exclusive license agreement to develop and commercialize NB-7" | NOT_ENC/T1 | T1 |
| SG2 | China license | "Nerida Bio entered into an exclusive license agreement with Chinaco Pharma for the development and commercialization of NB-7" | NOT_ENC/T1 | T1 |
| SG3 | China license | "Chinaco Pharma entered into an exclusive license agreement with Nerida Bio for the development and commercialization of NB-7" | NOT_ENC/T1 | T1 |
| SG4 | China option | "Nerida Bio and Chinaco Pharma entered into an exclusive option and license agreement for NB-7" | NOT_ENC/T1 | T1 |
| SG6 | China license | "Nerida Bio and Chinaco Pharma announced an exclusive license agreement for NB-7 for $20 million upfront and up to $200 million in milestones" | NOT_ENC/T1 | blocked |
| ws_n TORL-2-307-ADC | Y06 | "TORL Biotherapeutics and Chinaco Pharma entered into an exclusive license agreement to develop and commercialize TORL-2-307-ADC" | memo "#7 TORL-2-307-ADC: no third-party grant in evidence" | — |

These are in the `t` list, which needs no place (`rights_template.py:462-473`, `:486-489`). Revision 13 required a
place on "E obtained the sole rights to develop … NB-7" (UN6) for the reason that, with no place, it reads as the
whole program. "An exclusive license agreement to develop and commercialize NB-7" says the same. Medium, like
UNPLACED: the row's own territory field is explicit.

### 2d. ACQ-TWO2: two acquirers written two ways (Medium; claimed fixed: ACQ-TWO)

| Id | Input | Output (copied) | Expected |
|---|---|---|---|
| AQ1 | China license; "Omega Holdings acquired Nerida Bio" (2025-02-01); "Sideco Bio acquired The Nerida Bio" (2025-03-01) | `OWNER_ACQUIRED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP holder='Sideco Bio' owner='Sideco Bio'`, reason "Sideco Bio acquired The Nerida Bio (the company or its rights to this program) per source; no third-party grant recorded", cited rows [3, 1, 2] | blocked: "who owns it is not established" (as AQ3, same spelling, does) |
| AQ2 | same, the spellings swapped | owner 'Sideco Bio', tier 1 | same |
| ws_n SKB315 | Y09 license, Y10 "Omega Holdings acquired Sichuan Kelun-Biotech Biopharmaceutical", Y11 "Sideco Bio acquired The Sichuan Kelun-Biotech Biopharmaceutical" | memo "#5 SKB315: no third-party grant in evidence; rights position: owner acquired per evidence (Sideco Bio acquired The Sichuan Kelun-Biotech Biopharmaceutical …)"; Omega's row is listed as evidence, but the reason does not mention it | blocked |

Rev 12 also gave tier 1 here, with owner Omega Holdings (AQ1) or Sideco (AQ2). Cause: rivals are grouped by
`party_key(e.grantor)` (`rights_ledger.py:197`, `:234`), which keeps "the" ("the nerida bio" vs "nerida bio"), while
succession is now keyed by `_entity_key` (`:261`), which drops it. The later record overwrites the earlier one.

### 2e. SUBSID: the subsidiary strip hides control (Medium; older, first reported here)

| Id | Quote (China license) | Output | Rev 12 |
|---|---|---|---|
| SB1 | "Nerida Bio, a wholly owned subsidiary of Chinaco Pharma, licensed NB-7 to Chinaco Pharma for mainland China" | NOT_ENC/T1 | T1 |
| SB2 | "C; Nerida Bio, a subsidiary of Chinaco Pharma, retains all rights in the U.S." | NOT_ENC/T1 | blocked |
| SB3 | "Nerida Bio, an affiliate of Chinaco Pharma, retains all rights to NB-7 outside mainland China" | NOT_ENC/T1 | blocked |
| ws_n JS107 | Y04 "NingBo Junyan Hongshi Biosciences, a wholly owned subsidiary of Chinaco Pharma, licensed JS107 to Chinaco Pharma for mainland China" | memo "#3 JS107: no third-party grant in evidence"; owner shown is the subsidiary | — |

`_SUBSIDIARY` replaces "<known>, a (wholly owned) subsidiary/affiliate of <known>" with the first party
(`rights_quote.py:125-126`, `:237`). When the first party is the program's company and the second the licensee, the
quote says the licensee controls the company and its U.S. rights; the output names the company as owner and shows
no holder. Medium, like OWNER-THE: the owner shown is wrong, but no third-party grant is hidden.

### 2f. PUNCT: punctuation is not read (Low; older)

| Id | Quote (China license) | Output |
|---|---|---|
| PU1 | "C?" | NOT_ENC/T1 |

`_WORD` (`rights_template.py:243`) skips every character it does not match, so a question mark, quotation marks and
brackets are silently dropped. PU2–PU4 (strike-through, bracketed name, quoted rumour) block on their words. Low: I
found no realistic quote where punctuation alone changes who holds rights.

### 2g. What held (selected)

All REREVIEW11 inputs (PF, NL, HD1–HD8, AO, UN, QC/Q, X4/X5, OK3). RT11 ("retains … under the license agreement")
and RX6 (a retention dated 2027) block. RG0–RG3, RG5 (in-licensed or sublicensed programs without the company's own
grant) block on the owner check. DL3 (wire-form headline) blocks. Non-ASCII text and full-width letters block
(p12d 0 of 6).

### 2h. Judgement calls (not counted)

- RT4 / RT5 "Nerida Bio retains U.S. commercialization rights" / "… U.S. development rights" (tier 1): a partial
  retention in the buyer territory often means the partner holds the other half (REREVIEW11's X6/X7 partial returns
  are the same question).
- RT7 "retains rights to NB-7 in mainland China" beside an exclusive China license, RT8 "retains worldwide rights",
  RX1 a China row whose whole quote is "Nerida Bio retains all rights to NB-7" (all tier 1): the quote contradicts
  the row, though not toward a third party.
- RT6 "Nerida Bio retained U.S. rights to NB-7 in 2019" (tier 1): past tense says nothing about now.
- RT12 / RX5 "will retain", "will keep" (tier 1): the only future tense the reader accepts.
- RT9 / RT10 "Nerida Bio Oncology / Nerida Bio Pharma retains all rights in the U.S." (tier 1, same in rev 12): the
  revision-11 rule reads a business word after a known name as the same company; a parent and its "Oncology" unit
  can be different legal entities.
- SG5 and X19: signing sentences with no scope and no place (tier 1), accepted by the response.
- Everything REREVIEW11 §2j lists is unchanged (D1, PT1–PT3, X1/X3, X6/X7, UN8, etc.).

## 3. The confirmation (CONFIRM_RIGHTS_ROW)

Run by `e2e/conf.sh` on `e2e/ws_conf` (a copy of my `ws_i2`; TORL-2-307-ADC row 28, event `rx:9d396ce9:28`, blocks:
"Chinaco Pharma licenses China rights and also receives an exclusive option … is not one of the sentences …").
Every CONFIRMED record below was made by me, an AI, as a test (see Scope).

| # | Input | Output (copied) | Verdict |
|---|---|---|---|
| C1 | `decide --action CONFIRM_RIGHTS_ROW --subject rx:9d396ce9:28 --new-state CONFIRMED --reviewer-kind HUMAN` (shell has `CLAUDECODE=1`) | "REFUSED: this shell is run by an AI agent (CLAUDECODE is set); a rights row is confirmed only by a human analyst who has read the source" | held |
| C2 | `env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT decide …` with no `--reviewer-kind` | "REFUSED: a rights row confirmation states its reviewer kind explicitly (HUMAN, for a human analyst who has read the source)" | held |
| C3 | `env CLAUDECODE= CLAUDE_CODE_ENTRYPOINT= decide … --reviewer-kind HUMAN` | "recorded dec:00001: CONFIRM_RIGHTS_ROW rx:9d396ce9:28 UNCONFIRMED -> CONFIRMED"; after `screen`: TORL `NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, blockers `[]` | **CONFIRM-API** (an empty variable passes) |
| C-API | Python, same shell (`CLAUDECODE=1`): `ws.decision_log().record(action=Action.CONFIRM_RIGHTS_ROW, subject_id="rx:9d396ce9:28", new_state="CONFIRMED", reviewer_kind=ReviewerKind.HUMAN, context=ws.decision_context(), …)` on `ws_conf2` | "recorded dec:00001 HUMAN rx:9d396ce9:28 CONFIRMED"; after `screen`: TORL tier 1, blockers `[]` | **CONFIRM-API** |
| C4 | `--new-state WITHDRAWN` | "CONFIRMED -> WITHDRAWN"; TORL `RIGHTS_UNRESOLVED` | held |
| C5 | re-confirm (dec:00003); re-import with one unrelated row appended | event id becomes `rx:a69d510b:28`; TORL still tier 1, reason "…confirmed as restating the row by rr13-ai-test, recorded as a human analyst (DealScreen cannot verify this; dec:00003, …)" | held (CONFIRM-REIMPORT fixed) |
| C6 | withdraw through `rx:a69d510b:28` | "CONFIRMED -> WITHDRAWN"; TORL blocked | held |
| C7 | re-confirm (dec:00005); re-import with row 28's quote changed (adds "; Tessaly Pharma holds U.S. rights") | blocked; blocker ends "(a confirmation was recorded for an earlier version of this row)" (`ws_conf_c7`) | held |
| C8 | the analyst, seeing the change, withdraws through the changed row's id `rx:05435b35:28` | "recorded dec:00006: CONFIRM_RIGHTS_ROW rx:05435b35:28 UNCONFIRMED -> WITHDRAWN" (no warning that nothing was withdrawn) | **WITHDRAW-STALE** |
| C9 | the vendor reverts the row; re-import the earlier file | TORL `NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, blockers `[]`, reason "… confirmed … (DealScreen cannot verify this; dec:00005, 2026-11-08)" | **WITHDRAW-STALE**: a withdrawn confirmation clears the block |

Findings:

- **CONFIRM-API (Medium; process; claimed fixed: CONFIRM-KIND).** The agent-shell refusal lives only in the CLI
  (`cli/dealscreen.py:139`). `DecisionLog.record` accepts `reviewer_kind=HUMAN` from any caller (`review.py:226-311`),
  and an agent with a Python shell is the common case. `agent_shell` tests truthiness (`review.py:437`), so an empty
  variable passes. The response does say that anyone who controls the shell can unset the variable; it does not say
  that the API needs no change at all. Moving the check into `DecisionLog.record` would close the API path for an
  agent that does not edit its environment; nothing closes it against one that does.
- **WITHDRAW-STALE (Medium; introduced).** A withdrawal removes the stored record whose hash equals the *current*
  row's hash, or whose stored event id equals the subject (`review.py:186-189`). After a re-import with a changed
  row, neither matches the old record, so the withdrawal is recorded as "UNCONFIRMED -> WITHDRAWN" and removes
  nothing. The old confirmation (hash of the earlier content) stays in `ReviewState.rights_rows` and applies again
  whenever a row with that content comes back. Expected: the withdrawal removes every confirmation for the same
  program, deal and type (`row_key`), or the CLI refuses a withdrawal that withdraws nothing.
- **What a confirmation binds to.** Holds: the hash covers external id, deal, related deal, type, parties, territory,
  exclusivity, dates, status, URL and quote (`rights_model.py:90-91`); it cannot match a row of another program
  (different external id). It is not bound to the buyer territory or as-of date it was given for; a confirmation of
  "the quote restates the row" made at a late as-of date also skips the quote's date check at an earlier one (read,
  not run; judgement).
- **A confirmed row is still read** for party notes and the ledger; only its quote is skipped. The memo and the
  workbook say who confirmed it, that the kind is as recorded, and that DealScreen cannot verify it (memo line:
  "the quote on rights row 28 (license) was confirmed as restating the row by rr13-ai-test-api, recorded as a human
  analyst (DealScreen cannot verify this; dec:00001, 2026-11-08); it is not read again"). That is honest. It is
  printed beside the confirmed quote "Chinaco Pharma licenses China rights and also receives an exclusive option",
  so the memo shows tier 1 beside an unscoped option (the response's cost 3).

## 4. Over-caution and usefulness

These are usefulness costs, not safety errors.

| Measure | Result | Source |
|---|---|---|
| REREVIEW10's 43 clean cases (`rr10/a/u10.py`) | 6 pass (response: 6) | `prev/u10.out` "HELD BACK 37 of 43" |
| REREVIEW11's 24 sentences (`rr12/a/u12.py`) | 15 pass (response: 15); UC22 "will return" still blocks (correct) | `prev/u12.out` |
| Real CLDN18.2 quotes read directly | 15 of 17 block (response: 15) | `real_quotes.out`, byte-identical to `after_v13/real_quotes.txt` |
| Real CLDN18.2 quotes through the gate | 4 of 17 block, the 4 rows that give a clear position alone | same |
| My 8 realistic clean sentences (`a/u13.py`) | 3 pass | `a/u13.out` |

Clean cases held back (reviewer-written, fictional; each `RIGHTS_UNRESOLVED` with the clause quoted):

| Id | Quote | Why it blocks |
|---|---|---|
| UC33 | "Chinaco Pharma will pay Nerida Bio an upfront payment of $20 million" | no payment sentence; "will" |
| UC34 | "Nerida Bio is eligible to receive up to $200 million in milestones" | no payment sentence |
| UC35 | "HANGZHOU, Zhejiang Province, China, March 3, 2025 /PRNewswire/ -- C" | "Zhejiang Province" is not on `_DATELINE_REGIONS` (only "Zhejiang"); the dateline stays and its words are names |
| UC37 | "Chinaco Pharma announced that it has licensed NB-7 from Nerida Bio" | no place (the response lists this cost) |
| UC38 | "Nerida Bio granted Chinaco Pharma exclusive rights to NB-7 in the Territory, defined as mainland China" | a defined "Territory" is a capitalised name |

Passing clean cases: UC31 (HKEX dateline, "announced that it has entered into an exclusive license agreement with
Chinaco Pharma for NB-7 in mainland China"), UC32 (Greater China listed out), UC36 ("Nerida Bio retains rights in the
rest of the world", via the retention sentence).

Real-quote breakdown: I agree with the response, except row 12 (ROW12-REASON, §1). Rows 9/10 block on the China
co-promotion option and row 16 on "in cancer patients in China"; both are reasonable blocks. Rows 3/4 block on the
description "a promising therapeutic target in gastric cancer"; that is a usefulness cost.

Judgement on the usefulness claims: the counts are honest. "One analyst confirmation per real rights row, paid once"
now holds for unchanged rows (C5). Payment and milestone sentences, the most common lines in a deal release, still
never pass, so a real release with more than one sentence nearly always needs a confirmation. The retention sentence
added usefulness (UC6, UC36) but did so by skipping the place check, which is the cause of RET-PLACE.

## 5. Output honesty

In favour: no CLDN18.2, ws_m, ws_n or ws_conf2 memo calls a program available or open as a rights tier; `grep` finds no
position or tier code and no action code in memo prose (`cldn_memo.md`, `memo_m.md`, `memo_n.md`, `memo_conf2.md`).
A confirmed row says who confirmed it and that the kind cannot be verified (§3). Every holder shown in ws_n is cited.
The workbook's Screening sheet lists the event id to confirm.

| # | Where | Output (copied) | Problem | Cause |
|---|---|---|---|---|
| O1 | `e2e/memo_n.md` #2 ATG-022 | "no grant over the buyer territory per evidence (recorded grants do not cover US; …)" beside the cited quote "…; Chinaco Pharma retains all rights to ATG-022 in the United States" | the reason contradicts the quote it prints | RET-GRANTOR |
| O2 | `e2e/memo_n.md` #5 SKB315 | "owner acquired per evidence (Sideco Bio acquired The Sichuan Kelun-Biotech Biopharmaceutical …)"; ask "Would Sideco Bio license or sell US rights?"; Omega's acquisition is listed as evidence | the reason and question name one acquirer although the cited evidence names two | ACQ-TWO2 |
| O3 | `e2e/memo_n.md` #3 JS107 | owner shown: the licensor; the quote says it is "a wholly owned subsidiary of Chinaco Pharma" | owner shown is not the controlling party | SUBSID |
| O4 | `memo_conf2.md` #3 TORL | "…recorded as a human analyst (DealScreen cannot verify this; dec:00001, …)" | an internal decision id in memo prose; harmless | `rights_gate.py:288-291` |

The CLI `rights_reading_note` (`cli/dealscreen.py:105-131`) is unchanged by revision 13 apart from the import line;
it speaks only for availability text and says nothing about rights-row confirmations. No contradiction found.

## 6. CLDN18.2 measured against the reference and B

| Item | Revision 12 | Revision 13 |
|---|---|---|
| `after_transaction.csv` (62 programs) | — | my HEAD re-screen of a copy of `fin13_ws` is byte-identical to `after_v13/after_transaction.csv`, which is byte-identical to `after_v12` |
| Screens in the JSON | — | identical to `after_v13`; vs `after_v12`, 13 screens differ only in the two new evidence fields (`external_id`, `related_deal_id`) |
| Memo | — | identical to `fin13/out/memo.md` (generation stamps ignored) |
| Scientific fields vs frozen baseline (`compare.py`) | 0 of 62 | **0 of 62** ("AC8 scientific fields changed: 0 of 62") |
| Tiers | 44 / 17 / 1, 0 top tier | 44 RIGHTS_UNRESOLVED, 17 DEPRIORITIZED, 1 EXCLUDED_BY_BUYER_PREFERENCE; **0 top tier** |

Error classes against `reference_calls.csv`, re-read for the programs with rights evidence and the reference's deal
programs. No position or holder changed from revision 12, so the classes are REREVIEW11's:

| Class | Count | Programs |
|---|---|---|
| False unobstructed | **0** | — |
| False encumbrance | 0 definite; 2 likely outdated | EO-3021, SYSA1801 (reference "RETURNED_TO_ORIGINATOR_UNCLEAR"; tool: licensed to Elevation Oncology, deprioritized) |
| Wrong holder | 1, labelled | LM-302 "Turning Point Therapeutics (recorded; conflicting)" (reference: returned by BMS) |
| Wrong territory | 0 | — |
| Missed return | 2 | SKB315 (`NO_RIGHTS_EVIDENCE`; the return is not in the rights file), LM-302 (conflicting) |
| Missed owner | 2 (not a false call) | Zolbetuximab, IMAB362 (`RIGHTS_ROWS_NOT_APPLIED`); reference "Astellas (owns 100% via Ganymed acquisition)" |

Usefulness against general Claude (B) on REREVIEW.md's 15 deal programs: unchanged, **DealScreen 8 right / 6
partial / 1 missed; B 14 / 1 / 0**. I checked that no position or holder changed; I did not re-score each row. No
advantage is shown.

## 7. Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | ws_h2/i2/j2/l/m/n: "N events, 0 rejected rows"; provenance in every evidence line (memo and workbook) |
| AC2 | PARTIAL | CLDN18.2: no OPEN tier; nothing called available. Held-out: ws_n reaches tier 1 for 7 programs whose quotes say or imply that a third party holds or may hold U.S. rights (§2) |
| AC3 | PARTIAL | Rights-file territories parse; named wider places in grant sentences block; unplaced `tp` grants block. Not met: a retention may name any place (RET-PLACE) and any grantor (RET-GRANTOR); signing sentences with a scope need no place (UNPLACED2) |
| AC4 | PARTIAL | REREVIEW11's ending inputs block. Not met: "…; Nerida Bio retains rights to NB-7 outside the United States" on a termination row gives RIGHTS_RETURNED / tier 1 (RX3); LM-302 still not RETURNED (data) |
| AC5 | PASS for the inputs I ran | Option-to-acquire removed; lapse controls pass; AO1–AO3 block. SG4 ("option and license agreement for NB-7" with no place) is counted under AC3 |
| AC6 | PARTIAL | ACQ-TWO blocks two acquirers spelled alike, but not "Nerida Bio" vs "The Nerida Bio" (ACQ-TWO2); the position is not CONFLICTING (judgement) |
| AC7 | PASS | No change from revision 12; RX6 (a 2027 date) blocks |
| AC8 | PASS | `compare.py` 0 of 62; HEAD re-screen identical to `after_v13`; cycle-4 equivalence re-run: 4 of 4 `byte_identical: true`, `fast_path: true` (`/tmp/claude-1000/rr13/equiv.json`; the tracked result file's md5 `94450c24…` unchanged). Cross-version not re-run by me |
| AC9 | PARTIAL | Preferences work. Most real phrasings still need a confirmation (§4); confirmations now survive re-imports |
| AC10 | PARTIAL | Every applied row is cited; a confirmed row names its confirmer and says the kind cannot be verified. Not met: memo reasons contradict the quotes they print (O1), name one of two acquirers (O2), show a controlled subsidiary as owner (O3) |
| AC11 | PARTIAL | Blocked rows ask a specific question; the §2 paths ask "Who holds US rights?" generically and never name the holder in the quote |
| AC12 | PASS | 447 added lines of `git diff 55ac585 d6d2d7f -- src/` grepped for 130 CLDN18.2 company, licensee, licensor and program names: no hit |
| AC13 | PARTIAL | IBI343, SHR-A1904 not unobstructed; RC148, FL-301, XNW27011 encumbered; LM-302 CONFLICTING, not returned |
| AC14 | FAIL | 3 new High and 5 new Medium errors on held-out inputs (§2, §3); none in the CLDN18.2 output |

## 8. Remaining issues, ranked

1. **(Safety, High, introduced) RET-GRANTOR and RET-PLACE.** `_retention` passes before any place check and takes
   the row's grantor as "G" whoever it is. Tier 1 beside "Chinaco Pharma retains all rights to ATG-022 in the United
   States" (a sublicensing licensee) and beside "<company> retains rights … outside the United States". End to end:
   ATG-022, QLS31905, Spevatamig.
2. **(Safety, High) HEADLINE3.** A one-line all-capitals headline with a verb off `_HOLD_WORDS` ("TESSALY BUYS
   <company>") is stripped as a dateline city. End to end: BL-M05D1. The word-list check on the city repeats the
   pattern every review has broken.
3. **(Process, Medium) CONFIRM-API and WITHDRAW-STALE.** The agent-shell check is CLI-only and treats an empty
   variable as unset; a withdrawal after a changed row removes nothing, and the withdrawn confirmation clears the
   block when the row comes back.
4. **(Medium) UNPLACED2.** "entered into an exclusive license agreement to develop and commercialize P" and "option
   and license agreement for P" need no place. End to end: TORL-2-307-ADC.
5. **(Medium) ACQ-TWO2, SUBSID.** Two acquirers spelled with and without "The" are not rivals; "<company>, a wholly
   owned subsidiary of <licensee>" is stripped. End to end: SKB315, JS107.
6. **(Usefulness)** 15 of 17 real quotes, 37 of 43 and 8 of 23 earlier clean cases (UC22 excluded as a correct block), and payment/milestone sentences
   need a confirmation; "Zhejiang Province" datelines block; defined terms ("the Territory") block.
7. **(Low)** ROW12-REASON (the block names excluded regions as granted); PUNCT; a decision id in memo prose.
8. **(Judgement)** partial retentions (RT4/RT5), retentions that contradict the row (RT7, RT8, RX1), past and future
   retentions (RT6, RT12), business-word variants as the grantor (RT9/RT10), and REREVIEW11 §2j unchanged.
9. **(Recall)** The rights file still caps recall (LM-302's and SKB315's returns); no real vendor export tested.

## 9. The single highest-value next fix

Make the retention sentence as strict as the grant sentences, or remove it. Concretely: accept `_retention` only when
"G" is one legal entity with the program's company (`_one_entity(company, grantor)`) and the row is not a sublicense,
and require that every place it names, unioned, covers the buyer territory (a retention that names only other places
says the buyer-territory rights are elsewhere); allow no place only with "all rights". Put the check after the place
loop, not before it. In the same change, drop `_name_ok`'s word list for datelines and accept a city only from a
city list (or never strip a dateline whose first part has more than two words), and move the agent-shell refusal
into `DecisionLog.record` with a non-empty test. This closes the two High paths opened by revision 13 and the
headline path with the smallest change.

## 10. Checks

| Check | Result |
|---|---|
| `tests/dealscreen` at HEAD | 1,726 passed, 5 warnings (173.5 s) |
| `ruff check --no-cache src/bve/dealscreen src/bve/cli/dealscreen.py` | "All checks passed!" |
| `mypy` (cache in `/tmp/claude-1000/rr13/mypy_cache`) | "Success: no issues found in 38 source files" |
| `compare.py` (frozen baseline `baseline_ws/screening.json`) | "AC8 scientific fields changed: 0 of 62" |
| Cycle-4 equivalence (`rr12/run_equiv.py`, which does not write the tracked file) | 4 of 4 `byte_identical: true`, `fast_path: true`; tracked `cycle4/equivalence_result.json` md5 `94450c24dd45550248f008573c800843` before and after |
| Previous probes re-run (p10, p10b, av10, d10, d10b, rt10, u10, p11, q11, p12, p12b, p12c, p12d, u12) | all byte-identical to `fin13/out` |
| End to end (CLDN18.2, ws_h2, ws_i2, ws_j2, ws_l, ws_m) | tiers and memos identical to `fin13/out`; CSV identical to `after_v13` |
| SHA-256 of `src/bve/dealscreen/*.py` | start (`sha_start.txt`) and end (`sha_end.txt`) identical: no file changed during the review |
| Git | no commit, stash or checkout by me; the only new file is this report (the U1 reviewer's `REVIEW7.md` also appeared) |
