# tasks.md — Implementation Roadmap

Last updated: 2026-03-24
Current branch: core-engine-v1
Test baseline: 1,407 passing

---

## How to Read This File

Tasks are organized by sprint. Each sprint must be fully complete before the next begins.
Each task lists: files to create or modify, key design decisions, and done criteria.
Do not parallelize the watchlist processing loop until Postgres migration is complete.

---

## Sprint 1 — Foundation

### Task 1.1 — Universe Registry YAML + Data Models

**Why first**: Everything else depends on knowing which assets to expand to.

**Create:**
- `examples/configs/universe_registry.yaml`
  - 30 seed entries covering Stage 1 assets
  - Per-entry fields: `ticker, company_name, asset_id, drug_name, indication,
    therapeutic_area, stage, modality, nct_id, tam_millions,
    net_price_per_patient_usd, addressable_patients_annual, peak_penetration,
    patent_life_years, discount_rate`
  - Stage 1 tickers: VRTX, ALNY, BMRN, MRNA, IONS, SRPT, ACAD, SAGE, CRSP, NTLA,
    BEAM, PRAX, RXRX, IMVT, KYMR, ARQT, MDGL, FATE, BLUE, EDIT, ANAB, PTCT,
    FOLD, TGTX, SPNV, AGEN, RLAY (already exists — skip YAML gen), REGN (already exists)

- `src/bve/pipeline/universe_registry.py`
  - `UniverseRegistryEntry` (Pydantic BaseModel) — mirrors YAML entry fields
  - `load_universe_registry(path: Path) -> list[UniverseRegistryEntry]`

**Done criteria:**
- `load_universe_registry("examples/configs/universe_registry.yaml")` returns 30 entries
- All entries pass Pydantic validation

---

### Task 1.2 — DiskCache

**Why before generator**: Generator calls CT.gov, SEC, yfinance; without caching, batch
generation of 30 assets makes ~90 network calls. With cache it makes ~90 on first run,
~0 on subsequent runs within TTL.

**Create:**
- `src/bve/pipeline/disk_cache.py`
  - `DiskCache(root: Path = Path("outputs/cache"))`
  - `get(namespace: str, key: str) -> Optional[dict]` — returns None if missing or expired
  - `put(namespace: str, key: str, data: dict) -> None` — writes JSON atomically with
    `fetched_at` timestamp
  - TTLs: `ctgov=timedelta(days=7)`, `sec=timedelta(days=1)`, `market=timedelta(minutes=15)`
  - Atomic write: write to `.tmp` file, then `os.replace()` to avoid partial reads

**Add to `.gitignore`:**
- `outputs/cache/`

**Done criteria:**
- `put` then `get` within TTL returns data
- `get` after TTL returns None
- Concurrent writes do not corrupt cache (atomic replace)

---

### Task 1.3 — Auto-Config Generator

**Create:**
- `src/bve/pipeline/auto_config_generator.py`
  - `AutoConfigGenerator(cache: DiskCache, rate_limiter: ServiceRateLimiter)`
  - `generate(entry: UniverseRegistryEntry) -> dict`
    1. Fetch NCT from CT.gov if `nct_id` present → parse phase, enrollment,
       primary_endpoint, estimated_completion_date; cache under `ctgov/{nct_id}.json`
    2. Fetch company financials from SEC EDGAR → cash, shares, burn rate;
       cache under `sec/{ticker}_{quarter}.json`
    3. Fetch current price + market_cap from yfinance;
       cache under `market/{ticker}.json`
    4. Look up PoS base rates from `AssumptionsLoader.phase_success_rate(ta, phase)`
    5. Build config dict with all fields that `cli/run_asset.py::_build_objects()` can parse
  - Config snapshot versioning — every generated config dict must include:
    ```yaml
    _meta:
      config_version: "auto-v1"
      generator_version: "0.3"
      generated_at: "2026-03-09"
      source_nct_id: "NCT05076344"
      source_sec_filing: "10-K 2025"
    ```
    This enables reproducing historical valuations if assumptions change.
  - `generate_batch(entries: list[UniverseRegistryEntry]) -> list[tuple[entry, dict, Optional[str]]]`
    — returns (entry, config_dict, error_message) tuples; errors do not abort the batch

**Modify:**
- `src/bve/cli/run_asset.py::_build_objects()` — ignore `_meta` key (skip unknown top-level keys
  gracefully so auto-generated configs parse without errors)

**Create:**
- `src/bve/cli/generate_config.py` — `bve-generate-config`
  - `--ticker VRTX` — single asset
  - `--batch` — all entries in registry
  - `--registry path` — default `examples/configs/universe_registry.yaml`
  - `--out-dir path` — default `examples/configs/auto_generated/`
  - `--db path` — if provided, writes entry to `asset_registry` table with `source="auto_generated"`
  - Output: prints the watchlist YAML block to add for each generated config
  - Warnings printed for every field that used a default (not sourced from live data)

**Add to `pyproject.toml` `[project.scripts]`:**
- `bve-generate-config = "bve.cli.generate_config:main"`

**Create output directory:**
- `examples/configs/auto_generated/.gitkeep`

**Done criteria:**
- `bve-generate-config --ticker VRTX --dry-run` prints config without writing files
- Generated YAML parses through `_build_objects()` without error
- `_meta` block present in every generated YAML
- Batch generation of 30 assets completes; second run uses cache exclusively (zero network calls)

---

### Task 1.4 — Asset Registry DB Table

**Modify:**
- `src/bve/intelligence/knowledge_layer.py::KnowledgeStore._init_tables()`
  - Add `asset_registry` table:
    ```sql
    CREATE TABLE IF NOT EXISTS asset_registry (
        asset_id                    TEXT PRIMARY KEY,
        ticker                      TEXT,
        company_id                  TEXT,
        drug_name                   TEXT,
        indication                  TEXT,
        therapeutic_area            TEXT,
        modality                    TEXT,
        stage                       TEXT,
        nct_id                      TEXT,
        tam_millions                REAL,
        created_at                  TEXT NOT NULL,
        source                      TEXT NOT NULL,
        last_competitor_discovery_at TEXT,
        UNIQUE(ticker, drug_name, indication)
    );
    CREATE INDEX IF NOT EXISTS idx_asset_registry_ticker
        ON asset_registry(ticker);
    CREATE INDEX IF NOT EXISTS idx_asset_registry_ta
        ON asset_registry(therapeutic_area);
    ```
  - Add `upsert_asset_registry_entry(entry: AssetRegistryEntry) -> None`
    — uses `INSERT OR REPLACE`
  - Add `get_asset_registry_entry(asset_id: str) -> Optional[AssetRegistryEntry]`
  - Add `list_asset_registry(ta=None, stage=None) -> list[AssetRegistryEntry]`
  - Add `count_competitor_programs(asset_id: str) -> int`
    — `SELECT COUNT(*) FROM competitor_programs WHERE asset_id = ?`
  - Add `update_competitor_discovery_timestamp(asset_id: str, ts: datetime) -> None`
    — updates `last_competitor_discovery_at` in `asset_registry`

**Done criteria:**
- `UNIQUE(ticker, drug_name, indication)` prevents duplicate entries
- `upsert_asset_registry_entry` called twice with same data does not raise
- `last_competitor_discovery_at` starts as NULL

---

### Task 1.5 — Competitor Discovery Wiring

**Why**: `CompetitorDiscoveryEngine` (Wave 2B) exists and is tested but is never called
from `watchlist_runner.py`. This is the highest-value small change in the entire plan.

**Modify:**
- `src/bve/pipeline/watchlist_runner.py`
  - Add `_should_run_competitor_discovery(self, asset_id: str) -> bool`:
    - Returns True if `count_competitor_programs(asset_id) == 0`
    - OR `last_competitor_discovery_at` is None
    - OR `(utcnow() - last_competitor_discovery_at) > timedelta(days=7)`
  - Add `_run_competitor_discovery(self, asset_cfg: WatchlistAsset, run_id: str) -> None`:
    1. Check `_should_run_competitor_discovery` — return early if False
    2. Find or create asset KG node (`find_node_by_external_id(NodeType.ASSET, asset_id)`;
       upsert if missing)
    3. `self.rate_limiter.wait("clinicaltrials_gov")` — unified rate limiting
    4. Create `CompetitorDiscoveryEngine(store=self.knowledge, request_delay_seconds=0.0)`
       — rate limiter handles pacing; engine's internal sleep disabled
    5. Call `engine.discover(asset_cfg.asset_id, asset_node.node_id, asset_cfg.indication)`
    6. On success: call `self.knowledge.update_competitor_discovery_timestamp(asset_id, utcnow())`
    7. Log result: programs found, KG edges added, errors
    8. Errors logged, never raised — failure does not abort the asset run
  - Call `_run_competitor_discovery()` from `_run_asset()` after the main ingestion stage,
    only when `asset_cfg.indication` is set

**Done criteria:**
- First watchlist run: discovery fires for all assets with indication
- Second run within 7 days: discovery skipped (log shows "skipped, last_run=X days ago")
- Asset with no indication: discovery never fires
- CompetitorDiscoveryEngine errors do not cause `_run_asset()` to fail
- `COMPETES_WITH` KG edges appear in `kg_edges` table after first run

---

### Task 1.6 — Staged Watchlist Files + --watchlist-dir

**Create:**
- `examples/configs/watchlists/` directory
- Copy existing `examples/configs/watchlist.yaml` → `examples/configs/watchlists/watchlist_example.yaml`
- `examples/configs/watchlists/watchlist_stage1.yaml` — 30 assets using auto-generated configs
  from Task 1.3; RLAY and REGN point to existing hand-crafted configs

**Modify:**
- `src/bve/pipeline/watchlist_runner.py::load_watchlist_config()`
  - Accept `str | Path` for either a file or a directory
  - If directory: glob `watchlist_*.yaml`, load each, merge `watchlist:` lists,
    deduplicate by `asset_id` (first occurrence wins), take all other config from first file
- `src/bve/services/intelligence_service.py::IntelligenceServiceConfig`
  - Add `watchlist_dir: Optional[str] = None`
  - Exactly one of `watchlist_path` or `watchlist_dir` must be set (validator)
