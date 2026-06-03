"""
Tests for Sprint C1: PayerAccessModel.

Coverage areas
--------------
1. PayerAccessModel field validation
2. effective_penetration_multiplier() formula
3. coverage_delay_fraction() per-year logic
4. step_edit_ramp_multiplier() decay profile
5. combined_multiplier() product of all components
6. Default model produces no effect (multiplier == 1.0)
7. MarketModel.payer_access field — TAM-based mode
8. MarketModel.payer_access field — patient-based mode
9. access_probability scales revenue proportionally
10. prior_auth_burden reduces effective penetration
11. coverage_delay_months reduces early-year revenue, not late
12. step_edit_risk ramp: Year-1 worst, Year-3+ restored
13. Combination of all four factors
14. Backward compatibility — existing models without payer_access unaffected
15. CommercialInputs mode: peak_sales adjusted by permanent multiplier
16. High-price specialty drug example (meaningful access impact)
17. __init__ export
"""
from __future__ import annotations

import pytest

from bve.models.market_model import MarketModel
from bve.models.payer_access import PayerAccessModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tam_market(
    peak_pen: float = 0.20,
    tam: float = 1_000.0,
    patent_life: int = 12,
    payer_access: PayerAccessModel | None = None,
    years_to_peak: int = 4,
) -> MarketModel:
    kwargs: dict = dict(
        asset_id="test",
        total_addressable_market_millions=tam,
        peak_penetration=peak_pen,
        patent_life_years=patent_life,
        adoption_curve_mode="s_curve",
        years_to_peak=years_to_peak,
    )
    if payer_access is not None:
        kwargs["payer_access"] = payer_access
    return MarketModel(**kwargs)


def _patient_market(
    peak_pen: float = 0.20,
    payer_access: PayerAccessModel | None = None,
) -> MarketModel:
    kwargs: dict = dict(
        asset_id="test",
        addressable_patients_annual=50_000,
        net_price_per_patient_usd=100_000.0,
        peak_penetration=peak_pen,
        patent_life_years=12,
        adoption_curve_mode="s_curve",
        years_to_peak=4,
    )
    if payer_access is not None:
        kwargs["payer_access"] = payer_access
    return MarketModel(**kwargs)


# ---------------------------------------------------------------------------
# 1. PayerAccessModel field validation
# ---------------------------------------------------------------------------

class TestPayerAccessModelValidation:
    def test_defaults_valid(self):
        pa = PayerAccessModel()
        assert pa.access_probability == pytest.approx(1.0)
        assert pa.coverage_delay_months == pytest.approx(0.0)
        assert pa.prior_auth_burden == pytest.approx(0.0)
        assert pa.step_edit_risk == pytest.approx(0.0)

    def test_access_probability_must_be_positive(self):
        with pytest.raises(Exception):
            PayerAccessModel(access_probability=0.0)

    def test_access_probability_max_one(self):
        pa = PayerAccessModel(access_probability=1.0)
        assert pa.access_probability == 1.0

    def test_coverage_delay_max_24_months(self):
        with pytest.raises(Exception):
            PayerAccessModel(coverage_delay_months=25.0)

    def test_prior_auth_burden_range(self):
        pa = PayerAccessModel(prior_auth_burden=0.0)
        assert pa.prior_auth_burden == 0.0
        pa2 = PayerAccessModel(prior_auth_burden=1.0)
        assert pa2.prior_auth_burden == 1.0

    def test_step_edit_risk_range(self):
        pa = PayerAccessModel(step_edit_risk=0.0)
        assert pa.step_edit_risk == 0.0
        pa2 = PayerAccessModel(step_edit_risk=1.0)
        assert pa2.step_edit_risk == 1.0

    def test_is_frozen(self):
        from pydantic import ValidationError
        pa = PayerAccessModel(access_probability=0.8)
        with pytest.raises((AttributeError, TypeError, ValidationError)):
            pa.access_probability = 0.9  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. effective_penetration_multiplier()
# ---------------------------------------------------------------------------

