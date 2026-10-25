# Asset-specific evidence attribution (v3): development report

**Grade: DEVELOPMENT.** This is a replay of the frozen pilot `gucy2c_oncology_v1`'s sealed
corpus, scored against its already-disclosed AI reference. **Not validation.** The frozen
pilot is unchanged. Policy, frozen criteria, amendment and results:
`docs/se_policies/evidence_attribution_v1.md` (declared at `2dc0833`, before any code).

## What changed

Free-text documents (PubMed, public documents) no longer turn their context into facts
about every name in them.

| Evidence | Before | After |
|---|---|---|
| Area discussed by the document | gate-decisive `therapeutic_area` for every name | contextual `document_therapeutic_area`, cited; no gate reads it |
| Area tied to *this* asset ("X in patients with Y", "X for the treatment of Y", no coordination with another product) | – | gate-decisive `therapeutic_area`, citing that sentence |
| Modality discussed by the document | the candidate's modality for every name | `context_modality_terms` / `document_modality_context` |
| Modality by apposition or head noun ("X, an antibody-drug conjugate"; "the ADC X") | – | the candidate's modality |
| CT.gov intervention → condition, authority modality and targets, construct targets, human PoC | – | unchanged (already structured or attributed) |

Display:
- `Disposition: ELIGIBLE` now carries "meets the declared search criteria; not evidence of
  current development, ownership or licensing availability". The shortlist JSON carries it
  too, as `disposition_note`.
- The status line is now `Trial registry status`, noted as per-record and as not
  excluding historical programmes.
- `Phase:` shows the highest of the cited records.

## Replays (identical sealed bytes, pre-C10 code; see the v2 report for why)

| Run | Code | Wall | RSS |
|---|---|---:|---:|
| `gi_v1_preC10` (v2 end state) | `94fefff` + G1/G2 | 2:00 | 2.42 GB |
| `attr_v1_preC10` (first try; kept as a record) | + attribution | 2:05 | 2.48 GB |
| `attr_v2_preC10` (acceptance) | + Amendment 1 | 2:02 | 2.51 GB |

## Results

