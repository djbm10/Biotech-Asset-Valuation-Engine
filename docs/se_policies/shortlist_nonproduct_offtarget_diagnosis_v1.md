# SHORTLIST_NONPRODUCT_OFFTARGET_DIAGNOSIS v1 — why a TIGIT search shows honey and unrelated drugs

**Status:** DIAGNOSIS ONLY, 2026-10-11. No behaviour changed. Ranking was not touched.
**Precondition met first:** the untouched H16–H20 suite was frozen at `eaace55`
(`heldout_validation_suite_v4.md`) before any diagnostic data was read.
**Cases:**
- H2 and H4 (v1 runs at `40b7ec9`) and H11–H14 (v3 runs at `f0e90e6`). These are 120 top-20
  rows, labelled with the frozen blind labels (`labels_v1.json`, `labels_v3.json`; OFF_TARGET =
  WRONG_TARGET).
- H15 is excluded and recorded separately in `h15_extra_target_diagnosis_v1.md`.
- H11–H15 are diagnostic data from now on and can never count as generalization evidence.

**Artifacts** (`research/se_shortlist_diag/`, all read-only over the sealed runs):

| File | Contents |
|---|---|
| `extract_rows_v1.py` → `rows_v1.json` | Every field below, per row |
| `rows_v1_table.md` | Human-readable per-row appendix |
| `classify_v1.py` → `classified_v1.json` | Mechanical first-boundary classes; rules in the docstring, no name-specific logic |
| `counterfactual_v1.py` → `counterfactual_v1.json` | Authority coverage, indication false-FAIL population, ranking displacement |

Each row records:
- the frozen label;
- all six gate statuses;
- target assertions with their evidence sources;
- `construct_target_set` and compatibility facts;
- the authority drug id and its direct targets;
- the NCIt non-product type;
- the qualification reason;
- the entity link (trials, companies, targets);
- comparator, therapeutic and unknown observation counts;
- origin publishers;
- declared and authority modality and the match result;
- stage;
- the location of every reference product.

## 1. How a row reaches the top 20 (mechanism, from code)

1. **Candidate generation.** A name in a PubMed or AACR sentence becomes a provisional asset.
2. **Qualification.** `asset_qualification.qualification_reason` admits the name if
   `drug_name_shape.is_identity_bearing_drug_name` holds. This is the route
   **DIRECT_APPROVED_NAME**: ChEMBL lists the string as a molecule's own name. It decides
   alone, ahead of the comparator veto and ahead of the v6 NCIt non-product veto.
3. **Low-support routing** holds back names that do not qualify (9,949 / 396 / 453 / 2,650 /
   2,018 / 2,738 per query).
4. **Gates.** A row with no facts gets UNKNOWN on every requirement, which gives disposition
   UNRESOLVED. An UNRESOLVED row is shown. **Only a FAIL excludes.**
5. **Shortlist order** (`reporting/shortlist._rank_key`):
   - eligible first (no query has any eligible asset);
   - then modality match;
   - then the target decision (PASS before UNKNOWN);
   - then human PoC and stage;
   - then the name, alphabetically.

   Among all-UNKNOWN rows, nearly everything ties and the **order is alphabetical**. That is why
   H15/H2 run through "Abacavir, acetone, acipimox…".

## 2. The decisive finding: true products are excluded and junk is not

All **38/38** reference products across the six queries were **discovered**, so discovery
misses are zero. Of these, **33 are EXCLUDED**, and every one of the 33 fails **only**
`strategy.indication`. The five that are shown are Krazati (H2), the three TL1A products (H4)
and Bimzelx (H13).

| Query | References | Shortlisted | Excluded (indication FAIL only) | Absent |
|---|---|---|---|---|
| H2 | 9 | 1 | 8 | 0 |
| H4 | 3 | 3 | 0 | 0 |
| H11 | 6 | 0 | 6 | 0 |
| H12 | 7 | 0 (PiaSky, Veopoz, Ultomiris shown as trade-name rows; see §4 H) | 7 | 0 |
| H13 | 8 | 1 | 7 | 0 |
| H14 | 5 | 0 (isatuximab-irfc / SARCLISA shown) | 5 | 0 |

**Why they fail.** `ontology/indications.py` defines one concept, `B_CELL_LYMPHOMA`.
`compiler.residual_indications` turns any other disease phrase into word **literals**, and the
engine evaluates those with exact `IN` equality on the whole registry condition string.

