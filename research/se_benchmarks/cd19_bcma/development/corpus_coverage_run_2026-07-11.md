# Corpus Evidence-Coverage Run — 2026-07-11 (corrected identity and declared sources)

Sprint: **source acquisition and ingestion** (not ranking, not holdout).
Decisive metric: does at least one supporting document exist in the corpus for each benchmark asset?

## Headline

| Metric | Prior discovery run (2026-07-10) | This corpus-coverage run |
|---|---|---|
| GOLD | 2/5 | **5/5** |
| SILVER | 1/16 | **16/16** |
| Total | 3/21 (14.3%) | **21/21 (100%)** |
| Release gate (GOLD 5/5, SILVER ≥15/16) | fail | **pass** |

The prior number was *discovery recall over an insufficient preloaded corpus*. This number is
*corpus evidence coverage* after running the new generic acquisition layer against live public
sources. Coverage is measured directly against the corpus, independent of discovery extraction and
ranking.

## What was built

Bounded context `src/bve/se/acquisition/` plus an evaluation module and a CLI:

- `corpus_store.py` — content-addressed `CorpusStore`. Every document carries source family,
  source URL, retrieval date, `as_of_date`, raw snapshot + content hash, `parser_status`, and
  `index_status`. Idempotent by content hash; JSONL manifest.
- `connectors.py` — generic connectors keyed **only** on the buyer's canonical target and modality
  vocabulary, never on asset names: `ClinicalTrialsGovConnector`, `FdaLabelConnector` (openFDA
  full-text over label prose), `PubMedConnector`, `SecEdgarConnector` (EDGAR full-text), and a
  `DeclaredUrlConnector` for company/press/conference pages, seeded through the versioned
  `declared_sources.yaml` source-location manifest.
- `source_health.py` — the five-stage decomposition that replaces "zero source failures":
  1 connector_succeeded · 2 query_returned_results · 3 required_evidence_present · 4 documents_parsed
  · 5 documents_indexed.
- `evaluation/corpus_coverage.py` — per-asset coverage against `reference_universe.csv`
  (evaluation only; asset names never re-enter acquisition queries).
- CLI `bve-se-acquire` and 14 offline tests (no network in tests; connectors inject fakes).

## Source health (five stages)

| Source family | connector ok | query results | required evidence | parsed | indexed | raw records |
|---|---|---|---|---|---|---|
| clinicaltrials_gov | ✅ | ✅ | ✅ | ✅ | ✅ | 664 |
| fda_label (openFDA) | ✅ | ✅ | ✅ | ✅ | ✅ | 11 |
| pubmed | ✅ | ✅ | ✅ | ✅ | ✅ | 579 |
| sec_edgar | ✅ | ✅ | ✅ | ✅ | ✅ | 25 fetched / 222 hits |
| company_press_release | ✅ | ✅ | ✅ | ✅ | ✅ | 3 |
| company_pipeline_or_presentation | ✅ | ✅ | — | ✅ | ✅ | 1 |

Stage 3 is now attributed across **all** families that hold matching evidence, not just the first
match — every configured family contributes required evidence for at least one benchmark asset.

## Per-asset coverage

