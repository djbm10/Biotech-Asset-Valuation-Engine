# S&E Evidence-First Vertical Slice — Claude Handoff

Updated: 2026-07-11 (corpus-acquisition sprint)

## Sprint update — corpus evidence coverage (2026-07-11)

The bottleneck was corpus construction, not query formulation. A generic acquisition layer now
builds the public corpus by target+modality only (never asset names), and corpus evidence coverage
jumped from 3/21 to **19/21 (GOLD 5/5, SILVER 14/16)**. The two residual SILVER misses (MK-1045/CN201,
MK-6070/HPN217) are precisely classified as *retrieval — mechanism-bearing evidence exists only in
company/conference sources*, one SILVER short of the release gate. Full run report:
`research/se_benchmarks/cd19_bcma/development/corpus_coverage_run_2026-07-11.md`. New code:
`src/bve/se/acquisition/`, `src/bve/se/evaluation/corpus_coverage.py`, CLI `bve-se-acquire`.

## Objective

Build an auditable buyer-specific biotech Search & Evaluation system:

> Given a precise buyer gap, discover the coverage-measured public universe, resolve asset
> identities, apply evidence-backed PASS/FAIL/UNKNOWN gates, rank only confirmed eligible assets
> within comparable cohorts, and explain every material conclusion with citations.

This is not a valuation or rNPV workflow. Do not add scoring sophistication while retrieval and
evidence coverage are failing.

## Current stopping point

The system is safe but not yet effective. The autonomous YAML-driven development run found only
3 of 21 benchmark assets:

- GOLD recall: 2/5 (40%).
- SILVER recall: 1/16 (6.25%).
- Total recall: 3/21 (14.3%).
- Candidates returned: 36.
- Residual duplicate normalized names: 6.
- False exclusions: 0 (no candidate reached confirmed exclusion).
- UNKNOWN routing: 36/36 unresolved candidates routed (100%).
- Connector crashes: 0.
- Required-source coverage: incomplete; the configured source index is only a small fixture corpus.

The 18 missing records are retrieval failures for this run because their evidence is absent from
the configured snapshots/index. This does not prove that public sources lack the programs.

The expanded alias-query pass did not add benchmark identities for the same reason. Code must not
be frozen and the hidden holdout must not be opened.

Detailed run report:

`research/se_benchmarks/cd19_bcma/development/autonomous_discovery_run_2026-07-10.md`

## Benchmark artifacts

Development reference universe (21 rows; 7 CD19, 14 BCMA):

`research/se_benchmarks/cd19_bcma/development/reference_universe.csv`

Miss matrix (21 rows, expected source/adapter/query/evidence state):

`research/se_benchmarks/cd19_bcma/development/miss_matrix.csv`

Benchmark governance:

`research/se_benchmarks/cd19_bcma/benchmark_manifest.yaml`

The reference universe contains five GOLD primary-verified records and 16 SILVER records requiring
independent status/ownership refresh. SILVER records are development retrieval targets, not
production-trusted current-status evidence.

## Private holdout rule

Never copy, inspect, or commit `holdout_labels_private.csv`. It is intentionally outside the
repository. The holdout may be evaluated only after development recall and identity quality meet
the release thresholds, code/configuration are frozen, and the evaluation protocol is fixed.

## What has been implemented

Bounded context: `src/bve/se/`

- Strict BuyerProblem v2, evidence, claim, fact, gate, review, run, cohort, and ranking contracts.
- CD19/BCMA and T-cell-engager ontology.
- CT.gov, PubMed, indexed-document, URL, frozen, and unavailable-source adapters.
- Content-addressed snapshots and run manifests.
- Iterative discovery/convergence and source-attempt logging.
- Reversible identity merges and temporal ownership records.
- Claim-level evidence ledger and citation-entailment checks.
- Three-state hard gates with UNKNOWN review routing.
- Clinical-result records, comparable-cohort assignment, and meaningfulness assessment.
- Pairwise within-cohort ranking foundations with abstention.
- JSON/memo reporting and offline CLI.

Recent changes in this sprint:

- Query compiler now expands target and modality aliases, including TNFRSF17/CD269, CD3/CD3E,
  TCE, BiTE, bispecific, and trispecific.
- CT.gov search uses expanded terms for broad retrieval while retaining canonical target checks.
- Protocol-level target/modality text is no longer assigned to every background intervention in a
  combination study.
- Same named assets are merged deterministically across multiple trials while retaining trial IDs
  and provenance.

## Required next work: retrieval only

1. Populate the declared source corpus with primary evidence for the 18 missing benchmark records:
   ClinicalTrials.gov records, company pipeline/press pages, SEC filings, DailyMed labels, PubMed,
   and ASH/ASCO/AACR/EHA abstracts as appropriate.
2. Run the miss matrix row by row and record whether the expected evidence is present/indexed.
3. Ensure discovery follows this loop without benchmark-name seeding:

   target/modality query → asset alias extraction → sponsor/trial-ID extraction → alias/sponsor/trial
   searches → repeat until two complete passes add no new identities.

4. Improve asset-name extraction so trial titles, generic “BCMA/CD3 bispecific” labels, dose-level
   names, and background/supportive interventions do not become canonical assets.
5. Recompute duplicate identities after retrieval improves. Target: zero duplicate canonical assets.
6. Classify every remaining miss or false positive as retrieval, ontology, extraction, identity,
   temporal-status, or gating failure.
7. Rerun the YAML-only command and report GOLD/SILVER recall, duplicates, false exclusions, UNKNOWN
   routing, source coverage failures, and classifications.

Do not proceed to clinical ranking, scoring refinement, or holdout evaluation until approximately:

- GOLD recall 5/5.
- SILVER recall at least 15/16.
- False exclusions 0.
- Duplicate canonical assets 0.
- Every residual miss and false positive specifically classified.

## Reproduction command

Use the buyer YAML only; do not pass an assets/reference file:

```bash
MPLCONFIGDIR=/tmp/mpl PYTHONPATH=src python -m bve.cli.se_search \
  --problem examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml \
  --offline \
  --snapshot-dir research/se_benchmarks/cd19_bcma/development/snapshots/clinicaltrials_gov \
  --pubmed-snapshot-dir research/se_benchmarks/cd19_bcma/development/snapshots/pubmed \
  --source-index examples/configs/se/source_index_fixture.yaml \
  --format json \
  --output /tmp/se_dev_run.json
```

Validation currently passes:

```bash
python -m pytest tests/se -q       # 70 passed
python -m mypy src/bve/se
python -m ruff check src/bve/se tests/se
```

## Important interpretation

Passing tests and static checks demonstrate code quality only. They do not demonstrate autonomous
discovery coverage. The benchmark exposed that the current run is mostly searching an insufficient
preloaded corpus rather than constructing the public universe. Retrieval coverage is the current
product bottleneck.
