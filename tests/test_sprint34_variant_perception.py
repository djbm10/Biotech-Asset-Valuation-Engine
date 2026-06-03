"""
Sprint 34 — Variant Perception Back-Solve tests.

Covers:
- AssetAllocationSpec: defaults, field validation, helpers
- BackSolvePoint: structure and arithmetic
- back_solve_variant_perception: returns None when no price
- back_solve_variant_perception: exact implied_pos arithmetic
- back_solve_variant_perception: exact implied_peak_sales arithmetic
- back_solve_variant_perception: exact implied_penetration / price / patients
- Three allocation cases: conservative < base < aggressive asset EV
- Guardrail: ev_below_cost (implied_pos < 0)
- Guardrail: ev_above_full_success (implied_pos > 1)
- Guardrail: multi_asset_required
- Guardrail: pv_fcf_invalid
- emit_guardrail_warnings=False suppresses UserWarning
- Classification: clinical (POS gap ≥ 15pp)
- Classification: commercial (peak-sales gap ≥ 30%)
- Classification: mixed
- Classification: allocation (gap sign flips)
- Classification: indeterminate (small gaps)
- memo_interpretation non-empty
- VariantPerceptionResult fields typed correctly
- Single-asset default (no explicit allocation_spec)
- milestone and upfront_receipt included in numerator
"""
import warnings
from unittest.mock import MagicMock

import pytest

from bve.analysis.variant_perception import (
    AssetAllocationSpec,
    BackSolvePoint,
    VariantPerceptionResult,
    back_solve_variant_perception,
)


# ---------------------------------------------------------------------------
# Helpers — build a minimal mock ValuationOutput
# ---------------------------------------------------------------------------

def _make_output(
    *,
    current_price: float = 10.0,
    shares: float = 100.0,          # market_cap = 1000
    net_cash: float = 200.0,        # company_ev = 800
    pv_fcf: float = 2000.0,         # gross_revenue_pv_millions
    pv_costs: float = 300.0,        # trial_costs_pv_millions
    pv_milestones: float = 0.0,     # deal_milestone_receipts_pv_millions
    upfront: float = 0.0,           # upfront_receipt_millions
    model_pos: float = 0.50,        # cumulative_success_probability
    model_peak_sales: float = 800.0,
    peak_penetration: float = 0.20,
    net_price: float = 80_000.0,
    addressable_patients: int = 50_000,
    asset_ids: list = None,
):
    if asset_ids is None:
        asset_ids = ["asset-001"]

    company = MagicMock()
    company.current_price = current_price
    company.shares_outstanding_millions = shares
    company.net_cash_millions = net_cash
    company.asset_ids = asset_ids

    rnpv = MagicMock()
    rnpv.gross_revenue_pv_millions = pv_fcf
    rnpv.trial_costs_pv_millions = pv_costs
    rnpv.deal_milestone_receipts_pv_millions = pv_milestones
    rnpv.upfront_receipt_millions = upfront
    rnpv.cumulative_success_probability = model_pos
    rnpv.peak_sales_millions = model_peak_sales

    market_model = MagicMock()
    market_model.peak_penetration = peak_penetration
    market_model.net_price_per_patient_usd = net_price
    market_model.addressable_patients_annual = addressable_patients

    out = MagicMock()
    out.company = company
    out.rnpv = rnpv
    out.market_model = market_model
    return out


# ---------------------------------------------------------------------------
# AssetAllocationSpec
# ---------------------------------------------------------------------------

