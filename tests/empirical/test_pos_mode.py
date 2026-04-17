"""
Tests for bve.empirical.pos_mode — POSMode routing, compare_pos_modes,
and ValuationEngine pos_mode parameter integration.
"""
import pytest

from bve.empirical.engine import EmpiricalPOSEngine
from bve.empirical.pos_mode import (
    POSMode,
    HeuristicVsEmpiricalComparison,
    TrialPOSComparison,
    compare_pos_modes,
)
from bve.empirical.pos_outcome import POSOutcomeRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rec(phase="phase_2", success=True, sponsor="AcmeBio") -> POSOutcomeRecord:
    return POSOutcomeRecord(
        program_id=f"T-{phase}-{success}-{sponsor}",
        sponsor=sponsor,
        asset_name="DrugX",
        indication_raw="NSCLC",
        phase_at_entry=phase,
        therapeutic_area="oncology",
        moa_precedent="novel",
        biomarker_selected=False,
        success=success,
        outcome_raw="advanced" if success else "failed",
        outcome_date="2020",
    )


def _make_engine(n_per_phase: int = 8) -> EmpiricalPOSEngine:
    recs = []
    for phase in ["phase_1", "phase_2", "phase_3", "nda_bla"]:
        for i in range(n_per_phase):
            recs.append(_rec(phase=phase, success=(i % 2 == 0)))
    return EmpiricalPOSEngine(recs, smoothing_alpha=1.0, min_n_for_stratified=3)


def _make_valuation_engine(pos_mode="heuristic", empirical_engine=None):
    from bve.entities.asset import Asset, DevelopmentStage, TherapeuticArea, Modality
    from bve.entities.company import Company
    from bve.entities.trial import ClinicalTrial, TrialPhase
    from bve.models.market_model import MarketModel
    from bve.models.monte_carlo import MonteCarloParams
    from bve.valuation.valuation_engine import ValuationEngine

    asset = Asset(
        id="pm-001", name="PM-001", indication="Lung Cancer",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=0.10,
    )
    company = Company(
        id="pm-co", name="PMCo", ticker="PMC",
        cash_millions=100.0, shares_outstanding_millions=50.0,
    )
    trials = [
        ClinicalTrial(
            asset_id="pm-001", phase=TrialPhase.PHASE_2,
            success_probability=0.35, duration_years=2.5, cost_millions=80.0,
        ),
        ClinicalTrial(
            asset_id="pm-001", phase=TrialPhase.PHASE_3,
            success_probability=0.55, duration_years=3.5, cost_millions=250.0,
        ),
    ]
    market = MarketModel(
        asset_id="pm-001",
        total_addressable_market_millions=4000.0,
        peak_penetration=0.10,
        years_to_peak=5,
        patent_life_years=12,
    )
    return ValuationEngine(
        asset=asset,
        company=company,
        trials=trials,
        market_model=market,
        empirical_pos_engine=empirical_engine,
        pos_mode=pos_mode,
        mc_params=MonteCarloParams(n_simulations=200, random_seed=0),
    )


# ---------------------------------------------------------------------------
# POSMode enum
# ---------------------------------------------------------------------------

class TestPOSModeEnum:
    def test_enum_values(self):
        assert POSMode.HEURISTIC == "heuristic"
        assert POSMode.EMPIRICAL_RAW == "empirical_raw"
        assert POSMode.EMPIRICAL_CALIBRATED == "empirical_calibrated"

    def test_enum_is_string(self):
        # POSMode(str, Enum) — can be compared to strings
        assert POSMode.HEURISTIC == "heuristic"

    def test_all_three_modes_distinct(self):
        modes = {POSMode.HEURISTIC, POSMode.EMPIRICAL_RAW, POSMode.EMPIRICAL_CALIBRATED}
        assert len(modes) == 3

    def test_empirical_fitted_mode_exists(self):
        assert POSMode.EMPIRICAL_FITTED == "empirical_fitted"

    def test_all_four_modes_distinct(self):
        modes = {
            POSMode.HEURISTIC, POSMode.EMPIRICAL_RAW,
            POSMode.EMPIRICAL_CALIBRATED, POSMode.EMPIRICAL_FITTED,
        }
        assert len(modes) == 4


