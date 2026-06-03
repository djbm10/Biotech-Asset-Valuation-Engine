"""
Tests for P3.5 — SOTP (sum-of-the-parts) valuation and ex-US modelling.

Verifies:
- build_sotp returns SOTPResult
- total_nav = sum(geo_adjusted_values) + net_cash - adjustments
- Each component has name, rnpv_millions, geo_adjusted_value
- geo_adjusted_value <= rnpv_millions (ex-US haircut reduces value)
- us_fraction=1.0 means no ex-US haircut (geo_adjusted == rnpv)
- ex_us_discount applied only to the ex-US fraction
- as_waterfall_bars() returns list of dicts with name/value/bar_type
- Waterfall bars include each asset, net_cash, adjustments, and total_nav bar
- corporate_adjustments are negative (deductions)
- nav_per_share = total_nav / shares_outstanding
- nav_per_share is None when shares is None or zero
- Empty assets raises ValueError
- Component with negative rnpv is preserved (loss-making program)
- SOTPResult is frozen (immutable)
- geo_segments dict sums to 1.0 for each component
- US-only (us_fraction=1.0) component unaffected by ex_us_discount
- Multi-component total matches sum
- summary_dict contains expected keys
- as_csv_rows header and dimensions
- as_waterfall_bars total bar matches total_nav_millions
"""
from __future__ import annotations

import pytest