- `src/bve/cli/watchlist_run.py` — add `--watchlist-dir` flag
- `src/bve/cli/service_control.py` — add `--watchlist-dir` flag

**Done criteria:**
- `bve-watchlist-run --watchlist-dir examples/configs/watchlists/` loads all 30 assets
- Duplicate `asset_id` across files is silently deduplicated (first file wins, warning logged)

---

## Sprint 2 — Data Quality + Stage 1 Live

### Task 2.1 — Data Quality Monitor

**Create:**
- `src/bve/ops/data_quality.py`
  - `DataQualityCheck` (Pydantic) — `check_type, asset_id, value, threshold, passed, details`
  - `DataQualityScore` (Pydantic) — `source, asset_id, overall_score, checks, failing_checks,
    gated, generated_at`
  - `DataQualityMonitor(store: KnowledgeStore, gate_threshold: float = 0.70)`
  - `check_asset(asset_id: str) -> DataQualityScore` — runs all 6 checks below
  - `check_all(asset_ids: list[str]) -> list[DataQualityScore]`

**Six checks (all query existing KnowledgeStore tables):**

| Check | Query | Threshold |
|---|---|---|
| `doc_freshness` | `MAX(fetched_at) FROM raw_documents WHERE asset_id=?` | ≤ 3 days ago |
| `doc_volume_7d` | `COUNT(*) WHERE asset_id=? AND fetched_at > 7d ago` | ≥ 1 |
| `confidence_trend_30d` | `AVG(confidence) FROM structured_signals WHERE asset_id=? AND created_at > 30d ago` | ≥ 0.60 |
| `null_field_rate` | % of signals with `delta_npv_millions IS NULL` | ≤ 10% |
| `connector_error_rate` | `run_state WHERE status='failure' / total` last 20 runs | ≤ 5% |
| `duplicate_rate` | `(COUNT(*) - COUNT(DISTINCT document_hash)) / COUNT(*)` | ≤ 2% |

**Modify:**
- `src/bve/intelligence/knowledge_layer.py::KnowledgeStore._init_tables()`
  - Add `data_quality_log` table:
    ```sql
    CREATE TABLE IF NOT EXISTS data_quality_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id     TEXT,
        overall_score REAL NOT NULL,
        gated        INTEGER NOT NULL,
        checks_json  TEXT NOT NULL,
        checked_at   TEXT NOT NULL
    );
    ```
  - Add `log_data_quality(score: DataQualityScore) -> None`
  - Add `get_latest_data_quality(asset_id: str) -> Optional[DataQualityScore]`

- `src/bve/services/intelligence_service.py::IntelligenceService.run_cycle()`
  - After `watchlist_summary`, call `DataQualityMonitor.check_all(asset_ids)`
  - Log quality scores
  - Pass list of non-gated asset_ids to `scanner.scan_from_watchlist_config()` so gated assets
    are excluded from opportunity scoring

**Create:**
- `src/bve/cli/data_quality_report.py` — `bve-data-quality`
  - `--db path`, `--asset asset_id`, `--gated-only`, `--json`
  - Tabular output: asset, score, failing checks, gated status

**Add to `pyproject.toml` `[project.scripts]`:**
- `bve-data-quality = "bve.cli.data_quality_report:main"`

**Done criteria:**
- All 6 checks run without error against an empty DB (edge case: returns score=1.0 when no data)
- Gated assets (score < 0.70) are excluded from opportunity scan output
- `bve-data-quality --gated-only` lists only gated assets

---

### Task 2.2 — Connector Health Metrics

**Why**: Connector success rates catch API breakages (CT.gov v2 changes, SEC EDGAR rate limits,
yfinance schema changes) before they silently degrade signal quality.

**Modify:**
- `src/bve/ops/metrics.py`
  - Add `ConnectorHealthMetrics` (Pydantic):
    ```python
    class ConnectorHealthMetrics(BaseModel):
        connector: str
        success_rate: float       # over last 20 runs
        n_runs_sampled: int
        last_failure_at: Optional[datetime]
        last_success_at: Optional[datetime]
        health_threshold: float = 0.80
        healthy: bool             # success_rate >= health_threshold
    ```
  - Add `StageLatencyMetrics` (Pydantic):
    ```python
    class StageLatencyMetrics(BaseModel):
        stage: str
        avg_ms: float
        p50_ms: float
        p95_ms: float
        p99_ms: float
        n_observations: int
    ```
  - Extend `RunMetrics`:
    ```python
    class RunMetrics(BaseModel):
        # ... existing fields unchanged ...
        stage_latencies: list[StageLatencyMetrics] = Field(default_factory=list)
        connector_health: list[ConnectorHealthMetrics] = Field(default_factory=list)
    ```

- `src/bve/pipeline/watchlist_runner.py::WatchlistPipelineRunner`
  - Wrap each stage in `_run_asset()` with `time.perf_counter()` brackets
  - Stages to time: `ingestion`, `extraction`, `valuation`, `alerts`
  - Collect per-asset timings; aggregate to p50/p95/p99 in `run_once()` before returning
    `WatchlistRunSummary`
  - Track per-connector success/failure counts in a rolling window of last 20 runs
    (store in `run_state` table or a lightweight in-memory deque on the runner instance)

- `src/bve/services/intelligence_service.py::IntelligenceService.run_cycle()`
  - Also time `opportunity_scan` and `dashboard_cache` stages
  - Pass latency + connector health to `_build_metrics()`

- Alert on connector health drop: if any `ConnectorHealthMetrics.healthy == False`,
  emit a `LOW` severity alert via `AlertRouter` (connector name + success rate in message)
  — uses existing alert infrastructure, no new alert types needed

**Done criteria:**
- `RunMetrics` includes `stage_latencies` and `connector_health` after every cycle
- `p95_ms` is computed correctly (requires ≥ 20 asset samples for stability; falls back to
  `max_ms` when n < 20)
- A simulated connector that fails 5/20 times triggers a health alert
- Latency timing does not add more than 1ms overhead per stage (perf_counter is cheap)

---

### Task 2.3 — Stage 1 Watchlist Go-Live

**Action (no code):**
1. Run `bve-generate-config --batch --registry examples/configs/universe_registry.yaml`
   to generate all 28 remaining configs (RLAY and REGN already exist)
2. Review each auto-generated YAML — correct any obviously wrong PoS rates or TAM assumptions
3. Add all 30 assets to `watchlist_stage1.yaml`
4. Run `bve-watchlist-run --watchlist examples/configs/watchlists/watchlist_stage1.yaml`
   with `backend: fake` extraction to validate pipeline end-to-end
5. Switch to `backend: anthropic` or `backend: openai` for production

**Stage 1 → Stage 2 Gate (observe for 1–2 weeks before Sprint 3):**
- ≥ 20/30 assets produce at least 1 signal in first 14 days
- Competitor discovery finds ≥ 3 programs per asset on average
- No connector error rate > 5% (data quality monitor confirms)
- Weekly brief ranking is stable (top-5 does not flip entirely week-over-week)
- No `data_quality_log` entries with `gated=1` persisting more than 48 hours

---

## Sprint 3 — Intelligence Layers

### Task 3.1 — Catalyst Model (Layer-Separated)

**Key constraint**: The catalyst model must never modify rNPV, ValuationOutput, or any field
on ValuationEngine outputs. It is a separate scoring layer consumed only by OpportunityScanner.

**Create:**
- `src/bve/config/catalyst_calibration.yaml`
  - Initial values sourced from published BioPharmCatalyst / BioMedTracker data:
    ```yaml
    profiles:
      - event_type: phase_3_readout
        phase: phase_3
        p_positive_outcome: 0.52
        median_move_positive_pct: 28.0
        median_move_negative_pct: 38.0
        move_volatility: 0.18
        n_observations: 847
        last_calibrated: "2025-01-01"
      - event_type: fda_approval
        p_positive_outcome: 0.85
        median_move_positive_pct: 18.0
        median_move_negative_pct: 28.0
        move_volatility: 0.12
        n_observations: 412
        last_calibrated: "2025-01-01"
      - event_type: phase_2_readout
        ...
      - event_type: advisory_committee
        ...
      - event_type: earnings
        ...
      - event_type: conference_presentation
        ...
    ```

- `src/bve/models/catalyst_model.py`
  - `CatalystMoveProfile` (Pydantic, frozen) — mirrors YAML entry
  - `CatalystValuation` (Pydantic) — `event_key, asset_id, event_type, catalyst_date,
    days_to_catalyst, p_positive_outcome, expected_return_pct, expected_move_magnitude_pct,
    current_price, expected_move_dollars, profile_source`
    — `profile_source: Literal["calibrated", "default", "override"]`
  - `CatalystModel(store: KnowledgeStore, calibration_path: Path)`
    - `load_profiles() -> dict[str, CatalystMoveProfile]`
    - `score_catalyst(event_type, phase, signal_id=None) -> CatalystValuation`
      - Integrates `TrialDesignAssessment.design_quality_multiplier` (Wave 2C):
        ```python
        design_multiplier = 1.0
        if signal_id:
            assessment = self._store.get_design_assessment(signal_id)
            if assessment:
                design_multiplier = assessment.design_quality_multiplier
        adjusted_p_positive = min(1.0, profile.p_positive_outcome * design_multiplier)
        ```
      - `expected_return_pct = adjusted_p * positive_move - (1-adjusted_p) * negative_move`
      - Returns `CatalystValuation` — never touches any rNPV field

**Modify:**
- `src/bve/intelligence/opportunity_scanner.py`
  - Add optional `CatalystModel` parameter to `OpportunityScanner.__init__()`
  - When `catalyst_model` is set, call `score_catalyst()` for each opportunity
    and attach result as `RankedOpportunity.catalyst_valuation: Optional[CatalystValuation]`
  - `composite_score` weighting: catalyst `expected_return_pct` is used as a boost weight,
    same pattern as `extraction_confidence` — it does not replace the score, it adjusts it
  - When `catalyst_model` is None: behavior is unchanged (backward compatible)

**Done criteria:**
- `CatalystValuation` has no reference to `ValuationOutput`, `RNPVResult`, or any rNPV field
- `score_catalyst()` with a `TrialDesignAssessment` (OS_RCT tier) gives `p_positive * 1.10`
- `score_catalyst()` with no assessment uses `design_multiplier=1.0` (no change)
- `OpportunityScanner` with no `CatalystModel` produces identical output to before

