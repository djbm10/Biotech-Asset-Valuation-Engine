"""Tests for the variant perception and acquisition timeline output sections."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from bve.cli.ma_probability import (
    _PEAK_SALES_TO_NPV_MULTIPLE,
    _derive_implied_pos,
    _derive_model_pos,
    _format_acquisition_timeline,
    _format_variant_perception,
    _npv_if_approved,
    _timeline_for_row,
)
from bve.intelligence.ma_probability import MAProbabilityResult, MAProbabilityRow


def _make_row(**kwargs) -> MAProbabilityRow:
    defaults = dict(
        rank=1,
        asset_id="test_asset",
        ticker="TEST",
        stage="phase_2",
        therapeutic_area="oncology",
        enterprise_value_millions=500.0,
        model_rnpv_millions=1200.0,
        peak_sales_millions=600.0,
        acquisition_discount=0.42,
        mna_probability_score=0.50,
        p_acquisition=0.50,
        raw_probability=0.50,
        above_alert_threshold=False,
        score_version="v1.4",
        best_acquirer_id="pfizer",
        best_acquirer_name="Pfizer",
        best_acquirer_fit_score=0.65,
        valuation_discount_score=0.60,
        strategic_fit_score=0.55,
        de_risking_stage_score=0.42,
        capital_vulnerability_score=0.30,
        scarcity_score=0.40,
        scarcity_peer_count=2,
        scarcity_bucket="medium",
        vulnerability_score=0.35,
        explanation="test",
    )
    defaults.update(kwargs)
    return MAProbabilityRow(**defaults)


def _make_result(rows: list[MAProbabilityRow]) -> MAProbabilityResult:
    return MAProbabilityResult(
        scanned_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
        as_of_date=date(2026, 5, 8),
        score_version="v1.4",
        alert_threshold=0.70,
        n_assets=len(rows),
        n_ranked=len(rows),
        n_above_alert_threshold=0,
        rows=rows,
    )


# ---------------------------------------------------------------------------
# _npv_if_approved
# ---------------------------------------------------------------------------


class TestNpvIfApproved:
    def test_uses_peak_sales_when_available(self):
        row = _make_row(peak_sales_millions=650.0, model_rnpv_millions=300.0)
        npv = _npv_if_approved(row)
        assert npv == pytest.approx(650.0 * _PEAK_SALES_TO_NPV_MULTIPLE)

    def test_falls_back_to_rnpv_over_stage_pos(self):
        row = _make_row(peak_sales_millions=None, model_rnpv_millions=300.0, stage="phase_2")
        npv = _npv_if_approved(row)
        # stage_pos = 0.25 → npv = 300 / 0.25 = 1200
        assert npv == pytest.approx(1200.0)

    def test_returns_none_when_no_data(self):
        row = _make_row(peak_sales_millions=None, model_rnpv_millions=None)
        assert _npv_if_approved(row) is None

    def test_returns_none_when_stage_unknown(self):
        row = _make_row(peak_sales_millions=None, model_rnpv_millions=300.0, stage=None)
        # stage_pos defaults to 0.0 → cannot divide
        assert _npv_if_approved(row) is None


# ---------------------------------------------------------------------------
# _derive_model_pos / _derive_implied_pos
# ---------------------------------------------------------------------------


class TestPoSBackSolve:
    def test_derive_model_pos_from_rnpv(self):
        row = _make_row(model_rnpv_millions=300.0)
        # NPV_if_approved = 650 × 4.5 = 2925; model_pos = 300 / 2925 ≈ 0.1026
        row2 = _make_row(peak_sales_millions=650.0, model_rnpv_millions=300.0)
        npv = 650.0 * _PEAK_SALES_TO_NPV_MULTIPLE
        pos = _derive_model_pos(row2, npv)
        assert pytest.approx(pos, abs=0.001) == 300.0 / npv

    def test_derive_model_pos_capped_at_one(self):
        row = _make_row(model_rnpv_millions=10_000.0)
        pos = _derive_model_pos(row, 100.0)
        assert pos == 1.0

    def test_derive_implied_pos(self):
        row = _make_row(enterprise_value_millions=540.0)
        npv = 540.0 / 0.20  # NPV s.t. implied_pos = 20%
        implied = _derive_implied_pos(row, npv)
        assert pytest.approx(implied, abs=0.001) == 0.20

    def test_derive_implied_pos_none_when_no_ev(self):
        row = _make_row(enterprise_value_millions=None)
        assert _derive_implied_pos(row, 2500.0) is None

    def test_gap_example_from_user(self):
        """Reproduces the user's canonical example: EV=$540M, peak=$650M → gap=32pp."""
        row = _make_row(
            enterprise_value_millions=540.0,
            peak_sales_millions=650.0,
            model_rnpv_millions=650.0 * _PEAK_SALES_TO_NPV_MULTIPLE * 0.52,  # model_pos=52%
        )
        npv = _npv_if_approved(row)
        model_pos = _derive_model_pos(row, npv)
        implied = _derive_implied_pos(row, npv)
        gap_pp = (model_pos - implied) * 100.0
        assert pytest.approx(model_pos, abs=0.005) == 0.52
        assert pytest.approx(implied, abs=0.01) == 540.0 / npv
        # gap should be positive (market underprices)
        assert gap_pp > 25.0


# ---------------------------------------------------------------------------
# _timeline_for_row
# ---------------------------------------------------------------------------


