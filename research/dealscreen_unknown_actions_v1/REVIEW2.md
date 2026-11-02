# Cycle U1 revision 2: adversarial re-review

INTERNAL DEVELOPMENT. This is an AI-simulated adversarial review. It is not human or independent validation.

**Reviewed:** the staged copy `/home/djmann/.cache/u1_stage4` (R1 revision 7 at 50fd206, plus U1 revision 2).
**Criteria:** `ACCEPTANCE.md`, including the revision note (`u1r3/acceptance_note.md`), `MEASUREMENT.md` and
`REVIEW_RESPONSE.md`.

The reviewer recomputed every number below by running code, unless it is marked "read, not re-run". The stage
imports from `/home/djmann/.cache/u1_stage4/src/bve/__init__.py`. Scratch files are in `/tmp/claude-1000/u1rr/`.

## Verdict in one paragraph

Revision 2 still changes no science. Coverage is complete. Most of the first review's findings are fixed:

- **D1 fixed.** An unresolvable request no longer makes an exact match a "different disease".
- **D3 and D10 fixed.** The acronym clean-up and the no-field wording are fixed.
- **Mostly fixed:** D2, D4, D6, D7 and D12.

U1-7 is still **not met**. Held-out inputs show four problems:

1. **The J1 change sends real leads to the bottom.** "Stage IV gastric cancer", a common vendor phrasing, is now
   DIFFERENT_DISEASE. That class sits below BASKET. Revision 1 classed it NAMES_REQUESTED_SITE. The same happens
   with "Stage IV colorectal cancer" against a colorectal adenocarcinoma request.
2. **The suggested restatement can be a different disease.**
   - "pnh" → "Periventricular Nodular Heterotopia". The memo and the `screen` warning show only this suggestion.
   - "astrocytoma" → "Childhood Astrocytoma".
   - "mesothelioma" → "Mesothelial Neoplasm".
3. **New site rule (regression).** It never reports a multi-word site that a record names. Also, the British-spelling
   clean-up corrupts the American spelling "gastroesophageal" to "gastresophageal". As a result "Gastroesophageal
   Junction Cancer" is UNREADABLE, while "GEJ Cancer" is NAMES_REQUESTED_SITE.
4. **"ALL" is called a basket.** "Relapsed/refractory ALL" is still classed BASKET, "names no disease or site",
   although the NCIt index reads "ALL" as Acute Lymphoblastic Leukemia.

Several smaller target and site-word defects remain (D2, D4 and D5 residues). On the shipped CLDN18.2 outputs, the
reviewer found no false program-level statement. The new spelling and multi-word defects do understate two
reference-IN programs' GEJ names at the name level.

## Verdict per criterion

