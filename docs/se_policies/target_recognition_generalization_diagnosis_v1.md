# TARGET_RECOGNITION_GENERALIZATION_DIAGNOSIS v1 — why H1/H3/H5 were refused (diagnosis + preregistration)

**Status:** DIAGNOSIS FROZEN 2026-10-09. TARGET_AFFIX_RECOGNITION v1 is preregistered in §5.
No behaviour change has been made.
**Engine:** `6b1d4f2`. **Ontology:** `chembl_ChEMBL_37__open_targets_26.06__resolver_v2__modality_v2`.
**Artifacts** (in `research/se_heldout/`): `target_probe_v1.txt` (resolver and parser probes),
`target_population_v1.py` → `.txt` / `.json` (population study, sha256 `5d48552868a8…`).

**Contamination disclosure.** The resolver probe also looked up HER2, PCSK9, IL-23, DLL3 and
LRRK2, which are terms in the untouched H6–H10 suite. No engine run was made for them, and
no design decision below uses them. They are recorded so the reader can judge.

## 1. Per-query findings

| | H1 GPRC5D | H3 FcRn | H5 Claudin 18.2 | H2 KRAS G12C (control) | H4 TL1A (control) |
|---|---|---|---|---|---|
| **1. Concept stated** | GPRC5D protein | the neonatal Fc receptor (FCGRT α-chain + B2M) | the CLDN18 isoform 2 (gastric), not isoform 1 (lung) | KRAS carrying the G12C mutation | TNFSF15 ligand |
| **2. Authority resolves it?** | yes: `GPRC5D` → GPRC5D | yes: `FcRn` → **FCGRT**, unique alias | **no**: `CLDN18` resolves; `CLDN18.2`, `Claudin 18.2` and `Claudin` do not. No isoform entity exists | `KRAS` yes; `G12C` and `KRAS G12C` no. No variant entity exists | yes: `TL1A` → TNFSF15 |
| **3. Where it is lost** | parser: the whitespace token is `GPRC5D-directed`; the resolver receives the whole hyphenated token → UNRESOLVED | same: `FcRn-blocking` | the tokens are `Claudin` and `18.2-directed`. Neither n-gram resolves, and the isoform has no entity | **not refused, but broadened**: compiles to `KRAS`, and `G12C` becomes free text | compiles correctly |
| **4. Correct representation** | `TARGET:GPRC5D` | `TARGET:FCGRT`. Every FcRn blocker binds the FCGRT α-chain; B2M is shared with MHC-I and must not be added | `TARGET:CLDN18` **plus** an isoform constraint (18.2). Not representable today | `TARGET:KRAS` **plus** a variant constraint (G12C). Not representable today | `TARGET:TNFSF15` |
| **5. Effect of resolving** | preserves | preserves | collapsing to CLDN18 would **broaden** (losing the isoform constraint) → must fail closed | the current behaviour already **broadens**. The diagnosis shows the existing control is semantically incorrect | preserves |

## 2. Population study (offline, frozen sample)

The sample is every 40th target of the pinned snapshot (1,960 targets), taking each target's
symbol and a short alias. Each name was placed in six query frames and parsed with the
current parser.

| Frame | Symbol | Alias |
|---|---|---|
| bare (`X therapies`) | 1937/1960 (0.99) | 711/784 (0.91) |
| `X inhibitors` | 0.99 | 0.91 |
| **`X-directed`** | **0/1960** | **0/784** |
| **`X-targeting`** | **0** | **0** |
| **`X-blocking`** | **0** | **0** |
| **`anti-X`** | **0** | **0** |

The negative controls (20 ordinary, modality, disease and non-target biomedical words × 6
frames) produced 0 targets out of 120.

**Root cause, general rather than query-specific.** The parser hands every
whitespace-delimited token, including a hyphenated affix, to the resolver as one string.
The only intra-token separators it splits on are dual-target joins (`/`, `x`). So **every**
target written in the most common biomedical modifier forms (`anti-X`, `X-directed`,
`X-targeting`, `X-blocking`) is refused, for every target in the ontology. H1 and H3 are two
instances of this; it has nothing to do with GPRC5D or FcRn.

