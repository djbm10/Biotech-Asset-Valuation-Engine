# PROTOCOL_ID_TRIAL_ATTRIBUTION v1 — a trial's own protocol id can move it to its coded product (preregistration)

**Status:** PREREGISTERED 2026-10-06. No implementation exists.
**Operator decision:** 2026-10-06. Trial-level attribution, not whole-asset merging.
**Parent diagnoses:** `icg318_trial_attribution_diagnosis_v1.md`,
`generic_descriptor_split_diagnosis_v1.md`.
**Baselines:** `~/se_runs/{tac01,mint5}_ncitid_v1`, ranked under ranking v2.

## 1. Problem

A trial can sit on a descriptor asset ("CD19-targeted Chimeric Antigen Receptor (CAR) T
Cells") while its own sponsor protocol id (`JWCAR029-005`) names a product that already
exists as an asset. Ownership is then wrong at the trial level. That affects stage,
indication, provenance and, potentially, human-efficacy attribution.

## 2. Rule (frozen)

The reference implementation is `research/se_protocol_id/enumerate_v1.py` (sha256
`549d4538d7d5e4bf3a94756f88be0c62464982c69aa01e410b83800a10de0efb`).

For each asset S and each CT.gov trial T that S holds:

- **R1. Protocol prefix.** Read T's own sponsor protocol id from the sealed record
  (`identificationModule.orgStudyIdInfo.id`). The prefix is its leading code token,
  `^[A-Za-z]{2,8}[- ]?\d{2,5}[A-Za-z]?` followed by the end of the id or `-`, `_`, space or `.`.
  No prefix, no move.
- **R2. Destination.** The prefix's link key (casefolded alphanumerics) equals a name or alias
  of **exactly one** other asset D. S itself must not carry that name.
- **R3. Not antigen-shaped.** The prefix is not an antigen or designator: `CDnn`, `BCMAnn`,
  `CARnn`, `CAR-Tnn` or `CARTnn`.
- **R4. Destination is product-specific.** D is not a generic descriptor, using the frozen
  vocabulary of `generic_descriptor_split_diagnosis_v1` §1.
- **R5. Prefix demonstrated as a product identifier.** At least one of D's own trials
  registers the code as an intervention name, an `otherNames` entry, or a token of one. This
  excludes study-series prefixes such as `STK-009`, `PLAT-02`, `Meta10` and `ALLO-647`, whose
  codes no intervention uses.
- **R6. Source is not product-specific.** S has no ChEMBL drug authority (that would make it a
  real co-intervention such as fludarabine, bendamustine or a comparator antibody). No name of
  S contains a non-antigen code token. An NCIt link alone does **not** make S product-specific,
  because NCIt files construct-family names: `BCMA-CD19 cCAR T cells` is NCIt C174412, a family
  name iCell reuses across ICG185, ICG180 and ICG318.
- **R7. Not already held.** D does not already hold T.

**Effect.** T moves from S to D:
- T leaves S's `trial_ids` and joins D's;
- every hit of T that was registered to S is redirected to D, so T's claims and facts are
  re-extracted under D;
- S is **never** deleted or merged, even when it is left empty.

Each move is recorded reversibly as `{trial_id, from_asset_id, to_asset_id, protocol_id,
prefix, basis="protocol_id:<prefix>"}`. It runs in the IDENTITY stage, after
`consolidate_by_ncit_product`.

**What it does not do:**
- create assets;
- merge assets;
- use sponsor, name similarity or trial counts;
- change target, modality, efficacy-reader, qualification or ranking rules.

## 3. Frozen population (enumerated and verified before code)

The population is `research/se_protocol_id/population_v1.json` (sha256
`663b5d7b0b6fa3f1210986fe0bb0a4688186a53b1f8450fb511cc27494060dc0`). It holds 18 moves: 10
in TAC01 and 8 in mint5. Every move was checked against the sealed record:

| Trial | Protocol id | From | To | Verification |
|---|---|---|---|---|
| NCT04089215, NCT04718883, NCT06149169 | JWCAR029-002/-005/-017 | *CD19-targeted Chimeric Antigen Receptor (CAR) T Cells* | JWCAR029 | Descriptions say "JWCAR029 will be administered" or "Relma-cel"; the official titles name JWCAR029 or relma-cel. **Correct.** |
| NCT06787989 | ICG318-ITP-01 | BCMA-CD19 cCAR T cells | ICG318 | Per the ICG318 diagnosis. **Correct.** |
| NCT06794008 | ICG318-AAV-02 | *BCMA-CD19 CAR-T therapy* | ICG318 | Per the ICG318 diagnosis (weaker evidence: hospital sponsor). **Accepted.** |
| NCT06446128, NCT06732232 | BZE2204-A-01 / B-01 | *CD19/CD20/BCMA CAR T cells*, *CD19/CD20/BCMA CAR-T*, and (TAC01) the title-minted "A Dose Escalating Study …" | BZE2204 | Same sponsor protocol series as BZE2204-C-01, whose intervention is "CD19/CD22/BCMA CAR-T cells (BZE2204)". **Correct.** The sponsor's own CD20/CD22 inconsistency is in the record. |
| NCT07113496 | RN1201-Onc | *Allogeneic CAR-T* | RN1201 | The official title says "Allogeneic CAR-T Cell (RN1201)". **Correct.** |

**ICG318 expected semantics:**
- the existing ICG318 trials stay attached;
- NCT06787989 and NCT06794008 move;
- NCT04162353 (ICG185-001) and NCT05474885 (ICG180-001) do not, because no asset is named
  ICG185 or ICG180;
- `BCMA-CD19 cCAR T cells` stays a separate asset with its two remaining trials. It is not an
  alias of ICG318.

**Excluded candidates:** `excluded_v1.json`, 175 rows, each with a general reason.

| Reason | TAC01 | mint5 | Examples |
|---|---|---|---|
| `source_is_product_specific` | 54 | 38 | fludarabine, cyclophosphamide, bendamustine, nirogacestat, talquetamab; axi-cel → FKC876 (Fosun Kite axi-cel: an identity question, not attribution); UTAA09 → ALLO-501 via `UCART-19` (would be **false**); `Blinatumomab (MT103)`, `ssCART-19 Cells`, `JWCAR029 (Relmacabtagene Autoleucel)` (duplicate coded assets: identity, not attribution) |
| `antigen_or_designator_prefix` | 25 | 20 | `CD19-005`, `CART19-BE-01`, `CD19 CAR ALL` |
| `prefix_not_demonstrated_as_intervention` | 13 | 11 | `STK-009`, `PLAT-02`, `Meta10`, `ALLO-647`, `CF33`, `TAK-007` (no intervention record is named TAK-007) |
| `destination_already_holds_trial` | 11 | 3 | |

**Emptied sources** (kept, not deleted):
- *CD19-targeted CAR T Cells*;
- *BCMA-CD19 CAR-T therapy*;
- *CD19/CD20/BCMA CAR T cells* and *CD19/CD20/BCMA CAR-T*;
- the title-minted *A Dose Escalating Study …*.

*Allogeneic CAR-T* keeps NCT07129642.

**Human efficacy.** No source asset carries `human_poc_present`, so no human-PoC claim is
lost. A destination may gain human-PoC only from a moved trial's own documents.

## 4. Acceptance (frozen)

Sealed replays go into new directories. Identity, facts and gates are compared against raw
`*_ncitid_v1`. Ranking is compared against `*_ncitid_v1` rebuilt under ranking v2 at HEAD.
Determinism comparisons exclude `created_at` and `applied_at`.

- **T1.** The recorded moves equal the frozen population exactly, per benchmark.
- **T2.** Zero false moves, by T1 plus §3. No whole-asset merge is created by this route; the
  merge records equal the baseline's.
- **T3.** Provenance: every move has a complete audit record. Each moved trial is in D and not
  in S. Every other trial of every asset is unchanged. No asset is deleted.
- **T4.** Assets that neither gave nor received a trial keep their facts, gates,
  qualification, `construct_target_set` and modality unchanged. Fact changes on S and D come
  only from moved trials.
- **T5.** Human-efficacy changes, if any, are only on D assets, and only supported by a moved
  trial's document.
- **T6.** Ranking code is unchanged. Every top-50 movement is an S or D row whose key changed,
  a backfill, or an emptied S leaving. Retained relative order is otherwise preserved.
- **T7.** Two TAC01 replays are identical, timestamps excluded.
- **T8.** `tests/se` and ruff pass.

## 5. Stop condition

- **Adopt** if T1–T8 all pass.
- **Otherwise** record the failure and revert. Do not tune R1–R7.
