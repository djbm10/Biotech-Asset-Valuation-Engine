# CANDIDATE_QUALIFICATION v7 — treatment-category descriptors are not products (preregistration)

**Status:** PREREGISTERED 2026-10-04. No pipeline implementation exists.

**Predecessors:**
- `candidate_qualification_v6.md` (adopted). Its §3 declared descriptive residuals.
- `target_compatibility_v1.md` (adopted). Baselines: `~/se_runs/{tac01,mint5}_compat_v1`.

This milestone is kept separate from target compatibility, as the operator directed.

## 1. Problem

Registries enter descriptions of a *category of treatment* as interventions. Examples:
`Fludarabine-based`, `Lymphodepletion Chemotherapy`, `Chemotherapy Agents`,
`Post-CR Consolidation Regimens`.

v6 could not reach them:
- NCIt has no concept for these phrases, so Q1 does not apply.
- They do not coordinate two named drugs, so Q2 does not apply.

A drug name inside such a phrase is a *modifier*. "Cyclophosphamide-based chemotherapy"
refers to a regimen category, not to cyclophosphamide. The representation that separates the
two is the phrase's **head**.

## 2. Rule Q3 (frozen)

The reference implementation is `research/se_qualification_v7/reader_frozen_v1.py`
(sha256 `b9ac6a49e8945c78498b57bf584fd6a88453ec1b5557ba8c45700fadadc30a8a`). The production
code must reproduce its decision on every frozen name.

1. Remove parenthesised and bracketed text, then tokenize on non-alphanumerics.
2. **Protection (P1).** If any token is a construct/product noun, there is no veto. The set
   is closed:
   > car, cart, cell, cells, antibody, antibodies, nanobody, vector, mrna, vaccine, virus,
   > tcr, nk, til, lnp

   A described construct (`… CAR-T cells`) is kept, under the adopted construct route.
3. **Protection (P2).** If any whitespace token is a development code (existing
   `is_development_code`), there is no veto. A sponsor code identifies a product.
4. **Veto (head).** The final token is a treatment-category noun from this closed set:
   > chemotherapy, chemotherapies, regimen, regimens, treatment, treatments, therapy,
   > therapies, agents, conditioning, immunosuppression, consolidation, induction,
   > lymphodepletion, care

   The reason code is `TREATMENT_CATEGORY_DESCRIPTOR`.
5. **Veto (elliptical).** The phrase ends in `-based` with no head noun. That is an
   attributive left without the noun it modifies. The reason code is
   `TREATMENT_CATEGORY_DESCRIPTOR`.

**Placement.** Q3 is part of `qualification_veto`, after Q1 and Q2:
- below the ontology route, so a name the drug ontology identifies is never touched;
- above every weaker route.

The effect is the same as v6: the name is unqualified but retained, and the veto is reported
in `qualification_vetoes`. No name, gene or benchmark row appears in the rule.

## 3. Frozen population and expected vetoes

The population is all 546 qualified non-`DIRECT_APPROVED_NAME` names across the two
`*_compat_v1` runs. It is frozen at `research/se_qualification_v7/population_v1.json`
(sha256 `94ee58e0ccedd559d4e4f24766e0fc912a7e3e866e6a51e07a947b325c823be5`).

**Expected vetoes: 15. Each was checked by hand as a treatment-category descriptor, not a
product.**

- Chemotherapy Agents
- Chemotherapy Regimen
- Cyclophosphamide and Fludarabine lymphodepleting chemotherapy
- Cyclophosphamide-based chemotherapy
- Fludarabine-based
- Induction Chemotherapy
- Induction Therapy Regimen
- Lymphodepleting Conditioning
- Lymphodepletion Chemotherapy
- MMF Immunosuppression
- Modified Ponticelli regimen
- Post-CR Consolidation Regimens
- Pre-Treatment Regimen
- standard corticosteroid treatment
- Standard of Care Treatment

**Protected by design.** The rule must leave these unchanged:
- `Senl_B19 autologous CAR-T (S1904) treatment`: a CAR head and a code are present;
- `Bispecific antibody-based combined with CAR-T cell therapy`: construct nouns are present;
- every `… CAR-T cells` description;
- NKTR-255, SYNCAR-001, AcNK-Sup003, Tecartus, AZD0120, FKC289, CLN-978.

**Declared residuals (not patched).** Each needs a different representation:
- `Withhold IS (…)` and `Continue IS (…)`: action phrases;
- `Corticosteroids`: a drug class with no head noun;
- `Placebo …` variants and `Comparator: Placebo`: control material, which should be
  extended in the comparator layer;
- sentence-shaped arm descriptions (`… will be injected intravenously …`);
- `Sequential Treatment With different CART`.

## 4. Acceptance (frozen)

These are scored on sealed replays into new directories, against `*_compat_v1`.

- **D1.** The newly unqualified names equal the 15 expected, restricted to each benchmark.
  Nothing extra and nothing missing.
- **D2.** Zero real products disqualified: D1 plus §3's hand check.
- **D3.** The §3 protected names keep their qualification reason unchanged. Every
  `DIRECT_APPROVED_NAME` is unchanged.
- **D4.** No `construct_target_set`, compatibility fact or target-gate decision changes on
  any asset that is still evaluated.
- **D5.** Ranking code is unchanged. Every top-50 movement is a vetoed row leaving, or
  backfill, with retained order preserved.
- **D6.** Two TAC01 replays give identical results.
- **D7.** `tests/se` and ruff pass.

## 5. Stop condition

- **Adopt** if D1–D7 all pass.
- **Otherwise** record the failure and revert. Do not tune the head set, the protection set or
  the population.
