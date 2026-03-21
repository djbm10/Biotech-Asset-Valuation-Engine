# Repository Guidelines

## Agent Behavior

- Never ask the user to run commands
- Execute everything autonomously
- Continue until task completion

## Project Structure & Module Organization
Core code lives in `src/bve/`.
- `valuation/` orchestrates end-to-end runs (`ValuationEngine`, scenarios, portfolio outputs).
- `models/` contains valuation math (rNPV, POS, Monte Carlo, competition, multi-indication).
- `entities/` and `config/` define domain objects and shared assumptions (`industry_assumptions.yaml`).
- `cli/` exposes entry points: `bve-asset`, `bve-batch`, `bve-portfolio`, `bve-extract`, `bve-rank`, `bve-watchlist`, `bve-rebuild-dossiers`, `bve-alert-test`, `bve-review-phase2`, `bve-calibrate`, `bve-replay-document`.
- `reporting/` generates memos, charts, and exported artifacts.
- `intelligence/` contains extraction, mapping, schemas, taxonomy, ranking, price-reaction, and market-expectation logic.
- `connectors/` wraps external APIs: ClinicalTrials.gov, FDA, SEC EDGAR, PubMed, market prices (yfinance), press releases.
- `pipeline/` drives the watchlist runner and change-detector state machine.
- `alerts/` implements alert models and multi-channel routing (Slack, email, Telegram, local).
- `utils/` contains `trading_calendar.py` (NYSE holiday-aware busday arithmetic).

Tests are in `tests/` (plus `tests/intelligence/`, `tests/alerts/`, `tests/pipeline/`). Example configs are in `examples/configs/`. Case studies and research artifacts live in `case_studies/` and `research/`.

## Current State (as of 2026-03-18)

**Branch:** `core-engine-v1`
**Test suite:** 84 Sprint 5 tests passing (all waves J/K/M/L); full suite passing.
**Last sprint:** Sprint 5 — Decision Loop + Weekly Review

### Completed layers

| Layer | Description |
|---|---|
| Core valuation engine (Steps 1–7) | rNPV, POS, revenue/cost/probability models, LOE erosion, DrugAssetProgram, DealEconomics, scenarios, Monte Carlo, sensitivities, regression fixtures |
| Competition model | CrowdingModel, FirstMoverConfig, ClassSaturationProfile; MC sampling |
| Multi-indication | Cascade PoS, FranchiseCostSharing, IndicationResult |
| Intelligence pipeline — Phase 1 | Document ingestion, LLM extraction, confidence gating, review queue, mapping engine, Phase 2 policy |
| Alerting layer | AlertModel, multi-channel router, WatchlistPipelineRunner |
| Ranking engine | RankedOpportunity with score, PoS gap, opportunity tier |
| Wave 1A | Market price snapshotting (MarketPriceRecord, MarketPriceConnector, KnowledgeStore `market_prices` table, volume spike detection) |
| Wave 1B | Event outcome tracking (EventOutcome, PriceReactionTracker, trading_calendar NYSE calendar) |
| Wave 1C | PubMed connector (esearch + efetch, topic filter, rate limiting, 429 backoff) |
| Wave 1D | Market expectation modeling (ImpliedPoSEstimator, MarketExpectation, `market_expectations` table, PoS gap in ranking) |
| Wave F | Conference event detection (ConferenceEventDetector, ConferenceCalendar, 12-conference registry, presentation type classification) |
| Wave G | Earnings transcript ingestion (EarningsTranscriptParser, section detection, guidance direction, tonal signals) |
| Wave I | ThesisTracker (claim lifecycle: open→confirmed/refuted/expired/superseded, `thesis_strength`, `snapshot()`) |
| **Wave J** | **Decision + Position Layer** (`DecisionLayer`, 3 SQLite tables: `decision_records`, `position_snapshots`, `outcome_attributions`; recommended vs executed; portfolio context snapshot; `model_vs_execution_drift()`) |
| **Wave K** | **Weekly Actionable Output** (`ActionableGenerator`, `WeeklyActionableReport`, score versioning via `SCORE_VERSIONS`, CAUTION→downgrade, `has_actionable` always populated) |
| **Wave M** | **Weighted Thesis Strength** (`DEFAULT_CLAIM_WEIGHTS` by ClaimType; `weighted_thesis_strength` field on `ThesisSnapshot`; backward-compatible schema migration) |
| **Wave L** | **Weekly Review Engine** (`WeeklyReviewEngine`, four-section report: fundamental/market_timing/thesis/sizing; strict `confirmed_thesis` rule requiring key claim evidence; stored to `weekly_review_records`) |

