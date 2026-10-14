# MODALITY_SCOPE_PRODUCT_DESCRIPTION v1 — Rule A ADOPTED, Rule B removed

Preregistration `ce9aa9b` (`docs/se_policies/modality_scope_product_description_v1.md`); red-first tests `8bdb992`. Decision-neutral: `modality_scope` still has no production importer.

## Outcome

| Rule | Independent result (103 units) | Disposition |
|---|---|---|
| A — appositive `X, a/an … M` | recall **5/5**, 0 unsafe | **adopted** (`explicit_product_appositive`) |
| B — premodified copula `X is a/an … M` | recall 26/32 (81%), **2 unsafe** | **removed** under the preregistered per-rule fallback |
| C — class-of | 0 independent examples | unsupported |
| D — CT.gov name | identity boundary | unsupported |
| E — CT.gov otherNames | identity boundary | unsupported |

Rule B's unsafe promotions:
- `Bexxar is a radioimmunotherapeutic drug, an antibody that …`: a radioconjugate certified as MONOCLONAL_ANTIBODY.
- `Immune Checkpoint Inhibitor (ICI) is a monoclonal antibody designed …`: a class-label subject.

Both are the identity and composite boundaries that kept D and E out. B was removed with no other change, and every gate was re-validated with Rule A alone: `checker.py --rules A` gives **ADOPT**, G1–G7 all pass, the self-test passes and two builds are byte-identical. Full `tests/se` and Ruff are recorded in `results/`.

Rule A changes no frozen assertion: the v1 33, v2 14, head-attachment 25 and H19 5 controls are unchanged, and the 78-record population is byte-identical. The 5 adjudicated-FALSE admitted facts gain no PRODUCT_LEVEL support. Rule A safeguards: same-modality premodifiers only (a TCE premodifier blocks an `antibody` head), no nested-suffix promotion (`antibody` inside `bispecific antibody`), POST must end the noun phrase, and the existing hedge/negation and embedded-alias checks.

## Disclosed process errors (none changed a rule after results)

1. The first sample draw was discarded before adjudication because of two sampler defects: aliases pooled across candidates, and embedded-substring triggers.
2. The checker's HA21 control ID was wrong and was fixed before commit; the red baseline then exposed the pending delta.
3. A terminal output-compression hook stripped articles from displayed text. Reading HA21 through it, I wrongly "corrected" the predicted HA21 delta to none before implementation. The real text is "is **a** novel peptide therapeutic", so Rule B did change it. That change disappeared only because Rule B was removed for its independent safety failure. The prediction error is recorded, not edited away.
4. The adjudicator also wrote the rule spec.

## Limits

Rule A recall is measured on only 5 independent positives. Rule A adds little to the dev v3 population: appositives were 15/293 rows in the diagnosis, and most real copula descriptions stay AMBIGUOUS now that B is gone. Its effect on hypothetical gate migration is for the separately preregistered v4 design to measure (`docs/se_policies/product_vs_component_modality_semantics_v4.md`). Adoption authorizes no gate change.
