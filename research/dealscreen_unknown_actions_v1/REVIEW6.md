# Cycle U1 revision 6: sixth adversarial review

INTERNAL DEVELOPMENT. This is an AI-simulated adversarial review. It is not human or independent validation, and
nothing in it is an approval.

**Reviewed:** HEAD `55ac585` on `dealscreen-mvp` in `/home/djmann/projects/bve-b8`, read-only. U1 revision 6 was
committed in `7a62efd` together with R1 revision 11; U1 revision 5 is `b0388eb`. Among the U1 modules,
`git diff b0388eb 7a62efd` changes only `diagnostics.py` (+25/-6) and `indication_relations.py` (+5/-2).
The `screening.py` changes in `7a62efd` and `55ac585`, and those to `facts.py` and `cli/dealscreen.py` in
`55ac585`, are rights-only: no line touching `diagnose` or `unknown_diagnostics` changed, and `workbook.py` and
`memo.py` are unchanged since `b0388eb`.
**Criteria:** `ACCEPTANCE.md` with its revision notes, `MEASUREMENT.md`, `REVIEW5.md` and `REVIEW5_RESPONSE.md`.

Every number below was recomputed by running code, unless it is marked "read, not re-run". Scratch files and probe
scripts are in `/tmp/claude-1000/u1rr6b/`. The partial files of the stalled first revision-6 review
(`/tmp/claude-1000/u1rr6/`) were read; only its `bk6.py` probe was reused, and it was re-run.

Abbreviations:
- `dg` = `bve.dealscreen.diagnostics`; `ir` = `bve.dealscreen.indication_relations`.
- `GAS` = the CLDN18.2 request `["gastric adenocarcinoma", "gastroesophageal junction adenocarcinoma"]`.
- `ALL-A` = the request `["adult acute lymphoblastic leukemia"]`; `UC` = `["ulcerative colitis"]`;
  `MG` = `["myasthenia gravis"]`.
- `VORP3` = a fictional required target (`VORP3`, label "Vorpin 3.1") with a fictional reader that knows `KLX9`.
- "E2E" = confirmed through `bve-dealscreen import`, `import-rights` and `screen` (and `export`/`memo` where stated)
  on a workspace built from the CLDN18.2 inputs with cells edited (see Reproduction).
- "rev5" = revision 5's two U1 modules, loaded side by side from `git show b0388eb:…`
  (`/tmp/claude-1000/u1rr6b/rev5/`).

## Verdict in one paragraph

Revision 6 changes no science, and coverage is complete. N1 and N2 of REVIEW5 are fixed for every input REVIEW5
listed, confirmed end to end on fresh screens of REVIEW5's own workspaces. The N3 items the response says it fixed
("&", en/em dash after the symbol) are fixed. The two transaction-view changes on CLDN18.2 (Zolbetuximab, IMAB362)
come from R1, not U1: a screen of the same workspace with U1's `diagnose` stubbed out gives the same transactions.

**U1-7 is still not met.** The main finding is not new in revision 6. It is a pre-existing defect that the five
earlier reviews did not report, and it is the U1-6 harm itself:
1. **E1 (high).** When an indication name joins two diseases with "or", the screen's coordination reading keeps only
   the right-hand one. U1 classes the whole name by that one reading. So a record that names the requested indication
   word for word is called a different disease: "'Ulcerative colitis or Crohn's disease' reads as Crohn Disease (NCIt)
   once coordination expanded, neither a requested indication nor a subtype of one" (UC request). The same happens
   with "Myasthenia gravis or CIDP", "Adult ALL or AML", "HCC or cholangiocarcinoma", "Gastric adenocarcinoma or
   NSCLC" and "Pancreatic, gastric or esophageal adenocarcinoma". Five cells (two UC, three gastric) are confirmed
   end to end, in the Diligence sheet and in the memo's "a disease neither requested nor a subtype of one" group;
   the MG, ALL and HCC rows are unit-level. Output is identical with revision 5's modules.
2. **E2 (medium; N2 partly fixed).** A "positive" that belongs to another target still cancels the required target's
   negation when it is written *before* that target ("CLDN18.2 negative, positive PD-L1 expression"), or after an
   "or" or " / " that the list splitter does not split ("VORP3.1 negative or positive for KLX9"). The other target is
   now shown ("also on record"), so this is less harmful than REVIEW5's N2. The class and the memo summary still say
   "the required target in a form DealScreen does not read". Confirmed end to end (SG1906).

## Verdict per criterion