---

### Task 3.2 — Ranking Calibrator + Feedback Loop

**Create:**
- `src/bve/analysis/ranking_calibrator.py`
  - `CalibrationReport` (Pydantic) — `run_date, n_resolved_forecasts, event_type_weights,
    event_type_weights_prior, confidence_scaling_factor, brier_score, calibration_curve,
    drift_alerts`
  - `RankingCalibrator(store: KnowledgeStore, calibration_path: Path)`
    - `calibrate() -> CalibrationReport`
      - Groups `forecast_records WHERE outcome_label IS NOT NULL` by `event_type`
      - N < 20 for any type: use `DEFAULT_EVENT_TYPE_SCORES` unchanged (existing fallback)
      - N ≥ 20: compute precision, recall, F1; apply dampened update:
        `new_weight = 0.80 × prior + 0.20 × f1`
      - Platt-scale `extraction_confidence` vs `outcome` for `confidence_scaling_factor`
      - Drift alert if any weight shifts > 20% from prior
    - `write_calibration(report: CalibrationReport) -> None`
      — writes to `src/bve/config/ranking_calibration.yaml` (version-controlled)

- `src/bve/config/ranking_calibration.yaml`
  - Initial content: all weights equal to `DEFAULT_EVENT_TYPE_SCORES`; `confidence_scaling_factor=1.0`
  - Auto-updated weekly by calibrator

**Modify:**
- `src/bve/intelligence/ranking.py` (or wherever `RankingConfig` lives)
  - On load, check for `ranking_calibration.yaml`; if present, merge weights
  - If file missing: fall back to `DEFAULT_EVENT_TYPE_SCORES` (no error)

- `src/bve/services/scheduler.py` or `intelligence_service.py`
  - Trigger `RankingCalibrator.calibrate()` weekly (after Sunday watchlist run)

**Done criteria:**
- With 0 resolved forecasts: calibration writes identical weights to defaults
- With N=15 for event_type X: X weight is unchanged (N < 20 guard)
- With N=25 for event_type Y and F1=0.8: `new_weight = 0.8×prior + 0.2×0.8`
- Drift alert fires when weight shifts > 20%
- `ranking_calibration.yaml` missing: ranking engine loads without error

---

### Task 3.3 — Backtest Snapshot Table + Portfolio Backtester

**Modify:**
- `src/bve/intelligence/knowledge_layer.py::KnowledgeStore._init_tables()`
  - Add `backtest_snapshots` table:
    ```sql
    CREATE TABLE IF NOT EXISTS backtest_snapshots (
        snapshot_id           TEXT PRIMARY KEY,
        alert_id              TEXT NOT NULL,
        asset_id              TEXT NOT NULL,
        signal_date           TEXT NOT NULL,
        composite_score       REAL,
        extraction_confidence REAL,
        delta_npv_millions    REAL,
        mispricing_score      REAL,
        catalyst_date         TEXT,
        catalyst_type         TEXT,
        rank_at_signal        INTEGER,
        model_version         TEXT,
        created_at            TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_backtest_snapshots_asset
        ON backtest_snapshots(asset_id, signal_date);
    ```
  - Add `write_backtest_snapshot(snapshot: BacktestSnapshot) -> None`
  - Add `get_backtest_snapshots(asset_id=None, since=None) -> list[BacktestSnapshot]`

- `src/bve/alerts/alert_router.py::AlertRouter.route()`
  - After alert is persisted (alert cleared all thresholds), write one `BacktestSnapshot`
  - `AlertRouter.__init__()` accepts optional `knowledge_store: Optional[KnowledgeStore] = None`
  - When `knowledge_store` is None: no snapshot written (default, backward compatible)
  - Snapshot includes: composite_score, extraction_confidence, delta_npv_millions,
    mispricing_score, catalyst_date, catalyst_type, rank_at_signal from the `RankedOpportunity`
    that triggered the alert

**Create:**
- `src/bve/analysis/portfolio_backtest.py`
  - `PortfolioBacktestConfig` (Pydantic) — `start_date, end_date, strategy, n_holdings,
    rebalance_freq_days, benchmark_ticker="XBI", initial_capital=1_000_000,
    transaction_cost_bps=10`
  - `BacktestResult` (Pydantic) — `cagr, sharpe_ratio, sortino_ratio, max_drawdown,
    win_rate, alpha_vs_benchmark, beta_vs_benchmark, information_ratio,
    monthly_returns, equity_curve, benchmark_equity_curve, position_log`
  - `PortfolioStrategy` enum — `TOP_N_EQUAL_WEIGHT, SCORE_WEIGHTED, HOLD_UNTIL_CATALYST,
    CATALYST_MOMENTUM`
  - `PortfolioBacktester(store: KnowledgeStore, config: PortfolioBacktestConfig)`
    - `run() -> BacktestResult` — reads from `backtest_snapshots`, fetches returns via yfinance
    - Mode 1 (live): uses `backtest_snapshots` accumulated since system went live
    - Mode 2 (event study): seeds from known historical PDUFA/Phase3 events using
      `event_study/abnormal_returns.py` (already exists) for the Stage 1 tickers

  **Survivorship bias disclaimer** (must appear in CLI output and any generated reports):
  ```
  WARNING: This backtest does not correct for survivorship bias. Biotech tickers
  with negative outcomes may be delisted; yfinance returns NaN for delisted names,
  which are excluded from return calculations. Results will overstate performance
  until a delisting-adjusted price feed is integrated.
  ```

**Add to `pyproject.toml` `[project.scripts]`:**
- `bve-portfolio-backtest = "bve.cli.portfolio_backtest:main"`

**Done criteria:**
- Alert fires → `backtest_snapshots` row written with correct score/confidence/rank
- No snapshot written for non-firing ranked opportunities
- `AlertRouter` with no `knowledge_store` behaves identically to before (backward compat)
- `PortfolioBacktester.run()` with empty `backtest_snapshots` returns graceful result
  (not error) with `n_signals=0` note
- Survivorship bias disclaimer appears in CLI output unconditionally

---

## Sprint 4 — Stress Tests + Stage 2 Expansion

### Task 4.1 — KG Integrity Checker

**Create:**
- `src/bve/intelligence/kg_integrity.py`
  - `KGIntegrityReport` (Pydantic) — `checked_at, n_nodes, n_edges, orphan_edges,
    duplicate_nodes, invalid_confidence, missing_asset_nodes, passed`
  - `KGIntegrityChecker(store: KnowledgeStore)`
    - `check(watchlist_asset_ids: list[str]) -> KGIntegrityReport`
      - Orphan edges: `edge_id WHERE source_node_id NOT IN kg_nodes OR target_node_id NOT IN kg_nodes`
      - Duplicate nodes: `(node_type, external_id) WITH COUNT(*) > 1 WHERE external_id IS NOT NULL`
      - Invalid confidence: `edge_id WHERE confidence < 0.0 OR confidence > 1.0`
      - Missing asset nodes: `asset_id WHERE NOT EXISTS (kg_nodes WHERE external_id=asset_id AND node_type='asset')`
    - `passed = len(orphan_edges) == 0 AND len(duplicate_nodes) == 0 AND len(invalid_confidence) == 0`

**Modify:**
- `src/bve/intelligence/knowledge_layer.py::KnowledgeStore._init_tables()`
  - Add `kg_integrity_log` table:
    ```sql
    CREATE TABLE IF NOT EXISTS kg_integrity_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        report_json TEXT NOT NULL,
        passed      INTEGER NOT NULL,
        checked_at  TEXT NOT NULL
    );
    ```
  - Add `log_kg_integrity(report: KGIntegrityReport) -> None`

- `src/bve/services/intelligence_service.py::IntelligenceService.run_cycle()`
  - Run `KGIntegrityChecker.check()` weekly (not every cycle — expensive at scale)
    — use a 7-day check similar to competitor discovery frequency gate
  - If `passed=False`: emit `HIGH` severity alert via `AlertRouter`
    (message: "KG integrity check failed: N orphan edges, M duplicate nodes")

**Done criteria:**
- Clean KG returns `passed=True`
- Manually inserted orphan edge is detected
- Manually inserted duplicate node (same external_id, same node_type) is detected
- `passed=False` triggers alert
- Check runs weekly, not every cycle

---

### Task 4.2 — Stress Test Suite

**Create directory:** `tests/stress/`

**Create:**
- `tests/stress/__init__.py`
- `tests/stress/conftest.py` — marks all tests in this directory with `@pytest.mark.stress`
- `src/bve/ops/load_generator.py`
  - `LoadGenerator(store: KnowledgeStore)`
  - `seed_assets(n: int) -> list[str]` — inserts N synthetic `asset_registry` rows
  - `seed_signals(n: int, asset_ids: list[str]) -> None` — inserts N `structured_signals`
  - `seed_documents(n: int, asset_ids: list[str]) -> None` — inserts N `raw_documents`
    with unique `document_hash` values
  - `seed_competitor_programs(n_per_asset: int, asset_ids: list[str]) -> None`

- `tests/stress/test_scale_500_assets.py`
  - **Scenario A**: seed 500 assets + 10k signals; run opportunity scan; measure per-asset
    scan time; assert **p95 ≤ 2 seconds per asset** (not total runtime)
  - Also records: total runtime, median scan time, max scan time

- `tests/stress/test_100k_documents.py`
  - **Scenario B**: insert 100k documents with unique hashes; run dedup check;
    assert **avg dedup check ≤ 10ms per document**

- `tests/stress/test_concurrent_writes.py`
  - **Scenario C**: 2 threads writing signals + 1 thread writing metrics simultaneously
    for 60 seconds; assert **zero data loss** (row count matches inserted count)
    and **lock retry rate ≤ 1%**
  - Note in docstring: "Do not parallelize watchlist processing loop until Postgres
    migration. This test validates that the current sequential model is safe."

- `tests/stress/test_history_replay.py`
  - **Scenario D**: replay 365 watchlist cycles for 100 assets (synthetic data);
    assert DB file size **< 500MB** and final query plan not degraded vs initial

