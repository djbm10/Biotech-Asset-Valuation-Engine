# DealScreen on a real public landscape: FcRn antagonists in myasthenia gravis

**Grade: INTERNAL DEVELOPMENT.** The same AI environment curated the landscape, wrote the
manual reference, prepared the candidate list and reviewed the result. The reference was
committed (`fd4c6f8`) before DealScreen was run on the data. This is a workflow test, not
independent validation, and nobody approved anything.

## What was built (Phase 2)

| Item | Path |
|---|---|
| 40-program landscape | `examples/dealscreen_real/landscape_fcrn_gmg.csv` |
| Field-level provenance (393 rows: field, value, source, URL, date, quote/record) | `examples/dealscreen_real/field_provenance.csv` |
| Source snapshots | `examples/dealscreen_real/sources/` |
| Builder (deterministic, offline from the snapshots) | `research/dealscreen_real_v1/build_landscape.py` |
| Manual reference (pre-screen) | `examples/dealscreen_real/reference_manual_assessment.csv` |
| Buyer spec (hypothetical buyer) | `examples/dealscreen_real/buyer_fcrn_gmg.yaml` |
| Agent evidence library (verbatim public quotes) | `examples/dealscreen_real/evidence_library_public.json` |
| Hypothetical valuation inputs | `examples/dealscreen_real/valuation_assumptions_hypothetical.yaml` |
| Workbook, memo, decision log | `research/dealscreen_real_v1/deliverables/` |

### Sources