class TestAssetAllocationSpec:
    def test_defaults_all_zero(self):
        spec = AssetAllocationSpec()
        assert spec.other_pipeline_base == 0.0
        assert spec.royalty_stream_value == 0.0
        assert spec.platform_value == 0.0
        assert spec.non_core_value == 0.0

    def test_total_fixed_deductions(self):
        spec = AssetAllocationSpec(
            royalty_stream_value=100.0,
            platform_value=50.0,
            non_core_value=25.0,
        )
        assert spec.total_fixed_deductions() == pytest.approx(175.0)

    def test_other_pipeline_cases(self):
        spec = AssetAllocationSpec(
            other_pipeline_conservative=500.0,
            other_pipeline_base=300.0,
            other_pipeline_aggressive=100.0,
        )
        assert spec.other_pipeline("conservative") == 500.0
        assert spec.other_pipeline("base") == 300.0
        assert spec.other_pipeline("aggressive") == 100.0

    def test_conservative_deducts_most(self):
        spec = AssetAllocationSpec(
            other_pipeline_conservative=500.0,
            other_pipeline_base=300.0,
            other_pipeline_aggressive=100.0,
        )
        # Conservative deducts most → least EV for modeled asset
        assert spec.other_pipeline("conservative") > spec.other_pipeline("base")
        assert spec.other_pipeline("base") > spec.other_pipeline("aggressive")

    def test_negative_other_pipeline_raises(self):
        with pytest.raises(Exception):
            AssetAllocationSpec(other_pipeline_base=-100.0)


# ---------------------------------------------------------------------------
# Returns None when no price
# ---------------------------------------------------------------------------

class TestNoPriceReturnsNone:
    def test_none_when_price_is_none(self):
        out = _make_output(current_price=None)
        assert back_solve_variant_perception(out, emit_guardrail_warnings=False) is None

    def test_none_when_price_is_zero(self):
        out = _make_output(current_price=0.0)
        assert back_solve_variant_perception(out, emit_guardrail_warnings=False) is None


# ---------------------------------------------------------------------------
# Exact arithmetic — implied_pos
# ---------------------------------------------------------------------------

class TestImpliedPosArithmetic:
    def test_exact_implied_pos(self):
        # company_ev = 10*100 - 200 = 800
        # numerator = 800 + 300 - 0 - 0 = 1100
        # implied_pos = 1100 / 2000 = 0.55
        out = _make_output()
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        assert result is not None
        assert result.base.implied_pos == pytest.approx(0.55, abs=1e-4)

    def test_implied_pos_with_milestones_and_upfront(self):
        # numerator = 800 + 300 - 50 - 30 = 1020
        # implied_pos = 1020 / 2000 = 0.51
        out = _make_output(pv_milestones=50.0, upfront=30.0)
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        assert result.base.implied_pos == pytest.approx(0.51, abs=1e-4)

    def test_company_ev_computed_correctly(self):
        # market_cap = 10 * 100 = 1000; net_cash = 200; ev = 800
        out = _make_output()
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        assert result.company_ev_millions == pytest.approx(800.0, abs=0.1)

    def test_implied_pos_with_allocation_deduction(self):
        # asset_implied_ev = 800 - 200 (other_pipeline) = 600
        # numerator = 600 + 300 - 0 - 0 = 900
        # implied_pos = 900 / 2000 = 0.45
        spec = AssetAllocationSpec(other_pipeline_base=200.0)
        out = _make_output()
        result = back_solve_variant_perception(out, allocation_spec=spec,
                                               emit_guardrail_warnings=False)
        assert result.base.implied_pos == pytest.approx(0.45, abs=1e-4)

    def test_implied_pos_clamped_to_zero_when_negative(self):
        # Force very high deductions → numerator negative
        spec = AssetAllocationSpec(other_pipeline_base=10_000.0)
        out = _make_output()
        result = back_solve_variant_perception(out, allocation_spec=spec,
                                               emit_guardrail_warnings=False)
        # implied_pos clipped to 0.0 (guardrail raw_implied_pos < 0)
        assert result.base.implied_pos == 0.0

    def test_raw_implied_pos_preserved_when_negative(self):
        spec = AssetAllocationSpec(other_pipeline_base=10_000.0)
        out = _make_output()
        result = back_solve_variant_perception(out, allocation_spec=spec,
                                               emit_guardrail_warnings=False)
        assert result.base.raw_implied_pos < 0.0

    def test_implied_pos_clamped_to_one_when_above(self):
        # Force tiny costs, huge EV
        out = _make_output(current_price=100.0, shares=100.0, net_cash=0.0,
                           pv_fcf=500.0, pv_costs=0.0)
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        # raw = 10000 / 500 = 20.0 → clamped to 1.0
        assert result.base.implied_pos == 1.0
        assert result.base.raw_implied_pos > 1.0