| AC | Verdict | Evidence |
|---|---|---|
| U1-1 coverage | **Met** | From fresh `screen` runs of copies of `u1_stage4_ws` and all four `u1_stage4_xv` workspaces (`coverage.py`): CLDN18.2 38/38, c5_heldout 28/28, fcrn_v1 28/28, fcrn_v2 28/28, synthetic_200 20/20. None of these has a diagnostic on an excluded program or a non-UNKNOWN decision. Every fresh `screening.json` is identical to the shipped one. Request-level cases also reach full coverage: buyer `gastric cancer` 53/53, `pnh` 53/53, `gastric cancer, gastroesophageal junction adenocarcinoma` 40/40. Every action names the value as written or "nothing on record". The c5 "Nothing on record." mechanism rows match empty `Mechanism` cells. |
| U1-2 authorities only | **Met (letter), with notes** | `grep -i -E "gastr\|claudin\|cldn\|gej\|stomach\|fcrn\|myasthenia\|tigit\|zolbet\|pancrea\|junction…"` on `indication_relations.py` and `diagnostics.py` finds only docstrings and comments. The one exception is the generic spelling pair `("oesophag","esophag")`; this rule is the source of defect N3. `workbook.py`, `memo.py`, `screening.py`, `facts.py` and `cli/dealscreen.py` have no hits in U1 logic. Some logic does not come from the authorities: `_SYMBOL_SHAPE`, `_PLACEHOLDER_WORDS` and `_SPELLING`. The "by-site" site phrases come from NCIt but include non-sites (N5). |
| U1-3 no change to science | **Met** | **CLDN18.2:** fresh screen vs `baseline/screening_R1.json` — 0 of 62 programs differ on disposition, rank, decisions, machine_recommendation, transaction or transaction_rank. Top-level keys are equal. The only per-program key that differs is `unknown_diagnostics`. **Held-out:** each `u1_stage4_xv` workspace (re-screened fresh) vs `rights_v1/xv7` — 0 of 40, 40, 40 and 192 programs differ; again only `unknown_diagnostics` differs. **Equivalence:** re-run, byte-identical on 4 of 4 (see the "Equivalence" section). |
| U1-4 held-back tests | **Met as written; insufficient in substance** | `test_unknown_actions.py`: 106 cases, all pass. DealScreen suite: 922 passed, 5 warnings (re-run). No test covers any of the following, and each fails (N1–N4): a record-side multi-word site phrase; American "gastroesophageal"; NCIt stage concepts; an acronym that is also a basket word; restatement of an acronym request or of a request whose exact-label concept has no unique name. The test at line 366 checks that "gastroesophageal junction" is a site phrase. It never checks that a record naming it is classed as naming it. |
| U1-5 surfaces | **Met, with notes** | Regenerated from a copy of the workspace. The memo is identical to `after/memo_u1.md`. The Screening (64 rows) and Diligence (93 rows) sheets are cell-identical to `after/u1_cldn18.xlsx`. Diligence has 38 GATE_UNKNOWN rows, each with the DealScreen action followed by "(S&E: …)". "Confidence limitations" holds "Record class … (DealScreen; describes the record, which can be wrong)". The Screening sheet gives the class per open gate and per name. No scope or recommendation wording appears in any diagnostic in the five landscapes (searched: in/out of scope, exclude, eligible, recommend, prioriti, pursue, promising, should, attractive, relevant, drop). Notes: in the memo, SOT102 (different disease, reference IN) is still hidden in "3 more" (N13). For an unresolved request, the memo and the `screen` warning show only the suggested restatement, not the readings (N2). |
| U1-6 per program vs reference | **Met as measured** | Recomputed against `reference_calls.csv`. 16 reference-IN programs are not ELIGIBLE: 15 UNRESOLVED, plus LCB02A, which is EXCLUDED and has no diagnostic (disclosed). No gastric or GEJ name of a reference-IN program is DIFFERENT_DISEASE. All 6 basket programs among them (RC118, VBC108, SG1906, TQB2103, AK132, Q-1802) and the other basket programs name the requested indications in the action. Rilvegostomig, Volrustomig and RC148 name TIGIT, CTLA-4 and 'PD-1' respectively. SOT102 is reported as pointing away. DA-3501 is now BROADER, with the population artefact stated. Below the program level: CMG901 "Gastroesophageal Junction Cancer" and AZD5863 "Gastro-esophageal Junction Cancer" are UNREADABLE, and IBI343 and AMG 910 show only "gastric" (N3). This does not change any program's class. |
| U1-7 adversarial review | **Not met** | N1–N8 below are actions that misstate the record or the authority, or mislead, on held-out inputs. N1 and N3 are regressions introduced by revision 2: the revision 1 stage at `/home/djmann/.cache/u1_stage` gives NAMES_REQUESTED_SITE for both inputs. N1, N3 and N4 were confirmed end to end through `import` and `screen`. No hidden UNKNOWN and no change to science. |

## Status of the first review's findings

The inputs used are those in `/tmp/claude-1000/u1rev/verify_*.py`, re-run against stage4, plus the reviewer's
probes in `/tmp/claude-1000/u1rr/probes/`.

