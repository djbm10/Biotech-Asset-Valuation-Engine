# Pilot chek1_clinical_any_v1: results

**Official grade: UNVALIDATED.** The answer key is AI-prepared, by a separate Claude process
(`independent_of_engine: false`). Claude also drew the target and operated the engine. The
scorer therefore issued no pass/fail verdict (`passes_thresholds: null`). The threshold
comparison below is reported for information only.

## What ran

| Step | Record |
|---|---|
| Target draw | Protocol pushed at `faf35aa` (15:50:07Z). drand round 6583757 → **CHEK1**, the first of 159 eligible targets by `sha256(seed:symbol)` |
| Preregistration | `80a0a00` (16:01:49Z, pushed). Engine `src/` identical to `ba9becf` |
| Deviation | an aborted, unread pre-registration acquisition (operator error; see PROTOCOL.md) |
| Engine run | `se:a93f9efc…`, 16:02:04–16:05:10Z, **3 min 6 s, peak 2.02 GB** (cap 4 GiB), exit 2, **INCOMPLETE** |
| Sources | CT.gov SUCCESS (30 queries); PubMed SUCCESS (30 queries, 5,362 found, 1 retry). NOT_CONFIGURED as preregistered: company pipeline, company press release, AACR, ASCO, ASH, EHA, SEC EDGAR |
| Documents | CT.gov 27, PubMed 402 |
| Seal | `a0dcb1b` (16:06:49Z, pushed; no candidate names in it) |
| Reference | attempt 1 (16:07:03–16:07:47Z) failed before writing anything: its web tools were blocked by non-interactive permission prompts. Attempt 2 (16:08:39–16:15:17Z) used the same isolation with web tools explicitly allowed |
| Reference content | 14 in-scope assets, 48 trial ids (all NCT), 8 negative controls; sha256 `e28e608c…` (kept outside the repo) |

## Scores (existing scorer, both sealed views)

| Metric | Official (all 701 candidates) | Review population (94 = 3 eligible + 91 review) |
|---|---:|---:|
| Recall (in-scope assets) | **12/14 = 85.7%** | **12/14 = 85.7%** |
| Strict precision | 12/701 = **1.7%** | 12/94 = **12.8%** |
| Adjudicated precision (TP ÷ candidates matching the reference) | 12/19 = 63.2% | 12/14 = 85.7% |
| Candidates matching nothing in the reference (unadjudicated) | 682 | 80 |
| Negative-control hits | 4 (adavosertib, ceralasertib, berzosertib, gemcitabine), **all EXCLUDED** by the engine | 0 |
| Identity merges / splits | 0 / 3 (R-001, R-003, R-005) | 0 / 2 (R-003, R-005) |
| Target accuracy, stated / incl. UNKNOWN | 1.00 / 0.67 (4 UNKNOWN) | same |
| Modality accuracy, stated / incl. UNKNOWN | 1.00 / 0.50 (6 UNKNOWN) | same |
| Trial coverage, overall (all ids = NCT only) | **15/48 = 31.3%** | 31.3% |
| Trial coverage, recovered assets only | 33.3% | 33.3% |
| Unreferenced trials attached | 0 | 0 |
| Misleading claims (scorer) | 0 (all 5,124 claims "unverifiable": the reference has no field-level values to compare) | 0 |

The analyst would have to review **94** candidates, 3 of them ELIGIBLE.

Against the preregistered thresholds (official view): precision ≥ 0.5 **fails** (0.017);
recall ≥ 0.6 **passes** (0.857); trial coverage ≥ 0.5 **fails** (0.313); identity errors
≤ 1 **fails** (3); misleading claims ≤ 2 passes (scorer 0; AI-reviewed 1, below). It
would be a FAIL on three of five, had a verdict been issued.

## Every reference asset