class TestTimelineForRow:
    def test_phase2_base_range(self):
        row = _make_row(stage="phase_2")
        min_m, max_m = _timeline_for_row(row)
        assert min_m >= 3
        assert max_m <= 30

    def test_near_term_transaction_shortens_timeline(self):
        row_standard = _make_row(stage="phase_2", watchlist_type="strategic_watch")
        row_near = _make_row(stage="phase_2", watchlist_type="near_term_transaction")
        min_s, max_s = _timeline_for_row(row_standard)
        min_n, max_n = _timeline_for_row(row_near)
        assert max_n < max_s

    def test_high_urgency_shortens_timeline(self):
        row_low = _make_row(stage="phase_3", gap_urgency="medium")
        row_high = _make_row(stage="phase_3", gap_urgency="high")
        _, max_l = _timeline_for_row(row_low)
        _, max_h = _timeline_for_row(row_high)
        assert max_h <= max_l

    def test_distressed_shortens_timeline(self):
        row_ok = _make_row(stage="phase_2", capital_vulnerability_score=0.20)
        row_dist = _make_row(stage="phase_2", capital_vulnerability_score=0.80)
        _, max_ok = _timeline_for_row(row_ok)
        _, max_dist = _timeline_for_row(row_dist)
        assert max_dist <= max_ok

    def test_min_always_at_least_3(self):
        row = _make_row(
            stage="nda_bla",
            watchlist_type="near_term_transaction",
            gap_urgency="high",
            transaction_driver_count=3,
            days_to_catalyst=30,
            capital_vulnerability_score=0.90,
        )
        min_m, _ = _timeline_for_row(row)
        assert min_m >= 3


# ---------------------------------------------------------------------------
# _format_variant_perception
# ---------------------------------------------------------------------------


class TestFormatVariantPerception:
    def test_renders_section_header(self):
        row = _make_row()
        result = _make_result([row])
        output = _format_variant_perception(result)
        assert "VARIANT PERCEPTION" in output
        assert "MARKET MISPRICING" in output

    def test_underpriced_label_when_ev_below_npv(self):
        # EV=$500M, NPV_approved=$2700M → implied_pos=18.5%, model ~44% → positive gap
        row = _make_row(
            enterprise_value_millions=500.0,
            peak_sales_millions=600.0,
            model_rnpv_millions=1200.0,
        )
        result = _make_result([row])
        output = _format_variant_perception(result)
        assert "UNDERPRICED" in output

    def test_overpriced_label_when_ev_exceeds_npv(self):
        row = _make_row(
            enterprise_value_millions=4000.0,
            peak_sales_millions=600.0,  # NPV_approved = 2700M, EV >> NPV → implied_pos > model
            model_rnpv_millions=800.0,
        )
        result = _make_result([row])
        output = _format_variant_perception(result)
        assert "OVERPRICED" in output

    def test_returns_empty_when_no_valid_rows(self):
        row = _make_row(enterprise_value_millions=None, peak_sales_millions=None, model_rnpv_millions=None)
        result = _make_result([row])
        output = _format_variant_perception(result)
        assert output == ""

    def test_sorted_most_underpriced_first(self):
        row_a = _make_row(ticker="AAAA", enterprise_value_millions=200.0, peak_sales_millions=600.0)
        row_b = _make_row(ticker="BBBB", enterprise_value_millions=800.0, peak_sales_millions=600.0)
        result = _make_result([row_b, row_a])  # BBBB first in input
        output = _format_variant_perception(result)
        # AAAA has lower EV → bigger gap → should appear first
        assert output.index("AAAA") < output.index("BBBB")


# ---------------------------------------------------------------------------
# _format_acquisition_timeline
# ---------------------------------------------------------------------------


class TestFormatAcquisitionTimeline:
    def test_renders_section_header(self):
        row = _make_row()
        result = _make_result([row])
        output = _format_acquisition_timeline(result)
        assert "ACQUISITION PROBABILITY RANKING" in output
        assert "2-YEAR SCOPE" in output

    def test_excludes_low_probability_rows(self):
        row = _make_row(mna_probability_score=0.10, p_acquisition=0.10)
        result = _make_result([row])
        output = _format_acquisition_timeline(result)
        assert output == ""

    def test_excludes_rows_outside_30_month_window(self):
        # preclinical defaults to (30,48) → max_m=48 > 30 → excluded
        row = _make_row(stage="preclinical", mna_probability_score=0.55)
        result = _make_result([row])
        output = _format_acquisition_timeline(result)
        assert output == ""

    def test_near_term_flag_shown(self):
        row = _make_row(
            stage="phase_3",
            mna_probability_score=0.70,
            p_acquisition=0.70,
            watchlist_type="near_term_transaction",
        )
        result = _make_result([row])
        output = _format_acquisition_timeline(result)
        assert "NEAR TERM" in output or "near-term-flag" in output

    def test_sorted_by_score_descending(self):
        row_a = _make_row(ticker="HIGH", stage="phase_3", mna_probability_score=0.75, p_acquisition=0.75)
        row_b = _make_row(ticker="LOWW", stage="phase_3", mna_probability_score=0.35, p_acquisition=0.35)
        result = _make_result([row_b, row_a])
        output = _format_acquisition_timeline(result)
        assert output.index("HIGH") < output.index("LOWW")

    def test_conviction_labels(self):
        row_high = _make_row(ticker="HCON", stage="phase_3", mna_probability_score=0.75, p_acquisition=0.75)
        row_med = _make_row(ticker="MCON", stage="phase_2", mna_probability_score=0.50, p_acquisition=0.50)
        row_low = _make_row(ticker="LCON", stage="phase_2", mna_probability_score=0.25, p_acquisition=0.25)
        result = _make_result([row_high, row_med, row_low])
        output = _format_acquisition_timeline(result)
        assert "[HIGH]" in output
        assert "[MED]" in output
        assert "[LOW]" in output