| Id | Status | Input → output (stage4) |
|---|---|---|
| D1 unresolvable request | **Fixed** (new defect N2 in the suggestion) | `indication_diagnostic(["Gastric Cancer"], ["gastric cancer"])` → REQUEST_NOT_ONE_CONCEPT; no name is compared. **End to end**, buyer `[gastric cancer]`: all 39 indication diagnostics are REQUEST_NOT_ONE_CONCEPT, and the `screen` stderr warning is printed. Buyer `[gastric cancer, gastroesophageal junction adenocarcinoma]`: 20 programs PASS through the resolved request; the 26 UNKNOWN programs name the cited fact and the restatement. "INDICATION:B_CELL_LYMPHOMA" is described as an S&E rule. "the gate cannot pass any record through it" is true: 62/62 UNKNOWN with `[gastric cancer]` and with `[pnh]`. |
| D2 non-site "site words" | **Partly fixed** | Every row of the first review's D2 table is now DIFFERENT_DISEASE or UNREADABLE. Still present: "neuroendocrine", "endocrine", "hematologic", "pregnancy", "immunodeficiency", "lymphoproliferative", "aids related", "histiocytic" and "sex cord stromal" are site phrases (N5). The first review's own case still says "'Pancreatic Neuroendocrine Tumor' … although it names neuroendocrine, a requested site". |
| D3 acronym clean-up | **Fixed** | "Adenocarcinoma (PDAC)", "Gastrointestinal Cancer (CRC)", "Leukemia (AML)", "Lymphoma (DLBCL)", "Carcinoma (breast)" and "Tumor (brain)" → UNREADABLE. "Lung Cancer (NSCLC)" for an SCLC request → NAMES_REQUESTED_SITE "names lung", which is true (judgement J-b). Clean-ups are shown in the AMBIGUOUS sentences ("Breast Cancer (BC)" … "once acronym '(BC)' removed"). |
| D4 variant spelling, placeholders | **Partly fixed** | "CLDN 18.2", "Claudin-18.2" and "CLDN-18.2" → names the required target. "CLDN18A2" → may name it. "Undisclosed Target", "PROPRIETARY", "TAA", "TBD" and "Tumor antigen" → placeholder. Still wrong: "Novel ADC target", "Proprietary antigen X" and "Target 1" → SOURCE_NAMES_OTHER_TARGETS, summary "names other targets only" (N8). |
| D5 isoform pairs, negations | **Partly fixed** | Fixed: "QRX7.1xZPL4" and "CLDN18.1xCD3" → other isoform. Still wrong: "VORP3, isoform 2" → names the required target "without stating isoform 1". "VORP3-AS1", "VORP3.1 non-expressing", "VORP3.1 (formerly)" and "VORP3.1 knockout" → SOURCE_NAMES_REQUIRED_TARGET. "KLX9 (VORP3.1 negative)" → SOURCE_MAY_NAME_REQUIRED_TARGET, and KLX9 is not mentioned (N6, N7). |
| D6 exclusions | **Fixed** | All 7 exclusion forms → UNREADABLE. "HER2-negative, not previously treated gastric cancer" and "Unresectable (not amenable to surgery) gastric cancer" → NAMES_REQUESTED_SITE. "Non-liver solid tumors" and "Solid tumours, liver excluded" → UNREADABLE. New understatement: "Peritoneal metastases of gastric cancer" → UNREADABLE (N10). |
| D7 index artefacts | **Fixed (with disclosure)** | DA-3501 → BROADER, "('Childhood Gastric Carcinoma' read as 'Gastric Carcinoma' (the record states no population))". "Adenocarcinoma" → BROADER (the concept its label names exactly). New artefact of the same kind: a record "Stage IV gastric cancer" is read as the edition-specific "Stage IV Gastric Cancer AJCC v7" (part of N1). |
| D8 understatements | **Partly fixed; regression** | "GEJ adenocarcinoma" and "GEJ Cancer" → NAMES_REQUESTED_SITE. "Gastro-oesophageal junction adenocarcinoma" → READS_AS_REQUESTED. But the spelled-out phrase is now *worse*: "Gastroesophageal Junction Cancer" and "Esophagogastric junction cancer" → UNREADABLE, where revision 1 gave NAMES_REQUESTED_SITE (N3). |
| D9 lead name | **Fixed** (memo part unchanged) | EO-3021 leads with "'Stomach Neoplasm' reads as Gastric Neoplasm". The memo still hides SOT102 in "3 more" (N13). |
| D10 no assertable field | **Fixed** | `other_diagnostic([], None, …, "identity_valid")` → "DealScreen maps no landscape field to this gate's fact (identity_valid)." |
| D11 wording | **Mostly fixed** | No false "the gate does not apply" remains, and steps are written in words. Residue: "once relapsed", "once refractory" (for example "'AIDS-related Kaposi sarcoma, refractory' reads as … once refractory"). |
| D12 over-promise | **Fixed** | "What would pass the gate: …"; "The gate never fails on this evidence …"; "or reject a wrong claim" is gone (it is kept only for CONFLICTING, where it is correct). |
| D13 spec deviation | **Fixed (disclosed)** | The revision note discloses it. "Pancreatic Cancer" → DIFFERENT_DISEASE, and both readings are listed. |
| J1 resolved reading outranks site | **Adopted; side effect N1** | "Gastric Ulcer", "Gastric GIST", "Gastric MALT Lymphoma" → DIFFERENT_DISEASE "although it names gastric, a requested site". The same rule sends NCIt stage concepts for the requested site to DIFFERENT_DISEASE (N1). |
| J2 site word's role | **Adopted** | "with liver metastases", "metastatic to the liver", "gastric type" and "Gastric Outlet Obstruction" no longer give NAMES_REQUESTED_SITE. |
| J3 excluded programs | **Stated** | Recomputed: 17 UNKNOWN decisions on 16 excluded programs, matching MEASUREMENT. |
| J4 unread targets | **Adopted** | "It also names 'PD-1', which the target authority does not read; it is not written as CLDN18 or its name." |

