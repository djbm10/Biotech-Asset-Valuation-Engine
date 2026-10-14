# MODALITY_SCOPE_PRODUCT_DESCRIPTION v1 — preregistration

Decision-neutral extractor milestone. No gate consumer, no fact or gate change, no identity/target/qualification/ranking/acquisition change. v3 stays unadopted. Based on the coverage diagnosis (`19c9074`, `b221143`).

## Structures

| Rule | Status | Reason |
|---|---|---|
| A — appositive | **in scope** | 5 independent positives |
| B — premodified copula | **in scope** | 32 independent positives |
| C — class-of | **unsupported** | 0 independent examples in the frozen sample (1 in the discarded first draw); the threshold is ≥5 |
| D — CT.gov intervention name | **unsupported** | development data shows class-label names ("CD19 CAR-T cells", "BiTE (CD19 x CD3 Bispecific Antibody)") are the norm; telling a named product from a class label needs target/identity authority that is out of scope |
| E — CT.gov otherNames | **unsupported** | development data shows otherNames attributing other products ("Withhold IS" → "anti-BAFF mAb"; "F182112+CD38" → "CD38 monoclonal antibody"); alias reliability needs identity evidence that is out of scope |

## Frozen rule (A and B)

Applies only to a mention the existing path leaves AMBIGUOUS with rule `unproven_subject_or_relation` or `product_phrase_not_head`, that is not an embedded alias (existing prefix/suffix check), and whose sentence has no negation/hedge (existing check). Existing PRODUCT/COMPONENT/RELATIONAL/coordination results are never overridden.

- **PRE** (between article and mention): zero or more items, each a token (`[^\W_]+` joined by `-` or `/`) or a parenthetical `(…)`, optionally followed by a comma, separated by whitespace. No item may be a boundary word (head-attachment v1 list) or a coordinator (`and or nor`). Every detected modality mention lying inside PRE must have the **same modality** as the candidate mention.
- **Nested suffix:** the candidate mention must not be a proper suffix of another detected mention ending at the same offset (e.g. `antibody` inside `bispecific antibody`).
- **POST** (after the mention): zero or more generic product heads (`therapeutic therapeutics therapy therapies drug agent product treatment medicine candidate`), an optional parenthetical, then end of sentence, `, ; : )`, or a next word that is a boundary word or ends in `-ed`/`-ing`.
- **A** (`explicit_product_appositive`): a source product name anywhere in the sentence, optional parenthetical, `,` then `a|an`, then PRE + mention + POST.
- **B** (`explicit_product_predicate_premodified`): the product name at sentence start (as now), optional parenthetical, `is|are a|an`, then PRE + mention + POST.
- Output: PRODUCT_LEVEL; `PRODUCT_IS_MODALITY`; relation span = product end → mention start; product span = matched name.

Predicted delta on the frozen existing population (v1 33 + v2 14 + H19 5 = 78 records): **none**. On the 25 head-attachment controls: **none**. Any change fails. (A draft predicted a HA21_PLAIN_PREMOD change; its frozen text, "Novel Product is novel peptide therapeutic", has no article, so Rule B cannot apply. The prediction was corrected before implementation and the rule was not changed.)

## Independent population

`research/se_modality_scope_product_description_v1/sample.py` → `sample.json`, built from sources disjoint from tac01/mint5_protoid_v1:
- CT.gov intervention descriptions from `tac01_control_r2` (an incomplete development run; trials not in the protoid runs);
- PubMed/conference abstracts in `aacr_safety` not present in the protoid snapshots.

A unit is a sentence with a token-bounded modality alias and one product's source-declared names. All comma/copula/class-shaped units are taken, plus 20 hash-ordered other units per pool. **103 units.** A first draw was discarded before adjudication because of two sampler defects: aliases pooled across candidates, and embedded-substring triggers.

`labels.json` holds the blind adjudication of required, allowed and forbidden spans. It is single-adjudicator, and that adjudicator also wrote this rule; this is a disclosed limitation.

## Acceptance (computed by `checker.py`, self-tested)

- G1 independent safety: zero PRODUCT_LEVEL assertions outside `required ∪ allowed` across all 103 units (covers class-label subjects, payload candidates, polyclonal IgG and other-product mentions).
- G2 per-rule recall: A and B each recall ≥ 80% of the units adjudicated with their structure.
- G3 frozen controls: v1 33, v2 14 and HA 25 conform with no delta.
- G4 the 5 FALSE admitted v3 facts gain no PRODUCT_LEVEL assertion of their value (v3 routing).
- G5 the 78-record population is byte-identical.
- G6 every PRODUCT_LEVEL assertion has product span, relation span, rule and source.
- G7 no production importer of `modality_scope`.
- G8 byte-identical builds. G9 checker self-test. G10 full `tests/se` (existing xfails only) and Ruff clean.

Per-rule fallback (frozen): if A or B fails G1 or G2 on its own assertions, that rule is removed, and the remaining set is re-validated on all gates **without any other change**. If none remain, revert. No lexical exceptions or post-result patching.

After adoption: a separately preregistered PRODUCT_VS_COMPONENT_MODALITY_SEMANTICS v4 design. Adoption here authorizes no gate migration.
