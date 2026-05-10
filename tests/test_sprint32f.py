"""
Sprint 32F — Enhanced MC outputs + compact audit trail tests.

Covers:
- SimulationAuditRecord fields present and typed correctly
- audit_trail has exactly 3 records
- audit_trail percentile labels: "P5", "P50", "P95"
- audit_trail P5 rNPV ≤ P50 rNPV ≤ P95 rNPV
- full traces NOT stored (simulated_values_millions sorted, not per-trial detail)
- expected_upside ≥ 0
- expected_downside ≤ 0
- downside_value_at_risk ≥ 0
- top_variance_drivers: non-empty list of strings
- clinical_failure_rate in [0, 1]
- competitor_disruption_rate in [0, 1]
- payer_restriction_rate in [0, 1]
- probability_nav_above_ev: None when EV not provided; in [0,1] when provided
- probability_nav_above_price: None when price not provided; in [0,1] when provided
- expected_upside > 0 for healthy asset (most trials profitable)
- downside_value_at_risk = |P5| when P5 < 0
- audit main_value_driver non-empty strings
- audit failure_reason None for positive rNPV
- audit competition_draw is int ≥ 0
"""
import pytest

from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.competition_model import CompetitionModel, CompetitorLaunch
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import (
    MCMode,
    MonteCarloParams,
    MonteCarloResult,
    SimulationAuditRecord,
    run_monte_carlo,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _asset() -> Asset:
    return Asset(
        id="mc32f-001",
        name="Test Drug",
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
            asset_id="mc32f-001",
            phase=TrialPhase.PHASE_3,
            success_probability=0.60,
            duration_years=3.0,
            cost_millions=80.0,
        ),
    ]


def _market(with_competitor: bool = False) -> MarketModel:
    comp = None
    if with_competitor:
        comp = CompetitionModel(competitors=[
            CompetitorLaunch(
                name="PipelineRival",
                status="phase_3",
                launch_year_relative=1.0,
                peak_market_share=0.20,
                years_to_peak=3,
                approval_probability=0.50,
            )
        ])
    return MarketModel(
        asset_id="mc32f-001",
        therapeutic_area="oncology",
        addressable_patients_annual=50_000,
        net_price_per_patient_usd=80_000,
        peak_penetration=0.20,
        years_to_peak=4,
        patent_life_years=12,
        cogs_rate=0.12,
        sgna_rate_launch=0.35,
        sgna_rate_mature=0.18,
        competition_model=comp,
    )


def _run(n: int = 300, seed: int = 42, **kwargs) -> MonteCarloResult:
    params = MonteCarloParams(n_simulations=n, random_seed=seed)
    return run_monte_carlo(_asset(), _trials(), _market(), params, **kwargs)


# ---------------------------------------------------------------------------
# SimulationAuditRecord structure
# ---------------------------------------------------------------------------

class TestAuditRecordStructure:
    def test_audit_trail_has_exactly_3_records(self):
        result = _run()
        assert len(result.audit_trail) == 3

    def test_percentile_labels(self):
        result = _run()
        labels = {r.percentile_label for r in result.audit_trail}
        assert labels == {"P5", "P50", "P95"}

    def test_p5_le_p50_le_p95(self):
        result = _run()
        by_label = {r.percentile_label: r.rnpv_millions for r in result.audit_trail}
        assert by_label["P5"] <= by_label["P50"] <= by_label["P95"]

    def test_audit_record_has_all_fields(self):
        result = _run()
        r = result.audit_trail[0]
        assert isinstance(r, SimulationAuditRecord)
        assert isinstance(r.simulation_id, int)
        assert isinstance(r.percentile_label, str)
        assert isinstance(r.clinical_draw, float)
        assert isinstance(r.commercial_draw, float)
        assert isinstance(r.cost_draw, float)
        assert isinstance(r.competition_draw, int)
        assert isinstance(r.rnpv_millions, float)
        assert isinstance(r.main_value_driver, str)

    def test_competition_draw_is_non_negative_int(self):
        result = _run()
        for r in result.audit_trail:
            assert r.competition_draw >= 0
            assert isinstance(r.competition_draw, int)

    def test_main_value_driver_non_empty(self):
        result = _run()
        for r in result.audit_trail:
            assert len(r.main_value_driver) > 0

    def test_failure_reason_none_for_positive_rnpv(self):
        result = _run()
        for r in result.audit_trail:
            if r.rnpv_millions >= 0:
                assert r.failure_reason is None

    def test_cost_draw_in_valid_wacc_range(self):
        result = _run()
        for r in result.audit_trail:
            assert 0.01 <= r.cost_draw <= 0.50

    def test_clinical_draw_in_unit_interval(self):
        result = _run()
        for r in result.audit_trail:
            assert 0.0 <= r.clinical_draw <= 1.0


# ---------------------------------------------------------------------------
# Expected upside / downside
# ---------------------------------------------------------------------------

