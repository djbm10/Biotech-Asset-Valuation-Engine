# Pilot gucy2c_oncology_v1: results

**Grade: UNVALIDATED.** This was an AI-run exploratory benchmark. Claude (`claude-opus-5-5`) chose
the question, ran the engine and scored it. A separate Claude session wrote the answer key. No
human built or checked the answer key. Read the numbers as a measured development result, not
as validation.

**Question.** Find every anticancer therapeutic directed at GUCY2C (GCC) that has entered human
trials, as of 2026-10-24, in any modality. The preregistration was pushed before the run:
`e909f4d`, 2026-10-24 16:51 EDT. That timestamp comes from git and GitHub only. Nobody emailed
the hashes to a third party, so no independent timestamp exists.

## Headline numbers

The run status was **INCOMPLETE**. Only ClinicalTrials.gov and PubMed were acquired. The seven
company, conference and SEC source families had no connector configured, and the engine
reported this itself.

| Metric | Official view (all 5,984 candidates) | Review-population view (474) |
|---|---:|---:|
| Recall (named asset recovered) | **8/17 = 47%** | 6/17 = 35% |
| Strict precision | 8/5,984 = 0.13% | 6/474 = 1.3% |
| Adjudicated precision (TP ÷ TP + control hits) | 73% | 67% |
| Negative-control hits | **3/9** (all 3 GI agonist peptides) | 3/9 |
| Merges / splits (scorer) | 0 / 0 | 0 / 0 |
| Target accuracy, as scored | 0% *(exporter bug, see below)* | 0% |
| Target accuracy, prefix-normalized (my recomputation) | 1/1 stated correct; 1/8 counting unknowns | – |
| Modality accuracy, as scored | 33% (1/3 stated); 12.5% counting unknowns | 50% |
| Trial coverage, overall (scorer) | 33% | 27% |
| Trial coverage, recovered assets (scorer) | 48% | 45% |
| Citation coverage | 100% of 42,474 claims cite a document | 100% |
| Claims checkable against the reference | 0 (field names don't overlap) | 0 |

Runtime: 58 min 52 s wall clock. Peak RSS was 3.33 GB under a 4 GiB cap. No paid APIs or
cloud resources were used.

**Exporter defect, found before the answer key existed.** The engine writes targets as
`TARGET:GUCY2C`, and the scorer compares them with bare HGNC symbols. Every correct target
therefore scored as wrong. The sealed export was not changed. I fixed the exporter for future
runs (`blinded_pilot.py`, with a test). The row above labelled "prefix-normalized" is my own
recomputation and is not scorer output.

## Asset-by-asset

Legend for the BVE column:
- **found**: the drug was recovered under a name that matches the reference.
- **label only**: the engine retrieved the drug's trial but attached it to a generic label.
- **missed**: the drug was not surfaced at all.

Engine routing shows where the drug landed in the engine's own output:
- **REVIEW**: shown to an analyst.
- **LOW**: hidden as low-support.
- **EXCL**: excluded by the engine.

| Ref | Asset (reference names) | Modality | BVE | Engine routing / name | Trials found / ref NCT | Notes, evidence |
|---|---|---|---|---|---|---|
| R-001 | indusatumab vedotin / MLN0264 / TAK-264 | ADC | found | REVIEW #3 "TAK-264" | 4/4 | Target and modality correct. INN not linked as an alias. [NCT01577758](https://clinicaltrials.gov/study/NCT01577758) |
| R-002 | TAK-164 | ADC | found | REVIEW | 1/1 | Target and modality unknown. [NCT03449030](https://clinicaltrials.gov/study/NCT03449030) |
| R-003 | PF-07062119 (Pfizer CD3×GUCY2C) | T-cell engager | **missed** | none | 0/1 | **Confirmed engine defect.** The trial was acquired and lists `Drug: PF-07062119` in a structured field, but the document yielded no mention, claim or candidate. [NCT04171141](https://clinicaltrials.gov/study/NCT04171141) |
| R-004 | Ad5-GUCY2C-PADRE | vaccine | label only | LOW "vaccine" | 0/1 | Generic label. [NCT01972737](https://clinicaltrials.gov/study/NCT01972737) |
| R-005 | Ad5.F35-hGCC-PADRE | vaccine | found | LOW | 1/2 | Hidden from the analyst. The second trial was attached to "CT Scan" and "vaccine". [NCT07417488](https://clinicaltrials.gov/study/NCT07417488) |
| R-006 | Lm-GUCY2C | vaccine | label only | LOW "CT Scan"/"vaccine" | 0/1 | Same trial as R-005. |
| R-007 | LYL273 / GCC19CART | CAR-T | found | REVIEW "LYL273" | 1/3 | The two investigator trials sit on a separate LOW candidate, "gucy2c cart cells". The reference's link of those trials to GCC19CART is itself unresolved. [NCT05319314](https://clinicaltrials.gov/study/NCT05319314), [NCT04652219](https://clinicaltrials.gov/study/NCT04652219) |
| R-008 | IM96 | CAR-T | found | REVIEW | 1/3 | Two newer IM96 trials were never acquired. Both are confirmed on CT.gov. [NCT06718738](https://clinicaltrials.gov/study/NCT06718738), [NCT07406984](https://clinicaltrials.gov/study/NCT07406984) |
| R-009 | LCAR-G08 | CAR-T | found | **LOW** | 1/1 | Hidden from the analyst by low-support routing. [NCT06197178](https://clinicaltrials.gov/study/NCT06197178) |
| R-010 | XKDCT080 | CAR-T | label only | REVIEW #7 "Chimeric antigen receptor T cell preparation targeting GCC" | (trial held) | Useful to a reader, but not a drug name. [NCT05875402](https://clinicaltrials.gov/study/NCT05875402) |
| R-011 | WD-01 | CAR-T | found | REVIEW | 1/1 | [NCT06675513](https://clinicaltrials.gov/study/NCT06675513) |
| R-012 | REVO-UWD-01 | CAR-T | **missed** | none | 0/1 | Trial not acquired. GCC targeting is confirmed in the record text. [NCT06653010](https://clinicaltrials.gov/study/NCT06653010) |
| R-013 | CDH17/GUCY2C CAR-T (Guangzhou Bio-gene) | CAR-T | label only | LOW "CAR-T" | 0/1 | [NCT07152210](https://clinicaltrials.gov/study/NCT07152210) |
| R-014 | anti-GUCY2C CAR-T (Parasol) | CAR-T | missed | none | 0/0 NCT | Registered only in ChiCTR, which BVE has no connector for. The reference's link rests on trade press. |
| R-015 | EB-DUO-CAR-NK-CEA/GCC | CAR-NK | found | REVIEW #4 and #5 | 2/2 | **Split** into two candidates, one with an "(IV)" suffix; the scorer did not detect it. **False target KALRN**: "DUO" is a KALRN alias. [NCT07589517](https://clinicaltrials.gov/study/NCT07589517) |
| R-016 | Mesothelin/GPC3/GUCY2C CAR-T (Guangzhou Med. Univ.) | CAR-T | label only | EXCL / LOW "CAR-T cells" | 0/2 | Multi-antigen, borderline in scope. [NCT05779917](https://clinicaltrials.gov/study/NCT05779917) |
| R-017 | CAR-DC (PKU Shenzhen) | CAR-DC | missed | none | 0/1 | Not acquired. GCC is one of five antigens, borderline in scope. [NCT07504445](https://clinicaltrials.gov/study/NCT07504445) |
| C-001 | linaclotide | GI agonist (control) | **control hit** | REVIEW #6, CONFIRMED_TARGET GUCY2C | – | Excluded by the spec. |
| C-002 | plecanatide | GI agonist (control) | **control hit** | **REVIEW #1**, modality "CELL_THERAPY", `human_poc_present=True`, indication Barrett esophagus | – | Picked up from a UW-Madison chemoprevention biopsy study. [NCT05107219](https://clinicaltrials.gov/study/NCT05107219) |
| C-003 | dolcanatide | GI agonist (control) | **control hit** | REVIEW #2 | – | |
| C-004 to C-009 | imaging agents, preclinical ADCs, CEACAM5 ADC | controls | not hit | – | – | |

Of the 9 scorer misses:
- 5 had their trial retrieved and attached to a generic label (label only).
- 4 were never surfaced: PF-07062119, REVO-UWD-01, the ChiCTR-only program and CAR-DC.

Two of those 9 (R-016, R-017) are borderline multi-antigen programs.

I did not find any GUCY2C asset that BVE surfaced and the reference missed. I checked all 71
acquired CT.gov records that mention GUCY2C/GCC. The rest of the 5,984-candidate pool was not
reviewed exhaustively.

**Scorer-detected vs confirmed.** The following were checked against ClinicalTrials.gov and are
confirmed:
- the PF-07062119 drop;
- REVO-UWD-01, CAR-DC and the two IM96 trials exist as the reference describes;
- the three agonist peptides are out of scope;
- the EB-DUO split and the KALRN target.

The following rest on the AI reference alone and were not independently verified:
- whether the GCC19CART ↔ NCT04652219/NCT04780529 and Parasol ↔ ChiCTR links are correct;
- the reference's ownership facts.

The reference itself may be incomplete. It could not query ChiCTR, ICTRP or CTIS.

## Answers

1. **Real assets discovered:** 8 of 17 under a usable drug name. Only 6 of those were in the
   review population shown to an analyst. 5 more were present only as a retrieved trial under a
   generic label.
2. **Reference assets missed:** 9 by the scorer. Of these, 4 were never surfaced at all, and 2
   of the 9 are borderline in scope.
3. **Incorrect or unsupported candidates:** 3 of 9 negative controls were returned. They are
   the excluded GI agonist peptides, ranked #1, #2 and #6. Beyond the matches, there were
   5,973 unmatched candidates overall and 465 in the review population, most of them junk:
   imaging procedures, "anise", "Rusfertide", eye-scan "GCC" (ganglion cell complex) and cancer
   center study codes such as "GCC 1635". The 3 junk entries in the top 10 alone took 30% of the
   analyst-visible shortlist.
4. **Scientific classification:**
   - Targets were mostly UNKNOWN. A target was stated for 1 of 8 recovered assets, and it was
     correct.
   - One confirmed-false target was asserted: KALRN for EB-DUO.
   - The only CONFIRMED_TARGET assertions on GUCY2C went to the three out-of-scope agonists.
   - Modality, where stated, was right but coarse: CAR-T is reported as CELL_THERAPY.
5. **Clinical-trial retrieval:**
   - Strong at the acquisition layer: 21/25 reference NCT trials were acquired (84%), and 20
     were attached to some candidate.
   - Weak at the asset layer: only 11 were attached to the correctly named asset.
   - The scorer's overall trial coverage is 33%. It also counts EudraCT/Japic IDs and ChiCTR,
     which BVE never emits.
6. **Errors that could mislead a BD analyst:**
   - (a) GUCY2C *agonists* for constipation lead the list, with a confirmed target and a
     "human PoC" flag.
   - (b) Pfizer's CD3×GUCY2C engager is invisible even though its trial was downloaded.
   - (c) Real assets are hidden as low-support (LCAR-G08, the Ad5.F35 vaccine).
   - (d) A false KALRN target.
   - (e) No owner, licensee or rights facts at all. The Lyell/ICT licence of LYL273 is absent.
     The run produced no commercial claims.
7. **Manual or AI follow-up needed:**
   - Every result needed follow-up.
   - An analyst must sift 474 review items to find 6 assets, about 1 in 80.
   - They must trace generic-labelled trials back to drug names.
   - All ownership and deal facts must be researched separately.
   - By comparison, the AI reference session built a fuller list (17 assets, 32 trial IDs, with
     sources) in 11 minutes.
8. **Three engineering changes justified by measured failures:**
   1. **Find and fix the silent document drop.** 32/630 CT.gov records (5%) and 170/4,766
      PubMed records produced no mention or claim. One of them was the PF-07062119 trial.
      Every acquired trial should yield at least its structured interventions, or a recorded
      reason why not.
   2. **Disambiguate target aliases and target direction.**
      - "GCC" matched cancer-center study codes and the retinal ganglion cell complex.
      - "DUO" resolved to KALRN.
      - The spec's exclusion of agonists and of bowel-disorder use had no way to reach the
        gates.
      Short ambiguous aliases need context, and indication or mechanism intent must be
      expressible so it can exclude the agonists.
   3. **Name assets from the trial, not the intervention label.** Generic interventions
      ("vaccine", "CAR-T", "CAR-T cells", "CT Scan") absorbed 5 in-scope programs. Two smaller
      fixes belong with this: collapse route-suffixed duplicates such as "(IV)", and
      re-examine low-support routing, which hid 2 of 8 true hits.
9. **What worked well:**
   - Target-driven CT.gov retrieval was close to complete.
   - Exact development codes resolved cleanly: TAK-264 with all 4 trials, TAK-164, IM96,
     WD-01, LYL273.
   - No asset was merged with a different drug.
   - Every claim carries a document citation.
   - The run fit in 3.3 GB and under an hour.
   - The engine reported its own INCOMPLETE status and blind spots honestly.
10. **Narrow usefulness:**
    - Useful as a **first-pass trial sweep** for a target: "give me every CT.gov record that
      touches GUCY2C, with a provisional drug label", for an analyst who does the naming and
      scoping.
    - Not yet useful as an autonomous landscape list or a BD shortlist. Its top-ranked items
      were out of scope and it carries no commercial facts.

## Limits of this experiment

- **The reference is AI-prepared**, with `independent_of_engine: false`. Recall is measured
  against a list that is probably incomplete for China-only programs.
- **The engine run was INCOMPLETE.** Company, conference and SEC sources were not configured,
  so this measures the CT.gov + PubMed engine.
- **The same model (Claude) operated the engine, saw its output before the reference existed,
  and adjudicated discrepancies.** The reference session was separate and isolated (see
  `REPRODUCIBILITY.md`), but the adjudication was not blind.
- **One run, one target.** No engine change or rerun was made after scoring. The only code
  change, the exporter fix, does not touch the engine and was made before the reference existed.
