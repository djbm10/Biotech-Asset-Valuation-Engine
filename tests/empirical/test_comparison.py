"""
Tests for bve.empirical.comparison — compare_all_modes, POSModeComparison,
ModeEvalResult.
"""
import pytest

from bve.empirical.comparison import (
    compare_all_modes,
    ModeEvalResult,
    POSModeComparison,
)
from bve.empirical.engine import EmpiricalPOSEngine
from bve.empirical.overlay_model import fit_overlay
from bve.empirical.base_rate_table import BaseRateTable
from bve.empirical.pos_outcome import POSOutcomeRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rec(
    phase="phase_2",
    success=True,
    moa="novel",
    bio=False,
    endpoint="surrogate_validated",
    safety="minor",
    competition="moderate",
    outcome_date=None,
    idx=0,
) -> POSOutcomeRecord:
    return POSOutcomeRecord(
        program_id=f"T-{idx}-{phase}-{moa}-{bio}",
        sponsor="AcmeBio",
        asset_name="DrugX",
        indication_raw="NSCLC",
        phase_at_entry=phase,
        moa_precedent=moa,
        biomarker_selected=bio,
        endpoint_type=endpoint,
        safety_profile=safety,
        competitive_pressure=competition,
        success=success,
        outcome_raw="advanced" if success else "failed",
        outcome_date=outcome_date,
    )


def _make_records(n: int = 40, with_dates: bool = False) -> list[POSOutcomeRecord]:
    recs = []
    phases = ["phase_1", "phase_2", "phase_3", "nda_bla"]
    for i in range(n):
        yr = str(2015 + (i % 10)) if with_dates else None
        recs.append(_rec(
            phase=phases[i % len(phases)],
            success=(i % 2 == 0),
            outcome_date=yr,
            idx=i,
        ))
    return recs


def _make_engine(records: list[POSOutcomeRecord] = None) -> EmpiricalPOSEngine:
    if records is None:
        records = _make_records(40)
    return EmpiricalPOSEngine(records, smoothing_alpha=1.0, min_n_for_stratified=3)


def _make_overlay(records: list[POSOutcomeRecord] = None):
    if records is None:
        records = _make_records(40)
    table = BaseRateTable(records, smoothing_alpha=1.0)
    return fit_overlay(records, table, alpha=1.0)


# ---------------------------------------------------------------------------
# compare_all_modes — basic contract
# ---------------------------------------------------------------------------

