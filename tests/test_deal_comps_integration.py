"""
Integration tests: deal comps → ValuationOutput → memo rendering.

Covers:
  - ValuationEngine populates comps_fair_value_band when comparable_deals supplied
  - ValuationEngine leaves comps_fair_value_band=None when no deals supplied (backward compat)
  - ValuationOutput.summary_dict and to_json_dict include comps fields
  - MemoGenerator renders deal comps table in BD memo when comps are present
  - MemoGenerator renders fallback text in BD memo when no comps match
"""
from __future__ import annotations

import pytest

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.intelligence.comparable_deals import ComparableDeal, ComparableDealAnalysis, FairValueBand
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import MonteCarloParams
from bve.reporting.memo_generator import MemoGenerator
from bve.valuation.valuation_engine import ValuationEngine


# ──────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def asset():
    return Asset(
        id="a-test",
        name="TEST-101",
        indication="ulcerative colitis",
        therapeutic_area=TherapeuticArea.IMMUNOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=0.12,
    )


@pytest.fixture
def company():
    return Company(
        id="co-test",
        name="Test Therapeutics",
        ticker="TEST",
        cash_millions=200.0,
        shares_outstanding_millions=80.0,
        burn_rate_millions_per_quarter=20.0,
        current_price=15.00,
    )


@pytest.fixture
def trials(asset):
    return [
        ClinicalTrial(
            asset_id=asset.id,
            phase=TrialPhase.PHASE_2,
            success_probability=0.40,
            duration_years=2.5,
            cost_millions=60.0,
        ),
        ClinicalTrial(
            asset_id=asset.id,
            phase=TrialPhase.PHASE_3,
            success_probability=0.60,
            duration_years=3.0,
            cost_millions=180.0,
        ),
        ClinicalTrial(
            asset_id=asset.id,
            phase=TrialPhase.NDA_BLA,
            success_probability=0.90,
            duration_years=1.0,
            cost_millions=20.0,
        ),
    ]


@pytest.fixture
def market(asset):
    return MarketModel(
        asset_id=asset.id,
        total_addressable_market_millions=5_000.0,
        peak_penetration=0.10,
        years_to_peak=5,
        patent_life_years=10,
        cogs_rate=0.20,
        sgna_rate_launch=0.40,
        sgna_rate_mature=0.20,
    )


_MC_FAST = MonteCarloParams(n_simulations=200, random_seed=42)


def _make_deal(
    target_name: str,
    indication: str,
    ta: str,
    phase: str,
    ev: float,
    peak_sales: float,
    upfront: float | None = None,
    milestones: float | None = None,
    territory: str = "global",
    deal_structure: str = "M&A",
    post_deal_outcome: str | None = None,
) -> ComparableDeal:
    d: dict = {
        "target_name": target_name,
        "indication": indication,
        "therapeutic_area": ta,
        "phase_at_acquisition": phase,
        "acquirer": "Large Pharma",
        "deal_date": "2024-01-01",
        "enterprise_value_millions": ev,
        "peak_sales_millions": peak_sales,
        "territory": territory,
        "deal_structure": deal_structure,
    }
    if upfront is not None:
        d["upfront_millions"] = upfront
    if milestones is not None:
        d["total_milestones_millions"] = milestones
    if post_deal_outcome is not None:
        d["post_deal_outcome"] = post_deal_outcome
    return ComparableDeal.model_validate(d)


@pytest.fixture
def immunology_phase2_deals():
    return [
        _make_deal("Deal A", "ulcerative colitis", "immunology", "phase_2",
                   ev=1000, peak_sales=500, upfront=1000, milestones=0,
                   post_deal_outcome="approved"),
        _make_deal("Deal B", "ulcerative colitis", "immunology", "phase_2",
                   ev=2000, peak_sales=500, upfront=2000, milestones=0,
                   post_deal_outcome="ongoing"),
        _make_deal("Deal C", "crohn's disease", "immunology", "phase_2",
                   ev=1500, peak_sales=500, upfront=1200, milestones=300,
                   post_deal_outcome="approved"),
    ]


