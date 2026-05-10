"""
Sprint E4 — TA/phase-specific cost defaults.

Tests cover:
  1. AssumptionsLoader.phase_cost(ta, phase): lookup, fallback, warning
  2. _apply_trial_cost_defaults(): substitution when cost_source="default",
     no-op when cost_source="override"
  3. Regression: cost_source="override" trials are unchanged end-to-end
"""
from __future__ import annotations

import warnings

import pytest

from bve.config.assumptions_loader import AssumptionsLoader
from bve.entities.asset import Asset
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial
from bve.models.market_model import MarketModel
from bve.valuation.valuation_engine import ValuationEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _asset(ta: str = "oncology") -> Asset:
    return Asset(
        id=f"e4-test-{ta}",
        name="E4 Test Asset",
        indication="Test",
        therapeutic_area=ta,
        stage="phase_3",
        modality="small_molecule",
        discount_rate=0.10,
    )


def _company() -> Company:
    return Company(
        id="e4-co",
        name="E4 Co",
        cash_millions=200.0,
        shares_outstanding_millions=50.0,
    )


def _market(ta: str = "oncology") -> MarketModel:
    return MarketModel(
        asset_id=f"e4-test-{ta}",
        therapeutic_area=ta,
        total_addressable_market_millions=500.0,
        peak_penetration=0.10,
        patent_life_years=10,
    )


def _trial(phase: str, cost: float, source: str = "override", ta: str = "oncology") -> ClinicalTrial:
    return ClinicalTrial(
        asset_id=f"e4-test-{ta}",
        phase=phase,
        success_probability=0.55,
        duration_years=2.0,
        cost_millions=cost,
        cost_source=source,
    )


# ---------------------------------------------------------------------------
# 1. AssumptionsLoader.phase_cost — lookup
# ---------------------------------------------------------------------------

class TestPhaseCostLookup:
    def test_known_ta_known_phase_returns_float(self):
        cost = AssumptionsLoader.get().phase_cost("oncology", "phase_3")
        assert isinstance(cost, float)
        assert cost > 0

    def test_oncology_phase3_is_higher_than_rare_disease(self):
        onc = AssumptionsLoader.get().phase_cost("oncology", "phase_3")
        rd = AssumptionsLoader.get().phase_cost("rare_disease", "phase_3")
        assert onc > rd, "Oncology Phase 3 should be more expensive than rare disease"

    def test_cardiovascular_phase3_is_highest(self):
        """CV CVOT trials are the most expensive Phase 3s."""
        cv = AssumptionsLoader.get().phase_cost("cardiovascular", "phase_3")
        onc = AssumptionsLoader.get().phase_cost("oncology", "phase_3")
        rd = AssumptionsLoader.get().phase_cost("rare_disease", "phase_3")
        assert cv >= onc >= rd

    def test_phase3_more_expensive_than_phase2(self):
        for ta in ("oncology", "rare_disease", "cns", "cardiovascular", "immunology"):
            p2 = AssumptionsLoader.get().phase_cost(ta, "phase_2")
            p3 = AssumptionsLoader.get().phase_cost(ta, "phase_3")
            assert p3 > p2, f"{ta}: Phase 3 should cost more than Phase 2"

    def test_phase2_more_expensive_than_phase1(self):
        for ta in ("oncology", "rare_disease", "cns"):
            p1 = AssumptionsLoader.get().phase_cost(ta, "phase_1")
            p2 = AssumptionsLoader.get().phase_cost(ta, "phase_2")
            assert p2 > p1, f"{ta}: Phase 2 should cost more than Phase 1"

    def test_all_entry_matches_flat_defaults(self):
        """'all' entry must be consistent with the legacy phase_costs_millions table."""
        loader = AssumptionsLoader.get()
        flat = loader.phase_costs_millions
        for phase in ("phase_1", "phase_2", "phase_3", "nda_bla"):
            assert loader.phase_cost("all", phase) == pytest.approx(
                float(flat[phase]), rel=1e-6
            ), f"phase_cost_defaults['all'][{phase!r}] should match phase_costs_millions"

    def test_granular_tas_covered(self):
        """All major TAs should have entries."""
        for ta in ("oncology", "rare_disease", "cns", "cardiovascular", "immunology",
                   "infectious_disease", "ophthalmology", "metabolic", "dermatology"):
            cost = AssumptionsLoader.get().phase_cost(ta, "phase_3")
            assert cost > 0, f"Missing phase_cost_defaults entry for {ta!r}"

    def test_unknown_ta_falls_back_to_all_with_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cost = AssumptionsLoader.get().phase_cost("xenobiology", "phase_2")
        assert any("xenobiology" in str(w.message) for w in caught)
        assert any("all" in str(w.message) for w in caught)
        # should equal the "all" phase_2 default
        expected = AssumptionsLoader.get().phase_cost("all", "phase_2")
        assert cost == pytest.approx(expected, rel=1e-6)

    def test_other_ta_is_same_as_all(self):
        """'other' fallback should mirror the cross-TA average."""
        loader = AssumptionsLoader.get()
        for phase in ("phase_1", "phase_2", "phase_3", "nda_bla"):
            assert loader.phase_cost("other", phase) == pytest.approx(
                loader.phase_cost("all", phase), rel=1e-6
            )


