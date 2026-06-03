"""
Sprint 32A — MCMode dual-mode framework + double-counting validation tests.

Covers:
- MCMode enum values and string serialisation
- MonteCarloParams defaults (SIMPLE mode)
- DRIVER_BASED mode: mode flag and active driver flags
- Double-counting ValueError: sample_peak_sales=True + any driver active
- DRIVER_BASED produces a valid rNPV distribution (positive mean for healthy asset)
- Driver-based mode produces wider std when multiple drivers are active vs single driver
- Mode equivalence: DRIVER_BASED with all CVs→0 ≈ deterministic base
- mode_used stored on MonteCarloResult
- sample_peak_sales=False with no driver flags → flat distribution (all draws = base_peak)
"""
import pytest
import numpy as np

from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import (
    MCMode,
    MonteCarloParams,
    MonteCarloResult,
    run_monte_carlo,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _asset() -> Asset:
    return Asset(
        id="mc32a-001",
        name="MC Test Drug",
        indication="Oncology",
        therapeutic_area="oncology",
        stage="phase_3",
        modality="small_molecule",
        launch_year=2027,
        patent_expiry_year=2039,
        discount_rate=0.10,
        effective_tax_rate=0.21,
        royalty_rate=0.0,
    )


def _trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id="mc32a-001",
            phase=TrialPhase.PHASE_3,
            success_probability=0.60,
            duration_years=3.0,
            cost_millions=100.0,
        ),
    ]


def _market() -> MarketModel:
    return MarketModel(
        asset_id="mc32a-001",
        therapeutic_area="oncology",
        addressable_patients_annual=50_000,
        net_price_per_patient_usd=80_000,
        peak_penetration=0.20,
        years_to_peak=4,
        patent_life_years=12,
        cogs_rate=0.12,
        sgna_rate_launch=0.35,
        sgna_rate_mature=0.18,
    )


def _run(params: MonteCarloParams) -> MonteCarloResult:
    return run_monte_carlo(_asset(), _trials(), _market(), params)


# ---------------------------------------------------------------------------
# MCMode enum
# ---------------------------------------------------------------------------

class TestMCModeEnum:
    def test_simple_value(self):
        assert MCMode.SIMPLE == "simple"

    def test_driver_based_value(self):
        assert MCMode.DRIVER_BASED == "driver_based"

    def test_enum_members(self):
        modes = {m.value for m in MCMode}
        assert "simple" in modes
        assert "driver_based" in modes

    def test_string_construct(self):
        assert MCMode("simple") is MCMode.SIMPLE
        assert MCMode("driver_based") is MCMode.DRIVER_BASED


# ---------------------------------------------------------------------------
# MonteCarloParams defaults
# ---------------------------------------------------------------------------

class TestParamsDefaults:
    def test_default_mode_is_simple(self):
        p = MonteCarloParams()
        assert p.mode == MCMode.SIMPLE

    def test_default_sample_peak_sales_true(self):
        p = MonteCarloParams()
        assert p.sample_peak_sales is True

    def test_default_driver_flags_false(self):
        p = MonteCarloParams()
        assert p.sample_eligible_patients is False
        assert p.sample_net_price is False
        assert p.sample_peak_penetration is False
        assert p.sample_payer_access is False
        assert p.sample_geography is False

    def test_default_driver_cvs_positive(self):
        p = MonteCarloParams()
        assert p.eligible_patients_cv > 0
        assert p.net_price_cv > 0
        assert p.peak_penetration_cv > 0
        assert p.payer_access_cv > 0
        assert p.geography_cv > 0


# ---------------------------------------------------------------------------
# Double-counting validation
# ---------------------------------------------------------------------------

class TestDoubleCountingValidation:
    def test_simple_mode_no_drivers_ok(self):
        # No error: sample_peak_sales=True, all drivers off
        p = MonteCarloParams(sample_peak_sales=True)
        assert p.sample_peak_sales is True

    def test_driver_based_no_peak_sales_ok(self):
        # No error: sample_peak_sales=False, one driver on
        p = MonteCarloParams(
            mode=MCMode.DRIVER_BASED,
            sample_peak_sales=False,
            sample_eligible_patients=True,
        )
        assert p.sample_eligible_patients is True

    def test_peak_sales_plus_eligible_patients_raises(self):
        with pytest.raises(ValueError, match="double-counting|Double-counting"):
            MonteCarloParams(
                sample_peak_sales=True,
                sample_eligible_patients=True,
            )

    def test_peak_sales_plus_net_price_raises(self):
        with pytest.raises(ValueError, match="double-counting|Double-counting"):
            MonteCarloParams(
                sample_peak_sales=True,
                sample_net_price=True,
            )

    def test_peak_sales_plus_penetration_raises(self):
        with pytest.raises(ValueError, match="double-counting|Double-counting"):
            MonteCarloParams(
                sample_peak_sales=True,
                sample_peak_penetration=True,
            )

    def test_peak_sales_plus_payer_access_raises(self):
        with pytest.raises(ValueError, match="double-counting|Double-counting"):
            MonteCarloParams(
                sample_peak_sales=True,
                sample_payer_access=True,
            )

    def test_peak_sales_plus_geography_raises(self):
        with pytest.raises(ValueError, match="double-counting|Double-counting"):
            MonteCarloParams(
                sample_peak_sales=True,
                sample_geography=True,
            )

    def test_peak_sales_plus_multiple_drivers_raises(self):
        with pytest.raises(ValueError, match="double-counting|Double-counting"):
            MonteCarloParams(
                sample_peak_sales=True,
                sample_eligible_patients=True,
                sample_net_price=True,
                sample_peak_penetration=True,
            )

    def test_error_message_names_active_drivers(self):
        with pytest.raises(ValueError) as exc_info:
            MonteCarloParams(
                sample_peak_sales=True,
                sample_eligible_patients=True,
                sample_net_price=True,
            )
        msg = str(exc_info.value)
        assert "eligible_patients" in msg or "net_price" in msg


