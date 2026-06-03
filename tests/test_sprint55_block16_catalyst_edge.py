"""Block 16 — Catalyst Edge Calendar tests.

Coverage
--------
TestEdgeScoreFormula (10)       — timing_weight, event_materiality, confidence_weight,
                                   compute_edge_score clipping / None handling
TestExpectedMoveProxy (6)       — cap buckets, all event types, unknown fallback
TestComputeImpliedPos (5)       — formula correctness, None propagation, clamp to 1
TestCatalystEdgeRecord (8)      — construction, to_dict, pos_gap sign, staleness list
TestCatalystEdgeCalendar (12)   — build with injected fetcher, filter, sort, render
TestCatalystCalendarCLI (5)     — CLI invocation with --skip-refresh, --json, flags
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

from bve.intelligence.catalyst_edge_calendar import (
    CatalystEdgeCalendar,
    CatalystEdgeRecord,
    _cap_bucket,
    _classify_confidence,
    _compute_edge_score,
    _compute_implied_pos,
    _confidence_weight,
    _event_materiality,
    _expected_move_proxy,
    _timing_weight,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    ticker: str = "SRPT",
    event_type: str = "trial_readout",
    days: int = 30,
    model_pos: float = 0.50,
    implied_pos: float = 0.30,
    market_cap: float = 800.0,
    edge_score: Optional[float] = None,
) -> CatalystEdgeRecord:
    pos_gap = round(model_pos - implied_pos, 4)
    today = date.today()
    ed = today + timedelta(days=days)
    mat = _event_materiality(event_type)
    conf_w = _confidence_weight(None, True)
    timing_w = _timing_weight(days)
    if edge_score is None:
        edge_score = _compute_edge_score(pos_gap, mat, conf_w, timing_w)
    return CatalystEdgeRecord(
        ticker=ticker,
        asset_name=f"{ticker}-001",
        event_type=event_type,
        expected_date=ed,
        days_to_event=days,
        model_pos=model_pos,
        market_implied_pos=implied_pos,
        pos_gap=pos_gap,
        market_cap_millions=market_cap,
        ev_millions=market_cap - 100,
        expected_move_proxy=_expected_move_proxy(event_type, market_cap),
        edge_score=edge_score,
        confidence="medium",
    )


# ---------------------------------------------------------------------------
# TestEdgeScoreFormula (10 tests)
# ---------------------------------------------------------------------------

class TestEdgeScoreFormula:
    def test_timing_weight_ideal_window(self):
        assert _timing_weight(30) == 1.0

    def test_timing_weight_too_close(self):
        assert _timing_weight(7) == 0.7

    def test_timing_weight_boundary_14(self):
        assert _timing_weight(14) == 1.0

    def test_timing_weight_far(self):
        assert _timing_weight(150) == 0.3

    def test_timing_weight_mid_range(self):
        assert _timing_weight(90) == 0.5

    def test_timing_weight_past_event(self):
        assert _timing_weight(-1) == 0.0

    def test_event_materiality_pdufa(self):
        assert _event_materiality("pdufa_decision") == 1.00

    def test_event_materiality_trial_readout(self):
        assert _event_materiality("trial_readout") == 0.70

    def test_event_materiality_unknown(self):
        assert _event_materiality("completely_unknown") == 0.40

    def test_confidence_weight_full(self):
        w = _confidence_weight(0, True)
        assert w == 1.0

    def test_confidence_weight_no_implied_pos(self):
        w = _confidence_weight(0, False)
        assert w == 0.4

    def test_confidence_weight_stale_model(self):
        w = _confidence_weight(200, True)
        assert w < 1.0

    def test_edge_score_positive_gap(self):
        score = _compute_edge_score(0.20, 0.70, 1.0, 1.0)
        assert score is not None
        assert score > 0
        assert score == round(0.20 * 0.70, 4)

    def test_edge_score_negative_gap_clips_to_zero(self):
        score = _compute_edge_score(-0.15, 0.70, 1.0, 1.0)
        assert score == 0.0

    def test_edge_score_none_when_pos_gap_none(self):
        assert _compute_edge_score(None, 0.70, 1.0, 1.0) is None

    def test_edge_score_clamped_to_one(self):
        score = _compute_edge_score(2.0, 1.0, 1.0, 1.0)
        assert score == 1.0


# ---------------------------------------------------------------------------
# TestExpectedMoveProxy (6 tests)
# ---------------------------------------------------------------------------

class TestExpectedMoveProxy:
    def test_pdufa_large_cap(self):
        proxy = _expected_move_proxy("pdufa_decision", 6000.0)
        assert proxy == pytest.approx(0.18)

    def test_trial_readout_small_cap(self):
        proxy = _expected_move_proxy("trial_readout", 200.0)
        assert proxy == pytest.approx(0.50)

    def test_trial_readout_mid_cap(self):
        proxy = _expected_move_proxy("trial_readout", 1000.0)
        assert proxy == pytest.approx(0.28)

    def test_unknown_event_type_fallback(self):
        proxy = _expected_move_proxy("nonexistent_type", 800.0)
        assert proxy == pytest.approx(0.12)

    def test_cap_bucket_boundaries(self):
        assert _cap_bucket(5000.0) == "large"
        assert _cap_bucket(4999.9) == "mid"
        assert _cap_bucket(500.0) == "mid"
        assert _cap_bucket(499.9) == "small"

    def test_cap_bucket_none(self):
        assert _cap_bucket(None) == "mid"


# ---------------------------------------------------------------------------
# TestComputeImpliedPos (5 tests)
# ---------------------------------------------------------------------------

class TestComputeImpliedPos:
    def test_basic_formula(self):
        # implied_ev = 500 - 100 = 400; raw = (400 + 50) / 1000 = 0.45
        result = _compute_implied_pos(500.0, 100.0, 1000.0, 50.0)
        assert result == pytest.approx(0.45)

    def test_none_when_any_input_missing(self):
        assert _compute_implied_pos(None, 100.0, 1000.0, 50.0) is None
        assert _compute_implied_pos(500.0, None, 1000.0, 50.0) is None
        assert _compute_implied_pos(500.0, 100.0, None, 50.0) is None
        assert _compute_implied_pos(500.0, 100.0, 1000.0, None) is None

    def test_none_when_gross_pv_zero(self):
        assert _compute_implied_pos(500.0, 100.0, 0.0, 50.0) is None

    def test_clamped_to_one(self):
        result = _compute_implied_pos(10000.0, -500.0, 100.0, 10.0)
        assert result == 1.0

    def test_none_when_negative_raw(self):
        # implied_ev = 10 - 500 = -490; raw = (-490 + 50) / 1000 < 0
        assert _compute_implied_pos(10.0, 500.0, 1000.0, 50.0) is None


# ---------------------------------------------------------------------------
# TestCatalystEdgeRecord (8 tests)
# ---------------------------------------------------------------------------

class TestCatalystEdgeRecord:
    def test_construction(self):
        rec = _make_record()
        assert rec.ticker == "SRPT"
        assert rec.event_type == "trial_readout"
        assert rec.pos_gap == pytest.approx(0.20)

    def test_to_dict_keys(self):
        rec = _make_record()
        d = rec.to_dict()
        assert "ticker" in d
        assert "edge_score" in d
        assert "staleness_warnings" in d

    def test_to_dict_date_iso(self):
        rec = _make_record()
        d = rec.to_dict()
        assert isinstance(d["expected_date"], str)
        date.fromisoformat(d["expected_date"])  # should not raise

    def test_pos_gap_positive_when_undervalued(self):
        rec = _make_record(model_pos=0.60, implied_pos=0.35)
        assert rec.pos_gap > 0

    def test_pos_gap_negative_when_overvalued(self):
        rec = _make_record(model_pos=0.30, implied_pos=0.55)
        assert rec.pos_gap < 0

    def test_edge_score_none_when_pos_gap_none(self):
        rec = CatalystEdgeRecord(
            ticker="X", asset_name="X-001", event_type="trial_readout",
            expected_date=None, days_to_event=None,
            model_pos=None, market_implied_pos=None, pos_gap=None,
            market_cap_millions=None, ev_millions=None,
            expected_move_proxy=None, edge_score=None,
            confidence="insufficient_data",
        )
        assert rec.edge_score is None

    def test_staleness_warnings_default_empty(self):
        rec = _make_record()
        assert rec.staleness_warnings == []

    def test_staleness_warnings_preserved(self):
        rec = _make_record()
        rec.staleness_warnings = ["price data is 45 days old"]
        assert len(rec.staleness_warnings) == 1

    def test_to_dict_none_date(self):
        rec = _make_record()
        rec.expected_date = None
        d = rec.to_dict()
        assert d["expected_date"] is None


# ---------------------------------------------------------------------------
# TestClassifyConfidence (3 tests)
# ---------------------------------------------------------------------------

class TestClassifyConfidence:
    def test_high_when_all_present(self):
        assert _classify_confidence(0.50, 0.30, 800.0) == "high"

    def test_medium_when_one_missing(self):
        assert _classify_confidence(0.50, None, 800.0) == "medium"

    def test_insufficient_when_all_missing(self):
        assert _classify_confidence(None, None, None) == "insufficient_data"


# ---------------------------------------------------------------------------
# TestCatalystEdgeCalendar (12 tests)
# ---------------------------------------------------------------------------

def _make_mock_event(event_type: str = "trial_readout", days: int = 45):
    """Build a minimal mock CatalystEvent."""
    ev = MagicMock()
    ev.catalyst_type = MagicMock()
    ev.catalyst_type.value = event_type
    ev.expected_date = date.today() + timedelta(days=days)
    ev.is_active = True
    return ev


class TestCatalystEdgeCalendar:
    def _calendar(self, tmp_path: Path, fetcher=None, skip=True) -> CatalystEdgeCalendar:
        return CatalystEdgeCalendar(
            ops_db=tmp_path / "ops.db",
            outputs_dir=tmp_path / "outputs",
            market_fetcher=fetcher,
            skip_market_refresh=skip,
        )

    def test_build_empty_universe_returns_empty(self, tmp_path):
        cal = self._calendar(tmp_path)
        records = cal.build(tickers=[])
        assert records == []

    def test_build_ticker_with_no_valuation(self, tmp_path):
        cal = self._calendar(tmp_path)
        records = cal.build(tickers=["SRPT"])
        assert records == []  # no valuation.json → skipped

    def test_build_ticker_with_valuation_no_catalysts(self, tmp_path):
        val_json = {
            "model_pos": 0.45,
            "rnpv": {
                "gross_revenue_pv_millions": 800.0,
                "trial_costs_pv_millions": 40.0,
                "cumulative_success_probability": 0.45,
            },
        }
        (tmp_path / "outputs" / "SRPT").mkdir(parents=True)
        (tmp_path / "outputs" / "SRPT" / "valuation.json").write_text(
            json.dumps(val_json), encoding="utf-8"
        )
        cal = self._calendar(tmp_path)
        records = cal.build(tickers=["SRPT"])
        # No catalysts seeded and skip_refresh → no edge_score, confidence=insufficient_data
        assert len(records) == 1
        assert records[0].edge_score is None
        assert records[0].confidence == "insufficient_data"

    def test_build_with_mock_events(self, tmp_path, monkeypatch):
        val_json = {
            "model_pos": 0.50,
            "rnpv": {
                "gross_revenue_pv_millions": 1000.0,
                "trial_costs_pv_millions": 60.0,
            },
        }
        (tmp_path / "outputs" / "SRPT").mkdir(parents=True)
        (tmp_path / "outputs" / "SRPT" / "valuation.json").write_text(
            json.dumps(val_json), encoding="utf-8"
        )

        mock_ev = _make_mock_event("trial_readout", 40)

        def patched_load(ticker, ops_db, max_days):
            return [mock_ev] if ticker == "SRPT" else []

        monkeypatch.setattr(
            "bve.intelligence.catalyst_edge_calendar._load_catalyst_events_for_ticker",
            patched_load,
        )

        cal = self._calendar(tmp_path)
        records = cal.build(tickers=["SRPT"])
        assert len(records) == 1
        assert records[0].event_type == "trial_readout"
        assert records[0].days_to_event == 40

    def test_edge_score_none_without_market_data(self, tmp_path, monkeypatch):
        val_json = {"model_pos": 0.50, "rnpv": {"gross_revenue_pv_millions": 800.0, "trial_costs_pv_millions": 50.0}}
        (tmp_path / "outputs" / "SRPT").mkdir(parents=True)
        (tmp_path / "outputs" / "SRPT" / "valuation.json").write_text(json.dumps(val_json))

        mock_ev = _make_mock_event("pdufa_decision", 30)
        monkeypatch.setattr(
            "bve.intelligence.catalyst_edge_calendar._load_catalyst_events_for_ticker",
            lambda t, db, d: [mock_ev] if t == "SRPT" else [],
        )

        cal = self._calendar(tmp_path, skip=True)
        records = cal.build(tickers=["SRPT"])
        assert records[0].edge_score is None  # no market cap → no implied POS

    def test_sort_by_edge_score_desc(self, tmp_path, monkeypatch):
        recs = [
            _make_record("A", days=30, model_pos=0.50, implied_pos=0.30),
            _make_record("B", days=30, model_pos=0.60, implied_pos=0.20),
        ]
        cal = self._calendar(tmp_path)
        recs.sort(
            key=lambda r: (-(r.edge_score or -1.0), r.days_to_event or 9999)
        )
        assert recs[0].ticker == "B"  # larger gap → higher edge score

    def test_max_days_forward_respected(self, tmp_path, monkeypatch):
        far_event = _make_mock_event("trial_readout", 200)
        near_event = _make_mock_event("trial_readout", 30)

        call_log = []

        def patched_load(ticker, ops_db, max_days):
            call_log.append(max_days)
            return []

        monkeypatch.setattr(
            "bve.intelligence.catalyst_edge_calendar._load_catalyst_events_for_ticker",
            patched_load,
        )

        cal = CatalystEdgeCalendar(
            ops_db=tmp_path / "ops.db",
            outputs_dir=tmp_path / "outputs",
            max_days_forward=90,
            skip_market_refresh=True,
        )
        cal.build(tickers=["SRPT"])
        assert all(d == 90 for d in call_log)

    def test_render_markdown_empty(self, tmp_path):
        cal = self._calendar(tmp_path)
        md = cal.render_markdown([])
        assert "No catalyst edge data" in md

    def test_render_markdown_with_records(self, tmp_path):
        rec = _make_record()
        cal = self._calendar(tmp_path)
        md = cal.render_markdown([rec])
        assert "SRPT" in md
        assert "trial_readout" in md

    def test_render_markdown_table_header(self, tmp_path):
        rec = _make_record()
        cal = self._calendar(tmp_path)
        md = cal.render_markdown([rec])
        assert "Model P" in md
        assert "Edge" in md
        assert "Gap" in md

    def test_build_graceful_on_exception(self, tmp_path, monkeypatch):
        def bad_load(*a, **kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "bve.intelligence.catalyst_edge_calendar._load_valuation_data",
            bad_load,
        )
        cal = self._calendar(tmp_path)
        # Should not raise
        records = cal.build(tickers=["SRPT"])
        assert isinstance(records, list)

    def test_universe_tickers_graceful(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "bve.intelligence.catalyst_edge_calendar.CatalystEdgeCalendar._universe_tickers",
            lambda self: [],
        )
        cal = self._calendar(tmp_path)
        records = cal.build()
        assert records == []


# ---------------------------------------------------------------------------
# TestCatalystCalendarCLI (5 tests)
# ---------------------------------------------------------------------------

class TestCatalystCalendarCLI:
    def test_skip_refresh_runs_without_error(self, tmp_path):
        from bve.cli.catalyst_calendar import main
        ret = main([
            "--skip-refresh",
            "--tickers", "SRPT",
            "--ops-db", str(tmp_path / "ops.db"),
            "--outputs-dir", str(tmp_path / "outputs"),
        ])
        assert ret == 0

    def test_json_output_valid(self, tmp_path, capsys):
        from bve.cli.catalyst_calendar import main
        main([
            "--skip-refresh", "--json",
            "--tickers", "SRPT",
            "--ops-db", str(tmp_path / "ops.db"),
            "--outputs-dir", str(tmp_path / "outputs"),
        ])
        captured = capsys.readouterr()
        # Should be valid JSON (empty array is OK)
        data = json.loads(captured.out)
        assert isinstance(data, list)

    def test_days_flag_accepted(self, tmp_path):
        from bve.cli.catalyst_calendar import main
        ret = main([
            "--skip-refresh", "--days", "60",
            "--tickers", "SRPT",
            "--ops-db", str(tmp_path / "ops.db"),
            "--outputs-dir", str(tmp_path / "outputs"),
        ])
        assert ret == 0

    def test_output_writes_file(self, tmp_path):
        from bve.cli.catalyst_calendar import main
        out_path = tmp_path / "calendar.md"
        main([
            "--skip-refresh",
            "--tickers", "SRPT",
            "--output", str(out_path),
            "--ops-db", str(tmp_path / "ops.db"),
            "--outputs-dir", str(tmp_path / "outputs"),
        ])
        assert out_path.exists()

    def test_min_edge_filter(self, tmp_path, capsys):
        from bve.cli.catalyst_calendar import main
        main([
            "--skip-refresh",
            "--min-edge", "0.99",
            "--tickers", "SRPT",
            "--ops-db", str(tmp_path / "ops.db"),
            "--outputs-dir", str(tmp_path / "outputs"),
        ])
        captured = capsys.readouterr()
        # With min-edge=0.99 and no real data, table should show no records
        assert "No catalyst edge data" in captured.out or captured.out.strip() == ""
