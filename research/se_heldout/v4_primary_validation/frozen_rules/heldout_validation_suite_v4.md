# HELDOUT_VALIDATION_SUITE v4 (H16–H20) — untouched suite for shortlist precision (preregistration)

**Status:** PREREGISTERED 2026-10-11, before SHORTLIST_NONPRODUCT_OFFTARGET_DIAGNOSIS v1 starts.
**Not run.** No query was run through the engine, looked up in the target resolver, or checked
against any candidate output. The targets were chosen from public product knowledge only.
**When to run:** only after a shortlist-precision fix is adopted or reverted. All five runs use one
declared engine commit, with no code change between them. This is the **primary** untouched suite
for any shortlist fix. H11–H15 (v3) and H1–H5 (v1) are now **diagnostic** data and never count as
generalization evidence. H6–H10 (v2) stay unrun as secondary confirmation.

**Excluded concepts** (previously used or exposed): CD19, BCMA, PDCD1, SLC6A2, HRH1, HTR2A,
CHRM1, GPRC5D, KRAS, FcRn, TL1A, CLDN18.2, HER2, PCSK9, IL-23, DLL3, LRRK2, TIGIT, C5, IL-17A,
CD38, ANGPTL3.

## 1. Queries

| Id | Query | `--therapeutic-area` |
|---|---|---|
| H16 | Find clinical-stage LAG-3 antibodies for melanoma. | ONCOLOGY |
| H17 | Find clinical-stage anti-IL-4Rα antibodies for atopic dermatitis. | AUTOIMMUNE |
| H18 | Find clinical-stage GLP-1 receptor agonists for obesity. | *(omitted → UNSPECIFIED)* |
| H19 | Find clinical-stage TROP2-directed antibody-drug conjugates for breast cancer. | ONCOLOGY |
| H20 | Find clinical-stage factor XI inhibitors for prevention of thrombosis. | *(omitted → UNSPECIFIED)* |

Only ONCOLOGY and AUTOIMMUNE are classified areas, so H18 and H20 omit the flag.

**Run rules:** live runs with `--allow-incomplete` and `--as-of` set to the run date. Each run goes to
`~/se_runs/heldout_h<N>_v4`, one at a time, in the operator's terminal. A refused query fails
and is not re-phrased.

## 2. Reference sets (any listed name counts, including trade names and codes)

- **H16 (LAG3):** relatlimab (Opdualag, BMS-986016); fianlimab (REGN3767); favezelimab (MK-4280);
  ieramilimab (LAG525); encelimab (TSR-033); tebotelimab (MGD013).
- **H17 (IL4R):** dupilumab (Dupixent, REGN668); stapokibart (CM310); rademikibart (CBP-201);
  comekibart (QX005N); manfidokimab (611).
- **H18 (GLP1R):** semaglutide (Ozempic, Wegovy, Rybelsus); tirzepatide (Mounjaro, Zepbound,
  LY3298176); liraglutide (Saxenda, Victoza); orforglipron (LY3502970); survodutide (BI 456906);
  retatrutide (LY3437943); mazdutide (IBI362, LY3305677); danuglipron (PF-06882961).
- **H19 (TACSTD2):** sacituzumab govitecan (Trodelvy, IMMU-132); datopotamab deruxtecan
  (Datroway, Dato-DXd, DS-1062); sacituzumab tirumotecan (sac-TMT, MK-2870, SKB264); ESG401;
  BL-M02D1.
- **H20 (F11):** abelacimab (MAA868); osocimab (BAY 1213790); asundexian (BAY 2433334);
  milvexian (BMS-986177, JNJ-70033093); fesomersen (IONIS-FXIRx, BAY 2976217); xisomab (AB023).

**Matching** is unchanged from v1–v3: a casefolded alphanumeric key on the canonical name or any
alias. Products with suffixes (for example `-xxxx`) match only where §2 lists that exact form.
This is the frozen v3 behaviour and is carried forward unchanged.

## 3. Labels

The rubric of v2 §3 applies: RELEVANT, WRONG_TARGET (= OFF_TARGET), DUPLICATE, NON_ASSET,
UNVERIFIABLE. Labels are blind, written from public product knowledge, and committed before
scoring.

## 4. Metrics and thresholds

These are unchanged from v1–v3 §4:
- per query: P@20 ≥ 0.70 (UNVERIFIABLE excluded from the denominator), Recall@all ≥ 0.60,
  NON_ASSET ≤ 1, DUPLICATE ≤ 2, false human-PoC = 0 (v1 §4 definition);
- suite: PASS if at least 4/5 pass and there is no false human-PoC; PASS_WITH_LIMITATIONS if 3/5
  pass; FAIL otherwise.

**Target-recognition readout** (reported; a different or additional target counts as a failure):
H16 LAG3, H17 IL4R, H18 GLP1R, H19 TACSTD2, H20 F11.
