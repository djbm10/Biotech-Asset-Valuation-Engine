# TARGET_QUERY_AUTHORITY_SPAN_BOUNDARY_DIAGNOSIS v1

Status: diagnosis only; frozen scope before additional measurements, 2026-10-12.
Baseline: de33df6, with Greek v2 candidate normally reverted in 9a7cdeb.

## Question and population

Why does an exact authority name fail to own its complete query span, allowing another target's shorter alias to be asserted inside it? Use all 96 existing Greek proposal/original-authority pairs and their frozen biological references from `research/se_target_query_greek_orthography_v2/query_reference.json`. The three failed names are diagnostic examples, not exceptions. No new expected answers or holdout queries are introduced.

Trace the restored parser on both original and Greek spellings in all seven already frozen survey frames. Record every target-resolver invocation, full-name authority resolution, emitted spans and target references. Preserve source identity abstentions. Compare the observed boundaries against adopted alias-fragment, separator and affix policies. Inspect grammar/status/modality/evidence role precedence and the original target-length restriction in git history.

## Interpretation limits

A complete authority match is an identity claim, not proof that its occurrence in an arbitrary query is a requested target. A shorter independently valid alias is not proof that its occurrence inside a different complete scientific name refers to that alias's entity. An ambiguous longer name must not become permission to select a shorter claimant. Whole-name ownership, biological identity and query grammatical role require separate treatment.

This is not preregistration of a behavior change. No parser, ontology, acquisition, ranking, qualification, identity or efficacy behavior may change. No live runs, replays, H6–H10 or H21–H25. Human-PoC recovery remains stopped. Do not repair frozen oracle errors from either failed Greek study.

## Output and stop boundary

Produce per-name traces and a summary distinguishing tokenization/length limits, prior role consumption, authority ambiguity and nested target assignments. Identify the minimum design still needed for atomic authority-span ownership without unrestricted substring inference. Implementation needs its own frozen controls and preregistration; do not implement a raised n-gram limit or name-specific suppression in this diagnosis.
