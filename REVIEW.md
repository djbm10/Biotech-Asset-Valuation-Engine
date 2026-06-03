# REVIEW.md — Current Review / Next Initiative

## Current Initiative — Wave 8: Acquisition Screening + M&A Replay

**Why this is next**
- Phase 1 reuses the current valuation engine, stored market-cap data, and
  knowledge-store plumbing with minimal incremental infrastructure.
- Phase 2 is mostly manual research, so the engineering layer can stay thin.
- Phase 3 can reuse existing trial-design and phase-correlation outputs instead of
  introducing a brand-new M&A model.
- Phase 4 extends replay from catalyst trading into acquisition-horizon testing.

**Critical implementation constraints**
- `rnpv_millions` is already risk-adjusted in this repo. The screen must not multiply
  `rNPV × P(approval)` unless the numerator is first converted to an explicit
  un-risked pipeline value.
- Current replay `max_positions` limits entries per decision step, not open positions
  across the portfolio. A real top-8 concentration rule needs a separate
  `max_open_positions` constraint.
- Current replay cadence only supports `weekly` and `biweekly`; quarterly requires a
  calendar-based three-month step.
- Enterprise value needs an explicit methodology tag. Initial v1 should treat
  `EV = market_cap - net_cash` and surface missing debt data rather than hiding it.

**Phase plan**
1. Phase 1 — Acquisition discount screener:
   dedicated screen + snapshot table + CLI; output EV, market cap, net cash, model
   rNPV, model PoS, acquisition discount, and threshold flag.
2. Phase 2 — Comparable deal database:
   curate 30-50 recent biotech M&A deals into YAML and add a thin
   loader/validator plus percentile comparison using EV/peak-sales multiples.
3. Phase 3 — Acquisition readiness filter:
   reuse trial-design and phase-correlation outputs to gate the screen to Phase 2
   proof-of-concept or later, with explicit inclusion/exclusion reasons.
4. Phase 4 — M&A replay profile:
   quarterly decisions, 365-day hold, true top-8 open-position cap, no catalyst
   gate, and `-40%` loss blocking; benchmark against the current replay profile.

**Expected file touch points**
- `src/bve/intelligence/knowledge_layer.py`
- `src/bve/intelligence/acquisition_screen.py`
- `src/bve/intelligence/comparable_deals.py`
- `src/bve/intelligence/acquisition_readiness.py`
- `src/bve/intelligence/replay_policy.py`
- `src/bve/ops/historical_replay.py`
- `src/bve/analysis/portfolio_experiments.py`
- `research/mna/comparable_deals.yaml`
- `tests/intelligence/test_acquisition_screen.py`
- `tests/intelligence/test_comparable_deals.py`
- `tests/intelligence/test_acquisition_readiness.py`
- `tests/test_replay_policy.py`
- `tests/test_historical_replay.py`
- `tests/test_portfolio_experiments.py`

## Status
- Phases 1, 3, and 4 are implemented:
  acquisition screener, acquisition-readiness gate, and M&A replay profile.
- Phase 2 engineering is implemented:
  `ComparableDealLoader`, matcher tiers, `--with-comps`, and YAML validation.
- Manual M&A research complete to lower bound:
  `research/mna/comparable_deals.yaml` now contains 35 screenable public
  deals (target 30–50; lower bound reached) and `research/mna/deal_universe_2020_2026.yaml`
  contains a broader 43-deal sourcing universe.
- Live-name monitoring is now separated from closed-deal comps:
  `research/mna/target_monitor.yaml` tracks current or recently resolved public
  target names such as Revolution Medicines, Avidity Biosciences, and Tango
  Therapeutics.
- Remaining gap:
  continue promoting unresolved private/platform or weakly disclosed deals only
  when a defensible `EV/peak_sales` input can be sourced.

---

## Archived Review — Wave 4B (conf-weighted fix) + Wave 4C: Portfolio Ranking + Clustering

### Wave 4B — Confidence-weighted ΔNPV (optional addition)

Added to `AcceptedChange`:
- `confidence_weighted_delta_npv_millions: float` — `delta_npv × reviewer_confidence` (default weight = 1.0 when confidence is `None`)

Added to `WeeklyOpportunityBrief`:
- `net_confidence_weighted_delta_npv_millions: float` — aggregate across all accepted changes

**Sorting change:** `accepted_changes` now sorted by `|confidence_weighted_delta_npv_millions|` descending (not raw ΔNPV), so low-confidence signals don't dominate the table.

Template updated: throughput section shows both Raw ΔNPV and Confidence-adjusted ΔNPV rows; accepted changes table has a new "Conf-adj ΔNPV" column.

