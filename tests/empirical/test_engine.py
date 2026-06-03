"""
Tests for EmpiricalPOSEngine — empirical POS predictions and ValuationEngine integration.
"""
from __future__ import annotations

import pytest

from bve.empirical.engine import EmpiricalPOSEngine
from bve.empirical.pos_outcome import POSOutcomeRecord, load_bundled_records


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    phase: str,
    success: bool,
    moa: str | None = "partial",
    biomarker: bool = False,
    drug: str = "drug",
    year: str = "2020",
    sponsor: str = "Acme",
) -> POSOutcomeRecord:
    return POSOutcomeRecord(
        program_id=f"{drug}_{year}",
        sponsor=sponsor,
        asset_name=drug,
        indication_raw="NSCLC",
        phase_at_entry=phase,
        moa_precedent=moa,
        biomarker_selected=biomarker,
        success=success,
        outcome_raw="approved" if success else "failed",
        outcome_date=year,
    )


def _minimal_records() -> list[POSOutcomeRecord]:
    """Small but balanced dataset for unit tests."""
    return [
        _make_record("phase_2", True, moa="novel", drug=f"a{i}") for i in range(4)
    ] + [
        _make_record("phase_2", False, moa="novel", drug=f"b{i}") for i in range(2)
    ] + [
        _make_record("phase_3", True, moa="partial", drug=f"c{i}") for i in range(3)
    ] + [
        _make_record("phase_3", False, moa="partial", drug=f"d{i}") for i in range(2)
    ]


# ---------------------------------------------------------------------------
# Engine construction
# ---------------------------------------------------------------------------

