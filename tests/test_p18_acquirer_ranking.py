"""
Tests for P1.8 — Acquirer profiling v0: rank_acquirers() + ValuationOutput.top_acquirers.
"""
from __future__ import annotations

import pytest

from bve.entities.acquirer import (
    ACQUIRER_UNIVERSE,
    AcquirerMatch,
    AcquirerProfile,
    BDStyle,
    LOECliff,
    PipelineGap,
    rank_acquirers,
)


# ---------------------------------------------------------------------------
# AcquirerMatch model
# ---------------------------------------------------------------------------

class TestAcquirerMatchModel:
    def test_valid_construction(self):
        m = AcquirerMatch(
            company_id="test",
            name="Test Pharma",
            ticker="TST",
            ta_match=True,
            modality_match=True,
            loe_urgency=0.5,
            budget_ok=True,
            cash_firepower_millions=5000.0,
            composite_score=0.75,
            rationale="oncology is a strategic area; firepower $5,000M covers deal",
        )
        assert m.composite_score == 0.75
        assert m.ta_match is True

    def test_composite_score_bounds(self):
        with pytest.raises(Exception):
            AcquirerMatch(
                company_id="x", name="X", ta_match=True, modality_match=True,
                loe_urgency=0.5, budget_ok=True, cash_firepower_millions=1000.0,
                composite_score=1.5, rationale="bad",
            )


# ---------------------------------------------------------------------------
# rank_acquirers() core logic
# ---------------------------------------------------------------------------