class TestEffectivePenetrationMultiplier:
    def test_defaults_return_one(self):
        assert PayerAccessModel().effective_penetration_multiplier() == pytest.approx(1.0)

    def test_access_probability_scales_linearly(self):
        pa = PayerAccessModel(access_probability=0.70)
        assert pa.effective_penetration_multiplier() == pytest.approx(0.70)

    def test_prior_auth_burden_zero_no_effect(self):
        pa = PayerAccessModel(prior_auth_burden=0.0)
        assert pa.effective_penetration_multiplier() == pytest.approx(1.0)

    def test_prior_auth_burden_one_gives_half(self):
        pa = PayerAccessModel(prior_auth_burden=1.0)
        # 1 - 1.0 × 0.5 = 0.5
        assert pa.effective_penetration_multiplier() == pytest.approx(0.5)

    def test_prior_auth_burden_0_5(self):
        pa = PayerAccessModel(prior_auth_burden=0.5)
        # 1 - 0.5 × 0.5 = 0.75
        assert pa.effective_penetration_multiplier() == pytest.approx(0.75)

    def test_combined_access_and_pa_burden(self):
        pa = PayerAccessModel(access_probability=0.80, prior_auth_burden=0.40)
        # 0.80 × (1 - 0.40 × 0.5) = 0.80 × 0.80 = 0.64
        assert pa.effective_penetration_multiplier() == pytest.approx(0.64)


# ---------------------------------------------------------------------------
# 3. coverage_delay_fraction()
# ---------------------------------------------------------------------------

class TestCoverageDelayFraction:
    def test_no_delay_full_fraction_all_years(self):
        pa = PayerAccessModel(coverage_delay_months=0.0)
        for yr in range(1, 6):
            assert pa.coverage_delay_fraction(yr) == pytest.approx(1.0)

    def test_6mo_delay_year1_half(self):
        pa = PayerAccessModel(coverage_delay_months=6.0)
        assert pa.coverage_delay_fraction(1) == pytest.approx(0.5)

    def test_6mo_delay_year2_full(self):
        pa = PayerAccessModel(coverage_delay_months=6.0)
        assert pa.coverage_delay_fraction(2) == pytest.approx(1.0)

    def test_12mo_delay_year1_zero(self):
        pa = PayerAccessModel(coverage_delay_months=12.0)
        assert pa.coverage_delay_fraction(1) == pytest.approx(0.0)

    def test_12mo_delay_year2_full(self):
        pa = PayerAccessModel(coverage_delay_months=12.0)
        assert pa.coverage_delay_fraction(2) == pytest.approx(1.0)

    def test_18mo_delay_year1_zero(self):
        pa = PayerAccessModel(coverage_delay_months=18.0)
        assert pa.coverage_delay_fraction(1) == pytest.approx(0.0)

    def test_18mo_delay_year2_half(self):
        pa = PayerAccessModel(coverage_delay_months=18.0)
        # year=2, delay_years=1.5 → 2 - 1.5 = 0.5
        assert pa.coverage_delay_fraction(2) == pytest.approx(0.5)

    def test_18mo_delay_year3_full(self):
        pa = PayerAccessModel(coverage_delay_months=18.0)
        # year=3, delay_years=1.5 → 3 - 1.5 = 1.5, clamped to 1.0
        assert pa.coverage_delay_fraction(3) == pytest.approx(1.0)

    def test_3mo_delay_year1_fraction(self):
        pa = PayerAccessModel(coverage_delay_months=3.0)
        # 1 - 0.25 = 0.75
        assert pa.coverage_delay_fraction(1) == pytest.approx(0.75)

    def test_fraction_never_below_zero(self):
        pa = PayerAccessModel(coverage_delay_months=24.0)
        assert pa.coverage_delay_fraction(1) == pytest.approx(0.0)
        assert pa.coverage_delay_fraction(2) == pytest.approx(0.0)
        assert pa.coverage_delay_fraction(3) == pytest.approx(1.0)

    def test_fraction_never_above_one(self):
        pa = PayerAccessModel(coverage_delay_months=1.0)
        # Even with tiny delay, year 2 is clamped at 1.0
        assert pa.coverage_delay_fraction(2) == pytest.approx(1.0)
        assert pa.coverage_delay_fraction(5) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 4. step_edit_ramp_multiplier()
