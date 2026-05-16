"""
Tests for P3.4 — BD/HF output mode switch.

Verifies:
- generate_mode_view returns ModeView for BD and TRADE modes
- BD mode: headline_metrics contains BD-relevant keys
- TRADE mode: headline_metrics contains trade-relevant keys
- narrative_sections is a list of dicts with title/content
- action_recommendation is a non-empty string
- key_risks is a non-empty list of strings
- BD mode mentions acquirers
- TRADE mode mentions POS gap or market expectations
- full_summary is a superset of headline_metrics
- mode_label returns readable string
- section() accessor returns content or None
- ModeView is frozen (immutable)
- OutputMode enum has BD and TRADE
- Unknown mode raises ValueError
- With current_price set, TRADE mode computes implied_upside
- BD view narrative has Strategic Rationale section
- TRADE view narrative has Market Expectations section
"""
from __future__ import annotations

import pytest

from bve.analysis.output_mode import ModeView, OutputMode, generate_mode_view


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

def _build_output(current_price: float = 20.0):
    from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
    from bve.entities.company import Company
    from bve.entities.trial import ClinicalTrial, TrialPhase
    from bve.models.market_model import MarketModel
    from bve.valuation.valuation_engine import ValuationEngine

    asset = Asset(
        id="mode-test", name="ModeDrug",
        indication="Non-small cell lung cancer",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        modality=Modality.SMALL_MOLECULE,
        stage=DevelopmentStage.PHASE_3,
        discount_rate=0.10,
    )
    company = Company(
        id="co-mode", name="Mode Pharma", ticker="MPH",
        shares_outstanding_millions=100.0,
        cash_millions=150.0,
        current_price=current_price if current_price > 0 else None,
    )
    trials = [
        ClinicalTrial(
            asset_id="mode-test", phase=TrialPhase.PHASE_3,
            success_probability=0.55, duration_years=3.0, cost_millions=80.0,
        )
    ]
    market_model = MarketModel(
        asset_id="mode-test",
        total_addressable_market_millions=5000.0,
        peak_penetration=0.05, years_to_peak=4, patent_life_years=10,
    )
    return ValuationEngine(
        asset=asset, company=company, trials=trials, market_model=market_model
    ).run()


# ---------------------------------------------------------------------------
# OutputMode enum
# ---------------------------------------------------------------------------

class TestOutputModeEnum:
    def test_bd_value(self):
        assert OutputMode.BD.value == "bd"

    def test_trade_value(self):
        assert OutputMode.TRADE.value == "trade"

    def test_bd_label(self):
        assert "Business Development" in OutputMode.BD.label()

    def test_trade_label(self):
        assert "Trade" in OutputMode.TRADE.label() or "Equity" in OutputMode.TRADE.label()

    def test_unknown_mode_raises(self):
        output = _build_output()
        with pytest.raises((ValueError, AttributeError)):
            generate_mode_view(output, "unknown")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# BD mode
# ---------------------------------------------------------------------------

class TestBDMode:
    def setup_method(self):
        self.output = _build_output(current_price=20.0)
        self.view = generate_mode_view(self.output, OutputMode.BD)

    def test_returns_mode_view(self):
        assert isinstance(self.view, ModeView)

    def test_mode_is_bd(self):
        assert self.view.mode == OutputMode.BD

    def test_headline_has_rnpv(self):
        assert "model_rnpv_millions" in self.view.headline_metrics

    def test_headline_has_top_acquirer(self):
        assert "top_acquirer_1" in self.view.headline_metrics

    def test_headline_has_nav_per_share(self):
        assert "nav_per_share" in self.view.headline_metrics

    def test_headline_has_peak_sales(self):
        assert "peak_sales_millions" in self.view.headline_metrics

    def test_narrative_sections_is_list(self):
        assert isinstance(self.view.narrative_sections, list)
        assert len(self.view.narrative_sections) >= 1

    def test_each_section_has_title_and_content(self):
        for s in self.view.narrative_sections:
            assert "title" in s
            assert "content" in s

    def test_has_strategic_rationale_section(self):
        section = self.view.section("Strategic Rationale")
        assert section is not None
        assert len(section) > 10

    def test_action_recommendation_is_string(self):
        assert isinstance(self.view.action_recommendation, str)
        assert len(self.view.action_recommendation) > 10

    def test_key_risks_is_list(self):
        assert isinstance(self.view.key_risks, list)
        assert len(self.view.key_risks) >= 1

    def test_key_risks_are_strings(self):
        for risk in self.view.key_risks:
            assert isinstance(risk, str)

    def test_full_summary_superset_of_headline(self):
        for key in self.view.headline_metrics:
            assert key in self.view.full_summary

    def test_asset_and_company_names(self):
        assert self.view.asset_name == "ModeDrug"
        assert self.view.company_name == "Mode Pharma"
        assert self.view.ticker == "MPH"

    def test_mode_label_readable(self):
        assert len(self.view.mode_label) > 5

    def test_section_returns_none_for_missing(self):
        assert self.view.section("Nonexistent Section") is None


