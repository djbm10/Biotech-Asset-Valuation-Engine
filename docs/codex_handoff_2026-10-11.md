# Codex handoff — S&E engine, 2026-10-11

## Current outcome — INDICATION_REQUIREMENT_SEMANTICS v1 REVERTED (2026-10-11)

The operator authorized v1. It was preregistered at `0aefe85`, implemented at `93c1f83`,
scored/recorded FAILED_ACCEPTANCE at `8f466b4`, and reverted normally at `d8f5023`.
Engine source and tests are byte-identical to `c70461e` (engine `f0e90e6`).
Worktree remains `/home/djmann/projects/bve-b8`, branch `m11-identity-graph`.

Authoritative record: `docs/se_policies/indication_requirement_semantics_v1.md`.
Frozen artifacts: `research/se_indication_semantics_v1/`. 38 reference products, 33
indication-only reference exclusions, 655 indication-only excluded assets, 16 semantic
controls, 18 non-disease terms, and TAC01/mint5 accepted artifacts were frozen before code.

Criteria: I1 FAIL; I2 PASS; I3 PASS; I4 PASS; I5 FAIL; I6 FAIL; I7 PASS; I8 FAIL.
Attempt tests/se: 1,653 passed, 10 failed, 3 expected xfails. Attempt and restored ruff
check src/ are clean. After reversion, 108 indication/intent tests passed. The full suite
was not rerun after reversion; source/tests restoration is verified byte-for-byte.

The attempt made 31/33 excluded references visible, but 21 through absent requirements,
only 10 through proper PASS decisions; Crovalimab and zilucoplan still FAIL. TAC01 lost
JCAR014's accepted PASS (Not Otherwise Specified treated as negation), with 14/20 order
positions changed; mint5 stayed invariant. All non-indication data/decisions stayed fixed;
23 positive condition strings reviewed, no false positive indication assertion found.

Failures to diagnose BEFORE a newly preregistered v2:
- NSCLC crosses the parser's AMBIGUOUS_TARGET `cell` span; residual-only grouping erases
  the disease requirement. Recover full disease spans without changing target parsing.
- NCIt C128429 Hidradenitis Suppurativa is typed Finding; the disease-type filter omits it.
  Use an authority taxonomy with explicit indication semantics, not all Findings.
- Different observed diseases do not establish an exhaustive drug indication history:
  Crovalimab has only aHUS facts, zilucoplan only COVID-19 in the frozen rows. Preregister
  the positive incompatibility evidence needed under incomplete/open-world coverage.
- Legacy B-cell lymphoma has a broad/subtype name ambiguity (C188021/C3457), and disease
  qualifiers cannot be handled by an unrestricted negation-token veto.

No behavior patch after results. Failed attempt remains in history. No durable diagnostic
improvement: frozen baseline remains 5/38 visible references, 33 indication-excluded,
57 TARGET_UNKNOWN_FILL, 40 NON_PRODUCT_GENERATION plus 1 QUALIFICATION_MISS top-20 rows.
No post-adoption remeasurement applies. Do not start qualification/routing/target milestones.
**H16–H20 remain entirely untouched. Do not run or inspect them.** No long live acquisition
or benchmark replay was launched. Next action: a NEW v2 preregistration resolving these
indication semantics failures; untouched validation is premature until adoption.


Start here, then read `docs/se_handoff_state.md` for the older context. That file predates
the target-recognition work, so this file wins wherever the two disagree.

## 1. Where you are

- **Worktree:** `/home/djmann/projects/bve-b8`. This is **not** the main repo checkout at
  `~/projects/biotech-asset-valuation-engine`.
- **Branch:** `m11-identity-graph`. **HEAD:** `a508831`, the diagnosis commit (or later).
  The tree is clean apart from this file.
- **Engine code version:** `f0e90e6`. Every later commit is docs, labels or research scripts
  only.
- **Environment:**
  - conda env `biotech-env`;
  - `PYTHONPATH=/home/djmann/projects/bve-b8/src` when running anything from this worktree
    (an editable install may point at another worktree);
  - tests: `python -m pytest tests/se -q`, last run 1,663 passed, 3 xfailed;
  - lint: `ruff check src/`.
