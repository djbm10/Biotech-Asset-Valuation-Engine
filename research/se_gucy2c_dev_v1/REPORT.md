# GUCY2C pilot remediation: development report

**Grade: DEVELOPMENT.** Every number here comes from replaying the sealed custody corpus
of the frozen pilot `gucy2c_oncology_v1`. It is scored against that pilot's AI-prepared
reference, which has already been disclosed, and the fixes were designed after reading the
pilot's failures and the reference's asset names. **This is not independent or
out-of-sample validation.**

The frozen pilot is unchanged: its preregistration, sealed outputs, report and score.
Policy and acceptance criteria: `docs/se_policies/gucy2c_pilot_remediation_v1.md`
(frozen at `1925156` before implementation; amendments 1–2 are recorded there).

## What was run

All runs used the same sealed bytes: `~/se_runs/gucy2c_pilot_v1/run/custody`. The as-of
date was 2026-10-24 throughout, and the evaluation definitions came from the pilot
scorer's own `_compute`.

| Run | Code | Problem | Wall clock | Peak RSS |
|---|---|---|---:|---:|
| baseline | `845316e` (pilot code) | frozen `engine_problem.yaml` | 38:03 | 3.71 GB |
| ta_only | `845316e` | TA fixed only (`engine_problem_ta_fixed.yaml`) | 37:03 | 3.72 GB |
| after_c11 | this change (C1–C9, C11) | `engine_problem_dev.yaml` (TA fixed, plus the spec's agonist exclusion) | 2:01 | 2.44 GB |

The baseline replay reproduces the sealed pilot summary exactly; only the run id and
timing differ. Commands: `replay.sh`, `dev_evaluate.py` and `diagnose_ctgov.py` in this
folder. The results JSONs are in `results/`.

**Replay limit.** Sealed custody is keyed by query text. In `after_c11`, 4 queries failed
because they are *new* follow-up leads with no sealed record: PF-07062119 and XKDCT080, on
CT.gov and PubMed. Their own trials were already in hand. Measuring what a live follow-up
for them would add needs a live run. C10, the change to the compiled query string, cannot
be replayed at all; it is verified by tests only.

## Results

"Visible" means the analyst-visible population: eligible plus review. The pilot reported
this as the review population (474).

| Measure | baseline | ta_only | after_c11 |
|---|---:|---:|---:|
| Candidates (all) | 5,984 | 5,984 | 279 |
| Analyst-visible | 474 | 469 (2 eligible: both EB-DUO entries) | 32 |
| Named in-scope assets recovered, all | 8/17 | 8/17 | 12/17 |
| Named in-scope assets recovered, visible | 6/17 | 6/17 | 12/17 |
| Visible strict precision | 1.3% (6/474) | 1.3% (6/469) | 37.5% (12/32) |
| Visible adjudicated precision (TP ÷ TP + control hits) | 67% | 67% | 92% |
| Negative controls visible | 3/9 (all three agonists) | 3/9 | 0/9 |
| Agonist controls EXCLUDED with recorded reason | 0 | 0 | 3 (`target_action_type = AGONIST`) |
| Trial coverage, overall, all registry ids | 33% | 33% | 52% |
| Trial coverage, overall, NCT ids only | 42% | 42% | 65% |
| Trial coverage, recovered assets only | 48% | 48% | 63% |
| Scorer merge errors / split errors | 0 / 0 | 0 / 0 | 0 / 1 (R-005) |
| Engine identity merges | 23 | 23 | 2 |
| Stated targets correct / stated | 1/1 | 1/1 | 1/1 (11 of 12 recovered assets UNKNOWN) |
| False construct targets on recovered assets | 1 (EB-DUO: KALRN, plus IL15) | – | 0 |
| Human PoC asserted for an out-of-area control | 1 (plecanatide) | – | 0 (kept as `human_efficacy_outside_requested_area`) |

Changes per in-scope reference asset (baseline → after_c11):

| Ref | Baseline | after_c11 | Change |
|---|---|---|---|
| R-001 indusatumab vedotin | REVIEW "TAK-264", 4/4 trials | same | – |
| R-002 TAK-164 | REVIEW | REVIEW | – |
| R-003 PF-07062119 | **missed** (trial acquired, dropped) | REVIEW, NCT04171141 | C4 |
| R-004 Ad5-GUCY2C-PADRE | label "vaccine" (LOW) | REVIEW "Ad5-hGCC-PADRE" | C6, C11 |
| R-005 Ad5.F35-hGCC-PADRE | LOW | REVIEW, **split** into two spellings (NCT07417488, NCT04111172) | C6, C11; split not merged (no safe evidence) |
| R-006 Lm-GUCY2C | label "vaccine"/"CT Scan" | REVIEW "Lm-GUCY2C" | C5, C6, C11 |
| R-007 LYL273 | REVIEW | REVIEW | – |
| R-008 IM96 | REVIEW | REVIEW | – |
| R-009 LCAR-G08 | LOW "LCAR-G08 cells" | REVIEW "LCAR-G08" | C6, C11 |
| R-010 XKDCT080 | REVIEW under descriptor label | REVIEW "XKDCT080" (descriptor kept as alias) | C6 |
| R-011 WD-01 | REVIEW | REVIEW | – |
| R-015 EB-DUO-CAR-NK-CEA/GCC | REVIEW ×2 (split by "(IV)"), false KALRN | one candidate, both trials, construct set {GUCY2C} | C6, C7 |
| R-012, R-014, R-017 | not acquired | not acquired | source acquisition |
| R-013, R-016 | generic label | generic label ("CAR-T", "CAR-T cells"), LOW | none: the records name no product |

Acceptance (A1–A11, from the frozen policy):

| | Criterion | Result |
|---|---|---|
| A1 | Frozen problem refuses to load; bare string refuses to compile | **PASS** (tests) |
| A2 | PF-07062119 a candidate with NCT04171141; partners not nominated | **PASS** |
| A3 | The 31 irrelevant no-output records yield no candidate | **PASS** |
| A4 | Visible named in-scope ≥ 6/17, none lost | **PASS** (12/17, none lost) |
| A5 | Visible ≤ 237 and all ≤ 2,992 | **PASS** (32; 279) |
| A6 | No agonist visible; each EXCLUDED with reason; no other control visible | **PASS** |
| A7 | No KALRN/IL15 on EB-DUO; no new false target | **PASS** |
| A8 | EB-DUO one candidate with both trials; scorer merges 0 | **PASS** |
| A9 | Vaccines, LCAR-G08, XKDCT080 carry product names; no generic "vaccine"/"CT Scan" holding a reference trial; nothing invented | **PASS** |
| A10 | Plecanatide has no `human_poc_present`; evidence retained | **PASS** |
| A11 | Wall clock ≤ baseline + 20%; RSS ≤ 4.5 GB | **PASS** (2:01, 2.44 GB) |

The final code, after the serializer fix made for the frozen oracles, was replayed again
(`after_final`, 2:09, 2.47 GB). Its counts, scores, routing and gate decisions are
identical to `after_c11`.

C11 (amendment 2) is reported on its own. On top of C1–C9 it moves exactly the 5 named
`BIOLOGICAL` products from LOW_SUPPORT to review (27 → 32 visible, 8 → 12 named), and adds no
other candidate. Its cost across the rest of the S&E suite: no test failed on it.

**Declared cost of C9.** A document that reports a response without naming any
classified disease no longer establishes in-area human PoC; the evidence is kept as
`human_efficacy_outside_requested_area`. One synthetic test fixture had to name its
disease (see the policy's test-change record).

## Root causes (summary; the full table is in the policy)

1. **The letter-split therapeutic area was operator error enabled by the code.**
   `compile_intent(therapeutic_areas="ONCOLOGY")` reproduces the frozen file
   byte-identically, and the CLI path is not affected. The compiler called `list()` on a
   string, and the schema accepted one-letter areas. Both now refuse. Fixing it alone (ta_only) changes almost nothing: 469 visible instead of 474, the three agonists stay visible, and recall is unchanged. The only new decisions are both EB-DUO entries becoming ELIGIBLE, and they are still split.
2. **Candidate explosion: two defects compounding.**
   - The shared alias `STAR`, refused by the frozen admission policy, was reintroduced
     from the problem's recognition alias list. It accounted for 557 of 630 CT.gov records.
   - Follow-up leads were treated as target terms. A follow-up for "Walking" made every
     document mentioning "walking" GUCY2C-relevant.
3. **Context-free short aliases.** `GCC` has at least nine meanings in this corpus. It
   counts as the target only in a target frame, or next to a longer target name.
4. **The trial-to-asset drop was a single confirmed defect: PF-07062119.** It is a
   multi-intervention trial, and the target text is not repeated in the drug's own
   intervention field. The other 31 no-output records are irrelevant documents.
5. **Naming.** Class words beat product codes, form and route suffixes became identities,
   and descriptor interventions ignored the code named in the title and arm.
6. **Relevance.** The authority knew linaclotide, plecanatide and dolcanatide were
   AGONISTs, but the action type never reached a fact. The human-PoC prose route had no
   disease scope.

## Unresolved failures

- **19 of the 32 visible candidates are not GUCY2C programs.** They are reagents and
  co-mentioned drugs from PubMed abstracts that name GUCY2C: laxatives from constipation
  reviews (bisacodyl, senna, lactulose, polyethylene glycol), assay reagents (fluorescein,
  dextran, water) and others. They stay in review because their therapeutic area is
  UNKNOWN: the TA lexicon classifies only oncology and autoimmune, so "constipation" is
  never evidence *against* oncology. Fixing this needs a declared change to TA gate
  semantics, which was not made here.
- **Targets and modality are mostly UNKNOWN.** 11 of 12 recovered assets have no stated
  target, and modality is stated for 3. EB-DUO now has the correct construct fact, but
  `target_ids` is filled only from confirmed assertions.
- **Nothing is eligible.** The agonist exclusion is UNKNOWN for every asset the
  drug-target authority does not know, which is all the cell and vaccine products. They
  stay in review, as intended, but a cleaner analyst view needs a modality-aware reading
  (an ADC or CAR-T cannot be an agonist peptide), and that was not attempted.
- **R-005 is split** across two registry spellings. No evidence safe for merging links
  them.
- **R-013 and R-016** remain generic ("CAR-T", "CAR-T cells"): the registry records name
  no product.
- **R-012, R-014 and R-017 were never acquired.** One is ChiCTR-only; the other two are
  CT.gov records the target query did not return.
- **The `hSTAR` acronym** (NCT05052957, "hSTAR GBM") still matches as a whole word. It
  produces no candidate here.
- **Commercial facts:** none. Owner, licensee and rights are absent, as in the pilot.
- **The 2 new follow-up leads** (PF-07062119, XKDCT080) could not be measured; this needs
  a live run.
