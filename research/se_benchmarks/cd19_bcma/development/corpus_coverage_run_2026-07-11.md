# Corpus Evidence-Coverage Run — 2026-07-11

Sprint: **source acquisition and ingestion** (not ranking, not holdout).
Decisive metric: does at least one supporting document exist in the corpus for each benchmark asset?

## Headline

| Metric | Prior discovery run (2026-07-10) | This corpus-coverage run |
|---|---|---|
| GOLD | 2/5 | **5/5** |
| SILVER | 1/16 | **14/16** |
| Total | 3/21 (14.3%) | **19/21 (90.5%)** |
| Release gate (GOLD 5/5, SILVER ≥15/16) | fail | **fail by one SILVER** |

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
  `DeclaredUrlConnector` for company/press/conference pages.
- `source_health.py` — the five-stage decomposition that replaces "zero source failures":
  1 connector_succeeded · 2 query_returned_results · 3 required_evidence_present · 4 documents_parsed
  · 5 documents_indexed.
- `evaluation/corpus_coverage.py` — per-asset coverage against `reference_universe.csv`
  (evaluation only; asset names never re-enter acquisition queries).
- CLI `bve-se-acquire` and 14 offline tests (no network in tests; connectors inject fakes).

## Source health (five stages)

| Source family | connector ok | query results | required evidence | parsed | indexed | raw records |
|---|---|---|---|---|---|---|
| clinicaltrials_gov | ✅ | ✅ | ✅ | ✅ | ✅ | 321+ |
| fda_label (openFDA) | ✅ | ✅ | ✅ | ✅ | ✅ | ~11 |
| pubmed | ✅ | ✅ | ✅ | ✅ | ✅ | 193+ |
| sec_edgar | ✅ | ✅ | ✅ | ✅ | ✅ | 25 fetched / 222 hits |

Stage 3 is now attributed across **all** families that hold matching evidence, not just the first
match — every configured family contributes required evidence for at least one benchmark asset.

## Per-asset coverage

| Benchmark | Tier | Asset | Covered | Matching families | Match token |
|---|---|---|---|---|---|
| DEV-CD19-001 | GOLD | blinatumomab | ✅ | ctgov, fda_label, pubmed, sec | blinatumomab |
| DEV-CD19-002 | GOLD | AZD0486 | ✅ | ctgov | azd0486 |
| DEV-CD19-003 | SILVER | MK-1045 (CN201) | ❌ | — | — |
| DEV-CD19-004 | SILVER | CLN-978 | ✅ | ctgov, sec | cln978 |
| DEV-CD19-005 | SILVER | AMG 562 | ✅ | ctgov | NCT03571828 |
| DEV-CD19-006 | SILVER | AFM11 | ✅ | ctgov | afm11 |
| DEV-CD19-007 | SILVER | duvortuxizumab | ✅ | ctgov | NCT02454270 |
| DEV-BCMA-001 | GOLD | teclistamab | ✅ | ctgov, fda_label, pubmed | teclistamab |
| DEV-BCMA-002 | GOLD | elranatamab | ✅ | ctgov, fda_label, pubmed | elranatamab |
| DEV-BCMA-003 | GOLD | linvoseltamab | ✅ | ctgov, fda_label, pubmed | linvoseltamab |
| DEV-BCMA-004 | SILVER | ABBV-383 | ✅ | ctgov, pubmed | abbv383 |
| DEV-BCMA-005 | SILVER | alnuctamab | ✅ | ctgov, pubmed | NCT03486067 |
| DEV-BCMA-006 | SILVER | MK-6070 (HPN217) | ❌ | — | — |
| DEV-BCMA-007 | SILVER | REGN5459 | ✅ | ctgov | regn5459 |
| DEV-BCMA-008 | SILVER | AMG 420 | ✅ | pubmed | amg420 |
| DEV-BCMA-009 | SILVER | pavurutamab | ✅ | pubmed | NCT03287908 |
| DEV-BCMA-010 | SILVER | WVT078 | ✅ | pubmed | wvt078 |
| DEV-BCMA-011 | SILVER | EMB-06 | ✅ | ctgov, pubmed | NCT04735575 |
| DEV-BCMA-012 | SILVER | ISB 2001 | ✅ | pubmed | NCT05862012 |
| DEV-BCMA-013 | SILVER | JNJ-79635322 | ✅ | ctgov, pubmed | jnj79635322 |
| DEV-BCMA-014 | SILVER | SIM0500 | ✅ | ctgov | sim0500 |

## Residual misses — precise classification

Both residual misses are the **same failure class**, and it is not corpus-search depth.

- **DEV-BCMA-006 — MK-6070 / HPN217.** The trial exists (NCT04184050) but its registry record
  discloses **no mechanism**: the brief/official title and summary contain neither "BCMA" nor any
  modality token ("bispecific", "CD3", "BiTE", "T-cell engager", "TriTAC"). PubMed returns **zero**
  articles for "HPN217". The evidence that HPN217 is a BCMA×CD3 engager lives only in Harpoon/Merck
  company and conference disclosures.
  **Class: retrieval — mechanism-bearing evidence exists only in company/conference sources.**

- **DEV-CD19-003 — MK-1045 / CN201.** CD19×CD3 bispecific (Curon, acquired by Merck). No PubMed
  article under "CN201"; sparse/ex-US registry presence; SEC full-text surfaces the "Curon"
  acquisition context but not the CN201 asset code or a CD19-modality mention.
  **Class: retrieval — mechanism-bearing evidence only in company/conference/ex-US-registry sources.**

Neither miss is an ontology, extraction, identity, temporal-status, or gating failure at this stage,
and neither is a false exclusion (no candidate reached confirmed exclusion). No fix should seed
benchmark asset names into acquisition queries to close them.

## To reach the release gate (SILVER ≥15/16)

The `DeclaredUrlConnector` framework is built but not yet given live seeds. The bounded next step is
to configure **source-location seeds** (company pipeline/press domains and ASH/ASCO/AACR/EHA abstract
indices) — retrieval configuration that enumerates *where a source family publishes*, not *which
assets to find*. Fetching the Harpoon/Merck and Curon/Merck disclosures through that connector is the
direct path to covering the two residual assets without asset-name seeding.

## Reproduction

```bash
MPLCONFIGDIR=/tmp/mpl PYTHONPATH=src python -m bve.cli.se_acquire \
  --problem examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml \
  --corpus-dir research/se_benchmarks/cd19_bcma/development/corpus \
  --acquire \
  --reference-universe research/se_benchmarks/cd19_bcma/development/reference_universe.csv \
  --source-index-out research/se_benchmarks/cd19_bcma/development/corpus/source_index.yaml
```

Validation: `python -m pytest tests/se -q` (84 passed) · `ruff check src/bve/se` · `mypy src/bve/se`.

Do not proceed to clinical ranking, scoring refinement, or holdout evaluation until SILVER coverage
reaches ≥15/16 and both residual misses are closed via generic acquisition.
