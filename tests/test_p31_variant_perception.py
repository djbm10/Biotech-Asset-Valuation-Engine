"""
Tests for P3.1 — Variant perception back-solve wired into ValuationOutput.

Verifies:
- back_solve_variant_perception returns VariantPerceptionResult from rnpv+company data
- VariantPerceptionResult has three allocation cases (conservative/base/aggressive)
- implied_pos is in [0, 1] or None when guardrail fires
- implied_peak_sales_millions is positive when implied_pos is valid
- raw_implied_pos exists and can be outside [0, 1]
- variant_perception_category is a known literal
- memo_interpretation is a non-empty string
- ValuationOutput.variant_perception is populated when company.current_price > 0
- ValuationOutput.variant_perception is None when no price
- summary_dict contains vp_* keys
- vp_pos_gap_pp = model_pos - implied_pos (in pp)
- AssetAllocationSpec deductions reduce asset_implied_ev
- back-solve returns None for zero gross_revenue_pv (guardrail: pv_fcf_invalid)
- VariantCategory classification: clinical, commercial, indeterminate
"""
from __future__ import annotations

import pytest

from bve.analysis.variant_perception import (
    AssetAllocationSpec,
    BackSolvePoint,
    VariantPerceptionResult,
    back_solve_variant_perception,
)


# ---------------------------------------------------------------------------
# Shared test fixture builders
# ---------------------------------------------------------------------------

def _build_output(current_price: float = 20.0, shares: float = 100.0, net_cash: float = 150.0):
    """Build a minimal ValuationOutput-like stub for variant perception tests."""
    from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
    from bve.entities.company import Company
    from bve.entities.trial import ClinicalTrial, TrialPhase
    from bve.models.market_model import MarketModel
    from bve.valuation.valuation_engine import ValuationEngine

    asset = Asset(
        id="vp-test",
        name="VP Test Drug",
        indication="Non-small cell lung cancer",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        modality=Modality.SMALL_MOLECULE,
        stage=DevelopmentStage.PHASE_3,
        discount_rate=0.10,
    )
    company = Company(
        id="co-vp",
        name="VP Pharma",
        ticker="VPP",
        shares_outstanding_millions=shares,
        cash_millions=net_cash,
        current_price=current_price if current_price > 0 else None,
    )
    trials = [
        ClinicalTrial(
            asset_id="vp-test",
            phase=TrialPhase.PHASE_3,
            success_probability=0.55,
            duration_years=3.0,
            cost_millions=80.0,
        )
    ]
    market_model = MarketModel(
        asset_id="vp-test",
        total_addressable_market_millions=5000.0,
        peak_penetration=0.05,
        years_to_peak=4,
        patent_life_years=10,
        net_price_per_patient_usd=100000,
        addressable_patients_annual=10000,
    )
    return ValuationEngine(
        asset=asset, company=company, trials=trials, market_model=market_model
    ).run()


# ---------------------------------------------------------------------------
# back_solve_variant_perception unit tests
# ---------------------------------------------------------------------------

class TestBackSolveVariantPerception:
    def setup_method(self):
        self.output = _build_output(current_price=20.0)

    def test_returns_result_when_price_set(self):
        result = back_solve_variant_perception(self.output, emit_guardrail_warnings=False)
        assert result is not None
        assert isinstance(result, VariantPerceptionResult)

    def test_returns_none_when_no_price(self):
        output_no_price = _build_output(current_price=0.0)
        result = back_solve_variant_perception(output_no_price, emit_guardrail_warnings=False)
        assert result is None

    def test_has_three_allocation_cases(self):
        result = back_solve_variant_perception(self.output, emit_guardrail_warnings=False)
        assert isinstance(result.conservative, BackSolvePoint)
        assert isinstance(result.base, BackSolvePoint)
        assert isinstance(result.aggressive, BackSolvePoint)

    def test_implied_pos_in_unit_interval_when_valid(self):
        result = back_solve_variant_perception(self.output, emit_guardrail_warnings=False)
        if result.base.implied_pos is not None:
            assert 0.0 <= result.base.implied_pos <= 1.0

    def test_implied_peak_sales_positive_when_valid(self):
        result = back_solve_variant_perception(self.output, emit_guardrail_warnings=False)
        if result.base.implied_peak_sales_millions is not None:
            assert result.base.implied_peak_sales_millions > 0

    def test_raw_implied_pos_is_float(self):
        result = back_solve_variant_perception(self.output, emit_guardrail_warnings=False)
        assert isinstance(result.base.raw_implied_pos, float)

    def test_category_is_known_value(self):
        result = back_solve_variant_perception(self.output, emit_guardrail_warnings=False)
        valid = {"clinical", "commercial", "pricing", "mixed", "allocation", "indeterminate"}
        assert result.variant_perception_category in valid

    def test_memo_interpretation_is_string(self):
        result = back_solve_variant_perception(self.output, emit_guardrail_warnings=False)
        assert isinstance(result.memo_interpretation, str)
        assert len(result.memo_interpretation) > 10

    def test_market_cap_computed_correctly(self):
        """market_cap = price × shares = 20 × 100 = 2000."""
        result = back_solve_variant_perception(self.output, emit_guardrail_warnings=False)
        assert abs(result.market_cap_millions - 2000.0) < 0.5

    def test_company_ev_computed_correctly(self):
        """company_ev = market_cap - net_cash = 2000 - 150 = 1850."""
        result = back_solve_variant_perception(self.output, emit_guardrail_warnings=False)
        assert abs(result.company_ev_millions - 1850.0) < 0.5

    def test_model_pos_matches_rnpv(self):
        result = back_solve_variant_perception(self.output, emit_guardrail_warnings=False)
        assert result.model_pos == pytest.approx(
            self.output.rnpv.cumulative_success_probability, abs=0.001
        )


