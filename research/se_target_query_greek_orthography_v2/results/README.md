# TARGET_QUERY_GREEK_ORTHOGRAPHY v2 — FAILED

Preregistration `8ee443a`; unmodified candidate `e3ad3fd`. G3, G5, G6 and G9 fail. No post-result behavior or expected-label changes. Normal revert is required; see the subsequent restoration record for its commit and verification.

## Observed results

- 704/704 raw query-target oracle outcomes match; all 704 original global resolver status/entity/candidate outcomes remain unchanged.
- All 4,032 non-proposal parser frames preserve their frozen scientific fields/spans/provenance.
- All three multi-gene groups remain non-resolving for their new Greek spellings.
- 21/672 Greek query frames add an unrelated target: three distinct names, each repeated across seven frozen affix frames.
- Full tests/se: **1,926 passed, three failed, three existing xfails**. Ruff clean. The 103 current compatibility cases and 1,791 historical source checks pass.
- Synthetic outputs are identical under seeds 0/1/42.
- The exact H17 query compiles offline to TARGET:IL4R and three search plans without namespace literals. Factor XI remains unresolved. No engine run, asset retrieval, replay or generalization test was performed.

## First scientific failure boundary: authority-name ownership

| Full authority name / intended target | New internal alias interpreted independently | Wrong added target |
|---|---|---|
| MHC class I antigen HLA-B α chain / HLA-B | α chain → authority alias alpha-chain | FCGRT |
| C3 and PZP-like α-2-macroglobulin domain-containing protein 4 / C5 | α-2-macroglobulin → Alpha-2-macroglobulin | A2M |
| CD8 β opposite / SMYD1 | CD8 β → CD8beta | CD8B |

Each whole Greek name resolves correctly when submitted directly to the candidate. Instrumented parser traces show that none is submitted in full. The main loop has MAX_NGRAM=5 but skips **target** resolution when `size > 2`. It therefore recognizes smaller aliases while losing the identity established by the containing authority name. Some unrelated targets already existed in baseline parses; the 21 failures count new additions only. Both before/after spans and resolver calls are frozen in `first_boundaries.json`.

Among the 90 names with certified biological reference identities, bare-query exact target lists increase from 3 to 31. This descriptive improvement does not satisfy precision acceptance. H17 success is development evidence only. The engine is not validated.

## Separate failures

- `_TARGET_JOIN` requires an ASCII alphanumeric character before `/` or `×`. Thus Greek-ending compound targets fail two frozen parser controls. Changing that grammar was outside this candidate's allowed scope; no patch was made.
- One synthetic expected ambiguous candidate ID was wrong. The frozen fixture expects TARGET:GQ32, but the installed resolver elects TARGET:GQ31 for that merged component. Actual ambiguity is safely retained; the literal expected candidate set still fails. Preserve this as a preregistration error, not a passing test.

## Correction to earlier technical descriptions

The actual `_elect_symbol` predicate is `record.canonical_symbol and record.source not in by_source`. It keeps the **first** symbol per source, not the last. Earlier descriptions saying it overwrote earlier symbols, and the synthetic fixture's last-symbol assumption, were incorrect. The underlying diagnosis remains: it considers only one symbol per source when checking disagreement, so same-source multi-gene records can be missed. Seven distinct approved gene identities and all captured authority evidence remain unchanged. Do not silently edit historical artifacts to conceal this correction.

## Next priority

After reverting, perform **TARGET_QUERY_AUTHORITY_SPAN_BOUNDARY_DIAGNOSIS v1**, diagnosis/design only. Freeze each false addition's first failure boundary and compare complete authority-name ownership with embedded aliases across existing positive/negative controls. Inspect the reason for the two-token target limit, existing grammar/modality/indication precedence, family/complex safeguards, and qualifier/relational names. Do not merely increase the n-gram limit or blacklist these phrases. Establish a general safe ownership rule before another alias implementation.

Unicode separator coverage is a separate prerequisite after the scientific ownership boundary is understood. Future synthetic oracles must validate that every expected canonical ID exists in the baseline fixture; do not infer election order from memory. Keep common-name admission, human-PoC recovery, ranking, qualification and duplicate work separate. H21–H25 remain untouched; H6–H10 remain secondary/unrun.

The recorded evaluation/trace scripts depend on candidate code. Reproduce them against `e3ad3fd`, with the fixed repository path used by the research scripts. Do not report their candidate outputs as restored-HEAD outcomes.