**Add to `pyproject.toml`:**
  ```toml
  [tool.pytest.ini_options]
  markers = ["stress: marks tests as large-scale stress tests (deselect with -m 'not stress')"]
  ```

**SQLite migration gate**: If Scenario A p95 > 2s at 500 assets → activate
`ops/migrate_to_postgres.py` plan. SQLite is expected to comfortably handle Stage 2
(~150 assets, ~20k signals, ~200k documents) without hitting this gate.

**Done criteria:**
- `pytest tests/ -m "not stress"` — stress tests excluded (default CI behavior)
- `pytest tests/stress/ -m stress` — runs all 4 scenarios
- `LoadGenerator` seeds 500 assets in < 10 seconds
- All 4 scenarios have clear pass/fail assertions, not just timing prints

---

### Task 4.3 — Stage 2 Expansion (100 assets)

**Prerequisite**: Stage 1 gates from Task 2.3 must be met AND Scenario A p95 ≤ 2s.

**Action (no code):**
1. Add 70 more entries to `universe_registry.yaml`
   - Small-cap clinical-stage biotech (high signal density)
   - Priority: active Phase 2/3, upcoming catalysts, TA diversity
2. Run `bve-generate-config --batch` to generate 70 new configs
3. Review and correct; add to `watchlist_stage2.yaml`
4. Run data quality monitor for 48 hours before switching production to Stage 2

---

## Sprint 5 — Presentation Layer

### Task 5.1 — Dashboard Panel Extensions

**Create:**
- `src/bve/ui/dashboard/components/catalyst_calendar_panel.py`
  - Renders 30-day Gantt-style timeline
  - Watched-asset catalysts (from YAML `upcoming_catalysts`) + competitor completion dates
    (from `competitor_programs` table) as risk markers — clearly distinguished visually
  - Uses `visualization/catalyst_charts.py` for Plotly JSON spec

- `src/bve/ui/dashboard/components/indication_exposure_panel.py`
  - Stacked horizontal bar: each bar = one TA/indication, segments = asset count + ΔNPV
  - Derived from KG `TREATS` edges + `opportunity_alerts`

- `src/bve/ui/dashboard/components/moa_cluster_panel.py`
  - Heatmap: cluster × metric (|ΔNPV|, confidence, n_pending)
  - Uses `edge_type=SAME_MECHANISM` (not `SAME_INDICATION`) for true MoA clustering
  - User can toggle edge type in Streamlit UI

- `src/bve/visualization/catalyst_charts.py`
  - `catalyst_calendar_chart(events: list[CatalystCalendarEntry], days_forward: int) -> dict`
    — Plotly JSON spec (Gantt timeline)
  - `indication_exposure_chart(data: list[dict]) -> dict` — Plotly JSON spec

**Modify:**
- `src/bve/ui/dashboard/dashboard_app.py`
  - Add tabs or sidebar navigation for the three new panels
  - Catalyst calendar is shown by default on load (highest daily utility)

**Done criteria:**
- All three panels render without error when DB is empty (graceful empty state)
- MoA cluster panel defaults to `SAME_MECHANISM`; edge type selector changes clustering live
- Competitor risk events appear in calendar with distinct color/marker vs watched-asset catalysts

---

### Task 5.2 — Global Catalyst Calendar

**Create:**
- `src/bve/config/conference_calendar.yaml`
  - Known 2026 conference dates: ASCO (Jun), ASH (Dec), ESMO (Sep), AHA (Nov),
    DDW (May), AACR (Apr), ENDO (Jun), ASHP (Dec)
  - Format: `conference, date_range_start, date_range_end, abstract_deadline`

- `src/bve/connectors/pdufa_calendar.py`
  - `PDUFACalendarConnector` — scrapes FDA PDUFA calendar HTML page (public)
  - Uses `ServiceRateLimiter("fda_website")` (already at 1.0s min interval)
  - Returns list of `PDUFAEntry(drug_name, applicant, action_date, nda_bla_number)`
  - Falls back to empty list on scrape failure (FDA page structure changes occasionally)

- `src/bve/intelligence/catalyst_calendar.py`
  - `CatalystCalendarEntry` (Pydantic) — `event_key, asset_id, ticker, catalyst_type,
    catalyst_date, date_confidence, days_to_event, p_positive_outcome,
    expected_move_magnitude_pct, description, source, last_updated`
    - `date_confidence`: 1.0 = PDUFA confirmed; 0.7 = CT.gov primary_completion;
      0.5 = conference estimated; 0.3 = analyst estimate
  - `CatalystCalendar(store: KnowledgeStore, pdufa_connector: PDUFACalendarConnector,
    conference_calendar_path: Path)`
  - `upcoming(days: int = 30, asset_ids: Optional[list[str]] = None) -> list[CatalystCalendarEntry]`
    - Sources: PDUFA connector, CT.gov completion dates from `competitor_programs`,
      `upcoming_catalysts` from `asset_registry`, conference dates from YAML
    - Includes competitor Phase 3 completions as risk events (labeled as competitor risk)
  - `refresh(asset_ids: list[str]) -> None` — re-fetches and caches for given assets

- `src/bve/cli/catalyst_calendar.py` — `bve-catalyst-calendar`
  - `--days 30`, `--asset VRTX`, `--db path`, `--json`
  - Default text output format:
    ```
    CATALYST CALENDAR  2026-03-09 → 2026-04-08
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    +3d   SRPT  PDUFA — SRP-9001 DMD       P(+)=78%  EMM±21%  🔴 [FDA confirmed]
    +7d   CRSP  Ph3 completion — CTX001    P(+)=61%  EMM±29%  🔴 [CT.gov estimate]
    +11d  ⚠     competitor Phase3 risk     [risk to ALNY]
    ```

**Modify:**
- `src/bve/intelligence/opportunity_scanner.py`
  - Accept optional `CatalystCalendar` parameter
  - When set, populate `RankedOpportunity.catalyst_context` from `calendar.upcoming(days=30)`
  - When None: `catalyst_context` remains as-is (backward compat)

**Add to `pyproject.toml` `[project.scripts]`:**
- `bve-catalyst-calendar = "bve.cli.catalyst_calendar:main"`

**Done criteria:**
- `bve-catalyst-calendar` runs with empty `competitor_programs` (no crash)
- PDUFA scraper failure returns empty list, not exception
- Competitor risk events clearly labeled (not confused with watched-asset catalysts)
- `CatalystCalendar` with no `PDUFACalendarConnector` falls back to CT.gov + YAML sources only

---

## Sprint 6 — Stage 3 + Zero-YAML Provider

### Task 6.1 — AutoConfigAssetContextProvider

**Prerequisites**: Stage 2 stable for 2+ weeks; stress tests pass; `DiskCache` proven reliable.

**Modify:**
- `src/bve/pipeline/watchlist_runner.py`
  - Add `AutoConfigAssetContextProvider` implementing `AssetContextProvider` protocol
    - `get_context(asset: WatchlistAsset) -> AssetValuationContext`
    - When `valuation_config=None`: builds `AssetValuationContext` in-memory from:
      1. `KnowledgeStore.get_asset_registry_entry(asset.asset_id)` for seed TAM/pricing
      2. CT.gov NCT data (via `DiskCache`)
      3. SEC financials (via `DiskCache`)
      4. `AssumptionsLoader` PoS defaults
    - Caches resulting `AssetValuationContext` in-memory per `asset_id` per run
  - Replace `ConfigAssetContextProvider()` default with `CompositeAssetContextProvider`:
    - Tries `ConfigAssetContextProvider` first (when `valuation_config` is set)
    - Falls through to `AutoConfigAssetContextProvider` when `valuation_config=None`
    - This is fully backward-compatible — existing configs continue to work unchanged

**Create:**
- `examples/configs/watchlists/watchlist_stage3.yaml`
  - 300+ assets; all using `valuation_config: null` (relying on auto-provider)
  - Requires `asset_registry` table populated for all entries

**Done criteria:**
- Asset with `valuation_config: null` and a valid `asset_registry` entry runs through
  full pipeline without error
- Asset with `valuation_config: some/path.yaml` behaves identically to before
- `CompositeAssetContextProvider` logs which provider resolved each asset

---

## Sprint 8 — Acquisition Screening + M&A Replay

### Task 8.1 — Acquisition Discount Screener

**Status (2026-03-22): complete**

**Why first**: Highest-value, lowest-risk entry point. Reuses the current valuation
engine, market-cap snapshots, and knowledge-store plumbing without requiring new
connectors or LLM work.

**Modeling checkpoint before coding:**
- `RNPVResult.rnpv_millions` is already risk-adjusted in this repo.
- The screener must therefore implement exactly one of:
  1. `acquisition_discount = rnpv_millions / enterprise_value`
  2. `acquisition_discount = unrisked_pipeline_value × model_pos / enterprise_value`
- Do **not** implement `rnpv_millions × model_pos / enterprise_value`; that would
  double-apply approval probability.

**Create:**
- `src/bve/intelligence/acquisition_screen.py`
  - `AcquisitionScreenConfig`
  - `AcquisitionDiscountSnapshot`
  - `AcquisitionScreenRow`
  - `AcquisitionScreenResult`
  - `AcquisitionScreener.screen_assets(...)`
  - Enterprise-value resolution path:
    - base case: `EV = market_cap - net_cash`
    - optional extension: add debt when available
    - every row must store `ev_methodology` so missing-debt assumptions are visible

- `src/bve/cli/acquisition_screen.py`
  - `bve-acquisition-screen`
  - Flags:
    - `--db`
    - `--universe-file`
    - `--threshold 2.0`
    - `--phase2-plus-only`
    - `--with-comps`
    - `--json`

**Modify:**
- `src/bve/intelligence/knowledge_layer.py`
  - Add `acquisition_discount_snapshots` table:
    ```sql
    CREATE TABLE IF NOT EXISTS acquisition_discount_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        asset_id TEXT NOT NULL,
        ticker TEXT,
        snapshot_date TEXT NOT NULL,
        formula_version TEXT NOT NULL,
        model_rnpv_millions REAL,
        model_pos REAL,
        market_cap_millions REAL,
        enterprise_value_millions REAL,
        net_cash_millions REAL,
        acquisition_discount REAL,
        passes_threshold INTEGER NOT NULL,
        is_acquisition_ready INTEGER,
        exclusion_reason TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(asset_id, snapshot_date, formula_version)
    );
    ```
  - Add `upsert_acquisition_discount_snapshot()`
  - Add `get_latest_acquisition_discount_snapshot(asset_id)`
  - Add `list_acquisition_discount_snapshots(...)`

