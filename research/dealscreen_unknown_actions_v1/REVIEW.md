# Cycle U1 adversarial review: a concrete next action for every tool UNKNOWN

INTERNAL DEVELOPMENT. This is an AI-simulated adversarial review of code and outputs. It is not human or
independent validation.

Reviewed: the staged copy at `/home/djmann/.cache/u1_stage` (R1 revision 4 plus U1), against
`ACCEPTANCE.md` (frozen criteria plus revision note) and `MEASUREMENT.md`. Every number below was recomputed by
the reviewer unless marked "read, not re-run".

## Verdict in one paragraph

U1 changes no science. That claim holds on every check the reviewer ran. Coverage is complete on the five measured
landscapes, and on CLDN18.2 every action the reviewer checked is true to the record. U1-7 is **not met**. With
held-out inputs the diagnostic misstates the NCIt authority or the record in several ways. The worst case: when
the buyer's requested indication is not one NCIt concept ("gastric cancer", "generalized myasthenia gravis",
"diffuse large b-cell lymphoma"), a record that names exactly the requested disease is told it is "neither a
requested indication nor a subtype of one". The deciding fact the action names then cannot be asserted, or cannot
pass the gate. Changing only the CLDN18.2 buyer's wording to `indications: [gastric cancer]` reproduces this on the
real landscape: 17 programs are classed DIFFERENT_DISEASE. Two more defects can push an analyst towards the wrong
programs: NCIt "site words" that are not sites ("hodgkin lymphoma", "diabetes", "small cell", "unspecified",
"head"), and an acronym clean-up that deletes the subtype ("Lung Cancer (NSCLC)" is called broader than a
small-cell request).

## Verdict per criterion

| AC | Verdict | Evidence |
|---|---|---|
| U1-1 coverage | **Met as measured; partly met in general** | CLDN18.2: 38 UNKNOWN decisions on non-excluded programs, 38 with a diagnostic, 0 diagnostics on excluded programs or non-UNKNOWN decisions (recomputed from a fresh `screen` of a copy of `cldn_ws4`). FcRn v1 28/28, FcRn v2 28/28, C5 held-out 28/28, synthetic 20/20 (recomputed from `~/.cache/u1/xv4/*/screening.json`). Every action names the value as written or "nothing on record". All 8 CLDN18.2 NO_RECORD statements match empty cells in `inputs/landscape.csv`. Exception: with an unresolvable requested indication (D1), the "fact that decides the gate" cannot decide it. Gates with no assertable field always say "Nothing on record." whatever the record holds (D10, latent). |
| U1-2 authorities only, no landscape words | **Met (letter); one non-authority heuristic** | `grep -n -i -E "gastr\|claudin\|cldn\|gej\|stomach\|fcrn\|myasthenia\|pd-1\|zolbet"` on `indication_relations.py` and `diagnostics.py`: 4 hits, all in docstrings or comments (`indication_relations.py` lines 12, 68 and 85; `diagnostics.py` line 96). The word lists in the logic (`_BASKET_HEADS` and similar) hold generic words (tumor, cancer, carcinoma), not landscape words. `workbook.py`, `memo.py`, `screening.py`, `facts.py`: no hits in U1 logic. However, SOURCE_NAMES_OTHER_TARGETS for strings the target authority cannot read ("PD-1" reads as `None` in the authority) comes from a symbol-shape regex (`_SYMBOL_SHAPE`), not from the authority. This is the source of D4. |
| U1-3 no change to science | **Met** | Three checks. (1) `cldn_ws4/screening.json` vs `baseline/screening_R1.json`: 0 of 62 programs differ on disposition, rank, decisions, machine_recommendation, transaction or transaction_rank; funnel, ranking rule and rights_import_issues are equal; the only differing key is `unknown_diagnostics`. (2) A/B in-process on a scratch copy with `screening.diagnose` patched to return `{}`: results identical apart from `unknown_diagnostics`. (3) Cross-version: 0 of 312 programs differ from `xv4/science.json` on decisions, disposition, machine_recommendation, rank and tier (`transaction.tier`). Only display code reads `unknown_diagnostics` (workbook lines 234 and 473, memo line 300). Equivalence: `~/.cache/u1/equiv4.json` reports byte-identical on 4 of 4 (read, not re-run). |
| U1-4 held-back tests | **Met as written; insufficient in substance** | `tests/dealscreen/test_unknown_actions.py`: 21 functions and 47 cases, all passing. Every class and all four named adversarial cases are covered. DealScreen suite (`python -m pytest tests/dealscreen -q -p no:cacheprovider`, re-run at the end of the review): 559 passed, 5 warnings. The held-out probes below find whole defect families that no test exercises: unresolved requests, non-site site words, subtype acronyms, exclusion abbreviations, placeholder targets and the isoform regex. |
| U1-5 surfaces | **Met, with notes** | Regenerated from the scratch copy: the memo is identical to `after/memo_u1.md` apart from timestamps; the Screening and Diligence sheets are cell-identical to `after/u1_cldn18.xlsx`. Diligence has 38 GATE_UNKNOWN rows. "Next action" holds the DealScreen action followed by "(S&E: …)". "Confidence limitations" starts with "Record class … (DealScreen; describes the record, which can be wrong)". The Screening sheet's last column gives the class per gate and each name's class. The memo lists 15 single-gate programs. Across all 142 diagnostics in the five landscapes there is no scope or recommendation wording (searched for in/out of scope, exclude, eligible, recommend, prioriti/deprioriti, pursue, promising, should, attractive, relevant). Notes are in D12 and in the memo remark under D9. |
| U1-6 per program vs reference | **Partly met** | Reproduced: 15 reference-IN programs are UNRESOLVED, and LCB02A is EXCLUDED with no diagnostic. 0 gastric or GEJ names are classed DIFFERENT_DISEASE. 11 of 11 basket actions name the requested indications. All 3 PD-1 partner rows name the other targets. SOT102 is reported. **Not reported:** DA-3501 (reference IN) also has an action that partly points away. It says NCIt reads its "Gastric (Stomach) Cancer" as "Childhood Gastric Carcinoma, not a requested concept or a subtype" (D7). `measurement.json` only tests whether a gastric name has class DIFFERENT_DISEASE, so this case was missed. |
| U1-7 adversarial review | **Not met** | D1–D6 are actions that misstate the authority or the record on held-out inputs. D1 reverses an exact match across a whole landscape from a natural buyer phrasing. On the CLDN18.2 outputs as shipped, the reviewer found no false statement, but one misleading statement (D7), one weak lead name (D9) and one undisclosed spec deviation (D13). There are no hidden UNKNOWNs among non-excluded programs and no change to science. |

