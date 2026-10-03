# TARGET_AUTHORITY_ARBITRATION v1 — NCIt product facts outrank CT.gov intervention-text facts (preregistration)

**Status:** PREREGISTERED 2026-10-02. No implementation exists.
**Predecessor:** `ncit_target_sidecar_v1.md`, ADOPTED. That milestone was fill-only, so a
conflicting existing fact was logged as `kept_existing_conflict` and left in place.

## 1. Conflict population (enumerated before any rule was written)

The population is every asset, in either `*_ncit_v1` run, whose NCIt disposition exists and
whose ledger holds at least one `construct_target_set` fact differing from the NCIt set. It is
frozen at `research/se_arbitration/conflict_population_v1.json` (sha256 `f3202623580be27a5342a5f26d7ac4b84ce4997500d183954f3271110a559e72`).

Provenance is taken from the facts' supporting claims.

- **DRUG_AUTHORITY:** ChEMBL/OT direct edge (`drug_target_authority_direct_edge`).
- **CTGOV_INTERVENTION_TEXT:** `clinicaltrials_structured` claims with predicate
  `construct_target_set`. The intervention free-text reader is the only producer of that pair.

| Class | TAC01 | mint5 | Assets |
|---|---|---|---|
| NCIt no target (`no_antigen_class` / `no_antigen` / `class_mechanism_disagree` / `no_mechanism_sentence`) | 8 | 6 | Anti-CD19/CD20/CD22 CAR, TAK-007, iCAR NK, afami-cel, prizlon-cel, NKX019, IL13Rα2 CAR, MC-19PD1 |
| DRUG_AUTHORITY present (already superseded at runtime; the authority fact is effective) | 2 | 2 | liso-cel, CART19/tisagenlecleucel |
| **APPLICABLE**: NCIt emits, link unambiguous, every existing fact is CTGOV_INTERVENTION_TEXT | 5 | 5 | see below |

**Manual determination for every APPLICABLE conflict.** The verdicts were checked against the
product's NCIt definition and its known pharmacology, before implementation.

| Asset (NCIt) | Existing (CT.gov text) | NCIt | Correct effective set | Rule correct? |
|---|---|---|---|---|
| CD19CAR-CD28-CD3ζ-EGFRt Tcm (C133072) | {CD19, EGFR} | {CD19} | {CD19}: EGFRt is a truncated-EGFR tracking/safety tag | yes |
| autologous CD19CAR-CD28-CD3ζ-EGFRt Tcm (C105614) | {CD19, EGFR} | {CD19} | {CD19} | yes |
| Human anti-CD19CAR-4-1BB-CD3ζ-EGFRt CD4+/CD8+ (C133191) | {CD19, CD4, CD8A} | {CD19} | {CD19}: CD4/CD8 describe the cell population | yes |
| CD19-CD8-CD28-CD3ζ-CAR-mbIL15-HER1t (C150906) | {CD19, CD28, CD8A} | {CD19} | {CD19}: CD8 hinge, CD28 costimulatory domain | yes |
| AUTO3 (C162620) | {CD22} | {CD19, CD22} | {CD19, CD22}: a bicistronic CD19/CD22 CAR, and NCIt's class and mechanism statements independently give both | yes |

**Recorded, but outside this rule.** Some NCIt-no-target rows carry existing CT.gov facts that
are wrong:
- the IL13Rα2 CAR → {CD19}, from its CD19t tag;
- MC-19PD1 → {CD19, CD28};
- TAK-007 → {IL15}, from its armoring.

The rule does not reach them, by design. They stay as they are and are reported.

## 2. Rule (frozen)

This runs in the existing `NCIT_TARGETS` stage, for an asset with an existing
`construct_target_set`.

- **A1. Preconditions.** NCIt must have `link.reason == "emit"`, from an unambiguous link,
  and every existing effective fact must be CTGOV_INTERVENTION_TEXT. Every claim behind
  every fact must have `extraction_method == "clinicaltrials_structured"` and predicate
  `construct_target_set`.
- **A2. Resolution.** If any existing fact differs from the NCIt set, the NCIt fact replaces
  all of the asset's effective `construct_target_set` facts, using the same
  `supersede_construct_targets` mechanism the drug authority uses. The superseded facts and
  claims stay in the ledger. The disposition action is `arbitrated_ncit_over_ctgov_text` and
  lists the superseded values.
- **A3. Fall-through.** If an existing fact has any other provenance (DRUG_AUTHORITY, or
  anything else), nothing changes, and the action stays `kept_existing_conflict`.
- **A4.** Non-emit NCIt dispositions and ambiguous links never arbitrate.
- **A5.** No asset, gene, domain or benchmark name appears in the rule. The decision depends
  only on provenance class and the NCIt disposition.

**Precedence after v1:**

DRUG_AUTHORITY > NCIt(emit, unambiguous) > CTGOV_INTERVENTION_TEXT. Otherwise, whatever is
present is kept.

## 3. Acceptance (frozen)

These are scored on sealed replays of the same corpora, into new directories, against
`{tac01,mint5}_ncit_v1`.

- **B1.** Exactly the 5 APPLICABLE assets per benchmark are arbitrated, and each one's
  effective set equals the §1 "correct" column. That means zero wrong effective targets.
- **B2.** No asset with a DRUG_AUTHORITY fact changes its effective set.
- **B3.** No asset with an ambiguous link or a non-emit NCIt disposition changes. That
  includes the three wrong-but-out-of-scope rows above.
- **B4.** No other `construct_target_set` changes anywhere, and no ST6GALNAC4 / CARTPT /
  alias-fragment target appears that the baseline did not have.
- **B5.** Ranking code is unchanged.
  - Predicted gate changes: TAC01 AUTO3 FAIL→PASS; all others unchanged. The EGFRt/CD4/CD28
    rows already pass on CD19 in TAC01, and all five still fail in mint5 for lack of BCMA.
  - Every movement must be explained by an effective-target change.
- **B6.** Determinism: two TAC01 replays give identical facts, dispositions and top 50. The
  fail-closed sidecar dependency is unchanged.
- **B7.** `tests/se` and `ruff check src/` pass.

## 4. Stop condition

- **Adopt** if B1–B7 all pass.
- **Otherwise** record the failure and revert. Do not tune.
