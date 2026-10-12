# TARGET_MENTION_ROLE_REPRESENTATION v1

Status: PREREGISTERED before production implementation. Baseline `92e8f56`.

## Scope and API

Add one internal module `bve.se.intent.target_mentions`, with typed mention/authority/relationship/production-observation records and `analyze_target_mentions(intent: SearchIntent) -> TargetMentionAnalysis`. It accepts an already parsed intent. It is a separate diagnostic return value, not a new SearchIntent field; no parser/compiler/version/serialized decision changes. No automatic target projection, new resolver, new alias or source identity merge. Existing production decisions remain authoritative even when visibly wrong. No live calls/replays/holdouts.

The record separates exact occurrence, authority identity/status, geometric relationships, unadjudicated ownership, tentative role and observed production decision. Preserve original offsets/surface and lookup text separately. Resolved identity is the installed snapshot's identity, not a newly certified biological equivalence. Record source-symbol/gene conflicts without repairing them. Keep ambiguous and fragment-only claimants.

## Frozen enumeration and provenance rules

1. Enumerate all contiguous whitespace-token intervals in the original query and in its existing `_strip_target_affixes` view. Also enumerate intervals from the existing separator tokenizer for those two views. Retain original offsets. Each token contributes both original and existing `_clean`-trimmed edge boundaries; never clean the interior of a candidate or discard the untrimmed candidate. Resolve the original-query interval, not an invented phrase. Add the exact observed TARGET/AMBIGUOUS_TARGET lookup text/interval from the input intent, explicitly tagged production lookup; this preserves normalized legacy observations without admitting a new alias.
2. Keep intervals if the existing resolver returns RESOLVED/AMBIGUOUS or its existing `claimants_of` has a claim (including an ineligible split fragment). No arbitrary n-gram cap. Deduplicate only identical intervals and normalized lookup keys; preserve alternate lookup origins. No arbitrary character substring generation, new Unicode/separator normalization or qualifier deletion.
3. Resolution status/entity/candidates are the unchanged resolver's answer. For each claimant, enumerate all matching source-record symbols, labels and aliases under the existing normalized key; retain exact source spelling/type/key. Include sorted source record keys, canonical symbols, Ensembl IDs and identifier edges of its installed component. For direct canonical-ID lookup explicitly identify that basis and component records. Do not select one alias spelling from an unordered set; sort provenance. Source snapshot/version is mandatory. Missing snapshot returns no mentions with explicit unavailable status. A supplied intent from a different installed snapshot is rejected without mutation.
4. Record all pairwise geometric relations: strict contained/contains, same-extent equivalent (geometric only, never biological equivalence), crossing overlap, independent. Keep all containing mention IDs, not an elected parent. Ownership remains UNADJUDICATED for every emitted mention; geometry never assigns a target role.

## Role and production-decision semantics

Support the six distinct roles TARGET_CANDIDATE, TARGET_ROLE_CONFIRMED, EMBEDDED_BIOLOGICAL_MENTION, CONTEXTUAL_BIOLOGICAL_MENTION, AMBIGUOUS_ROLE and NON_TARGET_ROLE. Automatic annotations in this representation-only milestone are restricted to:

- contained by another authority-backed interval: EMBEDDED_BIOLOGICAL_MENTION, with containing IDs and explicit note that independence/ownership is unadjudicated;
- otherwise crossing another mention: AMBIGUOUS_ROLE;
- otherwise intersecting an existing non-target, non-residual production span: CONTEXTUAL_BIOLOGICAL_MENTION, preserving the observed span/rule and stating this is a production role claim, not independently certified role evidence;
- otherwise TARGET_CANDIDATE, meaning identity candidate with role unconfirmed, including ambiguous biological identities.

No automated TARGET_ROLE_CONFIRMED or NON_TARGET_ROLE records are emitted: the adopted parser provides no independent grammar certificate. These states must be representable with explicit role evidence for a future binder. Zero confirmed-role counts are expected, not a recall defect to tune. Identity ambiguity is reported separately, never used alone as a role classifier.

