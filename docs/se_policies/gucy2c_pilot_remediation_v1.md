# GUCY2C_PILOT_REMEDIATION v1

**Status: OPEN — diagnosis and acceptance criteria frozen before implementation.**
Development-only. The frozen pilot `research/se_blinded_pilot_v1/gucy2c_oncology_v1/`
(preregistration `e909f4d`, seal `f7f3fad`, score `845316e`) is not modified, re-scored
or re-graded. Every measurement below is made on its sealed custody corpus and is a
**development result on a disclosed example, not independent or out-of-sample
validation.**

Diagnostic evidence: `research/se_gucy2c_dev_v1/` (per-trial CT.gov loss diagnostic,
alias-term census, key-asset extract). Baseline replay of the sealed corpus at
`845316e` reproduces the sealed summary exactly except run id and timing (38 min, 3.8 GB).

## Root causes established

| ID | Failure observed in the pilot | Root cause (located) |
|---|---|---|
| D1 | `therapeutic_areas: [O,N,C,O,L,O,G,Y]`; TA gate UNKNOWN for every asset | Operator called `compile_intent(therapeutic_areas="ONCOLOGY")`; compiler does `list(value)`; `StrategicGap` accepts any `list[str]`. Reproduced byte-identically. The CLI (`action="append"`) is not affected. |
| D2 | 557/630 CT.gov records and most PubMed hits matched GUCY2C only via `STAR` | `STAR` is a shared alias refused by `retrieval_alias_admission_v1`, but problem-supplied aliases (the full recognition set) are re-added by `compile_problem_queries`, `QueryVocabulary.for_query` and `query_facets`, bypassing the frozen policy. |
| D3 | 5,984 candidates; arbitrary trials/abstracts "about" GUCY2C | A follow-up query's lead term is added to the *target* recognition vocabulary (`for_query`, single target), so a follow-up for "Walking" makes every document containing "walking" GUCY2C-relevant and every co-mentioned drug a hit. Leads are queued for non-drug intervention names ("Walking", "index", "Novel", "CT Scan"). |
| D4 | "GCC" matched cancer-center protocol codes, retinal ganglion cell complex, Gulf Cooperation Council, a GCC regimen, FMR1 GCC repeats, brand names | `GCC` is a sole-claimant alias, so it is searchable and recognised by substring with no context. In the 49 GCC-only records the target sense always appears in an explicit frame ("targeting GCC", "GCC-positive", "expression of GCC"); the other senses never do. |
| D5 | PF-07062119 (NCT04171141) dropped silently | Multi-intervention trial: target inherited from protocol text only when exactly one intervention exists; PF-07062119's own intervention text does not repeat the target, so the intervention-target filter discarded it. The other 31 no-output records are irrelevant documents (STAR/GCC senses), correctly producing nothing. |
| D6 | "vaccine", "CT Scan" absorbed two vaccine programs | `extract_observed_asset_names("Ad5-hGCC-PADRE vaccine") == ["vaccine"]` — the class word is chosen and the product code lost. `DIAGNOSTIC_TEST`/`PROCEDURE` interventions are nominated as assets. |
| D7 | "LCAR-G08 cells" LOW_SUPPORT; "EB-DUO-CAR-NK-CEA/GCC (IV)" split | When extraction yields nothing the raw intervention name, with product-form ("cells", "vaccine") or route ("(IV)") suffix, becomes the identity. |
| D8 | XKDCT080 shown as "Chimeric antigen receptor T cell preparation targeting GCC" | Intervention is a generic descriptor; the product code is explicit in the title and in the EXPERIMENTAL arm label that lists the intervention, and is not read. |
| D9 | EB-DUO construct targets `{GUCY2C, IL15, KALRN}` | `attributed_targets_in` resolves the code fragment `DUO` (KALRN alias) inside "EB-DUO-CAR-…", and reads "CAR, an IL-15 support element" across a comma. |
| D10 | Linaclotide/plecanatide/dolcanatide in REVIEW #1/#2/#6 with CONFIRMED_TARGET | The authority records them as GUCY2C **AGONIST** (indusatumab vedotin: BINDING AGENT), but the edge's `action_type` is dropped before facts are emitted, so the spec's agonist exclusion had nothing to act on — and the exclusion was not written into the problem. |
| D11 | Plecanatide `human_poc_present=True` in an oncology search | Prose route emits the fact from "more patients in plecanatide versus placebo…" (constipation) with no disease scope; the ranker uses it. |