| AC | Verdict | Evidence |
|---|---|---|
| U1-1 coverage | **Met** | `coverage.py` (the second reviewer's script, re-run): `fin12_ws` 38/38 and a fresh screen of a copy 38/38; `xv12f` c5_heldout 28/28, fcrn_v1 28/28, fcrn_v2 28/28, synthetic_200 20/20. My four E2E workspaces: 41/41, 52/52, 53/53 and 40/40. Missing 0 and extra 0 everywhere. |
| U1-2 authorities only | **Met (letter), with notes** | I grepped both U1 modules for landscape words (gastr, claudin, cldn, gej, stomach, fcrn, myasthen, tigit, zolbet, pancrea, junction, rilveg, volrus, esophag, oesoph, lymphoblastic, leuk, tl1a, ibd, crohn, colitis, her2, pd-l1, cd3, cd47). The only hits are docstrings, comments and the generic British-spelling pairs. The revision-6 logic is generic: `_BASKET_HEADS \| {"solid", "comers"}`, a second-state regex and en/em dashes. The basket, negation, role, lineage and placeholder word lists remain DealScreen's own (J5). E1 is a case of U1 adopting a screen reading (`indications.indication_readings`) as if it were the authority's. |
| U1-3 no change to science | **Met** | `science_diff.py`: `fin12_ws` vs `baseline/screening_R1.json` shows 2 of 62 programs changed, both in `transaction` only (`ds:4cc0848e49c9`, `ds:99f19433e42d`, i.e. Zolbetuximab and IMAB362). Disposition, rank, decisions, machine_recommendation and transaction_rank are unchanged, and the top level is equal. **Attribution:** a screen of a copy of `fin12_ws` with `screening.diagnose` replaced by a stub returning `{}` (`probes/nou1.py`) gives the same science as `fin12_ws`, transactions included; the only differing key is `unknown_diagnostics`. `fin12_ws` is also science-identical to R1's own artifact `research/dealscreen_rights_v1/after_v12/screening_R1v12.json`. So the two transaction changes are R1 (revisions 11 and 12), as the responses say. A fresh screen of a copy of `fin12_ws` is byte-identical to `fin12_ws/screening.json`. Held-out: `xv12f` vs `xv10` and vs `xvu5` (revision 5): 0 differing per-program keys of any kind in all four landscapes (40, 40, 40, 192), so revision 6 does not change even a diagnostic there; vs `xv8` (no U1): 0 science fields. Cycle-4 equivalence: `equivalence.main()` called in-process with output to scratch; all 4 cases `byte_identical: true`, `fast_path: true`. The md5 of the tracked `equivalence_result.json` (`94450c24…`, already modified in the working tree before this review) is unchanged. |
| U1-4 held-back tests | **Met as written; insufficient in substance** | `python -m pytest tests/dealscreen -q -p no:cacheprovider`: **1,575 passed**, 5 warnings, 414 s (the count rose from REVIEW5's 1,327 with R1's tests). `test_unknown_actions.py`: 274 passed. The 24 new cases test exactly REVIEW5's inputs. None puts two diseases in an "or" coordination (E1). None writes the other target's "positive" before it (E2), joins the two states with "and/or", "+" or "\|" (E3), puts a non-ASCII dash before the symbol (E4), or writes "ALL" before "disease" (E5). |
| U1-5 surfaces | **Met** | A regenerated workbook vs `after/u1_cldn18.xlsx`: Diligence and the other 7 sheets are cell-identical, except the README timestamp and 2 Screening cells in the rights column (Zolbetuximab, IMAB362). The regenerated workbook is cell-identical to R1's `after_v12/rights_R1v12.xlsx` (timestamp aside). The regenerated memo differs from `after/memo_u1.md` only on line 31, the same two programs' rights wording, and is identical to `after_v12/memo_R1v12.md`. So `after/` is stale only in R1 text written by `55ac585`. The Diligence sheet keeps the S&E rationale beside the DealScreen action. E1 shows in the Diligence sheet and the memo of the E2E workspaces. |
| U1-6 per program vs reference | **Met as measured; the harm is reachable (E1)** | Recomputed from `reference_calls.csv`: 30 reference-IN programs; 14 ELIGIBLE, 15 UNRESOLVED, 1 EXCLUDED (LCB02A, disclosed). No gastric or GEJ name is DIFFERENT_DISEASE. SOT102 ("Pancreatic Cancer") is DIFFERENT_DISEASE and is reported. RC118, Q-1802, TQB2103, SG1906, VBC108 and AK132 are BASKET, and the action names both requested indications. Rilvegostomig names TIGIT and 'PD-1', volrustomig CTLA-4 and 'PD-1', RC148 'PD-1'. But E1 produces the forbidden outcome as soon as a reference-IN record writes "Gastric adenocarcinoma or <another disease>": E2E, Q-1802 and VBC108 become "a disease neither requested nor a subtype of one". |
| U1-7 adversarial review | **Not met** | E1 (high) and E2 (medium) are confirmed end to end; E3–E7 are low. I found no hidden UNKNOWN, no stray diagnostic, no scope or recommendation wording and no change to science. |

## Status of REVIEW5's findings

Inputs: REVIEW5's probes (`/tmp/claude-1000/u1rr5/probes/b5.py`, `t5.py`, `ta5.py`); REVIEW4's `p_ind4.py`,
`p_sib.py`, `p_tgt4.py` and `restate.py`; the third reviewer's `p_ind.py`, `p_tgt.py` and `p_sib2.py`; the second
reviewer's `p1–p10.py`; and the stalled revision-6 review's `bk6.py`. All were re-run unchanged from the repository
root and diffed against REVIEW5's saved outputs (`/tmp/claude-1000/u1rr6b/out/`):
- p1–p3, p5, p6, p8–p10, `p_ind`, `p_sib2`, `p_ind4`, `p_sib`, `restate` and `ta5`: identical.
- p4: the same lines in a different order among tied counts.
- p7 and `p_tgt` (third reviewer): 'CLDN6', 'Claudin-6' and 'PDL1' are now read by the target reader. REVIEW5 had
  already noted that this depends on the working directory (the S&E target snapshot path is relative). It is
  environmental, not U1.
- `b5`, `t5` and `p_tgt4`: change exactly on the N1, N2 and N3 rows (below), plus the new "also on record" tail.

| Id | Status | Input → output at HEAD |
|---|---|---|
| N1 "ALL" before a qualifier/population/function word called a basket | **Fixed as stated; residue E5** | All 12 rows of the response, plus "ALL Stage IV", "ALL of any stage" and "ALL MULTIPLE" → UNREADABLE (rev5: BASKET). E2E (a fresh screen of a copy of REVIEW5's `ws_e2e_all5`): RC118 "Relapsed ALL in adults", Q-1802 "ALL RELAPSED", VBC108 "Relapsed or refractory ALL in adults" and TQB2103 "ALL in children" → UNREADABLE; AK132 "RELAPSED ALL" → BROADER_THAN_REQUESTED. Controls kept: "ALL COMERS", "ALL-COMERS", "ALL SOLID TUMORS", "Solid tumors (ALL comers)" → BASKET. Residue: "ALL" before a tumour head that is not a basket in English ("Adult ALL disease") is still a basket (E5). |
| N2 another target's both-states phrase cancelled the negation | **Fixed for REVIEW5's inputs; residue E2** | E2E (fresh screen of a copy of `ws_e2e_gas5`): SG1906 "not CLDN18.2; HER2 positive or negative" → SOURCE_NAMES_OTHER_TARGETS naming 'HER2 positive or negative', with "('not CLDN18.2' states it is not CLDN18.2)"; AK132 "CLDN18.2 negative, positive for CD47" → SOURCE_NAMES_OTHER_TARGETS naming 'positive for CD47', negation shown. Unit: all fictional and real N2 rows of `t5.py` keep the negation. "KLX9 positive/negative; VORP3.1 negative" and "VORP3.1 negative, KLX9 positive/negative" (new) also keep it. Single-target both-states cells ("VORP3.1 negative or positive", "neg/pos", "negative/positive", "negative, positive") are still not called negated. The SOURCE_MAY_NAME sentence now lists the other parts. But see E2. |
| N3 residues | **Partly fixed, as declared** | "VORP3.1 neg & pos" → SOURCE_MAY_NAME (rev5: STATES_NOT). "CLDN18.2–negative", "VORP3.1 – negative", "VORP3.1–neg", "VORP3.1 —negative" → STATES_NOT (rev5: NAMES_REQUIRED). Declared open and still open: "negative or low" read as negation; quotes cut at the slash ("'CLDN18.2 neg' … also on record: 'pos'"); broken parentheses ("'CLDN18.2 (negative' … 'positive)'"). New residues of the same family are E3 and E4. |
| D5 TNBC request has no site words | **Open (declared)** | `site_phrases` for Triple-Negative Breast Carcinoma is still empty. |
| D6 partner hidden after " / ", "or" | **Open (declared)** | "CLDN18.2 or PD-L1" and "CLDN18.2 / CD3" → "names CLDN18 (Claudin 18.2), but no target set was built from it", with no partner shown. |
| D7 "without X selection" | **Open (declared)** | `p_tgt4` unchanged on these rows. |

## Defects in revision 6, ranked by how much they could mislead

### E1 (high; pre-existing, not reported before). A two-disease "or" name is classed by its right-hand disease only, so a record naming the requested indication is called a different disease

`ir._raw_lookup` takes the screen's readings (`indications.indication_readings`) when the authority's index does
not read the name. For "A or B", `indications._coordinated` keeps `B`, and adds `A <head>` only when `A` plus a
suffix of `B` is a specific concept. When `A` is a whole disease name ("Ulcerative colitis", "Gastric
adenocarcinoma", "Adult ALL"), nothing is added. U1 then classes the whole name by `B` alone. With one concept that
is not requested, `classify_name` returns DIFFERENT_DISEASE, and the sentence says the name "reads as B …, neither
a requested indication nor a subtype of one". The J1 rule ("the authority's reading outranks a shared site word")
is then applied to a reading of half the name, and that reading is not the authority's.

| Request | Record name | HEAD (= rev5) | Expected |
|---|---|---|---|
| UC | "Ulcerative colitis or Crohn's disease" (**E2E**, SOT102; Diligence and memo) | DIFFERENT_DISEASE: "reads as Crohn Disease (NCIt) once coordination expanded, neither a requested indication nor a subtype of one" | not DIFFERENT_DISEASE; the sentence names both readings (UC = requested; Crohn Disease = not requested), e.g. AMBIGUOUS_NAME |
| UC | "UC or Crohn's disease" (**E2E**, Q-1802) | DIFFERENT_DISEASE, as above | same |
| UC | "Crohn's disease or ulcerative colitis" (control, **E2E**, VBC108) | gate PASS (the screen reads it as UC); no diagnostic | (the asymmetry is the screen's: J-a) |
| MG | "Myasthenia gravis or CIDP" | DIFFERENT_DISEASE: "reads as Chronic Inflammatory Demyelinating Polyneuropathy" | not DIFFERENT_DISEASE |
| ALL-A | "Adult ALL or AML", "Adult acute lymphoblastic leukemia or AML" | DIFFERENT_DISEASE: "reads as Acute Myeloid Leukemia" (the record names the requested concept itself) | READS_AS_REQUESTED or AMBIGUOUS_NAME naming both |
| ALL-A | "ALL or AML" | DIFFERENT_DISEASE ("AML or ALL" → BROADER) | AMBIGUOUS_NAME (ALL broader; AML not requested) |
| HCC | "HCC or cholangiocarcinoma" | DIFFERENT_DISEASE: "reads as Cholangiocarcinoma" | not DIFFERENT_DISEASE |
| GAS | "Gastric adenocarcinoma or NSCLC" (**E2E**, VBC108) | DIFFERENT_DISEASE: "reads as Lung Non-Small Cell Carcinoma (NCIt) once coordination expanded, neither a requested indication nor a subtype of one, although it names gastric, a requested site" | READS_AS_REQUESTED/AMBIGUOUS_NAME; at least NAMES_REQUESTED_SITE |
| GAS | "Gastric Adenocarcinoma or Pancreatic Ductal Adenocarcinoma" (**E2E**, Q-1802) | DIFFERENT_DISEASE ("reads as Pancreatic Ductal Adenocarcinoma") | same |
| GAS | "Pancreatic, gastric or esophageal adenocarcinoma" (**E2E**, SOT102) | DIFFERENT_DISEASE ("reads as Esophageal Adenocarcinoma") | same |
| GAS | controls: "Gastric adenocarcinoma or pancreatic cancer", "Gastric or pancreatic cancer" | NAMES_REQUESTED_SITE (the screen reads neither half) | (correct) |
| GAS | control: "Pancreatic or gastric adenocarcinoma" | AMBIGUOUS_NAME naming Gastric Adenocarcinoma (requested) and Pancreatic Adenocarcinoma | (correct: both halves read) |

- **Why it misleads:** this is the outcome U1-6 forbids: a requested indication called a different disease. The
  record states the requested indication word for word. For a request with no site words (UC, MG, ALL, most
  non-oncology), nothing in the sentence hints that it does. In the E2E memo (`e2e_gas6/memo.md`, line 47), VBC108,
  SOT102 and Q-1802 are listed under "a disease neither requested nor a subtype of one", below the baskets. In the
  UC memo, SOT102 and Q-1802 are among that group's "(+10 more)". The Diligence sheet says "Record class
  DIFFERENT_DISEASE". "UC or Crohn's disease" and "MG or CIDP" are ordinary condition strings in IBD and FcRn
  landscapes. "<site> or <site> <head>" is common in trial titles.
- **Not reachable** on the shipped CLDN18.2 landscape or the four held-out landscapes. The only coordination
  reading there is IBI343, which reads as requested (REVIEW3 J4 called it "true, but partial").
- **Why the earlier reviews missed it:** their coordination inputs were "<site> or <site> <head>" names, which the
  screen expands into both halves.
- **Expected and fix:** never class a name DIFFERENT_DISEASE (or say "neither a requested indication") from a reading
  whose steps include "coordination expanded" unless every conjunct was read. Better: U1 splits a two-way "or" itself
  and looks each conjunct up in the authority (the index reads "Ulcerative colitis", "Adult ALL", "Gastric
  adenocarcinoma" and "Myasthenia gravis" directly). It then classes the name by all the readings, as it already
  does for ambiguous names. Add the rows above as tests. The screen's own lossy reading (J-a) is outside U1, but U1
  must not turn it into a statement about the record.

### E2 (medium; N2 partly fixed). A "positive" belonging to another target still cancels the negation when it is written before that target, or inside an unsplit "or"

`_SECOND_STATE` excludes only a "positive" followed by "for", "selection" or "selected". A "positive" followed by the
other target's name is read as the negated target's second state. The part-level test (`_BOTH_STATES.search(part)`)
has no such exclusion at all. It fires whenever "or" or a spaced " / " leaves the two targets in one part.

| Target cell | HEAD | rev5 | Expected |
|---|---|---|---|
| "CLDN18.2 negative, positive PD-L1 expression" (**E2E**, SG1906; Diligence and Screening sheets) | SOURCE_MAY_NAME_REQUIRED_TARGET: "'CLDN18.2 negative' contains CLDN18 or its name, in a form neither the target authority nor DealScreen reads …; also on record: 'positive PD-L1 expression'"; summary "the required target in a form DealScreen does not read" | same class, without the "also on record" tail | SOURCE_NAMES_OTHER_TARGETS, with "('CLDN18.2 negative' states it is not CLDN18.2)" |
| "VORP3.1 negative and positive KLX9", "VORP3.1 negative, pos. KLX9", "VORP3.1-negative, positive KLX9 status", "VORP3.1 negative, positive in KLX9 cohort", "VORP3.1 negative, positive (KLX9)" | SOURCE_MAY_NAME | SOURCE_MAY_NAME | as above |
| "VORP3.1 negative or positive for KLX9", "VORP3.1 negative / positive for KLX9", "… or positive by IHC for KLX9" | SOURCE_MAY_NAME, quoting the whole part | SOURCE_MAY_NAME | as above (consistent with the next row) |
| control: "VORP3.1 neg/pos for KLX9", "VORP3.1 negative, positive for KLX9" | SOURCE_NAMES_OTHER_TARGETS, negation shown | SOURCE_MAY_NAME | (correct) |

- **Why it misleads:** the record says the program is *not* the required target. The class, the Screening-sheet
  class column and the memo summary say the opposite: the target is present in an unreadable form. Revision 6's
  "also on record" tail now shows the other target, so this is less harmful than REVIEW5's N2.
- **Fix:** apply the "second state" exclusion to a "positive" followed by any word that is not a state or a
  cohort/population word, and to the part-level test. Or, simpler: a second state counts only when nothing but
  punctuation, "cohorts" or the end of the cell follows it.

### E3 (low; D3/N3 family). Both states joined by "and/or", "&/or", "+", "plus", "|" or a dash are read as a negation, and the quote drops the positive half

`_parts` replaces "and/or" with the separator, and `_LIST_WORDS` splits at "+", "plus" and "&" between spaces, before
`_both_states` looks for the second state. `_SECOND_STATE` accepts only "/", "or", "and", "&" and ",". A doubled space
or a parenthesis makes `value.find(part)` miss, because `_paren_parts` rebuilds the part with single spaces.

| Target cell | HEAD (= rev5 except "&") | Expected |
|---|---|---|
| "CLDN18.2 negative and/or positive" (**E2E**, TQB2103) | SOURCE_STATES_NOT_REQUIRED_TARGET: "'CLDN18.2 negative' states it is not CLDN18.2" | not STATES_NOT (the record states both) |
| "VORP3.1 negative &/or positive", "VORP3.1 neg + pos", "VORP3.1 negative plus positive", "VORP3.1 negative\|positive", "VORP3.1 negative – positive", "VORP3.1 neg–pos" | STATES_NOT | same |
| "VORP3.1  neg/pos" (two spaces), "VORP3.1 (neg)/pos" | STATES_NOT | same |

- The quoted part omits the second state, so the sentence misquotes the record.

### E4 (low; N3 fix incomplete). A dash other than ASCII "-" before the symbol, or a Unicode hyphen after it, is not read as a negation: the record is said to *name* the target

Revision 6 added "–" and "—" to `_NEGATED_AFTER` only. `_NEGATED` (before the symbol) still allows only `[\s\-]`, and
neither regex knows U+2010 "‐", U+2011 "‑" (non-breaking hyphen, common in text pasted from web pages and labels) or
U+2212 "−".

| Target cell | HEAD (= rev5) | Expected |
|---|---|---|
| "non–CLDN18.2" (en dash; **E2E**, AK132) | SOURCE_NAMES_REQUIRED_TARGET: "'non–CLDN18.2' names CLDN18 (Claudin 18.2), but no target set was built from it" | SOURCE_STATES_NOT_REQUIRED_TARGET |
| "non—VORP3.1", "non‐VORP3.1", "not–VORP3.1" | SOURCE_NAMES_REQUIRED_TARGET | same |
| "CLDN18.2‑negative" (U+2011), "VORP3.1‐negative" (U+2010), "VORP3.1−negative" (U+2212) | SOURCE_NAMES_REQUIRED_TARGET | same |

- This is the exact opposite of the record (REVIEW2's N6 harm), but it needs non-ASCII input. Fix: normalise every
  Unicode dash and hyphen to "-" before matching, on both sides of the symbol.

### E5 (low; N1 residue). "ALL" before "disease", "disorder", "condition", "malignancy", "cancer" or "carcinoma" is still the word "all"

`_before_basket_word` now accepts `_BASKET_HEADS | {"solid", "comers"}`. `_BASKET_HEADS` contains disease, disorder,
condition, malignancy, malignant, carcinoma and neoplasm, not only plural tumour heads.

| Request | Record name | HEAD | Expected |
|---|---|---|---|
| ALL-A | "Adult ALL disease" (**E2E**, RC118: "names no disease or site (a basket)") | BASKET | READS_AS_REQUESTED or UNREADABLE (not a basket) |
| ALL-A | "ALL disease", "ALL Disease", "Relapsed ALL disease", "Relapsed/refractory ALL disease", "ALL disorder", "ALL malignancy", "ALL carcinoma", "ALL condition", "ALL-disease" | BASKET | UNREADABLE |
| controls | "ALL cancers", "ALL solid tumors", "ALL COMERS", "ALL tumors" | BASKET | (basket is a fair reading) |

- Judgement on reach: "ALL disease" is uncommon in vendor cells, so this is low. A narrower rule (plural heads,
  "solid" and "comers") or REVIEW5's robust alternative (an acronym the index reads as one disease is never a
  basket word unless followed by "comers" or "solid") would close it.

### E6 (low). Lexical gaps and an order asymmetry in the negation reading

- "CLDN18.2 not expressed", "VORP3.1 expression absent" and "absent VORP3.1" → SOURCE_NAMES_REQUIRED_TARGET: "names
  …". Explicit absence is missed. Pre-existing.
- "CLDN18.2 negative or low" → STATES_NOT ("states it is not CLDN18.2"), but "CLDN18.2 low or negative" →
  SOURCE_NAMES_REQUIRED_TARGET. Same meaning, opposite classes, by word order. The response keeps "negative or low"
  as a judgement (expression "low" names the target), but under that same rule the first cell should not be
  STATES_NOT either.

### E7 (low). Role words after a site drop a real requested site

`_ROLE_AFTER` contains "metastatic", "refractory" and "resistant", so the site before them is masked:
"Gastric metastatic adenocarcinoma", "Gastric Metastatic Cancer", "Gastric refractory cancer", "Gastric
treatment-refractory cancer" and "Gastric resistant cancer" → UNREADABLE ("not a name the NCIt authority can
read"). Expected: NAMES_REQUESTED_SITE. The sentence is true, but it understates the record and sorts it below
the site group. "Gastric, metastatic" and "Gastric advanced or metastatic cancer" → NAMES_REQUESTED_SITE (correct).
Pre-existing.

### Cosmetic

- `site_phrases("cutaneous melanoma")` includes "skin stage unspecified" and "skin unspecified". These are NCIt
  index keys with non-site words kept. They only matter if a record repeats them, and "skin" matches first.
- `site_phrases("colorectal adenocarcinoma")` is only "colorectal" ("colon", "rectal" are lost). This is an
  understatement on unreadable names; judgement.

## Judgement calls (labelled; not counted as defects)

- **J-a. The screen's coordination reading is lossy and asymmetric (outside U1).** With a UC request, "Crohn's
  disease or ulcerative colitis" passes the indication gate (VBC108, ELIGIBLE in `ws_e2e_uc6`), while "Ulcerative
  colitis or Crohn's disease" is UNKNOWN. The Screening sheet discloses the reading ("read as 'Lung Non-Small Cell
  Carcinoma' (coordination expanded)"). Changing that is a gate change, outside this cycle. It should go to the
  owner of `indications.py`. E1 is U1's part: U1 turns that reading into a class and a sentence about the record.
- **J-b. The stage-only sibling rule held on my inputs.** I tried 107 names, mostly stage names, under 19 requests
  across lung, prostate, kidney, skin, ovary, colon, liver, head and neck, bladder, cervix, endometrium, pancreas,
  oesophagus, breast, lymphoma, brain and stomach (`sib6.py`). UNDER_REQUESTED_PARENT was given only to stage
  concepts of the request's own site and lineage. Examples: "Stage IV Lung Cancer AJCC v8" for lung adenocarcinoma,
  "Stage D prostate cancer", "Stage IV ovarian cancer" for high-grade serous, "Stage IV cervical cancer" for cervical
  SCC, "Stage IV pancreatic cancer" for PDAC, "Stage IV gastric cancer". Concepts of other histologies (small cell
  lung, esophageal adenocarcinoma for ESCC, Wilms, uveal melanoma, Merkel cell) → DIFFERENT_DISEASE or
  OVERLAPS_REQUESTED by NCIt's own graph. Unreadable names that name the requested site ("Stage IV lung squamous cell
  carcinoma" for lung adenocarcinoma, "Stage IV gastric lymphoma", "Stage IV gastric GIST") → NAMES_REQUESTED_SITE,
  as the acceptance rule specifies; the sentence is true but sorts them high. Two readings come from the screen or
  the index, not the rule: "Stage IV kidney cancer" reads as "Stage IV Renal Cell Cancer AJCC v6", and "Stage IV
  endometrial cancer" as the "Uterine Corpus Carcinoma or Carcinosarcoma" stage grouping. I did not repeat REVIEW5's
  full 7,680-request sweep; that code is unchanged since revision 5.
- **J-c. Site rule and lineage list.** `site_phrases` over 70 requests (solid tumours, haematology, immunology, neurology, metabolic, respiratory, renal, cardiology and ophthalmology; `sites6.py`) gave only
  anatomical places, apart from the cosmetic case above. Haematological, immunological, neurological and metabolic
  requests have none (as designed). "Chronic kidney disease" has "kidney" and "renal". No lineage word was kept, and
  no real site was lost apart from the colorectal subsites.
- **J-d. Placeholders.** "Undisclosed (likely CLDN18.2)" → "'likely CLDN18.2' names CLDN18 …; also on record:
  'Undisclosed'". "TBD; not CLDN18.2" → STATES_NOT. "PD-1 x TBD" → names 'PD-1' only. All are true to the record.

## Reading `after/` as a BD analyst

The 38 CLDN18.2 actions are unchanged from revision 5 (`unknown_diagnostics` identical between `fin12_ws` and
`after/screening_u1.json`). REVIEW4's and REVIEW5's reading still holds:
- Each action says what is on record, its class, and the one cited fact that would decide the gate, with the
  `assert` field.
- The PD-1 rows name TIGIT, CTLA-4 and 'PD-1'.
- The six basket rows name both requested indications.
- The "Imaging agent" rows give the allowed modalities.
- The memo's single-gate list (15 programs) has no scope or recommendation words.

Still less useful:
- The repeated "The gate never fails on this evidence…" tail on 24 rows.
- DR30303's "'Malignant Neoplasm of Digestive System' is not a name the NCIt authority can read".
- "(+1 more)" in the memo's basket group.
- 'PD-1' is "not read by the target authority" (an authority gap, not U1).

Nothing is hidden: every UNKNOWN on a non-excluded program has its diagnostic, here and in every E2E workspace. The
risk an analyst would not see is E1. It needs an "or" between two full disease names, which this landscape does not
contain. If it did, a program with a gastric adenocarcinoma record would be filed among "different diseases".

`after/` is not regenerated at HEAD. It differs from a fresh run only in R1 rights wording (memo line 31, two
Screening cells), which `55ac585` wrote and which match `research/dealscreen_rights_v1/after_v12/`.

## What I could not check

- Whether the new tests were written before the code was tuned.
- Workbooks and memos for the held-out landscapes; I read their `screening.json` only. For the E2E workspaces I
  generated the GAS workbook and both memos.
- The `.docx` memo was regenerated but not opened.
- Domain judgements used to rate harm, not checked against an authority: that "UC or Crohn's disease" and
  "Myasthenia gravis or CIDP" are common landscape strings; that "CLDN18.2 negative, positive PD-L1 expression"
  describes a CLDN18.2-negative program; and how often Unicode hyphens survive vendor exports. The NCIt claims
  (index readings of UC, Crohn Disease, CIDP, AML, NSCLC; stage groupings; site phrases) were checked against the
  frozen authority through the U1 code.
- E1–E5 fixes were not implemented or tested.
- I did not repeat REVIEW5's full stage-sibling sweep (code unchanged).
- The rights code (under concurrent review): not touched. I used it only to attribute the two transaction changes.

## Reproduction

```
cd /home/djmann/projects/bve-b8 && . .venv/bin/activate && export TMPDIR=$HOME/.cache/dealscreen_suite
# run every probe from the repository root (the S&E target snapshot path is relative)
python -m pytest tests/dealscreen -q -p no:cacheprovider              # 1575 passed, 5 warnings, 414 s
P=/tmp/claude-1000/u1rr6b/probes
python $P/t6.py; python $P/t6_r5.py            # E2, E3, E4, E6 (t6_r5 = revision 5 modules)
python $P/i6.py; python $P/i6b.py              # E5; coordination readings
python $P/i6c.py; python $P/i6c.py r5          # E1 across therapy areas; r5 = revision 5 modules (identical)
python $P/misc6.py                             # E7, real-reader target rows, placeholders
python $P/sib6.py; python $P/sites6.py         # J-b, J-c
python $P/nou1.py <copy of fin12_ws>           # screen with U1 stubbed out (U1-3 attribution)
python3 /tmp/claude-1000/u1rr/science_diff.py <screening.json> <reference screening.json>
python3 /tmp/claude-1000/u1rr/coverage.py <screening.json ...>
python3 /tmp/claude-1000/u1rr5/probes/show.py <screening.json> <program names>
```

Scratch workspaces (copies; the originals were not modified):
- `/tmp/claude-1000/u1rr6b/ws_copy`: a fresh CLDN18.2 screen (byte-identical to `fin12_ws`), export (`out.xlsx`) and
  memo (`memo.md`).
- `/tmp/claude-1000/u1rr6b/ws_nou1`: the same with `diagnose` stubbed out.
- `/tmp/claude-1000/u1rr6b/r5_ws_e2e_all5`, `r5_ws_e2e_gas5`: copies of REVIEW5's E2E workspaces, re-screened at HEAD.
- `/tmp/claude-1000/u1rr6b/ws_e2e_gas6` (inputs in `e2e_gas6/`, with `out.xlsx` and `memo.md`): the CLDN18.2 inputs
  with these cells: SOT102 indication "Pancreatic, gastric or esophageal adenocarcinoma", Q-1802 "Gastric
  Adenocarcinoma or Pancreatic Ductal Adenocarcinoma", VBC108 "Gastric adenocarcinoma or NSCLC", RC118 "Adult ALL
  disease"; targets SG1906 "CLDN18.2 negative, positive PD-L1 expression", AK132 "non–CLDN18.2" (en dash), TQB2103
  "CLDN18.2 negative and/or positive".
- `/tmp/claude-1000/u1rr6b/ws_e2e_uc6` (inputs and `memo.md` in `e2e_uc6/`): buyer indications `[ulcerative colitis]`;
  SOT102 "Ulcerative colitis or Crohn's disease", Q-1802 "UC or Crohn's disease", VBC108 "Crohn's disease or
  ulcerative colitis".
- Equivalence: `/tmp/claude-1000/u1rr6b/equiv.log`.