Record existing production spans using stable structural fields (offsets, kind, lookup text, resolved identity/symbol, rule and sorted candidates). Do not copy the known potentially unstable display-alias explanation as the new record's provenance; exact source-record alias evidence replaces that presentation dependency. A mention is currently decision-bearing ONLY if an existing TARGET span at exactly that interval selects the same installed canonical ID. AMBIGUOUS_TARGET links remain visible as blockers, not resolved target requirements. It may be both embedded and currently selected: this exposes existing mistakes without changing them. Roles never alter decision-bearing state.

## Frozen population and baselines

`research/se_target_mention_role_representation_v1/baseline.json` freezes complete parser/compiler/trial-query decision hashes under PYTHONHASHSEED=0 before implementation: all 1,344 diagnosis parses; all 48 structural controls; the complete 4,704 alias-survey parses; all 103 adopted scientific compatibility cases (including affix/separator controls). All 6,199 observations stay in the denominator, including duplicates. `required_mentions.json` freezes every supported/claimed interval from the prior 1,344-row audit, including all 32 English mismatches and the three protected Greek cases. Input hashes pin the old studies; S041/S042 labels are not corrected and are not used to force new decisions.

## Exact acceptance

- **R1 neutrality:** 6,199/6,199 exact canonical-JSON SHA256 decision hashes match baseline before and after analysis; input intent serialization and subsequent compiler/trial-query output unchanged. No metadata projection waiver is needed.
- **R2 completeness:** every frozen required interval/lookup key has a mention with matching status/entity/claimants. All required containing and contained spans coexist. No unexplained omission.
- **R3 provenance:** every claimant trace matches source-record data and installed component; exact offsets round-trip to original query. No unsupported entity/alias record. Ambiguous/fragment-only evidence retained.
- **R4 no promotion:** decision-bearing records have an exact matching existing TARGET observation. All other mentions remain non-bearing, regardless of role. No analyzer caller in parser/compiler/discovery/gates; no new producer of TargetTerm.
- **R5 determinism:** byte-identical canonical mention-analysis JSON on repeated analysis of every query and in independent processes with seeds 0, 1 and 42 for all 1,344 diagnosis parses plus 48 structural controls. Compare full new records, including provenance, not only counts. Existing parser display nondeterminism is not fixed or hidden by changing its outputs.
- **R6 controls:** all 103 adopted compatibility observations and 48 structural current decisions unchanged; existing focused affix/separator tests pass. The two bad historical expectations remain documented errors.
- **R7 no merges:** every mention identity/claimant equals an existing resolver entity ID; no graph/data changes. Same-extent relations explicitly mean geometric equivalence only.
- **R8 explainability:** all 224 English mismatch frames and 21 protected Greek frames contain their required spans, authority provenance, all containment relations and exact observed production bindings/rules. Summarize all 32+3 names individually.
- **R9 isolation:** source edits confined to the new module; tests/scripts/research/docs may be added. Existing production files, snapshot and other semantics unchanged.
- **R10 quality:** red-first focused tests, all non-xfail tests/se pass, Ruff clean on src/bve/se, tests/se and new scripts. Existing xfails retained.

Emit an immutable diagnostic ledger for every one of the 1,344 parses. Report one-mention/multiple/overlap/ambiguous-role/confirmed-role/embedded/authority-conflict query and mention counts, including zero-mention cases; do not tune toward them. Report snapshot unavailable and stale-input behavior in synthetic tests using arbitrary fixture entities, not new real-world aliases.

## Decision rule

Commit this policy, baseline and required intervals before implementation. Commit red tests before code; implement once; run focused/full/lint/frozen evaluation. Any failed acceptance criterion: preserve evidence, normally revert the candidate, do not patch after measured acceptance results or weaken neutrality. If all pass: adopt, record counts and limitations, update handoff; propose a separately preregistered later role/ownership decision milestone and stop. Human-PoC recovery remains stopped. H21–H25 untouched; H6–H10 unrun. No H17/H20 fix or new aliases.
