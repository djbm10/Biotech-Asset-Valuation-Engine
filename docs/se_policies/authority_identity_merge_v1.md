# Authority identity merge v1 — two registered names, one drug

Status: **PREREGISTERED** 2026-09-28. Parent commit: `8a7764d`.
Milestone: the identity-merge milestone logged in `ranking_lexicographic_v1.md` (KTE-C19 is a
DUPLICATE of axi-cel). Ranking v1 is not changed or tuned by this document.

Written and committed **before** any code change. The acceptance criteria in §5 are fixed here and
are not revised after seeing the result.

## 1. What this closes

The registry merges two names only when a source offers them together (CT.gov `otherNames`) **and**
the ontology resolves both to one drug. It never merges two separately registered assets whose own
names each resolve to the same drug. `KTE-C19` and `axicabtagene ciloleucel` never co-occur in one
intervention record, so they stay two assets although ChEMBL files `KTE-C19` as axi-cel's
development code.

> **Two assets whose names reach the same canonical drug through the authority's own identifier
> names are one asset.** Co-occurrence is still not identity (M11 unchanged).

## 2. The rule

An asset name carries **merge authority** for canonical drug `D` when all of these hold:

1. The resolver resolves the name (entity type DRUG) to `D`, unambiguously.
2. The name reaches `D` through an alias of type **`APPROVED_NAME` or `DEVELOPMENT_CODE`**.
   `TRADE_NAME`, bare `SYNONYM`, `XREF`, `SYMBOL` alone and `DESCRIPTION` confer no merge authority.
   (They still resolve for every other purpose; only merging is restricted.)
3. The name is not a **class term** (`bve.se.discovery.class_terms.is_class_term`, v5). A class
   label denotes a set of assets and cannot be an identifier of one of them.
4. The name is not a **biosimilar product code** of `D`: the same entity carries another alias
   containing both the name (as a whole token run) and the word `biosimilar`. The ontology itself
   is then saying the code names a distinct product of the same molecule, and same molecule is not
   same development asset.

Rules 3 and 4 are the two ontology-quality defects found in the pre-registration survey
(`CART19` → tisagenlecleucel filed as a development code; `EG12014` → trastuzumab filed as a
development code alongside `Eg12014 trastuzumab biosimilar`). They are expressed as general rules
over ontology content. **No drug name is listed anywhere in code.**

An asset's authority drugs are the set of `D` over its canonical name and aliases. An asset with
**more than one** authority drug takes part in no merge (conflict, fail closed). Assets sharing
exactly one authority drug `D` are merged into one, after all hits are ingested, through the
registry's existing reversible `propose_merge`/`apply_merge` with
`deterministic_basis = "authority_drug:<D>"`. Every merge is emitted in `identity_merges`.

The surviving asset id and display name are those of the member whose name is `D`'s approved
name, if any; otherwise the lowest asset id. Hit→asset mappings are rewritten to the survivor.

Existing `otherNames` alias handling at ingest is **unchanged**.

## 3. Declared non-merges

- `GC012F` ↔ `AZD0120`: neither name resolves. The only link is CT.gov `otherNames` — source
  co-occurrence, which M11 forbids as identity evidence.
- `CNCT19` ↔ `inaticabtagene autoleucel`: `CNCT19` does not resolve.

Both remain separate and are labelled **identity unresolved / likely alias** in the results
section. They become mergeable only through a separate, provenance-backed identity source
(sponsor pipeline, regulatory filing, a publication stating "formerly known as"), which is not
built here.

## 4. Out of scope

Stage attribution (closed, documented limitation), the regimen/role model, a modality key, ranking
policy, CCL19, and the mint5 target-evidence coverage limitation.

## 5. Acceptance (same sealed replays: TAC01 `tac01_control_a1`, mint5 `mint5_on` custody)

- **M1** `KTE-C19`↔axi-cel and `KTE-X19`↔brexu-cel merge in TAC01 and mint5; `CCS1477`↔inobrodib
  merges in mint5.
- **M2** `GC012F`/`AZD0120` and `CNCT19`/inaticabtagene autoleucel remain separate assets.
- **M3** Zero false merges among merge groups containing any asset in either run's top 50 (ranking
  v1, after merging). Every such group is inspected by hand and listed in the results.
- **M4** No class term, biosimilar product code, or ordinary word absorbs or is absorbed into a
  real asset in **any** merge group of either run (all groups listed and checked).
- **M5** `tests/se` passes.

Then the frozen ranking v1 scorer is re-run and TAC01 is re-examined for the residual problem.
Failure of M1–M4 → revert with a normal revert commit and record the result here.

## 6. Results

(appended after measurement)

### 6.1 Measurement — 2026-09-28, implementation `20934ce`

Sealed replays: `se_runs/tac01_merge_v1` (custody `tac01_control_a1`), `se_runs/mint5_merge_v1`
(custody `mint5_on`). Per-group listing: `merge_eval.txt` in each run dir; frozen ranker output:
`ranking_v1_compare.txt`. Ranking v1 R1–R3 PASS on both.

- **M1 PASS.** KTE-C19→axi-cel and KTE-X19→brexu-cel merged in both runs; CCS1477→inobrodib in
  mint5 (#211).
- **M2 PASS.** GC012F, AZD0120, CNCT19 and inaticabtagene autoleucel remain separate assets
  (identity unresolved / likely alias). CNCT19 is TAC01 #2; GC012F/AZD0120 are mint5 #8/#5.
- **M3 PASS.** TAC01 has 7 merge groups in the top 50, all correct: brexu-cel/KTE-X19 (#1),
  axi-cel/KTE-C19 (#3), tafasitamab/XmAb5574 (#6), tisa-cel/CTL019 (#7), coltuximab
  ravtansine/SAR3419 (#16), denintuzumab mafodotin/SGN-CD19A (#17), inebilizumab/MEDI-551 (#18).
  mint5 has none in the top 50.
- **M4 PASS.** 31 TAC01 and 23 mint5 groups checked by hand. CART19, EG12014, avert and ALLO-647 remain
  standalone. No class term, biosimilar code or ordinary word merged. Noted but not violations:
  - `VP16`→etoposide phosphate, and levocetirizine hydrochloride/dihydrochloride, are merges
    between salt forms of one active moiety. Both are excluded, not ranked.
  - Tisagenlecleucel still carries `CART19` as an alias. It came from CT.gov `otherNames` at ingest
    and is identical in the baseline `tac01_ind_fix`, so v1 did not introduce it.
- **M5 PASS.** `tests/se`: 1499 passed, 3 xfailed.

**Status: ADOPTED.**