- `pyproject.toml`
  - Register `bve-acquisition-screen = "bve.cli.acquisition_screen:main"`

**Done criteria:**
- CLI prints a sorted table with `asset_id, ticker, market_cap, EV, rnpv, model_pos,
  acquisition_discount, threshold_flag`
- Universe-wide run surfaces all assets, including rows excluded for missing EV or
  missing valuation snapshot
- Threshold filter `acquisition_discount > 2.0` works deterministically
- Snapshot rows are persisted for longitudinal tracking
- Full unit coverage for EV resolution, missing-data behavior, and thresholding

---

### Task 8.2 — Comparable Deal Database

**Status (2026-03-22): engineering complete; manual comp set seeded at 26
screenable public deals and backed by a 43-deal broader sourcing universe in
`research/mna/deal_universe_2020_2026.yaml`, plus a named live-target monitor in
`research/mna/target_monitor.yaml`**

**Why second**: The research work is manual and should start early, but the engineering
side should stay deliberately thin and deterministic.

**Create:**
- `research/mna/comparable_deals.yaml`
  - 30-50 biotech M&A deals from the last 3 years
  - Required fields per record:
    - `target_name`
    - `ticker`
    - `drug_name`
    - `indication`
    - `therapeutic_area`
    - `phase_at_acquisition`
    - `acquirer`
    - `deal_date`
    - `enterprise_value_millions`
    - `peak_sales_millions`
    - `ev_to_peak_sales`
    - `source`
    - `notes`

- `src/bve/intelligence/comparable_deals.py`
  - `ComparableDeal`
  - `ComparableDealSet`
  - `ComparableDealMatch`
  - `ComparableDealLoader.load(path)`
  - `ComparableDealMatcher.match(asset_context, deals)`
  - Matching tiers:
    1. exact indication + phase bucket
    2. therapeutic area + phase bucket
    3. phase bucket only

- `tests/intelligence/test_comparable_deals.py`

**Design decisions:**
- Manual research remains outside the app; the code only validates and compares
- Primary comparison metric is `enterprise_value / peak_sales`
- Assets with insufficient comparable coverage must return explicit `"no_comps"` output,
  not silent omission

**Done criteria:**
- YAML validates cleanly with 30-50 rows
- Every watchlist asset can produce either a peer percentile or an explicit no-comps state
- `--with-comps` enriches the acquisition screen output without requiring a DB migration

---

### Task 8.3 — Acquisition Readiness Filter

**Status (2026-03-22): complete**

**Why before replay rebuild**: The M&A replay should operate on the acquisition-eligible
universe, not the short-dated catalyst universe.

**Create:**
- `src/bve/intelligence/acquisition_readiness.py`
  - `AcquisitionReadinessAssessment`
  - `AcquisitionReadinessEvaluator`
  - `ReadinessReason` enum or string constants

- `tests/intelligence/test_acquisition_readiness.py`

**Reuse existing signals rather than inventing a new model:**
- `src/bve/intelligence/trial_design_feature_extractor.py`
- `src/bve/intelligence/phase_correlation_updater.py`
- `structured_signals` / `valuation_diffs` / `market_expectations` records already in `KnowledgeStore`

**Rules for v1:**
- Default include set: assets with Phase 2 proof-of-concept data or later
- Stage floor: `phase_2` or higher
- Positive evidence can come from:
  - confirmed Phase 2/3 readout with `primary_endpoint_met=True`
  - phase-correlation posterior update sourced from prior efficacy data
  - explicit manual override in config when evidence is known but not yet structured
- Exclude:
  - preclinical / Phase 1 only assets
  - negative Phase 2 proof-of-concept assets
  - assets missing enough structured evidence to support inclusion
- Every exclusion must emit a reason string so the screen remains auditable

**Modify:**
- `src/bve/intelligence/acquisition_screen.py`
  - Add readiness filtering and readiness columns
  - `phase2_plus_only` should default to `False` in the first validation pass, then
    become the default once the readiness logic is verified on the full universe

**Done criteria:**
- Readiness classification requires no new network calls
- Screen output shows `is_acquisition_ready` plus a human-readable reason
- Existing trial-design and phase-correlation math is unchanged in v1
- Tests cover positive Phase 2, Phase 1-only, ambiguous evidence, and refuted efficacy

---

### Task 8.4 — M&A Replay Profile

**Status (2026-03-22): complete**

**Why last**: Depends on the screen, readiness filter, and comparable-deal framing to
define the right universe and objective function.

**Key gaps to close first:**
- Current replay cadence supports `weekly` and `biweekly` only
- Current `ReplayPolicyConfig.max_positions` is a per-step decision cap, not a true
  open-book concentration cap

**Modify:**
- `src/bve/intelligence/replay_policy.py`
  - Add `max_open_positions`
  - Add profile defaults for `mna_acquisition_v1`:
    - `max_open_positions=8`
    - `max_positions=8`
    - `max_hold_days=365`
    - `loss_block_threshold_pct=-40.0`
    - `require_catalyst_within_days=0`
    - `catalyst_timing=False`
  - Enforce open-position cap before emitting new decisions

- `src/bve/ops/historical_replay.py`
  - Support `cadence="quarterly"`
  - Use calendar-based three-month stepping, not a fixed 84-day approximation
  - Add `--profile mna_acquisition_v1` or equivalent explicit flags
  - Pass current open-position count into replay policy selection

- `src/bve/analysis/portfolio_experiments.py`
  - Add M&A experiment rows:
    - quarterly cadence
    - 365-day hold
    - top-8 concentration
    - no catalyst gate
    - `-40%` loss block

- `tests/test_replay_policy.py`
- `tests/test_historical_replay.py`
- `tests/test_portfolio_experiments.py`

**Done criteria:**
- Quarterly replay advances correctly across the full date range without date drift
- No new entries are opened once 8 positions are already live
- Hold-period exits occur at 365 days when no earlier exit condition exists
- Catalyst-density/timing gates are fully disabled for the M&A profile
- Loss blocking triggers only below `-40%`
- Report compares M&A profile results against the current short-horizon baseline

---

### Task 8.5 — Unified Mispricing Screener

**Status (2026-03-24): engineering complete**

**Why now:** The engine already has the three core primitives needed for a higher-signal
screening surface:
- ranking output in `src/bve/intelligence/ranking.py`
- acquisition discount output in `src/bve/intelligence/acquisition_screen.py`
- catalyst timing from `KnowledgeStore.get_catalyst_events()` and the catalyst calendar layer

The missing piece is a deterministic asset-level aggregator and CLI that present those
signals in one ranked report without introducing a parallel valuation stack.

**Create:**
- `src/bve/intelligence/mispricing_screener.py`
  - `MispricingScreenConfig`
  - `MispricingScreenRow`
  - `MispricingScreenResult`
  - `UnifiedMispricingScreener`
  - Responsibilities:
    - load ranked opportunities from `AssetRankingEngine`
    - run a fresh `AcquisitionScreener` pass for the same watchlist / `as_of` date
    - attach nearest active catalyst and `days_to_catalyst`
    - surface stage, model PoS, implied PoS, and `pos_gap`
    - compute one versioned `unified_score`

- `src/bve/cli/screen.py`
  - `bve-screen --watchlist <file> --output-format report|json`
  - Flags:
    - `--watchlist`
    - `--db`
    - `--as-of`
    - `--top`
    - `--days-ahead`
    - `--output-format report|json`
    - `--output`

**Scoring contract (v1):**
- Ranking remains the dominant component
- Acquisition discount is the second-largest component
- Catalyst timing is a bounded modifier, not an unbounded force multiplier
- Stage is light context only
- PoS adjustment must use `pos_gap` or bounded posterior-vs-prior evidence deltas,
  not raw PoS, because `rnpv_millions` already embeds approval probability
- Missing inputs degrade to neutral values and explicit notes; assets are not silently dropped

**Report output must include:**
- `rank`
- `asset_id`
- `ticker`
- `unified_score`
- `mispricing_pct`
- `rnpv_millions`
- `enterprise_value_millions`
- `acquisition_discount`
- `stage`
- `model_pos`
- `implied_pos`
- `pos_gap`
- `next_catalyst`
- `days_to_catalyst`

**Completed implementation steps:**
1. Added the tracker entry and finalized the row / score contract
2. Implemented the intelligence-layer aggregator with deterministic joins by `asset_id`
3. Implemented `bve-screen` CLI and report rendering
4. Added deterministic tests for scoring, tie-breaking, missing-data handling, and CLI output
5. Registered the console script and ran targeted pytest coverage

**Done criteria:**
- `bve-screen --watchlist <file> --output-format report` returns one ranked watchlist report
- The implementation reuses ranking, acquisition, and catalyst plumbing instead of
  duplicating valuation math
- Read path remains DB-backed and deterministic
- Tests cover both happy path and incomplete-data behavior

---

### Task 8.6 — Acquirer Pipeline Gap Analysis

**Status (2026-03-24): engineering complete**
**Progress (2026-03-24): Steps 1-6 complete; profile curation, typed loading, deterministic scoring, watchlist/acquisition/comps integration, acquisition-memo generation, deterministic tests, and the direct `bve-acquirer-fit` CLI/report surface are in place.**

**Why now:** The M&A layer can already identify undervalued and acquisition-ready targets,
but it still lacks the acquirer-side lens needed to answer the harder question:
which strategic buyer is the best fit for a given target, and why.

**Initial acquirer:**
- `regeneron`

**Create:**
- `research/mna/pipeline_gaps.yaml`
  - Manually curated acquirer profiles with exact-dated source metadata
  - First profile: Regeneron Pharmaceuticals
  - Required fields for Step 1:
    - therapeutic areas with LOE / franchise-pressure exposure
    - historically preferred modalities
    - stated strategic priorities from earnings calls / investor presentations
    - recent deal history and implied valuation bands
    - budget snapshot (`cash`, `debt`, net cash, plus capacity notes)

