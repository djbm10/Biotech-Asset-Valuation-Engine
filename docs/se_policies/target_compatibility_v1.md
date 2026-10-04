# TARGET_COMPATIBILITY v1 — a positively established other target makes the query incompatible (preregistration)

**Status:** PREREGISTERED 2026-10-03. No implementation exists.
**Decision:** the operator chose Option A on 2026-10-03 and asked for it as a
*compatibility* state, not as negative target facts.

## 1. Semantics

The rule never creates a fact that an asset "does not target gene X". It creates an
authority-backed `target_compatibility_evidence` fact. That fact means: *the product has a
positively identified therapeutic target entity (a complex/family, or a non-gene antigen)
that this source names*. The gate reads it only when no `construct_target_set` exists.

| Gate | Condition |
|---|---|
| **PASS** | Unchanged: the construct target set satisfies the expression. |
| **FAIL** (new path) | No construct target set exists. One compatibility fact positively establishes target entities, **and** no queried canonical target is a member of any established entity. |
| **UNKNOWN** | Everything else, including the case where a queried target *is* a member of an established complex. Membership never becomes a positive claim. |

Absence is never evidence. A FAIL requires a positively identified entity.

## 2. Eligible authority (frozen, narrow)

- **E1. ChEMBL/OT structured edges.**
  - **Condition:** the asset resolves (existing `resolve_asset`) to a drug whose **USABLE**
    edges are **all** `FAMILY_OR_COMPLEX_ASSOCIATION` and number at least one. A usable
    `DIRECT_TARGET` row disables E1, because that is the construct-set route's job.
  - **Representation:** each source record is kept as one entity, written as
    `COMPLEX:<source>:<record_id>` together with its member list. Members are listed only
    so the gate can test membership. They are **never** emitted as target ids, and no
    `construct_target_set` or target assertion is created from them.
- **E2. Adopted NCIt antigen classes.**
  - **Condition:** an unambiguous NCIt link whose product sits **only** in non-gene antigen
    classes (Claudin18.2 C201172, GD2 C201491).
  - **Representation:** the entity is `NONGENE:<class code>`, with an empty member list.
    No gene is created from it.
- **Not eligible:**
  - prose of any kind;
  - NCIt mechanism sentences without the class (for example satri-cel, which is not filed
    under the Claudin18.2 class);
  - tabelecleucel and lifileucel;
  - absence of a queried gene from a database.

## 3. Frozen population (enumerated and hand-verified before code)

The population is every evaluated asset in `~/se_runs/{tac01,mint5}_qual_v6` with target
gate UNKNOWN and no construct target set where E1 or E2 applies. It is frozen at
`research/se_compat/population_v1.json` (sha256 `27c6ce88b676186fb8c4b5c64d5cc97403403cc8f93d2c021b6af04af7313944`). The unique-name audit is in
`research/se_compat/audit_list_v1.txt`.

**Size:**
- 109 transitions in TAC01 and 62 in mint5 would go UNKNOWN→FAIL, all through E1.
- 0 transitions go through E2: no linked product sits only in a non-gene class.
- 0 assets have a queried target inside an established complex.

**Not changed:** 554 TAC01 and 328 mint5 UNKNOWN assets have **no** positive other-target
evidence, so they stay UNKNOWN. That count includes tabelecleucel, lifileucel, satri-cel,
rese-cel and TAK-007.

**Manual verification, done before implementation.** I read all 127 unique names against
their established entities. Each one is a product whose pharmacology is a non-CD19, non-BCMA
target entity. The groups are:

- **Ligase complex:** IMiDs/CELMoDs → CRL4-CRBN (pomalidomide, lenalidomide, thalidomide,
  iberdomide).
- **Integrins:** vedolizumab and natalizumab → α4β7/α4β1.
- **Cytoskeleton, DNA and enzymes:**
  - taxanes, vincas and colchicine → tubulin;
  - purine/pyrimidine analogues (including fludarabine phosphate and cytarabine) → DNA
    polymerases;
  - proteasome inhibitors → proteasome;
  - HDAC and PARP inhibitors;
  - ABL1/BCR TKIs.
- **Cytokines and receptors:** IL-2R, IL-6R, IL-12/23, IFN-α, the FIX/FX bispecific
  (emicizumab).
- **CNS, cardiovascular and anaesthetic agents:** GABA-A, NMDA, adrenergic, opioid, Nav and
  Cav channels.
- **PK booster:** CYP3A (ritonavir, cobicistat).
- **Others:** each a correctly identified family.

No name is a CD19- or BCMA-directed product. **0 of 171 transitions are false.**

## 4. Acceptance (frozen)

These are scored on sealed replays into new directories, against `*_qual_v6`.

- **T1.** The set of UNKNOWN→FAIL transitions equals the frozen population exactly. That
  means zero false transitions, by §3.
- **T2.** Pomalidomide and vedolizumab transition, because E1 positively supports it.
  Satri-cel stays UNKNOWN, because it has no Claudin18.2 class membership and E2 does not
  apply. I record this and do not tune it.
- **T3.** Tabelecleucel, lifileucel, rese-cel and TAK-007 stay UNKNOWN.
- **T4.** No PASS changes. No other gate transition happens, so no PASS→FAIL and no
  FAIL→other.
- **T5.** No new `construct_target_set` and no new target assertion. Compatibility facts
  contain only `COMPLEX:` and `NONGENE:` entities.
- **T6.** Ranking code is unchanged. Every top-50 movement is explained by a frozen
  UNKNOWN→FAIL row leaving, or by backfill.
- **T7.** Two TAC01 replays give identical results. No new sidecar is introduced, because
  E1 and E2 use already-sealed artifacts.
- **T8.** `tests/se` and ruff pass.

## 5. Stop condition

- **Adopt** if T1–T8 all pass.
- **Otherwise** record the failure and revert. Do not tune.

## 6. Result — 2026-10-04, code `d175dbb`

**Runs:**
- `~/se_runs/tac01_compat_v1`
- `~/se_runs/tac01_compat_v1_det`
- `~/se_runs/mint5_compat_v1`

**Score:** `research/se_compat/stage_t_v1.txt`.

| Criterion | Result |
|---|---|
| **T1** | **PASS.** The UNKNOWN→FAIL transitions equal the frozen population exactly: 171/171, with 0 extra and 0 missing. That gives 0 false transitions, by §3. |
| **T2** | **PASS.** Pomalidomide and vedolizumab go UNKNOWN→FAIL in both benchmarks. Satri-cel stays UNKNOWN; this is recorded and not tuned. |
| **T3** | **PASS.** Tabelecleucel, lifileucel, rese-cel and TAK-007 stay UNKNOWN. |
| **T4** | **PASS.** The only transitions are UNKNOWN→FAIL: 109 in TAC01 and 62 in mint5. No PASS changed. |
| **T5** | **PASS.** `construct_target_set` facts and target assertions are identical. Every compatibility entity is `COMPLEX:`; no E2 entity occurred, and no gene id was emitted. |
| **T6** | **PASS.** Ranking code is unchanged. The TAC01 top 50 is unchanged, because no frozen row was in it. In mint5, pomalidomide (#3) and vedolizumab (#4) left, retained order is preserved, and two dual CD19/BCMA CAR-T rows backfill at #49–50. |
| **T7** | **PASS.** The two TAC01 runs are identical in facts, gates, ranking and top 50. |
| **T8** | **PASS.** `tests/se` 1568 passed, 3 xfailed. Ruff is clean. |

**Status: ADOPTED.** The new baselines are `~/se_runs/{tac01,mint5}_compat_v1`.