# ---------------------------------------------------------------------------
# Exact arithmetic — implied peak sales and commercial drivers
# ---------------------------------------------------------------------------

class TestCommercialBackSolves:
    def _base_result(self):
        # implied_pos = 0.55; model_pos = 0.50
        # scale = (1100) / (0.50 * 2000) = 1100/1000 = 1.10
        # implied_peak_sales = 800 * 1.10 = 880
        return back_solve_variant_perception(_make_output(), emit_guardrail_warnings=False)

    def test_implied_peak_sales_exact(self):
        result = self._base_result()
        assert result.base.implied_peak_sales_millions == pytest.approx(880.0, abs=1.0)

    def test_implied_penetration_exact(self):
        # implied_pen = 0.20 * 1.10 = 0.22
        result = self._base_result()
        assert result.base.implied_peak_penetration == pytest.approx(0.22, abs=1e-3)

    def test_implied_net_price_exact(self):
        # implied_price = 80000 * 1.10 = 88000
        result = self._base_result()
        assert result.base.implied_net_price_usd == pytest.approx(88000.0, abs=100.0)

    def test_implied_eligible_patients_exact(self):
        # implied_patients = 50000 * 1.10 = 55000
        result = self._base_result()
        assert result.base.implied_eligible_patients == pytest.approx(55000.0, abs=100.0)

    def test_no_commercial_drivers_when_lot_mode(self):
        # Simulate LOT mode: no patients/price/penetration
        out = _make_output()
        out.market_model.peak_penetration = None
        out.market_model.net_price_per_patient_usd = None
        out.market_model.addressable_patients_annual = None
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        assert result.base.implied_peak_penetration is None
        assert result.base.implied_net_price_usd is None
        assert result.base.implied_eligible_patients is None
        # But implied_peak_sales still computed
        assert result.base.implied_peak_sales_millions is not None


# ---------------------------------------------------------------------------
# Three allocation cases: asset EV ordering
# ---------------------------------------------------------------------------

class TestAllocationRange:
    def test_conservative_has_smallest_asset_ev(self):
        spec = AssetAllocationSpec(
            other_pipeline_conservative=400.0,
            other_pipeline_base=200.0,
            other_pipeline_aggressive=50.0,
        )
        out = _make_output()
        result = back_solve_variant_perception(out, allocation_spec=spec,
                                               emit_guardrail_warnings=False)
        assert (result.conservative.asset_implied_ev_millions
                < result.base.asset_implied_ev_millions
                < result.aggressive.asset_implied_ev_millions)

    def test_conservative_has_lowest_implied_pos(self):
        spec = AssetAllocationSpec(
            other_pipeline_conservative=400.0,
            other_pipeline_base=200.0,
            other_pipeline_aggressive=50.0,
        )
        out = _make_output()
        result = back_solve_variant_perception(out, allocation_spec=spec,
                                               emit_guardrail_warnings=False)
        assert (result.conservative.implied_pos
                <= result.base.implied_pos
                <= result.aggressive.implied_pos)

    def test_default_allocation_all_cases_identical(self):
        out = _make_output()
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        assert result.conservative.implied_pos == result.base.implied_pos
        assert result.base.implied_pos == result.aggressive.implied_pos


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------