class TestCompareAllModes:
    def test_returns_pos_mode_comparison(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        assert isinstance(result, POSModeComparison)

    def test_without_overlay_returns_three_modes(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        assert len(result.modes) == 3

    def test_with_overlay_returns_four_modes(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        overlay = _make_overlay(recs)
        result = compare_all_modes(engine, recs, overlay_artifact=overlay)
        assert len(result.modes) == 4

    def test_mode_names_without_overlay(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        names = {m.mode for m in result.modes}
        assert "heuristic_only" in names
        assert "empirical_base_only" in names
        assert "empirical_heuristic" in names

    def test_mode_names_with_overlay(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        overlay = _make_overlay(recs)
        result = compare_all_modes(engine, recs, overlay_artifact=overlay)
        names = {m.mode for m in result.modes}
        assert "empirical_fitted" in names

    def test_n_test_equals_n_records_when_no_cutoff(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        assert result.n_test == 40

    def test_n_train_equals_n_records_when_no_cutoff(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        assert result.n_train == 40

    def test_empty_test_fold_returns_empty_comparison(self):
        """When cutoff_year is very high, all records are in train — no test."""
        recs = _make_records(40, with_dates=True)  # years 2015-2024
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs, cutoff_year=2030)
        assert result.n_test == 0
        assert result.modes == []
        assert result.best_mode_by_brier == "n/a"

    def test_temporal_split_separates_records(self):
        """Records after cutoff_year should be test; before = train."""
        recs = _make_records(40, with_dates=True)  # years 2015-2024
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs, cutoff_year=2019)
        # Should have some test records (years 2020-2024)
        assert result.n_test > 0
        assert result.n_train > 0
        assert result.n_train + result.n_test == 40

    def test_cutoff_year_stored(self):
        recs = _make_records(40, with_dates=True)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs, cutoff_year=2019)
        assert result.cutoff_year == 2019

    def test_no_cutoff_year_is_none(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        assert result.cutoff_year is None

    def test_empirical_success_rate_in_unit_interval(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        assert 0.0 <= result.empirical_success_rate <= 1.0

    def test_empirical_success_rate_correct(self):
        """Half successes → success rate ≈ 0.5."""
        recs = _make_records(40)  # alternating success
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        assert abs(result.empirical_success_rate - 0.5) < 0.01

    def test_best_mode_by_brier_is_valid_mode(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        valid_names = {m.mode for m in result.modes}
        assert result.best_mode_by_brier in valid_names


# ---------------------------------------------------------------------------
# ModeEvalResult contract
# ---------------------------------------------------------------------------

class TestModeEvalResult:
    def _get_mode(self, mode_name: str) -> ModeEvalResult:
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        m = result.get(mode_name)
        assert m is not None
        return m

    def test_brier_in_unit_interval(self):
        m = self._get_mode("heuristic_only")
        assert 0.0 <= m.brier <= 1.0

    def test_ece_in_unit_interval(self):
        m = self._get_mode("heuristic_only")
        assert 0.0 <= m.ece <= 1.0

    def test_n_samples_equals_n_records(self):
        m = self._get_mode("heuristic_only")
        assert m.n_samples == 40

    def test_mean_pred_in_unit_interval(self):
        m = self._get_mode("heuristic_only")
        assert 0.0 < m.mean_pred < 1.0

    def test_all_three_modes_have_metrics(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        for m in result.modes:
            assert 0.0 <= m.brier <= 1.0
            assert 0.0 <= m.ece <= 1.0

    def test_str_representation_contains_mode_name(self):
        m = self._get_mode("heuristic_only")
        s = str(m)
        assert "heuristic_only" in s
        assert "Brier=" in s

    def test_get_returns_none_for_missing_mode(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        assert result.get("nonexistent_mode") is None

    def test_get_returns_correct_mode(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        m = result.get("heuristic_only")
        assert m is not None
        assert m.mode == "heuristic_only"


# ---------------------------------------------------------------------------
# fitted_beats_heuristic / fitted_beats_empirical_heuristic
# ---------------------------------------------------------------------------

class TestFittedBeatsComparisons:
    def test_fitted_beats_heuristic_none_when_no_overlay(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        # No overlay → no fitted mode → returns None
        assert result.fitted_beats_heuristic() is None

    def test_fitted_beats_heuristic_returns_bool_when_overlay_present(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        overlay = _make_overlay(recs)
        result = compare_all_modes(engine, recs, overlay_artifact=overlay)
        fb = result.fitted_beats_heuristic()
        assert isinstance(fb, bool)

    def test_fitted_beats_empirical_heuristic_none_when_no_overlay(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        assert result.fitted_beats_empirical_heuristic() is None

    def test_fitted_beats_empirical_heuristic_returns_bool_when_overlay_present(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        overlay = _make_overlay(recs)
        result = compare_all_modes(engine, recs, overlay_artifact=overlay)
        fbe = result.fitted_beats_empirical_heuristic()
        assert isinstance(fbe, bool)

    def test_fitted_beats_heuristic_is_consistent_with_brier_values(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        overlay = _make_overlay(recs)
        result = compare_all_modes(engine, recs, overlay_artifact=overlay)
        fitted = result.get("empirical_fitted")
        heuristic = result.get("heuristic_only")
        expected = fitted.brier < heuristic.brier
        assert result.fitted_beats_heuristic() == expected

    def test_fitted_beats_empirical_heuristic_is_consistent_with_brier(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        overlay = _make_overlay(recs)
        result = compare_all_modes(engine, recs, overlay_artifact=overlay)
        fitted = result.get("empirical_fitted")
        emp_h = result.get("empirical_heuristic")
        expected = fitted.brier < emp_h.brier
        assert result.fitted_beats_empirical_heuristic() == expected


# ---------------------------------------------------------------------------
# POSModeComparison.summary
# ---------------------------------------------------------------------------

class TestPOSModeComparisonSummary:
    def test_summary_returns_string(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        assert isinstance(result.summary(), str)

    def test_summary_is_multiline(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        assert "\n" in result.summary()

    def test_summary_contains_mode_names(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        s = result.summary()
        assert "heuristic_only" in s
        assert "empirical_base_only" in s
        assert "empirical_heuristic" in s

    def test_summary_contains_fitted_when_overlay_present(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        overlay = _make_overlay(recs)
        result = compare_all_modes(engine, recs, overlay_artifact=overlay)
        s = result.summary()
        assert "empirical_fitted" in s

    def test_summary_contains_train_and_test_counts(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        s = result.summary()
        assert "Train" in s
        assert "Test" in s

    def test_summary_contains_best_mode_by_brier(self):
        recs = _make_records(40)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs)
        s = result.summary()
        assert "Best by Brier" in s

    def test_empty_comparison_summary_does_not_raise(self):
        recs = _make_records(40, with_dates=True)
        engine = _make_engine(recs)
        result = compare_all_modes(engine, recs, cutoff_year=2030)
        # Should not raise even with empty modes
        s = result.summary()
        assert isinstance(s, str)