## Defects in revision 2, ranked by how much they could mislead

`dg` = `bve.dealscreen.diagnostics` and `ir` = `bve.dealscreen.indication_relations`. "E2E" means confirmed through
`bve-dealscreen import` and `screen` on a scratch copy of the CLDN18.2 inputs with some indication cells edited
(`/tmp/claude-1000/u1rr/ws_e2e2`, `/tmp/claude-1000/u1rr/ws_all`).

### N1 (high, regression). NCIt stage concepts for the requested site become DIFFERENT_DISEASE, below BASKET

- **Input:** `dg.indication_diagnostic(["Stage IV gastric cancer"], ["gastric adenocarcinoma", "gastroesophageal junction adenocarcinoma"])`.
  E2E: VBC108's indication cell set to "Stage IV gastric cancer".
- **Wrong output:** class DIFFERENT_DISEASE. Action: "'Stage IV gastric cancer' reads as Stage IV Gastric Cancer AJCC
  v7 (NCIt), neither a requested indication nor a subtype of one, although it names gastric, a requested site."
  The memo groups VBC108 with SOT102 under "a disease neither requested nor a subtype of one". In the program order,
  DIFFERENT_DISEASE ranks below BASKET.
- **Same result:**
  - "Stage III gastric cancer".
  - "Stage IV colorectal cancer" against `colorectal adenocarcinoma`, which reads as two AJCC-edition concepts.
- **Inconsistent results for near-identical wording:**
  - "Gastric cancer stage IV", "Stage IV Gastric Cancer AJCC v8" and "Resectable gastric cancer" → NAMES_REQUESTED_SITE.
  - "Metastatic Gastric Carcinoma" and "Recurrent Gastric Carcinoma" → OVERLAPS_REQUESTED.
  - "Metastatic gastric cancer" → AMBIGUOUS_NAME_ALL_BROADER.

  The class depends on word order and on which NCIt edition concept the index happens to hold.
- **Why it misleads:** NCIt places "Stage IV Gastric Cancer AJCC v7" under Gastric Carcinoma. Gastric Carcinoma is
  the requested concept's own parent, so the concept is a sibling under a broader parent, not an unrelated disease.
  The relation function has no notion of such a sibling, so it returns "not requested". The class name and the memo
  phrase then present a gastric-cancer program as a different disease. This is the U1-6 failure mode on a common
  vendor phrasing. The record does not state an AJCC edition, yet the reading names v7 (an index artefact, like D7).
  The revision 1 stage classed the same input NAMES_REQUESTED_SITE.
- **Expected:** not DIFFERENT_DISEASE. For example, a class such as "a subtype of Gastric Carcinoma (broader than
  requested) that NCIt does not place under the request", ordered with the broader classes. Do not state the
  edition as the record's.

### N2 (high). The suggested restatement of an unresolvable request can be a different disease