from bve.analysis.sotp import (
    GeographySpec,
    SOTPComponent,
    SOTPResult,
    build_sotp,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _two_asset_sotp(**kwargs) -> SOTPResult:
    components = [
        SOTPComponent(
            name="DrugA",
            rnpv_millions=300.0,
            us_fraction=0.65,
            ex_us_discount=0.10,  # 10% additional haircut on ex-US
        ),
        SOTPComponent(
            name="DrugB",
            rnpv_millions=150.0,
            us_fraction=1.0,
        ),
    ]
    return build_sotp(
        components=components,
        net_cash_millions=100.0,
        shares_outstanding_millions=80.0,
        **kwargs,
    )


def _single_asset_sotp(**kwargs) -> SOTPResult:
    return build_sotp(
        components=[SOTPComponent(name="DrugX", rnpv_millions=200.0, us_fraction=0.70)],
        net_cash_millions=50.0,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# SOTPComponent
# ---------------------------------------------------------------------------

class TestSOTPComponent:
    def test_default_us_fraction_is_one(self):
        c = SOTPComponent(name="A", rnpv_millions=100.0)
        assert c.us_fraction == pytest.approx(1.0)

    def test_geo_adjusted_value_no_ex_us(self):
        """us_fraction=1.0 → no ex-US fraction → geo_adjusted == rnpv."""
        c = SOTPComponent(name="A", rnpv_millions=100.0, us_fraction=1.0)
        assert c.geo_adjusted_value == pytest.approx(100.0)

    def test_geo_adjusted_value_with_ex_us_fraction(self):
        """us_fraction=0.60, no discount → geo_adjusted == rnpv (discount=0)."""
        c = SOTPComponent(name="A", rnpv_millions=100.0, us_fraction=0.60, ex_us_discount=0.0)
        assert c.geo_adjusted_value == pytest.approx(100.0)

    def test_geo_adjusted_value_with_discount(self):
        """us=0.60, ex_us=0.40 at 20% discount → 60 + 40*(1-0.20) = 60+32 = 92."""
        c = SOTPComponent(name="A", rnpv_millions=100.0, us_fraction=0.60, ex_us_discount=0.20)
        assert c.geo_adjusted_value == pytest.approx(92.0, abs=0.1)

    def test_geo_adjusted_le_rnpv_when_discount_positive(self):
        c = SOTPComponent(name="A", rnpv_millions=200.0, us_fraction=0.50, ex_us_discount=0.15)
        assert c.geo_adjusted_value <= c.rnpv_millions

    def test_negative_rnpv_preserved(self):
        c = SOTPComponent(name="LossProgram", rnpv_millions=-50.0)
        assert c.geo_adjusted_value == pytest.approx(-50.0)

    def test_geo_haircut_pct(self):
        c = SOTPComponent(name="A", rnpv_millions=100.0, us_fraction=0.60, ex_us_discount=0.20)
        assert c.geo_haircut_pct == pytest.approx(8.0, abs=0.1)  # (100-92)/100*100

    def test_no_haircut_when_us_only(self):
        c = SOTPComponent(name="A", rnpv_millions=100.0, us_fraction=1.0, ex_us_discount=0.30)
        assert c.geo_haircut_pct == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# GeographySpec
# ---------------------------------------------------------------------------

class TestGeographySpec:
    def test_default_spec_sums_to_one(self):
        spec = GeographySpec()
        total = spec.us + spec.eu + spec.japan + spec.row
        assert abs(total - 1.0) < 0.01

    def test_custom_spec_sums_to_one(self):
        spec = GeographySpec(us=0.60, eu=0.25, japan=0.05, row=0.10)
        assert abs(spec.us + spec.eu + spec.japan + spec.row - 1.0) < 0.01

    def test_bad_spec_raises(self):
        with pytest.raises(ValueError, match="sum"):
            GeographySpec(us=0.50, eu=0.50, japan=0.10, row=0.10)


# ---------------------------------------------------------------------------
# SOTPResult structure
# ---------------------------------------------------------------------------

class TestSOTPResultStructure:
    def test_returns_sotp_result(self):
        assert isinstance(_two_asset_sotp(), SOTPResult)

    def test_has_components(self):
        result = _two_asset_sotp()
        assert len(result.components) == 2

    def test_component_names(self):
        result = _two_asset_sotp()
        names = [c.name for c in result.components]
        assert "DrugA" in names
        assert "DrugB" in names

    def test_net_cash_preserved(self):
        result = _two_asset_sotp()
        assert result.net_cash_millions == pytest.approx(100.0)

    def test_is_frozen(self):
        result = _two_asset_sotp()
        with pytest.raises((AttributeError, TypeError)):
            result.net_cash_millions = 999.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SOTPResult total_nav math
# ---------------------------------------------------------------------------

class TestTotalNAVMath:
    def test_total_nav_no_adjustments(self):
        """total_nav = sum(geo_adjusted) + net_cash."""
        result = _single_asset_sotp()
        expected = result.components[0].geo_adjusted_value + 50.0
        assert result.total_nav_millions == pytest.approx(expected, abs=0.01)

    def test_total_nav_with_adjustments(self):
        """corporate adjustments are subtracted."""
        result = _two_asset_sotp(corporate_adjustments_millions=20.0)
        geo_sum = sum(c.geo_adjusted_value for c in result.components)
        expected = geo_sum + 100.0 - 20.0
        assert result.total_nav_millions == pytest.approx(expected, abs=0.01)

    def test_nav_per_share(self):
        result = _two_asset_sotp()
        expected = result.total_nav_millions / 80.0
        assert result.nav_per_share == pytest.approx(expected, abs=0.01)

    def test_nav_per_share_none_when_no_shares(self):
        result = _single_asset_sotp(shares_outstanding_millions=None)
        assert result.nav_per_share is None

    def test_nav_per_share_none_when_zero_shares(self):
        result = _single_asset_sotp(shares_outstanding_millions=0.0)
        assert result.nav_per_share is None

    def test_total_matches_manual_two_assets(self):
        """
        DrugA: rnpv=300, us=0.65, ex_us=0.10
          → geo_adjusted = 300*(0.65 + 0.35*(1-0.10)) = 300*(0.65+0.315) = 300*0.965 = 289.5
        DrugB: rnpv=150, us=1.0 → geo_adjusted = 150
        total = 289.5 + 150 + 100 (cash) = 539.5
        """
        result = _two_asset_sotp()
        assert result.total_nav_millions == pytest.approx(539.5, abs=0.5)


# ---------------------------------------------------------------------------
# Waterfall bars
# ---------------------------------------------------------------------------

class TestWaterfallBars:
    def test_returns_list(self):
        bars = _two_asset_sotp().as_waterfall_bars()
        assert isinstance(bars, list)
        assert len(bars) >= 1

    def test_each_bar_has_required_keys(self):
        bars = _two_asset_sotp().as_waterfall_bars()
        for bar in bars:
            assert "name" in bar
            assert "value" in bar
            assert "bar_type" in bar

    def test_has_bar_for_each_asset(self):
        bars = _two_asset_sotp().as_waterfall_bars()
        names = [b["name"] for b in bars]
        assert "DrugA" in names
        assert "DrugB" in names

    def test_has_net_cash_bar(self):
        bars = _two_asset_sotp().as_waterfall_bars()
        names = [b["name"] for b in bars]
        assert any("cash" in n.lower() or "net cash" in n.lower() for n in names)

    def test_has_total_nav_bar(self):
        bars = _two_asset_sotp().as_waterfall_bars()
        names = [b["name"] for b in bars]
        assert any("total" in n.lower() or "nav" in n.lower() for n in names)

    def test_total_bar_matches_total_nav(self):
        result = _two_asset_sotp()
        bars = result.as_waterfall_bars()
        total_bar = next(b for b in bars if "total" in b["name"].lower() or "nav" in b["name"].lower())
        assert total_bar["value"] == pytest.approx(result.total_nav_millions, abs=0.1)

    def test_asset_bar_type(self):
        bars = _two_asset_sotp().as_waterfall_bars()
        for bar in bars:
            if bar["name"] in ("DrugA", "DrugB"):
                assert bar["bar_type"] in ("asset", "positive", "waterfall")

    def test_adjustments_bar_is_negative_when_present(self):
        result = _two_asset_sotp(corporate_adjustments_millions=30.0)
        bars = result.as_waterfall_bars()
        adj_bars = [b for b in bars if "adjust" in b["name"].lower() or "overhead" in b["name"].lower()]
        if adj_bars:
            assert adj_bars[0]["value"] < 0

    def test_zero_adjustment_bar_excluded_or_zero(self):
        result = _two_asset_sotp(corporate_adjustments_millions=0.0)
        bars = result.as_waterfall_bars()
        adj_bars = [b for b in bars if "adjust" in b["name"].lower()]
        # Either no adjustment bar, or value=0
        for bar in adj_bars:
            assert bar["value"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# summary_dict
# ---------------------------------------------------------------------------

class TestSummaryDict:
    def test_has_expected_keys(self):
        result = _two_asset_sotp()
        sd = result.summary_dict()
        for key in [
            "total_nav_millions", "nav_per_share", "net_cash_millions",
            "n_components", "corporate_adjustments_millions",
        ]:
            assert key in sd

    def test_n_components_correct(self):
        result = _two_asset_sotp()
        assert result.summary_dict()["n_components"] == 2

    def test_total_nav_in_summary(self):
        result = _two_asset_sotp()
        assert result.summary_dict()["total_nav_millions"] == pytest.approx(
            result.total_nav_millions, abs=0.01
        )


# ---------------------------------------------------------------------------
# as_csv_rows
# ---------------------------------------------------------------------------

class TestCSVRows:
    def test_header_row_exists(self):
        rows = _two_asset_sotp().as_csv_rows()
        assert len(rows) >= 1
        assert isinstance(rows[0], list)

    def test_header_contains_expected_columns(self):
        header = _two_asset_sotp().as_csv_rows()[0]
        header_str = " ".join(str(h).lower() for h in header)
        assert "name" in header_str or "component" in header_str
        assert "rnpv" in header_str or "value" in header_str

    def test_one_data_row_per_component(self):
        rows = _two_asset_sotp().as_csv_rows()
        # header + 2 components + totals rows
        assert len(rows) >= 3


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_empty_components_raises(self):
        with pytest.raises(ValueError, match="empty"):
            build_sotp(components=[], net_cash_millions=100.0)

    def test_us_fraction_out_of_range_raises(self):
        with pytest.raises(ValueError):
            SOTPComponent(name="A", rnpv_millions=100.0, us_fraction=1.5)

    def test_ex_us_discount_out_of_range_raises(self):
        with pytest.raises(ValueError):
            SOTPComponent(name="A", rnpv_millions=100.0, ex_us_discount=1.5)
