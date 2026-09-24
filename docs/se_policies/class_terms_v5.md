# Class terms v5 — a class label is not an asset

Status: **PREREGISTERED** 2026-09-24. Parent commit: `0dfb18c`.
Follows `asset_qualification_evidence_subjects_v4.md` (kept; PASS_ON_V4_CHANGES).

Written and committed **before** any v5 code change. Costs in §4 were measured against the v4 live
artifact `/home/djmann/se_runs/mint4_on` and are declared here so they cannot be revised after
seeing the v5 result.

## 1. What this closes

v4 satisfied its six criteria on the changes it made, but the frozen criterion 2 — **zero non-assets
with a decisional PASS** — is not met: `CAR19` and `CART19` hold asset-level `human_poc` PASSes.
Neither is a specific therapeutic. `CART19` aggregates **33 trials across 14 companies**; those are
14 different constructs, not 14 sponsors of one molecule. The defect predates v4 and the bar is not
relaxed on that account.

This is the third invariant in the series, and like the other two it is about what a name *is*, not
about a threshold:

> **A class label denotes a set of assets. It cannot be a member of that set.**

v1–v2 asked *is this string a drug name?* v4 asked *is this record about this object?* v5 asks
*does this name denote one thing or a category?*

## 2. The rule

A canonical name is a **class term** when its entire content is exhausted by modality vocabulary,
target designations and grammatical filler — that is, when nothing in it individuates a molecule.

- **Modality vocabulary**: `CAR`, `CAR-T`, `CART`, `NK`, `TCR`, `TIL`, `BiTE`, `ADC`, `mAb`,
  `bsAb`/`bsAbs`, `bispecific`, `trispecific`, `antibody`/`antibodies`, `cell(s)`, `therapy`/
  `therapies`, `vaccine`, `degrader`, `ASO`, `siRNA`, `CRISPR`.
- **Target designations**: any symbol resolving in the ontology, plus a bare number `n` where
  `CD<n>` resolves in the ontology. This is what makes `CART19` a class term (`CD19`) while
  `CAR088` is not (`CD088` does not resolve). **The ontology is the authority — not a hand list of
  CD numbers, and not the target vocabulary of the current run.**
- **Filler**: `anti`, `dual`, `target(ed|ing)`, `specific`, `directed`, `autologous`, `allogeneic`,
  `humanized`, `human`, `murine`, `armored`, `redirected`, `positive`, `based`.

Anything left over individuates, and the name is an asset. `TAC01-CD19` keeps `TAC01`; `ABBV-383`
keeps `ABBV`; `tisagenlecleucel` is a molecule name. A **zero-padded** numeric (`0\d{2,}`) is read
as a sponsor serial and never as a target designation, which is what protects `CAR011`, `CAR066`,
`CAR088`.

### Disposition

Class terms are **retained as metadata and lose asset standing**:

1. Not canonical assets: off the default path, not eligible, not shortlisted as assets.
2. **No asset-level `human_poc`.** A class label cannot hold a decisional efficacy verdict.
3. Not deleted. They remain in the review population with an explicit reason, exactly like every
   other demotion since M18 — routing by support, never deletion.
4. Their trial and target edges are **not** discarded. A class term legitimately groups assets, and
   that grouping is the useful part; it simply is not itself an asset.

## 3. Why not the alternatives

- **Owner count.** Rejected: `pembrolizumab` also appears across many sponsors. Sponsor breadth
  describes a molecule's popularity, not its individuation.
- **A name blacklist.** Forbidden by standing constraint, and it would not generalize past this
  corpus — the whole point of M13–M17 was zero-shot behaviour.
- **Demoting anything whose name contains a target symbol.** Would take `TAC01-CD19` and the
  `FIT-(BCMA+CD19)-CAR-T Cells` family, which are real assets. Individuating residue is the
  discriminator, not target-symbol presence.

## 4. Declared cost

Measured on `mint4_on` (1,136 default-path assets) with the run's own target vocabulary, which
**lacks `CD20`, `CD22` and `CD138`** and therefore *under*counts:

- **35 default-path names classify as class terms**, of which **2 hold a `human_poc` PASS**
  (`CAR19`, `CART19`). Composition: `CAR-T`, `CAR-T cell(s)`, `CAR-T Therapy`, `CAR T-cell therapy`,
  `CD19 CAR-T` (and 14 further orthographic variants of "anti-CD19 CAR-T cells"), `CD19-CAR-NK`,
  `CD19-CAR-NK/T`, `CAR-CD19 T cell(s)`, `CAR-NK-CD19 Cells`, `Allogeneic/Autologous CD19 CAR-T
  cells`, `CAR19`, `CART19`. **Every one of the 35 is a category, not a molecule.** No real asset is
  among them.
- Under the ontology-backed rule required by §2, `CAR-20`, `CART22` and `CART-138` are expected to
  join them (`CD20`, `CD22`, `CD138` all resolve). They are likewise class labels. `TAC01` stays an
  asset on its `TAC01` residue. **Declared range: 35–38 demotions, 2 `human_poc` PASSes withdrawn.**
- **Declared genuine-asset cost: zero.** This is the first milestone in the series with no real
  asset priced in, which is itself a falsifiable claim: if the paired run demotes any name carrying
  individuating residue, that is a **FAIL**, not an accepted cost.

## 5. Acceptance bar

1. `CAR19` and `CART19` are off the default path and hold **no** `human_poc` PASS.
2. **Zero non-assets with a decisional PASS** — criterion 2 of the v4 bar, now met outright.
3. Every v4 frozen positive still survives with an unchanged `qualification_reason`, including
   `SYNCAR-001`, `HB2198`, `ABBV-383`, `ALLO-715`, `AMG 420` and `TAC01-CD19` if present.
4. No name carrying individuating residue is demoted. Zero real-asset loss, as declared in §4.
5. Human-PoC population falls by exactly the class terms that held one (expected 31 → 29) and by
   nothing else.
6. Every remaining default-path asset still carries a named `qualification_reason`; zero anonymous
   admissions.
7. Every demoted class term carries an explicit class-term reason in the review population — the
   demotion must be as auditable as an admission.

Validation is a **fresh paired same-day live acquisition**, `mint5_on` vs `mint5_off` at the v5
parent, on the unchanged v4 acceptance query. Sealed replay is not the adoption test.

## 6. Not to be done under v5

- No hand-written name blacklist.
- No weakening of target or `human_poc` rules — this milestone only *removes* PASSes.
- No threshold tuned after seeing the acceptance corpus.
- No change to v4, fragmentation, or the A3 symmetry rule.
- No ranking work. Ranking begins only after this bar and the A3 positive control both pass.