## Defects, ranked by how much they could mislead an analyst

Each item gives a minimal input, the output observed (copied from runs), and the expected output.
`dg` = `bve.dealscreen.diagnostics`, `ir` = `bve.dealscreen.indication_relations`.

### D1 (critical). An unresolvable requested indication makes every record, even an exact match, a "different disease"

- **Input:** `dg.indication_diagnostic(["Gastric Cancer"], ["gastric cancer"])`.
  **Wrong output:** DIFFERENT_DISEASE: "'Gastric Cancer' reads as Gastric Carcinoma; Malignant Gastric Neoplasm
  (NCIt), neither a requested indication nor a subtype of one. What decides the gate: a cited source naming gastric
  cancer (or a subtype) for this program; …"
- Same result for `(["Generalized Myasthenia Gravis"], ["generalized myasthenia gravis"])`. Output: "'Generalized
  Myasthenia Gravis' reads as Myasthenia Gravis (NCIt) once generalized, neither a requested indication nor a
  subtype of one".
- Same result for `(["Diffuse Large B-Cell Lymphoma"], ["diffuse large b-cell lymphoma"])` and
  `(["Glioblastoma"], ["glioblastoma"])`.
- Requests that `disease_id` does not resolve, among those the reviewer tried:
  - several codes in the name index: "gastric cancer" (2), "diffuse large b-cell lymphoma" (3: adult, childhood,
    plain), "glioblastoma" (3), "hodgkin lymphoma" (3), "immune thrombocytopenia" (2), "osteosarcoma" (2);
  - no entry in the name index: "generalized myasthenia gravis", "alzheimer disease", "obesity", "hidradenitis
    suppurativa" and "INDICATION:B_CELL_LYMPHOMA".