# ---------------------------------------------------------------------------

class TestStepEditRampMultiplier:
    def test_no_risk_all_ones(self):
        pa = PayerAccessModel(step_edit_risk=0.0)
        for yr in range(1, 5):
            assert pa.step_edit_ramp_multiplier(yr) == pytest.approx(1.0)

    def test_full_risk_year1(self):
        pa = PayerAccessModel(step_edit_risk=1.0)
        # 1 - 1.0 = 0.0
        assert pa.step_edit_ramp_multiplier(1) == pytest.approx(0.0)

    def test_full_risk_year2(self):
        pa = PayerAccessModel(step_edit_risk=1.0)
        # 1 - 1.0 × 0.5 = 0.5
        assert pa.step_edit_ramp_multiplier(2) == pytest.approx(0.5)

    def test_full_risk_year3_restored(self):
        pa = PayerAccessModel(step_edit_risk=1.0)
        assert pa.step_edit_ramp_multiplier(3) == pytest.approx(1.0)

    def test_partial_risk_year1(self):
        pa = PayerAccessModel(step_edit_risk=0.40)
        assert pa.step_edit_ramp_multiplier(1) == pytest.approx(0.60)

    def test_partial_risk_year2(self):
        pa = PayerAccessModel(step_edit_risk=0.40)
        # 1 - 0.40 × 0.5 = 0.80
        assert pa.step_edit_ramp_multiplier(2) == pytest.approx(0.80)

    def test_year4_always_one(self):
        pa = PayerAccessModel(step_edit_risk=0.80)
        for yr in [3, 4, 5, 10]:
            assert pa.step_edit_ramp_multiplier(yr) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 5. combined_multiplier()
# ---------------------------------------------------------------------------

class TestCombinedMultiplier:
    def test_defaults_all_ones(self):
        pa = PayerAccessModel()
        for yr in range(1, 6):
            assert pa.combined_multiplier(yr) == pytest.approx(1.0)

    def test_access_only(self):
        pa = PayerAccessModel(access_probability=0.70)
        for yr in range(1, 6):
            assert pa.combined_multiplier(yr) == pytest.approx(0.70)

    def test_delay_only_year1_reduced(self):
        pa = PayerAccessModel(coverage_delay_months=6.0)
        assert pa.combined_multiplier(1) == pytest.approx(0.5)
        assert pa.combined_multiplier(2) == pytest.approx(1.0)

    def test_step_edit_only_ramps(self):
        pa = PayerAccessModel(step_edit_risk=0.60)
        assert pa.combined_multiplier(1) == pytest.approx(0.40)
        assert pa.combined_multiplier(2) == pytest.approx(0.70)
        assert pa.combined_multiplier(3) == pytest.approx(1.0)

    def test_all_factors_combined(self):
        pa = PayerAccessModel(
            access_probability=0.80,
            coverage_delay_months=6.0,
            prior_auth_burden=0.40,
            step_edit_risk=0.50,
        )
        # effective_pen_mult = 0.80 × (1 - 0.40×0.5) = 0.80 × 0.80 = 0.64
        # year1: delay_frac = 0.5, step_edit = 0.50 (1-0.50 = 0.50)
        # combined year1 = 0.64 × 0.5 × 0.50 = 0.16
        assert pa.combined_multiplier(1) == pytest.approx(0.64 * 0.5 * 0.50)
        # year2: delay_frac = 1.0, step_edit = 0.75 (1-0.50×0.5)
        assert pa.combined_multiplier(2) == pytest.approx(0.64 * 1.0 * 0.75)
        # year3+: delay_frac = 1.0, step_edit = 1.0
        assert pa.combined_multiplier(3) == pytest.approx(0.64)
        assert pa.combined_multiplier(10) == pytest.approx(0.64)

    def test_combined_never_negative(self):
        pa = PayerAccessModel(
            access_probability=0.10,
            prior_auth_burden=1.0,
            step_edit_risk=1.0,
            coverage_delay_months=12.0,
        )
        for yr in range(1, 8):
            assert pa.combined_multiplier(yr) >= 0.0