class TestExpectedUpsideDownside:
    def test_expected_upside_non_negative(self):
        result = _run()
        assert result.expected_upside >= 0.0

    def test_expected_downside_non_positive(self):
        result = _run()
        assert result.expected_downside <= 0.0

    def test_expected_upside_positive_for_healthy_asset(self):
        """A well-resourced Phase 3 asset should have positive expected upside."""
        result = _run(n=400)
        assert result.expected_upside > 0.0

    def test_downside_value_at_risk_non_negative(self):
        result = _run()
        assert result.downside_value_at_risk >= 0.0

    def test_downside_var_equals_abs_p5_when_p5_negative(self):
        result = _run(n=500)
        if result.percentile_5_millions < 0:
            assert result.downside_value_at_risk == pytest.approx(
                -result.percentile_5_millions, abs=5.0
            )


# ---------------------------------------------------------------------------
# Top variance drivers
# ---------------------------------------------------------------------------

class TestTopVarianceDrivers:
    def test_top_variance_drivers_non_empty(self):
        result = _run(n=400)
        assert len(result.top_variance_drivers) > 0

    def test_top_variance_drivers_are_strings(self):
        result = _run()
        for d in result.top_variance_drivers:
            assert isinstance(d, str) and len(d) > 0

    def test_top_variance_drivers_max_5(self):
        result = _run()
        assert len(result.top_variance_drivers) <= 5

    def test_peak_sales_in_top_drivers(self):
        """peak_sales should consistently be a top variance driver in SIMPLE mode."""
        result = _run(n=500, seed=0)
        assert "peak_sales" in result.top_variance_drivers


# ---------------------------------------------------------------------------
# Event rate diagnostics
# ---------------------------------------------------------------------------

class TestEventRateDiagnostics:
    def test_clinical_failure_rate_in_unit_interval(self):
        result = _run()
        assert 0.0 <= result.clinical_failure_rate <= 1.0

    def test_competitor_disruption_rate_zero_without_competitors(self):
        params = MonteCarloParams(n_simulations=200, random_seed=0)
        result = run_monte_carlo(_asset(), _trials(), _market(with_competitor=False), params)
        assert result.competitor_disruption_rate == pytest.approx(0.0)

    def test_competitor_disruption_rate_positive_with_p05_competitor(self):
        params = MonteCarloParams(n_simulations=300, random_seed=7)
        result = run_monte_carlo(_asset(), _trials(), _market(with_competitor=True), params)
        assert result.competitor_disruption_rate > 0.0

    def test_payer_restriction_rate_zero_without_payer_sampling(self):
        result = _run()
        assert result.payer_restriction_rate == pytest.approx(0.0)

    def test_payer_restriction_rate_in_unit_interval(self):
        result = _run()
        assert 0.0 <= result.payer_restriction_rate <= 1.0


# ---------------------------------------------------------------------------
# Conditional probability fields
# ---------------------------------------------------------------------------

class TestConditionalProbabilities:
    def test_prob_nav_above_ev_none_by_default(self):
        result = _run()
        assert result.probability_nav_above_ev is None

    def test_prob_nav_above_price_none_by_default(self):
        result = _run()
        assert result.probability_nav_above_price is None

    def test_prob_nav_above_ev_populated_when_ev_provided(self):
        params = MonteCarloParams(n_simulations=300, random_seed=0)
        result = run_monte_carlo(
            _asset(), _trials(), _market(), params,
            enterprise_value_millions=500.0,
        )
        assert result.probability_nav_above_ev is not None
        assert 0.0 <= result.probability_nav_above_ev <= 1.0

    def test_prob_nav_above_price_populated_when_price_provided(self):
        params = MonteCarloParams(n_simulations=300, random_seed=0)
        result = run_monte_carlo(
            _asset(), _trials(), _market(), params,
            current_price_per_share=50.0,
            shares_outstanding_millions=20.0,
        )
        assert result.probability_nav_above_price is not None
        assert 0.0 <= result.probability_nav_above_price <= 1.0

    def test_prob_nav_above_ev_zero_for_very_high_ev(self):
        params = MonteCarloParams(n_simulations=200, random_seed=1)
        result = run_monte_carlo(
            _asset(), _trials(), _market(), params,
            enterprise_value_millions=1_000_000.0,  # 1 trillion
        )
        assert result.probability_nav_above_ev == pytest.approx(0.0, abs=0.01)

    def test_prob_nav_above_ev_high_for_very_low_ev(self):
        params = MonteCarloParams(n_simulations=200, random_seed=2)
        result = run_monte_carlo(
            _asset(), _trials(), _market(), params,
            enterprise_value_millions=-1_000.0,
            net_cash_millions=0.0,
        )
        assert result.probability_nav_above_ev > 0.5


# ---------------------------------------------------------------------------
# Full traces not stored
# ---------------------------------------------------------------------------

class TestFullTracesNotStored:
    def test_audit_trail_only_3_not_n(self):
        """audit_trail has 3 records, not n_simulations records."""
        result = _run(n=500)
        assert len(result.audit_trail) == 3
        assert result.n_simulations == 500

    def test_simulated_values_is_sorted(self):
        """simulated_values_millions is sorted (ascending), not raw trial order."""
        result = _run(n=300)
        vals = result.simulated_values_millions
        assert vals == sorted(vals)