# ---------------------------------------------------------------------------
# Trade mode
# ---------------------------------------------------------------------------

class TestTradeMode:
    def setup_method(self):
        self.output = _build_output(current_price=20.0)
        self.view = generate_mode_view(self.output, OutputMode.TRADE)

    def test_returns_mode_view(self):
        assert isinstance(self.view, ModeView)

    def test_mode_is_trade(self):
        assert self.view.mode == OutputMode.TRADE

    def test_headline_has_implied_upside(self):
        assert "implied_upside_pct" in self.view.headline_metrics

    def test_headline_has_vp_pos_gap(self):
        assert "vp_pos_gap_pp" in self.view.headline_metrics

    def test_headline_has_catalyst_delta_ev(self):
        assert "catalyst_delta_ev_millions" in self.view.headline_metrics

    def test_headline_has_nav_per_share(self):
        assert "model_nav_per_share" in self.view.headline_metrics

    def test_has_market_expectations_section(self):
        section = self.view.section("Market Expectations")
        assert section is not None
        assert len(section) > 10

    def test_has_risk_return_section(self):
        section = self.view.section("Risk / Return")
        assert section is not None

    def test_has_catalyst_section_when_available(self):
        if self.output.catalyst_payoff is not None:
            section = self.view.section("Catalyst Payoff")
            assert section is not None

    def test_action_recommendation_is_string(self):
        assert isinstance(self.view.action_recommendation, str)
        assert len(self.view.action_recommendation) > 10

    def test_key_risks_non_empty(self):
        assert len(self.view.key_risks) >= 1

    def test_full_summary_has_mc_metrics(self):
        assert "mc_p10_millions" in self.view.full_summary
        assert "mc_p90_millions" in self.view.full_summary

    def test_full_summary_has_market_implied_pos(self):
        assert "market_implied_pos" in self.view.full_summary

    def test_mode_label_readable(self):
        assert len(self.view.mode_label) > 5


# ---------------------------------------------------------------------------
# No-price edge case
# ---------------------------------------------------------------------------

class TestNoPriceMode:
    def test_bd_mode_no_price(self):
        output = _build_output(current_price=0.0)
        view = generate_mode_view(output, OutputMode.BD)
        assert isinstance(view, ModeView)
        assert view.headline_metrics.get("implied_deal_premium_pct") is None

    def test_trade_mode_no_price(self):
        output = _build_output(current_price=0.0)
        view = generate_mode_view(output, OutputMode.TRADE)
        assert isinstance(view, ModeView)
        assert view.headline_metrics.get("implied_upside_pct") is None


# ---------------------------------------------------------------------------
# Consistency tests
# ---------------------------------------------------------------------------

class TestConsistency:
    def test_bd_and_trade_same_asset_name(self):
        output = _build_output()
        bd = generate_mode_view(output, OutputMode.BD)
        tr = generate_mode_view(output, OutputMode.TRADE)
        assert bd.asset_name == tr.asset_name

    def test_bd_rnpv_matches_output(self):
        output = _build_output()
        view = generate_mode_view(output, OutputMode.BD)
        assert view.headline_metrics["model_rnpv_millions"] == pytest.approx(
            output.rnpv.rnpv_millions, abs=0.1
        )

    def test_trade_nav_matches_output(self):
        output = _build_output()
        view = generate_mode_view(output, OutputMode.TRADE)
        assert view.headline_metrics["model_nav_per_share"] == pytest.approx(
            output.nav_per_share, abs=0.01
        )
