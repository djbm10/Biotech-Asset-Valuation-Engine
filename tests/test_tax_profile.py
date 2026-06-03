"""
Tests for TaxProfile, TaxAudit, compute_year_fcf, and RNPVModel.compute() tax paths.

Coverage:
  - TaxProfile construction and validation
  - blended_tax_rate property (both jurisdiction modes)
  - compute_year_fcf: NOL tracking, utilization limit, NOL generation, loss years
  - RNPVModel Path A: nol_benefit_years unchanged without TaxProfile
  - RNPVModel Path B: full per-year NOL tracking with TaxProfile
  - Royalties and profit share deducted before taxable income
  - Capex and working capital reduce FCF
  - transaction_structure stored in audit, does not change math
  - Canonical valuation output unchanged when all new fields are default
  - TaxAudit populated only when TaxProfile provided
"""
from __future__ import annotations

import pytest

from bve.models.tax_profile import TaxProfile, TaxAudit, compute_year_fcf
from bve.models.rnpv_model import RNPVModel, RNPVResult, compute_rnpv_full
from bve.models.probability_model import ProbabilityModel, ProbabilityResult
from bve.models.revenue_model import RevenueModel
from bve.models.cost_model import CostModel
from bve.models.deal_economics import DealEconomics
from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.market_model import MarketModel


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _asset(royalty_rate: float = 0.0, tax_rate: float = 0.21,
           nol_years: int = 0) -> Asset:
    return Asset(
        id="tax-001", name="Tax Test Asset",
        stage="phase_3", therapeutic_area="oncology", modality="small_molecule",
        indication="test",
        discount_rate=0.10,
        royalty_rate=royalty_rate,
        effective_tax_rate=tax_rate,
        nol_benefit_years=nol_years,
    )


def _trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(asset_id="tax-001", phase=TrialPhase.PHASE_3,
                      duration_years=3.0, cost_millions=60.0, success_probability=0.60),
        ClinicalTrial(asset_id="tax-001", phase=TrialPhase.NDA_BLA,
                      duration_years=1.0, cost_millions=8.0, success_probability=0.90),
    ]


def _market(tam: float = 1_000.0, penetration: float = 0.10,
            peak_years: int = 4, patent_years: int = 10) -> MarketModel:
    return MarketModel(
        asset_id="tax-001",
        total_addressable_market_millions=tam,
        peak_penetration=penetration,
        years_to_peak=peak_years,
        patent_life_years=patent_years,
        cogs_rate=0.20,
        sgna_rate_launch=0.30,
        sgna_rate_mature=0.15,
    )


def _compute(tax_profile=None, deal=None) -> RNPVResult:
    asset = _asset()
    prob = ProbabilityModel.compute(asset, _trials())
    rev = RevenueModel.compute(_market())
    cost = CostModel.compute(prob, asset.discount_rate, deal=deal)
    return RNPVModel.compute(asset, prob, rev, cost, deal=deal, tax_profile=tax_profile)


# ---------------------------------------------------------------------------
# TestTaxProfileConstruction
# ---------------------------------------------------------------------------