- **Live runs:** `bve-se-search` with `--source-index ~/se_runs/aacr_probe5/source_index.yaml`,
  output under `~/se_runs/<name>/`.

  **Never launch live runs or TAC01/mint5 replays yourself.** Background jobs are
  memory-reaped. Ask the operator to run them in their own terminal, giving the exact
  command.

## 2. Non-negotiable workflow rules (operator)

1. Every milestone gets a preregistration doc in `docs/se_policies/<NAME>_v<k>.md`, which
   freezes the population and acceptance criteria. It is committed **before** any
   implementation.
2. Adopt or revert strictly. Never patch after results, and never weaken criteria to fit an
   implementation. A failed version is recorded as FAILED_ACCEPTANCE, reverted, and
   re-preregistered as v<k+1>.
3. No query-specific, product-specific or name-list exclusions.
4. Do **not** tune ranking. The order in `reporting/shortlist._rank_key` is frozen.
5. Never combine distinct root causes in one implementation.
6. UNKNOWN is preferable to a false target. Preserve every adopted TAC01/mint5 identity,
   target, modality and efficacy rule.
7. Commits use conventional messages via `git commit -m ... -m ...`. A hook blocks
   `--no-verify` and the `printf | git commit -F` pattern. End every commit message with
   `Co-Authored-By:` attribution.

## 3. Validation sets and their status

| Set | Doc | Status | Use |
|---|---|---|---|
| TAC01, mint5 | (benchmarks) | **FROZEN** | Only to confirm a fix for an independently found bug |
| H1–H5 | `heldout_validation_suite_v1.md` | Run; FAIL 0/5 | Diagnostic only, never generalization evidence |
| H6–H10 | `heldout_validation_suite_v2.md` | **Unrun**, partially exposed | Secondary confirmation only |
| H11–H15 | `heldout_validation_suite_v3.md` §5 | Run at f0e90e6; FAIL 0/5; target recognition 4/5 exact | Now **diagnostic** only |
| **H16–H20** | `heldout_validation_suite_v4.md` (`eaace55`) | **Untouched**: never run, never resolved, no outputs inspected | **Primary** validation for the next shortlist fix |

H16–H20 must stay untouched. Do not run their queries, do not resolve their targets, and do
not look up their reference products in any run output.

Rubric, used by every suite:
- labels: RELEVANT, WRONG_TARGET, DUPLICATE, NON_ASSET, UNVERIFIABLE;
- blind labels are committed before scoring;
- per query: P@20 ≥ 0.70, Recall@all ≥ 0.60, NON_ASSET ≤ 1, DUP ≤ 2, false human-PoC = 0;
- suite: PASS at ≥4/5.

Scorers live at `scripts/score_heldout_suite_v{1,3}.py`, with labels in
`research/se_heldout/labels_v{1,3}.json`.

## 4. What was just finished

- **TARGET_AFFIX_RECOGNITION v5 ADOPTED** (`f0e90e6`): `anti-X` and `X-directed` parse exactly
  as bare `X`.
- **DUAL_TARGET_SEPARATOR_SAFETY ADOPTED** (earlier).
- **HELDOUT v3 (H11–H15) scored** (`b0580ec`): FAIL 0/5, with no false human-PoC.
- **SHORTLIST_NONPRODUCT_OFFTARGET_DIAGNOSIS v1** (`a508831`), diagnosis only. Read
  `docs/se_policies/shortlist_nonproduct_offtarget_diagnosis_v1.md`. Data is in
  `research/se_shortlist_diag/`.

Key findings:
- **All 38/38 reference products in H2, H4 and H11–H14 were discovered, and 33 are
  EXCLUDED solely by `strategy.indication` FAIL.**
  - `ontology/indications.py` knows a single concept (B_CELL_LYMPHOMA).
  - `intent/compiler.residual_indications` turns every other disease phrase into single-word
    literals, e.g. `["non-small","lung","cancer"]`.
  - It also includes non-disease words such as `inhibitors`, `G12C` and `complement`.
  - These literals are compared by exact `IN` against whole registry condition strings. So
    any asset *with* indication evidence FAILs, while evidence-less names stay UNKNOWN and are
    shown.
- The 102 bad top-20 rows break down as:

  | Class | Rows |
  |---|---|
  | D TARGET_UNKNOWN_FILL | 57 |
  | A NON_PRODUCT_GENERATION | 40 (all qualify via `DIRECT_APPROVED_NAME` = a ChEMBL molecule name) |
  | B QUALIFICATION_MISS | 1 (methane; the NCIt veto sits below the ontology route) |
  | H DUPLICATE | 4 (trade name vs INN) |
  | C false target PASS, E known incompatible, G discovery miss | 0 each |