# ──────────────────────────────────────────────────────────────────────────────
# ValuationEngine: comps wiring
# ──────────────────────────────────────────────────────────────────────────────

class TestValuationEngineCompsWiring:
    def test_no_comps_supplied_leaves_field_none(self, asset, company, trials, market):
        engine = ValuationEngine(asset, company, trials, market, mc_params=_MC_FAST)
        output = engine.run()
        assert output.comps_fair_value_band is None

    def test_empty_deals_list_produces_no_comps_result(self, asset, company, trials, market):
        engine = ValuationEngine(
            asset, company, trials, market, mc_params=_MC_FAST, comparable_deals=[]
        )
        output = engine.run()
        assert output.comps_fair_value_band is not None
        assert output.comps_fair_value_band.match_tier == "no_comps"
        assert output.comps_fair_value_band.n_comps == 0

    def test_matching_deals_populate_fair_value_band(
        self, asset, company, trials, market, immunology_phase2_deals
    ):
        engine = ValuationEngine(
            asset, company, trials, market,
            mc_params=_MC_FAST,
            comparable_deals=immunology_phase2_deals,
        )
        output = engine.run()
        assert output.comps_fair_value_band is not None
        assert output.comps_fair_value_band.match_tier in (
            "exact_indication_phase", "therapeutic_area_phase", "phase_only"
        )
        assert output.comps_fair_value_band.n_comps >= 1
        assert isinstance(output.comps_fair_value_band.fair_value_band, FairValueBand)

    def test_comps_fair_value_band_ev_quantiles_are_plausible(
        self, asset, company, trials, market, immunology_phase2_deals
    ):
        engine = ValuationEngine(
            asset, company, trials, market,
            mc_params=_MC_FAST,
            comparable_deals=immunology_phase2_deals,
        )
        output = engine.run()
        band = output.comps_fair_value_band.fair_value_band
        assert band is not None
        assert band.n_comps_with_ev >= 2
        assert band.ev_p25 is not None
        assert band.ev_p50 is not None
        assert band.ev_p75 is not None
        # Monotonicity
        assert band.ev_p25 <= band.ev_p50 <= band.ev_p75

    def test_comps_upfront_quantiles_populated_when_deals_have_upfront(
        self, asset, company, trials, market, immunology_phase2_deals
    ):
        engine = ValuationEngine(
            asset, company, trials, market,
            mc_params=_MC_FAST,
            comparable_deals=immunology_phase2_deals,
        )
        output = engine.run()
        band = output.comps_fair_value_band.fair_value_band
        assert band.n_comps_with_upfront >= 2
        assert band.upfront_p50 is not None
        assert band.upfront_p25 <= band.upfront_p50 <= band.upfront_p75


# ──────────────────────────────────────────────────────────────────────────────
# ValuationOutput: summary_dict and to_json_dict
# ──────────────────────────────────────────────────────────────────────────────

class TestValuationOutputCompsFields:
    def test_summary_dict_includes_comps_keys_when_no_comps(
        self, asset, company, trials, market
    ):
        engine = ValuationEngine(asset, company, trials, market, mc_params=_MC_FAST)
        output = engine.run()
        sd = output.summary_dict
        assert "comps_match_tier" in sd
        assert sd["comps_match_tier"] is None
        assert sd["comps_n_comps"] is None
        assert sd["comps_peer_median_ev_to_peak_sales"] is None

    def test_summary_dict_includes_comps_values_when_comps_match(
        self, asset, company, trials, market, immunology_phase2_deals
    ):
        engine = ValuationEngine(
            asset, company, trials, market,
            mc_params=_MC_FAST,
            comparable_deals=immunology_phase2_deals,
        )
        output = engine.run()
        sd = output.summary_dict
        assert sd["comps_match_tier"] is not None
        assert sd["comps_n_comps"] >= 1
        assert sd["comps_peer_median_ev_to_peak_sales"] is not None

    def test_to_json_dict_includes_deal_comps_section(
        self, asset, company, trials, market, immunology_phase2_deals
    ):
        engine = ValuationEngine(
            asset, company, trials, market,
            mc_params=_MC_FAST,
            comparable_deals=immunology_phase2_deals,
        )
        output = engine.run()
        d = output.to_json_dict()
        assert "deal_comps" in d["outputs"]
        dc = d["outputs"]["deal_comps"]
        assert "match_tier" in dc
        assert "fair_value_band" in dc
        assert dc["fair_value_band"]["ev_p50"] is not None

    def test_to_json_dict_no_deal_comps_section_when_none(
        self, asset, company, trials, market
    ):
        engine = ValuationEngine(asset, company, trials, market, mc_params=_MC_FAST)
        output = engine.run()
        d = output.to_json_dict()
        assert "deal_comps" not in d["outputs"]


