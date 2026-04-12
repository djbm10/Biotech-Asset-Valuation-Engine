from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from bve.intelligence.comparable_deals import (
    ComparableDeal,
    ComparableDealAnalysis,
    ComparableDealLoader,
    ComparableDealMatcher,
    DealCompsAnalytics,
    FairValueBand,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _deal(**overrides: object) -> ComparableDeal:
    return ComparableDeal.model_validate(overrides)


def _base_deal(**extra) -> dict:
    return {
        "target_name": "Example Therapeutics",
        "indication": "Indication X",
        "therapeutic_area": "oncology",
        "phase_at_acquisition": "phase_2",
        "acquirer": "Large Pharma",
        "deal_date": "2025-02-14",
        "enterprise_value_millions": 3200,
        "peak_sales_millions": 1600,
        **extra,
    }


# ──────────────────────────────────────────────────────────────────────────────
# ComparableDeal: existing schema behaviour (must not regress)
# ──────────────────────────────────────────────────────────────────────────────

def test_comparable_deal_loader_populates_ev_to_peak_sales(tmp_path: Path):
    path = tmp_path / "comps.yaml"
    path.write_text(
        yaml.safe_dump({"deals": [_base_deal()]}),
        encoding="utf-8",
    )
    deal_set = ComparableDealLoader.load(path)
    assert len(deal_set.deals) == 1
    assert deal_set.deals[0].ev_to_peak_sales == pytest.approx(2.0, abs=1e-9)


def test_comparable_deal_loader_accepts_direct_multiple_without_raw_inputs(tmp_path: Path):
    path = tmp_path / "comps.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "deals": [
                    {
                        "target_name": "Example Therapeutics",
                        "indication": "Indication X",
                        "therapeutic_area": "oncology",
                        "phase_at_acquisition": "phase_2",
                        "acquirer": "Large Pharma",
                        "deal_date": "2025-02-14",
                        "ev_to_peak_sales": 2.75,
                        "source": "Press release + analyst note",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    deal_set = ComparableDealLoader.load(path)
    assert len(deal_set.deals) == 1
    assert deal_set.deals[0].ev_to_peak_sales == pytest.approx(2.75, abs=1e-9)
    assert deal_set.deals[0].enterprise_value_millions is None
    assert deal_set.deals[0].peak_sales_millions is None


def test_comparable_deal_requires_multiple_or_raw_inputs():
    with pytest.raises(ValidationError):
        ComparableDeal.model_validate(
            {
                "target_name": "Example Therapeutics",
                "indication": "Indication X",
                "therapeutic_area": "oncology",
                "phase_at_acquisition": "phase_2",
                "acquirer": "Large Pharma",
                "deal_date": "2025-02-14",
            }
        )


def test_comparable_deal_matcher_prefers_exact_indication_phase():
    deals = [
        _deal(**_base_deal(target_name="Exact A", indication="Ulcerative colitis",
                           therapeutic_area="immunology", phase_at_acquisition="phase_2",
                           enterprise_value_millions=3000, peak_sales_millions=1000,
                           acquirer="Pharma A", deal_date="2024-03-01")),
        _deal(**_base_deal(target_name="Exact B", indication="Ulcerative colitis",
                           therapeutic_area="immunology", phase_at_acquisition="phase ii",
                           enterprise_value_millions=2000, peak_sales_millions=1000,
                           acquirer="Pharma B", deal_date="2025-06-20")),
        _deal(**_base_deal(target_name="TA Only", indication="Crohn's disease",
                           therapeutic_area="immunology", phase_at_acquisition="phase_2",
                           enterprise_value_millions=1000, peak_sales_millions=1000,
                           acquirer="Pharma C", deal_date="2025-10-01")),
    ]
    analysis = ComparableDealMatcher.analyze(
        asset_indication="Ulcerative Colitis",
        asset_therapeutic_area="Immunology",
        asset_stage="phase_2",
        asset_ev_to_peak_sales=2.0,
        deals=deals,
    )
    assert analysis.match_tier == "exact_indication_phase"
    assert analysis.n_comps == 2
    assert analysis.peer_min_ev_to_peak_sales == pytest.approx(2.0, abs=1e-9)
    assert analysis.peer_median_ev_to_peak_sales == pytest.approx(2.5, abs=1e-9)
    assert analysis.peer_max_ev_to_peak_sales == pytest.approx(3.0, abs=1e-9)
    assert analysis.percentile_vs_comps == pytest.approx(0.25, abs=1e-9)
    assert analysis.premium_discount_vs_median == pytest.approx(-0.2, abs=1e-9)
    assert analysis.matched_targets == ["Exact A", "Exact B"]


def test_comparable_deal_matcher_falls_back_to_therapeutic_area_then_phase_only():
    deals = [
        _deal(**_base_deal(target_name="TA Match", indication="Psoriasis",
                           therapeutic_area="immunology", phase_at_acquisition="phase_2",
                           enterprise_value_millions=1800, peak_sales_millions=1000,
                           acquirer="Pharma A", deal_date="2024-04-01")),
        _deal(**_base_deal(target_name="Phase Only", indication="Rare disease",
                           therapeutic_area="genetic medicine", phase_at_acquisition="phase_2",
                           enterprise_value_millions=2400, peak_sales_millions=1000,
                           acquirer="Pharma B", deal_date="2025-01-15")),
    ]
    ta_analysis = ComparableDealMatcher.analyze(
        asset_indication="Ulcerative colitis",
        asset_therapeutic_area="immunology",
        asset_stage="phase_2",
        asset_ev_to_peak_sales=1.8,
        deals=deals,
    )
    phase_analysis = ComparableDealMatcher.analyze(
        asset_indication="Amyotrophic lateral sclerosis",
        asset_therapeutic_area="neuroscience",
        asset_stage="phase_2",
        asset_ev_to_peak_sales=2.4,
        deals=deals,
    )
    assert ta_analysis.match_tier == "therapeutic_area_phase"
    assert ta_analysis.n_comps == 1
    assert ta_analysis.peer_median_ev_to_peak_sales == pytest.approx(1.8, abs=1e-9)
    assert phase_analysis.match_tier == "phase_only"
    assert phase_analysis.n_comps == 2
    assert phase_analysis.percentile_vs_comps == pytest.approx(0.75, abs=1e-9)


def test_comparable_deal_matcher_returns_no_comps_without_asset_multiple():
    deals = [_deal(**_base_deal(target_name="Exact A", indication="Ulcerative colitis",
                                therapeutic_area="immunology", phase_at_acquisition="phase_2",
                                enterprise_value_millions=3000, peak_sales_millions=1000,
                                acquirer="Pharma A", deal_date="2024-03-01"))]
    analysis = ComparableDealMatcher.analyze(
        asset_indication="Ulcerative colitis",
        asset_therapeutic_area="immunology",
        asset_stage="phase_2",
        asset_ev_to_peak_sales=None,
        deals=deals,
    )
    assert analysis.match_tier == "no_comps"
    assert analysis.n_comps == 0
    assert analysis.percentile_vs_comps is None


# ──────────────────────────────────────────────────────────────────────────────
# New fields: schema serialisation round-trip
# ──────────────────────────────────────────────────────────────────────────────

def test_new_deal_structure_fields_accept_and_round_trip():
    deal = ComparableDeal.model_validate(
        _base_deal(
            upfront_millions=1200.0,
            total_milestones_millions=800.0,
            royalty_rate_low=0.08,
            royalty_rate_high=0.14,
            equity_component_millions=50.0,
            territory="global",
            deal_structure="M&A",
            post_deal_outcome="approved",
        )
    )
    assert deal.upfront_millions == pytest.approx(1200.0)
    assert deal.total_milestones_millions == pytest.approx(800.0)
    assert deal.royalty_rate_low == pytest.approx(0.08)
    assert deal.royalty_rate_high == pytest.approx(0.14)
    assert deal.equity_component_millions == pytest.approx(50.0)
    assert deal.territory == "global"
    assert deal.deal_structure == "M&A"
    assert deal.post_deal_outcome == "approved"

    # Round-trip via model_dump → model_validate
    d2 = ComparableDeal.model_validate(deal.model_dump())
    assert d2 == deal


def test_total_biobucks_auto_computed_from_upfront_and_milestones():
    deal = ComparableDeal.model_validate(
        _base_deal(upfront_millions=500.0, total_milestones_millions=300.0)
    )
    assert deal.total_biobucks == pytest.approx(800.0)


def test_total_biobucks_explicit_value_not_overwritten():
    deal = ComparableDeal.model_validate(
        _base_deal(upfront_millions=500.0, total_milestones_millions=300.0, total_biobucks=900.0)
    )
    # Explicit value wins; auto-compute only kicks in when total_biobucks is None
    assert deal.total_biobucks == pytest.approx(900.0)


def test_new_fields_default_to_none_for_legacy_deals():
    deal = ComparableDeal.model_validate(_base_deal())
    assert deal.upfront_millions is None
    assert deal.total_milestones_millions is None
    assert deal.royalty_rate_low is None
    assert deal.royalty_rate_high is None
    assert deal.total_biobucks is None
    assert deal.equity_component_millions is None
    assert deal.territory is None
    assert deal.deal_structure is None
    assert deal.post_deal_outcome is None


def test_comparable_deal_loader_roundtrips_new_fields(tmp_path: Path):
    path = tmp_path / "comps.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "deals": [
                    _base_deal(
                        upfront_millions=600,
                        total_milestones_millions=400,
                        royalty_rate_low=0.10,
                        royalty_rate_high=0.15,
                        territory="global",
                        deal_structure="M&A",
                        post_deal_outcome="approved",
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    deal_set = ComparableDealLoader.load(path)
    d = deal_set.deals[0]
    assert d.upfront_millions == pytest.approx(600.0)
    assert d.total_milestones_millions == pytest.approx(400.0)
    assert d.total_biobucks == pytest.approx(1000.0)
    assert d.territory == "global"
    assert d.deal_structure == "M&A"
    assert d.post_deal_outcome == "approved"


# ──────────────────────────────────────────────────────────────────────────────
# DealCompsAnalytics._quantile: numeric correctness
# ──────────────────────────────────────────────────────────────────────────────

class TestQuantile:
    def test_empty_returns_none(self):
        assert DealCompsAnalytics._quantile([], 0.5) is None

    def test_single_value_returns_that_value(self):
        assert DealCompsAnalytics._quantile([42.0], 0.5) == pytest.approx(42.0)

    def test_two_values_median(self):
        assert DealCompsAnalytics._quantile([10.0, 20.0], 0.5) == pytest.approx(15.0)

    def test_four_values_q25(self):
        # sorted: [10, 20, 30, 40]; idx = 0.25*(4-1) = 0.75; lo=0, hi=1; 10 + 0.75*(20-10) = 17.5
        assert DealCompsAnalytics._quantile([10.0, 20.0, 30.0, 40.0], 0.25) == pytest.approx(17.5)

    def test_four_values_q75(self):
        # idx = 0.75*3 = 2.25; lo=2, hi=3; 30 + 0.25*(40-30) = 32.5
        assert DealCompsAnalytics._quantile([10.0, 20.0, 30.0, 40.0], 0.75) == pytest.approx(32.5)

    def test_five_values_q50(self):
        # sorted: [1,2,3,4,5]; median = 3.0
        assert DealCompsAnalytics._quantile([1.0, 2.0, 3.0, 4.0, 5.0], 0.5) == pytest.approx(3.0)

    def test_q0_returns_minimum(self):
        assert DealCompsAnalytics._quantile([5.0, 10.0, 15.0], 0.0) == pytest.approx(5.0)

    def test_q1_returns_maximum(self):
        assert DealCompsAnalytics._quantile([5.0, 10.0, 15.0], 1.0) == pytest.approx(15.0)


# ──────────────────────────────────────────────────────────────────────────────
# DealCompsAnalytics.fair_value_band
# ──────────────────────────────────────────────────────────────────────────────

def test_fair_value_band_empty_deals():
    band = DealCompsAnalytics.fair_value_band([])
    assert band.n_comps_with_ev == 0
    assert band.ev_p50 is None
    assert band.upfront_p50 is None
    assert band.biobucks_p50 is None


def test_fair_value_band_no_new_fields():
    """Deals without upfront/biobucks still produce an EV band."""
    deals = [
        _deal(**_base_deal(target_name="A", enterprise_value_millions=1000, peak_sales_millions=500)),
        _deal(**_base_deal(target_name="B", enterprise_value_millions=2000, peak_sales_millions=500)),
        _deal(**_base_deal(target_name="C", enterprise_value_millions=3000, peak_sales_millions=500)),
    ]
    band = DealCompsAnalytics.fair_value_band(deals)
    assert band.n_comps_with_ev == 3
    assert band.ev_p50 == pytest.approx(2000.0)
    assert band.n_comps_with_upfront == 0
    assert band.upfront_p50 is None
    assert band.n_comps_with_biobucks == 0
    assert band.biobucks_p50 is None


def test_fair_value_band_with_upfront_and_biobucks():
    deals = [
        _deal(**_base_deal(target_name="A", enterprise_value_millions=1000, peak_sales_millions=500,
                           upfront_millions=400, total_milestones_millions=200)),
        _deal(**_base_deal(target_name="B", enterprise_value_millions=2000, peak_sales_millions=500,
                           upfront_millions=800, total_milestones_millions=400)),
        _deal(**_base_deal(target_name="C", enterprise_value_millions=3000, peak_sales_millions=500,
                           upfront_millions=1200, total_milestones_millions=600)),
    ]
    band = DealCompsAnalytics.fair_value_band(deals)
    # EV: [1000, 2000, 3000] → p50 = 2000
    assert band.ev_p50 == pytest.approx(2000.0)
    # upfront: [400, 800, 1200] → p50 = 800
    assert band.upfront_p50 == pytest.approx(800.0)
    assert band.n_comps_with_upfront == 3
    # biobucks auto-computed: [600, 1200, 1800] → p50 = 1200
    assert band.biobucks_p50 == pytest.approx(1200.0)
    assert band.n_comps_with_biobucks == 3


def test_fair_value_band_partial_data():
    """Only some deals have upfront data — band uses only what's available."""
    deals = [
        _deal(**_base_deal(target_name="A", enterprise_value_millions=1000, peak_sales_millions=500,
                           upfront_millions=400, total_milestones_millions=200)),
        _deal(**_base_deal(target_name="B", enterprise_value_millions=2000, peak_sales_millions=500)),
    ]
    band = DealCompsAnalytics.fair_value_band(deals)
    assert band.n_comps_with_ev == 2
    assert band.n_comps_with_upfront == 1
    # Single value returns that value
    assert band.upfront_p50 == pytest.approx(400.0)
    assert band.n_comps_with_biobucks == 1
    assert band.biobucks_p50 == pytest.approx(600.0)


# ──────────────────────────────────────────────────────────────────────────────
# ComparableDealAnalysis: fair_value_band populated by matcher
# ──────────────────────────────────────────────────────────────────────────────

def test_matcher_populates_fair_value_band():
    deals = [
        _deal(**_base_deal(target_name="A", indication="Ulcerative colitis",
                           therapeutic_area="immunology", phase_at_acquisition="phase_2",
                           enterprise_value_millions=1000, peak_sales_millions=500,
                           upfront_millions=400, total_milestones_millions=200)),
        _deal(**_base_deal(target_name="B", indication="Ulcerative colitis",
                           therapeutic_area="immunology", phase_at_acquisition="phase_2",
                           enterprise_value_millions=2000, peak_sales_millions=500,
                           upfront_millions=800, total_milestones_millions=400)),
    ]
    analysis = ComparableDealMatcher.analyze(
        asset_indication="Ulcerative colitis",
        asset_therapeutic_area="immunology",
        asset_stage="phase_2",
        asset_ev_to_peak_sales=1.5,
        deals=deals,
    )
    assert analysis.match_tier == "exact_indication_phase"
    assert analysis.fair_value_band is not None
    assert isinstance(analysis.fair_value_band, FairValueBand)
    # EV: [1000, 2000] → p50 = 1500
    assert analysis.fair_value_band.ev_p50 == pytest.approx(1500.0)
    # upfront: [400, 800] → p50 = 600
    assert analysis.fair_value_band.upfront_p50 == pytest.approx(600.0)


def test_matcher_fair_value_band_none_on_no_comps():
    analysis = ComparableDealMatcher.analyze(
        asset_indication="Ulcerative colitis",
        asset_therapeutic_area="immunology",
        asset_stage="phase_2",
        asset_ev_to_peak_sales=None,
        deals=[],
    )
    assert analysis.match_tier == "no_comps"
    assert analysis.fair_value_band is None


def test_comparable_deal_analysis_serialises_fair_value_band():
    deals = [
        _deal(**_base_deal(target_name="A", enterprise_value_millions=1500, peak_sales_millions=500,
                           upfront_millions=600, total_milestones_millions=300,
                           indication="Ulcerative colitis", therapeutic_area="immunology",
                           phase_at_acquisition="phase_2")),
    ]
    analysis = ComparableDealMatcher.analyze(
        asset_indication="Ulcerative colitis",
        asset_therapeutic_area="immunology",
        asset_stage="phase_2",
        asset_ev_to_peak_sales=3.0,
        deals=deals,
    )
    dumped = analysis.model_dump()
    assert "fair_value_band" in dumped
    assert dumped["fair_value_band"]["ev_p50"] == pytest.approx(1500.0)
    assert dumped["fair_value_band"]["upfront_p50"] == pytest.approx(600.0)
    assert dumped["fair_value_band"]["biobucks_p50"] == pytest.approx(900.0)