## Changes (declared)

- **C1 (D1)** `compile_intent` refuses a bare `str` for `therapeutic_areas`/`indications`;
  `StrategicGap` rejects entries shorter than two characters.
- **C2 (D2, D3)** Target recognition vocabulary = canonical + `searchable_target_aliases`
  + problem/query aliases **not** claimed by another target entity. A follow-up lead is
  never a target term: at depth ≥ 1, a document that does not itself name the target may
  yield only the lead's own intervention/mention, which keeps its inherited discovery
  context. CT.gov retrieval facets use the same filtered vocabulary.
- **C3 (D4)** A target alias of ≤ 3 letters, all alphabetic and not the approved symbol,
  is target evidence in a document only if a longer alias of the same target also occurs,
  or one occurrence sits within two tokens of a target frame word (targeting, targeted,
  directed, specific, positive, expressing, expression, protein, antigen, receptor, CAR,
  ADC, bispecific, anti, against, binding, engager). Applies to query vocabularies only.
- **C4 (D5)** In a multi-intervention trial that names the target, an intervention
  inherits the protocol target only if it is the unique intervention that is the sole
  occupant of an EXPERIMENTAL arm and its name is a recognised identity.
- **C5 (D3, D6)** `DIAGNOSTIC_TEST`, `PROCEDURE` and `BEHAVIORAL` interventions are not
  nominated. Follow-up leads are queued only for names the shape-free extractor
  recognises (development codes, INNs).
- **C6 (D6, D7, D8)** Identity name from a structured intervention: a trailing route
  parenthetical or product-form word is removed when what remains is a single code-like
  token that is not a class term; this outranks an extracted class word. A generic
  intervention whose trial title and listing EXPERIMENTAL arm both name exactly one
  development code takes that code as its name (generic label kept as alias). Nothing is
  named when the record names no product ("CAR-T", "gucy2c cart cells" stay generic).
- **C7 (D9)** Construct-target reading: the cue window does not cross `, ; : ( )`; in a
  hyphen compound whose first part is an unresolvable code prefix, parts before the
  first cue are identifiers, not targets.