- **Inputs and outputs (`ir.restatement`, as shown in the action, the memo and the `screen` warning):**
  - `pnh` → "for example 'Periventricular Nodular Heterotopia', which the authority reads as Periventricular Nodular
    Heterotopia alone". The request matches Periventricular Nodular Heterotopia and Paroxysmal Nocturnal
    Hemoglobinuria. The suggestion is a neurological malformation, picked by index order. E2E on a copy with
    `indications: [pnh]`: the stderr warning and the memo's "Investigate next" line show only this suggestion, not
    the two readings.
  - `astrocytoma` → "Childhood Astrocytoma". The docstring promises to avoid population-specific concepts unless the
    request states one. The concept labelled "Astrocytoma" has no uniquely resolving name, so the code falls through
    to the childhood concept.
  - `mesothelioma` → "Mesothelial Neoplasm", a broader concept that includes benign mesothelial tumours. The concept
    labelled "Mesothelioma" is skipped for the same reason.
  - `endometrial cancer` → "Malignant Endometrial Neoplasm" (broader). `gastric cancer` → "Gastric Carcinoma"
    (narrower). The rule is not consistent between "cancer" requests.
- **Cause:** the rank orders candidates by "label equals request", then "no unstated population", then index
  position. When the best-ranked concept has no unique name, the next concept is suggested without any check that
  it is the same disease.
- **Expected:**
  - Suggest a restatement only when it reads the same concept as the request's exact-label reading. Otherwise give
    a unique name for that concept, or no example.
  - When the readings are unrelated (an acronym), list them and ask the buyer to choose; never pick one.
  - Show the readings in the memo and the warning, not only the example.

### N3 (medium-high, regression). Multi-word requested sites are never reported, and "gastroesophageal" is misspelled

- **Input:** `dg.indication_diagnostic(["Gastroesophageal Junction Cancer"], GAS)`. E2E: Q-1802's cell set to that
  name.
  **Wrong output:** UNREADABLE, "'Gastroesophageal Junction Cancer' is not a name the NCIt authority can read".
  "GEJ Cancer" gives NAMES_REQUESTED_SITE.
- **Same result:**
  - "Esophagogastric junction cancer" → UNREADABLE (E2E, AK132).
  - "Recurrent head and neck cancer, platinum-refractory" against a head and neck squamous cell carcinoma (HNSCC)
    request → UNREADABLE.
- **Two causes:**
  1. `ir._shown_sites` drops every hit for which some phrase "abbreviates" it. `ir._abbreviates(p, p)` is True for
     any multi-word phrase (checked for "head and neck", "esophagogastric junction" and "gastroesophageal junction").
     So every multi-word site the record names is removed, and the name falls to UNREADABLE.
  2. `ir.us_spelling` replaces the substring "oesophag" anywhere: "Gastroesophageal" → "Gastresophageal",
     "tracheoesophageal" → "tracheesophageal", "cardioesophageal" → "cardiesophageal". The American spelling of the
     requested site never matches.
- **Shipped CLDN18.2 effect (name level only):**
  - CMG901 "Gastroesophageal Junction Cancer" and AZD5863 "Gastro-esophageal Junction Cancer" are UNREADABLE.
  - IBI343 and AMG 910 report "names gastric" only.

  A program whose only GEJ name is spelled out falls to the lowest class. The revision 1 stage classed
  "Gastroesophageal Junction Cancer" NAMES_REQUESTED_SITE.
- **Expected:** NAMES_REQUESTED_SITE ("names gastroesophageal junction, a requested site"). To fix:
  - In `_shown_sites`, exclude the phrase itself (`p != hit`).
  - Apply British-to-American spellings only at a word start (`\b`), or as whole-word mappings.

### N4 (medium). An acronym that is also a basket word is called "a basket naming no disease"

- **Input:** buyer `[acute lymphoblastic leukemia]`; record "Relapsed/refractory ALL" (E2E, VBC108).
- **Wrong output:** BASKET, "'Relapsed/refractory ALL' names no disease or site (a basket)."
- **What else is true:**
  - The NCIt index maps "all" to Acute Lymphoblastic Leukemia.
  - Through the same `screen`, "Relapsed ALL", "Adult ALL" and "ALL (adult)" PASS the gate.
  - Through `dg.indication_diagnostic`, "ALL", "Adult ALL" and "ALL, children" are also called baskets.