## 3. Separate defects (recorded, not part of v1)

- **D-iso.** Isoform-specific targets (CLDN18.2) cannot be represented. They must fail closed
  until an isoform-constraint representation exists. Collapsing to CLDN18 is not allowed.
- **D-var.** Variant-specific targets (KRAS G12C) compile to the bare gene and silently drop
  the variant. This is a semantic broadening in an existing control. It needs its own
  milestone: either a variant constraint, or failing closed with a warning.
- **D-amb.** Some common target names resolve as AMBIGUOUS in this snapshot (for example
  `PD-1` → PDCD1/RPL17, `CD20` → MS4A1/KRT20). That is the existing fail-closed behaviour and
  v1 leaves it as it is.

## 4. Recommendation

Fix the general affix defect now (§5). Keep D-iso and D-var as separate preregistered
milestones. H5 is therefore **expected to stay refused** after v1, and that is the correct
outcome until D-iso is addressed.

## 5. TARGET_AFFIX_RECOGNITION v1 — preregistration

**Rule (frozen).** In target matching, a single token that does **not** resolve as a whole
(neither RESOLVED nor AMBIGUOUS) is retried once with exactly one affix removed from a closed
grammar.

```
prefix:  anti-
suffix:  -directed | -targeted | -targeting | -blocking | -binding | -specific
```

Matching is case-insensitive, and the remainder must be non-empty.

- The remainder goes to the **same** `resolve_target`.
- RESOLVED creates a TARGET span covering the whole token.
- AMBIGUOUS creates an AMBIGUOUS_TARGET span (fail closed, as for bare tokens).
- Anything else leaves the token as free text.
- No new vocabulary, no aliases and no query-specific names.
- Multi-word phrases are unaffected: only single tokens are retried, matching the existing
  single-token target rule.

**Frozen extra negative controls** (affixed forms of non-targets): anti-inflammatory,
anti-tumor, anti-cancer, tumor-directed, cancer-targeting, cell-directed, T-cell-directed,
antibody-directed, drug-binding, disease-specific, patient-specific, B-cell-directed,
anti-drug, liver-targeted.

**Acceptance (scored offline; no replays needed because the change is compile-time):**
- **AR1.** In the frozen population sample, for every affixed frame, a name is recognized
  as target T **if and only if** its bare frame recognizes it as T. Recall equals bare recall
  exactly, and no affixed frame yields a different target.
- **AR2.** Negative controls: the original 120 plus the 14 extra affixed controls produce
  **0** targets.
- **AR3.** H1 compiles to exactly `[GPRC5D]` and H3 to exactly `[FCGRT]`. H5 is still refused
  (D-iso).
- **AR4.** The parsed intent for the TAC01, mint5, H2 and H4 queries is identical before and
  after: targets, operator, spans and warnings.
- **AR5.** An affixed form of an AMBIGUOUS name (`anti-CD20`, `PD-1-directed`) produces an
  AMBIGUOUS span, never a RESOLVED target.
- **AR6.** `tests/se` and ruff pass.

**Stop condition.**
- **Adopt** if AR1–AR6 all pass.
- **Otherwise** revert. Do not extend the affix grammar.
- Generalization is judged only on H6–H10.

## 6. Result — TARGET_AFFIX_RECOGNITION v1, 2026-10-09: FAILED_ACCEPTANCE, reverted

**Scorer:** `scripts/score_target_affix_recognition_v1.py` → `research/se_heldout/affix_stage_ar_v1.txt`.
**Implementation:** applied to the working tree only, never committed, and reverted. The
revert restores the baseline parses byte for byte.