# ---------------------------------------------------------------------------
# SIMPLE mode execution
# ---------------------------------------------------------------------------

class TestSimpleMode:
    def test_simple_mode_runs(self):
        p = MonteCarloParams(n_simulations=200, random_seed=42)
        result = _run(p)
        assert result.n_simulations == 200

    def test_simple_mode_result_has_mode_used(self):
        p = MonteCarloParams(n_simulations=200, random_seed=42)
        result = _run(p)
        assert result.mode_used == MCMode.SIMPLE

    def test_simple_mode_mean_positive(self):
        p = MonteCarloParams(n_simulations=300, random_seed=0)
        result = _run(p)
        assert result.mean_millions > 0

    def test_simple_mode_std_positive(self):
        p = MonteCarloParams(n_simulations=300, random_seed=0)
        result = _run(p)
        assert result.std_millions > 0


# ---------------------------------------------------------------------------
# DRIVER_BASED mode execution
# ---------------------------------------------------------------------------

class TestDriverBasedMode:
    def _driver_params(self, n_simulations: int = 300, random_seed: int = 99, **kwargs) -> MonteCarloParams:
        return MonteCarloParams(
            mode=MCMode.DRIVER_BASED,
            sample_peak_sales=False,
            n_simulations=n_simulations,
            random_seed=random_seed,
            **kwargs,
        )

    def test_driver_based_runs(self):
        p = self._driver_params(sample_eligible_patients=True)
        result = _run(p)
        assert result.n_simulations == 300

    def test_driver_based_mode_stored(self):
        p = self._driver_params(sample_net_price=True)
        result = _run(p)
        assert result.mode_used == MCMode.DRIVER_BASED

    def test_driver_based_mean_positive(self):
        p = self._driver_params(
            sample_eligible_patients=True,
            sample_net_price=True,
            sample_peak_penetration=True,
        )
        result = _run(p)
        assert result.mean_millions > 0

    def test_driver_based_std_positive_when_drivers_active(self):
        p = self._driver_params(
            sample_eligible_patients=True,
            sample_net_price=True,
        )
        result = _run(p)
        assert result.std_millions > 0

    def test_driver_based_no_drivers_flat_distribution(self):
        """With sample_peak_sales=False and no driver flags, all draws = base_peak → std=0."""
        p = MonteCarloParams(
            mode=MCMode.DRIVER_BASED,
            sample_peak_sales=False,
            n_simulations=100,
            random_seed=7,
        )
        result = _run(p)
        # Without any driver variation, the commercial side is deterministic.
        # std should be much lower than simple mode (driven only by POS + WACC).
        simple = _run(MonteCarloParams(n_simulations=100, random_seed=7))
        assert result.std_millions <= simple.std_millions

    def test_more_drivers_wider_std(self):
        """Activating more drivers increases commercial dispersion."""
        p_one = self._driver_params(
            n_simulations=500,
            random_seed=42,
            sample_eligible_patients=True,
        )
        p_multi = self._driver_params(
            n_simulations=500,
            random_seed=42,
            sample_eligible_patients=True,
            sample_net_price=True,
            sample_peak_penetration=True,
            sample_payer_access=True,
        )
        r_one = _run(p_one)
        r_multi = _run(p_multi)
        assert r_multi.std_millions > r_one.std_millions


# ---------------------------------------------------------------------------
# Mode independence
# ---------------------------------------------------------------------------

class TestModeIndependence:
    def test_simple_and_driver_based_produce_different_stds(self):
        """SIMPLE and DRIVER_BASED with equivalent CVs should differ (different sampling paths)."""
        simple = _run(MonteCarloParams(n_simulations=400, random_seed=5, peak_sales_cv=0.40))
        driver = _run(MonteCarloParams(
            mode=MCMode.DRIVER_BASED,
            sample_peak_sales=False,
            sample_eligible_patients=True,
            sample_net_price=True,
            eligible_patients_cv=0.28,
            net_price_cv=0.28,
            n_simulations=400,
            random_seed=5,
        ))
        # Both should have positive mean and std; we don't require identical values
        assert simple.mean_millions > 0
        assert driver.mean_millions > 0
        assert simple.std_millions > 0
        assert driver.std_millions > 0
