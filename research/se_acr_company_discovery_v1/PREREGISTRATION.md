# ACR/company discovery v1 — preregistration

Frozen before new searches, connector implementation, retrieval and outcome measurement.
Date: 2026-10-24 UTC (2026-10-23 America/New_York). Base: 58432ad.

## Strategic question

Which named investigational CD19- or BCMA-directed T-cell engager antibody programmes
are being developed for autoimmune disease, and which have primary-source evidence
worth an analyst investigating? ANY target, not an AND requirement. Clinical Phase 1+
is the desired diligence population; earlier programmes may be discovery leads but may
not be called scientifically eligible. Human efficacy, ownership, territorial rights and
availability are unknown unless independently established. A registered/planned trial is
not clinical proof of concept.

## Search and resource envelope

`search_spec.json` contains exactly four generic search-engine queries. Execute each once,
in declared order, long response. No asset names, sponsor names, known product URLs,
reference aliases or authority-seeded names may enter a search. Save the complete returned
search response before selecting URLs. No adaptive queries to improve results.

Select URLs in returned rank order: at most 12 distinct ACR abstract pages from queries
1–2 and at most 12 distinct official drug-developer pipeline/product/news pages from queries
3–4. Deduplicate exact URLs, strip fragments only. ACR requires acrabstracts.org/abstract/.
Company inclusion requires an issuer-controlled site, including its investor subdomain;
exclude news publishers, syndication services, journals, social media, trial registries,
consultancies, aggregators, investor commentary and PDFs. Log every considered URL and
include/exclude reason, including cap exclusions. If publisher ownership is unclear, exclude.
No follow-link expansion during acquisition. Fewer than 24 pages is allowed; never replace
failed pages or backfill with known reference URLs. Asset-named URLs returned naturally by
the fixed generic queries are discoveries, not query seeds.

Existing DeclaredUrlConnector, CorpusStore and extract_observed_asset_names must be reused.
Every page is fetched once through the bounded public HTTP boundary; retain raw HTML,
URL, SHA-256, observation time, parsed text and error receipts. At most 2 MiB per page,
timeout (5,20) seconds, no added retries beyond existing bounded HTTP policy. Sequential
execution, 4 GiB process virtual-memory limit and 20-minute process timeout. No full engine
landscape replay, live CT.gov/PubMed crawl, paid API, cloud provisioning or new dependencies.
Use actual observation date for undated pages; do not backdate them. Index acceptance is
separate from primary-evidence adjudication. Dates after study as_of are inadmissible.

## Leakage boundary

The operator has seen the prior reference and failures; this is an EXPOSED DEVELOPMENT
reference, not blinded generalization or independent recall. Copy its labels and baseline
found/not-found annotations into evaluation/reference.json before search. Acquisition and
nomination code must accept only search_spec and selected SERP URLs, never reference paths,
names or labels. The original reference files remain unchanged. Tests must demonstrate
identical nominations with evaluation labels removed/changed. Freeze nominations and raw
acquisition hashes BEFORE opening them alongside evaluation labels for scoring.

Do not patch nomination/qualification/aliases/modality/PoC after seeing outcomes. Record
misses as failures. No manually supplied candidates in source records. Names recovered only
by the evaluator reading a page, but absent from the existing extractor, are not successes.

## Labels and evidence requirements

Frozen reference categories retain their existing exact values. For this study, primary
success requires ALL of:
1. Prior reference label RELEVANT_INVESTIGATIONAL and fully_verified=true; absent from the
   old A_base nominated population (the frozen metrics, not just its displayed top ten).
2. Existing extractor nominates the exact name or an already-frozen alias from a successfully
   acquired primary page reached through one of the four generic queries.
3. A dated primary issuer disclosure or ACR abstract explicitly links that named product
   to CD19 or BCMA, T-cell-engaging antibody format, autoimmune development, and an
   investigational development context. Disease rationale alone does not prove clinical
   testing. Generic constructs, bibliographic IDs, approved comparators, inferred targets,
   oncology-only evidence and non-primary summaries cannot satisfy this endpoint.
4. The supporting disclosure predates or equals the old baseline cutoff 2026-10-15, so a
   newly published post-baseline programme cannot be called a previously missed opportunity.
   Current retrieval still cannot prove that the page's bytes were available historically.
5. Exact supporting passages, source URL, raw-page hash and distinct query provenance are
   recorded. Quotes are manually adjudicated for product-specific entailment. Support from
   co-occurrence or adjacent programme text is insufficient. Negative/contradictory evidence
   must remain visible. Manual adjudication is explicitly not an engine gate decision.

Any asset outside the frozen reference is exploratory, not retroactively added to the primary
endpoint. An unfamiliar name can be recorded UNKNOWN pending independent primary evidence.
Known comparator and wrong-modality controls may be acquired/nominated but never count as
qualified research leads. Absence of an FDA match or an agreement never proves investigational
status or availability. Investigational context does not establish worldwide non-approval.

## Success criteria and reports

Primary development success: >=1 new qualifying, previously missing named investigational
lead under all five requirements, zero approved/generic/wrong-modality/unsupported entries
promoted as primary successes, and zero reference-name query seeding. Otherwise FAIL or
INCONCLUSIVE (source access/essential evidence unavailable). Do not change thresholds.

Report separately: search results; selected/attempted/fetched/indexed documents; literal
mentions nominated; normalized names; manually identified named drug assets; primary
endpoint successes; scientific eligibility (NOT_EVALUATED unless unchanged gates actually
run); confirmed BD opportunities/rights (UNKNOWN, never inferred). Report every failure,
excluded control and missing reference. This is a bounded source-recovery test, not a
comprehensive recall estimate or replacement for the sealed source-coverage experiment.

Final brief <=1,200 words, primary-source links, why investigate, what is supported/unknown,
clinical evidence caveats and next verification. Final independent BD review is outstanding
unless actually performed; implementing-agent desk review is not independent. No validation
grade promotion. H21–H25 sealed, H6–H10 unrun; parked experiments remain parked.
