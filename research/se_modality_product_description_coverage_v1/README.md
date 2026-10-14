# MODALITY_PRODUCT_DESCRIPTION_COVERAGE_DIAGNOSIS v1 — JUSTIFIED (narrowly)

Preregistration `19c9074` (adjudication, v3 reconciliation, taxonomy, readiness rule). Diagnosis only: no production change, v3 stays unadopted. Reproduce: `PYTHONPATH=src python research/se_modality_product_description_coverage_v1/diagnose.py --output <new dir>`. Two builds byte-identical.

## Adjudication (13 admitted v3 facts)

13/13 agree with the frozen v3 labels (8 TRUE, 5 FALSE). v3 `labels.json` is unchanged and no new validation contract is needed. Three evidence limitations are recorded in `adjudication.json`:
- CLN-978 is TRUE, but linking it to the modality needs cross-sentence coreference (unnamed title + "construct called CLN-978"); the stored claim passage is truncated before the name.
- Two candidates are generic class labels ("BiTE (CD19 x CD3 Bispecific Antibody)"), an identity limitation.
- BNT162b2 is supported only by `otherNames`, one of which is a registry error.

## Denominator

v3's categories are exclusive (282 + 11 = 293); "1 conflict" is a flag on a D row. **New finding:** the 293 are *run-fact rows*, not facts. They are **172 distinct content-addressed facts**, 121 of which appear in both TAC01 and mint5. v3's R2 counted rows against its frozen 293 and is unaffected, but its "293 facts" wording overstates the evidence. The checker here keys rows by (run, fact_id); the self-test caught the original fact_id-only key before any verdict was computed.

## Source-structure coverage (293 rows; mutually exclusive primary class)

| Class | Rows | Eligible |
|---|---|---|
| APPOSITIVE | 15 | yes |
| COPULA (incl. plain premodifiers) | 10 | yes |
| NAME_SELF_DESCRIBING (CT.gov name) | 11 | yes |
| STRUCTURED_OTHERNAMES | 4 | yes |
| CLASS_OF | 2 | yes |
| REGISTRY_CATEGORY ("Biological/Vaccine:") | 2 | no |
| CO_OCCURRENCE (name + modality, no product link) | 199 | no |
| NAME_ABSENT | 26 | no |
| MODALITY_ABSENT | 24 | no |

42 rows (30 distinct facts) have an explicit product-level structure; 251 do not. By modality, **PEPTIDE has 0/32 eligible**: every legacy PEPTIDE fact is co-occurrence or has no modality text, consistent with datopotamab. Most public-document TCE facts (148) are co-occurrence: abstracts about *other* engagers that mention the candidate.

## Readiness (computed; self-test passes)

C1 safety PASS: none of the 5 FALSE facts has an eligible structure (the registry category, co-arm vaccine labels and other-product TCE all reject). C2 explicit recall PASS: 7/7 explicitly supported TRUE facts match their adjudicated structure, and CLN-978 correctly has none. C3 PASS. **Verdict: JUSTIFIED.** A post-measurement spot check of all 27 other eligible distinct facts found no false product attribution (`results/eligible_spot_check.txt`; evidence only, not acceptance).

## Limits of this justification

- The calibration set is 13 facts; the 27 spot-checked facts were not adjudicated in advance.
- These are research matchers, not a recognizer. An implementation must re-derive the five structures inside `modality_scope` with frozen positive and negative controls, including the generic-identity and registry-category cases.
- Even a perfect implementation leaves ~86% of rows UNKNOWN, because most source evidence is genuinely co-occurrence. A semantic consumer would therefore still withdraw most legacy facts; whether that is acceptable is a v4 semantic-design question, not settled here.

## Next (recommended, not preregistered here)

`MODALITY_SCOPE_PRODUCT_DESCRIPTION v1`: a decision-neutral extractor milestone adding APPOSITIVE, COPULA-with-plain-premodifiers, CLASS_OF and structured CT.gov name/otherNames scope. Preregister independent controls, an independently adjudicated sample beyond these 13, and a REGISTRY_CATEGORY negative. Only then a v4 semantic design.
