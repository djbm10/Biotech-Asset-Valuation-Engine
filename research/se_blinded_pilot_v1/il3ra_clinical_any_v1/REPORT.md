# Pilot il3ra_clinical_any_v1: results

**Official grade: UNVALIDATED.** The answer key is AI-prepared, by a separate Claude process
(`independent_of_engine: false`). Claude also drew the target and operated the engine. The
scorer issued no pass/fail verdict (`passes_thresholds: null`). The threshold comparison
below is reported as computed, with no relabelling.

**Engine status:**
- **FAILED / UNSCOREABLE**, by the engine's own verdict (exit 3): one mandatory CT.gov query
  failed.
- Seven source families were NOT_CONFIGURED.
- Reported here as **INCOMPLETE**. It was scored anyway, because candidates existed and the
  protocol forbids a retry.

## What ran

| Step | Record |
|---|---|
| Target draw | Protocol and pool pushed at `3c7f48d` (153 eligible; CHEK1, GUCY2C and every target named in a report or S&E test excluded). drand round 6584099 → **IL3RA (CD123)** |
| Preregistration | `dacbca2`, pushed 18:50:32Z. `src/` identical to `fcfefe3`. Problem compiled without any search (`problem_from_args` only; `outputs/se/` empty, run dir absent) |
| Engine run | `se:56d01728…`, 18:50:53–18:54:14Z, **3 min 21 s, peak 2.02 GB** (cap 4 GiB), exit 3 |
| Sources | CT.gov 45/46 queries SUCCESS, **1 FAILED** (HTTP 400 ×3); PubMed 46 queries (35 SUCCESS, 11 no evidence). NOT_CONFIGURED: company pipeline, press release, AACR, ASCO, ASH, EHA, SEC EDGAR |
| Documents | CT.gov 293, PubMed 305 |
| Seal | `6950960`, pushed 18:56:35Z, before the reference started. It contains no candidate names |
| Reference | `claude -p --restricted`, 18:56:46–19:11:56Z. **50 in-scope assets, 10 negative controls, 110 trial ids** (108 NCT, 2 ChiCTR) |
| Deviation | The reference omitted the two required provenance flags. The scoring copy adds exactly `independent_of_engine: false, synthetic: false`, with the assets byte-identical (checked). See REPRODUCIBILITY.md |

## Scores (existing scorer, both sealed views)

| Metric | Official (all 442) | Review population (74 = 25 eligible + 49 review) |
|---|---:|---:|
| Recall | **23/50 = 46%** | **21/50 = 42%** |
| Strict precision | 23/442 = **5.2%** | 21/74 = **28.4%** |
| Adjudicated precision (TP ÷ candidates matching the reference) | 82% | 100% |
| Negative-control hits | 4: gemtuzumab ozogamicin (CD33), tamibarotene, magrolimab (CD47), benralizumab (IL-5Rα). **All EXCLUDED** by the engine | 0 |
| Identity merges / splits (scorer) | 0 / 1 (pivekimab sunirine vs DECNUPAZ) | 0 / 0 |
| Target accuracy, stated / incl. UNKNOWN | 1.00 / 0.22 (18 UNKNOWN) | 1.00 / 0.24 |
| Modality accuracy, stated / incl. UNKNOWN | 0.13 / 0.04 | 0.13 / 0.05 |
| Trial coverage, overall | **66/110 = 60%** | 58% |
| Trial coverage, recovered assets | 90% | 96% |
| Unreferenced trials attached | 11 | 8 |
| Misleading claims (scorer) | 0 (3,487 claims, all "unverifiable") | 0 |

**Preregistered thresholds, official view:**

| Criterion | Threshold | Result | |
|---|---|---|---|
| Strict precision | ≥ 0.50 | 0.052 | **FAIL** |
| Recall | ≥ 0.60 | 0.46 | **FAIL** |
| Trial coverage | ≥ 0.50 | 0.60 | pass |
| Identity errors | ≤ 1 | 1 (scorer) | pass |
| Misleading claims | ≤ 2 | 0 (scorer) | pass |

This would be a FAIL on two of five, had a verdict been issued. Operator review (below)
finds more identity errors and misleading claims than the scorer counts, which would fail
two more criteria. That is reported separately and does not change the official numbers.

## Three kinds of finding, kept apart

### 1. Scorer disagreements (mechanical, not engine errors)

- **Names.** The scorer matches by exact name. 15 reference assets were missed by the scorer
  but sit in the analyst-visible list under a descriptive registry name carrying the
  reference trial. Examples: "Third-generation anti-CD123 CAR-T cells", "anti Tim-3/CD123
  CAR-T cell therapy", "CD33/CD123/CLL-1 CAR-T Cells", "CARCIK CD123/33 infusion", and the
  4SCAR family (4 rows).
