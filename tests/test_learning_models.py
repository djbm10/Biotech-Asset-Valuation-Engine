"""Tests for learning module: calibration, weight_updates, and bias_report."""

from __future__ import annotations

from datetime import date

import pytest

from bve.learning import calibration as cal_module
from bve.learning.bias_report import BiasEntry, BiasReport, BiasReportEngine
from bve.learning.calibration import (
    CalibrationEngine,
    CalibrationRecord,
    CalibrationSummary,
)
from bve.learning.weight_updates import WeightUpdate, WeightUpdateEngine


# ---------------------------------------------------------------------------
# CalibrationRecord
# ---------------------------------------------------------------------------

def test_calibration_record_basic():
    rec = CalibrationRecord(
        record_id="R1",
        asset_id="A1",
        module="pos",
        prediction_date=date(2025, 1, 1),
        predicted_value=0.55,
    )
    assert rec.is_resolved is False
    assert rec.realized_value is None
    assert rec.error is None


# ---------------------------------------------------------------------------
# CalibrationEngine
# ---------------------------------------------------------------------------

def test_calibration_engine_add_and_resolve():
    engine = CalibrationEngine()
    rec = CalibrationRecord(
        record_id="R1",
        asset_id="A1",
        module="pos",
        prediction_date=date(2025, 1, 1),
        predicted_value=0.55,
    )
    engine.add_record(rec)
    resolved = engine.resolve_record("R1", realized_value=0.70)
    assert resolved.is_resolved is True
    assert resolved.realized_value == 0.70
    assert abs(resolved.error - 0.15) < 1e-9
    assert abs(resolved.squared_error - 0.15 ** 2) < 1e-9


def test_calibration_engine_resolve_not_found():
    engine = CalibrationEngine()
    with pytest.raises(ValueError, match="R99"):
        engine.resolve_record("R99", realized_value=0.5)


def test_calibration_engine_summarize_empty():
    engine = CalibrationEngine()
    summary = engine.summarize("pos")
    assert summary.n_resolved == 0
    assert summary.mean_error == 0.0
    assert summary.rmse == 0.0


def test_calibration_engine_summarize_with_data():
    engine = CalibrationEngine()
    for i, (pred, real) in enumerate([(0.50, 0.60), (0.40, 0.50), (0.60, 0.55)]):
        rec = CalibrationRecord(
            record_id=f"R{i}",
            asset_id="A1",
            module="pos",
            prediction_date=date(2025, 1, 1),
            predicted_value=pred,
        )
        engine.add_record(rec)
        engine.resolve_record(f"R{i}", realized_value=real)

    summary = engine.summarize("pos")
    assert summary.n_resolved == 3
    # errors: 0.10, 0.10, -0.05; mean = 0.05
    assert abs(summary.mean_error - 0.05) < 1e-9
    assert summary.rmse > 0


def test_calibration_engine_module_isolation():
    engine = CalibrationEngine()
    pos_rec = CalibrationRecord(
        record_id="R1", asset_id="A1", module="pos",
        prediction_date=date(2025, 1, 1), predicted_value=0.5,
    )
    sales_rec = CalibrationRecord(
        record_id="R2", asset_id="A1", module="peak_sales",
        prediction_date=date(2025, 1, 1), predicted_value=500.0,
    )
    engine.add_record(pos_rec)
    engine.add_record(sales_rec)
    engine.resolve_record("R1", 0.6)
    engine.resolve_record("R2", 550.0)

    pos_summary = engine.summarize("pos")
    sales_summary = engine.summarize("peak_sales")
    assert pos_summary.n_resolved == 1
    assert sales_summary.n_resolved == 1


# ---------------------------------------------------------------------------
# WeightUpdateEngine
# ---------------------------------------------------------------------------

def test_weight_update_engine_propose():
    engine = WeightUpdateEngine()
    update = engine.propose_update("pos", "phase2_base_rate", 0.40, 0.43, "Calibration uplift")
    assert update.approved is False
    assert update.requires_human_review is True
    assert abs(update.delta - 0.03) < 1e-9


def test_weight_update_engine_pending():
    engine = WeightUpdateEngine()
    engine.propose_update("pos", "p1", 0.4, 0.45, "r1")
    engine.propose_update("pos", "p2", 0.5, 0.52, "r2")
    assert len(engine.pending_updates()) == 2


def test_weight_update_engine_approve():
    engine = WeightUpdateEngine()
    update = engine.propose_update("pos", "p1", 0.4, 0.45, "r1")
    approved = engine.approve(update.update_id)
    assert approved.approved is True
    assert engine.pending_updates() == []


def test_weight_update_engine_approve_not_found():
    engine = WeightUpdateEngine()
    with pytest.raises(ValueError):
        engine.approve("nonexistent-id")


# ---------------------------------------------------------------------------
# BiasReportEngine
# ---------------------------------------------------------------------------

def _make_summary(module: str, bias: float, n: int = 10) -> CalibrationSummary:
    import math
    return CalibrationSummary(
        module=module,
        n_resolved=n,
        mean_error=bias,
        rmse=math.sqrt(bias ** 2 + 0.01),
        bias=bias,
    )


def test_bias_report_engine_generates_report():
    engine = BiasReportEngine()
    summaries = [
        _make_summary("pos", bias=0.10),
        _make_summary("peak_sales", bias=-0.15),
        _make_summary("timeline", bias=0.01),
    ]
    report = engine.generate(summaries)
    assert len(report.entries) == 3
    assert report.most_biased_module is not None
    assert 0.0 <= report.overall_bias_score <= 1.0
    assert len(report.recommendations) > 0


def test_bias_report_engine_calibrated_modules():
    engine = BiasReportEngine()
    summaries = [_make_summary("pos", bias=0.01), _make_summary("peak_sales", bias=-0.02)]
    report = engine.generate(summaries)
    for entry in report.entries:
        assert entry.direction == "calibrated"
    assert report.most_biased_module is None


def test_bias_report_engine_empty():
    engine = BiasReportEngine()
    report = engine.generate([])
    assert report.entries == []
    assert report.overall_bias_score == 0.0


def test_bias_entry_direction_optimistic():
    engine = BiasReportEngine()
    summaries = [_make_summary("pos", bias=0.20)]
    report = engine.generate(summaries)
    assert report.entries[0].direction == "optimistic"


def test_bias_entry_direction_pessimistic():
    engine = BiasReportEngine()
    summaries = [_make_summary("pos", bias=-0.20)]
    report = engine.generate(summaries)
    assert report.entries[0].direction == "pessimistic"