# ---------------------------------------------------------------------------
# 2. _apply_trial_cost_defaults — substitution behaviour
# ---------------------------------------------------------------------------

def _dummy_trial(phase: str = "phase_3", cost: float = 100.0, source: str = "override") -> ClinicalTrial:
    """Trial with asset_id matching _asset() helper."""
    return ClinicalTrial(
        asset_id="e4-test-oncology",
        phase=phase,
        success_probability=0.55,
        duration_years=2.0,
        cost_millions=cost,
        cost_source=source,
    )


def _engine(ta: str = "oncology") -> ValuationEngine:
    """Construct a minimal ValuationEngine for the given TA."""
    asset = _asset(ta)
    dummy = [_dummy_trial()]  # engine filters by asset_id anyway
    return ValuationEngine(asset, _company(), dummy, _market(ta))


class TestCostSubstitution:
    def test_default_source_substitutes_cost(self):
        """cost_source='default' trial gets cost replaced with TA-calibrated value."""
        engine = _engine("oncology")
        trial = _trial("phase_3", cost=99.0, source="default")
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = engine._apply_trial_cost_defaults([trial])

        expected = AssumptionsLoader.get().phase_cost("oncology", "phase_3")
        assert result[0].cost_millions == pytest.approx(expected, rel=1e-6)

    def test_default_source_marks_as_default_applied(self):
        """After substitution, cost_source becomes 'default_applied'."""
        engine = _engine("oncology")
        trial = _trial("phase_3", cost=99.0, source="default")
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = engine._apply_trial_cost_defaults([trial])

        assert result[0].cost_source == "default_applied"

    def test_default_source_emits_warning(self):
        """cost_source='default' must emit a UserWarning with TA and calibrated cost."""
        engine = _engine("oncology")
        trial = _trial("phase_3", cost=99.0, source="default")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            engine._apply_trial_cost_defaults([trial])

        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warnings) >= 1
        msg = str(user_warnings[0].message)
        assert "oncology" in msg
        assert "phase_3" in msg

    def test_override_source_not_substituted(self):
        """cost_source='override' trial cost is unchanged."""
        engine = _engine("oncology")
        original_cost = 180.0
        trial = _trial("phase_3", cost=original_cost, source="override")
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = engine._apply_trial_cost_defaults([trial])

        assert result[0].cost_millions == pytest.approx(original_cost, rel=1e-6)
        assert result[0].cost_source == "override"

    def test_override_source_emits_no_warning(self):
        """cost_source='override' should emit no UserWarning."""
        engine = _engine("oncology")
        trial = _trial("phase_3", cost=180.0, source="override")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            engine._apply_trial_cost_defaults([trial])

        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warnings) == 0

    def test_already_applied_source_not_resubstituted(self):
        """cost_source='default_applied' is treated as override (idempotent)."""
        engine = _engine("oncology")
        trial = _trial("phase_3", cost=300.0, source="default_applied")
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = engine._apply_trial_cost_defaults([trial])

        assert result[0].cost_millions == pytest.approx(300.0, rel=1e-6)
        assert result[0].cost_source == "default_applied"

    def test_mixed_trials_selective_substitution(self):
        """Only 'default' trials are substituted; 'override' trials are preserved."""
        engine = _engine("oncology")
        t_override = _trial("phase_2", cost=55.0, source="override")
        t_default = ClinicalTrial(
            asset_id="e4-test-oncology",
            phase="nda_bla",
            success_probability=0.90,
            duration_years=1.0,
            cost_millions=10.0,
            cost_source="default",
        )

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = engine._apply_trial_cost_defaults([t_override, t_default])

        assert result[0].cost_millions == pytest.approx(55.0, rel=1e-6)
        assert result[0].cost_source == "override"
        expected_nda = AssumptionsLoader.get().phase_cost("oncology", "nda_bla")
        assert result[1].cost_millions == pytest.approx(expected_nda, rel=1e-6)
        assert result[1].cost_source == "default_applied"

    def test_substitution_uses_asset_ta(self):
        """Cost default is keyed to the asset's therapeutic_area, not a fixed TA."""
        for ta in ("oncology", "rare_disease", "cardiovascular"):
            engine = _engine(ta)
            trial = ClinicalTrial(
                asset_id=f"e4-test-{ta}",
                phase="phase_3",
                success_probability=0.60,
                duration_years=3.0,
                cost_millions=999.0,
                cost_source="default",
            )
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                result = engine._apply_trial_cost_defaults([trial])

            expected = AssumptionsLoader.get().phase_cost(ta, "phase_3")
            assert result[0].cost_millions == pytest.approx(expected, rel=1e-6), (
                f"TA={ta}: expected ${expected:.0f}M, got ${result[0].cost_millions:.0f}M"
            )

    def test_original_trial_not_mutated(self):
        """model_copy must be used — original trial object is unchanged."""
        engine = _engine("oncology")
        original_cost = 99.0
        trial = _trial("phase_3", cost=original_cost, source="default")

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = engine._apply_trial_cost_defaults([trial])

        assert trial.cost_millions == pytest.approx(original_cost, rel=1e-6)
        assert result[0] is not trial