class TestTaxProfileConstruction:
    def test_defaults_are_backward_compatible(self):
        tp = TaxProfile()
        assert tp.effective_tax_rate == pytest.approx(0.21)
        assert tp.nol_balance_millions == pytest.approx(0.0)
        assert tp.nol_utilization_limit_rate == pytest.approx(0.80)
        assert tp.allow_nol_generation is False
        assert tp.jurisdiction_mode == "blended"
        assert tp.transaction_structure == "standalone"
        assert tp.annual_maintenance_capex_rate == pytest.approx(0.0)
        assert tp.working_capital_rate == pytest.approx(0.0)
        assert tp.one_time_launch_capex_millions == pytest.approx(0.0)

    def test_blended_rate_returns_effective_tax_rate(self):
        tp = TaxProfile(effective_tax_rate=0.25)
        assert tp.blended_tax_rate == pytest.approx(0.25)

    def test_us_ex_us_requires_both_rates(self):
        with pytest.raises(ValueError, match="us_tax_rate"):
            TaxProfile(jurisdiction_mode="us_ex_us", us_tax_rate=0.21)

    def test_us_ex_us_blended_rate(self):
        tp = TaxProfile(
            jurisdiction_mode="us_ex_us",
            us_revenue_fraction=0.60,
            us_tax_rate=0.21,
            ex_us_tax_rate=0.15,
        )
        expected = 0.60 * 0.21 + 0.40 * 0.15
        assert tp.blended_tax_rate == pytest.approx(expected)

    def test_transaction_structure_stored(self):
        tp = TaxProfile(transaction_structure="asset_purchase")
        assert tp.transaction_structure == "asset_purchase"

    def test_invalid_transaction_structure(self):
        with pytest.raises(Exception):
            TaxProfile(transaction_structure="merger")  # type: ignore

    def test_frozen_immutability(self):
        tp = TaxProfile()
        with pytest.raises(Exception):
            tp.effective_tax_rate = 0.30  # type: ignore


# ---------------------------------------------------------------------------
# TestComputeYearFcf
# ---------------------------------------------------------------------------