- **End to end:** a copy of `cldn_ws4` with only `indications: [gastric cancer]` changed, then re-screened. Every
  "Gastric Cancer" name is classed DIFFERENT_DISEASE; program classes are BASKET 19, DIFFERENT_DISEASE 17,
  UNREADABLE 3. A copy of `xv4/fcrn_v1` with `indications: [generalized myasthenia gravis]`: 18 of 18 indication
  diagnostics are DIFFERENT_DISEASE.
- **The named deciding fact cannot decide the gate.** `FactBuilder.readable("indication", "gastric cancer")` is
  False, so the assertion is refused. "generalized myasthenia gravis" can be asserted, but
  `compatibility("generalized myasthenia gravis", "Myasthenia Gravis")` is None, so it can never pass.
- **Cause:** `ir.requested_codes` silently drops any request that `disease_id` does not resolve to exactly one code.
  `ir.relation` then compares against an empty or partial set and returns "not requested" for everything. The S&E
  gate is also UNKNOWN for every program in this case (pre-existing, not U1). U1 turns "cannot be established" into
  "is not requested".
- **Expected:** if any requested indication is not exactly one NCIt concept, make no relation claim against the
  partial set. Emit a distinct class instead, for example REQUEST_NOT_RESOLVED: "The requested indication 'gastric
  cancer' is not one NCIt concept (the authority reads it as Gastric Carcinoma; Malignant Gastric Neoplasm); no
  record can pass this gate until the request names one concept." Better still, refuse such a buyer spec at import.

### D2 (high). "Site words" that are not sites override the authority's different-disease reading

- `site_phrases` takes every word of every ancestor under an NCIt "… by Site" node, minus words of non-site
  ancestors. For haematology, endocrine and non-neoplastic requests, almost every ancestor sits under
  "Disorder by Site" or "Neoplasm by Site". Disease names therefore become site words. A "non-" prefix is ignored
  when phrases are built, and "head and neck" splits on "and".
- Site phrases computed by the reviewer: follicular lymphoma {"hodgkin lymphoma", "hodgkin s lymphoma"}; COPD
  {"unspecified"}; type 2 diabetes {"diabetes"}; haemophilia A {"hemophilia"}; small cell lung carcinoma
  {"small cell", "oat cell", "small cell neuroendocrine", …}; CLL {"b cell", "lymphocytic leukemia", …}; HNSCC
  {"head", "neck"}; neuroendocrine carcinoma {"neuroendocrine"}.
- Each row below is classed NAMES_REQUESTED_SITE ("names a requested site, not a requested NCIt concept"), and in
  most the action itself reports that NCIt reads the name as a non-requested concept.

| Request | Record name | Action says |
|---|---|---|
| follicular lymphoma | "Hodgkin Lymphoma" | "names hodgkin lymphoma" |
| follicular lymphoma | "Classic Hodgkin Lymphoma" | "names hodgkin lymphoma" |
| type 2 diabetes mellitus | "Type 1 Diabetes Mellitus" | "names diabetes" |
| type 2 diabetes mellitus | "Diabetes Insipidus" | "names diabetes" |
| hemophilia a | "Hemophilia B" | "names hemophilia" |
| small cell lung carcinoma | "Bladder Small Cell Carcinoma" | "names small cell" (histology, which the acceptance excludes) |
| chronic lymphocytic leukemia | "B-Cell Acute Lymphoblastic Leukemia" | "names b cell" |
| chronic lymphocytic leukemia | "Acute Lymphocytic Leukemia" | "names lymphocytic leukemia" |
| chronic obstructive pulmonary disease | "Asthma, unspecified" | "names unspecified" |
| head and neck squamous cell carcinoma | "Adenocarcinoma of the Head of the Pancreas" | "names head" |
| head and neck squamous cell carcinoma | "Bladder Neck Cancer" | "names neck" |
| neuroendocrine carcinoma | "Pancreatic Neuroendocrine Tumor" | "names neuroendocrine" |

- **Expected:** DIFFERENT_DISEASE for all of these.
- **Fix direction:** site words should come only from site-named nodes (anatomic structure, not "Lymphoma",
  "Diabetes Mellitus" or a "… Carcinoma"). Apply the "non" exclusion when phrases are built, and keep multi-word
  sites whole.
- CLDN18.2 is not affected (its phrases are gastric, stomach, gastroesophageal junction and esophagogastric
  junction). Every other therapy area is exposed.