- **C8 (D10)** Authority `action_type` travels on the evidence reference and is emitted
  as fact `target_action_type` with the same claims as `construct_target_set`. The
  spec's exclusion is expressible as `required_biology: target_action_type NOT_IN
  [AGONIST]`; missing evidence is UNKNOWN (review), never PASS.
- **C9 (D11)** A prose efficacy sentence supports `human_poc_present` for a problem
  that states therapeutic areas only if its document supports one of them; otherwise it
  is retained as `human_efficacy_outside_requested_area`.
- **C10 (D2)** The compiled query string uses the same filtered alias set. **Not
  replayable** (sealed custody is keyed by query text); verified by tests only and
  committed separately after the replay measurement.

No change to qualification thresholds, gate semantics, ranking keys, identity merge
rules, the TA lexicon or any frozen experiment.

## Acceptance criteria (frozen before implementation)

Measured by replaying the sealed corpus with C1–C9 against the baseline replay, on a
development problem identical to the frozen one except `therapeutic_areas: [ONCOLOGY]`
(C1) and the C8 exclusion requirement. Scored with the pilot's evaluation definitions
against the pilot's AI reference, labelled DEVELOPMENT.

- **A1** Frozen problem refuses to load; a bare string refuses to compile (tests).
- **A2** PF-07062119 becomes a candidate carrying NCT04171141; Anti-PD1/Anti-VEGF do not.
- **A3** None of the 31 irrelevant no-output CT.gov records yields a candidate.
- **A4** Analyst-visible (review + eligible) named in-scope assets ≥ baseline (6/17),
  with no previously recovered asset lost.
- **A5** Analyst-visible population ≤ 50% of baseline (474) and all-candidate count
  ≤ 50% of baseline (5,984).
- **A6** None of the three agonist controls is analyst-visible; each is EXCLUDED with
  the `target_action_type` reason recorded. No other negative control becomes visible.
- **A7** No KALRN or IL15 in EB-DUO's construct set; no new false target on any
  recovered in-scope asset.
- **A8** EB-DUO is one candidate holding both trials; scorer merge errors stay 0.
- **A9** Ad5/Lm vaccines, LCAR-G08 and XKDCT080 carry product names; no generic
  "vaccine"/"CT Scan" candidate holds an in-scope reference trial; no invented name.
- **A10** Plecanatide has no `human_poc_present` for the oncology problem; the evidence
  is retained.
- **A11** Wall clock ≤ baseline + 20%; peak RSS ≤ 4.5 GB.

A criterion that fails is reported as failed. Recall gained by admitting large numbers
of irrelevant candidates does not count as success (A5 guards it).

## Amendment 1 (during implementation, before any replay of the changes)

Spot-checking C2/C3 on the sealed records found a further recognition defect not in the
frozen list: `QueryVocabulary.targets_in` matches target terms as substrings, so GUCY2C's
`hstar` matched the study identifiers `NORTHSTAR003`, `northstar 02 001` and `hSTAR013`
(NCT07747103, NCT05712421, NCT04431154, NCT02780492). **C3b:** a *query* vocabulary
matches target terms shorter than six characters on word boundaries only (longer terms
keep substring semantics: `hGUCY2C` in "Ad5.F35-hGUCY2C-PADRE" is GUCY2C, and a strict
boundary lost it in the first spot-check); the whole-ontology indexing vocabulary is
unchanged. Also in C3: a target whose sense the enclosing trial record has already
established (a longer alias in the record) needs no second frame inside that record's own
intervention text — without this, "EB-DUO-CAR-NK-CEA/GCC" lost its target in NCT07589517.
C4's sole-occupant test ignores the C5 non-therapeutic intervention types. Acceptance
criteria are unchanged.

## Amendment 2 (after the first development replay, before acceptance is assessed)

The first replay of C1–C9 left LCAR-G08, Ad5-hGCC-PADRE, Ad5.F35-hGUCY2C-PADRE (two
spellings) and Lm-GUCY2C in LOW_SUPPORT although each is now correctly named. Cause: the
structured-therapeutic route (`asset_qualification_tiered_evidence_v3`) accepts only
intervention type `DRUG`; CT.gov types cell, gene and vaccine products `BIOLOGICAL`. In this
corpus exactly 8 low-support candidates come from CT.gov records, all `BIOLOGICAL`: the 5
named products above and 3 class labels ("CAR-T", "CAR-T cells", "gucy2c cart cells").
**C11:** `BIOLOGICAL` counts as a structured therapeutic type. The class-term, comparator
and v6 vetoes that precede the route are unchanged and keep the 3 class labels out. This
modifies a v3 qualification decision; it is declared here and its cost outside this corpus
is measured by the full regression suite before adoption. Acceptance criteria unchanged;
the C11 effect is reported separately from C1–C9.

## Test changes made by this remediation

- `test_replay_determinism.py`: the synthetic press release for CLN-978 now names its
  disease ("with B-cell lymphoma"). Under C9 a document naming no classified disease cannot
  establish human PoC for an oncology question, so the fixture's only efficacy sentence
  had moved to `human_efficacy_outside_requested_area` and the module's non-vacuity check
  failed. This is the declared C9 cost: real sources that report a response without naming
  the disease anywhere in the document lose the in-area human-PoC fact (kept as the
  out-of-area fact). Loosening C9 to "withhold only when another classified area is named"
  would readmit plecanatide, since constipation is not a classified area.
- `test_study_identifier_boundary.py`: the stub vocabulary accepts the new `established`
  keyword of `targets_in`.
- `TargetEvidenceRef.action_type` is omitted from serialization when absent, so frozen
  oracles (`test_target_reference_interface.py`) and pre-existing dumps are byte-identical.