# ---------------------------------------------------------------------------
# 6. Default model: no effect on MarketModel revenue
# ---------------------------------------------------------------------------

class TestDefaultNoEffect:
    def test_default_pa_same_as_no_pa_tam(self):
        m_none = _tam_market()
        m_default = _tam_market(payer_access=PayerAccessModel())
        for yr in range(1, 13):
            assert m_none.revenue_in_year(yr) == pytest.approx(m_default.revenue_in_year(yr))

    def test_default_pa_same_peak_sales(self):
        m_none = _tam_market()
        m_default = _tam_market(payer_access=PayerAccessModel())
        assert m_none.peak_sales_millions == pytest.approx(m_default.peak_sales_millions)

    def test_none_pa_same_as_no_pa(self):
        m1 = _tam_market()
        m2 = _tam_market(payer_access=None)
        for yr in range(1, 13):
            assert m1.revenue_in_year(yr) == pytest.approx(m2.revenue_in_year(yr))


# ---------------------------------------------------------------------------
# 7. access_probability scales revenue
# ---------------------------------------------------------------------------

class TestAccessProbabilityScaling:
    def test_access_0_7_scales_all_years(self):
        m_base = _tam_market()
        m_pa = _tam_market(payer_access=PayerAccessModel(access_probability=0.70))
        for yr in range(1, 13):
            base_rev = m_base.revenue_in_year(yr)
            pa_rev = m_pa.revenue_in_year(yr)
            assert pa_rev == pytest.approx(base_rev * 0.70, rel=1e-6)

    def test_access_0_5_halves_revenue(self):
        m_base = _tam_market()
        m_pa = _tam_market(payer_access=PayerAccessModel(access_probability=0.50))
        for yr in range(1, 13):
            assert m_pa.revenue_in_year(yr) == pytest.approx(
                m_base.revenue_in_year(yr) * 0.50, rel=1e-6
            )

    def test_access_1_0_same_as_no_pa(self):
        m_base = _tam_market()
        m_pa = _tam_market(payer_access=PayerAccessModel(access_probability=1.0))
        for yr in range(1, 13):
            assert m_pa.revenue_in_year(yr) == pytest.approx(m_base.revenue_in_year(yr))


# ---------------------------------------------------------------------------
# 8. prior_auth_burden reduces effective penetration
# ---------------------------------------------------------------------------

class TestPriorAuthBurden:
    def test_burden_0_5_reduces_penetration(self):
        m_base = _tam_market()
        m_pa = _tam_market(payer_access=PayerAccessModel(prior_auth_burden=0.50))
        # factor = 1 - 0.5 × 0.5 = 0.75
        factor = 1.0 - 0.50 * 0.5
        for yr in range(1, 13):
            assert m_pa.revenue_in_year(yr) == pytest.approx(
                m_base.revenue_in_year(yr) * factor, rel=1e-6
            )

    def test_burden_1_0_halves_revenue(self):
        m_base = _tam_market()
        m_pa = _tam_market(payer_access=PayerAccessModel(prior_auth_burden=1.0))
        for yr in range(1, 13):
            assert m_pa.revenue_in_year(yr) == pytest.approx(
                m_base.revenue_in_year(yr) * 0.50, rel=1e-6
            )

    def test_burden_persistent_across_years(self):
        m_base = _tam_market()
        m_pa = _tam_market(payer_access=PayerAccessModel(prior_auth_burden=0.40))
        factor = 1.0 - 0.40 * 0.5
        # Same factor in year 1 and year 10
        r1_base = m_base.revenue_in_year(1)
        r10_base = m_base.revenue_in_year(10)
        assert m_pa.revenue_in_year(1) == pytest.approx(r1_base * factor)
        assert m_pa.revenue_in_year(10) == pytest.approx(r10_base * factor)


