# Indication gate semantics: parser defect #3

Status: **FROZEN**, 2026-09-26, written before any code change. The operator ordered this as a
narrow milestone ahead of ranking. Defect: `docs/se_parser_defects.md` #3. Evidence:
`docs/se_candidate_population_validation.md`, Finding 1.

## Defect

When the caller does not pass `--indication`, the compiler copies the intent's residual tokens
into `strategic_gap.indications` as independent literals. For `tac01_control_a1` these are
`relapsed`, `refractory`, `B-cell`, `lymphoma`. `strategy.indication` then asks whether each
registry condition string *is one of* those words (`IN`, exact).

"Relapsed/Refractory Diffuse Large B-cell Lymphoma" is not the word `lymphoma`, so every asset
with a condition fact FAILs. Every reference CD19 CAR-T is EXCLUDED.

## The change (exactly three parts)

1. **Phrase grouping in the compiler, not the parser.**
   - Residual spans that are adjacent in the query form one phrase. Adjacent means the text
     between two spans is only whitespace, `/`, `,`, `-`, or the connectors `or`/`and`.
   - `SearchIntent.residual_terms` is **unchanged**. It also feeds trial retrieval
     (`intent_to_trial_query`), and retrieval must be identical for the sealed replay to be
     valid.
2. **Concept resolution.** A phrase compiles to one indication concept when, after removing
   disease-status qualifiers and connectors, what remains is exactly one of the concept's
   request surfaces.
   - Everything else about the question compiles **exactly as before**, including the per-token
     literal fallback for a phrase that does not resolve.
   - Caller-supplied `--indication` values stay literal, as the CLI documents. That is out of
     scope here and logged as a follow-up.
3. **Concept matching in `strategy.indication`.** This applies only when the requirement
   contains a concept. An all-literal requirement is evaluated by the existing
   `evaluate_requirement`, unchanged.

### Frozen vocabulary

Text is normalised as follows: casefold; every non-alphanumeric character becomes a space; runs
of whitespace collapse. Terms match on whole-word boundaries in the normalised text. The two
stems `malignan` and `haematolog` are word prefixes (`malignancy`, `malignancies`,
`haematological`).

**Status qualifiers.** These are recognised in the query phrase and not enforced:
`relapsed`, `refractory`, `recurrent`, `r r`.
- A registry condition field does not reliably state disease status. Requiring it would
  exclude on missing data.
- The qualifier is disclosed here as unenforced. The parse-time residual warning continues to
  list it.

**Concept `INDICATION:B_CELL_LYMPHOMA`** (the B-cell non-Hodgkin lymphomas, per the WHO
classification):
- Request surfaces: `b cell lymphoma`, `b cell non hodgkin lymphoma`, `b cell nhl`, `b nhl`.
- **MATCH terms** (the condition names the concept or a subtype of it): `b cell lymphoma`,
  `lymphoma b cell`, `b cell non hodgkin`, `b cell nhl`, `b nhl`, `large b cell`, `dlbcl`,
  `lbcl`, `follicular lymphoma`, `lymphoma follicular`, `mantle cell lymphoma`,
  `lymphoma mantle cell`, `marginal zone lymphoma`, `lymphoma marginal zone`, `malt lymphoma`,
  `burkitt`, `primary mediastinal`, `pmbcl`, `small lymphocytic lymphoma`,
  `high grade b cell`, `hgbl`, `transformed follicular`.
- **DISJOINT terms** (a lymphoma that is not B-cell NHL): `hodgkin` (when not preceded by
  `non`), `t cell lymphoma`, `lymphoma t cell`, `peripheral t cell`, `cutaneous t cell`,
  `mycosis fungoides`, `sezary`, `anaplastic large cell`, `nk t cell`.
- **BROADER terms** (an ancestor that neither confirms nor rules out B-cell NHL): `lymphoma`,
  `non hodgkin`, `nhl`, `lymphoproliferative`, `hematologic malignan`,
  `hematological malignan`, `haematolog`, `b cell malignan`, `b cell neoplasm`.

### Classifying one condition fact

The first rule that applies wins:
1. MATCH, if any MATCH term occurs.
2. NO, if any DISJOINT term occurs.
3. UNDETERMINED, if any BROADER term occurs.
4. Otherwise NO. Every such fact FAILs today as well, so this step loosens nothing.

A requested literal (fallback) matches a fact only by the existing exact `IN` comparison.

### Gate decision (union, as in the TA gate)

- The existing no-fact, conflict and staleness guards apply first (`_undecidable`).
- PASS if any indication fact is MATCH. An asset developed in several indications addresses
  the requested one if any of them is it.
- Otherwise UNKNOWN if any fact is UNDETERMINED.
- Otherwise FAIL.

## Not changed