The compiled requirements are:

| Query | Compiled indication literals |
|---|---|
| H11 | `["non-small","lung","cancer"]` |
| H12 | `["complement","inhibitors","paroxysmal","nocturnal","hemoglobinuria"]` |
| H2 | `["G12C","inhibitors","non-small","lung","cancer"]` |
| H15 | `["inhibitors","homozygous"]` |

No condition string ("Non Small Cell Lung Cancer", "Hidradenitis Suppurativa", "Multiple
Myeloma") equals one bare word. So **every asset that has any indication evidence FAILs**,
while an asset with no indication evidence is UNKNOWN and is shown. The gate penalises
evidence. It also takes in non-disease residual words (`inhibitors`, `G12C`, `complement`) as
indication literals.

Excluded assets failing only on indication, by target gate (`counterfactual_v1.json` M2):

| Query | Target PASS | Target UNKNOWN | PASS with a condition containing the query's disease words (crude, reported only) |
|---|---|---|---|
| H2 | 25 | 419 | 7 |
| H4 | 1 | 1 | 1 |
| H11 | 14 | 13 | 4 |
| H12 | 13 | 49 | 7 |
| H13 | 19 | 14 | 4 |
| H14 | 27 | 60 | 14 |

A target-PASS asset ranks above every target-UNKNOWN row of equal modality status. So these
are exactly the rows the UNKNOWN fill is standing in for.

## 3. Target layer: no false targets

- **C TARGET_FALSE_PASS: 0 / 120 rows.** Every target-PASS row is RELEVANT, a trade-name
  duplicate of a RELEVANT row, or `Alexion` (a ChEMBL synonym of eculizumab; see A).
- **E KNOWN_INCOMPATIBLE_NOT_FAILED: 0.** Every off-target row resolves to a ChEMBL drug with
  **no direct target edge**: 57/57 D rows are `resolved_no_edges`. The compatibility layer had
  nothing to read. Examples are benmelstobart, gremubamab and AFM11, which have no direct
  ChEMBL/Open Targets target, and carboplatin, whose target is not a protein.
- **Requiring target PASS is not safe.** 5 of the 15 RELEVANT top-20 rows are target UNKNOWN:
  afimkibart, duvakitug and tulisokibart (all of H4's hits) and gumokimab and netakimab (H13).
  New INNs often have no authority edge yet.

## 4. First-failure classification of every bad top-20 row

There are 102 bad rows: 120 total, less 15 RELEVANT and 3 UNVERIFIABLE.

| Class | H2 | H4 | H11 | H12 | H13 | H14 | Total |
|---|---|---|---|---|---|---|---|
| A NON_PRODUCT_GENERATION | 10 | 10 | 3 | 6 | 5 | 6 | **40** |
| B QUALIFICATION_MISS | 1 | 0 | 0 | 0 | 0 | 0 | **1** |
| C TARGET_FALSE_PASS | 0 | 0 | 0 | 0 | 0 | 0 | **0** |
| D TARGET_UNKNOWN_FILL | 7 | 7 | 17 | 6 | 9 | 11 | **57** |
| E TARGET_KNOWN_INCOMPATIBLE | 0 | 0 | 0 | 0 | 0 | 0 | **0** |
| F RANKING_ERROR (relevant rows displaced) | 0 | 0 | 0 | 0 | 1 | 2 | **3** (not bad rows) |
| G SOURCE_COVERAGE (reference absent) | 0 | 0 | 0 | 0 | 0 | 0 | **0** |
| H IDENTITY / DUPLICATE | 0 | 0 | 0 | 3 | 0 | 1 | **4** |
| *Upstream cause of the fill: reference excluded by indication false-FAIL* | 8 | 0 | 6 | 7 | 7 | 5 | **33** |

**A — 40 rows** (bromide, eosin, hematoxylin, paraffin, vehicle, honey, ginger, amino acids,
carbon monoxide, …):
- All 40 qualify by **DIRECT_APPROVED_NAME**. ChEMBL carries these substances as molecules.
- 40/40 are provisional, with 0 trials, 0 companies and 0 targets, and come only from
  PubMed/AACR prose.
- `Alexion` (H12 #1) is a company name. It qualifies as an ENTITY_CORROBORATED_SYNONYM of
  eculizumab and carries eculizumab's correct C5 target. Its boundary is generation (a sponsor
  name minted as an asset), not the target.

**B — 1 row:** `methane` (H2). NCIt types it as a non-product, but the v6 veto sits *below*
the ontology route, so DIRECT_APPROVED_NAME returned first.

**D — 57 rows:** real drugs with no evidence for the requested target (chemotherapies,
antibiotics, antivirals, off-target antibodies). They surface because UNKNOWN rows fill the
list once the PASS supply is exhausted, and §2 shows that the PASS supply was largely
excluded upstream.

**F — 3 relevant rows displaced:**
- Bimzelx (H13 #14), isatuximab-irfc (H14 #12) and SARCLISA (H14 #13) are target PASS but
  have modality_match UNKNOWN.
- Modality precedence sits ahead of the target decision in the rank key, so they rank below
  modality-MATCH, target-UNKNOWN off-target antibodies.
- Recorded only. Ranking is frozen.

**H — 4 rows:** trade name and suffixed INN shown as separate assets (Izervay/ARC1905,
PiaSky/crovalimab-akkz, Veopoz/pozelimab-bbfg, SARCLISA/isatuximab-irfc).

**Discriminator check (for the A milestone).** An entity link does *not* separate junk from
real products. 0/97 A/D rows have one, but neither do 5/15 RELEVANT rows (all of H4's hits and
2 in H13). A non-product rule keyed on "no trial/company" would delete the TL1A answers.

## 5. Answer and recommended milestones (separate; none combined)

**Largest contributor of bad top-20 rows:** D TARGET_UNKNOWN_FILL (57/102), then A
NON_PRODUCT_GENERATION (40/102).

These are both *fill*, and the fill exists because the gate excludes the products that should
occupy those slots. The upstream cause is the **indication-gate false FAIL**:
- it removes 33/38 reference products;
- it removes 99 target-PASS assets in total across the six queries;
- 37 of those carry a condition naming the queried disease.

**Highest expected precision benefit with the lowest false-negative risk:**
**INDICATION_REQUIREMENT_SEMANTICS v1.**
- Disease phrases compile to concepts matched by authority against registry conditions,
  generalizing the adopted B-cell-lymphoma mechanism. Non-disease residual words
  (`inhibitors`, `G12C`, `complement`) are no longer indication literals.
- An unmatched phrase must produce UNKNOWN rather than FAIL.
- It can only *remove* FAILs, so its false-negative risk is ≈0 by construction. The risk it
  does carry is admitting assets developed only in other indications. That is the acceptance
  criterion to preregister.
- Expected effect: target-PASS products move above all target-UNKNOWN fill. Recall@all is
  directly restored, because the 33 excluded references fail only this requirement.
- It cannot by itself push A/D rows out of queries with few PASS products (H4, H11).

Then, in this order, each as its own preregistered milestone:

1. **NONPRODUCT_QUALIFICATION v1 (A + B, 41 rows).**
   - The DIRECT_APPROVED_NAME route admits ChEMBL substance records (salts, stains, solvents,
     foods, "vehicle").
   - Needs an authority discriminator: e.g. ChEMBL molecule type/structure class or NCIt
     semantic type ordered *above* the ontology route.
   - It must not use entity links (they would delete the H4 answers) or name lists.
   - Medium false-negative risk. Requires a real-drug control set.
2. **TARGET_UNKNOWN_SHORTLIST_ROUTING v1 (D, 57 rows).**
   - Re-measure only after the indication fix, since much of D is displacement.
   - Requiring PASS would cost 5/15 RELEVANT rows, so the candidate design is a separate
     "target unconfirmed" section rather than removal.
3. **TARGET_AUTHORITY_COVERAGE v1.**
   - All 57 D rows and 5 relevant UNKNOWN rows lack direct authority edges.
   - Source coverage of target evidence for new INNs (e.g. NCIt definitions, WHO INN
     target statements).
4. **TRADE_NAME_IDENTITY v1 (H, 4 rows).**
   - Trade name vs suffixed INN not merged.
   - Also the `Alexion`-as-synonym case.
5. **Ranking (F, 3 rows).** Modality-before-target precedence. Record only until the ranking
   arc reopens.
6. **H15_EXTRA_TARGET_DIAGNOSIS v1.** Separate; see its own doc.

Validation for each fix is the untouched H16–H20 suite (`eaace55`), with H6–H10 as secondary.
H1–H5 and H11–H15 are diagnostic only.