- **Trial-linked view** (`adjudicate.py`, labelled operator analysis):
  - **37/50 (74%)** in-scope assets are in the analyst-visible list;
  - **46/50 (92%)** are somewhere in the output, 9 of them only in LOW_SUPPORT.
- **Modality.** The scorer compares the engine's code (`ANTIBODY_DRUG_CONJUGATE`) with the
  reference's free text ("antibody-drug conjugate") as strings. After mapping both to coarse
  classes, modality is correct for **31/40** assets with a stated modality.

### 2. Operator-reviewed discrepancies (checked in the sealed artifacts)

- **Identity merges the scorer cannot see:**
  - **MB-102.** Mustang Bio's CD123 CAR-T is merged with MediBeacon's MB-102
    (relmapirazin, a kidney-function agent). The merged asset is shown **ELIGIBLE**, with
    authority modality `SMALL_MOLECULE`, the company list "Mustang Bio, MediBeacon, …", and
    8 trials of which about 6 are not CD123 studies.
  - **Generic labels.** "CD123 CAR-T cells" covers two sponsors' programmes (R-030 and
    R-036). "CART123" covers Penn's product and a donor-derived programme (R-022 and R-034).
    "TM123" spans UniCAR and RevCAR (R-024 and R-025), which the reference itself calls a
    granularity judgement.
- **Splits:**
  - MP0533: three rows, two REVIEW and one LOW_SUPPORT;
  - pivekimab sunirine: ELIGIBLE, plus a "pivekimab" REVIEW fragment and a DECNUPAZ
    LOW_SUPPORT fragment.
- **Displayed claims that are wrong:**
  - **Tagraxofusp** has discovery modality **`CELL_THERAPY`**; it is a fusion protein. Same
    defect class as prexasertib in CHEK1.
  - **AZD9829** is `CELL_THERAPY`; it is an ADC.
  - **MB-102** is `SMALL_MOLECULE`; it is a cell therapy.
  - **Flotetuzumab, vibecotamab, JNJ-63709178 and AFM28** are labelled plain
    antibodies. They are engagers.
- **Eligibility decisions:**
  - All 25 ELIGIBLE rows are CD123 programmes in the reference. That is correct as an
    outcome.
  - But **20 of the 25 have no target asserted** (`UNRESOLVED`): ELIGIBLE rests on the
    registry text naming CD123, not on a target fact.
  - MB-102 is ELIGIBLE as a merged identity, which is wrong as an entity.
- **Review population noise.** 30 of 74 visible rows are not CD123 programmes:
  - hepatitis-B/HIV antivirals: adefovir ×2, entecavir, telbivudine, clevudine,
    emtricitabine, tenofovir;
  - HCV protease inhibitors: telaprevir, ITMN-191, TMC-435350;
  - antibiotics and anti-infective antibodies: biapenem, bezlotoxumab, suptavumab;
  - CD33 agents: AMG 330, AMV564, IMGN779;
  - other drugs: TAK164 (a GCC ADC), linaclotide, KO-539, motesanib, darinaparsin,
    glufosfamide, sivelestat, cladribine, AEG-35156, ibritumomab;
  - reagents and elements: hematoxylin, iodine, yttrium;
  - the fragment "UCART".

### 3. Engine failures confirmed in primary artifacts

- **The CT.gov failure is self-inflicted.**
  - The pass-2 follow-up query sent a whole arm label as an intervention search:
    `MP0533 (multispecific DARPin CD3 Engager Targeting CD33, CD123 and CD70) monotherapy,
    Part 2-Arm A`. CT.gov returned HTTP 400 on all 3 attempts.
  - The string is the trial's registered intervention text, sent unescaped and unshortened
    by the asset-seeded follow-up query. That query path was changed at `e72ad34`, and
    composite labels were changed at `fcfefe3`. Which change exposed it was **not
    isolated**.
  - It made the whole run UNSCOREABLE by the engine's own rules.
  - It cost MP0533's own trial: it is not attributed to the drug.
- **SAR443579.** Its trial NCT06508489 *was* acquired, and lists `SAR443579` as an
  intervention, but it produced no candidate. This is the LY2880070 pattern from CHEK1,
  unfixed: a registry-only code without an authority edge is dropped.
- **Never acquired:** KHK2823 (NCT02181699), SAR440234 (NCT03594955) and a ChiCTR-only
  CAR-T. ChiCTR is not a source.

## Analyst usefulness