Tests: 45/45 (7 new confidence-weighted tests in `TestWeeklyBriefGeneratorNetDelta`).

---

### Wave 4C — Portfolio Ranking + Clustering

### `src/bve/intelligence/portfolio_ranking.py` (new)

**Step 1 — `OpportunityCluster`:**
- `cluster_id` (sorted asset_ids joined by `|`), `cluster_label` (indication name from KG TREATS edge, or asset_id list), `edge_type`, `asset_ids`, `n_assets`
- `combined_delta_npv_millions`, `combined_confidence_weighted_delta_npv_millions`
- `n_pending_review` (members with no review_decision), `top_asset_id`

**Step 2 — `AssetClusterer` (Union-Find):**
- Resolves `asset_id → kg_node.external_id` mapping
- Queries KG edges of the requested `edge_type` between known nodes
- Union-Find (path compression) groups transitively connected assets
- Assets with no KG node → singleton cluster (nothing silently dropped)
- `cluster_label` derived from first `TREATS → indication` node found; falls back to asset_id list
- Result sorted by `|combined_delta_npv|` desc

**Step 3 — `PortfolioConstraints`:**
- `min_confidence: float = 0.0` — exclude diffs with signal confidence below threshold
- `max_queue_age_days: Optional[int]` — exclude diffs older than N days
- `min_abs_delta_npv_millions: Optional[float]` — exclude diffs below magnitude threshold
- `require_accepted_review: bool = False` — accepted diffs only
- `max_assets: Optional[int]` — cap assets before clustering
- `cluster_edge_type: str = "same_indication"` — KG edge type
- `top_n: int = 10` — max clusters returned
- `constraints_from_dict(d)` — load from YAML/dict

**Step 4 — `PortfolioRankingEngine`:**
- Loads all (or specified) `valuation_diffs` from store
- Applies all 4 constraint filters; tracks `n_filtered_*` telemetry per filter
- Keeps best diff per asset (highest `|ΔNPV|` that passes filters)
- Computes `confidence_weighted_delta` per asset (conf defaults to 1.0 when no signal)
- Passes `asset_stats` to `AssetClusterer.cluster()`
- Returns `PortfolioRankingResult` with clusters + telemetry

### `src/bve/cli/portfolio_rank.py` (new — Step 5)

- `--db`, `--min-confidence`, `--max-age-days`, `--min-delta`, `--accepted-only`, `--top-n`, `--cluster-edge`, `--json`
- Table output: rank, label, n_assets, ΔNPV, adj ΔNPV, pending count, top asset

### `pyproject.toml`
- Registered `bve-portfolio-rank = "bve.cli.portfolio_rank:main"`

### `tests/test_portfolio_ranking.py` (new — Step 6) — 35 tests

| Group | Tests |
|---|---|
| `TestOpportunityClusterModel` | defaults, fields |
| `TestAssetClustererSingletons` | no KG, empty, single, label |
| `TestAssetClustererWithKG` | two linked, unlinked, transitive, mixed, stats propagated, sort, indication label |
| `TestPortfolioConstraints` | defaults, custom, bounds, from_dict |
| `TestPortfolioRankingEngineEmpty` | empty store, ranked_at, constraints echoed |
| `TestPortfolioRankingEngineBasic` | single asset, multi asset, sorted, asset_ids filter |
| `TestPortfolioRankingEngineConstraints` | confidence, magnitude, age, accepted-only, max_assets, top_n |
| `TestPortfolioRankingEngineKGClusters` | multi-asset cluster, combined delta, pending count, singleton fallback, custom edge type |

### Files Modified/Added
- `src/bve/intelligence/weekly_brief.py` — `confidence_weighted_delta_npv_millions` on `AcceptedChange` + `WeeklyOpportunityBrief`
- `src/bve/reporting/templates/weekly_brief.md.j2` — both ΔNPV figures in throughput + table
- `src/bve/intelligence/portfolio_ranking.py` (new)
- `src/bve/cli/portfolio_rank.py` (new)
- `pyproject.toml` — `bve-portfolio-rank` entry point
- `tests/test_weekly_brief.py` — 7 new confidence-weighted tests (45 total)
- `tests/test_portfolio_ranking.py` (new, 35 tests)

### Tests Passed
- `tests/test_weekly_brief.py`: **45/45**
- `tests/test_portfolio_ranking.py`: **35/35**
- Full suite: **1 362 passed**, 0 new failures

### Historical Next Step
Ready at that time to proceed to Wave 5A — Calibrated Propagation
(competitor failure / class-effect safety).
