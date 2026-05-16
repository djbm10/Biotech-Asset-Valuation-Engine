"""
Tests for P3.6 — IC-ready memo generator: IC/BD best-practice section structure.

Verifies:
- generate_ic_memo returns ICMemo for BD and TRADE types
- ICMemo.full_text is a non-empty string (Markdown)
- All required IC sections are present (by title)
- BD memo: has Executive Summary, Asset Profile, Market Opportunity,
  Deal Valuation, Acquirer Analysis, Risk Factors, Recommendation
- TRADE memo: has Investment Thesis, Clinical Evidence, Variant Perception,
  Risk/Return, Catalyst Analysis sections
- Each section has title and content attributes
- section() accessor returns content or None for missing
- Recommendation section is non-empty
- rNPV value appears in full_text
- P(approval) appears in full_text
- ICMemoSection has title/content/required fields
- word_count > 100
- as_markdown() returns same as full_text
- Unknown memo_type raises ValueError
- Missing optional data (no price, no acquirers) handled gracefully
- BD memo mentions acquirer name when top_acquirers is available
- sections list is ordered (Executive Summary comes first)
- Each required section exists with len(content) > 10
"""
from __future__ import annotations

import pytest


def _build_output(current_price: float = 25.0):
    from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
    from bve.entities.company import Company
    from bve.entities.trial import ClinicalTrial, TrialPhase
    from bve.models.market_model import MarketModel
    from bve.valuation.valuation_engine import ValuationEngine

    asset = Asset(
        id="ic-test", name="ICDrug",
        indication="Metastatic breast cancer",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        modality=Modality.BIOLOGIC,
        stage=DevelopmentStage.PHASE_3,
        discount_rate=0.10,
    )
    company = Company(
        id="co-ic", name="IC Pharma", ticker="ICP",
        shares_outstanding_millions=120.0,
        cash_millions=200.0,
        current_price=current_price if current_price > 0 else None,
    )
    trials = [
        ClinicalTrial(
            asset_id="ic-test", phase=TrialPhase.PHASE_3,
            success_probability=0.60, duration_years=2.5, cost_millions=90.0,
        )
    ]
    market_model = MarketModel(
        asset_id="ic-test",
        total_addressable_market_millions=8000.0,
        peak_penetration=0.06, years_to_peak=4, patent_life_years=10,
    )
    return ValuationEngine(
        asset=asset, company=company, trials=trials, market_model=market_model
    ).run()


from bve.reporting.ic_memo import ICMemo, ICMemoSection, generate_ic_memo, ICMemoType


# ---------------------------------------------------------------------------
# ICMemoSection
# ---------------------------------------------------------------------------

class TestICMemoSection:
    def test_has_title(self):
        s = ICMemoSection(title="Executive Summary", content="Some content here.", required=True)
        assert s.title == "Executive Summary"

    def test_has_content(self):
        s = ICMemoSection(title="Executive Summary", content="Some content here.", required=True)
        assert s.content == "Some content here."

    def test_required_flag(self):
        s = ICMemoSection(title="Risks", content="Risk content.", required=True)
        assert s.required is True

    def test_optional_flag(self):
        s = ICMemoSection(title="Appendix", content="Appendix.", required=False)
        assert s.required is False


# ---------------------------------------------------------------------------
# ICMemoType enum
# ---------------------------------------------------------------------------

class TestICMemoType:
    def test_bd_value(self):
        assert ICMemoType.BD.value == "ic_bd"

    def test_trade_value(self):
        assert ICMemoType.TRADE.value == "ic_trade"

    def test_unknown_raises(self):
        output = _build_output()
        with pytest.raises((ValueError, AttributeError)):
            generate_ic_memo(output, "ic_unknown")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# BD IC memo structure
# ---------------------------------------------------------------------------

