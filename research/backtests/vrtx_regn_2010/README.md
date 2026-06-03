# VRTX / REGN Historical Backtest — 2010 to Present

## Purpose

This backtest asks two questions using only pre-announcement information:

1. **Ranking question**: At 365, 180, 90, and 30 days before each actual acquisition,
   would the model have ranked the actual target highly versus realistic alternatives?

2. **Valuation question**: Would the model's standalone rNPV and buyer-specific value
   have been directionally close to the actual deal value?

## Non-negotiable design rules

- **No look-ahead**: every feature uses only data available as of the snapshot date.
  Enforced by `LeakageGuard` — the backtest runner refuses to proceed if the audit fails.
- **No tuning on results**: model weights are frozen `evidence-informed priors` set
  before seeing any backtest outcomes.
- **Full provenance**: every feature row carries `source_url`, `source_published_date`,
  `data_as_of_date`, `extraction_method`, and `confidence`.
- **Label isolation**: actual deal value, deal premium, and acquisition outcome are
  evaluation-only fields — they never appear in model input columns.
- **Unknown = null**: missing facts are written to `research_gaps.csv` rather than imputed.
- **Unverified deals excluded by default**: only deals with `verified=TRUE` in the seed
  file are included in primary metrics. Pass `--include-unverified-deals` to include all.

## Verified deals in this backtest

| Acquirer | Target | Announced | Value | Source |
|---|---|---|---|---|
| VRTX | Semma Therapeutics | 2019-09-03 | $950M cash | Vertex official press release |
| VRTX | Alpine Immune Sciences | 2024-04-10 | ~$4.9B cash | Vertex official press release |
| REGN | Decibel Therapeutics | 2023-08-09 | ~$109M + $213M CVR | Regeneron official press release |

## Unverified research-gap deals (excluded by default)

| Acquirer | Target | Notes |
|---|---|---|
| VRTX | ViaCyte | Official deal value unverified |
| VRTX | Exonics | Classification (acquisition vs collaboration) uncertain |
| REGN | Checkmate Pharmaceuticals | Official deal terms unverified |
| REGN | 2seventy bio assets | Exact asset scope and timing unverified |
| REGN | Libtayo rights from Sanofi | Rights restructuring, not target acquisition — excluded from ranking |

## How to run

```bash
# Build dataset
python -m bve.backtest_research.vrtx_regn_dataset_builder \
  --since 2010 \
  --acquirers VRTX REGN \
  --snapshot-days 365 180 90 30 \
  --min-negatives 30 \
  --output research/backtests/vrtx_regn_2010/curated

# Run backtest
python -m bve.backtest_research.vrtx_regn_backtest_runner \
  --dataset research/backtests/vrtx_regn_2010/curated \
  --score-mode approved_only \
  --output research/backtests/vrtx_regn_2010/outputs
```

## Output files

| File | Description |
|---|---|
| `curated/vrtx_regn_deals_master.csv` | All deals (verified + unverified) with classification |
| `curated/vrtx_regn_acquirer_snapshots.csv` | Acquirer profiles at each snapshot date |
| `curated/vrtx_regn_target_snapshots.csv` | Target profiles at each snapshot date |
| `curated/vrtx_regn_asset_snapshots.csv` | Lead asset profiles at each snapshot date |
| `curated/vrtx_regn_candidate_pairs.csv` | All (acquirer, target, snapshot) pairs |
| `curated/vrtx_regn_feature_store.csv` | All model input features with provenance |
| `curated/vrtx_regn_research_gaps.csv` | Unknown/missing facts |
| `outputs/vrtx_regn_backtest_results.csv` | Per-pair scores and ranks |
| `outputs/vrtx_regn_backtest_report.md` | Human-readable report |
| `outputs/vrtx_regn_leakage_audit.csv` | Leakage guard audit results |
| `outputs/vrtx_regn_error_review.csv` | False positives / false negatives |
| `outputs/vrtx_regn_source_audit.md` | Source quality summary |

## Limitations

- **Small N**: Only 3 verified deals. All metrics have very wide confidence intervals.
  Treat direction and order-of-magnitude as meaningful; exact numbers are not.
- **Survivorship bias**: negative candidates are limited to companies that were publicly
  visible at snapshot date and survived to be indexed. Delisted companies before the
  snapshot date may be missing.
- **No point-in-time CT.gov**: ClinicalTrials.gov v2 API does not provide historical
  snapshots. Update dates are used as a proxy; this may introduce minor look-ahead in
  trial status features.
- **Private target limitation**: Semma Therapeutics was private at acquisition.
  Features derived from public filings (SEC, market cap) are not available.
  This case relies on press releases and academic publications for feature construction.
- **Do not overclaim**: with N=3 verified deals, the model cannot be statistically
  validated for predictive accuracy. The purpose is to identify feature gaps, data
  quality issues, and directional plausibility — not to prove the model works.