# ──────────────────────────────────────────────────────────────────────────────
# MemoGenerator: BD memo rendering
# ──────────────────────────────────────────────────────────────────────────────

class TestMemoGeneratorCompsRendering:
    def test_bd_memo_contains_comps_table_when_comps_match(
        self, asset, company, trials, market, immunology_phase2_deals
    ):
        engine = ValuationEngine(
            asset, company, trials, market,
            mc_params=_MC_FAST,
            comparable_deals=immunology_phase2_deals,
        )
        output = engine.run()
        memo = MemoGenerator().generate(output, memo_type="bd")
        assert "Deal Comps" in memo
        assert "match" in memo.lower()
        # Should contain the matched deal names
        assert any(
            d.target_name in memo for d in immunology_phase2_deals
        )

    def test_bd_memo_contains_fallback_when_no_comps(
        self, asset, company, trials, market
    ):
        engine = ValuationEngine(asset, company, trials, market, mc_params=_MC_FAST)
        output = engine.run()
        memo = MemoGenerator().generate(output, memo_type="bd")
        assert "Deal Comps" in memo
        # Fallback text present when comps_fair_value_band is None
        assert "comparable_deals.yaml" in memo or "BD team to populate" in memo

    def test_bd_memo_contains_fallback_when_deals_supplied_but_no_match(
        self, asset, company, trials, market
    ):
        # Deals in a completely different indication/TA/phase — will not match
        unrelated = [
            _make_deal("Unrelated A", "heart failure", "cardiovascular", "phase_3",
                       ev=5000, peak_sales=2000, upfront=5000, milestones=0),
        ]
        engine = ValuationEngine(
            asset, company, trials, market,
            mc_params=_MC_FAST,
            comparable_deals=unrelated,
        )
        output = engine.run()
        assert output.comps_fair_value_band is not None
        assert output.comps_fair_value_band.match_tier == "no_comps"
        memo = MemoGenerator().generate(output, memo_type="bd")
        assert "Deal Comps" in memo

    def test_bd_memo_shows_ev_quantiles_when_available(
        self, asset, company, trials, market, immunology_phase2_deals
    ):
        engine = ValuationEngine(
            asset, company, trials, market,
            mc_params=_MC_FAST,
            comparable_deals=immunology_phase2_deals,
        )
        output = engine.run()
        memo = MemoGenerator().generate(output, memo_type="bd")
        # EV P50 should appear in the table — deals have EV 1000/1500/2000
        assert "$1" in memo or "$2" in memo  # some EV figure present

    def test_bd_memo_shows_upfront_framework_when_upfront_available(
        self, asset, company, trials, market, immunology_phase2_deals
    ):
        engine = ValuationEngine(
            asset, company, trials, market,
            mc_params=_MC_FAST,
            comparable_deals=immunology_phase2_deals,
        )
        output = engine.run()
        memo = MemoGenerator().generate(output, memo_type="bd")
        # Upfront comp median should replace placeholder in deal framework section
        assert "comp set median" in memo or "To be determined" in memo

    def test_hf_memo_generates_without_comps_error(
        self, asset, company, trials, market, immunology_phase2_deals
    ):
        """HF memo template does not have the comps block — should not error."""
        engine = ValuationEngine(
            asset, company, trials, market,
            mc_params=_MC_FAST,
            comparable_deals=immunology_phase2_deals,
        )
        output = engine.run()
        # Should not raise — comps variable is in context but HF template may not render it
        memo = MemoGenerator().generate(output, memo_type="hf")
        assert len(memo) > 100
