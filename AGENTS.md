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

## Current State (as of 2026-03-08)

**Branch:** `core-engine-v1`
**Test suite:** 1 071 tests collected, all passing.
**Last commit:** `0652279` — pre-Wave-2 hardening (dedup, NYSE calendar, PoS logging, 429 backoff).

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
| Pre-Wave-2 hardening | DB dedup (INSERT OR IGNORE + UNIQUE on event_outcomes.event_id), NYSE holiday calendar, implied PoS guardrail logs |

### Key architecture notes
- `KnowledgeStore` (SQLite) holds: `raw_documents`, `structured_signals`, `valuation_proposals`, `market_prices`, `event_outcomes`, `market_expectations`.
- `WatchlistPipelineRunner.run_cycle()` wires: connectors → extraction → mapping → ranking → price refresh → resolve_pending → alert routing.
- LLM confidence gating: discard < 0.3, queue for review < 0.5, auto-process ≥ 0.5.
- `ImpliedPoSEstimator`: NAV back-solve `implied_pos = equity_value / peak_npv`; warns when equity < 0 or raw > 1.0.
- `trading_calendar.py`: NYSE 2010–2035 holiday calendar; functions `trading_days_after`, `count_trading_days_between`, `resolution_targets`.

## Next tasks (Wave 2)

Wave 2 is the **quantitative enrichment** layer — feeding live market and literature signals back into the valuation engine.

Suggested Wave 2 milestones (in dependency order):

1. **Wave 2A — Catalyst calendar integration**
   - Pull PDUFA dates, trial readout windows, and congress presentation slots from ClinicalTrials + FDA connectors.
   - Store as `CatalystEvent` rows in KnowledgeStore.
   - Surface upcoming catalysts in `RankedOpportunity` and alert payloads.

2. **Wave 2B — Dynamic PoS updating**
   - After each `EventOutcome` is resolved (T+30 or T+90), use abnormal return magnitude to Bayesian-update the stored `model_pos` for that asset.
   - Write updated PoS back to `valuation_proposals` / trigger a re-ranking pass.

3. **Wave 2C — Peer-set comps auto-population**
   - Given a drug's therapeutic area + modality, auto-fetch comparable approved drugs from FDA connector.
   - Use their market-cap / revenue multiples to calibrate `peak_sales_millions` priors.
   - Surface as `ComparableSetResult` attached to `RankedOpportunity`.

4. **Wave 2D — Portfolio-level risk aggregation**
   - Extend `portfolio.py` to aggregate MC distributions across watchlist assets.
   - Compute correlation-aware VaR and CVaR at the portfolio level.
   - Export as a portfolio risk dashboard (JSON + chart).

5. **Wave 2E — End-to-end smoke test**
   - Integration test: watchlist YAML → `run_cycle()` → DB assertions → ranked output, with all external calls mocked.

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