| Measure | gi_v1_preC10 | attr_v2_preC10 |
|---|---:|---:|
| Candidates | 279 | 279 |
| Analyst-visible (eligible + review) | 21 (1 + 20) | 32 (1 + 31) |
| Named in-scope recall, visible / all | 12/17 / 12/17 | 12/17 / 12/17 |
| Visible strict precision | 57.1% | 37.5% |
| Negative-control hits visible | 0 | 0 |
| EXCLUDED | 37 | 26 |
| Visible with an **asset-specific** area fact | 19 | 13 (the 12 recovered assets plus R-005's second spelling; 0 of the 19 non-reference) |
| Visible non-reference candidates passing the area gate on document context | 6 | **0** |
| Candidates whose modality was document context and is now none | – | 174 (13 visible) |
| Modality corrected rather than removed | – | linaclotide CELL_THERAPY → PEPTIDE |
| Target changes | – | 0 |
| Engine merges / scorer splits | 2 / 1 | 2 / 1 |
| Trial coverage, all ids / NCT | 52% / 65% | 52% / 65% |
| ELIGIBLE | 1 (TAK-264) | 1 (TAK-264) |

**Unsupported classifications removed.**
- **Area:** water, ether, aniline, amino acids, hematoporphyrin and polyethylene glycol
  passed the area gate only on their paper's ONCOLOGY context. They are now UNKNOWN, with
  the context kept and cited.
- **Modality:** the document-level modalities on the visible non-reference names are gone
  (dextran `T_CELL_ENGAGER`, aniline `ADC`, ether `RNA_THERAPEUTIC`, lactulose
  `CELL_THERAPY`, …).

**Lost.** The 11 v2 exclusions came from document-level GI evidence: 7 laxatives,
rifaximin, creatinine, fluorescein, isothiocyanate and vehicle. None has a sentence that
ties the GI indication to that drug alone; every one is listed or coordinated
("polyethylene glycol or sennosides"). So they are UNKNOWN again and back in REVIEW. This
was the declared price of R3 (no exclusion without asset-specific evidence). It is the
main reason strict visible precision falls back to 37.5%.

**Gained, as negative evidence.** Linaclotide, plecanatide, dolcanatide and prucalopride
now carry *attributed* GI area facts ("Plecanatide for the treatment of chronic idiopathic
constipation…") and FAIL the oncology area gate. They were already EXCLUDED, so no route
changed. This breaks frozen criterion E5 as written; see the policy.

**Preserved.**
- All 12 recovered reference assets are visible, and their CT.gov area facts are unchanged.
- Every vaccine (Ad5-hGCC-PADRE, Ad5.F35, Lm-GUCY2C) and cell therapy (LYL273, LCAR-G08,
  XKDCT080, WD-01, IM96, EB-DUO) keeps its area and modality.
- TAK-164 keeps ADC. The first replay lost it to a too-short apposition window, which
  Amendment 1 fixed.

## TAK-264, gate by gate (attr_v2_preC10)

| Gate | Status | Evidence |
|---|---|---|
| identity | PASS | CT.gov NCT02391038 (structured) |
| construct target | PASS | ChEMBL_37 + Open Targets: GUCY2C |
| agonist exclusion | PASS | authority action BINDING AGENT |
| therapeutic area | PASS | PMID 30631747 title: "Evaluation of TAK-264, an Antibody-Drug Conjugate in Pancreatic Cancer Cell Lines…" (R1-attributed, preclinical) |
| minimum stage | PASS | CT.gov PHASE1 (NCT02391038), PHASE2 (NCT02202785) |

What ELIGIBLE means here: **historical scientific eligibility under the declared criteria.**

- **Current development.** Not established. Every cited trial is COMPLETED or TERMINATED,
  and the display says so. The problem declares no activity gate.
- **Ownership, licensing and deal availability.** Not established. The run holds no
  ownership or licensing facts; the company line shows the trial sponsor only. The
  disposition note now says this explicitly.
- **Area evidence.** It is a preclinical oncology study. The CT.gov conditions
  ("…Carcinoma", "…Malignancies") would have carried it, had the frozen ONCOLOGY lexicon
  matched those words.

The v2 post-hoc B4/B7 failures and their amendment remain in
`gi_area_evidence_v1.md`, unchanged. A correction was added there: TAK-264's highest
stage was always PHASE_2, so v2's "not the highest (PHASE_3)" was wrong.

## Generalization tests (synthetic, several areas)

`tests/se/test_evidence_attribution.py`, 25 cases written from the preregistered table:
- a reagent in an oncology paper;
- a multi-drug paper where one drug is evaluated for cancer;
- coordinated and combination partners stay UNKNOWN;
- a drug with autoimmune + oncology evidence gets both;
- ambiguous wording stays UNKNOWN (term before the name, no cue, no area);
- whole-word names;
- apposition and head-noun modality, and the document modality not given to a reagent;
- context alone is UNKNOWN at the gate, never FAIL;
- CT.gov trials for a vaccine, a CAR-T and a GI drug keep their structured areas;
- a historical programme stays ELIGIBLE with the scope note;
- the highest phase is shown;
- Amendment 1's two regressions.

## Remaining gaps

- **Recall of attribution.** R1 is deliberately narrow. Guidelines and reviews list drugs
  together, so most real GI uses go unattributed and stay in REVIEW.
- **Reagents.** Without a nontherapeutic authority (ChEMBL `max_phase`/indication data is
  not in the offline snapshot), the 8 reagent-like names stay visible as UNKNOWN.
- **Lexicon.** The ONCOLOGY lexicon still misses `carcinoma`/`malignancies`, and it is
  frozen.
- **Acquisition.** The 3 unacquired reference assets remain, one of them ChiCTR-only. No
  company, conference or SEC connectors are configured. PubMed fetches the newest 50 per
  query.
- **Commercial intelligence.** There are no ownership, licensing, partnering or deal-status
  facts at all.
- **Replay.** The current HEAD cannot replay this corpus (C10 changed the custody key).
