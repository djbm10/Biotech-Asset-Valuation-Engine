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
