# Response to the fourth U1 review (REVIEW4.md): revision 5

Revision 5 is U1 on top of revision 4 (04faab7) and R1 revision 10, on `dealscreen-mvp`, as of 2026-11-02. Nobody
has reviewed it yet. This file is the implementer's account, not a review: every claim below should be checked by
running code. The reviewer and the implementer are both AI. Neither is a human approval, and nothing here is
validation. U1-7 is not claimed.

## 1. The two medium findings

**D1 (regression): an all-caps qualifier made an "ALL" record a basket.** Revision 4 stopped reading any capitalised
word as an acronym once the text had two capitalised words of three or more letters. Revision 5 drops that switch.
A capitalised word that the index reads as one concept (`_acronym`) is an acronym unless a basket word follows it
("ALL COMERS", "ALL SOLID TUMORS"; `_before_basket_word`). Results:
- "RELAPSED ALL", "ALL, RELAPSED", "ADULT ALL", "ADVANCED ALL" and "RELAPSED/REFRACTORY ALL" are no longer baskets.
- "PEDIATRIC ALL" is not a basket either.
- "ALL COMERS", "SOLID TUMORS (ALL COMERS)", "ALL SOLID TUMORS" and "STAGE IV SOLID TUMORS" stay baskets.
- In the reviewer's end-to-end workspace, Q-1802 ("RELAPSED ALL") is BROADER_THAN_REQUESTED and TQB2103
  ("PEDIATRIC ALL") is DIFFERENT_DISEASE (Childhood ALL), as expected.

**D2: the stage-only sibling rule admitted stage concepts of other lineages.** This uses the reviewer's tested fix.
`ir._sibling` now also requires that every ancestor of the stage concept that the request lacks has "stage" in its
label, so the only extra ancestors are stage groupings. These are no longer UNDER_REQUESTED_PARENT:
- "Stage IV gastric neuroendocrine tumor" and "Stage III Gastric Neuroendocrine Tumor AJCC v8" (gastric request);
- "Stage IV pancreatic neuroendocrine tumor" (pancreatic ductal adenocarcinoma);
- "Stage IV colorectal neuroendocrine tumor" (colorectal adenocarcinoma);
- "Stage IV small cell lung cancer" (lung adenocarcinoma);
- "Stage IV uterine corpus leiomyosarcoma" (endometrioid adenocarcinoma).

"Stage IV gastric cancer", "Stage IV colorectal cancer" and the held-out "Stage IV pancreatic cancer" keep the
class. The cost is the reviewer's own: "Stage … Endometrial Cancer FIGO 2023", "Stage … Adult Liver Cancer AJCC
v7" and "Stage … Anal Canal Cancer" become DIFFERENT_DISEASE again, the older understatement. The docstring now
says so.

## 2. The other findings

| Id | Revision 5 | Tests |
|---|---|---|
| D3 both expression states read as negation | A value that states the target both negative and positive ("X negative or positive", "X neg/pos", "X-negative and -positive") is not read as stating the target absent. It now gives "may name the required target". "X negative; Y positive" still reports X as negated | `test_r5_d3_…` (4) |
| D4 a basket with its own acronym | `is_basket` removes a parenthetical acronym of the words before it first: "Advanced solid tumors (AST)", "Advanced Cancer (AC)", "Malignant solid tumor (MST)" and "Advanced malignancies (AM)" are baskets | `test_r5_d4_…` (4) |
| D5 a TNBC request has no site words | Not changed. The cause is the site-phrase boundary rule (biomarker words before the site); a change there touches every request and needs its own sweep | — |
| D6 partner targets after " / ", "or", "vs", "→" | Not changed (low). Each separator is another list word; adding "or" would split "X negative or positive", which D3 now reads whole | — |
| D7 "without X selection" read as a negation | Not changed (low). "without" before a symbol is a negation in other phrasings ("without X expression"); the reviewer's examples need a rule for "selection", which is a new word list | — |
| D8 "<site> <tumour head> type" read as a role | A tumour head before "type" is not a role: "Gastric cancer type: diffuse" and "Gastric carcinoma type 2" are readable again | `test_r5_d8_…` (2) |
| D9 "TUMOR" as a restatement | A basket word is never offered as a restatement | `test_r5_d9_…` |

## 3. Measured result

| Check | Result |
|---|---|
| Tests | `tests/dealscreen`: 1,327 pass (1,300 with R1 revision 10 alone; `test_unknown_actions.py` 250 cases, 27 new). `ruff` and `mypy` clean on `bve.dealscreen` and the CLI |
| U1-1 coverage | CLDN18.2 38 of 38; held-out 104 of 104 (FcRn v1 28, FcRn v2 28, C5 28, synthetic 20); no stray diagnostic |
| U1-3 science | CLDN18.2 0 of 62 against the frozen baseline; cross-version 0 of 312; cycle-4 equivalence byte-identical, 4 of 4 |
| CLDN18.2 outputs | Identical to revision 4: all 38 rows of `unknown_actions.csv` and the memo (`after/` unchanged) |
| Reviewer's end-to-end workspace (`u1rr4/ws_e2e_all`, re-screened) | Q-1802 BROADER_THAN_REQUESTED, TQB2103 DIFFERENT_DISEASE, RC118 ("Relapsed ALL") BROADER_THAN_REQUESTED as before |

## 4. Costs and open issues

1. **D2's cost.** Stage concepts NCIt files under a population or staging-system node the request lacks are
   different diseases again (FIGO endometrial, adult liver, anal canal).
2. **D5, D6 and D7 are open** (low). Each is a change to a shared word rule that needs its own sweep.
3. **Word lists remain** (J5). Basket, negation, role and lineage words are generic, not landscape words, but they
   are DealScreen's own.
4. **U1-7 is open** until a fresh adversarial review of revision 5.