# ---------------------------------------------------------------------------
# 3. Regression — override trials pass through engine unmodified
# ---------------------------------------------------------------------------

class TestRegressionConfig:
    """Verify that existing configs with cost_source='override' run unaffected."""

    def _run(self, ta: str, cost_p3: float, cost_nda: float) -> float:
        """Run engine, return base-case rNPV."""
        asset = _asset(ta)
        company = _company()
        market = _market(ta)
        trials = [
            ClinicalTrial(
                asset_id=asset.id,
                phase="phase_3",
                success_probability=0.55,
                duration_years=3.0,
                cost_millions=cost_p3,
                cost_source="override",
            ),
            ClinicalTrial(
                asset_id=asset.id,
                phase="nda_bla",
                success_probability=0.88,
                duration_years=1.5,
                cost_millions=cost_nda,
                cost_source="override",
            ),
        ]
        engine = ValuationEngine(asset, company, trials, market)
        output = engine.run()
        return output.rnpv.rnpv_millions

    def test_oncology_override_runs(self):
        """Oncology config with override costs completes without error."""
        rnpv = self._run("oncology", cost_p3=180.0, cost_nda=20.0)
        assert isinstance(rnpv, float)
        assert rnpv != 0  # some non-trivial result

    def test_rare_disease_override_runs(self):
        rnpv = self._run("rare_disease", cost_p3=120.0, cost_nda=18.0)
        assert isinstance(rnpv, float)

    def test_override_is_deterministic(self):
        """Same override costs → identical rNPV on repeated calls."""
        r1 = self._run("oncology", cost_p3=200.0, cost_nda=30.0)
        r2 = self._run("oncology", cost_p3=200.0, cost_nda=30.0)
        assert r1 == pytest.approx(r2, rel=1e-6)

    def test_higher_cost_lower_rnpv(self):
        """Doubling trial cost reduces rNPV."""
        r_low = self._run("oncology", cost_p3=100.0, cost_nda=20.0)
        r_hi = self._run("oncology", cost_p3=400.0, cost_nda=80.0)
        assert r_low > r_hi

    def test_default_cost_source_field_default_is_override(self):
        """ClinicalTrial.cost_source defaults to 'override', not 'default'."""
        trial = ClinicalTrial(
            asset_id="x",
            phase="phase_3",
            success_probability=0.55,
            duration_years=3.0,
            cost_millions=100.0,
        )
        assert trial.cost_source == "override"