- `src/bve/intelligence/acquirer_profiles.py`
  - `AcquirerProfile`
  - `TherapeuticGap`
  - `PreferredModality`
  - `StrategicPriority`
  - `RecentDeal`
  - `BudgetSnapshot`
  - `AcquirerProfileLoader.load(path)`

- `src/bve/intelligence/acquirer_fit.py`
  - `AcquirerFitScore`
  - `AcquirerFitScorer`
  - Responsibilities:
    - match targets against acquirer therapeutic gaps
    - score modality alignment
    - score stage / readiness fit
    - score strategic-priority overlap
    - score valuation-range fit using comp / screen context
    - score budget fit and emit explicit hard-fail reasons

**Reuse boundaries:**
- Target set should come from existing watchlist + acquisition screen outputs
- Valuation framing should reuse:
  - `src/bve/intelligence/acquisition_screen.py`
  - `src/bve/intelligence/comparable_deals.py`
  - `src/bve/intelligence/mispricing_screener.py`
- Deal structure should reuse:
  - `src/bve/models/deal_economics.py`
- Memo generation should reuse:
  - `src/bve/reporting/memo_generator.py`
  - existing `bd` memo surface where possible

**Step-by-step plan:**
1. Manually curate Regeneron into `research/mna/pipeline_gaps.yaml`
2. Add typed loader / validator for acquirer profiles
3. Build deterministic `AcquirerFitScorer`
4. Integrate scorer with target universe, acquisition screen, and comparable deals
5. Generate one acquisition memo per target using existing memo and deal-economics plumbing
6. Add deterministic tests and, if useful, expose the flow through a small CLI/report command

**Completed implementation steps:**
1. Curated the initial Regeneron acquirer profile in `research/mna/pipeline_gaps.yaml`
2. Added typed acquirer-profile loading and validation in `src/bve/intelligence/acquirer_profiles.py`
3. Implemented deterministic component scoring in `src/bve/intelligence/acquirer_fit.py`
4. Integrated acquisition-screen rows, comparable deals, and acquirer-fit ranking across a watchlist
5. Reused the existing BD memo generator plus deal economics in `src/bve/intelligence/acquisition_memo.py`
6. Added the direct `bve-acquirer-fit` CLI with report/JSON output and optional per-target memo generation
7. Added deterministic unit coverage for profile loading, scoring, integration, memo generation, and the CLI surface

**CLI acceptance:**
- `bve-acquirer-fit --watchlist <file> --acquirer regeneron --output-format report` returns a ranked fit report
- The CLI can optionally emit one acquisition memo per ranked target and persist those memos into the knowledge store
- The implementation reuses the existing acquisition screen, comparable deals, BD memo generator, and deal-economics plumbing
- Ranking and memo generation remain deterministic under fixed fixtures

**Done criteria:**
- Regeneron profile is attributable, dated, and auditable from primary sources
- `AcquirerFitScorer` returns component-level fit attribution, not just a black-box score
- Budget and valuation mismatches are explicit in output
- Per-target acquisition memos reuse existing reporting paths rather than introducing a second memo framework

---

### Task 8.7 — M&A Probability Scanner

**Status (2026-03-24): Steps 1-5 complete**
**Progress (2026-03-24): Added the vulnerability-signal dataset and loader, implemented `src/bve/intelligence/ma_probability.py` to rank watchlist targets by bounded acquisition probability across all configured acquirers while keeping valuation, strategic fit, stage, and vulnerability as separate components, completed Step 4 with persisted daily M&A probability snapshots plus idempotent threshold-cross and top-entry alerts backed by `opportunity_alerts`, and completed Step 5 with a direct `bve-ma-probability` CLI/report surface.**

**Why now:** The acquisition-discount and acquirer-fit layers can already answer
"who looks cheap?" and "who fits which buyer?", but the stack still lacks a
watchlist-level probability lens that combines strategic fit, de-risking, and
target-side vulnerability into one acquisition-likelihood output.

**Build on:**
- `src/bve/intelligence/acquirer_fit.py`
- `src/bve/intelligence/acquisition_screen.py`
- `src/bve/intelligence/capital_structure.py`
- `src/bve/intelligence/opportunity_scanner.py`
- `src/bve/intelligence/opportunity_monitor.py`

**Create:**
- `research/mna/vulnerability_signals.yaml`
  - versioned manual signal dataset
  - cash-runway policy points back to dynamic computation in `capital_structure.py`
  - manually curated overlays for:
    - insider activity
    - board / management changes
    - recent same-space external deal activity

- `src/bve/intelligence/vulnerability_signals.py`
  - typed loader / validator for the YAML schema
  - models for:
    - target-specific vulnerability signals
    - sector / same-space deal activity signals
    - dated source references and staleness windows

- `src/bve/intelligence/ma_probability.py`
  - `MAProbabilityConfig`
  - `MAProbabilityRow`
  - `MAProbabilityResult`
  - `MAProbabilityScanner`
  - responsibilities:
    - evaluate all relevant acquirers per target
    - combine valuation discount, strategic fit, stage/readiness, and vulnerability overlays
    - emit a bounded `p_acquisition`
    - retain component breakdown and best-acquirer explanations

- `src/bve/cli/ma_probability.py`
  - weekly scan surface
  - report and JSON output
  - optional alert emission when `p_acquisition >= 0.70`

**Reuse boundaries:**
- Strategic-fit inputs must reuse `acquirer_fit.py`, not rebuild buyer matching from scratch
- Cash-runway pressure must reuse `capital_structure.py`
- Weekly top-10 and threshold-cross persistence should reuse `opportunity_alerts`
- Weekly summary should plug into the existing weekly-brief/reporting path where practical

**Step-by-step plan:**
1. Create `research/mna/vulnerability_signals.yaml`
2. Add typed loader / validator for vulnerability signals
3. Build deterministic `MAProbabilityScanner`
4. Add alert persistence for threshold-cross and top-10 entry signals
5. Add a direct CLI/report surface
6. Extend weekly output with top-10 M&A candidates
7. Add deterministic tests and score-versioned calibration hooks

**Acceptance:**
- Weekly scan returns the top 10 highest `p_acquisition` targets for the watchlist
- Threshold-cross events at `>= 0.70` are idempotently persisted and can be routed as alerts
- The score contract is decomposed and avoids double-counting acquirer-fit inputs
- Cash-runway pressure is derived dynamically; manually curated vulnerability signals are dated and auditable

**Completed so far:**
1. Created `research/mna/vulnerability_signals.yaml` with a versioned split between dynamic runway pressure and manually curated overlays
2. Added `src/bve/intelligence/vulnerability_signals.py` with typed models, duplicate-ID validation, staleness-window validation, target matching helpers, and external-deal lookup
3. Added `tests/intelligence/test_vulnerability_signals.py` covering repository YAML loading, duplicate-ID rejection, staleness-window validation, identifier requirements, and stale-signal filtering
4. Added `src/bve/intelligence/ma_probability.py` with:
   - `MAProbabilityConfig`
   - `VulnerabilityAssessment`
   - `MAAcquirerCandidate`
   - `MAProbabilityRow`
   - `MAProbabilityResult`
   - `MAProbabilityScanner`
   - multi-acquirer ranking built on top of `AcquirerFitEngine` and the acquisition screen
   - separate probability components for valuation discount, strategic fit, de-risking stage, and vulnerability
   - deterministic best-acquirer selection plus runner-up retention
5. Extended `src/bve/intelligence/capital_structure.py` with an as-of-aware capital-risk helper so acquisition-probability scans remain deterministic for arbitrary snapshot dates
6. Added `tests/intelligence/test_ma_probability.py` covering:
   - watchlist ranking across multiple acquirers
   - dynamic runway / catalyst vulnerability
   - separation of strategic-fit scoring from valuation discount changes
7. Extended `src/bve/intelligence/ma_probability.py` with:
   - `MAProbabilitySnapshotRecord`
   - `MAProbabilitySnapshotStore`
   - `MAProbabilityMonitorConfig`
   - `MAProbabilityMonitorResult`
   - `MAProbabilityMonitor`
   - deterministic scan timestamps for historical snapshot dates
   - persisted daily M&A probability snapshots for all ranked rows
   - idempotent `ma_probability_threshold_cross` and `ma_probability_top_n_entry` alerts stored via `opportunity_alerts`
8. Extended `tests/intelligence/test_ma_probability.py` with monitor coverage for:
   - snapshot persistence across scan dates
   - threshold-cross alert emission at `>= 0.70`
   - top-entry alert emission when a target moves into the configured top window
   - duplicate suppression on same-day reruns
9. Added `src/bve/cli/ma_probability.py` and registered `bve-ma-probability` with:
   - report and JSON output modes
   - `--watchlist`, `--as-of`, `--top`, and `--alert-threshold`
   - configurable profile / comp / vulnerability research file inputs
   - explicit `--emit-alerts` control so ad hoc scans do not persist snapshots or alerts unless requested
10. Added `tests/intelligence/test_ma_probability_cli.py` covering:
   - report rendering for the new scan surface
   - JSON output
   - CLI forwarding of `--emit-alerts`, `--alert-threshold`, `--top`, `--as-of`, and readiness-filter settings

---

## Summary Checklist

### Sprint 1
- [ ] Task 1.1 — Universe Registry YAML + data models
- [ ] Task 1.2 — DiskCache (`outputs/cache/`, 3 namespaces, TTLs)
- [ ] Task 1.3 — AutoConfigGenerator + config snapshot versioning (`_meta` block)
- [ ] Task 1.4 — `asset_registry` DB table + `UNIQUE(ticker, drug_name, indication)`
- [ ] Task 1.5 — Competitor discovery wiring (7-day frequency gate)
- [ ] Task 1.6 — Staged watchlist files + `--watchlist-dir`

### Sprint 2
- [ ] Task 2.1 — Data quality monitor (6 checks, `data_quality_log` table, gate ≥0.70)
- [ ] Task 2.2 — Connector health metrics + stage latency (p50/p95/p99)
- [ ] Task 2.3 — Stage 1 live (30 assets); observe 1–2 weeks

### Sprint 3
- [ ] Task 3.1 — Catalyst model (layer-separated; integrates TrialDesignAssessment)
- [ ] Task 3.2 — Ranking calibrator + `ranking_calibration.yaml`
- [ ] Task 3.3 — `backtest_snapshots` table + AlertRouter wiring + `PortfolioBacktester`