# ---------------------------------------------------------------------------
# 9. coverage_delay reduces early-year revenue, not late-year
# ---------------------------------------------------------------------------

class TestCoverageDelayRevenue:
    def test_6mo_delay_suppresses_year1(self):
        m_base = _tam_market()
        m_pa = _tam_market(payer_access=PayerAccessModel(coverage_delay_months=6.0))
        # Year 1 halved
        assert m_pa.revenue_in_year(1) == pytest.approx(m_base.revenue_in_year(1) * 0.5, rel=1e-6)

    def test_6mo_delay_no_effect_year2(self):
        m_base = _tam_market()
        m_pa = _tam_market(payer_access=PayerAccessModel(coverage_delay_months=6.0))
        assert m_pa.revenue_in_year(2) == pytest.approx(m_base.revenue_in_year(2), rel=1e-6)

    def test_12mo_delay_year1_zero(self):
        m_pa = _tam_market(payer_access=PayerAccessModel(coverage_delay_months=12.0))
        assert m_pa.revenue_in_year(1) == pytest.approx(0.0, abs=1e-9)

    def test_12mo_delay_year2_full(self):
        m_base = _tam_market()
        m_pa = _tam_market(payer_access=PayerAccessModel(coverage_delay_months=12.0))
        assert m_pa.revenue_in_year(2) == pytest.approx(m_base.revenue_in_year(2), rel=1e-6)

    def test_18mo_delay_year2_half(self):
        m_base = _tam_market()
        m_pa = _tam_market(payer_access=PayerAccessModel(coverage_delay_months=18.0))
        assert m_pa.revenue_in_year(2) == pytest.approx(m_base.revenue_in_year(2) * 0.5, rel=1e-6)

    def test_late_years_unaffected_by_delay(self):
        m_base = _tam_market()
        m_pa = _tam_market(payer_access=PayerAccessModel(coverage_delay_months=6.0))
        for yr in range(3, 13):
            assert m_pa.revenue_in_year(yr) == pytest.approx(m_base.revenue_in_year(yr), rel=1e-6)


# ---------------------------------------------------------------------------
# 10. step_edit_risk ramp
# ---------------------------------------------------------------------------

class TestStepEditRiskRevenue:
    def test_step_edit_ramp_year1_worst(self):
        m_base = _tam_market()
        m_pa = _tam_market(payer_access=PayerAccessModel(step_edit_risk=0.40))
        assert m_pa.revenue_in_year(1) == pytest.approx(m_base.revenue_in_year(1) * 0.60, rel=1e-6)

    def test_step_edit_ramp_year2_partial(self):
        m_base = _tam_market()
        m_pa = _tam_market(payer_access=PayerAccessModel(step_edit_risk=0.40))
        # 1 - 0.40 × 0.5 = 0.80
        assert m_pa.revenue_in_year(2) == pytest.approx(m_base.revenue_in_year(2) * 0.80, rel=1e-6)

    def test_step_edit_ramp_year3_restored(self):
        m_base = _tam_market()
        m_pa = _tam_market(payer_access=PayerAccessModel(step_edit_risk=0.40))
        assert m_pa.revenue_in_year(3) == pytest.approx(m_base.revenue_in_year(3), rel=1e-6)

    def test_step_edit_years_beyond_3_unaffected(self):
        m_base = _tam_market()
        m_pa = _tam_market(payer_access=PayerAccessModel(step_edit_risk=0.80))
        for yr in range(3, 13):
            assert m_pa.revenue_in_year(yr) == pytest.approx(m_base.revenue_in_year(yr), rel=1e-6)

    def test_step_edit_zero_no_effect(self):
        m_base = _tam_market()
        m_pa = _tam_market(payer_access=PayerAccessModel(step_edit_risk=0.0))
        for yr in range(1, 13):
            assert m_pa.revenue_in_year(yr) == pytest.approx(m_base.revenue_in_year(yr))


