# Repository Guidelines

## Project Structure & Module Organization
Core code lives in `src/bve/`.
- `valuation/` orchestrates end-to-end runs (`ValuationEngine`, scenarios, portfolio outputs).
- `models/` contains valuation math (rNPV, POS, Monte Carlo, competition, multi-indication).
- `entities/` and `config/` define domain objects and shared assumptions (`industry_assumptions.yaml`).
- `cli/` exposes entry points (`bve-asset`, `bve-batch`, `bve-portfolio`, `bve-extract`).
- `reporting/` generates memos, charts, and exported artifacts.
- `intelligence/` contains extraction, mapping, schemas, and taxonomy logic.

Tests are in `tests/` (plus `tests/intelligence/` for extraction/taxonomy workflows). Example configs are in `examples/configs/`. Case studies and research artifacts live in `case_studies/` and `research/`.

## Build, Test, and Development Commands
- `pip install -e ".[dev]"`: install package in editable mode with dev tooling.
- `python -m pytest tests/ -v`: run full test suite.
- `python -m pytest tests/test_models.py::TestRNPVModel::test_base_case -v`: run one targeted test.
- `ruff check src/`: lint source files.
- `mypy src/bve/`: static type check core package.
- `bve-asset --config examples/configs/relay_rly2608.yaml --memo bd --charts`: run canonical single-asset valuation.

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
