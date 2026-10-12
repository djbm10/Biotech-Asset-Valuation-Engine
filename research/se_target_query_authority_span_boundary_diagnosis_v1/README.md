# Authority-span boundary diagnosis — first measurements

Baseline `2ff9604`; production equals the restored adopted target-reference baseline. No candidate code was loaded. Input hashes and all 1,344 parses are in trace.json: 96 frozen name pairs × two spellings × seven frozen frames. No holdouts, live acquisition or replay.

## Findings

- 67/96 names tokenize above the target-specific two-token cap. All 67 complete names are never offered in either spelling. The global five-token n-gram limit is not the operative target limit.
- One additional two-token name is altered by punctuation stripping: `(R)-beta-hydroxybutyrate dehydrogenase` becomes `R)-beta-hydroxybutyrate dehydrogenase`. Its Greek spelling has the same boundary. This is a separate exact-name preservation problem, not evidence for deleting qualifiers.
- The remaining 28 complete names are offered in all seven frames (196/672 per spelling). Being offered does not guarantee authority resolution or a certified single-gene identity.
- Original English names produce targets outside the frozen certified whole-name identity for 32 names / 224 frames. Greek names do so for 31 names / 217 frames on this restored baseline. These are pre-existing diagnostic mismatches, not new failures of the reverted candidate. The six uncertified references are excluded from this comparison.
- The three Greek-candidate failures have existing English analogues: HLA-B's full name emits HLA-C/HLA-B/FCGRT; C5's descriptive name emits C3/A2MP1/A2M; SMYD1's `CD8 beta opposite` emits CD8A. The complete English names independently resolve to HLA-B, C5 and SMYD1. None reaches the parser resolver in full.

## Existing policy and architecture

`be41c23` introduced the two-token cap. Both its commit message and docs/se_search_intent_layer.md explain the intent: avoid descriptive protein names pulling in whole families. The code comment says single tokens while the actual predicate allows two. This was a conservative heuristic, not an established biological equivalence rule.

At the n-gram pass, existing status, modality, evidence, disease-class and target-logic vocabularies claim spans before target lookup. Phases and grammatical negation are located earlier. Longest-first matching applies only within the finite n-grams considered. Indication interpretation is a later, separate layer. Existing separator safety establishes whole-name precedence only inside a single whitespace token containing a recognized separator. It does not own multiword authority names. The adopted fragment veto concerns the source's split-alias pattern and preserves all ambiguity claimants; it cannot generally detect a valid alias embedded in another entity's name.

## Design boundary — not an implementation contract

A safe next contract needs an atomic authority-name span record with exact original offsets, original/normalized surface, all identity claimants, source records and eligibility, plus a separate query-role decision. All longer authority claimants must be considered before resolving inner aliases, including ambiguous/ineligible claimants. Suppressing a claimant must never resolve another by removing ambiguity. Unknown role or ownership must abstain.

Exact scientific-name coverage must preserve parentheses, digits and qualifiers; it cannot use punctuation deletion to manufacture a different name. Name-internal `and`, slash or other operator-like text cannot automatically become a request for multiple targets. Conversely, an actual dual-target request must retain the adopted semantics. Overlapping, non-contained authority spans need a deterministic conservative rule. A longest-match heuristic alone does not establish a target query role or gene identity.

This representation can use existing IntentSpan offsets and TargetReference identities but requires a pre-resolution authority-span/role arbitration design. Raising MAX_NGRAM or the two-token cap is not a sufficient fix. No production extension is authorized by this diagnosis packet.

## Remaining work before preregistering behavior

Freeze general structural controls for complete descriptive names vs explicit multi-target requests, ambiguous longer names, family/complex names, clinical/biomarker roles, scientific parentheses and cross-role overlaps. Derive a deterministic arbitration contract and test it offline against the existing 96 pairs, original non-proposal controls and adopted affix/separator/indication controls. Do not use the failed Greek oracle as new expected truth. Generic alias source typing also needs review: a source SYMBOL label does not prove that an occurrence such as `alpha-chain` is a requested FCGRT target.

Greek v2 stays reverted. Human-PoC recovery stopped; qualification/ranking/duplicates unchanged. H21–H25 untouched and H6–H10 unrun. Implementation readiness: **NO** until the query-role/authority-overlap contract and controls are frozen and evaluated.