class TestRankAcquirers:
    def test_returns_top_n(self):
        results = rank_acquirers("oncology", "small_molecule", 500.0, top_n=2)
        assert len(results) <= 2

    def test_sorted_by_composite_score_desc(self):
        results = rank_acquirers("oncology", "biologic", 1000.0, top_n=5)
        scores = [r.composite_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_ta_match_correct(self):
        results = rank_acquirers("oncology", "small_molecule", 500.0, top_n=len(ACQUIRER_UNIVERSE))
        for r in results:
            acquirer = next(a for a in ACQUIRER_UNIVERSE if a.company_id == r.company_id)
            assert r.ta_match == acquirer.covers_ta("oncology")

    def test_budget_ok_correct(self):
        deal_size = 10_000.0  # large deal
        results = rank_acquirers("oncology", "biologic", deal_size, top_n=len(ACQUIRER_UNIVERSE))
        for r in results:
            acquirer = next(a for a in ACQUIRER_UNIVERSE if a.company_id == r.company_id)
            assert r.budget_ok == acquirer.can_afford(deal_size)

    def test_loe_urgency_from_profile(self):
        results = rank_acquirers("oncology", "biologic", 500.0, top_n=len(ACQUIRER_UNIVERSE))
        for r in results:
            acquirer = next(a for a in ACQUIRER_UNIVERSE if a.company_id == r.company_id)
            assert abs(r.loe_urgency - acquirer.loe_urgency) < 1e-6

    def test_composite_score_in_range(self):
        results = rank_acquirers("oncology", "small_molecule", 500.0, top_n=len(ACQUIRER_UNIVERSE))
        for r in results:
            assert 0.0 <= r.composite_score <= 1.0

    def test_rationale_nonempty(self):
        results = rank_acquirers("oncology", "biologic", 1000.0, top_n=5)
        for r in results:
            assert isinstance(r.rationale, str) and len(r.rationale) > 0

    def test_custom_universe(self):
        """rank_acquirers() should work with a custom universe."""
        custom = [
            AcquirerProfile(
                company_id="custom-a",
                name="Custom A",
                cash_millions=20_000,
                annual_fcf_millions=5_000,
                strategic_areas=["oncology"],
                preferred_modalities=["biologic"],
                bd_style=BDStyle.BOLT_ON,
                loe_cliffs=[
                    LOECliff(
                        product_name="Drug X", indication="oncology",
                        peak_sales_millions=5000, loe_year=2026,
                        revenue_at_risk_millions=3000,
                    )
                ],
            ),
            AcquirerProfile(
                company_id="custom-b",
                name="Custom B",
                cash_millions=1_000,
                annual_fcf_millions=500,
                strategic_areas=["neuroscience"],
                preferred_modalities=["small_molecule"],
                bd_style=BDStyle.BOLT_ON,
            ),
        ]
        results = rank_acquirers("oncology", "biologic", 2000.0, top_n=2, universe=custom)
        assert results[0].company_id == "custom-a"
        assert results[0].ta_match is True
        assert results[0].loe_urgency > 0.0
        assert results[1].company_id == "custom-b"
        assert results[1].ta_match is False

    def test_ta_mismatch_lowers_score(self):
        """A TA mismatch should result in a lower score than a TA match (all else equal)."""
        results_on = rank_acquirers("oncology", "biologic", 500.0, top_n=len(ACQUIRER_UNIVERSE))
        # Assets with ta_match=True should have higher scores on average
        ta_match_scores = [r.composite_score for r in results_on if r.ta_match]
        ta_miss_scores = [r.composite_score for r in results_on if not r.ta_match]
        if ta_match_scores and ta_miss_scores:
            assert min(ta_match_scores) >= max(ta_miss_scores) or sum(ta_match_scores) > sum(ta_miss_scores)

    def test_top_n_zero_returns_empty(self):
        results = rank_acquirers("oncology", "biologic", 500.0, top_n=0)
        assert results == []

    def test_returns_acquirer_match_objects(self):
        results = rank_acquirers("oncology", "biologic", 500.0, top_n=2)
        for r in results:
            assert isinstance(r, AcquirerMatch)


# ---------------------------------------------------------------------------
# LOECliff urgency_score
# ---------------------------------------------------------------------------

class TestLOECliffUrgencyScore:
    def test_urgency_score_bounded(self):
        cliff = LOECliff(
            product_name="X", indication="oncology",
            peak_sales_millions=5000, loe_year=2027,
            revenue_at_risk_millions=20_000,  # > 10k cap
        )
        assert cliff.urgency_score == 1.0

    def test_urgency_score_proportional(self):
        cliff = LOECliff(
            product_name="X", indication="oncology",
            peak_sales_millions=2000, loe_year=2027,
            revenue_at_risk_millions=5_000,
        )
        assert cliff.urgency_score == pytest.approx(0.5)

    def test_zero_urgency_when_no_risk(self):
        cliff = LOECliff(
            product_name="X", indication="oncology",
            peak_sales_millions=100, loe_year=2030,
            revenue_at_risk_millions=0,
        )
        assert cliff.urgency_score == 0.0


# ---------------------------------------------------------------------------
# Integration: ValuationOutput.top_acquirers
# ---------------------------------------------------------------------------

class TestValuationOutputTopAcquirers:
    def _make_output(self):
        from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
        from bve.entities.company import Company
        from bve.entities.trial import ClinicalTrial, TrialPhase
        from bve.models.market_model import MarketModel
        from bve.valuation.valuation_engine import ValuationEngine

        asset = Asset(
            id="acq-test-01",
            name="Test Asset",
            indication="NSCLC",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            modality=Modality.BIOLOGIC,
            stage=DevelopmentStage.PHASE_3,
            discount_rate=0.10,
        )
        company = Company(
            id="co-01", name="Test Co", ticker="TST",
            shares_outstanding_millions=50.0,
            cash_millions=100.0,
        )
        trials = [
            ClinicalTrial(
                asset_id="acq-test-01",
                phase=TrialPhase.PHASE_3,
                success_probability=0.55,
                duration_years=3.0,
                cost_millions=80.0,
            )
        ]
        market_model = MarketModel(
            asset_id="acq-test-01",
            total_addressable_market_millions=5000.0,
            peak_penetration=0.05,
            years_to_peak=3,
            patent_life_years=10,
        )
        return ValuationEngine(
            asset=asset, company=company, trials=trials, market_model=market_model
        ).run()

    def test_top_acquirers_populated(self):
        output = self._make_output()
        assert len(output.top_acquirers) == 2

    def test_top_acquirers_are_acquirer_match(self):
        output = self._make_output()
        for acq in output.top_acquirers:
            assert isinstance(acq, AcquirerMatch)

    def test_top_acquirers_sorted_desc(self):
        output = self._make_output()
        if len(output.top_acquirers) == 2:
            assert output.top_acquirers[0].composite_score >= output.top_acquirers[1].composite_score

    def test_summary_dict_acquirer_keys(self):
        output = self._make_output()
        sd = output.summary_dict
        assert "top_acquirer_1" in sd
        assert "top_acquirer_2" in sd
        assert "top_acquirer_1_score" in sd
        assert "top_acquirer_1_rationale" in sd

    def test_summary_dict_acquirer_1_is_str(self):
        output = self._make_output()
        sd = output.summary_dict
        assert isinstance(sd["top_acquirer_1"], str)
        assert isinstance(sd["top_acquirer_1_score"], float)