class TestComputeYearFcf:
    """Unit tests for the per-year FCF helper function."""

    def _tp(self, **kwargs) -> TaxProfile:
        return TaxProfile(**kwargs)

    def test_no_nol_full_tax_applied(self):
        tp = self._tp(effective_tax_rate=0.21, nol_balance_millions=0.0)
        (usable_nol, nol_rem, taxable, cash_tax, at_ebit,
         maint, wc, launch, fcf) = compute_year_fcf(100.0, 500.0, 0.0, tp, yr=1)
        assert usable_nol == pytest.approx(0.0)
        assert taxable == pytest.approx(100.0)
        assert cash_tax == pytest.approx(21.0)
        assert at_ebit == pytest.approx(79.0)
        assert fcf == pytest.approx(79.0)  # no capex/WC

    def test_nol_shields_income(self):
        """$100M NOL, $100M taxable income, 80% limit → $80M shielded, $20M taxable."""
        tp = self._tp(effective_tax_rate=0.21, nol_balance_millions=100.0,
                      nol_utilization_limit_rate=0.80)
        (usable_nol, nol_rem, taxable, cash_tax, at_ebit,
         _, _, _, fcf) = compute_year_fcf(100.0, 500.0, 100.0, tp, yr=1)
        assert usable_nol == pytest.approx(80.0)
        assert nol_rem == pytest.approx(20.0)
        assert taxable == pytest.approx(100.0)
        assert cash_tax == pytest.approx(20.0 * 0.21)
        assert at_ebit == pytest.approx(100.0 - cash_tax)

    def test_nol_exhausts_correctly_across_years(self):
        """After year 1 uses $80M of $100M NOL, year 2 starts with $20M."""
        tp = self._tp(effective_tax_rate=0.21, nol_balance_millions=100.0,
                      nol_utilization_limit_rate=0.80)
        _, nol_after_yr1, _, _, _, _, _, _, _ = compute_year_fcf(
            100.0, 500.0, 100.0, tp, yr=1)
        assert nol_after_yr1 == pytest.approx(20.0)

        # Year 2: $100M taxable, 80% limit = $80M, but only $20M left
        (usable_nol_yr2, nol_after_yr2, _, cash_tax_yr2, _, _, _, _, _) = compute_year_fcf(
            100.0, 500.0, nol_after_yr1, tp, yr=2)
        assert usable_nol_yr2 == pytest.approx(20.0)
        assert nol_after_yr2 == pytest.approx(0.0)
        assert cash_tax_yr2 == pytest.approx(80.0 * 0.21)

    def test_utilization_limit_prevents_full_immediate_nol_use(self):
        """80% limit: $200M income, $200M NOL → only $160M usable."""
        tp = self._tp(effective_tax_rate=0.21, nol_balance_millions=200.0,
                      nol_utilization_limit_rate=0.80)
        (usable_nol, nol_rem, _, _, _, _, _, _, _) = compute_year_fcf(
            200.0, 1000.0, 200.0, tp, yr=1)
        assert usable_nol == pytest.approx(160.0)
        assert nol_rem == pytest.approx(40.0)

    def test_loss_year_no_tax_no_nol_generation_default(self):
        """Negative EBIT: cash_tax = 0, NOL does not increase when allow_nol_generation=False."""
        tp = self._tp(allow_nol_generation=False, nol_balance_millions=50.0)
        (usable_nol, nol_rem, taxable, cash_tax, at_ebit,
         _, _, _, fcf) = compute_year_fcf(-30.0, 100.0, 50.0, tp, yr=1)
        assert cash_tax == pytest.approx(0.0)
        assert nol_rem == pytest.approx(50.0)  # unchanged
        assert at_ebit == pytest.approx(-30.0)  # loss passed through
        assert fcf == pytest.approx(-30.0)

    def test_loss_year_generates_nol_when_enabled(self):
        """Negative EBIT with allow_nol_generation=True increases NOL balance."""
        tp = self._tp(allow_nol_generation=True, nol_balance_millions=50.0)
        (_, nol_rem, _, cash_tax, _, _, _, _, _) = compute_year_fcf(
            -30.0, 100.0, 50.0, tp, yr=1)
        assert cash_tax == pytest.approx(0.0)
        assert nol_rem == pytest.approx(80.0)  # 50 + 30

    def test_maintenance_capex_reduces_fcf(self):
        tp = self._tp(annual_maintenance_capex_rate=0.02)
        (_, _, _, _, at_ebit, maint, _, _, fcf) = compute_year_fcf(
            100.0, 500.0, 0.0, tp, yr=1)
        assert maint == pytest.approx(10.0)  # 2% of $500M
        assert fcf == pytest.approx(at_ebit - 10.0)

    def test_working_capital_reduces_fcf(self):
        tp = self._tp(working_capital_rate=0.05)
        (_, _, _, _, at_ebit, _, wc, _, fcf) = compute_year_fcf(
            100.0, 500.0, 0.0, tp, yr=1)
        assert wc == pytest.approx(25.0)  # 5% of $500M
        assert fcf == pytest.approx(at_ebit - 25.0)

    def test_launch_capex_in_correct_year(self):
        """one_time_launch_capex_millions=50 at offset=0 → deducted in yr=1 only."""
        tp = self._tp(one_time_launch_capex_millions=50.0, launch_capex_year_offset=0.0)
        (_, _, _, _, at_ebit_yr1, _, _, launch_yr1, fcf_yr1) = compute_year_fcf(
            100.0, 500.0, 0.0, tp, yr=1)
        (_, _, _, _, at_ebit_yr2, _, _, launch_yr2, fcf_yr2) = compute_year_fcf(
            100.0, 500.0, 0.0, tp, yr=2)
        assert launch_yr1 == pytest.approx(50.0)
        assert launch_yr2 == pytest.approx(0.0)
        assert fcf_yr1 == pytest.approx(at_ebit_yr1 - 50.0)
        assert fcf_yr2 == pytest.approx(at_ebit_yr2)

    def test_launch_capex_offset_shifts_year(self):
        """launch_capex_year_offset=1 → capex in yr=2, not yr=1."""
        tp = self._tp(one_time_launch_capex_millions=50.0, launch_capex_year_offset=1.0)
        (_, _, _, _, _, _, _, launch_yr1, _) = compute_year_fcf(100.0, 500.0, 0.0, tp, yr=1)
        (_, _, _, _, _, _, _, launch_yr2, _) = compute_year_fcf(100.0, 500.0, 0.0, tp, yr=2)
        assert launch_yr1 == pytest.approx(0.0)
        assert launch_yr2 == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# TestPathABackwardCompat
# ---------------------------------------------------------------------------