### Key architecture notes — Sprint 5 additions

**Decision loop** (`intelligence/decision_layer.py`):
- `DecisionRecord`: recommended_action/size_pct (system), executed_action/size_pct (analyst), full portfolio context snapshot at decision time.
- `PositionSnapshot`: entry/exit dates, `holding_period_days` computed only at close, `is_active` boolean.
- `OutcomeAttribution`: links `decision_id → attribution_type` (pos_error, timing_error, sizing_error, thesis_error, market_drift, confirmed_thesis, unclassified).
- `model_vs_execution_drift()`: returns n_total, n_with_execution, n_diverged, pct_diverged.

**Actionable output** (`intelligence/actionable_output.py`):
- `ActionableGenerator(score_version, min_composite_score, max_position_pct)`.
- Composite score = 0.50×ranking + 0.30×thesis + 0.20×opportunity.
- Action thresholds: ≥0.70→buy, ≥0.50→add, ≥0.30→monitor, <0.30→avoid.
- CAUTION critic → downgrade to monitor + zero size (never filtered out).
- `SCORE_VERSIONS` dict enables future scoring regime comparisons.
- `WeeklyActionableReport.has_actionable` is always set (never silent).

**Weighted thesis** (`intelligence/thesis_tracker.py`):
- `DEFAULT_CLAIM_WEIGHTS`: ENDPOINT_MET=2.0, REGULATORY_PATHWAY=1.5, COMPETITOR_FAILURE=1.5, LABEL_EXPANSION=1.25, POS_ABOVE_THRESHOLD=1.0, ENROLLMENT_ON_TRACK=0.75, MARKET_REACTION_POSITIVE=0.5, CUSTOM=1.0.
- `ThesisSnapshot.weighted_thesis_strength`: impact-weighted ratio of confirmed claims; None when no resolved claims.
- Schema: `ALTER TABLE ADD COLUMN weight REAL DEFAULT 1.0` (idempotent, try/except).

**Weekly review** (`intelligence/weekly_review.py`):
- `_KEY_CLAIM_TYPES`: {endpoint_met, regulatory_pathway, competitor_failure}.
- Strict `confirmed_thesis`: positive outcome AND ≥1 confirmed key claim AND 0 refuted key claims. Requires `thesis_tracker`; returns False conservatively when unavailable.
- Each section degrades gracefully: SizingQuality→empty when no DecisionLayer, ThesisAccuracy→empty when no ThesisTracker.
- Reports stored via `INSERT OR REPLACE` (upsert by week_ending).

**KnowledgeStore additions**: `weekly_review_records` table (review_id, week_ending UNIQUE, report_json, created_at).

## Build, Test, and Development Commands
- `pip install -e ".[dev]"`: install package in editable mode with dev tooling.
- `python -m pytest tests/ -v`: run full test suite (1 071 tests).
- `python -m pytest tests/test_models.py::TestRNPVModel::test_base_case -v`: run one targeted test.
- `ruff check src/`: lint source files.
- `mypy src/bve/`: static type check core package.
- `bve-asset --config examples/configs/relay_rly2608.yaml --memo bd --charts`: run canonical single-asset valuation.
- `bve-watchlist --config examples/configs/watchlist.yaml`: run pipeline cycle.
- `bve-rank --config examples/configs/watchlist.yaml`: display ranked opportunity table with PoS gap.

## Coding Style & Naming Conventions
Use Python 3.11+, 4-space indentation, and keep lines within 100 chars (Ruff config). Prefer explicit type hints and Pydantic v2 models for structured data. Use `snake_case` for modules/functions/variables and `PascalCase` for classes. Keep assumptions centralized in `src/bve/config/industry_assumptions.yaml` instead of hard-coding constants in model logic.

## Testing Guidelines
Use `pytest` for all tests; name files `test_*.py` and test functions `test_*`. Add tests in the closest feature area (e.g., `tests/test_competition_crowding.py`, `tests/intelligence/extraction/`). Reuse fixtures under `tests/intelligence/extraction/fixtures/` for extractor behavior. For stochastic paths, use fixed seeds to keep results reproducible.

## Commit & Pull Request Guidelines
Recent history follows Conventional Commit style: `feat:`, `feat(scope):`, `fix(scope):`, `refactor:`, `chore:`. Write short, imperative subjects (example: `feat(models): add class saturation profile`). For PRs, include:
- what changed and why,
- impacted modules/configs,
- commands run (`pytest`, `ruff`, `mypy`),
- sample output paths when behavior changes (for example `outputs/RLAY/valuation.json`).
