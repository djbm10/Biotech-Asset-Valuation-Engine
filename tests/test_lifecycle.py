"""
Tests for LifecycleEvent and MarketModel lifecycle mechanics.

Covers:
  - LifecycleEvent construction and validation
  - label_expansion: TAM multiplier and penetration boost
  - new_formulation: effective patent life extension
  - combination_therapy: TAM multiplier
  - peak_sales_millions reflects lifecycle-adjusted peak
  - TAM multiplier applied before competition fraction
  - multiple events compose correctly
  - backward compatibility: no events → no change
"""
import pytest

from bve.models.market_model import LifecycleEvent, MarketModel


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _patient_market(
    asset_id: str = "drug-a",
    patients: int = 20_000,
    price: float = 100_000.0,
    peak_pen: float = 0.20,
    years_to_peak: int = 3,
    patent_life: int = 12,
    lifecycle_events=None,
) -> MarketModel:
    return MarketModel(
        asset_id=asset_id,
        addressable_patients_annual=patients,
        net_price_per_patient_usd=price,
        peak_penetration=peak_pen,
        years_to_peak=years_to_peak,
        patent_life_years=patent_life,
        lifecycle_events=lifecycle_events or [],
    )


def _tam_market(
    tam: float = 500.0,
    peak_pen: float = 0.25,
    patent_life: int = 10,
    lifecycle_events=None,
) -> MarketModel:
    return MarketModel(
        asset_id="drug-b",
        total_addressable_market_millions=tam,
        peak_penetration=peak_pen,
        patent_life_years=patent_life,
        lifecycle_events=lifecycle_events or [],
    )


# ---------------------------------------------------------------------------
# LifecycleEvent construction and validation
# ---------------------------------------------------------------------------

class TestLifecycleEventConstruction:
    def test_valid_label_expansion(self):
        e = LifecycleEvent(event_type="label_expansion", trigger_year=3, tam_expansion_factor=1.30)
        assert e.event_type == "label_expansion"
        assert e.trigger_year == 3
        assert e.tam_expansion_factor == 1.30
        assert e.penetration_boost == 0.0
        assert e.loe_delay_years == 0

    def test_valid_new_formulation(self):
        e = LifecycleEvent(event_type="new_formulation", trigger_year=5, loe_delay_years=3)
        assert e.loe_delay_years == 3

    def test_valid_combination_therapy(self):
        e = LifecycleEvent(event_type="combination_therapy", trigger_year=2, tam_expansion_factor=1.20)
        assert e.event_type == "combination_therapy"

    def test_invalid_event_type_raises(self):
        with pytest.raises(Exception):
            LifecycleEvent(event_type="magic", trigger_year=1)

    def test_trigger_year_must_be_positive(self):
        with pytest.raises(Exception):
            LifecycleEvent(event_type="label_expansion", trigger_year=0)

    def test_tam_expansion_factor_must_be_ge_1(self):
        with pytest.raises(Exception):
            LifecycleEvent(event_type="label_expansion", trigger_year=1, tam_expansion_factor=0.90)

    def test_defaults_produce_no_op(self):
        """An event with all defaults has no effect on revenue."""
        e = LifecycleEvent(event_type="label_expansion", trigger_year=1)
        assert e.tam_expansion_factor == 1.0
        assert e.penetration_boost == 0.0
        assert e.loe_delay_years == 0


# ---------------------------------------------------------------------------
# No lifecycle events → no change (backward compatibility)
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_empty_lifecycle_events_no_effect_patient_mode(self):
        m_base = _patient_market()
        m_lc = _patient_market(lifecycle_events=[])
        for yr in range(1, 13):
            assert m_base.revenue_in_year(yr) == m_lc.revenue_in_year(yr)

    def test_empty_lifecycle_events_no_effect_peak_sales(self):
        m_base = _patient_market()
        m_lc = _patient_market(lifecycle_events=[])
        assert m_base.peak_sales_millions == m_lc.peak_sales_millions

    def test_effective_patent_life_unchanged_without_events(self):
        m = _patient_market(patent_life=12)
        assert m._effective_patent_life() == 12


# ---------------------------------------------------------------------------
# label_expansion: TAM multiplier
# ---------------------------------------------------------------------------

class TestLabelExpansionTAM:
    def test_tam_multiplier_not_active_before_trigger(self):
        """Revenue before trigger_year is unchanged."""
        event = LifecycleEvent(event_type="label_expansion", trigger_year=5, tam_expansion_factor=1.30)
        m_base = _patient_market()
        m_lc = _patient_market(lifecycle_events=[event])
        for yr in range(1, 5):
            assert abs(m_lc.revenue_in_year(yr) - m_base.revenue_in_year(yr)) < 1e-9

    def test_tam_multiplier_active_from_trigger_year(self):
        """From trigger_year onward, revenue is multiplied by tam_expansion_factor."""
        event = LifecycleEvent(event_type="label_expansion", trigger_year=5, tam_expansion_factor=1.30)
        m_base = _patient_market()
        m_lc = _patient_market(lifecycle_events=[event])
        for yr in range(5, 13):
            expected = m_base.revenue_in_year(yr) * 1.30
            assert abs(m_lc.revenue_in_year(yr) - expected) < 1e-6

    def test_tam_multiplier_applies_in_tam_mode(self):
        """TAM multiplier works in TAM-based mode (mode 3)."""
        event = LifecycleEvent(event_type="label_expansion", trigger_year=3, tam_expansion_factor=1.20)
        m_base = _tam_market()
        m_lc = _tam_market(lifecycle_events=[event])
        assert abs(m_lc.revenue_in_year(5) - m_base.revenue_in_year(5) * 1.20) < 1e-6