- **Cause:** `is_basket` runs first, and "all" is a basket word (`_BASKET_EXTRA`). The frozen check order allows this
  (pre-existing; the revision 1 stage gives the same output), but the sentence misstates the record.
- **Expected:** treat a token in upper case as possibly an acronym. Do not call a name a basket when the authority
  reads one of its tokens as a concept; give UNREADABLE at worst.

### N5 (medium, D2 residue). Non-site words still reported as "a requested site"

Site phrases come from NCIt nodes under "… by Site". They still include lineage, histology, therapy and state words.
Each output below says "names X, a requested site" (or "although it names X, a requested site"):

| Request | Record name | Output |
|---|---|---|
| Recurrent Endocrine Carcinoma | "Endocrine therapy-resistant breast cancer" | NAMES_REQUESTED_SITE, "names endocrine" |
| Metastatic Neuroendocrine Tumor | "Neuroendocrine prostate cancer" | NAMES_REQUESTED_SITE, "names neuroendocrine" |
| neuroendocrine carcinoma | "Pancreatic Neuroendocrine Tumor" | DIFFERENT_DISEASE "… although it names neuroendocrine, a requested site" |
| Hematologic Neoplasm with Germline DDX41 Mutation | "Hematologic toxicity" | NAMES_REQUESTED_SITE, "names hematologic" |
| Toxemia of Pregnancy | "Pregnancy-associated breast cancer" | NAMES_REQUESTED_SITE, "names pregnancy" |
| Immunodeficiency with Hyper-IgM Type 2 | "Severe combined immunodeficiency" | "… although it names immunodeficiency, a requested site" |
| Lymphoproliferative Disorder | "X-linked lymphoproliferative disease" | NAMES_REQUESTED_SITE, "names lymphoproliferative" |

- **Wider sweep:** over all 24,906 NCIt concepts, the 1,090 distinct site phrases also include:
  - "aids related", "histiocytic", "ambiguous lineage", "sex cord stromal", "peroxisome biogenesis";
  - "von willebrand", "immunosuppression related", "well differentiated neuroendocrine", "myoepithelial".
- **Expected:** never call these sites. Exclude phrases that name a morphology, lineage, condition or state. One way:
  require the site node's own children to include anatomic subdivisions; another is to subtract the names of
  concepts under "… by Morphology" and "Disorder by Special Category".

### N6 (medium, D5 residue). A negated mention of the required target hides the other target and is summarised as the required target

- **Request:** fictional `TargetTerm("VORP3", "Vorpin 3.1")`, with KLX9 readable.
- **Input:** "KLX9 (VORP3.1 negative)".
  **Wrong output:** SOURCE_MAY_NAME_REQUIRED_TARGET, "'KLX9 (VORP3.1 negative)' contains VORP3 or its name, in a form
  neither the target authority nor DealScreen reads". KLX9, the only target the record states, is not mentioned.
- **The real reader gives the same class for:** "CLDN18.2-negative", "CLDN18.2 low" and "not CLDN18.2".
- **The Screening sheet summary:** "the required target in a form DealScreen does not read". For a negation, this
  asserts the opposite of the record.
- **Expected:**
  - A negated mention is reported as negated ("states it is not CLDN18.2").
  - Other targets in the same value are still listed.
  - The summary does not call the value the required target.

### N7 (medium-low, D5 residue). Isoform and annotation errors in "names the required target"

- **"VORP3, isoform 2"** → SOURCE_NAMES_REQUIRED_TARGET, "names VORP3 (Vorpin 3.1) without stating isoform 1".
  The record states isoform 2: the comma defeats the isoform pattern, which accepts only "X.2" and "X isoform 2".
- **"VORP3-AS1"** (an antisense-RNA symbol shape) → "names VORP3 … without stating isoform 1".
- **Negations written after the symbol:** "VORP3.1 non-expressing", "VORP3.1 (formerly)" and "VORP3.1 knockout"
  → SOURCE_NAMES_REQUIRED_TARGET. `_NEGATED` catches "formerly" only before the symbol.