| Ref | Asset | Found as (route) | Target / modality stated | Trials found / ref | Missing |
|---|---|---|---|---:|---|
| R-001 | prexasertib (LY2606368, ACR-368) | Prexasertib (**ELIGIBLE**); ACR-368 (LOW_SUPPORT): split | CHEK1(+CHEK2) / authority small molecule; **displayed `CELL_THERAPY`** | 9/20 | 11 trials; ACR-368 not merged |
| R-002 | rabusertib (LY2603618) | rabusertib (REVIEW) | CHEK1 / small molecule | 0/7 | every trial: CT.gov records under the code were never fetched |
| R-003 | MK-8776 (SCH 900776) | SCH 900776 (**ELIGIBLE**) + MK-8776 (REVIEW): split | CHEK1 / small molecule | 1/4 | 3 trials; the two codes not merged |
| R-004 | AZD7762 | AZD7762 (REVIEW) | CHEK1 / small molecule | 0/3 | trials |
| R-005 | PF-00477736 | PF-00477736 + PF477736 (both REVIEW): split | CHEK1 on one / small molecule | 0/1 | trial; spelling variants not merged |
| R-006 | XL844 | XL-844 (REVIEW) | CHEK1 / UNKNOWN | 0/2 | trials, modality |
| R-007 | GDC-0425 | GDC-0425 (REVIEW) | CHEK1 / small molecule | 0/1 | trial |
| R-008 | GDC-0575 | GDC-0575 (REVIEW) | CHEK1 / UNKNOWN | 0/1 | trial, modality |
| R-009 | SRA737 | SRA737 (REVIEW) | UNKNOWN / small molecule | 1/2 | target, 1 trial |
| R-010 | LY2880070 | **not found** | – | 0/2 | its trial NCT05275426 *was* acquired, but the intervention was not nominated: no CHK1 edge in the authority, and the record never ties CHK1 to it |
| R-011 | BBI-355 | BBI-355 (**ELIGIBLE**) | construct target CHEK1 from the trial text; candidate target UNKNOWN / UNKNOWN | 1/1 | modality |
| R-012 | PEP07 | PEP07 (REVIEW) | UNKNOWN / UNKNOWN | 2/2 | target, modality |
| R-013 | SMP-3124LP | **not found** | – | 0/1 | not in the ontology, trial not acquired |
| R-014 | XS-02 | XS-02 (REVIEW) | UNKNOWN / small molecule | 1/1 | target |

Negative controls:
- adavosertib, ceralasertib, berzosertib and gemcitabine were candidates, and **all four
  were EXCLUDED**;
- PHI-101, CCT244747, CHIR-124 and CBP501 were not candidates.

## Eligibility (3 ELIGIBLE)

All three are in-scope CHK1 programmes in the reference. Every gate is supported by primary
evidence:
- identity from a CT.gov record;
- target from the ChEMBL/Open Targets edge, or, for BBI-355, the registry's "CHK1 Inhibitor
  BBI-355" text;
- stage from CT.gov phases.

Caveats:
- **SCH 900776 is ELIGIBLE while MK-8776, the same drug, is REVIEW.** The split shows one
  programme twice, with two dispositions.
- **Prexasertib is ELIGIBLE with `Modality: CELL_THERAPY` displayed.** The line is labelled
  "read from trial/protocol text … not asserted as a property of the molecule", while the
  authority line correctly says small molecule.
- The problem has no activity gate, and the ELIGIBLE note says that ELIGIBLE is not
  evidence of current development, ownership or licensing. No commercial facts were
  acquired.

## Three kinds of finding, kept apart

**1. Scorer disagreements (mechanical).**
- The scorer reads `authority_modality`, so it scores prexasertib's modality correct.
- It cannot see the variant names `prexasertib-drug` (LOW_SUPPORT) and `ACR-368` as the
  same asset unless a reference name matches exactly. ACR-368 did match.
- It marks all 5,124 claims unverifiable, because the reference carries no field values the
  scorer can compare.