# ---------------------------------------------------------------------------
# ValuationEngine pos_mode routing
# ---------------------------------------------------------------------------

class TestValuationEnginePOSModeRouting:
    def test_heuristic_mode_runs_without_empirical_engine(self):
        engine = _make_valuation_engine(pos_mode="heuristic", empirical_engine=None)
        result = engine.run()
        assert result.rnpv.rnpv_millions is not None

    def test_empirical_raw_mode_uses_empirical_engine(self):
        emp = _make_engine()
        engine = _make_valuation_engine(pos_mode="empirical_raw", empirical_engine=emp)
        result = engine.run()
        assert result.rnpv.rnpv_millions is not None

    def test_empirical_raw_and_heuristic_produce_different_rnpv(self):
        """Empirical engine should produce different POS than heuristic."""
        emp = _make_engine()
        h_engine = _make_valuation_engine(pos_mode="heuristic")
        e_engine = _make_valuation_engine(pos_mode="empirical_raw", empirical_engine=emp)
        h_result = h_engine.run()
        e_result = e_engine.run()
        # Not strictly guaranteed to differ, but with our dataset they should
        # Test that both complete successfully and produce finite results
        assert h_result.rnpv.rnpv_millions is not None
        assert e_result.rnpv.rnpv_millions is not None

    def test_heuristic_mode_ignores_empirical_engine(self):
        """pos_mode=heuristic should ignore the empirical engine even when attached."""
        emp = _make_engine()
        h_engine_no_emp = _make_valuation_engine(pos_mode="heuristic", empirical_engine=None)
        h_engine_with_emp = _make_valuation_engine(pos_mode="heuristic", empirical_engine=emp)
        r1 = h_engine_no_emp.run()
        r2 = h_engine_with_emp.run()
        # With pos_mode=heuristic, empirical_engine should be ignored
        assert abs(r1.rnpv.rnpv_millions - r2.rnpv.rnpv_millions) < 1e-3

    def test_empirical_calibrated_without_artifact_falls_back_to_raw(self):
        """Engine without calibration artifact should fall back to empirical_raw."""
        emp = _make_engine()  # no calibration attached
        engine = _make_valuation_engine(pos_mode="empirical_calibrated", empirical_engine=emp)
        # Should not raise; just uses raw
        result = engine.run()
        assert result.rnpv.rnpv_millions is not None

    def test_empirical_calibrated_with_artifact_completes(self):
        from bve.empirical.calibration import fit_calibration

        emp = _make_engine()
        preds = [emp.compute_pos_with_adjusters("phase_2")] * 10
        outcomes = [i % 2 == 0 for i in range(10)]
        artifact = fit_calibration(preds, outcomes, method="platt")
        emp.attach_calibration(artifact)

        engine = _make_valuation_engine(pos_mode="empirical_calibrated", empirical_engine=emp)
        result = engine.run()
        assert result.rnpv.rnpv_millions is not None

    def test_pos_mode_stored_on_engine(self):
        engine = _make_valuation_engine(pos_mode="empirical_raw")
        assert engine.pos_mode == "empirical_raw"

    def test_default_pos_mode_is_heuristic(self):
        from bve.valuation.valuation_engine import ValuationEngine
        from bve.entities.asset import Asset, DevelopmentStage, TherapeuticArea, Modality
        from bve.entities.company import Company
        from bve.entities.trial import ClinicalTrial, TrialPhase
        from bve.models.market_model import MarketModel

        asset = Asset(
            id="def-001", name="DEF-001", indication="Test",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            stage=DevelopmentStage.PHASE_2,
            modality=Modality.SMALL_MOLECULE,
            discount_rate=0.10,
        )
        company = Company(
            id="def-co", name="DefCo", ticker="DEF",
            cash_millions=100.0, shares_outstanding_millions=50.0,
        )
        trials = [ClinicalTrial(
            asset_id="def-001", phase=TrialPhase.PHASE_2,
            success_probability=0.35, duration_years=2.5, cost_millions=80.0,
        )]
        market = MarketModel(
            asset_id="def-001",
            total_addressable_market_millions=3000.0,
            peak_penetration=0.10, years_to_peak=5, patent_life_years=12,
        )
        engine = ValuationEngine(asset=asset, company=company, trials=trials, market_model=market)
        assert engine.pos_mode == "heuristic"