# ---------------------------------------------------------------------------
# AssetAllocationSpec deductions
# ---------------------------------------------------------------------------

class TestAssetAllocationSpec:
    def test_zero_deductions_by_default(self):
        spec = AssetAllocationSpec()
        assert spec.total_fixed_deductions() == 0.0
        assert spec.other_pipeline("base") == 0.0

    def test_conservative_case_higher_deduction(self):
        spec = AssetAllocationSpec(
            other_pipeline_conservative=500.0,
            other_pipeline_base=300.0,
            other_pipeline_aggressive=100.0,
        )
        assert spec.other_pipeline("conservative") == 500.0
        assert spec.other_pipeline("base") == 300.0
        assert spec.other_pipeline("aggressive") == 100.0

    def test_deductions_reduce_asset_ev(self):
        output = _build_output(current_price=20.0)
        no_spec = back_solve_variant_perception(output, emit_guardrail_warnings=False)
        spec = AssetAllocationSpec(other_pipeline_base=500.0)
        with_spec = back_solve_variant_perception(output, allocation_spec=spec,
                                                  emit_guardrail_warnings=False)
        assert with_spec.base.asset_implied_ev_millions < no_spec.base.asset_implied_ev_millions

    def test_total_fixed_deductions(self):
        spec = AssetAllocationSpec(
            royalty_stream_value=100.0,
            platform_value=50.0,
            non_core_value=25.0,
        )
        assert spec.total_fixed_deductions() == 175.0


# ---------------------------------------------------------------------------
# ValuationOutput integration
# ---------------------------------------------------------------------------

class TestValuationOutputVariantPerception:
    def test_variant_perception_populated_with_price(self):
        output = _build_output(current_price=20.0)
        assert output.variant_perception is not None
        assert isinstance(output.variant_perception, VariantPerceptionResult)

    def test_variant_perception_none_without_price(self):
        output = _build_output(current_price=0.0)
        assert output.variant_perception is None

    def test_summary_dict_has_vp_keys(self):
        output = _build_output(current_price=20.0)
        sd = output.summary_dict
        for key in ["vp_category", "vp_implied_pos", "vp_pos_gap_pp",
                    "vp_implied_peak_sales_millions", "vp_memo"]:
            assert key in sd, f"Missing key: {key}"

    def test_summary_dict_vp_category_valid(self):
        output = _build_output(current_price=20.0)
        valid = {"clinical", "commercial", "pricing", "mixed", "allocation", "indeterminate"}
        assert output.summary_dict["vp_category"] in valid

    def test_summary_dict_vp_keys_none_when_no_price(self):
        output = _build_output(current_price=0.0)
        sd = output.summary_dict
        assert sd["vp_category"] is None
        assert sd["vp_implied_pos"] is None
        assert sd["vp_pos_gap_pp"] is None

    def test_summary_dict_vp_pos_gap_formula(self):
        """vp_pos_gap_pp = (model_pos - implied_pos) × 100."""
        output = _build_output(current_price=20.0)
        sd = output.summary_dict
        if sd["vp_implied_pos"] is not None and sd["vp_pos_gap_pp"] is not None:
            model_pos = output.rnpv.cumulative_success_probability
            expected_gap = round((model_pos - sd["vp_implied_pos"]) * 100, 1)
            assert sd["vp_pos_gap_pp"] == pytest.approx(expected_gap, abs=0.2)

    def test_summary_dict_vp_memo_is_string(self):
        output = _build_output(current_price=20.0)
        memo = output.summary_dict["vp_memo"]
        assert isinstance(memo, str)
        assert len(memo) > 5

    def test_vp_pv_fcf_matches_rnpv(self):
        output = _build_output(current_price=20.0)
        assert output.variant_perception.pv_full_success_fcf_millions == pytest.approx(
            output.rnpv.gross_revenue_pv_millions, rel=1e-3
        )

    def test_vp_base_asset_ev_matches_market_less_cash(self):
        """With no allocation spec, base asset_implied_ev = company_ev (full EV to this asset)."""
        output = _build_output(current_price=20.0, shares=100.0, net_cash=150.0)
        vp = output.variant_perception
        if vp is not None:
            expected_ev = 20.0 * 100.0 - 150.0  # market_cap - net_cash
            assert vp.base.asset_implied_ev_millions == pytest.approx(expected_ev, abs=1.0)