### Sprint 4
- [ ] Task 4.1 — KG integrity checker (weekly; HIGH alert on failure)
- [ ] Task 4.2 — Stress test suite (p95 per-asset ≤2s gate for Stage 3)
- [ ] Task 4.3 — Stage 2 expansion (100 assets; gated by Task 4.2 Scenario A)

### Sprint 5 — Decision + Capital Allocation Engine ✅ COMPLETE (2026-03-18)
- [x] Task 5.1 — Wave J: Decision + Position Layer (`decision_layer.py`)
- [x] Task 5.2 — Wave K: Weekly Actionable Output Generator (`actionable_output.py`)
- [x] Task 5.3 — Wave M: Weighted Thesis Strength (extend `thesis_tracker.py`)
- [x] Task 5.4 — Wave L: Weekly Review Engine (`weekly_review.py`)

### Sprint 6 — Dashboard + Stage Expansion
- [ ] Task 6.1 — Dashboard panel extensions (catalyst calendar, indication exposure, MoA cluster)
- [ ] Task 6.2 — Global catalyst calendar + PDUFA connector + `conference_calendar.yaml`

### Sprint 7
- [ ] Task 7.1 — `AutoConfigAssetContextProvider` + Stage 3 expansion

### Sprint 8
- [x] Task 8.1 — Acquisition discount screener + snapshot table + CLI
- [ ] Task 8.2 — Comparable deal YAML + loader + percentile comparison
- [x] Task 8.3 — Acquisition readiness filter (Phase 2 POC+ gate)
- [x] Task 8.4 — M&A replay profile (quarterly, 365d, top-8, no catalyst gate, -40% block)
- [x] Task 8.5 — Unified mispricing screener (`bve-screen`)
- [x] Task 8.6 — Acquirer pipeline gap analysis + fit scoring + acquisition memo flow
- [ ] Task 8.7 — M&A probability scanner + vulnerability signals + weekly/alert output

---

## Sprint 5 Task Specifications

### Task 5.1 — Wave J: Decision + Position Layer

**Why first:** K immediately consumes recommended_action; L needs sizing quality data.
Without this, the learning loop has no ground truth.

**Create:** `src/bve/intelligence/decision_layer.py`

**Three SQLite tables** (lazy creation via `_ensure_schema()`):

```
decision_records
  decision_id TEXT PRIMARY KEY
  asset_id TEXT NOT NULL
  signal_id TEXT
  thesis_id TEXT                          -- FK to thesis_claims (nullable)
  recommended_action TEXT NOT NULL        -- buy | size_up | hold | reduce | pass | exit
  recommended_size_pct REAL
  executed_action TEXT                    -- set after actual execution (may differ)
  executed_size_pct REAL
  signal_strength REAL
  portfolio_exposure_pct_at_decision REAL -- total portfolio pct at decision time
  catalyst_bucket_exposure_pct REAL       -- pct in same catalyst type (e.g. ASCO readouts)
  indication_bucket_exposure_pct REAL     -- pct in same indication (e.g. oncology)
  liquidity_bucket TEXT                   -- liquid | semi_liquid | illiquid
  conviction_tier TEXT                    -- high | medium | low | speculative
  critic_flags_count INT DEFAULT 0
  reasoning_text TEXT
  decided_at TEXT NOT NULL

position_snapshots
  snapshot_id TEXT PRIMARY KEY
  asset_id TEXT NOT NULL
  decision_id TEXT                        -- FK to decision_records
  entry_date TEXT NOT NULL
  entry_price_usd REAL
  current_size_pct REAL NOT NULL
  linked_catalyst_id TEXT
  thesis_strength_at_entry REAL
  is_active INTEGER DEFAULT 1
  exit_date TEXT
  exit_price_usd REAL
  exit_reason TEXT                        -- catalyst_resolved | thesis_refuted | stop_loss |
                                          --   profit_target | rebalance | manual
  holding_period_days INT                 -- set at close: exit_date - entry_date
  created_at TEXT NOT NULL

outcome_attributions
  attribution_id TEXT PRIMARY KEY
  decision_id TEXT NOT NULL
  asset_id TEXT NOT NULL
  return_pct REAL NOT NULL
  attribution_type TEXT NOT NULL          -- pos_error | timing_error | sizing_error |
                                          --   thesis_error | market_drift | confirmed_thesis |
                                          --   unclassified
  resolved_at TEXT NOT NULL
  notes TEXT
```

**`DecisionLayer` class:**
```python
class DecisionLayer:
    def __init__(self, store: Any) -> None
    def record_decision(...) -> DecisionRecord
    def update_execution(decision_id, executed_action, executed_size_pct) -> Optional[DecisionRecord]
    def record_position(asset_id, entry_price, size_pct, *, decision_id, ...) -> PositionSnapshot
    def close_position(asset_id, exit_price, exit_reason) -> Optional[PositionSnapshot]
    def attribute_outcome(decision_id, return_pct, attribution_type, notes="") -> OutcomeAttribution
    def get_active_positions() -> list[PositionSnapshot]
    def get_decision_history(asset_id=None, limit=100) -> list[DecisionRecord]
    def model_vs_execution_drift() -> dict   # {n_diverged, n_total, pct_diverged}
```

**Key invariants:**
- `recommended_action` always set at record time; `executed_action` is set later via `update_execution()`
- `holding_period_days` computed from `exit_date - entry_date` at close, not stored before then
- All portfolio context fields are snapshots at decision time, not recomputed live

**Done criteria:**
- All three tables created lazily
- `record_decision()` + `update_execution()` round-trip preserves both recommended and executed
- `close_position()` sets `holding_period_days` and `is_active=0`
- `model_vs_execution_drift()` correctly counts diverged decisions
- Full test coverage (~25 tests)

---

### Task 5.2 — Wave K: Weekly Actionable Output Generator

**Why after J:** Needs `DecisionLayer.record_decision()` to persist recommended actions.

**Create:** `src/bve/intelligence/actionable_output.py`

**`ScoredCandidate` dataclass** (input, decoupled from specific opportunity format):
```python
@dataclass
class ScoredCandidate:
    asset_id: str
    ticker: str
    ranking_score: float        # from ranking engine
    opportunity_score: float = 0.0
    thesis_strength: Optional[float] = None   # from ThesisTracker.snapshot()
    critic_severity: Optional[str] = None     # "caution" | "warning" | None
    catalyst_description: str = ""
    indication: str = ""
    company_id: str = ""
```

**`ActionableOpportunity` model** (frozen Pydantic):
```python
class ActionableOpportunity(BaseModel):
    asset_id: str
    ticker: str
    recommended_action: str          # buy | add | monitor | avoid
    recommended_size_pct: float
    catalyst_description: str
    composite_score: float           # weighted combination
    ranking_component: float         # contribution from ranking_score
    thesis_component: float          # contribution from thesis_strength
    opportunity_component: float     # contribution from opportunity_score
    score_version: str               # e.g. "v1.0" — logged for regime comparison
    thesis_strength: Optional[float]
    critic_severity: Optional[str]
    risk_flags: list[str]
    one_line_summary: str
```

**`WeeklyActionableReport` model:**
```python
class WeeklyActionableReport(BaseModel):
    generated_at: datetime
    week_ending: date
    score_version: str
    score_weights: dict[str, float]  # {"ranking": 0.5, "thesis": 0.3, "opportunity": 0.2}
    opportunities: list[ActionableOpportunity]   # max top_n, ordered by composite_score desc
    n_considered: int
    n_filtered_by_min_score: int
    n_elevated_by_critic: int        # caution → downgraded to "monitor"
    has_actionable: bool             # False when list is empty — explicit, never silent
```

**`ActionableGenerator` class:**
```python
class ActionableGenerator:
    SCORE_VERSION = "v1.0"
    DEFAULT_WEIGHTS = {"ranking": 0.5, "thesis": 0.3, "opportunity": 0.2}

    def __init__(self, weights=None, min_composite_score=0.0, max_position_pct=0.20)
    def generate(candidates, *, top_n=5, week_ending=None) -> WeeklyActionableReport
```

**`generate()` pipeline:**
1. Compute `composite = w_r×ranking_score + w_t×thesis_strength_or_zero + w_o×opportunity_score`
2. Determine `recommended_action`:
   - composite ≥ 0.70 → "buy"
   - composite ≥ 0.50 → "add"
   - critic_severity == "caution" → downgrade to "monitor"
   - composite < min_composite_score → "avoid"
3. Sort by composite descending; take top_n
4. Compute `recommended_size_pct = min(max_position_pct, max(0.01, composite × max_position_pct))`
5. Build `risk_flags` from critic_severity + thesis_strength thresholds
6. Format `one_line_summary`
7. Return report with full score decomposition and `has_actionable`

**Key invariant:** `generate()` always returns a report. `has_actionable=False` is explicit.
Score weights are always logged in the report for longitudinal regime comparison.

**Done criteria:**
- `generate()` with empty list returns `has_actionable=False` report
- Score decomposition (ranking/thesis/opportunity components) stored on each opportunity
- `score_version` and `score_weights` logged in every report
- Critic caution correctly downgrades action to "monitor"
- Full test coverage (~20 tests)

---

### Task 5.3 — Wave M: Weighted Thesis Strength

**Why before L:** `WeeklyReviewEngine` consumes `weighted_thesis_strength` for confirmed_thesis
classification. If thesis strength is noisy, L's error taxonomy is polluted upstream.

**Modify:** `src/bve/intelligence/thesis_tracker.py`

**Schema migration** (backward-compatible):
```python
# In _ensure_schema(), add after CREATE TABLE:
self.store._conn.execute(
    "ALTER TABLE thesis_claims ADD COLUMN weight REAL DEFAULT 1.0"
)
# Catch OperationalError (column already exists) silently
```