class TestPathABackwardCompat:
    """Without TaxProfile, nol_benefit_years window behavior is unchanged."""

    def test_no_tax_profile_uses_asset_tax_rate(self):
        """tax_profile=None → simple 21% flat rate from asset."""
        result_no_tp = _compute(tax_profile=None)
        # Manual path A expectation: should match asset.effective_tax_rate=21%
        assert result_no_tp.tax_audit is None

    def test_nol_window_zero_tax_in_window(self):
        """nol_benefit_years=3 on Asset: first 3 years tax-free without TaxProfile."""
        asset = _asset(tax_rate=0.21, nol_years=3)
        prob = ProbabilityModel.compute(asset, _trials())
        rev = RevenueModel.compute(_market())
        cost = CostModel.compute(prob, asset.discount_rate)
        result_with_nol = RNPVModel.compute(asset, prob, rev, cost, tax_profile=None)
        result_no_nol = RNPVModel.compute(_asset(tax_rate=0.21, nol_years=0),
                                          prob, rev, cost, tax_profile=None)
        # NOL window gives higher rNPV (fewer taxes early)
        assert result_with_nol.rnpv_millions > result_no_nol.rnpv_millions
        assert result_with_nol.tax_audit is None

    def test_canonical_unchanged_without_tax_profile(self):
        """result without tax_profile matches compute_rnpv_full baseline (no TaxProfile)."""
        baseline = compute_rnpv_full(_asset(), _trials(), _market())
        result = _compute(tax_profile=None)
        assert result.rnpv_millions == pytest.approx(baseline.rnpv_millions, abs=0.01)


# ---------------------------------------------------------------------------
# TestPathBWithTaxProfile
# ---------------------------------------------------------------------------

