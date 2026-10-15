# BD_DISCOVERY_SOURCE_COVERAGE_PILOT v1: preregistration

Development pilot. No change to gates, identity, target attribution, modality inference,
human-PoC, qualification, ranking or historical validation labels. H21–H25 stay sealed and
H6–H10 unrun. Frozen September runs are not touched.

## Questions (frozen in `research/se_bd_discovery_source_coverage_v1/problems/`)

Both questions share the same constraints:

- targets CD19 and TNFRSF17;
- modality `T_CELL_ENGAGER`;
- therapeutic area AUTOIMMUNE;
- minimum stage PHASE_1;
- as of 2026-10-15.

They differ only in how the targets combine:

- **Search A** (`bd_cov_A_cd19_or_bcma_tce`) uses `operator: ANY`.
- **Search B** (`bd_cov_B_cd19_and_bcma_tce`) uses `operator: ALL`.

The NL compiler refused both phrasings ("no biological target recognized"). The problems are
therefore derived from the MINT5 problem file, changing only the operator, modality, date and
human-PoC requirement. No AND requirement is ever loosened to OR: A and B are separate
questions.

## Source inventory (measured before outcomes)

One live acquisition (`bve-se-acquire`, 2026-10-15) ran on problem A's target and modality
queries. B has the same targets and modality, so it issues the same queries. Every built-in
connector ran, plus the existing declared company-pipeline manifest. Per-family health is in
`acquire_report.json`, and the source-index hashes are in `frozen_inputs.sha256`.

## Reference (frozen before any engine outcome)

`reference_raw.json` was built by an independent agent context that saw no repository file. It
was instructed to use fetched sources only.

- **Quotes:** every quoted passage (33/33) was re-fetched and verified verbatim by
  `verify_reference.py`.
- **Derived file:** `reference_frozen.json` is derived mechanically.
- **`fully_verified`:** an entry counts only if it is `RELEVANT_INVESTIGATIONAL` and has quoted
  identity, target, modality and indication.
- **CND261:** relabelled `UNSUPPORTED_LABEL`, because its target came from an unquoted search
  summary.
- **Exposed controls:** names seen in earlier demos are not independent successes.
- **Disclosure:** before freezing I saw titles from the newly acquired corpus (for example CC312
  and a CD19×CD20×CD3 trispecific). I added nothing to the reference from them. The reference
  file was produced before I opened the corpus.

## Comparison

- **Baseline arm:** a live `bve-se-search` run with native CT.gov and PubMed, plus a source
  index containing only `conference_aacr`. These are the families the earlier demos used.
- **Treatment arm:** the same sealed CT.gov and PubMed custody, replayed, plus the full source
  index from the same acquisition. That adds SEC filings, SEC-filed press releases, ASH, EHA,
  ASCO, FDA labels and declared pipeline pages.
- **Search B** replays the baseline custody under problem B with each index.

## Measures

The run-level measures are:

- incremental documents per family;
- new candidate mentions and new distinct candidates;
- reference entries found, by label;
- **fully verified relevant investigational assets found, baseline vs treatment** (the primary
  measure);
- approved comparators promoted to eligible;
- wrong-target or wrong-modality candidates that reach the review population;
- relevant assets still missing;
- source failures.

A reference entry counts as **found** when the engine nominates a candidate whose name or alias
equals one of the entry's names or aliases, after normalisation. Discovery is reported
separately from eligibility.

## Success criterion

The pilot succeeds only if the treatment arm finds **more fully verified relevant
investigational assets** than the baseline, with no increase in approved comparators or
wrong-target assets reported as eligible.