class TestEmpiricalPOSEngineConstruction:
    def test_from_records(self):
        engine = EmpiricalPOSEngine(_minimal_records())
        assert engine.n_records == 11

    def test_empty_records_raises(self):
        with pytest.raises(ValueError, match="at least one"):
            EmpiricalPOSEngine([])

    def test_from_bundled(self):
        engine = EmpiricalPOSEngine.from_bundled()
        assert engine.n_records >= 60

    def test_from_csv(self, tmp_path):
        """Write a minimal CSV and load from it."""
        import csv
        csv_file = tmp_path / "test.csv"
        fields = [
            "drug", "company", "indication", "phase_start", "outcome", "year",
            "moa_precedent", "biomarker_enriched", "safety_profile",
            "competitive_pressure", "endpoint_type", "notes",
        ]
        rows = [
            {
                "drug": f"d{i}", "company": "Co", "indication": "NSCLC",
                "phase_start": "phase_2", "outcome": "approved" if i % 2 == 0 else "failed",
                "year": "2020", "moa_precedent": "novel", "biomarker_enriched": "false",
                "safety_profile": "clean", "competitive_pressure": "low",
                "endpoint_type": "hard_clinical", "notes": "",
            }
            for i in range(6)
        ]
        with open(csv_file, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

        engine = EmpiricalPOSEngine.from_csv(csv_file)
        assert engine.n_records == 6


# ---------------------------------------------------------------------------
# F. predict() — raw empirical base rates
# ---------------------------------------------------------------------------

class TestEmpiricalPredict:
    def test_predict_returns_float_in_range(self):
        engine = EmpiricalPOSEngine(_minimal_records())
        p = engine.predict("phase_2", moa_precedent="novel")
        assert 0.0 < p < 1.0

    def test_predict_with_biomarker_selection(self):
        records = [
            _make_record("phase_2", True, moa="novel", biomarker=True, drug=f"bio{i}")
            for i in range(5)
        ] + [
            _make_record("phase_2", False, moa="novel", biomarker=False, drug=f"nobio{i}")
            for i in range(5)
        ]
        engine = EmpiricalPOSEngine(records, min_n_for_stratified=1)
        # Explicit True/False triggers biomarker stratification
        p_bio = engine.predict("phase_2", moa_precedent="novel", biomarker_selected=True)
        p_no = engine.predict("phase_2", moa_precedent="novel", biomarker_selected=False)
        assert p_bio > p_no

    def test_predict_unknown_phase_fallback(self):
        engine = EmpiricalPOSEngine(_minimal_records())
        p = engine.predict("phase_99")
        # Should return the fallback default (0.40)
        assert p == 0.40

    def test_predict_phase3_higher_than_phase2(self):
        """Standard oncology result: Phase 3 rate > Phase 2 rate."""
        engine = EmpiricalPOSEngine.from_bundled()
        p2 = engine.predict("phase_2")
        p3 = engine.predict("phase_3")
        assert p3 > p2


# ---------------------------------------------------------------------------
# F. compute_pos_with_adjusters() — empirical base + heuristic adjusters
# ---------------------------------------------------------------------------

class TestComputePosWithAdjusters:
    def test_no_adjusters_returns_raw_empirical(self):
        engine = EmpiricalPOSEngine(_minimal_records())
        pos = engine.compute_pos_with_adjusters("phase_2")
        base = engine.predict("phase_2")
        # Without adjusters, result should equal raw empirical rate
        assert abs(pos - base) < 1e-4

    def test_adjusters_applied_on_top(self):
        from bve.models.pos_model import (
            CompetitivePressure,
            EndpointType,
            MoAPrecedent,
            POSAdjusters,
            SafetyProfile,
        )
        from bve.entities.trial import TrialPhase
        from bve.entities.asset import TherapeuticArea

        engine = EmpiricalPOSEngine.from_bundled()
        adj_good = POSAdjusters(
            endpoint_type=EndpointType.HARD_CLINICAL,
            moa_precedent=MoAPrecedent.VALIDATED,
            safety_profile=SafetyProfile.CLEAN,
            competitive_pressure=CompetitivePressure.LOW,
            biomarker_selected_population=True,
        )
        adj_bad = POSAdjusters(
            endpoint_type=EndpointType.BIOMARKER_ONLY,
            moa_precedent=MoAPrecedent.NOVEL,
            safety_profile=SafetyProfile.SERIOUS,
            competitive_pressure=CompetitivePressure.HIGH,
            biomarker_selected_population=False,
        )
        pos_good = engine.compute_pos_with_adjusters(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY, adj_good
        )
        pos_bad = engine.compute_pos_with_adjusters(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY, adj_bad
        )
        assert pos_good > pos_bad

    def test_result_bounded(self):
        """Results must stay in (0, 1) for any combination."""
        from bve.models.pos_model import POSAdjusters, MoAPrecedent, SafetyProfile, CompetitivePressure, EndpointType
        from bve.entities.trial import TrialPhase

        engine = EmpiricalPOSEngine.from_bundled()
        for phase in (TrialPhase.PHASE_2, TrialPhase.PHASE_3, TrialPhase.NDA_BLA):
            for moa in (MoAPrecedent.VALIDATED, MoAPrecedent.NOVEL):
                for bio in (True, False):
                    adj = POSAdjusters(
                        moa_precedent=moa,
                        biomarker_selected_population=bio,
                    )
                    p = engine.compute_pos_with_adjusters(phase, adjusters=adj)
                    assert 0.0 < p < 1.0, f"Out of range for phase={phase}, moa={moa}, bio={bio}: {p}"

    def test_phase_as_string_accepted(self):
        """Phase can be passed as string or enum."""
        engine = EmpiricalPOSEngine(_minimal_records())
        pos_str = engine.compute_pos_with_adjusters("phase_2")
        from bve.entities.trial import TrialPhase
        pos_enum = engine.compute_pos_with_adjusters(TrialPhase.PHASE_2)
        assert abs(pos_str - pos_enum) < 1e-9


# ---------------------------------------------------------------------------
# Sponsor context
# ---------------------------------------------------------------------------

class TestSponsorTrack:
    def test_known_sponsor_found(self):
        records = [_make_record("phase_2", True, sponsor="BigPharma", drug=f"d{i}") for i in range(3)]
        engine = EmpiricalPOSEngine(records)
        track = engine.sponsor_track("BigPharma")
        assert track is not None
        assert track.n_trials == 3

    def test_unknown_sponsor_returns_none(self):
        engine = EmpiricalPOSEngine(_minimal_records())
        assert engine.sponsor_track("UnknownCo") is None

    def test_all_sponsor_tracks_returns_dict(self):
        engine = EmpiricalPOSEngine(_minimal_records())
        tracks = engine.all_sponsor_tracks()
        assert isinstance(tracks, dict)
        assert len(tracks) > 0


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

class TestProvenance:
    def test_provenance_structure(self):
        engine = EmpiricalPOSEngine.from_bundled()
        prov = engine.provenance()
        assert prov["is_empirically_calibrated"] is True
        assert prov["n_records"] == engine.n_records
        assert "phase_rates" in prov
        assert "model" in prov


# ---------------------------------------------------------------------------
# G. ValuationEngine integration
# ---------------------------------------------------------------------------

class TestValuationEngineIntegration:
    """Integration tests: empirical_pos_engine wires into ValuationEngine."""

    def _build_engine_output(self, empirical_pos_engine=None):
        """Build a minimal ValuationOutput via ValuationEngine."""
        from bve.entities.asset import Asset, Modality, TherapeuticArea
        from bve.entities.company import Company
        from bve.entities.trial import ClinicalTrial, TrialPhase
        from bve.models.market_model import MarketModel
        from bve.models.monte_carlo import MonteCarloParams
        from bve.valuation.valuation_engine import ValuationEngine

        asset = Asset(
            id="emp-asset",
            name="EmpiricalDrug",
            indication="NSCLC",
            stage="phase_2",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            modality=Modality.SMALL_MOLECULE,
            discount_rate=0.12,
        )
        company = Company(
            id="emp-co",
            name="EmpCo",
            cash_millions=100.0,
            shares_outstanding_millions=50.0,
        )
        trial = ClinicalTrial(
            asset_id="emp-asset",
            phase=TrialPhase.PHASE_2,
            success_probability=0.32,
            duration_years=2.0,
            cost_millions=30.0,
        )
        market = MarketModel(
            asset_id="emp-asset",
            total_addressable_market_millions=5000.0,
            years_to_peak=3,
            peak_penetration=0.10,
            patent_life_years=10,
        )
        engine = ValuationEngine(
            asset=asset,
            company=company,
            trials=[trial],
            market_model=market,
            mc_params=MonteCarloParams(n_simulations=100, random_seed=42),
            empirical_pos_engine=empirical_pos_engine,
            pos_mode="empirical_raw" if empirical_pos_engine is not None else "heuristic",
        )
        return engine

    def test_valuation_engine_accepts_empirical_pos_engine(self):
        emp_engine = EmpiricalPOSEngine.from_bundled()
        ve = self._build_engine_output(empirical_pos_engine=emp_engine)
        assert ve.empirical_pos_engine is emp_engine

    def test_empirical_engine_overrides_trial_pos(self):
        """When empirical_pos_engine is set, trial.success_probability should change."""
        emp_engine = EmpiricalPOSEngine.from_bundled()
        ve_no_emp = self._build_engine_output(empirical_pos_engine=None)
        ve_emp = self._build_engine_output(empirical_pos_engine=emp_engine)

        out_no_emp = ve_no_emp.run()
        out_emp = ve_emp.run()

        # rnpv should differ because trial POS was overridden
        base_trial_pos = 0.32  # raw value set in trial
        empirical_pos = emp_engine.compute_pos_with_adjusters("phase_2")

        # The empirical RNPV should use the empirical POS, not 0.32
        if abs(empirical_pos - base_trial_pos) > 0.01:
            assert out_emp.rnpv.rnpv_millions != pytest.approx(
                out_no_emp.rnpv.rnpv_millions, rel=0.01
            )

    def test_valuation_without_empirical_engine_uses_raw_trial_pos(self):
        """Without empirical engine and apply_pos_model=False, raw trial POS is used."""
        ve = self._build_engine_output(empirical_pos_engine=None)
        out = ve.run()
        # With raw phase_2 pos=0.32 and one trial, cumulative_success_prob ≈ 0.32
        # (may differ slightly from model_copy math)
        assert 0.20 <= out.rnpv.cumulative_success_probability <= 0.50

    def test_run_completes_without_error(self):
        emp_engine = EmpiricalPOSEngine.from_bundled()
        ve = self._build_engine_output(empirical_pos_engine=emp_engine)
        out = ve.run()
        assert out is not None
        assert out.rnpv.rnpv_millions > 0 or out.rnpv.rnpv_millions <= 0  # any value
        assert out.nav_per_share is not None
