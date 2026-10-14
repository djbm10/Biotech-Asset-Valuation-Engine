# ESG401_CANDIDATE_NOMINATION_DIAGNOSIS v1 — STOP (J1 first; J2 and J3 also fail)

Prereg `505121d` (`docs/se_policies/esg401_candidate_nomination_diagnosis_v1.md`). Diagnosis only; no production change. Reproduce: `PYTHONPATH=src python research/se_esg401_candidate_nomination_diagnosis_v1/diagnose.py --output <new dir>`. Snapshot hashes are verified per unit and two builds are byte-identical. Self-test: a valid fixture is JUSTIFIED; no failure class fails J1; a spurious probe name fails J2; development-reference-only evidence does not count toward J1; an added ALTERNATIVE relation is detected.

## ESG401 trace: first boundary = nomination input selection

| Stage | Result |
|---|---|
| Raw field (`NCT06145308` `armGroups[3].description`, sha `4c21f6a5…`) | `ESG401 16 mg/kg IV …, sacituzumab govitecan 10 mg/kg IV …, or sacituzumab tirumotecan 5 mg/kg IV q2w` |
| Arm → intervention linkage | arm "Cohort 4 (TROP2 ADC)" → intervention `TROP2 ADC` (generic class label; no otherNames carrying the products) |
| Nomination inputs (`interventions[].name/otherNames`) | ESG401 **not reachable**: **first loss** |
| Arm-description name route | **does not exist**: `_candidate_interventions` iterates interventions only |
| Mention probe over the description (hypothetical) | ESG401, sacituzumab govitecan, sacituzumab tirumotecan (all three; nothing spurious here) |
| H19 candidate population | no ESG401 candidate or alias |
| Relationship representation | no "alternative" relation: `IdentityRelationship` has ALIAS / COFORMULATED / COMBINATION_PARTNER / COADMINISTERED_WITH / CONJUGATE_PARENT / UNCERTAIN |

The relationship is an investigator-choice **alternative**. Recording the three as combination partners or co-administered would be false.

## Independent sample (45 arms, 3 shape strata, frozen before measurement)

63 named-entity mentions; 45 THERAPEUTIC_PRODUCT mentions (39 distinct names); 10 generic class labels. Relations: 20 single, 5 combination, 5 sequence (including a crossover written with ` / `), 2 randomized product-vs-placebo `or`, 3 background lists, 10 none. **Product alternatives: 0** outside ESG401.

| Requirement | Result |
|---|---|
| **J1 failure class** (≥5 uncovered administered products, ≥3 trials) | **FAIL: 0.** 41/45 product mentions are already nomination inputs; the 4 uncovered ones are BACKGROUND (fludarabine/cyclophosphamide lymphodepletion) |
| **J2 probe safety** (existing extractor over arm descriptions emits nothing spurious) | **FAIL: 29 spurious strings** (`their`, `Level`, `weeks`, `until`, `safety`, `ACUVUE`, `CliniMACS` …); recall on products is only 0.67 |
| **J3 alternative relation in schema** | **absent** (non-blocking by prereg; it defines the representation gap) |

## Pool scan (unadjudicated upper bound, all 3,509 development arms)

The probe emits a name not covered by trial interventions in 1,570 arms / 803 trials / 343 distinct strings. Spot inspection shows these are dominated by ordinary words and background agents (`cycle`, `level`, `cyclophosphamide`, `prednisolone`). There are a few real arm-only leads (e.g. `NK019`, `brexucel`), but they are unadjudicated and **not counted**.

## Verdict and boundary

- **Failure class not established.** In independent development data, explicitly named administered products that appear only in arm descriptions are rare. ESG401 is a real miss, but it is one development observation.
- **Second boundary (would block any implementation):** the existing mention extractor is unsafe on arm-description prose. It mints ordinary words, the same defect as ordinary-word minting in identity work, so a description route would flood nomination.
- **Third boundary:** there is no representation for product alternatives.

`ARM_ALTERNATIVE_CANDIDATE_NOMINATION v1` is **not justified**. If pursued later, it needs:
1. a larger adjudicated sample establishing the failure class;
2. a description-safe name extractor (identity-authority-backed, not shape-based);
3. a new `ALTERNATIVE_IN_ARM` relation distinct from combination and randomized allocation.

No blacklist and no ESG401 alias were added. Note: the prereg text says both "iff J1 ∧ J2 ∧ J3" and "J3 alone does not block". The code applies the latter, but the verdict is STOP either way.