### D3 (high). The acronym clean-up deletes a subtype or site, and AMBIGUOUS sentences hide that it ran

`_lookup` removes any parenthetical of 2–6 letters, not only an acronym of the adjacent words. The classes that
result rank above BASKET and DIFFERENT. Each case below is a record naming a different disease:

| Request | Record name | Class | Action says |
|---|---|---|---|
| gastric adenocarcinoma + GEJ adenocarcinoma | "Adenocarcinoma (PDAC)" | AMBIGUOUS_NAME | lists "Gastric Adenocarcinoma (requested or a subtype)" |
| gastric adenocarcinoma + GEJ adenocarcinoma | "Gastrointestinal Cancer (CRC)" | BROADER_THAN_REQUESTED | "reads as Malignant Digestive System Neoplasm (NCIt) once acronym removed, broader than requested" |
| small cell lung carcinoma | "Lung Cancer (NSCLC)" | AMBIGUOUS_NAME_ALL_BROADER | "matches several NCIt concepts, all broader than requested: Lung Carcinoma; Malignant Lung Neoplasm" (no clean-up shown) |
| chronic lymphocytic leukemia | "Leukemia (AML)" | AMBIGUOUS_NAME | "Leukemia (broader than requested)" |
| follicular lymphoma | "Lymphoma (DLBCL)" | AMBIGUOUS_NAME | "Lymphoma (broader than requested)" |
| gastric adenocarcinoma + GEJ adenocarcinoma | "Carcinoma (breast)" | BROADER_THAN_REQUESTED | "reads as Carcinoma (NCIt) once acronym removed" ("breast" is not an acronym) |
| gastric adenocarcinoma + GEJ adenocarcinoma | "Tumor (brain)" | BROADER_THAN_REQUESTED | "reads as Neoplasm (NCIt) once acronym removed" |

- The acceptance describes this clean-up only for READS_AS_REQUESTED. For BROADER it allows "directly or by a
  disclosed DealScreen reading", and this clean-up is not one of those readings.