**Default weights by ClaimType:**
```python
DEFAULT_CLAIM_WEIGHTS: dict[ClaimType, float] = {
    ClaimType.ENDPOINT_MET:            2.0,   # binary, high-stakes, directly valuation-relevant
    ClaimType.REGULATORY_PATHWAY:      1.5,   # FDA designation / label change
    ClaimType.COMPETITOR_FAILURE:      1.5,   # structural market share impact
    ClaimType.LABEL_EXPANSION:         1.25,
    ClaimType.POS_ABOVE_THRESHOLD:     1.0,
    ClaimType.ENROLLMENT_ON_TRACK:     0.75,  # execution signal, not outcome
    ClaimType.MARKET_REACTION_POSITIVE: 0.5,  # lagging / supportive only
    ClaimType.CUSTOM:                  1.0,
}
```

**Changes to `ThesisClaim`:**
- Add `weight: float = Field(default=1.0, ge=0.0)` field

**Changes to `ThesisSnapshot`:**
- Add `weighted_thesis_strength: Optional[float] = None` field
- Existing `thesis_strength` (unweighted) preserved for backward compatibility

**Changes to `ThesisTracker.snapshot()`:**
- Compute `weighted_thesis_strength = Σ(weight_i for confirmed) / Σ(weight_i for resolved)`
- Only computed when `n_resolved > 0`, else `None`

**Changes to `add_claim()`:**
- Add `weight: Optional[float] = None` parameter
- Default: `weight = DEFAULT_CLAIM_WEIGHTS.get(claim_type, 1.0)` when None

**Done criteria:**
- Migration runs safely on existing DB (column already exists → no error)
- `add_claim()` uses DEFAULT_CLAIM_WEIGHTS when no weight provided
- A refuted ENDPOINT_MET (weight=2.0) dominates two confirmed MARKET_REACTION_POSITIVE (weight=0.5 each)
- `thesis_strength` (unweighted) unchanged — existing tests still pass
- ~8 new tests for weighted path

---

### Task 5.4 — Wave L: Weekly Review Engine

**Why last:** Consumes DecisionLayer (sizing quality), ThesisTracker (thesis accuracy),
and forecast_records (fundamental accuracy). All must be populated first.

**Create:** `src/bve/intelligence/weekly_review.py`

**Four structured review sections:**

```python
class FundamentalAccuracy(BaseModel):
    n_resolved: int
    n_correct: int
    hit_rate: Optional[float]           # n_correct / n_resolved
    n_pos_error: int                    # predicted direction wrong on trial_readout
    n_timing_error: int                 # correct direction, signal age > 30d at execution
    n_market_drift: int                 # correct direction, return < 0 (market moved against)
    n_unclassified: int

class MarketTimingAccuracy(BaseModel):
    n_stale_signals: int                # signals > 30d old when forecast recorded
    avg_signal_age_days: Optional[float]
    pct_stale: Optional[float]

class ThesisAccuracy(BaseModel):
    n_key_claims_confirmed: int         # ENDPOINT_MET, REGULATORY_PATHWAY, COMPETITOR_FAILURE
    n_key_claims_refuted: int
    n_assets_with_refuted_key_claim: int
    net_thesis_score: Optional[float]   # (confirmed - refuted) / total_key_resolved

class SizingQuality(BaseModel):
    n_decisions_with_sizing: int
    n_recommended_vs_executed_diverged: int
    pct_diverged: Optional[float]
    avg_size_divergence_pct: Optional[float]   # mean(|executed - recommended|) in pp
    n_oversized: int                    # executed > recommended by > 2pp
```

**`WeeklyReviewReport` model:**
```python
class WeeklyReviewReport(BaseModel):
    week_ending: date
    fundamental: FundamentalAccuracy
    market_timing: MarketTimingAccuracy
    thesis: ThesisAccuracy
    sizing: SizingQuality
    top_miss: Optional[str]             # asset_id with largest negative surprise
    top_win: Optional[str]              # asset_id with largest positive return
    calibration_drift_fired: bool
    generated_at: datetime
```

**`WeeklyReviewEngine` class:**
```python
class WeeklyReviewEngine:
    def __init__(self, store: Any, decision_layer: Optional[DecisionLayer] = None,
                 thesis_tracker: Optional[ThesisTracker] = None)
    def run_review(*, week_ending=None, lookback_days=7) -> WeeklyReviewReport
```

**Strict `confirmed_thesis` classification rule** (NOT just "return > 0"):

A forecast is classified as `confirmed_thesis` only when ALL of:
1. `return_pct > 0` (market outcome positive)
2. AND at least one of:
   - A `ThesisClaim` with `claim_type in {ENDPOINT_MET, POS_ABOVE_THRESHOLD, REGULATORY_PATHWAY}`
     was `confirmed` for this asset within the same lookback window
   - OR the forecast `event_type` is `trial_readout` and `predicted_direction` matches
     the `primary_endpoint_met` resolution
3. AND no `ENDPOINT_MET` or `REGULATORY_PATHWAY` claim was `refuted` for this asset
   in the same window

If conditions 2 or 3 fail despite `return_pct > 0` → classified as `market_drift`.

**New SQLite table** `weekly_review_records`:
```
weekly_review_records
  review_id TEXT PRIMARY KEY
  week_ending TEXT NOT NULL UNIQUE
  report_json TEXT NOT NULL
  created_at TEXT NOT NULL
```

**Integration:** Wired into `IntelligenceService._maybe_run_weekly_pos_calibration()` block
(Sunday-only, same dedup pattern). Also callable via CLI: `bve review --week 2026-03-17`.

**Done criteria:**
- Four separate sections populated independently (each degrades gracefully when no data)
- `confirmed_thesis` requires thesis claim evidence, not just positive return
- `SizingQuality` correctly counts recommended vs executed divergence using DecisionLayer
- `weekly_review_records` table stores report for longitudinal analysis
- ~20 tests covering all four sections + edge cases (no data, all-correct, all-wrong)

---

## Architecture Invariants (Do Not Violate)

1. **Do not parallelize `for asset in self.config.watchlist`** until Postgres migration.
   SQLite handles ~150 assets / ~20k signals / ~200k documents sequentially without contention.
   Beyond that, writer lock contention becomes the primary bottleneck.

2. **Catalyst model never touches rNPV.** `CatalystValuation` is a scoring adjunct only.
   Three layers: ValuationEngine (intrinsic value) → CatalystModel (price reaction) →
   OpportunityScanner (ranking). No cross-layer mutation.

3. **`DEFAULT_EVENT_TYPE_SCORES` is the permanent fallback.** RankingCalibrator only
   writes overrides to `ranking_calibration.yaml` when N ≥ 20 per event type.
   The calibration file being missing or deleted must never cause a runtime error.

4. **All auto-generated configs include `_meta` block.** `config_version`, `generator_version`,
   `generated_at` are required for historical reproducibility. `_build_objects()` must
   silently ignore `_meta` (unknown top-level key).

5. **Backtest snapshots written by AlertRouter only.** Only fired alerts get snapshots.
   Low-ranked non-firing opportunities are never snapshotted. This keeps the backtest
   signal-to-noise ratio high.

6. **Acquisition screening is additive, not a rewrite of ranking.** Do not overload
   `mispricing`, `RankedOpportunity`, or the default catalyst-ranking path to mean
   acquisition discount. Use a dedicated screen, dedicated fields, and a dedicated CLI.

---

## Sprint 9 — Institutional Grade Model Fixes

**Status: IN PROGRESS (2026-03-25)**
**Branch:** core-engine-v1
**Plan file:** `PLAN_SPRINT9.md`
**Trigger:** Forensic audit (2026-03-25) rated system ⚠️ Pre-institutional.
**Target:** ✅ Institutional-grade BD/VC screening + ⚠️→✅ HF directional use.

All Sprint 9 tasks are specified in detail in `PLAN_SPRINT9.md`. This section
tracks completion status.

---

### Phase 1 — Core Model Math Corrections

> All Phase 1 tasks alter `rnpv_millions`. Implemented as one batch; regression
> baselines updated once after all Phase 1 tasks are complete.

#### Task 9.1 — UFCF / Tax Treatment ✅ COMPLETE
**Files:** `asset.py`, `rnpv_model.py`, `industry_assumptions.yaml`,
           `scenario.py`, `valuation_engine.py`
**Change:** Applied 21% effective tax rate to EBIT before discounting.
           Added `effective_tax_rate` and `nol_benefit_years` fields to Asset.
           Added `tax_rate_add` to ScenarioAssumptions.
           Added `effective_tax_rate` as 6th sensitivity parameter.
**Impact:** All rNPV values decreased ~40-45% (revenue × (1-tax) with fixed costs).

#### Task 9.2 — POS Layer 1 Adjuster Cap ✅ COMPLETE
**Files:** `pos_model.py`, `industry_assumptions.yaml`
**Change:** Added ±0.80 log-odds cap on Layer 1 combined adjustment.
           Extracted `_compute_layer1_adjustment()` helper.
**Impact:** Any asset with 4+ stacked positive adjusters will see lower POS.

#### Task 9.3 — BTD Log-odds Correction ✅ COMPLETE
**Files:** `pos_model.py`, `industry_assumptions.yaml`
**Change:** BTD log-odds reduced from +0.20 to +0.05.
           Comment explains BTD = process designation, not approval probability.
**Impact:** BTD-flagged assets see ~1-2pp lower POS.

#### Task 9.4 — WACC Modernization ✅ COMPLETE
**Files:** `industry_assumptions.yaml`, `asset.py`
**Change:** Default discount_rate: 0.10 → 0.12 (2026-Q1 recalibration).
           Added `vintage`, `erp_biotech` fields to wacc section.
           Updated commercial.defaults.discount_rate to match.
**Impact:** Assets using default WACC will see lower rNPV by ~8-12%.

---

### Phase 2 — Revenue / Cost Corrections (TODO)

Tasks 9.5–9.10: S-curve warning, compliance by modality, SG&A profiles,
accelerated approval, post-approval R&D, LOE 5-year extension.

### Phase 3 — Validation (TODO)

Tasks 9.11–9.15: G2N price basis, output precision, tornado expansion,
POS double-counting block, cost override enforcement.

### Phase 4 — Scoring Safety (TODO)

Tasks 9.16–9.17: Capital risk hard gate, score bounds clamping.

### Phase 5 — Calibration (TODO)

Tasks 9.18–9.20: POS backtest dataset remediation, MC distributions,
replay N≥30 graduation.

### Phase 6 — Provenance (TODO)

Tasks 9.21–9.22: Assumption hash, data lineage.