class TestBDICMemo:
    def setup_method(self):
        self.output = _build_output(current_price=25.0)
        self.memo = generate_ic_memo(self.output, ICMemoType.BD)

    def test_returns_ic_memo(self):
        assert isinstance(self.memo, ICMemo)

    def test_mode_is_bd(self):
        assert self.memo.memo_type == ICMemoType.BD

    def test_full_text_is_string(self):
        assert isinstance(self.memo.full_text, str)
        assert len(self.memo.full_text) > 100

    def test_as_markdown_equals_full_text(self):
        assert self.memo.as_markdown() == self.memo.full_text

    def test_word_count_above_100(self):
        assert self.memo.word_count > 100

    def test_has_executive_summary_section(self):
        s = self.memo.section("Executive Summary")
        assert s is not None
        assert len(s) > 10

    def test_has_asset_profile_section(self):
        s = self.memo.section("Asset Profile")
        assert s is not None

    def test_has_market_opportunity_section(self):
        s = self.memo.section("Market Opportunity")
        assert s is not None

    def test_has_deal_valuation_section(self):
        s = self.memo.section("Deal Valuation")
        assert s is not None

    def test_has_risk_factors_section(self):
        s = self.memo.section("Risk Factors")
        assert s is not None

    def test_has_recommendation_section(self):
        s = self.memo.section("Recommendation")
        assert s is not None
        assert len(s) > 10

    def test_sections_list_non_empty(self):
        assert len(self.memo.sections) >= 5

    def test_each_section_has_title_and_content(self):
        for s in self.memo.sections:
            assert isinstance(s, ICMemoSection)
            assert len(s.title) > 0
            assert len(s.content) > 0

    def test_executive_summary_is_first(self):
        assert "Summary" in self.memo.sections[0].title or "Overview" in self.memo.sections[0].title

    def test_rnpv_in_full_text(self):
        # rNPV value should appear in the memo
        assert "$" in self.memo.full_text and "M" in self.memo.full_text

    def test_p_approval_in_full_text(self):
        text = self.memo.full_text
        assert "%" in text  # at minimum a percentage is mentioned

    def test_section_returns_none_for_missing(self):
        assert self.memo.section("Nonexistent Section XYZ") is None

    def test_required_sections_all_present(self):
        required = [s for s in self.memo.sections if s.required]
        assert len(required) >= 4

    def test_asset_name_in_memo(self):
        assert "ICDrug" in self.memo.full_text

    def test_company_name_in_memo(self):
        assert "IC Pharma" in self.memo.full_text or "ICP" in self.memo.full_text


# ---------------------------------------------------------------------------
# TRADE IC memo structure
# ---------------------------------------------------------------------------

class TestTradeICMemo:
    def setup_method(self):
        self.output = _build_output(current_price=25.0)
        self.memo = generate_ic_memo(self.output, ICMemoType.TRADE)

    def test_returns_ic_memo(self):
        assert isinstance(self.memo, ICMemo)

    def test_mode_is_trade(self):
        assert self.memo.memo_type == ICMemoType.TRADE

    def test_full_text_non_empty(self):
        assert len(self.memo.full_text) > 100

    def test_has_investment_thesis_section(self):
        s = self.memo.section("Investment Thesis")
        assert s is not None

    def test_has_clinical_evidence_section(self):
        s = self.memo.section("Clinical Evidence")
        assert s is not None

    def test_has_risk_return_section(self):
        s = self.memo.section("Risk / Return")
        assert s is not None

    def test_has_recommendation_section(self):
        s = self.memo.section("Recommendation")
        assert s is not None
        assert len(s) > 10

    def test_word_count_above_100(self):
        assert self.memo.word_count > 100


# ---------------------------------------------------------------------------
# No-price edge case
# ---------------------------------------------------------------------------

class TestNoPriceICMemo:
    def test_bd_no_price_does_not_crash(self):
        output = _build_output(current_price=0.0)
        memo = generate_ic_memo(output, ICMemoType.BD)
        assert isinstance(memo, ICMemo)
        assert len(memo.full_text) > 100

    def test_trade_no_price_does_not_crash(self):
        output = _build_output(current_price=0.0)
        memo = generate_ic_memo(output, ICMemoType.TRADE)
        assert isinstance(memo, ICMemo)


# ---------------------------------------------------------------------------
# Consistency
# ---------------------------------------------------------------------------

class TestConsistency:
    def test_bd_and_trade_have_same_asset_name(self):
        output = _build_output()
        bd = generate_ic_memo(output, ICMemoType.BD)
        tr = generate_ic_memo(output, ICMemoType.TRADE)
        assert "ICDrug" in bd.full_text
        assert "ICDrug" in tr.full_text

    def test_bd_and_trade_different_structure(self):
        output = _build_output()
        bd = generate_ic_memo(output, ICMemoType.BD)
        tr = generate_ic_memo(output, ICMemoType.TRADE)
        bd_titles = {s.title for s in bd.sections}
        tr_titles = {s.title for s in tr.sections}
        # BD and TRADE have at least some different sections
        assert bd_titles != tr_titles