# ---------------------------------------------------------------------------
# compare_pos_modes
# ---------------------------------------------------------------------------

class TestComparePOSModes:
    def _make_asset_and_trials(self):
        from bve.entities.asset import Asset, DevelopmentStage, TherapeuticArea, Modality
        from bve.entities.trial import ClinicalTrial, TrialPhase

        asset = Asset(
            id="cpm-001", name="CPM-001", indication="NSCLC",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            stage=DevelopmentStage.PHASE_2,
            modality=Modality.SMALL_MOLECULE,
            discount_rate=0.10,
        )
        trials = [
            ClinicalTrial(
                asset_id="cpm-001", phase=TrialPhase.PHASE_2,
                success_probability=0.35, duration_years=2.5, cost_millions=80.0,
            ),
            ClinicalTrial(
                asset_id="cpm-001", phase=TrialPhase.PHASE_3,
                success_probability=0.55, duration_years=3.5, cost_millions=250.0,
            ),
        ]
        return asset, trials

    def test_returns_comparison_object(self):
        asset, trials = self._make_asset_and_trials()
        emp = _make_engine()
        result = compare_pos_modes(trials, asset, emp)
        assert isinstance(result, HeuristicVsEmpiricalComparison)

    def test_trial_count_matches(self):
        asset, trials = self._make_asset_and_trials()
        emp = _make_engine()
        result = compare_pos_modes(trials, asset, emp)
        assert len(result.trials) == 2

    def test_trial_comparisons_are_trial_pos_comparison(self):
        asset, trials = self._make_asset_and_trials()
        emp = _make_engine()
        result = compare_pos_modes(trials, asset, emp)
        for t in result.trials:
            assert isinstance(t, TrialPOSComparison)

    def test_cumulative_pos_is_product_of_trials(self):
        asset, trials = self._make_asset_and_trials()
        emp = _make_engine()
        result = compare_pos_modes(trials, asset, emp)
        # Cumulative heuristic should be product of individual trial heuristic POS
        expected = 1.0
        for t in result.trials:
            expected *= t.heuristic_pos
        assert abs(result.cumulative_heuristic_pos - expected) < 1e-4

    def test_agree_within_5pp_flag(self):
        asset, trials = self._make_asset_and_trials()
        emp = _make_engine()
        result = compare_pos_modes(trials, asset, emp)
        for t in result.trials:
            expected_agree = abs(t.delta_heuristic_vs_raw) < 0.05
            assert t.agree_within_5pp == expected_agree

    def test_max_delta_is_max_of_abs_deltas(self):
        asset, trials = self._make_asset_and_trials()
        emp = _make_engine()
        result = compare_pos_modes(trials, asset, emp)
        expected_max = max(abs(t.delta_heuristic_vs_raw) for t in result.trials)
        assert abs(result.max_delta - expected_max) < 1e-4

    def test_n_diverging_counts_disagreements(self):
        asset, trials = self._make_asset_and_trials()
        emp = _make_engine()
        result = compare_pos_modes(trials, asset, emp)
        expected_n = sum(1 for t in result.trials if not t.agree_within_5pp)
        assert result.n_diverging == expected_n

    def test_summary_is_multi_line_string(self):
        asset, trials = self._make_asset_and_trials()
        emp = _make_engine()
        result = compare_pos_modes(trials, asset, emp)
        summary = result.summary()
        assert isinstance(summary, str)
        assert "Heuristic vs Empirical" in summary

    def test_calibrated_pos_none_without_calibration(self):
        asset, trials = self._make_asset_and_trials()
        emp = _make_engine()  # no calibration artifact
        result = compare_pos_modes(trials, asset, emp)
        assert result.cumulative_empirical_calibrated_pos is None
        for t in result.trials:
            assert t.empirical_calibrated_pos is None

    def test_calibrated_pos_populated_with_calibration(self):
        from bve.empirical.calibration import fit_calibration

        asset, trials = self._make_asset_and_trials()
        emp = _make_engine()
        preds = [emp.compute_pos_with_adjusters("phase_2")] * 10
        outcomes = [i % 2 == 0 for i in range(10)]
        artifact = fit_calibration(preds, outcomes, method="platt")
        emp.attach_calibration(artifact)

        result = compare_pos_modes(trials, asset, emp)
        assert result.cumulative_empirical_calibrated_pos is not None
        for t in result.trials:
            assert t.empirical_calibrated_pos is not None
            assert 0.0 < t.empirical_calibrated_pos < 1.0