- F (ranking) has 3 relevant rows displaced because modality precedence comes before the
  target decision. This is recorded only.
- **Requiring target PASS is unsafe.** 5 of the 15 RELEVANT rows are target-UNKNOWN (all of
  H4's TL1A hits, plus gumokimab and netakimab).
- **An entity link is not a junk discriminator.** 5 of the 15 RELEVANT rows also have none.
- **H15_EXTRA_TARGET_DIAGNOSIS v1** is recorded but not fixed (`h15_extra_target_diagnosis_v1.md`):
  - the LDLR alias "familial hypercholesterolemia" turned the disease phrase into a target;
  - the H15 indication became `["inhibitors","homozygous"]`.

## 5. Historical v1 recommendation (superseded by the outcome above)

The diagnosis recommends this milestone as having the highest precision benefit and the
lowest false-negative risk. The operator subsequently authorized it; v1 was attempted and reverted as recorded above.

Proposed shape:
- Disease phrases compile to concepts, matched against registry conditions by
  name-or-subtype. This generalizes the adopted B-cell-lymphoma mechanism in
  `ontology/indications.py` and `gates/evaluator.evaluate_indication`.
- Non-disease residual words are no longer indication literals. `residual_terms` must stay
  untouched, because they drive trial retrieval (see the docstring of `residual_indications`).
- A phrase that cannot be matched yields **UNKNOWN, never FAIL**.
- The vocabulary must come from an authority, not hand-picked per query. A hand-picked
  list would be tuning on diagnostic data.
- Preregister:
  - a population of query disease phrases and registry conditions that is **not** drawn from
    H11–H20;
  - acceptance criteria that include the off-indication admission risk;
  - TAC01/mint5 parity;
  - `tests/se` green.

  Then validate on H16–H20, with the operator running it live.

Later milestones, each separate, in this order:
1. NONPRODUCT_QUALIFICATION v1 (A+B). Use an authority substance-type discriminator above
   the `DIRECT_APPROVED_NAME` route. No name lists, no entity-link rule.
2. TARGET_UNKNOWN_SHORTLIST_ROUTING v1 (D). Re-measure after the indication fix first.
3. TARGET_AUTHORITY_COVERAGE v1.
4. TRADE_NAME_IDENTITY v1 (H).
5. H15_EXTRA_TARGET_DIAGNOSIS.
6. D-var (KRAS G12C) and D-iso (Claudin 18.2).
7. Merged-survivor display-name cleanup.

## 6. Code map (only what you need next)

| Path | Role |
|---|---|
| `src/bve/se/intent/parser.py` | Query to spans. Contains the affix and separator rules (adopted; do not touch) |
| `src/bve/se/intent/compiler.py` | `residual_indications` builds `strategic_gap.indications` |
| `src/bve/se/ontology/indications.py` | Indication concept vocabulary (frozen by `indication_gate_semantics.md`; a change is declared) |
| `src/bve/se/gates/engine.py` (~L227) and `gates/evaluator.py` (`evaluate_indication`, `evaluate_requirement`) | The indication gate |
| `src/bve/se/discovery/asset_qualification.py` | `qualification_reason` (route order) and `qualification_veto` |
| `src/bve/se/pipeline.py` (~L915–1030) | Qualification, low-support routing, gating |
| `src/bve/se/reporting/shortlist.py` | `build_shortlist`, `_rank_key` (frozen) |
| `scripts/score_heldout_suite_v3.py` | Template for a v4 scorer (swap REFS/INTENDED/paths/labels) |

## 7. Known caveats

- Ruff flags style issues (E702, E741, F401) in `research/se_shortlist_diag/*.py`. They are
  research scripts outside the `src/` lint scope, and they reproduce their committed JSON
  outputs.
- Under the frozen matching rule, suffixed INNs (`pozelimab-bbfg`) don't match the bare
  reference. This is recorded as-is in v3 §5 and carried into v4 §2.
- In the final report of the previous session, the diagnosis commit hash was misquoted as
  "4a0e1c2…". The correct hash is **`a508831`**.
