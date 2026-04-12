# Company SOTP Override Templates

Three archetype templates for `research/company_sotp_overrides.yaml` entries.
Use the template that best matches the company's primary value-creation pattern.

## Templates

| Template | Use when | Expected manual bucket share |
|---|---|---|
| `platform_biotech_override_template.yaml` | RNA, ADC, gene therapy, TPD, IO platform companies | 40–70% |
| `commercial_rare_disease_override_template.yaml` | Approved / NDA-stage rare disease with lead modeled asset | 20–35% |
| `multi_asset_oncology_override_template.yaml` | Multi-program oncology / CNS with named pipeline assets | 40–70% |

## Evidence standards (Step 4)

| source_kind | Confidence range | Example |
|---|---|---|
| `sec_filing` / `contractual` | 0.88–0.90 | 10-K royalty schedule, licensing agreement terms |
| `company_disclosure` / `investor_day` | 0.72–0.82 | Investor-day pipeline value, 10-K partnership economics |
| `analyst_bridge` | 0.65–0.70 | Stage × deal-comp estimate, internal model |
| `inferred` | 0.60–0.65 | Derived from comps, geography expansion proxy |

## Step-4 enforcement (CompanySOTPBuilder defaults)

- **Single-bucket concentration**: any bucket > 25% of SOTP that has only 1 `source_ref` → `needs_manual_review` (`manual_bucket_source_concentration`)
- **Low-evidence total share**: total manual share > 35% AND avg confidence < 0.80 → `needs_manual_review` (`manual_bucket_quality_below_threshold`)

To clear these gates: use `company_disclosure` instead of `analyst_bridge` where possible, add a second corroborating `source_ref`, or raise per-bucket confidence when harder data is available.

## How to use

1. Copy the appropriate template block into `research/company_sotp_overrides.yaml`.
2. Fill `value_millions`, `as_of_date`, and `source_ref` for each bucket.
3. Upgrade `source_kind` (and `confidence`) whenever harder data is available.
4. Run the backfiller to verify the company action policy improves:
   ```
   python -m bve.ops.company_sotp_backfiller \
     --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml \
     --db outputs/intelligence/replay_knowledge.db \
     --replay-db outputs/intelligence/replay_store.sqlite \
     --start 2021-02-01 --end 2024-03-01 --output-dir outputs/analysis
   ```
5. Run the backtest to measure the wave effect (Step 7):
   ```
   python -m bve.analysis.company_sotp_backtest \
     --db outputs/intelligence/replay_knowledge.db \
     --replay-db outputs/intelligence/replay_store.sqlite \
     --start 2021-02-01 --end 2024-03-01 \
     --hold-days 365 --top-n 5 --min-ranked-discount 1.0 \
     --compare-to-strict-buy-watch \
     --output-dir outputs/analysis
   ```