- **Expected:**
  - "isoform 2 of VORP3, not isoform 1" for the first.
  - "may name" at most for the second.
  - Not "names the required target" for the negations.

### N8 (medium-low, D4 residue). Placeholder variants are "other targets"

- **Inputs:** "Novel ADC target", "Proprietary antigen X", "Target 1".
- **Output:** SOURCE_NAMES_OTHER_TARGETS, "The record names 'Novel ADC target', which the target authority does not
  read; it is not written as VORP3 or its name." Summary: "names other targets only".
- **Cause:** "ADC" and "1" make `_SYMBOL_SHAPE` treat the text as a symbol.
- **Expected:** UNREADABLE (a placeholder), or at least not the summary "names other targets only".

### N9 (low). Misquoted fragments of the record

- "CLDN18.2 and/or CLDN6" → "'CLDN18.2 and' names CLDN18 …; also on record: 'or CLDN6'". The "/" is turned into a
  separator.
- "CLDN6/9" → "It also names '9'".
- "N/A" → "('N', 'A' is a placeholder)".

**Expected:** quote the values as written.

### N10 (low). "metastases of" masks the primary site

- "Peritoneal metastases of gastric cancer" → UNREADABLE. `_ROLE_BEFORE` treats the words after "metastases of" as
  a metastatic site, but here they name the primary.
- This is an understatement (the safe direction).

### N11 (low). Wording

- **Request level:** "DealScreen compares no record name with a request it cannot read (it still compares names with
  X)". No per-name comparison is then shown: every name is classed REQUEST_NOT_ONE_CONCEPT. The gate compares; the
  diagnostic does not.
- **Restatements are written as normalised index keys:** "burkitt s lymphoma", "lymphomatous", "medulloblastomas",
  "wilms tumor wt", "neuroblastoma nbl".
- **Duplicated labels:** "reads as Polycystic Ovary Syndrome; Polycystic Ovary Syndrome (NCIt)".
- **Unread steps:** "once relapsed", "once refractory" (D11 residue).

### N12 (low, latent). Not reached through `screen`

`dg.indication_diagnostic(names, [])` classes every resolvable name DIFFERENT_DISEASE against an empty request. Through
`screen` an empty `indications` list skips the gate (checked E2E: no indication diagnostics), so no output is affected.

### N13 (low, D9 memo part, unchanged)

The memo's single-gate line ends "3 more". This hides SOT102 (DIFFERENT_DISEASE, reference IN, the one program
MEASUREMENT reports as pointing away), AZD5863 and Givastomig.

## Judgement calls (labelled; not counted as defects)

- **J-a. A requested site in a non-disease name that NCIt cannot read is a lead.** Each of these is
  NAMES_REQUESTED_SITE, the second-highest class:
  - "Stomach flu" (E2E, TQB2103);
  - "Breast-feeding" (breast carcinoma request);
  - "Liver fibrosis" (HCC request);
  - "Kidney stones" (CKD request);
  - "Chemotherapy-induced nausea in gastric cancer" and "Intestinal Metaplasia of the Stomach".

  Names of the same kind that NCIt does read are DIFFERENT_DISEASE ("Overactive bladder" vs "Bladder pain syndrome").
  The rule conforms to the spec, and each sentence is true. The lead is lexical.
- **J-b. The record's own words exclude the request.** "Lung Cancer (NSCLC)" (SCLC request), "Hormone-sensitive
  prostate cancer" (castration-resistant prostate cancer (CRPC) request) and "Liver cancer, not hepatocellular" (HCC
  request) each → "names <site>, a requested site". This is true, but the record excludes the requested histology or
  state.
- **J-c. Understatement of exact requests with a qualifier.** These are UNREADABLE, the lowest class:
  - "Hepatocellular Carcinoma (Child-Pugh B)";
  - "Heart failure with preserved ejection fraction (HFpEF)";
  - "Plaque psoriasis (moderate-to-severe)";
  - "Severe eosinophilic asthma";
  - "Myasthenia gravis, excluding ocular".

  Non-oncology requests have no site phrases, so they have no lead class at all. This conforms to the spec and errs
  in the safe direction. For a myasthenia gravis or asthma buyer it puts the best leads last.