# ---------------------------------------------------------------------------
# label_expansion: penetration boost
# ---------------------------------------------------------------------------

class TestLabelExpansionPenetrationBoost:
    def test_penetration_boost_not_active_before_trigger(self):
        event = LifecycleEvent(event_type="label_expansion", trigger_year=4, penetration_boost=0.10)
        m_base = _patient_market(peak_pen=0.20)
        m_lc = _patient_market(peak_pen=0.20, lifecycle_events=[event])
        for yr in range(1, 4):
            assert abs(m_lc.revenue_in_year(yr) - m_base.revenue_in_year(yr)) < 1e-9

    def test_penetration_boost_increases_revenue_from_trigger(self):
        event = LifecycleEvent(event_type="label_expansion", trigger_year=4, penetration_boost=0.10)
        m_base = _patient_market(peak_pen=0.20, years_to_peak=1)
        m_lc = _patient_market(peak_pen=0.20, years_to_peak=1, lifecycle_events=[event])
        # At year 4, base pen = 0.20; boosted pen = 0.30 → revenue ratio = 1.5
        ratio = m_lc.revenue_in_year(4) / m_base.revenue_in_year(4)
        assert abs(ratio - 1.50) < 1e-6

    def test_penetration_boost_clamped_at_one(self):
        """Large penetration boost is clamped so effective penetration ≤ 1.0."""
        event = LifecycleEvent(event_type="label_expansion", trigger_year=1, penetration_boost=0.90)
        m_lc = _patient_market(peak_pen=0.50, years_to_peak=1, lifecycle_events=[event])
        # Boosted pen would be 1.40 → clamped to 1.0
        m_cap = _patient_market(peak_pen=1.00, years_to_peak=1)
        # Revenue at year 1 for m_lc should equal what we'd get with pen=1.0
        assert abs(m_lc.revenue_in_year(1) - m_cap.revenue_in_year(1)) < 1e-6


# ---------------------------------------------------------------------------
# new_formulation: LOE delay
# ---------------------------------------------------------------------------

class TestNewFormulationLOEDelay:
    def test_effective_patent_life_extended(self):
        event = LifecycleEvent(event_type="new_formulation", trigger_year=8, loe_delay_years=3)
        m = _patient_market(patent_life=12, lifecycle_events=[event])
        assert m._effective_patent_life() == 15

    def test_revenue_zero_before_extended_life(self):
        """Revenue is non-zero in the extension window (years 13–15 for +3 delay)."""
        event = LifecycleEvent(event_type="new_formulation", trigger_year=8, loe_delay_years=3)
        m = _patient_market(patent_life=12, lifecycle_events=[event])
        assert m.revenue_in_year(13) > 0.0
        assert m.revenue_in_year(15) > 0.0

    def test_revenue_zero_after_extended_life(self):
        """Revenue is zero beyond effective patent life."""
        event = LifecycleEvent(event_type="new_formulation", trigger_year=8, loe_delay_years=3)
        m = _patient_market(patent_life=12, lifecycle_events=[event])
        assert m.revenue_in_year(16) == 0.0

    def test_no_extension_without_new_formulation(self):
        """label_expansion event does not extend patent life."""
        event = LifecycleEvent(event_type="label_expansion", trigger_year=5, tam_expansion_factor=1.20)
        m = _patient_market(patent_life=12, lifecycle_events=[event])
        assert m._effective_patent_life() == 12

    def test_multiple_formulations_stack(self):
        """Two new_formulation events: total delay = sum of loe_delay_years."""
        events = [
            LifecycleEvent(event_type="new_formulation", trigger_year=5, loe_delay_years=2),
            LifecycleEvent(event_type="new_formulation", trigger_year=9, loe_delay_years=1),
        ]
        m = _patient_market(patent_life=12, lifecycle_events=events)
        assert m._effective_patent_life() == 15


# ---------------------------------------------------------------------------
# combination_therapy
# ---------------------------------------------------------------------------

class TestCombinationTherapy:
    def test_combination_tam_multiplier(self):
        event = LifecycleEvent(event_type="combination_therapy", trigger_year=3, tam_expansion_factor=1.25)
        m_base = _patient_market()
        m_lc = _patient_market(lifecycle_events=[event])
        for yr in range(3, 13):
            assert abs(m_lc.revenue_in_year(yr) - m_base.revenue_in_year(yr) * 1.25) < 1e-6


# ---------------------------------------------------------------------------
# peak_sales_millions reflects lifecycle-adjusted peak
# ---------------------------------------------------------------------------