- the parser
- `residual_terms` and the parse warnings
- retrieval and extraction (claims and facts are byte-identical)
- identity, target resolution, modality, the TA gate, human-PoC, source coverage and ranking
- defects #1, #2 and #4, the duplicate/wrong-target/arm-asset findings, and any
  caller-supplied `--indication`

## Evaluation

The evaluation uses sealed replays: the change is downstream of acquisition, and retrieval is
unchanged. The user runs them in their own terminal.

1. **TAC01**
   - replay of `tac01_control_a1/custody`
   - baseline: `se_runs/tac01_ta_fix_a1d` (accepted TA fix)
   - scored with `scripts/se_indication_gate_compare.py`, frozen with this declaration
2. **mint5**
   - replay of `mint5_on/custody`
   - baseline: `se_runs/mint5_ta_fix_a1`

**If TAC01 fails any criterion, stop.**

## Acceptance criteria

- **B1 — recovery for the right reason.** Each of the canonical records `Axicabtagene
  Ciloleucel`, `Tisagenlecleucel`, `Lisocabtagene Maraleucel`, `Brexucabtagene Autoleucel` and
  `TAC01` must:
  - be neither EXCLUDED nor low-support;
  - have `strategy.indication` = PASS;
  - have no other gate decision changed.
- **B2 — no leak.** Both checks below must hold.
  - **Mechanical:** no asset's `strategy.indication` moves FAIL→PASS or FAIL→UNKNOWN unless at
    least one of its indication facts contains a term from the MATCH or BROADER lists.
  - **Review:** every distinct condition string classified MATCH is listed in full. Zero may
    name a disease that is not a B-cell non-Hodgkin lymphoma. The judgement is recorded with
    the result.
- **B3 — isolation.**
  - The candidate and low-support sets are identical to the baseline.
  - Facts are identical to the baseline.
  - Search attempts are identical to the baseline.
  - Every decision other than `strategy.indication` is unchanged.
- **B4 — attribution.** Every disposition change coincides with a `strategy.indication` status
  change.
- **B5 — mint5 invariance.**
  - mint5 compiles no indication requirement; its baseline `indications` is `[]`.
  - Every gate decision and disposition is identical to `mint5_ta_fix_a1`.

## Predictions (reported, not criteria)

- TAC01 problem: `indications: [INDICATION:B_CELL_LYMPHOMA]`.
- Most of the 607 `strategy.indication` FAILs move, to PASS (B-cell NHL trials) or to UNKNOWN
  (generic "lymphoma" records).
- Records whose conditions are ALL, CLL, myeloma, autoimmune or solid tumours stay FAIL.
- `Obecabtagene autoleucel` and `KITE-363` stay EXCLUDED on `strategy.therapeutic_area`
  (defect #4 territory). This is not a B1 failure; they are not B1 records.
- The visible population gains a trial-linked tier, where TAC01 had 0.

## Result: TAC01 (appended 2026-09-27)

Code `e84f2f2`. Sealed replay `se_runs/tac01_ind_fix` scored against `tac01_ta_fix_a1d` with the
frozen scorer; raw output at `se_runs/tac01_ind_fix/ind_compare.txt`. **All criteria PASS.**

- **B1:** 5/5. Axi-cel, tisa-cel, liso-cel, brexu-cel and TAC01 are all UNRESOLVED with
  `strategy.indication` PASS.
- **B2 mechanical:** 246 FAIL→PASS/UNKNOWN moves, all explained by a lexicon term.
- **B2 review:** all 93 distinct MATCH strings name B-cell NHL. Two were judged at the boundary:
  - "B-cell lymphoma, unclassifiable, intermediate between DLBCL and classic Hodgkin" is WHO
    grey-zone lymphoma, which is a B-cell lymphoma.
  - "CLL/SLL" strings match through SLL, which is a declared term. CLL alone does not match.
- **B3:** candidates, low-support, facts and search attempts are identical, and no
  non-indication decision changed.
- **B4:** 214 disposition changes, all EXCLUDED→UNRESOLVED, each with an indication change.

Predictions (reported, not criteria):
- `strategy.indication` went from FAIL 607 / UNKNOWN 836 to FAIL 361 / PASS 175 / UNKNOWN 907.
- Visible assets went from 469 to 683; visible assets with an indication fact went from 0 to 214.

## Result: mint5 (appended 2026-09-27)

Sealed replay `se_runs/mint5_ind_fix` scored against `mint5_ta_fix_a1`; raw output at
`se_runs/mint5_ind_fix/ind_compare.txt`. **B5 and B3 PASS.** mint5 compiles no indications
(`[]`), and its decisions, dispositions, candidates, facts and search attempts are identical to
the baseline.

**Verdict: the fix is ACCEPTED.** TAC01 (CD19 oncology) is now the oncology ranking benchmark,
and mint5 (dual CD19/BCMA autoimmune) is the autoimmune ranking benchmark.
