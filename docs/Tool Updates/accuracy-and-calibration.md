# Accuracy And Calibration

Plain-language record of the valuation-accuracy work. Goal is honest calibration and uncertainty, not false precision.

## 2026-07-02 - POS Accuracy Program + Commercial Backtest

### What Changed

1. **Headline POS backtest now reports out-of-sample metrics.**
   The report prints in-sample and out-of-sample Brier, AUC, and ECE side by side using the existing time split: train rows before 2022, out-of-sample rows from 2022 onward.

2. **POS recalibration is measured out-of-sample only.**
   Added an isotonic recalibration path that fits on `<2022` rows and reports raw OOS vs calibrated OOS on `>=2022` rows. Existing valuation outputs still use raw POS unless explicitly changed later.

3. **Science double-count was verified already fixed.**
   The science modifier is T/D/B only: target validity, enough drug, translation bridge. H/M/S-style signals no longer add positive science multiplier credit when POS already owns them. The overlap guard remains in place.

4. **The phase-transition dataset was expanded and then split correctly.**
   The mixed dataset is now `research/data/phase_transitions.csv` with 155 rows including oncology plus immunology, CNS, and metabolic examples. The legacy `research/data/oncology_phase_transitions.csv` is oncology-only again so older oncology-specific loaders do not silently pool non-oncology rows.

5. **Prior-phase evidence is now fallback-only.**
   `prior_phase_data` no longer stacks on top of more granular evidence like clinical effect magnitude, biomarker selection, dose confidence, or placebo-response assessment. When detailed evidence is present, prior-phase data is ignored and flagged.

6. **Peak-sales backtest now exists.**
   Added `research/data/peak_sales_backtest.csv` and `bve.analysis.peak_sales_backtest`. It compares predicted peak sales vs realized sales for approved drugs. The seed dataset is intentionally tiny (`N=2`) and the report prints a low-N warning so it cannot be mistaken for a calibration basis.

### Why It Matters

- The model now separates **measurement** from **model changes**: first report OOS behavior, then recalibrate, then grow data.
- Non-oncology rows no longer make an oncology-named file or legacy oncology calibration path misleading.
- The POS model avoids one real evidence double-count: broad prior-phase evidence cannot boost POS again when more specific clinical evidence already explains the same signal.
- Revenue accuracy now has a measurement surface instead of being untested.

### How It Works

- `run_backtest_from_csv(...)` loads row-level therapeutic areas and labels the calibration suite `heuristic_mixed_ta` when a file contains more than one TA.
- `phase_transitions.csv` is the mixed headline dataset.
- `oncology_phase_transitions.csv` remains the oncology-only legacy dataset.
- Isotonic recalibration lives behind explicit analysis functions and reports calibrated POS alongside raw POS.
- `prior_phase_data` applies only when no granular evidence field supersedes it.
- Peak-sales backtest computes MAE, RMSE, MAPE, median APE, within-25%, within-50%, and within-2x.

### Proof It Works

Commits:

- `9f63ee1` - `feat(analysis): report OOS POS calibration metrics`
- `08d9b3c` - `feat(analysis): surface OOS POS recalibration metrics`
- `547a3a8` - `feat(analysis): expand POS backtest dataset`
- `8917446` - `feat(analysis): add peak-sales backtest`
- `298b86a` - `fix(analysis): separate mixed POS backtest dataset`
- `bddb182` - `fix(models): treat prior phase data as fallback evidence`

Verification:

- `python -m pytest tests/ -v` passed.
- `ruff check src/` passed.
- Focused checks passed for calibration decomposition, oncology dataset guard, prior-phase fallback, POS realism, and peak-sales backtest.

Current caution:

- The mixed POS dataset is still small (`N=155`), and non-oncology slices are very small. Use OOS calibration metrics directionally, not as proof of precision.
- Peak-sales backtest is only a scaffold until many more sourced commercial cases are added.