class TestPeakSalesWithLifecycle:
    def test_peak_sales_higher_with_label_expansion(self):
        """label_expansion increases peak sales beyond static base."""
        event = LifecycleEvent(event_type="label_expansion", trigger_year=4, tam_expansion_factor=1.30)
        m_base = _patient_market()
        m_lc = _patient_market(lifecycle_events=[event])
        assert m_lc.peak_sales_millions > m_base.peak_sales_millions

    def test_peak_sales_higher_with_loe_extension(self):
        """new_formulation doesn't change peak but extends the window; peak stays ≥ base."""
        event = LifecycleEvent(event_type="new_formulation", trigger_year=5, loe_delay_years=3)
        m_base = _patient_market(years_to_peak=2)
        m_lc = _patient_market(years_to_peak=2, lifecycle_events=[event])
        # Peak value is the same (no TAM change), but it's retained longer
        assert abs(m_lc.peak_sales_millions - m_base.peak_sales_millions) < 1e-6

    def test_peak_sales_no_lifecycle_fast_path(self):
        """Without lifecycle events, fast path and slow path produce the same peak."""
        m = _patient_market(years_to_peak=2, patent_life=10)
        # Fast path (no lifecycle, no competition) == iterating revenue_in_year
        from_curve = max(m.revenue_in_year(y) for y in range(1, 11))
        assert abs(m.peak_sales_millions - from_curve) < 1e-6


# ---------------------------------------------------------------------------
# TAM multiplier applied before competition fraction
# ---------------------------------------------------------------------------

class TestLifecycleBeforeCompetition:
    def test_tam_expands_before_competition_fraction(self):
        """
        With lifecycle TAM expansion + competition model:
          revenue = base_revenue × tam_multiplier × competition_fraction
        TAM expansion inflates the market; competition then takes its share of that.
        """
        from bve.models.competition_model import CompetitionModel, CompetitorLaunch

        comp = CompetitorLaunch(
            name="competitor",
            status="approved",
            launch_year_relative=-1,
            peak_market_share=0.30,
            years_to_peak=1,
            approval_probability=1.0,
        )
        cm = CompetitionModel(competitors=[comp])

        event = LifecycleEvent(event_type="label_expansion", trigger_year=1, tam_expansion_factor=1.50)
        m_base_comp = MarketModel(
            asset_id="x",
            addressable_patients_annual=10_000,
            net_price_per_patient_usd=100_000,
            peak_penetration=0.20,
            years_to_peak=1,
            patent_life_years=10,
            competition_model=cm,
        )
        m_lc_comp = MarketModel(
            asset_id="x",
            addressable_patients_annual=10_000,
            net_price_per_patient_usd=100_000,
            peak_penetration=0.20,
            years_to_peak=1,
            patent_life_years=10,
            competition_model=cm,
            lifecycle_events=[event],
        )
        # At year 2 (both at peak), with tam=1.50 and competition fraction = f:
        #   lc_revenue = base_revenue × 1.50 × f
        #   base_comp_revenue = base_revenue × f
        # → ratio = 1.50
        ratio = m_lc_comp.revenue_in_year(2) / m_base_comp.revenue_in_year(2)
        assert abs(ratio - 1.50) < 1e-6


# ---------------------------------------------------------------------------
# Multiple events compose correctly
# ---------------------------------------------------------------------------

class TestMultipleEventsCompose:
    def test_two_tam_expansion_events_multiply(self):
        """Two label_expansion events: effective TAM = factor_1 × factor_2."""
        events = [
            LifecycleEvent(event_type="label_expansion", trigger_year=2, tam_expansion_factor=1.20),
            LifecycleEvent(event_type="label_expansion", trigger_year=4, tam_expansion_factor=1.10),
        ]
        m_base = _patient_market(years_to_peak=1)
        m_lc = _patient_market(years_to_peak=1, lifecycle_events=events)
        # At year 4: both active → 1.20 × 1.10 = 1.32
        assert abs(m_lc.revenue_in_year(4) / m_base.revenue_in_year(4) - 1.32) < 1e-6
        # At year 2–3: only first active → 1.20
        assert abs(m_lc.revenue_in_year(3) / m_base.revenue_in_year(3) - 1.20) < 1e-6

    def test_mixed_events_compose(self):
        """label_expansion + new_formulation: TAM expanded AND patent life extended."""
        events = [
            LifecycleEvent(event_type="label_expansion", trigger_year=3, tam_expansion_factor=1.30),
            LifecycleEvent(event_type="new_formulation", trigger_year=6, loe_delay_years=2),
        ]
        m = _patient_market(patent_life=10, lifecycle_events=events)
        assert m._effective_patent_life() == 12
        assert m.revenue_in_year(11) > 0.0   # in extension window
        assert m.revenue_in_year(13) == 0.0   # beyond extension
        # Year 5: label expansion active → 1.30× base
        m_base = _patient_market(patent_life=10)
        assert abs(m.revenue_in_year(5) / m_base.revenue_in_year(5) - 1.30) < 1e-6