| Benchmark | Tier | Asset | Covered | Matching families | Match token |
|---|---|---|---|---|---|
| DEV-CD19-001 | GOLD | blinatumomab | ✅ | ctgov, fda_label, pubmed, sec | blinatumomab |
| DEV-CD19-002 | GOLD | AZD0486 | ✅ | ctgov | azd0486 |
| DEV-CD19-003 | SILVER | MK-1045 (CN201) | ✅ | company_press_release | cn201 |
| DEV-CD19-004 | SILVER | CLN-978 | ✅ | ctgov, sec | cln978 |
| DEV-CD19-005 | SILVER | AMG 562 | ✅ | ctgov | NCT03571828 |
| DEV-CD19-006 | SILVER | AFM11 | ✅ | ctgov | afm11 |
| DEV-CD19-007 | SILVER | duvortuxizumab | ✅ | ctgov | NCT02454270 |
| DEV-BCMA-001 | GOLD | teclistamab | ✅ | ctgov, fda_label, pubmed | teclistamab |
| DEV-BCMA-002 | GOLD | elranatamab | ✅ | ctgov, fda_label, pubmed | elranatamab |
| DEV-BCMA-003 | GOLD | linvoseltamab | ✅ | ctgov, fda_label, pubmed | linvoseltamab |
| DEV-BCMA-004 | SILVER | ABBV-383 | ✅ | ctgov, pubmed | abbv383 |
| DEV-BCMA-005 | SILVER | alnuctamab | ✅ | ctgov, pubmed | NCT03486067 |
| DEV-BCMA-006 | SILVER | HPN217 | ✅ | company_press_release | hpn217 |
| DEV-BCMA-007 | SILVER | REGN5459 | ✅ | ctgov | regn5459 |
| DEV-BCMA-008 | SILVER | AMG 420 | ✅ | pubmed | amg420 |
| DEV-BCMA-009 | SILVER | pavurutamab | ✅ | pubmed | NCT03287908 |
| DEV-BCMA-010 | SILVER | WVT078 | ✅ | pubmed | wvt078 |
| DEV-BCMA-011 | SILVER | EMB-06 | ✅ | ctgov, pubmed | NCT04735575 |
| DEV-BCMA-012 | SILVER | ISB 2001 | ✅ | pubmed | NCT05862012 |
| DEV-BCMA-013 | SILVER | JNJ-79635322 | ✅ | ctgov, pubmed | jnj79635322 |
| DEV-BCMA-014 | SILVER | SIM0500 | ✅ | ctgov | sim0500 |

## Corrected benchmark identity and residual misses

The original development row incorrectly identified **MK-6070 as HPN217**. Merck's Harpoon
acquisition announcement distinguishes the programs: HPN217 is the BCMA-targeting T-cell engager,
while MK-6070 was formerly HPN328 and targets DLL3. MK-6070/HPN328 is a separate DLL3 program
that fails the BCMA target gate and is not a row in this BCMA benchmark.

- **DEV-BCMA-006 — HPN217.** The corrected identity is covered by the declared Merck Harpoon
  acquisition source, which supplies the BCMA/T-cell-engager context.

- **DEV-CD19-003 — MK-1045 / CN201.** CD19×CD3 bispecific (Curon, acquired by Merck). No PubMed
  article under "CN201"; sparse/ex-US registry presence; SEC full-text surfaces the "Curon"
  acquisition context but not the CN201 asset code or a CD19-modality mention.
  **Class: retrieval gap; now covered by the declared Merck source.**

The pre-correction HPN217 miss was both a missing-source issue and a benchmark identity defect;
CN201 was a retrieval gap. Neither required ranking, query, or gating changes.

## Release gate result

The versioned `declared_sources.yaml` manifest configures source-location URLs only. It does not add
benchmark asset names to generic acquisition queries. The corrected live run covered both residual
assets and reached GOLD 5/5, SILVER 16/16, and total 21/21.

## Reproduction

```bash
MPLCONFIGDIR=/tmp/mpl PYTHONPATH=src python -m bve.cli.se_acquire \
  --problem examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml \
  --corpus-dir research/se_benchmarks/cd19_bcma/development/corpus \
  --acquire \
  --declared-source-manifest research/se_benchmarks/cd19_bcma/development/declared_sources.yaml \
  --reference-universe research/se_benchmarks/cd19_bcma/development/reference_universe.csv \
  --source-index-out research/se_benchmarks/cd19_bcma/development/corpus/source_index.yaml
```

Validation: `python -m pytest tests/se -q` (84 passed) · `ruff check src/bve/se` · `mypy src/bve/se`.

Ranking, scoring refinement, and holdout remain unchanged and out of scope for this acquisition
validation.