- **J-d.** SOURCE_MAY_NAME_REQUIRED_TARGET for "CLDN18A2" and "VORP3L1" is a reasonable hedge.

## Reading `after/` as a BD analyst

- **Clear and true per program.** For example, RC118: "'Advanced Solid Tumor' names no disease or site (a basket)
  (and 3 other name(s) on record). What would pass the gate: a cited source naming gastric adenocarcinoma or
  gastroesophageal junction adenocarcinoma (or a subtype)…".
- **The PD-1 rows are clear and correct.**
- **Modality rows are specific.** "'Imaging agent' is not a modality the authority can type … (the requirement: one
  of antibody drug conjugate, bispecific antibody, t cell engager)".
- **Less useful:**
  - The indication rows repeat the same "What would pass the gate" clause for 24 programs. The useful part is the
    first sentence.
  - DA-3501's population note is hard to read: "'Childhood Gastric Carcinoma' read as 'Gastric Carcinoma' (the
    record states no population)" sits in a nested parenthetical.
  - "is not a name the NCIt authority can read" for CMG901's "Gastroesophageal Junction Cancer" (Screening sheet)
    would puzzle an analyst, since it plainly names the GEJ (N3).
- **Memo.** The "Investigate next" line is specific and uses no scope wording. Its grouping hides the
  different-disease group (N13).

## What I could not check

- (The equivalence harness was re-run; see the "Equivalence" section.)
- The full repository suite (not requested). The `.docx` memo was not opened.
- Workbooks and memos for the held-out landscapes; for those, only `screening.json` was read.
- Whether the unit tests were written before the code was tuned.
- External facts: that "PNH" means paroxysmal nocturnal hemoglobinuria to a C5 buyer, and that most gastric cancers
  are adenocarcinomas, are domain knowledge. The NCIt structure claims (stage concept under Gastric Carcinoma; index
  entries) were checked against the authority.
- Whether "Stage IV gastric cancer"-type names occur in real vendor landscapes the team uses. None occurs in the
  CLDN18.2 landscape (`grep -ic "stage i"` = 0).

## Reproduction

```
cd /home/djmann/.cache/u1_stage4 && . /home/djmann/projects/bve-b8/.venv/bin/activate
export TMPDIR=$HOME/.cache/dealscreen_suite PYTHONPATH=/home/djmann/.cache/u1_stage4/src
python -m pytest tests/dealscreen -q -p no:cacheprovider          # 922 passed, 5 warnings
python /tmp/claude-1000/u1rr/probes/p1.py    # N3 (spelling, multi-word sites)
python /tmp/claude-1000/u1rr/probes/p2.py    # N2 (restatements)
python /tmp/claude-1000/u1rr/probes/p3.py    # held-out indication sweep
python /tmp/claude-1000/u1rr/probes/p6.py    # N5 (non-site site words)
python /tmp/claude-1000/u1rr/probes/p7.py    # N6-N9 (targets, fictional and real reader)
python /tmp/claude-1000/u1rr/probes/p9.py    # N4, N10, J-a
python /tmp/claude-1000/u1rr/probes/p10.py   # N1 (stage concepts) and the ancestors of the stage concept
python3 /tmp/claude-1000/u1rr/science_diff.py <new screening.json> <reference screening.json>
python3 /tmp/claude-1000/u1rr/coverage.py <screening.json ...>
```

**Scratch workspaces** (copies; the originals were not modified):

| Workspace | Contents |
|---|---|
| `ws` | Fresh CLDN18.2 screen, export and memo |
| `xv/*` | Held-out workspaces, re-screened |
| `ws_gc`, `ws_mixed`, `ws_pnh`, `ws_empty` | Request variants |
| `ws_e2e2` | N1, N3 and J-a end to end |
| `ws_all` | N4 end to end |

## Equivalence

The reviewer re-ran the cycle-4 harness with the stage on the path. It used the wrapper
`u1r3/run_equiv.py`, with output to `/tmp/claude-1000/u1rr/equiv`; the tracked result file was not written. The
result: `byte_identical: true` and `fast_path: true` on all 4 cases (synthetic_200, real_v1, real_v2,
real_v1_with_cycle1_assertions). Saved at `/tmp/claude-1000/u1rr/equiv.json`. U1-3 is met on every check.