**2. AI-reviewed discrepancies (operator judgement, not source-checked).**
- **UCN-01** is in REVIEW with CHEK1 asserted from the authority. The reference excluded it
  as a judgement call (originally a PKC inhibitor) and listed its 22 trials in its notes. If
  it counted, recall would be 13/15.
- **The 80 unmatched review candidates:**
  - 29 drugs for other targets, mostly DNA-damage-response and oncology agents (niraparib,
    iniparib, AZD2461, AZD-7648, IDE-161, ING-41, RP-6306, CX-5461, …);
  - 5 chemotherapies;
  - 18 natural products;
  - 14 antibiotics or other unrelated drugs;
  - 11 reagents or solvents (water, vehicle, acetonitrile, propidium, rhodamine, cesium, …);
  - 2 non-asset strings: `Exelixis` (a company) and `PARPi` (a class abbreviation).
- **One misleading displayed claim:** prexasertib `CELL_THERAPY`.

**3. Independently confirmed primary-source findings (checked by the operator in the sealed
artifacts).**
- All 30 CT.gov query attempts (10 queries × 3 passes) map to **one identical 27-record set** (`custody/query_record_map.jsonl`).
  Each code query (LY2603618, AZD7762, XL-844, GDC-0425, PF-00477736, UCN-01) found 0
  candidates in that universe.
- NCT05275426, LY2880070's trial, is in the 27, with `LY2880070` as a DRUG intervention, and
  produced no candidate.

## Comparison with gucy2c_oncology_v1 (caution)

| | GUCY2C (official) | CHEK1 (official) |
|---|---:|---:|
| Recall | 8/17 (47%) | 12/14 (86%) |
| Strict precision | 8/5,984 (0.13%) | 12/701 (1.7%) |
| Review population | 474 | 94 |
| Trial coverage, overall | 33% | 31% |
| Runtime | 58:52 | 3:06 |

The engine code differs: CHEK1 ran on everything fixed since then, including the
`ONCOLOGY` letter-split and the `STAR` expansion. The targets differ too. CHEK1 is a
small-molecule landscape fully curated in ChEMBL, while GUCY2C is mostly biologics and
cell therapies outside it. Reference quality, prompt and scope differ (oncology-only vs any
area). **None of the differences can be attributed to the fixes.** What repeats across both
runs: trial coverage near one-third, and PubMed-minted noise dominating the review
population.

## Top three generalizable failures (not fixed here)

1. **CT.gov acquisition is one target-term universe.**
   - Authority-seeded drug-code queries re-scan the records retrieved for the target's
     aliases instead of fetching their own. So trials registered under a code that never
     write the target's name are not acquired.
   - Cost here: 7 of 12 found assets had 0 trials, and coverage was 31%.
2. **PubMed name minting floods the review population.**
   - 80 of 94 review candidates are substances named in CHK1 abstracts but not CHK1
     programmes: other-target drugs, chemotherapy, natural products, antibiotics, reagents,
     a company and a class abbreviation.
   - The `DIRECT_APPROVED_NAME` route admits any ChEMBL name.
3. **Identity variants are not merged, and registry-only drugs without an authority edge
   are dropped.**
   - Not merged: PF-00477736/PF477736, SCH 900776/MK-8776 and prexasertib/ACR-368, plus a
     `prexasertib-drug` fragment.
   - Dropped: LY2880070's acquired trial produced no candidate.

**Next development priority: failure 1.** Fetch CT.gov records per seeded drug code, and
measure it live on a target that is not this one. It is the largest loss, it sits upstream
of everything else, and fixing it is acquisition work, not tuning against this reference.
No change was made during this experiment.

## Reference limitations (from the reference's own notes)

- UCN-01 and CBP501 are judgement calls.
- PEP07 may be the same as SOL578.
- XS-02's owner is unclear, and GDC-0575 aliases rest on vendor pages.
- Not searched directly: WHO ICTRP, ChiCTR, the CDE registry, jRCT and EU CTR/CTIS. Non-NCT
  and China-only programmes may be missing.