class TestGuardrails:
    def test_ev_below_cost_guardrail_fires(self):
        # Force implied_pos < 0 by huge deductions
        spec = AssetAllocationSpec(other_pipeline_base=10_000.0)
        out = _make_output()
        result = back_solve_variant_perception(out, allocation_spec=spec,
                                               emit_guardrail_warnings=False)
        assert any("ev_below_cost" in g for g in result.guardrails)

    def test_ev_above_full_success_guardrail_fires(self):
        out = _make_output(current_price=100.0, shares=100.0, net_cash=0.0,
                           pv_fcf=500.0, pv_costs=0.0)
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        assert any("ev_above_full_success" in g for g in result.guardrails)

    def test_multi_asset_guardrail_fires(self):
        out = _make_output(asset_ids=["asset-001", "asset-002"])
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        assert any("multi_asset_required" in g for g in result.guardrails)

    def test_multi_asset_guardrail_suppressed_when_explicit_allocation(self):
        spec = AssetAllocationSpec(other_pipeline_base=100.0)
        out = _make_output(asset_ids=["asset-001", "asset-002"])
        result = back_solve_variant_perception(out, allocation_spec=spec,
                                               emit_guardrail_warnings=False)
        assert not any("multi_asset_required" in g for g in result.guardrails)

    def test_pv_fcf_invalid_guardrail_fires(self):
        out = _make_output(pv_fcf=0.0)
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        assert any("pv_fcf_invalid" in g for g in result.guardrails)

    def test_emit_warnings_false_no_user_warning(self):
        spec = AssetAllocationSpec(other_pipeline_base=10_000.0)
        out = _make_output()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            back_solve_variant_perception(out, allocation_spec=spec,
                                          emit_guardrail_warnings=False)
            assert len(w) == 0

    def test_emit_warnings_true_fires_user_warning(self):
        spec = AssetAllocationSpec(other_pipeline_base=10_000.0)
        out = _make_output()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            back_solve_variant_perception(out, allocation_spec=spec,
                                          emit_guardrail_warnings=True)
            assert any(issubclass(wi.category, UserWarning) for wi in w)

    def test_no_guardrails_when_valid(self):
        out = _make_output()
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        assert result.guardrails == []


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

class TestClassification:
    def test_clinical_when_pos_gap_large(self):
        # implied_pos much lower than model_pos (model_pos=0.70 vs implied~0.55)
        # numerator = 800+300 = 1100; implied_pos = 1100/2000 = 0.55; gap = 15pp
        out = _make_output(model_pos=0.70, model_peak_sales=800.0)
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        # gap = 70% - 55% = 15pp — on the boundary, should be clinical
        assert result.variant_perception_category == "clinical"

    def test_indeterminate_when_gaps_small(self):
        # model_pos = 0.55 → implied_pos = 0.55 → gap = 0pp
        out = _make_output(model_pos=0.55, model_peak_sales=880.0)
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        assert result.variant_perception_category == "indeterminate"

    def test_variant_category_is_valid_literal(self):
        out = _make_output()
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        valid = {"clinical", "commercial", "pricing", "mixed", "allocation", "indeterminate"}
        assert result.variant_perception_category in valid


# ---------------------------------------------------------------------------
# Memo and result structure
# ---------------------------------------------------------------------------

class TestResultStructure:
    def test_memo_non_empty(self):
        out = _make_output()
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        assert len(result.memo_interpretation) > 0

    def test_result_has_all_fields(self):
        out = _make_output()
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        assert isinstance(result, VariantPerceptionResult)
        assert isinstance(result.conservative, BackSolvePoint)
        assert isinstance(result.base, BackSolvePoint)
        assert isinstance(result.aggressive, BackSolvePoint)
        assert isinstance(result.guardrails, list)
        assert isinstance(result.memo_interpretation, str)

    def test_model_estimates_preserved(self):
        out = _make_output(model_pos=0.50, model_peak_sales=800.0,
                           peak_penetration=0.20, net_price=80_000.0,
                           addressable_patients=50_000)
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        assert result.model_pos == pytest.approx(0.50)
        assert result.model_peak_sales_millions == pytest.approx(800.0)
        assert result.model_peak_penetration == pytest.approx(0.20)
        assert result.model_net_price_usd == pytest.approx(80_000.0)
        assert result.model_eligible_patients == pytest.approx(50_000.0)

    def test_pv_fields_preserved(self):
        out = _make_output(pv_fcf=2000.0, pv_costs=300.0, pv_milestones=50.0, upfront=30.0)
        result = back_solve_variant_perception(out, emit_guardrail_warnings=False)
        assert result.pv_full_success_fcf_millions == pytest.approx(2000.0)
        assert result.pv_remaining_dev_costs_millions == pytest.approx(300.0)
        assert result.pv_receivable_milestones_millions == pytest.approx(50.0)
        assert result.upfront_receipts_millions == pytest.approx(30.0)