| Criterion | Result |
|---|---|
| **AR1** | **FAIL.** 10,881 of 10,888 affixed parses equal the bare parse. 7 mismatches, from 2 names. |
| **AR2** | PASS. 0 of 134 negative controls produce a target. |
| **AR3** | PASS. H1 → `[GPRC5D]`, H3 → `[FCGRT]`, H5 still refused. |
| **AR4** | PASS. TAC01, mint5, H2 and H4 parse identically. |
| **AR5** | PASS. `anti-CD20` and `PD-1-directed` produce AMBIGUOUS spans. |
| **AR6** | Not run, because AR1 had already failed. |

**The 7 AR1 mismatches** both come from tokenization that runs before the affix retry:

1. **`IGKV1/OR1-1` + affix, ×4.** The dual-target tokenizer splits on `/`. The second piece,
   `OR1-1-directed`, loses its affix and resolves `OR1-1`, an alias of **OR4F3**. That is a
   **wrong target**, so the rule can manufacture false targets from slash-containing names.
2. **`14q(II-21)` + suffix, ×3.** The bare frame is not recognized: the parenthesis cleaning
   in `_clean` breaks the name. The affixed token survives cleaning and resolves to
   SNORD114-21. This is a recall difference, not a wrong target, but it breaks the frozen
   "if and only if" rule.

Following §5's stop condition, **v1 is reverted, and the affix grammar is not extended or
tuned.**

**Diagnosis stands.** Affixed target language is refused for every target. H1 and H3 remain
refused at HEAD.

**What a v2 would have to settle before preregistration (operator decision):**
- the affix retry has to run **before** dual-target splitting, or skip tokens containing a
  join separator;
- whether AR1 should require "affixed ⊆ bare-or-equal" (no new or different target), rather
  than strict equality, given that case 2 is a pre-existing bare-frame tokenization defect.

**Benchmarks touched:** none. Nothing was replayed. H6–H10 are untouched.

## 7. TARGET_AFFIX_RECOGNITION v2 — preregistration (2026-10-09)

The v1 result and its population (§2, §6) are preserved unchanged.

**Rule.** The rule is v1 §5 (same closed affix grammar, one affix, one retry, only when the
whole token does not resolve), plus two path constraints:

- **S1. Separator exclusion.** No affix retry when the **original whitespace token** contains
  a dual-target separator (`_TARGET_JOIN`: `/`, `×`, or `x` before a capital letter). Such
  tokens go through the existing multi-target logic unchanged. The retry is never run before
  the splitter.
- **S2. Path equivalence.** The affix remainder goes through the same `_clean` normalization
  as a bare token before `resolve_target`. An affixed expression can therefore never get past
  a bare-path limitation: `14q(II-21)-directed` cleans to the same string as bare
  `14q(II-21)`, and so stays unresolved.

**Frozen population.** `research/se_heldout/affix_population_v2.json`, built by
`affix_population_v2.py` before any v2 code (sha256
`28cb3aabb544589a5a4050b90169bb60a38190e1a05fc9d0951a2b907c5e9e38`), with 7,329 names:
- a new sample: every 40th target at offset 20, which is disjoint from v1;
- every v1 sample name;
- every snapshot alias of 24 characters or fewer that contains a dual-target separator (1,430)
  or a parenthesis (467).

It also stores each name's bare-frame parse (targets and ambiguous candidate sets) at
`ab7ace9`.

**Acceptance (strict, no weakening):**
- **AV1. Metamorphic parity.** For every population name B and each wrapper W ∈ {`B-directed`,
  `B-targeting`, `B-blocking`, `anti-B`}, `parse(W(B))` equals the frozen `parse(B)` exactly:
  the same target ids and the same ambiguous candidate sets. Resolved stays identical,
  ambiguous stays ambiguous, unresolved stays unresolved. **Zero** mismatches are allowed.
