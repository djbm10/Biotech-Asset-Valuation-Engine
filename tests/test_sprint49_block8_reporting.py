"""Tests for Block 8: Decision-Grade Reporting & Validation Evidence.

Covers:
- provenance.py: ProvenanceItem, build_pos_provenance, build_valuation_provenance,
  render_provenance_table
- validation_summary.py: build_validation_summary, render_validation_summary,
  missing-data behavior, calibration param fallback
- decision_report.py: render_decision_report, all sections, missing-data behavior,
  prediction log rendering, auto-provenance population
- CLI bve_report: argument parsing, graceful missing-data output
- CLI bve_validate: argument parsing, --no-* flags, graceful missing-data output
"""
from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

from bve.reporting.provenance import (
    ProvenanceItem,
    build_pos_provenance,
    build_valuation_provenance,
    render_provenance_table,
)
from bve.reporting.validation_summary import (
    ValidationSummaryData,
    build_validation_summary,
    render_validation_summary,
)
from bve.reporting.decision_report import (
    DecisionReportInput,
    render_decision_report,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_mock_asset(
    stage="phase_2",
    ta="oncology",
    breakthrough=True,
    biomarker=False,
):
    """Minimal mock Asset with the attributes provenance builder reads."""
    asset = MagicMock()
    stage_mock = MagicMock()
    stage_mock.value = stage
    asset.stage = stage_mock
    ta_mock = MagicMock()
    ta_mock.value = ta
    asset.therapeutic_area = ta_mock
    asset.breakthrough_designation = breakthrough
    asset.biomarker_selected = biomarker
    return asset


def _make_mock_trial(phase="phase_2", success_probability=0.42):
    trial = MagicMock()
    phase_mock = MagicMock()
    phase_mock.value = phase
    trial.phase = phase_mock
    trial.success_probability = success_probability
    return trial


def _make_mock_company(price=12.50, net_cash=80.0, shares=100.0):
    company = MagicMock()
    company.current_price = price
    company.net_cash_millions = net_cash
    company.shares_outstanding_millions = shares
    company.cash_runway_quarters = 8.0
    company.ticker = "TSTR"
    company.name = "Test Biotech Inc."
    company.price_as_of = None
    return company


def _make_mock_rnpv(
    rnpv_millions=120.0,
    peak_sales=400.0,
    cum_pos=0.42,
    years_to_launch=3.5,
    discount_rate=0.12,
    net_ownership=1.0,
):
    rnpv = MagicMock()
    rnpv.rnpv_millions = rnpv_millions
    rnpv.peak_sales_millions = peak_sales
    rnpv.cumulative_success_probability = cum_pos
    rnpv.years_to_launch = years_to_launch
    rnpv.discount_rate = discount_rate
    rnpv.net_ownership = net_ownership
    return rnpv


def _make_mock_valuation_output(
    ticker="TSTR",
    model_pos=0.42,
    rnpv_base=120.0,
    implied_pos=None,
):
    vo = MagicMock()
    vo.asset = _make_mock_asset()
    vo.company = _make_mock_company()
    vo.trials = [_make_mock_trial()]
    vo.market_model = MagicMock()
    vo.market_model.peak_penetration = 0.15
    vo.market_model.patent_life_years = 12
    vo.rnpv = _make_mock_rnpv(cum_pos=model_pos, rnpv_millions=rnpv_base)
    vo.market_expectation = None

    # summary_dict returns a real dict
    sd = {
        "model_pos": model_pos,
        "pos_comparison_text": None,
        "market_implied_pos": implied_pos,
        "market_pos_gap_pct": None,
        "market_mispricing_direction": None,
        "bull_rnpv": 200.0,
        "base_rnpv": rnpv_base,
        "bear_rnpv": 50.0,
        "bull_nav_ps": 4.50,
        "base_nav_ps": 2.80,
        "bear_nav_ps": 0.90,
        "mc_mean": 130.0,
        "mc_p25": 80.0,
        "mc_p75": 190.0,
        "mc_prob_positive": "78.0%",
        "prob_approval_pct": "42.0%",
        "peak_sales_millions": 400.0,
        "years_to_launch": 3.5,
        "current_price": 12.50,
        "nav_per_share": 2.80,
        "implied_upside_pct": -77.6,
        "ticker": ticker,
        "asset_name": "Test Asset",
    }
    vo.summary_dict = sd
    vo.pos_comparison_text = None
    return vo


def _make_mock_ma_row(ticker="TSTR", score=0.65, p_acq=0.18):
    row = MagicMock()
    row.ticker = ticker
    row.mna_probability_score = score
    row.p_acquisition = p_acq
    row.p_takeout_calibrated = 0.14
    row.best_acquirer_name = "BigPharma Co"
    row.best_acquirer_fit_score = 0.72
    row.watchlist_type = "catalyst_watch"
    row.rank = 3
    row.strategic_fit_score = 0.70
    row.valuation_discount_score = 0.65
    row.de_risking_stage_score = 0.60
    row.capital_vulnerability_score = 0.30
    row.score_drivers = ["High strategic fit (0.70)", "Good valuation discount (0.65)"]
    row.score_suppressors = ["Moderate capital vulnerability (0.30)"]
    return row


# ---------------------------------------------------------------------------
# Tests: ProvenanceItem
# ---------------------------------------------------------------------------

class TestProvenanceItem:

    def test_defaults(self):
        item = ProvenanceItem(field="test_field", value=42)
        assert item.source == "not_available"
        assert item.as_of is None
        assert item.staleness_warning is None
        assert item.confidence == "medium"
        assert item.notes is None

    def test_full_construction(self):
        item = ProvenanceItem(
            field="Peak sales",
            value=400.0,
            source="yaml_config",
            as_of=date(2024, 6, 1),
            staleness_warning="90 days old",
            confidence="low",
            notes="Analyst estimate",
        )
        assert item.field == "Peak sales"
        assert item.source == "yaml_config"
        assert item.staleness_warning == "90 days old"


# ---------------------------------------------------------------------------
# Tests: build_pos_provenance
# ---------------------------------------------------------------------------

class TestBuildPosProvenance:

    def test_returns_list_of_items(self):
        asset = _make_mock_asset()
        trials = [_make_mock_trial("phase_2", 0.42)]
        items = build_pos_provenance(asset, trials)
        assert isinstance(items, list)
        assert len(items) > 0
        assert all(isinstance(i, ProvenanceItem) for i in items)

    def test_stage_item_present(self):
        asset = _make_mock_asset(stage="phase_3")
        items = build_pos_provenance(asset, [])
        fields = [i.field for i in items]
        assert any("stage" in f.lower() for f in fields)

    def test_ta_item_present(self):
        asset = _make_mock_asset(ta="oncology")
        items = build_pos_provenance(asset, [])
        fields = [i.field for i in items]
        assert any("therapeutic" in f.lower() or "area" in f.lower() for f in fields)

    def test_trial_success_p_present(self):
        asset = _make_mock_asset()
        trials = [_make_mock_trial("phase_2", 0.42)]
        items = build_pos_provenance(asset, trials)
        fields = [i.field for i in items]
        assert any("phase_2" in f.lower() or "success" in f.lower() for f in fields)

    def test_breakthrough_item_present(self):
        asset = _make_mock_asset(breakthrough=True)
        items = build_pos_provenance(asset, [])
        fields = [i.field for i in items]
        assert any("breakthrough" in f.lower() for f in fields)

    def test_no_trials_ok(self):
        asset = _make_mock_asset()
        items = build_pos_provenance(asset, [])
        assert isinstance(items, list)

    def test_missing_asset_attribute_does_not_raise(self):
        # Minimal asset with no attributes
        asset = object()
        items = build_pos_provenance(asset, [])
        assert isinstance(items, list)


# ---------------------------------------------------------------------------
# Tests: build_valuation_provenance
# ---------------------------------------------------------------------------

class TestBuildValuationProvenance:

    def test_returns_list_of_items(self):
        vo = _make_mock_valuation_output()
        items = build_valuation_provenance(vo)
        assert isinstance(items, list)
        assert len(items) > 0

    def test_peak_sales_present(self):
        vo = _make_mock_valuation_output()
        items = build_valuation_provenance(vo)
        fields = [i.field for i in items]
        assert any("peak sales" in f.lower() or "peak" in f.lower() for f in fields)

    def test_discount_rate_present(self):
        vo = _make_mock_valuation_output()
        items = build_valuation_provenance(vo)
        fields = [i.field for i in items]
        assert any("discount" in f.lower() for f in fields)

    def test_price_item_present(self):
        vo = _make_mock_valuation_output()
        items = build_valuation_provenance(vo)
        fields = [i.field for i in items]
        assert any("price" in f.lower() for f in fields)

    def test_stale_price_warning_when_old(self):
        vo = _make_mock_valuation_output()
        vo.company.price_as_of = date(2020, 1, 1)  # Very old
        items = build_valuation_provenance(vo, as_of_date=date(2025, 1, 1))
        price_items = [i for i in items if "price" in i.field.lower()]
        assert any(i.staleness_warning for i in price_items)

    def test_no_staleness_warning_for_fresh_price(self):
        vo = _make_mock_valuation_output()
        today = date.today()
        vo.company.price_as_of = today
        items = build_valuation_provenance(vo, as_of_date=today)
        price_items = [i for i in items if "price" in i.field.lower()]
        assert all(i.staleness_warning is None for i in price_items)

    def test_missing_valuation_output_does_not_raise(self):
        items = build_valuation_provenance(object())
        assert isinstance(items, list)


# ---------------------------------------------------------------------------
# Tests: render_provenance_table
# ---------------------------------------------------------------------------

class TestRenderProvenanceTable:

    def test_returns_string(self):
        items = [
            ProvenanceItem(field="Peak sales", value="400", source="yaml_config"),
        ]
        result = render_provenance_table(items)
        assert isinstance(result, str)

    def test_header_present(self):
        items = [ProvenanceItem(field="X", value="1", source="yaml_config")]
        result = render_provenance_table(items)
        assert "## Assumption Provenance" in result

    def test_table_row_contains_field(self):
        items = [ProvenanceItem(field="Peak sales", value="400.0", source="yaml_config")]
        result = render_provenance_table(items)
        assert "Peak sales" in result

    def test_staleness_warning_shown(self):
        items = [
            ProvenanceItem(
                field="Net cash",
                value="80",
                source="market_data",
                staleness_warning="45 days old",
            )
        ]
        result = render_provenance_table(items)
        assert "45 days old" in result
        assert "⚠" in result

    def test_empty_items_shows_message(self):
        result = render_provenance_table([])
        assert "no provenance" in result.lower() or "not available" in result.lower()

    def test_custom_section_title(self):
        result = render_provenance_table([], section_title="My Inputs")
        assert "## My Inputs" in result

    def test_not_available_shown_for_none_value(self):
        items = [ProvenanceItem(field="X", value=None)]
        result = render_provenance_table(items)
        assert "Not available" in result


# ---------------------------------------------------------------------------
# Tests: build_validation_summary
# ---------------------------------------------------------------------------

class TestBuildValidationSummary:

    def test_defaults_with_no_inputs(self):
        data = build_validation_summary()
        assert isinstance(data, ValidationSummaryData)
        assert data.replay_n_resolved == 0
        assert data.ma_n == 0

    def test_replay_fields_populated(self):
        replay = MagicMock()
        replay.mean_return_pct = 3.5
        replay.mean_alpha_pct = 2.1
        replay.alpha_hit_rate = 0.67
        replay.n_resolved = 15
        replay.n_with_xbi_data = 12
        replay.validation_status = "directional_only"
        replay.hit_rate = 0.55
        replay.brier_score = 0.22
        replay.run_id = "abc-123"
        replay.strategy_version = "top2_add"
        replay.start_date = date(2022, 1, 1)
        replay.end_date = date(2024, 12, 31)
        data = build_validation_summary(replay_summary=replay)
        assert data.replay_mean_return_pct == pytest.approx(3.5)
        assert data.replay_mean_alpha_pct == pytest.approx(2.1)
        assert data.replay_n_resolved == 15
        assert data.replay_strategy == "top2_add"
        assert "2022" in data.replay_period

    def test_ma_backtest_fields_populated(self):
        ma = MagicMock()
        ma.auc = 0.74
        ma.brier_score = 0.18
        ma.base_rate = 0.25
        ma.score_separation = 0.22
        ma.n = 120
        ma.n_positive = 30
        ma.training_window = "2020-01-01 to 2025-12-31"
        data = build_validation_summary(ma_backtest_result=ma)
        assert data.ma_auc == pytest.approx(0.74)
        assert data.ma_n == 120
        assert data.ma_training_window == "2020-01-01 to 2025-12-31"

    def test_pos_backtest_fields_populated(self):
        pos = MagicMock()
        pos.heuristic_brier_score = 0.2127
        pos.heuristic_auc = 0.74
        pos.n_programs = 99
        pos.phase2_base_rate = 0.396
        pos.phase3_base_rate = 0.608
        data = build_validation_summary(pos_backtest_result=pos)
        assert data.pos_heuristic_brier == pytest.approx(0.2127)
        assert data.pos_n_programs == 99

    def test_calibration_fallback_when_no_json(self, tmp_path):
        from bve.intelligence.ma_backtest import _DEFAULT_SLOPE, _DEFAULT_MIDPOINT
        missing = tmp_path / "absent.json"
        data = build_validation_summary(calibration_params_path=missing)
        assert data.calibration_source == "hardcoded_fallback"
        assert data.calibration_slope == _DEFAULT_SLOPE
        assert data.calibration_midpoint == _DEFAULT_MIDPOINT

    def test_calibration_fitted_when_json_present(self, tmp_path):
        params_file = tmp_path / "calib.json"
        params_file.write_text(json.dumps({
            "slope": 9.5, "midpoint": 0.62,
            "n_positive": 25, "training_window": "2020-2025",
        }))
        data = build_validation_summary(calibration_params_path=params_file)
        assert data.calibration_source == "fitted"
        assert data.calibration_slope == pytest.approx(9.5)
        assert data.calibration_midpoint == pytest.approx(0.62)
        assert data.calibration_params_n_positive == 25

    def test_generated_at_is_set(self):
        data = build_validation_summary()
        assert data.generated_at != ""

    def test_all_none_does_not_raise(self):
        data = build_validation_summary(
            replay_summary=None,
            ma_backtest_result=None,
            pos_backtest_result=None,
        )
        assert isinstance(data, ValidationSummaryData)


# ---------------------------------------------------------------------------
# Tests: render_validation_summary
# ---------------------------------------------------------------------------

class TestRenderValidationSummary:

    def test_returns_string(self):
        data = ValidationSummaryData(generated_at="2026-01-01T00:00:00+00:00")
        result = render_validation_summary(data)
        assert isinstance(result, str)

    def test_disclaimer_always_present(self):
        data = ValidationSummaryData()
        result = render_validation_summary(data)
        assert "VALIDATION STATUS" in result or "directional" in result.lower()

    def test_section_headers_present(self):
        data = ValidationSummaryData()
        result = render_validation_summary(data)
        assert "Historical Replay Alpha" in result
        assert "M&A Backtest" in result
        assert "POS Model Calibration" in result
        assert "Logistic Calibration" in result

    def test_not_available_for_empty_fields(self):
        data = ValidationSummaryData()
        result = render_validation_summary(data)
        assert "Not available" in result

    def test_replay_values_rendered(self):
        data = ValidationSummaryData(
            replay_mean_return_pct=4.2,
            replay_n_resolved=20,
        )
        result = render_validation_summary(data)
        assert "+4.20%" in result
        assert "20" in result

    def test_ma_auc_rendered(self):
        data = ValidationSummaryData(ma_auc=0.7412, ma_n=80)
        result = render_validation_summary(data)
        assert "0.7412" in result
        assert "80" in result

    def test_calibration_fallback_label(self):
        data = ValidationSummaryData(calibration_source="hardcoded_fallback")
        result = render_validation_summary(data)
        assert "Hard-coded fallback" in result or "hardcoded" in result.lower()

    def test_calibration_fitted_label(self):
        data = ValidationSummaryData(calibration_source="fitted")
        result = render_validation_summary(data)
        assert "Fitted" in result

    def test_notes_rendered(self):
        data = ValidationSummaryData(notes=["This is a test note."])
        result = render_validation_summary(data)
        assert "This is a test note." in result

    def test_generated_at_shown(self):
        data = ValidationSummaryData(generated_at="2026-05-26T12:00:00+00:00")
        result = render_validation_summary(data)
        assert "2026-05-26" in result


# ---------------------------------------------------------------------------
# Tests: render_decision_report — all sections
# ---------------------------------------------------------------------------

class TestRenderDecisionReport:

    def test_returns_string(self):
        inp = DecisionReportInput(ticker="TSTR")
        result = render_decision_report(inp)
        assert isinstance(result, str)

    def test_header_has_ticker(self):
        inp = DecisionReportInput(ticker="SRPT")
        result = render_decision_report(inp)
        assert "SRPT" in result

    def test_disclaimer_always_present(self):
        inp = DecisionReportInput(ticker="X")
        result = render_decision_report(inp)
        assert "Research-grade output" in result or "Not investment advice" in result

    def test_all_sections_present_with_no_data(self):
        inp = DecisionReportInput(ticker="TSTR")
        result = render_decision_report(inp)
        for section in [
            "Model vs. Market POS",
            "rNPV Summary",
            "M&A / BD Action Assessment",
            "Staleness Warnings",
            "Assumption Provenance",
            "Prediction Log History",
            "Validation Evidence",
        ]:
            assert section in result, f"Missing section: {section}"

    def test_not_available_in_empty_report(self):
        inp = DecisionReportInput(ticker="TSTR")
        result = render_decision_report(inp)
        assert "Not available" in result

    def test_pos_section_with_valuation_output(self):
        vo = _make_mock_valuation_output(ticker="TSTR", model_pos=0.42)
        inp = DecisionReportInput(ticker="TSTR", valuation_output=vo)
        result = render_decision_report(inp)
        assert "42%" in result or "0.42" in result

    def test_rnpv_section_with_valuation_output(self):
        vo = _make_mock_valuation_output(rnpv_base=120.0)
        inp = DecisionReportInput(ticker="TSTR", valuation_output=vo)
        result = render_decision_report(inp)
        assert "120" in result  # base rNPV
        assert "200" in result  # bull rNPV

    def test_ma_section_with_row(self):
        row = _make_mock_ma_row(score=0.65)
        inp = DecisionReportInput(ticker="TSTR", ma_row=row)
        result = render_decision_report(inp)
        assert "BigPharma Co" in result
        assert "0.6500" in result or "0.65" in result

    def test_score_drivers_rendered(self):
        row = _make_mock_ma_row()
        inp = DecisionReportInput(ticker="TSTR", ma_row=row)
        result = render_decision_report(inp)
        assert "High strategic fit" in result

    def test_score_suppressors_rendered(self):
        row = _make_mock_ma_row()
        inp = DecisionReportInput(ticker="TSTR", ma_row=row)
        result = render_decision_report(inp)
        assert "Moderate capital vulnerability" in result

    def test_staleness_warnings_rendered(self):
        inp = DecisionReportInput(
            ticker="TSTR",
            staleness_warnings=["Financial data is 90 days old (>60d threshold)"],
        )
        result = render_decision_report(inp)
        assert "90 days old" in result

    def test_no_staleness_section_shows_clear_message(self):
        inp = DecisionReportInput(ticker="TSTR", staleness_warnings=[])
        result = render_decision_report(inp)
        assert "No staleness warnings" in result or "within freshness" in result

    def test_prediction_log_entries_rendered(self):
        entries = [
            {
                "id": 1, "log_type": "ma_score", "ticker": "TSTR",
                "score": 0.65, "confidence": 0.80,
                "logged_at": "2025-03-15T10:00:00+00:00",
                "outcome": None, "outcome_notes": None,
                "notes": "Best acquirer: BigPharma",
            }
        ]
        inp = DecisionReportInput(ticker="TSTR", prediction_log_entries=entries)
        result = render_decision_report(inp)
        assert "ma_score" in result
        assert "0.6500" in result

    def test_no_log_entries_shows_message(self):
        inp = DecisionReportInput(ticker="TSTR", prediction_log_entries=[])
        result = render_decision_report(inp)
        assert "No prediction log entries" in result

    def test_prediction_log_accuracy_computed(self):
        entries = [
            {"id": 1, "log_type": "ma_score", "ticker": "TSTR", "score": 0.7,
             "confidence": None, "logged_at": "2024-01-01", "outcome": "correct",
             "outcome_notes": None, "notes": None},
            {"id": 2, "log_type": "ma_score", "ticker": "TSTR", "score": 0.6,
             "confidence": None, "logged_at": "2024-02-01", "outcome": "incorrect",
             "outcome_notes": None, "notes": None},
        ]
        inp = DecisionReportInput(ticker="TSTR", prediction_log_entries=entries)
        result = render_decision_report(inp)
        assert "50%" in result or "1/2" in result or "Accuracy" in result

    def test_provenance_auto_populated_from_valuation_output(self):
        vo = _make_mock_valuation_output()
        inp = DecisionReportInput(
            ticker="TSTR",
            valuation_output=vo,
            provenance_items=[],  # explicitly empty → should be auto-populated
        )
        result = render_decision_report(inp)
        assert "Assumption Provenance" in result
        assert "yaml_config" in result or "Peak sales" in result

    def test_explicit_provenance_items_used(self):
        prov = [
            ProvenanceItem(
                field="Custom field",
                value="custom_value",
                source="manual",
                confidence="high",
            )
        ]
        inp = DecisionReportInput(ticker="TSTR", provenance_items=prov)
        result = render_decision_report(inp)
        assert "Custom field" in result
        assert "custom_value" in result

    def test_notes_rendered(self):
        inp = DecisionReportInput(
            ticker="TSTR",
            notes=["This is a manual analyst note."],
        )
        result = render_decision_report(inp)
        assert "This is a manual analyst note." in result

    def test_validation_summary_injected(self):
        vs = ValidationSummaryData(ma_auc=0.79, generated_at="2026-01-01T00:00:00Z")
        inp = DecisionReportInput(ticker="TSTR", validation_summary=vs)
        result = render_decision_report(inp)
        assert "0.7900" in result

    def test_as_of_date_in_header(self):
        inp = DecisionReportInput(ticker="TSTR", as_of_date=date(2025, 7, 4))
        result = render_decision_report(inp)
        assert "2025-07-04" in result

    def test_prediction_log_notes_truncated(self):
        long_notes = "A" * 100
        entries = [
            {"id": 1, "log_type": "ma_score", "ticker": "TSTR", "score": 0.7,
             "confidence": None, "logged_at": "2024-01-01", "outcome": None,
             "outcome_notes": None, "notes": long_notes},
        ]
        inp = DecisionReportInput(ticker="TSTR", prediction_log_entries=entries)
        result = render_decision_report(inp)
        # Long notes should be truncated in the table
        assert "..." in result


# ---------------------------------------------------------------------------
# Tests: CLI bve_report
# ---------------------------------------------------------------------------

class TestBveReportCLI:

    def test_help_exits_cleanly(self):
        from bve.cli.bve_report import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_missing_ticker_exits_nonzero(self):
        from bve.cli.bve_report import main
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code != 0

    def test_valid_ticker_produces_output(self, tmp_path, capsys):
        from bve.cli.bve_report import main
        out = tmp_path / "report.md"
        # Use a ticker with no data — should still produce a report
        ret = main(["--ticker", "NONEXISTENT", "--output", str(out)])
        assert ret == 0
        assert out.exists()
        content = out.read_text()
        assert "NONEXISTENT" in content
        assert "Not available" in content

    def test_invalid_date_returns_error(self, capsys):
        from bve.cli.bve_report import main
        ret = main(["--ticker", "TSTR", "--as-of", "not-a-date"])
        assert ret == 1

    def test_output_written_to_file(self, tmp_path):
        from bve.cli.bve_report import main
        out = tmp_path / "out.md"
        ret = main(["--ticker", "TSTR", "--output", str(out)])
        assert ret == 0
        assert out.exists()
        assert len(out.read_text()) > 100

    def test_stdout_when_no_output_flag(self, capsys):
        from bve.cli.bve_report import main
        ret = main(["--ticker", "TSTR"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "TSTR" in captured.out
        assert "BVE Decision Report" in captured.out


# ---------------------------------------------------------------------------
# Tests: CLI bve_validate
# ---------------------------------------------------------------------------

class TestBveValidateCLI:

    def test_help_exits_cleanly(self):
        from bve.cli.bve_validate import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_no_args_produces_output(self, capsys):
        from bve.cli.bve_validate import main
        ret = main(["--no-replay", "--no-ma-backtest", "--no-pos-backtest"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "Validation Evidence" in captured.out
        assert "Not available" in captured.out

    def test_output_written_to_file(self, tmp_path):
        from bve.cli.bve_validate import main
        out = tmp_path / "validate.md"
        ret = main([
            "--output", str(out),
            "--no-replay", "--no-ma-backtest", "--no-pos-backtest",
        ])
        assert ret == 0
        assert out.exists()
        content = out.read_text()
        assert "Validation Evidence" in content

    def test_disclaimer_always_in_output(self, capsys):
        from bve.cli.bve_validate import main
        main(["--no-replay", "--no-ma-backtest", "--no-pos-backtest"])
        captured = capsys.readouterr()
        assert "directional" in captured.out.lower() or "VALIDATION" in captured.out

    def test_no_replay_flag(self, capsys):
        from bve.cli.bve_validate import main
        ret = main(["--no-replay", "--no-ma-backtest", "--no-pos-backtest"])
        assert ret == 0

    def test_all_no_flags(self, capsys):
        from bve.cli.bve_validate import main
        ret = main(["--no-replay", "--no-ma-backtest", "--no-pos-backtest"])
        assert ret == 0
        captured = capsys.readouterr()
        # With all data suppressed, every numeric row should show Not available
        assert "Not available" in captured.out