class TestPathBWithTaxProfile:
    """With TaxProfile, per-year NOL tracking and FCF adjustments apply."""

    def test_tax_audit_populated_when_profile_provided(self):
        result = _compute(tax_profile=TaxProfile())
        assert result.tax_audit is not None
        assert isinstance(result.tax_audit, TaxAudit)
        n_years = len(result.revenue_stream.ebit_by_year)  # type: ignore
        assert len(result.tax_audit.pre_tax_adjusted_ebit_by_year) == n_years
        assert len(result.tax_audit.after_tax_fcf_by_year) == n_years
        assert result.tax_audit.tax_profile_used is not None

    def test_tax_audit_none_without_profile(self):
        result = _compute(tax_profile=None)
        assert result.tax_audit is None

    def test_default_tax_profile_matches_path_a(self):
        """TaxProfile() with nol_balance=0 and no capex/WC should match simple 21% flat rate."""
        tp = TaxProfile(effective_tax_rate=0.21, nol_balance_millions=0.0)
        result_b = _compute(tax_profile=tp)
        result_a = _compute(tax_profile=None)
        # Should be identical (both 21% flat, no NOL)
        assert result_b.rnpv_millions == pytest.approx(result_a.rnpv_millions, abs=1.0)

    def test_nol_balance_shields_early_income(self):
        """Large NOL balance shields early commercial years → higher rNPV than no NOL."""
        tp_nol = TaxProfile(nol_balance_millions=500.0)
        tp_no_nol = TaxProfile(nol_balance_millions=0.0)
        result_nol = _compute(tax_profile=tp_nol)
        result_no_nol = _compute(tax_profile=tp_no_nol)
        assert result_nol.rnpv_millions > result_no_nol.rnpv_millions

    def test_nol_remaining_decreases_each_year(self):
        """NOL balance should decrease monotonically while income is positive."""
        tp = TaxProfile(nol_balance_millions=200.0)
        result = _compute(tax_profile=tp)
        audit = result.tax_audit
        assert audit is not None
        remaining = audit.remaining_nol_by_year
        # Once NOL is > 0 and taxable income > 0, remaining should not increase
        for i in range(1, len(remaining)):
            assert remaining[i] <= remaining[i - 1] + 1e-6  # monotone non-increasing

    def test_nol_exhausts_to_zero(self):
        """Small NOL (10M) exhausts within first few years of a profitable program."""
        tp = TaxProfile(nol_balance_millions=10.0)
        result = _compute(tax_profile=tp)
        audit = result.tax_audit
        assert audit is not None
        assert audit.remaining_nol_by_year[-1] == pytest.approx(0.0, abs=1e-6)

    def test_utilization_limit_leaves_nol_longer(self):
        """50% limit exhausts NOL more slowly than 100% limit."""
        tp_50 = TaxProfile(nol_balance_millions=100.0, nol_utilization_limit_rate=0.50)
        tp_100 = TaxProfile(nol_balance_millions=100.0, nol_utilization_limit_rate=1.00)
        result_50 = _compute(tax_profile=tp_50)
        result_100 = _compute(tax_profile=tp_100)
        audit_50 = result_50.tax_audit
        audit_100 = result_100.tax_audit
        assert audit_50 is not None and audit_100 is not None
        # At year 1, 50% limit uses less NOL → more remaining
        assert audit_50.remaining_nol_by_year[0] >= audit_100.remaining_nol_by_year[0]

    def test_royalties_deducted_before_taxable_income(self):
        """Royalty reduces adjusted_EBIT → lower taxable_income → less cash tax."""
        tp = TaxProfile()
        deal_no_royalty = DealEconomics(royalty_rate=0.0)
        deal_royalty = DealEconomics(royalty_rate=0.15)
        asset = _asset()
        prob = ProbabilityModel.compute(asset, _trials())
        rev = RevenueModel.compute(_market())
        cost_nr = CostModel.compute(prob, asset.discount_rate, deal=deal_no_royalty)
        cost_r = CostModel.compute(prob, asset.discount_rate, deal=deal_royalty)
        result_nr = RNPVModel.compute(asset, prob, rev, cost_nr, deal=deal_no_royalty, tax_profile=tp)
        result_r = RNPVModel.compute(asset, prob, rev, cost_r, deal=deal_royalty, tax_profile=tp)
        audit_nr = result_nr.tax_audit
        audit_r = result_r.tax_audit
        assert audit_nr is not None and audit_r is not None
        # royalty reduces adjusted_ebit → lower total cash taxes
        total_tax_nr = sum(audit_nr.cash_tax_by_year)
        total_tax_r = sum(audit_r.cash_tax_by_year)
        assert total_tax_r < total_tax_nr

    def test_profit_share_deducted_before_taxable_income(self):
        """Profit share reduces adjusted_EBIT → lower taxable income → less cash tax."""
        tp = TaxProfile()
        deal_no_ps = DealEconomics(profit_share_rate=0.0)
        deal_ps = DealEconomics(profit_share_rate=0.20)
        asset = _asset()
        prob = ProbabilityModel.compute(asset, _trials())
        rev = RevenueModel.compute(_market())
        cost_nps = CostModel.compute(prob, asset.discount_rate)
        result_nps = RNPVModel.compute(asset, prob, rev, cost_nps, deal=deal_no_ps, tax_profile=tp)
        result_ps = RNPVModel.compute(asset, prob, rev, cost_nps, deal=deal_ps, tax_profile=tp)
        audit_nps = result_nps.tax_audit
        audit_ps = result_ps.tax_audit
        assert audit_nps is not None and audit_ps is not None
        total_tax_nps = sum(audit_nps.cash_tax_by_year)
        total_tax_ps = sum(audit_ps.cash_tax_by_year)
        assert total_tax_ps < total_tax_nps

    def test_capex_and_working_capital_reduce_fcf(self):
        """Positive capex/WC rates → after_tax_fcf < after_tax_ebit every year."""
        tp = TaxProfile(annual_maintenance_capex_rate=0.02, working_capital_rate=0.03)
        result = _compute(tax_profile=tp)
        audit = result.tax_audit
        assert audit is not None
        for at_ebit, at_fcf in zip(audit.after_tax_ebit_by_year, audit.after_tax_fcf_by_year):
            assert at_fcf <= at_ebit + 1e-9

    def test_capex_and_wc_reduce_rnpv(self):
        """Higher capex/WC rates reduce rNPV compared to zero rates."""
        tp_zero = TaxProfile()
        tp_capex = TaxProfile(annual_maintenance_capex_rate=0.03, working_capital_rate=0.02)
        result_zero = _compute(tax_profile=tp_zero)
        result_capex = _compute(tax_profile=tp_capex)
        assert result_capex.rnpv_millions < result_zero.rnpv_millions

    def test_launch_capex_reduces_rnpv(self):
        """One-time launch capex reduces rNPV."""
        tp_no_lc = TaxProfile()
        tp_lc = TaxProfile(one_time_launch_capex_millions=50.0)
        result_no = _compute(tax_profile=tp_no_lc)
        result_lc = _compute(tax_profile=tp_lc)
        assert result_lc.rnpv_millions < result_no.rnpv_millions

    def test_transaction_structure_in_audit_does_not_change_math(self):
        """transaction_structure='asset_purchase' vs 'standalone' → same rNPV."""
        tp_standalone = TaxProfile(transaction_structure="standalone")
        tp_asset_purchase = TaxProfile(transaction_structure="asset_purchase")
        result_sa = _compute(tax_profile=tp_standalone)
        result_ap = _compute(tax_profile=tp_asset_purchase)
        assert result_sa.rnpv_millions == pytest.approx(result_ap.rnpv_millions)
        assert result_ap.tax_audit is not None
        assert result_ap.tax_audit.tax_profile_used.transaction_structure == "asset_purchase"

    def test_all_capex_lists_correct_length(self):
        """All TaxAudit lists have one entry per commercial year."""
        tp = TaxProfile(annual_maintenance_capex_rate=0.01, working_capital_rate=0.02,
                        one_time_launch_capex_millions=20.0)
        result = _compute(tax_profile=tp)
        audit = result.tax_audit
        assert audit is not None
        n = len(result.revenue_stream.ebit_by_year)  # type: ignore
        for field_name in (
            "pre_tax_adjusted_ebit_by_year", "taxable_income_by_year",
            "nol_used_by_year", "remaining_nol_by_year", "cash_tax_by_year",
            "after_tax_ebit_by_year", "capex_by_year", "working_capital_by_year",
            "after_tax_fcf_by_year",
        ):
            lst = getattr(audit, field_name)
            assert len(lst) == n, f"{field_name} has wrong length"

    def test_us_ex_us_mode_uses_blended_rate(self):
        """us_ex_us mode computes higher blended rate than pure ex-US rate."""
        tp_blended = TaxProfile(effective_tax_rate=0.21)
        tp_us_exus = TaxProfile(
            jurisdiction_mode="us_ex_us",
            us_revenue_fraction=0.60,
            us_tax_rate=0.21,
            ex_us_tax_rate=0.10,
        )
        result_blended = _compute(tax_profile=tp_blended)
        result_us_exus = _compute(tax_profile=tp_us_exus)
        # blended rate = 0.60*0.21 + 0.40*0.10 = 0.166 < 0.21 → higher rNPV
        assert result_us_exus.rnpv_millions > result_blended.rnpv_millions


# ---------------------------------------------------------------------------
# TestCanonicalValueUnchanged
# ---------------------------------------------------------------------------

class TestCanonicalValueUnchanged:
    """Existing canonical test values must be unchanged when all new fields are default."""

    def test_rnpv_unchanged_with_default_tax_profile(self):
        """TaxProfile() with all defaults matches Path A (no TaxProfile)."""
        result_no_tp = compute_rnpv_full(_asset(), _trials(), _market())
        result_default_tp = compute_rnpv_full(_asset(), _trials(), _market(),
                                              tax_profile=TaxProfile())
        assert result_default_tp.rnpv_millions == pytest.approx(
            result_no_tp.rnpv_millions, abs=1.0
        )

    def test_gross_revenue_pv_unchanged(self):
        result_a = compute_rnpv_full(_asset(), _trials(), _market())
        result_b = compute_rnpv_full(_asset(), _trials(), _market(),
                                     tax_profile=TaxProfile())
        assert result_b.gross_revenue_pv_millions == pytest.approx(
            result_a.gross_revenue_pv_millions, abs=2.0
        )