| Source | What it supplied | Date |
|---|---|---|
| ClinicalTrials.gov API v2, `query.cond=myasthenia gravis`, interventional (234 studies) | aliases, highest phase, status, sponsor, collaborators, trial IDs, conditions | retrieved 2026-10-28 |
| openFDA drug-label API | U.S. approval with a myasthenia gravis indication, labeler, label mechanism text | retrieved 2026-10-28; label effective dates per row |
| ChEMBL 37 / Open Targets 26.06 (S&E ontology snapshot) | drug→target edges with action type; ChEMBL molecule type | releases as named |
| [UCB press release, 27 Jun 2023](https://www.ucb.com/newsroom/press-releases/article/ucb-announces-us-fda-approval-of-rystiggor-rozanolixizumab-noli-for-the-treatment-of-adults-with-generalized-myasthenia-gravis) | rozanolixizumab U.S. approval and FcRn mechanism (agent library only) | 2023-06-27 |
| [Immunovant 10-Q, period ended 31 Dec 2025](https://www.sec.gov/Archives/edgar/data/1764013/000176401326000011/imvt-20251231.htm) | IMVT-1402 anti-FcRn; possible return of batoclimab rights to HanAll (agent library only) | period 2025-12-31 |

**Gaps in the sources:**
- **U.S. rights:** no source stated them for any program, so every cell is blank.
- **Rozanolixizumab and inebilizumab:** their U.S. labels are missing from openFDA, so rozanolixizumab shows the registry's highest phase (Phase 4) rather than "Marketed".
- **Curated fields:** "Therapeutic Area = Neurology" is a curator classification, and its provenance row says so.

## Screening result (actual run, real S&E ontology)

| | Count |
|---|---:|
| Imported | 40 of 40 rows (0 rejected, 0 duplicates) |
| ELIGIBLE | 4 |
| UNRESOLVED | 14 |
| EXCLUDED | 22 |

**Against the pre-committed reference:**

| Outcome | Count |
|---|---:|
| Correct eligible | 4 |
| Correct excluded | 21 |
| **Wrong inclusion** | **0** |
| **Wrong exclusion** | **0** |
| In scope but left for review (missed) | 5 of 9 in-scope programs |
| Out of scope but left for review (noise) | 8 |
| Reference itself unknown (SHR-2173, cizutamig) | 2 |

**Identity:**
- The authority proposed two merges within one company: batoclimab with RVT-1401, and gefurulimab with ALXN1720. Both are correct; neither was applied.
- HBM9161 (Harbour BioMed's code for batoclimab) got **no flag**. It is the same molecule held by a different territorial licensee, and the cross-company rule (built against MB-102-style false merges) suppresses that link.
- The two eculizumab biosimilars stay separate, which is correct.

**U.S. rights:** UNKNOWN for all 40 programs, including the three marketed FcRn products. That is true of the sources, but unhelpful: a U.S. label implies the labeler holds U.S. rights, and the rights reader does not draw that inference.

### Asset by asset

| ID | Program | Reference | DealScreen | Outcome | Gates not passed | Identity |
|---|---|---|---|---|---|---|
| RW-01 | Efgartigimod alfa (IV) | IN | UNRESOLVED | in scope but left for review (missed) | modality.required UNKNOWN |  Same molecule as RW-02 (different product/formulation) |
| RW-02 | Efgartigimod alfa and hyaluronidase (SC) | IN | UNRESOLVED | in scope but left for review (missed) | modality.required UNKNOWN, strategy.indication UNKNOWN |  Same molecule as RW-01 |
| RW-03 | Rozanolixizumab | IN | ELIGIBLE | correct: eligible | all gates PASS |   |
| RW-04 | Nipocalimab | IN | ELIGIBLE | correct: eligible | all gates PASS |  M281 = earlier Momenta code |
| RW-05 | Batoclimab | IN | UNRESOLVED | in scope but left for review (missed) | strategy.indication UNKNOWN | PROPOSED_MERGE:DRUG:BATOCLIMAB Same molecule as RW-06 and RW-07 |
| RW-06 | HBM9161 | IN | ELIGIBLE | correct: eligible | all gates PASS |  Duplicate of RW-05 (territorial licensee) |
| RW-07 | RVT-1401 | IN | ELIGIBLE | correct: eligible | all gates PASS | PROPOSED_MERGE:DRUG:BATOCLIMAB Duplicate of RW-05 |
| RW-08 | IMVT-1402 | IN | UNRESOLVED | in scope but left for review (missed) | target.expression UNKNOWN, modality.required UNKNOWN, biology.mechanism_direction UNKNOWN, strategy.indication UNKNOWN |   |
| RW-09 | Orilanolimab (ALXN1830) | IN | UNRESOLVED | in scope but left for review (missed) | strategy.indication UNKNOWN |   |
| RW-10 | Eculizumab | OUT | EXCLUDED | correct: excluded | target.expression FAIL |  Eculizumab biosimilars RW-11/RW-12 share the INN |
| RW-11 | Eculizumab-aeeb (BKEMV) | OUT | EXCLUDED | correct: excluded | target.expression FAIL |  Distinct product sharing INN with RW-10 |
| RW-12 | Eculizumab-aagh (EPYSQLI) | OUT | EXCLUDED | correct: excluded | target.expression FAIL |  Distinct product sharing INN with RW-10 |
| RW-13 | Ravulizumab | OUT | EXCLUDED | correct: excluded | target.expression FAIL, strategy.indication UNKNOWN |   |
| RW-14 | Zilucoplan | OUT | EXCLUDED | correct: excluded | target.expression FAIL, modality.required UNKNOWN, strategy.indication UNKNOWN |   |
| RW-15 | Gefurulimab | OUT | UNRESOLVED | out of scope but left for review (noise) | target.expression UNKNOWN, biology.mechanism_direction UNKNOWN, strategy.indication UNKNOWN | PROPOSED_MERGE:DRUG:GEFURULIMAB Same molecule as RW-16 |
| RW-16 | ALXN1720 | OUT | UNRESOLVED | out of scope but left for review (noise) | target.expression UNKNOWN, biology.mechanism_direction UNKNOWN, strategy.indication UNKNOWN | PROPOSED_MERGE:DRUG:GEFURULIMAB Duplicate of RW-15 |
| RW-17 | Pozelimab + Cemdisiran | OUT | EXCLUDED | correct: excluded | target.expression FAIL, strategy.indication UNKNOWN |  Composite program |
| RW-18 | Iptacopan | OUT | EXCLUDED | correct: excluded | target.expression FAIL, modality.required FAIL, strategy.indication UNKNOWN |   |
| RW-19 | Vemircopan (ALXN2050) | OUT | EXCLUDED | correct: excluded | target.expression UNKNOWN, modality.required FAIL, biology.mechanism_direction UNKNOWN |   |
| RW-20 | Claseprubart | OUT | UNRESOLVED | out of scope but left for review (noise) | target.expression UNKNOWN, modality.required UNKNOWN, biology.mechanism_direction UNKNOWN, strategy.indication UNKNOWN |   |
| RW-21 | Empasiprubart | OUT | UNRESOLVED | out of scope but left for review (noise) | target.expression UNKNOWN, biology.mechanism_direction UNKNOWN |   |
| RW-22 | Inebilizumab | OUT | EXCLUDED | correct: excluded | target.expression FAIL, biology.mechanism_direction UNKNOWN |   |
| RW-23 | Rituximab (investigator-sponsored) | OUT | EXCLUDED | correct: excluded | target.expression FAIL, biology.mechanism_direction UNKNOWN |  Multiple academic sponsors |
| RW-24 | Ublituximab | OUT | EXCLUDED | correct: excluded | target.expression FAIL, biology.mechanism_direction UNKNOWN |   |
| RW-25 | Mezagitamab (TAK-079) | OUT | EXCLUDED | correct: excluded | target.expression FAIL, biology.mechanism_direction UNKNOWN |   |
| RW-26 | Telitacicept | OUT | UNRESOLVED | out of scope but left for review (noise) | target.expression UNKNOWN, modality.required UNKNOWN, biology.mechanism_direction UNKNOWN, strategy.indication UNKNOWN |  Sponsor changed between trials (RemeGen; Vor Biopharma) |
| RW-27 | Povetacicept | OUT | UNRESOLVED | out of scope but left for review (noise) | target.expression UNKNOWN, modality.required UNKNOWN, biology.mechanism_direction UNKNOWN, strategy.indication UNKNOWN |   |
| RW-28 | Iscalimab (CFZ533) | OUT | EXCLUDED | correct: excluded | target.expression FAIL, strategy.indication UNKNOWN |   |
| RW-29 | Belimumab | OUT | EXCLUDED | correct: excluded | target.expression FAIL, strategy.therapeutic_area FAIL, strategy.indication UNKNOWN |   |
| RW-30 | Satralizumab | OUT | UNRESOLVED | out of scope but left for review (noise) | target.expression UNKNOWN, biology.mechanism_direction UNKNOWN, strategy.indication UNKNOWN |   |
| RW-31 | Tocilizumab (investigator-sponsored) | OUT | EXCLUDED | correct: excluded | target.expression FAIL, strategy.indication UNKNOWN |   |
| RW-32 | Remibrutinib | OUT | EXCLUDED | correct: excluded | target.expression UNKNOWN, modality.required FAIL, biology.mechanism_direction UNKNOWN, strategy.indication UNKNOWN |   |
| RW-33 | Tolebrutinib | OUT | EXCLUDED | correct: excluded | target.expression FAIL, modality.required FAIL |   |
| RW-34 | Descartes-08 | OUT | EXCLUDED | correct: excluded | target.expression FAIL, modality.required FAIL, biology.mechanism_direction UNKNOWN, strategy.indication UNKNOWN |   |
| RW-35 | KYV-101 | OUT | EXCLUDED | correct: excluded | target.expression FAIL, modality.required FAIL, biology.mechanism_direction UNKNOWN |   |
| RW-36 | CABA-201 | OUT | EXCLUDED | correct: excluded | target.expression UNKNOWN, modality.required UNKNOWN, biology.mechanism_direction UNKNOWN, strategy.indication UNKNOWN, evidence.phase_constraint FAIL |   |
| RW-37 | Anitocabtagene autoleucel | OUT | EXCLUDED | correct: excluded | target.expression FAIL, modality.required UNKNOWN, biology.mechanism_direction UNKNOWN, evidence.phase_constraint FAIL |   |
| RW-38 | SHR-2173 | UNKNOWN | UNRESOLVED | reference UNKNOWN | target.expression UNKNOWN, modality.required UNKNOWN, biology.mechanism_direction UNKNOWN, strategy.indication UNKNOWN |   |
| RW-39 | Cizutamig | UNKNOWN | EXCLUDED | reference UNKNOWN | target.expression UNKNOWN, biology.mechanism_direction UNKNOWN, strategy.indication UNKNOWN, evidence.phase_constraint FAIL |   |
| RW-40 | NMD670 | OUT | UNRESOLVED | out of scope but left for review (noise) | target.expression UNKNOWN, modality.required UNKNOWN, biology.mechanism_direction UNKNOWN |   |

### Why each in-scope program was missed

- **Efgartigimod IV and SC (RW-01/02):** two real U.S.-marketed FcRn blockers.
  - ChEMBL types efgartigimod as "Protein", and the label calls it an "IgG1 antibody fragment". Neither phrase is in the modality vocabulary, so modality is UNKNOWN.
  - The SC product's registry conditions also lack the plain "Myasthenia Gravis" wording.
- **Batoclimab and orilanolimab (RW-05/09):** the registry words the condition only as "Generalized Myasthenia Gravis". The NCIt indication authority has no entry under that name, so indication stays UNKNOWN. The same molecule is ELIGIBLE as HBM9161, whose registry entry says "Myasthenia Gravis".
- **IMVT-1402 (RW-08):** no target in any structured source. The agent proposed FcRn from the 10-Q; it awaits a human.

None of these is a wrong answer. Each is a correct UNKNOWN about wording or missing data, and closing each takes one sourced fact.

## Analyst readiness (Phase 3)

**Candidate list:** 7 programs, recorded as `CANDIDATE_NOT_APPROVED` by reviewer kind `AI_PREPARED`:
- rozanolixizumab, HBM9161, nipocalimab, IMVT-1402, efgartigimod IV, efgartigimod SC, batoclimab;
- RVT-1401 (an older code for batoclimab, Phase 2 only) and orilanolimab (withdrawn) were left off.

**No human approval exists.** The log refused the assistant's attempts to approve and to confirm evidence.

**Valuation readiness (3 programs):**

| Program | Inputs | Result |
|---|---|---|
| IMVT-1402 | HYPOTHETICAL, labelled | READY. rNPV bear −$143M / base $163M / bull $736M; P(approval) 58.5%; scenarios in order. Hypothetical U.S. license ($500M upfront, 15% royalty, $400M approval milestone): −$590M base |
| Batoclimab | deliberately partial | NOT READY, 5 inputs missing. Registered gMG trials are terminated and rights may return to HanAll (10-Q) |
| Nipocalimab | none | NOT READY, 11 missing. It is U.S.-marketed; a trial-path rNPV does not describe a commercial product |

### Manual actions actually required

These were counted from the workspace, not estimated (`results/manual_actions.json`):

| Action | Count | In DealScreen? |
|---|---:|---|
| Open UNKNOWN gates on the 14 unresolved programs | 39 | — |
| … closable by confirming an agent finding | 1 (IMVT-1402 target) | yes |
| … needing a sourced fact the analyst has to type in | 38 | **no**: the analyst must edit the landscape file and re-import, because there is no analyst fact-entry or gate override |
| Rights questions for listed candidates | 7 | queue only; no rights evidence was found |
| Identity decisions | 2 proposed merges + 1 unflagged pair (HBM9161) | proposals yes; the unflagged pair no |
| Landscape assembly (curation, 3 public APIs, 2 documents) | the whole landscape | **no**: done by a script outside DealScreen |

No time savings are claimed: nothing was timed against a human analyst.

## Five-minute demonstration (real assets)

1. **(0:00)** "Forty real myasthenia gravis programs from ClinicalTrials.gov, FDA labels and ChEMBL. Every cell traces to a URL, record and date (`field_provenance.csv`)."
2. **(0:45)** Buyer: FcRn-blocking antibodies, Phase 2+. Run `bve-dealscreen import` and `screen`.
3. **(1:30)** *Screening* sheet:
   - rozanolixizumab, nipocalimab and two batoclimab codes are eligible;
   - complement, CD19/CD20, BTK and CAR-T programs fail on the cited target;
   - no in-scope program is excluded.
4. **(2:15)** Show the honest misses:
   - Vyvgart (efgartigimod) sits in review because the data calls it a "Protein";
   - batoclimab sits in review while HBM9161 (the same drug) passes, because one registry entry says "Generalized".
   "It refuses to guess, and you can see exactly why."
5. **(3:00)** *Diligence* sheet:
   - the agent quotes Immunovant's 10-Q that IMVT-1402 is anti-FcRn;
   - it stays pending until a person confirms it;
   - every program's U.S. rights are UNKNOWN, because no source states them.
6. **(3:45)** *Finalists* sheet: seven candidates prepared by the assistant, stamped NOT APPROVED. Then *Valuation*: one hypothetical case, two NOT READY with checklists.
7. **(4:30)** Close: "Today it gives you a cited first pass and a precise list of what is unknown. The 38 gaps you'd close by hand are the next thing to build into the tool."

## What a BD Finance analyst could genuinely do with it today

- Turn a landscape they already have into a cited, reproducible first-pass screen. Here there were no wrong inclusions or exclusions, and every decision traces to a row and column.
- Get an explicit queue of what is unknown and why (gate by gate), instead of a silent filter.
- Keep scientific fit and rights visibly separate, so "eligible" is never read as "available".
- Hand a selected program to BVE's valuation engine with a readiness checklist, and see out-of-order scenarios explained or blocked.
- **Not yet:**
  - close most open questions inside the tool;
  - get rights or ownership answers;
  - get an accurate approval status where openFDA lacks the label;
  - value marketed products;
  - rely on any of it without human review.

## Smallest next improvement justified by this evidence

**An analyst fact-entry action.**
- An `ASSERT_FACT` decision lets a named human add one field value with a citation. It is stored as an analyst-confirmed claim, which the fact builder already prefers.
- 38 of the 39 open gates here need exactly that, and all 5 missed in-scope programs would close with one cited entry each.
- It uses the existing claim and decision-log machinery and changes no gate rule. The alternative, widening vocabularies so the misses pass automatically, would be changing the engine to make results look better.