| Question | Answer |
|---|---|
| Relevant programmes found | **37 of 50** in the 74-row list (74%); 9 more are hidden in LOW_SUPPORT; 4 are absent |
| Irrelevant items to inspect | **30 of 74** rows, plus 7 duplicate rows for the same programmes |
| Complete clinical histories | Official trial coverage 60%. Every reference trial was attached for 43 of 46 found programmes, but most CAR-Ts have one trial. The large programmes are near complete (tagraxofusp 21/22, flotetuzumab 8/8, talacotuzumab 5/5) |
| Scientific facts missing | Target asserted for only **5 of 46** found programmes. Modality is wrong for 9 of 40. No efficacy readout. Programme status (active vs discontinued) is never stated, only per-trial registry status |
| Commercial facts missing | **All of them.** 0 owner, rights, deal or licensing claims among 3,487. Pivekimab's approval status, sponsor changes and partnerships are absent. Company lists are trial sponsors, including academic sites |
| Manual work for a decision-useful report | About 2–4 analyst hours. Discard 30 rows, merge 7, split MB-102, and confirm the target on 32 rows. Correct 9 modalities, research owner/status/deal facts for all 37 from scratch, and search for the 13 missed (4 absent, 9 in LOW_SUPPORT). The engine saves the CT.gov sweep; it does not produce the report |

## Comparison across the three pilots (caution: different targets and engine commits)

| | GUCY2C | CHEK1 | IL3RA |
|---|---:|---:|---:|
| Engine status | INCOMPLETE | INCOMPLETE | **FAILED** (CT.gov 400) |
| Recall (scorer) | 47% | 86% | 46% |
| Strict precision | 0.13% | 1.7% | 5.2% |
| Analyst-visible rows | 474 | 94 | 74 |
| Trial coverage, overall | 33% | 31% | 60% |
| Commercial facts | 0 | 0 | 0 |
| Misleading modality on top asset | — | prexasertib CELL_THERAPY | tagraxofusp CELL_THERAPY |

The trial-coverage gain is consistent with the CT.gov seeded-retrieval fix, but one run on
a different target cannot attribute it. Recall and precision are still far below the
preregistered bar on two of three pilots. Each pilot exposed new defect classes, and this
one's run-killing defect sits in the recently changed follow-up query path.

## Limitations of the reference and of the target draw

- **The reference is one AI session.** It ran for 15 minutes, with no human check.
  - It reports that ChiCTR rendered via JavaScript and could not be read.
  - ICTRP, jRCT, CTRI and systematic EU CTIS were not searched.
  - Programme granularity (UniCAR/RevCAR, MB-102, UCART123, 4SCAR) could move the in-scope
    count between about 45 and 60.
  - It states that pivekimab sunirine was FDA-approved on 2026-05-27 ("Decnupaz"). The
    operator did not verify this.
  - It omitted the required provenance flags.
  - Being the same model as the operator, it may share the operator's blind spots.
- **Ontology bias.** The target was drawn from BVE's own ontology, among targets with at
  least 5 curated drugs, so it favours well-curated targets. IL3RA's landscape is mostly
  cell therapies and biologics with no authority record. That is exactly where target
  attribution fails (5/46 asserted).
- **Isolation** is process-level only: same machine, account and model, open web, and global
  CLAUDE.md possibly loaded.

## Recommendation

**Shift effort to the BD Finance and Excel-workflow opportunity. Stop developing S&E as a
product; keep it as a trial-sweep helper.**

- After three preregistered, mechanically drawn or out-of-sample pilots, the S&E engine:
  - has never completed a clean acquisition;
  - met the recall bar once in three;
  - never met the precision bar (best 5.2%);
  - has produced **zero commercial facts** in any run.
  Commercial facts are what a BD user needs most.
- Each milestone fixed the previous pilot's top failure and the next pilot found new ones.
  Here, a defect in the recently changed follow-up query path killed the run. The defect surface (identity,
  target attribution, modality, naming, junk minting, source coverage) is wide, and it is
  measured only by AI-prepared keys. There is no human-validated benchmark to converge
  against.
- What does work, and is worth keeping as is: a 3-minute, free CT.gov/PubMed sweep finds
  roughly three-quarters of a target's clinical programmes, with near-complete trial lists
  for the big ones. That is a useful first pass for an analyst, who still does the
  naming, scoping and commercial work.
- If S&E work resumes later, the gating step is not another engine fix. It is a
  **human-prepared reference** for at least one landscape, so that progress can be
  validated at all. Until then, BD finance work (valuation, deal modelling, Excel
  integration) is closer to user value per hour invested.
