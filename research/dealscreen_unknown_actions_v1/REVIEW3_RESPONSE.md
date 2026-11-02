# Response to the third U1 review (REVIEW3.md): revision 4

Revision 4 is U1 on top of revision 3 (f5ab4c4), on `dealscreen-mvp`, as of 2026-11-02. Nobody has reviewed it yet.
This file is the implementer's account, not a review: every claim below should be checked by running code. The
reviewer and the implementer are both AI. Neither is a human approval, and nothing here is validation. U1-7 is not
claimed.

## 1. The highest-value fix: the "under a broader parent" class is for stage concepts only

REVIEW3 D1 found that revision 3's sibling rule (`ir._sibling`) admitted anything under a shared by-site parent:
lymphomas, sarcomas, other histologies, another organ's cancer with "gastric" in its type, and records that name no
site. The reviewer's suggested morphology test was tried first and did not separate the cases: NCIt files many
lymphomas and organ cancers under site trees, so their histology ancestors look like the request's. Revision 4
narrows the class to what it was introduced for. A concept is `UNDER_REQUESTED_PARENT` only when all of these hold:

- it is an NCIt stage concept (its label starts "Stage", or it sits under a "... by AJCC vN Stage" grouping);
- it shares a by-site ancestor with a requested concept;
- every ancestor not under a site is also an ancestor of the request (no virus-related, squamous or other
  non-site category the request lacks);
- its own names name one of the request's sites;
- the record's name itself names a requested site. If it does not, the name is a different disease, and the
  sentence never says "names a requested site" without the record doing so.

All 12 of the reviewer's D1 and J1 rows are now DIFFERENT_DISEASE. "Stage IV gastric cancer", "Stage III gastric
cancer", "Stage IV colorectal cancer" and the held-out "Stage IV pancreatic cancer" against a pancreatic ductal
adenocarcinoma request keep the class. The last needed one more change: a site's other names on the same by-site
node ("pancreas" and "pancreatic") are added to the request's site phrases, single words only. A multi-word name such
as "hepatic and intrahepatic bile duct" would have made bile-duct names a liver site, so it is not added.

## 2. The other findings

| Id | Revision 4 | Tests |
|---|---|---|
| D2 qualifiers read as negation | Only explicit absence is a negation: "negative", "neg", "non-expressing", "knockout", "-independent" after the symbol; "not", "no", "non", "lacking", "without", "formerly", "previously" before it; "(formerly)" as a whole note. "-low", "low-expressing", "null-Fc", "previously validated", "loss-of-function", "KO-resistant" and "deficient" now name the target | `test_d2_…` (9) |
| D3 capitals switch off BASKET | A capitalised word counts as an acronym only if it has at most 4 letters, is not a Roman numeral, reads as exactly one concept that is not a stage concept, and the text is not written in capitals. "Stage IV Solid Tumours", "STAGE IV SOLID TUMORS", "Stage III/IV solid tumors", "Solid Tumors (ALL COMERS)" and "Advanced CANCER" are baskets; "ALL", "Adult ALL" and "Relapsed ALL" still read as requested | `test_d3_…` (5) |
| D4 other negation wordings | "lacking X expression" and "X-independent" are negations. REVIEW2_RESPONSE §4.4 misstated the failure mode; it was not true | `test_d4_…` (2) |
| D5 spelling after "o" | The lookbehind no longer folds "o" into its class: "tracheooesophageal" and "hypoglycaemia" are converted, and "Gastro-oesophageal junction cancer" names the junction | `test_d5_…` (4) |
| D6 one role word blocks every occurrence | Judged per occurrence: "Gastric cancer with gastric outlet obstruction" names gastric. "<site> <word> type" is a role ("gastric foveolar type") | `test_d5_d6_…` |
| D7 transplant states | "transplant", "post", "lymphoproliferative", "myeloproliferative", "hematologic" and "hematopoietic" are not site words | `test_d7_…` |
| D8 restatements | Only an acronym is suggested ("GBM", "DLBCL"); otherwise no example. "lymphoma" and "neuroblastoma" get none | `test_d8_…` (4) |
| D9 partner target hidden | "/" splits before a name starting with a digit ("4-1BB"); " + ", " and ", " & ", ", " (not before "isoform") and "x" before "4-1BB" separate names. The partner is listed whatever the order | `test_d9_…` (6) |
| J2 request reading not shown | Not changed. The gate reads "gc" the same way; a note when a request's label differs from its text is a candidate for the next revision | — |
| J3 record excludes the requested histology | Not changed (judgement) | — |

## 3. Measured result

| Check | Result |
|---|---|
| Tests | `tests/dealscreen`: 1,099 pass (1,052 at revision 3; `test_unknown_actions.py` 223 cases). `ruff` and `mypy` clean on `bve.dealscreen` and the CLI |
| U1-1 coverage | CLDN18.2 38 of 38; held-out 104 of 104; no stray diagnostic |
| U1-3 science | CLDN18.2 0 of 62 against R1 revision 8; cross-version 0 of 312; cycle-4 equivalence byte-identical, 4 of 4 |
| CLDN18.2 outputs | Identical to revision 3: classes, actions, memo and measurement (`after/` unchanged) |

## 4. Costs and open issues

1. **The sibling class is narrow.** A non-stage concept under the request's parent that a buyer might still want
   (for example a same-site, same-histology concept NCIt files oddly) is DIFFERENT_DISEASE, with the
   "although it names <site>" clause when the record names the site.
2. **Word lists remain.** Negation, lineage, role and placeholder words are generic, not landscape words, but they
   are DealScreen's own (J5). Each review has found inputs they miss.
3. **U1-7 is open** until a fresh adversarial review of revision 4.