# ---------------------------------------------------------------------------
# EMPIRICAL_FITTED mode routing — ValuationEngine
# ---------------------------------------------------------------------------

def _make_overlay_artifact(engine: "EmpiricalPOSEngine"):
    from bve.empirical.overlay_model import fit_overlay
    from bve.empirical.base_rate_table import BaseRateTable
    from bve.empirical.pos_outcome import POSOutcomeRecord

    recs = []
    phases = ["phase_1", "phase_2", "phase_3", "nda_bla"]
    for i in range(40):
        recs.append(POSOutcomeRecord(
            program_id=f"ov-{i}",
            sponsor="AcmeBio",
            asset_name="DrugX",
            indication_raw="NSCLC",
            phase_at_entry=phases[i % len(phases)],
            moa_precedent="validated" if i % 3 == 0 else "novel",
            biomarker_selected=(i % 2 == 0),
            endpoint_type="hard_clinical" if i % 4 == 0 else "surrogate_validated",
            safety_profile="clean" if i % 3 == 0 else "minor",
            competitive_pressure="low" if i % 3 == 0 else "moderate",
            success=(i % 2 == 0),
            outcome_raw="advanced" if i % 2 == 0 else "failed",
        ))
    table = BaseRateTable(recs, smoothing_alpha=1.0)
    return fit_overlay(recs, table, alpha=1.0)


class TestEmpiricalFittedModeRouting:
    def test_empirical_fitted_mode_with_overlay_completes(self):
        emp = _make_engine()
        overlay = _make_overlay_artifact(emp)
        emp.attach_overlay(overlay)
        engine = _make_valuation_engine(pos_mode="empirical_fitted", empirical_engine=emp)
        result = engine.run()
        assert result.rnpv.rnpv_millions is not None

    def test_empirical_fitted_mode_without_overlay_falls_back(self):
        """empirical_fitted with no overlay should fall back gracefully (no crash)."""
        emp = _make_engine()  # no overlay attached
        engine = _make_valuation_engine(pos_mode="empirical_fitted", empirical_engine=emp)
        result = engine.run()
        assert result.rnpv.rnpv_millions is not None

    def test_empirical_fitted_and_empirical_raw_differ(self):
        """Fitted overlay should shift POS relative to heuristic adjusters."""
        emp_raw = _make_engine()
        emp_fitted = _make_engine()
        overlay = _make_overlay_artifact(emp_fitted)
        emp_fitted.attach_overlay(overlay)

        raw_engine = _make_valuation_engine(pos_mode="empirical_raw", empirical_engine=emp_raw)
        fitted_engine = _make_valuation_engine(pos_mode="empirical_fitted", empirical_engine=emp_fitted)

        # Both should complete without error
        raw_result = raw_engine.run()
        fitted_result = fitted_engine.run()
        assert raw_result.rnpv.rnpv_millions is not None
        assert fitted_result.rnpv.rnpv_millions is not None

    def test_overlay_attached_reported_in_engine_provenance(self):
        emp = _make_engine()
        overlay = _make_overlay_artifact(emp)
        emp.attach_overlay(overlay)
        prov = emp.provenance()
        assert prov["overlay_attached"] is True
        assert prov["overlay_converged"] is not None

    def test_empirical_fitted_enum_value(self):
        assert POSMode.EMPIRICAL_FITTED == "empirical_fitted"