# ---------------------------------------------------------------------------
# 11. Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_no_payer_access_field_unchanged(self):
        m = MarketModel(
            asset_id="bc-test",
            total_addressable_market_millions=500.0,
            peak_penetration=0.15,
            patent_life_years=10,
        )
        assert m.payer_access is None
        assert m.revenue_in_year(1) > 0.0  # sanity check
        assert m.peak_sales_millions == pytest.approx(500.0 * 0.15)

    def test_patient_mode_unchanged(self):
        m1 = _patient_market()
        m2 = _patient_market(payer_access=None)
        for yr in range(1, 13):
            assert m1.revenue_in_year(yr) == pytest.approx(m2.revenue_in_year(yr))


# ---------------------------------------------------------------------------
# 12. CommercialInputs mode: peak_sales adjusted by permanent multiplier
# ---------------------------------------------------------------------------

class TestCommercialInputsMode:
    def _ci_market(self, access_probability: float = 1.0, prior_auth_burden: float = 0.0) -> MarketModel:
        from bve.models.commercial_inputs import CommercialInputs, PatientPool, PricingModel, ShareModel
        ci = CommercialInputs(
            patient_pool=PatientPool(
                indication="Test",
                disease_model="prevalent",
                prevalence_thousands=100.0,
                diagnosed_fraction=0.80,
                eligible_rate=0.70,
                treated_fraction=0.90,
            ),
            pricing=PricingModel(net_price_usd=50_000.0, launch_discount=0.0),
            share=ShareModel(peak_share=0.20, years_to_peak=4),
        )
        pa = PayerAccessModel(
            access_probability=access_probability,
            prior_auth_burden=prior_auth_burden,
        ) if (access_probability != 1.0 or prior_auth_burden != 0.0) else None
        return MarketModel(
            asset_id="ci-test",
            total_addressable_market_millions=500.0,  # needed for revenue_in_year fallback
            peak_penetration=0.20,
            patent_life_years=12,
            commercial_inputs=ci,
            payer_access=pa,
        )

    def test_default_pa_unchanged(self):
        m_base = self._ci_market()
        m_pa = MarketModel(
            asset_id="ci-test",
            total_addressable_market_millions=500.0,
            peak_penetration=0.20,
            patent_life_years=12,
            commercial_inputs=m_base.commercial_inputs,
            payer_access=PayerAccessModel(),  # all defaults
        )
        assert m_pa.peak_sales_millions == pytest.approx(m_base.peak_sales_millions)

    def test_access_probability_reduces_ci_peak(self):
        m_base = self._ci_market()
        m_pa = self._ci_market(access_probability=0.70)
        base_peak = m_base.peak_sales_millions
        pa_peak = m_pa.peak_sales_millions
        assert pa_peak == pytest.approx(base_peak * 0.70, rel=1e-4)

    def test_prior_auth_burden_reduces_ci_peak(self):
        m_base = self._ci_market()
        m_pa = self._ci_market(prior_auth_burden=0.40)
        # factor = 1 - 0.40 × 0.5 = 0.80
        factor = 1.0 - 0.40 * 0.5
        assert m_pa.peak_sales_millions == pytest.approx(m_base.peak_sales_millions * factor, rel=1e-4)


# ---------------------------------------------------------------------------
# 13. High-price specialty drug — meaningful access impact
# ---------------------------------------------------------------------------