- **Expected:** drop a parenthetical only when its letters are the initials of the adjacent words ("Gastroesophageal
  Junction (GEJ)"). Otherwise do not strip it; the name is UNREADABLE or keeps its true class. Show the clean-up in
  every sentence, including AMBIGUOUS_NAME and AMBIGUOUS_NAME_ALL_BROADER.

### D4 (medium-high). Target: a variant spelling of the required target, or a placeholder, is called "other targets"

Fictional request: `TargetTerm(canonical_id="QRX7", label="Quorin 7.2")`.

| Input | Wrong output | Expected |
|---|---|---|
| "QRX 7.2" | SOURCE_NAMES_OTHER_TARGETS: "The record names QRX 7.2; none is QRX7 (Quorin 7.2)." | The required target written differently |
| "Undisclosed Target" | "The record names Undisclosed Target; none is …" | UNREADABLE: names no target |
| "PROPRIETARY" | "The record names PROPRIETARY; none is …" | UNREADABLE |
| "Not Specified" | "The record names Not Specified; none is …" | UNREADABLE |
| "Novel Target" | "The record names Novel Target; none is …" | UNREADABLE |
| "TAA" | "The record names TAA; none is …" | Unknown antigen; "none is" not supported |

- With the real CLDN18.2 reader (built from a scratch copy of the workspace), "CLDN 18.2", "CLDN18A2" and "Claudin 18
  isoform A2" each read as `None`. Each gives "The record names <value>; none is CLDN18 (Claudin 18.2).", for
  example "The record names CLDN 18.2; none is CLDN18 (Claudin 18.2).". The gate reads none of them, so the program
  stays UNRESOLVED with an action pointing away. "CONFIDENTIAL" gives the same wording with the real reader.
  Whether "CLDN18A2" is a recognised alternative name for the isoform is the reviewer's domain knowledge, not
  checked against an authority.
- **Cause:** `_SYMBOL_SHAPE` (any digit, or two capital letters) treats a string as a named target. "None is X"
  comes from a failed string match, not from the authority.
- **Expected:** list parts the target authority does not read as "not read as a target", never as other targets.
  Assert "none is X" only for parts the authority reads as a different id.

### D5 (medium). Target: another isoform in pair notation is read as the required target; negations count as naming it

- "QRX7.1xZPL4" (and "CLDN18.1xCD3" with the real request and reader) gives SOURCE_NAMES_REQUIRED_TARGET:
  "'QRX7.1xZPL4' names QRX7 (Quorin 7.2), but no target set was built from it; not read as a target:
  'QRX7.1xZPL4'.". The same sentence says the value names the required target and that it is not read as a target.
- **Cause:** the symbol pattern `QRX7(?:\s*\.\s*(?P<iso>\d+))?(?![A-Za-z0-9])` backtracks. It matches "QRX7"
  without the isoform group, because the "." after it is not alphanumeric.
- The same input with spaces, "QRX7.1 x ZPL4" (and "CLDN18.1 x CD3"), is correctly SOURCE_NAMES_OTHER_TARGETS.
  "QRX7.2xZPL4" is REQUIRED only by the same accident.
- "not QRX7.2", "QRX7.2-negative" and "formerly QRX7.2, now ZPL4" all give SOURCE_NAMES_REQUIRED_TARGET.
- **Expected:** SOURCE_NAMES_OTHER_TARGETS for another isoform. One way: add a `(?!\s*\.\s*\d)` guard at the end of
  the symbol pattern, so a bare symbol cannot match when an isoform suffix follows. Also split pair notation ("x")
  before matching, so that "QRX7.2xZPL4" still names the required target for a stated reason. Negated or former
  targets should not count as naming the required target.

### D6 (medium). Exclusion handling: common forms are missed, and "not" over-truncates

- Each of these gives NAMES_REQUESTED_SITE "'…' names gastric but is not a requested NCIt concept", although every
  one excludes gastric:
  - "Solid tumors excl. gastric"
  - "Solid tumours (gastric cancer excluded)"
  - "Solid tumors, no gastric"
  - "Solid tumors (ex-gastric)"
  - "Solid tumors w/o gastric"
  - "Solid tumours apart from gastric"
  - "Solid tumors besides gastric"
- The opposite error: "not" anywhere cuts the rest of the name. "HER2-negative, not previously treated gastric
  cancer" and "Unresectable (not amenable to surgery) gastric cancer" both give UNREADABLE, the lowest class.
- **Expected:** treat "excl.", post-positive "excluded", "no", "ex-", "w/o", "apart from" and "besides" as
  exclusions. Scope "not" to the phrase that follows it.

### D7 (medium). Name-index artefacts presented as "NCIt reads it as …" (affects one CLDN18.2 output)

- **DA-3501** (reference IN, rank 14): "'Gastric (Stomach) Cancer' names gastric and stomach but is not a requested
  NCIt concept (NCIt reads it as Childhood Gastric Carcinoma, not a requested concept or a subtype)". The authority's
  only entry for "gastric stomach cancer" is C118813 Childhood Gastric Carcinoma.
- 47 index names with no population word ("childhood", "pediatric") map only to a Childhood concept. Some are
  paediatric by definition, for example "acute lymphoblastic leukemia cns1". Others carry no paediatric sense, for
  example "colorectal colon or rectal cancer" maps only to C118808 Childhood Colorectal Carcinoma.
- A bare "Adenocarcinoma" gives AMBIGUOUS_NAME listing "Gastric Adenocarcinoma (requested or a subtype)". The index
  maps "adenocarcinoma" to 6 concepts, including Lung, Bile Duct, Cervical and Gastric Adenocarcinoma.
- Both outputs are faithful to the index and consistent with the gate. Read by an analyst, though, they say "this
  program is paediatric" or "this record may be gastric".
- **Expected:** when one reading's label equals the name, prefer it (Adenocarcinoma, so BROADER). Mark
  population-specific readings (Childhood/Adult) that the record did not state as artefacts of the index. Report
  DA-3501 under U1-6.

### D8 (low-medium). Understatements: requested sites written another way are UNREADABLE

- "GEJ adenocarcinoma", "GEJ Cancer", "Gastro-oesophageal junction adenocarcinoma" (the buyer statement's own
  spelling) and "Oesophagogastric adenocarcinoma" all give UNREADABLE. "gej" is a name of the requested concept
  ("adenocarcinoma gej") but not of a by-site ancestor, so it is not a site word.
- Biomarker-defined baskets ("CLDN18.2-positive Solid Tumors", "HER2-positive Solid Tumors", "NTRK fusion-positive
  solid tumors") give UNREADABLE, not BASKET. The memo would group them under "no name the NCIt authority reads".
- Both are consistent with the frozen definitions. They place records that name the request in the lowest class.

### D9 (low). The lead name is chosen alphabetically, not by specificity

- EO-3021's action leads with "'Digestive System Neoplasm' … broader than requested (and 4 other name(s) on
  record)". Its record lists "Stomach Neoplasm" first, which is also BROADER and is the more informative name.
  Names are sorted alphabetically before the lead is chosen.
- Memo (related): "2 more" hides the two single-member groups, SOT102 (different disease) and Givastomig (all
  broader). This is bounded and disclosed, but the one reference-IN program flagged as pointing away is among the
  hidden.

### D10 (low, latent). "Nothing on record." for gates with no assertable field

- `diagnose` on IBI343 (14 claim fields) with UNKNOWN `identity.distinct_asset`, `evidence.human_poc` or
  `evidence.evaluable_patients` gives "Nothing on record. S&E: …".
- `values` is always empty when the field is None, so the statement is never checked. No measured buyer uses these
  gates.
- **Expected:** "DealScreen maps no field to this fact" rather than a claim about the record.

### D11 (low). Wording errors in the public functions (unreachable through `screen`)

- READS_AS_REQUESTED with no clean-up still says "a clean-up the gate does not apply". Examples: "'STAD' reads as
  Gastric Adenocarcinoma (NCIt), a clean-up the gate does not apply", and "Ulcerative Colitis" against an IBD
  request.
- Readings that come from DealScreen's own `indication_readings`, which the gate does apply, are labelled the same
  way. Example against "myasthenia gravis": "'AChR+ generalized myasthenia gravis' reads as Myasthenia Gravis (NCIt)
  once biomarker subset 'AChR+'; qualifiers ['generalized'], a clean-up the gate does not apply."
- Steps render as "once generalized" and "qualifiers ['generalized']" (a Python list repr), as in the sentence
  above.
- Through `screen`, these names PASS the gate, so no shipped output is affected. The functions are exported and
  tested directly, though.

### D12 (low). The way to decide the gate is over-promised

- "…, or reject a wrong claim" reads as a second way to decide the gate. For a single, non-conflicting claim,
  rejecting it leaves NO_RECORD and the gate stays UNKNOWN.
- The memo's "one cited fact … would decide each" holds for the indication gate only when the fact is positive; the
  gate never FAILs. The per-program action states this correctly ("a cited source naming …").

### D13 (spec deviation, undisclosed)

- An ambiguous name whose readings are all "not requested" ("Pancreatic Cancer" reads as Pancreatic Carcinoma and
  Malignant Pancreatic Neoplasm) is DIFFERENT_DISEASE in the code. The frozen definition makes it AMBIGUOUS_NAME
  ("several concepts, but not all of them are broader"). It affects 2 CLDN18.2 programs: ANO31905 and SOT102.
- The code's choice reads better, but the revision note discloses only OVERLAPS_REQUESTED.
- The `_lookup` acronym/qualifier clean-up also feeds BROADER, AMBIGUOUS and DIFFERENT classes beyond the spec
  (see D3).

## Judgement calls I disagree with (labelled as such)

- **J1 (judgement). NAMES_REQUESTED_SITE outranks a resolved authority reading.** When NCIt resolves a name to one
  concept that is neither requested, broader nor overlapping, the class is still NAMES_REQUESTED_SITE, the second
  highest, above BROADER. Examples for the gastric request: "Gastric Ulcer", "Gastric GIST", "Gastric MALT Lymphoma"
  and "Gastric Squamous Cell Carcinoma". Others: "Liver metastases" for HCC, "Acute Kidney Injury" for CKD. The
  parenthetical is honest, but the Screening sheet, memo summary and class all say "names a requested site". I
  would class resolved-different concepts DIFFERENT_DISEASE ("same site" noted) and keep NAMES_REQUESTED_SITE for
  names the authority cannot read. Meanwhile "Gastritis" is DIFFERENT_DISEASE, so the rule is lexical.
- **J2 (judgement). Site words ignore the word's role.** Metastatic site: "Colorectal cancer with liver metastases"
  and "Uveal melanoma metastatic to the liver" name liver for an HCC request. Histologic type: "Gastric-type
  endocervical adenocarcinoma" and "Intraductal papillary mucinous neoplasm, gastric type". Complication: "Gastric
  Outlet Obstruction". All give NAMES_REQUESTED_SITE.
- **J3 (judgement). Excluded programs get nothing.** On CLDN18.2, 17 UNKNOWN decisions on 16 excluded programs get
  no diagnostic; MEASUREMENT names only LCB02A. This is acceptable by design, but stating the total would be
  clearer. The Diligence sheet omits excluded programs entirely, which predates U1.
- **J4 (judgement). "none is X" from string matching.** For targets the authority cannot read ("PD-1"), the action
  should say "not read by the target authority" next to the name. U1-6 still asks for the other targets to be named.

## What I could not check

- I did not re-run the cycle-4 equivalence harness; I read `~/.cache/u1/equiv4.json`. I did not run the full
  repository suite, as instructed.
- I could not verify that the unit tests were held back (written before the code was tuned). I can only say they
  pass and cover the named cases.
- I did not open the `.docx` memo or the FcRn, C5 and synthetic workbooks and memos. For those landscapes I read
  only `screening.json`.
- I did not check the reference calls' correctness or any external fact. "CLDN18A2" as an isoform name (D4) is
  domain knowledge, not checked.
- S&E code was read only where U1 depends on it: the indication gate, `indication_compatibility` and
  `ontology.indications`.

## Reproduction

```
cd /home/djmann/.cache/u1_stage && . /home/djmann/projects/bve-b8/.venv/bin/activate
export PYTHONPATH=$PWD/src TMPDIR=$HOME/.cache/dealscreen_suite
python -c "import bve; print(bve.__file__)"    # /home/djmann/.cache/u1_stage/src/bve/__init__.py
python -m pytest tests/dealscreen -q -p no:cacheprovider    # 559 passed, 5 warnings
python -c "from bve.dealscreen import diagnostics as dg; print(dg.indication_diagnostic(['Gastric Cancer'], ['gastric cancer'])['action'])"
python -c "from bve.dealscreen import diagnostics as dg; print(dg.indication_diagnostic(['Hodgkin Lymphoma'], ['follicular lymphoma'])['action'])"
python -c "from bve.dealscreen import diagnostics as dg; print(dg.indication_diagnostic(['Lung Cancer (NSCLC)'], ['small cell lung carcinoma'])['action'])"
```

Scratch workspaces (copies; originals untouched):
- `/tmp/claude-1000/u1rev/ws`: re-screen, memo and workbook regeneration.
- `/tmp/claude-1000/u1rev/ws_ab`: A/B with diagnostics disabled.
- `/tmp/claude-1000/u1rev/ws_gc`: buyer request "gastric cancer".
- `/tmp/claude-1000/u1rev/fcrn_gmg`: buyer request "generalized myasthenia gravis".

The reviewer re-checked every quoted output just before finishing, with these scripts. They are outside the
repository and modify nothing. Run each with the stage's `src` first on the path.
- `/tmp/claude-1000/u1rev/verify_claims.py`: indication defects D1–D3, D6–D8, D11, D13 and J1–J2.
- `/tmp/claude-1000/u1rev/verify_targets.py`: target defects D4 and D5, with a fictional request and the real
  reader.
- `/tmp/claude-1000/u1rev/verify_d1.py`: D1 end to end on `ws_gc` and `fcrn_gmg`.
- `/tmp/claude-1000/u1rev/verify_cldn.py`: the per-program CLDN18.2 outputs cited for U1-1, U1-6, D7, D9 and D13.

## Single highest-value fix

D1. Never compute an indication relation against a request set with an unresolved member. In
`ir.requested_codes` and `dg.indication_diagnostic`, detect any requested indication that `disease_id` does not
resolve to exactly one concept. For it, emit one honest class that says the request is not one NCIt concept and
that no record can pass the gate until it is restated. Add tests for "gastric cancer", "generalized myasthenia
gravis" and "diffuse large b-cell lymphoma" requests. Ideally, also reject such a buyer spec at import. This fix is
small. Without it, a natural buyer phrasing turns every exact match in a landscape into "neither a requested
indication nor a subtype of one".