- **AV2.** 0 of the 134 negative controls (v1 §2 plus §5's 14) produce a target.
- **AV3.** H1 → exactly `[GPRC5D]`; H3 → exactly `[FCGRT]`, never B2M; H5 refused; H2 parse
  unchanged (KRAS G12C defect untouched).
- **AV4.** TAC01, mint5, H2 and H4 parses are identical to `affix_controls_before_v1.json`.
- **AV5.** `anti-CD20` and `PD-1-directed` stay AMBIGUOUS.
- **AV6.** `tests/se` and ruff pass.

**Decision.**
- **If any of AV1–AV6 fails:** revert with no patching after the results.
- **If all pass:** adopt, then run H11–H15 (primary), then H6–H10 (secondary).

**Out of scope:** KRAS G12C variant semantics, Claudin 18.2 isoform semantics, and shortlist
pollution.

## 8. Result — TARGET_AFFIX_RECOGNITION v2, 2026-10-09: FAILED_ACCEPTANCE, reverted

**Scorer:** `scripts/score_target_affix_recognition_v2.py` → `research/se_heldout/affix_stage_av_v2.txt`;
breakdown in `affix_stage_av_v2_breakdown.txt`. The v2 code was applied to the working tree
only and is reverted. A copy is kept outside the repository.

| Criterion | Result |
|---|---|
| **AV1** | **FAIL.** 24,375 of 29,316 parses match. **All 4,941 mismatches are names containing a dual-target separator.** Plain names and parenthesis names: **0 mismatches** (S2 closed the `14q(II-21)` class). Separator-name mismatches: 4,457 target lost, 430 different target, 26 target gained, 28 ambiguity changed. |
| AV2 | PASS. 0 of 134 negative controls produce a target. |
| AV3 | PASS. H1 → `[GPRC5D]`, H3 → `[FCGRT]`, H5 refused, H2 unchanged. |
| AV4 | PASS. TAC01, mint5, H2 and H4 are identical. |
| AV5 | PASS. `anti-CD20` and `PD-1-directed` stay ambiguous. |
| AV6 | Not run, because AV1 had already failed. |

**Attribution of the AV1 failure (measured after the revert, on the unmodified parser at
`69f00e7`).** The same 4,941 mismatches, with the identical class counts, occur **without v2**
(`affix_v2_baseline_check.txt`). They are produced by the existing dual-target splitter, which
S1 deliberately leaves untouched. For example, `anti-ABP/ZF` splits into `anti-ABP` + `ZF`,
and `ZF` → CREBZF. v2 added **zero** mismatches of its own. The strict parity criterion
nevertheless measures the parser's end-to-end behaviour on affixed forms, and that behaviour
fails for separator names whether or not v2 is present.

**Decision.** Reverted, as preregistered, with no patching after the results. H11–H15 are
**not** run, and H1/H3 remain refused at HEAD.

**New finding, recorded as a separate pre-existing defect (D-sep).** Any affixed
slash-containing target name (430 different-target cases) makes the current splitter assert a
**wrong target**. This happens today on the production parser, independent of any affix work.
It is a correctness bug in its own right.

**Operator decision needed before any v3.** The AV1 population includes 1,430 separator names
whose affixed forms the parser cannot handle without changing the dual-target splitter, which
was ruled out of scope. Either:
- fix D-sep first, as its own milestone (the splitter must not mint a target from a fragment of
  an affixed token), then re-run the affix work; or
- re-scope affix parity to a population that excludes separator names. That would weaken what
  "parity" covers, so it needs an explicit operator decision.

## 9. TARGET_AFFIX_RECOGNITION v3 — preregistration (2026-10-09)

**What changed since v2.** The dual-target separator defect (D-sep) is fixed and adopted
(`dual_target_separator_safety_v1.md` §10, `d830ae0`). Nothing else changed.

**Population (re-frozen, identical construction).** `research/se_heldout/affix_population_v3.json`
(sha256 `48d2999d95ec700acaeceafa3c997b4fb6f22981c03c8b7d8273ebb627b97f84`), built by
`affix_population_v3.py` at `d830ae0` with the same 7,329 names and bare parses at that commit.
The control baseline `affix_controls_before_v3.json` is identical to
`affix_controls_before_v1.json`.

**Rule.** The **identical** v2 rule (§7: closed affix grammar, S1 separator exclusion, S2
path equivalence), re-applied byte for byte from the reverted copy.

**Acceptance.** AV1–AV6 are **unchanged** from §7, scored by
`scripts/score_target_affix_recognition_v3.py`:
- **AV1:** strict parity, with zero add, substitute or lose;
- **AV2:** 0 of 134 negative controls produce a target;
- **AV3:** H1 → [GPRC5D], H3 → [FCGRT] only, H5 refused, H2 unchanged;
- **AV4:** TAC01, mint5, H2 and H4 identical;
- **AV5:** ambiguous names stay ambiguous;
- **AV6:** full `tests/se` and ruff.

Adopt or revert strictly. If adopted, run H11–H15 untouched.

## 10. Result — TARGET_AFFIX_RECOGNITION v3, 2026-10-09: FAILED_ACCEPTANCE, reverted

**Scorer:** `scripts/score_target_affix_recognition_v3.py` → `research/se_heldout/affix_stage_av_v3.txt`;
breakdown in `affix_stage_av_v3_breakdown.txt`. The identical v2 hunks were re-applied
(verified byte-identical) and then reverted. H11–H15 were **not** run.

| Criterion | Result |
|---|---|
| **AV1** | **FAIL.** 23,615 of 29,316 parses match. All 5,701 mismatches are separator names: 5,648 target **lost**, 53 ambiguity changed. **0 different, 0 gained.** Plain and parenthesis names: 0 mismatches. |
| AV2 | PASS. 0 of 134. |
| AV3 | PASS. H1 → [GPRC5D], H3 → [FCGRT], H5 refused, H2 unchanged. |
| AV4 | PASS. TAC01, mint5, H2 and H4 identical. |
| AV5 | PASS. |
| AV6 | Not run, because AV1 had already failed. |

**Why.** After D-sep, wrong targets are gone. But strict parity also forbids **losing** a
target, and S1 (no affix retry on separator tokens), set by the operator in v2, makes every
affixed separator name unresolved. For example, `12/15-lipoxygenase` gives ALOX15, while
`12/15-lipoxygenase-directed` gives ∅. So S1 and strict parity are jointly unsatisfiable for
the 1,430 separator names. That was predictable from v2 §8 and should have been caught before
preregistering v3.

**Operator decision needed for v4:**
- (a) **Allow the affix retry on a separator token only for the whole-name path:** strip the
  affix, then resolve the **whole** remainder by the authority (the D-sep WHOLE rule). It never
  splits. A miss stays unresolved. This keeps the S1 intent (no affix handling inside the
  splitter), but S1 as worded forbids it.
- (b) Keep S1 and **scope parity to non-separator names**, reporting separator names as
  "may lose, never add or substitute".

## 11. TARGET_AFFIX_RECOGNITION v4 — preregistration (2026-10-09)

**Operator decision.** Strip the **outer** affix first, then pass the resulting expression
through the **existing bare-name parser** unchanged. An affix is never stripped from an
individual separator fragment. This makes parity hold by construction:
`parse(W(B)) = parse(B)`.

**Rule (frozen).** Before any span matching:
1. for each whitespace token, take its cleaned core (`_clean`);
2. if the core fully matches the closed affix grammar (`anti-X` |
   `X-{directed,targeted,targeting,blocking,binding,specific}`), **and** the core as a whole
   does not resolve (RESOLVED or AMBIGUOUS), **and** the remainder is non-empty and not a
   stopword,
3. then the affix characters, including their hyphen, are replaced by spaces in a working copy
   of the query. The copy keeps the same length, so every span offset still indexes the
   original query, and `original_query` is unchanged.

The working copy is then parsed by the existing pipeline: separator safety, dual-target
reading, n-grams, everything. There is no other change: no S1/S2 special cases, no retry
inside the splitter, and no new vocabulary.

Examples:

| Input | After stripping | Bare parser result |
|---|---|---|
| `12/15-lipoxygenase-directed` | `12/15-lipoxygenase` | ALOX15 |
| `CD19/BCMA-directed` | `CD19/BCMA` | CD19 + BCMA |
| `anti-CD20` | `CD20` | AMBIGUOUS |

**Population.** `affix_population_v3.json` (frozen at `d830ae0`). No `src/` change has
been made since, so its bare parses are still current. Same controls.

**Acceptance.** AV1–AV6 are unchanged, **with AV1 strict** (zero add, substitute **or lose**),
scored by `scripts/score_target_affix_recognition_v3.py`. Adopt or revert strictly. H11–H15
stay untouched until then.

## 12. Result — TARGET_AFFIX_RECOGNITION v4, 2026-10-09: FAILED_ACCEPTANCE (AV6), reverted

**Scorer:** `scripts/score_target_affix_recognition_v4.py` → `research/se_heldout/affix_stage_av_v4.txt`.
The code was applied to the working tree only and is reverted. A copy is kept outside the
repository. H11–H15 were **not** run.

| Criterion | Result |
|---|---|
| **AV1** | **PASS.** Strict parity holds for **29,316 of 29,316**, with 0 mismatches. |
| AV2 | PASS. 0 of 134. |
| AV3 | PASS. H1 → [GPRC5D], H3 → [FCGRT] only, H5 refused, H2 unchanged. |
| AV4 | PASS. TAC01, mint5, H2 and H4 identical. |
| AV5 | PASS. `anti-CD20` and `PD-1-directed` stay ambiguous. |
| **AV6** | **FAIL.** ruff is clean. `tests/se`: **1 failed**, 1,659 passed, 3 xfailed. |

**The one failing test** is `test_dual_target_separator_safety.py::test_a_fragment_of_an_unresolved_name_is_not_a_target`.
It asserts `anti-ABP/ZF` → ∅. Under v4, `anti-ABP/ZF` parses exactly as bare `ABP/ZF`, which
the authority resolves as a whole name to **TRPV6** (DUAL_TARGET_SEPARATOR_SAFETY's WHOLE
label). That is the parity the operator specified for v4, and TRPV6 is not a fragment
target.

I added that test after scoring DUAL_TARGET_SEPARATOR_SAFETY v3, and it was **not**
preregistered. It encoded the pre-affix behaviour (affixed separator names unrecognized), not
a correctness property, so its expectation conflicts with v4's specified semantics. AV6 was
frozen as "`tests/se` passes", so v4 fails as preregistered. Editing the test after the
results would be post-hoc, so I did not.

**Operator decision needed:**
- replace that test's example with a genuine fragment case that v4 leaves unchanged (for
  example `AK/ATPase` → never ADK); then
- re-run AV6 alone on the byte-identical v4 code. AV1–AV5 are already measured and would not
  be re-run.

## 13. TARGET_AFFIX_RECOGNITION v5 — preregistration (2026-10-09)

**This is a clean new cycle, not a retroactive adoption of v4.**

**What changed since v4.** Only the invalid post-hoc regression test was corrected, in its own
commit (`6ca30f5`):
- `anti-ABP/ZF → ∅` was replaced by a genuine fragment-safety case: `AK/ATPase` and its
  affixed forms must never give ADK, and bare `AK/ATPase` gives AK6;
- the commit message explains why the old test was invalid.

**Production code.** Byte-identical to v4. `src/bve/se/intent/parser.py` is restored from the
saved v4 copy, sha256 `c4ce8d99509be2438de9abee087cead5a2abfd4838356b7f6eeb459f1ed95fad`. No other `src/` change has been made since `d830ae0`.

**Population and criteria.** Unchanged:
- population: `affix_population_v3.json`, with the same controls;
- **AV1–AV6 are all re-run together** with `scripts/score_target_affix_recognition_v4.py` and
  the full `tests/se` plus ruff; none of the earlier v4 measurements is reused.

Adopt or revert strictly. If adopted, run H11–H15 untouched.