class TestHighPriceAssetAccessImpact:
    """
    Simulate a PCSK9i-like scenario:
      - Only 70% of payers grant formulary access
      - 50% prior-auth burden (persistent step-therapy failure requirement)
      - 6-month coverage delay (payer negotiations)
      - 40% year-1 step-edit suppression

    Effective peak penetration = 0.70 × (1 - 0.50 × 0.5) = 0.70 × 0.75 = 0.525
    (vs 1.0 without payer access)
    """
    TAM = 5_000.0   # $5B addressable market
    PEAK_PEN = 0.10  # 10% before access barriers

    def _pcsk9i_pa(self) -> PayerAccessModel:
        return PayerAccessModel(
            access_probability=0.70,
            prior_auth_burden=0.50,
            coverage_delay_months=6.0,
            step_edit_risk=0.40,
        )

    def test_year1_materially_suppressed(self):
        m_base = _tam_market(peak_pen=self.PEAK_PEN, tam=self.TAM)
        m_pa = _tam_market(peak_pen=self.PEAK_PEN, tam=self.TAM, payer_access=self._pcsk9i_pa())
        # Year 1: access=0.70, pa_burden=0.75, delay=0.5, step_edit=0.60
        # combined = 0.70 × 0.75 × 0.5 × 0.60 ≈ 0.1575
        combined_y1 = self._pcsk9i_pa().combined_multiplier(1)
        assert m_pa.revenue_in_year(1) == pytest.approx(m_base.revenue_in_year(1) * combined_y1, rel=1e-4)

    def test_year3_plus_reduced_by_permanent_factors_only(self):
        m_base = _tam_market(peak_pen=self.PEAK_PEN, tam=self.TAM)
        m_pa = _tam_market(peak_pen=self.PEAK_PEN, tam=self.TAM, payer_access=self._pcsk9i_pa())
        # Year 3+: delay resolved, step_edit resolved → only permanent factors remain
        perm = self._pcsk9i_pa().effective_penetration_multiplier()  # 0.70 × 0.75 = 0.525
        for yr in range(3, 13):
            assert m_pa.revenue_in_year(yr) == pytest.approx(
                m_base.revenue_in_year(yr) * perm, rel=1e-4
            )

    def test_access_impact_significant(self):
        """Verify the total NPV impact from payer barriers is material (>40% revenue loss)."""
        m_base = _tam_market(peak_pen=self.PEAK_PEN, tam=self.TAM)
        m_pa = _tam_market(peak_pen=self.PEAK_PEN, tam=self.TAM, payer_access=self._pcsk9i_pa())
        total_base = sum(m_base.revenue_in_year(y) for y in range(1, 13))
        total_pa = sum(m_pa.revenue_in_year(y) for y in range(1, 13))
        reduction = (total_base - total_pa) / total_base
        assert reduction > 0.40, f"Expected >40% revenue reduction, got {reduction:.1%}"

    def test_effective_peak_penetration_formula(self):
        """Verify effective_penetration_multiplier matches the Sprint C1 formula exactly."""
        pa = self._pcsk9i_pa()
        # Formula: peak_pen × access_probability × (1 - prior_auth_burden × 0.5)
        expected = 0.70 * (1.0 - 0.50 * 0.5)  # 0.525
        assert pa.effective_penetration_multiplier() == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 14. Patient-based mode
# ---------------------------------------------------------------------------

class TestPatientBasedMode:
    def test_access_probability_scales_patient_mode(self):
        m_base = _patient_market()
        m_pa = _patient_market(payer_access=PayerAccessModel(access_probability=0.65))
        for yr in range(1, 13):
            assert m_pa.revenue_in_year(yr) == pytest.approx(
                m_base.revenue_in_year(yr) * 0.65, rel=1e-6
            )

    def test_coverage_delay_patient_mode(self):
        m_base = _patient_market()
        m_pa = _patient_market(payer_access=PayerAccessModel(coverage_delay_months=6.0))
        assert m_pa.revenue_in_year(1) == pytest.approx(m_base.revenue_in_year(1) * 0.5, rel=1e-6)
        assert m_pa.revenue_in_year(2) == pytest.approx(m_base.revenue_in_year(2), rel=1e-6)


# ---------------------------------------------------------------------------
# 15. __init__ export
# ---------------------------------------------------------------------------

class TestInitExport:
    def test_payer_access_model_exported(self):
        from bve.models import PayerAccessModel as PAM  # noqa: F401
        assert PAM is not None

    def test_default_instance_from_init(self):
        from bve.models import PayerAccessModel as PAM
        pa = PAM()
        assert pa.access_probability == pytest.approx(1.0)
